import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.express as px
import pandas as pd
import numpy as np
import db
from components.filters import init_filter_defaults, get_filter_dict, render_filters
from components.maps import seller_scatter_map

st.set_page_config(
    page_title="Seller Performance · Olist",
    page_icon="🏪",
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
st.session_state.setdefault("filters_open",        True)
st.session_state.setdefault("filter_seller_states", [])
st.session_state.setdefault("filter_min_orders",    10)
st.session_state.setdefault("seller_highlight_id",  None)

filters       = get_filter_dict()
seller_states = st.session_state["filter_seller_states"]
min_orders    = st.session_state["filter_min_orders"]

# ── Build WHERE clause (global + seller-state extension) ──────────────────────
where = db.build_where(filters)
if seller_states:
    vals = ", ".join(f"'{s}'" for s in seller_states)
    seller_clause = f"seller_state IN ({vals})"
    full_where = f"{where} AND {seller_clause}" if where else f"WHERE {seller_clause}"
else:
    full_where = where

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    '<h1 style="margin-bottom:0">'
    '<i class="fa-solid fa-store" style="color:#4da6d8;margin-right:0.4em"></i>'
    'Seller Performance Ranking'
    '</h1>',
    unsafe_allow_html=True,
)
cap_col, tog_col = st.columns([8, 2])
with cap_col:
    st.caption(
        "Who are the top sellers, and which high-volume sellers have quality or lateness problems? "
        "Click a bubble in the scatter plot to spotlight that seller in the leaderboard."
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
            st.divider()
            st.markdown("**Seller Filters**")

            @st.cache_data(show_spinner=False)
            def _seller_state_options() -> list:
                return db.query(
                    "SELECT DISTINCT seller_state FROM orders_enriched "
                    "WHERE seller_state IS NOT NULL ORDER BY 1"
                )["seller_state"].tolist()

            st.multiselect(
                "Seller State",
                options=_seller_state_options(),
                key="filter_seller_states",
                placeholder="All seller states",
            )
            st.slider(
                "Min orders per seller",
                min_value=1, max_value=100, step=1,
                key="filter_min_orders",
                help="Raise this to filter out low-volume sellers and focus on established ones.",
            )
else:
    content_col = st.container()

# ── Styler helpers (no rendering) ─────────────────────────────────────────────
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


# ── Main content ──────────────────────────────────────────────────────────────
with content_col:
    seller_df = db.query(f"""
        SELECT
            seller_id,
            seller_city,
            seller_state,
            AVG(seller_lat)                                     AS seller_lat,
            AVG(seller_lng)                                     AS seller_lng,
            COUNT(DISTINCT order_id)                            AS order_count,
            SUM(total_item_value)                               AS gmv,
            AVG(avg_review_score)                               AS avg_review_score,
            SUM(is_late::int) * 100.0 / COUNT(*)               AS late_pct,
            AVG(approval_wait_hours)                            AS avg_approval_wait_hours,
            COUNT(DISTINCT product_category_name_english)       AS category_count
        FROM orders_enriched
        {full_where}
        GROUP BY seller_id, seller_city, seller_state
        HAVING COUNT(DISTINCT order_id) >= {min_orders}
        ORDER BY gmv DESC
    """)

    if seller_df.empty:
        st.warning("No sellers match the current filters. Try lowering the minimum order count or broadening the filters.")
        st.stop()

    seller_df = seller_df.reset_index(drop=True)

    # ── KPI row ───────────────────────────────────────────────────────────────
    n_sellers  = len(seller_df)
    total_gmv  = float(seller_df["gmv"].sum())
    avg_review = float(seller_df["avg_review_score"].mean())
    avg_late   = float(seller_df["late_pct"].mean())

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🏪  Active Sellers",   f"{n_sellers:,}")
    k2.metric("💰  Total GMV",        f"R$ {total_gmv:,.0f}")
    k3.metric("⭐  Avg Review Score", f"{avg_review:.2f} / 5")
    k4.metric("🚨  Avg Late Rate",    f"{avg_late:.1f}%")

    st.divider()

    # ── Side-by-side: scatter plot + mini map ─────────────────────────────────
    scatter_col, map_col = st.columns([3, 2])

    with scatter_col:
        st.subheader("Quality vs. Lateness")
        st.caption(
            "Each bubble = one seller · **Size** = GMV · **Color** = Review Score "
            "(green = high, red = low). Click a bubble to spotlight it in the leaderboard."
        )

        scatter_df = seller_df.dropna(subset=["avg_review_score", "late_pct", "gmv"]).copy()
        scatter_df["_size"] = np.log1p(scatter_df["gmv"]).clip(lower=1)
        scatter_df["_sid_short"] = scatter_df["seller_id"].str[:12] + "…"

        fig_scatter = px.scatter(
            scatter_df,
            x="avg_review_score",
            y="late_pct",
            size="_size",
            color="avg_review_score",
            hover_name="_sid_short",
            custom_data=["seller_id"],
            hover_data={
                "seller_city":             True,
                "seller_state":            True,
                "order_count":             True,
                "gmv":                     True,
                "avg_review_score":        True,
                "late_pct":                True,
                "avg_approval_wait_hours": True,
                "_size":                   False,
                "_sid_short":              False,
            },
            size_max=40,
            color_continuous_scale=[[0, "#cc2200"], [0.5, "#ffdd00"], [1, "#00aa44"]],
            labels={
                "avg_review_score":        "Avg Review Score",
                "late_pct":                "Late Rate (%)",
                "order_count":             "Orders",
                "gmv":                     "GMV (R$)",
                "avg_approval_wait_hours": "Avg Approval Wait (h)",
                "seller_city":             "City",
                "seller_state":            "State",
            },
            template="plotly_dark",
        )

        fig_scatter.add_vline(
            x=4.0,
            line_dash="dash",
            line_color="rgba(232,234,240,0.35)",
            line_width=1.5,
            annotation_text="Review = 4.0",
            annotation_position="bottom right",
            annotation_font=dict(color="#7aa3c8", size=10),
        )
        fig_scatter.add_hline(
            y=10.0,
            line_dash="dash",
            line_color="rgba(232,234,240,0.35)",
            line_width=1.5,
            annotation_text="Late = 10%",
            annotation_position="top right",
            annotation_font=dict(color="#7aa3c8", size=10),
        )
        fig_scatter.add_annotation(
            xref="paper", yref="paper", x=0.01, y=0.99,
            text="⚠️ Problem Sellers",
            showarrow=False,
            font=dict(color="#f87171", size=11),
            xanchor="left", yanchor="top",
            bgcolor="rgba(239,68,68,0.10)", borderpad=3,
        )
        fig_scatter.add_annotation(
            xref="paper", yref="paper", x=0.99, y=0.01,
            text="✅ Reliable",
            showarrow=False,
            font=dict(color="#4ade80", size=11),
            xanchor="right", yanchor="bottom",
            bgcolor="rgba(34,197,94,0.10)", borderpad=3,
        )

        # Highlight previously selected seller with a ring marker
        if st.session_state["seller_highlight_id"]:
            hl = seller_df[seller_df["seller_id"] == st.session_state["seller_highlight_id"]]
            if not hl.empty:
                import plotly.graph_objects as go
                fig_scatter.add_trace(go.Scatter(
                    x=hl["avg_review_score"],
                    y=hl["late_pct"],
                    mode="markers",
                    marker=dict(
                        symbol="circle-open",
                        size=22,
                        color="#ffffff",
                        line=dict(color="#ffffff", width=2.5),
                    ),
                    showlegend=False,
                    hoverinfo="skip",
                    name="",
                ))

        fig_scatter.update_layout(
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            font=dict(color="#e8eaf0"),
            height=480,
            margin=dict(t=20, b=50, l=50, r=10),
            xaxis=dict(
                title="Avg Review Score",
                tickfont=dict(size=11),
                gridcolor="rgba(255,255,255,0.07)",
                zeroline=False,
            ),
            yaxis=dict(
                title="Late Rate (%)",
                tickfont=dict(size=11),
                gridcolor="rgba(255,255,255,0.07)",
                zeroline=False,
            ),
            coloraxis_colorbar=dict(
                title="Review",
                tickfont=dict(size=10),
                len=0.55,
                thickness=12,
            ),
        )

        scatter_event = st.plotly_chart(
            fig_scatter,
            on_select="rerun",
            key="seller_scatter",
        )

        if scatter_event and scatter_event.selection and scatter_event.selection.points:
            pt = scatter_event.selection.points[0]
            if "customdata" in pt and pt["customdata"]:
                st.session_state["seller_highlight_id"] = pt["customdata"][0]

    with map_col:
        st.subheader("Seller Locations")
        st.caption(
            "Each dot = one seller location. "
            "🟢 Green = high review score · 🔴 Red = low review score · Size = GMV."
        )
        map_df = seller_df.dropna(subset=["seller_lat", "seller_lng"]).copy()
        if not map_df.empty:
            deck = seller_scatter_map(map_df)
            st.pydeck_chart(deck, height=480)
        else:
            st.info("No seller geo data for current filters.")

    # ── Selected seller info card ─────────────────────────────────────────────
    hl_id = st.session_state.get("seller_highlight_id")
    if hl_id:
        hl_row = seller_df[seller_df["seller_id"] == hl_id]
        if not hl_row.empty:
            r = hl_row.iloc[0]
            st.divider()
            info_cols = st.columns([1, 1, 1, 1, 1])
            info_cols[0].metric("📍  Location",  f"{r['seller_city'].title()}, {r['seller_state']}")
            info_cols[1].metric("📦  Orders",    f"{int(r['order_count']):,}")
            info_cols[2].metric("💰  GMV",       f"R$ {r['gmv']:,.0f}")
            info_cols[3].metric("⭐  Review",    f"{r['avg_review_score']:.2f}")
            info_cols[4].metric("🚨  Late Rate", f"{r['late_pct']:.1f}%")
            st.caption(
                f"**Selected:** `{hl_id[:20]}…` · "
                f"{int(r['category_count'])} categor{'y' if r['category_count'] == 1 else 'ies'} · "
                f"Avg approval wait: {r['avg_approval_wait_hours']:.1f} h · "
                f"[Click any other bubble to switch, or reload to clear]"
            )

    st.divider()

    # ── Leaderboard table ─────────────────────────────────────────────────────
    st.subheader(f"Leaderboard — Top {n_sellers:,} Sellers by GMV")
    st.caption(
        "Sorted by GMV descending. Click any column header to re-sort. "
        "**Review**: 🟢 ≥ 4.0 · 🟡 3–4 · 🔴 < 3 · **Late rate**: 🔴 > 10%"
    )

    orig_ids = seller_df["seller_id"].tolist()

    display_df = seller_df.copy()
    display_df["Seller ID"]         = display_df["seller_id"].str[:12] + "…"
    display_df["City"]              = display_df["seller_city"].str.title()
    display_df["State"]             = display_df["seller_state"]
    display_df["Orders"]            = display_df["order_count"].astype(int)
    display_df["GMV (R$)"]          = display_df["gmv"]
    display_df["Avg Review"]        = display_df["avg_review_score"]
    display_df["Late Rate (%)"]     = display_df["late_pct"]
    display_df["Approval Wait (h)"] = display_df["avg_approval_wait_hours"]
    display_df["Categories"]        = display_df["category_count"].astype(int)

    display_df = display_df[[
        "Seller ID", "City", "State", "Orders", "GMV (R$)",
        "Avg Review", "Late Rate (%)", "Approval Wait (h)", "Categories",
    ]]

    def _highlight_selected(row):
        if hl_id and orig_ids[row.name] == hl_id:
            return ["background-color: rgba(77,166,216,0.28)"] * len(row)
        return [""] * len(row)

    styled = (
        display_df.style
        .map(_color_review, subset=["Avg Review"])
        .map(_color_late,   subset=["Late Rate (%)"])
        .apply(_highlight_selected, axis=1)
    )

    st.dataframe(
        styled,
        hide_index=True,
        height=500,
        column_config={
            "Orders":             st.column_config.NumberColumn(format="%d"),
            "GMV (R$)":          st.column_config.NumberColumn(format="R$ %.0f"),
            "Avg Review":        st.column_config.NumberColumn(format="%.2f"),
            "Late Rate (%)":     st.column_config.NumberColumn(format="%.1f%%"),
            "Approval Wait (h)": st.column_config.NumberColumn(format="%.1f"),
        },
    )

    st.divider()

    # ── Bottom insight panels ─────────────────────────────────────────────────
    insight_l, insight_r = st.columns(2)

    with insight_l:
        st.markdown("**Top 5 Sellers by GMV**")
        top5 = seller_df.nlargest(5, "gmv")[
            ["seller_id", "seller_city", "seller_state", "order_count", "gmv", "avg_review_score", "late_pct"]
        ].copy()
        top5["Seller ID"] = top5["seller_id"].str[:12] + "…"
        top5 = top5.rename(columns={
            "seller_city":      "City",
            "seller_state":     "State",
            "order_count":      "Orders",
            "gmv":              "GMV (R$)",
            "avg_review_score": "Review",
            "late_pct":         "Late %",
        })[["Seller ID", "City", "State", "Orders", "GMV (R$)", "Review", "Late %"]]
        st.dataframe(
            top5,
            hide_index=True,
            column_config={
                "GMV (R$)": st.column_config.NumberColumn(format="R$ %.0f"),
                "Review":   st.column_config.NumberColumn(format="%.2f"),
                "Late %":   st.column_config.NumberColumn(format="%.1f%%"),
            },
        )

    with insight_r:
        st.markdown("**Most Problematic Sellers** (lowest review, min 50 orders)")
        problem = (
            seller_df[seller_df["order_count"] >= 50]
            .nsmallest(5, "avg_review_score")[
                ["seller_id", "seller_city", "seller_state", "order_count", "avg_review_score", "late_pct"]
            ]
            .copy()
        )
        if problem.empty:
            st.info("No sellers with ≥ 50 orders in this filter set.")
        else:
            problem["Seller ID"] = problem["seller_id"].str[:12] + "…"
            problem = problem.rename(columns={
                "seller_city":      "City",
                "seller_state":     "State",
                "order_count":      "Orders",
                "avg_review_score": "Review",
                "late_pct":         "Late %",
            })[["Seller ID", "City", "State", "Orders", "Review", "Late %"]]

            styled_problem = problem.style.map(_color_review, subset=["Review"])
            st.dataframe(
                styled_problem,
                hide_index=True,
                column_config={
                    "Review": st.column_config.NumberColumn(format="%.2f"),
                    "Late %": st.column_config.NumberColumn(format="%.1f%%"),
                },
            )
