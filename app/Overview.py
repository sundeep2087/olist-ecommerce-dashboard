import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import db
from components.filters import init_filter_defaults, get_filter_dict, render_filters
import plotly.express as px
from components.charts import line_chart

st.set_page_config(
    page_title="Olist Geospatial Analytics",
    page_icon="🛒",
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
    '<i class="fa-solid fa-cart-shopping" style="color:#4da6d8;margin-right:0.4em"></i>'
    'Olist E-Commerce Analytics'
    '</h1>',
    unsafe_allow_html=True,
)
cap_col, tog_col = st.columns([8, 2])
with cap_col:
    st.caption("Brazilian marketplace data · Sep 2016 – Sep 2018")
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
            COUNT(DISTINCT order_id)                            AS total_orders,
            SUM(total_item_value)                               AS total_gmv,
            AVG(avg_review_score)                               AS avg_review_score,
            SUM(is_late::int) * 100.0 / COUNT(*)               AS late_delivery_pct
        FROM orders_enriched
        {where}
    """)

    col1, col2, col3, col4 = st.columns(4)

    total_orders = int(kpi_df["total_orders"].iloc[0] or 0)
    total_gmv    = float(kpi_df["total_gmv"].iloc[0] or 0)
    avg_review   = float(kpi_df["avg_review_score"].iloc[0] or 0)
    late_pct     = float(kpi_df["late_delivery_pct"].iloc[0] or 0)

    col1.metric("📦  Total Orders",       f"{total_orders:,}")
    col2.metric("💰  Total GMV",          f"R$ {total_gmv:,.0f}")
    col3.metric("⭐  Avg Review Score",   f"{avg_review:.2f} / 5")
    col4.metric("🚚  Late Delivery Rate", f"{late_pct:.1f}%")

    st.divider()

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        monthly_df = db.query(f"""
            SELECT
                DATE_TRUNC('month', order_purchase_timestamp)::DATE AS month,
                COUNT(DISTINCT order_id)                            AS orders
            FROM orders_enriched
            {where}
            GROUP BY 1
            ORDER BY 1
        """)
        monthly_df["month"] = monthly_df["month"].astype(str)
        fig_monthly = line_chart(
            monthly_df, x="month", y="orders",
            title="Monthly Order Volume",
            line_color="#4da6d8",
        )
        fig_monthly.update_xaxes(title_text="Month", tickangle=-30)
        fig_monthly.update_yaxes(title_text="Orders")
        st.plotly_chart(fig_monthly)

    with chart_col2:
        top_states_df = db.query(f"""
            SELECT
                customer_state,
                SUM(total_item_value) AS gmv
            FROM orders_enriched
            {where}
            GROUP BY customer_state
            ORDER BY gmv DESC
            LIMIT 5
        """)
        fig_states = px.bar(
            top_states_df,
            x="customer_state",
            y="gmv",
            title="Top 5 States by GMV",
            text="gmv",
            color="gmv",
            color_continuous_scale=[[0, "#8b4000"], [0.5, "#cc6600"], [1, "#ffaa20"]],
            template="plotly_dark",
        )
        fig_states.update_traces(
            texttemplate="R$ %{text:,.0f}",
            textposition="outside",
            textfont=dict(color="#e8eaf0", size=11),
        )
        fig_states.update_layout(
            coloraxis_showscale=False,
            xaxis_title="State",
            yaxis_title="GMV (R$)",
            margin=dict(t=40, b=0, l=0, r=0),
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            font=dict(color="#e8eaf0"),
        )
        fig_states.update_yaxes(tickformat="~s")
        st.plotly_chart(fig_states)
