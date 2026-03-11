import pyodbc
import os
from dotenv import load_dotenv

load_dotenv()

print("Available Drivers:")
drivers = pyodbc.drivers()
for d in drivers:
    print(f" - {d}")

driver = None
for name in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"):
    if any(name in d for d in drivers):
        driver = "{" + name + "}"
        break

print(f"\nSelected Driver: {driver}")

server = os.getenv("DB_SERVER")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
database = "sql-afg-backend-dev"

if driver and server:
    conn_str = f"DRIVER={driver};SERVER={server};DATABASE={database};UID={user};PWD={password};TrustServerCertificate=yes;"
    if "ODBC Driver 18" in driver:
        conn_str += "Encrypt=yes;"
    
    print(f"\nTesting Connection String (Masked): {conn_str.replace(password, '***')}")
    
    try:
        conn = pyodbc.connect(conn_str)
        print("Success! Connected to cloud.")
        conn.close()
    except Exception as e:
        print(f"Connection Failed: {e}")
else:
    print("Driver or Server not found.")
