import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from patrimoine import ui
from patrimoine.analytics import BENCHMARKS, kind_of, region_of

pos = ui.positions()
inv = ui.invested()
if pos.empty or inv.empty:
    st.warning("Aucune position : lance `uv run patrimoine sync`.", icon=":material/info:")
    st.stop()
st_ = ui.invested_stats()

with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader("Portefeuille", icon=":material/candlestick_chart:")
    period = st.segmented_control("Période", ["3 mois", "6 mois", "1 an", "Tout"], default="1 an",
                                  label_visibility="collapsed")
with st.expander("Lexique : PMP, TWR, TRI, plus-values…", icon=":material/help:"):
    st.markdown(ui.GLOSSARY)

end = inv.index.max()
start = {"3 mois": end - pd.DateOffset(months=3), "6 mois": end - pd.DateOffset(months=6),
         "1 an": end - pd.DateOffset(years=1)}.get(period, inv.index.min())

# ---------- KPIs (Trade Republic: compte-titres + PEA) ----------
st.caption("Performance des placements Trade Republic (compte-titres et PEA). Le PEG n'a pas d'historique d'achat.")
with st.container(horizontal=True):
    st.metric("Valeur", ui.eur(st_["valeur"]), ui.eur(st_["valeur"] - inv.value.asof(end - pd.Timedelta(days=30)),
              sign=True) + " sur 30 j", border=True,
              chart_data=inv.value[inv.index >= start].resample("W").last().tolist(), chart_type="area")
    st.metric("Net investi", ui.eur(st_["net_investi"]), border=True,
              help="Achats moins ventes : l'argent que tu as laissé en bourse.")
    st.metric("Gain total", ui.eur(st_["gain_total"], sign=True), ui.pct(st_["gain_total"] / st_["net_investi"]),
              border=True, help="Valeur moins net investi : plus-values latentes et réalisées, Saveback compris.")
    st.metric("TRI annuel", ui.pct(st_["tri"]), border=True,
              help="Rendement annuel de ton argent, compte tenu des dates de tes versements.")
with st.container(horizontal=True):
    st.metric("Performance annualisée (TWR)", ui.pct(st_["twr_annuel"]), border=True,
              help="Performance des placements eux-mêmes, à comparer aux indices.")
    st.metric("Depuis le 1er janvier", ui.pct(st_["twr_ytd"]), border=True)
    st.metric("Sur 1 an", ui.pct(st_["twr_1an"]), border=True)
    st.metric("Volatilité", ui.pct(st_["volatilite"], sign=False), "MSCI World ≈ 15 %", delta_color="off", border=True)
    st.metric("Pire baisse", ui.pct(st_["pire_baisse"]), f"actuellement {ui.pct(st_['baisse_actuelle'])}",
              delta_color="off", border=True)

# ---------- value vs invested vs index ----------
col1, col2 = st.columns([3, 2])
with col1, st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown("**Valeur, argent investi et comparaison**")
        bench_name = st.selectbox("Indice", list(BENCHMARKS), label_visibility="collapsed", width=180)
    bench = ui.benchmark(BENCHMARKS[bench_name])
    frame = pd.DataFrame({"Ton portefeuille": inv.value, "Net investi": inv.net_invested})
    if bench is not None:
        frame[f"Mêmes versements sur le {bench_name}"] = bench
    frame = frame[frame.index >= start].reset_index(names="date").melt("date", var_name="série", value_name="eur")
    fig = px.line(frame, x="date", y="eur", color="série", labels={"eur": "", "date": "", "série": ""},
                  color_discrete_sequence=[ui.CATEGORICAL[0], ui.OTHER, ui.CATEGORICAL[1]])
    fig.update_traces(line=dict(width=2), hovertemplate="%{y:,.0f} €")
    fig.for_each_trace(lambda t: t.update(line_dash="dot") if t.name == "Net investi" else None)
    ui.plotly_layout(fig, 360)
    fig.update_yaxes(ticksuffix=" €", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch")
    if bench is not None:
        gap = inv.value.iloc[-1] - bench.iloc[-1]
        st.caption(f"Si chaque achat et chaque vente avait porté sur le {bench_name}, tu aurais "
                   f"{ui.eur(bench.iloc[-1])} aujourd'hui : ton choix de titres fait {ui.eur(gap, sign=True)}.")

with col2, st.container(border=True):
    st.markdown("**Baisse depuis le plus haut**")
    dd = inv.loc[inv.index >= start, ["drawdown"]].reset_index(names="date")
    fig = px.area(dd, x="date", y="drawdown", labels={"drawdown": "", "date": ""})
    fig.update_traces(line=dict(width=1.5, color=ui.CATEGORICAL[7]), fillcolor="rgba(227,73,72,0.18)",
                      hovertemplate="%{y:.1%}")
    ui.plotly_layout(fig, 360)
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, width="stretch")

