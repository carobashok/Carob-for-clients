"""
Extracts fiscal-year vehicle registration data from a FADA annual/FY press
release. Unlike the monthly releases, these typically show the CURRENT FY
and the PREVIOUS FY side by side with a YoY% column, and sometimes include
sub-category breakouts (e.g. LCV/MCV/HCV under CV, E-RICKSHAW(P) under 3W).

One upload therefore yields TWO fiscal years' worth of rows — useful for
backfilling years you don't have a dedicated release for.
"""

import json
import re

import streamlit as st
from anthropic import Anthropic

from utils.extractor import extract_pdf_text, normalize_category, VALID_CATEGORIES  # noqa: F401 (re-exported)

ANNUAL_EXTRACTION_PROMPT = """You are extracting vehicle registration data from a FADA \
(Federation of Automobile Dealers Associations) ANNUAL / FISCAL YEAR press release or \
summary table.

These releases typically show TWO fiscal years side by side (the current FY and the \
previous FY) with a YoY% column, e.g. columns "FY23" and "FY22". Some rows are top-level \
categories (2W, 3W, PV, CV, TRAC, CE, Total) and some are indented SUB-CATEGORY rows \
nested under a parent category (e.g. "LCV", "MCV", "HCV", "OTHERS" under CV; \
"E-RICKSHAW(P)", "THREE WHEELER (GOODS)" under 3W).

Return ONLY a JSON object, no other text, no markdown fences, in this exact shape:

{
  "current_fiscal_year": "FY23",
  "previous_fiscal_year": "FY22",
  "rows": [
    {"category": "2W", "subcategory": "", "current_year_units": 15995968, "previous_year_units": 13494214},
    {"category": "3W", "subcategory": "", "current_year_units": 767071, "previous_year_units": 417108},
    {"category": "3W", "subcategory": "E-RICKSHAW(P)", "current_year_units": 350247, "previous_year_units": 160065},
    {"category": "CV", "subcategory": "", "current_year_units": 939741, "previous_year_units": 707186},
    {"category": "CV", "subcategory": "LCV", "current_year_units": 554585, "previous_year_units": 438802}
  ]
}

Rules:
- "current_fiscal_year" / "previous_fiscal_year" must be in "FYxx" format (e.g. "FY23"),
  matching whatever the two data columns in the table represent.
- The "category" field must be EXACTLY one of: "2W", "3W", "PV", "CV", "TRAC", "CE",
  "Total" — even if the source table labels a row differently (e.g. "TRACTOR" -> "TRAC",
  "GRAND TOTAL" -> "Total").
- "subcategory" is "" (empty string) for a row that IS the parent category's own total.
  For an indented sub-row nested under a category, set "subcategory" to that row's label
  exactly as printed (e.g. "LCV", "E-RICKSHAW(P)", "THREE WHEELER (GOODS)").
- Only include sub-category rows that ACTUALLY appear in the table — do not invent ones
  that aren't present. Many fiscal years won't have any sub-rows for some or all
  categories, and that's fine; just omit them.
- current_year_units / previous_year_units must be plain integers with commas/spaces
  stripped (Indian releases use lakh-style grouping like 15,95,968 -> 1595968).
- If the table is missing a previous-year column entirely, set previous_year_units to null
  and previous_fiscal_year to null.
- Do not include YoY% or any other column.
- Only extract from the ALL-INDIA summary category table — ignore state-wise or OEM-wise
  breakdown tables if present.
"""


def parse_annual_with_claude(pdf_text: str) -> dict:
    api_key = st.secrets["ANTHROPIC_API_KEY"]
    client = Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=ANNUAL_EXTRACTION_PROMPT,
        messages=[{"role": "user", "content": pdf_text[:15000]}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude did not return valid JSON:\n{raw}") from e

    if "current_fiscal_year" not in data or "rows" not in data:
        raise ValueError(f"Unexpected response shape: {data}")

    for row in data["rows"]:
        row["category"] = normalize_category(row.get("category", ""))
        if row["category"] not in VALID_CATEGORIES:
            raise ValueError(f"Unrecognized category in response: {row}")
        row["subcategory"] = (row.get("subcategory") or "").strip()

    return data


def build_annual_rows(parsed: dict, source_filename: str) -> list[dict]:
    """Flatten current+previous FY columns into one row per (fiscal_year, category,
    subcategory), ready for the Supabase upsert."""
    current_fy = parsed["current_fiscal_year"]
    previous_fy = parsed.get("previous_fiscal_year")

    rows = []
    for r in parsed["rows"]:
        rows.append(
            {
                "fiscal_year": current_fy,
                "category": r["category"],
                "subcategory": r["subcategory"],
                "current_year_units": r["current_year_units"],
                "source_file": source_filename,
            }
        )
        if previous_fy and r.get("previous_year_units") is not None:
            rows.append(
                {
                    "fiscal_year": previous_fy,
                    "category": r["category"],
                    "subcategory": r["subcategory"],
                    "current_year_units": r["previous_year_units"],
                    "source_file": source_filename,
                }
            )
    return rows
