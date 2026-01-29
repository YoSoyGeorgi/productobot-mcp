import asyncio
import os
import time
from dotenv import load_dotenv
import logging
from pathlib import Path
import sys

# Load environment variables
load_dotenv()

# Add the agent directory to sys.path
agent_path = Path(__file__).parent / "agent"
sys.path.append(str(agent_path))

from agent.ruto_agent import productobot_agent, UserInfoContext
from agents import Runner

async def test_metrics():
    context = UserInfoContext(first_name="Tester")
    input_items = [{"content": "Busco una experiencia de senderismo en Oaxaca que sea barata", "role": "user"}]
    
    start_time = time.time()
    result = await Runner.run(productobot_agent, input_items, context=context)
    duration = time.time() - start_time
    
    print(f"Duration: {duration:.2f}s")
    print(f"Result type: {type(result)}")
    print(f"Result attributes: {dir(result)}")
    
    # Check for usage in raw_responses
    total_tokens = 0
    if hasattr(result, 'raw_responses'):
        print(f"Number of raw responses: {len(result.raw_responses)}")
        for i, resp in enumerate(result.raw_responses):
            if hasattr(resp, 'usage') and resp.usage:
                print(f"Response {i} usage: {resp.usage}")
                total_tokens += resp.usage.total_tokens
            elif isinstance(resp, dict) and 'usage' in resp:
                 print(f"Response {i} usage (dict): {resp['usage']}")
                 total_tokens += resp['usage'].get('total_tokens', 0)
    
    print(f"Total tokens: {total_tokens}")
    
    # Check new items for tool calls
    print("\nItems in result:")
    for item in result.new_items:
        print(f"- {type(item).__name__}")
        # Use dir to see what's available if it's a ToolCallItem
        if "ToolCall" in type(item).__name__ and not "Output" in type(item).__name__:
            print(f"  Raw Item: {item.raw_item}")
            if hasattr(item.raw_item, 'call') and hasattr(item.raw_item.call, 'function'):
                 print(f"  Tool Name (raw_item.call.function.name): {item.raw_item.call.function.name}")
            elif isinstance(item.raw_item, dict) and 'call' in item.raw_item:
                 print(f"  Tool Name (dict): {item.raw_item['call']['function']['name']}")
        if "Message" in type(item).__name__:
            if hasattr(item, 'content'):
                print(f"  Content snippet: {str(item.content)[:100]}...")

if __name__ == "__main__":
    asyncio.run(test_metrics())
