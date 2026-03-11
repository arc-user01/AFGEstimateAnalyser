from urllib.parse import unquote
load_dotenv()

server = os.getenv("DB_SERVER")
user = os.getenv("DB_USER")
password = unquote(os.getenv("DB_PASSWORD", ""))
db_name = "sql-afg-pmo-dev"

conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={db_name};UID={user};PWD={password};TrustServerCertificate=yes;"
try:
    conn = pyodbc.connect(conn_str)
    cur = conn.cursor()
    cur.execute("SELECT TOP 1 * FROM consolidated_validation_rules")
    cols = [c[0] for c in cur.description]
    print(f"Columns: {cols}")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
