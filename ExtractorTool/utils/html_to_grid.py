import os
import json
import re
from bs4 import BeautifulSoup

def parse_coordinate(coord_str):
    """
    Parses 'A120' or 'A120:B121' into (start_row, start_col, end_row, end_col)
    Returns row indices (1-based) and column names.
    """
    def split_coord(c):
        match = re.match(r"([A-Z]+)([0-9]+)", c)
        if match:
            return int(match.group(2)), match.group(1)
        return None, None

    if ':' in coord_str:
        start, end = coord_str.split(':')
        sr, sc = split_coord(start)
        er, ec = split_coord(end)
        return sr, sc, er, ec
    else:
        r, c = split_coord(coord_str)
        return r, c, r, c

def get_col_range(start_col, end_col):
    """Returns list of column names between start and end (inclusive)."""
    def col_to_int(c):
        res = 0
        for char in c:
            res = res * 26 + (ord(char) - ord('A') + 1)
        return res
        
    def int_to_col(n):
        res = ""
        while n > 0:
            n, r = divmod(n - 1, 26)
            res = chr(ord('A') + r) + res
        return res

    s_idx = col_to_int(start_col)
    e_idx = col_to_int(end_col)
    return [int_to_col(i) for i in range(s_idx, e_idx + 1)]

def html_to_grid(html_path, output_md_path):
    """
    Parses Aspose HTML into a DOM grid.
    Extracts styles from CSS classes and handles merged cells via 'excelCoordinate'.
    """
    print(f"Parsing HTML: {html_path}")
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
    
    # 1. Parse Styles
    styles = {}
    style_tags = soup.find_all('style')
    for tag in style_tags:
        content = tag.string
        if not content: continue
        # Simple regex to extract .className { props }
        # Note: This is a basic parser. Aspose CSS is usually clean.
        matches = re.findall(r"\.([a-zA-Z0-9_-]+)\s*\{([^}]+)\}", content)
        for class_name, props in matches:
            prop_dict = {}
            for prop in props.split(';'):
                if ':' in prop:
                    k, v = prop.split(':', 1)
                    prop_dict[k.strip().lower()] = v.strip().lower()
            styles[class_name] = prop_dict

    # 2. Build Grid
    grid = {}
    cells = soup.find_all('td')
    
    for td in cells:
        coord_attr = td.get('excelCoordinate')
        if not coord_attr:
            continue
            
        sr, sc, er, ec = parse_coordinate(coord_attr)
        if sr is None: continue
        
        text = td.get_text(strip=True)
        classes = td.get('class', [])
        
        # Merge styles from classes and inline
        cell_style = {}
        for cls in classes:
            if cls in styles:
                cell_style.update(styles[cls])
        
        inline_style = td.get('style', '')
        if inline_style:
            for item in inline_style.split(';'):
                if ':' in item:
                    k, v = item.split(':', 1)
                    cell_style[k.strip().lower()] = v.strip().lower()
                    
        # Determine bold/size
        # Aspose might use font-weight or font-family/size classes
        is_bold = 'bold' in cell_style.get('font-weight', '') or td.find(['b', 'strong'])
        # Also check for '700' or higher
        fw = cell_style.get('font-weight', '')
        if fw.isdigit() and int(fw) >= 700:
            is_bold = True
            
        cell_data = {
            "coordinate": coord_attr,
            "text": text,
            "style": cell_style,
            "is_bold": bool(is_bold),
            "font_size": cell_style.get('font-size', '11pt')
        }
        
        # Expand Merged Cells
        col_list = get_col_range(sc, ec)
        for r in range(sr, er + 1):
            if r not in grid:
                grid[r] = {}
            for c in col_list:
                grid[r][c] = cell_data

    # 3. Save to MD and JSON
    print(f"Generating Output: {output_md_path}")
    sorted_rows = sorted(grid.keys())
    
    # Save MD
    with open(output_md_path, 'w', encoding='utf-8') as f:
        for r in sorted_rows:
            f.write(f"Row {r}\n\n")
            row_data = grid[r]
            sorted_cols = sorted(row_data.keys(), key=lambda x: (len(x), x))
            for c in sorted_cols:
                cell = row_data[c]
                f.write(f"[{c}{r}] {cell['text']}\n")
            f.write("\n")
            
    # Save JSON for detector
    json_path = output_md_path.replace('.md', '.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({"grid": grid}, f, indent=4)
        
    return grid