import os
import json
import requests
import logging
from typing import Dict, Any, List, Optional, Union

from agent_framework import (
    WorkflowBuilder,
    WorkflowContext,
    executor
)

from MSAF.logger import setup_task_logger
from ExtractorTool.dbUtils.sql_client import DatabaseClient
from MSAF.tools import run_rule_validation, summarize_rule_output


# ------------------------------------------------
# INPUT NORMALIZATION (User-provided logic)
# ------------------------------------------------

def normalize_input(data):
    # Level 1
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except:
            return {"jobID": data}

    # Level 2
    if isinstance(data, dict) and "input" in data:
        inner = data["input"]

        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except:
                pass

        if isinstance(inner, dict) and "input" in inner:
            try:
                inner = json.loads(inner["input"])
            except:
                pass

        if isinstance(inner, dict):
            return inner

    return data if isinstance(data, dict) else {}


# ------------------------------------------------
# HUMAN INPUT NODE (Start)
# ------------------------------------------------

@executor(id="request_input")
async def request_input(data: Any, ctx: WorkflowContext) -> dict:
    """Prompt the user for input if not already provided."""
    print(f"\n[TRACE] Node: request_input | Raw Input: {data}")
    
    normalized = normalize_input(data)
    
    # Check if we have the minimum required fields
    if not normalized or "jobID" not in normalized:
        prompt = "Hello! Please provide the validation job details in JSON format (jobID, tco_file_url, retry_flag)."
        print(f"[TRACE] Node: request_input | Missing jobID, yielding prompt.")
        await ctx.yield_output(prompt)
        
        # Wait for the next message from the user
        user_msg = await ctx.wait_for_message()
        print(f"[TRACE] Node: request_input | Received user message: {user_msg}")
        normalized = normalize_input(user_msg)
    
    print(f"[TRACE] Node: request_input | Proceeding with: {normalized}")
    await ctx.send_message(normalized)
    return normalized


# ------------------------------------------------
# EXTRACTION NODE
# ------------------------------------------------

@executor(id="extraction")
async def extract_data(input_data: dict, ctx: WorkflowContext) -> dict:
    print(f"\n[TRACE] Node: extract_data | Input: {input_data}")
    
    data = normalize_input(input_data)
    jobID = str(data.get("jobID") or data.get("task_id") or "default")
    extraction_schema = f"ext_{jobID}"
    
    # Store jobID in context state for subsequent nodes using .set()
    ctx.state.set("jobID", jobID)
    
    logger = setup_task_logger(jobID, f"Workflow_{jobID}")
    logger.info(f"Phase 1: Extraction node triggered for Job {jobID}")

    tco_file_url = data.get("tco_file_url") or data.get("tco_file_path")
    retry_flag = data.get("retry_flag", False)
    
    extraction_url = os.getenv("EXTRACTION_SERVICE_URL", "http://localhost:1204")
    detection_result = {"status": "skipped", "extraction_schema": extraction_schema, "detected_mode": "capex"}

    if not retry_flag and tco_file_url:
        tco_path = tco_file_url.replace("file:///", "").replace("file://", "")
        payload = {
            "jobID": jobID,
            "tco_file_path": tco_path
        }
        
        try:
            logger.info(f"Triggering Extraction Service at {extraction_url}/extract")
            response = requests.post(f"{extraction_url}/extract", json=payload, timeout=300)
            if response.status_code == 200:
                detection_result = response.json()
                logger.info(f"Extraction Service Success: {detection_result}")
            else:
                logger.error(f"Extraction Service Error ({response.status_code}): {response.text}")
                detection_result = {"status": "error", "message": response.text, "extraction_schema": extraction_schema}
        except Exception as e:
            logger.error(f"Extraction error: {e}")
            detection_result = {"status": "error", "message": str(e), "extraction_schema": extraction_schema}
    
    output_payload = {
        "extraction_result": detection_result,
        "jobID": jobID,
        "extraction_schema": extraction_schema,
        "detected_mode": detection_result.get("detected_mode", "capex")
    }
    
    # Send message to downstream nodes
    await ctx.send_message(output_payload)
    return output_payload


# ------------------------------------------------
# RULE DISCOVERY NODE
# ------------------------------------------------

@executor(id="rule_discovery")
async def discover_rules(prev_output: dict, ctx: WorkflowContext) -> dict:
    print(f"\n[TRACE] Node: rule_discovery | Input: {prev_output}")
    
    jobID = prev_output.get("jobID")
    extraction_schema = prev_output.get("extraction_schema")
    detected_mode = prev_output.get("detected_mode", "capex")
    
    logger = setup_task_logger(jobID, f"Workflow_{jobID}")
    logger.info(f"Phase 2: Discovering rules for mode '{detected_mode}'")

    db = DatabaseClient()
    rules = []
    try:
        rules = db.list_available_rules(sheet_name=detected_mode)
    except Exception as e:
        logger.error(f"Discovery error: {e}")

    # Build a list of dicts with rule_code and rule_name
    rule_configs = [{"rule_code": r["rule_code"], "rule_name": r.get("rule_name", r["rule_code"])} for r in rules]
    logger.info(f"Rule Discovery completed. Rules found: {[r['rule_code'] for r in rule_configs]}")
    
    output_payload = {
        "jobID": jobID,
        "rules": rule_configs,
        "extraction_schema": extraction_schema
    }
    
    await ctx.send_message(output_payload)
    return output_payload


