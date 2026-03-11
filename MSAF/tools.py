import logging
import json
import sys
import io
import traceback
import os
import pandas as pd
import inspect
import difflib
import multiprocessing
import requests
import tempfile
import shutil
import subprocess # For diagnostic
from typing import List, Annotated, Dict, Any, Optional
from agent_framework import tool
from pydantic import Field
from ExtractorTool.dbUtils.sql_client import DatabaseClient
from MSAF.summarization import summarize_rule_output as _summarize_rule_output

# Ensure the framework directory is in the path for both this process and spawned children
framework_dir = os.path.dirname(os.path.abspath(__file__))
if framework_dir not in sys.path:
    sys.path.append(framework_dir)
os.environ["PYTHONPATH"] = framework_dir + os.pathsep + os.environ.get("PYTHONPATH", "")

logger = logging.getLogger("MicrosoftAgentTools")
db = DatabaseClient()

# Removed _sandbox_worker as we now use sandbox_executor.py via subprocess for better Windows stability.

@tool(approval_mode="never_require")
def get_available_rules(
    sheet_name: Annotated[Optional[str], Field(description="Filter validation rules by delivery mode (e.g., 'waterfall' or 'agile').")] = None
) -> str:
    """
    Lists all available validation rules from the consolidated view.
    Rules are ordered by their defined execution order.
    Use this to discover which rules (rule_code) exist in the system.
    """
    logger.info(f"Tool Action: Discovering available rules | Filter: '{sheet_name}'")
    try:
        # Log config source
        server = os.getenv("DB_SERVER", "unknown")
        db_name = os.getenv("DB_NAME", "unknown")
        logger.info(f"Fetching rule list from DB: {db_name} on {server} (View: vw_consolidated_validation_config)")
        
        rules = db.list_available_rules(sheet_name=sheet_name)
        if not rules:
            return f"No rules found for sheet '{sheet_name}' in database '{db_name}'."
        return json.dumps(rules, indent=2, default=str)
    except Exception as e:
        error_msg = f"Error listing rules from {os.getenv('DB_NAME')}: {str(e)}"
        logger.error(error_msg)
        return error_msg

