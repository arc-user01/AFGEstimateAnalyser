from bs4 import BeautifulSoup
import re

def col_to_num(c):
    n=0
    for char in c:
        n=n*26 + (ord(char.upper()) - 64)
    return n

def num_to_col(n):
    col=""
    while n>0:
        n,r=divmod(n-1,26)
        col=chr(65+r)+col
    return col

class HTMLTableBuilder:

    def __init__(self, schema, data_cells):
        self.schema = schema
        self.data_cells = data_cells
        html = "<table>" + "".join(data_cells) + "</table>"
        self.soup = BeautifulSoup(html, "html.parser")

    def _extract_rows(self):
        table = {}
        all_cols_n = set()
        
        # 1. Gather all data and all columns
        for td in self.soup.find_all("td"):
            coord = td.get("excelcoordinate") or td.get("excelCoordinate")
            if not coord:
                continue
            
            m = re.search(r"([A-Z]+)(\d+)", coord)
            if not m:
                continue
            
            col_str, row_str = m.groups()
            row = int(row_str)
            col_n = col_to_num(col_str)
            txt = td.get_text(" ", strip=True) or ""
            
            all_cols_n.add(col_n)
            table.setdefault(row, {})[col_str] = f"{col_str}{row}_{txt}"

        if not table:
            return []

        # Find the bounding box of the table rows
        rows_present = sorted(table.keys())
        min_row = min(rows_present)
        max_row = max(rows_present)
        
        # Determine the target column range using schema length
        # Start from the first column encountered in any row
        min_col_n = min(all_cols_n)
        schema_len = len(self.schema)
        target_cols = [num_to_col(min_col_n + i) for i in range(schema_len)]

        # 2. Build ordered rows for the absolute range (min_row to max_row)
        ordered_rows = []
        for r in range(min_row, max_row + 1):
            row_data = []
            for c_str in target_cols:
                # Use coordinate-aware default (prefix_{txt})
                val = table.get(r, {}).get(c_str, f"{c_str}{r}_")
                row_data.append(val)
            ordered_rows.append(row_data)

        return ordered_rows

    def build_markdown(self):
        rows = self._extract_rows()
        header = self.schema
        md = []
        md.append("| " + " | ".join(header) + " |")
        md.append("|" + "|".join(["---"]*len(header)) + "|")

        for r in rows:
            # Already aligned by _extract_rows
            md.append("| " + " | ".join(r) + " |")

        return "\n".join(md)

    def build_html(self):
        rows = self._extract_rows()
        html = []
        html.append("<table border='1'>")
        html.append("<thead>")
        html.append("<tr>")
        for h in self.schema:
            html.append(f"<th>{h}</th>")
        html.append("</tr>")
        html.append("</thead>")
        html.append("<tbody>")

        for r in rows:
            html.append("<tr>")
            for c in r:
                html.append(f"<td>{c}</td>")
            html.append("</tr>")

        html.append("</tbody>")
        html.append("</table>")
        return "\n".join(html)

def build_markdown_table(schema, data_cells):
    builder = HTMLTableBuilder(schema, data_cells)
    return builder.build_markdown()

def build_html_table(schema, data_cells):
    builder = HTMLTableBuilder(schema, data_cells)
    return builder.build_html()