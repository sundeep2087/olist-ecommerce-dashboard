import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import db
from components.filters import init_filter_defaults, get_filter_dict, render_filters
from components.maps import arc_flow_map

st.set_page_config(
    page_title="Seller → Customer Flow · Olist",
    page_icon="🔀",
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
    font-weight: 600 !important; font-size: 0.78rem !important;
    text-transform: uppercase !important; letter-spacing: 0.08em !important;
    color: #7aa3c8 !important;
}
[data-testid="stMetricValue"] { font-size: 1.75rem !important; font-weight: 700 !important; }
</style>
""", unsafe_allow_html=True)

# ── Filter state ──────────────────────────────────────────────────────────────
init_filter_defaults()
st.session_state.setdefault("filters_open",       True)
st.session_state.setdefault("flow_seller_states", [])
st.session_state.setdefault("flow_min_orders",    50)

filters       = get_filter_dict()
seller_states = st.session_state["flow_seller_states"]
min_flow      = st.session_state["flow_min_orders"]

# ── Build WHERE clause (global + seller-state extension) ──────────────────────
where = db.build_where(filters)
if seller_states:
    vals = ", ".join(f"'{s}'" for s in seller_states)
    seller_clause = f"seller_state IN ({vals})"
    where = f"{where} AND {seller_clause}" if where else f"WHERE {seller_clause}"

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    '<h1 style="margin-bottom:0">'
    '<i class="fa-solid fa-right-left" style="color:#4da6d8;margin-right:0.4em"></i>'
    'Seller → Customer Flow Map'
    '</h1>',
    unsafe_allow_html=True,
)
cap_col, tog_col = st.columns([8, 2])
with cap_col:
    st.caption("Which seller states supply which customer states — and at what volume?")
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
            st.markdown("**Flow Filters**")

            @st.cache_data(show_spinner=False)
            def _seller_state_options() -> list:
                return db.query(
                    "SELECT DISTINCT seller_state FROM orders_enriched "
                    "WHERE seller_state IS NOT NULL ORDER BY 1"
                )["seller_state"].tolist()

            st.multiselect(
                "Seller State",
                options=_seller_state_options(),
                key="flow_seller_states",
                placeholder="All seller states",
            )
            st.slider(
                "Min orders per route",
                min_value=1, max_value=500, step=10,
                key="flow_min_orders",
                help="Routes with fewer orders than this are hidden from the arc map.",
            )
else:
    content_col = st.container()

# ── Main content ──────────────────────────────────────────────────────────────
with content_col:
    # ── Metric toggle ─────────────────────────────────────────────────────────
    ctrl_col, _ = st.columns([5, 5])
    with ctrl_col:
        metric_label = st.segmented_control(
            "Color arcs by",
            options=["Order Count", "GMV", "Avg Delay Days"],
            default="Order Count",
            key="flow_metric",
        )
    if metric_label is None:
        metric_label = "Order Count"

    METRIC_MAP = {
        "Order Count":    ("order_count",    "Orders",         "teal"),
        "GMV":            ("gmv",            "GMV (R$)",       "orange"),
        "Avg Delay Days": ("avg_delay_days", "Avg Delay Days", "delay"),
    }
    metric_col, metric_display, color_scheme = METRIC_MAP[metric_label]

    # ── Flow query ────────────────────────────────────────────────────────────
    flow_df = db.query(f"""
        SELECT
            seller_state,
            customer_state,
            AVG(seller_lat)                  AS seller_lat,
            AVG(seller_lng)                  AS seller_lng,
            AVG(customer_lat)                AS customer_lat,
            AVG(customer_lng)                AS customer_lng,
            COUNT(DISTINCT order_id)         AS order_count,
            SUM(total_item_value)            AS gmv,
            AVG(delay_days)                  AS avg_delay_days,
            AVG(seller_customer_distance_km) AS avg_distance_km
        FROM orders_enriched
        {where}
        GROUP BY seller_state, customer_state
        HAVING COUNT(DISTINCT order_id) >= {min_flow}
    """)

    if flow_df.empty:
        st.warning(
            "No flow data for the current filters. "
            "Try lowering **Min orders per route** or broadening the date range."
        )
        st.stop()

    # ── KPI cards ─────────────────────────────────────────────────────────────
    cross_df = flow_df[flow_df["seller_state"] != flow_df["customer_state"]]
    n_routes   = len(cross_df)
    total_gmv  = flow_df["gmv"].sum()
    top_seller = flow_df.groupby("seller_state")["order_count"].sum().idxmax()
    top_buyer  = flow_df.groupby("customer_state")["order_count"].sum().idxmax()

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Cross-State Routes", f"{n_routes:,}")
    kpi2.metric("Total GMV",          f"R$ {total_gmv:,.0f}")
    kpi3.metric("Top Seller State",   top_seller)
    kpi4.metric("Top Buyer State",    top_buyer)

    st.divider()

    # ── Arc map ───────────────────────────────────────────────────────────────
    deck = arc_flow_map(flow_df, metric_col, metric_display, color_scheme)
    st.pydeck_chart(deck, height=540)

    color_legend = {
        "Order Count":    "teal  — brighter = more orders",
        "GMV":            "amber — brighter = higher GMV",
        "Avg Delay Days": "blue → red — red = more delayed",
    }
    st.caption(
        f"Arc **width** = order volume · Arc **color** = {color_legend[metric_label]} "
        f"(dim end = seller state · bright end = customer state) · "
        f"{n_routes:,} cross-state routes shown"
    )

    st.divider()

    # ── Flow matrix heatmap ───────────────────────────────────────────────────
    st.subheader("Flow Matrix — Orders by Seller × Customer State")
    st.caption("All routes shown (ignores minimum order threshold above).")

    heatmap_df = db.query(f"""
        SELECT
            seller_state,
            customer_state,
            COUNT(DISTINCT order_id) AS order_count
        FROM orders_enriched
        {where}
        GROUP BY seller_state, customer_state
    """)

    pivot = heatmap_df.pivot_table(
        index="seller_state", columns="customer_state",
        values="order_count", fill_value=0,
    )

    fig_hm = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale=[
            [0.00, "#0e1117"], [0.05, "#003838"],
            [0.30, "#007766"], [0.70, "#00bb99"],
            [1.00, "#00ddc0"],
        ],
        hovertemplate=(
            "<b>Seller: %{y} → Buyer: %{x}</b><br>"
            "Orders: %{z:,}<extra></extra>"
        ),
        colorbar=dict(
            title=dict(text="Orders", side="right", font=dict(color="#e8eaf0")),
            tickfont=dict(color="#e8eaf0"),
            thickness=14, len=0.55,
        ),
    ))

    n_states = max(len(pivot.index), len(pivot.columns))
    fig_hm.update_layout(
        height=max(480, n_states * 26 + 80),
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#e8eaf0"),
        xaxis=dict(title="Customer State", tickfont=dict(size=11), side="bottom"),
        yaxis=dict(title="Seller State",   tickfont=dict(size=11), autorange="reversed"),
        margin=dict(t=10, b=50, l=60, r=10),
    )
    st.plotly_chart(fig_hm)

    st.divider()

    # ── Top routes table ──────────────────────────────────────────────────────
    st.subheader("Top 20 Routes by Order Volume")
    top_routes = (
        cross_df
        .nlargest(20, "order_count")
        [["seller_state", "customer_state", "order_count", "gmv",
          "avg_delay_days", "avg_distance_km"]]
        .copy()
    )
    top_routes["gmv"] = top_routes["gmv"].apply(lambda x: f"R$ {x:,.0f}")
    top_routes["avg_delay_days"] = top_routes["avg_delay_days"].apply(
        lambda x: f"{x:.1f}" if pd.notna(x) else "N/A"
    )
    top_routes["avg_distance_km"] = top_routes["avg_distance_km"].apply(
        lambda x: f"{x:,.0f}" if pd.notna(x) else "N/A"
    )
    top_routes.rename(columns={
        "seller_state":    "Seller",
        "customer_state":  "Buyer",
        "order_count":     "Orders",
        "gmv":             "GMV (R$)",
        "avg_delay_days":  "Avg Delay (days)",
        "avg_distance_km": "Avg Distance (km)",
    }, inplace=True)
    st.dataframe(top_routes, hide_index=True)
