import os
from dotenv import load_dotenv
from agent_framework.azure import AzureOpenAIChatClient

load_dotenv(r"c:\AI-projects\afg_agno\afg_final\.env")

api_key = os.getenv("OPENAI_API_KEY")
endpoint = os.getenv("OPENAI_BASE_URL")
deployment_name = os.getenv("OPENAI_MODEL_ID")
clean_endpoint = endpoint.split("/openai")[0]

client = AzureOpenAIChatClient(
    api_key=api_key,
    endpoint=clean_endpoint,
    deployment_name=deployment_name,
    timeout=600
)

print(f"Client: {client}")
# Try to find where timeout is stored
for attr in dir(client):
    if "timeout" in attr.lower():
        try:
            val = getattr(client, attr)
            print(f"Attribute {attr}: {val}")
        except:
            pass

# Check the underlying openai client if it exists
if hasattr(client, "_chat_client"):
    cc = getattr(client, "_chat_client")
    print(f"Internal Chat Client: {cc}")
    if hasattr(cc, "timeout"):
        print(f"Internal Timeout: {cc.timeout}")
