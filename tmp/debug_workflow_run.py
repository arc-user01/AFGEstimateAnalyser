import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure project root is in sys.path
proj_root = r"c:\AI-projects\afg_agno\AFGEstimateAnalyser"
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)
if os.path.join(proj_root, "MSAF") not in sys.path:
    sys.path.insert(0, os.path.join(proj_root, "MSAF"))

load_dotenv(os.path.join(proj_root, ".env"))

from MSAF.workflow import workflow, run_msaf_workflow

async def debug_workflow():
    payload = {
        "jobID": "4352395345",
        "tco_file_url": r"C:\Users\AlokRanjanMishra\Downloads\waterfall_test.xltx",
        "questionaries_file_url": "string",
        "retry_flag": False
    }
    
    print(f"--- Running Debug Workflow for Job {payload['jobID']} ---")
    
    try:
        # We manually step through or just run the legacy wrapper but with more prints
        result = await run_msaf_workflow(
            jobID=payload["jobID"],
            tco_file_url=payload["tco_file_url"],
            retry_flag=payload["retry_flag"]
        )
        print("\nWorkflow Result:")
        print(result)
        
    except Exception as e:
        print(f"\nWorkflow Crashed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_workflow())
