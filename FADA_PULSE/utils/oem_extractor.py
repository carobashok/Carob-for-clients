"""
Extracts OEM (manufacturer) market-share data from a FADA "<Category> OEM"
table (e.g. "Tractor OEM", "Three-Wheeler OEM", "Passenger Vehicle OEM").

These tables show OEM-wise units for the current and previous fiscal year,
plus market-share % columns (which we don't store — can be recalculated from
units / category total on the fly). Some OEMs have indented sub-entity rows
nested under them (e.g. Mahindra & Mahindra Limited's tractor business vs.
its Swaraj Division, or a subsidiary like Mahindra Last Mile Mobility Ltd
under the parent M&M row for three-wheelers).
"""

import streamlit as st
from anthropic import Anthropic

from utils.extractor import parse_claude_json, normalize_oem_name, VALID_CATEGORIES

OEM_CATEGORIES = VALID_CATEGORIES - {"Total"}  # OEM tables don't have a "Total" category

CATEGORY_LABELS = {
    "2W": "Two-Wheeler",
    "3W": "Three-Wheeler",
    "PV": "Passenger Vehicle",
    "CV": "Commercial Vehicle",
    "TRAC": "Tractor",
    "CE": "Construction Equipment",
}

OEM_EXTRACTION_PROMPT_TEMPLATE = """You are extracting OEM (manufacturer) market-share data \
from a FADA document. This document may contain OEM tables for MULTIPLE categories \
(Two-Wheeler, Three-Wheeler, Passenger Vehicle, Commercial Vehicle, Tractor, etc.) — \
find and extract ONLY the table for: {category_label} ({category_code}). It will be \
titled something like "{category_label} OEM". IGNORE every other category's OEM table \
that may also appear in the document.

The table shows OEM-wise unit counts for the CURRENT and PREVIOUS fiscal year side by \
side, plus market-share % columns for each year. Some OEM rows have indented SUB-ENTITY \
rows nested under them — e.g. a parent OEM row might be a combined total for two related \
entities listed just below it (like a company's core brand plus a subsidiary or acquired \
brand). Note: a sub-entity can share the exact same name as its own parent row — treat \
these as distinct records regardless.

Return ONLY a JSON object, no other text, no markdown fences, in this exact shape:

{{
  "current_fiscal_year": "FY26",
  "previous_fiscal_year": "FY25",
  "rows": [
    {{"oem_name": "MAHINDRA & MAHINDRA LIMITED", "parent_oem": "", "current_year_units": 110036, "previous_year_units": 77768}},
    {{"oem_name": "MAHINDRA LAST MILE MOBILITY LTD", "parent_oem": "MAHINDRA & MAHINDRA LIMITED", "current_year_units": 109135, "previous_year_units": 76900}},
    {{"oem_name": "MAHINDRA & MAHINDRA LIMITED", "parent_oem": "MAHINDRA & MAHINDRA LIMITED", "current_year_units": 901, "previous_year_units": 868}}
  ]
}}

Rules:
- Output ONLY the JSON object. Do not show your reasoning, do not narrate steps, do
  not write any text before or after the JSON. Your entire response must start with
  "{{" and end with "}}".
- Extract ONLY the {category_label} ({category_code}) OEM table. If that table isn't
  present in the document at all, return {{"current_fiscal_year": null, "previous_fiscal_year": null, "rows": []}}.
- Read every number DIRECTLY from the table text provided — never estimate, infer, or
  back-calculate a value from a market-share percentage.
- "current_fiscal_year" / "previous_fiscal_year" in "FYxx" format, matching the two
  data columns in the table. If there's truly no previous-year column, set both
  previous_fiscal_year and previous_year_units to null.
- "oem_name" is exactly as printed in the table (keep the original casing/punctuation).
- "parent_oem" is "" for a row that is NOT indented under another OEM row. For an
  indented sub-entity row, set "parent_oem" to the exact oem_name of the row it's
  nested under.
- current_year_units / previous_year_units must be plain integers with commas/spaces
  stripped (e.g. 2,49,973 -> 249973).
- Do not include the "Total" row (the category grand total) — that's already captured
  elsewhere.
- Do not include market-share % columns.
- Include an "Others" / "Others including EV" row if the table has one — it's a
  legitimate rollup row, just extract its units like any other row.
"""


def parse_oem_with_claude(pdf_text: str, category: str) -> dict:
    """Extract just the OEM table for the given category, ignoring any other
    category tables present in the same document."""
    if category not in OEM_CATEGORIES:
        raise ValueError(f"Unknown category: {category}")

    api_key = st.secrets["ANTHROPIC_API_KEY"]
    client = Anthropic(api_key=api_key)

    prompt = OEM_EXTRACTION_PROMPT_TEMPLATE.format(
        category_label=CATEGORY_LABELS[category], category_code=category
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=prompt,
        messages=[{"role": "user", "content": pdf_text[:150000]}],  # generous cap; Sonnet's context window is far larger than any FADA release
    )

    raw = response.content[0].text
    data = parse_claude_json(raw)

    if "rows" not in data:
        raise ValueError(f"Unexpected response shape: {data}")
    if not data["rows"]:
        raise ValueError(
            f"No {CATEGORY_LABELS[category]} ({category}) OEM table found in this document."
        )

    for row in data["rows"]:
        row["parent_oem"] = normalize_oem_name(row.get("parent_oem") or "")
        row["oem_name"] = normalize_oem_name(row.get("oem_name") or "")
        if not row["oem_name"]:
            raise ValueError(f"Row missing oem_name: {row}")

    data["category"] = category
    return data


def build_oem_rows(parsed: dict, source_filename: str) -> list[dict]:
    """Flatten current+previous FY columns into one row per (fiscal_year, category,
    oem_name, parent_oem), ready for the Supabase upsert."""
    category = parsed["category"]
    current_fy = parsed["current_fiscal_year"]
    previous_fy = parsed.get("previous_fiscal_year")

    rows = []
    for r in parsed["rows"]:
        rows.append(
            {
                "fiscal_year": current_fy,
                "category": category,
                "oem_name": r["oem_name"],
                "parent_oem": r["parent_oem"],
                "current_year_units": r["current_year_units"],
                "source_file": source_filename,
            }
        )
        if previous_fy and r.get("previous_year_units") is not None:
            rows.append(
                {
                    "fiscal_year": previous_fy,
                    "category": category,
                    "oem_name": r["oem_name"],
                    "parent_oem": r["parent_oem"],
                    "current_year_units": r["previous_year_units"],
                    "source_file": source_filename,
                }
            )
    return rows
