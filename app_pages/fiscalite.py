import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from patrimoine import queries, ui


@st.cache_data(ttl="10m", show_spinner=False)
def fees() -> pd.DataFrame:
    return ui._load(queries.fees_by_year)


today = pd.Timestamp.today().normalize()
year = str(today.year)
tax = ui.taxes()
if not tax.empty:
    tax.index = tax.index.astype(str)
pos = ui.positions()
opens = ui.account_open_dates()

st.subheader("Fiscalité et frais", icon=":material/gavel:")

# ---------- this year ----------
cur = tax.loc[year] if year in tax.index else pd.Series(dtype=float)
g = lambda k: float(cur.get(k, 0.0) or 0.0)  # noqa: E731
cto = pos[pos.account == "Compte-titres"] if not pos.empty else pos
latent_cto = float(cto.gain.sum()) if not cto.empty else 0.0
carry = g("moins_values_reportables")
with st.container(border=True):
    st.markdown(f"**{year}, année en cours** · compte-titres (le PEA et le PEG ne sont pas imposés tant que tu n'en "
                "retires rien)")
    with st.container(horizontal=True):
        st.metric("Plus-values réalisées", ui.eur(g("plus_values"), sign=True), border=True,
                  help="Ventes du compte-titres depuis le 1er janvier, au PMP frais compris.")
        st.metric("Dividendes et intérêts", ui.eur(g("dividendes") + g("interets")), border=True)
        st.metric("Impôt estimé à ce jour", ui.eur(max(g("pfu_estime"), 0)), border=True,
                  help="PFU 30 % sur les plus-values imposables, dividendes et intérêts, moins ce qui a déjà été "
                       "prélevé. Payé l'an prochain avec la déclaration (vérifier l'IFU de Trade Republic).")
        st.metric("Moins-values reportables", ui.eur(carry), border=True,
                  help="Pertes passées non encore utilisées : elles effacent les plus-values des 10 années suivantes.")
        st.metric("Plus-values latentes du compte-titres", ui.eur(latent_cto, sign=True),
                  ui.eur(max(latent_cto - carry, 0) * 0.30) + " d'impôt si tu vendais tout", delta_color="off",
                  border=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Ce qu'il faut savoir cette année**")
        tips = []
        pea_open = opens.get("tr_pea")
        if pea_open:
            five = pd.Timestamp(pea_open) + pd.DateOffset(years=5)
            left = (five - today).days
            tips.append(f"**PEA** : première opération le {pd.Timestamp(pea_open):%d/%m/%Y} (date d'ouverture à vérifier), 5 ans le {five:%d/%m/%Y}"
                        + (f" (dans {left // 30} mois). Avant, un retrait clôture le PEA et les gains sont taxés à "
                           "30 %. N'y touche pas d'ici là." if left > 0 else ". Retraits possibles sans clôture, "
                           "seulement 17,2 % de prélèvements sociaux sur les gains."))
        losers = cto[cto.gain < 0] if not cto.empty else cto
        if not losers.empty and g("plus_values") > 0:
            tips.append(f"**Tu as {ui.eur(g('plus_values'))} de plus-values réalisées** et des lignes en perte sur le "
                        f"compte-titres ({', '.join(losers.name.str.slice(0, 25))}, {ui.eur(losers.gain.sum())}). "
                        "Vendre une ligne en perte avant le 31/12 compense ces gains (puis la racheter si tu y crois "
                        "encore) : jusqu'à " + ui.eur(min(-losers.gain.sum(), g("plus_values")) * 0.30)
                        + " d'impôt en moins.")
        elif not losers.empty:
            tips.append(f"Lignes en perte sur le compte-titres ({ui.eur(losers.gain.sum())}) : à vendre seulement si "
                        "tu réalises des plus-values ailleurs cette année, pour les compenser.")
        if carry > 0:
            tips.append(f"**{ui.eur(carry)} de moins-values reportables** : tu peux réaliser autant de plus-values "
                        "sans impôt.")
        tips.append("**Compte-titres ou PEA** : à placement égal, le PEA évite 12,8 points d'impôt sur les gains "
                    "après 5 ans. Les ETF éligibles (S&P 500, Nasdaq, MSCI World en version PEA) y ont leur place ; "
                    "le compte-titres garde ce qui n'est pas éligible (Corée, espace, terres rares).")
        tips.append("**PEG Airbus** : les gains ne supportent que 17,2 % de prélèvements sociaux, mais c'est une seule "
                    "action (ton plus gros risque de concentration) : débloquer pour diversifier ne coûte que ces 17,2 % sur les gains, pas le PFU.")
        for t in tips:
            st.markdown(f"- {t}")
    with col2:
        if not cto.empty:
            st.markdown("**Compte-titres, ligne par ligne**")
            st.dataframe(cto[["name", "value", "gain", "gain_pct"]], hide_index=True, width="stretch", column_config={
                "name": "Ligne", "value": st.column_config.NumberColumn("Valeur", format="%.0f €"),
                "gain": st.column_config.NumberColumn("Plus-value latente", format="%+.0f €"),
                "gain_pct": st.column_config.NumberColumn("%", format="percent")})

# ---------- fees ----------
f = fees()
with st.container(border=True):
    st.markdown("**Frais** · ce que te coûtent ta banque, tes ordres et tes fonds, chaque année")
    this = f.loc[year] if year in f.index else None
    held = pos[pos["isin"].isin(queries.TER)] if not pos.empty else pos
    ter_now = float((held.value * held["isin"].map(queries.TER)).sum()) if not held.empty else 0.0
    with st.container(horizontal=True):
        if this is not None:
            st.metric(f"Total {year} à ce jour", ui.eur(this.total), border=True)
        st.metric("Frais des fonds au rythme actuel", ui.eur(ter_now) + " / an", border=True,
                  help="Frais courants (TER) de tes ETF sur leur valeur actuelle, prélevés dans le cours sans "
                       "apparaître sur tes relevés.")
        st.metric("Banque (CMB)", ui.eur(this.banque if this is not None else 0), "cotisation Offre Jeunes 4,70 € / mois",
                  delta_color="off", border=True,
                  help="Elle augmentera à la fin de l'offre jeunes : une banque en ligne gratuite ferait économiser "
                       "ces frais (Trade Republic sert déjà de compte courant pour la carte).")
        st.metric("Courtage", ui.eur(this.courtage if this is not None else 0),
                  f"{int(this.ordres) if this is not None else 0} opérations", delta_color="off", border=True,
                  help="1 € par ordre chez Trade Republic ; les plans d'épargne sont gratuits.")
    col1, col2 = st.columns([3, 2])
    with col1:
        fig = go.Figure([
            go.Bar(x=f.index, y=f.banque, name="Banque", marker_color=ui.CATEGORICAL[1], hovertemplate="%{y:,.0f} €"),
            go.Bar(x=f.index, y=f.courtage, name="Courtage", marker_color=ui.CATEGORICAL[3], hovertemplate="%{y:,.0f} €"),
            go.Bar(x=f.index, y=f.frais_fonds, name="Frais des fonds (estimés)", marker_color=ui.CATEGORICAL[0],
                   hovertemplate="%{y:,.0f} €"),
        ])
        ui.plotly_layout(fig, 300)
        fig.update_layout(barmode="stack")
        fig.update_yaxes(ticksuffix=" €")
        st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)
    with col2:
        if not held.empty:
            t = held.assign(ter=held["isin"].map(queries.TER), cost=held.value * held["isin"].map(queries.TER))
            st.dataframe(t[["name", "value", "ter", "cost"]].sort_values("cost", ascending=False), hide_index=True,
                         width="stretch", column_config={
                             "name": "Fonds", "value": st.column_config.NumberColumn("Valeur", format="%.0f €"),
                             "ter": st.column_config.NumberColumn("Frais / an", format="percent"),
                             "cost": st.column_config.NumberColumn("Coût / an", format="%.0f €")})
        st.caption("Le Nasdaq x2 coûte 0,60 %/an, quatre fois un ETF S&P 500 ; le levier coûte aussi en « décote de "
                   "volatilité ». Frais des fonds : taux publiés, à vérifier dans leurs DIC.")

# ---------- past years ----------
if not tax.empty:
    with st.container(border=True):
        st.markdown("**Années passées** · compte-titres, estimation PFU 30 % à comparer avec l'IFU")
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
        st.dataframe(table.T, width="stretch",
                     column_config={y: st.column_config.NumberColumn(y, format="%.2f €") for y in table.index})
