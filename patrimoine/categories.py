"""What a money movement is (its flow) and, for spending and income, which category it falls in.

The flow is what keeps saving apart from spending: moving money from CMB to Trade Republic is
``interne`` (it only changes pocket), whereas paying with the Trade Republic card is ``depense``
exactly like a CMB card payment. The 1 % Saveback earned on card payments is its own flow.
"""
from __future__ import annotations

import re
import unicodedata

# Every transaction gets exactly one flow.
FLOWS = {
    "depense": "Dépense (carte, prélèvement, virement vers un tiers)",
    "revenu": "Revenu (salaire, remboursement, virement reçu d'un tiers)",
    "interne": "Virement entre mes propres comptes (épargne déplacée, pas dépensée)",
    "achat_titre": "Achat de titres",
    "vente_titre": "Vente de titres",
    "dividende": "Dividende",
    "interets": "Intérêts (livrets, espèces Trade Republic)",
    "saveback": "Saveback 1 % sur les paiements carte Trade Republic",
    "titres_offerts": "Actions offertes (parrainage, bienvenue)",
    "operation_titres": "Opération sur titres sans espèces (division, regroupement)",
    "transfert_titres": "Titres transférés depuis un autre courtier",
    "frais": "Frais bancaires ou de courtage",
    "impot": "Impôt ou prélèvement fiscal",
}

SPENDING = [
    "Courses",
    "Cantine",
    "Restaurants et sorties",
    "Transports",
    "Logement et énergie",
    "Abonnements et télécom",
    "Santé",
    "Shopping",
    "Sport et loisirs",
    "Voyages",
    "Cadeaux et dons",
    "Services et administratif",
    "Impôts et taxes",
    "Études",
    "Retraits d'espèces",
    "Virements à des particuliers",
    "Divers",
]
INCOME = ["Salaire", "Titres-restaurant", "Primes et intéressement", "Aides et allocations", "Famille", "Remboursements", "Héritage et donations", "Autres revenus"]
# Income that only gives back money already spent (friends paying their share, health insurance): the
# savings rate nets it off spending instead of counting it as income.
REFUNDS = ("Remboursements",)
# Bonuses, profit-sharing (intéressement, participation) and every premium: income, hence savings. Those paid into the
# PEG show up as ``achat_titre`` lines of the PEG account (``PEG_PRIMES``); the bank ones as ``revenu`` of this category.
PRIMES = "Primes et intéressement"
# Meal vouchers credited on a prepaid card (Edenred, Swile…): income, as the user decided (see cartes.py).
TITRES_RESTAURANT = "Titres-restaurant"
PEG_PRIMES = ("PEG_INTERESSEMENT", "PEG_PARTICIPATION", "PEG_SUPPLEMENT_D'INTERESSEMENT")
# Capital received once (inheritance, life insurance paid on a death, gifts): it adds to the wealth but is
# neither income nor savings, otherwise one cheque would inflate the savings rate and the projection.
WINDFALLS = ("Héritage et donations",)
# Flows that bring securities without moving cash: their amount is the value received.
NON_CASH_FLOWS = {"saveback", "titres_offerts", "operation_titres", "transfert_titres"}
CATEGORIES = SPENDING + INCOME
FALLBACK = {"depense": "Divers", "revenu": "Autres revenus"}

# Pattern -> category. The longest matching pattern wins, so "UBER EATS" beats "UBER". Only generic French
# chains, brands and words live here: rules that are personal (people, places, local shops) are added by the
# user (``db.set_rule``, ``categoriser``) and live in the database, merged over these.
_R, _S, _T = "Restaurants et sorties", "Sport et loisirs", "Transports"
DEFAULT_RULES: dict[str, str] = {
    # Courses
    "CARREFOUR": "Courses", "LECLERC": "Courses", "INTERMARCHE": "Courses", "LIDL": "Courses",
    "AUCHAN": "Courses", "SUPER U": "Courses", "HYPER U": "Courses", "U EXPRESS": "Courses",
    "MONOPRIX": "Courses", "FRANPRIX": "Courses", "ALDI": "Courses", "BIOCOOP": "Courses",
    "PICARD": "Courses", "GRAND FRAIS": "Courses", "CASINO": "Courses", "SPAR": "Courses",
    "NETTO": "Courses", "TOO GOOD T": "Courses", "TOO GOOD TO GO": "Courses", "TOOGOODTOGO": "Courses", "TGTG": "Courses", "NESPRESSO": "Courses",
    "TESCO": "Courses", "SAINSBURY": "Courses",
    # Restaurants et sorties
    "MCDONALD": _R, "MC DO": _R, "BURGER KING": _R, "KFC": _R, "SUBWAY": _R, "DOMINO": _R,
    "UBER EATS": _R, "DELIVEROO": _R, "STARBUCKS": _R, "RESTAURANT": _R, "BRASSERIE": _R,
    "BOULANGERIE": _R, "CINEMA": _R, "CINE ": _R, "PATHE": _R, "GAUMONT": _S, "BAR ": _R,
    "CROUS": _R, "SODEXO": _R, "CLICKEAT": _R, "PANS & COMPANY": _R, "AMORINO": _R, "HAAGEN": _R,
    # Words matched at word starts ("PIZZ" -> "PIZZERIA")
    "CAFE": _R, "COFFEE": _R, "RAMEN": _R, "PIZZ": _R, "BURGER": _R, "KEBAP": _R, "KEBAB": _R,
    "DONER": _R, "TACOS": _R, "SUSHI": _R, "PATISSERIE": _R, "BISTRO": _R, "RESTO": _R,
    "AUBERGE": _R, "CREPERIE": _R, "GRILL": _R, "TRATTORIA": _R, "BRIOCHE": _R, "FASTFOOD": _R,
    "FOOD": _R, "FOURNIL": _R, "TARTINE": _R, "THAI": _R, "CREMERIE": _R, "SORBET": _R,
    "ENTRECOTE": _R, "CATERING": _R, "BIER": _R,
    # Transports
    "SNCF": _T, "TOTALENERGIES": _T, "TOTALENERGIES ELECTRICITE": "Logement et énergie", "TOTAL ": _T,
    "ESSO": _T, "SHELL": _T, "BP ": _T, "UBER": _T, "BOLT": _T, "BLABLACAR": _T, "RATP": _T,
    "NAVIGO": _T, "FLIXBUS": _T, "AUTOROUTE": _T, "VINCI": _T, "SANEF": _T, "PARKING": _T,
    "TRAINLINE": _T, "OUIGO": _T, "TRANSPORT FOR LONDON": _T,
    # Logement et énergie
    "LOYER": "Logement et énergie", "EDF": "Logement et énergie", "ENGIE": "Logement et énergie",
    "VEOLIA": "Logement et énergie", "IKEA": "Logement et énergie",
    "LEROY MERLIN": "Logement et énergie", "CASTORAMA": "Logement et énergie",
    # Abonnements et télécom
    "NETFLIX": "Abonnements et télécom", "SPOTIFY": "Abonnements et télécom",
    "DISNEY": "Abonnements et télécom", "DEEZER": "Abonnements et télécom",
    "FREE MOBILE": "Abonnements et télécom", "FREE TELECOM": "Abonnements et télécom",
    "ORANGE": "Abonnements et télécom", "SFR": "Abonnements et télécom",
    "BOUYGUES": "Abonnements et télécom", "SOSH": "Abonnements et télécom",
    "APPLE.COM": "Abonnements et télécom", "GOOGLE": "Abonnements et télécom",
    "AMAZON PRIME": "Abonnements et télécom", "CANAL": "Abonnements et télécom",
    "ANTHROPIC": "Abonnements et télécom", "OPENAI": "Abonnements et télécom",
    "STRAVA": "Abonnements et télécom", "GITHUB": "Abonnements et télécom",
    # Santé
    "PHARMACIE": "Santé", "DOCTOLIB": "Santé", "MEDECIN": "Santé", "DENTISTE": "Santé",
    "KINE": "Santé", "OPTIC": "Santé", "MUTUELLE": "Santé", "LABORATOIRE": "Santé",
    "TELECONSULTATION": "Santé", "DR ": "Santé",
    # Shopping
    "AMAZON": "Shopping", "FNAC": "Shopping", "DARTY": "Shopping", "ZARA": "Shopping",
    "H&M": "Shopping", "UNIQLO": "Shopping", "ACTION": "Shopping", "CDISCOUNT": "Shopping",
    "VINTED": "Shopping", "ALIEXPRESS": "Shopping", "BOULANGER": "Shopping", "ZALANDO": "Shopping",
    "LEBONCOIN": "Shopping", "HEMA": "Shopping", "PRIMARK": "Shopping", "CELIO": "Shopping",
    "PAPETERIE": "Shopping", "LIBRAIRIE": "Shopping", "TRUFFAUT": "Shopping", "DELL": "Shopping",
    # Sport et loisirs
    "DECATHLON": _S, "INTERSPORT": _S, "GO SPORT": _S, "ALLTRICKS": _S, "BASIC FIT": _S,
    "STEAM": _S, "PLAYSTATION": _S, "ADIDAS": _S, "ASICS": _S, "INSTANT GAMING": _S,
    "JEUX": _S, "MUSEE": _S, "SKI": _S, "ESCAPE": _S,
    # Voyages
    "AIRBNB": "Voyages", "BOOKING": "Voyages", "RYANAIR": "Voyages", "EASYJET": "Voyages",
    "AIR FRANCE": "Voyages", "TRANSAVIA": "Voyages", "VOLOTEA": "Voyages", "HOTEL": "Voyages",
    "HOSTEL": "Voyages", "OTEL": "Voyages", "EDREAMS": "Voyages", "GITES DE FRANCE": "Voyages",
    "GETYOURGUIDE": "Voyages", "HILTON": "Voyages", "MISTERFLY": "Voyages", "ESIM": "Voyages",
    "CHEQUES VACANCE": "Voyages",
    # Services, administratif, impôts
    "IMPOT": "Impôts et taxes", "IMPOTS": "Impôts et taxes", "DGFIP": "Impôts et taxes",
    "DIRECTION GENERALE DES FINA": "Impôts et taxes", "TIMBRE FISCAL": "Services et administratif",
    "RET DAB": "Retraits d'espèces", "LA POSTE": "Services et administratif",
    "ANTS": "Services et administratif", "BARBIER": "Services et administratif",
    "BARBER": "Services et administratif", "COIFF": "Services et administratif",
    "TREATWELL": "Services et administratif", "BOOKSY": "Services et administratif",
    "HELLOASSO": "Cadeaux et dons",
    # Études et cantine
    "IZLY": "Cantine", "LYC ": "Études", "CONCOURS": "Études", "RU ": "Cantine",
    # Revenus
    "PAYE": "Salaire", "SALAIRE": "Salaire", "TITRES-RESTAURANT": TITRES_RESTAURANT,
    "INTERESSEMENT": PRIMES, "PARTICIPATION": PRIMES, "GRATIFICATION": PRIMES, "13EME MOIS": PRIMES,
    "TREIZIEME MOIS": PRIMES, "BONUS": PRIMES, "PRIME": PRIMES, "PRIME EXC": PRIMES, "PRIME DE": PRIMES,
    "PRIME ANN": PRIMES, "PRIME VAC": PRIMES, "PRIME PAR": PRIMES, "PRIMES": PRIMES,
    "CPAM": "Remboursements", "AMELI": "Remboursements", "LYDIA": "Remboursements",
    "WERO": "Remboursements", "CAF": "Aides et allocations", "MSA": "Aides et allocations",
    "ACTION LOGEMENT": "Aides et allocations",
    "REGLT DECES": "Héritage et donations", "SUCCESSION": "Héritage et donations",
}


