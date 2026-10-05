"""The analysis as a short phone-width mail: key figures, one chart, the verdicts. The rest is on the Analyses page.

Mail clients ignore stylesheets and scripts: everything is inline-styled tables, and the chart is a PNG attached
inline (cid:), drawn with matplotlib.
"""
from __future__ import annotations

import html
import io
from datetime import date

from . import notify

GREEN, RED, GREY, INK, MUTED, LINE = "#15803d", "#b91c1c", "#8a8983", "#111827", "#6b7280", "#e5e7eb"
SHORT = {
    "NL0000235190": "Airbus (PEG)", "FR0011550185": "S&P 500", "FR0010342592": "Nasdaq 100 x2",
    "IE00BHZRR030": "Corée", "IE000YU9K6K2": "Spatial", "IE000KHX9DX6": "Terres rares",
}
VERDICT_STYLE = {"rien à faire": ("#f3f4f6", "#374151"), "surveiller": ("#fef3c7", "#92400e"),
                 "agir": ("#dbeafe", "#1e40af")}
TONE_STYLE = {"haussier": ("#dcfce7", GREEN), "baissier": ("#fee2e2", RED), "mitigé": ("#fef3c7", "#92400e"),
              "calme": ("#f3f4f6", "#374151")}
ACTION_STYLE = {"acheter": ("#dcfce7", GREEN), "renforcer": ("#dcfce7", GREEN), "alléger": ("#fee2e2", RED),
                "vendre": ("#fee2e2", RED), "arbitrer": ("#dbeafe", "#1e40af"), "attendre": ("#f3f4f6", "#374151")}
DASHBOARD = "http://localhost:8501/analyses"
DAYS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def pct(x: float | None, digits: int = 1) -> str:
    return "–" if x is None else f"{x * 100:+.{digits}f} %".replace(".", ",").replace("-", "−")


def eur(x: float | None, sign: bool = False) -> str:
    if x is None:
        return "–"
    s = f"{x:+,.0f}" if sign else f"{x:,.0f}"
    return s.replace(",", " ").replace("-", "−") + " €"


