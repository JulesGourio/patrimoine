import streamlit as st

from patrimoine import db, notify, vault

st.subheader("Réglages", icon=":material/settings:")

with st.container(border=True):
    st.markdown("**E-mails d'alerte et de rapport**")
    st.caption(f"Les mails partent de {notify.EMAIL} vers {notify.EMAIL}, avec un mot de passe d'application Google "
               "(16 lettres, créé sur myaccount.google.com/apppasswords). Il est rangé dans le gestionnaire "
               "d'identifiants Windows, jamais dans un fichier.")
    st.badge("Configuré" if notify.mail_ready() else "Pas encore configuré",
             color="green" if notify.mail_ready() else "orange",
             icon=":material/check:" if notify.mail_ready() else ":material/schedule:")
    with st.form("smtp", border=False):
        password = st.text_input("Mot de passe d'application", type="password", placeholder="xxxx xxxx xxxx xxxx")
        if st.form_submit_button("Enregistrer et envoyer un mail de test", icon=":material/send:", type="primary"):
            if len(password.replace(" ", "")) != 16:
                st.error("Un mot de passe d'application Google fait 16 lettres.", icon=":material/error:")
            else:
                vault.set("smtp_password", password.replace(" ", ""))
                if notify.mail("Test", "Les mails du tableau de bord Patrimoine fonctionnent."):
                    st.success("Mail envoyé : vérifie ta boîte de réception.", icon=":material/check_circle:")
                else:
                    st.error("Gmail a refusé la connexion : vérifie le mot de passe d'application.",
                             icon=":material/error:")

with st.container(border=True):
    st.markdown("**Notifications sur le téléphone (ntfy)**")
    st.caption("Installe l'appli ntfy, puis « S'abonner » avec ce sujet. Ne le partage pas : il sert de mot de passe.")
    st.code(notify.topic(), language=None)
    if st.button("Envoyer une notification de test", icon=":material/notifications:"):
        st.toast("Envoyée" if notify.push("Test Patrimoine", "Les notifications fonctionnent.") else "Échec",
                 icon=":material/check:")

with st.container(border=True):
    st.markdown("**Connexions**")
    con = db.connect(__import__("patrimoine.config", fromlist=["Settings"]).Settings().db_path)
    db.init(con)
    until = db.get_meta(con, "cmb_consent_until")
    last = db.get_meta(con, "last_sync") or {}
    con.close()
    st.markdown(f"- Accès CMB valable jusqu'au **{until[:10] if until else '?'}** (à renouveler avec Claude).\n"
                f"- Dernière synchronisation : **{(last.get('at') or 'jamais')[:16].replace('T', ' ')}** (UTC).\n"
                "- Synchronisation automatique chaque jour à 7 h 30, rapport hebdo le dimanche à 18 h.")
    for line in last.get("summary", []):
        st.caption(line)