def normalize(text: str | None) -> str:
    """Uppercase, accents removed, runs of spaces collapsed, one space of padding on each side."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " " + re.sub(r"\s+", " ", t.upper()).strip() + " "


def categorize(flow: str, label: str | None, counterparty: str | None, rules: dict[str, str]) -> str | None:
    """Category for a spending or income line; None for every other flow.

    Patterns are matched at word starts ("ACTION" must not match "TRANSACTION"); a trailing
    space in a pattern also requires a word end ("BAR " must not match "BARBIER"). Among the
    patterns that match, the longest one wins. A pattern whose category does not fit the flow
    (a salary rule on a card payment) is skipped. An instant transfer received from someone with no
    rule is a friend paying back a share ("VIR INST M. X kebab"): a refund, not an income. The other way round, a
    transfer sent to someone (VIR, Wero, Lydia, Paylib) with no rule is "Virements à des particuliers".
    """
    if flow not in FALLBACK:
        return None
    allowed = SPENDING if flow == "depense" else INCOME
    text = normalize(label) + normalize(counterparty)
    best: tuple[int, str] | None = None
    for pattern, category in rules.items():
        if category not in allowed:
            continue
        p = normalize(pattern).strip()
        end = r"(?![A-Z0-9])" if pattern.endswith(" ") else ""
        if not p or not re.search(r"(?<![A-Z0-9])" + re.escape(p) + end, text):
            continue
        if best is None or len(p) > best[0]:
            best = (len(p), category)
    if best:
        return best[1]
    if flow == "revenu" and re.match(r" VIR (INST|WERO) ", normalize(label)):
        return "Remboursements"
    if flow == "depense" and re.search(r"^ (VIR|WERO) | (PAYLIB|LYDIA)", normalize(label) + normalize(counterparty)):
        return "Virements à des particuliers"
    return FALLBACK[flow]
