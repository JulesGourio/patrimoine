import calendar

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from patrimoine import queries, ui
from patrimoine.analytics import recurring
from patrimoine.categories import SPENDING

df = ui.spending()
if df.empty:
    st.warning("Aucune dépense importée.", icon=":material/info:")
    st.stop()

with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader("Dépenses", icon=":material/receipt_long:")
    period = st.segmented_control("Période", ["3 mois", "6 mois", "12 mois", "Tout"], default="12 mois",
                                  label_visibility="collapsed")
    accounts = st.multiselect("Comptes", sorted(df.account.dropna().unique()), placeholder="Tous les comptes",
                              label_visibility="collapsed")

today = pd.Timestamp.today().normalize()
this_month = today.to_period("M").to_timestamp()
months = {"3 mois": 3, "6 mois": 6, "12 mois": 12}.get(period)
start = this_month - pd.DateOffset(months=months) if months else df.month.min()
base = df[df.account.isin(accounts)] if accounts else df
view = base[base.month >= start]
complete = view[view.month < this_month]

monthly = view.groupby("month")["amount"].sum()
full = monthly[monthly.index < this_month]
avg = full.mean() if not full.empty else None
current = monthly.get(this_month, 0.0)
variable = complete[~complete.category.isin(ui.FIXED)].groupby("month")["amount"].sum()
cur_variable = view[(view.month == this_month) & ~view.category.isin(ui.FIXED)].amount.sum()
bal = ui.monthly_balance()
bal_full = bal[(bal.index < this_month) & (bal.index >= start)]
spent_lines = view[view.amount > 0]

with st.container(horizontal=True):
    st.metric("Ce mois-ci", ui.eur(current), ui.eur(current - avg, sign=True) + " vs moyenne" if avg else None,
              delta_color="inverse", border=True,
              help=f"Au {today.day} du mois ; au même rythme, il finirait vers "
                   f"{ui.eur(current / today.day * today.days_in_month)}.")
    st.metric("Moyenne mensuelle", ui.eur(avg), border=True, chart_data=full.tolist(), chart_type="bar",
              help="Mois complets de la période.")
    st.metric("Dépenses du quotidien", ui.eur(variable.mean()) + " / mois" if len(variable) else "–",
              f"ce mois-ci {ui.eur(cur_variable)}", delta_color="off", border=True,
              help="Hors loyer, énergie, abonnements et impôts : ce sur quoi tu décides au jour le jour.")
    st.metric("Taux d'épargne", ui.pct(bal_full.epargne.sum() / bal_full.revenus.sum(), sign=False)
              if bal_full.revenus.sum() else "–", ui.eur(bal_full.epargne.mean()) + " / mois" if len(bal_full) else None,
              delta_color="off", border=True, help="(Revenus − dépenses) / revenus, sur les mois complets.")
    st.metric("Opérations", f"{len(spent_lines)}", f"panier moyen {ui.eur(spent_lines.amount.mean(), 2)}",
              delta_color="off", border=True)

by_cat = view.groupby("category")["amount"].sum().sort_values(ascending=False)
top = [c for c in by_cat.index if c != "Divers"][:7]
colors = dict(zip(top, ui.CATEGORICAL)) | {"Autres": ui.OTHER}
view = view.assign(groupe=view.category.where(view.category.isin(top), "Autres"))
order = top + ["Autres"]

# ---------- months, clickable ----------
with st.container(border=True):
    st.markdown("**Par mois** · clique sur une barre pour ouvrir le mois")
    per_month, labels = ui.month_axis(view.groupby(["month", "groupe"], as_index=False)["amount"].sum())
    fig = px.bar(per_month, x="mois", y="amount", color="groupe",
                 category_orders={"groupe": order, "mois": labels}, color_discrete_map=colors,
                 labels={"amount": "Montant", "groupe": "Catégorie", "mois": ""})
    fig.update_traces(hovertemplate="%{y:,.0f} €", marker_line_width=1, marker_line_color="white")
    if avg:
        fig.add_hline(y=avg, line_dash="dot", line_color=ui.OTHER, annotation_text=f"moyenne {ui.eur(avg)}",
                      annotation_position="top left")
    ui.plotly_layout(fig, 380)
    fig.update_layout(bargap=0.3)
    fig.update_yaxes(ticksuffix=" €", tickformat=",.0f")
    event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points", key="months")

points = event.selection.points if event and event.selection else []
months_list = sorted(view.month.unique(), reverse=True)
picked = None
if points:
    label = points[0].get("x")
    picked = next((m for m in months_list if ui.short_month(m) == label), None)

