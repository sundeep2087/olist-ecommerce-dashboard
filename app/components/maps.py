import math
import pydeck as pdk
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


# ── Brazil view constants ─────────────────────────────────────────────────────
_BRAZIL_CENTER = {"lat": -14.2, "lon": -51.9}
_BRAZIL_ZOOM = 3.3
_MAP_STYLE = "carto-darkmatter"

# ── Color scales — min is saturated mid-tone so low-value dots stay visible
# on the dark map tile (carto-darkmatter ≈ #1a1a1a background).
SCALES = {
    "orange": [[0, "#8b4000"], [0.5, "#cc6600"], [1, "#ffaa20"]],   # GMV — rust → amber
    "teal":   [[0, "#005555"], [0.5, "#009988"], [1, "#00ddbb"]],   # Orders — dark → bright teal
    "purple": [[0, "#550077"], [0.5, "#9922cc"], [1, "#dd88ff"]],   # Customers — deep → bright violet
    "score":  [[0, "#cc2200"], [0.5, "#ffdd00"], [1, "#00aa44"]],   # Review — RdYlGn
    "blue":   [[0, "#0a1628"], [0.5, "#1e5799"], [1, "#56c8e0"]],   # fallback
}

UF_TO_NAME = {
    "RO": "Rondônia",         "AC": "Acre",                "AM": "Amazonas",
    "RR": "Roraima",          "PA": "Pará",                "AP": "Amapá",
    "TO": "Tocantins",        "MA": "Maranhão",            "PI": "Piauí",
    "CE": "Ceará",            "RN": "Rio Grande do Norte", "PB": "Paraíba",
    "PE": "Pernambuco",       "AL": "Alagoas",             "SE": "Sergipe",
    "BA": "Bahia",            "MG": "Minas Gerais",        "ES": "Espírito Santo",
    "RJ": "Rio de Janeiro",   "SP": "São Paulo",           "PR": "Paraná",
    "SC": "Santa Catarina",   "RS": "Rio Grande do Sul",   "MS": "Mato Grosso do Sul",
    "MT": "Mato Grosso",      "GO": "Goiás",               "DF": "Distrito Federal",
}


def _metric_fmt(metric_col: str, value_token: str) -> str:
    if metric_col == "gmv":
        return f"R$ %{{{value_token}:,.0f}}"
    if metric_col == "avg_review_score":
        return f"%{{{value_token}:.2f}}"
    return f"%{{{value_token}:,}}"


def state_choropleth(
    df: pd.DataFrame,
    geojson: dict,
    metric_col: str,
    metric_display: str,
    color_scheme: str = "blue",
) -> go.Figure:
    scale = SCALES.get(color_scheme, SCALES["blue"])

    hover_cols = ["order_count", "unique_customers", "gmv", "avg_review_score"]
    for col in hover_cols:
        if col not in df.columns:
            df[col] = 0

    fig = px.choropleth_mapbox(
        df,
        geojson=geojson,
        locations="customer_state",
        featureidkey="properties.uf",
        color=metric_col,
        color_continuous_scale=scale,
        mapbox_style=_MAP_STYLE,
        zoom=_BRAZIL_ZOOM,
        center=_BRAZIL_CENTER,
        opacity=0.82,
        labels={metric_col: metric_display},
    )

    fig.update_traces(
        customdata=df[hover_cols].values,
        hovertemplate=(
            "<b>%{location}</b><br>"
            "GMV: R$ %{customdata[2]:,.0f}<br>"
            "Orders: %{customdata[0]:,}<br>"
            "Customers: %{customdata[1]:,}<br>"
            "Avg Review: %{customdata[3]:.2f}<br>"
            "<extra></extra>"
        ),
    )

    label_df = df.dropna(subset=["lat", "lng"])
    fig.add_trace(
        go.Scattermapbox(
            lat=label_df["lat"].tolist(),
            lon=label_df["lng"].tolist(),
            mode="text",
            text=label_df["customer_state"].tolist(),
            textfont=dict(size=9, color="#e8eaf0", family="Arial Black"),
            showlegend=False,
            hoverinfo="none",
            hovertemplate=None,
            name="",
        )
    )

    tickfmt = "$~s" if metric_col == "gmv" else ".1f" if metric_col == "avg_review_score" else ","
    fig.update_layout(
        margin=dict(t=0, b=0, l=0, r=0),
        height=520,
        clickmode="event+select",
        paper_bgcolor="#0e1117",
        coloraxis_colorbar=dict(
            title=dict(text=metric_display, side="right", font=dict(color="#e8eaf0")),
            tickfont=dict(color="#e8eaf0"),
            thickness=14,
            len=0.55,
            tickformat=tickfmt,
        ),
    )
    return fig


