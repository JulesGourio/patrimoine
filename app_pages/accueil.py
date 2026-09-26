import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from patrimoine import ui
from patrimoine.analytics import kind_of

hist = ui.history()
if hist.empty:
    st.warning("Pas encore d'historique : lance `uv run patrimoine sync`.", icon=":material/info:")
    st.stop()

ORDER = ["PEA", "Compte-titres", "PEG Airbus", "Livret CMB", "Livret Jeune", "Trade Republic espèces", "CMB courant"]
GROUP = {"PEA": "Bourse", "Compte-titres": "Bourse", "PEG Airbus": "Épargne salariale", "Livret CMB": "Livrets",
         "Livret Jeune": "Livrets", "Trade Republic espèces": "Liquidités", "CMB courant": "Liquidités"}

with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader("Patrimoine", icon=":material/account_balance:")
    period = st.segmented_control("Période", ["3 mois", "6 mois", "1 an", "Tout"], default="1 an",
                                  label_visibility="collapsed")
    with_peg = st.toggle("Compter le PEG", value=True)

if not with_peg:
    hist = hist[hist.account_id != "peg_airbus"]
total = hist.groupby("date")["value"].sum()
today = total.index.max()
start = {"3 mois": today - pd.DateOffset(months=3), "6 mois": today - pd.DateOffset(months=6),
         "1 an": today - pd.DateOffset(years=1)}.get(period, total.index.min())


def at(d):
    return total.asof(d) if d >= total.index.min() else None


now = total.iloc[-1]
jan1 = at(pd.Timestamp(today.year - 1, 12, 31))
bal = ui.monthly_balance()
full = bal[bal.index < pd.Timestamp.today().to_period("M").to_timestamp()].tail(12)
last = hist[hist.date == today]
by_group = last.assign(g=last.account.map(GROUP)).groupby("g")["value"].sum()

with st.container(horizontal=True):
    st.metric("Patrimoine net", ui.eur(now), ui.eur(now - at(today - pd.Timedelta(days=30)), sign=True) + " sur 30 j",
              border=True, chart_data=total[total.index >= start].resample("W").last().tolist(), chart_type="area")
    st.metric("Depuis le 1er janvier", ui.eur(now - jan1, sign=True) if jan1 else "–",
              ui.pct(now / jan1 - 1) if jan1 else None, border=True)
    st.metric("Sur 1 an", ui.eur(now - at(today - pd.DateOffset(years=1)), sign=True)
              if at(today - pd.DateOffset(years=1)) else "–", border=True)
    st.metric("Épargne moyenne", ui.eur(full.epargne.mean()) + " / mois", ui.pct(full.epargne.sum() / full.revenus.sum(),
              sign=False) + " des revenus" if full.revenus.sum() else None, delta_color="off", border=True,
              help="Revenus moins dépenses, moyenne des 12 derniers mois complets.")
    invested_now = by_group.get("Bourse", 0) + by_group.get("Épargne salariale", 0)
    st.metric("Part investie en actions", ui.pct(invested_now / now, sign=False), ui.eur(invested_now),
              delta_color="off", border=True, help="Compte-titres, PEA et PEG Airbus.")

col1, col2 = st.columns([3, 2])
with col1, st.container(border=True):
    st.markdown("**Évolution par compte**")
    view = hist[hist.date >= start]
    weekly = view.set_index("date").groupby("account").resample("W")["value"].last().reset_index()
    accounts = [a for a in ORDER if a in weekly.account.unique()]
    colors = dict(zip(ORDER, ui.CATEGORICAL))
    fig = px.area(weekly, x="date", y="value", color="account", category_orders={"account": accounts},
                  color_discrete_map=colors, labels={"value": "Valeur", "account": "Compte", "date": ""})
    fig.update_traces(line=dict(width=1.5), hovertemplate="%{y:,.0f} €")
    ui.plotly_layout(fig, 400)
    fig.update_yaxes(ticksuffix=" €", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)

