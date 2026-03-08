# AFG Estimate Analyser Consolidated Project

Welcome to the unified AFG Estimate Analyser ecosystem. This repository consolidates the extraction tools, agent framework, and frontend/backend services into a single, cohesive structure.

## Project Structure

- **`AFGEstimateAnalyser/`** (Root)
    - `.env`: Unified configuration for all components.
    - `sql_client.py`: Shared SQL Server client for both MSAF and Extractor.
    - `requirements.txt`: Single pip requirements file for the whole project.
    - **`MSAF/`**: Microsoft Agent Framework (Orchestrator, Tools, Worker).
    - **`ExtractorTool/`**: TCO Extraction Logic, ROI engine, and Validation Rules.
    - **`agent_backend/`**: FastAPI Backend that serves the UI and manages tasks.
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

You will need 4 terminal windows open (all from the root `AFGEstimateAnalyser` folder):

1. **Extraction Service:**
   ```bash
   python ExtractorTool/extraction_service.py
   ```
   *(Running on http://localhost:1204)*

2. **Celery Worker (MSAF):**
   ```bash
   celery -A MSAF.worker worker --loglevel=info -P threads --concurrency=10
   ```

3. **Backend API:**
   ```bash
   python agent_backend/main.py
   ```
   *(Running on http://localhost:2357)*

4. **Frontend UI:**
   ```bash
   cd ui
   npm run dev
   ```

## Key Consolidated Features

- **Unified SQL Client**: `sql_client.py` handles all raw pyodbc and SQLAlchemy connections.
- **Improved Rule Sandbox**: Rule execution includes auto-loading of `df` and safe JSON serialization for DataFrames.
- **Centralized Traceability**: All logs from extraction through agent reasoning flow to the UI sidebar in real-time.