@tool(approval_mode="never_require")
def run_rule_validation(
    rule_code: Annotated[str, Field(description="The unique code of the rule to execute.")],
    extraction_schema: Annotated[Optional[str], Field(description="The formal SQL schema name (e.g. 'ext_1234') containing the extracted data for this project.")] = "dbo"
) -> str:
    """
    Executes all tasks associated with a given rule_code sequentially.
    Tasks are executed in their specific task_execution_order within a sandboxed environment.
    """
    logger.info(f"Tool Action: Running multi-task validation for Rule Code: {rule_code} | Schema: {extraction_schema}")
    try:
        # Log config source
        server = os.getenv("DB_SERVER", "unknown")
        db_name = os.getenv("DB_NAME", "unknown")
        logger.info(f"Fetching task config for '{rule_code}' from DB: {db_name} on {server}")
        
        tasks = db.fetch_rule_config(rule_code)
        if not tasks:
            return f"Rule Code '{rule_code}' not found in database '{db_name}'."
        
        overall_results = []
        
        # Get project roots — dynamic from __file__, with env override
        proj_root = os.getenv("PROJECT_ROOT") or os.path.dirname(framework_dir)
        extractor_root = os.getenv("EXTRACTOR_ROOT") or os.path.join(proj_root, "ExtractorTool")
        
        # Add extractor root to sys.path for rules
        if extractor_root not in sys.path:
            sys.path.append(extractor_root)

        # Create temporary workspace for this extraction_schema if it's not "dbo"
        workspace_dir = None
        if extraction_schema and extraction_schema != "dbo":
            workspace_dir = os.path.join(tempfile.gettempdir(), f"agent_workspace_{extraction_schema}")
            os.makedirs(workspace_dir, exist_ok=True)
            logger.info(f"Created isolated workspace: {workspace_dir}")

        for task in tasks:
            inner_task_id = task.get("task_id")
            task_name = task.get("task_name", "Unnamed Task")
            log_msg = f"--- [Rule: {rule_code}] Starting Task {inner_task_id}: {task_name} ---"
            logger.info(log_msg)

            code = task.get("fn_code")
            if not code:
                overall_results.append({"task_id": inner_task_id, "task_name": task_name, "result": "Error: No function code found."})
                continue
            
            params = task.get("task_params", {})
            if isinstance(params, str) and params.strip():
                try:
                    params = json.loads(params)
                except:
                    params = {}
            if not isinstance(params, dict): params = {}

            # Remote File Support: Handle URLs if present
            for file_key in ["tco_file_url", "questionaries_file_url"]:
                url = params.get(file_key)
                if url and url.startswith("http"):
                    local_filename = f"{file_key}_{inner_task_id}.xlsx"
                    local_path = os.path.join(workspace_dir or tempfile.gettempdir(), local_filename)
                    try:
                        logger.info(f"Downloading remote file: {url} -> {local_path}")
                        response = requests.get(url, timeout=30)
                        response.raise_for_status()
                        with open(local_path, "wb") as f:
                            f.write(response.content)
                        # Inject local path into parameters for the rule function
                        params[file_key.replace("_url", "_path")] = local_path
                    except Exception as download_e:
                        logger.error(f"Failed to download {url}: {download_e}")

            # Merge with view columns
            if "sheet_name" not in params and task.get("sheet_name"): params["sheet_name"] = task.get("sheet_name")
            if "header" not in params and task.get("header_name"): params["header"] = task.get("header_name")

            # Sandboxed Execution via Subprocess
            payload = {
                "code": code,
                "params": params,
                "func_name": task.get("fn_name"),
                "proj_root": proj_root,
                "extractor_root": extractor_root,
                "framework_dir": framework_dir,
                "extraction_schema": extraction_schema
            }
            
            try:
                # Use current python interpreter and the new executor script
                py_exec = sys.executable
                executor_script = os.path.join(framework_dir, "sandbox_executor.py")
                
                process_result = subprocess.run(
                    [py_exec, executor_script],
                    input=json.dumps(payload),
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if process_result.returncode != 0:
                    task_res = {"success": False, "error": f"Sandbox failed with code {process_result.returncode}: {process_result.stderr}"}
                else:
                    try:
                        task_res = json.loads(process_result.stdout)
                    except Exception as parse_e:
                        task_res = {"success": False, "error": f"Failed to parse sandbox output: {str(parse_e)} | Raw: {process_result.stdout}"}
                        
            except subprocess.TimeoutExpired:
                task_res = {"success": False, "error": "Task exceeded timeout (120s) and was terminated."}
            except Exception as e:
                task_res = {"success": False, "error": f"Sandbox controller error: {str(e)}"}
            
            if task_res["success"]:
                log_finish = f"Task {inner_task_id} COMPLETED successfully."
                logger.info(log_finish)
                overall_results.append({
                    "task_id": inner_task_id,
                    "task_name": task_name,
                    "result": task_res["result"],
                    "logs": task_res.get("logs", "")
                })
            else:
                log_fail_msg = f"Task {inner_task_id} FAILED: {task_res.get('error')}"
                if task_res.get("traceback"):
                     log_fail_msg += f"\nTraceback: {task_res.get('traceback')}"
                
                logger.error(f"Task {inner_task_id} FAILED: {task_res.get('error')}")

                overall_results.append({
                    "task_id": inner_task_id,
                    "task_name": task_name,
                    "result": f"Execution Error: {task_res.get('error')}",
                    "traceback": task_res.get("traceback", ""),
                    "logs": task_res.get("logs", "")
                })

        # Cleanup workspace if created
        if workspace_dir:
            try:
                shutil.rmtree(workspace_dir)
            except: pass

        return json.dumps({
            "rule_code": rule_code,
            "rule_name": tasks[0].get("rule_name"),
            "tasks_executed": len(overall_results),
            "results": overall_results
        }, indent=2, default=str)

    except Exception as e:
        return f"Execution Error for {rule_code}: {str(e)}\n{traceback.format_exc()}"


@tool(approval_mode="never_require")
def summarize_rule_output(
    rule_code: Annotated[str, Field(description="The unique code of the rule (e.g. from get_available_rules or run_rule_validation).")],
    rule_description: Annotated[str, Field(description="Short description of what the rule validates or does.")],
    output: Annotated[str, Field(description="Raw output to summarize (e.g. JSON or text from run_rule_validation).")]
) -> str:
    """
    Summarizes a rule's output using a standard prompt with placeholders for rule_code,
    rule_description, and Output. The output is processed for display using Markdown and
    HTML tags: table, ul, li, h1, h2 for clear presentation.
    """
    logger.info(f"Tool Action: Summarizing rule output | Rule: {rule_code}")
    try:
        return _summarize_rule_output(rule_code, rule_description, output)
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        return f"Summarization Error: {str(e)}\n{traceback.format_exc()}"
