import asyncio
from MSAF.workflow import workflow

async def inspect():
    try:
        # Minimal input to trigger start
        result = await workflow.run(message={"jobID": "test"})
        print(f"Result Type: {type(result)}")
        print(f"Available attributes: {dir(result)}")
    except Exception as e:
        print(f"Error during inspection: {e}")

if __name__ == "__main__":
    asyncio.run(inspect())
