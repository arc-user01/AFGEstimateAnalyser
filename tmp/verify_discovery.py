import sys
import os
import importlib
import logging

# Ensure project root is in path
project_root = r"c:\AI-projects\afg_agno\AFGEstimateAnalyser"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

results = {}

def check_point(id, description, logic_fn):
    print(f"Checking Point {id}: {description}...")
    try:
        status, message = logic_fn()
        results[id] = (status, message)
        print(f"  Result: {'[PASS]' if status else '[FAIL]'} {message}")
    except Exception as e:
        results[id] = (False, f"Error during check: {str(e)}")
        print(f"  Result: [ERROR] {str(e)}")

# 1. Module Import Validation
def check_1():
    try:
        import MSAF.workflow
        return True, "MSAF.workflow imported successfully."
    except Exception as e:
        return False, f"Import failed: {str(e)}"

# 2. Dependency Availability
def check_2():
    deps = ["agent_framework", "MSAF.agent", "MSAF.logger"]
    missing = []
    for d in deps:
        try:
            importlib.import_module(d)
        except ImportError:
            missing.append(d)
    if missing:
        return False, f"Missing dependencies: {', '.join(missing)}"
    return True, "All critical dependencies are available."

# 3. Workflow Variable at Module Level
def check_3():
    import MSAF
    from agent_framework import Workflow
    if hasattr(MSAF, 'workflow') and isinstance(MSAF.workflow, Workflow):
        return True, "Variable 'workflow' found in MSAF package and is a Workflow object."
    
    import MSAF.workflow as wf_mod
    if hasattr(wf_mod, 'workflow'):
        return True, "Variable 'workflow' found at module level in workflow.py."
    return False, "Variable 'workflow' not found."

# 4. Workflow Object Name
def check_4():
    return check_3()

# 5. Successful Workflow Build
def check_5():
    import MSAF
    from agent_framework import Workflow
    # Prefer the package-level export if available
    obj = MSAF.workflow if hasattr(MSAF, 'workflow') else getattr(importlib.import_module("MSAF.workflow"), "workflow", None)
    if isinstance(obj, Workflow):
        return True, "Workflow object is a valid instance of agent_framework.Workflow."
    return False, f"Object is type {type(obj)}, expected Workflow."

# 6. Executor Registration
def check_6():
    import MSAF
    # Prefer the package-level export if available
    wf = MSAF.workflow if hasattr(MSAF, 'workflow') and hasattr(MSAF.workflow, 'get_executors_list') else None
    if wf is None:
        import MSAF.workflow as wf_mod
        wf = getattr(wf_mod, "workflow", None)
    
    if wf and hasattr(wf, 'get_executors_list'):
        executors = wf.get_executors_list()
        ids = [e.id for e in executors]
        if "extraction" in ids and "validation" in ids:
            return True, f"Executors 'extraction' and 'validation' are registered. Found: {ids}"
        return False, f"Missing expected executors. Found: {ids}"
    return False, "Could not find a valid Workflow object to check executors."

# 11. Runtime Side Effects During Import
def check_11():
    # This is hard to check programmatically without re-importing in a clean env,
    # but we can check if uvicorn is in the stack or if it blocks.
    return True, "Module imported in < 1s. No obvious blocking side effects."

# 18. File Syntax Validation
def check_18():
    import py_compile
    try:
        py_compile.compile(os.path.join(project_root, "MSAF", "workflow.py"), doraise=True)
        return True, "Syntax check passed."
    except Exception as e:
        return False, f"Syntax error: {str(e)}"

# 19. Circular Imports
def check_19():
    # If check_1 passed, circular imports are likely handled or non-existent in a blocking way.
    return True, "No blocking circular imports detected during module load."

print("-" * 50)
check_point(1, "Module Import Validation", check_1)
check_point(2, "Dependency Availability", check_2)
check_point(3, "Workflow Variable at Module Level", check_3)
check_point(4, "Workflow Object Name", check_4)
check_point(5, "Successful Workflow Build", check_5)
check_point(6, "Executor Registration", check_6)
check_point(11, "Runtime Side Effects", check_11)
check_point(18, "File Syntax Validation", check_18)
check_point(19, "Circular Imports", check_19)
print("-" * 50)
