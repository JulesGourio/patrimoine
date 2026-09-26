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
    "frais": "Frais bancaires ou de courtage",
    "impot": "Impôt ou prélèvement fiscal",
}

SPENDING = [
    "Courses",
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
    "Divers",
]
INCOME = ["Salaire", "Remboursements", "Autres revenus"]
CATEGORIES = SPENDING + INCOME
FALLBACK = {"depense": "Divers", "revenu": "Autres revenus"}

# Pattern -> category. The longest matching pattern wins, so "UBER EATS" beats "UBER"; rules
# added by hand live in the database and are merged over these.
DEFAULT_RULES: dict[str, str] = {
    # Courses
    "CARREFOUR": "Courses", "LECLERC": "Courses", "INTERMARCHE": "Courses", "LIDL": "Courses",
    "AUCHAN": "Courses", "SUPER U": "Courses", "HYPER U": "Courses", "MONOPRIX": "Courses",
    "FRANPRIX": "Courses", "ALDI": "Courses", "BIOCOOP": "Courses", "PICARD": "Courses",
    "GRAND FRAIS": "Courses", "CASINO": "Courses", "SPAR": "Courses", "NETTO": "Courses",
    # Restaurants et sorties
    "MCDONALD": "Restaurants et sorties", "BURGER KING": "Restaurants et sorties",
    "KFC": "Restaurants et sorties", "UBER EATS": "Restaurants et sorties",
    "DELIVEROO": "Restaurants et sorties", "STARBUCKS": "Restaurants et sorties",
    "RESTAURANT": "Restaurants et sorties", "BRASSERIE": "Restaurants et sorties",
    "BOULANGERIE": "Restaurants et sorties", "CINEMA": "Restaurants et sorties",
    "PATHE": "Restaurants et sorties", "BAR ": "Restaurants et sorties",
    # Transports
    "SNCF": "Transports", "TOTALENERGIES": "Transports", "TOTAL ": "Transports",
    "ESSO": "Transports", "SHELL": "Transports", "BP ": "Transports", "UBER": "Transports",
    "BOLT": "Transports", "BLABLACAR": "Transports", "RATP": "Transports",
    "AUTOROUTE": "Transports", "VINCI": "Transports", "SANEF": "Transports",
    "PARKING": "Transports", "TRAINLINE": "Transports", "OUIGO": "Transports",
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
    "STRAVA": "Abonnements et télécom",
    # Santé
    "PHARMACIE": "Santé", "DOCTOLIB": "Santé", "MEDECIN": "Santé", "DENTISTE": "Santé",
    "KINE": "Santé", "OPTIC": "Santé", "MUTUELLE": "Santé", "LABORATOIRE": "Santé",
    # Shopping
    "AMAZON": "Shopping", "FNAC": "Shopping", "DARTY": "Shopping", "ZARA": "Shopping",
    "H&M": "Shopping", "UNIQLO": "Shopping", "ACTION": "Shopping", "CDISCOUNT": "Shopping",
    "VINTED": "Shopping", "ALIEXPRESS": "Shopping", "BOULANGER": "Shopping",
    # Sport et loisirs
    "DECATHLON": "Sport et loisirs", "INTERSPORT": "Sport et loisirs",
    "GO SPORT": "Sport et loisirs", "I-RUN": "Sport et loisirs", "ALLTRICKS": "Sport et loisirs",
    "COROS": "Sport et loisirs", "BASIC FIT": "Sport et loisirs", "STEAM": "Sport et loisirs",
    "PLAYSTATION": "Sport et loisirs",
    # Voyages
    "AIRBNB": "Voyages", "BOOKING": "Voyages", "RYANAIR": "Voyages", "EASYJET": "Voyages",
    "AIR FRANCE": "Voyages", "TRANSAVIA": "Voyages", "VOLOTEA": "Voyages", "HOTEL": "Voyages",
    # Services et administratif
    "IMPOTS": "Services et administratif", "DGFIP": "Services et administratif",
    "LA POSTE": "Services et administratif", "ANTS": "Services et administratif",
    # Revenus
    "AIRBUS": "Salaire", "SALAIRE": "Salaire", "CPAM": "Remboursements",
    "AMELI": "Remboursements", "CAF": "Autres revenus", "LYDIA": "Remboursements",
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
    (a salary rule on a card payment) is skipped.
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
    return best[1] if best else FALLBACK[flow]
