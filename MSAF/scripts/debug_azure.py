import os
import asyncio
import logging
from dotenv import load_dotenv
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework import Agent

async def test_azure():
    load_dotenv(r"c:\AI-projects\afg_agno\afg_final\.env")
    
    api_key = os.getenv("OPENAI_API_KEY")
    endpoint = os.getenv("OPENAI_BASE_URL")
    deployment_name = os.getenv("OPENAI_MODEL_ID")

    print(f"Testing Azure OpenAI:")
    print(f"Endpoint: {endpoint}")
    print(f"Deployment: {deployment_name}")
    print(f"API Key: {api_key[:10]}...")

    clean_endpoint = endpoint.split("/openai")[0]
    
    client = AzureOpenAIChatClient(
        api_key=api_key,
        endpoint=clean_endpoint,
        deployment_name=deployment_name,
        timeout=30 # Short timeout for test
    )

    agent = client.as_agent(
        name="TestAgent",
        instructions=["You are a helpful assistant."],
    )

    try:
        print("Sending request...")
        response = await agent.run("Hi, can you hear me?")
        print("\nSUCCESS!")
        print(response)
    except Exception as e:
        print("\nFAILED!")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_azure())