# ---------- positions ----------
with st.container(border=True):
    scope = st.segmented_control("Compte", ["Tout", "PEA", "Compte-titres", "PEG Airbus"], default="Tout",
                                 key="scope")
    view = pos if scope in (None, "Tout") else pos[pos.account == scope]
    view = view.assign(weight=view.value / view.value.sum(), kind=view.name.map(kind_of))
    view.loc[view.account == "PEG Airbus", "kind"] = "Action"
    st.dataframe(
        view[["name", "account", "kind", "quantity", "unit_cost", "price", "value", "gain", "gain_pct", "weight"]],
        hide_index=True, width="stretch",
        column_config={
            "name": st.column_config.TextColumn("Titre", width="large"), "account": "Compte", "kind": "Type",
            "quantity": st.column_config.NumberColumn("Quantité", format="%.4g"),
            "unit_cost": st.column_config.NumberColumn("PMP", format="%.2f €",
                                                       help="Prix moyen payé par titre, frais inclus."),
            "price": st.column_config.NumberColumn("Cours", format="%.2f €"),
            "value": st.column_config.NumberColumn("Valeur", format="%.0f €"),
            "gain": st.column_config.NumberColumn("+/- latente", format="%+.0f €"),
            "gain_pct": st.column_config.NumberColumn("%", format="percent"),
            "weight": st.column_config.ProgressColumn("Poids", format="percent", min_value=0, max_value=1),
        },
    )

cols = st.columns(3)
for col, (title, key) in zip(cols, [("Par type", "kind"), ("Par zone", "region"), ("Par compte", "account")]):
    with col, st.container(border=True):
        st.markdown(f"**{title}**")
        g = view.assign(region=view.name.map(region_of)).groupby(key)["value"].sum().sort_values()
        fig = go.Figure(go.Bar(x=g.values, y=g.index, orientation="h", marker_color=ui.CATEGORICAL[0],
                               text=[f"{v / g.sum():.0%}" for v in g.values], textposition="outside", cliponaxis=False,
                               hovertemplate="%{x:,.0f} €<extra></extra>"))
        ui.plotly_layout(fig, 70 + 40 * len(g))
        fig.update_xaxes(ticksuffix=" €", tickformat=",.0f")
        st.plotly_chart(fig, width="stretch")

# ---------- one line in detail ----------
with st.container(border=True):
    st.markdown("**Détail d'une ligne**")
    names = dict(zip(pos.name, pos["isin"]))
    choice = st.selectbox("Ligne", list(names), label_visibility="collapsed")
    isin = names[choice]
    px_s = ui.prices(isin)
    tr = ui.trades(isin)
    row = pos[pos["isin"] == isin].iloc[0]
    with st.container(horizontal=True):
        st.metric("Cours", ui.eur(row.price, 2), border=True)
        st.metric("PMP", ui.eur(row.unit_cost, 2) if row.unit_cost == row.unit_cost and row.unit_cost else "–",
                  border=True)
        st.metric("+/- latente", ui.eur(row.gain, sign=True) if row.gain == row.gain else "–",
                  ui.pct(row.gain_pct) if row.gain_pct == row.gain_pct else None, border=True)
        for label, days in (("1 mois", 30), ("1 an", 365)):
            past = px_s[px_s.index <= px_s.index.max() - pd.Timedelta(days=days)] if not px_s.empty else px_s
            st.metric(f"Cours sur {label}", ui.pct(px_s.iloc[-1] / past.iloc[-1] - 1) if len(past) else "–", border=True)
    if not px_s.empty:
        s = px_s[px_s.index >= min(start, tr.date.min() if not tr.empty else start)]
        fig = go.Figure(go.Scatter(x=s.index, y=s.values, mode="lines", name="Cours",
                                   line=dict(width=2, color=ui.CATEGORICAL[0]), hovertemplate="%{y:.2f} €"))
        if row.unit_cost == row.unit_cost and row.unit_cost:
            fig.add_hline(y=row.unit_cost, line_dash="dot", line_color=ui.OTHER, annotation_text="PMP",
                          annotation_position="top left")
        for flow, name, color, symbol in (("achat_titre", "Achat", ui.CATEGORICAL[5], "triangle-up"),
                                          ("vente_titre", "Vente", ui.CATEGORICAL[7], "triangle-down")):
            t = tr[(tr.flow == flow) & (tr.date >= s.index.min())]
            if not t.empty:
                fig.add_trace(go.Scatter(x=t.date, y=s.reindex(t.date, method="ffill"), mode="markers", name=name,
                                         marker=dict(size=11, color=color, symbol=symbol,
                                                     line=dict(width=2, color="white")),
                                         customdata=t[["quantity", "amount"]],
                                         hovertemplate="%{customdata[0]:.4g} titres · %{customdata[1]:,.0f} €<extra>"
                                                       + name + "</extra>"))
        ui.plotly_layout(fig, 320)
        fig.update_layout(hovermode="closest")
        fig.update_yaxes(ticksuffix=" €")
        st.plotly_chart(fig, width="stretch")
        st.caption("Cours historiques Yahoo, remis à l'échelle après une division d'actions.")

