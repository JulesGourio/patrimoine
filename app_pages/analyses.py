import subprocess
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from patrimoine import brief_mail, briefing, ui
from patrimoine.config import ROOT

GREEN, RED, GREY = "#15803d", "#b91c1c", "#8a8983"
VERDICT_BADGE = {"rien à faire": "gray", "surveiller": "orange", "agir": "blue"}
TONE_BADGE = {"haussier": "green", "baissier": "red", "mitigé": "orange", "calme": "gray"}

con = ui.connect()
b = briefing.load(con)


def launch(period: str) -> None:
    """Claude Code runs in the background (5 to 10 minutes); the page shows the result once published."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen([sys.executable, "-m", "patrimoine.cli", "rapport" if period == "semaine" else "analyse",
                      "--sans-sync"], cwd=ROOT, creationflags=flags)
    st.toast("Analyse lancée : elle arrive dans 5 à 10 minutes (mail et cette page).", icon=":material/schedule:")


with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader("Analyses", icon=":material/insights:")
    if not b.empty:
        labels = {r.id: f"{brief_mail.day_label(r.session)} · {'semaine' if r.kind == 'hebdo' else 'séance'}"
                  for r in b.itertuples()}
        chosen = st.selectbox("Analyse", list(labels), format_func=labels.get, label_visibility="collapsed",
                              width=240, key="an_pick")
    with st.popover("Nouvelle analyse", icon=":material/play_arrow:"):
        st.caption("Claude cherche l'actualité et rédige l'analyse (5 à 10 min). Elle part aussi par mail.")
        if st.button("Dernière séance", width="stretch"):
            launch("jour")
        if st.button("Semaine", width="stretch"):
            launch("semaine")

if b.empty:
    st.info("Pas encore d'analyse publiée. Les routines Claude (claude.ai/code/routines) en écrivent une du mardi au samedi "
            "à 8 h et le dimanche à 18 h ; tu peux aussi les lancer là-bas, ou ici avec « Nouvelle analyse ».",
            icon=":material/info:")
    st.stop()

r = b[b.id == chosen].iloc[0]
f, a = r.facts, r.analysis
weekly = r.kind == "hebdo"
period = "sur 5 séances" if weekly else "sur la séance"
market = {m["symbole"]: m for m in f["marche"]}
lines = {l["isin"]: l for l in f["lignes"]}

# ---------- header ----------
st.caption(f"{'Bilan de la semaine' if weekly else 'Analyse du jour'} · séance"
           f"{'s jusqu’au' if weekly else ' du'} {brief_mail.day_label(f['seance'])} · publiée le "
           f"{pd.Timestamp(r.published_at).tz_convert('Europe/Paris'):%d/%m à %H:%M}")
st.markdown(f"### {a['titre']}  \n:{TONE_BADGE.get(a['ton'], 'gray')}-badge[{a['ton']}]")

p = f["patrimoine"]
titles_before = (p["titres"] or 0) - p["effet_marche_eur"]
with st.container(horizontal=True):
    st.metric("Patrimoine total", ui.eur(p["total"]), border=True,
              help=f"Somme des avoirs au {p['date']}, avant impôts.")
    st.metric(f"Tes titres {period}", ui.eur(p["effet_marche_eur"], sign=True),
              ui.pct(p["effet_marche_eur"] / titles_before) if titles_before else None, border=True,
              help="Variation de valeur de tes lignes (PEG Airbus compris) due aux cours, hors achats et ventes.")
    for sym in ("^GSPC", "^NDX", "^FCHI"):
        if sym in market:
            m = market[sym]
            st.metric(m["nom"], f"{m['last']:,.0f}".replace(",", " "), ui.pct(m["move"]), border=True)
    if "EURUSD=X" in market:
        m = market["EURUSD=X"]
        st.metric("Euro / dollar", f"{m['last']:.4f}".replace(".", ","), ui.pct(m["move"]), border=True,
                  help="Un euro plus fort fait baisser en euros tes lignes en dollars.")

with st.container(border=True):
    st.markdown("**L'essentiel**\n\n" + "\n".join(f"- {x}" for x in a["points_cles"]))
    if a.get("bilan_semaine"):
        st.markdown(a["bilan_semaine"])
    if a.get("a_faire"):
        st.markdown("**À faire**\n\n" + "\n".join(f"- {x}" for x in a["a_faire"]))

sources = {s["id"]: s for s in a.get("sources", [])}
ACTION_BADGE = {"acheter": "green", "renforcer": "green", "alléger": "red", "vendre": "red", "arbitrer": "blue",
                "attendre": "gray"}


def cite(refs) -> str:
    return " · ".join(f"[{sources[i].get('media') or i}]({sources[i]['url']})" for i in refs or [] if i in sources)


if a.get("conseils"):
    st.markdown("**Mes conseils**")
    cols = st.columns(min(len(a["conseils"]), 2))
    for k, c in enumerate(a["conseils"]):
        with cols[k % len(cols)], st.container(border=True):
            size = [ui.eur(c["montant_eur"])] if c.get("montant_eur") else []
            if c.get("prix_limite"):
                size.append(f"limite {c['prix_limite']:,.2f}".replace(",", " ").replace(".", ","))
            st.markdown(f":{ACTION_BADGE.get(c['action'], 'gray')}-badge[{c['action']}] **{c['cible']}**"
                        + (f" · {' · '.join(size)}" if size else "")
                        + f" :gray-badge[confiance {c['confiance']}] :gray-badge[{c['horizon']}]")
            st.markdown(c["pourquoi"])
            st.markdown(f":red[Risque :] {c['risque']}  \n**Invalidé si :** {c['invalidation']}")
            if c.get("sources"):
                st.caption("Sources : " + cite(c["sources"]))


tab_lines, tab_market, tab_ideas, tab_agenda, tab_sources, tab_verdicts, tab_reports = st.tabs(
    [":material/pie_chart: Mes lignes", ":material/public: Marchés", ":material/lightbulb: Idées et argent suivi",
     ":material/event: À venir", ":material/link: Sources", ":material/fact_check: Suivi des conseils",
     ":material/article: Rapports libres"])

# ---------- my lines ----------
with tab_lines:
    ls = sorted([l for l in f["lignes"] if l.get("move") is not None], key=lambda l: l["move"])
    names = [brief_mail.short(l) for l in ls]
    fig = go.Figure()
    fig.add_bar(y=names, x=[l["move"] for l in ls], orientation="h", name="Ta ligne (en euros)",
                marker_color=[GREEN if l["move"] >= 0 else RED for l in ls],
                customdata=[[ui.eur(l.get("impact_eur"), sign=True)] for l in ls],
                texttemplate="%{customdata[0]}", textposition="outside",
                hovertemplate="%{y} : %{x:+.2%} · %{customdata[0]}<extra></extra>")
    fig.add_scatter(y=names, x=[(l.get("indice_move") or 0) * l.get("levier", 1) if l.get("indice_move") is not None
                                else None for l in ls], mode="markers", name="Son indice (× levier)",
                    marker=dict(symbol="line-ns", size=18, line=dict(width=3, color="#111827")),
                    customdata=[[l.get("indice")] for l in ls],
                    hovertemplate="%{customdata[0]} : %{x:+.2%}<extra></extra>")
    fig.update_xaxes(tickformat="+.1%", zeroline=True, zerolinecolor=GREY)
    fig.update_layout(bargap=0.45)
    st.markdown(f"**Chaque ligne {period} et son indice**")
    st.plotly_chart(ui.plotly_layout(fig, height=60 + 42 * len(ls)), config=ui.PLOT_CONFIG)

    for v in a.get("lignes", []):
        l = lines.get(v["isin"], {"isin": v["isin"], "nom": v["isin"]})
        with st.container(border=True):
            c1, c2 = st.columns([3, 2])
            with c1:
                st.markdown(f"**{l['nom']}** · {ui.pct(l.get('move'))} "
                            f":{VERDICT_BADGE.get(v['verdict'], 'gray')}-badge[{v['verdict']}] "
                            f":gray-badge[confiance {v['confiance']}]")
                st.markdown(v["cause"])
                st.markdown(f"*Thèse :* {v['these']}")
                if v.get("action"):
                    st.markdown(f"**→ {v['action']}**")
                if v.get("sources"):
                    st.caption("Sources : " + cite(v["sources"]))
                meta = [f"du {pd.Timestamp(l['depuis']):%d/%m} au {pd.Timestamp(l['date']):%d/%m}"] if l.get("depuis") else []
                meta += [f"poids {ui.pct(l.get('poids'), sign=False)}", f"sur 1 mois {ui.pct(l.get('m1'))}"]
                if l.get("plus_value_latente_pct") is not None:
                    meta.append(f"plus-value latente {ui.pct(l['plus_value_latente_pct'])}")
                if l.get("z") is not None:
                    meta.append(f"mouvement de {abs(l['z']):.1f} écart-type".replace(".", ","))
                st.caption(" · ".join(meta))
            with c2:
                s = f["series"].get(v["isin"])
                bs = f["series"].get(l.get("indice_symbole") or "")
                if s:
                    fig = go.Figure()
                    ss = pd.Series({pd.Timestamp(d): c for d, c in s})
                    fig.add_scatter(x=ss.index, y=ss / ss.iloc[0] * 100, name="Ta ligne",
                                    line=dict(color=ui.CATEGORICAL[0], width=2))
                    if bs:
                        bb = pd.Series({pd.Timestamp(d): c for d, c in bs})
                        bb = bb[bb.index >= ss.index[0]]
                        if not bb.empty:
                            fig.add_scatter(x=bb.index, y=bb / bb.iloc[0] * 100, name=f"Indice : {l.get('indice')}",
                                            line=dict(color=GREY, width=2))
                    fig.update_yaxes(ticksuffix="")
                    st.caption("3 mois, base 100")
                    st.plotly_chart(ui.plotly_layout(fig, height=200), config=ui.PLOT_CONFIG,
                                    key=f"line_{v['isin']}")

    movers = f.get("moteurs_etf", [])
    if movers:
        st.markdown(f"**Ce qui a fait bouger tes ETF {period}**")
        st.caption("Grosses positions de tes ETF (dans l'ETF de référence américain) : variation en devise locale × "
                   "ce que tu en détiens à travers eux. Estimation.")
        mv = sorted(movers, key=lambda m: m["contribution_eur"])
        fig = go.Figure(go.Bar(
            y=[m["ticker"] for m in mv], x=[m["contribution_eur"] for m in mv], orientation="h",
            marker_color=[GREEN if m["contribution_eur"] >= 0 else RED for m in mv],
            customdata=[[f"{m['move']:+.1%}".replace(".", ","), ", ".join(brief_mail.SHORT.get(x, x) for x in m["via"]),
                         ui.eur(m["exposition_eur"])] for m in mv],
            hovertemplate="%{y} %{customdata[0]} · %{x:+.0f} € pour toi<br>détenu %{customdata[2]} via "
                          "%{customdata[1]}<extra></extra>"))
        fig.update_xaxes(ticksuffix=" €")
        fig.update_layout(bargap=0.35)
        st.plotly_chart(ui.plotly_layout(fig, height=60 + 28 * len(mv)), config=ui.PLOT_CONFIG)

# ---------- markets ----------
with tab_market:
    m = a.get("marche", {})
    st.markdown(m.get("resume", ""))
    for t in m.get("themes", []):
        st.markdown(f"**{t['titre']}.** {t['detail']} " + cite(t.get("sources")))
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown(f"**Marchés {period}**")
        df = pd.DataFrame(f["marche"])
        df["Variation"] = [f"{x * 100:+.0f} pb" if s == "^TNX" else ui.pct(x) for s, x in zip(df.symbole, df.move)]
        df["Sur 1 mois"] = [f"{x * 100:+.0f} pb" if s == "^TNX" else ui.pct(x) for s, x in zip(df.symbole, df.m1)]
        df["Inhabituel"] = df.z.abs().fillna(0)
        st.dataframe(df[["groupe", "nom", "last", "Variation", "Sur 1 mois", "Inhabituel"]], hide_index=True,
                     width="stretch", column_config={
                         "groupe": "Groupe", "nom": "Marché", "last": st.column_config.NumberColumn("Niveau", format="%.2f"),
                         "Inhabituel": st.column_config.ProgressColumn(
                             "Inhabituel", format="%.1f σ", min_value=0, max_value=3,
                             help="Taille du mouvement en écarts-types de ses variations habituelles. Au-delà de 2 : rare.")})
    with c2, st.container(border=True):
        st.markdown(f"**Secteurs et thèmes américains {period}**")
        sec = sorted(f.get("secteurs", []), key=lambda x: x["move"])
        fig = go.Figure(go.Bar(y=[x["nom"] for x in sec], x=[x["move"] for x in sec], orientation="h",
                               marker_color=[GREEN if x["move"] >= 0 else RED for x in sec],
                               hovertemplate="%{y} : %{x:+.2%}<extra></extra>"))
        fig.update_xaxes(tickformat="+.1%")
        fig.update_layout(bargap=0.35)
        st.plotly_chart(ui.plotly_layout(fig, height=60 + 24 * len(sec)), config=ui.PLOT_CONFIG)

# ---------- ideas ----------
with tab_ideas:
    for i in a.get("idees", []):
        with st.container(border=True):
            st.markdown(f"**{i['nom']}** {'· ' + i['ticker'] if i.get('ticker') else ''}")
            st.markdown(i["these"])
            st.markdown(f":red[Risque : {i['risque']}]")
            st.caption("Sources : " + cite(i.get("sources")))
    if not a.get("idees"):
        st.caption("Pas d'idée retenue pour cette séance : aucune raison concrète et récente trouvée.")
    if f.get("analystes"):
        st.markdown("**Changements d'avis d'analystes** (tes grosses positions)")
        st.dataframe(pd.DataFrame(f["analystes"]), hide_index=True, width="stretch", column_config={
            "ticker": "Titre", "date": "Date", "firme": "Banque", "action": "Action", "avant": "Avant",
            "apres": "Après", "objectif": st.column_config.NumberColumn("Objectif", format="%.0f"),
            "objectif_avant": st.column_config.NumberColumn("Objectif avant", format="%.0f")})
    if f.get("argent_suivi"):
        st.markdown("**Argent suivi : dernières déclarations**")
        st.dataframe(pd.DataFrame(f["argent_suivi"]).drop(columns=["value_usd"]), hide_index=True, width="stretch",
                     column_config={"date": "Publié", "kind": "Type", "who": "Qui", "ticker": "Titre", "name": None,
                                    "what": st.column_config.TextColumn("Quoi", width="large"),
                                    "since": st.column_config.NumberColumn("Depuis", format="percent"),
                                    "mine": st.column_config.CheckboxColumn("Chez toi"),
                                    "link": st.column_config.LinkColumn("Lien", display_text="ouvrir")})
    if f.get("radar"):
        st.markdown("**Radar**")
        st.dataframe(pd.DataFrame(f["radar"]), hide_index=True, width="stretch", column_config={
            "ticker": "Titre", "nom": "Nom", "score": st.column_config.NumberColumn("Score", format="%.1f"),
            "pourquoi": st.column_config.TextColumn("Pourquoi", width="large"),
            "depuis_signal": st.column_config.NumberColumn("Depuis le signal", format="percent"),
            "r1m": st.column_config.NumberColumn("1 mois", format="percent")})

# ---------- agenda ----------
with tab_agenda:
    rows = [{"Date": x["date"], "Événement": x["evenement"], "Enjeu": x["enjeu"]} for x in a.get("agenda", [])]
    rows += [{"Date": x["ticker"] and x["date"], "Événement": f"Résultats {x['ticker']}",
              "Enjeu": "grosse position de tes ETF" if x["ticker"] != "AIR.PA" else "ton PEG"}
             for x in f.get("resultats_a_venir", []) if not any(x["ticker"] in e["Événement"] for e in rows)]
    if rows:
        st.dataframe(pd.DataFrame(rows).sort_values("Date"), hide_index=True, width="stretch",
                     column_config={"Enjeu": st.column_config.TextColumn(width="large")})
    else:
        st.caption("Rien de noté pour les 7 prochains jours.")

# ---------- sources ----------
with tab_sources:
    st.caption("Chaque affirmation de l'analyse renvoie à une de ces sources.")
    for s in a.get("sources", []):
        st.markdown(f"{s['id']}. [{s.get('titre') or s['url']}]({s['url']}) · {s.get('media', '')} · {s.get('date', '')}")

# ---------- verdicts ----------
with tab_verdicts:
    v = briefing.verdicts(con)
    if v.empty:
        st.caption("Aucun verdict pour l'instant.")
    else:
        st.caption("Chaque verdict donné sur une ligne et l'évolution de son cours depuis : pour juger les analyses "
                   "sur pièces.")
        st.dataframe(v.drop(columns=["isin"]), hide_index=True, width="stretch", column_config={
            "date": "Séance", "nom": "Ligne", "verdict": "Verdict", "confiance": "Confiance",
            "action": st.column_config.TextColumn("Action", width="medium"),
            "cours": st.column_config.NumberColumn("Cours alors", format="%.2f €"),
            "cours_actuel": st.column_config.NumberColumn("Cours actuel", format="%.2f €"),
            "depuis": st.column_config.NumberColumn("Depuis", format="percent")})

    adv = briefing.advice(con)
    if not adv.empty:
        st.markdown("**Suivi des conseils**")
        st.caption("Cours du titre visé au moment du conseil et aujourd'hui (Yahoo, devise de cotation). Pour un "
                   "achat, une hausse donne raison au conseil ; pour une vente, une baisse.")

        @st.cache_data(ttl="1h", show_spinner=False)
        def last_prices(tickers: tuple) -> dict:
            import yfinance as yf

            try:
                px = yf.download(list(tickers), period="5d", auto_adjust=True, progress=False)["Close"]
            except Exception:  # noqa: BLE001
                return {}
            px = px if isinstance(px, pd.DataFrame) else px.to_frame(tickers[0])
            return {t: float(px[t].dropna().iloc[-1]) for t in px if not px[t].dropna().empty}

        adv["cours_actuel"] = adv.ticker.map(last_prices(tuple(sorted(set(adv.ticker)))))
        adv["depuis"] = adv.cours_actuel / adv.cours_ref - 1
        sign = adv.action.map({"acheter": 1, "renforcer": 1, "alléger": -1, "vendre": -1}).fillna(0)
        adv["juste"] = (adv.depuis * sign).map(lambda x: None if pd.isna(x) or x == 0 else ("oui" if x > 0 else "non"))
        st.dataframe(adv, hide_index=True, width="stretch", column_config={
            "date": "Séance", "action": "Action", "cible": "Cible", "ticker": "Titre",
            "montant_eur": st.column_config.NumberColumn("Montant", format="%.0f €"), "confiance": "Confiance",
            "cours_ref": st.column_config.NumberColumn("Cours alors", format="%.2f"),
            "cours_actuel": st.column_config.NumberColumn("Cours actuel", format="%.2f"),
            "depuis": st.column_config.NumberColumn("Depuis", format="percent"),
            "juste": "Le marché lui donne raison ?"})

# ---------- free reports ----------
with tab_reports:
    reports = pd.read_sql_query("SELECT created_at, kind, title, body_md FROM reports ORDER BY created_at DESC", con)
    if reports.empty:
        st.caption("Aucun rapport libre : demande-en un à Claude.")
    for rep in reports.itertuples():
        with st.expander(f"{rep.title} · {rep.created_at[:10]}", icon=":material/article:"):
            st.markdown(rep.body_md)
