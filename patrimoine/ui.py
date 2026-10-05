"""Shared helpers for the Streamlit pages: cached loaders and French number formatting."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import db, queries
from .config import Settings


# Same order as chartCategoricalColors in .streamlit/config.toml; "Autres" is always the neutral grey.
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
OTHER = "#8a8983"
PLOT_CONFIG = {"displayModeBar": False, "locale": "fr"}


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
def income() -> pd.DataFrame:
    return _load(queries.income)


@st.cache_data(ttl="10m", show_spinner=False)
def last_sync() -> str | None:
    return _load(queries.last_sync)


@st.cache_data(ttl="10m", show_spinner=False)
def investment_income() -> pd.DataFrame:
    return _load(queries.investment_income)


@st.cache_data(ttl="10m", show_spinner=False)
def account_open_dates() -> dict:
    return _load(queries.account_open_dates)


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
        height=height, margin=dict(l=0, r=48, t=10, b=0), hovermode="x unified",  # r: room for bar labels
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        separators=", ", xaxis_title=None, yaxis_title=None,
    )
    if any(getattr(t, "type", "") == "bar" and getattr(t, "orientation", None) == "h" for t in fig.data):
        fig.update_layout(hovermode="y unified")  # the hover header then names the bar under the mouse
    return fig


@st.cache_data(ttl="10m", show_spinner=False)
def invested() -> pd.DataFrame:
    from . import analytics

    return _load(analytics.invested_series)


@st.cache_data(ttl="10m", show_spinner=False)
def invested_stats() -> dict:
    from . import analytics

    return analytics.stats(invested())


@st.cache_data(ttl="6h", show_spinner=False)
def benchmark(symbol: str) -> pd.Series | None:
    from . import analytics

    return _load(lambda con: analytics.benchmark(con, invested(), symbol))


@st.cache_data(ttl="10m", show_spinner=False)
def lines() -> pd.DataFrame:
    from . import analytics

    return _load(analytics.lines)


@st.cache_data(ttl="10m", show_spinner=False)
def monthly_balance() -> pd.DataFrame:
    from . import analytics

    return _load(analytics.monthly_balance)


@st.cache_data(ttl="10m", show_spinner=False)
def prices(isin: str) -> pd.Series:
    df = _load(lambda con: pd.read_sql_query("SELECT date, close FROM prices WHERE isin = ? ORDER BY date", con,
                                             params=(isin,), parse_dates=["date"]))
    return df.set_index("date")["close"]


@st.cache_data(ttl="10m", show_spinner=False)
def trades(isin: str) -> pd.DataFrame:
    return _load(lambda con: pd.read_sql_query(
        "SELECT date, flow, quantity, amount_cents / 100.0 AS amount, fees_cents / 100.0 AS fees,"
        " COALESCE(holding_account_id, account_id) AS account FROM transactions WHERE isin = ? AND flow IN"
        " ('achat_titre', 'vente_titre', 'saveback', 'titres_offerts', 'operation_titres') ORDER BY date", con,
        params=(isin,), parse_dates=["date"]))


def month_label(ts) -> str:
    months = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    ts = pd.Timestamp(ts)
    return f"{months[ts.month - 1]} {ts.year}"


GLOSSARY = """
- **PMP** (prix moyen pondéré) : prix moyen payé par titre, frais d'achat inclus. Une vente ne le change pas ;
  c'est la base de calcul de l'impôt.
- **Plus-value latente** : valeur actuelle moins le coût de ce que tu détiens encore. Non imposée tant que tu ne vends pas.
- **Plus-value réalisée** : prix de vente moins le coût des titres vendus. Imposée au PFU (30 %) sur le compte-titres.
- **Net investi** : total des achats moins total des ventes. Ce que tu as sorti de ta poche et laissé en bourse.
- **Gain total** : valeur actuelle moins net investi (plus-values latentes + réalisées + Saveback et cadeaux).
- **TWR** (performance pondérée par le temps) : la performance des placements eux-mêmes, sans l'effet du moment où
  tu as ajouté ou retiré de l'argent. C'est le chiffre à comparer à un indice. Calculé à partir de 1 000 € investis.
- **TRI** (taux de rendement interne) : le rendement annuel de *ton* argent, compte tenu des dates de tes versements.
- **Volatilité** : amplitude annuelle des variations. 15 % pour un indice actions mondial, beaucoup plus avec du levier.
- **Pire baisse** (drawdown) : plus forte chute depuis un plus haut, avant de le retrouver.
- **Levier (2x, 3x)** : l'ETF fait deux ou trois fois la variation *quotidienne* de l'indice. Sur plusieurs jours
  agités, il perd du terrain même si l'indice revient à son niveau (décote de volatilité).
- **Turbo / warrant** : produit à effet de levier avec une barrière ; s'il la touche, il est désactivé et vaut presque 0.
"""


FIXED = ("Logement et énergie", "Abonnements et télécom", "Impôts et taxes")  # not day-to-day choices


def short_month(ts) -> str:
    months = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    ts = pd.Timestamp(ts)
    label = f"{months[ts.month - 1]} {str(ts.year)[2:]}"
    return label + " (en cours)" if ts.to_period("M") == pd.Timestamp.today().to_period("M") else label


def month_axis(df: pd.DataFrame, col: str = "month", through_now: bool = True) -> tuple[pd.DataFrame, list[str]]:
    """Months as ordered text labels, so each label sits centred under its bar (no tilted date ticks). The
    current month is part of the axis even before its first line (pass the labels to ``keep_months``)."""
    months = sorted(pd.Timestamp(m) for m in df[col].unique())
    now = pd.Timestamp.today().to_period("M").to_timestamp()
    if through_now and months and now not in months:
        months.append(now)
    df = df.assign(mois=df[col].map(short_month))
    return df, [short_month(m) for m in months]


def keep_months(fig, labels: list[str]) -> None:
    """Show every month of ``labels`` on the x axis, even one with no data yet (an invisible marker)."""
    fig.add_trace(go.Scatter(x=labels, y=[0] * len(labels), mode="markers", marker=dict(opacity=0),
                             showlegend=False, hoverinfo="skip"))
    fig.update_xaxes(categoryorder="array", categoryarray=labels)


def reset_filters_button(values: dict, pop: list[str] | None = None,
                         label: str = "Réinitialiser les filtres") -> None:
    """A button that restores the given session-state keys to ``values`` (segmented_control keeps its own
    frontend state and ignores ``default`` once a key has been popped, so it must be set explicitly) and
    pops the rest, so their widgets fall back to their defaults.

    Uses ``on_click`` rather than an inline ``if st.button(...)``: the button sits after the widgets it
    resets in the script, and Streamlit forbids writing to a widget's session-state key once that widget
    has already been instantiated in the same run — the callback runs before the rerun, so it's still early.
    """

    def _reset() -> None:
        for k, v in values.items():
            st.session_state[k] = v
        for k in (pop or []):
            st.session_state.pop(k, None)

    st.button(label, icon=":material/filter_alt_off:", key=f"reset_{'_'.join(values) + '_'.join(pop or [])}",
             on_click=_reset)
