# -*- coding: utf-8 -*-
# =============================================================================
# tests/test_xpath_versatz_messen.py
# Regressionstests zu tools/xpath_versatz_messen.py
# =============================================================================
# Zweck:
#   Das Werkzeug misst, um wie viele BEITRAEGE ein gespeicherter
#   XPath-Ausdruck danebenzeigt, und ob der Versatz an der ZEIT oder an der
#   POSITION haengt. Diese Tests halten fest, dass es
#
#     * richtig misst (XV04),
#     * NICHT raet, wo der Wortlaut mehrdeutig ist (XV06),
#     * "nicht entscheidbar" sagt, statt sich eine Deutung auszusuchen (XV07),
#     * und nichts schreibt (XV08).
#
# ── JEDE GEGENPROBE MUSS ANSCHLAGEN ──────────────────────────────────────────
#
#   Strategie 4.3 aus der Uebergabe nach Build 752: zweimal wurde in dieser
#   Sitzungsreihe ein Schutz stillgelegt und KEIN Test rot. Zu jedem Test hier
#   steht deshalb, was ihn rot macht - und XV06 und XV07 sind ausdruecklich
#   Gegenproben und nicht Bestaetigungen.
#
# Version: 0.8.753 - Build 753
# =============================================================================

from __future__ import annotations

import json
import os
import sqlite3
import sys

import pytest

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WURZEL not in sys.path:
    sys.path.insert(0, WURZEL)

from tools import xpath_versatz_messen as XV                # noqa: E402


# ---------------------------------------------------------------------------
# Die Vorrichtung
# ---------------------------------------------------------------------------
#
# SIE BILDET DEN AUFBAU DER PN-SEITEN NACH, und zwar den gemessenen: unter
# '#page-body' stehen drei fuehrende Elemente und danach je Beitrag ZWEI
# (ein Trenner-<div> und der Beitrag selbst). Daraus folgt
# 'Elementindex = 2*Platz + 3', genau wie in Alex' Browsermessung vom
# 31.08.2026 ueber '/forum/pmsnew.php?mdl=topic&tid=64200' - dort ohne eine
# einzige Abweichung ueber 25 Beitraege.
#
# Waere die Vorrichtung anders gebaut, pruefte sie einen Aufbau, den es nicht
# gibt - und ein gruener Test sagte dann nichts ueber den Bestand.

_BEITRAEGE = (1001, 1002, 1003, 1004)


def _seiten_html() -> bytes:
    teile = []
    for pid in _BEITRAEGE:
        teile.append(
            '<div class="sep"></div>'
            '<div id="p%d" class="blockpost">'
            '<div><div><div><div><p>Gemeinsamer Satz. Kennwort%d hier.</p>'
            '</div></div></div></div></div>' % (pid, pid))
    return (
        '<div id="wrap"><div id="brdleft"></div><div id="page-header"></div>'
        '<div id="page-body">'
        '<div class="kopf"></div><div class="pagepost"></div>'
        '<div class="leiste"></div>'
        + "".join(teile) +
        '</div></div>').encode("utf-8")


def _anker(div_index: int) -> str:
    """Ein Ausdruck, der auf den Beitrag am gegebenen Elementindex zeigt."""
    return ("./div[1]/div[3]/div[%d]/div[1]/div[1]/div[1]/div[1]/p[1]"
            "/text()[1]" % div_index)


def _div_fuer_platz(platz: int) -> int:
    """
    Der <div>-Index des Beitrags am gegebenen Platz.

    Drei fuehrende Elemente, danach je Beitrag zwei (Trenner + Beitrag):
    Platz 1 ist das 5. Kind, Platz 2 das 7. usw. In dieser Vorrichtung sind
    ALLE Kinder <div>, deshalb faellt der <div>-Index mit dem Elementindex
    zusammen - im Bestand tut er das nicht, dort steht davor ein Element
    anderen Namens, und der <div>-Index liegt um eins darunter. Fuer die
    Messung ist das ohne Belang: sie zaehlt Plaetze, nicht Indizes.
    """
    return 2 * platz + 3


