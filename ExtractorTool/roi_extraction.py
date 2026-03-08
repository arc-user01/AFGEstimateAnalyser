import os
import json
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load .env from project root
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

HTML_FILE = os.path.join(os.getenv("HTML_OUT_DIR", ""), "Waterfall.html")
EXTRACTION_JSON_PATH = os.getenv("EXTRACTION_CONFIG_PATH")
OUTPUT_FOLDER = os.path.join(os.getenv("PROJECT_ROOT", ""), "data", "roi_result")


# ------------------------------------------------
# LOAD CONFIG
# ------------------------------------------------

with open(EXTRACTION_JSON_PATH, "r", encoding="utf-8") as f:
    EXTRACTION_JSON = json.load(f)


# ------------------------------------------------
# PARSE HTML TABLE INTO ROW STRUCTURE
# ------------------------------------------------

def load_html_rows(path):

    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "lxml")

    table = soup.find("table")

    rows = []

    for tr in table.find_all("tr"):

        cells = []

        for td in tr.find_all(["td","th"]):

            text = td.get_text(strip=True)

            has_formula = any("fmla" in str(k).lower() for k in td.attrs)

            cells.append({
                "text": text,
                "formula": has_formula
            })

        rows.append(cells)

    return rows


# ------------------------------------------------
# HELPERS
# ------------------------------------------------

def row_text(row):

    return " ".join(c["text"].lower() for c in row if c["text"])


def row_values(row):

    return [c["text"] for c in row if c["text"]]


def first_col_empty(row):

    return len(row)==0 or row[0]["text"]==""


def non_empty_cells(row):

    return sum(1 for c in row if c["text"] or c["formula"])


# ------------------------------------------------
# FIND HEADER ROW
# ------------------------------------------------

def find_header(rows, text):

    text = text.lower()

    for i,row in enumerate(rows):

        if text in row_text(row):
            return i

    return None


# ------------------------------------------------
# EXTRACT METADATA BLOCK
# ------------------------------------------------

def extract_metadata(rows, start, stop_headers):

    metadata = []

    for i in range(start, len(rows)):

        row = rows[i]
        text = row_text(row)

        if any(h.lower() in text for h in stop_headers):
            return metadata, i

        if first_col_empty(row) and len(row_values(row)) > 0:
            return metadata, i

        vals = row_values(row)

        if vals:
            metadata.append(vals)

    return metadata, len(rows)


# ------------------------------------------------
# FIND TABLE SCHEMA
# ------------------------------------------------

def find_schema(rows,start):

    for i in range(start,len(rows)):

        row=rows[i]

        if first_col_empty(row):

            headers=row_values(row)

            if headers:
                return i,["element_name"]+headers

    return None,None


# ------------------------------------------------
# FIND TABLE END
# ------------------------------------------------

def find_table_end(rows,start,width):

    for i in range(start,len(rows)):

        window=rows[i:i+3]

        ranks=[]

        for j,r in enumerate(window):

            filled=non_empty_cells(r)

            rank=1 if filled<=1 else 2

            ranks.append((i+j,rank))

        if any(r==1 for _,r in ranks):

            return max(pos for pos,r in ranks if r==1)

    return len(rows)


# ------------------------------------------------
# EXTRACT TABLE
# ------------------------------------------------

def extract_table(rows,schema_row,schema):

    start=schema_row+1
    end=find_table_end(rows,start,len(schema))

    table=[]

    for r in rows[start:end]:

        if len(r)==0:
            continue

        element=r[0]["text"]

        if element=="":
            continue

        rec={"element_name":element}

        for j in range(1,min(len(r),len(schema))):

            val=r[j]["text"]

            if val:
                rec[schema[j]]=val

        table.append(rec)

    return table,end


# ------------------------------------------------
# PROCESS SECTION
# ------------------------------------------------

def process_section(rows,header,subheaders):

    stop_headers=[header]+subheaders

    start=find_header(rows,header)

    if start is None:
        return {}

    current=start+1
    block=1

    result={}

    while current<len(rows):

        metadata,end_meta=extract_metadata(rows,current,stop_headers)

        if metadata:
            result[f"metadata_{block}"]=metadata

        schema_row,schema=find_schema(rows,end_meta)

        if schema_row is None:
            break

        table,end_table=extract_table(rows,schema_row,schema)

        result[f"table_{block}"]={
            "schema":schema,
            "rows":table
        }

        current=end_table+1
        block+=1

    return result


# ------------------------------------------------
# SAVE OUTPUT
# ------------------------------------------------

def save_md(output):

    os.makedirs(OUTPUT_FOLDER,exist_ok=True)

    for sheet,data in output.items():

        folder=os.path.join(OUTPUT_FOLDER,sheet)

        os.makedirs(folder,exist_ok=True)

        for key,val in data.items():

            path=os.path.join(folder,f"{key}.md")

            with open(path,"w",encoding="utf-8") as f:

                if key.startswith("metadata"):

                    f.write("<table>\n")

                    for row in val:
                        f.write("<tr>")
                        for c in row:
                            f.write(f"<td>{c}</td>")
                        f.write("</tr>\n")

                    f.write("</table>")

                else:

                    schema=val["schema"]
                    rows=val["rows"]

                    f.write("<table>\n<tr>")

                    for c in schema:
                        f.write(f"<th>{c}</th>")

                    f.write("</tr>\n")

                    for r in rows:

                        f.write("<tr>")

                        for c in schema:
                            f.write(f"<td>{r.get(c,'')}</td>")

                        f.write("</tr>\n")

                    f.write("</table>")


# ------------------------------------------------
# MAIN
# ------------------------------------------------

rows=load_html_rows(HTML_FILE)

final={}

for sheet in EXTRACTION_JSON["sheets"]:

    name=sheet["name"]
    headers=sheet["headers"]

    for h,subs in headers.items():

        final[name]=process_section(rows,h,subs)

save_md(final)

print("Extraction completed.")