import pandas as pd
import streamlit as st

from patrimoine import alerts, ui
from patrimoine.categories import SPENDING

st.subheader("Suivi", icon=":material/notifications:")

con = ui.connect()
alerts.seed(con)

tab_reports, tab_orders, tab_alerts, tab_budgets = st.tabs(
    [":material/article: Rapports", ":material/shopping_cart: Ordres préparés", ":material/notifications: Alertes",
     ":material/savings: Budgets"])

with tab_reports:
    reports = pd.read_sql_query("SELECT created_at, kind, title, body_md FROM reports ORDER BY created_at DESC", con)
    if reports.empty:
        st.caption("Aucun rapport pour l'instant : le premier rapport hebdo arrive dimanche soir, ou demande-en un "
                   "à Claude.")
    for r in reports.itertuples():
        with st.expander(f"{r.title} · {r.created_at[:10]}", expanded=r.Index == 0, icon=":material/article:"):
            st.markdown(r.body_md)

with tab_orders:
    st.caption("Ordres préparés par Claude. Rien n'est passé automatiquement : tu les exécutes dans Trade Republic.")
    orders = pd.read_sql_query("SELECT id, created_at, side, name, account_id, quantity, amount_eur, limit_price, "
                               "rationale, risks, status FROM order_ideas ORDER BY created_at DESC", con)
    edited = st.data_editor(orders, hide_index=True, width="stretch", disabled=[c for c in orders if c != "status"],
                            column_config={
                                "id": None, "created_at": st.column_config.TextColumn("Date", width="small"),
                                "side": "Sens", "name": "Titre", "account_id": "Compte",
                                "quantity": st.column_config.NumberColumn("Qté", format="%g"),
                                "amount_eur": st.column_config.NumberColumn("Montant", format="%.0f €"),
                                "limit_price": st.column_config.NumberColumn("Limite", format="%.2f €"),
                                "rationale": st.column_config.TextColumn("Pourquoi", width="large"),
                                "risks": st.column_config.TextColumn("Risques", width="medium"),
                                "status": st.column_config.SelectboxColumn(
                                    "Statut", options=["proposé", "passé", "abandonné"], required=True),
                            })
    changed = edited[edited.status != orders.status]
    if not changed.empty and st.button("Enregistrer les statuts", icon=":material/save:", type="primary"):
        for r in changed.itertuples():
            con.execute("UPDATE order_ideas SET status = ? WHERE id = ?", (r.status, r.id))
        con.commit()
        st.rerun()

with tab_alerts:
    events = pd.read_sql_query("SELECT triggered_at, message, sent_to FROM alert_events ORDER BY triggered_at DESC "
                               "LIMIT 100", con)
    st.markdown("**Dernières alertes**")
    st.dataframe(events, hide_index=True, width="stretch", column_config={
        "triggered_at": st.column_config.TextColumn("Quand", width="small"), "message": "Alerte",
        "sent_to": st.column_config.TextColumn("Envoyée", width="small")})
    st.markdown("**Règles**")
    rules = pd.read_sql_query("SELECT id, kind, isin, target, threshold, window_days, active, note FROM alert_rules",
                              con)
    rules["active"] = rules.active.astype(bool)
    edited = st.data_editor(rules, hide_index=True, width="stretch", num_rows="dynamic", key="rules",
                            column_config={
                                "id": None,
                                "kind": st.column_config.SelectboxColumn("Type", required=True, options=[
                                    "baisse_ligne", "hausse_ligne", "baisse_portefeuille", "seuil_bas", "seuil_haut",
                                    "concentration", "budget"]),
                                "isin": st.column_config.TextColumn("ISIN (vide : toutes les lignes)"),
                                "target": st.column_config.SelectboxColumn("Catégorie (budget)", options=SPENDING),
                                "threshold": st.column_config.NumberColumn("Seuil (% ou €)", required=True),
                                "window_days": st.column_config.NumberColumn("Séances / jours", min_value=1),
                                "active": st.column_config.CheckboxColumn("Active"), "note": "Note",
                            })
    st.caption(alerts.__doc__.split("Kinds:")[0].strip())
    if st.button("Enregistrer les règles", icon=":material/save:", type="primary", key="save_rules"):
        con.execute("DELETE FROM alert_rules WHERE id NOT IN (%s)" % ",".join(
            str(int(i)) for i in edited.id.dropna()) if edited.id.notna().any() else "DELETE FROM alert_rules")
        for r in edited.itertuples():
            vals = (r.kind, r.isin or None, r.target or None, r.threshold,
                    None if pd.isna(r.window_days) else int(r.window_days), int(bool(r.active)), r.note or None)
            if pd.isna(r.id):
                con.execute("INSERT INTO alert_rules (kind, isin, target, threshold, window_days, active, note)"
                            " VALUES (?, ?, ?, ?, ?, ?, ?)", vals)
            else:
                con.execute("UPDATE alert_rules SET kind=?, isin=?, target=?, threshold=?, window_days=?, active=?,"
                            " note=? WHERE id=?", (*vals, int(r.id)))
        con.commit()
        st.toast("Règles enregistrées", icon=":material/check:")

with tab_budgets:
    sp = ui.spending()
    month = pd.Timestamp.today().to_period("M").to_timestamp()
    spent = sp[sp.month == month].groupby("category")["amount"].sum()
    budgets = pd.read_sql_query("SELECT category, monthly_limit_cents / 100.0 AS budget FROM budgets", con)
    budgets = pd.DataFrame({"category": SPENDING}).merge(budgets, how="left")
    budgets["depense"] = budgets.category.map(spent).fillna(0.0)
    budgets["usage"] = (budgets.depense / budgets.budget).where(budgets.budget > 0)
    edited = st.data_editor(budgets, hide_index=True, width="stretch", disabled=["category", "depense", "usage"],
                            column_config={
                                "category": "Catégorie",
                                "budget": st.column_config.NumberColumn("Budget mensuel", format="%.0f €", min_value=0),
                                "depense": st.column_config.NumberColumn("Dépensé ce mois", format="%.0f €"),
                                "usage": st.column_config.ProgressColumn("Utilisé", format="percent", min_value=0,
                                                                         max_value=1),
                            })
    if st.button("Enregistrer les budgets", icon=":material/save:", type="primary"):
        con.execute("DELETE FROM budgets")
        for r in edited.itertuples():
            if not pd.isna(r.budget) and r.budget > 0:
                con.execute("INSERT INTO budgets (category, monthly_limit_cents) VALUES (?, ?)",
                            (r.category, round(r.budget * 100)))
        con.commit()
        st.cache_data.clear()
        st.toast("Budgets enregistrés", icon=":material/check:")

con.close()
