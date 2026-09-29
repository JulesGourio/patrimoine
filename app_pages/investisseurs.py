import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from patrimoine import investors, politicians, radar, ui
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


@st.cache_data(ttl="1h", show_spinner=False)
def load_fund_perf() -> pd.DataFrame:
    return ui._load(investors.performance)


@st.cache_data(ttl="1h", show_spinner=False)
def load_radar() -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
    from patrimoine import db

    return ui._load(lambda con: (radar.load(con), radar.selling(con), db.get_meta(con, "radar_at")))


def radar_view() -> None:
    r, sold, at = load_radar()
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption("Ce que l'argent suivi achète : élus sélectionnés et autres élus (90 jours), fonds 13F (dernier "
                   "trimestre, les fonds qui battent le marché comptent double), tendance des cours et avis des "
                   "analystes. Des idées à creuser, pas des ordres : tout est public et en retard."
                   + (f" Calculé le {at[:10]}." if at else ""))
        if st.button("Recalculer", icon=":material/refresh:", help="Quelques minutes (cours et analystes Yahoo)."):
            with st.spinner("Calcul du radar…"):
                ui._load(radar.build)
            st.cache_data.clear()
            st.rerun()
    if r.empty:
        st.info("Radar pas encore calculé : clique sur « Recalculer » (la synchronisation quotidienne le fait aussi).",
                icon=":material/info:")
        return

    st.markdown("#### À regarder en premier")
    cols = st.columns(3)
    for i, row in r.head(6).iterrows():
        with cols[i % 3], st.container(border=True, height="stretch"):
            st.markdown(f"**{row.ticker}** · {row['name'] or ''}")
            with st.container(horizontal=True):
                st.metric("3 mois", ui.pct(row.r3m) if pd.notna(row.r3m) else "–", border=False)
                st.metric("Objectif analystes", ui.pct(row.upside) if pd.notna(row.upside) else "–", border=False)
                st.metric("Chez toi", ui.eur(row.mine_eur) if row.mine_eur else "–", border=False,
                          help=row.mine_via or "Tu n'en détiens pas.")
            st.caption(row.why)

    col1, col2 = st.columns([3, 2])
    with col1, st.container(border=True):
        st.markdown("**Le radar complet** · classé par score (élus suivis ×3, bons fonds ×2, tendance, analystes) · "
                    "clique sur une ligne pour ouvrir sa fiche plus bas")
        t = r.assign(sector=r.sector.fillna("–"))
        picked = st.dataframe(t[["ticker", "name", "sector", "score", "cg_sel_buyers", "cg_buyers", "fd_buyers", "fd_holders",
                        "r1m", "r3m", "r1y", "from_high", "rating", "upside", "mine_eur"]],
                     hide_index=True, width="stretch", height=520, on_select="rerun", selection_mode="single-row",
                     key="radar_tbl", column_config={
                         "ticker": "Ticker", "name": st.column_config.TextColumn("Société", width="medium"),
                         "sector": "Secteur",
                         "score": st.column_config.ProgressColumn("Score", format="%.1f", min_value=0,
                                                                  max_value=float(r.score.max())),
                         "cg_sel_buyers": st.column_config.NumberColumn("Élus suivis", format="%d"),
                         "cg_buyers": st.column_config.NumberColumn("Élus", format="%d"),
                         "fd_buyers": st.column_config.NumberColumn("Fonds acheteurs", format="%d"),
                         "fd_holders": st.column_config.NumberColumn("Fonds détenteurs", format="%d"),
                         "r1m": st.column_config.NumberColumn("1 mois", format="percent"),
                         "r3m": st.column_config.NumberColumn("3 mois", format="percent"),
                         "r1y": st.column_config.NumberColumn("1 an", format="percent"),
                         "from_high": st.column_config.NumberColumn("vs plus haut", format="percent",
                                                                    help="Écart au plus haut sur un an."),
                         "rating": st.column_config.NumberColumn("Analystes", format="%.1f",
                                                                 help="1 = achat fort, 3 = conserver, 5 = vente."),
                         "upside": st.column_config.NumberColumn("Objectif", format="percent",
                                                                 help="Objectif de cours moyen des analystes."),
                         "mine_eur": st.column_config.NumberColumn("Chez toi", format="%.0f €",
                                                                   help="Via tes ETF (10 premières lignes) ou en direct.")})
    with col2, st.container(border=True):
        st.markdown("**Tendances** · secteurs où l'argent suivi se place")
        sec = r.groupby(r.sector.fillna("Autre")).agg(score=("score", "sum"), n=("ticker", "size"),
                                                      who=("ticker", lambda x: ", ".join(x[:5])))
        sec = sec.sort_values("score").tail(10)
        fig = go.Figure(go.Bar(x=sec.score, y=sec.index, orientation="h", marker_color=ui.CATEGORICAL[0],
                               customdata=sec[["n", "who"]],
                               hovertemplate="%{y} : %{customdata[0]} titre(s) · %{customdata[1]}<extra></extra>"))
        ui.plotly_layout(fig, 60 + 32 * len(sec))
        fig.update_xaxes(showticklabels=False)
        st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)
        st.markdown("**Élan** · les titres du radar qui montent le plus sur 3 mois")
        mom = r.dropna(subset=["r3m"]).sort_values("r3m", ascending=False).head(6)
        st.dataframe(mom[["ticker", "name", "r3m", "from_high"]], hide_index=True, width="stretch", column_config={
            "ticker": "Ticker", "name": "Société", "r3m": st.column_config.NumberColumn("3 mois", format="percent"),
            "from_high": st.column_config.NumberColumn("vs plus haut", format="percent")})

    rows = picked.selection.rows if picked and picked.selection else []
    tickers = list(r.ticker)
    default = rows[0] if rows else 0
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown("**Fiche d'un titre**")
            tk = st.selectbox("Titre", tickers, index=default, key=f"radar_pick_{default}", width=320,
                              format_func=lambda x: f"{x} · {r.set_index('ticker').at[x, 'name'] or ''}",
                              label_visibility="collapsed")
        row = r[r.ticker == tk].iloc[0]
        d = load_detail(tk)
        with st.container(horizontal=True):
            st.metric("Cours", f"{row.price:,.2f} $".replace(",", " ").replace(".", ",") if pd.notna(row.price) else "–",
                      ui.pct(row.r3m) + " sur 3 mois" if pd.notna(row.r3m) else None, border=True)
            st.metric("Objectif des analystes", f"{row.target:,.0f} $".replace(",", " ") if pd.notna(row.target) else "–",
                      ui.pct(row.upside) if pd.notna(row.upside) else None, border=True,
                      help=f"{int(row.analysts)} analystes, note {row.rating:.1f}/5 (1 = achat fort)."
                      if pd.notna(row.analysts) and pd.notna(row.rating) else None)
            st.metric("Écart au plus haut sur 1 an", ui.pct(row.from_high) if pd.notna(row.from_high) else "–", border=True)
            st.metric("Chez toi", ui.eur(row.mine_eur) if row.mine_eur else "–", row.mine_via or None,
                      delta_color="off", border=True)
        c1, c2 = st.columns([3, 2])
        with c1:
            px_ = load_price(tk)
            tr = d["trades"]
            if not px_.empty:
                fig = go.Figure(go.Scatter(x=px_.index, y=px_.values, name="Cours", line=dict(color=ui.CATEGORICAL[0], width=2),
                                           hovertemplate="%{y:,.2f} $<extra></extra>"))
                for side, color, symbol in (("achat", ui.CATEGORICAL[2], "triangle-up"),
                                            ("vente", ui.CATEGORICAL[7], "triangle-down")):
                    x = tr[tr.action.str.startswith(side)] if not tr.empty else tr
                    x = x[pd.to_datetime(x.tx_date) >= px_.index[0]] if not x.empty else x
                    if x.empty:
                        continue
                    ys = [px_.asof(pd.Timestamp(dd)) for dd in x.tx_date]
                    fig.add_trace(go.Scatter(x=pd.to_datetime(x.tx_date), y=ys, mode="markers", name=f"{side} d'élu",
                                             marker=dict(color=color, size=11, symbol=symbol,
                                                         line=dict(width=1, color="white")),
                                             customdata=x[["name", "amount_min", "amount_max"]].fillna(0),
                                             hovertemplate="%{customdata[0]} · %{customdata[1]:,.0f}-%{customdata[2]:,.0f} $"
                                                           "<extra></extra>"))
                if pd.notna(row.target):
                    fig.add_hline(y=row.target, line_dash="dot", line_color=ui.OTHER,
                                  annotation_text="objectif analystes", annotation_position="top left")
                ui.plotly_layout(fig, 340)
                fig.update_layout(hovermode="closest")
                fig.update_yaxes(ticksuffix=" $")
                st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)
            st.caption(row.why)
        with c2:
            f = d["funds"]
            st.markdown("**Fonds qui le détiennent** (dernier 13F)")
            if f.empty:
                st.caption("Aucun fonds suivi.")
            else:
                st.dataframe(f[["fund", "change", "weight", "weight_prev"]], hide_index=True, width="stretch",
                             column_config={"fund": "Fonds", "change": "Mouvement",
                                            "weight": st.column_config.NumberColumn("Poids", format="percent"),
                                            "weight_prev": st.column_config.NumberColumn("Avant", format="percent")})
            st.markdown("**Élus** (2 ans)")
            if tr.empty:
                st.caption("Aucune opération d'élu.")
            else:
                tt = tr.sort_values("tx_date", ascending=False).assign(
                    montant=[amount(a, b) for a, b in zip(tr.amount_min, tr.amount_max)])
                st.dataframe(tt[["tx_date", "name", "action", "montant"]].head(30), hide_index=True, width="stretch",
                             column_config=TRADE_COLUMNS)

    col1, col2 = st.columns(2)
    with col1, st.container(border=True):
        st.markdown("**Sur tes lignes** · ce que l'argent suivi fait sur ce que tu détiens déjà")
        mine = r[r.mine_eur > 0]
        if mine.empty:
            st.caption("Aucun titre du radar dans tes lignes.")
        else:
            st.dataframe(mine[["ticker", "name", "mine_eur", "mine_via", "why"]], hide_index=True, width="stretch",
                         column_config={"ticker": "Ticker", "name": "Société",
                                        "mine_eur": st.column_config.NumberColumn("Chez toi", format="%.0f €"),
                                        "mine_via": "Via", "why": st.column_config.TextColumn("Signal", width="large")})
        st.caption("Tes ETF S&P 500 et Nasdaq x2 contiennent les géants américains : quand l'argent suivi les achète, "
                   "tu es déjà exposé. Airbus et tes ETF Corée, espace, terres rares n'y apparaissent presque jamais.")
    with col2, st.container(border=True):
        st.markdown("**Ce qu'ils vendent** · plus de vendeurs que d'acheteurs (élus 90 j + fonds)")
        if not sold.empty:
            st.dataframe(sold[["ticker", "name", "cg_sellers", "fd_sellers", "cg_buyers", "fd_buyers"]].head(15),
                         hide_index=True, width="stretch", column_config={
                             "ticker": "Ticker", "name": "Société",
                             "cg_sellers": st.column_config.NumberColumn("Élus vendeurs", format="%d"),
                             "fd_sellers": st.column_config.NumberColumn("Fonds vendeurs", format="%d"),
                             "cg_buyers": st.column_config.NumberColumn("Élus acheteurs", format="%d"),
                             "fd_buyers": st.column_config.NumberColumn("Fonds acheteurs", format="%d")})


