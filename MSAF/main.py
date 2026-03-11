import os
import sys
from typing import Optional
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Ensure project root is in sys.path
# This file is located in <PROJECT_ROOT>/MSAF/main.py
current_file_path = os.path.abspath(__file__)
msaf_dir = os.path.dirname(current_file_path)
proj_root = os.path.dirname(msaf_dir)

if proj_root not in sys.path:
    sys.path.insert(0, proj_root)
if msaf_dir not in sys.path:
    sys.path.insert(0, msaf_dir)

# Load .env
load_dotenv(os.path.join(proj_root, ".env"))

# Import Workflow
from MSAF.workflow import run_msaf_workflow

app = FastAPI(title="MSAF Direct API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Router
v1_router = APIRouter(prefix="/api/v1")

class MSAFRequest(BaseModel):
    jobID: str
    tco_file_url: Optional[str] = None
    questionaries_file_url: Optional[str] = None
    retry_flag: bool

@v1_router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "msaf-standalone"}

@v1_router.post("/msaf_process")
async def process_msaf_task(req: MSAFRequest):
    """Standalone entry point to trigger MSAF extraction/validation."""
    if not req.retry_flag and not req.tco_file_url:
        raise HTTPException(status_code=400, detail="tco_file_url is required when retry_flag is false.")

    # Call workflow directly
    try:
        result = await run_msaf_workflow(
            jobID=req.jobID,
            tco_file_url=req.tco_file_url,
            questionaries_file_url=req.questionaries_file_url,
            retry_flag=req.retry_flag
        )
    except Exception as e:
        import traceback
        error_detail = f"Workflow Crash: {str(e)}\n{traceback.format_exc()}"
        print(f"[CRITICAL ERROR] {error_detail}")
        raise HTTPException(status_code=500, detail=error_detail)

    if result["status"] == "error":
        print(f"[WORKFLOW ERROR] {result.get('error')}")
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error in MSAF workflow."))

    return result

app.include_router(v1_router)

if __name__ == "__main__":
    import uvicorn
    # Serve on 2357 as requested/previously used
    uvicorn.run(app, host="0.0.0.0", port=2357)
