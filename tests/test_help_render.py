# =============================================================================
# tests/test_help_render.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H2)
# =============================================================================
# Testsuite fuer Build 589: die reine Renderfunktion der Vollhilfe.
#
# Die Renderfunktion sieht die ungefilterten Daten NIE - sie bekommt eine
# bereits gefilterte Gliederung. Diese Suite prueft deshalb zwei Dinge
# getrennt: dass die Gliederung richtig gebaut wird (Filterung) und dass das
# HTML daraus stimmt (Darstellung, Escaping, Anker).
#
# HD01 - baue_gliederung: nur erlaubte Sichten, in Katalog-/Gruppenfolge
# HD02 - baue_gliederung: Sicht ohne Kapitel -> Eintrag MIT Platzhalter
#        (sie verschwindet nicht - Grundregel 1)
# HD03 - Verzeichnis nennt jede sichtbare Sicht und markiert die offenen
# HD04 - Kapitel-HTML: Rechtelage prominent, Abschnitte mit Ankern
#        '<sicht>-<anker>', Stand-Angabe
# HD05 - Escaping: '<', '&' und '"' aus Registertexten landen escaped
# HD06 - Listen: geordnet -> <ol>, sonst <ul>
# HD07 - Fusszeile nennt Version und Build
# HD08 - Aufbauhinweis erscheint nur, solange etwas offen ist
# HD09 - kontext_nutzlast: gebuendelt je Sicht, mit Verweis; unbekannte Sicht
#        -> leere, aber wohlgeformte Nutzlast
# HD10 - anker_id ist die eine Stelle, an der die Sprungmarke gebildet wird
#
# Build 593 (H6):
# HD12 - suchindex: ein Eintrag je sichtbarem Kapitel, mit den Stichworten
#        aus dem VIEW_CATALOG (kein zweiter Stichwortbestand)
# HD13 - der Index ist BEREITS gefiltert - was gesperrt ist, ist auch nicht
#        durchsuchbar (E1 gilt auch fuer die Suche)
# HD14 - der eingebettete Index ist gueltiges JSON und kann den Script-Block
#        nicht verlassen ('<' maskiert)
# HD15 - Blaetterleiste: erstes Kapitel ohne Rueckweg, letztes ohne Weiter
# HD16 - help.js wird eingebunden; das Suchfeld ist ohne JavaScript verborgen
#
# Version: v0.8.589 - Build: 589 - 2026-07-31
# =============================================================================

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.help.modell import (                     # noqa: E402
    Abschnitt, HilfeRegister, Kontexthilfe, Sichthilfe, PFLICHT_ANKER,
    PFLICHT_TITEL,
)
from management.help.render_html import (                # noqa: E402
    PLATZHALTER_TEXT, anker_id, baue_gliederung, kontext_nutzlast,
    render_hilfe_seite, suchindex,
)


def _kapitel(sicht_id, zusatz=(), kontext=(), titel=None, stand=589):
    return Sichthilfe(
        sicht=sicht_id, titel=titel or ("Kapitel %s" % sicht_id),
        recht_klartext="Recht: dashboard.view (Scope 'alle')",
        abschnitte=tuple(Abschnitt(a, PFLICHT_TITEL[a], ("Text %s." % a,))
                         for a in PFLICHT_ANKER) + tuple(zusatz),
        kontext=tuple(kontext), stand=stand)


# --- HD01 / HD02 --------------------------------------------------------------

def test_hd01_gliederung_filtert_und_ordnet():
    reg = HilfeRegister((_kapitel("faelle"), _kapitel("dashboard")))
    g = baue_gliederung(reg, ["dashboard.view"])
    assert [gr for gr, _ in g.gruppen] == ["Ueberblick", "Fallsteuerung",
                                           "Persoenlich"]
    assert [e.sicht_id for e in g.eintraege()] == ["dashboard", "faelle",
                                                   "viewprefs"]


