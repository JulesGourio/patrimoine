import calendar

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from patrimoine import queries, ui
from patrimoine.analytics import recurring
from patrimoine.categories import INCOME, SPENDING, normalize

df = ui.spending()
if df.empty:
    st.warning("Aucune dépense importée.", icon=":material/info:")
    st.stop()

ss = st.session_state
# A row picked in "Où tu dépenses le plus" or "Dépenses récurrentes" (previous run) searches that merchant. It has
# to be handled here, before the search box exists: a widget's value cannot be set once it is drawn.
for tbl in ("tbl_merchants", "tbl_recurring"):
    try:
        picked = list(ss[tbl]["selection"]["rows"])
    except (KeyError, TypeError):
        picked = []
    if picked and ss.get(f"_seen_{tbl}") != picked:
        tbl_names = ss.get(f"_{tbl}_names") or []
        if picked[0] < len(tbl_names):
            ss["dep_search"] = tbl_names[picked[0]]
            st.toast(f"Recherche « {tbl_names[picked[0]]} » ouverte en haut de la page", icon=":material/search:")
    ss[f"_seen_{tbl}"] = picked

with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader("Dépenses", icon=":material/receipt_long:")
    period = st.segmented_control("Période", ["3 mois", "6 mois", "12 mois", "Tout"], default="12 mois",
                                  label_visibility="collapsed", key="dep_period")
    categories = st.multiselect("Catégories", [c for c in SPENDING if c in set(df.category)],
                                placeholder="Toutes les catégories", label_visibility="collapsed",
                                key="dep_categories", width=200)
    accounts = st.multiselect("Comptes", sorted(df.account.dropna().unique()), placeholder="Tous les comptes",
                              label_visibility="collapsed", key="dep_accounts", width=180)
    search = st.text_input("Rechercher", key="dep_search", placeholder="Rechercher : commerçant, libellé, montant…",
                           label_visibility="collapsed", icon=":material/search:", width=220)
    ui.reset_filters_button({"dep_period": "12 mois", "dep_categories": [], "dep_accounts": [], "dep_search": ""},
                            pop=["dep_month", "dep_cat", "dep_day"])

today = pd.Timestamp.today().normalize()
this_month = today.to_period("M").to_timestamp()
months = {"3 mois": 3, "6 mois": 6, "12 mois": 12}.get(period)
start = this_month - pd.DateOffset(months=months) if months else df.month.min()
base = df[df.account.isin(accounts)] if accounts else df
base = base[base.category.isin(categories)] if categories else base
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
bal_view = bal[bal.index >= start]  # charts: the month in progress too (averages stay on complete months)
spent_lines = view[view.amount > 0]
salaries = bal[(bal.index < this_month) & (bal.salaire > 0)].salaire
inc = ui.income()
last12_sal = salaries[salaries.index >= this_month - pd.DateOffset(months=12)]


# ---------- search: every period, the account filter only ----------
def matches(lines: pd.DataFrame, q: str) -> pd.DataFrame:
    """Lines whose merchant, label or category contain every word of ``q`` (accents and case ignored); a number
    also matches an amount within 1 euro ("42" finds 41,90 €)."""
    hay = (lines.merchant.fillna("") + " " + lines.label.fillna("") + " " + lines.category.fillna("")).map(normalize)
    mask = pd.Series(True, index=lines.index)
    for word in q.split():
        try:
            amount = float(word.replace(",", ".").replace("€", ""))
        except ValueError:
            amount = None
        hit = hay.str.contains(normalize(word).strip(), regex=False)
        if amount is not None:
            hit |= (lines.amount.abs() - amount).abs() <= 1
        mask &= hit
    return lines[mask]


