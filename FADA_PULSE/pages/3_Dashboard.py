import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px

from utils.db import fetch_all_rows, fetch_all_annual_rows, fetch_all_oem_rows, CATEGORY_ORDER
from utils.oem_extractor import CATEGORY_LABELS

st.set_page_config(page_title="Dashboard — FADA Pulse", page_icon="📈", layout="wide")
st.title("📈 Trends")

# Native st.tabs() loses its selection whenever a widget inside a tab
# (e.g. the OEM category dropdown below) triggers a rerun — the whole
# script re-executes and the tab strip snaps back to the first tab. A
# session_state-backed radio doesn't have that problem, so we use one
# styled as tabs instead.
tab_labels = ["Monthly", "Annual (FY)", "OEM"]
if "dashboard_active_tab" not in st.session_state:
    st.session_state["dashboard_active_tab"] = tab_labels[0]
active_tab = st.radio(
    "Trend view",
    tab_labels,
    horizontal=True,
    key="dashboard_active_tab",
    label_visibility="collapsed",
)
st.divider()


def monthly_trend_chart(data: pd.DataFrame, title: str) -> None:
    """Line+marker chart on a categorical month axis, so gaps in coverage
    don't get visually smoothed over as if data were continuous."""
    data = data.copy()
    data["month_label"] = pd.to_datetime(data["month"], format="%Y-%m").dt.strftime("%b-%y")

    fig = px.line(
        data,
        x="month_label",
        y="current_month_units",
        markers=True,
        title=title,
    )
    fig.update_xaxes(
        type="category",
        title="Month",
        categoryorder="array",
        categoryarray=data["month_label"].tolist(),  # data is pre-sorted chronologically
    )
    fig.update_yaxes(title="Units", tickformat=",")
    fig.update_traces(hovertemplate="%{x}<br>%{y:,}<extra></extra>")
    fig.update_layout(height=400, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def annual_bar_chart(data: pd.DataFrame, title: str) -> None:
    fig = px.bar(data, x="fiscal_year", y="current_year_units", title=title)
    fig.update_xaxes(type="category", title="Fiscal Year")
    fig.update_yaxes(title="Units", tickformat=",")
    fig.update_traces(hovertemplate="%{x}<br>%{y:,}<extra></extra>")
    fig.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


def fy_sort_key(fy: str) -> int:
    """Sort 'FY23', 'FY26' etc. chronologically rather than alphabetically."""
    digits = "".join(ch for ch in fy if ch.isdigit())
    return int(digits) if digits else 0


# ============================================================
# MONTHLY TAB
# ============================================================
if active_tab == "Monthly":
    with st.spinner("Loading data..."):
        rows = fetch_all_rows()

    if not rows:
        st.info("No data yet — upload a PDF on the Upload page to get started.")
    else:
        df = pd.DataFrame(rows)
        df = df[["month", "category", "current_month_units"]].sort_values("month")

        months_present = sorted(df["month"].unique())
        st.caption(
            f"{len(months_present)} months loaded: {months_present[0]} to {months_present[-1]} "
            f"(not all months in between are necessarily present — see Data Table for the full list)"
        )

        total_df = df[df["category"] == "Total"]
        if not total_df.empty:
            monthly_trend_chart(total_df, "Total vehicles")
        else:
            st.warning("No 'Total' category rows found yet.")

        st.subheader("Category-wise trends")
        other_categories = [c for c in CATEGORY_ORDER if c != "Total" and c in df["category"].unique()]
        for category in other_categories:
            cat_df = df[df["category"] == category]
            monthly_trend_chart(cat_df, category)

        missing_categories = [c for c in CATEGORY_ORDER if c not in df["category"].unique() and c != "Total"]
        if missing_categories:
            st.caption(f"No data yet for: {', '.join(missing_categories)}")

# ============================================================
# ANNUAL TAB
# ============================================================
elif active_tab == "Annual (FY)":
    with st.spinner("Loading data..."):
        all_annual_rows = fetch_all_annual_rows()

    if not all_annual_rows:
        st.info("No annual data yet — upload on the Annual & OEM page to get started.")
    else:
        all_annual_df = pd.DataFrame(all_annual_rows)
        all_annual_df["subcategory"] = all_annual_df["subcategory"].fillna("")
        parent_df = all_annual_df[all_annual_df["subcategory"] == ""].sort_values("fiscal_year")

        total_df = parent_df[parent_df["category"] == "Total"]
        if not total_df.empty:
            annual_bar_chart(total_df, "Total vehicles")
        else:
            st.warning("No 'Total' category rows found yet.")

        st.subheader("Category-wise trends")
        other_categories = [c for c in CATEGORY_ORDER if c != "Total" and c in parent_df["category"].unique()]
        for category in other_categories:
            cat_df = parent_df[parent_df["category"] == category]
            annual_bar_chart(cat_df, category)

# ============================================================
# OEM TAB
# ============================================================
else:
    with st.spinner("Loading data..."):
        all_oem_rows = fetch_all_oem_rows()

    if not all_oem_rows:
        st.info("No OEM data yet — upload on the Annual & OEM page to get started.")
    else:
        all_oem_df = pd.DataFrame(all_oem_rows)
        all_oem_df["parent_oem"] = all_oem_df["parent_oem"].fillna("")

        category_filter = st.selectbox(
            "Category",
            options=["All"] + sorted(all_oem_df["category"].unique()),
            format_func=lambda c: c if c == "All" else f"{CATEGORY_LABELS.get(c, c)} ({c})",
            key="dash_oem_category_filter",
        )

        scope_df = all_oem_df if category_filter == "All" else all_oem_df[all_oem_df["category"] == category_filter]
        top_level = scope_df[scope_df["parent_oem"] == ""]  # exclude sub-entities to avoid double counting

        fy_order = sorted(top_level["fiscal_year"].unique(), key=fy_sort_key)

        # --- Overall trend ---
        trend_df = top_level.groupby("fiscal_year", as_index=False)["current_year_units"].sum()
        trend_df["fiscal_year"] = pd.Categorical(trend_df["fiscal_year"], categories=fy_order, ordered=True)
        trend_df = trend_df.sort_values("fiscal_year")

        title = (
            "Total units — all categories"
            if category_filter == "All"
            else f"Total units — {CATEGORY_LABELS.get(category_filter, category_filter)}"
        )
        fig = px.bar(trend_df, x="fiscal_year", y="current_year_units", title=title)
        fig.update_xaxes(type="category", title="Fiscal Year", categoryorder="array", categoryarray=fy_order)
        fig.update_yaxes(title="Units", tickformat=",")
        fig.update_traces(hovertemplate="%{x}<br>%{y:,}<extra></extra>")
        fig.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, use_container_width=True)

        # --- Per-OEM trend, with a way to avoid a 15-line spaghetti chart ---
        st.subheader("OEM-wise trend")

        totals_by_oem = (
            top_level.groupby("oem_name")["current_year_units"].sum().sort_values(ascending=False)
        )
        all_oem_names = list(totals_by_oem.index)

        col1, col2, col3 = st.columns([1.2, 2, 1.2])
        with col1:
            top_n = st.selectbox(
                "Show top",
                options=[5, 8, 10, 15, "All"],
                index=1,
                key="dash_oem_top_n",
            )
        with col2:
            manual_oems = st.multiselect(
                "Or pick specific OEMs (overrides Top N above)",
                options=all_oem_names,
                default=[],
                key="dash_oem_manual_pick",
            )
        with col3:
            show_as_share = st.checkbox("Show as % market share", value=False, key="dash_oem_as_share")

        if manual_oems:
            selected_oems = manual_oems
        elif top_n == "All":
            selected_oems = all_oem_names
        else:
            selected_oems = list(totals_by_oem.head(top_n).index)

        trend_by_oem = top_level[top_level["oem_name"].isin(selected_oems)].copy()

        if show_as_share:
            fy_totals = top_level.groupby("fiscal_year")["current_year_units"].sum()
            trend_by_oem["value"] = trend_by_oem.apply(
                lambda r: (r["current_year_units"] / fy_totals[r["fiscal_year"]] * 100)
                if fy_totals[r["fiscal_year"]] else 0,
                axis=1,
            )
            y_col, y_title, hover_fmt = "value", "Market share (%)", "%{x}<br>%{y:.2f}%<extra></extra>"
        else:
            trend_by_oem["value"] = trend_by_oem["current_year_units"]
            y_col, y_title, hover_fmt = "value", "Units", "%{x}<br>%{y:,}<extra></extra>"

        trend_by_oem["fiscal_year"] = pd.Categorical(trend_by_oem["fiscal_year"], categories=fy_order, ordered=True)
        trend_by_oem = trend_by_oem.sort_values("fiscal_year")

        oem_fig = px.line(
            trend_by_oem,
            x="fiscal_year",
            y=y_col,
            color="oem_name",
            markers=True,
        )
        oem_fig.update_xaxes(type="category", title="Fiscal Year", categoryorder="array", categoryarray=fy_order)
        oem_fig.update_yaxes(title=y_title, tickformat="," if not show_as_share else None)
        oem_fig.update_traces(hovertemplate=hover_fmt)
        oem_fig.update_layout(height=450, margin=dict(l=10, r=10, t=20, b=10), legend_title="OEM")
        st.plotly_chart(oem_fig, use_container_width=True)

        if not manual_oems and top_n != "All" and len(all_oem_names) > top_n:
            st.caption(
                f"Showing top {top_n} of {len(all_oem_names)} OEMs by total volume. "
                f"Use the picker above to compare specific smaller players instead."
            )

        # --- OEM x fiscal-year table ---
        st.subheader("OEM breakdown by fiscal year")

        pivot = top_level.pivot_table(
            index="oem_name", columns="fiscal_year", values="current_year_units", aggfunc="sum", fill_value=0
        )
        pivot = pivot[fy_order]  # chronological column order
        pivot["Total"] = pivot.sum(axis=1)
        pivot = pivot.sort_values("Total", ascending=False).drop(columns="Total")

        st.dataframe(pivot, use_container_width=True)

        st.download_button(
            "Download OEM x FY table (CSV)",
            data=pivot.to_csv(),
            file_name=f"fada_oem_by_year_{category_filter}.csv",
            mime="text/csv",
            key="dash_oem_download",
        )
