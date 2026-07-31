# =============================================================================
# tests/test_help_katalog_paritaet.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H1)
# =============================================================================
# Testsuite fuer Build 588: Paritaet zwischen dem VIEW_CATALOG in
# management/server/static/cockpit.js und dem Python-Spiegel
# management/help/sicht_katalog.py.
#
# WARUM DIESER TEST DER WICHTIGSTE DER GANZEN BAUSTELLE IST (Konzept §4.2):
#   Hilfe veraltet schneller als Code, weil sie beim Aendern nicht
#   mitkompiliert. Dieser Test IST die Kompilierung: Wer im Cockpit eine Sicht
#   hinzufuegt, umbenennt, verschiebt oder entfernt, ohne die Hilfe
#   nachzuziehen, bekommt hier einen roten Lauf - und zwar mit Nennung der
#   konkreten Sicht. Damit ist der bislang von Hand gepflegte ANKERDELTA-
#   Vermerk ("VIEW_CATALOG 43") fuer die Hilfe maschinell abgesichert.
#
# HP01 - der Spiegel ist in sich konsistent (verify_katalog_konsistent)
# HP02 - gleiche Anzahl Sichten in cockpit.js und Spiegel
# HP03 - gleiche IDs in GLEICHER REIHENFOLGE (die Reihenfolge ist die Nav-
#        und die Kapitelfolge - sie ist kein Zufall, sondern Aussage)
# HP04 - je Sicht: cap, caps, group, label, stichworte deckungsgleich
# HP05 - genau eine Sicht mit 'immer: true', und es ist 'viewprefs'
# HP06 - Gruppenfolge deckungsgleich (erstes Auftreten)
# HP07 - der Parser selbst ist scharf: an einem manipulierten Katalogtext
#        schlaegt der Vergleich an (Negativprobe - ein Test, der nie
#        anschlagen kann, ist kein Test)
#
# Version: v0.8.588 - Build: 588 - 2026-07-31
# =============================================================================

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.help.sicht_katalog import (            # noqa: E402
    SICHT_KATALOG, GRUPPEN_REIHENFOLGE, verify_katalog_konsistent,
)

COCKPIT_JS = os.path.join(
    os.path.dirname(__file__), "..",
    "management", "server", "static", "cockpit.js")


# -----------------------------------------------------------------------------
# Der Parser. Bewusst schlicht und auf die LITERALE Schreibweise des
# VIEW_CATALOG festgelegt (Konvention aus dem Bauplan H1): jeder Eintrag ist
# ein Objektliteral in einer festen Feldreihenfolge. Ein berechneter Eintrag
# waere hier nicht lesbar - und genau deshalb ist er im Katalog verboten.
# -----------------------------------------------------------------------------

def _katalog_block(quelltext: str) -> str:
    """Der Text zwischen 'var VIEW_CATALOG = [' und der schliessenden ']'."""
    start = quelltext.index("var VIEW_CATALOG")
    ende = quelltext.index("\n    ];", start)
    return quelltext[start:ende]


def _ohne_kommentare(block: str) -> str:
    """
    Entfernt Zeilenkommentare. Notwendig, weil die Begruendungen im Katalog
    Woerter wie 'immer' enthalten - ein Regex ueber den Rohtext wuerde sie
    dem falschen Eintrag zuschlagen (genau dieser Fehler ist beim Erstellen
    des Spiegels aufgetreten und hat den Test hier geformt).
    """
    zeilen = []
    for z in block.split("\n"):
        gestrippt = z.strip()
        if gestrippt.startswith("//"):
            continue
        zeilen.append(z)
    return "\n".join(zeilen)


def parse_view_catalog(quelltext: str):
    """
    Liest die VIEW_CATALOG-Eintraege als Liste von Woerterbuechern in
    Quelltext-Reihenfolge. Reine Funktion - deshalb in HP07 mit einem
    manipulierten Text pruefbar.
    """
    block = _ohne_kommentare(_katalog_block(quelltext))
    teile = re.split(r"(?=\{\s*id:\s*')", block)
    eintraege = []
    for t in teile[1:]:
        # Auf das Objektliteral begrenzen: bis zur ersten schliessenden
        # Klammer auf Eintragsebene.
        ende = t.index("}")
        t = t[:ende + 1]
        m_id = re.search(r"id:\s*'([^']+)'", t)
        m_cap = re.search(r"cap:\s*(?:'([^']+)'|null)", t)
        m_caps = re.search(r"caps:\s*\[([^\]]*)\]", t)
        m_grp = re.search(r"group:\s*'([^']+)'", t)
        m_lab = re.search(r"label:\s*'([^']*)'", t)
        m_st = re.search(r"stichworte:\s*'([^']*)'", t)
        assert m_id is not None, "Katalogeintrag ohne id: %r" % t[:80]
        assert m_grp is not None, "Katalogeintrag ohne group: %r" % t[:80]
        eintraege.append({
            "id": m_id.group(1),
            "cap": m_cap.group(1) if (m_cap and m_cap.group(1)) else None,
            "caps": tuple(c.strip().strip("'")
                          for c in m_caps.group(1).split(",")) if m_caps else (),
            "group": m_grp.group(1),
            "label": m_lab.group(1) if m_lab else None,
            "stichworte": m_st.group(1) if m_st else None,
            "immer": bool(re.search(r"immer:\s*true", t)),
        })
    return eintraege