if search.strip():
    sp_pool = df[df.account.isin(accounts)] if accounts else df
    in_pool = inc[inc.account.isin(accounts)] if accounts else inc
    found_sp = matches(sp_pool, search.strip()).assign(sens="Dépense", signed=lambda d: -d.amount)
    found_in = matches(in_pool, search.strip()).assign(sens="Revenu", signed=lambda d: d.amount)
    found = pd.concat([found_sp, found_in]).sort_values("date", ascending=False)
    # The figures follow what was found: spending if any, income otherwise (a search for the employer).
    focus = found_sp if not found_sp.empty else found_in
    with st.container(border=True):
        parts = []
        if not found_sp.empty:
            parts.append(f"{ui.eur(found_sp.amount.sum(), 2)} dépensés")
        if not found_in.empty:
            parts.append(f"{ui.eur(found_in.amount.sum(), 2)} reçus")
        st.markdown(f"**Recherche « {search.strip()} »** · {len(found)} opération(s) sur tout l'historique"
                    + (" · " + ", ".join(parts) if parts else ""))
        if found.empty:
            st.caption("Rien trouvé. La recherche porte sur les dépenses et les revenus : commerçant ou origine, "
                       "libellé bancaire, catégorie et montant (à 1 € près).")
        else:
            c1, c2 = st.columns([2, 3])
            with c1:
                fm = focus.groupby("month")["amount"].sum()
                first, last = focus.date.min(), focus.date.max()
                n_months = max(len(pd.period_range(first, today, freq="M")), 1)
                with st.container(horizontal=True):
                    st.metric("Par mois", ui.eur(fm.sum() / n_months), border=True,
                              help="Total divisé par le nombre de mois depuis la première opération.")
                    st.metric("Moyenne", ui.eur(focus.amount.mean()), border=True)
                    st.metric("12 mois", ui.eur(focus[focus.date >= today - pd.DateOffset(years=1)].amount.sum()),
                              border=True)
                fmf, flabels = ui.month_axis(fm.reset_index())
                fig = px.bar(fmf, x="mois", y="amount", category_orders={"mois": flabels},
                             labels={"amount": "", "mois": ""})
                fig.update_traces(marker_color=ui.CATEGORICAL[1] if focus is found_sp else ui.CATEGORICAL[0],
                                  hovertemplate="%{x} : %{y:,.2f} €<extra></extra>")
                ui.keep_months(fig, flabels)
                ui.plotly_layout(fig, 220)
                fig.update_yaxes(ticksuffix=" €", tickformat=",.0f")
                st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)
                st.caption(f"{'Dépenses' if focus is found_sp else 'Revenus'} du {first:%d/%m/%Y} au {last:%d/%m/%Y}.")
            with c2:
                st.dataframe(found[["date", "sens", "merchant", "category", "account", "signed", "label"]],
                             hide_index=True, width="stretch", height=380, column_config={
                                 "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"), "sens": "Sens",
                                 "merchant": "Commerçant / origine", "category": "Catégorie", "account": "Compte",
                                 "signed": st.column_config.NumberColumn("Montant", format="%+.2f €"),
                                 "label": st.column_config.TextColumn("Libellé bancaire", width="large")})

with st.container(horizontal=True):
    st.metric("Ce mois-ci", ui.eur(current), ui.eur(current - avg, sign=True) + " vs moyenne" if avg else None,
              delta_color="inverse", border=True, height="stretch",
              help=f"Au {today.day} du mois ; au même rythme, il finirait vers "
                   f"{ui.eur(current / today.day * today.days_in_month)}.")
    st.metric("Moyenne mensuelle", ui.eur(avg), border=True, height="stretch", chart_data=full.tolist(), chart_type="bar",
              help="Mois complets de la période.")
    st.metric("Dépenses du quotidien", ui.eur(variable.mean()) + " / mois" if len(variable) else "–",
              f"ce mois-ci {ui.eur(cur_variable)}", delta_color="off", border=True, height="stretch",
              help="Hors loyer, énergie, abonnements et impôts : ce sur quoi tu décides au jour le jour.")
    st.metric("Salaire net", ui.eur(salaries.iloc[-1]) if len(salaries) else "–",
              f"moyenne 12 mois {ui.eur(last12_sal.mean())}" if len(last12_sal) else None, delta_color="off",
              border=True, height="stretch", chart_data=last12_sal.tolist(), chart_type="bar",
              help="Dernier salaire versé (mois complets) et moyenne des 12 derniers mois, primes comprises.")
    st.metric("Taux d'épargne", ui.pct(bal_full.epargne.sum() / bal_full.revenus.sum(), sign=False)
              if bal_full.revenus.sum() else "–", ui.eur(bal_full.epargne.mean()) + " / mois" if len(bal_full) else None,
              delta_color="off", border=True, height="stretch",
              help="(Revenus − dépenses) / revenus, sur les mois complets de la période, tous comptes (les filtres "
                   "catégorie et compte ne s'y appliquent pas). Les remboursements d'amis et de la sécu viennent en "
                   "déduction des dépenses : ce ne sont pas des revenus. Les héritages et donations sont exclus.")
    st.metric("Opérations", f"{len(spent_lines)}", f"panier moyen {ui.eur(spent_lines.amount.mean(), 2)}",
              delta_color="off", border=True, height="stretch")

