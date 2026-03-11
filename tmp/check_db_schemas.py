import os
import pyodbc
from dotenv import load_dotenv

def check_db():
    load_dotenv()
    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    
    conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={user};PWD={password}"
    
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        print(f"Listing all schemas in database: {database}...")
        cursor.execute("SELECT name FROM sys.schemas")
        rows = cursor.fetchall()
        for row in rows:
            schema_name = row.name
            if "DevUI" in schema_name or schema_name.startswith("ext"):
                print(f"Schema: {schema_name}")
            # Now check tables in this schema
            try:
                cursor.execute(f"SELECT name FROM sys.tables WHERE schema_id = SCHEMA_ID(?)", (schema_name,))
                tables = cursor.fetchall()
                if not tables:
                    # Skip printing for system schemas if empty to keep output clean
                    if not schema_name.startswith('db_') and schema_name not in ('sys', 'INFORMATION_SCHEMA'):
                        print(f"  -> No tables in schema {schema_name}")
                else:
                    for t in tables:
                        print(f"  -> Table: {t.name}")
            except Exception as e:
                print(f"  -> Error checking tables in {schema_name}: {e}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    check_db()