def _baue(verz, markierungen, gesichert=1756000000):
    """
    (evidence-Pfad, forensic-Pfad) bauen.

    'markierungen' ist eine Folge von (id, ts, div_index, wortlaut).
    """
    os.makedirs(verz, exist_ok=True)
    f_pfad = os.path.join(verz, "forensic_999.db")
    e_pfad = os.path.join(verz, "evidence_999.db")
    for p in (f_pfad, e_pfad):
        if os.path.exists(p):
            os.remove(p)

    con = sqlite3.connect(f_pfad)
    con.execute("CREATE TABLE pages(id INTEGER PRIMARY KEY, "
                "url_canonical TEXT, html BLOB, title TEXT, "
                "fetched_at INTEGER, http_status INTEGER, "
                "scrape_context TEXT, method TEXT)")
    con.execute("CREATE TABLE page_aliases(url_raw TEXT PRIMARY KEY, "
                "page_id INTEGER)")
    con.execute("INSERT INTO pages VALUES(1,'/forum/pmsnew.php?tid=1',?,"
                "'t',?,200,'user','GET')", (_seiten_html(), gesichert))
    con.commit()
    con.close()

    con = sqlite3.connect(e_pfad)
    con.execute("CREATE TABLE annotations(id INTEGER PRIMARY KEY, "
                "page_url TEXT, element_id TEXT, category TEXT, text TEXT, "
                "ts INTEGER, investigator_id INTEGER, selection_json TEXT, "
                "tags_json TEXT, local_id TEXT, post_id INTEGER, "
                "created_by TEXT, deleted_at INTEGER, version_nr INTEGER, "
                "prev_id INTEGER, actual_uid INTEGER)")
    for kennung, ts, div_index, wortlaut in markierungen:
        sel = json.dumps({"xpathStart": _anker(div_index), "offsetStart": 0,
                          "xpathEnd": _anker(div_index), "offsetEnd": 1,
                          "textContent": wortlaut})
        con.execute(
            "INSERT INTO annotations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (kennung, "/forum/pmsnew.php?tid=1", None, "k", "", ts, 1, sel,
             None, None, None, "pruefer", None, 1, None, None))
    con.commit()
    con.close()
    return e_pfad, f_pfad


def _fahre(e_pfad, f_pfad, seite=None):
    """Den Lauf fahren und (Rueckgabewert, Ausgabetext) liefern."""
    zeilen = []
    code = XV.lauf(e_pfad, f_pfad, seite, zeilen.append)
    return code, "\n".join(zeilen)


# ---------------------------------------------------------------------------
# XV01 - Zeitstempel
# ---------------------------------------------------------------------------

def test_xv01_sekunden_nimmt_sekunden_und_millisekunden():
    """
    Rot, wenn die Millisekunden-Erkennung faellt: dann vergleicht das
    Werkzeug einen Millisekundenstempel mit einem Sekundenstempel und meldet
    reihenweise "Markierung aelter als der Abzug", wo nichts ist.
    """
    assert XV.sekunden(1756000000) == 1756000000
    assert XV.sekunden(1756000000123) == 1756000000
    assert XV.sekunden(None) is None
    assert XV.sekunden("keine Zahl") is None
    assert XV.zeit(None) == "(kein Zeitstempel)"
    assert XV.zeit(1756000000).startswith("2025-")


# ---------------------------------------------------------------------------
# XV02 - Monotonie
# ---------------------------------------------------------------------------

def test_xv02_monotonie_unterscheidet_vier_faelle():
    """
    Rot, wenn 'KONSTANT' mit 'monoton steigend' zusammenfaellt. Genau diese
    Unterscheidung traegt den Befund: eine konstante Folge sagt "eine Zahl je
    Seite", eine steigende sagt "es waechst nach unten".
    """
    assert XV.monotonie([3, 3, 3]) == "KONSTANT"
    assert XV.monotonie([1, 2, 5]) == "monoton steigend"
    assert XV.monotonie([5, 2, 1]) == "monoton fallend"
    assert XV.monotonie([1, 5, 2]) == "nicht monoton"


# ---------------------------------------------------------------------------
# XV03 - trennende Paare
# ---------------------------------------------------------------------------

