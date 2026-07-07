"""
Extracts month/category/unit data from a FADA press-release PDF.

Pipeline:
  1. pdfplumber pulls raw text out of the uploaded PDF.
  2. That text is sent to Claude with a strict JSON-only instruction.
  3. The JSON response is parsed into a list of row dicts ready for Supabase.

FADA has changed its release format several times (see CarobInsights project
notes: pre-2021 has no Tractor category, 2021-2023 drops urban/rural splits,
Sep'24-Feb'25 adds urban/rural, Apr'25+ adds fuel-mix and a separate CE
category). Rather than hand-coding a parser per format, we let Claude read
the whole document and pull out just the national-level category totals —
this is the same approach used for Annual Pass PDF parsing in PULSE.
"""

import json
import re

import pdfplumber
import streamlit as st
from anthropic import Anthropic

VALID_CATEGORIES = {"2W", "3W", "PV", "CV", "TRAC", "CE", "Total"}

CATEGORY_ALIASES = {
    "TRACTOR": "TRAC",
    "TRACTORS": "TRAC",
    "CONSTRUCTION EQUIPMENT": "CE",
    "CE (CONSTRUCTION EQUIPMENT)": "CE",
    "TWO WHEELER": "2W",
    "TWO-WHEELER": "2W",
    "THREE WHEELER": "3W",
    "THREE-WHEELER": "3W",
    "PASSENGER VEHICLE": "PV",
    "PASSENGER VEHICLES": "PV",
    "COMMERCIAL VEHICLE": "CV",
    "COMMERCIAL VEHICLES": "CV",
    "GRAND TOTAL": "Total",
    "ALL INDIA TOTAL": "Total",
    "TOTAL": "Total",
}


def normalize_category(raw: str) -> str:
    cleaned = raw.strip().upper()
    if cleaned in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[cleaned]
    # Already-canonical values (2W, 3W, PV, CV, TRAC, CE) are all uppercase
    # except "Total" — handle that case-insensitively too.
    if cleaned == "TOTAL":
        return "Total"
    return raw.strip()

EXTRACTION_PROMPT = """You are extracting vehicle registration data from a FADA \
(Federation of Automobile Dealers Associations) monthly press release.

Find the ALL-INDIA national summary table (not any state-wise or OEM-wise \
breakdown table) showing category-wise registration counts for the month this \
release covers.

Return ONLY a JSON object, no other text, no markdown fences, in this exact shape:

{
  "month": "YYYY-MM",
  "rows": [
    {"category": "2W", "current_month_units": 1234567},
    {"category": "3W", "current_month_units": 12345},
    {"category": "PV", "current_month_units": 123456},
    {"category": "CV", "current_month_units": 12345},
    {"category": "TRAC", "current_month_units": 12345},
    {"category": "CE", "current_month_units": 1234},
    {"category": "Total", "current_month_units": 1234567}
  ]
}

Rules:
- "month" is the month THIS release's data is FOR (not the release/publish date),
  as YYYY-MM.
- The "category" field must be EXACTLY one of: "2W", "3W", "PV", "CV", "TRAC",
  "CE", "Total" — even if the source table labels the row differently (e.g. a
  row titled "TRACTOR" or "TRACTORS" must still be output as "TRAC"; a row
  titled "GRAND TOTAL" must still be output as "Total").
- Only include categories that are actually present as their own row in the
  national summary table. Not every release has TRAC or CE — omit categories
  that aren't present rather than guessing or inventing a value.
- current_month_units must be a plain integer with commas/spaces stripped
  (Indian releases use lakh-style grouping like 13,34,941 — convert that to
  1334941).
- Do not include MoM%, YoY%, or any other column.
- Do not include state-wise or OEM-wise rows, only the national total table.
"""


def extract_pdf_text(uploaded_file) -> str:
    with pdfplumber.open(uploaded_file) as pdf:
        text_parts = [page.extract_text() or "" for page in pdf.pages]
    return "\n\n".join(text_parts)


def parse_with_claude(pdf_text: str) -> dict:
    """Send extracted PDF text to Claude and return the parsed {month, rows} dict."""
    api_key = st.secrets["ANTHROPIC_API_KEY"]
    client = Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=EXTRACTION_PROMPT,
        messages=[{"role": "user", "content": pdf_text[:15000]}],  # cap for very long docs
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude did not return valid JSON:\n{raw}") from e

    if "month" not in data or "rows" not in data:
        raise ValueError(f"Unexpected response shape: {data}")

    for row in data["rows"]:
        row["category"] = normalize_category(row.get("category", ""))
        if row["category"] not in VALID_CATEGORIES:
            raise ValueError(f"Unrecognized category in response: {row}")

    return data


def build_rows(parsed: dict, source_filename: str) -> list[dict]:
    """Convert {month, rows} into flat dicts ready for the Supabase upsert."""
    month = parsed["month"]
    return [
        {
            "month": month,
            "category": r["category"],
            "current_month_units": r["current_month_units"],
            "source_file": source_filename,
        }
        for r in parsed["rows"]
    ]
