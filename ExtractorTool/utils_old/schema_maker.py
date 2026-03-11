from bs4 import BeautifulSoup
import re


class DynamicSchemaMakerV2:


    # --------------------------------------------------
    # INIT
    # --------------------------------------------------

    def __init__(self,
                 html_input,
                 sheet_name=None,
                 header=None,
                 subheader=None,
                 force_schema_row=None):

        self.force_schema_row = force_schema_row


        if isinstance(html_input, list):
            html = "<table>" + "".join(html_input) + "</table>"
        elif isinstance(html_input, str) and html_input.lower().endswith(".html"):
            with open(html_input, "r", encoding="utf-8") as f:
                html = f.read()
        else:
            html = html_input

        self.original_html = html
        self.soup = BeautifulSoup(html, "html.parser")


    # --------------------------------------------------
    # COLUMN EXPANSION
    # --------------------------------------------------

    def _expand_columns(self,c1,c2):

        def col_to_num(col):

            n=0
            for ch in col:
                n=n*26+(ord(ch)-64)

            return n


        def num_to_col(n):

            col=""
            while n>0:
                n,r=divmod(n-1,26)
                col=chr(65+r)+col

            return col


        n1=col_to_num(c1)
        n2=col_to_num(c2)

        return [num_to_col(i) for i in range(n1,n2+1)]


    # --------------------------------------------------
    # DETECT SCHEMA ROWS
    # --------------------------------------------------

    def detect_schema_rows(self):

        if self.force_schema_row is not None:
            if isinstance(self.force_schema_row, (list, tuple)):
                return {
                    "start_row": min(self.force_schema_row),
                    "end_row": max(self.force_schema_row)
                }
            return {
                "start_row": self.force_schema_row,
                "end_row": self.force_schema_row
            }

        merged_candidates=[]

        for td in self.soup.find_all("td"):

            coord=td.get("excelcoordinate") or td.get("excelCoordinate")

            if not coord:
                continue

            m=re.search(r"([A-Z]+)(\d+):([A-Z]+)(\d+)",coord)

            if not m:
                continue

            c1,r1,c2,r2=m.groups()

            r1=int(r1)
            r2=int(r2)

            if r2>r1:
                merged_candidates.append((r1,r2))


        if merged_candidates:

            merged_candidates=sorted(merged_candidates)

            start,end=merged_candidates[0]

            return {
                "start_row":start,
                "end_row":end
            }


        # print("\nMerged schema not found -> trying single-row detection")


        row_counts={}

        for td in self.soup.find_all("td"):

            coord=td.get("excelcoordinate") or td.get("excelCoordinate")

            if not coord:
                continue

            m=re.search(r"\d+",coord)

            if not m:
                continue

            row=int(m.group())

            txt=td.get_text(" ",strip=True)

            if txt:

                row_counts.setdefault(row,0)
                row_counts[row]+=1


        # print("\nRow Counts Detected:")
        # for r,c in sorted(row_counts.items()):
        #     print("Row",r,"->",c,"cells")


        if not row_counts:
            print("Schema NOT detected")
            return None


        best_row=max(row_counts,key=row_counts.get)


        rows_sorted=sorted(row_counts.keys())

        # print("\nChecking Next Row Single Cell Rule")

        for r in rows_sorted:

            if r+1 in row_counts:

                c1=row_counts[r]
                c2=row_counts[r+1]

                # print("Row",r,"->",c1," | Row",r+1,"->",c2)

                if c1>=4 and c2==1:
                    best_row=r
                    # print("Next row single cell -> Selecting Row:",best_row)
                    break


        sorted_rows=sorted(row_counts.items(),
                           key=lambda x:x[1],
                           reverse=True)

        if len(sorted_rows)>=2:

            r1,c1=sorted_rows[0]
            r2,c2=sorted_rows[1]

            diff=abs(c1-c2)

            # print("\nTop Two Rows:")
            # print("Row",r1,"->",c1)
            # print("Row",r2,"->",c2)
            # print("Difference:",diff)

            if diff==1:

                best_row=min(r1,r2)

                print("Difference=1 -> Selecting MIN Row:",best_row)


        if row_counts[best_row] < 4:
            # print("Schema NOT detected")
            return None


        # print("\nSchema Rows:",best_row,"to",best_row)


        return {
            "start_row":best_row,
            "end_row":best_row
        }


    # --------------------------------------------------
    # FIX EMPTY FIRST COLUMN
    # --------------------------------------------------

    def _fix_empty_first_schema_column(self, tracker):

        if not tracker:
            return


        schema_row=tracker["start_row"]
        # print("\nChecking first schema column")

        first_col=None


        for td in self.soup.find_all("td"):

            coord=td.get("excelcoordinate") or td.get("excelCoordinate")

            if not coord:
                continue

            m=re.search(r"([A-Z]+)(\d+)",coord)

            if not m:
                continue

            col,row=m.groups()

            row=int(row)

            if row==schema_row:

                if not first_col or col<first_col:
                    first_col=col


        # print("First column:",first_col)


        for td in self.soup.find_all("td"):

            coord=td.get("excelcoordinate") or td.get("excelCoordinate")

            if not coord:
                continue

            m=re.search(r"([A-Z]+)(\d+)",coord)

            if not m:
                continue

            col,row=m.groups()

            row=int(row)


            if row==schema_row and col==first_col:

                txt=td.get_text(strip=True)
                if txt=="":
                    td.string="element_name"

                return


    # --------------------------------------------------
    # EXTRACT CELLS
    # --------------------------------------------------

    def extract_cells(self):

        cell_map={}

        for td in self.soup.find_all("td"):

            coord=td.get("excelcoordinate") or td.get("excelCoordinate")
            if not coord:
                continue

            txt=td.get_text(" ",strip=True)
            # We no longer skip if not txt to ensure coordinates are captured for empty cells


            m_range=re.search(r"([A-Z]+)(\d+):([A-Z]+)(\d+)",coord)
            if m_range:
                c1,r1,c2,r2=m_range.groups()
                r1=int(r1)
                r2=int(r2)
                for r in range(r1,r2+1):
                    for col in self._expand_columns(c1,c2):
                        cell_map.setdefault(r,{})[col]=txt
                continue


            m=re.search(r"([A-Z]+)(\d+)",coord)

            if not m:
                continue

            col,row=m.groups()

            row=int(row)

            cell_map.setdefault(row,{})[col]=txt


        return cell_map


    # --------------------------------------------------
    # CLEAN TEXT
    # --------------------------------------------------

    def clean(self,text):

        text=text.lower()

        text=re.sub(r'[^a-z0-9 ]',' ',text)

        text=re.sub(r'\s+',' ',text)

        text=text.strip()

        text=text.replace(" ","_")

        return text


    # --------------------------------------------------
    # BUILD SCHEMA
    # --------------------------------------------------

    def build_schema(self):
        # print("\n---------------- SCHEMA BUILD ----------------")


        tracker=self.detect_schema_rows()

        if not tracker:
            return [],None


        self._fix_empty_first_schema_column(tracker)


        start=tracker["start_row"]
        end=tracker["end_row"]


        # print("\nSchema Range:",start,"to",end)


        cell_map=self.extract_cells()


        columns=set()

        for r in range(start,end+1):

            if r in cell_map:
                columns.update(cell_map[r].keys())


        columns=sorted(columns)


        # print("\nColumns detected:",columns)


        schema=[]

        duplicate_counter={}


        for col in columns:

            hierarchy=[]

            for r in range(start,end+1):

                val=cell_map.get(r,{}).get(col)

                if val:
                    # Avoid duplication if the same value is repeated vertically (rowspan)
                    if not hierarchy or hierarchy[-1] != val:
                        hierarchy.append(val)


            if not hierarchy:
                continue


            cleaned=[self.clean(x) for x in hierarchy]

            col_name="_".join(cleaned)


            if col_name not in duplicate_counter:

                duplicate_counter[col_name]=1
                schema.append(col_name)

            else:

                duplicate_counter[col_name]+=1

                schema.append(
                    f"{col_name}_{duplicate_counter[col_name]}"
                )


        print(f"Generated Schema: {schema}")


        return schema,tracker


    # --------------------------------------------------
    # REMOVE SCHEMA ROWS
    # --------------------------------------------------

    def remove_schema_rows(self,tracker):

        if not tracker:
            return []


        start=tracker["start_row"]
        end=tracker["end_row"]


        filtered_cells=[]

        for td in self.soup.find_all("td"):

            coord=td.get("excelcoordinate") or td.get("excelCoordinate")

            if not coord:
                continue

            m=re.search(r"\d+",coord)

            if not m:
                continue

            row=int(m.group())


            # Only keep rows that are AFTER the schema rows
            if row > end:
                filtered_cells.append(str(td))


        return filtered_cells



# --------------------------------------------------
# PUBLIC FUNCTIONS
# --------------------------------------------------

def generate_schema_from_html(html_input,
                              sheet_name=None,
                              header=None,
                              subheader=None,
                              force_schema_row=None):

    maker=DynamicSchemaMakerV2(
            html_input,
            sheet_name,
            header,
            subheader,
            force_schema_row=force_schema_row
        )

    return maker.build_schema()



def remove_schema_rows_with_tracker(html_input, tracker, sheet_name=None, header=None, subheader=None, force_schema_row=None):

    maker=DynamicSchemaMakerV2(
        html_input,
        sheet_name,
        header,
        subheader,
        force_schema_row=force_schema_row
    )

    return maker.remove_schema_rows(tracker)