"""Shared helpers for the Streamlit pages: cached loaders and French number formatting."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import db, queries
from .config import Settings


# Same order as chartCategoricalColors in .streamlit/config.toml; "Autres" is always the neutral grey.
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
OTHER = "#8a8983"


def connect():
    con = db.connect(Settings().db_path)
    db.init(con)
    return con


def _load(fn):
    con = connect()
    try:
        return fn(con)
    finally:
        con.close()


@st.cache_data(ttl="10m", show_spinner=False)
def history() -> pd.DataFrame:
    return _load(queries.history)


@st.cache_data(ttl="10m", show_spinner=False)
def positions() -> pd.DataFrame:
    return _load(queries.positions)


@st.cache_data(ttl="10m", show_spinner=False)
def realised() -> pd.DataFrame:
    return _load(queries.realised)


@st.cache_data(ttl="10m", show_spinner=False)
def taxes() -> pd.DataFrame:
    return _load(queries.taxes)


@st.cache_data(ttl="10m", show_spinner=False)
def spending() -> pd.DataFrame:
    return _load(queries.spending)


@st.cache_data(ttl="10m", show_spinner=False)
def last_sync() -> str | None:
    return _load(queries.last_sync)


def eur(x: float | None, decimals: int = 0, sign: bool = False) -> str:
    if x is None or pd.isna(x):
        return "–"
    s = f"{x:+,.{decimals}f}" if sign else f"{x:,.{decimals}f}"
    return s.replace(",", " ").replace(".", ",") + " €"


def pct(x: float | None, sign: bool = True) -> str:
    if x is None or pd.isna(x):
        return "–"
    return (f"{x:+.1%}" if sign else f"{x:.1%}").replace(".", ",")


def plotly_layout(fig, height: int = 360):
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        separators=", ", xaxis_title=None, yaxis_title=None,
    )
    return fig
