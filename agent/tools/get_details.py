import os
from dotenv import load_dotenv
from supabase import create_client, Client
from pydantic import BaseModel
import json


load_dotenv()

def get_details(id: str, table: str) -> str:
    
    # Set up Supabase client
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Direct query without using run_sql RPC
    response = supabase.table(table).select("full_json").eq("id", id).limit(1).execute()
    
    if not response.data or len(response.data) == 0:
        return f"No data found for ID: {id}"
    
    # Return the JSON data
    return json.dumps(response.data[0]['full_json'])