import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.express as px
import pandas as pd
import numpy as np
import db
from components.filters import init_filter_defaults, get_filter_dict, render_filters

st.set_page_config(
    page_title="Category Scorecard · Olist",
    page_icon="🏷️",
    layout="wide",
)

# ── Styles + Font Awesome ─────────────────────────────────────────────────────
st.markdown("""
<link rel="stylesheet"
      href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css"
      crossorigin="anonymous">
<style>
[data-testid="stSidebarNavItems"] a,
section[data-testid="stSidebar"] nav a {
    font-weight: 600 !important;
    font-size: 0.92rem !important;
    letter-spacing: 0.03em !important;
    padding: 0.45rem 0.85rem !important;
    border-radius: 0.45rem !important;
    border-left: 3px solid transparent !important;
    transition: background 0.15s ease, border-left-color 0.15s ease !important;
}
[data-testid="stSidebarNavItems"] a:hover,
section[data-testid="stSidebar"] nav a:hover {
    background: rgba(77, 166, 216, 0.12) !important;
    border-left-color: rgba(77, 166, 216, 0.45) !important;
}
[data-testid="stSidebarNavItems"] a[aria-current="page"],
section[data-testid="stSidebar"] nav a[aria-current="page"] {
    background: rgba(77, 166, 216, 0.22) !important;
    border-left: 3px solid #4da6d8 !important;
    color: #4da6d8 !important;
    font-weight: 700 !important;
}
[data-testid="stMetric"] label {
    font-weight: 600 !important;
    font-size: 0.78rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: #7aa3c8 !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.75rem !important;
    font-weight: 700 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Filter state ──────────────────────────────────────────────────────────────
init_filter_defaults()
st.session_state.setdefault("filters_open", True)
filters = get_filter_dict()
where = db.build_where(filters)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    '<h1 style="margin-bottom:0">'
    '<i class="fa-solid fa-tags" style="color:#4da6d8;margin-right:0.4em"></i>'
    'Category Performance Scorecard'
    '</h1>',
    unsafe_allow_html=True,
)
cap_col, tog_col = st.columns([8, 2])
with cap_col:
    st.caption(
        "Which product categories drive revenue, which have quality problems, "
        "and which are expensive to ship relative to item price?"
    )
with tog_col:
    st.toggle("Filters", key="filters_open")

# ── Layout ────────────────────────────────────────────────────────────────────
if st.session_state["filters_open"]:
    content_col, filter_col = st.columns([3, 1], gap="large")
    with filter_col:
        with st.container(border=True):
            st.markdown("##### 🎛️ Filters")
            render_filters()
else:
    content_col = st.container()

# ── Styler helpers (defined at module level — no rendering) ───────────────────
def _color_review(val):
    if pd.isna(val):
        return ""
    if val >= 4.0:
        return "background-color: rgba(34,197,94,0.22); color: #4ade80"
    if val >= 3.0:
        return "background-color: rgba(234,179,8,0.22); color: #fbbf24"
    return "background-color: rgba(239,68,68,0.22); color: #f87171"


def _color_late(val):
    if pd.isna(val):
        return ""
    if val > 10.0:
        return "background-color: rgba(239,68,68,0.22); color: #f87171"
    return ""


def _color_freight(val):
    if pd.isna(val):
        return ""
    if val > 0.30:
        return "background-color: rgba(239,68,68,0.22); color: #f87171"
    return ""


# ── Main content ──────────────────────────────────────────────────────────────
with content_col:
    cat_df = db.query(f"""
        SELECT
            COALESCE(product_category_name_english, 'Unknown') AS category,
            COUNT(DISTINCT order_id)                            AS order_count,
            SUM(total_item_value)                               AS gmv,
            AVG(price)                                          AS avg_price,
            AVG(freight_ratio)                                  AS avg_freight_ratio,
            AVG(avg_review_score)                               AS avg_review_score,
            SUM(is_late::int) * 100.0 / COUNT(*)               AS late_pct,
            AVG(transit_days)                                   AS avg_transit_days
        FROM orders_enriched
        {where}
        GROUP BY category
        ORDER BY gmv DESC
    """)

    if cat_df.empty:
        st.warning("No category data matches the current filters.")
        st.stop()

    # ── KPI row ───────────────────────────────────────────────────────────────
    n_cats       = len(cat_df)
    total_gmv    = float(cat_df["gmv"].sum())
    avg_review   = float(cat_df["avg_review_score"].mean())
    avg_late_pct = float(cat_df["late_pct"].mean())

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🏷️  Categories",       f"{n_cats:,}")
    k2.metric("💰  Total GMV",        f"R$ {total_gmv:,.0f}")
    k3.metric("⭐  Avg Review Score", f"{avg_review:.2f} / 5")
    k4.metric("🚨  Avg Late Rate",    f"{avg_late_pct:.1f}%")

    st.divider()

    # ── Scorecard Table ───────────────────────────────────────────────────────
    st.subheader("Scorecard Table")
    st.caption(
        "Click any column header to sort. "
        "**Review score**: 🟢 ≥ 4.0 · 🟡 3–4 · 🔴 < 3 · "
        "**Late rate**: 🔴 > 10% · **Freight ratio**: 🔴 > 0.30"
    )

    display_df = cat_df.rename(columns={
        "category":          "Category",
        "order_count":       "Orders",
        "gmv":               "GMV (R$)",
        "avg_price":         "Avg Price (R$)",
        "avg_freight_ratio": "Freight Ratio",
        "avg_review_score":  "Avg Review",
        "late_pct":          "Late Rate (%)",
        "avg_transit_days":  "Avg Transit (days)",
    }).copy()

    styled = (
        display_df.style
        .map(_color_review,  subset=["Avg Review"])
        .map(_color_late,    subset=["Late Rate (%)"])
        .map(_color_freight, subset=["Freight Ratio"])
    )

    st.dataframe(
        styled,
        hide_index=True,
        height=440,
        column_config={
            "Orders":              st.column_config.NumberColumn(format="%d"),
            "GMV (R$)":           st.column_config.NumberColumn(format="R$ %.0f"),
            "Avg Price (R$)":     st.column_config.NumberColumn(format="R$ %.2f"),
            "Freight Ratio":      st.column_config.NumberColumn(format="%.3f"),
            "Avg Review":         st.column_config.NumberColumn(format="%.2f"),
            "Late Rate (%)":      st.column_config.NumberColumn(format="%.1f%%"),
            "Avg Transit (days)": st.column_config.NumberColumn(format="%.1f"),
        },
    )

    st.divider()

    # ── Scatter Plot ──────────────────────────────────────────────────────────
    st.subheader("Quality vs. Lateness — Category Bubble Chart")
    st.caption(
        "Bubble **size** = GMV (log-scaled) · Bubble **color** = Freight Ratio (blue → amber → red). "
        "Dashed lines divide the space at Review = 4.0 and Late Rate = 10%. "
        "Categories in the **top-left** quadrant (low review, high late rate) are the problem children."
    )

    scatter_df = cat_df.dropna(subset=["avg_review_score", "late_pct", "gmv"]).copy()
    scatter_df["_size"] = np.log1p(scatter_df["gmv"]).clip(lower=1)

    fig = px.scatter(
        scatter_df,
        x="avg_review_score",
        y="late_pct",
        size="_size",
        color="avg_freight_ratio",
        hover_name="category",
        hover_data={
            "order_count":       True,
            "gmv":               True,
            "avg_price":         True,
            "avg_freight_ratio": True,
            "avg_review_score":  True,
            "late_pct":          True,
            "avg_transit_days":  True,
            "_size":             False,
        },
        size_max=55,
        color_continuous_scale=[[0, "#4da6d8"], [0.35, "#f59e0b"], [1, "#ef4444"]],
        labels={
            "avg_review_score":  "Avg Review Score",
            "late_pct":          "Late Rate (%)",
            "avg_freight_ratio": "Freight Ratio",
            "order_count":       "Orders",
            "gmv":               "GMV (R$)",
            "avg_price":         "Avg Price (R$)",
            "avg_transit_days":  "Avg Transit (days)",
        },
        template="plotly_dark",
    )

    fig.add_vline(
        x=4.0,
        line_dash="dash",
        line_color="rgba(232,234,240,0.4)",
        line_width=1.5,
        annotation_text="Review = 4.0",
        annotation_position="bottom right",
        annotation_font=dict(color="#7aa3c8", size=11),
    )
    fig.add_hline(
        y=10.0,
        line_dash="dash",
        line_color="rgba(232,234,240,0.4)",
        line_width=1.5,
        annotation_text="Late = 10%",
        annotation_position="top right",
        annotation_font=dict(color="#7aa3c8", size=11),
    )

    fig.add_annotation(
        xref="paper", yref="paper",
        x=0.01, y=0.99,
        text="⚠️ Problem Children",
        showarrow=False,
        font=dict(color="#f87171", size=12, family="monospace"),
        xanchor="left", yanchor="top",
        bgcolor="rgba(239,68,68,0.10)",
        borderpad=4,
    )
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0.99, y=0.01,
        text="✅ High Quality",
        showarrow=False,
        font=dict(color="#4ade80", size=12, family="monospace"),
        xanchor="right", yanchor="bottom",
        bgcolor="rgba(34,197,94,0.10)",
        borderpad=4,
    )

    fig.update_layout(
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font=dict(color="#e8eaf0"),
        height=580,
        margin=dict(t=30, b=60, l=60, r=20),
        xaxis=dict(
            title="Avg Review Score",
            tickfont=dict(size=12),
            gridcolor="rgba(255,255,255,0.07)",
            zeroline=False,
        ),
        yaxis=dict(
            title="Late Rate (%)",
            tickfont=dict(size=12),
            gridcolor="rgba(255,255,255,0.07)",
            zeroline=False,
        ),
        coloraxis_colorbar=dict(
            title="Freight<br>Ratio",
            tickfont=dict(size=11),
            len=0.6,
            thickness=14,
        ),
    )

    st.plotly_chart(fig)

    # ── Bottom summary ────────────────────────────────────────────────────────
    st.divider()

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Top 5 Categories by GMV**")
        top5 = cat_df.nlargest(5, "gmv")[["category", "gmv", "avg_review_score", "late_pct"]].copy()
        top5.rename(columns={
            "category":         "Category",
            "gmv":              "GMV (R$)",
            "avg_review_score": "Avg Review",
            "late_pct":         "Late Rate (%)",
        }, inplace=True)
        st.dataframe(
            top5,
            hide_index=True,
            column_config={
                "GMV (R$)":      st.column_config.NumberColumn(format="R$ %.0f"),
                "Avg Review":    st.column_config.NumberColumn(format="%.2f"),
                "Late Rate (%)": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )

    with col_b:
        st.markdown("**Most Problematic Categories** (lowest review score, min 50 orders)")
        problem = (
            cat_df[cat_df["order_count"] >= 50]
            .nsmallest(5, "avg_review_score")[["category", "avg_review_score", "late_pct", "order_count"]]
            .copy()
        )
        problem.rename(columns={
            "category":         "Category",
            "avg_review_score": "Avg Review",
            "late_pct":         "Late Rate (%)",
            "order_count":      "Orders",
        }, inplace=True)

        styled_problem = problem.style.map(_color_review, subset=["Avg Review"])
        st.dataframe(
            styled_problem,
            hide_index=True,
            column_config={
                "Avg Review":    st.column_config.NumberColumn(format="%.2f"),
                "Late Rate (%)": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )
