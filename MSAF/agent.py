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
        
        # MOCK RESPONSE FOR FRONTEND INTEGRATION PHASE
        mock_response = "Hi there ! Good to see You again , How may i help you .."
        self.logger.info(f"Returning MOCK RESPONSE: {mock_response}")
        return mock_response

        # Original logic commented out for now
        """
        max_retries = 3
        retry_delay = 5 # seconds
        ...
        """

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
