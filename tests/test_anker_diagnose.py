# =============================================================================
# tests/test_anker_diagnose.py
#
# Build 737: Das Diagnosewerkzeug fuer den Ankerbruch.
#
# WOZU EIN DIAGNOSEWERKZEUG UEBERHAUPT UNTER EINEN TEST GEHOERT
#
# Weil an seiner Ausgabe eine Entscheidung haengt. Sagt es "die Annaeherung
# heilt es", wird der Fix eingebaut; sagt es "sie aendert nichts", wird
# woanders gesucht. Ein Werkzeug, das die falsche Auskunft gibt, kostet nicht
# einen Lauf, sondern eine Richtung - und dieses Teilprojekt hat schon vier
# Builds an Fehlspuren verloren.
#
# AD01  ein Anker, der roh bricht und nach der Annaeherung traegt, wird als
#       genau das gemeldet
# AD02  GEGENPROBE: ein Bestand OHNE <noscript> meldet KEINE Heilung
# AD03  das Werkzeug oeffnet beide Datenbanken NUR LESEND - belegt, nicht
#       behauptet
# AD04  Uebersetzungsmarken werden uebersprungen (sie haben keinen XPath)
# AD05  fehlende Datei -> Klartext, Rueckgabewert 1, kein Absturz
# AD06  Leerbefund -> Rueckgabewert 0 (kein Fund ist kein Fehler)
# AD07  der Ebenenbericht NENNT die Elemente an der Bruchstelle
# AD08  --beleg schraenkt auf einen einzelnen Beleg ein
# AD09  die Ausgabe traegt KEINEN Beitragstext
# AD10  GEGENPROBE zu AD09: der Beitragstext steht sehr wohl im Abzug -
#       AD09 ist also nicht deshalb gruen, weil es ihn gar nicht gibt
# AD11  Build 739: das Fehlerprotokoll von libxml2 wird gelesen und
#       ausgegeben (M4)
# AD12  Build 739: ein heiler Abzug hat ein LEERES Fehlerprotokoll - ohne
#       diese Gegenprobe waere AD11 auch mit einem Werkzeug gruen, das
#       immer irgendetwas meldet
# AD14  Build 741: die KETTE nennt das Element, das verschluckt hat - der
#       Pfad allein sagt nur, WO etwas steht
# AD15  Build 741: die genannten Quelltextzeilen werden gezeigt, und zwar
#       VERDECKT - Geruest offen, Text und fremde Attributwerte zu
# AD13  Build 739: M5 unterscheidet VERSCHLUCKT (steht tiefer) von
#       WEGGELASSEN (steht im Quelltext, fehlt im Baum) - zwei verschiedene
#       Ursachen mit zwei verschiedenen Abhilfen
#
# Beleg: management/maintenance/anker_diagnose.py; tools/anker_diagnose.py;
#        report_render/html5_annaeherung.py.
# =============================================================================

import json
import sqlite3
from pathlib import Path

import pytest

from management.maintenance.anker_diagnose import AnkerDiagnose

#: Der markierte Wortlaut. Er steht im Abzug und darf in der Ausgabe des
#: Werkzeugs NICHT auftauchen (AD09/AD10).
WORTLAUT = "Der Zug faehrt ab Hauptbahnhof"

ANKER = "./donate[1]/div[1]/div[4]/article[1]/p[1]/text()[1]"


def _seite(kopf: str) -> bytes:
    return ("<html><head><title>t</title></head><body>"
            "<donate><div id=\"wrap\" class=\"wrap shadow\">"
            "<div id=\"brdleft\">L</div>"
            + kopf +
            "<style>.x{color:red}</style>"
            "<div class=\"announce postmsg\">A</div>"
            "<div id=\"page-body\"><article class=\"post\" id=\"p721598\">"
            "<p>" + WORTLAUT + ".</p></article></div>"
            "<div id=\"page-footer\">F</div>"
            "</div></donate></body></html>").encode("utf-8")


KOPF_MIT_NOSCRIPT = ('<div id="page-header"><h1>Forum</h1>'
                     '<noscript><div class="n">Bitte JavaScript</noscript></div>')
KOPF_SCHLICHT = '<div id="page-header"><h1>Forum</h1></div>'

URL = "/forum/viewtopic.php?id=31351"


