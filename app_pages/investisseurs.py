import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from patrimoine import investors, ui
from patrimoine.sources import sec13f


@st.cache_data(ttl="1h", show_spinner=False)
def load_overview() -> pd.DataFrame:
    return ui._load(lambda con: (sec13f.init(con), investors.overview(con))[1])


@st.cache_data(ttl="1h", show_spinner=False)
def load_portfolio(cik: int) -> tuple[pd.DataFrame, dict]:
    return ui._load(lambda con: investors.portfolio(con, cik))


@st.cache_data(ttl="1h", show_spinner=False)
def load_history(cik: int) -> pd.DataFrame:
    return ui._load(lambda con: investors.history(con, cik))


@st.cache_data(ttl="1h", show_spinner=False)
def load_consensus() -> pd.DataFrame:
    return ui._load(lambda con: investors.consensus(con, 2))


def usd(x: float) -> str:
    return (f"{x / 1e9:,.1f} Md$" if x >= 1e9 else f"{x / 1e6:,.0f} M$").replace(",", " ").replace(".", ",")


st.subheader("Investisseurs suivis", icon=":material/groups:")
st.caption("Déclarations 13F à la SEC : positions longues cotées aux États-Unis à la fin de chaque trimestre, publiées "
           "jusqu'à 45 jours plus tard. Ni ventes à découvert, ni liquidités, ni actions hors US : une vue partielle "
           "et en retard, utile pour repérer des convictions, pas pour copier en temps réel.")

ov = load_overview()
if ov.empty:
    st.info("Aucune déclaration importée : la synchronisation quotidienne s'en charge.", icon=":material/info:")
    st.stop()

with st.container(border=True):
    st.markdown("**Vue d'ensemble** · clique sur une ligne pour ouvrir l'investisseur")
    table = ov.assign(total=ov.total_usd.map(usd))
    event = st.dataframe(
        table[["name", "manager", "style", "period", "total", "positions", "top10", "top3"]], hide_index=True,
        width="stretch", on_select="rerun", selection_mode="single-row", key="inv_table",
        column_config={"name": "Fonds", "manager": "Gérant", "style": "Style", "period": "Trimestre",
                       "total": "Encours 13F", "positions": st.column_config.NumberColumn("Lignes"),
                       "top10": st.column_config.ProgressColumn("Poids des 10 premières", format="percent",
                                                                min_value=0, max_value=1),
                       "top3": st.column_config.TextColumn("Plus grosses lignes", width="large")})

rows = event.selection.rows if event and event.selection else []
names = list(ov.name)
default = names.index(ov.iloc[rows[0]]["name"]) if rows else 0
choice = st.selectbox("Investisseur", names, index=default, label_visibility="collapsed")
cik = int(ov[ov.name == choice].cik.iloc[0])
m, meta = load_portfolio(cik)
stock = m[(m.put_call == "") & (m.change != "vendue")]
options = m[(m.put_call != "") & (m.change != "vendue")]

with st.container(horizontal=True):
    st.metric(meta["manager"] or meta["name"], usd(meta["total_usd"]), f"au {meta['period']}", delta_color="off",
              border=True, help=f"Déposé le {meta['filed']}.")
    st.metric("Lignes en actions", f"{len(stock)}", border=True)
    st.metric("Poids des 10 premières", ui.pct(stock.weight.head(10).sum(), sign=False), border=True)
    counts = m.change.value_counts()
    st.metric("Nouvelles lignes", f"{counts.get('nouvelle', 0)}", f"{counts.get('vendue', 0)} vendues",
              delta_color="off", border=True)
    st.metric("Options", ui.pct(options.weight.sum(), sign=False) if not options.empty else "–", border=True,
              help="Part de l'encours déclarée en options d'achat (CALL) ou de vente (PUT).")

