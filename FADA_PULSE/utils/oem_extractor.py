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

from utils.extractor import normalize_category, parse_claude_json, VALID_CATEGORIES

OEM_CATEGORIES = VALID_CATEGORIES - {"Total"}  # OEM tables don't have a "Total" category

OEM_EXTRACTION_PROMPT = """You are extracting OEM (manufacturer) market-share data from \
a FADA document. The document may contain MULTIPLE category OEM tables — e.g. \
"Two-Wheeler OEM", "Three-Wheeler OEM", "Passenger Vehicle OEM", "Commercial Vehicle \
OEM", "Tractor OEM" — one after another. You must find and extract EVERY such table \
present in the document, not just the first one.

Each table shows OEM-wise unit counts for the CURRENT and PREVIOUS fiscal year side by \
side, plus market-share % columns for each year. Some OEM rows have indented SUB-ENTITY \
rows nested under them — e.g. a parent OEM row might be a combined total for two related \
entities listed just below it (like a company's core brand plus a subsidiary or acquired \
brand). Note: a sub-entity can share the exact same name as its own parent row — treat \
these as distinct records regardless.

Return ONLY a JSON object, no other text, no markdown fences, in this exact shape:

{
  "tables": [
    {
      "category": "TRAC",
      "current_fiscal_year": "FY26",
      "previous_fiscal_year": "FY25",
      "rows": [
        {"oem_name": "MAHINDRA & MAHINDRA LIMITED (TRACTOR)", "parent_oem": "", "current_year_units": 249973, "previous_year_units": 208056}
      ]
    },
    {
      "category": "3W",
      "current_fiscal_year": "FY26",
      "previous_fiscal_year": "FY25",
      "rows": [
        {"oem_name": "MAHINDRA & MAHINDRA LIMITED", "parent_oem": "", "current_year_units": 110036, "previous_year_units": 77768},
        {"oem_name": "MAHINDRA LAST MILE MOBILITY LTD", "parent_oem": "MAHINDRA & MAHINDRA LIMITED", "current_year_units": 109135, "previous_year_units": 76900},
        {"oem_name": "MAHINDRA & MAHINDRA LIMITED", "parent_oem": "MAHINDRA & MAHINDRA LIMITED", "current_year_units": 901, "previous_year_units": 868}
      ]
    }
  ]
}

Rules:
- Output ONLY the JSON object. Do not show your reasoning, do not narrate steps, do
  not write any text before or after the JSON. Your entire response must start with
  "{" and end with "}".
- Scan the ENTIRE document for every distinct "<Category> OEM" table. Do not stop
  after finding the first one — a single document commonly has all of 2W, 3W, PV, CV,
  and TRAC (and sometimes CE) OEM tables one after another.
- Read every number DIRECTLY from the table text provided — never estimate, infer, or
  back-calculate a value from a market-share percentage.
- Each table entry's "category" must be EXACTLY one of: "2W", "3W", "PV", "CV", "TRAC",
  "CE" — inferred from that specific table's title (e.g. "Tractor OEM" -> "TRAC",
  "Three-Wheeler OEM" -> "3W", "Commercial Vehicle OEM" -> "CV").
- "current_fiscal_year" / "previous_fiscal_year" in "FYxx" format, matching the two
  data columns in that table. If a table truly has no previous-year column, set both
  previous_fiscal_year and previous_year_units to null for that table.
- "oem_name" is exactly as printed in the table (keep the original casing/punctuation).
- "parent_oem" is "" for a row that is NOT indented under another OEM row. For an
  indented sub-entity row, set "parent_oem" to the exact oem_name of the row it's
  nested under.
- current_year_units / previous_year_units must be plain integers with commas/spaces
  stripped (e.g. 2,49,973 -> 249973).
- Do not include each table's "Total" row (the category grand total) — that's already
  captured elsewhere.
- Do not include market-share % columns.
- Include an "Others" / "Others including EV" row if a table has one — it's a
  legitimate rollup row, just extract its units like any other row.
"""


def parse_oem_with_claude(pdf_text: str) -> dict:
    api_key = st.secrets["ANTHROPIC_API_KEY"]
    client = Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000,
        system=OEM_EXTRACTION_PROMPT,
        messages=[{"role": "user", "content": pdf_text[:40000]}],
    )

    raw = response.content[0].text
    data = parse_claude_json(raw)

    if "tables" not in data or not isinstance(data["tables"], list):
        raise ValueError(f"Unexpected response shape: {data}")

    for table in data["tables"]:
        table["category"] = normalize_category(table.get("category", ""))
        if table["category"] not in OEM_CATEGORIES:
            raise ValueError(f"Unrecognized category in response: {table.get('category')}")
        for row in table.get("rows", []):
            row["parent_oem"] = (row.get("parent_oem") or "").strip()
            row["oem_name"] = (row.get("oem_name") or "").strip()
            if not row["oem_name"]:
                raise ValueError(f"Row missing oem_name: {row}")

    return data


def build_oem_rows(parsed: dict, source_filename: str) -> list[dict]:
    """Flatten every table's current+previous FY columns into one row per
    (fiscal_year, category, oem_name, parent_oem), ready for the Supabase upsert."""
    all_rows = []
    for table in parsed["tables"]:
        category = table["category"]
        current_fy = table["current_fiscal_year"]
        previous_fy = table.get("previous_fiscal_year")

        for r in table.get("rows", []):
            all_rows.append(
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
                all_rows.append(
                    {
                        "fiscal_year": previous_fy,
                        "category": category,
                        "oem_name": r["oem_name"],
                        "parent_oem": r["parent_oem"],
                        "current_year_units": r["previous_year_units"],
                        "source_file": source_filename,
                    }
                )
    return all_rows