# ---------- what stands out this month (all accounts, whatever the filters) ----------
def insights() -> list[str]:
    out = []
    past = df[(df.month < this_month) & (df.month >= this_month - pd.DateOffset(months=12))]
    n_past = max(past.month.nunique(), 1)
    cur = df[df.month == this_month]
    # Categories running ahead of their usual month, at today's pace.
    pace = today.days_in_month / today.day
    usual = past.groupby("category")["amount"].sum() / n_past
    now = cur.groupby("category")["amount"].sum()
    for cat, v in now.items():
        ref = usual.get(cat, 0.0)
        if ref >= 40 and v > ref * 1.3 and cat not in ("Divers",):
            out.append(f"**{cat}** : {ui.eur(v)} déjà dépensés ce mois-ci contre {ui.eur(ref)} un mois habituel "
                       f"(au rythme actuel, {ui.eur(v * pace if cat not in ui.FIXED else v)} en fin de mois).")
    # Unusually large single payments.
    med = past.groupby("category")["amount"].median()
    big = cur[(cur.amount >= 100) & (cur.amount > 3 * cur.category.map(med).fillna(0)) & (cur.category != "Retraits d'espèces")]
    for r in big.sort_values("amount", ascending=False).head(3).itertuples():
        out.append(f"Dépense inhabituelle : **{r.merchant}** {ui.eur(r.amount, 2)} le {r.date:%d/%m} ({r.category}).")
    # Subscriptions that started recently.
    rec = recurring(df)
    if not rec.empty:
        first = df.groupby("merchant").date.min()
        new = rec[rec.merchant.map(first) >= today - pd.DateOffset(months=4)]
        for r in new.head(3).itertuples():
            out.append(f"Nouvel abonnement probable : **{r.merchant}**, {ui.eur(r.median, 2)} par mois "
                       f"({ui.eur(r.annual)} par an).")
    # Salary change.
    if len(salaries) >= 2:
        last_s, prev_s = salaries.iloc[-1], salaries.iloc[-2]
        if abs(last_s / prev_s - 1) > 0.05:
            out.append(f"Salaire de {ui.month_label(salaries.index[-1])} : {ui.eur(last_s)}, "
                       f"{ui.pct(last_s / prev_s - 1)} par rapport au mois d'avant (prime, absence ou changement ?).")
    # Uncategorised backlog.
    todo = df[(df.category == "Divers") & (df.date >= today - pd.DateOffset(months=3))]
    if len(todo) >= 5:
        out.append(f"{len(todo)} dépenses des 3 derniers mois sont en « Divers » ({ui.eur(todo.amount.sum())}) : "
                   "à classer tout en bas de la page.")
    return out


tips = insights()
if tips:
    with st.container(border=True):
        st.markdown("**À retenir ce mois-ci**")
        for t in tips:
            st.markdown(f"- {t}")

# ---------- salaries: every pay slip line, per employer ----------
sal = inc[inc.category == "Salaire"] if not inc.empty else inc
if not sal.empty:
    with st.container(border=True):
        sal_view = sal[sal.month >= start]
        st.markdown(f"**Salaires** · {len(sal_view)} versement(s) sur la période, {ui.eur(sal_view.amount.sum())} · "
                    "le salaire du mois arrive en fin de mois (il compte pour ce mois-là)")
        c1, c2 = st.columns([3, 2])
        with c1:
            per, slabels = ui.month_axis(sal_view.groupby(["month", "merchant"], as_index=False)["amount"].sum())
            fig = px.bar(per, x="mois", y="amount", color="merchant", category_orders={"mois": slabels},
                         color_discrete_sequence=ui.CATEGORICAL, labels={"amount": "", "mois": "", "merchant": ""})
            fig.update_traces(hovertemplate="%{x} : %{y:,.2f} €<extra></extra>", marker_line_width=1,
                              marker_line_color="white")
            if len(last12_sal):
                fig.add_hline(y=last12_sal.mean(), line_dash="dot", line_color=ui.OTHER,
                              annotation_text=f"moyenne 12 mois {ui.eur(last12_sal.mean())}",
                              annotation_position="top left")
            ui.keep_months(fig, slabels)
            ui.plotly_layout(fig, 280)
            fig.update_layout(bargap=0.3, hovermode="closest")
            fig.update_yaxes(ticksuffix=" €", tickformat=",.0f")
            st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)
        with c2:
            st.dataframe(sal_view.sort_values("date", ascending=False)[["date", "merchant", "amount", "account"]],
                         hide_index=True, width="stretch", height=280, column_config={
                             "date": st.column_config.DateColumn("Versé le", format="DD/MM/YYYY"),
                             "merchant": "Employeur", "amount": st.column_config.NumberColumn("Net", format="%.2f €"),
                             "account": "Compte"})

by_cat = view.groupby("category")["amount"].sum().sort_values(ascending=False)
top = [c for c in by_cat.index if c != "Divers"][:7]
colors = dict(zip(top, ui.CATEGORICAL)) | {"Autres": ui.OTHER}
view = view.assign(groupe=view.category.where(view.category.isin(top), "Autres"))
order = top + ["Autres"]

# ---------- filters shared by the charts: a click on a bar, a day or a cell sets them ----------
months_list = sorted(view.month.unique(), reverse=True)
if ss.get("dep_month") not in months_list:
    ss["dep_month"] = months_list[0]
ss.setdefault("dep_cat", None)
ss.setdefault("dep_day", None)


def clicked(key: str) -> list[dict]:
    """Points of a chart's selection, returned once per new click (a selection survives reruns)."""
    try:
        pts = list(ss[key]["selection"]["points"])
    except (KeyError, TypeError):
        pts = []
    sig = repr(pts)
    if ss.get(f"_seen_{key}") == sig:
        return []
    ss[f"_seen_{key}"] = sig
    return pts


