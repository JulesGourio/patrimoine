from patrimoine.categories import CATEGORIES, DEFAULT_RULES, categorize

R = DEFAULT_RULES


def test_every_default_rule_points_to_a_known_category():
    assert set(R.values()) <= set(CATEGORIES)


def test_longest_pattern_wins():
    assert categorize("depense", "UBER TRIP HELP.UBER.COM", None, R) == "Transports"
    assert categorize("depense", "UBER EATS PARIS", None, R) == "Restaurants et sorties"
    assert categorize("depense", "Amazon Prime FR", None, R) == "Abonnements et télécom"
    assert categorize("depense", "AMAZON EU SARL", None, R) == "Shopping"


def test_word_boundaries():
    assert categorize("depense", "PAIEMENT TRANSACTION 123", None, R) == "Divers"  # not "ACTION"
    assert categorize("depense", "BARRIQUE DU COIN", None, R) == "Divers"  # not "BAR "
    assert categorize("depense", "LE BAR", None, R) == "Restaurants et sorties"


def test_accents_and_case_are_ignored():
    assert categorize("depense", "Intermarché Rennes", None, R) == "Courses"
    assert categorize("depense", None, "pharmacie centrale", R) == "Santé"


def test_category_must_fit_the_flow():
    # A card payment at an Airbus shop is not a salary, and a refund from CPAM is not spending.
    assert categorize("depense", "AIRBUS BOUTIQUE", None, R) == "Divers"
    assert categorize("revenu", "VIR AIRBUS OPERATIONS SALAIRE", None, R) == "Salaire"
    assert categorize("revenu", "VIR XYZ", None, R) == "Autres revenus"


def test_instant_transfer_from_a_friend_is_a_refund():
    assert categorize("revenu", "VIR INST M. BABA MAXIME kebab 123", "M.", R) == "Remboursements"
    assert categorize("revenu", "VIR INST MP DATA SUD-OUEST Paye 06 2026", None, R) == "Salaire"


def test_non_budget_flows_have_no_category():
    for flow in ("interne", "achat_titre", "saveback", "dividende"):
        assert categorize(flow, "CARREFOUR", None, R) is None


def test_user_rule_overrides_default():
    rules = {**R, "CARREFOUR": "Divers"}
    assert categorize("depense", "CARREFOUR CITY", None, rules) == "Divers"


def test_transfer_sent_to_someone_is_its_own_category():
    assert categorize("depense", "VIR INST vers TRIHAN EMILIO", "vers TRIHAN EMILIO", R) == "Virements à des particuliers"
    assert categorize("depense", "WERO MAXIME M", None, R) == "Virements à des particuliers"
    assert categorize("depense", "CARTE 12/08 PAYPAL EUROPE", None, R) == "Divers"
    assert categorize("depense", "CARTE Too Good T KOEBENHAVN", None, R) == "Courses"
