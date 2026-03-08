import os
import re
from bs4 import BeautifulSoup
from pg_utils.pgsql_client import insert_md_file

def load_soup_rows(soup):
    """Convert BeautifulSoup table to row structure."""
    table = soup.find("table")
    if not table:
        return []
        
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

def row_text(row):
    return " ".join(c["text"].lower() for c in row if c["text"])

def row_values(row):
    return [c["text"] for c in row if c["text"]]

def first_col_empty(row):
    return len(row) == 0 or row[0]["text"] == ""

def non_empty_cells(row):
    return sum(1 for c in row if c["text"] or c["formula"])

def find_header_in_rows(rows, text):
    text = text.lower()
    for i, row in enumerate(rows):
        if text in row_text(row):
            return i
    return None

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

def find_schema(rows, start):
    for i in range(start, len(rows)):
        row = rows[i]
        if first_col_empty(row):
            headers = row_values(row)
            if headers:
                return i, ["element_name"] + headers
    return None, None

def find_table_end(rows, start, width):
    for i in range(start, len(rows)):
        window = rows[i:i+3]
        ranks = []
        for j, r in enumerate(window):
            filled = non_empty_cells(r)
            rank = 1 if filled <= 1 else 2
            ranks.append((i+j, rank))
        if any(r == 1 for _, r in ranks):
            return max(pos for pos, r in ranks if r == 1)
    return len(rows)

def extract_table_data(rows, schema_row, schema):
    start = schema_row + 1
    end = find_table_end(rows, start, len(schema))
    table = []
    for r in rows[start:end]:
        if len(r) == 0:
            continue
        element = r[0]["text"]
        if element == "":
            continue
        rec = {"element_name": element}
        for j in range(1, min(len(r), len(schema))):
            val = r[j]["text"]
            if val:
                rec[schema[j]] = val
        table.append(rec)
    return table, end

def process_roi_section(rows, header_name, subheaders):
    stop_headers = [header_name] + subheaders
    start = find_header_in_rows(rows, header_name)
    if start is None:
        return {}
    current = start + 1
    block = 1
    result = {}
    while current < len(rows):
        metadata, end_meta = extract_metadata(rows, current, stop_headers)
        if metadata:
            result[f"metadata_{block}"] = metadata
        schema_row, schema = find_schema(rows, end_meta)
        if schema_row is None:
            break
        table, end_table = extract_table_data(rows, schema_row, schema)
        if table:
            result[f"table_{block}"] = {
                "schema": schema,
                "rows": table
            }
        current = end_table + 1
        block += 1
    return result

def save_roi_blocks(sheet_name, header_name, blocks, result_folder, pg, schema_name="dbo"):
    os.makedirs(result_folder, exist_ok=True)
    
    for key, val in blocks.items():
        table_name = f"{sheet_name}_{header_name}_{key}".lower().replace(" ", "_")
        file_name = f"{table_name}.md"
        path = os.path.join(result_folder, file_name)
        
        with open(path, "w", encoding="utf-8") as f:
            if key.startswith("metadata"):
                f.write("<table>\n")
                for row in val:
                    f.write("<tr>")
                    for c in row:
                        f.write(f"<td>{c}</td>")
                    f.write("</tr>\n")
                f.write("</table>")
            else:
                schema = val["schema"]
                rows = val["rows"]
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
        
        # Insert into database
        insert_md_file(pg, path, table_name, schema_name)
