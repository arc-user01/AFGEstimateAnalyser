import pyodbc
import os
import json
import logging
import urllib.parse
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Load .env from project root
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AFG_SQL_Client")

class DatabaseClient:
    def __init__(self):
        # Configuration from environment
        self.server = os.getenv("DB_SERVER")
        self.database = os.getenv("DB_NAME")
        self.username = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASSWORD")
        
        if not all([self.server, self.database, self.username, self.password]):
            logger.error("Database configuration missing in environment variables.")
            raise EnvironmentError("DB_SERVER, DB_NAME, DB_USER, and DB_PASSWORD must be set in .env")

        self.conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={self.server};DATABASE={self.database};UID={self.username};PWD={self.password}'
        self.conn = None
        self.engine = None

    def get_connection(self):
        try:
            if not self.conn or self.conn.closed:
                logger.info(f"Connecting to SQL Server (Raw): {self.server}/{self.database}")
                self.conn = pyodbc.connect(self.conn_str)
            return self.conn
        except Exception as e:
            logger.error(f"Error connecting to SQL Server (Raw): {e}")
            raise

    @property
    def cur(self):
        if not self.conn or self.conn.closed:
            self.get_connection()
        return self.conn.cursor()

    def commit(self):
        if self.conn:
            self.conn.commit()

    def get_engine(self):
        try:
            if not self.engine:
                logger.info(f"Creating SQLAlchemy Engine: {self.server}/{self.database}")
                quoted_conn_str = urllib.parse.quote_plus(self.conn_str)
                self.engine = create_engine(f"mssql+pyodbc:///?odbc_connect={quoted_conn_str}")
            return self.engine
        except Exception as e:
            logger.error(f"Error creating SQLAlchemy Engine: {e}")
            raise

    def execute_query(self, query, params=None):
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            logger.info(f"Executing Query: {query} | Params: {params}")
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
            
            if cur.description:
                columns = [column[0] for column in cur.description]
                results = []
                for row in cur.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
            else:
                conn.commit()
                return {"rowcount": cur.rowcount}
        finally:
            cur.close()

    def _parse_json_if_needed(self, val):
        if isinstance(val, str):
            stripped = val.strip()
            if (stripped.startswith('{') and stripped.endswith('}')) or \
               (stripped.startswith('[') and stripped.endswith(']')):
                try:
                    return json.loads(val)
                except:
                    return val
        return val

    def list_available_rules(self, sheet_name=None):
        """Returns a list of all distinct rules available in the consolidated view."""
        query = """
            SELECT DISTINCT * 
            FROM vr.vw_consolidated_validation_config
        """
        params = None
        if sheet_name:
            query += " WHERE sheet_name LIKE ?"
            params = (f"%{sheet_name}%",)
            
        query += " ORDER BY rule_execution_order, rule_code, task_execution_order"
        
        return self.execute_query(query, params)

    def fetch_rule_config(self, rule_code):
        """Fetches the configuration for a specific rule."""
        query = """
            SELECT rule_code, task_id, rule_name, rule_group, sheet_name, table_name, header_name, 
                   task_name, task_description, task_params, rule_execution_order, task_execution_order, 
                   fn_id, fn_name, fn_code, fn_parameters
            FROM vr.vw_consolidated_validation_config 
            WHERE rule_code = ?
            ORDER BY task_execution_order
        """
        rows = self.execute_query(query, (rule_code,))
        
        if not rows:
            logger.warning(f"No configuration found in view for Rule Code: {rule_code}")
            return None
            
        tasks = []
        for row in rows:
            tasks.append({
                "rule_code": row.get("rule_code"),
                "task_id": row.get("task_id"),
                "rule_name": row.get("rule_name"),
                "sheet_name": row.get("sheet_name"),
                "table_name": row.get("table_name"),
                "header_name": row.get("header_name"),
                "task_name": row.get("task_name"),
                "task_description": row.get("task_description"),
                "task_params": self._parse_json_if_needed(row.get("task_params")),
                "fn_name": row.get("fn_name"),
                "fn_code": row.get("fn_code"),
                "fn_parameters": self._parse_json_if_needed(row.get("fn_parameters"))
            })
        
        return tasks

    def _clean_name(self, name):
        import re
        if not name: return "unnamed"
        name = name.lower()
        name = name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_").replace("-", "_")
        name = re.sub(r'[^a-z0-9_]', '', name)
        name = re.sub(r'_+', '_', name).strip("_")
        parts = name.split("_")
        return "_".join(parts[:8])

    def create_table(self, table_name, columns, schema_name="dbo"):
        if not columns:
            logger.warning(f"Skipping table (empty schema): {table_name}")
            return False

        table_name = self._clean_name(table_name)
        full_table_name = f"[{schema_name}].[{table_name}]"
        cols_sql = []
        for col in columns:
            col_clean = self._clean_name(col)
            if col_clean.strip():
                cols_sql.append(f'[{col_clean}] NVARCHAR(MAX)')

        if not cols_sql:
            logger.warning(f"Skipping table (invalid schema): {table_name}")
            return False

        conn = self.get_connection()
        cur = conn.cursor()
        try:
            cur.execute(f"IF OBJECT_ID('{schema_name}.{table_name}', 'U') IS NOT NULL DROP TABLE {full_table_name}")
            sql = f"CREATE TABLE {full_table_name} (id INT IDENTITY(1,1) PRIMARY KEY, {','.join(cols_sql)})"
            cur.execute(sql)
            conn.commit()
            logger.info(f"Table created: {full_table_name}")
            return True
        finally:
            cur.close()

    def truncate_table(self, table_name, schema_name="dbo"):
        table_name = self._clean_name(table_name)
        full_table_name = f"[{schema_name}].[{table_name}]"
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            cur.execute(f"TRUNCATE TABLE {full_table_name}")
            conn.commit()
            logger.info(f"Table truncated: {full_table_name}")
        finally:
            cur.close()

    def insert_rows(self, table_name, columns, rows, schema_name="dbo"):
        if not columns or not rows:
            return

        table_name = self._clean_name(table_name)
        full_table_name = f"[{schema_name}].[{table_name}]"
        cols_clean = [f'[{self._clean_name(c)}]' for c in columns]
        col_sql = ",".join(cols_clean)
        placeholders = ",".join(["?"] * len(cols_clean))

        sql = f"INSERT INTO {full_table_name} ({col_sql}) VALUES ({placeholders})"

        conn = self.get_connection()
        cur = conn.cursor()
        inserted = 0
        try:
            for r in rows:
                if len(r) == len(cols_clean):
                    cur.execute(sql, r)
                    inserted += 1
            conn.commit()
            logger.info(f"Inserted {inserted} rows into {full_table_name}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Error inserting rows into {full_table_name}: {e}")
            raise
        finally:
            cur.close()
