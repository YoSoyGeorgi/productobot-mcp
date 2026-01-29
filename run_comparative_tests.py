import json
import asyncio
import re
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add agent directory to sys.path
agent_path = Path(__file__).parent / "agent"
sys.path.append(str(agent_path))

from agent.ruto_agent import chat

# Regex to clean Slack user mentions
MENTION_REGEX = re.compile(r"<@[A-Z0-9]+>")

async def run_comparative_tests():
    print("Reading test_results.json...")
    with open("test_results.json", "r", encoding="utf-8") as f:
        results = json.load(f)
    
    # Filter for ORIG or DRAW
    target_tests = [
        r for r in results 
        if r.get("summary", {}).get("result") in ["ORIG", "DRAW"]
    ]
    
    print(f"Found {len(target_tests)} cases where Orig was better or tied.")
    
    comparative_results = []
    
    for i, test_case in enumerate(target_tests):
        raw_query = test_case.get("parent_message", "")
        # Clean query
        clean_query = MENTION_REGEX.sub("", raw_query).strip()
        
        print(f"[{i+1}/{len(target_tests)}] Running query: {clean_query}")
        
        try:
            # Run the new ReAct agent
            new_response = await chat(clean_query, first_name="Tester")
            
            # Construct comparison object
            comparison = {
                "query": clean_query,
                "original_result_type": test_case["summary"]["result"],
                "original_explanation": test_case["summary"]["explanation"],
                "original_scores": {
                    "orig": test_case["summary"]["score_orig"],
                    "mcp": test_case["summary"]["score_mcp"]
                },
                "new_agent_response": new_response
            }
            comparative_results.append(comparison)
            
        except Exception as e:
            print(f"Error running query '{clean_query}': {e}")
    
    # Save to test_results2.json
    print("Saving preliminary results to test_results2.json...")
    with open("test_results2.json", "w", encoding="utf-8") as f:
        json.dump(comparative_results, f, indent=2, ensure_ascii=False)

    print("Starting Evaluation against Original Results...")
    from evaluate_comparative_results import main as evaluate_main
    await evaluate_main()
    
    print("Done!")

if __name__ == "__main__":
    asyncio.run(run_comparative_tests())