# ---------- one month ----------
with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown("**Le mois en détail**")
        chosen = st.selectbox("Mois", months_list, index=months_list.index(picked) if picked in months_list else 0,
                              format_func=ui.month_label, label_visibility="collapsed", width=200)
    m = view[view.month == chosen]
    m_total = m.amount.sum()
    prev = view[view.month == chosen - pd.DateOffset(months=1)].amount.sum()
    with st.container(horizontal=True):
        st.metric("Total", ui.eur(m_total), ui.eur(m_total - prev, sign=True) + " vs mois précédent",
                  delta_color="inverse", border=True)
        st.metric("Écart à la moyenne", ui.eur(m_total - avg, sign=True) if avg else "–", border=True)
        st.metric("Du quotidien", ui.eur(m[~m.category.isin(ui.FIXED)].amount.sum()), border=True,
                  help="Hors loyer, énergie, abonnements et impôts.")
        st.metric("Opérations", f"{(m.amount > 0).sum()}", border=True)
        daily_var = m[(m.amount > 0) & ~m.category.isin(ui.FIXED)]
        days_spent = daily_var.groupby(daily_var.date.dt.day)["amount"].sum()
        st.metric("Jour le plus cher", f"le {days_spent.idxmax()}" if not days_spent.empty else "–",
                  ui.eur(days_spent.max()) if not days_spent.empty else None, delta_color="off", border=True,
                  help="Hors loyer et factures.")

    c1, c2 = st.columns(2)
    with c1:
        st.caption("Calendrier des dépenses (hors loyer et factures)")
        daily = m[~m.category.isin(ui.FIXED)].groupby(m.date.dt.day)["amount"].sum()
        first_wd, n_days = calendar.monthrange(chosen.year, chosen.month)
        weeks = (first_wd + n_days + 6) // 7
        z = [[None] * 7 for _ in range(weeks)]
        text = [[""] * 7 for _ in range(weeks)]
        for d in range(1, n_days + 1):
            w, wd = divmod(first_wd + d - 1, 7)
            v = float(daily.get(d, 0.0))
            z[w][wd] = v
            text[w][wd] = f"<b>{d}</b><br>{v:.0f} €" if v else f"{d}"
        fig = go.Figure(go.Heatmap(z=z, text=text, texttemplate="%{text}", x=["lun.", "mar.", "mer.", "jeu.", "ven.",
                                   "sam.", "dim."], y=[f"s{i + 1}" for i in range(weeks)], xgap=4, ygap=4,
                                   colorscale=[[0, "#eef4fc"], [1, ui.CATEGORICAL[0]]], showscale=False,
                                   hovertemplate="%{text}<extra></extra>"))
        ui.plotly_layout(fig, 300)
        fig.update_yaxes(autorange="reversed", showticklabels=False)
        fig.update_xaxes(side="top")
        fig.update_layout(hovermode="closest", margin_r=0)
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.caption("Cumul dans le mois, comparé à un mois moyen")
        cum = m.groupby(m.date.dt.day)["amount"].sum().reindex(range(1, 32), fill_value=0).cumsum()
        last_day = today.day if chosen == this_month else calendar.monthrange(chosen.year, chosen.month)[1]
        typical = (complete.groupby([complete.month, complete.date.dt.day])["amount"].sum().unstack(fill_value=0)
                   .reindex(columns=range(1, 32), fill_value=0).cumsum(axis=1).mean())
        fig = go.Figure([
            go.Scatter(x=typical.index, y=typical.values, name="Mois moyen", line=dict(color=ui.OTHER, width=2,
                                                                                         dash="dot"),
                       hovertemplate="%{y:,.0f} €"),
            go.Scatter(x=cum.index[:last_day], y=cum.values[:last_day], name=ui.month_label(chosen),
                       line=dict(color=ui.CATEGORICAL[0], width=2.5), hovertemplate="%{y:,.0f} €"),
        ])
        ui.plotly_layout(fig, 300)
        fig.update_xaxes(dtick=5, ticksuffix=" ")
        fig.update_yaxes(ticksuffix=" €", tickformat=",.0f")
        st.plotly_chart(fig, width="stretch")

    c1, c2 = st.columns([2, 3])
    with c1:
        st.caption("Par catégorie, comparé à la moyenne")
        cat_m = m.groupby("category")["amount"].sum()
        cat_avg = complete.groupby(["month", "category"])["amount"].sum().unstack(fill_value=0).mean()
        comp = pd.DataFrame({"Ce mois": cat_m, "Moyenne": cat_avg}).fillna(0).sort_values("Ce mois")
        comp = comp[(comp["Ce mois"] > 0) | (comp["Moyenne"] > 20)]
        fig = go.Figure([
            go.Bar(y=comp.index, x=comp["Moyenne"], orientation="h", name="Moyenne mensuelle",
                   marker_color="rgba(138,137,131,0.45)", hovertemplate="%{x:,.0f} €"),
            go.Bar(y=comp.index, x=comp["Ce mois"], orientation="h", name=ui.month_label(chosen),
                   marker_color=ui.CATEGORICAL[0], hovertemplate="%{x:,.0f} €"),
        ])
        ui.plotly_layout(fig, 80 + 30 * len(comp))
        fig.update_layout(barmode="group", bargap=0.3, hovermode="y unified")
        fig.update_xaxes(ticksuffix=" €", tickformat=",.0f")
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.caption("Opérations du mois")
        st.dataframe(m.sort_values("date", ascending=False)[["date", "merchant", "category", "account", "amount"]],
                     hide_index=True, width="stretch", height=80 + 30 * max(len(comp), 8), column_config={
                         "date": st.column_config.DateColumn("Date", format="DD/MM"), "merchant": "Commerçant",
                         "category": "Catégorie", "account": "Compte",
                         "amount": st.column_config.NumberColumn("Montant", format="%.2f €")})

