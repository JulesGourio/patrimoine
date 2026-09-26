import streamlit as st

from patrimoine import ui

st.subheader("Fiscalité du compte-titres", icon=":material/gavel:")
st.caption(
    "Estimation au prélèvement forfaitaire unique (30 %) à partir de tes opérations : à comparer avec l'IFU "
    "de Trade Republic avant la déclaration. Le PEA n'est pas imposé tant que tu n'en retires rien."
)

tax = ui.taxes()
if tax.empty:
    st.info("Aucune opération imposable.", icon=":material/info:")
    st.stop()

cols = {
    "plus_values": "Plus-values nettes de l'année",
    "moins_values_imputees": "Moins-values antérieures imputées",
    "plus_values_imposables": "Plus-values imposables",
    "moins_values_reportables": "Moins-values reportables (10 ans)",
    "dividendes": "Dividendes bruts",
    "interets": "Intérêts bruts",
    "deja_preleve": "Déjà prélevé à la source",
    "pfu_estime": "Reste à payer estimé (PFU 30 %)",
}
table = tax.reindex(columns=list(cols)).fillna(0).rename(columns=cols)
table.index = table.index.astype(str)

with st.container(horizontal=True):
    for year, row in table.iloc[::-1].head(3).iterrows():
        st.metric(f"Impôt estimé {year}", ui.eur(row[cols["pfu_estime"]]),
                  ui.eur(row[cols["plus_values_imposables"]]) + " de plus-values imposables",
                  delta_color="off", border=True)

with st.container(border=True):
    st.dataframe(table.T, width="stretch",
                 column_config={y: st.column_config.NumberColumn(y, format="%.2f €") for y in table.index})
