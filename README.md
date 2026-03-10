# AFG Estimate Analyser Consolidated Project

Welcome to the unified AFG Estimate Analyser ecosystem. This repository consolidates the extraction tools, agent framework, and frontend/backend services into a single, cohesive structure.

## Project Structure

- **`AFGEstimateAnalyser/`** (Root)
    - `.env`: Unified configuration for all components.
    - `sql_client.py`: Shared SQL Server client for both MSAF and Extractor.
    - `requirements.txt`: Single pip requirements file for the whole project.
    - **`MSAF/`**: Microsoft Agent Framework (Orchestrator, Tools, Worker).
    - **`ExtractorTool/`**: TCO Extraction Logic, ROI engine, and Validation Rules.
    - **`MSAF/main.py`**: FastAPI Backend that serves the API and runs the workflow (no Celery/Redis).
    - **`ui/`**: React-based administration and analysis dashboard.
    - **`data/`**: Centralized storage for HTML extraction, results, and uploads.

## One-Time Setup

1. **Create a Unified Virtual Environment:**
   ```bash
   python -m venv venv
   source venv/Scripts/activate 
   pip install -r requirements.txt
   ```

2. **Configure Environment:**
   Ensure the root `.env` reflects your local SQL Server and Azure OpenAI credentials.

## Running the System (End-to-End)

Celery and Redis have been removed. Run these from the project root (`AFGEstimateAnalyser`):

1. **Extraction Service** (optional; only if you need extraction before MSAF):
   ```bash
   python ExtractorTool/extraction_service.py
   ```
   *(http://localhost:1204)*

2. **Backend API (MSAF):**
   ```bash
   python MSAF/main.py
   ```
   *(http://localhost:2357)*

3. **Frontend UI** (optional):
   ```bash
   cd ui
   npm run dev
   ```

Trigger the workflow via `POST /api/v1/msaf_process` (jobID, tco_file_url, retry_flag). No Redis or Celery worker required.

## Key Consolidated Features

- **Unified SQL Client**: `sql_client.py` handles all raw pyodbc and SQLAlchemy connections.
- **Improved Rule Sandbox**: Rule execution includes auto-loading of `df` and safe JSON serialization for DataFrames.
- **Console logging**: Task and extraction logs go to the console (Redis traceability removed).