col1, col2 = st.columns([2, 3])
with col1, st.container(border=True):
    st.markdown("**Plus grosses lignes**")
    top = stock.head(15).iloc[::-1]
    label = top.ticker.fillna(top.issuer.str.slice(0, 22))
    colors = {"nouvelle": ui.CATEGORICAL[2], "renforcée": ui.CATEGORICAL[0], "allégée": ui.CATEGORICAL[1],
              "=": ui.OTHER}
    fig = go.Figure(go.Bar(x=top.weight, y=label, orientation="h",
                           marker_color=[colors.get(c, ui.OTHER) for c in top.change],
                           text=[f"{w:.1%}".replace(".", ",") for w in top.weight], textposition="outside",
                           cliponaxis=False, customdata=top[["issuer", "change"]],
                           hovertemplate="%{customdata[0]} · %{customdata[1]}<extra></extra>"))
    ui.plotly_layout(fig, 70 + 26 * len(top))
    fig.update_xaxes(tickformat=".0%")
    st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)
    st.caption("Couleur : vert nouvelle ligne, bleu renforcée, orange allégée, gris inchangée.")
with col2, st.container(border=True):
    st.markdown(f"**Mouvements depuis {meta.get('previous_period') or 'le trimestre précédent'}**")
    moves = m[m.change != "="].assign(value=m[["value_usd", "value_usd_prev"]].max(axis=1)) \
        .sort_values("value", ascending=False)
    st.dataframe(moves[["issuer", "ticker", "put_call", "change", "shares_change", "weight", "weight_prev", "value"]],
                 hide_index=True, width="stretch", height=70 + 26 * len(top), column_config={
                     "issuer": "Société", "ticker": "Ticker", "put_call": "Option", "change": "Mouvement",
                     "shares_change": st.column_config.NumberColumn("Actions", format="percent",
                                                                    help="Variation du nombre d'actions."),
                     "weight": st.column_config.NumberColumn("Poids", format="percent"),
                     "weight_prev": st.column_config.NumberColumn("Avant", format="percent"),
                     "value": st.column_config.NumberColumn("Montant ($)", format="compact")})

with st.container(border=True):
    st.markdown("**Évolution des principales lignes** · poids dans le portefeuille à chaque trimestre")
    h = load_history(cik)
    if not h.empty:
        keep = list(stock.cusip.head(6))
        h = h[h.cusip.isin(keep)].assign(nom=lambda d: d.ticker.fillna(d.issuer.str.slice(0, 20)))
        fig = px.line(h, x="period", y="weight", color="nom", markers=True,
                      labels={"weight": "", "period": "", "nom": ""})
        fig.update_traces(line=dict(width=2), hovertemplate="%{y:.1%}")
        ui.plotly_layout(fig, 300)
        fig.update_yaxes(tickformat=".0%")
        fig.update_xaxes(type="category")
        st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)

with st.container(border=True):
    st.markdown("**Convictions partagées** · sociétés détenues par plusieurs investisseurs suivis au dernier trimestre")
    c = load_consensus().head(20)
    if not c.empty:
        c = c.assign(nom=c.ticker.fillna(c.issuer.str.slice(0, 22)))
        long = pd.concat([c.assign(n=c.buyers, qui="achètent ou renforcent"),
                          c.assign(n=c.holders - c.buyers - c.trimmers, qui="gardent"),
                          c.assign(n=c.trimmers, qui="allègent"),
                          c.assign(n=c.sold_out, qui="vendent tout")])
        fig = px.bar(long, y="nom", x="n", color="qui", orientation="h", category_orders={"nom": list(c.nom)},
                     color_discrete_map={"achètent ou renforcent": ui.CATEGORICAL[2], "gardent": ui.OTHER,
                                         "allègent": ui.CATEGORICAL[1], "vendent tout": ui.CATEGORICAL[7]},
                     labels={"n": "Investisseurs", "nom": "", "qui": ""}, custom_data=["investors"])
        fig.update_traces(hovertemplate="%{x} %{fullData.name}<extra></extra>")
        ui.plotly_layout(fig, 80 + 24 * len(c))
        st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)
        st.dataframe(c[["issuer", "ticker", "holders", "buyers", "sellers", "avg_weight", "investors"]],
                     hide_index=True, width="stretch", column_config={
                         "issuer": "Société", "ticker": "Ticker", "holders": "Détenteurs", "buyers": "Achètent",
                         "sellers": "Allègent", "avg_weight": st.column_config.NumberColumn("Poids moyen",
                                                                                          format="percent"),
                         "investors": st.column_config.TextColumn("Qui", width="large")})