@st.cache_data(ttl="1h", show_spinner=False)
def load_detail(ticker: str) -> dict:
    return ui._load(lambda con: radar.detail(con, ticker))


@st.cache_data(ttl="6h", show_spinner=False)
def load_price(ticker: str) -> pd.Series:
    from patrimoine.prices import closes

    px_ = closes([ticker], (pd.Timestamp.today() - pd.DateOffset(years=1)).date())
    return px_[ticker].dropna() if ticker in px_ else pd.Series(dtype=float)


@st.cache_data(ttl="1h", show_spinner=False)
def load_ranking(months: int) -> pd.DataFrame:
    return ui._load(lambda con: politicians.ranking(con, months))


@st.cache_data(ttl="1h", show_spinner=False)
def load_trades(pid: str | None = None, days: int | None = None) -> pd.DataFrame:
    since = (pd.Timestamp.today() - pd.Timedelta(days=days)).date().isoformat() if days else None
    return ui._load(lambda con: politicians.trades(con, pid, since))


@st.cache_data(ttl="1h", show_spinner=False)
def load_congress_consensus(days: int) -> pd.DataFrame:
    return ui._load(lambda con: politicians.consensus(con, days))


def amount(lo: float, hi: float) -> str:
    def k(x: float) -> str:
        return f"{x / 1e6:.1f} M$".replace(".", ",") if x >= 1e6 else f"{x / 1e3:.0f} k$"

    if pd.isna(lo):
        return "?"
    return f"{k(lo)} – {k(hi)}" if pd.notna(hi) else f"plus de {k(lo)}"


