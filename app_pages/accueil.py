import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from patrimoine import ui
from patrimoine.analytics import kind_of
from patrimoine.categories import WINDFALLS

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
                                  label_visibility="collapsed", key="acc_period")
    with_peg = st.toggle("Compter le PEG", value=True, key="acc_with_peg")
    ui.reset_filters_button({"acc_period": "1 an", "acc_with_peg": True})

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

pos_all = ui.positions()
real = ui.realised()
income = ui.investment_income()
opens = ui.account_open_dates()

# Gain per wrapper (unrealised + realised), then gross/net of the tax due if withdrawn: PEA and PEG only owe
# social contributions (17,2 %) once past the 5-year mark; the compte-titres and interest owe the PFU (30 %).
PS, PFU = 0.172, 0.30
by_wrapper = (pos_all.groupby("account").gain.sum() if not pos_all.empty else pd.Series(dtype=float)).add(
    real.groupby("account").gain.sum() if not real.empty else pd.Series(dtype=float), fill_value=0.0)
gain_cto, gain_pea, gain_peg = (by_wrapper.get(a, 0.0) for a in ("Compte-titres", "PEA", "PEG Airbus"))
div_pea = income[(income.flow == "dividende") & (income.account == "PEA")].amount.sum() if not income.empty else 0.0
div_other = income[(income.flow == "dividende") & (income.account != "PEA")].amount.sum() if not income.empty else 0.0
interest_all = income[income.flow == "interets"].amount.sum() if not income.empty else 0.0

if not with_peg:
    gain_peg = 0.0
investment_gain = gain_cto + gain_pea + gain_peg + div_pea + div_other + interest_all
investment_gain_net = ((gain_cto + div_other + interest_all) * (1 - PFU) + (gain_pea + div_pea) * (1 - PS)
                       + gain_peg * (1 - PS))
tax_due = investment_gain - investment_gain_net

pea_open = opens.get("tr_pea")
pea_5y = pea_open and (today - pd.Timestamp(pea_open)).days >= 365.25 * 5

with st.container(horizontal=True):
    st.metric("Patrimoine total", ui.eur(now), ui.eur(now - at(today - pd.Timedelta(days=30)), sign=True) + " sur 30 j",
              border=True, chart_data=total[total.index >= start].resample("W").last().tolist(), chart_type="area",
              help="Somme de la valeur de tous tes comptes aujourd'hui, avant impôts (même total que la ligne "
                   "« Total » du tableau Comptes). Tu n'as pas de dette suivie.")
    st.metric("Après impôts si tout était vendu", ui.eur(now - tax_due), ui.eur(-tax_due, sign=True) + " d'impôts latents",
              delta_color="off", border=True,
              help="Patrimoine total moins l'impôt estimé sur tes gains si tu vendais et retirais tout aujourd'hui : "
                   "PFU 30 % sur le compte-titres, les dividendes hors PEA et les intérêts ; prélèvements sociaux "
                   "17,2 % sur les gains du PEA (plus de 5 ans) et du PEG. Les versements ne sont pas imposés.")
    st.metric("Depuis le 1er janvier", ui.eur(now - jan1, sign=True) if jan1 else "–",
              ui.pct(now / jan1 - 1) if jan1 else None, border=True)
    st.metric("Sur 1 an", ui.eur(now - at(today - pd.DateOffset(years=1)), sign=True)
              if at(today - pd.DateOffset(years=1)) else "–", border=True)
    st.metric("Épargne moyenne", ui.eur(full.epargne.mean()) + " / mois", ui.pct(full.epargne.sum() / full.revenus.sum(),
              sign=False) + " des revenus" if full.revenus.sum() else None, delta_color="off", border=True,
              help="Revenus moins dépenses, moyenne des 12 derniers mois complets. Les héritages et donations "
                   "n'en font pas partie : ils comptent dans le patrimoine, pas dans l'épargne.")

pea_note = ""
if pea_open:
    pea_note = (f" Le PEA a été ouvert le {pea_open[:10]} : " + ("plus de 5 ans, régime plein." if pea_5y else
                "moins de 5 ans, un retrait aujourd'hui serait en fait taxé à 30 % comme le compte-titres."))

with st.container(horizontal=True):
    invested_now = by_group.get("Bourse", 0) + by_group.get("Épargne salariale", 0)
    st.metric("Part investie en actions", ui.pct(invested_now / now, sign=False), ui.eur(invested_now),
              delta_color="off", border=True, help="Compte-titres, PEA et PEG Airbus.")
    st.metric("Gains d'investissement (brut)", ui.eur(investment_gain, sign=True),
              ui.eur(interest_all + div_pea + div_other, sign=True) + " d'intérêts et dividendes",
              delta_color="off", border=True,
              help="Avant impôt. Plus-values latentes et réalisées sur les actions (compte-titres, PEA, PEG "
                   "Airbus) et intérêts et dividendes perçus, depuis le début. Plus large que le « Gain total » "
                   "de l'onglet Portefeuille, qui ne compte que le compte-titres et le PEA. Le patrimoine total "
                   "inclut en plus l'argent que tu as épargné (versements, pas gains).")
    st.metric("Gains d'investissement (net d'impôt estimé)", ui.eur(investment_gain_net, sign=True),
              ui.eur(-tax_due, sign=True) + " de fiscalité", delta_color="off", border=True,
              help="Estimation à la sortie, au régime de chaque enveloppe : PEA (au-delà de 5 ans) et PEG ne "
                   "doivent que les prélèvements sociaux (17,2 %) ; compte-titres, dividendes hors PEA et "
                   f"intérêts sont au PFU (30 %).{pea_note}")