# ---------- income and savings (complete months only: the salary lands at the end of the month) ----------
col1, col2 = st.columns(2)
with col1, st.container(border=True):
    st.markdown("**Revenus, dépenses et épargne** · mois complets")
    b, labels = ui.month_axis(bal_full.reset_index(names="month"))
    long = b.melt(["month", "mois"], value_vars=["revenus", "depenses", "epargne"], var_name="série", value_name="eur")
    long["série"] = long["série"].map({"revenus": "Revenus", "depenses": "Dépenses", "epargne": "Épargne"})
    fig = px.bar(long, x="mois", y="eur", color="série", barmode="group", category_orders={"mois": labels},
                 labels={"eur": "", "mois": "", "série": ""},
                 color_discrete_map={"Revenus": ui.CATEGORICAL[0], "Dépenses": ui.CATEGORICAL[1],
                                     "Épargne": ui.CATEGORICAL[2]})
    fig.update_traces(hovertemplate="%{y:,.0f} €")
    ui.plotly_layout(fig, 320)
    fig.update_yaxes(ticksuffix=" €", tickformat=",.0f", zeroline=True)
    st.plotly_chart(fig, width="stretch")
    st.caption("Le mois en cours n'apparaît qu'une fois terminé : le salaire arrive en fin de mois.")
with col2, st.container(border=True):
    st.markdown("**Taux d'épargne** · mois complets")
    t, labels = ui.month_axis(bal_full[["taux"]].reset_index(names="month"))
    fig = px.line(t, x="mois", y="taux", markers=True, category_orders={"mois": labels}, labels={"taux": "", "mois": ""})
    fig.update_traces(line=dict(width=2, color=ui.CATEGORICAL[2]), marker=dict(size=8), hovertemplate="%{y:.0%}")
    if len(bal_full) and bal_full.revenus.sum():
        mean_rate = bal_full.epargne.sum() / bal_full.revenus.sum()
        fig.add_hline(y=mean_rate, line_dash="dot", line_color=ui.OTHER,
                      annotation_text=f"moyenne {ui.pct(mean_rate, sign=False)}", annotation_position="bottom left")
    ui.plotly_layout(fig, 320)
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    st.plotly_chart(fig, width="stretch")

# ---------- categories over time ----------
with st.container(border=True):
    st.markdown("**Catégories mois par mois**")
    grid = view.pivot_table(index="category", columns="month", values="amount", aggfunc="sum", fill_value=0)
    grid = grid.loc[grid.sum(axis=1).sort_values(ascending=False).index]
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=[ui.short_month(c) for c in grid.columns], y=grid.index, xgap=3, ygap=3, showscale=False,
        colorscale=[[0, "#f5f7fb"], [0.15, "#dbe8f8"], [1, ui.CATEGORICAL[0]]],
        text=[[f"{v:.0f}" if v >= 1 else "" for v in row] for row in grid.values], texttemplate="%{text}",
        hovertemplate="%{y} · %{x} : %{z:,.0f} €<extra></extra>"))
    ui.plotly_layout(fig, 60 + 28 * len(grid))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(side="top")
    fig.update_layout(hovermode="closest", margin_r=0)
    st.plotly_chart(fig, width="stretch")
    st.caption("Montants en euros ; plus la case est foncée, plus la dépense est forte.")