def city_scatter(
    df: pd.DataFrame,
    geojson: dict,
    metric_col: str,
    metric_display: str,
    selected_state: str,
    color_scheme: str = "blue",
) -> go.Figure:
    scale = SCALES.get(color_scheme, SCALES["blue"])
    df = df.dropna(subset=["lat", "lng"]).copy()

    use_size = metric_col != "avg_review_score"

    state_feature = next(
        (f for f in geojson["features"] if f["properties"]["uf"] == selected_state), None
    )

    center_lat = df["lat"].mean()
    center_lng = df["lng"].mean()

    lat_span = df["lat"].max() - df["lat"].min()
    lng_span = df["lng"].max() - df["lng"].min()
    span = max(lat_span, lng_span, 0.5)
    # Log2-based formula: zoom 5 ≈ 11° visible. Larger states → lower zoom, smaller → higher.
    zoom = max(4.5, min(8.5, math.log2(360 / span) + 0.8))

    hover_cols = ["order_count", "unique_customers", "gmv", "avg_review_score"]
    for col in hover_cols:
        if col not in df.columns:
            df[col] = 0

    fig = px.scatter_mapbox(
        df,
        lat="lat",
        lon="lng",
        size=metric_col if use_size else None,
        color=metric_col,
        color_continuous_scale=scale,
        mapbox_style=_MAP_STYLE,
        zoom=zoom,
        center={"lat": center_lat, "lon": center_lng},
        size_max=55,
        opacity=0.88,
        labels={metric_col: metric_display},
    )

    fig.update_traces(
        customdata=df[["customer_city", "customer_state"] + hover_cols].values,
        hovertemplate=(
            "<b>%{customdata[0]}, %{customdata[1]}</b><br>"
            "GMV: R$ %{customdata[4]:,.0f}<br>"
            "Orders: %{customdata[2]:,}<br>"
            "Customers: %{customdata[3]:,}<br>"
            "Avg Review: %{customdata[5]:.2f}<br>"
            "<extra></extra>"
        ),
        marker=dict(sizemin=7),
    )

    if state_feature:
        state_geojson = {"type": "FeatureCollection", "features": [state_feature]}
        fig.add_trace(
            go.Choroplethmapbox(
                geojson=state_geojson,
                locations=[selected_state],
                featureidkey="properties.uf",
                z=[0],
                colorscale=[[0, "rgba(77,166,216,0.12)"], [1, "rgba(77,166,216,0.12)"]],
                showscale=False,
                marker=dict(line=dict(width=2.5, color="#4da6d8")),
                hoverinfo="skip",
                name="",
            )
        )

    tickfmt = "$~s" if metric_col == "gmv" else ".1f" if metric_col == "avg_review_score" else ","
    fig.update_layout(
        margin=dict(t=0, b=0, l=0, r=0),
        height=520,
        paper_bgcolor="#0e1117",
        coloraxis_colorbar=dict(
            title=dict(text=metric_display, side="right", font=dict(color="#e8eaf0")),
            tickfont=dict(color="#e8eaf0"),
            thickness=14,
            len=0.55,
            tickformat=tickfmt,
        ),
    )
    return fig


# ── PyDeck fallback (used when GeoJSON not available) ─────────────────────────

_BRAZIL_PYDECK_VIEW = pdk.ViewState(latitude=-14.2, longitude=-51.9, zoom=3.5, pitch=0)


def _lerp_colors(values: pd.Series, scheme: str, alpha: int = 210) -> list:
    low_map  = {"orange": [45, 16, 0],  "teal": [0, 24, 24],  "purple": [26, 0, 48],  "blue": [10, 22, 40]}
    high_map = {"orange": [255, 140, 0], "teal": [0, 229, 204], "purple": [192, 132, 252], "blue": [86, 200, 224]}
    low  = low_map.get(scheme,  low_map["blue"])
    high = high_map.get(scheme, high_map["blue"])
    vmin, vmax = values.min(), values.max()
    span = max(vmax - vmin, 1e-9)
    return [
        [int(low[i] + (v - vmin) / span * (high[i] - low[i])) for i in range(3)] + [alpha]
        for v in values
    ]


def state_bubble_map(
    df: pd.DataFrame,
    metric_col: str,
    metric_label: str,
    color_scheme: str = "blue",
) -> pdk.Deck:
    df = df.dropna(subset=["lat", "lng", metric_col]).copy()
    if df.empty:
        return pdk.Deck(initial_view_state=_BRAZIL_PYDECK_VIEW)

    df["_color"] = _lerp_colors(df[metric_col], color_scheme)
    vmin, vmax = df[metric_col].min(), df[metric_col].max()
    df["_radius"] = 90_000 + (df[metric_col] - vmin) / max(vmax - vmin, 1e-9) * 190_000
    df["_label"] = df[metric_col].apply(
        lambda x: f"R$ {x:,.0f}" if "gmv" in metric_col else
                  f"{x:.2f}" if "score" in metric_col else f"{x:,.0f}"
    )

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position=["lng", "lat"],
        get_radius="_radius",
        get_fill_color="_color",
        get_line_color=[232, 234, 240, 180],
        line_width_min_pixels=1,
        pickable=True,
        stroked=True,
        opacity=0.85,
    )
    tooltip = {
        "html": f"<b>{{customer_state}}</b><br>{metric_label}: {{_label}}",
        "style": {
            "backgroundColor": "#1a1f2e",
            "color": "#e8eaf0",
            "fontSize": "13px",
            "padding": "6px 10px",
            "borderRadius": "4px",
            "border": "1px solid #4da6d8",
        },
    }
    return pdk.Deck(
        layers=[layer],
        initial_view_state=_BRAZIL_PYDECK_VIEW,
        tooltip=tooltip,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    )


# ── Arc flow map (Page 2: Seller → Customer state flows) ─────────────────────

_ARC_COLORS = {
    "teal":   ([0, 55, 55],   [0, 220, 195]),
    "orange": ([100, 40, 0],  [255, 160, 20]),
    "delay":  ([0, 80, 200],  [215, 25, 25]),
}

_ARC_VIEW = pdk.ViewState(latitude=-14.2, longitude=-51.9, zoom=3.5, pitch=30)


def arc_flow_map(
    df: pd.DataFrame,
    metric_col: str,
    metric_label: str,
    color_scheme: str = "teal",
) -> pdk.Deck:
    """PyDeck ArcLayer connecting seller state centroids to customer state centroids.

    Arc width encodes order_count; arc color encodes the selected metric.
    Source (seller) end is rendered dim; target (customer) end is bright to
    show flow directionality at a glance.
    """
    df = df.dropna(subset=["seller_lat", "seller_lng", "customer_lat", "customer_lng"]).copy()
    df = df[df["seller_state"] != df["customer_state"]]

    if df.empty:
        return pdk.Deck(initial_view_state=_ARC_VIEW)

    # Arc width: normalize order_count → [2, 14] pixels
    omin = float(df["order_count"].min())
    omax = float(df["order_count"].max())
    df["_width"] = 2.0 + (df["order_count"] - omin) / max(omax - omin, 1.0) * 12.0

    # Color lerp for selected metric
    low_c, high_c = _ARC_COLORS.get(color_scheme, _ARC_COLORS["teal"])
    vals = df[metric_col].fillna(0.0)
    vmin = float(vals.min())
    vmax = float(vals.max())
    vspan = max(vmax - vmin, 1e-9)

    def _lerp(v: float) -> list:
        t = max(0.0, min(1.0, (float(v) - vmin) / vspan))
        return [
            int(low_c[0] + t * (high_c[0] - low_c[0])),
            int(low_c[1] + t * (high_c[1] - low_c[1])),
            int(low_c[2] + t * (high_c[2] - low_c[2])),
            210,
        ]

    tgt_colors = [_lerp(v) for v in vals]
    df["_tgt_color"] = tgt_colors
    # Seller (source) end is a dim version of the target color
    df["_src_color"] = [[c // 3 for c in col[:3]] + [140] for col in tgt_colors]

    # Pre-format tooltip values — PyDeck doesn't support Python format specs inline
    df["_t_orders"] = df["order_count"].apply(lambda x: f"{int(x):,}")
    df["_t_gmv"]    = df["gmv"].apply(lambda x: f"R$ {x:,.0f}")
    df["_t_delay"]  = df["avg_delay_days"].apply(
        lambda x: f"{x:.1f} days" if pd.notna(x) else "N/A"
    )
    df["_t_dist"]   = df["avg_distance_km"].apply(
        lambda x: f"{x:,.0f} km" if pd.notna(x) else "N/A"
    )

    layer = pdk.Layer(
        "ArcLayer",
        data=df,
        get_source_position=["seller_lng", "seller_lat"],
        get_target_position=["customer_lng", "customer_lat"],
        get_source_color="_src_color",
        get_target_color="_tgt_color",
        get_width="_width",
        pickable=True,
        auto_highlight=True,
    )

    tooltip = {
        "html": (
            "<b>{seller_state} → {customer_state}</b><br>"
            "Orders: {_t_orders}<br>"
            "GMV: {_t_gmv}<br>"
            "Avg Delay: {_t_delay}<br>"
            "Avg Distance: {_t_dist}"
        ),
        "style": {
            "backgroundColor": "#1a1f2e",
            "color": "#e8eaf0",
            "fontSize": "13px",
            "padding": "8px 12px",
            "borderRadius": "4px",
            "border": "1px solid #4da6d8",
        },
    }

    return pdk.Deck(
        layers=[layer],
        initial_view_state=_ARC_VIEW,
        tooltip=tooltip,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    )


# ── Seller location scatter map (Page 5) ─────────────────────────────────────

def seller_scatter_map(df: pd.DataFrame) -> pdk.Deck:
    """PyDeck ScatterplotLayer of individual seller locations.

    Color encodes avg_review_score (red = low, yellow = mid, green = high).
    Radius is log-scaled from GMV so SP mega-sellers don't overwhelm the map.
    """
    import math

    df = df.dropna(subset=["seller_lat", "seller_lng", "avg_review_score", "gmv"]).copy()
    if df.empty:
        return pdk.Deck(initial_view_state=_BRAZIL_PYDECK_VIEW)

    # Red → Yellow → Green lerp for review score
    s_min = float(df["avg_review_score"].min())
    s_max = float(df["avg_review_score"].max())
    s_span = max(s_max - s_min, 0.01)

    _RED    = [204, 34,  0]
    _YELLOW = [255, 221, 0]
    _GREEN  = [0,  170, 68]

    def _score_color(s: float) -> list:
        t = (float(s) - s_min) / s_span
        if t < 0.5:
            u = t * 2.0
            return [int(_RED[i] + u * (_YELLOW[i] - _RED[i])) for i in range(3)] + [215]
        else:
            u = (t - 0.5) * 2.0
            return [int(_YELLOW[i] + u * (_GREEN[i] - _YELLOW[i])) for i in range(3)] + [215]

    df["_color"] = [_score_color(v) for v in df["avg_review_score"]]

    log_gmv = df["gmv"].apply(lambda x: math.log1p(max(float(x), 0.0)))
    l_min, l_max = log_gmv.min(), log_gmv.max()
    df["_radius"] = 12_000 + (log_gmv - l_min) / max(l_max - l_min, 1e-9) * 88_000

    df["_t_sid"]    = df["seller_id"].str[:8] + "…"
    df["_t_review"] = df["avg_review_score"].apply(lambda x: f"{x:.2f}")
    df["_t_gmv"]    = df["gmv"].apply(lambda x: f"R$ {x:,.0f}")
    df["_t_orders"] = df["order_count"].apply(lambda x: f"{int(x):,}")
    df["_t_late"]   = df["late_pct"].apply(lambda x: f"{x:.1f}%")

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position=["seller_lng", "seller_lat"],
        get_radius="_radius",
        get_fill_color="_color",
        get_line_color=[232, 234, 240, 100],
        line_width_min_pixels=1,
        pickable=True,
        stroked=True,
        opacity=0.88,
    )
    tooltip = {
        "html": (
            "<b>{_t_sid} — {seller_city}, {seller_state}</b><br>"
            "⭐ Review: {_t_review}<br>"
            "💰 GMV: {_t_gmv}<br>"
            "📦 Orders: {_t_orders}<br>"
            "🚨 Late: {_t_late}"
        ),
        "style": {
            "backgroundColor": "#1a1f2e",
            "color": "#e8eaf0",
            "fontSize": "13px",
            "padding": "8px 12px",
            "borderRadius": "4px",
            "border": "1px solid #4da6d8",
        },
    }
    return pdk.Deck(
        layers=[layer],
        initial_view_state=_BRAZIL_PYDECK_VIEW,
        tooltip=tooltip,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    )


# ── Delivery delay scatter map (Page 3) ──────────────────────────────────────

def delivery_scatter_map(df: pd.DataFrame) -> pdk.Deck:
    """PyDeck ScatterplotLayer showing avg delivery delay by state.

    Color diverges around 0: blue = consistently early, red = late on average.
    Bubble radius reflects the magnitude of the delay so extreme states stand out.
    """
    df = df.dropna(subset=["lat", "lng", "avg_delay_days"]).copy()
    if df.empty:
        return pdk.Deck(initial_view_state=_BRAZIL_PYDECK_VIEW)

    extreme = max(
        abs(float(df["avg_delay_days"].min())),
        float(df["avg_delay_days"].max()),
        1.0,
    )

    def _color(delay: float) -> list:
        t = max(-1.0, min(1.0, delay / extreme))
        if t < 0:
            s = -t  # 0 = neutral gray, 1 = deepest blue
            return [int(120 - 90 * s), int(120 - 20 * s), int(120 + 100 * s), 220]
        else:
            return [int(120 + 100 * t), int(120 - 80 * t), int(120 - 100 * t), 220]

    df["_color"]  = [_color(v) for v in df["avg_delay_days"]]
    df["_radius"] = 80_000 + df["avg_delay_days"].abs() / extreme * 160_000

    df["_t_delay"]   = df["avg_delay_days"].apply(
        lambda x: f"+{x:.1f}" if x > 0 else f"{x:.1f}"
    )
    df["_t_late_pct"] = df["late_pct"].apply(lambda x: f"{x:.1f}%")
    df["_t_transit"]  = df["avg_transit_days"].apply(lambda x: f"{x:.1f} days")

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position=["lng", "lat"],
        get_radius="_radius",
        get_fill_color="_color",
        get_line_color=[232, 234, 240, 140],
        line_width_min_pixels=1,
        pickable=True,
        stroked=True,
        opacity=0.90,
    )

    tooltip = {
        "html": (
            "<b>{customer_state}</b><br>"
            "Avg Delay: {_t_delay} days<br>"
            "Late Rate: {_t_late_pct}<br>"
            "Avg Transit: {_t_transit}"
        ),
        "style": {
            "backgroundColor": "#1a1f2e",
            "color": "#e8eaf0",
            "fontSize": "13px",
            "padding": "8px 12px",
            "borderRadius": "4px",
            "border": "1px solid #4da6d8",
        },
    }

    return pdk.Deck(
        layers=[layer],
        initial_view_state=_BRAZIL_PYDECK_VIEW,
        tooltip=tooltip,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    )