def day_label(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def short(line: dict) -> str:
    return SHORT.get(line["isin"], line["nom"][:22])


def move_label(m: dict) -> str:
    """Rates move in basis points, everything else in percent."""
    if m.get("symbole") == "^TNX":
        return f"{m['move'] * 100:+.0f} pb".replace("-", "−")
    return pct(m.get("move"))


def chart(facts: dict) -> bytes:
    """Horizontal bars: each line's move over the period, its index as a tick, the euro impact on the right."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    lines = [l for l in facts["lignes"] if l.get("move") is not None]
    lines.sort(key=lambda l: l["move"])
    n = len(lines)
    fig, ax = plt.subplots(figsize=(4.2, 0.42 * n + 0.6), dpi=250)
    ys = range(n)
    moves = [l["move"] * 100 for l in lines]
    ax.barh(ys, moves, color=[GREEN if m >= 0 else RED for m in moves], height=0.58, zorder=2)
    for y, l in zip(ys, lines):
        if l.get("indice_move") is not None:
            ax.plot([l["indice_move"] * 100 * l.get("levier", 1)] * 2, [y - 0.36, y + 0.36], color=INK, lw=1.6,
                    zorder=3)
    ax.set_yticks(list(ys), [short(l) for l in lines], fontsize=10, color=INK)
    lim = max(max(abs(m) for m in moves), max((abs(l.get("indice_move") or 0) * 100 * l.get("levier", 1)
                                               for l in lines), default=0), 0.5) * 1.15
    ax.set_xlim(-lim, lim)
    ax.axvline(0, color=GREY, lw=0.8, zorder=1)
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(4, symmetric=True))
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: "0" if abs(v) < 1e-9 else (f"{v:+.0f} %" if lim >= 1.5 else f"{v:+.1f} %")
        .replace(".", ",").replace("-", "−")))
    ax.tick_params(axis="x", labelsize=8.5, colors=MUTED, length=0)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=LINE, lw=0.6, zorder=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax2 = ax.twinx()
    ax2.set_ylim(ax.get_ylim())
    ax2.set_yticks(list(ys), [eur(l.get("impact_eur"), sign=True) for l in lines], fontsize=10, color=INK)
    ax2.tick_params(length=0)
    for s in ax2.spines.values():
        s.set_visible(False)
    fig.tight_layout(pad=0.4)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _chip(text: str, bg: str, fg: str) -> str:
    return (f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;background:{bg};color:{fg};'
            f'font-size:12px;font-weight:600;white-space:nowrap">{html.escape(text)}</span>')


def _tile(label: str, value: str, sub: str = "", color: str = INK) -> str:
    return (f'<td style="padding:10px 12px;border:1px solid {LINE};border-radius:8px;vertical-align:top;width:50%">'
            f'<div style="font-size:12px;color:{MUTED}">{html.escape(label)}</div>'
            f'<div style="font-size:19px;font-weight:700;color:{color}">{value}</div>'
            f'<div style="font-size:12px;color:{MUTED}">{sub}</div></td>')


def _heat(m: dict) -> str:
    """A market tile coloured by how unusual the move is."""
    z = abs(m.get("z") or 0)
    up = (m.get("move") or 0) >= 0
    if m.get("symbole") in ("^VIX", "^TNX"):  # up is bad news for stocks
        up = not up
    shade = 0 if z < 0.5 else 1 if z < 1.5 else 2
    bg = (["#f0fdf4", "#bbf7d0", "#4ade80"] if up else ["#fef2f2", "#fecaca", "#f87171"])[shade]
    return (f'<td style="background:{bg};padding:6px 4px;text-align:center;border:2px solid #fff;width:33%">'
            f'<div style="font-size:11px;color:#374151">{html.escape(m["nom"])}</div>'
            f'<div style="font-size:14px;font-weight:700;color:{INK}">{move_label(m)}</div></td>')


def _section(title: str) -> str:
    return (f'<h2 style="font-size:15px;margin:22px 0 8px;padding-bottom:4px;border-bottom:2px solid {INK};'
            f'color:{INK}">{html.escape(title)}</h2>')


def render(kind: str, facts: dict, a: dict) -> str:
    e = html.escape
    weekly = kind == "hebdo"
    period = "sur 5 séances" if weekly else "sur la séance"
    lines = {l["isin"]: l for l in facts["lignes"]}
    market = {m["symbole"]: m for m in facts["marche"]}
    p = facts["patrimoine"]
    titles_pct = p["effet_marche_eur"] / (p["titres"] - p["effet_marche_eur"]) if p.get("titres") else None
    bg, fg = TONE_STYLE.get(a["ton"], TONE_STYLE["calme"])
    out = [f'<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;'
           f'padding:0 4px;box-sizing:border-box;color:{INK};line-height:1.45;font-size:14px">']
    out.append(f'<div style="font-size:12px;color:{MUTED}">{"Bilan de la semaine" if weekly else "Analyse du jour"}'
               f' · séance{"s jusqu’au" if weekly else " du"} {day_label(facts["seance"])} &nbsp;{_chip(a["ton"], bg, fg)}</div>')
    out.append(f'<h1 style="font-size:21px;line-height:1.25;margin:6px 0 14px">{e(a["titre"])}</h1>')

    sp, nd, cac = market.get("^GSPC"), market.get("^NDX"), market.get("^FCHI")
    color = GREEN if p["effet_marche_eur"] >= 0 else RED
    out.append('<table role="presentation" style="width:100%;border-collapse:separate;border-spacing:6px;margin:0">')
    out.append("<tr>" + _tile("Patrimoine total", eur(p["total"]), f"au {day_label(p['date'])}" if p.get("date") else "")
               + _tile(f"Tes titres {period}", eur(p["effet_marche_eur"], sign=True), pct(titles_pct), color) + "</tr>")
    out.append("<tr>" + _tile("S&P 500 · Nasdaq 100", f"{pct(sp and sp['move'])} · {pct(nd and nd['move'])}", "en dollars")
               + _tile("CAC 40", pct(cac and cac["move"]), f"Euro/dollar {pct(market.get('EURUSD=X', {}).get('move'))}")
               + "</tr></table>")

    out.append(_section("L’essentiel"))
    out.append('<ul style="margin:0;padding-left:18px">' + "".join(
        f'<li style="margin-bottom:6px">{e(x)}</li>' for x in a["points_cles"]) + "</ul>")
    if weekly and a.get("bilan_semaine"):
        out.append(f'<p style="margin:10px 0 0">{e(a["bilan_semaine"])}</p>')

    if a.get("conseils"):
        out.append(_section("Mes conseils"))
        for c in a["conseils"]:
            cbg, cfg = ACTION_STYLE.get(c["action"], ACTION_STYLE["attendre"])
            size = [eur(c["montant_eur"])] if c.get("montant_eur") else []
            if c.get("prix_limite"):
                size.append(f"limite {c['prix_limite']:,.2f}".replace(",", " ").replace(".", ","))
            out.append(
                f'<div style="border:1px solid {LINE};border-left:4px solid {cfg};border-radius:6px;padding:8px 10px;'
                f'margin-bottom:8px"><div>{_chip(c["action"], cbg, cfg)} <b>{e(c["cible"])}</b>'
                f'{" · " + e(" · ".join(size)) if size else ""}</div>'
                f'<div style="margin-top:4px">{e(c["pourquoi"])}</div>'
                f'<div style="margin-top:4px;font-size:12px;color:{MUTED}"><span style="color:{RED}">Risque :</span> '
                f'{e(c["risque"])}<br>Invalidé si : {e(c["invalidation"])}<br>Horizon {e(c["horizon"])} · confiance '
                f'{e(c["confiance"])}</div></div>')

    out.append(_section(f"Tes lignes {period}"))
    out.append(f'<img src="cid:lignes" width="600" alt="Variation de chaque ligne" style="width:100%;max-width:600px;'
               f'height:auto;display:block">')
    out.append(f'<div style="font-size:11px;color:{MUTED};margin:2px 0 10px">Barre : ta ligne (en euros). '
               f'Trait noir : son indice (x2 pour le Nasdaq à levier, en devise locale).</div>')
    quiet = []
    for v in a.get("lignes", []):
        l = lines.get(v["isin"], {"nom": v["isin"], "isin": v["isin"]})
        vbg, vfg = VERDICT_STYLE.get(v["verdict"], VERDICT_STYLE["rien à faire"])
        mv = l.get("move")
        if v["verdict"] == "rien à faire":  # one line in the mail; the reasoning is on the page
            quiet.append(f'<b>{e(short(l))}</b> <span style="color:{GREEN if (mv or 0) >= 0 else RED}">{pct(mv)}</span>')
            continue
        action = f'<div style="margin-top:4px;font-weight:600">→ {e(v["action"])}</div>' if v.get("action") else ""
        out.append(
            f'<div style="border:1px solid {LINE};border-left:4px solid {vfg};border-radius:6px;padding:8px 10px;'
            f'margin-bottom:8px"><div><b>{e(short(l))}</b> <span style="color:{GREEN if (mv or 0) >= 0 else RED};'
            f'font-weight:600">{pct(mv)}</span> &nbsp;{_chip(v["verdict"], vbg, vfg)} '
            f'<span style="font-size:12px;color:{MUTED}">confiance {e(v["confiance"])}</span></div>'
            f'<div style="margin-top:4px">{e(v["cause"])}</div>{action}</div>')

    if quiet:
        out.append(f'<div style="font-size:13px;color:{MUTED}">Rien à faire : {" · ".join(quiet)}</div>')

    out.append(_section("Marchés"))
    order = ["^GSPC", "^NDX", "^FCHI", "^STOXX", "^KS11", "^VIX", "^TNX", "EURUSD=X", "GC=F", "BZ=F", "HG=F", "BTC-EUR"]
    tiles = [_heat(market[s]) for s in order if s in market]
    secs = facts.get("secteurs", [])
    if secs:
        tiles += [_heat(secs[0]), _heat(secs[-1])]
    out.append('<table role="presentation" style="width:100%;border-collapse:collapse">' + "".join(
        "<tr>" + "".join(tiles[i:i + 3]) + "</tr>" for i in range(0, len(tiles), 3)) + "</table>")
    if secs:
        out.append(f'<div style="font-size:11px;color:{MUTED};margin-top:2px">Deux dernières cases : meilleur et pire '
                   f'secteur américain. Couleur plus foncée = mouvement inhabituel.</div>')
    m = a.get("marche", {})
    out.append(f'<p style="margin:10px 0 4px">{e(m.get("resume", ""))}</p>')

    if a.get("idees"):
        out.append(_section("Idées à creuser"))
        for i in a["idees"]:
            tick = f' <span style="color:{MUTED}">{e(i["ticker"])}</span>' if i.get("ticker") else ""
            out.append(f'<div style="background:#f5f7fb;border-radius:6px;padding:8px 10px;margin-bottom:8px">'
                       f'<b>{e(i["nom"])}</b>{tick}<div style="margin-top:3px">{e(i["these"])}</div>'
                       f'<div style="margin-top:3px;font-size:13px;color:{RED}">Risque : {e(i["risque"])}</div></div>')

    if a.get("agenda"):
        out.append(_section("À venir"))
        out.append('<table role="presentation" style="width:100%;border-collapse:collapse;font-size:13px">' + "".join(
            f'<tr><td style="padding:4px 8px 4px 0;white-space:nowrap;vertical-align:top;color:{MUTED}">'
            f'{e(day_label(x["date"]) if len(x["date"]) == 10 else x["date"])}</td>'
            f'<td style="padding:4px 0"><b>{e(x["evenement"])}</b> · {e(x["enjeu"])}</td></tr>'
            for x in a["agenda"][:3]) + "</table>")

    if a.get("a_faire"):
        out.append(_section("À faire"))
        out.append("".join(f'<div style="margin-bottom:6px">☐ {e(x)}</div>' for x in a["a_faire"]))

    out.append(f'<p style="margin:24px 0 0;padding-top:10px;border-top:1px solid {LINE};font-size:12px;color:{MUTED}">'
               f'Détail, graphiques et les {len(a.get("sources", []))} sources : <a href="{DASHBOARD}" '
               f'style="color:#1d4ed8">tableau de bord → Analyses</a> (sur ton PC). Rien n’est un ordre : '
               f'tu décides et tu exécutes.</p></div>')
    return "".join(out)


def text(kind: str, facts: dict, a: dict) -> str:
    """Plain-text version (mail fallback)."""
    rows = [a["titre"], ""] + [f"- {x}" for x in a["points_cles"]] + [""]
    rows += [f"Conseil : {c['action']} {c['cible']} · {c['pourquoi']}" for c in a.get("conseils", [])] + [""]
    lines = {l["isin"]: l for l in facts["lignes"]}
    for v in a.get("lignes", []):
        l = lines.get(v["isin"], {"nom": v["isin"], "isin": v["isin"]})
        rows.append(f"{short(l)} {pct(l.get('move'))} · {v['verdict']} : {v['cause']}")
    rows += ["", f"Détail : {DASHBOARD}"]
    return "\n".join(rows)


def send(kind: str, facts: dict, a: dict) -> str | None:
    p = facts["patrimoine"]
    subject = ("Semaine : " if kind == "hebdo" else "") + a["titre"]
    done = []
    top = next((c for c in a.get("conseils", []) if c["action"] != "attendre"), None)
    push = f"Tes titres {eur(p['effet_marche_eur'], sign=True)} · " + (
        f"Conseil : {top['action']} {top['cible']}" + (f" ({eur(top['montant_eur'])})" if top.get("montant_eur") else "")
        if top else (a["points_cles"][0] if a["points_cles"] else ""))
    if notify.push(subject, push, priority=3, tags=["chart_with_upwards_trend"]):
        done.append("ntfy")
    if notify.mail(subject, text(kind, facts, a), render(kind, facts, a), images={"lignes": chart(facts)}):
        done.append("mail")
    return "+".join(done) or None
