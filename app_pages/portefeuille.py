import plotly.express as px
import streamlit as st

from patrimoine import ui

pos = ui.positions()
if pos.empty:
    st.warning("Aucune position.", icon=":material/info:")
    st.stop()

with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader("Portefeuille", icon=":material/candlestick_chart:")
    scope = st.segmented_control("Comptes", ["Tout", "PEA", "Compte-titres", "PEG Airbus"], default="Tout",
                                 label_visibility="collapsed")
view = pos if scope in (None, "Tout") else pos[pos.account == scope]
view = view.assign(weight=view.value / view.value.sum())

costed = view[view.cost.notna()]
latent = (costed.value - costed.cost).sum()
with st.container(horizontal=True):
    st.metric("Valeur des titres", ui.eur(view.value.sum()), border=True)
    st.metric("Prix de revient", ui.eur(costed.cost.sum()), border=True,
              help="PMP, frais d'achat inclus (règle fiscale). Le PEG n'a pas de prix de revient connu.")
    st.metric("Plus-value latente", ui.eur(latent, sign=True),
              ui.pct(latent / costed.cost.sum()) if costed.cost.sum() else None, border=True)
    top = view.iloc[0]
    st.metric("Plus grosse ligne", top["name"], ui.pct(top.weight, sign=False) + " du portefeuille",
              delta_color="off", border=True)

with st.container(border=True):
    st.markdown("**Positions**")
    st.dataframe(
        view[["name", "account", "quantity", "unit_cost", "price", "value", "gain", "gain_pct", "weight"]],
        hide_index=True, width="stretch",
        column_config={
            "name": st.column_config.TextColumn("Titre", width="large"),
            "account": "Compte",
            "quantity": st.column_config.NumberColumn("Quantité", format="%.4g"),
            "unit_cost": st.column_config.NumberColumn("PMP", format="%.2f €"),
            "price": st.column_config.NumberColumn("Cours", format="%.2f €"),
            "value": st.column_config.NumberColumn("Valeur", format="%.0f €"),
            "gain": st.column_config.NumberColumn("+/- latente", format="%+.0f €"),
            "gain_pct": st.column_config.NumberColumn("%", format="percent"),
            "weight": st.column_config.ProgressColumn("Poids", format="percent", min_value=0, max_value=1),
        },
    )

col1, col2 = st.columns(2)
with col1, st.container(border=True):
    st.markdown("**Répartition par ligne**")
    fig = px.bar(view.sort_values("value"), x="value", y="name", orientation="h",
                 labels={"value": "Valeur", "name": ""}, text=view.sort_values("value").weight.map(
                     lambda w: ui.pct(w, sign=False)))
    fig.update_traces(hovertemplate="%{x:,.0f} €", textposition="outside", cliponaxis=False)
    ui.plotly_layout(fig, 60 + 36 * len(view))
    fig.update_xaxes(ticksuffix=" €", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch")
with col2, st.container(border=True):
    st.markdown("**Ventes réalisées**")
    real = ui.realised()
    if scope not in (None, "Tout"):
        real = real[real.account == scope] if not real.empty else real
    st.dataframe(real, hide_index=True, width="stretch", height=60 + 36 * len(view), column_config={
        "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"), "account": "Compte",
        "name": "Titre", "isin": None, "quantity": None,
        "proceeds": st.column_config.NumberColumn("Vente", format="%.0f €"),
        "cost": st.column_config.NumberColumn("Coût", format="%.0f €"),
        "gain": st.column_config.NumberColumn("+/-", format="%+.0f €"),
    })

st.caption("Cours Yahoo Finance (clôture de la veille), convertis en euros. Turbos valorisés au prix de tes ordres.")
