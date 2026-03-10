import os
import sys
import io
import json
import logging
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from bs4 import BeautifulSoup
import aspose.cells as ac
from dotenv import load_dotenv

# Ensure project root and subdirectories are in path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)
if current_dir not in sys.path:
    sys.path.append(current_dir)

from utils.excel_to_html import convert_excel_to_html
from utils.header_subheader_detector import detect_headers_and_subcategories
from utils.header_process import process_header_tables
from sql_client import DatabaseClient
from pg_utils.sheet_metadata import insert_sheet_metadata
from utils.roi_engine import load_soup_rows, process_roi_section, save_roi_blocks

# Load .env from project root
env_path = os.path.join(project_root, '.env')
load_dotenv(env_path)


def _resolve_base_dir(env_key: str, project_root: str) -> str:
    """Read dir from .env and return a fully qualified (absolute) path. Relative paths are resolved against project_root."""
    raw = (os.getenv(env_key) or "").strip()
    if not raw:
        return ""
    if os.path.isabs(raw):
        return os.path.normpath(raw)
    return os.path.abspath(os.path.join(project_root, raw))


def _fully_qualified_job_dir(base_dir: str, job_id: str) -> str:
    """Build fully qualified path: base_dir / fl_{job_id}."""
    if not base_dir or not job_id:
        return ""
    return os.path.abspath(os.path.join(base_dir, f"fl_{job_id}"))

app = FastAPI(title="TCO Extraction Service")


class ExtractionRequest(BaseModel):
    task_id: str
    tco_file_path: str


def log_trace(task_id: str, message: str, level: str = "INFO"):
    """Log a trace message (console only; Redis/Celery removed)."""
    print(f"[{level}] [{task_id}] {message}")

