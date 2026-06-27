"""
Run: python scripts/prepare_data.py
Reads:  ../data/cleaned/*.csv
Writes: data/parquet/*.parquet
"""

import pandas as pd
import numpy as np
import duckdb
from pathlib import Path

_HERE = Path(__file__).resolve().parent        # scripts/
_ROOT = _HERE.parent                           # olist_geospatial_analysis/
CLEANED = _ROOT.parent / "data" / "cleaned"   # ../data/cleaned/
PARQUET = _ROOT / "data" / "parquet"
PARQUET.mkdir(parents=True, exist_ok=True)

ZIP_COLS = [
    "customer_zip_code_prefix",
    "seller_zip_code_prefix",
    "geolocation_zip_code_prefix",
]


def _fmt_zip(s: pd.Series) -> pd.Series:
    return s.astype(str).str.zfill(5)


def step1_csv_to_parquet() -> None:
    timestamp_cols = {
        "orders": [
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
        "order_items": ["shipping_limit_date"],
        "order_reviews": ["review_creation_date", "review_answer_timestamp"],
    }

    tables = [
        "customers", "geolocation", "order_items", "order_payments",
        "order_reviews", "orders", "products", "sellers", "category_translation",
    ]

    for name in tables:
        df = pd.read_csv(CLEANED / f"{name}.csv", low_memory=False)

        # zip code zero-padding
        for col in ZIP_COLS:
            if col in df.columns:
                df[col] = _fmt_zip(df[col])

        # timestamp parsing
        for col in timestamp_cols.get(name, []):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")

        # per-table dtype fixes
        if name == "order_payments":
            df["payment_installments"] = df["payment_installments"].astype("Int32")
        if name == "order_reviews":
            df["review_score"] = df["review_score"].astype("Int8")
        if name == "products":
            df["product_category_name"] = df["product_category_name"].where(
                df["product_category_name"].notna(), other=None
            )

        out = PARQUET / f"{name}.parquet"
        df.to_parquet(out, index=False, engine="pyarrow")
        print(f"  {name}.parquet — {len(df):,} rows  {out.stat().st_size // 1024} KB")


def step2_geo_centroids(con: duckdb.DuckDBPyConnection) -> None:
    geo = pd.read_parquet(PARQUET / "geolocation.parquet")
    con.register("geolocation", geo)

    result = con.execute("""
        SELECT
            geolocation_zip_code_prefix  AS zip,
            AVG(geolocation_lat)         AS lat,
            AVG(geolocation_lng)         AS lng,
            MODE(geolocation_city)       AS city,
            MODE(geolocation_state)      AS state
        FROM geolocation
        GROUP BY geolocation_zip_code_prefix
    """).df()

    out = PARQUET / "geo_centroids.parquet"
    result.to_parquet(out, index=False, engine="pyarrow")
    print(f"  geo_centroids.parquet — {len(result):,} rows  {out.stat().st_size // 1024} KB")


def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lng2 - lng1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def step3_orders_enriched(con: duckdb.DuckDBPyConnection) -> None:
    for name in [
        "order_items", "orders", "customers", "sellers",
        "products", "category_translation", "order_reviews", "order_payments",
    ]:
        df = pd.read_parquet(PARQUET / f"{name}.parquet")
        con.register(name, df)

    centroids = pd.read_parquet(PARQUET / "geo_centroids.parquet")
    con.register("geo_centroids", centroids)

    enriched = con.execute("""
        SELECT
            oi.order_id,
            oi.order_item_id,
            oi.product_id,
            oi.seller_id,
            o.customer_id,
            c.customer_unique_id,
            o.order_status,
            o.order_purchase_timestamp,
            o.order_approved_at,
            o.order_delivered_carrier_date,
            o.order_delivered_customer_date,
            o.order_estimated_delivery_date,
            oi.shipping_limit_date,
            CAST(oi.price AS FLOAT)          AS price,
            CAST(oi.freight_value AS FLOAT)  AS freight_value,
            p.product_category_name,
            ct.product_category_name_english,
            CAST(p.product_weight_g AS FLOAT) AS product_weight_g,
            s.seller_city,
            s.seller_state,
            CAST(sg.lat AS FLOAT)  AS seller_lat,
            CAST(sg.lng AS FLOAT)  AS seller_lng,
            c.customer_city,
            c.customer_state,
            CAST(cg.lat AS FLOAT)  AS customer_lat,
            CAST(cg.lng AS FLOAT)  AS customer_lng,
            CAST(rev.avg_review_score AS FLOAT)  AS avg_review_score,
            CAST(rev.min_review_score AS TINYINT) AS min_review_score,
            CAST(rev.review_count     AS TINYINT) AS review_count,
            CAST(pay.total_payment    AS FLOAT)   AS total_payment,
            CAST(pay.max_installments AS TINYINT) AS max_installments,
            pay.primary_payment_type
        FROM order_items oi
        JOIN orders   o  ON oi.order_id   = o.order_id
        JOIN customers c  ON o.customer_id = c.customer_id
        JOIN sellers   s  ON oi.seller_id  = s.seller_id
        JOIN products  p  ON oi.product_id = p.product_id
        LEFT JOIN category_translation ct
               ON p.product_category_name = ct.product_category_name
        LEFT JOIN geo_centroids cg
               ON c.customer_zip_code_prefix = cg.zip
        LEFT JOIN geo_centroids sg
               ON s.seller_zip_code_prefix  = sg.zip
        LEFT JOIN (
            SELECT order_id,
                   AVG(review_score)   AS avg_review_score,
                   MIN(review_score)   AS min_review_score,
                   COUNT(*)            AS review_count
            FROM order_reviews
            GROUP BY order_id
        ) rev ON oi.order_id = rev.order_id
        LEFT JOIN (
            SELECT order_id,
                   SUM(payment_value)          AS total_payment,
                   MAX(payment_installments)   AS max_installments,
                   MODE(payment_type)          AS primary_payment_type
            FROM order_payments
            GROUP BY order_id
        ) pay ON oi.order_id = pay.order_id
    """).df()

    # derived columns
    enriched["total_item_value"] = (enriched["price"] + enriched["freight_value"]).astype("float32")
    enriched["freight_ratio"] = np.where(
        enriched["price"] > 0,
        enriched["freight_value"] / enriched["price"],
        np.nan,
    ).astype("float32")

    def _hours(a, b):
        return ((a - b).dt.total_seconds() / 3600).astype("float32")

    def _days(a, b):
        return ((a - b).dt.total_seconds() / 86400).astype("float32")

    enriched["approval_wait_hours"] = _hours(
        enriched["order_approved_at"], enriched["order_purchase_timestamp"]
    )
    enriched["carrier_wait_hours"] = _hours(
        enriched["order_delivered_carrier_date"], enriched["order_approved_at"]
    )
    enriched["transit_days"] = _days(
        enriched["order_delivered_customer_date"], enriched["order_delivered_carrier_date"]
    )
    enriched["delay_days"] = _days(
        enriched["order_delivered_customer_date"], enriched["order_estimated_delivery_date"]
    )
    enriched["is_late"] = enriched["delay_days"] > 0

    enriched["order_year_month"] = (
        enriched["order_purchase_timestamp"].dt.to_period("M").dt.to_timestamp().dt.date
    )

    # haversine distance
    mask = (
        enriched["seller_lat"].notna()
        & enriched["seller_lng"].notna()
        & enriched["customer_lat"].notna()
        & enriched["customer_lng"].notna()
    )
    enriched["seller_customer_distance_km"] = np.nan
    enriched.loc[mask, "seller_customer_distance_km"] = haversine_km(
        enriched.loc[mask, "seller_lat"].values,
        enriched.loc[mask, "seller_lng"].values,
        enriched.loc[mask, "customer_lat"].values,
        enriched.loc[mask, "customer_lng"].values,
    )
    enriched["seller_customer_distance_km"] = enriched["seller_customer_distance_km"].astype("float32")

    # categorical columns
    for col in ["order_status", "seller_state", "customer_state", "primary_payment_type"]:
        enriched[col] = enriched[col].astype("category")

    out = PARQUET / "orders_enriched.parquet"
    enriched.to_parquet(out, index=False, engine="pyarrow")
    print(f"  orders_enriched.parquet — {len(enriched):,} rows  {out.stat().st_size // 1024} KB")


def step4_aggregations(con: duckdb.DuckDBPyConnection) -> None:
    enriched = pd.read_parquet(PARQUET / "orders_enriched.parquet")
    con.register("orders_enriched", enriched)

    agg_state = con.execute("""
        SELECT
            customer_state,
            order_year_month,
            COUNT(DISTINCT order_id)           AS order_count,
            COUNT(DISTINCT customer_unique_id) AS unique_customers,
            SUM(total_item_value)              AS gmv,
            AVG(delay_days)                    AS avg_delay_days,
            SUM(CAST(is_late AS INT)) / COUNT(*) AS late_rate,
            AVG(avg_review_score)              AS avg_review_score
        FROM orders_enriched
        GROUP BY customer_state, order_year_month
    """).df()
    out = PARQUET / "agg_state_monthly.parquet"
    agg_state.to_parquet(out, index=False, engine="pyarrow")
    print(f"  agg_state_monthly.parquet — {len(agg_state):,} rows  {out.stat().st_size // 1024} KB")

    agg_cat = con.execute("""
        SELECT
            product_category_name_english        AS category,
            COUNT(DISTINCT order_id)             AS order_count,
            SUM(total_item_value)                AS gmv,
            AVG(price)                           AS avg_price,
            AVG(freight_ratio)                   AS avg_freight_ratio,
            AVG(avg_review_score)                AS avg_review_score,
            SUM(CAST(is_late AS INT)) / COUNT(*) AS late_rate,
            AVG(transit_days)                    AS avg_transit_days
        FROM orders_enriched
        WHERE product_category_name_english IS NOT NULL
        GROUP BY product_category_name_english
    """).df()
    out = PARQUET / "agg_category.parquet"
    agg_cat.to_parquet(out, index=False, engine="pyarrow")
    print(f"  agg_category.parquet — {len(agg_cat):,} rows  {out.stat().st_size // 1024} KB")

    agg_seller = con.execute("""
        SELECT
            seller_id,
            seller_city,
            seller_state,
            seller_lat,
            seller_lng,
            COUNT(DISTINCT order_id)                         AS order_count,
            SUM(total_item_value)                            AS gmv,
            AVG(avg_review_score)                            AS avg_review_score,
            SUM(CAST(is_late AS INT)) / COUNT(*)             AS late_rate,
            AVG(approval_wait_hours)                         AS avg_approval_wait_hours,
            COUNT(DISTINCT product_category_name_english)    AS category_count
        FROM orders_enriched
        GROUP BY seller_id, seller_city, seller_state, seller_lat, seller_lng
    """).df()
    out = PARQUET / "agg_seller.parquet"
    agg_seller.to_parquet(out, index=False, engine="pyarrow")
    print(f"  agg_seller.parquet — {len(agg_seller):,} rows  {out.stat().st_size // 1024} KB")


def validate(con: duckdb.DuckDBPyConnection) -> None:
    enriched = pd.read_parquet(PARQUET / "orders_enriched.parquet")
    order_items = pd.read_parquet(PARQUET / "order_items.parquet")
    centroids = pd.read_parquet(PARQUET / "geo_centroids.parquet")

    assert len(enriched) == len(order_items), (
        f"Row count mismatch: enriched={len(enriched)}, order_items={len(order_items)}"
    )

    assert centroids["zip"].nunique() == len(centroids), "geo_centroids has duplicate zips"

    dist_non_null = enriched["seller_customer_distance_km"].notna().mean()
    assert dist_non_null > 0.95, (
        f"seller_customer_distance_km has only {dist_non_null:.1%} non-null (expected >95%)"
    )

    late_count = (enriched["delay_days"] > 0).sum()
    assert 7000 <= late_count <= 9000, (
        f"delay_days positive count={late_count:,} outside expected range [7000, 9000]"
    )

    valid_statuses = {"delivered", "shipped", "canceled", "unavailable", "processing",
                      "invoiced", "created", "approved"}
    actual = set(enriched["order_status"].cat.categories)
    unknown = actual - valid_statuses
    assert not unknown, f"Unexpected order_status values: {unknown}"

    print("  All validation checks passed.")


if __name__ == "__main__":
    con = duckdb.connect()

    print("Step 1 — CSV → Parquet")
    step1_csv_to_parquet()

    print("Step 2 — geo_centroids")
    step2_geo_centroids(con)

    print("Step 3 — orders_enriched")
    step3_orders_enriched(con)

    print("Step 4 — aggregations")
    step4_aggregations(con)

    print("Validating…")
    validate(con)

    print("\nDone. All Parquet files written to data/parquet/")
