# =============================================================================
# tests/test_help_sichtbarkeit.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H2)
# =============================================================================
# Testsuite fuer Build 589: die Capability-Sperre der Vollhilfe (E1).
#
# WARUM DIESE SUITE EIGEN STEHT: Eine Zugriffsbeschraenkung, die man nur "im
# Betrieb ausprobiert", ist nicht belegt. Hier steht sie als RECHTE-MATRIX -
# ein Tisch aus Rechtesaetzen und den daraus erwarteten Kapitelmengen. Wer die
# Sperre spaeter aendert, sieht an dieser Matrix sofort, was er veraendert.
#
# HS01 - leere Rechte: NUR die Sicht ohne Rechtepruefung ('viewprefs')
# HS02 - ein Recht -> genau die daran haengenden Sichten (Matrix)
# HS03 - any-of: 'reports' erscheint mit approve ODER review
# HS04 - unbekanntes Recht aendert nichts (kein Nebeneffekt)
# HS05 - alle Rechte -> alle 43 Sichten
# HS06 - sichtbare_kapitel liefert in KATALOGREIHENFOLGE, nicht in
#        Registerreihenfolge
# HS07 - Kapitel ohne Recht erscheint NICHT, auch wenn es im Register liegt
# HS08 - Waisenkapitel (Sicht nicht im Katalog) erscheint NICHT
# HS09 - darf_kapitel: unbekannte Sicht -> False (die Route macht daraus 404)
# HS10 - gruppen_mit_kapiteln: leere Gruppen entfallen, Reihenfolge stimmt
# HS11 - die Sperre bildet visibleViews() aus cockpit.js nach (Gegenprobe
#        gegen den geparsten Katalog: gleiche Auswahl fuer dieselben Rechte)
#
# Version: v0.8.589 - Build: 589 - 2026-07-31
# =============================================================================

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.help.modell import (                     # noqa: E402
    Abschnitt, HilfeRegister, Sichthilfe, PFLICHT_ANKER, PFLICHT_TITEL,
)
from management.help.sicht_katalog import (              # noqa: E402
    SICHT_KATALOG, SICHT_IDS, sicht,
)
from management.help.sichtbarkeit import (               # noqa: E402
    capabilities_aus_policy, darf_kapitel, gruppen_mit_kapiteln, hat_recht,
    sichtbare_kapitel, sichtbare_sicht_ids,
)


def _kapitel(sicht_id):
    return Sichthilfe(
        sicht=sicht_id, titel="Kapitel %s" % sicht_id,
        recht_klartext="Recht: beispiel.view",
        abschnitte=tuple(Abschnitt(a, PFLICHT_TITEL[a], ("Text.",))
                         for a in PFLICHT_ANKER),
        stand=589)


ALLE_RECHTE = sorted({r for e in SICHT_KATALOG for r in e.rechte()})


# --- HS01 --------------------------------------------------------------------

def test_hs01_ohne_rechte_nur_viewprefs():
    assert sichtbare_sicht_ids(()) == ("viewprefs",)


# --- HS02 --------------------------------------------------------------------

@pytest.mark.parametrize("recht,erwartet", [
    ("dashboard.view", {"dashboard", "faelle"}),
    ("assignment.edit", {"assignment", "cases"}),
    ("crossref.view", {"crossref", "crossfindings", "alias", "merge"}),
    ("ops.view", {"integrity", "audit", "promotion"}),
    ("templates.edit", {"templates", "doctemplates", "modules"}),
    ("capacity.edit", {"capacity", "capacity_pflege"}),
    ("stats.export_sta", {"stats", "planung", "annostats"}),
    ("evidence.fulltext_search", {"search"}),
])
def test_hs02_ein_recht_matrix(recht, erwartet):
    sichtbar = set(sichtbare_sicht_ids([recht]))
    # 'viewprefs' ist immer dabei - es ist die Ausnahme, nicht ein Fehler.
    assert sichtbar == erwartet | {"viewprefs"}


# --- HS03 --------------------------------------------------------------------

def test_hs03_any_of_bei_der_berichts_abnahme():
    nur_approve = set(sichtbare_sicht_ids(["reports.approve"]))
    nur_review = set(sichtbare_sicht_ids(["reports.review"]))
    # 'reports' haengt an approve ODER review; 'approval' nur an approve;
    # 'lectorate' an review ODER approve.
    assert "reports" in nur_approve and "reports" in nur_review
    assert "lectorate" in nur_approve and "lectorate" in nur_review
    assert "approval" in nur_approve
    assert "approval" not in nur_review


