import asyncio
import os
import sys
import logging
from dotenv import load_dotenv

# Ensure project root is in sys.path
proj_root = r"c:\AI-projects\afg_agno\AFGEstimateAnalyser"
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)
if os.path.join(proj_root, "MSAF") not in sys.path:
    sys.path.insert(0, os.path.join(proj_root, "MSAF"))

load_dotenv(os.path.join(proj_root, ".env"))

from MSAF.agent import AgentOrchestrator

async def test_agent():
    query = "The extraction for mode 'waterfall' and Job ID '4352395345' is ready. Please run all relevant validation rules for this project."
    print(f"--- Testing Agent with query: {query} ---")
    
    # Set up a console logger to see what's happening
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("TestAgent")
    
    agent = AgentOrchestrator(task_id="test_4352395345", logger=logger)
    
    try:
        async with agent:
            response = await agent.run_task(query)
            print("\nAgent Response:")
            print(response)
    except Exception as e:
        print(f"\nAgent Failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_agent())