# ---------- every line ever held ----------
hist_lines = ui.lines()
col1, col2 = st.columns([2, 3])
with col1, st.container(border=True):
    st.markdown("**Gain par ligne, depuis le début**")
    g = hist_lines.assign(label=hist_lines.name.str.slice(0, 28)).groupby("label")["gain"].sum().sort_values()
    g = pd.concat([g.head(8), g.tail(8)]).drop_duplicates()
    fig = go.Figure(go.Bar(x=g.values, y=g.index, orientation="h",
                           marker_color=[ui.CATEGORICAL[5] if v >= 0 else ui.CATEGORICAL[7] for v in g.values],
                           hovertemplate="%{x:+,.0f} €<extra></extra>"))
    ui.plotly_layout(fig, 60 + 26 * len(g))
    fig.update_xaxes(ticksuffix=" €", tickformat="+,.0f")
    st.plotly_chart(fig, width="stretch")
with col2, st.container(border=True):
    st.markdown("**Toutes les lignes détenues**")
    st.dataframe(hist_lines[["name", "account", "kind", "open", "invested", "received", "value", "gain", "gain_pct",
                             "tri", "since", "days"]], hide_index=True, width="stretch", height=60 + 26 * len(g),
                 column_config={
                     "name": st.column_config.TextColumn("Titre", width="medium"), "account": "Compte", "kind": "Type",
                     "open": st.column_config.CheckboxColumn("En cours"),
                     "invested": st.column_config.NumberColumn("Investi", format="%.0f €"),
                     "received": st.column_config.NumberColumn("Récupéré", format="%.0f €"),
                     "value": st.column_config.NumberColumn("Valeur", format="%.0f €"),
                     "gain": st.column_config.NumberColumn("Gain", format="%+.0f €"),
                     "gain_pct": st.column_config.NumberColumn("%", format="percent"),
                     "tri": st.column_config.NumberColumn("TRI", format="percent",
                                                          help="Rendement annualisé (vide si détenu trop peu de temps)."),
                     "since": st.column_config.DateColumn("Depuis", format="DD/MM/YYYY"),
                     "days": st.column_config.NumberColumn("Jours"),
                 })

col1, col2 = st.columns(2)
with col1, st.container(border=True):
    st.markdown("**Argent investi chaque mois** (achats moins ventes)")
    m = inv.flow.resample("ME").sum()
    m.index = m.index.to_period("M").to_timestamp()
    m = m[m.index >= start.to_period("M").to_timestamp()]
    fig = go.Figure(go.Bar(x=[ui.short_month(i) for i in m.index], y=m.values,
                           marker_color=[ui.CATEGORICAL[0] if v >= 0 else ui.CATEGORICAL[1] for v in m.values],
                           hovertemplate="%{y:+,.0f} €<extra></extra>"))
    ui.plotly_layout(fig, 280)
    fig.update_yaxes(ticksuffix=" €", tickformat=",.0f")
    fig.update_xaxes(type="category")
    st.plotly_chart(fig, width="stretch")
with col2, st.container(border=True):
    st.markdown("**Plus-values réalisées par année**")
    real = ui.realised()
    if not real.empty:
        y = real.assign(year=real.date.dt.year.astype(str)).groupby(["year", "account"], as_index=False)["gain"].sum()
        fig = px.bar(y, x="year", y="gain", color="account", barmode="group", labels={"gain": "", "year": "",
                                                                                     "account": ""})
        fig.update_traces(hovertemplate="%{y:+,.0f} €")
        ui.plotly_layout(fig, 280)
        fig.update_yaxes(ticksuffix=" €", tickformat=",.0f", zeroline=True)
        fig.update_xaxes(type="category")
        st.plotly_chart(fig, width="stretch")

st.caption("Cours Yahoo Finance (clôture de la veille), convertis en euros. Turbos valorisés au prix de tes ordres.")
