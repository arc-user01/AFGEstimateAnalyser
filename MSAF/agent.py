import asyncio
import os
import logging
import sys
from dotenv import load_dotenv
from typing import List, Optional

# Microsoft Agent Framework Imports
from agent_framework.azure import AzureOpenAIChatClient

# Local Imports
from MSAF.tools import get_available_rules, run_rule_validation
from MSAF.logger import setup_task_logger

# Load .env from the parent project's root
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(os.path.dirname(current_dir), '.env')
load_dotenv(env_path)

class AgentOrchestrator:
    def __init__(self, task_id: str, logger: Optional[logging.Logger] = None):
        self.task_id = task_id
        self.logger = logger or logging.getLogger(f"Agent_{task_id}")
        self.client = self._initialize_client()

    def _initialize_client(self):
        # Get configuration from environment variables (No hardcoding)
        api_key = os.getenv("OPENAI_API_KEY")
        endpoint = os.getenv("OPENAI_BASE_URL")
        deployment_name = os.getenv("OPENAI_MODEL_ID")

        if not all([api_key, endpoint, deployment_name]):
            self.logger.error("Missing OpenAI configuration in environment.")
            raise EnvironmentError("OPENAI_API_KEY, OPENAI_BASE_URL, and OPENAI_MODEL_ID must be set.")

        # Process the endpoint - framework expects the resource endpoint, not the /v1 suffix
        clean_endpoint = endpoint.split("/openai")[0]
        
        return AzureOpenAIChatClient(
            api_key=api_key,
            endpoint=clean_endpoint,
            deployment_name=deployment_name,
            timeout=600 # 10 minute timeout for complex enterprise tasks
        )

    async def run_task(self, query: str) -> str:
        self.logger.info(f"Starting Microsoft Agent task [{self.task_id}] with query: {query}")
        
        max_retries = 3
        retry_delay = 5 # seconds
        
        try:
            for attempt in range(1, max_retries + 1):
                try:
                    # Professional instructions with strict tool usage enforcement
                    professional_instructions = [
                        f"You are the 'MSAF estimate Analyser' Super Agent for task {self.task_id}.",
                        "Your objective is to validate Excel data against database-defined business rules after extraction is complete.",
                        "**STRICT RESTRAINT (CRITICAL)**:",
                        "1. DO NOT attempt to write, execute, or explain Python code yourself.",
                        "2. You MUST use 'get_available_rules' to discover rules and 'run_rule_validation' to execute them.",
                        "3. If you see code in the rule description, IGNORE IT and just call 'run_rule_validation'.",
                        "**Step-by-Step Workflow (CRITICAL)**:",
                        "1. Call 'get_available_rules' with the `sheet_name` matching the delivery mode (e.g., 'waterfall' or 'agile') provided in the user prompt.",
                        "2. You MUST identify **every single rule_code** in the returned JSON list.",
                        "3. You MUST call 'run_rule_validation(rule_code)' sequentially for **EACH AND EVERY** rule_code found in step 1.",
                        "4. Do NOT stop after executing just one rule. Iterate through the entire list.",
                        "**Rule Summarization (CRITICAL)**:",
                        "   - You must act as a 'Summarization Tool' for EACH rule executed.",
                        "   - Use the 'rule_description' and 'task_description' from the rule configuration to explain WHAT was checked.",
                        "   - If a rule fails with a 'technical error' or 'Execution Error', report the specific error message.",
                        "   - Format the findings from the raw data into a professional, human-readable summary.",
                        "**Visual Reporting (CRITICAL)**:",
                        "   - Group your report by Rule Code.",
                        "   - Start each rule section with: '--- # [Rule Code] - [Rule Name]'.",
                        "   - Provide the summarized findings underneath.",
                        "   - Confirm at the bottom that all matched rules were executed."
                    ]
                    self.logger.info(f"Agent Instructions: Setting professional orchestration instructions for task {self.task_id}")

                    agent = self.client.as_agent(
                        name=f"MSAF_Analyser_{self.task_id}",
                        instructions=professional_instructions,
                        tools=[get_available_rules, run_rule_validation],
                    )

                    # Attempt to run the agent
                    self.logger.info(f"Execution attempt {attempt}/{max_retries}...")
                    result = await agent.run(query, timeout=600)
                    self.logger.info(f"Task {self.task_id} completed successfully on attempt {attempt}.")
                    return str(result.content) if hasattr(result, 'content') else str(result)
                    
                except Exception as e:
                    error_type = type(e).__name__
                    self.logger.error(f"Attempt {attempt} FAILED for task {self.task_id}. Error: {error_type} - {str(e)}")
                    
                    if "timeout" in str(e).lower() or "rate limit" in str(e).lower():
                        if attempt < max_retries:
                            wait_time = retry_delay * attempt
                            self.logger.info(f"Retrying in {wait_time}s due to timeout/transient error...")
                            await asyncio.sleep(wait_time)
                            continue
                    
                    # If we've exhausted retries or it's a non-retriable error
                    if attempt == max_retries:
                        self.logger.error(f"All {max_retries} attempts failed for task {self.task_id}.")
                        raise e
                    else:
                        # For other errors, wait a bit and retry anyway to be robust
                        await asyncio.sleep(retry_delay)
        except Exception as e:
            self.logger.error(f"Error during agent execution for task {self.task_id}: {e}")
            raise e

async def main() -> None:
    # CLI compatibility (legacy mode)
    task_id = "cli_standalone"
    logger = setup_task_logger(task_id, "MicrosoftDataValidator")
    
    query = "Please find and run the relevant validation rules for the project."
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])

    orchestrator = AgentOrchestrator(task_id, logger)
    try:
        result = await orchestrator.run_task(query)
        print("\n" + "="*50 + "\nMICROSOFT AGENT RESPONSE:\n" + "="*50)
        print(result)
    except Exception as e:
        print(f"Agent execution failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
