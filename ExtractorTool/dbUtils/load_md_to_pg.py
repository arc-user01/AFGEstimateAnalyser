import sys
import os
# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ExtractorTool.dbUtils.sql_client import DatabaseClient, insert_md_file

db = DatabaseClient()

# Example folder path - update as needed
folder = r"data\temp" 

if os.path.exists(folder):
    for f in os.listdir(folder):
        if f.endswith(".md"):
            path = os.path.join(folder, f)
            table_name = f.replace(".md", "").lower()
            insert_md_file(db, path, table_name)

db.close()