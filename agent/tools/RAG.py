import os
import json
import nest_asyncio
import requests
import numpy as np
import pandas as pd
from typing import Union, List, Optional, Tuple, Dict, Any
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
    General_Description: Optional[str]
    Service_Details: Optional[str]
    Supplier_Information: Optional[str]
    Tariff_Information: Optional[str]
    Location: Optional[str]
    Facilities: Optional[str]
    Availability: Optional[str]
    Age_Restrictions: Optional[str]
    Operational_Info: Optional[str]

# ---------------------------------------
# 2. Set up an Agent to transform the user query into structured output
# ---------------------------------------
def format_structured_narrative_to_text(narrative: NarrativeQuery) -> str:
    lines = []
    if narrative.General_Description:
        lines.append(f"General Description: {narrative.General_Description.strip()}")
    if narrative.Service_Details:
        lines.append(f"Service Details: {narrative.Service_Details.strip()}")
    if narrative.Supplier_Information:
        lines.append(f"Supplier Information: {narrative.Supplier_Information.strip()}")
    if narrative.Tariff_Information:
        lines.append(f"Tariff Information: {narrative.Tariff_Information.strip()}")
    if narrative.Location:
        lines.append(f"Location: {narrative.Location.strip()}")
    if narrative.Facilities:
        lines.append(f"Facilities: {narrative.Facilities.strip()}")
    if narrative.Availability:
        lines.append(f"Availability: {narrative.Availability.strip()}")
    if narrative.Age_Restrictions:
        lines.append(f"Age Restrictions: {narrative.Age_Restrictions.strip()}")
    if narrative.Operational_Info:
        lines.append(f"Operational Info: {narrative.Operational_Info.strip()}")
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
You are a structured assistant specialized in tourism experiences search. Given a user query, return a JSON object with the following fields exactly:
- General_Description: A brief summary of the experience.
- Service_Details: Include fullServiceDescription, serviceDescription, serviceType, destinationName.
- Supplier_Information: Any supplier or group information.
- Tariff_Information: Include pricingYear, tariffProcess, productReady if applicable.
- Location: Use location_address and city.
- Facilities: Any amenities or features.
- Availability: Use availability_response_time.
- Age_Restrictions: Include min/max adult, child, and infant ages.
- Operational_Info: Any other operational notes.
If a piece of information is not present, leave the field blank.
""",
        "lodging": """
You are a structured assistant specialized in lodging search. Given a user query, return a JSON object with the following fields exactly:
- General_Description: A brief summary of the accommodation including type, beds, views, etc.
- Service_Details: Include accommodationType, availableFood, facilitiesServices, numRooms.
- Location: Use location_address and city.
- Availability: Include available_days and availability_response_time.
- Age_Restrictions: Include min/max adult, child, and infant ages if mentioned.
- Operational_Info: Any additional notes or tags.
If a piece of information is not present, leave the field blank.
""",
        "transport": """
You are a structured assistant specialized in transport search. Given a user query, return a JSON object with the following fields exactly:
- General_Description: A brief summary of the transport service.
- Service_Details: Include full_service_description, serviceNotes, duration, serviceType, destinationName.
- Availability: Include available_days and availability_response_time.
- Age_Restrictions: Include min/max adult, child, and infant ages if mentioned.
- Operational_Info: Include max_persons, tags, supplier_name or supplier_group if applicable.
If a piece of information is not present, leave the field blank.
"""
    }
    if table not in table_instructions:
        raise ValueError(f"Unsupported table: {table}")
    # Create a specialized agent for this table
    specialized_agent = Agent(
        name=f"{table}_NarrativeQueryAgent",
        instructions=table_instructions[table],
        model="gpt-4o-mini",
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
    
    # Build the SQL query using the embedding literal for the specified table
    # Now include full_json column
    sql_query = f"""
    SELECT id::text, narrative_text, city, full_json, vector_embedding <=> '{embedding_literal}'::vector AS distance
    FROM {table}
    ORDER BY vector_embedding <=> '{embedding_literal}'::vector
    LIMIT 10;
    """
    
    # Execute the SQL query via the RPC function
    response = supabase.rpc("run_sql", {"query": sql_query}).execute()
    
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
    
    return formatted_output, response.data

# Example usage:
# user_query = "I'm looking for a hiking experience in Oaxaca"
# structured_narrative, search_results, formatted_results = process_user_query(user_query, "experiences")
# print(structured_narrative)
# print(formatted_results)