def test_hd02_offene_sicht_bleibt_sichtbar():
    reg = HilfeRegister((_kapitel("dashboard"),))
    g = baue_gliederung(reg, ["dashboard.view"])
    eintraege = {e.sicht_id: e for e in g.eintraege()}
    assert eintraege["dashboard"].vorhanden is True
    assert eintraege["faelle"].vorhanden is False
    assert "faelle" in g.offene()


# --- HD03 / HD04 --------------------------------------------------------------

def test_hd03_verzeichnis_und_markierung():
    reg = HilfeRegister((_kapitel("dashboard"),))
    html = render_hilfe_seite(baue_gliederung(reg, ["dashboard.view"]))
    assert 'href="#dashboard"' in html
    assert 'href="#faelle"' in html
    assert "Hilfe folgt" in html
    assert "Fallübersicht" in html          # Label aus dem Katalog, UTF-8


def test_hd04_kapitel_html():
    reg = HilfeRegister((_kapitel(
        "dashboard",
        zusatz=[Abschnitt("ampel", "Die Ampel", ("Erklaerung.",))]),))
    html = render_hilfe_seite(baue_gliederung(reg, ["dashboard.view"]))
    assert '<article class="aiw-h-kapitel" id="dashboard">' in html
    assert "Rechtelage:" in html
    assert "Scope &#x27;alle&#x27;" in html or "Scope 'alle'" in html
    for a in PFLICHT_ANKER:
        assert 'id="dashboard-%s"' % a in html
    assert 'id="dashboard-ampel"' in html
    assert "Stand: Build 589" in html


# --- HD05 / HD06 --------------------------------------------------------------

def test_hd05_escaping():
    boese = 'Ein <script>alert("x")</script> & ein Anfuehrungszeichen "'
    reg = HilfeRegister((_kapitel(
        "dashboard", zusatz=[Abschnitt("probe", "Probe", (boese,))]),))
    html = render_hilfe_seite(baue_gliederung(reg, ["dashboard.view"]))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp;" in html


def test_hd06_listen():
    reg = HilfeRegister((_kapitel("dashboard", zusatz=[
        Abschnitt("schritte", "Schritte", (), ("erst", "dann"), True),
        Abschnitt("punkte", "Punkte", (), ("a", "b"), False),
    ]),))
    html = render_hilfe_seite(baue_gliederung(reg, ["dashboard.view"]))
    assert "<ol>\n<li>erst</li>" in html
    assert "<ul>\n<li>a</li>" in html


# --- HD07 / HD08 --------------------------------------------------------------

def test_hd07_fusszeile():
    reg = HilfeRegister((_kapitel("dashboard"),))
    html = render_hilfe_seite(baue_gliederung(reg, ["dashboard.view"]),
                              version="0.8.589", build=589,
                              stand_datum="2026-07-31")
    assert "0.8.589" in html
    assert "589" in html
    assert "fallinhaltsfrei" in html


def test_hd08_aufbauhinweis_nur_solange_offen():
    # alles offen -> Hinweis da
    html_offen = render_hilfe_seite(
        baue_gliederung(HilfeRegister(()), ["dashboard.view"]))
    assert "im Aufbau" in html_offen

    # nur 'viewprefs' sichtbar UND vorhanden -> kein Hinweis
    reg = HilfeRegister((_kapitel("viewprefs"),))
    html_zu = render_hilfe_seite(baue_gliederung(reg, []))
    assert "im Aufbau" not in html_zu


# --- HD09 / HD10 --------------------------------------------------------------

def test_hd09_kontext_nutzlast():
    reg = HilfeRegister((_kapitel("dashboard", kontext=[
        Kontexthilfe("dashboard.kachel", "Kachel", "Zeigt eine Kennzahl.",
                     verweis="dashboard#aufbau"),
        Kontexthilfe("dashboard.filter", "Filter", "Grenzt die Anzeige ein."),
    ]),))
    n = kontext_nutzlast(reg, "dashboard")
    assert n["sicht"] == "dashboard"
    assert n["anzahl"] == 2
    assert n["eintraege"]["dashboard.kachel"]["verweis"] == "dashboard#aufbau"
    assert n["eintraege"]["dashboard.filter"]["verweis"] is None

    leer = kontext_nutzlast(reg, "faelle")
    assert leer == {"sicht": "faelle", "anzahl": 0, "eintraege": {}}


