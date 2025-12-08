import os
import json
import nest_asyncio
import requests
import numpy as np
import pandas as pd
from typing import Union, List, Optional, Tuple, Dict, Any, Literal, Callable
from dotenv import load_dotenv
from supabase import create_client, Client
from agents import Agent, Runner, ModelSettings
from pydantic import BaseModel
from tools.format_rag import format_experience, format_lodging, format_transport

# Allow nested event loops (useful in notebooks/scripts)
nest_asyncio.apply()
load_dotenv()

# ---------------------------------------
# 1. Define a Pydantic model matching our narrative structure
# ---------------------------------------
class NarrativeQuery(BaseModel):
    Supplier_Name: Optional[str]
    General_Description: Optional[str]
    Service_Details: Optional[str]
    Supplier_Information: Optional[str]
    Location: Optional[str]
    Facilities: Optional[str]
    State_Code: Optional[Literal[
        "HGO", "ROO", "NAY", "BCS", "GTO", "TAB", "BCN", "YUC", "EMX", "CHI", 
        "JAL", "MXC", "VCZ", "CAM", "PBL", "QRO", "OAX", "MCH", "CHP", "TLX",
        "SIN", "AGS", "COA", "COL", "DGO", "GRO", "MOR", "NLE", "SLP", "SON", 
        "TMS", "ZAC"
    ]] = None

# ---------------------------------------
# 2. Set up an Agent to transform the user query into structured output
# ---------------------------------------
def format_structured_narrative_to_text(narrative: NarrativeQuery) -> str:
    lines = []
    if narrative.Supplier_Name:
        lines.append(f"Supplier Name: {narrative.Supplier_Name.strip()}")
    if narrative.General_Description:
        lines.append(f"General Description: {narrative.General_Description.strip()}")
    if narrative.Service_Details:
        lines.append(f"Service Details: {narrative.Service_Details.strip()}")
    if narrative.Supplier_Information:
        lines.append(f"Supplier Information: {narrative.Supplier_Information.strip()}")
    if narrative.Location:
        lines.append(f"Location: {narrative.Location.strip()}")
    if narrative.Facilities:
        lines.append(f"Facilities: {narrative.Facilities.strip()}")
    return "\n".join(lines)

