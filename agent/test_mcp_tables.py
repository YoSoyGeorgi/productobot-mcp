import asyncio
import os
from dotenv import load_dotenv
from tools.mcp_client import mcp_query_nl_to_sql

async def main():
    load_dotenv()
    
    # Test querying for all available tables
    queries = [
        "Muéstrame todas las tablas",
        "Qué datos hay disponibles?",
        "Lista las primeras filas de la tabla public",
    ]
    
    for query in queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        try:
            response = await mcp_query_nl_to_sql(query, access_token=os.environ.get("SUPABASE_ACCESS_TOKEN"))
            print(response)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
