"""Outil `projection` : Monte-Carlo du patrimoine (page Projection d'origine, portée dans le moteur)."""
import json

import pytest

from patrimoine import api, db, notify, vault
from patrimoine.config import Settings


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(vault, "_backend", vault.KeyringBackend())
    monkeypatch.setattr(notify, "_local", None)
    with db.session(Settings().db_path) as con:
        db.init(con)
    return tmp_path


def _remplir(cash_pea=2_000_000, cash_livret=1_000_000):
    with db.session(Settings().db_path) as con:
        for a, kind in (("tr_pea", "pea"), ("cmb_livret_a", "livret")):
            con.execute("INSERT OR IGNORE INTO accounts (id, institution, name, kind) VALUES (?, 'X', ?, ?)",
                        (a, a, kind))
        con.executemany("INSERT INTO valuations VALUES ('2026-11-01', ?, ?, 0, 0, 0, 0)",
                        [("tr_pea", cash_pea), ("cmb_livret_a", cash_livret)])


def test_without_history_returns_an_error(base):
    assert api.projection() == {"erreur": "historique vide : lancer synchroniser"}


def test_start_split_and_shape(base):
    _remplir()
    r = api.projection(horizon_ans=5)
    assert r["depart"] == {"total": 30000, "risque": 20000, "sur": 10000}
    assert r["hypotheses"]["part_actions_pct"] == 67 and r["hypotheses"]["epargne_mensuelle"] == 1000
    s = r["serie"]
    assert len(s["dates"]) == 61
    assert set(s) >= {"p10", "p25", "p50", "p75", "p90", "mediane_reelle", "verse"}
    assert all(len(v) == len(s["dates"]) for v in s.values())
    assert len(r["leviers"]) == 6
    assert r["final"]["p10"] <= r["final"]["mediane"] <= r["final"]["p90"]
    json.dumps(r)


def test_long_horizon_is_thinned(base):
    _remplir()
    s = api.projection(horizon_ans=40)["serie"]
    assert len(s["dates"]) <= 120 and s["dates"][-1] > s["dates"][0]


def test_deterministic(base):
    _remplir()
    assert api.projection() == api.projection()


def test_median_grows_with_savings(base):
    _remplir()
    a = api.projection(epargne_mensuelle=500)["final"]["mediane"]
    b = api.projection(epargne_mensuelle=1500)["final"]["mediane"]
    assert b > a


def test_trivial_goal_is_reached_for_sure(base):
    _remplir()
    r = api.projection(objectif_eur=1000)
    assert r["objectif"]["chance"] == 1.0 and r["objectif"]["mois_median"] is not None


def test_no_goal(base):
    _remplir()
    assert api.projection(objectif_eur=0)["objectif"] is None


@pytest.mark.parametrize("kw", [
    {"horizon_ans": 0}, {"horizon_ans": 41}, {"horizon_ans": float("nan")}, {"horizon_ans": 2.5},
    {"part_actions_pct": -1}, {"part_actions_pct": 101}, {"part_actions_pct": float("nan")},
    {"volatilite_pct": 0}, {"volatilite_pct": 101}, {"volatilite_pct": float("inf")},
    {"rendement_actions_pct": -100}, {"rendement_livrets_pct": -150}, {"inflation_pct": -100},
    {"epargne_mensuelle": -1}, {"epargne_mensuelle": float("inf")}, {"objectif_eur": -5},
    {"objectif_eur": float("nan")}, {"rendement_actions_pct": "abc"}, {"inflation_pct": None},
])
def test_invalid_bounds_return_an_error(base, kw):
    _remplir()
    assert "erreur" in api.projection(**kw)


def test_extreme_values_do_not_raise(base):
    _remplir()
    r = api.projection(horizon_ans=40, rendement_actions_pct=1e6, epargne_mensuelle=1e300)
    assert isinstance(r, dict)


def test_verse_is_start_plus_cumulative_savings(base):
    _remplir()  # départ 30000
    r = api.projection(horizon_ans=2, epargne_mensuelle=100, hausse_epargne_pct=10)
    # 12 mois à 100 puis 12 mois à 110
    assert r["verse"] == 30000 + 12 * 100 + 12 * 110
    assert r["serie"]["verse"][0] == 30000 and r["serie"]["verse"][-1] == r["verse"]


def test_mois_median_is_first_month_median_reaches_goal(base):
    _remplir()
    r = api.projection(horizon_ans=5, objectif_eur=40000)
    s = r["serie"]
    i = next(k for k, v in enumerate(s["p50"]) if v >= 40000)
    assert i > 0 and r["objectif"]["mois_median"] == s["dates"][i]
    assert api.projection(horizon_ans=1, epargne_mensuelle=0, objectif_eur=10_000_000)["objectif"]["mois_median"] is None
