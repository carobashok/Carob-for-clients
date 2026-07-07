-- Run this once in the Supabase SQL editor to create the table.
-- The UNIQUE constraint on (month, category) is what makes upload_to_supabase.py's
-- upsert() calls safe to re-run without creating duplicate rows.

create table if not exists fada_category_summary (
    id bigint generated always as identity primary key,
    month text not null,              -- format: YYYY-MM
    category text not null,           -- 2W, 3W, PV, CV, TRAC, CE, Total
    current_month_units bigint,
    source_file text,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (month, category)
);

-- Keep updated_at current on every upsert
create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_fada_updated_at on fada_category_summary;
create trigger trg_fada_updated_at
before update on fada_category_summary
for each row execute function set_updated_at();

-- Helpful index for the month-range queries you'll likely run from Streamlit
create index if not exists idx_fada_month on fada_category_summary (month);