# ------------------------------------------------
# EXECUTE RULES NODE
# ------------------------------------------------

import tempfile

@executor(id="execute_rules")
async def execute_rules(prev_output: dict, ctx: WorkflowContext) -> dict:
    print(f"\n[TRACE] Node: execute_rules | Input: {prev_output}")
    
    jobID = prev_output.get("jobID")
    extraction_schema = prev_output.get("extraction_schema")
    rules = prev_output.get("rules", [])
    
    logger = setup_task_logger(jobID, f"Workflow_{jobID}")
    logger.info(f"Phase 3: Executing {len(rules)} rules sequentially")

    results_dict = {}

    for rule in rules:
        rule_code = rule["rule_code"]
        rule_desc = rule.get("rule_name", rule_code)
        
        logger.info(f"  -> Running rule: {rule_code}")
        
        # 1. Execute task
        try:
            # run_rule_validation is a @tool, but can be called directly in python
            raw_output = run_rule_validation(rule_code=rule_code, extraction_schema=extraction_schema)
        except Exception as e:
            raw_output = f"Execution failed locally: {str(e)}"
            
        # 2. Summarize task
        try:
            summary = summarize_rule_output(rule_code=rule_code, rule_description=rule_desc, output=raw_output)
        except Exception as e:
            summary = f"Summarization failed: {str(e)}"
            
        results_dict[rule_code] = summary
        
    # 3. Store results in a temp JSON configuration
    # Use system temp directory directly
    temp_json_path = os.path.join(tempfile.gettempdir(), f"validation_results_{jobID}.json")
    
    try:
        with open(temp_json_path, "w", encoding="utf-8") as f:
            json.dump(results_dict, f, indent=2)
        logger.info(f"Saved aggregated rule results to: {temp_json_path}")
    except Exception as e:
        logger.error(f"Failed to save temp JSON: {e}")

    output_payload = {
        "jobID": jobID,
        "extraction_schema": extraction_schema,
        "results_file": temp_json_path,
        "results": results_dict
    }
    
    await ctx.send_message(output_payload)
    return output_payload


# ------------------------------------------------
# FINAL REPORT
# ------------------------------------------------

@executor(id="final_report")
async def finalize_report(prev_output: dict, ctx: WorkflowContext) -> dict:
    print(f"\n[TRACE] Node: final_report | Input keys: {list(prev_output.keys())}")
    
    jobID = prev_output.get("jobID", ctx.state.get("jobID", "unknown"))
    results = prev_output.get("results", {})
    
    logger = setup_task_logger(jobID, f"Workflow_{jobID}")
    logger.info("Phase 4: Generating Final Report Response")

    # The user requested: {job_id: result : <json of all the rules>}
    output_payload = {
        "jobID": jobID,
        "status": "success",
        "result": results
    }
    
    await ctx.yield_output(output_payload)
    return output_payload


# ------------------------------------------------
# WORKFLOW DEFINITION
# ------------------------------------------------

workflow = (
    WorkflowBuilder(
        name="MSAF_Validation_Workflow",
        description="AFG programmatic estimate validation workflow",
        start_executor=request_input
    )
    .add_edge(request_input, extract_data)
    .add_edge(extract_data, discover_rules)
    .add_edge(discover_rules, execute_rules)
    .add_edge(execute_rules, finalize_report)
    .build()
)


# ------------------------------------------------
# LEGACY ENTRY POINT
# ------------------------------------------------

async def run_msaf_workflow(jobID: str, tco_file_url: str = None, questionaries_file_url: str = None, retry_flag: bool = False):
    """Bridge for main.py to trigger the graph-based workflow."""
    
    input_payload = {
        "jobID": jobID,
        "tco_file_url": tco_file_url,
        "retry_flag": retry_flag,
        "questionaries_file_url": questionaries_file_url
    }
    
    # Run the workflow graph
    result_obj = await workflow.run(message=input_payload)
    
    # Extract final output
    outputs = result_obj.get_outputs() if hasattr(result_obj, "get_outputs") else result_obj
    
    if outputs:
        last_output = outputs[-1]
        if isinstance(last_output, dict) and "result" in last_output:
            return last_output 
        return {"status": "success", "jobID": jobID, "result": str(last_output)}
        
    return {"status": "error", "error": "Workflow did not produce outputs"}

