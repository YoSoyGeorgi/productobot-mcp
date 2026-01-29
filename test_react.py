import asyncio
import os
from dotenv import load_dotenv
import logging

# Disable excessive logging for the test
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

# Load environment variables
load_dotenv()

import sys
from pathlib import Path
# Add the agent directory to sys.path so it can find 'tools'
agent_path = Path(__file__).parent / "agent"
sys.path.append(str(agent_path)) 

from agent.ruto_agent import chat

async def test_react_agent():
    print("\n=== Testing ProductoBot ReAct Architecture ===\n")
    
    test_queries = [
        "¿Cómo puedo ir de CDMX a Puebla?"
    ]
    """
    "¿Qué tal está el clima en Cancún hoy?",
    "Necesito un hotel en Ciudad de México cerca del centro",
    "¿Cómo puedo ir de CDMX a Puebla?"
    "Busco una experiencia de senderismo en Oaxaca que sea barata"
    """
    
    for query in test_queries:
        print(f"\033[92mUser:\033[0m {query}")
        response = await chat(query, first_name="Tester")
        print(f"\033[94mProductoBot:\033[0m {response}\n")
        print("-" * 50 + "\n")

if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not found in environment.")
    else:
        asyncio.run(test_react_agent())
