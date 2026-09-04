# -*- coding: utf-8 -*-
# =============================================================================
# tests/test_anker_inventar.py
# Regressionstests zu management/maintenance/anker_inventar.py (Build 758)
# =============================================================================
# Die Vorrichtung bildet die Forenstruktur nach, NICHT eine erfundene:
#   PN-Seite  - include/pms_new/mdl/topic.php Z. 462 ff., mit der Signatur
#               'postsignature postmsg', die den Textausdruck in die Irre
#               fuehren wuerde, wenn er nicht exakt vergliche.
#   viewtopic - aeusserer <article id="p9001"> und innerer <div id="pp9001">
#               wie viewtopic0.php Z. 886 und Z. 975 (doppeltes 'p').
#   Systembeitrag - <article class="systempost"> mit Text in <td>, ohne
#               jedes 'postmsg', wie type4.php und viewtopic0.php Z. 354.
#
# Version: 0.8.758 - Build 758
# =============================================================================

from __future__ import annotations

import json
import os
import sqlite3
import sys

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WURZEL not in sys.path:
    sys.path.insert(0, WURZEL)

import pytest                                                  # noqa: E402
from management.maintenance import anker_inventar as AI         # noqa: E402

html5lib = pytest.importorskip("html5lib")

ANN = """CREATE TABLE annotations (id INTEGER PRIMARY KEY AUTOINCREMENT,
 page_url TEXT NOT NULL, element_id TEXT, category TEXT NOT NULL,
 text TEXT NOT NULL DEFAULT '', ts INTEGER NOT NULL, investigator_id INTEGER,
 selection_json TEXT, tags_json TEXT, local_id TEXT, post_id INTEGER,
 created_by TEXT NOT NULL DEFAULT '', deleted_at INTEGER,
 version_nr INTEGER NOT NULL DEFAULT 1, prev_id INTEGER, actual_uid INTEGER);"""
PAG = """CREATE TABLE pages (id INTEGER PRIMARY KEY AUTOINCREMENT,
 url_canonical TEXT NOT NULL, html BLOB, title TEXT, fetched_at INTEGER NOT NULL,
 http_status INTEGER NOT NULL, scrape_context TEXT NOT NULL DEFAULT 'user',
 method TEXT NOT NULL DEFAULT 'GET', UNIQUE(url_canonical, method));
CREATE TABLE page_aliases (url_raw TEXT PRIMARY KEY, page_id INTEGER NOT NULL);"""

U_PN = "/forum/pmsnew.php?mdl=topic&tid=64200"
U_VT = "/forum/viewtopic.php?id=145446"
PN = "./div[1]/div[3]/div[1]"
VT = "./div[1]/div[3]"
M = "/div[1]/div[1]/div[1]/div[2]/div[1]/p[1]/text()[1]"


def _pn_beitrag(pid, nr, autor, text):
    return ('<div id="p%d" class="blockpost roweven blockpost1">'
            '<h2><span><span class="conr">#%d</span> '
            '<a href="viewtopic.php?pid=%d#p%d">2026-05-01 12:00</a>'
            '</span></h2><div class="box"><div class="inbox">'
            '<div class="postbody"><div class="postleft"><dl><dt>'
            '<strong>%s</strong></dt><dd class="usertitle">'
            '<strong>Member</strong></dd></dl></div>'
            '<div class="postright"><div class="postmsg"><p>%s</p>'
            '<p>Zweiter Absatz von %s.</p></div>'
            '<div class="postsignature postmsg"><hr />Gruss %s</div>'
            '</div></div></div></div></div>'
            % (pid, nr, pid, pid, autor, text, autor, autor))


def _seiten():
    pn = ('<donate></donate><div id="wrap" class="wrap shadow">'
          '<div id="brdleft"></div><div id="page-header"><h1>Kopf</h1></div>'
          '<div id="page-body"><div class="blockpost"><h2>Thema</h2>'
          + _pn_beitrag(8801, 1, "alpha", "Erster Wortlaut zum Belegen.")
          + _pn_beitrag(8802, 2, "beta", "Zweiter Wortlaut, ganz anders.")
          + '</div></div><div id="page-footer"></div></div>')
    vt = ('<donate></donate><div id="wrap"><div id="brdleft"></div>'
          '<div id="page-header"></div><div id="page-body">'
          '<article class="post" id="p9001"><h2><span>'
          '<a href="viewtopic.php?pid=9001#p9001">2026-06-02 08:00</a>'
          '</span></h2><div class="box" id="pp9001"><div class="inbox">'
          '<div class="postbody"><div class="postleft"><dl><dt>'
          '<strong>gamma</strong></dt></dl></div><div class="postright">'
          '<div class="postmsg"><p>Inhalt im Artikel.</p></div>'
          '</div></div></div></div></article>'
          '<article class="systempost" id="p9002"><table><tr>'
          '<td>2026-06-03 09:00</td><td>Link als DEAD gemeldet.</td>'
          '</tr></table></article>'
          '</div><div id="page-footer"></div></div>')
    return pn, vt


def _sel(**kw):
    return json.dumps(kw)


def _bestand(tmp_path):
    ev, fo = tmp_path / "evidence", tmp_path / "forensic"
    ev.mkdir(); fo.mkdir()
    pn, vt = _seiten()
    con = sqlite3.connect(str(fo / "forensic_901.db"))
    con.executescript(PAG)
    for u, h, t in ((U_PN, pn, "PN"), (U_VT, vt, "Thema")):
        con.execute("INSERT INTO pages (url_canonical, html, title, "
                    "fetched_at, http_status, method) "
                    "VALUES (?,?,?,1756000000,200,'GET')",
                    (u, ("<html><body>%s</body></html>" % h).encode(), t))
    con.commit(); con.close()

    zeilen = [
        (U_PN, None, _sel(xpathStart=PN + "/div[1]" + M, offsetStart=0,
                          xpathEnd=PN + "/div[1]" + M, offsetEnd=12,
                          textContent="Erster Wortlaut"), None, None),
        (U_PN, None, _sel(xpathStart=PN + "/div[2]" + M, offsetStart=0,
                          xpathEnd=PN + "/div[2]" + M, offsetEnd=12,
                          textContent="Zweiter Wortlaut"), None, None),
        (U_PN, None, _sel(xpathStart=PN + "/div[99]/p[1]/text()[1]",
                          offsetStart=0, xpathEnd=PN + "/div[99]/p[1]",
                          offsetEnd=5, textContent="ganz anders"),
         None, None),
        (U_PN, None, _sel(xpathStart="./div[1]/div[2]/h1[1]/text()[1]",
                          offsetStart=0,
                          xpathEnd="./div[1]/div[2]/h1[1]/text()[1]",
                          offsetEnd=4, textContent="Kopf"), None, None),
        (U_VT, None, _sel(xpathStart=VT + "/article[1]" + M, offsetStart=0,
                          xpathEnd=VT + "/article[1]" + M, offsetEnd=6,
                          textContent="Inhalt im Artikel"), None, None),
        (U_VT, None, _sel(
            xpathStart=VT + "/article[2]/table[1]/tbody[1]/tr[1]/td[2]/text()[1]",
            offsetStart=0,
            xpathEnd=VT + "/article[2]/table[1]/tbody[1]/tr[1]/td[2]/text()[1]",
            offsetEnd=4, textContent="Link als DEAD"), None, None),
        (U_PN, "p8801", None, 8801, None),
        (U_PN, "p7777", None, 7777, None),
        (U_PN, None, _sel(xpathStart=PN, offsetStart=0, xpathEnd=PN,
                          offsetEnd=1, textContent="egal"), None, 1756000001),
    ]
    con = sqlite3.connect(str(ev / "evidence_901.db"))
    con.executescript(ANN)
    for url, eid, sj, pid, gel in zeilen:
        con.execute("INSERT INTO annotations (page_url, element_id, category, "
                    "text, ts, selection_json, post_id, deleted_at, "
                    "created_by) VALUES (?,?,'belastend','',1750000000,"
                    "?,?,?,'H0D0899')", (url, eid, sj, pid, gel))
    con.commit(); con.close()
    return str(ev), str(fo)


def _befund(tmp_path):
    ev, fo = _bestand(tmp_path)
    return AI.AnkerInventar("901", os.path.join(ev, "evidence_901.db"),
                            os.path.join(fo, "forensic_901.db")).erheben()


# ---------------------------------------------------------------------------

def test_ai01_doppeltes_p_wird_erkannt(tmp_path):
    """
    ROT, wenn 'pp9001' nicht als Beitragskennung gilt.

    viewtopic0.php Z. 975 schreibt 'id="p<?php echo \\'p\\'.$id;?>"' - das
    'p' einmal als Literal, einmal in der Ausgabe. Ein Zerleger mit
    '^p(\\d+)$' verloere diesen Zweig STILLSCHWEIGEND. Dieselbe Form
    benutzen bereits db/forensic_db.py und toolbar.js (_POST_KENNUNG).
    """
    assert AI.kennung_zerlegen("p123") == ("p", 123)
    assert AI.kennung_zerlegen("pp123") == ("pp", 123)
    assert AI.kennung_zerlegen("forum7") is None
    a = _befund(tmp_path).a_behaelter
    assert a["praefix"] == {"p": 4, "pp": 1}
    assert a["behaelter_gesamt"] == 5


def test_ai02_signatur_wird_nicht_fuer_den_beitragstext_gehalten(tmp_path):
    """
    ROT, wenn der Textausdruck die Signatur mittrifft.

    In pms_new/mdl/topic.php traegt die Signatur 'class="postsignature
    postmsg"'. Der Ausdruck aus der Weisung Alex vom 03.09.2026 vergleicht
    das Attribut EXAKT und trifft sie deshalb nicht;
    'contains(@class,"postmsg")' taete es. Beide PN-Beitraege der
    Vorrichtung tragen eine Signatur - der Zaehler MUSS null bleiben.
    """
    bb = _befund(tmp_path).b_anker
    assert bb["text_mehrfach"] == 0
    assert bb["text"]["postright_postmsg"] == 3


def test_ai03_systembeitrag_hat_keinen_postmsg(tmp_path):
    """
    ROT, wenn der Systembeitrag als 'kein Text gefunden' durchfaellt.

    type4.php enthaelt kein einziges 'postmsg'; viewtopic0.php Z. 354 gibt
    Systembeitraege als '<tr><td>Zeit</td><td>Text</td></tr>' aus. Bei
    27.346 Beitraegen mit posts.type=4 ist das keine Randerscheinung. Ein
    Werkzeug, das nur '.postmsg' kennt, faende dort NICHTS - und Etappe 2
    haette fuer diese Beitraege kein Textfeld.
    """
    bb = _befund(tmp_path).b_anker
    assert bb["text"]["tabellenzelle"] == 1
    assert bb["text"].get("(keiner)", 0) == 0
    # Verfasser und Zeitstempel fehlen dort - das MUSS gemeldet werden.
    assert bb["verfasser"]["(keiner)"] == 1
    assert bb["zeitstempel"]["(keiner)"] == 1


def test_ai04_aufloesung_bestimmt_die_post_id(tmp_path):
    """
    ROT, wenn ein aufgeloester Knoten nicht bis zum Behaelter zurueckgefuehrt
    wird. Das ist der Zweck des ganzen Werkzeugs.
    """
    c = _befund(tmp_path).c_aufloesung
    assert c["mit_ausdruck"] == 6
    assert c["aufgeloest"] == 5
    assert c["post_id_bestimmt"] == 4
    nach = {e["id"]: e["post_id"] for e in c["beispiele"]}
    assert nach == {1: 8801, 2: 8802, 5: 9001, 6: 9002}


def test_ai05_knoten_ausserhalb_eines_beitrags_wird_benannt(tmp_path):
    """
    ROT, wenn eine Markierung im Seitenkopf als Beitrag gezaehlt wird.

    Annotation 4 der Vorrichtung zeigt auf '<h1>Kopf</h1>' im
    '#page-header'. Der Ausdruck loest auf - aber darueber steht kein
    Beitragsbehaelter. Wer das nicht trennt, schriebe in Etappe 4 eine
    erfundene post_id in die Beweismitteldatenbank.
    """
    # Nur EINMAL erheben - _bestand() legt die Verzeichnisse an und wuerde
    # beim zweiten Aufruf ueber sich selbst stolpern.
    b = _befund(tmp_path)
    assert b.c_aufloesung["knoten_ohne_behaelter"] == 1
    lagen = {f["id"]: f["lage"] for f in b.d_wortlaut["faelle"]}
    assert lagen[4] == "knoten_ohne_behaelter"


def test_ai06_wortlaut_gegenprobe_bei_totem_ausdruck(tmp_path):
    """
    ROT, wenn ein toter Ausdruck ohne Gegenprobe verworfen wird.

    Annotation 3 traegt einen Ausdruck, der ins Leere zeigt ('div[99]').
    Ihr Wortlaut steht aber in genau EINEM Behaelter. Damit ist die
    Markierung inhaltlich einwandfrei und nur ihr Weg unbrauchbar - sie
    darf nicht als verloren gelten.
    """
    d = _befund(tmp_path).d_wortlaut
    assert d["wortlaut_eindeutig"] == 1
    fall = [f for f in d["faelle"] if f["id"] == 3][0]
    assert fall["lage"] == "ausdruck_ohne_knoten"
    assert fall["traeger"] == [8802]


def test_ai07_whole_post_wird_umgekehrt_geprueft(tmp_path):
    """
    ROT, wenn Variante 1 uebersprungen wird.

    'whole post' hat keinen Ausdruck, aber einen Ort. Die Pruefung laeuft
    umgekehrt: gibt es den Behaelter im Seiteninhalt ueberhaupt? Fehlt er,
    ist entweder der Seiteninhalt unvollstaendig oder die post_id falsch -
    beides muss der Ermittler erfahren.
    """
    c = _befund(tmp_path).c_aufloesung
    assert c["whole_post"] == 2
    assert c["whole_post_behaelter_da"] == 1
    fehlt = c["whole_post_behaelter_fehlt"]
    assert len(fehlt) == 1 and fehlt[0]["nummer"] == 7777


def test_ai08_geloeschte_zeilen_werden_nicht_mitgemessen(tmp_path):
    """
    ROT, wenn geloeschte oder ueberholte Zeilen in die Quote einfliessen.

    Zeile 9 der Vorrichtung traegt 'deleted_at'. Sie mitzuzaehlen
    verfaelschte jede Aussage darueber, wie gross Etappe 4 wird.
    """
    c = _befund(tmp_path).c_aufloesung
    assert c["mit_ausdruck"] + c["whole_post"] == 8      # nicht 9


def test_ai09_body_wird_wie_im_auslieferungspfad_ausgeschnitten():
    """
    ROT, wenn anders geschnitten wird als in blob_handler._extract_body().

    Der Browser bekommt genau diesen Ausschnitt in '#forensic-viewport'
    gesetzt, und die gespeicherten Ausdruecke sind relativ dazu. Wer hier
    anders schneidet, misst einen anderen Baum als den, in dem der
    Ermittler markiert hat.
    """
    assert AI.body_ausschneiden(b"<html><body><p>x</p></body></html>") \
        == "<p>x</p>"
    assert AI.body_ausschneiden(b'<html><body class="a"><p>x</p></body>') \
        == "<p>x</p>"
    # Ohne <body> bleibt alles stehen - nichts wird still verworfen.
    assert AI.body_ausschneiden(b"<p>x</p>") == "<p>x</p>"
    # DAS LETZTE '</body>' ZAEHLT, nicht das erste. Im Forum kommt die
    # Zeichenfolge im Inhalt vor - etwa in Beitraegen, die HTML zeigen.
    # Ein 'find' statt 'rfind' schnitte dort mitten im Inhalt ab und
    # verkuerzte die Seite lautlos; blob_handler._extract_body() benutzt
    # ebenfalls 'rfind'.
    roh = b"<html><body><p>zeigt &lt;/body&gt; und </body> im Text</p></body>"
    assert AI.body_ausschneiden(roh).endswith("im Text</p>")
    assert "</body>" in AI.body_ausschneiden(roh)


def test_ai10_verbindungen_sind_schreibgeschuetzt(tmp_path):
    """ROT, wenn 'mode=ro' entfaellt. Weisung: bis Etappe 4 nur lesen."""
    ev, _fo = _bestand(tmp_path)
    con = AI.AnkerInventar._ro(os.path.join(ev, "evidence_901.db"))
    try:
        with pytest.raises(sqlite3.OperationalError):
            con.execute("UPDATE annotations SET category='x'")
    finally:
        con.close()