def month_of(value) -> pd.Timestamp | None:
    found = next((m for m in months_list if ui.short_month(m) == value), None)
    if found is not None:
        return found
    try:
        ts = pd.Timestamp(value).to_period("M").to_timestamp()
    except (ValueError, TypeError):
        return None
    return ts if ts in months_list else None


for p in clicked("months"):
    cd = p.get("customdata") or []
    ss["dep_month"] = month_of(cd[0] if cd else p.get("x")) or ss["dep_month"]
    ss["dep_cat"] = cd[1] if len(cd) > 1 else None  # "Autres" is a valid filter: the categories outside the top 7
    ss["dep_day"] = None
for p in clicked("grid"):
    cd = p.get("customdata") or []
    if len(cd) == 2:
        ss["dep_month"], ss["dep_cat"], ss["dep_day"] = month_of(cd[0]) or ss["dep_month"], cd[1], None
        st.toast(f"{cd[1]} · {ui.month_label(ss['dep_month'])} ouvert plus haut", icon=":material/filter_alt:")
for p in clicked("catbars"):
    ss["dep_cat"] = None if ss["dep_cat"] == p.get("y") else p.get("y")
    ss["dep_day"] = None
for p in clicked("cal"):
    cd = p.get("customdata") or []
    if cd:
        ss["dep_day"] = None if ss["dep_day"] == int(cd[0]) else int(cd[0])

# ---------- months ----------
with st.container(border=True):
    st.markdown("**Par mois** · dépenses par catégorie et revenus · clique sur un mois, ou sur "
               "une couleur pour filtrer aussi la catégorie")
    per_month, labels = ui.month_axis(view.groupby(["month", "groupe"], as_index=False)["amount"].sum())
    per_month["month_iso"] = per_month.month.dt.strftime("%Y-%m-%d")
    fig = px.bar(per_month, x="mois", y="amount", color="groupe", custom_data=["month_iso", "groupe"],
                 category_orders={"groupe": order, "mois": labels}, color_discrete_map=colors,
                 labels={"amount": "Montant", "groupe": "Catégorie", "mois": ""})
    fig.update_traces(hovertemplate="%{y:,.0f} €", marker_line_width=1, marker_line_color="white",
                      selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)))
    if avg:
        fig.add_hline(y=avg, line_dash="dot", line_color=ui.OTHER, annotation_text=f"moyenne {ui.eur(avg)}",
                      annotation_position="top left")
    # Income (the month in progress has no salary yet: it lands at the end of the month); internal transfers excluded.
    rev = bal_view[[ui.short_month(m) in labels for m in bal_view.index]]
    rev_labels = [ui.short_month(m) for m in rev.index]
    fig.add_trace(go.Scatter(x=rev_labels, y=rev.revenus.values, mode="lines+markers", name="Revenus",
                             line=dict(width=2, color="#111827", dash="dot"), marker=dict(size=6),
                             hovertemplate="Revenus : %{y:,.0f} €<extra></extra>"))
    chosen_label = ui.short_month(ss["dep_month"])
    if chosen_label in labels:
        i = labels.index(chosen_label)
        fig.add_vrect(x0=i - 0.45, x1=i + 0.45, fillcolor="rgba(42,120,214,0.10)", line_width=0, layer="below")
    ui.keep_months(fig, labels)
    ui.plotly_layout(fig, 380)
    # One segment per click: with a unified hover, a click would select the whole month column.
    fig.update_layout(bargap=0.3, hovermode="closest")
    fig.update_traces(hovertemplate="%{customdata[1]} · %{x} : %{y:,.0f} €<extra></extra>", selector=dict(type="bar"))
    fig.update_yaxes(ticksuffix=" €", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG, on_select="rerun", selection_mode="points", key="months")
    st.caption("« Autres » regroupe les catégories hors de ce top 7 : clique dessus pour voir lesquelles, plus bas.")

