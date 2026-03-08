from pgsql_client import PgClient,insert_md_file
import os


folder=r"C:\AI-projects\AFG\result_table"


pg=PgClient(
    host="localhost",
    database="testdb",
    user="admin",
    password="admin123"
)


for f in os.listdir(folder):

    if f.endswith(".md"):

        path=os.path.join(folder,f)

        table_name=f.replace(".md","").lower()

        insert_md_file(pg,path,table_name)



pg.close()