TRADE_COLUMNS = {
    "filed": st.column_config.DateColumn("Déclaré", format="DD/MM/YY"),
    "tx_date": st.column_config.DateColumn("Opération", format="DD/MM/YY"),
    "name": "Élu", "chamber_label": "Chambre", "action": "Sens", "ticker": "Ticker",
    "asset": st.column_config.TextColumn("Titre", width="medium"), "asset_type": "Type", "owner": "Pour",
    "montant": "Montant déclaré",
    "ret": st.column_config.NumberColumn("Depuis", format="percent", help="Variation du cours depuis la date de "
                                                                          "l'opération (sous-jacent pour une option)."),
    "excess": st.column_config.NumberColumn("vs S&P 500", format="percent"),
    "comment": st.column_config.TextColumn("Détail", width="medium"),
}


def congress_view() -> None:
    st.caption("Déclarations obligatoires des élus du Congrès (STOCK Act) : Chambre des représentants et Sénat, "
               "sources officielles. Publiées jusqu'à 45 jours après l'opération, en fourchettes de montant, souvent "
               "au nom du conjoint. Performance estimée : cours depuis chaque achat, comparé au S&P 500 sur la même "
               "période, pondéré par le milieu de la fourchette. Ça dit si leurs choix battent l'indice, pas ce que "
               "leur compte a gagné.")
    with st.container(horizontal=True, vertical_alignment="center"):
        months = st.segmented_control("Fenêtre", [12, 24, 36], default=24, format_func=lambda m: f"{m} mois",
                                      key="cg_months", label_visibility="collapsed") or 24
        show_all = st.toggle("Voir tous les élus", key="cg_all",
                             help="Par défaut, seulement la sélection : Pelosi et les élus actifs dont les achats "
                                  "battent le S&P 500 d'au moins 5 points (15 achats minimum, 40 % gagnants), "
                                  "plus ceux que tu coches.")
        only_followed = not show_all
    r = load_ranking(months)
    if r.empty:
        st.info("Aucune déclaration importée : la synchronisation quotidienne s'en charge.", icon=":material/info:")
        return
    view = r[r.followed] if only_followed else r

    with st.container(horizontal=True):
        best = view[view.buys >= 10].head(1)
        st.metric("Élus classés", f"{(r.buys >= 10).sum()}", f"{r.followed.sum()} suivis", delta_color="off",
                  border=True, help="Au moins 10 achats d'actions ou d'options sur la fenêtre (les élus suivis restent "
                                    "affichés en bas).")
        if not best.empty:
            st.metric("En tête de la sélection" if only_followed else "En tête", best["name"].iloc[0], ui.pct(best.excess.iloc[0]) + " vs S&P 500", border=True)
        recent_all = load_trades(days=30)
        st.metric("Opérations déclarées sur 30 jours", f"{len(recent_all)}", border=True)

    with st.container(border=True):
        st.markdown("**Classement** · écart moyen au S&P 500 de leurs achats · « Suivi » : leurs nouvelles "
                    "opérations arrivent dans le récapitulatif quotidien (coche ou décoche pour changer la sélection)")
        table = view.fillna({"state": "–", "top": "–"}).assign(volume_txt=view.volume.map(lambda v: amount(v, None).replace("plus de ", "≈ ")))
        cols = ["followed", "name", "chamber", "state", "buys", "sales", "ret", "excess", "hit_rate", "options",
                "volume_txt", "top", "last_filed"]
        edited = st.data_editor(
            table[cols], hide_index=True, width="stretch", height=min(40 + 35 * len(table), 420), key=f"cg_rank_{months}_{only_followed}",
            disabled=[c for c in cols if c != "followed"],
            column_config={
                "followed": st.column_config.CheckboxColumn("Suivi"), "name": "Élu", "chamber": "Chambre",
                "state": "État", "buys": st.column_config.NumberColumn("Achats"),
                "sales": st.column_config.NumberColumn("Ventes"),
                "ret": st.column_config.NumberColumn("Perf. achats", format="percent",
                                                     help="Variation moyenne pondérée depuis chaque achat."),
                "excess": st.column_config.NumberColumn("vs S&P 500", format="percent",
                                                        help="Même calcul moins le S&P 500 sur les mêmes dates."),
                "hit_rate": st.column_config.ProgressColumn("Achats gagnants", format="percent", min_value=0,
                                                            max_value=1, help="Part des achats qui battent l'indice."),
                "options": st.column_config.NumberColumn("Options", format="percent",
                                                         help="Part des opérations en options : très risqué."),
                "volume_txt": "Volume estimé", "top": st.column_config.TextColumn("Principaux achats", width="medium"),
                "last_filed": st.column_config.DateColumn("Dernière décl.", format="DD/MM/YY")})
        changed = edited[edited.followed != table.followed]
        if not changed.empty:
            con = ui.connect()
            try:
                from patrimoine.sources import congress

                for i in changed.index:
                    congress.follow(con, table.at[i, "id"], bool(edited.at[i, "followed"]))
            finally:
                con.close()
            st.cache_data.clear()
            st.toast("Suivi mis à jour", icon=":material/check:")
            st.rerun()

    names = dict(zip(view["name"] + " · " + view.chamber, view.id))
    keys = list(names)
    best_followed = next((i for i, f in enumerate(view.followed) if f), 0)  # the ranking is sorted: best followed
    choice = st.selectbox("Élu", keys, index=best_followed, label_visibility="collapsed", key="cg_pick")
    pid = names[choice]
    t = load_trades(pid)
    row = view[view.id == pid].iloc[0]
    with st.container(horizontal=True):
        st.metric(row["name"], row.chamber + (f" · {row.state}" if row.state else ""),
                  "suivi" if row.followed else "non suivi", delta_color="off", border=True)
        st.metric("Achats sur la fenêtre", f"{row.buys}", f"{row.sales} ventes", delta_color="off", border=True)
        st.metric("Perf. moyenne de ses achats", ui.pct(row.ret), ui.pct(row.excess) + " vs S&P 500"
                  if pd.notna(row.excess) else None, border=True)
        st.metric("Délai moyen de déclaration", f"{t.delay_days.median():.0f} jours" if not t.empty else "–",
                  border=True, help="Entre l'opération et sa publication : ce que tu vois a déjà ce retard.")

    col1, col2 = st.columns([2, 3])
    with col1, st.container(border=True):
        st.markdown("**Ce qu'il ou elle achète le plus** · montant estimé")
        buys = t[(t.action == "achat") & t.ticker.notna()]
        top = buys.groupby("ticker").agg(montant=("amount_mid", "sum"), n=("id", "size"), ret=("ret", "mean")) \
            .sort_values("montant", ascending=False).head(12).iloc[::-1]
        if not top.empty:
            fig = go.Figure(go.Bar(x=top.montant, y=top.index, orientation="h", marker_color=[
                ui.CATEGORICAL[2] if (v or 0) >= 0 else ui.CATEGORICAL[7] for v in top.ret.fillna(0)],
                customdata=top[["n", "ret"]].fillna(0),
                hovertemplate="%{y} : %{x:,.0f} $ en %{customdata[0]} achat(s), %{customdata[1]:+.0%} depuis"
                              "<extra></extra>"))
            ui.plotly_layout(fig, 70 + 26 * len(top))
            fig.update_xaxes(tickformat="~s", ticksuffix=" $")
            st.plotly_chart(fig, width="stretch", config=ui.PLOT_CONFIG)
            st.caption("Vert : le titre a monté depuis ses achats, rouge : baissé.")
    with col2, st.container(border=True):
        st.markdown("**Ses opérations**")
        tt = t.sort_values(["tx_date", "filed"], ascending=False).fillna({"ticker": "–", "comment": ""}).assign(montant=[amount(a, b) for a, b in zip(t.amount_min, t.amount_max)])
        st.dataframe(tt[["tx_date", "filed", "action", "ticker", "asset", "asset_type", "owner", "montant", "ret",
                         "excess", "comment"]], hide_index=True, width="stretch", height=70 + 26 * 12,
                     column_config=TRADE_COLUMNS)

    col1, col2 = st.columns(2)
    with col1, st.container(border=True):
        st.markdown("**Dernières opérations des élus suivis** · 60 jours")
        rec = load_trades(days=105)
        rec = rec[(rec.followed == 1) & (rec.filed >= (pd.Timestamp.today() - pd.Timedelta(days=60)).date().isoformat())]
        rec = rec.sort_values(["tx_date", "filed"], ascending=False)
        rec = rec.fillna({"ticker": "–"}).assign(montant=[amount(a, b) for a, b in zip(rec.amount_min, rec.amount_max)])
        st.dataframe(rec[["tx_date", "filed", "name", "action", "ticker", "montant", "ret"]], hide_index=True,
                     width="stretch", height=380, column_config=TRADE_COLUMNS)
        st.caption("Triées par date d'opération ; « Déclaré » : date de publication, souvent des semaines plus tard.")
    with col2, st.container(border=True):
        st.markdown("**Titres traités par plusieurs élus** · 90 jours")
        c = load_congress_consensus(90).head(25)
        if not c.empty:
            st.dataframe(c[["ticker", "asset", "buyers", "sellers", "bought", "who"]], hide_index=True, width="stretch",
                         height=380, column_config={
                             "ticker": "Ticker", "asset": st.column_config.TextColumn("Titre", width="small"),
                             "buyers": st.column_config.NumberColumn("Acheteurs"),
                             "sellers": st.column_config.NumberColumn("Vendeurs"),
                             "bought": st.column_config.NumberColumn("Achats ($)", format="compact"),
                             "who": st.column_config.TextColumn("Qui", width="medium")})


