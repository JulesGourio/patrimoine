import streamlit as st

st.set_page_config(page_title="Patrimoine", page_icon=":material/account_balance:", layout="wide")

page = st.navigation(
    [
        st.Page("app_pages/accueil.py", title="Patrimoine", icon=":material/account_balance:", default=True),
        st.Page("app_pages/depenses.py", title="Dépenses", icon=":material/receipt_long:"),
        st.Page("app_pages/portefeuille.py", title="Portefeuille", icon=":material/candlestick_chart:"),
        st.Page("app_pages/fiscalite.py", title="Fiscalité", icon=":material/gavel:"),
        st.Page("app_pages/suivi.py", title="Suivi", icon=":material/notifications:"),
    ],
    position="top",
)
page.run()
