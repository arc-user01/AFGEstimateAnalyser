import os
import sys
import io
import json
import logging
import tempfile
import shutil
import aspose.cells as ac
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

# Ensure project root and subdirectories are in path
current_dir = os.path.dirname(os.path.abspath(__file__))
# extraction_service.py is in ExtractorTool/utils, so project_root is two levels up
extractor_root = os.path.dirname(current_dir)
project_root = os.path.dirname(extractor_root)

if project_root not in sys.path:
    sys.path.append(project_root)
if extractor_root not in sys.path:
    sys.path.append(extractor_root)
if current_dir not in sys.path:
    sys.path.append(current_dir)

from utils.excel_to_html import convert_excel_to_html
from utils.header_subheader_detector import detect_headers_and_subcategories
from utils.header_process import process_header_tables
from ExtractorTool.dbUtils.sql_client import DatabaseClient
from dbUtils.sheet_metadata import insert_sheet_metadata
from utils.roi_engine import load_soup_rows, process_roi_section, save_roi_blocks

# Load .env from project root
env_path = os.path.join(project_root, '.env')
load_dotenv(env_path)

# --- Helpers ---

def log_trace(jobID: str, message: str, level: str = "INFO"):
    """Log a trace message (console only; Redis/Celery removed)."""
    print(f"[{level}] [{jobID}] {message}")

# Blob Storage Configuration
ACCOUNT_NAME = os.getenv("AccountName", "").strip(";")
ACCOUNT_KEY = os.getenv("AccountKey", "").split(";")[0] # Extract only the key part
BLOB_CON_STR = f"DefaultEndpointsProtocol=https;AccountName={ACCOUNT_NAME};AccountKey={ACCOUNT_KEY};EndpointSuffix=core.windows.net"

def ensure_local_file(jobID: str, file_url_or_path: str, job_temp_dir: str) -> str:
    """
    Ensures the target file is available locally.
    Downloads from Azure Blob if it's a URL.
    Returns the absolute local path to the file.
    """
    if not file_url_or_path:
        return ""

    parsed = urlparse(file_url_or_path)
    
    # Check if it's an Azure Blob URL
    if parsed.scheme in ("http", "https") and "blob.core.windows.net" in parsed.netloc:
        log_trace(jobID, f"Detected Azure Blob URL: {file_url_or_path}. Downloading...")
        
        try:
            # Parse container and blob name
            path_parts = parsed.path.lstrip("/").split("/", 1)
            if len(path_parts) < 2:
                raise ValueError("Invalid Blob URL format. Expected <container>/<blob>")
            
            container_name = path_parts[0]
            blob_name = path_parts[1]
            
            blob_service_client = BlobServiceClient.from_connection_string(BLOB_CON_STR)
            blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
            
            # Save using the original blob filename inside the job's temp folder
            temp_path = os.path.join(job_temp_dir, blob_name.split("/")[-1])
            
            with open(temp_path, "wb") as download_file:
                download_file.write(blob_client.download_blob().readall())
            
            log_trace(jobID, f"Blob downloaded successfully to: {temp_path}")
            return temp_path
            
        except Exception as e:
            log_trace(jobID, f"Failed to download blob: {str(e)}", "ERROR")
            raise e
            
    # Handle local file path
    local_path = file_url_or_path.replace("file://", "")
    if not os.path.isabs(local_path):
        local_path = os.path.abspath(os.path.join(project_root, local_path))
    
    if os.path.exists(local_path):
        return local_path
    else:
        log_trace(jobID, f"File not found locally: {local_path}", "ERROR")
        return local_path

# --- FastAPI App ---

app = FastAPI(title="TCO Extraction Service")

class ExtractionRequest(BaseModel):
    jobID: str
    tco_file_path: str