def _bestand(tmp_path: Path, kopf: str, *, uebersetzung: bool = False):
    """Ein winziger, aber ECHTER Bestand: zwei SQLite-Dateien wie im Betrieb."""
    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    fo = tmp_path / "forensic_1.db"
    ev = tmp_path / "evidence_1.db"

    c = sqlite3.connect(fo)
    c.executescript(
        "CREATE TABLE pages (id INTEGER PRIMARY KEY, url_canonical TEXT,"
        " method TEXT, html BLOB);"
        "CREATE TABLE page_aliases (page_id INTEGER, url_raw TEXT);")
    c.execute("INSERT INTO pages (id,url_canonical,method,html) "
              "VALUES (1,?,'GET',?)", (URL, _seite(kopf)))
    c.commit()
    c.close()

    c = sqlite3.connect(ev)
    c.execute("CREATE TABLE annotations (id INTEGER PRIMARY KEY, page_url TEXT,"
              " selection_json TEXT, post_id INTEGER, deleted_at TEXT)")
    sel = {"xpathStart": ANKER, "offsetStart": 0, "xpathEnd": ANKER,
           "offsetEnd": 7, "textContent": WORTLAUT}
    c.execute("INSERT INTO annotations (id,page_url,selection_json) "
              "VALUES (1,?,?)", (URL, json.dumps(sel, ensure_ascii=False)))
    c.execute("INSERT INTO annotations (id,page_url,selection_json) "
              "VALUES (2,?,?)", (URL, json.dumps(sel, ensure_ascii=False)))
    if uebersetzung:
        c.execute(
            "INSERT INTO annotations (id,page_url,selection_json) "
            "VALUES (3,?,?)",
            (URL, json.dumps({"target": "translation", "postId": 1,
                              "charStart": 0, "charEnd": 5, "textLen": 9,
                              "textHash": "abc", "textContent": "xxxxx"})))
    c.commit()
    c.close()
    return ev, fo


# ---------------------------------------------------------------------------
def test_AD01_heilung_wird_als_solche_gemeldet(tmp_path):
    ev, fo = _bestand(tmp_path, KOPF_MIT_NOSCRIPT)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    z = befund.zaehlung()
    assert z["belege"] == 2
    assert z["lxml_traegt"] == 0, "roh darf hier NICHTS aufloesen"
    assert z["genaehert_traegt"] == 2
    assert z["entscheidend"] == 2
    assert all(b.entscheidend for b in befund.belege)


def test_AD02_gegenprobe_ohne_noscript_keine_heilung(tmp_path):
    # OHNE DIESE PROBE WAERE AD01 AUCH MIT EINEM WERKZEUG GRUEN, das jede
    # Zeile als geheilt meldet. Hier traegt der Anker schon roh - dann darf
    # nichts als 'nur nach Annaeherung' erscheinen.
    ev, fo = _bestand(tmp_path, KOPF_SCHLICHT)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    z = befund.zaehlung()
    assert z["lxml_traegt"] == 2
    assert z["entscheidend"] == 0
    assert not any(b.entscheidend for b in befund.belege)


def test_AD03_beide_datenbanken_werden_nur_lesend_geoeffnet(tmp_path):
    # BELEGT, NICHT BEHAUPTET: die Verbindung wird geholt und ein Schreiben
    # versucht. Es MUSS scheitern. Ein Werkzeug, das die
    # Beweismitteldatenbank schreibfaehig oeffnet, waere nach den
    # Wartungsstufen kein Stufe-C-Werkzeug mehr - und liefe damit unter
    # falscher Flagge.
    ev, fo = _bestand(tmp_path, KOPF_MIT_NOSCRIPT)
    d = AnkerDiagnose(evidence=ev, forensic=fo)
    con = d._oeffnen()
    try:
        with pytest.raises(sqlite3.OperationalError):
            con.execute("UPDATE annotations SET post_id = 99")
        with pytest.raises(sqlite3.OperationalError):
            con.execute("UPDATE fdb.pages SET method = 'POST'")
    finally:
        con.close()


def test_AD04_uebersetzungsmarken_werden_uebersprungen(tmp_path):
    # Sie verankern per Zeichenversatz im uebersetzten Text und haben gar
    # keinen XPath in den Abzug. Sie hier mitzuzaehlen verdruebe die Quote,
    # um derentwillen es das Werkzeug gibt.
    ev, fo = _bestand(tmp_path, KOPF_MIT_NOSCRIPT, uebersetzung=True)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    assert befund.zaehlung()["belege"] == 2
    assert {b.beleg_id for b in befund.belege} == {1, 2}


