import os
import pyodbc
from dotenv import load_dotenv

class DatabaseClient:
    """
    A unified SQL client for interacting with the project's SQL Server database.
    Loads configuration from the .env file in the project root.
    """
    def __init__(self):
        # Load .env if not already loaded (standard path relative to project root)
        # Assuming this file is in <PROJECT_ROOT>/sql_client.py
        proj_root = os.path.dirname(os.path.abspath(__file__))
        load_dotenv(os.path.join(proj_root, ".env"))
        
        server = os.getenv("DB_SERVER", "localhost,1433")
        user = os.getenv("DB_USER", "sa")
        password = os.getenv("DB_PASSWORD", "afg_admin@5623")
        database = os.getenv("DB_NAME", "testdb")
        
        # SQL Server Driver selection (prefer ODBC Driver 17/18 for SQL Server)
        driver = "{ODBC Driver 17 for SQL Server}"
        
        connection_string = (
            f"DRIVER={driver};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={user};"
            f"PWD={password};"
            "TrustServerCertificate=yes;"
        )
        
        try:
            self.conn = pyodbc.connect(connection_string)
            self.cur = self.conn.cursor()
            print(f"Connected to Database: {database} on {server}")
        except Exception as e:
            print(f"Database Connection Failed: {e}")
            raise e

    def __del__(self):
        """Ensures the connection is closed when the object is destroyed."""
        if hasattr(self, 'conn'):
            try:
                self.conn.close()
            except:
                pass