# ---------- one month ----------
with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown("**Le mois en détail**")
        st.selectbox("Mois", months_list, key="dep_month", format_func=ui.month_label, label_visibility="collapsed",
                     width=200, on_change=lambda: ss.update(dep_day=None))
        cat_choices = set(view[view.month == ss["dep_month"]].category.unique())
        show_autres = bool(cat_choices - set(top)) or ss["dep_cat"] == "Autres"
        if ss["dep_cat"] and ss["dep_cat"] != "Autres":
            cat_choices.add(ss["dep_cat"])
        cat_options = ["Toutes catégories"] + (["Autres"] if show_autres else []) + sorted(cat_choices)
        current_cat_label = ss["dep_cat"] or "Toutes catégories"
        cat_key = f"dep_cat_pick_{current_cat_label}"

        def _pick_cat(widget_key: str = cat_key) -> None:
            ss["dep_cat"] = None if ss[widget_key] == "Toutes catégories" else ss[widget_key]
            ss["dep_day"] = None

        st.selectbox("Catégorie", cat_options, index=cat_options.index(current_cat_label), key=cat_key,
                     label_visibility="collapsed", width=220, on_change=_pick_cat)
        if ss["dep_day"]:
            st.button(f"le {ss['dep_day']}  ✕", key="clear_day", icon=":material/calendar_today:",
                      on_click=lambda: ss.update(dep_day=None))
    chosen, cat, day = ss["dep_month"], ss["dep_cat"], ss["dep_day"]
    m = view[view.month == chosen]

    def by_cat_filter(lines: pd.DataFrame) -> pd.DataFrame:
        """Same category filter the whole section uses: a real category, "Autres" (outside the top 7), or none."""
        if cat == "Autres":
            return lines[~lines.category.isin(top)]
        return lines[lines.category == cat] if cat else lines

    mc = by_cat_filter(m)
    md = mc[mc.date.dt.day == day] if day else mc
    total_c = mc.amount.sum()
    prev = view[view.month == chosen - pd.DateOffset(months=1)]
    prev_total = by_cat_filter(prev).amount.sum()
    cat_avg_all = complete.groupby(["month", "category"])["amount"].sum().unstack(fill_value=0).mean()
    if cat == "Autres":
        autres_by_month = complete[~complete.category.isin(top)].groupby("month")["amount"].sum()
        ref = autres_by_month.mean() if not autres_by_month.empty else 0.0
    else:
        ref = cat_avg_all.get(cat, 0.0) if cat else avg
    with st.container(horizontal=True):
        st.metric(cat or "Total", ui.eur(total_c), ui.eur(total_c - prev_total, sign=True) + " vs mois précédent",
                  delta_color="inverse", border=True)
        st.metric("Écart à la moyenne", ui.eur(total_c - ref, sign=True) if ref else "–", delta_color="off",
                  border=True)
        if not cat:
            st.metric("Du quotidien", ui.eur(m[~m.category.isin(ui.FIXED)].amount.sum()), border=True,
                      help="Hors loyer, énergie, abonnements et impôts.")
        st.metric("Opérations", f"{(mc.amount > 0).sum()}", border=True)
        daily_var = mc[mc.amount > 0] if cat else mc[(mc.amount > 0) & ~mc.category.isin(ui.FIXED)]
        days_spent = daily_var.groupby(daily_var.date.dt.day)["amount"].sum()
        st.metric("Jour le plus cher", f"le {days_spent.idxmax()}" if not days_spent.empty else "–",
                  ui.eur(days_spent.max()) if not days_spent.empty else None, delta_color="off", border=True)

    c1, c2 = st.columns(2)
    with c1:
        st.caption("Calendrier · clique sur un jour pour voir ses opérations"
                   + ("" if cat else " (hors loyer et factures)"))
        cal_lines = mc if cat else mc[~mc.category.isin(ui.FIXED)]
        daily = cal_lines.groupby(cal_lines.date.dt.day)["amount"].sum()
        first_wd, n_days = calendar.monthrange(chosen.year, chosen.month)
        weeks = (first_wd + n_days + 6) // 7
        names = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
        rows = [f"s{i + 1}" for i in range(weeks)]
        z: list[list[float | None]] = [[None] * 7 for _ in range(weeks)]
        text = [[""] * 7 for _ in range(weeks)]
        cells = []
        for d in range(1, n_days + 1):
            w, wd = divmod(first_wd + d - 1, 7)
            v = float(daily.get(d, 0.0))
            z[w][wd] = v
            text[w][wd] = f"<b>{d}</b><br>{v:.0f} €" if v else f"{d}"
            cells.append((names[wd], rows[w], d, v))
        fig = go.Figure(go.Heatmap(z=z, text=text, texttemplate="%{text}", x=names, y=rows, xgap=4, ygap=4,
                                   colorscale=[[0, "#eef4fc"], [1, ui.CATEGORICAL[0]]], showscale=False,
                                   hoverinfo="skip"))
        # Invisible markers on top of the cells: a heatmap cannot be selected, markers can.
        fig.add_trace(go.Scatter(x=[c[0] for c in cells], y=[c[1] for c in cells], mode="markers",
                                 customdata=[[c[2]] for c in cells], text=[f"{c[3]:.0f} €" for c in cells],
                                 marker=dict(size=38, symbol="square", color="rgba(0,0,0,0)"), showlegend=False,
                                 hovertemplate="le %{customdata[0]} : %{text}<extra></extra>",
                                 selected=dict(marker=dict(color="rgba(0,0,0,0)")),
                                 unselected=dict(marker=dict(color="rgba(0,0,0,0)"))))
        if day:
            w, wd = divmod(first_wd + day - 1, 7)
            fig.add_shape(type="rect", x0=wd - 0.5, x1=wd + 0.5, y0=w - 0.5, y1=w + 0.5,
                          line=dict(color=ui.CATEGORICAL[1], width=3))
        ui.plotly_layout(fig, 300)
        fig.update_yaxes(autorange="reversed", showticklabels=False)
        fig.update_xaxes(side="top")
        fig.update_layout(hovermode="closest", margin_r=0, dragmode=False)
        st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG, on_select="rerun", selection_mode="points", key="cal")
    with c2:
        st.caption("Cumul dans le mois, comparé à un mois moyen" + (f" · {cat}" if cat else ""))
        cum = mc.groupby(mc.date.dt.day)["amount"].sum().reindex(range(1, 32), fill_value=0).cumsum()
        last_day = today.day if chosen == this_month else calendar.monthrange(chosen.year, chosen.month)[1]
        ref_lines = by_cat_filter(complete)
        typical = (ref_lines.groupby([ref_lines.month, ref_lines.date.dt.day])["amount"].sum().unstack(fill_value=0)
                   .reindex(index=complete.month.unique(), columns=range(1, 32), fill_value=0).cumsum(axis=1).mean())
        fig = go.Figure([
            go.Scatter(x=typical.index, y=typical.values, name="Mois moyen",
                       line=dict(color=ui.OTHER, width=2, dash="dot"), hovertemplate="%{y:,.0f} €"),
            go.Scatter(x=cum.index[:last_day], y=cum.values[:last_day], name=ui.month_label(chosen),
                       line=dict(color=ui.CATEGORICAL[0], width=2.5), hovertemplate="%{y:,.0f} €"),
        ])
        ui.plotly_layout(fig, 300)
        fig.update_xaxes(dtick=5, ticksuffix=" ")
        fig.update_yaxes(ticksuffix=" €", tickformat=",.0f")
        st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)

    c1, c2 = st.columns([2, 3])
    with c1:
        st.caption("Par catégorie, comparé à la moyenne · clique pour filtrer")
        comp = pd.DataFrame({"Ce mois": m.groupby("category")["amount"].sum(), "Moyenne": cat_avg_all}) \
            .fillna(0).sort_values("Ce mois")
        comp = comp[(comp["Ce mois"] > 0) | (comp["Moyenne"] > 20)]
        bar_colors = [ui.CATEGORICAL[1] if (c == cat or (cat == "Autres" and c not in top)) else ui.CATEGORICAL[0]
                     for c in comp.index]
        fig = go.Figure([
            go.Bar(y=comp.index, x=comp["Moyenne"], orientation="h", name="Moyenne mensuelle",
                   marker_color="rgba(138,137,131,0.45)", hovertemplate="%{x:,.0f} €"),
            go.Bar(y=comp.index, x=comp["Ce mois"], orientation="h", name=ui.month_label(chosen),
                   marker_color=bar_colors, hovertemplate="%{x:,.0f} €"),
        ])
        fig.update_traces(selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)))
        ui.plotly_layout(fig, 80 + 30 * len(comp))
        fig.update_layout(barmode="group", bargap=0.3, hovermode="closest")
        fig.update_traces(hovertemplate="%{y} : %{x:,.0f} €")
        fig.update_xaxes(ticksuffix=" €", tickformat=",.0f")
        st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG, on_select="rerun", selection_mode="points", key="catbars")
    with c2:
        title = "Opérations" + (f" · {cat}" if cat else "") + (f" · le {day}" if day else " du mois")
        st.caption(f"{title} · {ui.eur(md.amount.sum(), 2)} · la catégorie se modifie directement dans le tableau")
        ops = md.sort_values("date", ascending=False)[["id", "date", "merchant", "category", "account", "amount"]]
        edited_ops = st.data_editor(
            ops, hide_index=True, width="stretch", key=f"ops_editor_{chosen:%Y%m}_{cat}_{day}", height=80 + 30 * max(len(comp), 8),
            disabled=["id", "date", "merchant", "account", "amount"],
            column_order=["date", "merchant", "category", "account", "amount"],
            column_config={
                "date": st.column_config.DateColumn("Date", format="DD/MM"), "merchant": "Commerçant",
                "category": st.column_config.SelectboxColumn("Catégorie", options=SPENDING, required=True),
                "account": "Compte", "amount": st.column_config.NumberColumn("Montant", format="%.2f €")})
        changed_ops = edited_ops[edited_ops.category != ops.category]
        if st.button(f"Enregistrer ({len(changed_ops)})", icon=":material/save:", disabled=changed_ops.empty,
                     key="save_ops"):
            con = ui.connect()
            try:
                for r in changed_ops.itertuples():
                    queries.set_category(con, r.id, r.category)
            finally:
                con.close()
            st.cache_data.clear()
            st.toast(f"{len(changed_ops)} ligne(s) reclassée(s)", icon=":material/check:")
            st.rerun()
        m_inc = inc[inc.month == chosen] if not inc.empty else inc
        st.caption(f"Revenus du mois · {ui.eur(m_inc.amount.sum(), 2)}" if not m_inc.empty else
                   "Revenus du mois · aucun pour l'instant (le salaire arrive en fin de mois)")
        if not m_inc.empty:
            st.dataframe(m_inc.sort_values("date", ascending=False)[["date", "merchant", "category", "amount"]],
                         hide_index=True, width="stretch", column_config={
                             "date": st.column_config.DateColumn("Date", format="DD/MM"), "merchant": "Origine",
                             "category": "Catégorie", "amount": st.column_config.NumberColumn("Montant", format="%+.2f €")})

# ---------- income and savings (the month in progress has no salary yet: it lands at the end of the month) ----------
col1, col2 = st.columns(2)
with col1, st.container(border=True):
    st.markdown("**Revenus, dépenses et épargne**")
    b, labels = ui.month_axis(bal_view.reset_index(names="month"))
    b["autres"] = b.revenus - b.salaire
    fig = go.Figure([
        go.Bar(x=b.mois, y=b.salaire, name="Salaire", marker_color=ui.CATEGORICAL[0], offsetgroup="r",
               hovertemplate="%{y:,.0f} €"),
        go.Bar(x=b.mois, y=b.autres, name="Autres revenus", marker_color="rgba(42,120,214,0.45)", offsetgroup="r",
               base=b.salaire, hovertemplate="%{y:,.0f} €"),
        go.Bar(x=b.mois, y=b.depenses, name="Dépenses", marker_color=ui.CATEGORICAL[1], offsetgroup="d",
               hovertemplate="%{y:,.0f} €"),
        go.Bar(x=b.mois, y=b.epargne, name="Épargne", marker_color=ui.CATEGORICAL[2], offsetgroup="e",
               hovertemplate="%{y:,.0f} €"),
    ])
    fig.update_xaxes(categoryorder="array", categoryarray=labels)
    ui.plotly_layout(fig, 320)
    fig.update_yaxes(ticksuffix=" €", tickformat=",.0f", zeroline=True)
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)
    st.caption("Mois en cours partiel : le salaire arrive en fin de mois. Autres revenus : "
               "aides, famille, intérêts, dividendes (héritages et donations exclus). Dépenses nettes des remboursements "
               "(amis, sécu).")
