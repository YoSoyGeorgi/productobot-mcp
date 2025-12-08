import os
import json
import nest_asyncio
import requests
import numpy as np
import pandas as pd
import asyncio
from typing import Union, List, Optional, Tuple, Dict, Any, Literal, Callable
from dotenv import load_dotenv
from supabase import create_client, Client
from agents import Agent, Runner, ModelSettings
from pydantic import BaseModel
from tools.format_rag import format_lodging

# Allow nested event loops (useful in notebooks/scripts)
nest_asyncio.apply()
load_dotenv()

# ---------------------------------------
# 1. Define a Pydantic model matching our narrative structure
# ---------------------------------------
class NarrativeQuery(BaseModel):
    Name: Optional[str]
    Location: Optional[str]
    Description: Optional[str]
    Type: Optional[str]
    Services: Optional[str]
    Tags: Optional[str]
    Price_Range: Optional[Literal["low cost", "comfort", "luxury"]]
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
    def safe_field(val):
        return val.strip() if val and isinstance(val, str) and val.strip() else "NULL"

    lines = []
    lines.append(f"Name: {safe_field(narrative.Name)}")
    lines.append(f"Location: {safe_field(narrative.Location)}")
    lines.append(f"Description: {safe_field(narrative.Description)}")
    lines.append(f"Type: {safe_field(narrative.Type)}")
    lines.append(f"Services: {safe_field(getattr(narrative, 'Services', None))}")
    lines.append(f"Tags: {safe_field(getattr(narrative, 'Tags', None))}")
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

