import duckdb
from pathlib import Path

PARQUET = Path(__file__).parent.parent / "data" / "parquet"

_con = None


def get_con():
    global _con
    if _con is None:
        _con = duckdb.connect()
        for f in PARQUET.glob("*.parquet"):
            _con.execute(f"CREATE VIEW {f.stem} AS SELECT * FROM '{f}'")
    return _con


def build_where(filters: dict) -> str:
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


def query(sql: str):
    return get_con().execute(sql).df()
