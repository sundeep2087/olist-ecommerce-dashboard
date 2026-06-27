# Olist E-Commerce Analytics Dashboard

An interactive Streamlit dashboard for exploring the [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) — a real-world marketplace dataset covering **112,650 orders** placed between **September 2016 and September 2018**.

The dashboard is organized into thematic pages, each answering a distinct business question through maps, charts, and filterable tables. All visualizations respond to a shared global filter sidebar (date range, customer state, product category, order status, minimum order value).

**Live app:** [https://olist-ecommerce-dashboard-d6jsxugfmgplt4znvjlxkb.streamlit.app/](https://olist-ecommerce-dashboard-d6jsxugfmgplt4znvjlxkb.streamlit.app/)

---

## Pages

| # | Page | Business Question |
|---|------|------------------|
| 0 | **Overview** | What does the filtered dataset look like at a glance? |
| 1 | **Geographic Revenue & Order Density** | Where is money coming from, and which states are underserved? |
| 2 | **Seller → Customer Flow Map** | Which seller states supply which customer states, at what volume? |
| 3 | **Delivery Performance** | Where are late deliveries happening, and what is the bottleneck? |
| 4 | **Category Scorecard** | Which categories drive revenue, which have quality problems? |
| 5 | **Seller Performance Ranking** | Who are the top sellers, and which have quality or lateness issues? |
| 6 | **Payment Behavior & Installment Analysis** | How do customers pay, and does installment depth correlate with order value or review score? |
| 7 | Customer Cohorts *(planned)* | Are customers coming back? Which cohorts retained best? |
| 8 | Review Score Drivers *(planned)* | What operational factors most strongly predict a bad review? |
| 9 | Order Funnel *(planned)* | Where do orders get stuck in the lifecycle? |

### Page highlights

**Page 1 — Geographic Revenue**
Plotly choropleth of all 27 Brazilian states colored by GMV, order count, unique customers, or avg review score. Click a state on the map to drill down into a city-level scatter bubble view with the state boundary outlined.

**Page 2 — Seller → Customer Flow**
PyDeck `ArcLayer` connecting seller state centroids to customer state centroids. Arc width encodes order volume; arc color encodes the selected metric (order count / GMV / avg delay). Below: a 23×27 flow matrix heatmap.

**Page 3 — Delivery Performance**
Three tabs: a delivery delay scatter map (blue = early, red = late), a stacked lifecycle stage bar chart (order→approval / approval→carrier / carrier→delivery), and a histogram of raw delay days for the filtered dataset.

**Page 4 — Category Scorecard**
Color-coded sortable table (green/yellow/red for review score; red flags for late rate > 10% and freight ratio > 0.30). Below: a quality-vs-lateness bubble chart (X = avg review score, Y = late rate, size = GMV, color = freight ratio) with quadrant lines at review = 4.0 and late rate = 10%.

**Page 5 — Seller Performance Ranking**
Side-by-side: a scatter plot (X = avg review score, Y = late rate, size = GMV) where clicking a bubble spotlights that seller in the leaderboard table below via `st.session_state`; and a PyDeck map of all seller locations colored green-to-red by review score. Extra sidebar filters: seller state multiselect and a minimum-order-count slider (default 10, covers 1,271 of 3,095 sellers). Leaderboard table has per-row highlight for the selected seller and per-cell color coding for review score and late rate.

**Page 6 — Payment Behavior & Installment Analysis**
Two-column layout with three charts. Left: a stacked 100% bar showing payment method split across five order-value tiers (`<R$50` → `R$1000+`) — credit card dominates every tier but rises at higher price points. Right column stacks: (1) a monthly line chart of average credit-card installment count (peaked at ~3.9 in Oct 2016, settled to ~2.8–3.0 by 2018); and (2) a box plot of review score distribution by installment bucket (1 / 2–3 / 4–6 / 7–12 / 12+), one data point per distinct order, showing means declining from 4.08 at single-installment to 3.59 for 12+ installments. Bottom: payment type breakdown table (GMV, avg installments, avg review per type) and installment bucket summary (orders, avg review, late rate).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Dashboard framework | [Streamlit](https://streamlit.io) ≥ 1.35 |
| In-process query engine | [DuckDB](https://duckdb.org) 1.5.3 |
| Data format | Apache Parquet (via PyArrow) |
| Maps | [PyDeck](https://deckgl.readthedocs.io) (arc / scatter layers) + Plotly Mapbox (choropleth) |
| Charts | [Plotly](https://plotly.com/python) ≥ 5.20 |
| Data wrangling | pandas 3.x, NumPy |
| Python | 3.14 (managed via pipenv) |

---

## Project Structure

```
olist_geospatial_analysis/
├── app/
│   ├── Overview.py              # Entry point — Page 0: KPI landing
│   ├── db.py                    # DuckDB singleton + build_where()
│   ├── components/
│   │   ├── __init__.py
│   │   ├── filters.py           # Global sidebar filters → filter dict
│   │   ├── maps.py              # PyDeck layer builders (choropleth, arc, scatter)
│   │   └── charts.py            # Plotly figure builders (bar, line, box, heatmap, funnel)
│   └── pages/
│       ├── 01_Geo_Revenue.py
│       ├── 02_Seller_Customer_Flow.py
│       ├── 03_Delivery_Performance.py
│       ├── 04_Category_Scorecard.py
│       ├── 05_Seller_Performance.py
│       └── 06_Payment_Analysis.py
├── data/
│   ├── geojson/
│   │   └── brazil_states.geojson   # State boundary polygons (properties.uf = state code)
│   └── parquet/                    # All DuckDB query targets (auto-registered as views)
│       ├── orders_enriched.parquet # Primary fact table — 112,650 rows
│       ├── geo_centroids.parquet   # Median lat/lng per zip code
│       ├── agg_category.parquet    # Pre-aggregated category stats (unfiltered)
│       ├── agg_seller.parquet
│       ├── agg_state_monthly.parquet
│       └── ...                     # Raw tables (orders, customers, sellers, etc.)
├── scripts/
│   ├── prepare_data.py          # Full ETL: raw CSVs → Parquet + orders_enriched
│   └── download_geodata.py      # Downloads brazil_states.geojson
├── .streamlit/
│   └── config.toml              # Dark theme config — do not delete
├── APP_SPEC.md                  # Full 10-page dashboard specification
├── CLAUDE.md                    # AI assistant context file
└── README.md                    # This file
```

---

## Setup

### Prerequisites

- Python 3.14
- [pipenv](https://pipenv.pypa.io/en/latest/) — install with `pip install pipenv`
- The raw Olist CSV files (see [Data](#data) below)

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd olist_geospatial_analysis
pipenv install
```

> **Note (current layout):** The `Pipfile` currently lives one level up at the repo root
> (`olist_spark_portfolio/`), shared with PySpark pipeline scripts. When this app is
> extracted into its own repo, move or recreate the `Pipfile` here. The relevant
> packages are listed in [requirements](#requirements) below.

### 2. Obtain the raw data

Download the Olist dataset from Kaggle:
[https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)

Place the extracted CSV files into:
```
data/cleaned/
├── olist_customers_dataset.csv
├── olist_geolocation_dataset.csv
├── olist_order_items_dataset.csv
├── olist_order_payments_dataset.csv
├── olist_order_reviews_dataset.csv
├── olist_orders_dataset.csv
├── olist_products_dataset.csv
├── olist_sellers_dataset.csv
└── product_category_name_translation.csv
```

> The `data/cleaned/` directory is expected at `../data/cleaned/` relative to the
> `olist_geospatial_analysis/` folder (i.e., a sibling directory of the app folder).
> When reorganizing into a standalone repo, update `CLEANED` in `scripts/prepare_data.py`
> to point to the correct path.

### 3. Run the ETL pipeline

```bash
pipenv run python scripts/prepare_data.py
```

This runs four steps:
1. **CSV → Parquet** — type fixes, timestamp parsing, zip code zero-padding
2. **geo_centroids** — per-zip median lat/lng from the geolocation table
3. **orders_enriched** — star-schema join building the primary fact table with derived columns (`total_item_value`, `freight_ratio`, `approval_wait_hours`, `carrier_wait_hours`, `transit_days`, `delay_days`, `is_late`, `seller_customer_distance_km`)
4. **Aggregations** — `agg_state_monthly`, `agg_category`, `agg_seller`

A validation step at the end checks row counts, geocoding coverage (> 95%), and expected late-order counts. Takes ~60 seconds on a modern laptop.

### 4. Download the GeoJSON boundary file (optional)

The geographic map on Page 1 uses a GeoJSON file for Brazilian state boundaries. If it's not already in `data/geojson/`, run:

```bash
pipenv run python scripts/download_geodata.py
```

Page 1 falls back to a PyDeck scatter bubble map if the file is missing.

### 5. Run the dashboard

```bash
# Always launch via the entry point, never a page file directly
pipenv run streamlit run app/Overview.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

> Launching a page file directly (e.g., `streamlit run app/pages/01_Geo_Revenue.py`)
> breaks sidebar navigation and `sys.path` resolution. Always use `Overview.py`.

---

## Requirements

When creating a standalone `Pipfile` or `requirements.txt` for this app:

```
streamlit>=1.35
duckdb>=1.5
pandas>=2.0
pyarrow>=14
pydeck>=0.9
plotly>=5.20
numpy>=1.26
```

---

## Data Model

All pages query the `orders_enriched` Parquet file, which is registered as a DuckDB view on startup. It is a denormalized fact table joining orders, customers, sellers, products, payments, and reviews.

Key derived columns:

| Column | Description |
|--------|-------------|
| `total_item_value` | `price + freight_value` per order |
| `freight_ratio` | `freight_value / price` (NaN when price = 0) |
| `approval_wait_hours` | Hours from purchase to approval |
| `carrier_wait_hours` | Hours from approval to carrier pickup |
| `transit_days` | Days from carrier pickup to customer delivery |
| `delay_days` | Actual delivery vs. estimated date (positive = late) |
| `is_late` | Boolean: `delay_days > 0` |
| `seller_customer_distance_km` | Haversine distance between seller and customer centroids |
| `avg_review_score` | Average review score for the order |
| `primary_payment_type` | Dominant payment method on the order |
| `max_installments` | Maximum installment count across payments |

The dataset covers **98,666 orders**, **99,441 customers**, **3,095 sellers**, and **73 product categories** over the Sep 2016 – Sep 2018 period. `orders_enriched` has 112,650 rows because orders with multiple items produce multiple rows (one per item).

---

## Global Filters

Every page has a collapsible right-side filter panel rendered via `components/filters.py`. The left sidebar is navigation-only. The filter panel can be toggled open or closed with the **Filters** toggle in the page header.

| Filter | Widget | Column |
|--------|--------|--------|
| Date range | `st.date_input` | `order_purchase_timestamp` |
| Customer state | `st.multiselect` | `customer_state` |
| Product category | `st.multiselect` | `product_category_name_english` |
| Order status | `st.multiselect` | `order_status` |
| Min order value | `st.number_input` | `total_item_value` |

Pages 2 and 5 add page-specific filters below the global ones (seller state multiselect and min orders slider). Page 6 uses only the global filters. Filter values persist across page navigations and panel collapse/expand via `st.session_state`.

All filters are passed as a dict to `db.build_where()`, which returns a `WHERE` clause string appended to every query. Empty lists mean no filter applied.

---

## Theme

The app uses a custom dark theme defined in `.streamlit/config.toml`:

| Token | Value |
|-------|-------|
| Background | `#0e1117` |
| Secondary background | `#1a1f2e` |
| Primary accent | `#4da6d8` (steel blue) |
| Text | `#e8eaf0` |

All Plotly figures use `template="plotly_dark"` with `paper_bgcolor="#0e1117"`.

---

## Development Notes

- **Importing project modules in pages:** each page file adds its parent (`app/`) to `sys.path` via `sys.path.insert(0, str(Path(__file__).parent.parent))` before any project imports. This makes `import db` and `from components.xxx import yyy` work regardless of working directory.
- **Metric toggles:** use `st.segmented_control`, not `st.radio`.
- **`use_container_width` is deprecated** in modern Streamlit — charts stretch to fill containers by default. Do not add it to new code.
- **DuckDB connection:** a singleton per Streamlit worker, created in `db.get_con()`. All Parquet files in `data/parquet/` are auto-registered as views using their filename stem.

---

## Contributing

Contributions are welcome! This project has three pages still to be built (see the Pages table above) and plenty of room for improvements to existing ones.

**Ways to contribute:**

- **Build a missing page** — Pages 7 (Customer Cohorts), 8 (Review Score Drivers), and 9 (Order Funnel) are fully specced in [`APP_SPEC.md`](APP_SPEC.md). Pick one and open a PR.
- **Improve an existing page** — better chart types, additional metrics, UX polish, or performance optimisations are all fair game.
- **Report a bug** — open a GitHub Issue describing what you saw, what you expected, and which page/filter combination triggered it.
- **Suggest a feature** — open a GitHub Issue with the label `enhancement`.

**Getting started:**

1. Fork the repo and clone your fork.
2. Follow the [Setup](#setup) steps to get the app running locally.
3. Create a branch: `git checkout -b feature/your-feature-name`.
4. Make your changes, test them locally with `pipenv run streamlit run app/Overview.py`.
5. Open a pull request against `main` with a short description of what changed and why.

**Code conventions to follow (from [`CLAUDE.md`](CLAUDE.md)):**

- Every new page must include the `sys.path.insert` block before any project imports.
- Use `st.segmented_control` (not `st.radio`) for metric toggles.
- All Plotly figures must use `template="plotly_dark"` with `paper_bgcolor="#0e1117"`.
- Do not add `use_container_width=True` — charts fill their container by default.
- Follow the right-panel filter architecture already used by every existing page.

---

## Dataset Citation

Olist, & André Sionek. (2018). *Brazilian E-Commerce Public Dataset by Olist* [Data set]. Kaggle. [https://doi.org/10.34740/KAGGLE/DSV/195341](https://doi.org/10.34740/KAGGLE/DSV/195341)
