from bs4 import BeautifulSoup
import re

def opex_sub_category(html_input):

    if html_input.lower().endswith(".html"):
        with open(html_input,"r",encoding="utf-8") as f:
            html=f.read()
    else:
        html=html_input

    soup = BeautifulSoup(html,"html.parser")


    # -----------------------------
    # CSS Mapping
    # -----------------------------

    style_map={}

    css_block=soup.find("style").get_text()

    rules=re.findall(r'\.(\w+)\s*\{(.*?)\}',css_block,re.DOTALL)

    for cls,content in rules:

        props={}

        for p in content.split(";"):

            if ":" in p:
                k,v=p.split(":",1)
                props[k.strip().lower()]=v.strip().lower()

        style_map[cls]=props


    # -----------------------------
    # Detect Yellow Dynamically
    # -----------------------------

    yellow_colors=set()

    for cls in style_map:

        bg=style_map[cls].get("background") \
           or style_map[cls].get("background-color")

        if bg and "ffff00" in bg.lower():
            yellow_colors.add(bg.lower())


    # -----------------------------
    # Helpers
    # -----------------------------

    def get_row(coord):

        if not coord:
            return None

        m=re.search(r'\d+',coord)

        return int(m.group())


    def resolve_font(td):

        sizes=[]

        for cls in td.get("class",[]):

            size=style_map.get(cls,{}).get("font-size","")

            if size:
                sizes.append(float(size.replace("pt","")))

        return max(sizes) if sizes else None


    def resolve_bg(td):

        for cls in td.get("class",[]):

            bg=style_map.get(cls,{}).get("background")

            if not bg:
                bg=style_map.get(cls,{}).get("background-color")

            if bg:
                return bg.lower()

        return ""


    def find_header(text):

        td=soup.find(
            lambda t:
            t.name=="td"
            and t.get_text(strip=True).upper()==text
        )

        coord=td.get("excelcoordinate") or td.get("excelCoordinate")

        return get_row(coord)


    # -----------------------------
    # Range
    # -----------------------------

    opex_start=find_header("OPEX")
    stop_row=find_header("COST BENEFIT ANALYSIS")


    # -----------------------------
    # Rank Fonts
    # -----------------------------

    fonts=set()

    for td in soup.find_all("td"):

        coord=td.get("excelcoordinate") or td.get("excelCoordinate")
        row=get_row(coord)

        if not row:
            continue

        if row<=opex_start or row>=stop_row:
            continue

        if not coord.startswith("A"):
            continue

        f=resolve_font(td)

        if f:
            fonts.add(f)


    fonts=sorted(fonts,reverse=True)

    rank1_font=fonts[0]


    # -----------------------------
    # Extract Header → Subcategory
    # -----------------------------

    result={}
    headers=[]


    # First collect all Rank1 non-yellow cells
    for td in soup.find_all("td"):

        coord=td.get("excelcoordinate") or td.get("excelCoordinate")
        row=get_row(coord)

        if not row:
            continue

        if row<=opex_start or row>=stop_row:
            continue

        if not coord.startswith("A"):
            continue


        font=resolve_font(td)
        bg=resolve_bg(td)

        if font!=rank1_font:
            continue

        if bg in yellow_colors:
            continue


        text=td.get_text(" ",strip=True)

        if text:
            headers.append((row,text))


    headers=sorted(headers)


    # Convert to HEADER:[SUBHEADERS]

    subcategories = [h[1] for h in headers]

    return {
        "OPEX": subcategories
    }