with col2, st.container(border=True):
    st.markdown("**Taux d'épargne** · moyenne sur les mois complets")
    t, labels = ui.month_axis(bal_view[["taux"]].reset_index(names="month"))
    fig = px.line(t, x="mois", y="taux", markers=True, category_orders={"mois": labels}, labels={"taux": "", "mois": ""})
    fig.update_traces(line=dict(width=2, color=ui.CATEGORICAL[2]), marker=dict(size=8), hovertemplate="%{y:.0%}")
    if len(bal_full) and bal_full.revenus.sum():
        mean_rate = bal_full.epargne.sum() / bal_full.revenus.sum()
        fig.add_hline(y=mean_rate, line_dash="dot", line_color=ui.OTHER,
                      annotation_text=f"moyenne {ui.pct(mean_rate, sign=False)}", annotation_position="bottom left")
    ui.plotly_layout(fig, 320)
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)

# ---------- income, in detail (mirrors the spending breakdown above; internal transfers excluded) ----------
inc_view = inc[inc.month >= start] if not inc.empty else inc
if not inc_view.empty:
    col1, col2 = st.columns([2, 3])
    with col1, st.container(border=True):
        st.markdown("**Revenus par catégorie** · clique sur une barre pour filtrer les opérations")
        by_month_cat, ilabels = ui.month_axis(inc_view.groupby(["month", "category"], as_index=False)["amount"].sum())
        by_month_cat["month_iso"] = by_month_cat.month.dt.strftime("%Y-%m-%d")
        fig = px.bar(by_month_cat, x="mois", y="amount", color="category", custom_data=["month_iso", "category"],
                     category_orders={"mois": ilabels, "category": INCOME},
                     color_discrete_map=dict(zip(INCOME, ui.CATEGORICAL)),
                     labels={"amount": "", "mois": "", "category": ""})
        fig.update_traces(hovertemplate="%{customdata[1]} · %{x} : %{y:,.0f} €<extra></extra>", marker_line_width=1,
                          marker_line_color="white", selected=dict(marker=dict(opacity=1)),
                          unselected=dict(marker=dict(opacity=0.35)))
        ui.keep_months(fig, ilabels)
        ui.plotly_layout(fig, 360)
        fig.update_layout(bargap=0.3, hovermode="closest")
        fig.update_yaxes(ticksuffix=" €", tickformat=",.0f")
        ev = st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG, on_select="rerun", selection_mode="points",
                             key="inc_chart")
        st.caption("Virements entre tes propres comptes exclus. « Remboursements » : amis qui rendent leur part, "
                   "sécu, mutuelle ; déduits des dépenses dans le taux d'épargne. « Héritage et donations » : hors revenus et "
                   "épargne, compté seulement dans le patrimoine.")

    pts = (ev.selection.points if ev and ev.selection else []) or []
    inc_sel = inc_view
    sel_label = "sur la période"
    if pts and pts[0].get("customdata"):
        m_iso, c_sel = pts[0]["customdata"][0], pts[0]["customdata"][1]
        inc_sel = inc_view[(inc_view.month == pd.Timestamp(m_iso)) & (inc_view.category == c_sel)]
        sel_label = f"· {c_sel} · {ui.month_label(m_iso)} (reclique pour tout revoir)"
    with col2, st.container(border=True):
        st.markdown(f"**Opérations de revenus** · {ui.eur(inc_sel.amount.sum())} {sel_label}")
        st.caption("La catégorie se modifie directement dans le tableau.")
        inc_ops = inc_sel.sort_values("date", ascending=False)[
            ["id", "date", "merchant", "category", "account", "amount"]]
        edited_inc = st.data_editor(
            inc_ops, hide_index=True, width="stretch", key=f"income_editor_{sel_label}", height=330,
            disabled=["id", "date", "merchant", "account", "amount"],
            column_order=["date", "merchant", "category", "account", "amount"],
            column_config={
                "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"), "merchant": "Origine",
                "category": st.column_config.SelectboxColumn("Catégorie", options=INCOME, required=True),
                "account": "Compte", "amount": st.column_config.NumberColumn("Montant", format="%.2f €")})
        changed_inc = edited_inc[edited_inc.category != inc_ops.category]
        if st.button(f"Enregistrer ({len(changed_inc)})", icon=":material/save:", disabled=changed_inc.empty,
                     key="save_income"):
            con = ui.connect()
            try:
                for r in changed_inc.itertuples():
                    queries.set_category(con, r.id, r.category)
            finally:
                con.close()
            st.cache_data.clear()
            st.toast(f"{len(changed_inc)} ligne(s) reclassée(s)", icon=":material/check:")
            st.rerun()

