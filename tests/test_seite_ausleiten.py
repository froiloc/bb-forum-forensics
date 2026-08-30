# =============================================================================
# tests/test_seite_ausleiten.py
#
# Build 747: Das Werkzeug fuer die Gegenprobe im Browser.
#
# WARUM ES UEBERHAUPT IN DEN BESTAND GEHOERT
#
# Es hat am 31.08.2026 den Streit entschieden, an dem fuenf Builds
# gescheitert sind: der Anker ist richtig, der Abzug ist vollstaendig,
# falsch war die serverseitige Zerlegung. Damit ist die Gegenprobe im
# Browser das Verfahren, mit dem ein Zweifel an einem Anker kuenftig
# ausgeraeumt wird - und ein Verfahren, das in der Akte steht, gehoert in
# den Bestand und nicht auf einen Zuruf.
#
# AUFGEFALLEN IST DAS AN EINEM ROTEN WAECHTER: CK02 meldete
# 'seite_ausleiten.py OHNE Katalogeintrag', nachdem ich die Datei als
# Einzelwerkzeug ausserhalb der Lieferung uebergeben hatte und sie im
# Wurzelverzeichnis landete. Der Waechter hatte recht - ein Werkzeug, von
# dem niemand weiss, ist im Betrieb dasselbe wie keines, nur gefaehrlicher.
#
# SA01  ein gueltiger Beleg wird ausgeleitet, Rueckgabewert 0
# SA02  die Zieldatei traegt die Huelle des Ermittlungsfensters und den
#       Anker des Belegs - ohne beides waere sie zum Pruefen unbrauchbar
# SA03  der markierte WORTLAUT erscheint NICHT auf der Konsole, nur seine
#       Laenge - die Konsolenausgabe ist das, was weitergegeben wird
# SA04  GEGENPROBE zu SA03: der Wortlaut steht sehr wohl im Abzug (und in
#       der Zieldatei) - SA03 ist also nicht deshalb gruen, weil es ihn
#       gar nicht gibt
# SA05  unbekannter Beleg -> Klartext, Rueckgabewert 1, KEINE Datei
# SA06  fehlende Datenbank -> Klartext, Rueckgabewert 1
# SA07  beide Datenbanken werden NUR LESEND geoeffnet - belegt, nicht
#       behauptet
# SA08  der Warnhinweis auf den Beweismittelinhalt steht in der Ausgabe
#
# Beleg: tools/seite_ausleiten.py;
#        management/Befund_Ankerbruch_Browsergegenprobe_v1_0.md
# =============================================================================

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]

#: Der markierte Wortlaut. Er steht im Abzug und darf auf der KONSOLE nicht
#: auftauchen (SA03/SA04).
WORTLAUT = "Der Zug faehrt ab Hauptbahnhof"
ANKER = "./donate[1]/div[1]/div[4]/article[1]/p[1]/text()[1]"
URL = "/forum/viewtopic.php?id=31351"


def _werkzeug():
    """Ueber den Dateipfad laden: 'tools/' ist bewusst kein Paket."""
    spec = importlib.util.spec_from_file_location(
        "werkzeug_seite_ausleiten", str(WURZEL / "tools" / "seite_ausleiten.py"))
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _seite() -> bytes:
    return ("<html><head><title>t</title></head><body>"
            "<donate><div id=\"wrap\" class=\"wrap shadow\">"
            "<div id=\"brdleft\">L</div>"
            "<div id=\"page-header\"><h1>Forum</h1></div>"
            "<style>.x{color:red}</style>"
            "<div class=\"announce postmsg\">A</div>"
            "<div id=\"page-body\"><article class=\"post\" id=\"p721598\">"
            "<p>" + WORTLAUT + ".</p></article></div>"
            "<div id=\"page-footer\">F</div>"
            "</div></donate></body></html>").encode("utf-8")


def _bestand(tmp_path: Path):
    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    fo, ev = tmp_path / "forensic_1.db", tmp_path / "evidence_1.db"

    c = sqlite3.connect(fo)
    c.executescript(
        "CREATE TABLE pages (id INTEGER PRIMARY KEY, url_canonical TEXT,"
        " method TEXT, html BLOB);"
        "CREATE TABLE page_aliases (page_id INTEGER, url_raw TEXT);")
    c.execute("INSERT INTO pages (id,url_canonical,method,html) "
              "VALUES (1,?,'GET',?)", (URL, _seite()))
    c.commit(); c.close()

    c = sqlite3.connect(ev)
    c.execute("CREATE TABLE annotations (id INTEGER PRIMARY KEY, page_url TEXT,"
              " selection_json TEXT, post_id INTEGER, deleted_at TEXT)")
    sel = {"xpathStart": ANKER, "offsetStart": 0, "xpathEnd": ANKER,
           "offsetEnd": 7, "textContent": WORTLAUT}
    c.execute("INSERT INTO annotations (id,page_url,selection_json) "
              "VALUES (1,?,?)", (URL, json.dumps(sel, ensure_ascii=False)))
    c.commit(); c.close()
    return ev, fo


def test_SA01_ein_gueltiger_beleg_wird_ausgeleitet(tmp_path, capsys):
    ev, fo = _bestand(tmp_path)
    ziel = tmp_path / "sichtung" / "beleg_1.html"
    rc = _werkzeug().main(["--evidence", str(ev), "--forensic", str(fo),
                           "--beleg", "1", "--ziel", str(ziel)])
    assert rc == 0
    assert ziel.exists()


def test_SA02_die_zieldatei_ist_zum_pruefen_brauchbar(tmp_path, capsys):
    # OHNE DIE HUELLE '#forensic-viewport' waere der Bezugspunkt ein anderer
    # als beim Markieren, und der Anker traefe etwas anderes - die Datei
    # saehe richtig aus und waere es nicht.
    ev, fo = _bestand(tmp_path)
    ziel = tmp_path / "beleg_1.html"
    _werkzeug().main(["--evidence", str(ev), "--forensic", str(fo),
                      "--beleg", "1", "--ziel", str(ziel)])
    inhalt = ziel.read_text(encoding="utf-8")
    assert 'id="forensic-viewport"' in inhalt
    assert ANKER in inhalt, "der Anker des Belegs gehoert in die Pruefung"
    # Der <body>-Auszug, nicht das ganze Dokument - genau wie im
    # Auslieferungspfad.
    assert "<donate>" in inhalt
    assert "<title>t</title>" not in inhalt


def test_SA03_der_wortlaut_erscheint_nicht_auf_der_konsole(tmp_path, capsys):
    # DIE KONSOLENAUSGABE IST DAS, WAS WEITERGEGEBEN WIRD. Der Wortlaut
    # einer Markierung ist Beweismittelinhalt und hat dort nichts zu suchen.
    ev, fo = _bestand(tmp_path)
    _werkzeug().main(["--evidence", str(ev), "--forensic", str(fo),
                      "--beleg", "1", "--ziel", str(tmp_path / "b.html")])
    ausgabe = capsys.readouterr().out
    assert WORTLAUT not in ausgabe
    # Die LAENGE dagegen schon - sie sagt, ob ueberhaupt etwas markiert war.
    assert "Wortlaut" in ausgabe and "Zeichen" in ausgabe


def test_SA04_gegenprobe_der_wortlaut_steht_sehr_wohl_im_bestand(tmp_path):
    # OHNE DIESE PROBE waere SA03 auch dann gruen, wenn es den Wortlaut gar
    # nicht gaebe - und dann belegte er nichts.
    ev, fo = _bestand(tmp_path)
    ziel = tmp_path / "b.html"
    _werkzeug().main(["--evidence", str(ev), "--forensic", str(fo),
                      "--beleg", "1", "--ziel", str(ziel)])
    assert WORTLAUT in _seite().decode("utf-8")
    assert WORTLAUT in ziel.read_text(encoding="utf-8"), \
        "in der DATEI steht er - sie ist ja der Seitenabzug"


def test_SA05_unbekannter_beleg_legt_keine_datei_an(tmp_path, capsys):
    # EINE DATEI MIT BEWEISMITTELINHALT OHNE ANLASS waere genau eine zu viel.
    ev, fo = _bestand(tmp_path)
    ziel = tmp_path / "x.html"
    rc = _werkzeug().main(["--evidence", str(ev), "--forensic", str(fo),
                           "--beleg", "999", "--ziel", str(ziel)])
    assert rc == 1
    assert not ziel.exists()
    assert "gibt es" in capsys.readouterr().out


def test_SA06_fehlende_datenbank_gibt_klartext(tmp_path, capsys):
    ev, fo = _bestand(tmp_path)
    rc = _werkzeug().main(["--evidence", str(tmp_path / "gibtsnicht.db"),
                           "--forensic", str(fo), "--beleg", "1",
                           "--ziel", str(tmp_path / "x.html")])
    assert rc == 1
    assert "Datei fehlt" in capsys.readouterr().out


def test_SA07_beide_datenbanken_werden_nur_lesend_geoeffnet(tmp_path):
    # BELEGT, NICHT BEHAUPTET: ueber die geoeffnete Verbindung wird ein
    # Schreibversuch unternommen, und er MUSS scheitern.
    ev, fo = _bestand(tmp_path)
    con = _werkzeug()._oeffnen(ev, fo)
    try:
        with pytest.raises(sqlite3.OperationalError):
            con.execute("UPDATE annotations SET post_id = 1 WHERE id = 1")
        with pytest.raises(sqlite3.OperationalError):
            con.execute("UPDATE fdb.pages SET method = 'POST' WHERE id = 1")
    finally:
        con.close()


def test_SA08_der_warnhinweis_steht_in_der_ausgabe(tmp_path, capsys):
    # Die erzeugte Datei ist Beweismittelinhalt im Klartext. Wer sie
    # erzeugt, muss das lesen - und zwar in demselben Lauf.
    ev, fo = _bestand(tmp_path)
    _werkzeug().main(["--evidence", str(ev), "--forensic", str(fo),
                      "--beleg", "1", "--ziel", str(tmp_path / "b.html")])
    ausgabe = capsys.readouterr().out
    assert "BEWEISMITTELINHALT IM KLARTEXT" in ausgabe
    assert "loeschen" in ausgabe.lower()
    # Und der Herkunftsnachweis steht auch hier (Grundregel 8).
    assert "HERKUNFT DIESES LAUFS" in ausgabe
