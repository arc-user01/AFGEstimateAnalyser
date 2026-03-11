import pyodbc
import os
from dotenv import load_dotenv

load_dotenv()

server = os.getenv("DB_SERVER")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")

dbs = ["sql-afg-pmo-ai-dev", "sql-afg-pmo-dev", "sql-afg-backend-dev"]

def check_db(db_name):
    conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={db_name};UID={user};PWD={password};TrustServerCertificate=yes;"
    try:
        conn = pyodbc.connect(conn_str, timeout=10)
        cur = conn.cursor()
        print(f"[{db_name}] Connected.")
        
        # Check for the view
        cur.execute("SELECT COUNT(*) FROM sys.views WHERE name = 'consolidated_validation_rules'")
        count = cur.fetchone()[0]
        if count > 0:
            print(f"[{db_name}] Found 'consolidated_validation_rules' view.")
            # Check rule count
            cur.execute("SELECT COUNT(*) FROM consolidated_validation_rules")
            rules = cur.fetchone()[0]
            print(f"[{db_name}] Rules count: {rules}")
        else:
            print(f"[{db_name}] View 'consolidated_validation_rules' NOT found.")
        
        conn.close()
    except Exception as e:
        print(f"[{db_name}] Connection failed: {e}")

for db in dbs:
    check_db(db)
