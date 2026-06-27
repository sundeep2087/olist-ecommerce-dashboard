import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.express as px
import pandas as pd
import db
from components.filters import init_filter_defaults, get_filter_dict, render_filters
from components.maps import delivery_scatter_map

st.set_page_config(
    page_title="Delivery Performance · Olist",
    page_icon="🚚",
    layout="wide",
)

# ── Styles + Font Awesome ─────────────────────────────────────────────────────
st.markdown("""
<link rel="stylesheet"
      href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css"
      crossorigin="anonymous">
<style>
/* ── Sidebar navigation ──────────────────────────────────────────────────── */
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
/* ── Sidebar labels ──────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] label {
    font-weight: 600 !important;
    font-size: 0.85rem !important;
}
/* ── KPI metric cards ────────────────────────────────────────────────────── */
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
    '<i class="fa-solid fa-truck-fast" style="color:#4da6d8;margin-right:0.4em"></i>'
    'Delivery Performance &amp; Late Delivery Hotspots'
    '</h1>',
    unsafe_allow_html=True,
)
cap_col, tog_col = st.columns([8, 2])
with cap_col:
    st.caption("Where are late deliveries happening? Is the bottleneck approval, carrier pickup, or transit?")
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

# ── Main content ──────────────────────────────────────────────────────────────
with content_col:
    kpi_df = db.query(f"""
        SELECT
            SUM(CASE WHEN is_late THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS late_delivery_pct,
            AVG(CASE WHEN delay_days > 0 THEN delay_days END)            AS avg_delay_when_late,
            AVG(transit_days)                                             AS avg_transit_days,
            COUNT(DISTINCT order_id)                                      AS total_orders
        FROM orders_enriched
        {where}
    """)

    if kpi_df.empty or (kpi_df["total_orders"].iloc[0] or 0) == 0:
        st.warning("No data matches the current filters.")
        st.stop()

    late_pct      = float(kpi_df["late_delivery_pct"].iloc[0] or 0)
    avg_late_days = float(kpi_df["avg_delay_when_late"].iloc[0] or 0)
    on_time_pct   = 100.0 - late_pct
    avg_transit   = float(kpi_df["avg_transit_days"].iloc[0] or 0)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🚨  Late Delivery Rate",        f"{late_pct:.1f}%")
    k2.metric("⏱️  Avg Days Late (when late)", f"{avg_late_days:.1f} days")
    k3.metric("✅  On-Time Rate",              f"{on_time_pct:.1f}%")
    k4.metric("🚚  Avg Transit Days",          f"{avg_transit:.1f} days")

    st.divider()

    # ── Three tabs ────────────────────────────────────────────────────────────
    tab_a, tab_b, tab_c = st.tabs([
        "🗺️  Delay Map",
        "📊  Stage Breakdown",
        "📈  Delay Distribution",
    ])

    # ─────────────────────────────────────────────────────────────────────────
    # Tab A — Delay map
    # ─────────────────────────────────────────────────────────────────────────
    with tab_a:
        st.subheader("Late Delivery Hotspots by State")
        st.caption(
            "Bubble size reflects the magnitude of the average delay. "
            "**Blue** = consistently early · **Red** = late on average. "
            "Hover a bubble for details."
        )

        delay_map_df = db.query(f"""
            SELECT
                customer_state,
                AVG(customer_lat)                        AS lat,
                AVG(customer_lng)                        AS lng,
                AVG(delay_days)                          AS avg_delay_days,
                SUM(CASE WHEN is_late THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS late_pct,
                AVG(transit_days)                        AS avg_transit_days
            FROM orders_enriched
            {where}
            GROUP BY customer_state
        """)

        if delay_map_df.empty:
            st.info("No geographic data for the current filters.")
        else:
            deck = delivery_scatter_map(delay_map_df)
            st.pydeck_chart(deck, height=520)
            st.caption("🔵 Blue = early deliveries · 🔴 Red = late deliveries · Larger bubble = bigger deviation from expected date")

            st.divider()
            st.subheader("State Summary — Delay Metrics")

            table_df = (
                delay_map_df[["customer_state", "avg_delay_days", "late_pct", "avg_transit_days"]]
                .dropna(subset=["avg_delay_days"])
                .sort_values("avg_delay_days", ascending=False)
                .copy()
            )
            table_df.rename(columns={
                "customer_state":   "State",
                "avg_delay_days":   "Avg Delay (days)",
                "late_pct":         "Late %",
                "avg_transit_days": "Avg Transit (days)",
            }, inplace=True)

            st.dataframe(
                table_df,
                hide_index=True,
                column_config={
                    "Avg Delay (days)":   st.column_config.NumberColumn(format="%.1f"),
                    "Late %":             st.column_config.NumberColumn(format="%.1f%%"),
                    "Avg Transit (days)": st.column_config.NumberColumn(format="%.1f"),
                },
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Tab B — Stage breakdown
    # ─────────────────────────────────────────────────────────────────────────
    with tab_b:
        st.subheader("Lifecycle Stage Breakdown by State")
        st.caption(
            "Stacked bars show average days spent in each lifecycle stage. "
            "States are ordered from most delayed (top) to least delayed (bottom). "
            "Compare bar widths across stages to find the bottleneck."
        )

        stage_df = db.query(f"""
            SELECT
                customer_state,
                AVG(approval_wait_hours) / 24  AS avg_days_to_approve,
                AVG(carrier_wait_hours)  / 24  AS avg_days_to_pickup,
                AVG(transit_days)              AS avg_transit_days,
                AVG(delay_days)                AS avg_delay
            FROM orders_enriched
            {where}
            GROUP BY customer_state
            ORDER BY avg_delay DESC
        """)

        if stage_df.empty:
            st.info("No stage data for the current filters.")
        else:
            stage_df = stage_df.sort_values("avg_delay", ascending=True)

            melted = stage_df.melt(
                id_vars="customer_state",
                value_vars=["avg_days_to_approve", "avg_days_to_pickup", "avg_transit_days"],
                var_name="Stage",
                value_name="Days",
            )
            melted["Stage"] = melted["Stage"].map({
                "avg_days_to_approve": "Order → Approval",
                "avg_days_to_pickup":  "Approval → Carrier",
                "avg_transit_days":    "Carrier → Delivery",
            })

            fig_stage = px.bar(
                melted,
                x="Days",
                y="customer_state",
                color="Stage",
                orientation="h",
                barmode="stack",
                color_discrete_map={
                    "Order → Approval":   "#4da6d8",
                    "Approval → Carrier": "#f59e0b",
                    "Carrier → Delivery": "#6366f1",
                },
                labels={"customer_state": "State", "Days": "Avg Days"},
                template="plotly_dark",
            )
            fig_stage.update_layout(
                paper_bgcolor="#0e1117",
                plot_bgcolor="#0e1117",
                font=dict(color="#e8eaf0"),
                height=max(420, len(stage_df) * 24 + 100),
                margin=dict(t=20, b=40, l=60, r=20),
                legend=dict(
                    orientation="h",
                    yanchor="bottom", y=1.01,
                    xanchor="left",   x=0,
                    font=dict(size=12),
                ),
                xaxis=dict(title="Average Days", tickfont=dict(size=11)),
                yaxis=dict(title=None, tickfont=dict(size=12)),
            )
            st.plotly_chart(fig_stage)

            st.divider()
            st.subheader("Stage Detail Table")

            detail_df = (
                stage_df[["customer_state", "avg_days_to_approve", "avg_days_to_pickup",
                           "avg_transit_days", "avg_delay"]]
                .sort_values("avg_delay", ascending=False)
                .copy()
            )
            detail_df.rename(columns={
                "customer_state":      "State",
                "avg_days_to_approve": "Approval (days)",
                "avg_days_to_pickup":  "Carrier Wait (days)",
                "avg_transit_days":    "Transit (days)",
                "avg_delay":           "Net Delay (days)",
            }, inplace=True)

            st.dataframe(
                detail_df,
                hide_index=True,
                column_config={
                    "Approval (days)":     st.column_config.NumberColumn(format="%.2f"),
                    "Carrier Wait (days)": st.column_config.NumberColumn(format="%.2f"),
                    "Transit (days)":      st.column_config.NumberColumn(format="%.2f"),
                    "Net Delay (days)":    st.column_config.NumberColumn(format="%.2f"),
                },
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Tab C — Delay distribution
    # ─────────────────────────────────────────────────────────────────────────
    with tab_c:
        st.subheader("Delay Distribution — All Orders")
        st.caption(
            "Each bar = number of orders with that delay. "
            "Negative values = delivered early · Positive = delivered late. "
            "The spike in the far left tail (~−30 days) is a known data anomaly: "
            "≈1,359 orders where the carrier scanned pickup before approval was recorded."
        )

        null_ext = "AND delay_days IS NOT NULL" if where else "WHERE delay_days IS NOT NULL"
        hist_df = db.query(f"""
            SELECT delay_days
            FROM orders_enriched
            {where}
            {null_ext}
        """)

        if hist_df.empty:
            st.info("No distribution data for the current filters.")
        else:
            hist_df["Status"] = hist_df["delay_days"].apply(
                lambda x: "Late" if x > 0 else "Early / On Time"
            )

            fig_hist = px.histogram(
                hist_df,
                x="delay_days",
                color="Status",
                color_discrete_map={
                    "Late":            "#cc2200",
                    "Early / On Time": "#4da6d8",
                },
                nbins=100,
                barmode="overlay",
                opacity=0.80,
                labels={"delay_days": "Delay (days)"},
                template="plotly_dark",
            )
            fig_hist.add_vline(
                x=0,
                line_dash="dash",
                line_color="#e8eaf0",
                line_width=1.5,
                annotation_text="On Time",
                annotation_position="top right",
                annotation_font=dict(color="#e8eaf0", size=12),
            )
            fig_hist.update_layout(
                paper_bgcolor="#0e1117",
                plot_bgcolor="#0e1117",
                font=dict(color="#e8eaf0"),
                height=440,
                margin=dict(t=30, b=40, l=0, r=0),
                legend=dict(
                    orientation="h",
                    yanchor="bottom", y=1.01,
                    xanchor="left",   x=0,
                ),
                xaxis=dict(title="Delay (days)", zeroline=True, zerolinecolor="#444"),
                yaxis=dict(title="Order Count"),
            )
            st.plotly_chart(fig_hist)

            st.divider()

            n_late    = int((hist_df["delay_days"] > 0).sum())
            n_early   = int((hist_df["delay_days"] <= 0).sum())
            med_late  = hist_df.loc[hist_df["delay_days"] > 0, "delay_days"].median()
            med_early = hist_df.loc[hist_df["delay_days"] <= 0, "delay_days"].median()

            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Late Orders",          f"{n_late:,}")
            s2.metric("Early / On-Time",      f"{n_early:,}")
            s3.metric("Median Delay (Late)",  f"{med_late:.1f} days" if not pd.isna(med_late)  else "N/A")
            s4.metric("Median Early (Early)", f"{med_early:.1f} days" if not pd.isna(med_early) else "N/A")