#localhost:1204
@app.post("/extract")
async def extract_tco(req: ExtractionRequest):
    jobID = req.jobID
    excel_file = req.tco_file_path
    log_trace(jobID, f"--- NEW EXTRACTION REQUEST RECEIVED (jobID: {jobID}) ---")

    # Path Resolution (Config only)
    config_path = os.getenv("EXTRACTION_CONFIG_PATH", "").strip()
    if config_path and not os.path.isabs(config_path):
        config_path = os.path.abspath(os.path.join(project_root, config_path))

    # Validation
    if not excel_file:
        error_msg = "Missing tco_file_path in request."
        log_trace(jobID, error_msg, "ERROR")
        raise HTTPException(status_code=500, detail=error_msg)
    if not config_path or not os.path.isfile(config_path):
        error_msg = f"Extraction config not found: {config_path}"
        log_trace(jobID, error_msg, "ERROR")
        raise HTTPException(status_code=500, detail=error_msg)

    # Isolated Job Directory (Everything goes here)
    job_temp_dir = os.path.abspath(os.path.join(project_root, "data", "temp", f"fl_{jobID}"))
    os.makedirs(job_temp_dir, exist_ok=True)
    
    # Internal subfolders for artifacts
    html_out_dir = os.path.join(job_temp_dir, "html")
    md_out_dir = os.path.join(job_temp_dir, "md")
    os.makedirs(html_out_dir, exist_ok=True)
    os.makedirs(md_out_dir, exist_ok=True)

    log_trace(jobID, f"Extraction Phase Started | Workspace: {job_temp_dir}")
    log_trace(jobID, f"Incoming Request Data: jobID={jobID}, tco_file_path={excel_file}")

    try:
        # DB Connection Info (for diagnostics)
        server = os.getenv("DB_SERVER", "unknown")
        dbname = os.getenv("DB_NAME", "unknown")
        user = os.getenv("DB_USER", "unknown")
        log_trace(jobID, f"Active DB Context: Server={server} | Database={dbname} | User={user}")

        # Load Config
        log_trace(jobID, "Loading extraction configuration JSON...")
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # Ensure local file (Download to job folder if needed)
        tco_path = ensure_local_file(jobID, excel_file, job_temp_dir)
        if not os.path.exists(tco_path):
            raise FileNotFoundError(f"TCO file not found: {tco_path}")

        # Step 1 - Connect database & Create Schema
        log_trace(jobID, "Connecting to database...")
        db = DatabaseClient()
        
        # User requested EXACT jobID for schema extraction
        schema_name = f"ext_{jobID}".replace("-", "_")
        
        try:
            # Use user's requested syntax for schema creation
            schema_sql = f"IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = '{schema_name}') BEGIN EXEC('CREATE SCHEMA [{schema_name}]') END"
            db.cursor.execute(schema_sql)
            db.conn.commit()
            log_trace(jobID, f"Schema [{schema_name}] is created and all the table will be created in this schema.")
        except Exception as e:
            log_trace(jobID, f"Error creating schema [{schema_name}]: {e}", "WARNING")
            # If schema creation fails, we might still proceed with dbo or a fallback, 
            # but for this flow we assume the schema name is what's used.

        # Step 2 - Open Workbook
        log_trace(jobID, f"Opening Excel workbook: {os.path.basename(tco_path)}")
        wb = ac.Workbook(tco_path)
        wb.calculate_formula()

        log_trace(jobID, "Reading 'Intro' sheet to detect Delivery Mode...")
        intro_sheet = wb.worksheets.get("Intro")
        if not intro_sheet:
            log_trace(jobID, "Critical Error: 'Intro' sheet not found!", "ERROR")
            return {"status": "error", "message": "Intro sheet not found"}

        # Robustly find delivery mode cell
        delivery_val = "unknown"
        target_marker = "Agile or Waterfall".lower()
        
        # Scan first few rows/cols for the marker
        found_cell = False
        for r in range(15):
            for c in range(10):
                cell = intro_sheet.cells.get(r, c)
                val = (cell.string_value or "").strip().lower()
                if target_marker in val:
                    # The label itself contains both words "agile" and "waterfall".
                    # We must prioritize checking the next cell for the actual answer.
                    next_cell = intro_sheet.cells.get(r, c + 1)
                    next_val = (next_cell.string_value or "").strip().lower()
                    
                    if "agile" in next_val or "waterfall" in next_val:
                        delivery_val = next_val
                    elif "agile" in val and "waterfall" not in val:
                        # If the cell just says "agile"
                        delivery_val = val
                    elif "waterfall" in val and "agile" not in val:
                        # If the cell just says "waterfall"
                        delivery_val = val
                    else:
                        # Fallback to the next cell even if it doesn't explicitly contain the words (might be empty)
                        delivery_val = next_val
                        
                    found_cell = True
                    break
            if found_cell: break
        
        if not found_cell:
            log_trace(jobID, "Warning: Could not find 'Agile or Waterfall' marker on Intro sheet. Falling back to (5,2).", "WARNING")
            delivery_cell = intro_sheet.cells.get(5, 2)
            delivery_val = (delivery_cell.string_value or "").strip().lower()

        log_trace(jobID, f"Delivery Mode detected: '{delivery_val}'")

        target_sheet_prefix = "agile" if "agile" in delivery_val else "waterfall" if "waterfall" in delivery_val else None
        if not target_sheet_prefix:
            log_trace(jobID, f"Unknown delivery mode: '{delivery_val}'. Processing all sheets.", "WARNING")

        total_sheets = len(config["sheets"])
        processed_count = 0

        for idx, sheet_cfg in enumerate(config["sheets"]):
            sheet_name = sheet_cfg["name"]
            
            # Allow 'Intro' and the specific mode sheet
            # Also allow 'ROI' or other explicitly configured sheets if they exist in the workbook
            is_intro = sheet_name.lower() == "intro"
            is_mode_match = target_sheet_prefix and target_sheet_prefix in sheet_name.lower()
            
            # If we established a mode, only process Intro and that mode's sheets
            if target_sheet_prefix and not is_intro and not is_mode_match:
                continue

            log_trace(jobID, f"Processing Sheet {idx+1}/{total_sheets}: {sheet_name}...")
            
            try:
                # 1. Export Sheet to HTML (In temp job folder)
                html_file = os.path.join(html_out_dir, f"{sheet_name}.html")
                sheet = wb.worksheets.get(sheet_name)
                if not sheet: continue

                options = ac.HtmlSaveOptions()
                options.export_cell_coordinate = True
                options.export_grid_lines = True
                options.calculate_formula = True
                wb.worksheets.active_sheet_index = sheet.index
                options.export_active_worksheet_only = True
                wb.save(html_file, options)

                # 2. Detect Headers
                header_subcat_dict = detect_headers_and_subcategories(html_file)
                if not header_subcat_dict: continue

                # 3. Process Headers (Save MD to temp subfolder)
                sheet_md_folder = os.path.join(md_out_dir, sheet_name.lower())
                os.makedirs(sheet_md_folder, exist_ok=True)

                with open(html_file, "r", encoding="utf-8") as f:
                    soup = BeautifulSoup(f.read(), "html.parser")

                for header in header_subcat_dict.keys():
                    try:
                        # Log fully qualified table name for confirmation
                        target_table = header.replace(" ", "_").lower()
                        log_trace(jobID, f"Extracting to table: [{schema_name}].[{target_table}]")

                        if header.upper() == "ROI CALCULATION":
                            rows_data = load_soup_rows(soup)
                            subheaders = header_subcat_dict[header]
                            roi_blocks = process_roi_section(rows_data, header, subheaders)
                            save_roi_blocks(sheet_name, header, roi_blocks, sheet_md_folder, db, schema_name=schema_name)
                        else:
                            process_header_tables(
                                header_name=header,
                                header_subcat_dict=header_subcat_dict,
                                soup=soup,
                                result_folder=sheet_md_folder,
                                pg=db,
                                sheet_name=sheet_name,
                                schema_name=schema_name
                            )
                    except Exception as hex:
                        log_trace(jobID, f"Extraction failed for table [{schema_name}].[{header.replace(' ', '_').lower()}]: {hex}", "ERROR")

                # 4. Insert Metadata
                log_trace(jobID, f"Inserting metadata for sheet: {sheet_name} into [{schema_name}].[sheet_metadata]...")
                insert_sheet_metadata(db, sheet_name, header_subcat_dict, schema_name=schema_name)
                processed_count += 1

            except Exception as sex:
                log_trace(jobID, f"Error processing sheet {sheet_name}: {sex}", "ERROR")

        log_trace(jobID, f"Extraction Completed. All data saved into schema: [{schema_name}]. Processed {processed_count} sheets.")

        return {
            "status": "success",
            "jobID": jobID,
            "extraction_schema": schema_name,
            "detected_mode": delivery_val,
            "sheets_processed": processed_count
        }

    except Exception as e:
        log_trace(jobID, f"Critical Failure: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        # Cleanup WHOLE job folder
        if os.path.exists(job_temp_dir):
            try:
                shutil.rmtree(job_temp_dir)
                log_trace(jobID, "Cleaned up all temporary job artifacts.")
            except Exception as ex:
                log_trace(jobID, f"Cleanup failure: {ex}", "WARNING")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=1204)
