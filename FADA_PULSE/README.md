# FADA Pulse

CarobInsights app for tracking FADA monthly vehicle retail data over time.

## Setup

1. **Create the Supabase table** — run `create_table.sql` once in your
   Supabase project's SQL editor.

2. **Install dependencies**
   ```
   pip install -r requirements.txt --break-system-packages
   ```

3. **Configure secrets** — copy the template and fill in real values:
   ```
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```
   Edit `.streamlit/secrets.toml` with your actual Supabase URL/key and
   Anthropic API key. **Never commit this file or paste its contents into
   chat** — add it to `.gitignore` if this becomes a repo.

4. **Run it**
   ```
   streamlit run app.py
   ```

## Pages

- **Upload** — drop in a FADA monthly press-release PDF. The app extracts
  text with pdfplumber, sends it to Claude to pull out the national
  category-wise totals (2W/3W/PV/CV/TRAC/CE/Total), and shows a preview.
  If any (month, category) rows already exist in the database, they're
  flagged with a side-by-side comparison before you choose to overwrite or
  skip them.

- **Data Table** — browse everything loaded so far, filter by month range
  and category, search by source file, and download a filtered CSV.

## Notes

- The schema intentionally does **not** store MoM%/YoY% — only
  `month`, `category`, `current_month_units`, and `source_file`. Calculate
  percentage changes on the fly from the raw units if/when needed.
- Upserts key off `(month, category)`, matching the unique constraint in
  `create_table.sql`, so re-uploading the same month is always safe.
- One-off bulk migration from the existing `fada_category_summary.csv` can
  still use `upload_to_supabase.py` from the earlier round — this app is for
  ongoing month-by-month additions.
