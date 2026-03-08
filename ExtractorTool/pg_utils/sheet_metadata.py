import sys
import os
# Add project root to path for sql_client
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from sql_client import DatabaseClient


# --------------------------------------------------
# Create Metadata Table
# --------------------------------------------------

def create_metadata_table(pg, schema_name="dbo"):

    # SQL Server check for table existence
    check_sql = f"IF OBJECT_ID('{schema_name}.sheet_metadata', 'U') IS NULL BEGIN "
    create_sql = f"""
    CREATE TABLE [{schema_name}].[sheet_metadata]
    (
        id INT IDENTITY(1,1) PRIMARY KEY,
        sheet_name NVARCHAR(MAX),
        header NVARCHAR(MAX),
        subcategory NVARCHAR(MAX)
    )
    END
    """
    pg.cur.execute(check_sql + create_sql)
    pg.conn.commit()

    print("sheet_metadata table ready")


# --------------------------------------------------
# Insert Header → Subcategory Mapping
# --------------------------------------------------

def insert_sheet_metadata(pg, sheet_name, header_subcat_dict, schema_name="dbo"):
    create_metadata_table(pg, schema_name)

    sql = f"""
    INSERT INTO [{schema_name}].[sheet_metadata]
    (sheet_name, header, subcategory)
    VALUES (?,?,?)
    """

    rows = []
    for header, subcats in header_subcat_dict.items():
        # Ensure subcats is a collection we can iterate over
        if isinstance(subcats, str):
            subcats = [subcats]
        elif isinstance(subcats, dict):
            subcats = list(subcats.keys())

        for sub in subcats:
            # Handle dictionary for nested subcategories
            sub_display = sub if isinstance(sub, str) else list(sub.keys())[0]
            
            # Sanitize inputs to avoid TDS 0x62 error (ensure they are strings or empty strings, not None)
            row = (
                str(sheet_name) if sheet_name is not None else "",
                str(header) if header is not None else "",
                str(sub_display) if sub_display is not None else ""
            )
            rows.append(row)

    if len(rows) == 0:
        print("No metadata to insert")
        return

    try:
        pg.cur.executemany(sql, rows)
        pg.conn.commit()
        print("Inserted metadata rows:", len(rows))
    except Exception as e:
        print(f"Error inserting metadata: {e}")
        # Try individual inserts as fallback
        pg.conn.rollback()
        for r in rows:
            try:
                pg.cur.execute(sql, r)
            except: pass
        pg.conn.commit()