# --- HS04 / HS05 --------------------------------------------------------------

def test_hs04_unbekanntes_recht_ohne_wirkung():
    assert set(sichtbare_sicht_ids(["gibtsnicht.view"])) == {"viewprefs"}


def test_hs05_alle_rechte_alle_sichten():
    assert set(sichtbare_sicht_ids(ALLE_RECHTE)) == set(SICHT_IDS)
    assert len(SICHT_IDS) == 43


# --- HS06 / HS07 / HS08 -------------------------------------------------------

def test_hs06_reihenfolge_folgt_dem_katalog():
    # Register bewusst in VERKEHRTER Reihenfolge zusammengesetzt.
    reg = HilfeRegister((_kapitel("faelle"), _kapitel("dashboard")))
    kapitel = sichtbare_kapitel(reg, ["dashboard.view"])
    assert [k.sicht for k in kapitel] == ["dashboard", "faelle"]


def test_hs07_kapitel_ohne_recht_erscheint_nicht():
    reg = HilfeRegister((_kapitel("policy"), _kapitel("dashboard")))
    kapitel = sichtbare_kapitel(reg, ["dashboard.view"])
    assert [k.sicht for k in kapitel] == ["dashboard"]


def test_hs08_waisenkapitel_erscheint_nicht():
    reg = HilfeRegister((_kapitel("gibtsnicht"),))
    assert sichtbare_kapitel(reg, ALLE_RECHTE) == ()


# --- HS09 --------------------------------------------------------------------

def test_hs09_darf_kapitel():
    assert darf_kapitel("dashboard", ["dashboard.view"]) is True
    assert darf_kapitel("dashboard", []) is False
    assert darf_kapitel("viewprefs", []) is True
    assert darf_kapitel("gibtsnicht", ALLE_RECHTE) is False


# --- HS10 --------------------------------------------------------------------

def test_hs10_gruppen_ohne_kapitel_entfallen():
    reg = HilfeRegister((_kapitel("dashboard"), _kapitel("policy")))
    kapitel = sichtbare_kapitel(reg, ["dashboard.view", "policy.view"])
    gruppen = gruppen_mit_kapiteln(kapitel)
    assert [g for g, _ in gruppen] == ["Ueberblick", "Administration"]
    assert [k.sicht for k in gruppen[0][1]] == ["dashboard"]


# --- HS11 --------------------------------------------------------------------

def test_hs11_gleiche_auswahl_wie_visible_views():
    """
    Gegenprobe gegen die Auffassung im Browser: fuer denselben Rechtesatz muss
    hier dieselbe Sichtenmenge herauskommen wie in visibleViews()
    (cockpit.js:401-409). Wir bilden die dortige Logik hier NOCH EINMAL nach -
    aus dem GEPARSTEN Katalog, nicht aus dem Spiegel - und vergleichen. Waere
    der Spiegel falsch, faellt es hier auf, selbst wenn die Paritaet stimmte.
    """
    from tests.test_help_katalog_paritaet import parse_view_catalog, COCKPIT_JS

    with open(COCKPIT_JS, encoding="utf-8") as fh:
        js = parse_view_catalog(fh.read())

    def js_visible(caps):
        besitz = set(caps)
        out = []
        for e in js:
            if e["immer"]:
                out.append(e["id"])
                continue
            rechte = e["caps"] or ((e["cap"],) if e["cap"] else ())
            if any(c in besitz for c in rechte):
                out.append(e["id"])
        return out

    for probe in ([], ["dashboard.view"], ["reports.review"],
                  ["crossref.view", "ops.view"], ALLE_RECHTE):
        assert list(sichtbare_sicht_ids(probe)) == js_visible(probe), probe


# --- Adapter ------------------------------------------------------------------

def test_hs12_capabilities_aus_policy():
    class _P:
        capabilities = {"b.view": "alle", "a.view": None}
    assert capabilities_aus_policy(_P()) == ("a.view", "b.view")

    class _Leer:
        capabilities = {}
    assert capabilities_aus_policy(_Leer()) == ()
    assert capabilities_aus_policy(object()) == ()


def test_hs13_hat_recht_auf_katalogeintraegen():
    assert hat_recht([], sicht("viewprefs")) is True
    assert hat_recht([], sicht("dashboard")) is False
    assert hat_recht(["dashboard.view"], sicht("dashboard")) is True
