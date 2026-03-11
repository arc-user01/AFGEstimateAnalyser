import re
import os

from utils.schema_maker import generate_schema_from_html, remove_schema_rows_with_tracker
from utils.tbl_builder import build_html_table
from ExtractorTool.dbUtils.sql_client import insert_md_file


# -----------------------------
# Helpers
# -----------------------------

def get_row(coord):

    if not coord:
        return None

    m = re.search(r'\d+', coord)

    return int(m.group()) if m else None

def get_row_range(coord):
    if not coord:
        return []
    m_range = re.search(r'([A-Z]+)(\d+):([A-Z]+)(\d+)', coord)
    if m_range:
        r1 = int(m_range.group(2))
        r2 = int(m_range.group(4))
        return list(range(r1, r2+1))
    m_single = re.search(r'\d+', coord)
    if m_single:
        return [int(m_single.group())]
    return []



def limit_words(txt, n):
    words = [w for w in txt.split("_") if w]
    if len(words) > n:
        return "_".join(words[:n])
    return txt

def clean_filename(txt):
    txt = re.sub(r'[^a-zA-Z0-9 _]', '', txt)
    txt = txt.replace(" ", "_").lower()
    return txt



# -----------------------------
# Normalization Helper (Fallback Only)
# -----------------------------

def normalize(txt):

    if not txt:
        return ""

    txt = txt.replace("\xa0", " ")
    txt = txt.split("(")[0]
    txt = " ".join(txt.split())

    return txt.lower().strip()



# -----------------------------
# Header Row Finder
# -----------------------------

def find_header_row(soup, header_text):
    if not header_text:
        return None

    def normalize_internal(txt):
        if not txt: return ""
        import re
        txt = re.sub(r'[^a-zA-Z0-9\s]', '', txt)
        return " ".join(txt.split()).upper()

    target = normalize_internal(header_text)
    td = None
    for item in soup.find_all("td"):
        if normalize_internal(item.get_text()).startswith(target):
            td = item
            break

    if not td:
        return None

    coord = td.get("excelcoordinate") or td.get("excelCoordinate")
    return get_row(coord)



# -----------------------------
# Main Processor
# -----------------------------

import json

def get_boundary_classes(soup):
    """Finds all CSS classes in the soup that indicate a header/subheader boundary."""
    boundary_classes = set()
    style_tag = soup.find("style")
    if not style_tag:
        return boundary_classes
    
    styles = style_tag.get_text()
    
    # Find all class blocks
    import re
    blocks = re.findall(r'\.(x\d+)\s*\{([^}]+)\}', styles)
    for cls_name, content in blocks:
        # Check for background
        bg_match = re.search(r'background:([^;]+)', content)
        has_non_white_bg = False
        if bg_match:
            bg_val = bg_match.group(1).upper().strip()
            # If it's not white/auto/none, it's usually a header/subheader
            if bg_val not in ["#FFFFFF", "AUTO", "NONE", "WHITE", "TRANSPARENT"]:
                has_non_white_bg = True
        
        if has_non_white_bg:
            boundary_classes.add(cls_name)
    
    return boundary_classes

def get_row(coord):
    if not coord: return None
    m = re.search(r'\d+', coord)
    return int(m.group()) if m else None

def get_all_subcat_names(items):
    """Recursively flattens all subcategory names from the config."""
    names = []
    for item in items:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            name = list(item.keys())[0]
            names.append(name)
            data = item[name]
            if isinstance(data, list):
                names.extend(get_all_subcat_names(data))
    return names

def get_boundary_rows(soup, yellow_classes):
    """Finds all rows that should act as a hard boundary (mostly yellow cells)."""
    boundaries = set()
    for td in soup.find_all("td"):
        cls = td.get("class", [])
        is_yellow = any(c in yellow_classes for c in cls)
        style = td.get("style", "").lower()
        if "background:#ffff00" in style or "background:yellow" in style:
            is_yellow = True
        
        if is_yellow:
            coord = td.get("excelcoordinate") or td.get("excelCoordinate")
            rows = get_row_range(coord)
            for r in rows:
                boundaries.add(r)
    return sorted(list(boundaries))