def test_AD05_fehlende_datei_gibt_klartext(tmp_path):
    from tools import anker_diagnose
    code = anker_diagnose.main(["--evidence", str(tmp_path / "gibtsnicht.db"),
                                "--forensic", str(tmp_path / "auchnicht.db")])
    assert code == 1


def test_AD06_leerbefund_ist_kein_fehler(tmp_path):
    # Kein Fund ist eine AUSKUNFT und kein Fehlschlag. Ein Rueckgabewert 1
    # liesse ein Skript daraus einen Abbruch machen.
    from tools import anker_diagnose
    ev, fo = _bestand(tmp_path, KOPF_SCHLICHT)
    con = sqlite3.connect(ev)
    con.execute("DELETE FROM annotations")
    con.commit()
    con.close()
    code = anker_diagnose.main(["--evidence", str(ev), "--forensic", str(fo)])
    assert code == 0


def test_AD07_der_ebenenbericht_nennt_die_elemente(tmp_path):
    # NICHT NUR ZAEHLEN, SONDERN BENENNEN. Die blosse Zahl ('roh 2,
    # angenaehert 5') laesst offen, WELCHE zwei Elemente der Abzug hat -
    # und genau das ist die Angabe, mit der sich der Abzug in einem
    # Handgriff gegen den Browser halten laesst.
    ev, fo = _bestand(tmp_path, KOPF_MIT_NOSCRIPT)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    text = "\n".join(z for s in befund.seiten for z in s.zeilen)
    assert "div#brdleft" in text and "div#page-header" in text
    assert "div#page-body" in text
    assert any(s.abweichung_ab for s in befund.seiten)
    assert any("noscript" in r for s in befund.seiten for r in [s.rohtext])


def test_AD08_beleg_schraenkt_ein(tmp_path):
    ev, fo = _bestand(tmp_path, KOPF_MIT_NOSCRIPT)
    befund = AnkerDiagnose(evidence=ev, forensic=fo, nur_beleg=2).lauf()
    assert [b.beleg_id for b in befund.belege] == [2]


def test_AD09_die_ausgabe_traegt_keinen_beitragstext(tmp_path, capsys):
    # Die Zusage 'die Ausgabe darf unveraendert weitergegeben werden' hat am
    # 29.08.2026 schon einmal nicht gehalten - die Sonde gab in einem Feld
    # einen Klarnamen aus. Deshalb steht sie hier unter einem Test und nicht
    # nur in einem Kommentar.
    from tools import anker_diagnose
    ev, fo = _bestand(tmp_path, KOPF_MIT_NOSCRIPT)
    anker_diagnose.main(["--evidence", str(ev), "--forensic", str(fo)])
    ausgabe = capsys.readouterr().out
    assert WORTLAUT not in ausgabe
    assert "Hauptbahnhof" not in ausgabe
    assert "Bitte JavaScript" not in ausgabe


def test_AD10_gegenprobe_der_text_steht_sehr_wohl_im_abzug(tmp_path):
    # OHNE DIESE PROBE WAERE AD09 AUCH GRUEN, wenn der Testbestand den Text
    # gar nicht enthielte - die Zusage waere dann nicht geprueft, sondern
    # nur nicht widerlegt.
    ev, fo = _bestand(tmp_path, KOPF_MIT_NOSCRIPT)
    con = sqlite3.connect(fo)
    roh = con.execute("SELECT html FROM pages").fetchone()[0]
    con.close()
    assert WORTLAUT.encode("utf-8") in roh
    assert b"Bitte JavaScript" in roh


# ---------------------------------------------------------------------------
# Build 739 - was libxml2 selbst zu sagen hat
# ---------------------------------------------------------------------------

def test_AD11_das_fehlerprotokoll_wird_gelesen(tmp_path):
    # DIE QUELLE, DIE SECHS BUILDS LANG UNGELESEN BLIEB. libxml2 fuehrt Buch
    # darueber, was ihm begegnet ist, und benennt die Ursache oft unmittelbar.
    ev, fo = _bestand(tmp_path, KOPF_MIT_NOSCRIPT)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    protokoll = " ".join(befund.seiten[0].fehlerprotokoll)
    assert "MISMATCH" in protokoll, protokoll
    assert "noscript" in protokoll


def test_AD12_gegenprobe_heiler_abzug_meldet_nichts(tmp_path):
    # Ohne diese Probe waere AD11 auch mit einem Werkzeug gruen, das immer
    # irgendetwas meldet - und dann waere jede Seite verdaechtig.
    ev, fo = _bestand(tmp_path, KOPF_SCHLICHT)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    protokoll = " ".join(befund.seiten[0].fehlerprotokoll)
    assert "leer" in protokoll
    assert "MISMATCH" not in protokoll


