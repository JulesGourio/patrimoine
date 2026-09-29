import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from patrimoine import ui

hist = ui.history()
if hist.empty:
    st.warning("Pas encore d'historique : lance `uv run patrimoine sync`.", icon=":material/info:")
    st.stop()

RISKY = {"PEA", "Compte-titres", "PEG Airbus"}
last = hist[hist.date == hist.date.max()]
risky_now = float(last[last.account.isin(RISKY)].value.sum())
safe_now = float(last[~last.account.isin(RISKY)].value.sum())
total_now = risky_now + safe_now
bal = ui.monthly_balance()
this_month = pd.Timestamp.today().to_period("M").to_timestamp()
saving_12m = bal[(bal.index < this_month)].tail(12).epargne.mean()

st.subheader("Projection", icon=":material/trending_up:")
st.caption("Où peut aller ton patrimoine selon ton épargne et les marchés. Chaque scénario tire au hasard les "
           "rendements de chaque mois (moyenne et volatilité choisies ci-dessous) : la zone montre les issues "
           "plausibles, pas une promesse. Montants avant impôts à la sortie.")

with st.container(border=True):
    c1, c2, c3, c4 = st.columns(4)
    years = c1.slider("Horizon (années)", 1, 40, 20, key="pj_years")
    monthly = c2.number_input("Épargne par mois (€)", 0, 20_000, int(round(saving_12m / 50) * 50) if saving_12m > 0 else 1000,
                              step=50, key="pj_monthly",
                              help=f"Par défaut ta moyenne des 12 derniers mois : {ui.eur(saving_12m)}.")
    growth = c3.number_input("Hausse de l'épargne par an (%)", 0.0, 10.0, 2.0, 0.5, key="pj_growth",
                             help="Augmentations de salaire : l'épargne mensuelle grandit chaque année.")
    goal = c4.number_input("Objectif (€)", 0, 10_000_000, 500_000, 10_000, key="pj_goal")
    c1, c2, c3, c4 = st.columns(4)
    share = c1.slider("Part investie en actions (%)", 0, 100, int(round(100 * risky_now / total_now)), key="pj_share",
                      help="Pour le capital actuel et l'épargne future. Aujourd'hui : "
                           f"{ui.pct(risky_now / total_now, sign=False)} (PEA, compte-titres, PEG).") / 100
    mu = c2.number_input("Rendement actions (%/an)", -5.0, 20.0, 7.0, 0.5, key="pj_mu",
                         help="Moyenne historique des actions mondiales : environ 7 %/an sur longue période "
                              "(dividendes réinvestis, avant inflation).") / 100
    vol = c3.number_input("Volatilité actions (%/an)", 5.0, 60.0, 18.0, 1.0, key="pj_vol",
                          help="Environ 15-18 % pour un indice mondial ; bien plus avec du levier (ton Nasdaq x2) "
                               "ou une action seule (Airbus).") / 100
    safe_rate = c4.number_input("Rendement livrets (%/an)", 0.0, 6.0, 2.4, 0.1, key="pj_safe") / 100
    inflation = st.slider("Inflation (%/an)", 0.0, 5.0, 2.0, 0.1, key="pj_infl",
                          help="Pour exprimer le résultat en euros d'aujourd'hui.") / 100