# ---------- categories over time ----------
with st.container(border=True):
    st.markdown("**Catégories mois par mois**")
    grid = view.pivot_table(index="category", columns="month", values="amount", aggfunc="sum", fill_value=0)
    grid = grid.loc[grid.sum(axis=1).sort_values(ascending=False).index]
    xs = [ui.short_month(c) for c in grid.columns]
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=xs, y=grid.index, xgap=3, ygap=3, showscale=False,
        colorscale=[[0, "#f5f7fb"], [0.15, "#dbe8f8"], [1, ui.CATEGORICAL[0]]],
        text=[[f"{v:.0f}" if v >= 1 else "" for v in row] for row in grid.values], texttemplate="%{text}",
        hoverinfo="skip"))
    cells = [(xs[j], c, grid.columns[j].strftime("%Y-%m-%d"), grid.iat[i, j])
             for i, c in enumerate(grid.index) for j in range(len(xs))]
    fig.add_trace(go.Scatter(x=[c[0] for c in cells], y=[c[1] for c in cells], mode="markers",
                             customdata=[[c[2], c[1]] for c in cells], text=[f"{c[3]:,.0f} €" for c in cells],
                             marker=dict(size=24, symbol="square", color="rgba(0,0,0,0)"), showlegend=False,
                             hovertemplate="%{y} · %{x} : %{text}<extra></extra>",
                             selected=dict(marker=dict(color="rgba(0,0,0,0)")),
                             unselected=dict(marker=dict(color="rgba(0,0,0,0)"))))
    ui.plotly_layout(fig, 60 + 28 * len(grid))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(side="top")
    fig.update_layout(hovermode="closest", margin_r=0, dragmode=False)
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG, on_select="rerun", selection_mode="points", key="grid")
    st.caption("Clique sur une case pour ouvrir ce mois filtré sur la catégorie. Plus la case est foncée, "
               "plus la dépense est forte.")

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
        st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)
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
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)

col1, col2 = st.columns(2)
with col1, st.container(border=True):
    rec = recurring(base)
    st.markdown(f"**Dépenses récurrentes** · {ui.eur(rec.annual.sum() if not rec.empty else 0)} par an · clique "
                "sur une ligne pour voir tout son historique")
    ss["_tbl_recurring_names"] = list(rec.merchant) if not rec.empty else []
    st.dataframe(rec[["merchant", "category", "median", "months", "annual"]] if not rec.empty else rec,
                 hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                 key="tbl_recurring", column_config={
                     "merchant": "Commerçant", "category": "Catégorie",
                     "median": st.column_config.NumberColumn("Montant habituel", format="%.2f €"),
                     "months": st.column_config.NumberColumn("Mois"),
                     "annual": st.column_config.NumberColumn("Par an", format="%.0f €")})
    st.caption("Payés au moins 3 mois, pour un montant stable, et encore actifs.")
with col2, st.container(border=True):
    st.markdown("**Où tu dépenses le plus** · hors loyer et factures · clique sur une ligne pour la rechercher")
    merchants = (view[~view.category.isin(ui.FIXED)].groupby("merchant")
                 .agg(total=("amount", "sum"), fois=("amount", "size"), categorie=("category", "first"))
                 .sort_values("total", ascending=False).head(15).reset_index())
    ss["_tbl_merchants_names"] = list(merchants.merchant)
    st.dataframe(merchants, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                 key="tbl_merchants", column_config={
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
