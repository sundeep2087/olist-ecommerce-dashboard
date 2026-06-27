from datetime import date
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import db

DATE_MIN = date(2016, 9, 4)
DATE_MAX = date(2018, 9, 3)

_DEFAULTS: dict = {
    "filter_date_from":  DATE_MIN,
    "filter_date_to":    DATE_MAX,
    "filter_states":     [],
    "filter_categories": [],
    "filter_statuses":   [],
    "filter_min_value":  0.0,
}


def init_filter_defaults() -> None:
    for key, val in _DEFAULTS.items():
        st.session_state.setdefault(key, val)


def get_filter_dict() -> dict:
    init_filter_defaults()
    return {
        "date_from":  st.session_state["filter_date_from"],
        "date_to":    st.session_state["filter_date_to"],
        "states":     st.session_state["filter_states"],
        "categories": st.session_state["filter_categories"],
        "statuses":   st.session_state["filter_statuses"],
        "min_value":  st.session_state["filter_min_value"],
    }


@st.cache_data(show_spinner=False)
def _state_options() -> list:
    return db.query(
        "SELECT DISTINCT customer_state FROM orders_enriched "
        "WHERE customer_state IS NOT NULL ORDER BY 1"
    )["customer_state"].tolist()


@st.cache_data(show_spinner=False)
def _category_options() -> list:
    return db.query(
        "SELECT DISTINCT product_category_name_english FROM orders_enriched "
        "WHERE product_category_name_english IS NOT NULL ORDER BY 1"
    )["product_category_name_english"].tolist()


@st.cache_data(show_spinner=False)
def _status_options() -> list:
    return db.query(
        "SELECT DISTINCT order_status FROM orders_enriched "
        "WHERE order_status IS NOT NULL ORDER BY 1"
    )["order_status"].tolist()


def render_filters() -> dict:
    """Render filter widgets in the calling context (not the sidebar).

    Call inside whatever column or container the filter panel lives in.
    Reads/writes session state via widget keys so values survive panel collapse.
    Returns the current filter dict (same as get_filter_dict()).
    """
    init_filter_defaults()

    st.date_input(
        "Date from",
        min_value=DATE_MIN,
        max_value=DATE_MAX,
        key="filter_date_from",
    )
    st.date_input(
        "Date to",
        min_value=DATE_MIN,
        max_value=DATE_MAX,
        key="filter_date_to",
    )
    st.multiselect("Customer state",    options=_state_options(),    key="filter_states")
    st.multiselect("Product category",  options=_category_options(), key="filter_categories")
    st.multiselect("Order status",      options=_status_options(),   key="filter_statuses")
    st.number_input("Min order value (R$)", min_value=0.0, step=10.0, key="filter_min_value")

    return get_filter_dict()