st.subheader("Investisseurs suivis", icon=":material/groups:")
section = st.segmented_control("Vue", ["Radar", "Fonds (13F)", "Élus américains"], default="Radar",
                               key="inv_section", label_visibility="collapsed") or "Radar"


def funds() -> None:
    st.caption("Déclarations 13F à la SEC : positions longues cotées aux États-Unis à la fin de chaque trimestre, publiées "
               "jusqu'à 45 jours plus tard. Ni ventes à découvert, ni liquidités, ni actions hors US : une vue partielle "
               "et en retard, utile pour repérer des convictions, pas pour copier en temps réel.")

    perf = load_fund_perf()
    if not perf.empty:
        with st.container(border=True):
            st.markdown("**Qui bat le marché** · rendement si tu avais copié les 20-25 premières lignes de chaque 13F "
                        "le jour de sa publication, jusqu'au suivant")
            best = perf.iloc[0]
            with st.container(horizontal=True):
                st.metric("Meilleur", best["name"], ui.pct(best.excess) + " vs S&P 500", border=True,
                          help=f"{best.manager}, depuis le {best.since}.")
                st.metric("Fonds qui battent l'indice", f"{(perf.excess > 0).sum()} / {len(perf)}", border=True)
            st.dataframe(perf[["name", "manager", "style", "ret", "bench", "excess", "annual", "last_quarter", "since"]],
                         hide_index=True, width="stretch", column_config={
                             "name": "Fonds", "manager": "Gérant", "style": "Style",
                             "ret": st.column_config.NumberColumn("Copie 13F", format="percent"),
                             "bench": st.column_config.NumberColumn("S&P 500", format="percent"),
                             "excess": st.column_config.NumberColumn("Écart", format="percent"),
                             "annual": st.column_config.NumberColumn("Par an", format="percent"),
                             "last_quarter": st.column_config.NumberColumn("Dernier trimestre", format="percent"),
                             "since": st.column_config.DateColumn("Depuis", format="DD/MM/YY")})
            st.caption("Avant frais et impôts, positions longues cotées aux États-Unis seulement. Les fonds très en "
                       "retard sur l'indice (Akre, Durable, Fundsmith, Lone Pine, Third Point) ne sont plus suivis.")

    ov = load_overview()
    if ov.empty:
        st.info("Aucune déclaration importée : la synchronisation quotidienne s'en charge.", icon=":material/info:")
        return

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


if section == "Radar":
    radar_view()
elif section == "Fonds (13F)":
    funds()
else:
    congress_view()
