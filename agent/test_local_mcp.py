import asyncio
import os
from dotenv import load_dotenv
from tools.mcp_client import mcp_query_nl_to_sql
from ruto_agent import chat

async def main():
    import sys
    # Fix encoding for Windows console
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
    
    load_dotenv()
    print("MCP_SERVER_URL:", os.environ.get("MCP_SERVER_URL"))
    print("SUPABASE_ACCESS_TOKEN set:", bool(os.environ.get("SUPABASE_ACCESS_TOKEN")))

    prompt = "Actividades en yucatan"
    print("\nTesting raw MCP call...")
    try:
        text = await mcp_query_nl_to_sql(prompt, access_token=os.environ.get("SUPABASE_ACCESS_TOKEN"))
        print("MCP response:\n", text)
    except Exception as e:
        print("MCP error:", e)

    print("\nTesting chat() flow (MCP preferred, fallback to agents)...")
    resp = await chat(query=prompt, channel_id="local", thread_ts="test", chatbot_status="on", first_name="Tester")
    print("Chat response:\n", resp)

if __name__ == "__main__":
    asyncio.run(main())
