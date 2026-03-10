import os
import sys

# Ensure project root is in sys.path for MSAF and other modules
proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

import requests
import json
from MSAF.agent import AgentOrchestrator
from MSAF.logger import setup_task_logger

async def run_msaf_workflow(jobID: str, tco_file_url: str = None, questionaries_file_url: str = None, retry_flag: bool = False):
    """
    Unified workflow for handling MSAF extraction and orchestration directly.
    """
    logger = setup_task_logger(jobID, f"Workflow_{jobID}")
    logger.info(f"--- Starting MSAF Direct Workflow for Job: {jobID} | Retry: {retry_flag} ---")
    
    extraction_url = os.getenv("EXTRACTION_SERVICE_URL", "http://localhost:1204")
    
    try:
        detection_result = {"detected_mode": "unknown"}
        
        # Phase 1: Extraction (Skip if retry_flag is True)
        if not retry_flag:
            logger.info("Phase 1: Triggering Data Extraction Service...")
            # Convert file:// URL to path if local
            tco_path = tco_file_url.replace("file://", "") if tco_file_url else ""
            
            try:
                response = requests.post(f"{extraction_url}/extract", json={
                    "task_id": jobID,
                    "tco_file_path": tco_path
                }, timeout=300)
                
                if response.status_code == 200:
                    detection_result = response.json()
                    logger.info(f"Extraction Successful. Mode: {detection_result.get('detected_mode')}")
                else:
                    logger.error(f"Extraction Service Failed: {response.text}")
                    # We might still want to proceed to agent if it's a soft error, 
                    # but for this workflow we'll be cautious.
            except Exception as e:
                logger.error(f"Failed to connect to Extraction Service: {str(e)}")
        else:
            logger.info("Phase 1: Skipped (Retry Mode)")

        # Phase 2: Agent Orchestration
        logger.info("Phase 2: Initializing Super Agent Orchestrator...")
        orchestrator = AgentOrchestrator(jobID, logger)
        
        detected_mode = detection_result.get('detected_mode', 'unknown')
        query = (
            f"The extraction for mode '{detected_mode}' is ready. "
            f"Please run all relevant validation rules."
        )
        
        # This will return the mock response we set up in agent.py
        result = await orchestrator.run_task(query)
        
        logger.info(f"--- MSAF Workflow Completed for Job: {jobID} ---")
        return {
            "status": "success",
            "jobID": jobID,
            "response": result
        }

    except Exception as e:
        logger.error(f"Workflow Failed for Job {jobID}: {str(e)}")
        return {
            "status": "error",
            "jobID": jobID,
            "error": str(e)
        }
