import asyncio
import os
import logging
import sys
from typing import Optional

from dotenv import load_dotenv

from agent_framework import Agent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.observability import enable_instrumentation

from MSAF.tools import get_available_rules, run_rule_validation
from MSAF.logger import setup_task_logger


# ------------------------------------------------
# LOAD ENV
# ------------------------------------------------

current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(os.path.dirname(current_dir), ".env")
load_dotenv(env_path)

enable_instrumentation()


# ------------------------------------------------
# AZURE CLIENT
# ------------------------------------------------

def create_client():

    api_key = os.getenv("OPENAI_API_KEY")
    endpoint = os.getenv("OPENAI_BASE_URL")
    deployment_name = os.getenv("OPENAI_MODEL_ID")

    if not all([api_key, endpoint, deployment_name]):
        raise RuntimeError(
            "Missing OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL_ID"
        )

    clean_endpoint = endpoint.split("/openai")[0]

    return AzureOpenAIChatClient(
        api_key=api_key,
        endpoint=clean_endpoint,
        deployment_name=deployment_name,
        timeout=600
    )


# ------------------------------------------------
# AGENT
# ------------------------------------------------

class AgentOrchestrator(Agent):

    def __init__(self):

        client = create_client()

        super().__init__(
            client=client,
            name="AFG_Estimate_Validator",
            description="Validates AFG estimates using rule engine.",
            tools=[get_available_rules, run_rule_validation],
            instructions="Run validation rules on extracted estimate data."
        )


# ------------------------------------------------
# DEVUI DISCOVERY ENTITY
# ------------------------------------------------

agent = AgentOrchestrator()


# ------------------------------------------------
# CLI TEST MODE
# ------------------------------------------------

async def main():

    logger = setup_task_logger("cli", "AgentTest")

    orchestrator = AgentOrchestrator()

    query = "Run validation rules for this project."

    async with orchestrator:

        result = await orchestrator.run(query)

        print(result.text)


if __name__ == "__main__":
    asyncio.run(main())