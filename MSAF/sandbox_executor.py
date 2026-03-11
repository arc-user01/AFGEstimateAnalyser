import sys
import json
import os
import traceback
import io
import logging
import inspect
import pandas as pd
import difflib
from typing import Dict, Any, List

def main():
    stdout_capture = io.StringIO()
    try:
        # Read the payload from stdin
        payload_raw = sys.stdin.read()
        if not payload_raw:
            return
            
        payload = json.loads(payload_raw)
        
        code = payload.get("code")
        params = payload.get("params", {})
        func_name = payload.get("func_name")
        proj_root = payload.get("proj_root")
        extractor_root = payload.get("extractor_root")
        framework_dir = payload.get("framework_dir")
        extraction_schema = payload.get("extraction_schema")
        jobID = payload.get("jobID") or payload.get("task_id", "default")
    
        # Determine schema
        if extraction_schema:
            schema_name = extraction_schema
        elif jobID and jobID != "default":
            # Sync with Extraction Service: EXACT casing, replace hyphen
            schema_name = f"ext_{jobID}".replace("-", "_")
        else:
            schema_name = "dbo"

        # Set up paths for imports
        if proj_root and proj_root not in sys.path:
            sys.path.append(proj_root)
        if extractor_root and extractor_root not in sys.path:
            sys.path.append(extractor_root)
        if framework_dir and framework_dir not in sys.path:
            sys.path.append(framework_dir)
            
        # Re-initialize project-specific dependencies
        from ExtractorTool.dbUtils.sql_client import DatabaseClient
        local_db = DatabaseClient()
        
        # Capture stdout/stderr from the rule execution
        sys.stdout = stdout_capture
        sys.stderr = stdout_capture
        
        # Setup Logger for the sandbox
        sandbox_logger = logging.getLogger("sandbox")
        sandbox_logger.setLevel(logging.INFO)
        # Clear existing handlers to avoid duplicates
        sandbox_logger.handlers = []
        handler = logging.StreamHandler(stdout_capture)
        handler.setFormatter(logging.Formatter('%(message)s'))
        sandbox_logger.addHandler(handler)
        
        import re

        # Fetch all tables belonging to the dynamic schema to correctly prefix them dynamically
        schema_tables = []
        if schema_name != "dbo":
            try:
                cur = local_db.get_connection().cursor()
                cur.execute(f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{schema_name}'")
                schema_tables = [row[0] for row in cur.fetchall()]
                cur.close()
            except Exception as e:
                sandbox_logger.warning(f"Could not fetch tables for schema {schema_name}: {e}")

        def inject_dynamic_schema(sql_query):
            if not isinstance(sql_query, str) or not schema_tables:
                return sql_query
            
            # Sort by length descending to prevent partial replacements (e.g., 'table1' vs 'table10')
            for t in sorted(schema_tables, key=len, reverse=True):
                # Replace whole word not preceded by a dot
                sql_query = re.sub(rf'(?<!\.)\b{t}\b', f'[{schema_name}].[{t}]', sql_query, flags=re.IGNORECASE)
            return sql_query

        # Wrap DB calls to auto-inject schemas
        original_execute = local_db.execute
        def wrapped_execute(query, params=None):
            return original_execute(inject_dynamic_schema(query), params)
        local_db.execute = wrapped_execute
        local_db.execute_query = wrapped_execute # Compatibility for old rules

        class PdWrapper:
            def __getattr__(self, name):
                return getattr(pd, name)
            def read_sql(self, sql, con, *args, **kwargs):
                return pd.read_sql(inject_dynamic_schema(sql), con, *args, **kwargs)

        # Setup globals for the execution
        exec_globals = {
            "parameters": params,
            "db": local_db,
            "os": os,
            "json": json,
            "pd": PdWrapper(),
            "difflib": difflib,
            "List": List,
            "traceback": traceback,
            "print": print, # Use the captured print
            "logger": sandbox_logger,
            "logging": logging,
            "sys": sys,
            "inspect": inspect,
            "schema_name": schema_name
        }

        # Auto-load 'df' if table_name is in params (many rules expect a global 'df')
        if "table_name" in params and params["table_name"] and str(params["table_name"]).lower() != "none":
            try:
                table_name = params["table_name"]
                # Use SQLAlchemy engine from local_db with schema
                df = pd.read_sql(f"SELECT * FROM [{schema_name}].[{table_name}]", local_db.get_engine())
                exec_globals["df"] = df
            except Exception as df_e:
                # Log to the captured output
                print(f"[SANDBOX] Warning: Could not auto-load 'df' for table '{params.get('table_name')}': {df_e}")

        # Execute the function definition code
        exec(code, exec_globals)
        
        # Find the target function
        target_func = exec_globals.get(func_name)
        if not target_func:
            sys.stdout = sys.__stdout__
            print(json.dumps({"success": False, "error": f"Function '{func_name}' not found in rule code."}))
            return

        # Dependency Injection Logic (Mimic tools.py behavior)
        sig = inspect.signature(target_func)
        valid_args = {}
        for k, p in sig.parameters.items():
            if k in params:
                valid_args[k] = params[k]
            elif k == "conn":
                valid_args["conn"] = local_db.get_connection()
            elif k == "utils" or k == "uc":
                try:
                    from py_validationRules.utilsClass import PyUtils
                    valid_args[k] = PyUtils()
                except ImportError:
                    # Fallback if utilsClass isn't available in this context
                    pass

        # Run the function with injected parameters
        result = target_func(**valid_args)
        
        # Restore stdout and return JSON
        output = stdout_capture.getvalue()
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        
        # Custom JSON serializer to handle DataFrames and other non-serializable types
        def safe_serialize(obj):
            if isinstance(obj, pd.DataFrame):
                return obj.to_dict(orient='records')
            if hasattr(obj, 'to_dict'):
                try: return obj.to_dict()
                except: pass
            return str(obj)

        print(json.dumps({
            "success": True, 
            "result": result, 
            "output": output
        }, default=safe_serialize))

    except Exception as e:
        # Restore stdout on error
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        print(json.dumps({
            "success": False, 
            "error": str(e), 
            "traceback": traceback.format_exc(),
            "output": stdout_capture.getvalue()
        }))

if __name__ == "__main__":
    main()
