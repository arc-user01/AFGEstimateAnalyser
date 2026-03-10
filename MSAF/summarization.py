"""
Summarization tool: generalized prompt with placeholders and output formatting.

Placeholders: {{rule_code}}, {{rule_description}}, {{output}}
Output is processed for display using Markdown + HTML tags: table, ul, li, h1, h2.
"""
import json
import re
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Prompt template (placeholders: rule_code, rule_description, output)
# ---------------------------------------------------------------------------

SUMMARIZATION_PROMPT = """## Rule summary

<h1>Rule: {{rule_code}}</h1>

<h2>Description</h2>
{{rule_description}}

<h2>Output</h2>
{{output}}
"""


def fill_prompt(rule_code: str, rule_description: str, output: str) -> str:
    """Fill the summarization prompt with the given rule_code, rule_description, and output."""
    return (
        SUMMARIZATION_PROMPT.replace("{{rule_code}}", str(rule_code or ""))
        .replace("{{rule_description}}", str(rule_description or ""))
        .replace("{{output}}", str(output or ""))
    )


# ---------------------------------------------------------------------------
# Process output: structure content using Markdown + HTML (table, ul, li, h1, h2)
# ---------------------------------------------------------------------------

def process_output_for_display(raw_output: str) -> str:
    """
    Process raw output (e.g. from run_rule_validation) into Markdown + HTML
    using tags: table, ul, li, h1, h2 for clear presentation.
    """
    if not raw_output or not raw_output.strip():
        return "<p><em>No output.</em></p>"

    text = raw_output.strip()

    # Try to parse as JSON (e.g. rule result with results list)
    try:
        data = json.loads(text)
        return _structured_to_html(data)
    except (json.JSONDecodeError, TypeError):
        pass

    # Plain text: use h2 for lines that look like headers, ul/li for list-like lines
    return _plain_text_to_html(text)


def _structured_to_html(data: Any) -> str:
    """Convert JSON-like structure to HTML (table, ul, li, h2)."""
    if isinstance(data, dict):
        return _dict_to_html(data)
    if isinstance(data, list):
        return _list_to_html(data)
    return _escape(str(data))


def _dict_to_html(d: dict) -> str:
    parts = []
    for key, value in d.items():
        key_clean = str(key).replace("_", " ").title()
        if isinstance(value, (list, dict)):
            parts.append(f"<h2>{key_clean}</h2>\n{_structured_to_html(value)}")
        else:
            parts.append(f"<p><strong>{key_clean}:</strong> {_escape(str(value))}</p>")
    return "\n".join(parts)


def _list_to_html(items: list) -> str:
    if not items:
        return "<p><em>Empty list.</em></p>"
    # If list of dicts with similar keys -> table
    if items and isinstance(items[0], dict):
        return _list_of_dicts_to_table(items)
    # Simple list -> ul/li
    return "<ul>\n" + "\n".join(f"<li>{_escape(str(x))}</li>" for x in items) + "\n</ul>"


def _list_of_dicts_to_table(rows: List[Dict]) -> str:
    """Render list of dicts as HTML table."""
    if not rows:
        return "<p><em>No rows.</em></p>"
    headers = list(rows[0].keys())
    thead = "".join(f"<th>{_escape(str(h))}</th>" for h in headers)
    trs = []
    for row in rows:
        cells = []
        for h in headers:
            val = row.get(h, "")
            if isinstance(val, (list, dict)):
                val = _structured_to_html(val)
            else:
                val = _escape(str(val))
            cells.append(f"<td>{val}</td>")
        trs.append("<tr>" + "".join(cells) + "</tr>")
    return (
        "<table>\n<thead><tr>"
        + thead
        + "</tr></thead>\n<tbody>\n"
        + "\n".join(trs)
        + "\n</tbody>\n</table>"
    )


def _plain_text_to_html(text: str) -> str:
    """Convert plain text to HTML using h2, ul, li where appropriate."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return f"<p>{_escape(text)}</p>"

    parts = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Line that looks like a header (ends with : or is short and title-case)
        if re.match(r"^[A-Z][a-zA-Z0-9\s_-]+:?\s*$", line) and len(line) < 80:
            parts.append(f"<h2>{_escape(line.rstrip(':'))}</h2>")
            i += 1
            continue
        # Line starting with - or * or digit. -> list
        if re.match(r"^[\s]*[-*•]\s", line) or re.match(r"^[\s]*\d+[.)]\s", line):
            li_lines = []
            while i < len(lines) and (
                re.match(r"^[\s]*[-*•]\s", lines[i])
                or re.match(r"^[\s]*\d+[.)]\s", lines[i])
            ):
                li_lines.append(re.sub(r"^[\s]*[-*•\d.)]+\s*", "", lines[i]))
                i += 1
            parts.append("<ul>\n" + "\n".join(f"<li>{_escape(ln)}</li>" for ln in li_lines) + "\n</ul>")
            continue
        # Paragraph
        parts.append(f"<p>{_escape(line)}</p>")
        i += 1

    return "\n".join(parts) if parts else f"<p>{_escape(text)}</p>"


def _escape(s: str) -> str:
    """Escape HTML entities."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def summarize_rule_output(rule_code: str, rule_description: str, raw_output: str) -> str:
    """
    Fill the summarization prompt and process the output for display
    (Markdown + HTML: table, ul, li, h1, h2). Returns the full summary string.
    """
    processed = process_output_for_display(raw_output)
    return fill_prompt(rule_code, rule_description, processed)