@pytest.fixture(scope="module")
def js_katalog():
    with open(COCKPIT_JS, encoding="utf-8") as fh:
        return parse_view_catalog(fh.read())


def test_hp01_spiegel_in_sich_konsistent():
    verify_katalog_konsistent()  # darf nicht werfen


def test_hp02_gleiche_anzahl(js_katalog):
    assert len(js_katalog) == len(SICHT_KATALOG), (
        "cockpit.js fuehrt %d Sichten, der Hilfe-Spiegel %d. Neue Sicht ohne "
        "Hilfe-Nachzug?" % (len(js_katalog), len(SICHT_KATALOG)))


def test_hp03_gleiche_ids_in_gleicher_reihenfolge(js_katalog):
    js_ids = [e["id"] for e in js_katalog]
    py_ids = [s.id for s in SICHT_KATALOG]
    assert js_ids == py_ids, (
        "Sicht-IDs oder deren Reihenfolge weichen ab.\n  nur in cockpit.js: "
        "%s\n  nur im Spiegel: %s"
        % (sorted(set(js_ids) - set(py_ids)), sorted(set(py_ids) - set(js_ids))))


def test_hp04_felder_deckungsgleich(js_katalog):
    py = {s.id: s for s in SICHT_KATALOG}
    abweichungen = []
    for e in js_katalog:
        s = py[e["id"]]
        if s.cap != e["cap"]:
            abweichungen.append("%s.cap: js=%r py=%r" % (e["id"], e["cap"], s.cap))
        if tuple(s.caps) != tuple(e["caps"]):
            abweichungen.append(
                "%s.caps: js=%r py=%r" % (e["id"], e["caps"], s.caps))
        if s.gruppe != e["group"]:
            abweichungen.append(
                "%s.group: js=%r py=%r" % (e["id"], e["group"], s.gruppe))
        if s.label != e["label"]:
            abweichungen.append(
                "%s.label: js=%r py=%r" % (e["id"], e["label"], s.label))
        if s.stichworte != e["stichworte"]:
            abweichungen.append(
                "%s.stichworte: js=%r py=%r"
                % (e["id"], e["stichworte"], s.stichworte))
    assert not abweichungen, "Spiegel weicht ab:\n  " + "\n  ".join(abweichungen)


def test_hp05_genau_eine_sicht_ohne_rechtepruefung(js_katalog):
    js_immer = [e["id"] for e in js_katalog if e["immer"]]
    py_immer = [s.id for s in SICHT_KATALOG if s.immer]
    assert js_immer == ["viewprefs"], (
        "Es darf genau EINE Sicht ohne Rechtepruefung geben ('viewprefs', "
        "Beleg cockpit.js:337-348). Gefunden: %s" % js_immer)
    assert py_immer == js_immer


def test_hp06_gruppenfolge_deckungsgleich(js_katalog):
    js_gruppen = []
    for e in js_katalog:
        if e["group"] not in js_gruppen:
            js_gruppen.append(e["group"])
    assert tuple(js_gruppen) == GRUPPEN_REIHENFOLGE


def test_hp07_negativprobe_parser_schlaegt_an():
    """
    Der Test muss anschlagen KOENNEN. Wir bauen einen Miniatur-Katalogtext,
    entfernen daraus eine Sicht und pruefen, dass der Vergleich das merkt.
    """
    text = (
        "    var VIEW_CATALOG = [\n"
        "        // eine Begruendung, in der das Wort immer vorkommt\n"
        "        { id: 'alpha', cap: 'a.view', group: 'G1', label: 'Alpha',\n"
        "          stichworte: 'a' },\n"
        "        { id: 'beta',  cap: null, immer: true, group: 'G1',"
        " label: 'Beta',\n"
        "          stichworte: 'b' }\n"
        "    ];\n"
    )
    eintraege = parse_view_catalog(text)
    assert [e["id"] for e in eintraege] == ["alpha", "beta"]
    # Der Kommentar mit dem Wort 'immer' darf NICHT auf 'alpha' abfaerben.
    assert eintraege[0]["immer"] is False
    assert eintraege[1]["immer"] is True
    assert eintraege[0]["cap"] == "a.view"
    assert eintraege[1]["cap"] is None

    verkuerzt = text.replace(
        "        { id: 'beta',  cap: null, immer: true, group: 'G1',"
        " label: 'Beta',\n          stichworte: 'b' }\n", "")
    assert [e["id"] for e in parse_view_catalog(verkuerzt)] == ["alpha"]