col1, col2 = st.columns([3, 2])
with col1, st.container(border=True):
    st.markdown("**Cumul de l'année, comparé à l'an dernier**")
    y = today.year
    cum = []
    for year in (y - 1, y):
        d = base[(base.date.dt.year == year)].groupby(base.date.dt.dayofyear)["amount"].sum().sort_index().cumsum()
        if not d.empty:
            cum.append(pd.DataFrame({"jour": d.index, "cumul": d.values, "année": str(year)}))
    if cum:
        c = pd.concat(cum)
        c["date"] = pd.Timestamp(y, 1, 1) + pd.to_timedelta(c.jour - 1, unit="D")
        fig = px.line(c, x="date", y="cumul", color="année", labels={"cumul": "", "date": "", "année": ""},
                      color_discrete_map={str(y - 1): ui.OTHER, str(y): ui.CATEGORICAL[0]})
        fig.update_traces(line=dict(width=2), hovertemplate="%{y:,.0f} €")
        ui.plotly_layout(fig, 300)
        fig.update_yaxes(ticksuffix=" €", tickformat=",.0f")
        fig.update_xaxes(tickformat="%b", dtick="M1")
        st.plotly_chart(fig, width="stretch")
        st.caption("L'historique CMB commence en août 2025 : l'an dernier est incomplet avant cette date.")
with col2, st.container(border=True):
    st.markdown("**Par jour de la semaine** · hors loyer et factures")
    names = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
    day_lines = spent_lines[~spent_lines.category.isin(ui.FIXED)]
    weeks_n = max((view.date.max() - view.date.min()).days / 7, 1)
    w = day_lines.groupby(day_lines.date.dt.dayofweek)["amount"].sum().reindex(range(7), fill_value=0) / weeks_n
    fig = go.Figure(go.Bar(x=names, y=w.values, marker_color=ui.CATEGORICAL[0],
                           hovertemplate="%{y:,.0f} € en moyenne<extra></extra>"))
    ui.plotly_layout(fig, 300)
    fig.update_yaxes(ticksuffix=" €")
    st.plotly_chart(fig, width="stretch")

col1, col2 = st.columns(2)
with col1, st.container(border=True):
    rec = recurring(base)
    st.markdown(f"**Dépenses récurrentes** · {ui.eur(rec.annual.sum() if not rec.empty else 0)} par an")
    st.dataframe(rec[["merchant", "category", "median", "months", "annual"]] if not rec.empty else rec,
                 hide_index=True, width="stretch", column_config={
                     "merchant": "Commerçant", "category": "Catégorie",
                     "median": st.column_config.NumberColumn("Montant habituel", format="%.2f €"),
                     "months": st.column_config.NumberColumn("Mois"),
                     "annual": st.column_config.NumberColumn("Par an", format="%.0f €")})
    st.caption("Payés au moins 3 mois, pour un montant stable, et encore actifs.")
with col2, st.container(border=True):
    st.markdown("**Où tu dépenses le plus** · hors loyer et factures")
    merchants = (view[~view.category.isin(ui.FIXED)].groupby("merchant")
                 .agg(total=("amount", "sum"), fois=("amount", "size"), categorie=("category", "first"))
                 .sort_values("total", ascending=False).head(15).reset_index())
    st.dataframe(merchants, hide_index=True, width="stretch", column_config={
        "merchant": "Commerçant", "categorie": "Catégorie", "fois": st.column_config.NumberColumn("Achats"),
        "total": st.column_config.NumberColumn("Total", format="%.0f €")})

with st.container(border=True):
    st.markdown("**À classer** · les lignes en « Divers »")
    st.caption("Choisis une catégorie. « Tout ce commerçant » l'apprend comme règle pour toutes ses lignes, "
               "passées et futures.")
    todo = view[view.category == "Divers"][["id", "date", "merchant", "amount", "category"]].copy()
    todo["tout"] = False
    edited = st.data_editor(
        todo, hide_index=True, width="stretch", key="todo", disabled=["id", "date", "merchant", "amount"],
        column_order=["date", "merchant", "amount", "category", "tout"],
        column_config={
            "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
            "merchant": "Commerçant",
            "amount": st.column_config.NumberColumn("Montant", format="%.2f €"),
            "category": st.column_config.SelectboxColumn("Catégorie", options=SPENDING, required=True),
            "tout": st.column_config.CheckboxColumn("Tout ce commerçant"),
        },
    )
    changed = edited[(edited.category != todo.category) | edited.tout]
    if st.button(f"Enregistrer ({len(changed)})", icon=":material/save:", disabled=changed.empty, type="primary"):
        con = ui.connect()
        try:
            for r in changed.itertuples():
                queries.set_category(con, r.id, r.category, merchant_rule=r.merchant if r.tout else None)
        finally:
            con.close()
        st.cache_data.clear()
        st.toast(f"{len(changed)} ligne(s) reclassée(s)", icon=":material/check:")
        st.rerun()
