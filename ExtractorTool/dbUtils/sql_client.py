import os
import pyodbc
import urllib.parse
from dotenv import load_dotenv
from sqlalchemy import create_engine


class DatabaseClient:
    """
    Unified SQL Server client supporting:
    - Azure SQL
    - On-prem SQL Server
    - pyodbc connection
    - SQLAlchemy engine
    """

    def __init__(self):

        # Load .env from project root
        load_dotenv()

        server = os.getenv("DB_SERVER")
        database = os.getenv("DB_NAME")
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")
        timeout = int(os.getenv("DB_CONNECTION_TIMEOUT", "30"))
        trust_cert = os.getenv("DB_TRUST_SERVER_CERTIFICATE", "true").lower() == "true"

        if not all([server, database, user, password]):
            raise ValueError("Missing DB configuration in .env")

        is_azure = ".database.windows.net" in server.lower()

        # Detect installed ODBC driver
        drivers = pyodbc.drivers()
        driver = None

        for d in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"]:
            if d in drivers:
                driver = d
                break

        if not driver:
            raise RuntimeError("ODBC Driver 17 or 18 not installed")

        connection_string = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={user};"
            f"PWD={password};"
            f"Connection Timeout={timeout};"
        )

        if is_azure:
            connection_string += "Encrypt=yes;"
            connection_string += f"TrustServerCertificate={'yes' if trust_cert else 'no'};"
        else:
            connection_string += "TrustServerCertificate=yes;"
            if "18" in driver:
                connection_string += "Encrypt=no;"

        try:

            self.conn = pyodbc.connect(connection_string)
            self.cursor = self.conn.cursor()

            quoted = urllib.parse.quote_plus(connection_string)

            self.engine = create_engine(
                f"mssql+pyodbc:///?odbc_connect={quoted}"
            )

            print(f"Connected to {database} on {server}")

        except pyodbc.Error as e:
            print("Database connection failed:", e)
            raise

    # ------------------------------------------------
    # Connection helpers
    # ------------------------------------------------

    def get_connection(self):
        return self.conn

    def get_engine(self):
        return self.engine

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    # ------------------------------------------------
    # Query execution
    # ------------------------------------------------

    def execute(self, query, params=None):
        if params:
            return self.cursor.execute(query, params)
        return self.cursor.execute(query)

    def execute_query(self, query, params=None):
        """Alias for execute() to maintain backward compatibility."""
        return self.execute(query, params)

    def fetch_all(self):
        columns = [c[0] for c in self.cursor.description]
        return [dict(zip(columns, row)) for row in self.cursor.fetchall()]

    # ------------------------------------------------
    # Rule queries
    # ------------------------------------------------

    def list_available_rules(self, sheet_name=None):
        """Returns a distinct list of active rules for discovery."""
        query = """
        SELECT DISTINCT rule_code, rule_name, rule_group, sheet_name, rule_execution_order
        FROM [vr].vw_consolidated_validation_config
        """
        params = []
        if sheet_name:
            query += " WHERE sheet_name = ?"
            params.append(sheet_name)

        query += " ORDER BY rule_execution_order"

        self.execute(query, params)
        return self.fetch_all()

    def fetch_rule_config(self, rule_code):
        """Returns all tasks/functions associated with a specific rule."""
        query = """
        SELECT *
        FROM [vr].vw_consolidated_validation_config
        WHERE rule_code = ?
        ORDER BY task_execution_order
        """

        self.execute(query, [rule_code])
        return self.fetch_all()

    # ------------------------------------------------
    # Table operations
    # ------------------------------------------------

    def create_table(self, table_name, columns, schema="dbo"):

        cols = ", ".join([f"[{c}] NVARCHAR(MAX)" for c in columns])

        sql = f"""
        IF OBJECT_ID('{schema}.{table_name}', 'U') IS NOT NULL
        DROP TABLE [{schema}].[{table_name}];

        CREATE TABLE [{schema}].[{table_name}](
            id INT IDENTITY(1,1) PRIMARY KEY,
            {cols}
        )
        """

        self.execute(sql)
        self.conn.commit()

    def truncate_table(self, table_name, schema="dbo"):

        sql = f"TRUNCATE TABLE [{schema}].[{table_name}]"
        self.execute(sql)
        self.conn.commit()

    def insert_rows(self, table_name, columns, rows, schema="dbo"):

        cols = ",".join([f"[{c}]" for c in columns])
        placeholders = ",".join(["?"] * len(columns))

        sql = f"""
        INSERT INTO [{schema}].[{table_name}] ({cols})
        VALUES ({placeholders})
        """

        self.cursor.fast_executemany = True
        self.cursor.executemany(sql, rows)

        self.conn.commit()

    def _clean_name(self, name):
        import re
        if not name: return ""
        name = name.lower()
        name = name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_").replace("-", "_")
        name = re.sub(r'[^a-z0-9_]', '', name)
        name = re.sub(r'_+', '_', name).strip("_")
        parts = name.split("_")
        return "_".join(parts[:8])

    def __del__(self):
        self.close()

def parse_md_table(md_file):
    from bs4 import BeautifulSoup
    with open(md_file, "r", encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table: return [], []
    schema_raw = []
    thead = table.find("thead")
    if thead:
        header_row = thead.find("tr")
        if header_row:
            schema_raw = [c.get_text(strip=True) for c in header_row.find_all(["th", "td"])]
    if not schema_raw:
        first_row = table.find("tr")
        if first_row:
            schema_raw = [c.get_text(strip=True) for c in first_row.find_all(["th", "td"])]
    schema, keep_index = [], []
    for i, c in enumerate(schema_raw):
        if c.strip():
            schema.append(c)
            keep_index.append(i)
    if not schema: return [], []
    data = []
    tbody = table.find("tbody")
    data_rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]
    for r in data_rows:
        cols = r.find_all(["td", "th"])
        row = [cols[i].get_text(strip=True) if i < len(cols) else "" for i in keep_index]
        if any(row): data.append(row)
    return schema, data

def insert_md_file(db_client, md_file, table_name, schema_name="dbo"):
    schema, data = parse_md_table(md_file)
    if not schema or not data: return
    db_client.create_table(table_name, schema, schema_name) # create_table does not return a boolean, so removed the 'if'
    db_client.truncate_table(table_name, schema_name)
    db_client.insert_rows(table_name, schema, data, schema_name)
    print(f"Loaded: [{schema_name}].[{table_name}]")