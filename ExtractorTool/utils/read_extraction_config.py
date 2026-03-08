import os
import json
import requests


def load_extraction_config():

    config_path = os.getenv("EXTRACTION_CONFIG")

    if not config_path:
        raise ValueError("EXTRACTION_CONFIG environment variable not set")

    # Case 1 — URL
    if config_path.startswith("http://") or config_path.startswith("https://"):
        response = requests.get(config_path)

        if response.status_code != 200:
            raise Exception(f"Failed to download config: {response.status_code}")

        return response.json()

    # Case 2 — Local file
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)