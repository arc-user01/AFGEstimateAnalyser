import os
import json
import requests
import logging
from typing import Dict, Any, List, Optional, Union

from agent_framework import (
    WorkflowBuilder,
    WorkflowContext,
    executor,
    AgentExecutor,
    AgentExecutorRequest,
    Message,
    Case,
    Default
)

# Rename 'agent' import to hide it from DevUI discovery
# DevUI looks for 'agent' or 'workflow' variables to identify the entity type.
# If 'agent' is imported at top level, it might misclassify this graph as a chat agent.
from MSAF.agent import agent as _validation_agent
from MSAF.logger import setup_task_logger
from ExtractorTool.dbUtils.sql_client import DatabaseClient


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
# EXTRACTION NODE
# ------------------------------------------------

@executor(id="extraction")
async def extract_data(input_data: dict, ctx: WorkflowContext) -> dict:
    print(f"\n[TRACE] Node: extract_data | Input type: {type(input_data)}")
    
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
    
    # Send message to downstream nodes (REQUIRED for graph traversal)
    await ctx.send_message(output_payload)
    
    return output_payload


# ------------------------------------------------
# RULE DISCOVERY NODE
# ------------------------------------------------

@executor(id="rule_discovery")
async def discover_rules(prev_output: dict, ctx: WorkflowContext) -> dict:
    print(f"\n[TRACE] Node: rule_discovery | Input type: {type(prev_output)}")
    
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

    rule_codes = [r["rule_code"] for r in rules]
    logger.info(f"Rule Discovery completed. Rules found: {rule_codes}")
    
    output_payload = {
        "jobID": jobID,
        "rules": rule_codes,
        "detected_mode": detected_mode,
        "extraction_schema": extraction_schema
    }
    
    await ctx.send_message(output_payload)
    
    return output_payload


# ------------------------------------------------
# RULE ORCHESTRATOR NODE
# ------------------------------------------------

@executor(id="rule_orchestrator")
async def orchestrate_rules(prev_output: dict, ctx: WorkflowContext) -> dict:
    print(f"\n[TRACE] Node: rule_orchestrator | Input type: {type(prev_output)}")
    
    jobID = prev_output.get("jobID")
    extraction_schema = prev_output.get("extraction_schema")
    rules = prev_output.get("rules", [])
    
    logger = setup_task_logger(jobID, f"Workflow_{jobID}")
    logger.info(f"Phase 3: Orchestrating {len(rules)} rules")

    # Store results in state using .get() and .set()
    results = ctx.state.get("orchestration_results") or []
    results.append({"jobID": jobID, "rules_count": len(rules)})
    ctx.state.set("orchestration_results", results)

    output_payload = {
        "jobID": jobID,
        "extraction_schema": extraction_schema,
        "route": "agent" if rules else "final",
        "query": f"The extraction for job {jobID} in schema {extraction_schema} is complete. {len(rules)} rules were identified."
    }
    
    await ctx.send_message(output_payload)
    
    return output_payload


# ------------------------------------------------
# PREPARE AGENT REQUEST
# ------------------------------------------------

@executor(id="prepare_agent_request")
async def prepare_agent_request(prev_output: dict, ctx: WorkflowContext) -> AgentExecutorRequest:
    print(f"\n[TRACE] Node: prepare_agent_request | Input type: {type(prev_output)}")
    query = prev_output.get("query", "No query provided.")
    
    request = AgentExecutorRequest(
        messages=[Message(role="user", contents=[query])]
    )
    
    await ctx.send_message(request)
    
    return request


# ------------------------------------------------
# FINAL REPORT
# ------------------------------------------------

@executor(id="final_report")
async def finalize_report(data: Union[dict, Any], ctx: WorkflowContext) -> dict:
    print(f"\n[TRACE] Node: final_report | Input type: {type(data)}")
    
    jobID = ctx.state.get("jobID", "unknown")
    
    if isinstance(data, dict):
        response = data.get("query", data.get("response", "No details available."))
    else:
        # Assume it's an Agent Response
        response = str(data)

    report = f"# MSAF Validation Report\n\n- Job ID: {jobID}\n\n## Final Assessment\n{response}\n"

    output_payload = {
        "status": "success",
        "jobID": jobID,
        "response": report
    }
    
    await ctx.yield_output(output_payload)
    
    return output_payload


# Define the Validation Agent Node using the HIDDEN agent import
validation_agent_node = AgentExecutor(
    agent=_validation_agent,
    id="validation_agent"
)


# ------------------------------------------------
# WORKFLOW DEFINITION
# ------------------------------------------------

workflow = (
    WorkflowBuilder(
        name="MSAF_Validation_Workflow",
        description="AFG estimate validation workflow",
        start_executor=extract_data
    )
    .add_edge(extract_data, discover_rules)
    .add_edge(discover_rules, orchestrate_rules)
    .add_switch_case_edge_group(
        orchestrate_rules,
        [
            Case(
                condition=lambda data: isinstance(data, dict) and data.get("route") == "agent",
                target=prepare_agent_request
            ),
            Default(target=finalize_report)
        ]
    )
    .add_edge(prepare_agent_request, validation_agent_node)
    .add_edge(validation_agent_node, finalize_report)
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
        if isinstance(last_output, dict) and "response" in last_output:
            return last_output 
        return {"status": "success", "jobID": jobID, "response": str(last_output)}
        
    return {"status": "error", "error": "Workflow did not produce outputs"}