def process_header_tables(
        header_name,
        header_subcat_dict,
        soup,
        result_folder,
        pg,
        sheet_name=None,
        schema_name="dbo"
):
    if not sheet_name or str(sheet_name).lower() == "none":
        sheet_name = os.path.basename(result_folder) or "Sheet"
    
    print(f"\n[PROCESS] Header: {header_name} | Sheet: {sheet_name}")

    config_path = r'C:\AI-projects\afg_final\extraction_config.json'
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    sheet_config = next((s for s in config["sheets"] if header_name in s["headers"]), config["sheets"][0])
    all_headers = list(sheet_config["headers"].keys())
    
    # Header Boundaries
    header_start = find_header_row(soup, header_name)
    if header_start is None:
        print(f"    ! Header '{header_name}' row not found. Skipping.")
        return

    next_header = all_headers[all_headers.index(header_name) + 1] if all_headers.index(header_name) < len(all_headers)-1 else None
    header_stop = find_header_row(soup, next_header) or 99999

    # Context for instructions (schema caching)
    context = {"last_schema": None, "last_tracker": None}
    
    # Boundary detection (Yellow cells + Next Header)
    yellow_classes = get_boundary_classes(soup)
    boundary_rows = get_boundary_rows(soup, yellow_classes)
    if header_stop and header_stop < 99999:
        boundary_rows.append(header_stop)
    boundary_rows = sorted(list(set(boundary_rows)))
    print(f"    Boundary rows detected: {boundary_rows[:10]}... (Total: {len(boundary_rows)})")

    # Flattencategories for fallback filtering if needed
    subcats_config = sheet_config["headers"][header_name]
    
    # Pre-process all TDs to cache row numbers
    all_td_data = []
    for td in soup.find_all("td"):
        coord = td.get("excelcoordinate") or td.get("excelCoordinate")
        r = get_row(coord)
        if r:
            all_td_data.append((r, td))

    def execute_recursive_extraction(items, scoped_td_data, p_start, p_stop, boundary_rows, parent_naming=None):
        if isinstance(items, dict):
            iterable = list(items.items())
        elif isinstance(items, list):
            iterable = items
        else:
            return

        for i, entry in enumerate(iterable):
            instruction = None
            data = None
            
            if isinstance(iterable, list) and isinstance(items, dict):
                name, data = entry
            elif isinstance(items, list):
                # items is a list
                if isinstance(entry, str):
                    name = entry
                    data = None
                elif isinstance(entry, dict):
                    name = list(entry.keys())[0]
                    data = entry[name]
                else: continue
            else:
                # Handle direct dict iteration if items is a dict (fallback)
                if isinstance(entry, tuple):
                    name, data = entry
                else: 
                    name = entry
                    data = None
            
            if isinstance(data, dict) and "instruction" in data:
                instruction = data["instruction"]

            print(f"  > Processing: {name} (Instr: {instruction}) (Range: [{p_start}, {p_stop}])")

            # 1. Locate Cell
            start_row = None
            name_norm = name.strip()
            # Normalize internal spaces for matching: simplify all whitespace to single space
            name_clean = re.sub(r'\s+', ' ', name_norm)
            
            # fuzzy pattern: allow any characters between words
            # We want to be robust to quotes and &nbsp;
            # name_pattern: 'Incremental.*Software.*5.*year'
            name_pattern = re.sub(r'[^a-zA-Z0-9]+', '.*', name_norm)
            
            # Filter current list for the name
            for r, td in scoped_td_data:
                # We search within the scoped data
                td_text = re.sub(r'\s+', ' ', td.get_text(" ", strip=True))
                # Even cleaner match: only alphanumeric for sequence
                td_clean = re.sub(r'[^a-zA-Z0-9]+', ' ', td_text).strip()
                if re.search(name_pattern, td_text, re.IGNORECASE):
                    start_row = r
                    break
            
            if start_row is None:
                # Priority 2: Even more fuzzy (sequences)
                for r, td in scoped_td_data:
                    td_text = td.get_text(" ", strip=True)
                    td_clean = re.sub(r'[^a-zA-Z0-9]', '', td_text)
                    name_compact = re.sub(r'[^a-zA-Z0-9]', '', name_norm)
                    if name_compact.lower() in td_clean.lower():
                        start_row = r
                        break
            
            if start_row is None:
                print(f"    ! Not found: {name} in range [{p_start}, {p_stop}]. Skipping.")
                continue

            # 2. Determine Stop Row
            next_item_name = None
            if i < len(iterable) - 1:
                next_entry = iterable[i+1]
                if isinstance(items, dict):
                    next_item_name = next_entry[0]
                else:
                    next_item_name = next_entry if isinstance(next_entry, str) else list(next_entry.keys())[0]
            
            stop_row = p_stop

            # For nested subcategories, we ONLY stop at the next configured sibling
            # or the parent's boundary. We do NOT use physical boundary_rows (yellow cells)
            # here because they are often just part of the internal table structure.

            if next_item_name:
                next_norm = next_item_name.strip()
                next_pattern = re.sub(r'[^a-zA-Z0-9]+', '.*', next_norm)
                
                # Search for the NEXT occurrence of the sibling name within parent bounds
                for r, td in scoped_td_data:
                    if start_row < r < stop_row:
                        td_text = re.sub(r'\s+', ' ', td.get_text(" ", strip=True))
                        if re.search(next_pattern, td_text, re.IGNORECASE):
                            stop_row = r
                            break

            # 3. Handle Data/Recursion
            if isinstance(data, list):
                # Nested subcategories container
                # Scoping the data for recursion
                # We filter the td_data to only include elements between start_row and stop_row
                current_naming = f"{parent_naming}_{name}" if parent_naming else name
                new_scoped_tds = [(r, td) for r, td in scoped_td_data if start_row <= r < stop_row]
                execute_recursive_extraction(data, new_scoped_tds, start_row, stop_row, boundary_rows, parent_naming=current_naming)
            else:
                # Leaf node: Extract
                # We pass the parent scoped data and let extract_and_save_scoped handle the mapping
                extract_and_save_filtered(scoped_td_data, start_row, stop_row, header_start, header_stop,
                                         sheet_name, header_name, name, result_folder, pg,
                                         nested_name=parent_naming,
                                         instruction=instruction, context=context, schema_name=schema_name)

    # Initial call with all header data
    header_scoped_tds = [(r, td) for r, td in all_td_data if header_start <= r < header_stop]
    execute_recursive_extraction(subcats_config, header_scoped_tds, header_start, header_stop, boundary_rows)

def extract_and_save_filtered(scoped_td_data, start_row, stop_row, header_start, header_stop, 
                              sheet_name, header_name, subcat_name, result_folder, pg, 
                              nested_name=None, instruction=None, context=None, schema_name="dbo"):
    """Helper to extract cells, detect schema, and save to MD/PG."""
    
    # Logic for instruction-based row management
    actual_data_start = start_row
    force_schema_row = None

    if instruction == "previous cell as table schema":
        # Check if we should include one or two rows as schema
        # Standard: row-1. Multi-row: row-2 and row-1.
        schema_rows = [start_row - 1]
        
        # Heuristic: If row-2 is within the subcat scope and not the name row
        # We assume if it's >= header_start (+ some buffer if needed)
        if (start_row - 2) >= header_start:
             schema_rows.insert(0, start_row - 2)
        
        force_schema_row = schema_rows
        actual_data_start = start_row + 1
        print(f"    Instruction: previous cell as schema. Schema Rows: {force_schema_row}, Data Starts: {actual_data_start}")
    elif instruction == "use the previous schema":
        actual_data_start = start_row + 1
        print(f"    Instruction: use previous schema. Data Starts: {actual_data_start}")

    # Gather rows for extraction
    rows_to_include = list(range(actual_data_start, stop_row))
    if force_schema_row is not None:
        if isinstance(force_schema_row, (list, tuple)):
            for r_s in sorted(force_schema_row, reverse=True):
                rows_to_include.insert(0, r_s)
        else:
            rows_to_include.insert(0, force_schema_row)

    filtered_cells = []
    for r, td in scoped_td_data:
        if r in rows_to_include:
            filtered_cells.append(str(td))

    if not filtered_cells:
        print(f"    No cells for {subcat_name}")
        return

    # Instruction Logic
    schema, tracker = None, None

    if instruction == "use the previous schema" and context and context.get("last_schema"):
        schema = context["last_schema"]
        tracker = context["last_tracker"]
        print(f"    Using cached schema: {schema[:2] if schema else []}...")
    else:
        schema, tracker = generate_schema_from_html(filtered_cells, sheet_name=sheet_name, 
                                                   header=header_name, subheader=subcat_name,
                                                   force_schema_row=force_schema_row)
        if context is not None:
            context["last_schema"] = schema
            context["last_tracker"] = tracker

    if not schema:
        print(f"    No schema for {subcat_name}")
        return

    data_cells = remove_schema_rows_with_tracker(filtered_cells, tracker, sheet_name=sheet_name, 
                                                header=header_name, subheader=subcat_name,
                                                force_schema_row=force_schema_row)
    html_table = build_html_table(schema, data_cells)

    # Naming
    base_raw = f"{sheet_name}_{header_name}_{subcat_name}"
    base_clean = clean_filename(base_raw)
    base_final = limit_words(base_clean, 5)

    if nested_name:
        ext_clean = clean_filename(nested_name)
        ext_final = limit_words(ext_clean, 3)
        table_name = f"{base_final}_{ext_final}".lower()
    else:
        table_name = base_final.lower()

    file_name = f"{table_name}.md"
    save_path = os.path.join(result_folder, file_name)
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(html_table)

    insert_md_file(pg, save_path, table_name, schema_name)
    # print(f"Inserted: {table_name}")
