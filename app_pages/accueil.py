import pandas as pd
import plotly.express as px
import streamlit as st

from patrimoine import ui

hist = ui.history()
if hist.empty:
    st.warning("Pas encore d'historique : lance `uv run patrimoine historique`.", icon=":material/info:")
    st.stop()

ORDER = ["PEA", "Compte-titres", "Trade Republic espèces", "PEG Airbus", "CMB courant", "Livret A", "Livret Jeune"]

with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader("Patrimoine", icon=":material/account_balance:")
    period = st.segmented_control("Période", ["3 mois", "1 an", "Tout"], default="1 an",
                                  label_visibility="collapsed")
    with_peg = st.toggle("PEG Airbus", value=True)

if not with_peg:
    hist = hist[hist.account_id != "peg_airbus"]
total = hist.groupby("date")[["value"]].sum()["value"]
today = total.index.max()
start = {"3 mois": today - pd.DateOffset(months=3), "1 an": today - pd.DateOffset(years=1)}.get(period, total.index.min())

last = hist[hist.date == today]
invested = last[last.account_id.isin(["tr_cto", "tr_pea"])]
latent = (invested.securities - invested.cost).sum()
realised_total = last.realised.sum()
ago = total.asof(today - pd.Timedelta(days=30))
spark = total[total.index >= start].resample("W").last().tolist()

with st.container(horizontal=True):
    st.metric("Patrimoine", ui.eur(total.iloc[-1]), ui.eur(total.iloc[-1] - ago, sign=True) + " sur 30 j",
              border=True, chart_data=spark, chart_type="area")
    tr = last[last.account_id.str.startswith("tr_")].value.sum()
    st.metric("Trade Republic", ui.eur(tr), border=True)
    if with_peg:
        st.metric("PEG Airbus", ui.eur(last[last.account_id == "peg_airbus"].value.sum()), border=True)
    st.metric("Plus-values latentes", ui.eur(latent, sign=True),
              ui.pct(latent / invested.cost.sum()) if invested.cost.sum() else None, border=True)
    st.metric("Plus-values réalisées", ui.eur(realised_total, sign=True), border=True,
              help="Cumul des ventes, depuis l'ouverture du compte Trade Republic.")

with st.container(border=True):
    st.markdown("**Valeur par compte**")
    view = hist[hist.date >= start]
    weekly = (view.set_index("date").groupby("account").resample("W")["value"].last().reset_index())
    accounts = [a for a in ORDER if a in weekly.account.unique()]
    fig = px.area(weekly, x="date", y="value", color="account", category_orders={"account": accounts},
                  labels={"value": "Valeur", "account": "Compte", "date": ""})
    fig.update_traces(line=dict(width=2), hovertemplate="%{y:,.0f} €")
    ui.plotly_layout(fig, 380)
    fig.update_yaxes(ticksuffix=" €", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch")

with st.container(border=True):
    st.markdown("**Gain de l'investissement Trade Republic** (latent + réalisé)")
    inv = hist[hist.account_id.isin(["tr_cto", "tr_pea"]) & (hist.date >= start)]
    gain = inv.assign(gain=inv.securities - inv.cost + inv.realised).groupby("date")["gain"].sum()
    fig = px.line(gain.resample("D").last().reset_index(), x="date", y="gain", labels={"gain": "Gain", "date": ""})
    fig.update_traces(line=dict(width=2), hovertemplate="%{y:,.0f} €")
    ui.plotly_layout(fig, 260)
    fig.update_yaxes(ticksuffix=" €", tickformat=",.0f", zeroline=True)
    st.plotly_chart(fig, width="stretch")

sync = ui.last_sync()
st.caption(
    f"Dernière synchronisation Trade Republic : {sync[:16].replace('T', ' ') if sync else 'jamais'} (UTC). "
    "Le PEG est compté à sa quantité actuelle sur toute la période ; les turbos au prix de tes ordres."
)
