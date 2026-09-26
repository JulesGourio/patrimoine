import pandas as pd
import plotly.express as px
import streamlit as st

from patrimoine import queries, ui
from patrimoine.categories import SPENDING

df = ui.spending()
if df.empty:
    st.warning("Aucune dépense importée.", icon=":material/info:")
    st.stop()

with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader("Dépenses", icon=":material/receipt_long:")
    period = st.segmented_control("Période", ["3 mois", "12 mois", "Tout"], default="12 mois",
                                  label_visibility="collapsed")
    accounts = st.multiselect("Comptes", sorted(df.account.dropna().unique()), placeholder="Tous les comptes",
                              label_visibility="collapsed")

this_month = pd.Timestamp.today().to_period("M").to_timestamp()
months = {"3 mois": 3, "12 mois": 12}.get(period)
start = this_month - pd.DateOffset(months=months) if months else df.month.min()
view = df[(df.month >= start) & (df.account.isin(accounts) if accounts else True)]

# KPI: this month against the average of the full months of the period
monthly = view.groupby("month")["amount"].sum()
full = monthly[monthly.index < this_month]
avg = full.mean() if not full.empty else None
current = monthly.get(this_month, 0.0)
by_cat = view.groupby("category")["amount"].sum().sort_values(ascending=False)
with st.container(horizontal=True):
    st.metric("Ce mois-ci", ui.eur(current),
              ui.eur(current - avg, sign=True) + " vs moyenne" if avg else None, delta_color="inverse", border=True)
    st.metric("Moyenne mensuelle", ui.eur(avg), border=True,
              chart_data=full.tolist(), chart_type="bar")
    st.metric("Total de la période", ui.eur(view.amount.sum()), border=True)
    st.metric("Premier poste", by_cat.index[0] if not by_cat.empty else "–",
              ui.eur(by_cat.iloc[0]) if not by_cat.empty else None, delta_color="off", border=True)

# Seven named categories at most, the rest folded into "Autres" (fixed colour order, never cycled).
top = [c for c in by_cat.index if c != "Divers"][:7]
view = view.assign(groupe=view.category.where(view.category.isin(top), "Autres"))
order = top + ["Autres"]

col1, col2 = st.columns([3, 2])
with col1, st.container(border=True):
    st.markdown("**Par mois**")
    per_month = view.groupby(["month", "groupe"], as_index=False)["amount"].sum()
    colors = dict(zip(top, ui.CATEGORICAL)) | {"Autres": ui.OTHER}
    fig = px.bar(per_month, x="month", y="amount", color="groupe", category_orders={"groupe": order},
                 color_discrete_map=colors,
                 labels={"amount": "Montant", "groupe": "Catégorie", "month": ""})
    fig.update_traces(hovertemplate="%{y:,.0f} €", marker_line_width=1, marker_line_color="white")
    ui.plotly_layout(fig, 380)
    fig.update_layout(bargap=0.25)
    fig.update_xaxes(dtick="M1", tickformat="%b %y")
    fig.update_yaxes(ticksuffix=" €", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch")
with col2, st.container(border=True):
    st.markdown("**Par catégorie**")
    cats = by_cat.reset_index()
    cats["part"] = cats.amount / cats.amount.sum()
    st.dataframe(
        cats, hide_index=True, width="stretch", height=380,
        column_config={
            "category": st.column_config.TextColumn("Catégorie"),
            "amount": st.column_config.NumberColumn("Montant", format="%.0f €"),
            "part": st.column_config.ProgressColumn("Part", format="percent", min_value=0, max_value=1),
        },
    )

with st.container(border=True):
    st.markdown("**Commerçants les plus fréquents**")
    merchants = (view.groupby("merchant").agg(total=("amount", "sum"), fois=("amount", "size"),
                                              categorie=("category", "first"))
                 .sort_values("total", ascending=False).head(25).reset_index())
    st.dataframe(merchants, hide_index=True, width="stretch", column_config={
        "merchant": "Commerçant", "categorie": "Catégorie", "fois": st.column_config.NumberColumn("Achats"),
        "total": st.column_config.NumberColumn("Total", format="%.0f €"),
    })

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