def process_user_lodging_query(user_query: str, executor: Optional[Callable[[str], Any]] = None) -> Tuple[str, List[Dict[str, Any]], str]:
    """
    Process a user query for a specified table (experiences, lodging, or transport), transform it into a structured narrative, and search for similar entries.
    
    Args:
        user_query: The user's search query text
        executor: Optional function to execute SQL query. If None, uses direct Supabase client.
        
    Returns:
        A tuple containing (formatted_results, supabase_response, formatted_results_for_ai)
    """
    # Configuration for dynamic filters
    FILTER_CONFIG = {
        'state_name': {
            'field': 'destination_name',
            'operator': 'LIKE',
            'case_sensitive': False,
            'wildcard': True
        },
        'price_range': {
            'field': 'price_range',
            'operator': '=',
            'case_sensitive': True,
            'wildcard': False
        },
        'name': {
            'field': 'supplier_name',
            'operator': 'LIKE',
            'case_sensitive': False,
            'wildcard': True
        }
    }
    
    # Determine instructions based on the specified table
    table_instructions = """
    You are a structured assistant specialized in lodging search. Given a user query, return a JSON object with the following fields exactly:
    - Name: The name of the lodging.
    - Location: Use location_address and city if the user query mentions it.
    - Description: A brief description of the lodging.
    - Type: The type of lodging.
    - Services: The services offered by the lodging.
    - Tags: The tags associated with the lodging.
    - Price_Range: The price range of the lodging. [low cost, comfort, luxury]
    - State_Code: The state code of the lodging. [
        "HGO", "ROO", "NAY", "BCS", "GTO", "TAB", "BCN", "YUC", "EMX", "CHI", 
        "JAL", "MXC", "VCZ", "CAM", "PBL", "QRO", "OAX", "MCH", "CHP", "TLX",
        "SIN", "AGS", "COA", "COL", "DGO", "GRO", "MOR", "NLE", "SLP", "SON", 
        "TMS", "ZAC"    ]
    IMPORTANT: If a piece of information is not present in the user query leave the field blank so we dont match with other lodging.
    """
    # Create a specialized agent for this table
    specialized_agent = Agent(
        name=f"Lodging_NarrativeQueryAgent",
        instructions=table_instructions,
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
    price_range = structured_narrative.Price_Range
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
    
    # Set up Supabase client
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Define a threshold for vector similarity relevance
    SIMILARITY_THRESHOLD = 0.45  # Adjust this value based on your needs
    
    # Build dynamic filters based on available data
    def build_dynamic_query(embedding_literal: str, filters: Dict[str, Any] = None, limit: int = 10) -> str:
        """Build a dynamic SQL query with optional filters"""
        base_query = f"""
        SELECT id::text, narrative_text, city, full_json, vector_embedding <=> '{embedding_literal}'::vector AS distance
        FROM lodging
        """
        
        where_clauses = []
        if filters:
            for filter_key, filter_value in filters.items():
                if filter_value is not None and filter_key in FILTER_CONFIG:
                    config = FILTER_CONFIG[filter_key]
                    field = config['field']
                    operator = config['operator']
                    case_sensitive = config['case_sensitive']
                    wildcard = config['wildcard']
                    
                    # Build the condition based on configuration
                    if operator == 'LIKE' and wildcard:
                        if case_sensitive:
                            condition = f"{field} LIKE '%{filter_value}%'"
                        else:
                            condition = f"LOWER({field}) LIKE LOWER('%{filter_value}%')"
                    elif operator == '=':
                        if case_sensitive:
                            condition = f"{field} = '{filter_value}'"
                        else:
                            condition = f"LOWER({field}) = LOWER('{filter_value}')"
                    else:
                        # Handle other operators as needed
                        condition = f"{field} {operator} '{filter_value}'"
                    
                    where_clauses.append(condition)
        
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)
        
        base_query += f"""
        ORDER BY vector_embedding <=> '{embedding_literal}'::vector
        LIMIT {limit};
        """
        
        return base_query
    
    # Define progressive fallback strategy
    def get_best_results(embedding_literal: str, structured_narrative: NarrativeQuery, supabase_client: Client) -> Tuple[Any, str]:
        """Try different filter combinations with progressive fallback"""
        
        class MockResponse:
            def __init__(self, data):
                self.data = data

        # Extract available filters from structured narrative
        available_filters = {
            'state_name': state_name,
            'price_range': price_range,
            'name': structured_narrative.Name,
        }
        
        # Define filter strategies in order of preference (most specific to least specific)
        filter_strategies = [
            # Most specific: all available filters
            {k: v for k, v in available_filters.items() if v is not None},
            
            # State + price_range (current logic)
            {k: v for k, v in available_filters.items() if k in ['state_name', 'price_range'] and v is not None},
            
            # State only
            {k: v for k, v in available_filters.items() if k == 'state_name' and v is not None},
            
            # Price range only
            {k: v for k, v in available_filters.items() if k == 'price_range' and v is not None},
            
            # Name only
            {k: v for k, v in available_filters.items() if k == 'name' and v is not None},
            
            # No filters (fallback)
            {}
        ]
        
        # Try each strategy until we get satisfactory results
        for i, filters in enumerate(filter_strategies):
            if not filters and i == 0:  # Skip empty filters on first iteration
                continue
                
            sql_query = build_dynamic_query(embedding_literal, filters)
            
            if executor:
                data = executor(sql_query)
                # Handle async executor if needed
                if asyncio.iscoroutine(data):
                    loop = asyncio.get_event_loop()
                    data = loop.run_until_complete(data)
                response = MockResponse(data)
            else:
                response = supabase_client.rpc("run_sql", {"query": sql_query}).execute()
            
            # Determine match type based on filters used
            if not filters:
                match_type = "no_filters"
            elif 'state_name' in filters and 'price_range' in filters:
                match_type = "state_and_price"
            elif 'state_name' in filters:
                match_type = "state_only"
            elif 'price_range' in filters:
                match_type = "price_only"
            else:
                match_type = f"filtered_by_{'_'.join(filters.keys())}"
            
            # Check if results are satisfactory
            if (response.data and 
                len(response.data) >= 3 and 
                response.data[0]['distance'] < SIMILARITY_THRESHOLD):
                return response, match_type
            
            # If this is the last strategy or we have some results, return what we have
            if i == len(filter_strategies) - 1 or (response.data and len(response.data) > 0):
                return response, match_type
        
        # Fallback: return empty response
        sql_query = build_dynamic_query(embedding_literal)
        if executor:
            data = executor(sql_query)
            if asyncio.iscoroutine(data):
                loop = asyncio.get_event_loop()
                data = loop.run_until_complete(data)
            return MockResponse(data), "fallback"
        else:
            return supabase_client.rpc("run_sql", {"query": sql_query}).execute(), "fallback"
    
    # Get the best results using the dynamic approach
    response, match_type = get_best_results(embedding_literal, structured_narrative, supabase)
    
    # Format each result using the appropriate formatter from format_rag.py
    formatted_results = []
    for result in response.data:
        formatted_results.append(format_lodging(result))
    
    # Join all formatted results into a single string
    formatted_output = "\n\n".join(formatted_results)
    
    return formatted_output, response.data, match_type