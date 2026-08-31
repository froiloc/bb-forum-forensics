# -*- coding: utf-8 -*-
# =============================================================================
# tests/test_annotation_pruefung.py
# Regressionstests zu management/maintenance/annotation_pruefung.py
# und tools/annotationen_verifizieren.py
# =============================================================================
# Zweck:
#   Die Verifikation entscheidet, ob eine Annotation sich im gesicherten
#   Seitenabzug bestaetigen laesst - und mit welcher Belegkraft. Sie ersetzt
#   eine Pruefung, die bis Build 753 ausschliesslich nachgesehen hat, ob die
#   verlangte POSITION existiert.
#
# ── DIE GEGENPROBE, UM DIE ES HIER VOR ALLEM GEHT ────────────────────────────
#
#   AP04 ist der Fall, den die alte Pruefung durchgewunken hat: der Ausdruck
#   loest VOLLSTAENDIG auf, benennt einen Beitrag - und der markierte
#   Wortlaut steht in einem anderen. Bis Build 753 hiess das 'traegt' und
#   wurde eingetragen. Faellt AP04 weg, ist genau dieser Fehler zurueck, und
#   zwar unsichtbar.
#
#   Zu jedem Test steht, was ihn rot macht.
#
# Version: 0.8.754 - Build 754
# =============================================================================

from __future__ import annotations

import json
import os
import sqlite3
import sys

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WURZEL not in sys.path:
    sys.path.insert(0, WURZEL)

from management.maintenance import annotation_pruefung as AP     # noqa: E402
from tools import annotationen_verifizieren as AV                # noqa: E402


# ---------------------------------------------------------------------------
# Die Vorrichtung - vier Beitraege, jeder mit einem eigenen Kennwort und
# einem gemeinsamen Satz. Aufbau wie die PN-Seiten: drei fuehrende Elemente,
# danach je Beitrag ein Trenner-<div> und der Beitrag.
# ---------------------------------------------------------------------------

_POSTS = (1001, 1002, 1003, 1004)


def _html() -> bytes:
    teile = []
    for pid in _POSTS:
        teile.append(
            '<div class="sep"></div>'
            '<div id="p%d" class="blockpost"><div><div><div><div>'
            '<p>Gemeinsamer Satz. Kennwort%d steht hier allein.</p>'
            '</div></div></div></div></div>' % (pid, pid))
    return ('<div id="wrap"><div id="brdleft"></div>'
            '<div id="page-header"></div><div id="page-body">'
            '<div class="k"></div><div class="pagepost"></div>'
            '<div class="l"></div>' + "".join(teile)
            + '</div></div>').encode("utf-8")


def _pfad_zu_platz(platz: int) -> str:
    """Der Ausdruck auf den Text des Beitrags am gegebenen Platz."""
    return ("./div[1]/div[3]/div[%d]/div[1]/div[1]/div[1]/div[1]/p[1]"
            "/text()[1]" % (2 * platz + 3))


def _sel(platz: int, wortlaut: str, von=0, bis=None, ende_platz=None):
    start = _pfad_zu_platz(platz)
    ende = _pfad_zu_platz(ende_platz if ende_platz is not None else platz)
    if bis is None:
        bis = von + len(wortlaut)
    return json.dumps({"xpathStart": start, "xpathEnd": ende,
                       "offsetStart": von, "offsetEnd": bis,
                       "textContent": wortlaut})


def _pruefer():
    from report_render.absatz_finder import AbsatzFinder
    finder = AbsatzFinder.aus_seiten_html(_html())
    assert finder.brauchbar, "Die Vorrichtung ist nicht zerlegbar"
    return AP.AnnotationPruefer(finder)


# ---------------------------------------------------------------------------
# AP01 - die Vorrichtung selbst
# ---------------------------------------------------------------------------

def test_ap01_vorrichtung_bildet_den_gemessenen_aufbau_ab():
    """
    Rot, wenn die Vorrichtung nicht mehr dem gemessenen Seitenaufbau
    entspricht. Eine Vorrichtung, die einen Aufbau prueft, den es nicht gibt,
    liefert gruene Tests ueber nichts.
    """
    p = _pruefer()
    assert [nr for nr, _el in p.reihe] == list(_POSTS)
    assert p.platz(1001) == 1 and p.platz(1004) == 4
    assert p.platz(9999) is None


# ---------------------------------------------------------------------------
# AP02 - der starke Fall
# ---------------------------------------------------------------------------

def test_ap02_position_und_inhalt_sagen_dasselbe():
    """
    Rot, wenn die Textprobe nicht mehr greift. Sie ist der einzige Weg zu
    'BESTAETIGT'; ohne sie faellt jeder Fall auf die schwaechere
    Wortlautprobe zurueck, und die Unterscheidung, um die es geht, ist weg.
    """
    p = _pruefer()
    b = p.pruefe(1, "/s", _sel(2, "Gemeinsamer Satz."))
    assert b.urteil == AP.URTEIL_BESTAETIGT
    assert b.position_vorhanden is True
    assert b.beitrag_anker == 1002
    assert b.beitrag == 1002
    assert b.textprobe == AP.TEXT_GLEICH


# ---------------------------------------------------------------------------
# AP03 - Beitrag belegt, Fundstelle nicht
# ---------------------------------------------------------------------------

def test_ap03_beitrag_belegt_wenn_textprobe_nicht_greift():
    """
    Rot, wenn dieser Fall mit AP02 zusammenfaellt. 'BEITRAG_BELEGT' traegt
    den Beitrag, aber NICHT die Stelle darin - fuer die Beitragsnummer
    genuegt das, fuer den Zeichenausschnitt des Vollzitats nicht. Beides
    gleich zu benennen hiesse, dem Bericht eine Genauigkeit zu geben, die er
    nicht hat.
    """
    p = _pruefer()
    # Versatz zeigt auf eine andere Stelle desselben Beitrags; der Wortlaut
    # ist auf der Seite trotzdem eindeutig.
    b = p.pruefe(2, "/s", _sel(3, "Kennwort1003", von=0, bis=5))
    assert b.urteil == AP.URTEIL_BEITRAG_BELEGT
    assert b.beitrag == 1003
    assert b.textprobe == AP.TEXT_ABWEICHEND


# ---------------------------------------------------------------------------
# AP04 - DIE GEGENPROBE: der Fall, den die alte Pruefung durchwinkte
# ---------------------------------------------------------------------------

def test_ap04_vollstaendig_aufgeloest_und_trotzdem_falsch():
    """
    ROT HEISST: der Fehler aus Build 750-753 ist zurueck.

    Der Ausdruck loest VOLLSTAENDIG auf und benennt einen Beitrag - die alte
    Pruefung meldete hier 'traegt'. Der markierte Wortlaut steht aber
    eindeutig in einem ANDEREN Beitrag. Genau so entstanden auf
    '/forum/pmsnew.php?mdl=topic&tid=64200' 24 von 31 Eintragungen, die auf
    den falschen Beitrag zeigten.
    """
    p = _pruefer()
    b = p.pruefe(3, "/s", _sel(2, "Kennwort1004"))
    assert b.position_vorhanden is True, \
        "Der Ausdruck MUSS auflosen - sonst prueft dieser Fall nicht, was " \
        "er behauptet"
    assert b.beitrag_anker == 1002
    assert b.urteil == AP.URTEIL_WIDERLEGT
    assert b.beitraege_wortlaut == [1004]
    assert b.beitrag is None, \
        "Aus einer widerlegten Lage darf KEINE Nummer herausfallen"
    assert "#1004" in b.bemerkung


# ---------------------------------------------------------------------------
# AP05 - mehrdeutiger Wortlaut
# ---------------------------------------------------------------------------

def test_ap05_mehrdeutiger_wortlaut_entscheidet_nichts():
    """
    Rot, sobald ein in mehreren Beitraegen vorkommender Wortlaut als Beleg
    durchgeht. Befund Build 752, Beleg #65: ein Wortlaut, der in 24 von 25
    Beitraegen steht, bestaetigt jeden davon und damit keinen.
    """
    p = _pruefer()
    # 'Gemeinsamer Satz.' steht in allen vier - und der Versatz zeigt
    # danebe, damit die Textprobe nicht schon vorher traegt.
    b = p.pruefe(4, "/s", _sel(1, "Gemeinsamer Satz.", von=5, bis=9))
    assert b.urteil == AP.URTEIL_UNKLAR
    assert len(b.beitraege_wortlaut) == 4
    assert b.beitrag is None


# ---------------------------------------------------------------------------
# AP06 - Wortlaut kommt gar nicht vor
# ---------------------------------------------------------------------------

def test_ap06_wortlaut_nirgends_ist_unklar_und_nicht_widerlegt():
    """
    Rot, wenn 'kommt nirgends vor' als 'WIDERLEGT' gemeldet wuerde. Das waere
    eine Aussage ueber den Ermittler, und sie ist nicht gedeckt: der Wortlaut
    kann ueber eine Beitragsgrenze hinweg markiert oder anders gefaltet
    worden sein.
    """
    p = _pruefer()
    b = p.pruefe(5, "/s", _sel(1, "Diesen Satz gibt es auf der Seite nicht"))
    assert b.urteil == AP.URTEIL_UNKLAR
    assert b.beitraege_wortlaut == []
    assert b.beitrag is None


# ---------------------------------------------------------------------------
# AP07 - Ausdruck bricht, Wortlaut rettet den Beitrag
# ---------------------------------------------------------------------------

def test_ap07_nur_wortlaut_wenn_der_ausdruck_bricht():
    """
    Rot, wenn ein gebrochener Ausdruck den Fall unrettbar machte. Der Beitrag
    steht dann ueber den Inhalt fest - schwaecher als BESTAETIGT, aber nicht
    nichts.
    """
    p = _pruefer()
    sel = json.dumps({
        "xpathStart": "./div[1]/div[3]/div[999]/p[1]/text()[1]",
        "xpathEnd": "./div[1]/div[3]/div[999]/p[1]/text()[1]",
        "offsetStart": 0, "offsetEnd": 12,
        "textContent": "Kennwort1001"})
    b = p.pruefe(6, "/s", sel)
    assert b.position_vorhanden is False
    assert b.urteil == AP.URTEIL_NUR_WORTLAUT
    assert b.beitrag == 1001


# ---------------------------------------------------------------------------
# AP08 - Versatz widersinnig und Versatz zu gross
# ---------------------------------------------------------------------------

def test_ap08_widersinniger_versatz_wird_benannt():
    """
    Rot, wenn 'offsetEnd < offsetStart' unbemerkt bliebe. Eine gueltige
    Browser-Auswahl kann das nicht erzeugt haben - es ist ein Befund ueber
    die SPEICHERUNG, und im Bestand kommt es vor (Belege 14 und 50 in
    evidence_1488). Wer es unter 'abweichend' mischt, verliert den Befund.
    """
    p = _pruefer()
    b = p.pruefe(7, "/s", _sel(1, "Kennwort1001", von=48, bis=12))
    assert b.textprobe == AP.TEXT_VERSATZ_WIDERSINNIG
    # Der Wortlaut ist trotzdem eindeutig - der Beitrag bleibt belegt.
    assert b.urteil == AP.URTEIL_BEITRAG_BELEGT

    b2 = p.pruefe(8, "/s", _sel(1, "Kennwort1001", von=0, bis=99999))
    assert b2.textprobe == AP.TEXT_VERSATZ_UNGUELTIG


# ---------------------------------------------------------------------------
# AP09 - keine Auswahl, Uebersetzungsmarke
# ---------------------------------------------------------------------------

def test_ap09_ohne_ausdruck_und_uebersetzung():
    """
    Rot, wenn eine Altmarke ohne Ausdruck als unpruefbar durchfiele, obwohl
    ihr Wortlaut eindeutig ist - im Bestand gibt es solche (1547111, Belege
    2 und 4). Und rot, wenn eine Uebersetzungsmarke gegen den Abzug geprueft
    wuerde: sie steht dort gar nicht.
    """
    p = _pruefer()
    ohne = json.dumps({"textContent": "Kennwort1002"})
    b = p.pruefe(9, "/s", ohne)
    assert b.urteil == AP.URTEIL_NUR_WORTLAUT
    assert b.beitrag == 1002

    ohne2 = json.dumps({"textContent": "Gemeinsamer Satz."})
    assert p.pruefe(10, "/s", ohne2).urteil == AP.URTEIL_UNPRUEFBAR

    uebers = json.dumps({"target": "translation", "postId": 1003,
                         "textContent": "egal"})
    b3 = p.pruefe(11, "/s", uebers)
    assert b3.urteil == AP.URTEIL_UNPRUEFBAR
    assert "Uebersetzung" in b3.bemerkung


# ---------------------------------------------------------------------------
# AP10 - der Gesamtlauf ueber echte Datenbanken
# ---------------------------------------------------------------------------

def _baue_bestand(verz):
    os.makedirs(os.path.join(verz, "evidence"), exist_ok=True)
    os.makedirs(os.path.join(verz, "forensic"), exist_ok=True)
    f = sqlite3.connect(os.path.join(verz, "forensic", "forensic_900.db"))
    f.execute("CREATE TABLE pages(id INTEGER PRIMARY KEY, url_canonical TEXT,"
              " html BLOB, title TEXT, fetched_at INTEGER, http_status "
              "INTEGER, scrape_context TEXT, method TEXT)")
    f.execute("CREATE TABLE page_aliases(url_raw TEXT PRIMARY KEY, "
              "page_id INTEGER)")
    f.execute("INSERT INTO pages VALUES(1,'/s',?, 't',1,200,'user','GET')",
              (_html(),))
    f.commit()
    f.close()
    e = sqlite3.connect(os.path.join(verz, "evidence", "evidence_900.db"))
    e.execute("CREATE TABLE annotations(id INTEGER PRIMARY KEY, page_url "
              "TEXT, element_id TEXT, category TEXT, text TEXT, ts INTEGER, "
              "investigator_id INTEGER, selection_json TEXT, tags_json TEXT, "
              "local_id TEXT, post_id INTEGER, created_by TEXT, deleted_at "
              "INTEGER, version_nr INTEGER, prev_id INTEGER, actual_uid "
              "INTEGER)")
    faelle = [
        (1, _sel(2, "Gemeinsamer Satz."), None),                # BESTAETIGT
        (2, _sel(3, "Kennwort1003", 0, 5), None),               # BEITRAG_BELEGT
        (3, _sel(2, "Kennwort1004"), None),                     # WIDERLEGT
        (4, _sel(1, "Gemeinsamer Satz.", 5, 9), None),          # UNKLAR
        (5, json.dumps({"textContent": "Kennwort1002"}), 9999),  # NUR_WORTLAUT
        (6, json.dumps({"target": "translation"}), None),       # UNPRUEFBAR
    ]
    for kennung, sel, post in faelle:
        e.execute("INSERT INTO annotations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,"
                  "?,?,?)",
                  (kennung, "/s", None, "k", "", 1, 1, sel, None, None, post,
                   "p", None, 1, None, None))
    e.commit()
    e.close()


def test_ap10_gesamtlauf_zaehlt_alle_sechs_lagen(tmp_path):
    """
    Rot, sobald eine Lage im Gesamtlauf verschwindet oder in eine andere
    faellt. Die Zaehlung ist das, was am Ende in den Vermerk kommt.
    """
    _baue_bestand(str(tmp_path))
    zeilen = []
    code = AV.lauf(str(tmp_path), [], zeilen.append)
    text = "\n".join(zeilen)
    for lage in ("BESTAETIGT", "BEITRAG_BELEGT", "WIDERLEGT", "UNKLAR",
                 "NUR_WORTLAUT", "UNPRUEFBAR"):
        assert lage in text, "Lage %s fehlt in der Ausgabe" % lage
    assert "GESAMT ueber 1 Bestaende - 6 Annotationen" in text
    # Der Widerspruch zu einer eingetragenen Nummer muss gemeldet werden.
    assert "WIDERSPRUCH: eingetragen ist #9999" in text
    assert code == AV.RUECK_OFFEN


def test_ap11_rueckgabewerte_und_leeres_verzeichnis(tmp_path):
    """
    Rot, wenn ein Abbruch als Erfolg zurueckkaeme. Der Rueckgabewert ist das,
    was ein Ablauf auswertet.
    """
    zeilen = []
    assert AV.lauf(str(tmp_path / "gibt_es_nicht"), [], zeilen.append) \
        == AV.RUECK_ABBRUCH
    os.makedirs(str(tmp_path / "leer" / "evidence"))
    assert AV.lauf(str(tmp_path / "leer"), [], zeilen.append) \
        == AV.RUECK_ABBRUCH


def test_ap12_verbindungen_sind_schreibgeschuetzt(tmp_path):
    """
    Rot, sobald jemand 'mode=ro' entfernt. Bei einem Werkzeug, das ein
    Beweismittel anfasst, soll die Pruefung nicht 'nicht schreiben', sondern
    nicht schreiben KOENNEN.
    """
    _baue_bestand(str(tmp_path))
    e = os.path.join(str(tmp_path), "evidence", "evidence_900.db")
    vorher = (os.path.getmtime(e), os.path.getsize(e))
    AV.lauf(str(tmp_path), [], lambda *_a: None)
    assert (os.path.getmtime(e), os.path.getsize(e)) == vorher
    con = AV._oeffne_ro(e)
    try:
        try:
            con.execute("UPDATE annotations SET category='x'")
            raise AssertionError("Die Verbindung ist NICHT schreibgeschuetzt")
        except sqlite3.OperationalError:
            pass
    finally:
        con.close()