def test_AD13_verschluckt_und_weggelassen_sind_zu_unterscheiden(tmp_path):
    # DIE ENTSCHEIDENDE UNTERSCHEIDUNG. Beides sieht in der Kinderzahl gleich
    # aus und verlangt Verschiedenes: ein verschlucktes Element steht im Baum
    # an anderer Stelle und ist ueber einen berichtigten Pfad erreichbar; ein
    # weggelassenes ist gar nicht da, und dann hilft nur eine andere Zerlegung.
    ev, fo = _bestand(tmp_path, KOPF_MIT_NOSCRIPT)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    zeilen = "\n".join(befund.seiten[0].verortung)
    # VERSCHLUCKT: page-body steht im Baum, aber tiefer als erwartet.
    assert "#page-body" in zeilen
    assert "noscript" in zeilen, zeilen
    assert "FEHLT IM BAUM" not in zeilen

    # WEGGELASSEN: eine Schachtelung jenseits der Grenze von libxml2. Der
    # Zerleger bricht ab und laesst den Rest weg - eine Grenze, die ein
    # Browser nicht hat.
    tief = ('<div id="page-header">' + "<div>" * 300 + "x" + "</div>" * 300
            + "</div>")
    ev2, fo2 = _bestand(tmp_path / "tief", tief)
    befund2 = AnkerDiagnose(evidence=ev2, forensic=fo2).lauf()
    zeilen2 = "\n".join(befund2.seiten[0].verortung)
    assert "FEHLT IM BAUM" in zeilen2, zeilen2
    protokoll2 = " ".join(befund2.seiten[0].fehlerprotokoll)
    assert "Excessive depth" in protokoll2, protokoll2


# ---------------------------------------------------------------------------
# Build 741 - die Kette und die Quelltextzeilen
# ---------------------------------------------------------------------------

def test_AD14_die_kette_nennt_den_verschlucker(tmp_path):
    # DER PFAD SAGT, WO ETWAS STEHT ('div[2]/noscript[1]/div[3]'). Die KETTE
    # sagt, WER es aufgenommen hat - und erst damit ist die Stelle im
    # Quelltext wiederzufinden. Nach genau dieser Angabe wird gesucht, wenn
    # ein Element tiefer steht als erwartet.
    ev, fo = _bestand(tmp_path, KOPF_MIT_NOSCRIPT)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    zeilen = "\n".join(befund.seiten[0].verortung)
    assert "Kette:" in zeilen
    assert "div#page-header > noscript > div#page-body" in zeilen, zeilen


def test_AD15_die_quelltextzeilen_werden_verdeckt_gezeigt(tmp_path):
    # OHNE DIE ZEILE IST DIE MELDUNG EINE ZAHL. Mit ihr ist sie ein
    # Konstrukt, das man nachstellen und pruefen kann - und genau daran ist
    # der erste Anlauf gescheitert: sechs nachgestellte Konstrukte mit nicht
    # geschlossenem <li> verarbeitet libxml2 ALLE richtig; die Meldung
    # 'li and div' allein genuegt also nicht.
    ev, fo = _bestand(tmp_path, KOPF_MIT_NOSCRIPT)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    text = "\n".join(befund.seiten[0].quelltext)
    # Das Geruest ist offen - sonst waere die Zeile wertlos.
    assert 'id="page-header"' in text
    assert 'class="n"' in text
    assert "<noscript>" in text
    # Der TEXT ist zu. 'Bitte JavaScript' steht im Abzug (s. KOPF_MIT_NOSCRIPT)
    # und darf hier nicht erscheinen.
    assert "Bitte JavaScript" not in text
    assert "xxxxx" in text
    # Und die Verschiebung der Zeilenzaehlung wird BENANNT statt
    # stillschweigend hingenommen.
    assert "verschoben" in text


def test_AD16_gegenprobe_ohne_meldung_keine_zeilen(tmp_path):
    # Ein Werkzeug, das immer Quelltext zeigt, zeigt irgendwann Quelltext
    # ohne Anlass - und jede Zeile, die ohne Anlass erscheint, ist eine
    # Zeile zu viel in einer weitergebbaren Ausgabe.
    ev, fo = _bestand(tmp_path, KOPF_SCHLICHT)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    text = "\n".join(befund.seiten[0].quelltext)
    assert "Keine Fehlermeldung" in text
    assert "page-header" not in text
