from MSAF.workflow import workflow
import json

try:
    data = workflow.to_dict()
    print("Serialization success!")
    # print(json.dumps(data, indent=2)) # Might be too large
    print(f"Num executors: {len(data['executors'])}")
    print(f"Num edge groups: {len(data['edge_groups'])}")
except Exception as e:
    print(f"Serialization failed: {e}")
    import traceback
    traceback.print_exc()
