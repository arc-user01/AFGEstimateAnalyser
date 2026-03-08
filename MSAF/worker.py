import os
import asyncio
from celery import Celery
from MSAF.agent import AgentOrchestrator
from MSAF.logger import setup_task_logger
from dotenv import load_dotenv
import json
import nest_asyncio

# Enable nested event loops for async orchestration in threads
nest_asyncio.apply()

# Load .env
# Load .env from project root
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

# Initialize Celery app
broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

app = Celery('maf_worker', broker=broker_url, backend=result_backend)

# Celery Configuration
task_queue = os.getenv("CELERY_TASK_QUEUE", "get_task_queue")
result_queue_name = os.getenv("RESULT_QUEUE", "result_queue")

app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_default_queue=task_queue,
    worker_concurrency=10, 
)

@app.task(bind=True, name="process_extraction_task")
def process_extraction_task(self, tco_file_url=None, questionaries_file_url=None, rule_code=None):
    """
    Main entry point for the frontend to trigger an agent validation/extraction task.
    """
    task_id = self.request.id
    logger = setup_task_logger(task_id, f"Worker_{task_id}")
    
    logger.info(f"Received extraction task {task_id}")
    logger.info(f"TCO: {tco_file_url} | Questionaries: {questionaries_file_url} | Rule: {rule_code}")
    
    import requests
    extraction_url = os.getenv("EXTRACTION_SERVICE_URL", "http://localhost:1204")
    
    try:
        # Phase 1: Call Extraction Service
        logger.info(f"--- [Phase 1: Starting Data Extraction] ---")
        # Handle file:// URLs by converting back to path for the local service
        tco_path = tco_file_url.replace("file://", "") if tco_file_url else ""
        
        response = requests.post(f"{extraction_url}/extract", json={
            "task_id": task_id,
            "tco_file_path": tco_path
        }, timeout=300) # Long timeout for extraction
        
        if response.status_code != 200:
            error_msg = f"Extraction Service failed with status {response.status_code}: {response.text}"
            logger.error(error_msg)
            return {"status": "error", "task_id": task_id, "error": error_msg}
        
        extraction_res = response.json()
        logger.info(f"--- [Phase 1: Extraction Complete] | Mode: {extraction_res.get('detected_mode')} ---")

        # Phase 2: Agent Orchestration (Rule Validation)
        logger.info(f"--- [Phase 2: Starting Super Agent Orchestration] ---")
        orchestrator = AgentOrchestrator(task_id, logger)
        
        # Prepare query for the Agent
        detected_mode = extraction_res.get('detected_mode', 'unknown')
        query = (
            f"The extraction for mode '{detected_mode}' is complete. "
            f"Please find ALL validation rules associated with the '{detected_mode}' sheet mode and run EVERY single one of them sequentially."
        )
        
        # Run the agent (async) - Handle event loop correctly for green threads
        try:
            result = asyncio.run(orchestrator.run_task(query))
        except RuntimeError:
            # Fallback if a loop is already running or being closed
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(orchestrator.run_task(query))
            finally:
                loop.close()
        
        # Phase 3: Push result and signal completion
        import redis
        r = redis.from_url(broker_url)
        
        # 1. Store result in task-specific key (for fast lookup)
        result_key = f"task_result:{task_id}"
        result_payload = {
            "status": "success",
            "task_id": task_id,
            "result": result
        }
        r.setex(result_key, 3600, json.dumps(result_payload)) # Expire in 1 hour
        
        # 2. ALSO Push to general result_queue (legacy/compatibility)
        r.rpush(result_queue_name, json.dumps(result_payload))
        
        # 3. Emit a explicit completion message to signal SSE to close
        trace_queue = f"{os.getenv('TRACEBILITY_QUEUE_PREFIX', 'tracebility_queue:')}{task_id}"
        completion_msg = {
            "level": "SYSTEM",
            "message": "--- [TASK_COMPLETE] ---",
            "task_id": task_id
        }
        r.rpush(trace_queue, json.dumps(completion_msg))
        
        logger.info(f"Task {task_id} processed and result available at {result_key}")
        return result_payload
    except Exception as e:
        logger.error(f"Task {task_id} failed: {str(e)}")
        return {
            "status": "error",
            "task_id": task_id,
            "error": str(e)
        }

if __name__ == '__main__':
    # Usage: celery -A worker worker --loglevel=info --concurrency=10
    app.start()