# ---------------------------------------
# 3. Generate embedding for the refined query using the Jina API
# ---------------------------------------
def get_embeddings(texts: Union[str, List[str]]) -> List[List[float]]:
    if isinstance(texts, str):
        texts = [texts]
    url = "https://api.jina.ai/v1/embeddings"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('JINA_API_KEY')}"
    }
    data = {
        "model": "jina-clip-v2",
        "dimensions": 1024,
        "normalized": True,
        "embedding_type": "float",
        "input": [{"text": t} for t in texts]
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return [item["embedding"] for item in result["data"]]
    except requests.RequestException as e:
        print("Error fetching embeddings:", e)
        return [None for _ in texts]

def process_user_query(user_query: str, table: str) -> Tuple[str, List[Dict[str, Any]], str]:
    """
    Process a user query for a specified table (experiences, lodging, or transport), transform it into a structured narrative, and search for similar entries.
    
    Args:
        user_query: The user's search query text
        table: The data source table to query ('experiences', 'lodging', 'transport')
        
    Returns:
        A tuple containing (formatted_results, supabase_response, formatted_results_for_ai)
    """
    # Determine instructions based on the specified table
    table_instructions = {
        "experiences": """
You are a structured assistant specialized in tourism experiences search. Given a user query, return a JSON object to be used for vector embedding with the following fields exactly:
- Supplier_Name: Include supplier_name if the user query mentions it.
- General_Description: A brief summary of the experience.
- Service_Details: Include fullServiceDescription, serviceDescription, serviceType, destinationName if the user query mentions it.
- Supplier_Information: Any supplier or group information if the user query mentions it.
- Location: Use location_address and city if the user query mentions it.
- Facilities: Any amenities or features if the user query mentions it.
- State_Code: Include the state code for the experience. [
        "HGO", "ROO", "NAY", "BCS", "GTO", "TAB", "BCN", "YUC", "EMX", "CHI", 
        "JAL", "MXC", "VCZ", "CAM", "PBL", "QRO", "OAX", "MCH", "CHP", "TLX",
        "SIN", "AGS", "COA", "COL", "DGO", "GRO", "MOR", "NLE", "SLP", "SON", 
        "TMS", "ZAC"    ]

IMPORTANT: If a piece of information is not present in the user query leave the field blank so we dont match with other experiences.
""",
        "transport": """
You are a structured assistant specialized in transport search. Given a user query, return a JSON object with the following fields exactly:
- Supplier_Name: Include supplier_name if the user query mentions it.
- General_Description: A brief summary of the transport service.
- Service_Details: Include full_service_description, serviceNotes, duration, serviceType, destinationName if the user query mentions it.
- Supplier_Information: Any supplier or group information if the user query mentions it.
- State_Code: Include the state code for the experience. [
        "HGO", "ROO", "NAY", "BCS", "GTO", "TAB", "BCN", "YUC", "EMX", "CHI", 
        "JAL", "MXC", "VCZ", "CAM", "PBL", "QRO", "OAX", "MCH", "CHP", "TLX",
        "SIN", "AGS", "COA", "COL", "DGO", "GRO", "MOR", "NLE", "SLP", "SON", 
        "TMS", "ZAC"    ]
IMPORTANT: If a piece of information is not present in the user query leave the field blank so we dont match with other transport services.
"""
    }
    if table not in table_instructions:
        raise ValueError(f"Unsupported table: {table}")
    # Create a specialized agent for this table
    specialized_agent = Agent(
        name=f"{table}_NarrativeQueryAgent",
        instructions=table_instructions[table],
        model="gpt-4.1-mini-2025-04-14",
        output_type=NarrativeQuery,
        model_settings=ModelSettings(
            temperature=0.3,
            max_tokens=600,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )
    )
    structured_result = Runner.run_sync(specialized_agent, user_query)
    structured_narrative: NarrativeQuery = structured_result.final_output
    State_Code = structured_narrative.State_Code
    mexico_state_info = {
    'HGO': 'Hidalgo',
    'ROO': 'Quintana Roo',
    'NAY': 'Nayarit',
    'BCS': 'Baja California Sur',
    'GTO': 'Guanajuato Area',
    'TAB': 'Tabasco',
    'BCN': 'Baja California',
    'YUC': 'Yucatan',
    'EMX': 'Estado de Mexico',
    'CHI': 'Chiuahua',            # Note: Standard code often CHH, spelling usually Chihuahua
    'JAL': 'Jalisco',
    'MXC': 'Mexico Area',         # Note: Standard code often CMX for Ciudad de México
    'VCZ': 'Veracruz Area',       # Note: Standard code often VER
    'CAM': 'Campeche Area',
    'PBL': 'Puebla Area',
    'QRO': 'Queretaro Area',
    'OAX': 'Oaxaca',
    'MCH': 'Michoacan',
    'CHP': 'Chiapas',
    'TLX': 'Tlaxcala Area',
    'SIN': 'Sinaloa',
    # --- Added States ---
    'AGS': 'Aguascalientes',
    'COA': 'Coahuila',
    'COL': 'Colima',
    'DGO': 'Durango',
    'GRO': 'Guerrero',
    'MOR': 'Morelos',
    'NLE': 'Nuevo León',
    'SLP': 'San Luis Potosí',
    'SON': 'Sonora',
    'TMS': 'Tamaulipas',
    'ZAC': 'Zacatecas'
}

# Get the state name for GTO code
    state_name = mexico_state_info.get(State_Code)
    # Format the structured narrative into text
    refined_query_text = format_structured_narrative_to_text(structured_narrative)
    
    # Generate embedding for the refined query
    refined_embedding = get_embeddings(refined_query_text)[0]
    
    # Debug: Check that every element in the embedding is a number
    if not all(isinstance(x, (int, float)) for x in refined_embedding):
        print("Warning: Non-numeric tokens found in the embedding!")
        # Filter out non-numeric values
        refined_embedding = [float(x) for x in refined_embedding if isinstance(x, (int, float))]
    
    # Convert the refined embedding into a vector literal string
    embedding_literal = "[" + ",".join(str(x) for x in refined_embedding) + "]"
    
    # Define a threshold for vector similarity relevance
    SIMILARITY_THRESHOLD = 0.45  # Adjust this value based on your needs
    match_type = None
    
    # Only run state-specific query if state_name is not None
    if state_name:
        # First, try to find experiences that match the state name
        sql_query = f"""
        SELECT id::text, narrative_text, city, full_json, vector_embedding <=> '{embedding_literal}'::vector AS distance
        FROM {table}
        WHERE LOWER(destination_name) LIKE LOWER('%{state_name}%')
        ORDER BY vector_embedding <=> '{embedding_literal}'::vector
        LIMIT 10;
        """
        match_type = "state"
    else:
        # If no state_name, run without state filter
        sql_query = f"""
        SELECT id::text, narrative_text, city, full_json, vector_embedding <=> '{embedding_literal}'::vector AS distance
        FROM {table}
        ORDER BY vector_embedding <=> '{embedding_literal}'::vector
        LIMIT 10;
        """
        match_type = "no_state"
        
    return sql_query, match_type, embedding_literal

def process_user_query(user_query: str, table: str, executor: Optional[Callable[[str], Any]] = None) -> Tuple[str, List[Dict[str, Any]], str]:
    """
    Process a user query for a specified table (experiences, lodging, or transport), transform it into a structured narrative, and search for similar entries.
    
    Args:
        user_query: The user's search query text
        table: The data source table to query ('experiences', 'lodging', 'transport')
        executor: Optional function to execute SQL query. If None, uses direct Supabase client.
        
    Returns:
        A tuple containing (formatted_results, supabase_response, formatted_results_for_ai)
    """
    # Generate the SQL query
    sql_query, match_type, embedding_literal = generate_rag_query(user_query, table)
    
    class MockResponse:
        def __init__(self, data):
            self.data = data

    if executor:
        # Use provided executor (e.g. MCP)
        # Expect executor to return list of dicts
        # If executor is async, we might need to handle that. 
        # But process_user_query is sync. 
        # We'll assume executor is a sync wrapper or we run it sync.
        # Actually, mcp_execute_sql_raw is async.
        # We might need to run it in an event loop if called from sync code.
        # But ruto_agent.py calls this from async functions.
        # So maybe process_user_query should be async?
        # It uses Runner.run_sync which is sync.
        # Let's assume executor is sync for now, or we handle async in ruto_agent.
        
        # Wait, if ruto_agent calls this, and passes an async function, we can't await it here easily if this function is sync.
        # I should probably make process_user_query async.
        pass
    
    # For now, let's keep it sync and assume executor handles the async part (e.g. using asyncio.run or similar if needed)
    # OR, better, make process_user_query async.
    # But that requires changing signatures in ruto_agent.py too.
    
    # Let's check ruto_agent.py again.
    # It calls `formatted_results, search_results, match_type = process_user_query(...)` inside `async def get_experiences`.
    # So making process_user_query async is fine.
    
    # But Runner.run_sync is used inside.
    
    # Let's stick to the plan of modifying process_user_query to accept executor.
    # If executor is async, we can't call it directly here without await.
    
    # Maybe I should just return the SQL query from here and let the caller execute it?
    # But there is fallback logic here (if match_type == "state").
    
    # Okay, I will make process_user_query async.
    # And I will change Runner.run_sync to await Runner.run(...)
    
    # But wait, RAG.py imports Runner.
    
    # Let's try to keep it simple.
    # If I make it async, I need to update all calls.
    
    # Alternative:
    # Just return the generated SQL and let the caller handle the execution and fallback logic?
    # That duplicates logic in ruto_agent.py.
    
    # Let's make process_user_query async.
    
    # But first, let's update the code to use executor.
    
    if executor:
        if asyncio.iscoroutinefunction(executor):
             # This is tricky if we are in a sync function.
             # But we are in a sync function (def process_user_query).
             pass
             
    # Let's assume for now I will use a sync wrapper for the executor in ruto_agent.py
    # Or I can use nest_asyncio which is already applied in RAG.py
    
    response = None
    if executor:
        try:
            data = executor(sql_query)
            if asyncio.iscoroutine(data):
                import asyncio
                loop = asyncio.get_event_loop()
                data = loop.run_until_complete(data)
            response = MockResponse(data)
        except Exception as e:
            print(f"Error executing query with executor: {e}")
            response = MockResponse([])
    else:
        # Set up Supabase client
        SUPABASE_URL = os.getenv("SUPABASE_URL")
        SUPABASE_KEY = os.getenv("SUPABASE_KEY")
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Execute the SQL query
        response = supabase.rpc("run_sql", {"query": sql_query}).execute()
    
    # If we used state filter and got poor results, try fallback (only if match_type was state)
    SIMILARITY_THRESHOLD = 0.45
    if match_type == "state":
        if not (response.data and len(response.data) >= 3 and response.data[0]['distance'] < SIMILARITY_THRESHOLD):
            # Fallback to no state filter
            sql_query = f"""
            SELECT id::text, narrative_text, city, full_json, vector_embedding <=> '{embedding_literal}'::vector AS distance
            FROM {table}
            ORDER BY vector_embedding <=> '{embedding_literal}'::vector
            LIMIT 10;
            """
            if executor:
                data = executor(sql_query)
                if asyncio.iscoroutine(data):
                    import asyncio
                    loop = asyncio.get_event_loop()
                    data = loop.run_until_complete(data)
                response = MockResponse(data)
            else:
                response = supabase.rpc("run_sql", {"query": sql_query}).execute()
            match_type = "no_state"

    # Format each result using the appropriate formatter from format_rag.py
    formatted_results = []
    for result in response.data:
        if table == "experiences":
            formatted_results.append(format_experience(result))
        elif table == "lodging":
            formatted_results.append(format_lodging(result))
        elif table == "transport":
            formatted_results.append(format_transport(result))
    
    # Join all formatted results into a single string
    formatted_output = "\n\n".join(formatted_results)
    
    return formatted_output, response.data, match_type

def generate_rag_query(user_query: str, table: str) -> Tuple[str, str, str]:
    """
    Generate a SQL query for vector search based on user query.
    Returns: (sql_query, match_type, embedding_literal)
    """
    # Determine instructions based on the specified table
    table_instructions = {
        "experiences": """
You are a structured assistant specialized in tourism experiences search. Given a user query, return a JSON object to be used for vector embedding with the following fields exactly:
- Supplier_Name: Include supplier_name if the user query mentions it.
- General_Description: A brief summary of the experience.
- Service_Details: Include fullServiceDescription, serviceDescription, serviceType, destinationName if the user query mentions it.
- Supplier_Information: Any supplier or group information if the user query mentions it.
- Location: Use location_address and city if the user query mentions it.
- Facilities: Any amenities or features if the user query mentions it.
- State_Code: Include the state code for the experience. [
        "HGO", "ROO", "NAY", "BCS", "GTO", "TAB", "BCN", "YUC", "EMX", "CHI", 
        "JAL", "MXC", "VCZ", "CAM", "PBL", "QRO", "OAX", "MCH", "CHP", "TLX",
        "SIN", "AGS", "COA", "COL", "DGO", "GRO", "MOR", "NLE", "SLP", "SON", 
        "TMS", "ZAC"
    ]

IMPORTANT: If a piece of information is not present in the user query leave the field blank so we dont match with other experiences.
""",
        "transport": """
You are a structured assistant specialized in transport search. Given a user query, return a JSON object with the following fields exactly:
- Supplier_Name: Include supplier_name if the user query mentions it.
- General_Description: A brief summary of the transport service.
- Service_Details: Include full_service_description, serviceNotes, duration, serviceType, destinationName if the user query mentions it.
- Supplier_Information: Any supplier or group information if the user query mentions it.
- State_Code: Include the state code for the experience. [
        "HGO", "ROO", "NAY", "BCS", "GTO", "TAB", "BCN", "YUC", "EMX", "CHI", 
        "JAL", "MXC", "VCZ", "CAM", "PBL", "QRO", "OAX", "MCH", "CHP", "TLX",
        "SIN", "AGS", "COA", "COL", "DGO", "GRO", "MOR", "NLE", "SLP", "SON", 
        "TMS", "ZAC"    ]
IMPORTANT: If a piece of information is not present in the user query leave the field blank so we dont match with other transport services.
"""
    }
    if table not in table_instructions:
        raise ValueError(f"Unsupported table: {table}")
    # Create a specialized agent for this table
    specialized_agent = Agent(
        name=f"{table}_NarrativeQueryAgent",
        instructions=table_instructions[table],
        model="gpt-4.1-mini-2025-04-14",
        output_type=NarrativeQuery,
        model_settings=ModelSettings(
            temperature=0.3,
            max_tokens=600,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )
    )
    structured_result = Runner.run_sync(specialized_agent, user_query)
    structured_narrative: NarrativeQuery = structured_result.final_output
    State_Code = structured_narrative.State_Code
    mexico_state_info = {
    'HGO': 'Hidalgo',
    'ROO': 'Quintana Roo',
    'NAY': 'Nayarit',
    'BCS': 'Baja California Sur',
    'GTO': 'Guanajuato Area',
    'TAB': 'Tabasco',
    'BCN': 'Baja California',
    'YUC': 'Yucatan',
    'EMX': 'Estado de Mexico',
    'CHI': 'Chiuahua',            # Note: Standard code often CHH, spelling usually Chihuahua
    'JAL': 'Jalisco',
    'MXC': 'Mexico Area',         # Note: Standard code often CMX for Ciudad de México
    'VCZ': 'Veracruz Area',       # Note: Standard code often VER
    'CAM': 'Campeche Area',
    'PBL': 'Puebla Area',
    'QRO': 'Queretaro Area',
    'OAX': 'Oaxaca',
    'MCH': 'Michoacan',
    'CHP': 'Chiapas',
    'TLX': 'Tlaxcala Area',
    'SIN': 'Sinaloa',
    # --- Added States ---
    'AGS': 'Aguascalientes',
    'COA': 'Coahuila',
    'COL': 'Colima',
    'DGO': 'Durango',
    'GRO': 'Guerrero',
    'MOR': 'Morelos',
    'NLE': 'Nuevo León',
    'SLP': 'San Luis Potosí',
    'SON': 'Sonora',
    'TMS': 'Tamaulipas',
    'ZAC': 'Zacatecas'
}

# Get the state name for GTO code
    state_name = mexico_state_info.get(State_Code)
    # Format the structured narrative into text
    refined_query_text = format_structured_narrative_to_text(structured_narrative)
    
    # Generate embedding for the refined query
    refined_embedding = get_embeddings(refined_query_text)[0]
    
    # Debug: Check that every element in the embedding is a number
    if not all(isinstance(x, (int, float)) for x in refined_embedding):
        print("Warning: Non-numeric tokens found in the embedding!")
        # Filter out non-numeric values
        refined_embedding = [float(x) for x in refined_embedding if isinstance(x, (int, float))]

    # Convert the refined embedding into a vector literal string
    embedding_literal = "[" + ",".join(str(x) for x in refined_embedding) + "]"
    
    # Define a threshold for vector similarity relevance
    SIMILARITY_THRESHOLD = 0.45  # Adjust this value based on your needs
    match_type = None
    
    # Only run state-specific query if state_name is not None
    if state_name:
        # First, try to find experiences that match the state name
        sql_query = f"""
        SELECT id::text, narrative_text, city, full_json, vector_embedding <=> '{embedding_literal}'::vector AS distance
        FROM {table}
        WHERE LOWER(destination_name) LIKE LOWER('%{state_name}%')
        ORDER BY vector_embedding <=> '{embedding_literal}'::vector
        LIMIT 10;
        """
        match_type = "state"
    else:
        # If no state_name, run without state filter
        sql_query = f"""
        SELECT id::text, narrative_text, city, full_json, vector_embedding <=> '{embedding_literal}'::vector AS distance
        FROM {table}
        ORDER BY vector_embedding <=> '{embedding_literal}'::vector
        LIMIT 10;
        """
        match_type = "no_state"
        
    return sql_query, match_type, embedding_literal

# Example usage:
# user_query = "I'm looking for a hiking experience in Oaxaca"
# structured_narrative, search_results, formatted_results = process_user_query(user_query, "experiences")
# print(structured_narrative)
# print(formatted_results)