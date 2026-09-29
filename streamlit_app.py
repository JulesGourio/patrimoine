import streamlit as st

st.set_page_config(page_title="Patrimoine", page_icon=":material/account_balance:", layout="wide")

page = st.navigation(
    [
        st.Page("app_pages/accueil.py", title="Patrimoine", icon=":material/account_balance:", default=True),
        st.Page("app_pages/depenses.py", title="Dépenses", icon=":material/receipt_long:"),
        st.Page("app_pages/portefeuille.py", title="Portefeuille", icon=":material/candlestick_chart:"),
        st.Page("app_pages/projection.py", title="Projection", icon=":material/trending_up:"),
        st.Page("app_pages/fiscalite.py", title="Fiscalité et frais", icon=":material/gavel:"),
        st.Page("app_pages/investisseurs.py", title="Investisseurs", icon=":material/groups:"),
        st.Page("app_pages/suivi.py", title="Suivi", icon=":material/notifications:"),
        st.Page("app_pages/reglages.py", title="Réglages", icon=":material/settings:"),
    ],
    position="top",
)
page.run()