def test_xv03_trennende_paare_nur_bei_gegenlauf():
    """
    Rot, wenn gleichlaeufige Messwerte als trennend ausgegeben wuerden. Dann
    behauptete das Werkzeug, es koenne Zeit und Position auseinanderhalten,
    wo es das nicht kann - und das ist die Sorte Aussage, die diesem Projekt
    schon sechs Builds gekostet hat.
    """
    # (ts, platz, versatz, id) - Zeit und Position laufen gleich
    gleich = [(10, 1, 0, "a"), (20, 2, 1, "b"), (30, 3, 2, "c")]
    assert XV.trennende_paare(gleich) == []
    # eine Markierung spaeter, aber weiter oben
    gegen = gleich + [(40, 1, 3, "d")]
    paare = XV.trennende_paare(gegen)
    assert paare, "Der Gegenlauf wurde nicht erkannt"
    assert all(("d" in (a[3], b[3])) for a, b in paare)


# ---------------------------------------------------------------------------
# XV04 - der Kernfall: der Versatz wird richtig gemessen
# ---------------------------------------------------------------------------

def test_xv04_versatz_wird_richtig_gemessen(tmp_path):
    """
    Rot, sobald die Zuordnung Ausdruck -> Beitrag oder Wortlaut -> Beitrag
    kippt. Das ist der Kern des Werkzeugs.
    """
    e, f = _baue(str(tmp_path), [
        # Ausdruck zeigt auf Platz 1, Wortlaut steht in Platz 1 -> +0
        (1, 1755900000, _div_fuer_platz(1), "Kennwort1001"),
        # Ausdruck zeigt auf Platz 3, Wortlaut steht in Platz 2 -> +1
        (2, 1755900100, _div_fuer_platz(3), "Kennwort1002"),
        # Ausdruck zeigt auf Platz 2, Wortlaut steht in Platz 4 -> -2
        (3, 1755900200, _div_fuer_platz(2), "Kennwort1004"),
    ], gesichert=1755800000)
    code, text = _fahre(e, f)
    assert "Beitraege im Abzug: 4" in text
    assert "+0" in text and "+1" in text and "-2" in text
    assert code == XV.RUECK_BEFUND


# ---------------------------------------------------------------------------
# XV05 - Gegenprobe: Abzug juenger als die Markierung
# ---------------------------------------------------------------------------

def test_xv05_abzug_juenger_als_markierung_wird_gemeldet(tmp_path):
    """
    Rot, wenn der Zeitvergleich ausfaellt. Er ist die Angabe, die ueber
    'Sicherungsproblem' oder 'Auswertungsproblem' entscheidet - fehlt sie,
    bleibt die Frage offen, ohne dass es jemandem auffiele.
    """
    e, f = _baue(str(tmp_path), [
        (1, 1755900000, _div_fuer_platz(1), "Kennwort1001"),
    ], gesichert=1756000000)          # Abzug SPAETER als die Markierung
    _code, text = _fahre(e, f)
    assert "AELTER als der Abzug" in text

    # Und die Gegenrichtung: liegt der Abzug davor, darf der Satz NICHT
    # erscheinen. Ohne diese Haelfte wuerde ein Werkzeug, das den Satz immer
    # druckt, den Test bestehen.
    e2, f2 = _baue(str(tmp_path / "zwei"), [
        (1, 1756100000, _div_fuer_platz(1), "Kennwort1001"),
    ], gesichert=1756000000)
    _code2, text2 = _fahre(e2, f2)
    assert "AELTER als der Abzug" not in text2
    assert "erwarteter Fall" in text2


# ---------------------------------------------------------------------------
# XV06 - Gegenprobe: mehrdeutiger Wortlaut ergibt KEINEN Messwert
# ---------------------------------------------------------------------------