@st.cache_data(ttl="10m", show_spinner=False)
def week_news() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Alerts of the last 7 days and the followed members' trades filed in the last 7 days."""
    from patrimoine import politicians

    def load(con):
        alerts = pd.read_sql_query("SELECT triggered_at, message FROM alert_events WHERE triggered_at >= ?"
                                   " ORDER BY triggered_at DESC", con,
                                   params=((pd.Timestamp.today() - pd.Timedelta(days=7)).isoformat(),))
        return alerts, politicians.recent(con, 7, followed_only=True)

    return ui._load(load)


# ---------- this week, at a glance ----------
week_ago = today - pd.Timedelta(days=7)
w_total = now - at(week_ago) if at(week_ago) else None
movers = []
for r in pos_all.itertuples():
    if r.account == "PEG Airbus" and not with_peg:
        continue
    s_ = ui.prices(r.isin)
    if len(s_) > 6 and r.value:
        past = s_[s_.index <= week_ago]
        if len(past):
            movers.append((r.name, s_.iloc[-1] / past.iloc[-1] - 1, r.value * (1 - past.iloc[-1] / s_.iloc[-1])))
alerts_w, trades_w = week_news()
with st.container(border=True):
    st.markdown("**Cette semaine**")
    items = []
    if w_total is not None:
        market = sum(m[2] for m in movers)
        inc_all = ui.income()
        windfall = inc_all[(inc_all.date > week_ago) & inc_all.category.isin(WINDFALLS)].amount.sum()
        items.append(f"Patrimoine **{ui.eur(w_total, sign=True)}** ({ui.pct(w_total / (now - w_total))}) en 7 jours, "
                     f"dont {ui.eur(market, sign=True)} dus aux marchés sur tes lignes, "
                     + (f"{ui.eur(windfall, sign=True)} d'héritage ou de donation, " if windfall else "")
                     + f"et {ui.eur(w_total - market - windfall, sign=True)} d'argent entré ou sorti (salaire moins "
                     "dépenses ; les virements entre tes comptes ne comptent pas).")
    if movers:
        best = max(movers, key=lambda m: m[1])
        worst = min(movers, key=lambda m: m[1])
        items.append(f"Meilleure ligne : **{best[0]}** {ui.pct(best[1])} ({ui.eur(best[2], sign=True)}) ; "
                     f"moins bonne : **{worst[0]}** {ui.pct(worst[1])} ({ui.eur(worst[2], sign=True)}).")
    alerts_w = alerts_w[~alerts_w.message.str.startswith("Budget")]  # spending lives on the Dépenses page
    if not alerts_w.empty:
        items.append(f"{len(alerts_w)} alerte(s) : " + " ; ".join(alerts_w.message.str.split(" — ").str[0].head(3)) + ".")
    if not trades_w.empty:
        who = trades_w.groupby("name").ticker.agg(lambda x: ", ".join(sorted(set(x.dropna()))[:4]))
        items.append("Élus suivis : " + " ; ".join(f"**{n}** ({t or 'titres non cotés'})" for n, t in who.items())
                     + " — détail dans Investisseurs.")
    if pea_open and not pea_5y:
        five = pd.Timestamp(pea_open) + pd.DateOffset(years=5)
        items.append(f"PEA : 5 ans le {five:%d/%m/%Y}, n'y retire rien d'ici là.")
    for it in items:
        st.markdown(f"- {it}")

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
    tot_w = weekly.groupby("date")["value"].sum()
    fig.add_trace(go.Scatter(x=tot_w.index, y=tot_w.values, name="Total", mode="lines",
                             line=dict(color="#111827", width=2.5), hovertemplate="<b>%{y:,.0f} €</b>"))
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
    pos = pos_all
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
    windfall = bal.heritage.reindex(change.index).fillna(0.0)
    decomposition = pd.DataFrame({"Épargne du mois": saving, "Héritage et donations": windfall,
                                  "Effet marché et autres": change - saving - windfall})
    decomposition = decomposition[decomposition.index >= start.to_period("M").to_timestamp()]
    long, labels = ui.month_axis(decomposition.reset_index(names="month")
                                 .melt("month", var_name="part", value_name="eur"))
    fig = px.bar(long, x="mois", y="eur", color="part", barmode="relative", category_orders={"mois": labels},
                 color_discrete_map={"Épargne du mois": ui.CATEGORICAL[2], "Héritage et donations": ui.CATEGORICAL[3],
                                     "Effet marché et autres": ui.CATEGORICAL[0]},
                 labels={"eur": "", "mois": "", "part": ""})
    fig.update_traces(hovertemplate="%{y:+,.0f} €", marker_line_width=1, marker_line_color="white")
    ui.plotly_layout(fig, 60 + 42 * max(len(a), 5))
    fig.update_yaxes(ticksuffix=" €", tickformat=",.0f", zeroline=True)
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)
    st.caption("Mois en cours jusqu'à aujourd'hui. Épargne = revenus moins dépenses du mois, hors héritages et "
               "donations (montrés à part) ; le reste de la variation vient surtout des marchés.")

with st.container(border=True):
    st.markdown("**Patrimoine total et investissement Trade Republic**")
    inv = ui.invested()
    frame = pd.DataFrame({"Patrimoine total": total})
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
    "PEG reconstitué depuis les relevés Amundi (ESOP converti en équivalent actions) ; CMB depuis 2016 (exports CSV)."
)
