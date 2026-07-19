# Carob Order Tracker — Demo

A standalone, self-contained deployment package for the sales-demo
version of the Carob Order Tracker. Sample data only — safe to show
prospective clients, fully isolated from any real customer's data or
schema (including the real BTP/Jivan LLP deployment).

## 1. Set up the database

You have two options:

**Option A — Use a brand-new, dedicated Supabase project** (recommended)
Simplest and safest — a fresh free-tier project has zero risk of
colliding with any of your other apps' tables. Just run
`sql/demo_schema.sql` there.

**Option B — Use an existing shared Supabase project**
If you're adding this to a project that already has other apps'
tables (as ours did), the `demo` schema name keeps this fully
isolated from them. Still just run `sql/demo_schema.sql` — it only
touches the `demo` schema, nothing else in the project.

Either way:
1. Open your Supabase project → **SQL Editor** → New query.
2. Paste and run the contents of `sql/demo_schema.sql`. This creates
   the `demo` schema, all 5 tables, RLS policies, grants, and seeds
   sample customers/products so the app isn't empty on first run.
3. Go to **Project Settings → API → Exposed schemas** and add `demo`
   to the list, then save. (Supabase only exposes `public` over the
   REST API by default — skip this and every query fails.)

## 2. Configure credentials

Copy the example secrets file and fill in your project's values:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml`:
```toml
[supabase]
url      = "https://YOUR-PROJECT-REF.supabase.co"
key      = "YOUR-ANON-OR-SERVICE-ROLE-KEY-HERE"
pg_host  = "aws-1-ap-southeast-1.pooler.supabase.com"
pg_user  = "postgres.YOUR-PROJECT-REF"
password = "YOUR-DB-PASSWORD-HERE"
```

Get `url` and `key` from **Project Settings → API**. This app only
uses those two — the `pg_*` fields are unused placeholders, kept for
consistency with the other Carob apps' secrets format.

`secrets.toml` is git-ignored — never commit it.

## 3. Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Use the **"Viewing as"** dropdown in the sidebar to switch between
Sales Coordinator / Factory / Regional Sales Person / Management /
Admin — this simulated role switch (no real login) is exactly what
makes this version quick and frictionless to demo to a prospect.

## 4. Deploy to GitHub + Streamlit Cloud

1. Create a new GitHub repo, push everything in this folder
   (`.streamlit/secrets.toml` stays out of git — `.gitignore`
   already handles that).
2. Go to **share.streamlit.io** → New app → pick the repo → main
   file `app.py` → Deploy.
3. In the deployed app's **Settings → Secrets**, paste the same
   `[supabase]` block from your local `secrets.toml`.
4. Share the resulting public URL with prospective clients.

## What's in this package

- `app.py` — the full app (order entry, tracker, status workflow,
  dashboard, admin, PDF export, Excel bulk upload)
- `requirements.txt` — Python dependencies
- `sql/demo_schema.sql` — single consolidated schema script (all
  tables/columns already merged in — no need to run multiple
  incremental migrations)
- `.streamlit/config.toml` — light theme, navy/gold branding
- `.streamlit/secrets.toml.example` — credentials template
- `.gitignore` — keeps secrets and local artifacts out of git

## Note

This is intentionally the simpler, role-switcher version (no real
per-person login) — that's a feature for a demo, not a limitation:
it lets a prospect click through every role's view instantly without
needing credentials. The production version being built for the real
Jivan LLP customer uses proper Supabase Auth login instead, and lives
in a completely separate schema/project from this one.