def test_hd10_anker_id():
    assert anker_id("faelle", "ampel") == "faelle-ampel"


def test_hd11_platzhalter_text_ist_ehrlich():
    """
    Der Platzhalter darf nicht so klingen, als gaebe es nichts zu sagen. Er
    nennt die Baustelle - dann weiss die lesende Person, dass daran gearbeitet
    wird, und kann nachfragen.
    """
    assert "folgt" in PLATZHALTER_TEXT
    assert "Baustelle H" in PLATZHALTER_TEXT


# --- HD12 bis HD16 (Build 593 / H6) ------------------------------------------

def test_hd12_suchindex_inhalt():
    reg = HilfeRegister((_kapitel("dashboard"),))
    idx = suchindex(baue_gliederung(reg, ["dashboard.view"]))
    nach_id = {e["id"]: e for e in idx}
    assert set(nach_id) == {"dashboard", "faelle", "viewprefs"}

    d = nach_id["dashboard"]
    assert d["offen"] is False
    assert d["gruppe"] == "Ueberblick"
    # Die Stichworte stammen aus dem VIEW_CATALOG - dem Bestand, der auch die
    # Kommandopalette speist. Kein zweiter Stichwortvorrat.
    assert "kacheln" in d["worte"]
    # Abschnittsueberschriften sind mit drin ...
    assert "rechtelage" in d["worte"]
    # ... der Fliesstext dagegen NICHT (sonst faende 'Text' jedes Kapitel).
    assert "fuelltext" not in d["worte"]
    assert nach_id["faelle"]["offen"] is True


def test_hd13_suchindex_ist_gefiltert():
    reg = HilfeRegister((_kapitel("dashboard"), _kapitel("policy")))
    ids = {e["id"] for e in suchindex(baue_gliederung(reg, ["dashboard.view"]))}
    assert "policy" not in ids, (
        "Was gesperrt ist, darf auch nicht durchsuchbar sein (E1).")


def test_hd14_eingebetteter_index_ist_gueltiges_json():
    import json
    import re
    boese = 'Ein </script> und ein <b>Tag</b>'
    reg = HilfeRegister((_kapitel(
        "dashboard", zusatz=[Abschnitt("probe", boese, ("Text.",))]),))
    html = render_hilfe_seite(baue_gliederung(reg, ["dashboard.view"]))
    m = re.search(
        r'<script type="application/json" id="aiw-h-index">(.*?)</script>',
        html, re.S)
    assert m is not None
    # Der Block laesst sich lesen ...
    daten = json.loads(m.group(1))
    assert any(e["id"] == "dashboard" for e in daten)
    # ... und enthaelt kein rohes '<', das ihn vorzeitig beenden koennte.
    assert "<" not in m.group(1)


def test_hd15_blaetterleiste():
    reg = HilfeRegister((_kapitel("dashboard"),))
    g = baue_gliederung(reg, ["dashboard.view"])
    html = render_hilfe_seite(g)
    eintraege = g.eintraege()
    assert len(eintraege) >= 3
    assert html.count('class="aiw-h-blaettern"') == len(eintraege)
    # Das erste Kapitel hat keinen Rueckweg, das letzte kein Weiter.
    erstes = html.index('id="%s"' % eintraege[0].sicht_id)
    naechstes = html.index('id="%s"' % eintraege[1].sicht_id)
    assert "aiw-h-vor" not in html[erstes:naechstes]


def test_hd16_suchfeld_und_skript():
    html = render_hilfe_seite(
        baue_gliederung(HilfeRegister(()), ["dashboard.view"]))
    assert '<script src="/static/help.js"></script>' in html
    # Ohne JavaScript bleibt das Feld verborgen - ein totes Eingabefeld waere
    # schlechter als keines.
    assert 'id="aiw-h-suchfeld" hidden' in html
