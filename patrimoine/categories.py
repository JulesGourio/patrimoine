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
    "Divers",
]
INCOME = ["Salaire", "Aides et allocations", "Famille", "Remboursements", "Autres revenus"]
# Flows that bring securities without moving cash: their amount is the value received.
NON_CASH_FLOWS = {"saveback", "titres_offerts", "operation_titres", "transfert_titres"}
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
    "LOYER": "Logement et énergie", "DANIELLE PROPRIO": "Logement et énergie", "EDF": "Logement et énergie", "ENGIE": "Logement et énergie",
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
    "IMPOT": "Impôts et taxes", "IMPOTS": "Impôts et taxes", "DGFIP": "Impôts et taxes",
    "DIRECTION GENERALE DES FINA": "Impôts et taxes", "RET DAB": "Retraits d'espèces",
    "VELO TOULOUSE": "Transports", "PAYE": "Salaire", "WERO": "Remboursements",
    "LA POSTE": "Services et administratif", "ANTS": "Services et administratif",
    # Generic words, matched at word starts ("PIZZ" -> "PIZZERIA")
    "CAFE": "Restaurants et sorties", "COFFEE": "Restaurants et sorties", "RAMEN": "Restaurants et sorties",
    "PIZZ": "Restaurants et sorties", "BURGER": "Restaurants et sorties", "KEBAP": "Restaurants et sorties",
    "KEBAB": "Restaurants et sorties", "DONER": "Restaurants et sorties", "TACOS": "Restaurants et sorties",
    "SUSHI": "Restaurants et sorties", "PATISSERIE": "Restaurants et sorties", "BISTRO": "Restaurants et sorties",
    "RESTO": "Restaurants et sorties", "AUBERGE": "Restaurants et sorties", "CREPERIE": "Restaurants et sorties",
    "GRILL": "Restaurants et sorties", "TRATTORIA": "Restaurants et sorties", "PIDE": "Restaurants et sorties",
    "BRIOCHE": "Restaurants et sorties", "COOKIE": "Restaurants et sorties", "FASTFOOD": "Restaurants et sorties",
    "FOOD": "Restaurants et sorties", "BIER": "Restaurants et sorties", "ESCAPE": "Sport et loisirs",
    "JEUX": "Sport et loisirs", "MUSEE": "Sport et loisirs", "SKI": "Sport et loisirs",
    "HOSTEL": "Voyages", "OTEL": "Voyages", "BARBIER": "Services et administratif",
    "BARBER": "Services et administratif", "COIFF": "Services et administratif", "DR ": "Santé",
    # Places seen in Jules's own history (Toulouse, trips)
    "TOO GOOD TO GO": "Courses", "TGTG": "Courses", "CROUS": "Restaurants et sorties",
    "SODEXO": "Restaurants et sorties", "CLICKEAT": "Restaurants et sorties",
    "CHER MONSIEUR": "Restaurants et sorties", "LES SABLES D OR": "Restaurants et sorties",
    "BELLY": "Restaurants et sorties", "PRIMA LOVA": "Restaurants et sorties",
    "MONSIEUR GEORGES": "Restaurants et sorties", "KILOMETRE ZERO": "Restaurants et sorties",
    "STAREJ KUCHNI": "Restaurants et sorties", "PERIGOURDINE": "Restaurants et sorties",
    "TEPE NAUTILUS": "Restaurants et sorties", "BRIOCHERIE": "Restaurants et sorties",
    "MIE CALINE": "Restaurants et sorties", "BEL FRIES": "Restaurants et sorties",
    "FOCA FOCA": "Restaurants et sorties", "LES ZINC": "Restaurants et sorties",
    "P'TIT FLOT": "Restaurants et sorties", "MELTING POT": "Restaurants et sorties",
    "CALE SECHE": "Restaurants et sorties", "DELIRIUM": "Restaurants et sorties",
    "THE DANU": "Restaurants et sorties", "SORBET": "Restaurants et sorties",
    "MAZZOLINA": "Restaurants et sorties", "CREMERIE": "Restaurants et sorties",
    "ENTRECOTE": "Restaurants et sorties", "DELICIOSO": "Restaurants et sorties",
    "TANDOORY": "Restaurants et sorties", "CATERING": "Restaurants et sorties",
    "KASHMIR": "Restaurants et sorties", "AMORINO": "Restaurants et sorties",
    "HAAGEN": "Restaurants et sorties", "ICHIBANYA": "Restaurants et sorties",
    "UNLU MAMULLERI": "Restaurants et sorties", "AU GASCON": "Restaurants et sorties",
    "RAVIOLI": "Restaurants et sorties", "PITAYA": "Restaurants et sorties", "MIA CHA": "Restaurants et sorties",
    "4 TARTES": "Restaurants et sorties", "KIOSQUE": "Restaurants et sorties",
    "BOREKCISI": "Restaurants et sorties", "TAKUMI": "Restaurants et sorties",
    "TITO MOJITO": "Restaurants et sorties", "PANS & COMPANY": "Restaurants et sorties",
    "BANH MI": "Restaurants et sorties", "DOMINO": "Restaurants et sorties",
    "LEBREUILLY": "Restaurants et sorties", "GALACTICA": "Restaurants et sorties",
    "HELADERIA": "Restaurants et sorties", "MC DO": "Restaurants et sorties",
    "HALLE AUX PAINS": "Restaurants et sorties", "YOGO": "Restaurants et sorties",
    "FOLIE DOUCE": "Restaurants et sorties", "BOW & ROLL": "Restaurants et sorties",
    "N88DLES": "Restaurants et sorties", "XINYAN": "Restaurants et sorties",
    "JUNE CAFES": "Restaurants et sorties", "GD CAFE": "Restaurants et sorties",
    "GAUMONT": "Sport et loisirs", "LOUXOR": "Sport et loisirs", "MYSTERIA": "Sport et loisirs",
    "GAMEBOX": "Sport et loisirs", "GROTTE DU YETI": "Sport et loisirs", "CAP LOISIRS": "Sport et loisirs",
    "BARAKAJEUX": "Sport et loisirs", "BARAKA JEUX": "Sport et loisirs", "DREAM O CLOCK": "Sport et loisirs",
    "WIGMORE HALL": "Sport et loisirs", "BILLET REDUC": "Sport et loisirs", "KINGUIN": "Sport et loisirs",
    "ENEBA": "Sport et loisirs", "INSTANT GAMING": "Sport et loisirs", "ANKAMA": "Sport et loisirs",
    "ASICS": "Sport et loisirs", "VELOTOPIE": "Transports",
    "TISSEO": "Transports", "FLIXBUS": "Transports", "NAVIGO": "Transports", "BELBIM": "Transports",
    "TRANSPORT FOR LONDON": "Transports",
    "EDREAMS": "Voyages", "GITES DE FRANCE": "Voyages", "GETYOURGUIDE": "Voyages", "YHA": "Voyages",
    "HILTON": "Voyages", "HEADOUT": "Voyages", "TOULOUSE TOURISME": "Voyages", "ESIM": "Voyages",
    "VILLAGE IGLOO": "Voyages", "ZALANDO": "Shopping", "SIZE?": "Shopping", "LEBONCOIN": "Shopping",
    "TRUFFAUT": "Shopping", "GRAND BAZAAR": "Shopping",
    "TESCO": "Courses", "SAINSBURY": "Courses", "CONSUM": "Courses", "ASIA SHOP": "Courses",
    "KIM MARKET": "Courses", "LAITERIE": "Courses", "SAVEURS D": "Courses", "PALAIS DES THES": "Courses",
    "NESPRESSO": "Courses", "MAXICOFFEE": "Courses",
    "TREATWELL": "Services et administratif", "HELLOASSO": "Cadeaux et dons", "GITHUB": "Abonnements et télécom",
    "TELECONSULTATION": "Santé",
    # Older CMB history (2020-2025)
    "DANIELLE": "Logement et énergie", "METGE": "Logement et énergie", "FAUX JEAN": "Logement et énergie", "IZLY": "Cantine", "LYC ": "Études", "CONCOURS": "Études",
    "SCEI": "Études", "EN VOITURE SIMON": "Transports", "EVA AIR": "Voyages", "MSA": "Aides et allocations",
    "ACTION LOGEMENT": "Aides et allocations", "GOURIO SYLVAIN": "Famille", "VIOT": "Famille",
    "CHLOE GOURIO": "Famille", "WINAMAX": "Autres revenus", "DELL": "Shopping", "MI.COM": "Shopping",
    "LIBRAIRIE": "Shopping", "SMONEY": "Cantine",
    # Told by Jules
    "CSE AIRBUS": "Cantine", "COOP CE AIRBUS": "Cantine", "MONEWEB": "Cantine", "GALAXIE": "Cantine",
    "MA VILLE MON SHOPPING": "Sport et loisirs", "CHEQUES VACANCE": "Voyages",
    # Revenus
    "AIRBUS": "Salaire", "SALAIRE": "Salaire", "CPAM": "Remboursements",
    "AMELI": "Remboursements", "CAF": "Aides et allocations", "LYDIA": "Remboursements",
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
