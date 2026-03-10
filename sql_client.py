import os
import pyodbc
from urllib.parse import unquote
from dotenv import load_dotenv

class DatabaseClient:
    """
    A unified SQL client for interacting with the project's SQL Server database.
    Loads configuration from the .env file in the project root.
    Supports Azure SQL (database.windows.net) and on-premises SQL Server.
    """
    def __init__(self):
        # Load .env if not already loaded (standard path relative to project root)
        proj_root = os.path.dirname(os.path.abspath(__file__))
        load_dotenv(os.path.join(proj_root, ".env"))
        
        server = (os.getenv("DB_SERVER") or "localhost,1433").strip()
        user = (os.getenv("DB_USER") or "sa").strip()
        raw_password = os.getenv("DB_PASSWORD", "")
        # Decode URL-style encoding in password (e.g. %40 -> @)
        password = unquote(raw_password) if raw_password else ""
        database = (os.getenv("DB_NAME") or "testdb").strip()
        
        is_azure = ".database.windows.net" in server.lower()
        timeout = os.getenv("DB_CONNECTION_TIMEOUT", "90" if is_azure else "30").strip()
        try:
            timeout = int(timeout)
        except ValueError:
            timeout = 90 if is_azure else 30
        
        # Prefer ODBC Driver 18, fall back to 17 (required for Azure SQL)
        all_drivers = pyodbc.drivers()
        driver = None
        for name in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"):
            if any(name in d for d in all_drivers):
                driver = "{" + name + "}"
                break
        if not driver:
            raise RuntimeError(
                "No ODBC Driver 17 or 18 for SQL Server found. Install: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server"
            )
        
        connection_string = (
            f"DRIVER={driver};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={user};"
            f"PWD={password};"
            f"Connection Timeout={timeout};"
        )
        trust_cert = (os.getenv("DB_TRUST_SERVER_CERTIFICATE", "").strip().lower() in ("1", "true", "yes"))
        if is_azure:
            connection_string += "Encrypt=yes;"
            connection_string += "TrustServerCertificate=yes;" if trust_cert else "TrustServerCertificate=no;"
        else:
            connection_string += "TrustServerCertificate=yes;"
        
        try:
            self.conn = pyodbc.connect(connection_string)
            self.cur = self.conn.cursor()
            print(f"Connected to Database: {database} on {server}")
        except pyodbc.Error as e:
            msg = str(e).strip()
            hint = []
            if is_azure:
                hint.append("Azure firewall: add your client IP in Azure Portal -> SQL server -> Networking.")
            hint.append("Check DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME in .env (use @ in password as-is or as %40).")
            hint.append("Ensure ODBC Driver 17 or 18 for SQL Server is installed.")
            print(f"Database Connection Failed: {msg}")
            print("Tips: " + " ".join(hint))
            raise e

    def __del__(self):
        """Ensures the connection is closed when the object is destroyed."""
        if hasattr(self, 'conn'):
            try:
                self.conn.close()
            except:
                pass
