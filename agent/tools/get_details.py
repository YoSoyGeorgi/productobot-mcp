import os
from dotenv import load_dotenv
from supabase import create_client, Client
from pydantic import BaseModel


load_dotenv()

def get_details(id: str, table: str) -> str:
    
    # Set up Supabase client
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Build the SQL query using the embedding literal for the specified table
    # Cast full_json to TEXT to match the expected return type
    sql_query = f"""
    SELECT full_json::TEXT
    FROM {table}
    WHERE id = '{id}'
    LIMIT 1;
    """
    # Execute the SQL query via the RPC function
    response = supabase.rpc("run_sql", {"query": sql_query}).execute()
    
    return response.data[0]['full_json']