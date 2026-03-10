# Celery and Redis have been removed from this project.
# All workflow execution runs via the FastAPI backend (MSAF/main.py).
# Use: POST /api/v1/msaf_process with jobID, tco_file_url, retry_flag.
# Do not run: celery -A MSAF.worker worker