@app.post("/extract")
async def extract_tco(req: ExtractionRequest):
    task_id = req.task_id  # JOBID from input
    job_id = task_id
    excel_file = req.tco_file_path

    # Read HTML_OUT_DIR and RESULTS_DIR from .env; resolve to fully qualified paths (relative = resolved against PROJECT_ROOT or project_root)
    resolve_base = (os.getenv("PROJECT_ROOT") or "").strip() or project_root
    base_html_out_dir = _resolve_base_dir("HTML_OUT_DIR", resolve_base)
    base_results_dir = _resolve_base_dir("RESULTS_DIR", resolve_base)
    config_path = os.getenv("EXTRACTION_CONFIG_PATH", "").strip()
    if config_path and not os.path.isabs(config_path):
        config_path = os.path.abspath(os.path.join(resolve_base, config_path))

    if not excel_file:
        error_msg = "Missing tco_file_path in request."
        log_trace(task_id, error_msg, "ERROR")
        raise HTTPException(status_code=500, detail=error_msg)
    if not base_html_out_dir or not base_results_dir:
        error_msg = "Missing HTML_OUT_DIR or RESULTS_DIR in .env."
        log_trace(task_id, error_msg, "ERROR")
        raise HTTPException(status_code=500, detail=error_msg)
    if not config_path or not os.path.isfile(config_path):
        error_msg = f"Extraction config not found: {config_path}"
        log_trace(task_id, error_msg, "ERROR")
        raise HTTPException(status_code=500, detail=error_msg)

    log_trace(task_id, f"Extraction Phase Started for file: {os.path.basename(excel_file)}")

    # Create fully qualified per-JOBID paths: base_from_env / fl_{job_id}
    html_out_dir = _fully_qualified_job_dir(base_html_out_dir, job_id)
    results_dir = _fully_qualified_job_dir(base_results_dir, job_id)
    os.makedirs(html_out_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)
    log_trace(task_id, f"Created isolated directories: {html_out_dir} and {results_dir}")

    try:
        # Load Config
        log_trace(task_id, "Loading extraction configuration JSON...")
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # Step 1 - Connect database & Create Schema
        log_trace(task_id, "Connecting to database...")
        db = DatabaseClient()
        
        schema_name = f"ext_{task_id}".replace("-", "_").lower()
        log_trace(task_id, f"Creating schema if not exists: {schema_name}")

        try:
            # SQL Server schema creation
            schema_sql = f"IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = '{schema_name}') BEGIN EXEC('CREATE SCHEMA [{schema_name}]') END"
            db.cur.execute(schema_sql)
            db.conn.commit()
            log_trace(task_id, f"Schema '{schema_name}' is ready.")
        except Exception as e:
            log_trace(task_id, f"Error creating schema: {e}", "WARNING")
            # Fallback to dbo if schema creation fails due to permissions etc.
            log_trace(task_id, "Falling back to 'dbo' schema due to schema creation failure", "WARNING")
            schema_name = "dbo"

        # Step 2 - Determine Delivery Mode
        log_trace(task_id, "Opening Excel workbook with Aspose.Cells...")
        wb = ac.Workbook(excel_file)
        
        log_trace(task_id, "Calculating workbook formulas...")
        wb.calculate_formula()

        log_trace(task_id, "Reading 'Intro' sheet to detect Delivery Mode...")
        intro_sheet = wb.worksheets.get("Intro")
        if not intro_sheet:
            log_trace(task_id, "Critical Error: 'Intro' sheet not found!", "ERROR")
            # Close connection if needed (DatabaseClient handles it)
            return {"status": "error", "message": "Intro sheet not found"}

        # Cell C6 is (5, 2)
        delivery_cell = intro_sheet.cells.get(5, 2)
        delivery_val = (delivery_cell.string_value or "").strip().lower()
        log_trace(task_id, f"Delivery Mode detected: '{delivery_val}'")

        target_sheet_prefix = None
        if "agile" in delivery_val:
            target_sheet_prefix = "agile"
        elif "waterfall" in delivery_val:
            target_sheet_prefix = "waterfall"
        else:
            log_trace(task_id, f"Unknown delivery mode: '{delivery_val}'. Processing all sheets.", "WARNING")

        total_sheets = len(config["sheets"])
        processed_count = 0

        for idx, sheet_cfg in enumerate(config["sheets"]):
            sheet_name = sheet_cfg["name"]
            
            # Routing Filter
            if target_sheet_prefix and sheet_name.lower() != "intro" and sheet_name.lower() != target_sheet_prefix:
                log_trace(task_id, f"Skipping sheet '{sheet_name}' (Mismatch with {target_sheet_prefix})")
                continue

            log_trace(task_id, f"Processing Sheet {idx+1}/{total_sheets}: {sheet_name}...")
            
            try:
                # 1. Export Sheet to HTML
                html_file = os.path.join(html_out_dir, f"{sheet_name}.html")
                sheet = wb.worksheets.get(sheet_name)
                if not sheet:
                    log_trace(task_id, f"Error: Sheet '{sheet_name}' not found in workbook!", "ERROR")
                    continue

                log_trace(task_id, f"Converting '{sheet_name}' to HTML...")
                options = ac.HtmlSaveOptions()
                options.export_cell_coordinate = True
                options.export_grid_lines = True
                options.calculate_formula = True
                wb.worksheets.active_sheet_index = sheet.index
                options.export_active_worksheet_only = True
                wb.save(html_file, options)

                # 2. Detect Headers
                log_trace(task_id, f"Detecting headers and subcategories in {sheet_name}...")
                header_subcat_dict = detect_headers_and_subcategories(html_file)

                if not header_subcat_dict:
                    log_trace(task_id, f"No headers detected in {sheet_name}.", "WARNING")
                    continue

                # 3. Process Headers
                sheet_results_folder = os.path.join(results_dir, sheet_name.lower())
                os.makedirs(sheet_results_folder, exist_ok=True)

                log_trace(task_id, f"Parsing HTML with BeautifulSoup for sheet: {sheet_name}...")
                with open(html_file, "r", encoding="utf-8") as f:
                    soup = BeautifulSoup(f.read(), "html.parser")

                for h_idx, header in enumerate(header_subcat_dict.keys()):
                    log_trace(task_id, f"Extracting Header ({h_idx+1}/{len(header_subcat_dict)}): {header}...")
                    try:
                        if header.upper() == "ROI CALCULATION":
                            rows_data = load_soup_rows(soup)
                            subheaders = header_subcat_dict[header]
                            roi_blocks = process_roi_section(rows_data, header, subheaders)
                            save_roi_blocks(sheet_name, header, roi_blocks, sheet_results_folder, db, schema_name=schema_name)
                        else:
                            process_header_tables(
                                header_name=header,
                                header_subcat_dict=header_subcat_dict,
                                soup=soup,
                                result_folder=sheet_results_folder,
                                pg=db,
                                sheet_name=sheet_name,
                                schema_name=schema_name
                            )
                    except Exception as hex:
                        log_trace(task_id, f"Extraction failed for header {header}: {hex}", "ERROR")

                # 4. Insert Metadata
                log_trace(task_id, f"Inserting metadata for sheet: {sheet_name}...")
                insert_sheet_metadata(db, sheet_name, header_subcat_dict, schema_name=schema_name)
                processed_count += 1

            except Exception as sex:
                log_trace(task_id, f"Fatal error processing sheet {sheet_name}: {sex}", "ERROR")

        # DatabaseClient connections are handled by gc or explicit close if we add it
        log_trace(task_id, f"Extraction Phase Completed. Total sheets processed: {processed_count}")
        return {
            "status": "success",
            "task_id": task_id,
            "job_id": job_id,
            "detected_mode": delivery_val,
            "sheets_processed": processed_count,
            "html_dir": html_out_dir,
            "results_dir": results_dir,
        }

    except Exception as e:
        log_trace(task_id, f"Critical Extraction Failure: {e}", "ERROR")
        import traceback
        log_trace(task_id, traceback.format_exc(), "DEBUG")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Port 1204 as requested by user
    uvicorn.run(app, host="0.0.0.0", port=1204)
