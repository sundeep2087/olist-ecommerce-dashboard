import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.express as px
import db
from components.filters import init_filter_defaults, get_filter_dict, render_filters
from components.maps import state_choropleth, city_scatter, state_bubble_map, UF_TO_NAME, SCALES

st.set_page_config(
    page_title="Geo Revenue & Density · Olist",
    page_icon="🗺️",
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
/* ── Radio buttons ───────────────────────────────────────────────────────── */
.stRadio > label { font-weight: 600 !important; font-size: 0.88rem !important; }
</style>
""", unsafe_allow_html=True)

GEOJSON_PATH = Path(__file__).parent.parent.parent / "data" / "geojson" / "brazil_states.geojson"

# ── Metric config — each metric gets its own color scheme ────────────────────
METRICS = {
    "GMV":              ("gmv",             "GMV (R$)",           "orange"),
    "Order Count":      ("order_count",     "Orders",             "teal"),
    "Unique Customers": ("unique_customers","Unique Customers",   "purple"),
    "Avg Review Score": ("avg_review_score","Avg Review Score",  "score"),
}

# ── Filter state ──────────────────────────────────────────────────────────────
init_filter_defaults()
st.session_state.setdefault("filters_open", True)
filters = get_filter_dict()
where = db.build_where(filters)

# ── Init drill-down state ─────────────────────────────────────────────────────
if "geo_selected_state" not in st.session_state:
    st.session_state.geo_selected_state = None

selected_state = st.session_state.geo_selected_state

# ── Load GeoJSON (cached) ─────────────────────────────────────────────────────
@st.cache_data
def load_geojson():
    if GEOJSON_PATH.exists():
        return json.loads(GEOJSON_PATH.read_text())
    return None

geojson = load_geojson()

# ── State-level query ─────────────────────────────────────────────────────────
state_df = db.query(f"""
    SELECT
        customer_state,
        AVG(customer_lat)                        AS lat,
        AVG(customer_lng)                        AS lng,
        COUNT(DISTINCT order_id)                 AS order_count,
        COUNT(DISTINCT customer_unique_id)       AS unique_customers,
        SUM(total_item_value)                    AS gmv,
        AVG(avg_review_score)                    AS avg_review_score
    FROM orders_enriched
    {where}
    GROUP BY customer_state
""")

if state_df.empty:
    st.warning("No data matches the current filters.")
    st.stop()

available_states = sorted(state_df["customer_state"].dropna().tolist())

# ── Header ────────────────────────────────────────────────────────────────────
if selected_state:
    st.markdown(
        '<h1 style="margin-bottom:0">'
        '<i class="fa-solid fa-earth-americas" style="color:#4da6d8;margin-right:0.4em"></i>'
        'Geographic Revenue &amp; Order Density'
        '</h1>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<h1 style="margin-bottom:0">'
        '<i class="fa-solid fa-earth-americas" style="color:#4da6d8;margin-right:0.4em"></i>'
        'Geographic Revenue &amp; Order Density'
        '</h1>',
        unsafe_allow_html=True,
    )

cap_col, tog_col = st.columns([8, 2])
with cap_col:
    st.caption("Where is the money coming from? Click a state to explore its cities.")
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
    # State/city drill-down header
    if selected_state:
        col_back, col_pick, col_name = st.columns([1, 2, 7])
        with col_back:
            if st.button("← Brazil"):
                st.session_state.geo_selected_state = None
                st.rerun()
        with col_pick:
            switched = st.selectbox(
                "State",
                options=available_states,
                index=available_states.index(selected_state) if selected_state in available_states else 0,
                key="state_switcher",
                label_visibility="collapsed",
            )
            if switched != selected_state:
                st.session_state.geo_selected_state = switched
                st.rerun()
        with col_name:
            state_name = UF_TO_NAME.get(selected_state, selected_state)
            st.markdown(
                f'<h3><i class="fa-solid fa-location-dot" style="color:#4da6d8;margin-right:0.35em"></i>'
                f'{state_name} — City View</h3>',
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Metric selector ───────────────────────────────────────────────────────
    top_ctrl, _ = st.columns([4, 6])
    with top_ctrl:
        metric_label = st.radio(
            "Metric",
            options=list(METRICS.keys()),
            horizontal=True,
            key="geo_metric",
        )

    metric_col, metric_display, color_scheme = METRICS[metric_label]
    scale = SCALES.get(color_scheme, SCALES["blue"])

    # ── Map ───────────────────────────────────────────────────────────────────
    if selected_state is None:
        if geojson:
            fig = state_choropleth(state_df, geojson, metric_col, metric_display, color_scheme)
            event = st.plotly_chart(
                fig,
                on_select="rerun",
                key="state_choropleth_map",
            )

            try:
                pts = event.selection.points if (event and event.selection) else []
                if pts:
                    clicked = pts[0].get("location") if isinstance(pts[0], dict) else getattr(pts[0], "location", None)
                    if clicked and clicked in available_states:
                        st.session_state.geo_selected_state = clicked
                        st.rerun()
            except Exception:
                pass

            col_hint, col_sel = st.columns([3, 2])
            with col_hint:
                st.caption("💡 Click a state on the map, or pick one below to explore city-level data")
            with col_sel:
                picked = st.selectbox(
                    "Or select a state →",
                    options=[""] + available_states,
                    index=0,
                    label_visibility="collapsed",
                    key="state_selector_fallback",
                )
                if picked:
                    st.session_state.geo_selected_state = picked
                    st.rerun()
        else:
            deck = state_bubble_map(state_df, metric_col, metric_display, color_scheme)
            st.pydeck_chart(deck, height=520)
            picked = st.selectbox(
                "Select a State to Explore Its Cities",
                options=[""] + available_states,
                index=0,
                key="state_selector_fallback",
            )
            if picked:
                st.session_state.geo_selected_state = picked
                st.rerun()

    else:
        state_filters = {**filters, "states": [selected_state]}
        city_where = db.build_where(state_filters)

        city_df = db.query(f"""
            SELECT
                customer_city,
                customer_state,
                AVG(customer_lat)                        AS lat,
                AVG(customer_lng)                        AS lng,
                COUNT(DISTINCT order_id)                 AS order_count,
                COUNT(DISTINCT customer_unique_id)       AS unique_customers,
                SUM(total_item_value)                    AS gmv,
                AVG(avg_review_score)                    AS avg_review_score
            FROM orders_enriched
            {city_where}
            GROUP BY customer_city, customer_state
            ORDER BY {metric_col} DESC
        """)

        if city_df.empty:
            st.info(f"No city-level data for {selected_state} with the current filters.")
        else:
            fig = city_scatter(city_df, geojson, metric_col, metric_display, selected_state, color_scheme)
            st.plotly_chart(fig)
            st.caption(
                f"Showing **{len(city_df)} cities** in {selected_state} · "
                f"Bubble size = {metric_display} · Hover for details"
            )

    st.divider()

    # ── Bar chart (adapts to view level) ─────────────────────────────────────
    if selected_state is None:
        bar_title = f"{metric_label} by State — Ranked"
        bar_df = state_df[["customer_state", metric_col]].dropna()
        y_col, y_label = "customer_state", "State"
    else:
        bar_title = f"{metric_label} by City in {selected_state} — Top 20"
        bar_df = city_df[["customer_city", metric_col]].dropna().head(20)
        y_col, y_label = "customer_city", "City"

    bar_df = bar_df.sort_values(metric_col, ascending=True)

    tickfmt = "$~s" if metric_col == "gmv" else ".2f" if metric_col == "avg_review_score" else ","
    text_tpl = (
        "R$ %{text:,.0f}" if metric_col == "gmv" else
        "%{text:.2f}"     if metric_col == "avg_review_score" else
        "%{text:,.0f}"
    )

    st.subheader(bar_title)

    fig_bar = px.bar(
        bar_df,
        x=metric_col,
        y=y_col,
        orientation="h",
        labels={metric_col: metric_display, y_col: y_label},
        color=metric_col,
        color_continuous_scale=scale,
        text=metric_col,
        template="plotly_dark",
    )
    fig_bar.update_traces(
        texttemplate=text_tpl,
        textposition="outside",
        textfont=dict(color="#e8eaf0", size=11),
    )

    max_val = bar_df[metric_col].max()
    fig_bar.update_layout(
        coloraxis_showscale=False,
        height=max(380, len(bar_df) * 22),
        margin=dict(t=10, b=0, l=0, r=10),
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font=dict(color="#e8eaf0"),
        yaxis=dict(tickfont=dict(size=12), title=None),
        xaxis=dict(range=[0, max_val * 1.35], tickformat=tickfmt, title=metric_display),
    )
    st.plotly_chart(fig_bar)