N, months = 2000, years * 12
rng = np.random.default_rng(7)
m_mu, m_vol = np.log(1 + mu) / 12, vol / np.sqrt(12)
r_risky = np.exp(rng.normal(m_mu - m_vol ** 2 / 2, m_vol, (N, months))) - 1
r_safe = (1 + safe_rate) ** (1 / 12) - 1
risky = np.full(N, total_now * share)
safe = np.full(N, total_now * (1 - share))
path = np.empty((N, months + 1))
path[:, 0] = risky + safe
for m in range(months):
    add = monthly * (1 + growth / 100) ** (m // 12)
    risky = risky * (1 + r_risky[:, m]) + add * share
    safe = safe * (1 + r_safe) + add * (1 - share)
    path[:, m + 1] = risky + safe
dates = pd.date_range(this_month, periods=months + 1, freq="MS")
deflate = (1 + inflation) ** (np.arange(months + 1) / 12)
q = {p: np.percentile(path, p, axis=0) for p in (10, 25, 50, 75, 90)}
paid = total_now + sum(monthly * (1 + growth / 100) ** (m // 12) for m in range(months))
final = path[:, -1]
reach = (path >= goal).any(axis=1).mean() if goal else None
med_hit = next((dates[i] for i, v in enumerate(q[50]) if v >= goal), None) if goal else None

with st.container(horizontal=True):
    st.metric(f"Dans {years} ans (médiane)", ui.eur(np.median(final)), f"{ui.eur(np.median(final) / deflate[-1])} "
              "en euros d'aujourd'hui", delta_color="off", border=True)
    st.metric("Scénario prudent (1 sur 10)", ui.eur(q[10][-1]), border=True,
              help="9 scénarios sur 10 font mieux.")
    st.metric("Scénario favorable (1 sur 10)", ui.eur(q[90][-1]), border=True)
    st.metric("Dont versé de ta poche", ui.eur(paid), f"{ui.eur(np.median(final) - paid, sign=True)} de gains (médiane)",
              delta_color="off", border=True, help="Patrimoine actuel plus toutes les épargnes futures.")
    if goal:
        st.metric(f"Chance d'atteindre {ui.eur(goal)}", ui.pct(reach, sign=False),
                  f"médiane : {ui.month_label(med_hit)}" if med_hit is not None else "pas dans l'horizon (médiane)",
                  delta_color="off", border=True)

with st.container(border=True):
    st.markdown("**Trajectoires possibles** · zone foncée : 1 scénario sur 2, zone claire : 8 sur 10")
    fig = go.Figure([
        go.Scatter(x=dates, y=q[90], line=dict(width=0), hoverinfo="skip", showlegend=False),
        go.Scatter(x=dates, y=q[10], fill="tonexty", fillcolor="rgba(42,120,214,0.12)", line=dict(width=0),
                   name="8 scénarios sur 10", hoverinfo="skip"),
        go.Scatter(x=dates, y=q[75], line=dict(width=0), hoverinfo="skip", showlegend=False),
        go.Scatter(x=dates, y=q[25], fill="tonexty", fillcolor="rgba(42,120,214,0.25)", line=dict(width=0),
                   name="1 scénario sur 2", hoverinfo="skip"),
        go.Scatter(x=dates, y=q[50], name="Médiane", line=dict(color=ui.CATEGORICAL[0], width=2.5),
                   hovertemplate="%{y:,.0f} €"),
        go.Scatter(x=dates, y=q[50] / deflate, name="Médiane en euros d'aujourd'hui",
                   line=dict(color=ui.OTHER, width=2, dash="dot"), hovertemplate="%{y:,.0f} €"),
    ])
    cum_paid = total_now + np.cumsum([0] + [monthly * (1 + growth / 100) ** (m // 12) for m in range(months)])
    fig.add_trace(go.Scatter(x=dates, y=cum_paid, name="Versé", line=dict(color=ui.CATEGORICAL[1], width=1.5),
                             hovertemplate="%{y:,.0f} €"))
    if goal:
        fig.add_hline(y=goal, line_dash="dash", line_color=ui.CATEGORICAL[2],
                      annotation_text=f"objectif {ui.eur(goal)}", annotation_position="top left")
    ui.plotly_layout(fig, 420)
    fig.update_yaxes(ticksuffix=" €", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)

with st.container(border=True):
    st.markdown("**Ce qui change le plus le résultat** · médiane à l'horizon")
    base = np.median(final)

    def median_with(monthly_=monthly, share_=share, mu_=mu) -> float:
        rng2 = np.random.default_rng(7)
        m_mu2 = np.log(1 + mu_) / 12
        rr = np.exp(rng2.normal(m_mu2 - m_vol ** 2 / 2, m_vol, (500, months))) - 1
        rk, sf = np.full(500, total_now * share_), np.full(500, total_now * (1 - share_))
        for m in range(months):
            add = monthly_ * (1 + growth / 100) ** (m // 12)
            rk = rk * (1 + rr[:, m]) + add * share_
            sf = sf * (1 + r_safe) + add * (1 - share_)
        return float(np.median(rk + sf))

    ref = median_with()
    rows = [("Épargner 200 € de plus par mois", median_with(monthly_=monthly + 200) - ref),
            ("Épargner 200 € de moins par mois", median_with(monthly_=max(monthly - 200, 0)) - ref),
            ("10 points de plus en actions", median_with(share_=min(share + 0.1, 1)) - ref),
            ("10 points de moins en actions", median_with(share_=max(share - 0.1, 0)) - ref),
            ("Rendement actions +1 point", median_with(mu_=mu + 0.01) - ref),
            ("Rendement actions −1 point", median_with(mu_=mu - 0.01) - ref)]
    d = pd.DataFrame(rows, columns=["levier", "effet"]).sort_values("effet")
    fig = go.Figure(go.Bar(x=d.effet, y=d.levier, orientation="h",
                           marker_color=[ui.CATEGORICAL[2] if v >= 0 else ui.CATEGORICAL[7] for v in d.effet],
                           text=[ui.eur(v, sign=True) for v in d.effet], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y} : %{x:+,.0f} €<extra></extra>"))
    ui.plotly_layout(fig, 280)
    fig.update_xaxes(ticksuffix=" €", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)
    st.caption(f"Point de départ : {ui.eur(total_now)} aujourd'hui, dont {ui.eur(risky_now)} en actions (PEA, "
               f"compte-titres, PEG Airbus) et {ui.eur(safe_now)} en livrets et liquidités. Les rendements passés ne "
               "préjugent pas des futurs ; le levier et la concentration (Airbus) élargissent la zone.")
