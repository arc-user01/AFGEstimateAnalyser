import pyodbc
import os
import urllib.parse
from sqlalchemy import create_engine
from bs4 import BeautifulSoup
import re
from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------
# SQL Server Client (formerly PostgreSQL)
# --------------------------------------------------

class PgClient:

    def __init__(self, server=None, database=None, user=None, password=None):
        server = server or os.getenv("DB_SERVER")
        database = database or os.getenv("DB_NAME")
        user = user or os.getenv("DB_USER")
        password = password or os.getenv("DB_PASSWORD")

        # Connection string for SQL Server
        self.conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={user};PWD={password}'
        
        try:
            # Raw PyODBC connection
            self.conn = pyodbc.connect(self.conn_str)
            self.cur = self.conn.cursor()
            
            # SQLAlchemy Engine for Pandas compatibility
            quoted_conn_str = urllib.parse.quote_plus(self.conn_str)
            self.engine = create_engine(f"mssql+pyodbc:///?odbc_connect={quoted_conn_str}")
            
            print("SQL Server Connected (Raw & SQLAlchemy)")
        except Exception as e:
            print(f"Error connecting to SQL Server: {e}")
            raise e

    def close(self):
        if hasattr(self, 'cur'): self.cur.close()
        if hasattr(self, 'conn'): self.conn.close()
        print("Connection Closed")


# --------------------------------------------------
# CLEAN NAME FUNCTION (NEW)
# --------------------------------------------------

    def _clean_name(self,name):

        name=name.lower()

        name=name.replace(" ","_") \
                 .replace("(","") \
                 .replace(")","") \
                 .replace("/","_") \
                 .replace("-","_")


        # keep only letters numbers underscore
        name=re.sub(r'[^a-z0-9_]', '', name)


        # remove multiple underscores
        name=re.sub(r'_+','_',name)


        # remove leading trailing _
        name=name.strip("_")


        # keep max 5 words
        parts=name.split("_")

        name="_".join(parts[:8])


        return name


# --------------------------------------------------
# Create Table Automatically (Overwrite Schema)
# --------------------------------------------------

    def create_table(self, table_name, columns, schema_name="dbo"):
        if not columns:
            print("Skipping table (empty schema):", table_name)
            return False

        table_name = self._clean_name(table_name)
        full_table_name = f"[{schema_name}].[{table_name}]"
        cols_sql = []

        for col in columns:
            col_clean = self._clean_name(col)
            if col_clean.strip() == "":
                continue
            # SQL Server uses NVARCHAR(MAX) for large text/JSON
            cols_sql.append(f'[{col_clean}] NVARCHAR(MAX)')

        if len(cols_sql) == 0:
            print("Skipping table (invalid schema):", table_name)
            return False

        # Drop table (SQL Server syntax)
        self.cur.execute(f"IF OBJECT_ID('{schema_name}.{table_name}', 'U') IS NOT NULL DROP TABLE {full_table_name}")
        print("Old table dropped:", full_table_name)

        # Create table (SQL Server syntax: IDENTITY instead of SERIAL)
        sql = f"""
        CREATE TABLE {full_table_name}
        (
            id INT IDENTITY(1,1) PRIMARY KEY,
            {",".join(cols_sql)}
        )
        """
        self.cur.execute(sql)
        self.conn.commit()
        print("Table created:", full_table_name)
        return True


# --------------------------------------------------
# TRUNCATE TABLE
# --------------------------------------------------

    def truncate_table(self, table_name, schema_name="dbo"):
        table_name = self._clean_name(table_name)
        full_table_name = f"[{schema_name}].[{table_name}]"
        # SQL Server TRUNCATE TABLE resets IDENTITY by default
        sql = f"TRUNCATE TABLE {full_table_name}"
        self.cur.execute(sql)
        self.conn.commit()
        print("Table truncated:", full_table_name)


# --------------------------------------------------
# Insert Rows
# --------------------------------------------------

    def insert_rows(self, table_name, columns, rows, schema_name="dbo"):
        if not columns or not rows:
            print("Insert skipped:", table_name)
            return

        table_name = self._clean_name(table_name)
        full_table_name = f"[{schema_name}].[{table_name}]"
        cols_clean = [f'[{self._clean_name(c)}]' for c in columns]
        col_sql = ",".join(cols_clean)
        # SQL Server uses ? as placeholder for pyodbc
        placeholders = ",".join(["?"] * len(cols_clean))

        sql = f"""
        INSERT INTO {full_table_name}
        ({col_sql})
        VALUES ({placeholders})
        """

        inserted = 0
        try:
            for r in rows:
                if len(r) == len(cols_clean):
                    self.cur.execute(sql, r)
                    inserted += 1
            self.conn.commit()
            print("Inserted:", inserted)
        except Exception as e:
            self.conn.rollback()
            raise e



# --------------------------------------------------
# Parse MD Table
# --------------------------------------------------

def parse_md_table(md_file):

    with open(md_file,"r",encoding="utf-8") as f:
        html=f.read()

    soup=BeautifulSoup(html,"html.parser")

    table=soup.find("table")

    if not table:
        print("No table found:",md_file)
        return [],[]


    schema_raw=[]

    thead=table.find("thead")

    if thead:

        header_row=thead.find("tr")

        if header_row:

            schema_raw=[
                c.get_text(strip=True)
                for c in header_row.find_all(["th","td"])
            ]


    if not schema_raw:

        first_row=table.find("tr")

        if first_row:

            schema_raw=[
                c.get_text(strip=True)
                for c in first_row.find_all(["th","td"])
            ]


    schema=[]
    keep_index=[]


    for i,c in enumerate(schema_raw):

        if c.strip():

            schema.append(c)

            keep_index.append(i)


    if not schema:

        print("Schema detection failed:",md_file)

        return [],[]


    data=[]


    tbody=table.find("tbody")

    if tbody:

        data_rows=tbody.find_all("tr")

    else:

        data_rows=table.find_all("tr")[1:]


    for r in data_rows:

        cols=r.find_all(["td","th"])

        row=[]


        for i in keep_index:

            if i<len(cols):

                row.append(
                    cols[i].get_text(strip=True)
                )

            else:

                row.append("")


        if any(row):

            data.append(row)


    return schema,data


# --------------------------------------------------
# Insert MD File
# --------------------------------------------------

def insert_md_file(pg, md_file, table_name, schema_name="dbo"):

    schema,data=parse_md_table(md_file)


    if not schema:
        print("Skipping insert:",table_name)
        return


    if not data:
        print("Skipping insert:",table_name)
        return


    created=pg.create_table(table_name,schema, schema_name)

    if not created:
        return


    pg.truncate_table(table_name, schema_name)


    pg.insert_rows(table_name,schema,data, schema_name)


    print(f"Loaded: [{schema_name}].[{table_name}]")