def test_xv06_mehrdeutiger_wortlaut_ergibt_keinen_messwert(tmp_path):
    """
    Rot, sobald das Werkzeug bei mehrdeutigem Wortlaut irgendeinen Beitrag
    nimmt. Befund Build 752, Beleg #65: ein Wortlaut, der in 24 von 25
    Beitraegen vorkommt, bestaetigt jeden davon und damit keinen. Ein
    Messwert aus so etwas waere schlimmer als keiner, weil er wie einer
    aussieht.
    """
    e, f = _baue(str(tmp_path), [
        # 'Gemeinsamer Satz.' steht in ALLEN vier Beitraegen
        (1, 1755900000, _div_fuer_platz(1), "Gemeinsamer Satz."),
    ], gesichert=1755800000)
    _code, text = _fahre(e, f)
    assert "(4 Traeger)" in text, text
    # Keine Versatzangabe fuer diese Zeile - kein '+0', kein '-0'
    zeile = [z for z in text.split("\n") if z.strip().startswith("1 ")]
    assert zeile, "Die Zeile zur Markierung 1 fehlt"
    assert "+" not in zeile[0].split("(4 Traeger)")[1]


# ---------------------------------------------------------------------------
# XV07 - Gegenprobe: "nicht entscheidbar" wird gesagt
# ---------------------------------------------------------------------------

def test_xv07_ohne_trennendes_paar_wird_das_gesagt(tmp_path):
    """
    Rot, wenn das Werkzeug bei gleichlaeufigen Messwerten eine Deutung
    behauptet. Es MUSS an dieser Stelle sagen, dass es die Frage aus diesem
    Bestand nicht entscheiden kann.
    """
    e, f = _baue(str(tmp_path), [
        (1, 1755900000, _div_fuer_platz(2), "Kennwort1001"),
        (2, 1755900100, _div_fuer_platz(3), "Kennwort1002"),
        (3, 1755900200, _div_fuer_platz(4), "Kennwort1003"),
    ], gesichert=1755800000)
    _code, text = _fahre(e, f)
    assert "KEIN TRENNENDES PAAR" in text
    assert "NICHT zu entscheiden" in text


# ---------------------------------------------------------------------------
# XV08 - es schreibt nichts, und es KANN nichts schreiben
# ---------------------------------------------------------------------------

def test_xv08_verbindungen_sind_schreibgeschuetzt(tmp_path):
    """
    Rot, sobald jemand 'mode=ro' entfernt. Bei einem Werkzeug, das ein
    Beweismittel anfasst, ist das keine Formsache: die Trockenuebung soll
    nicht "nicht schreiben", sie soll nicht schreiben KOENNEN.
    """
    e, f = _baue(str(tmp_path), [
        (1, 1755900000, _div_fuer_platz(1), "Kennwort1001"),
    ])
    vorher = (os.path.getmtime(e), os.path.getsize(e),
              os.path.getmtime(f), os.path.getsize(f))
    _fahre(e, f)
    nachher = (os.path.getmtime(e), os.path.getsize(e),
               os.path.getmtime(f), os.path.getsize(f))
    assert vorher == nachher

    con = XV._oeffne_ro(e)
    try:
        with pytest.raises(sqlite3.OperationalError):
            con.execute("UPDATE annotations SET category='x'")
    finally:
        con.close()


# ---------------------------------------------------------------------------
# XV09 - Rueckgabewerte und Seitenfilter
# ---------------------------------------------------------------------------

def test_xv09_rueckgabewerte(tmp_path):
    """
    Rot, wenn ein Abbruch als Erfolg zurueckkaeme. Der Rueckgabewert ist das,
    was ein Ablauf auswertet - er darf nicht schoenreden.
    """
    e, f = _baue(str(tmp_path), [
        (1, 1755900000, _div_fuer_platz(1), "Kennwort1001"),
    ], gesichert=1755800000)

    # Fehlende Datei -> Abbruch
    code, _ = _fahre(os.path.join(str(tmp_path), "gibt_es_nicht.db"), f)
    assert code == XV.RUECK_ABBRUCH

    # Filter, der nichts trifft -> sauber, nichts zu melden
    code, text = _fahre(e, f, seite="tid=999999")
    assert code == XV.RUECK_SAUBER
    assert "nichts zu messen" in text

    # Filter, der trifft
    code, text = _fahre(e, f, seite="tid=1")
    assert "SEITE /forum/pmsnew.php?tid=1" in text
