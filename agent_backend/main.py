import os
import uuid
import json
import redis
import shutil
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from celery import Celery
from dotenv import load_dotenv

# Load .env from project root
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

app = FastAPI(title="MSAF Estimate Analyser API")

# Aggressive CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis & Celery Config
redis_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
celery_app = Celery('maf_worker', broker=redis_url, backend=redis_url)
r_client = redis.from_url(redis_url)

# Use data directory from PROJECT_ROOT if possible
proj_root = os.getenv("PROJECT_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_DIR = os.path.join(proj_root, "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

class ProcessRequest(BaseModel):
    rule_code: str
    tco_filename: str
    questionaries_filename: Optional[str] = None

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Uploads a file and returns the local filename/path proxy."""
    file_id = str(uuid.uuid4())
    filename = f"{file_id}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {"filename": filename, "status": "uploaded"}

@app.post("/process")
async def process_task(req: ProcessRequest):
    """Triggers the Celery task and returns the task_id."""
    tco_path = os.path.join(UPLOAD_DIR, req.tco_filename)
    q_path = os.path.join(UPLOAD_DIR, req.questionaries_filename) if req.questionaries_filename else None
    
    if not os.path.exists(tco_path):
        raise HTTPException(status_code=400, detail="TCO file not found on server.")

    # In a real scenario, these would be URLs. For mimicking, we use local paths.
    # The worker.py is already set up to handle 'tco_file_url' in params.
    task = celery_app.send_task(
        "process_extraction_task",
        kwargs={
            "tco_file_url": f"file://{tco_path}", # Mocking URL
            "questionaries_file_url": f"file://{q_path}" if q_path else None,
            "rule_code": req.rule_code
        },
        queue=os.getenv("CELERY_TASK_QUEUE", "get_task_queue")
    )
    
    return {"task_id": task.id}

@app.get("/stream/{task_id}")
async def stream_logs(task_id: str):
    """SSE endpoint to stream logs from Redis tracebility_queue."""
    queue_name = f"{os.getenv('TRACEBILITY_QUEUE_PREFIX', 'tracebility_queue:')}{task_id}"
    
    def event_generator():
        pubsub = r_client.pubsub() # Note: RedisList is used in logger.py, but for SSE we might want to poll or use list blpop
        # Actually our logger.py uses rpush (List). We will use blpop for real-time fetch.
        while True:
            # Use blpop for real-time fetch with a timeout
            message = r_client.blpop(queue_name, timeout=5)
            if message:
                data_str = message[1].decode('utf-8')
                yield f"data: {data_str}\n\n"
                
                # Check for completion signal
                try:
                    data = json.loads(data_str)
                    if "--- [TASK_COMPLETE] ---" in data.get("message", ""):
                        yield f"data: {json.dumps({'level': 'SYSTEM', 'message': 'Stream closed by server.'})}\n\n"
                        break
                except:
                    pass
            else:
                yield ": keepalive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/result/{task_id}")
async def get_result(task_id: str):
    """Fetch result on arrival from result_queue."""
    result_queue = os.getenv("RESULT_QUEUE", "result_queue")
    
    # This is a bit tricky with lists. We might need to scan the list or use a mapping.
    # For now, we'll mimic the "fetch on arrival" by searching the result_queue list.
    # In production, you'd use a separate key or Redis PubSub.
    
    # We'll use a blocking pop with a longer timeout to mimic "on arrival"
    # But result_queue is shared. So we might need a specific key.
    # Let's check how worker.py does it: r.rpush(result_queue_name, json.dumps(result_payload))
    
    # To properly fetch "on arrival" for a SPECIFIC task_id without polling all:
    # We should ideally have the worker push to result_queue:<task_id>
    
    # 1. Check for specific result key (Optimized)
    result_key = f"task_result:{task_id}"
    cached_res = r_client.get(result_key)
    if cached_res:
        return json.loads(cached_res)
    
    # 2. Fallback to list search (Legacy)
    results = r_client.lrange(result_queue, 0, -1)
    for res_bytes in results:
        res = json.loads(res_bytes)
        if res.get("task_id") == task_id:
            return res
            
    return {"status": "pending"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=2357) # Backend for frontend on 2357
