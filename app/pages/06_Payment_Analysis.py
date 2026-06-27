import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import plotly.express as px
import pandas as pd
import db
from components.filters import init_filter_defaults, get_filter_dict, render_filters

st.set_page_config(
    page_title="Payment Analysis · Olist",
    page_icon="💳",
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

# ── Constants ─────────────────────────────────────────────────────────────────
TIER_ORDER = ["<50", "50–200", "200–500", "500–1000", "1000+"]
BUCKET_ORDER = ["1", "2–3", "4–6", "7–12", "12+"]
PAYMENT_LABELS = {
    "credit_card": "Credit Card",
    "boleto":      "Boleto",
    "voucher":     "Voucher",
    "debit_card":  "Debit Card",
}
PAYMENT_COLORS = {
    "Credit Card": "#4da6d8",
    "Boleto":      "#f59e0b",
    "Voucher":     "#a78bfa",
    "Debit Card":  "#34d399",
}

# ── Filter state ──────────────────────────────────────────────────────────────
init_filter_defaults()
st.session_state.setdefault("filters_open", True)
filters = get_filter_dict()
where   = db.build_where(filters)

# Pre-compute conjunctions so each query can append extra conditions cleanly
_and = "AND" if where else "WHERE"
pay_ext  = f"{_and} primary_payment_type IS NOT NULL"
cc_ext   = f"{_and} max_installments > 0 AND primary_payment_type = 'credit_card'"
inst_ext = f"{_and} max_installments > 0 AND avg_review_score IS NOT NULL"

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    '<h1 style="margin-bottom:0">'
    '<i class="fa-solid fa-credit-card" style="color:#4da6d8;margin-right:0.4em"></i>'
    'Payment Behavior &amp; Installment Analysis'
    '</h1>',
    unsafe_allow_html=True,
)
cap_col, tog_col = st.columns([8, 2])
with cap_col:
    st.caption(
        "How do customers pay, and does installment depth correlate with order value or review score? "
        "Credit cards dominate at ~75 % with an average of ~2.85 installments."
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

# ── Main content ──────────────────────────────────────────────────────────────
with content_col:

    # ── KPI row ───────────────────────────────────────────────────────────────
    kpi_df = db.query(f"""
        SELECT
            COUNT(DISTINCT order_id)                                              AS total_orders,
            SUM(CASE WHEN primary_payment_type = 'credit_card' THEN 1 ELSE 0 END)
                * 100.0
                / NULLIF(SUM(CASE WHEN primary_payment_type IS NOT NULL THEN 1 ELSE 0 END), 0)
                                                                                  AS cc_pct,
            AVG(CASE WHEN max_installments > 0 THEN max_installments END)         AS avg_installments,
            SUM(CASE WHEN primary_payment_type = 'boleto' THEN 1 ELSE 0 END)
                * 100.0
                / NULLIF(SUM(CASE WHEN primary_payment_type IS NOT NULL THEN 1 ELSE 0 END), 0)
                                                                                  AS boleto_pct
        FROM orders_enriched
        {where}
    """)

    total_orders = int(kpi_df["total_orders"].iloc[0]      or 0)
    cc_pct       = float(kpi_df["cc_pct"].iloc[0]          or 0)
    avg_inst     = float(kpi_df["avg_installments"].iloc[0] or 0)
    boleto_pct   = float(kpi_df["boleto_pct"].iloc[0]      or 0)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📦  Total Orders",     f"{total_orders:,}")
    k2.metric("💳  Credit Card Rate", f"{cc_pct:.1f}%")
    k3.metric("📊  Avg Installments", f"{avg_inst:.2f}")
    k4.metric("🧾  Boleto Rate",      f"{boleto_pct:.1f}%")

    st.divider()

    # ── Two-column layout: Chart 1 left, Charts 2+3 right ────────────────────
    left_col, right_col = st.columns(2, gap="large")

    # ── Chart 1 — Payment mix by order value tier (stacked 100 % bar) ─────────
    with left_col:
        st.subheader("Payment Mix by Order Value Tier")
        st.caption(
            "Stacked bars sum to 100 % within each price tier. "
            "Hover to see raw order counts."
        )

        tier_df = db.query(f"""
            SELECT
                CASE
                    WHEN total_item_value < 50    THEN '<50'
                    WHEN total_item_value < 200   THEN '50–200'
                    WHEN total_item_value < 500   THEN '200–500'
                    WHEN total_item_value < 1000  THEN '500–1000'
                    ELSE '1000+'
                END                              AS value_tier,
                primary_payment_type,
                COUNT(DISTINCT order_id)         AS order_count
            FROM orders_enriched
            {where}
            {pay_ext}
            GROUP BY value_tier, primary_payment_type
        """)

        tier_df["payment_label"] = tier_df["primary_payment_type"].map(PAYMENT_LABELS)
        tier_df["value_tier"]    = pd.Categorical(
            tier_df["value_tier"], categories=TIER_ORDER, ordered=True
        )
        tier_df = tier_df.sort_values("value_tier")

        tier_totals      = tier_df.groupby("value_tier")["order_count"].transform("sum")
        tier_df["pct"]   = tier_df["order_count"] / tier_totals * 100

        fig_tier = px.bar(
            tier_df,
            x="value_tier",
            y="pct",
            color="payment_label",
            barmode="stack",
            color_discrete_map=PAYMENT_COLORS,
            custom_data=["order_count"],
            labels={
                "value_tier":    "Order Value Tier (R$)",
                "pct":           "Share (%)",
                "payment_label": "Payment Type",
            },
            template="plotly_dark",
        )
        fig_tier.update_traces(
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Tier: %{x}<br>"
                "Share: %{y:.1f}%<br>"
                "Orders: %{customdata[0]:,}<extra></extra>"
            ),
        )
        fig_tier.update_layout(
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            font=dict(color="#e8eaf0"),
            height=440,
            margin=dict(t=20, b=50, l=55, r=10),
            xaxis=dict(title="Order Value Tier (R$)", gridcolor="rgba(255,255,255,0.07)"),
            yaxis=dict(
                title="Share of Orders (%)",
                gridcolor="rgba(255,255,255,0.07)",
                range=[0, 100],
            ),
            legend=dict(
                title="Payment Type",
                orientation="h",
                yanchor="bottom", y=1.02,
                xanchor="right",  x=1,
            ),
        )
        st.plotly_chart(fig_tier)

    # ── Charts 2 & 3 stacked in right column ─────────────────────────────────
    with right_col:

        # Chart 2 — Avg installments over time (credit card only)
        st.subheader("Avg Installments Over Time")
        st.caption("Monthly credit-card installment depth across the dataset period.")

        monthly_df = db.query(f"""
            SELECT
                DATE_TRUNC('month', order_purchase_timestamp)::DATE AS month,
                AVG(max_installments)                               AS avg_installments,
                COUNT(DISTINCT order_id)                            AS orders
            FROM orders_enriched
            {where}
            {cc_ext}
            GROUP BY 1
            ORDER BY 1
        """)
        monthly_df["month"] = monthly_df["month"].astype(str)

        fig_line = px.line(
            monthly_df,
            x="month",
            y="avg_installments",
            markers=True,
            custom_data=["orders"],
            labels={"month": "", "avg_installments": "Avg Installments"},
            template="plotly_dark",
        )
        fig_line.update_traces(
            line=dict(color="#4da6d8", width=2.5),
            marker=dict(color="#4da6d8", size=5),
            fill="tozeroy",
            fillcolor="rgba(77,166,216,0.12)",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Avg Installments: %{y:.2f}<br>"
                "Orders: %{customdata[0]:,}<extra></extra>"
            ),
        )
        fig_line.update_layout(
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            font=dict(color="#e8eaf0"),
            height=210,
            margin=dict(t=10, b=60, l=55, r=10),
            xaxis=dict(gridcolor="rgba(255,255,255,0.07)", tickangle=-45, tickfont=dict(size=9)),
            yaxis=dict(title="Avg Installments", gridcolor="rgba(255,255,255,0.07)"),
        )
        st.plotly_chart(fig_line)

        # Chart 3 — Review score distribution by installment bucket (box plot)
        st.subheader("Review Score by Installment Count")
        st.caption(
            "One data point per distinct order. "
            "Dashed line inside box = mean. "
            "Higher installment counts correlate with slightly lower scores."
        )

        # GROUP BY order_id to get one observation per order (orders_enriched has
        # multiple rows per order when an order has multiple items)
        box_df = db.query(f"""
            SELECT
                CASE
                    WHEN MAX(max_installments) = 1    THEN '1'
                    WHEN MAX(max_installments) <= 3   THEN '2–3'
                    WHEN MAX(max_installments) <= 6   THEN '4–6'
                    WHEN MAX(max_installments) <= 12  THEN '7–12'
                    ELSE '12+'
                END                          AS installment_bucket,
                MAX(avg_review_score)        AS avg_review_score
            FROM orders_enriched
            {where}
            {inst_ext}
            GROUP BY order_id
        """)

        box_df["installment_bucket"] = pd.Categorical(
            box_df["installment_bucket"], categories=BUCKET_ORDER, ordered=True
        )

        fig_box = px.box(
            box_df,
            x="installment_bucket",
            y="avg_review_score",
            color="installment_bucket",
            color_discrete_sequence=["#4da6d8", "#68b9e8", "#82cdf5", "#a78bfa", "#c4b5fd"],
            labels={
                "installment_bucket": "Installments",
                "avg_review_score":   "Review Score",
            },
            template="plotly_dark",
        )
        fig_box.update_traces(showlegend=False, boxmean=True)
        fig_box.add_hline(
            y=4.0,
            line_dash="dash",
            line_color="rgba(232,234,240,0.35)",
            line_width=1.5,
            annotation_text="Score = 4.0",
            annotation_position="bottom right",
            annotation_font=dict(color="#7aa3c8", size=9),
        )
        fig_box.update_layout(
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            font=dict(color="#e8eaf0"),
            height=225,
            margin=dict(t=10, b=50, l=55, r=10),
            xaxis=dict(title="Installment Count", gridcolor="rgba(255,255,255,0.07)"),
            yaxis=dict(
                title="Review Score",
                gridcolor="rgba(255,255,255,0.07)",
                range=[0.5, 5.5],
            ),
        )
        st.plotly_chart(fig_box)

    st.divider()

    # ── Bottom summary tables ─────────────────────────────────────────────────
    sum_l, sum_r = st.columns(2)

    with sum_l:
        st.markdown("**Payment Type Breakdown**")

        pay_summary = db.query(f"""
            SELECT
                primary_payment_type,
                COUNT(DISTINCT order_id)                                    AS orders,
                SUM(total_item_value)                                       AS gmv,
                AVG(CASE WHEN max_installments > 0 THEN max_installments END) AS avg_installments,
                AVG(avg_review_score)                                       AS avg_review
            FROM orders_enriched
            {where}
            {pay_ext}
            GROUP BY 1
            ORDER BY orders DESC
        """)
        pay_summary["Payment Type"]     = pay_summary["primary_payment_type"].map(PAYMENT_LABELS)
        pay_summary["Orders"]           = pay_summary["orders"].astype(int)
        pay_summary["GMV (R$)"]         = pay_summary["gmv"]
        pay_summary["Avg Installments"] = pay_summary["avg_installments"]
        pay_summary["Avg Review"]       = pay_summary["avg_review"]
        pay_summary = pay_summary[
            ["Payment Type", "Orders", "GMV (R$)", "Avg Installments", "Avg Review"]
        ]
        st.dataframe(
            pay_summary,
            hide_index=True,
            column_config={
                "Orders":           st.column_config.NumberColumn(format="%d"),
                "GMV (R$)":         st.column_config.NumberColumn(format="R$ %.0f"),
                "Avg Installments": st.column_config.NumberColumn(format="%.2f"),
                "Avg Review":       st.column_config.NumberColumn(format="%.2f"),
            },
        )

    with sum_r:
        st.markdown("**Installment Bucket Summary**")

        inst_summary = db.query(f"""
            SELECT
                CASE
                    WHEN max_installments = 1    THEN '1'
                    WHEN max_installments <= 3   THEN '2–3'
                    WHEN max_installments <= 6   THEN '4–6'
                    WHEN max_installments <= 12  THEN '7–12'
                    ELSE '12+'
                END                                           AS installment_bucket,
                COUNT(DISTINCT order_id)                      AS orders,
                AVG(avg_review_score)                         AS avg_review,
                SUM(is_late::int) * 100.0 / COUNT(*)          AS late_pct
            FROM orders_enriched
            {where}
            {_and} max_installments > 0
            GROUP BY 1
        """)

        inst_summary["installment_bucket"] = pd.Categorical(
            inst_summary["installment_bucket"], categories=BUCKET_ORDER, ordered=True
        )
        inst_summary = inst_summary.sort_values("installment_bucket").rename(columns={
            "installment_bucket": "Installments",
            "orders":             "Orders",
            "avg_review":         "Avg Review",
            "late_pct":           "Late Rate (%)",
        })
        st.dataframe(
            inst_summary,
            hide_index=True,
            column_config={
                "Orders":        st.column_config.NumberColumn(format="%d"),
                "Avg Review":    st.column_config.NumberColumn(format="%.2f"),
                "Late Rate (%)": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )
