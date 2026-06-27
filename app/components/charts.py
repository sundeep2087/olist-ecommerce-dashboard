import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

_TEMPLATE = "plotly_dark"
_LAYOUT = dict(
    template=_TEMPLATE,
    paper_bgcolor="#0e1117",
    plot_bgcolor="#0e1117",
    margin=dict(t=40, b=0, l=0, r=0),
    font=dict(color="#e8eaf0"),
)


def bar_chart(df: pd.DataFrame, x: str, y: str, title: str, color=None, horizontal=False):
    orientation = "h" if horizontal else "v"
    _x, _y = (y, x) if horizontal else (x, y)
    fig = px.bar(df, x=_x, y=_y, color=color, orientation=orientation, title=title)
    fig.update_layout(**_LAYOUT)
    return fig


def line_chart(df: pd.DataFrame, x: str, y: str, title: str, color=None,
               line_color: str = "#4da6d8"):
    fig = px.line(df, x=x, y=y, color=color, title=title, markers=True)
    if color is None:
        fig.update_traces(
            line=dict(color=line_color, width=2.5),
            marker=dict(color=line_color, size=5),
            fill="tozeroy",
            fillcolor="rgba(77,166,216,0.12)",
        )
    fig.update_layout(**_LAYOUT)
    return fig


def box_plot(df: pd.DataFrame, x: str, y: str, title: str, color=None):
    fig = px.box(df, x=x, y=y, color=color, title=title)
    fig.update_layout(**_LAYOUT)
    return fig


def heatmap(df: pd.DataFrame, x: str, y: str, z: str, title: str):
    pivot = df.pivot(index=y, columns=x, values=z)
    fig = go.Figure(
        go.Heatmap(z=pivot.values, x=pivot.columns.tolist(), y=pivot.index.tolist(),
                   colorscale="Teal")
    )
    fig.update_layout(title=title, **_LAYOUT)
    return fig


def funnel(stages: dict, title: str):
    fig = go.Figure(go.Funnel(y=list(stages.keys()), x=list(stages.values())))
    fig.update_layout(title=title, **_LAYOUT)
    return fig