with col2, st.container(border=True):
    st.markdown("**Comptes**")
    d30, d365 = today - pd.Timedelta(days=30), today - pd.DateOffset(years=1)
    table = []
    for acc in accounts:
        s = hist[hist.account == acc].set_index("date")["value"]
        v = s.iloc[-1]
        table.append({"Compte": acc, "Valeur": v, "Part": v / now,
                      "30 j": v - s.asof(d30) if d30 >= s.index.min() else None,
                      "1 an": v - s.asof(d365) if d365 >= s.index.min() else None})
    table = pd.DataFrame(table)
    total_row = {"Compte": "Total", "Valeur": table.Valeur.sum(), "Part": 1.0,
                 "30 j": table["30 j"].sum(min_count=1), "1 an": table["1 an"].sum(min_count=1)}
    table = pd.concat([table, pd.DataFrame([total_row])], ignore_index=True)
    st.dataframe(table, hide_index=True, width="stretch", height=38 * (len(table) + 1), column_config={
        "Valeur": st.column_config.NumberColumn(format="%.0f €"),
        "Part": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
        "30 j": st.column_config.NumberColumn(format="%+.0f €"), "1 an": st.column_config.NumberColumn(format="%+.0f €"),
    })
    st.caption("La ligne Total additionne tous les comptes affichés.")

col1, col2 = st.columns(2)
with col1, st.container(border=True):
    st.markdown("**Répartition par type d'actif**")
    pos = ui.positions()
    alloc = {"Livrets": by_group.get("Livrets", 0.0), "Liquidités": by_group.get("Liquidités", 0.0)}
    if not pos.empty:
        for r in pos.itertuples():
            if r.account == "PEG Airbus" and not with_peg:
                continue
            k = "Actions (PEG Airbus)" if r.account == "PEG Airbus" else kind_of(r.name)
            alloc[k] = alloc.get(k, 0.0) + (r.value or 0)
    a = pd.Series(alloc).sort_values()
    a = a[a > 0]
    fig = go.Figure(go.Bar(x=a.values, y=a.index, orientation="h", marker_color=ui.CATEGORICAL[0],
                           text=[f"{v / a.sum():.0%}".replace(".", ",") for v in a.values], textposition="outside",
                           cliponaxis=False, hovertemplate="%{x:,.0f} €<extra></extra>"))
    ui.plotly_layout(fig, 60 + 42 * len(a))
    fig.update_xaxes(ticksuffix=" €", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)

with col2, st.container(border=True):
    st.markdown("**D'où vient la variation de chaque mois**")
    monthly = total.resample("ME").last()
    change = monthly.diff().dropna()
    change.index = change.index.to_period("M").to_timestamp()
    saving = bal.epargne.reindex(change.index).fillna(0.0)
    decomposition = pd.DataFrame({"Épargne du mois": saving, "Effet marché et autres": change - saving})
    this_month = pd.Timestamp.today().to_period("M").to_timestamp()
    decomposition = decomposition[(decomposition.index >= start.to_period("M").to_timestamp())
                                  & (decomposition.index < this_month)]
    long, labels = ui.month_axis(decomposition.reset_index(names="month")
                                 .melt("month", var_name="part", value_name="eur"))
    fig = px.bar(long, x="mois", y="eur", color="part", barmode="relative", category_orders={"mois": labels},
                 color_discrete_map={"Épargne du mois": ui.CATEGORICAL[2], "Effet marché et autres": ui.CATEGORICAL[0]},
                 labels={"eur": "", "mois": "", "part": ""})
    fig.update_traces(hovertemplate="%{y:+,.0f} €", marker_line_width=1, marker_line_color="white")
    ui.plotly_layout(fig, 60 + 42 * max(len(a), 5))
    fig.update_yaxes(ticksuffix=" €", tickformat=",.0f", zeroline=True)
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)
    st.caption("Mois complets. Épargne = revenus moins dépenses du mois ; le reste de la variation vient des "
               "marchés (et, avant août 2025, des comptes CMB dont l'historique manque).")

with st.container(border=True):
    st.markdown("**Patrimoine net et investissement Trade Republic**")
    inv = ui.invested()
    frame = pd.DataFrame({"Patrimoine net": total})
    if not inv.empty:
        frame["Valeur des placements"] = inv.value
        frame["Net investi en bourse"] = inv.net_invested
    frame = frame[frame.index >= start].resample("W").last().reset_index(names="date")
    long = frame.melt("date", var_name="série", value_name="eur")
    fig = px.line(long, x="date", y="eur", color="série", labels={"eur": "", "date": "", "série": ""},
                  color_discrete_sequence=[ui.CATEGORICAL[6], ui.CATEGORICAL[0], ui.OTHER])
    fig.update_traces(line=dict(width=2), hovertemplate="%{y:,.0f} €")
    ui.plotly_layout(fig, 320)
    fig.update_yaxes(ticksuffix=" €", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)

sync = ui.last_sync()
st.caption(
    f"Dernière synchronisation Trade Republic : {sync[:16].replace('T', ' ') if sync else 'jamais'} (UTC). "
    "PEG reconstitué depuis les relevés Amundi (ESOP converti en équivalent actions) ; l'historique CMB commence en août 2025."
)
