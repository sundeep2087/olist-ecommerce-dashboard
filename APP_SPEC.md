# Streamlit App Spec

## Entry Point & Navigation

`app/main.py` — sets page config, renders a sidebar nav, and routes to the selected page.
Streamlit's native multi-page setup (`pages/` directory) handles routing automatically;
`main.py` is the landing page (summary KPI cards).

Sidebar sections:
1. **Global filters** (rendered by `components/filters.py`, applied on every page)
2. **Page navigation** (Streamlit's built-in sidebar page list)

---

## Global Filters (`app/components/filters.py`)

These filters appear on every page. They return a dict that `db.py` converts to WHERE
clauses appended to every query.

| Widget | Type | Column(s) filtered | Notes |
|---|---|---|---|
| Date range | `st.date_input` (two-sided) | `order_purchase_timestamp` | Default: full range (Sep 2016 – Oct 2018) |
| Customer state | `st.multiselect` | `customer_state` | Options from distinct values in enriched table |
| Product category | `st.multiselect` | `product_category_name_english` | Options from category_translation |
| Order status | `st.multiselect` | `order_status` | Default: all; options: delivered, shipped, canceled, etc. |
| Min order value | `st.number_input` | `total_item_value` | Default: 0 |

```python
# components/filters.py
def render_filters(con) -> dict:
    """Renders sidebar widgets. Returns filter dict for db.py."""
    ...
    return {
        "date_from": ...,
        "date_to":   ...,
        "states":    [...],   # empty list = no filter
        "categories": [...],
        "statuses":  [...],
        "min_value": ...,
    }
```

---

## DuckDB Query Layer (`app/db.py`)

Single module responsible for all database interaction.

```python
import duckdb, os
from pathlib import Path

PARQUET = Path("data/parquet")

_con = None
def get_con():
    global _con
    if _con is None:
        _con = duckdb.connect()
        # register views so SQL can reference table names directly
        for f in PARQUET.glob("*.parquet"):
            _con.execute(f"CREATE VIEW {f.stem} AS SELECT * FROM '{f}'")
    return _con

def build_where(filters: dict) -> str:
    """Converts filter dict to a SQL WHERE clause string."""
    clauses = []
    if filters.get("date_from"):
        clauses.append(f"order_purchase_timestamp >= '{filters['date_from']}'")
    if filters.get("date_to"):
        clauses.append(f"order_purchase_timestamp <= '{filters['date_to']}'")
    if filters.get("states"):
        vals = ", ".join(f"'{s}'" for s in filters["states"])
        clauses.append(f"customer_state IN ({vals})")
    if filters.get("categories"):
        vals = ", ".join(f"'{c}'" for c in filters["categories"])
        clauses.append(f"product_category_name_english IN ({vals})")
    if filters.get("statuses"):
        vals = ", ".join(f"'{s}'" for s in filters["statuses"])
        clauses.append(f"order_status IN ({vals})")
    if filters.get("min_value", 0) > 0:
        clauses.append(f"total_item_value >= {filters['min_value']}")
    return "WHERE " + " AND ".join(clauses) if clauses else ""

def query(sql: str) -> "pd.DataFrame":
    return get_con().execute(sql).df()
```

Every page builds its SQL like:
```python
where = build_where(filters)
df = db.query(f"SELECT ... FROM orders_enriched {where} GROUP BY ...")
```

---

## Pages

### Page 0 — Landing / KPI Summary (`main.py`)

**Purpose:** Give a snapshot of the filtered dataset before the user drills into any view.

**Layout:** Four KPI metric cards across the top, then two mini-charts side by side.

**KPIs:**
- Total Orders (distinct `order_id`)
- Total GMV (`SUM(total_item_value)`)
- Average Review Score (`AVG(avg_review_score)`)
- Late Delivery Rate (`SUM(is_late) / COUNT(*)`)

**Mini-charts:**
- Left: Monthly order volume line chart (orders per month over the date range)
- Right: Top 5 states by GMV — horizontal bar chart

**Query source:** `orders_enriched` with full filter WHERE clause applied.

---

### Page 1 — Geographic Revenue & Order Density (`pages/01_geo_revenue.py`)

**Question answered:** Where is money coming from, and which states are underserved?

**Map type:** PyDeck `GeoJsonLayer` choropleth on Brazilian states, colored by the
selected metric. Falls back to a bubble map if a GeoJSON boundary file is not available
(use `ScatterplotLayer` with centroid lat/lng per state sized by value).

**Metric toggle** (`st.radio`): GMV / Order Count / Unique Customers / Avg Review Score

**Query:**
```sql
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
```

**Below the map:** A sorted bar chart of the same metric, state on Y-axis.

**Value:** Instantly shows SP's dominance and highlights lower-GMV northern states that
might represent growth opportunities or logistics gaps.

---

### Page 2 — Seller → Customer Flow Map (`pages/02_seller_customer_flow.py`)

**Question answered:** Which seller states supply which customer states, and at what volume?

**Map type:** PyDeck `ArcLayer`. Each arc connects the seller state centroid to the
customer state centroid. Arc width encodes order count; color encodes GMV or delay.

**Extra filter on this page:**
- Seller state multiselect (in addition to global customer state filter)
- Show metric toggle: Order Count / GMV / Avg Delay Days

**Query:**
```sql
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
```

**Below the map:** A matrix heatmap (seller state × customer state, colored by order count).

**Value:** Shows cross-state logistics dependency. Thick arcs from SP to every other state
confirm SP's seller concentration; arcs to the North/Northeast with high delay days point
to fulfillment gaps.

---

### Page 3 — Delivery Performance & Late Delivery Hotspots (`pages/03_delivery_performance.py`)

**Question answered:** Where are late deliveries happening, and what is the logistics
bottleneck (approval wait, carrier wait, or transit time)?

**Layout:** Three sub-tabs.

**Tab A — Delay map:**
PyDeck `ScatterplotLayer` of customer state centroids sized and colored by `avg_delay_days`.
Positive (red) = late on average; negative (blue) = consistently early.

```sql
SELECT
    customer_state,
    AVG(customer_lat)         AS lat,
    AVG(customer_lng)         AS lng,
    AVG(delay_days)           AS avg_delay_days,
    SUM(is_late::int) * 100.0 / COUNT(*) AS late_pct,
    AVG(transit_days)         AS avg_transit_days
FROM orders_enriched
{where}
GROUP BY customer_state
```

**Tab B — Stage breakdown:**
Stacked bar per state showing average days in each lifecycle stage:
`approval_wait_hours / 24`, `carrier_wait_hours / 24`, `transit_days`.

```sql
SELECT
    customer_state,
    AVG(approval_wait_hours) / 24  AS avg_days_to_approve,
    AVG(carrier_wait_hours) / 24   AS avg_days_to_pickup,
    AVG(transit_days)              AS avg_transit_days,
    AVG(delay_days)                AS avg_delay
FROM orders_enriched
{where}
GROUP BY customer_state
ORDER BY avg_delay DESC
```

**Tab C — Delay distribution:**
Plotly histogram of `delay_days` for the filtered dataset. Vertical line at 0.
Color-split: early vs. late. Known anomaly callout: 1,359 orders with carrier pickup
before approval should appear as a left-tail spike.

**Value:** Pinpoints whether late delivery is a carrier transit problem (last-mile) or
an internal approval/pickup bottleneck. Actionable for logistics partner decisions.

---

### Page 4 — Category Performance Scorecard (`pages/04_category_scorecard.py`)

**Question answered:** Which product categories drive revenue, which have quality problems,
and which are expensive to ship relative to item price?

**Layout:** Sortable table at top, scatter plot below.

**Table columns:** Category | Orders | GMV | Avg Price | Avg Freight Ratio | Avg Review Score
| Late Rate | Avg Transit Days

Color-coded cells: review score (green/yellow/red), late rate (red if >10%), freight
ratio (red if >0.3).

**Query:** Runs live against `orders_enriched` with WHERE clause (so filters apply to the
category table too — unlike the pre-aggregated `agg_category.parquet` which is unfiltered).

```sql
SELECT
    COALESCE(product_category_name_english, 'Unknown')  AS category,
    COUNT(DISTINCT order_id)                            AS order_count,
    SUM(total_item_value)                               AS gmv,
    AVG(price)                                          AS avg_price,
    AVG(freight_ratio)                                  AS avg_freight_ratio,
    AVG(avg_review_score)                               AS avg_review_score,
    SUM(is_late::int) * 100.0 / COUNT(*)                AS late_pct,
    AVG(transit_days)                                   AS avg_transit_days
FROM orders_enriched
{where}
GROUP BY category
ORDER BY gmv DESC
```

**Scatter plot:** X = avg_review_score, Y = late_pct, size = gmv, color = avg_freight_ratio.
Quadrant lines at review_score=4.0 and late_pct=10%. Categories in the bottom-left
quadrant (low review, high late rate) are the problem children.

**Value:** Connects product type to customer satisfaction and logistics cost in one view.
A category with high freight ratio signals either heavy/bulky items or long-distance shipping.

---

### Page 5 — Seller Performance Ranking (`pages/05_seller_performance.py`)

**Question answered:** Who are the top sellers, and which high-volume sellers have quality or
lateness problems?

**Layout:** Leaderboard table + scatter plot + mini map.

**Extra filter on this page:**
- Seller state multiselect
- Minimum order count slider (to filter out noise from one-off sellers)

**Leaderboard query:**
```sql
SELECT
    seller_id,
    seller_city,
    seller_state,
    seller_lat,
    seller_lng,
    COUNT(DISTINCT order_id)                  AS order_count,
    SUM(total_item_value)                     AS gmv,
    AVG(avg_review_score)                     AS avg_review_score,
    SUM(is_late::int) * 100.0 / COUNT(*)      AS late_pct,
    AVG(approval_wait_hours)                  AS avg_approval_wait_hours,
    COUNT(DISTINCT product_category_name_english) AS category_count
FROM orders_enriched
{where}
GROUP BY seller_id, seller_city, seller_state, seller_lat, seller_lng
HAVING order_count >= {min_orders}
ORDER BY gmv DESC
```

**Scatter plot:** X = avg_review_score, Y = late_pct, size = gmv. Click a point to
highlight that seller in the table (`st.session_state`).

**Mini map:** PyDeck `ScatterplotLayer` of seller locations, colored by avg_review_score
(green = high, red = low), sized by gmv.

**Value:** Separates high-volume/low-quality sellers from reliable smaller ones. A
marketplace would use this to target seller coaching or adjust their ranking algorithm.

---

### Page 6 — Payment Behavior & Installment Analysis (`pages/06_payment_analysis.py`)

**Question answered:** How do customers pay, and does installment depth correlate with
order value or geography?

**Layout:** Two columns, three charts.

**Chart 1 — Payment mix by order value tier** (stacked bar):
Bucket `total_item_value` into: <50, 50–200, 200–500, 500–1000, 1000+.
For each bucket, show the split of `primary_payment_type`.

```sql
SELECT
    CASE
        WHEN total_item_value < 50    THEN '<50'
        WHEN total_item_value < 200   THEN '50–200'
        WHEN total_item_value < 500   THEN '200–500'
        WHEN total_item_value < 1000  THEN '500–1000'
        ELSE '1000+'
    END AS value_tier,
    primary_payment_type,
    COUNT(DISTINCT order_id) AS order_count
FROM orders_enriched
{where}
GROUP BY value_tier, primary_payment_type
```

**Chart 2 — Avg installments over time** (line):
Monthly average of `max_installments` across all orders.

**Chart 3 — Installments vs. review score** (box plot):
Bucket `max_installments` (1, 2–3, 4–6, 7–12, 12+) and show review score distribution
per bucket.

**Query source for charts 2 & 3:** `orders_enriched` with WHERE clause applied.

**Value:** Credit cards dominate at 73.9% with avg 2.85 installments. High installment
counts on high-value items may correlate with repayment stress and negative reviews —
this chart either confirms or refutes that hypothesis.

---

### Page 7 — Customer Cohort & Repeat Purchase (`pages/07_customer_cohorts.py`)

**Question answered:** Are customers coming back, and which acquisition cohorts retained best?

**Layout:** Cohort retention heatmap + repeat purchase rate KPI.

**Step 1 — Tag each customer's first order month:**
```sql
WITH first_orders AS (
    SELECT
        customer_unique_id,
        DATE_TRUNC('month', MIN(order_purchase_timestamp)) AS cohort_month
    FROM orders_enriched
    {where}
    GROUP BY customer_unique_id
)
SELECT
    oe.customer_unique_id,
    fo.cohort_month,
    DATE_TRUNC('month', oe.order_purchase_timestamp) AS order_month,
    DATEDIFF('month', fo.cohort_month,
             DATE_TRUNC('month', oe.order_purchase_timestamp)) AS months_since_first
FROM orders_enriched oe
JOIN first_orders fo USING (customer_unique_id)
{additional_where_without_date_filter}
```

**Step 2 — Pivot in Python** (pandas pivot_table) into cohort × months_since_first,
with values = number of unique customers active that month. Divide by cohort size for
retention rate.

**Heatmap:** Plotly `go.Heatmap` with cohort_month on Y, months_since_first on X,
color = retention %. Known expectation: most customers appear only in month 0 (single
purchase), so retention drops sharply to near-zero after month 1. The interesting
signal is which cohorts bucked that trend.

**KPI cards above heatmap:**
- Repeat purchase rate: `customers with >1 order / total customers` (~3.5% expected)
- Avg orders per returning customer

**Value:** Confirms whether the marketplace has a loyalty problem or if single-purchase
is simply the norm for this product mix. Cohort view shows if any period (e.g. a
promotional month) drove disproportionate return visits.

---

### Page 8 — Review Score Driver Analysis (`pages/08_review_drivers.py`)

**Question answered:** What operational factors most strongly predict a bad review?

**Layout:** Three side-by-side box plots + a summary table.

**Score buckets:** Negative (1–2), Neutral (3), Positive (4–5). Shown as color groups.

**Box plot 1 — Delay days by score bucket:**
```sql
SELECT
    CASE
        WHEN min_review_score <= 2 THEN 'Negative (1–2)'
        WHEN min_review_score = 3  THEN 'Neutral (3)'
        ELSE 'Positive (4–5)'
    END AS score_bucket,
    delay_days,
    transit_days,
    freight_ratio,
    seller_customer_distance_km
FROM orders_enriched
{where}
WHERE min_review_score IS NOT NULL
```

Render three Plotly box plots from this dataset:
- `delay_days` by score bucket
- `transit_days` by score bucket
- `freight_ratio` by score bucket

**Summary table:** For each score bucket, show: median delay, median transit days,
median freight ratio, top 3 product categories, top 3 customer states.

**Value:** Quantifies whether late delivery or high freight cost is the primary driver
of bad reviews. From EDA we know 7,827 orders were late — this view shows how strongly
lateness correlates with 1–2 star reviews vs. other factors.

---

### Page 9 — Order Funnel & Status Breakdown (`pages/09_order_funnel.py`)

**Question answered:** Where do orders get stuck in the lifecycle, and what does the
non-delivered tail look like?

**Layout:** Funnel chart + status donut + stage duration table.

**Funnel chart:** Count of orders reaching each milestone:
- Placed (all orders in filtered set)
- Approved (`order_approved_at IS NOT NULL`)
- Carrier pickup (`order_delivered_carrier_date IS NOT NULL`)
- Delivered to customer (`order_delivered_customer_date IS NOT NULL`)

```sql
SELECT
    COUNT(DISTINCT order_id)                                                         AS placed,
    COUNT(DISTINCT CASE WHEN order_approved_at IS NOT NULL      THEN order_id END)  AS approved,
    COUNT(DISTINCT CASE WHEN order_delivered_carrier_date IS NOT NULL THEN order_id END) AS carrier_pickup,
    COUNT(DISTINCT CASE WHEN order_delivered_customer_date IS NOT NULL THEN order_id END) AS delivered
FROM orders_enriched
{where}
```

Render as Plotly `go.Funnel`.

**Status donut:** Distribution of `order_status` values for the filtered set (97%
"delivered" normally, but filtering by state or date may surface more cancellations).

**Stage duration table:** For each order status, show median hours in each stage
(purchase→approval, approval→carrier, carrier→customer).

**Value:** The 160 orders with null `order_approved_at` and 775 originally with no line
items surface here as funnel drop-offs. Filtering to a specific state might reveal that
certain regions have higher cancellation rates or longer approval waits.

---

## Shared Components

### `components/maps.py`

Reusable PyDeck layer builder functions:

```python
def state_bubble_layer(df, metric_col, color_scheme="blue-red"): ...
def arc_layer(df, ...): ...
def scatter_layer(df, lat_col, lng_col, size_col, color_col): ...
```

### `components/charts.py`

Reusable Plotly figure builders:

```python
def bar_chart(df, x, y, title, color=None, horizontal=False): ...
def line_chart(df, x, y, title, color=None): ...
def box_plot(df, x, y, title, color=None): ...
def heatmap(df, x, y, z, title): ...
def funnel(stages: dict, title): ...
```

---

## `requirements.txt`

```
streamlit>=1.35
duckdb>=0.10
pandas>=2.0
pyarrow>=14
pydeck>=0.9
plotly>=5.20
numpy>=1.26
```

---

## Build Order (step by step)

1. Run `scripts/prepare_data.py` — verify all Parquet files exist and pass validation checks
2. Build `app/db.py` — test with a raw DuckDB query in a Python REPL
3. Build `components/filters.py` — test that `build_where()` produces correct SQL for each filter combination
4. Build `app/main.py` — KPI cards only; confirm the app launches with `streamlit run app/main.py`
5. Build pages in dependency order (Page 1 → 3 → 4 → 5 → 2 → 6 → 7 → 8 → 9)
   — geo/delivery pages first because they exercise the map components
6. Build `components/maps.py` and `components/charts.py` incrementally as each page needs them
7. Final pass: test all filter combinations, confirm no SQL injection via widget values
   (use parameterized values or whitelist-validate all string inputs before interpolation)
