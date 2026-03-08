import json
import os
from bs4 import BeautifulSoup
import re

def detect_headers_and_subcategories(html_input: str):
    # ---------------------------------------
    # Load Config
    # ---------------------------------------
    config_path = r'C:\AI-projects\afg_final\extraction_config.json'
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Determine sheet name from filename (dynamic lookup from config)
    sheet_name = None
    base_name = os.path.basename(html_input).lower()
    
    for s in config["sheets"]:
        if s["name"].lower() in base_name:
            sheet_name = s["name"]
            break
    
    if not sheet_name:
        # Fallback to first sheet or keep as is if html_input is raw HTML
        sheet_name = config["sheets"][0]["name"]

    sheet_config = next((s for s in config["sheets"] if s["name"].lower() == sheet_name.lower()), None)
    if not sheet_config:
        raise Exception(f"Configuration for sheet '{sheet_name}' not found in {config_path}")

    config_headers = sheet_config["headers"]

    # ---------------------------------------
    # Load HTML
    # ---------------------------------------
    if html_input.lower().endswith(".html"):
        with open(html_input, "r", encoding="utf-8") as f:
            html = f.read()
    else:
        html = html_input

    soup = BeautifulSoup(html, "html.parser")

    # ---------------------------------------
    # Helpers
    # ---------------------------------------
    def get_row(coord):
        if not coord:
            return None
        m = re.search(r'\d+', coord)
        if m:
            return int(m.group())
        return None

    def normalize(txt):
        if not txt: return ""
        # Remove special characters
        txt = re.sub(r'[^a-zA-Z0-9\s]', '', txt)
        # Remove extra whitespaces
        txt = " ".join(txt.split())
        return txt.strip().upper()

    # ---------------------------------------
    # Identify Header Rows
    # ---------------------------------------
    header_locations = []
    
    # We look for headers defined in config
    for h_name in config_headers.keys():
        # Standalone search for the header
        target = normalize(h_name)
        cell = None
        for td in soup.find_all("td"):
            if normalize(td.get_text()).startswith(target):
                cell = td
                break
        
        if cell:
            coord = cell.get("excelcoordinate") or cell.get("excelCoordinate")
            row = get_row(coord)
            if row:
                header_locations.append({
                    "text": h_name,
                    "row": row
                })
        else:
            print(f"Warning: Header '{h_name}' not found in HTML.")

    # Sort headers by row
    header_locations = sorted(header_locations, key=lambda x: x["row"])

    # ---------------------------------------
    # Extract Subcategories within boundaries
    # ---------------------------------------
    result = {}

    for i in range(len(header_locations)):
        current_h = header_locations[i]
        h_name = current_h["text"]
        start_row = current_h["row"]
        
        if i < len(header_locations) - 1:
            stop_row = header_locations[i+1]["row"]
        else:
            stop_row = 999999

        expected_subs_raw = config_headers.get(h_name, [])
        found_subs = []

        for item in expected_subs_raw:
            if isinstance(item, str):
                # Standard flat subcategory
                sub_name = item
                target_sub = normalize(sub_name)
                for td in soup.find_all("td"):
                    coord = td.get("excelcoordinate") or td.get("excelCoordinate")
                    row = get_row(coord)
                    if not row:
                        continue
                    is_same_as_header = (target_sub == normalize(h_name))
                    valid_row = (start_row <= row < stop_row) if is_same_as_header else (start_row < row < stop_row)
                    
                    if valid_row:
                        cell_text = td.get_text(separator=" ", strip=True)
                        if normalize(cell_text) == target_sub or normalize(cell_text).startswith(target_sub):
                            found_subs.append(sub_name)
                            break
            elif isinstance(item, dict):
                # Nested subcategory (Deep Extraction)
                # Keep the main key as a subheader to find its range
                main_sub_name = list(item.keys())[0]
                sub_subs = item[main_sub_name]
                found_subs.append({main_sub_name: sub_subs})

        result[h_name] = found_subs

        result[h_name] = found_subs

    return result
