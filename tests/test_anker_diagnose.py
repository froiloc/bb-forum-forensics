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
#        report_render/html5_zerleger.py.
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


# ---------------------------------------------------------------------------
# Build 744 - M7: wo stehen die Elemente, die der gebrochene Schritt verlangt?
#
# DER ANLASS. Nach dem Fix aus Build 742 loesten 25 von 27 Ankern auf. Bei
# den zwei uebrigen sagt die Bruchmeldung: der Anker verlangt den 29.
# <article>, an der Stelle stehen 2 - und die ganze Seite traegt 500. Die
# Elemente SIND also da. Damit bleiben zwei Lagen uebrig, die Verschiedenes
# verlangen: sie stehen INEINANDER (eine zweite Kaskade der Zerlegung, hier
# zu beheben) oder NEBENEINANDER an anderer Stelle (ein anderer Abzug als
# der gesehene, nicht durch Code zu heilen).
#
# EINE ZAHL UNTERSCHEIDET SIE: wie viele stehen in einem gleichnamigen
# Element? Bei der Kaskade fast alle, sonst keines. Genau diese Zahl misst
# M7 - und diese Tests halten sie fest, damit sie nicht irgendwann
# stillschweigend etwas anderes zaehlt.
#
# AD17  Kaskade -> M7 nennt die Zahl der verschachtelten und die Tiefe
# AD18  GEGENPROBE: Geschwister anderswo -> M7 sagt ausdruecklich, dass
#       KEINES verschachtelt ist. Ohne diese Probe waere AD17 auch mit
#       einem Werkzeug gruen, das immer "Kaskade" meldet
# AD19  ohne Bruch KEINE Verteilung - eine Messung ohne Anlass ist Ballast
#       in einer weitergebbaren Ausgabe
# AD20  die Verteilung traegt KEINEN Beitragstext
# AD21  eine lange Kette wird gekuerzt, aber MIT der Zahl der ausgelassenen
#       Glieder - die Laenge der Kette ist hier der Messwert
# ---------------------------------------------------------------------------

#: Der Anker verlangt den 29. <article> unter '#page-body'. In beiden
#: Bestaenden unten steht dort genau EINER - der Anker bricht also, und M7
#: hat einen Anlass.
ANKER_ARTIKEL = "./donate[1]/div[1]/div[4]/article[29]/p[1]/text()[1]"


def _seite_artikel(koerper: str) -> bytes:
    """Dieselbe Seitenhuelle wie _seite, aber mit frei setzbarem #page-body."""
    return ("<html><head><title>t</title></head><body>"
            "<donate><div id=\"wrap\" class=\"wrap shadow\">"
            "<div id=\"brdleft\">L</div>"
            + KOPF_SCHLICHT +
            "<div class=\"announce postmsg\">A</div>"
            "<div id=\"page-body\">" + koerper + "</div>"
            "<div id=\"page-footer\">F</div>"
            "</div></donate></body></html>").encode("utf-8")


def _kaskade(tiefe: int = 12) -> str:
    """<article> in <article> in <article> - die Lage (a)."""
    innen = "<p>" + WORTLAUT + ".</p>"
    text = innen
    for i in range(tiefe, 0, -1):
        text = '<article class="post" id="p%d">%s</article>' % (100 + i, text)
    return text


def _verstreut(anzahl: int = 12) -> str:
    """Lauter Geschwister - aber unter einem eigenen Kasten je Stueck."""
    stuecke = ['<article class="post" id="p100"><p>%s.</p></article>'
               % WORTLAUT]
    for i in range(1, anzahl):
        stuecke.append('<div class="kasten"><article class="post" id="p%d">'
                       '<p>%s.</p></article></div>' % (100 + i, WORTLAUT))
    return "".join(stuecke)


def _bestand_artikel(tmp_path: Path, koerper: str, *, anker: str):
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
              "VALUES (1,?,'GET',?)", (URL, _seite_artikel(koerper)))
    c.commit()
    c.close()

    c = sqlite3.connect(ev)
    c.execute("CREATE TABLE annotations (id INTEGER PRIMARY KEY, page_url TEXT,"
              " selection_json TEXT, post_id INTEGER, deleted_at TEXT)")
    sel = {"xpathStart": anker, "offsetStart": 0, "xpathEnd": anker,
           "offsetEnd": 7, "textContent": WORTLAUT}
    c.execute("INSERT INTO annotations (id,page_url,selection_json) "
              "VALUES (1,?,?)", (URL, json.dumps(sel, ensure_ascii=False)))
    c.commit()
    c.close()
    return ev, fo


def test_AD17_kaskade_wird_als_kaskade_benannt(tmp_path):
    ev, fo = _bestand_artikel(tmp_path, _kaskade(12), anker=ANKER_ARTIKEL)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    s = befund.seiten[0]
    assert s.verteilung_marke == "article", s.verteilung_marke
    text = "\n".join(s.verteilung_genaehert)
    # Zwoelf <article>, davon elf in einem anderen - der zwoelfte ist der
    # aeusserste. Die tiefste Schachtelung ist damit 11.
    assert "<article>: 12 im Baum" in text, text
    assert "11 von 12 stehen INNERHALB" in text, text
    assert "tiefste Schachtelung: 11" in text, text
    assert "Die Schachtelung stammt also aus der Zerlegung" in text, text
    # Die Begruendung stuetzt sich auf die VORLAGE DIESES FORUMS und nicht
    # auf HTML5 - der Standard erlaubt <article> in <article> ausdruecklich.
    assert "Vorlage dieses Forums" in text, text


def test_AD18_gegenprobe_geschwister_sind_keine_kaskade(tmp_path):
    # OHNE DIESE PROBE waere AD17 auch mit einem Werkzeug gruen, das bei
    # jedem Bruch "Kaskade" meldet. Genau dieser Kurzschluss hat dieses
    # Teilprojekt vier Builds gekostet.
    ev, fo = _bestand_artikel(tmp_path, _verstreut(12), anker=ANKER_ARTIKEL)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    text = "\n".join(befund.seiten[0].verteilung_genaehert)
    assert "<article>: 12 im Baum" in text, text
    assert "KEINES steht innerhalb" in text, text
    assert "INNERHALB eines anderen" not in text, text
    assert "Eine Kaskade scheidet damit aus" in text, text
    # Und die Gruppierung sagt, WO sie stattdessen stehen: einer unmittelbar
    # unter #page-body, elf je unter einem eigenen div.kasten.
    assert "verteilt auf 2 Vorfahrenkette(n)" in text, text
    assert "div.kasten" in text, text


def test_AD19_ohne_bruch_keine_verteilung(tmp_path):
    # Eine Messung ohne Anlass ist Ballast - und in einer Ausgabe, die an
    # die StA weitergegeben werden kann, ist jede Zeile ohne Anlass eine
    # Zeile zu viel.
    ev, fo = _bestand(tmp_path, KOPF_SCHLICHT)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    s = befund.seiten[0]
    assert s.verteilung_marke == ""
    assert s.verteilung_roh == []
    assert s.verteilung_genaehert == []


def test_AD20_die_verteilung_traegt_keinen_beitragstext(tmp_path):
    ev, fo = _bestand_artikel(tmp_path, _kaskade(12), anker=ANKER_ARTIKEL)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    text = "\n".join(befund.seiten[0].verteilung_roh
                     + befund.seiten[0].verteilung_genaehert)
    assert WORTLAUT not in text, text
    # Gegenprobe: der Wortlaut steht sehr wohl im Abzug - der Test ist also
    # nicht deshalb gruen, weil es ihn gar nicht gibt.
    assert WORTLAUT in _seite_artikel(_kaskade(12)).decode("utf-8")


def test_AD21_lange_ketten_werden_mit_zahl_gekuerzt(tmp_path):
    # Bei einer Kaskade wird die Vorfahrenkette so lang wie die Kaskade
    # tief ist. Gekuerzt werden darf sie nur dort, wo auch gesagt wird, WIE
    # VIEL weggelassen wurde: die Laenge der Kette IST hier der Befund.
    ev, fo = _bestand_artikel(tmp_path, _kaskade(12), anker=ANKER_ARTIKEL)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    text = "\n".join(befund.seiten[0].verteilung_genaehert)
    assert "Glieder) ..." in text, text
    # Und die Tiefe des ganzen Baums steht dabei - sie sagt, ob libxml2 an
    # seine Grenze (256) gekommen ist und den Rest weggelassen hat.
    assert "groesste Schachtelungstiefe im ganzen Baum:" in text, text


# ---------------------------------------------------------------------------
# Build 747 - M8 IST GESTRICHEN, und das gehoert festgehalten
#
# M8 zeigte, an welcher Quelltextzeile der handgebaute Teilnachbau der
# HTML5-Regeln ein Endtag nachgezogen und dabei ein Geruestelement
# mitgeschlossen hat. Es hat genau das geleistet, wofuer es gebaut wurde: es
# hat den Fehler IM WERKZEUG gefunden ('</div> hat article#p151.post
# mitgeschlossen'). Mit dem Teilnachbau ist auch der Mechanismus fort -
# html5lib zieht keine Endtags in den Text ein. Die frueheren AD22 und AD23
# sind deshalb ersatzlos entfallen; eine Rubrik, die ueber ein nicht mehr
# vorhandenes Verfahren berichtet, kann nur leer bleiben, und eine leere
# Rubrik wird gelesen, als sei dort nichts gewesen.
# ---------------------------------------------------------------------------

def test_AD24_bei_div_wird_die_schachtelung_nicht_als_befund_ausgelegt(tmp_path):
    # BUILD 746 - EINE BEHAUPTUNG OHNE BELEG, die mir selbst unterlaufen
    # ist: die Ausgabe schrieb 'ein <div> gehoert nicht in ein <div>'. DAS
    # IST FALSCH - ein <div> in einem <div> ist voellig gewoehnlich. Die
    # Zahl ist dort BESCHREIBEND und kein Vorwurf, und genau das muss sie
    # auch sagen.
    ev, fo = _bestand(tmp_path, KOPF_MIT_NOSCRIPT)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    s = befund.seiten[0]
    assert s.verteilung_marke == "div", s.verteilung_marke
    text = "\n".join(s.verteilung_roh)
    assert "gehoert nicht in ein" not in text, text
    assert "gewoehnlich und fuer sich KEIN Befund" in text, text


def test_AD25_gegenprobe_bei_article_wird_sie_sehr_wohl_ausgelegt(tmp_path):
    # OHNE DIESE PROBE waere AD24 auch mit einer Fassung gruen, die
    # ueberhaupt keine Auslegung mehr gibt - und dann waere die Angabe,
    # um derentwillen M7 gebaut wurde, wieder eine blosse Zahl.
    ev, fo = _bestand_artikel(tmp_path, _kaskade(12), anker=ANKER_ARTIKEL)
    befund = AnkerDiagnose(evidence=ev, forensic=fo).lauf()
    text = "\n".join(befund.seiten[0].verteilung_genaehert)
    assert "Vorlage dieses Forums" in text, text
    assert "gewoehnlich und fuer sich KEIN Befund" not in text, text


# =============================================================================
# BUILD 763 - DER POST-BEZUG UND DIE FALLZUORDNUNG
# =============================================================================
# AD22 und AD23 sind in der Reihe frei geblieben und werden NICHT
# nachbelegt - eine Kennung, die spaeter etwas anderes bezeichnet als beim
# ersten Lesen, macht jeden Verweis darauf unbrauchbar. Die neuen Waechter
# beginnen deshalb bei AD26.
#
# AD26  BEIDE Ausdruecke werden gemessen, nicht nur 'xpathStart'
# AD27  GEGENPROBE zu AD26: bricht NUR der zweite, faellt der Fall auf 0 -
#       ohne die zweite Messung waere er faelschlich bestimmbar
# AD28  der Aufstieg zaehlt 'pN' und 'ppN' als EINEN Beitrag, nicht als zwei
# AD29  ein Knoten oberhalb der Beitragsebene liefert KEINE post_id
# AD30  GEGENPROBE zu AD29: ein Knoten ausserhalb liefert auch keine
#       container unter sich - sonst waere AD29 auch mit einer Fassung gruen,
#       die immer 'oberhalb' meldet
# AD31  die Seitenart schaltet die Erkennung NICHT ab; der Widerspruch wird
#       benannt (Grundregel 1)
# AD32  die Faelle 1 bis 6 werden an gebauten Lagen richtig zugeordnet
# AD33  verschachtelte container mit VERSCHIEDENEN Nummern werden gemeldet,
#       mit gleicher Nummer nicht
# AD34  --uid schraenkt ein, ohne --uid laufen alle Bestaende, und die
#       JSON-Ausgabe ist gueltiges JSON
# =============================================================================

from management.maintenance.anker_postbezug import (          # noqa: E402
    ZUSTAND_AUSSERHALB, ZUSTAND_IM_POST, ZUSTAND_OBERHALB, seitenklasse)

#: Ein Knoten im page-header - vor allen Beitraegen.
VOR = "./div[1]/div[1]/h1[1]/text()[1]"
#: Ein Knoten im page-footer - nach allen Beitraegen.
NACH = "./div[1]/div[3]/text()[1]"


def _in_post(platz: int) -> str:
    """Ein Ausdruck, der IN den Beitrag an dieser Stelle zeigt."""
    return "./div[1]/div[2]/article[%d]/div[1]/p[1]/text()[1]" % platz


def _seite_mit_posts(nummern, doppelte_kennung: bool = True,
                     schachtel: bool = False) -> bytes:
    """
    Ein Abzug mit so vielen Beitraegen, wie Nummern genannt sind.

    'doppelte_kennung' bildet die Vollansicht nach: aussen
    '<article id="pN">', darin '<div class="box" id="ppN">' - beide mit
    DERSELBEN Nummer (viewtopic0.php Z. 886/975/1212).

    'schachtel' legt den ZWEITEN Beitrag in den ersten. Das bildet nach, was
    verschraenkt geschlossener BB-Code erzeugen kann: verschachtelte
    container mit VERSCHIEDENEN Nummern.
    """
    def einer(n):
        innen = ('<div class="box" id="pp%d"><p>Text von Beitrag %d</p></div>'
                 % (n, n)) if doppelte_kennung else \
                ('<div class="box"><p>Text von Beitrag %d</p></div>' % n)
        return '<article class="post" id="p%d">%s</article>' % (n, innen)

    if schachtel and len(nummern) >= 2:
        aussen = nummern[0]
        inneres = "".join(einer(n) for n in nummern[1:])
        posts = ('<article class="post" id="p%d">'
                 '<div class="box" id="pp%d"><p>Text von Beitrag %d</p>%s'
                 '</div></article>' % (aussen, aussen, aussen, inneres))
    else:
        posts = "".join(einer(n) for n in nummern)

    return ("<html><head><title>t</title></head><body>"
            "<div id=\"wrap\"><div id=\"page-header\"><h1>Forum</h1></div>"
            "<div id=\"page-body\">" + posts + "</div>"
            "<div id=\"page-footer\">F</div></div></body></html>").encode(
                "utf-8")


def _bau(tmp_path, seiten, markierungen, uid: str = "9"):
    """
    Ein Bestand aus mehreren Seiten und Markierungen.

    'seiten'       : {url: bytes}
    'markierungen' : [(id, url, xpathStart, xpathEnd)] - xpathEnd darf None
                     sein; dann fehlt 'xpathEnd' im selection_json.
    Rueckgabe: (evidence_verzeichnis, forensic_verzeichnis)
    """
    tmp_path = Path(tmp_path)
    ev_dir = tmp_path / "evidence"
    fo_dir = tmp_path / "forensic"
    ev_dir.mkdir(parents=True, exist_ok=True)
    fo_dir.mkdir(parents=True, exist_ok=True)

    c = sqlite3.connect(fo_dir / ("forensic_%s.db" % uid))
    c.executescript(
        "CREATE TABLE pages (id INTEGER PRIMARY KEY, url_canonical TEXT,"
        " method TEXT, html BLOB);"
        "CREATE TABLE page_aliases (page_id INTEGER, url_raw TEXT);")
    for nr, (url, roh) in enumerate(seiten.items(), 1):
        c.execute("INSERT INTO pages (id,url_canonical,method,html) "
                  "VALUES (?,?,'GET',?)", (nr, url, roh))
    c.commit()
    c.close()

    c = sqlite3.connect(ev_dir / ("evidence_%s.db" % uid))
    c.execute("CREATE TABLE annotations (id INTEGER PRIMARY KEY,"
              " page_url TEXT, selection_json TEXT, post_id INTEGER,"
              " deleted_at TEXT)")
    for kennung, url, anfang, ende in markierungen:
        sel = {"xpathStart": anfang, "offsetStart": 0, "offsetEnd": 4,
               "textContent": "Text"}
        if ende is not None:
            sel["xpathEnd"] = ende
        c.execute("INSERT INTO annotations (id,page_url,selection_json) "
                  "VALUES (?,?,?)", (kennung, url, json.dumps(sel)))
    c.commit()
    c.close()
    return ev_dir, fo_dir


def _lauf(tmp_path, seiten, markierungen, uid: str = "9"):
    """Ein Lauf ueber einen gebauten Bestand. Gibt den Laufbefund zurueck."""
    ev_dir, fo_dir = _bau(tmp_path, seiten, markierungen, uid=uid)
    d = AnkerDiagnose(evidence=ev_dir / ("evidence_%s.db" % uid),
                      forensic=fo_dir / ("forensic_%s.db" % uid))
    return d.lauf(grenze=0)


URL_T = "/forum/viewtopic.php?id=1"


# ---------------------------------------------------------------------------
def test_AD26_beide_ausdruecke_werden_gemessen(tmp_path):
    """
    Bis Build 762 sah das Werkzeug nur 'xpathStart' an. Rot, sobald der
    zweite Ausdruck wieder unter den Tisch faellt.
    """
    befund = _lauf(tmp_path, {URL_T: _seite_mit_posts([100, 101])},
                   [(1, URL_T, _in_post(1), _in_post(2))])
    b = befund.belege[0]
    assert b.anker_end == _in_post(2), b.anker_end
    assert b.zweite_end is not None
    assert b.zweite_end.position_vorhanden is True
    assert b.bezug_end is not None
    assert b.bezug_end.post_id == 101, b.bezug_end


def test_AD27_gegenprobe_bricht_nur_der_zweite_ist_der_fall_unbestimmt(
        tmp_path):
    """
    OHNE DIESE PROBE waere AD26 auch mit einer Fassung gruen, die den
    zweiten Ausdruck zwar liest, sein Ergebnis aber nicht auswertet: der
    Fall stuende dann allein auf dem ersten Endpunkt.

    Und sie haelt zugleich die Festlegung fest, dass aus einem GEBROCHENEN
    Ausdruck KEIN Fall abgeleitet wird - der ueberlebende Prefix sagt etwas
    ueber sich aus, nicht ueber die Lage der Markierung (Rueckbau Block C,
    Build 762).
    """
    kaputt = "./div[1]/div[2]/article[99]/p[1]/text()[1]"
    befund = _lauf(tmp_path, {URL_T: _seite_mit_posts([100, 101])},
                   [(1, URL_T, _in_post(1), kaputt)])
    b = befund.belege[0]
    assert b.zweite.position_vorhanden is True, "der ERSTE traegt"
    assert b.zweite_end.position_vorhanden is False, "der ZWEITE bricht"
    assert b.fall == 0, b.fall
    assert b.fall_typ == "", b.fall_typ
    assert "xpathEnd" in b.fall_grund, b.fall_grund


def test_AD28_aussen_p_und_innen_pp_sind_EIN_beitrag(tmp_path):
    """
    'p<n>' aussen und 'pp<n>' innen tragen DIESELBE Nummer und gehoeren zu
    demselben Beitrag (viewtopic0.php Z. 886/975/1212). Rot, sobald der
    Aufstieg oder die Aufzaehlung sie als zwei zaehlt.
    """
    befund = _lauf(tmp_path, {URL_T: _seite_mit_posts([100])},
                   [(1, URL_T, _in_post(1), _in_post(1))])
    b = befund.belege[0]
    assert b.bezug_start.post_id == 100, b.bezug_start
    assert b.bezug_start.zustand == ZUSTAND_IM_POST
    assert befund.seiten[0].container_zahl == 1, "EIN Beitrag, nicht zwei"
    assert befund.seiten[0].verschachtelungen == [], \
        "gleiche Nummer ist der Regelfall und KEIN Befund"


def test_AD29_oberhalb_der_beitragsebene_gibt_es_keine_post_id(tmp_path):
    """
    Bricht der Ausdruck frueh, ueberlebt ein hoher Prefix. Unter ihm liegen
    ALLE Beitraege der Seite - eine einzelne Nummer daraus zu waehlen waere
    geraten. Rot, sobald das Werkzeug es doch tut.
    """
    kaputt = "./div[1]/div[2]/article[99]/p[1]/text()[1]"
    befund = _lauf(tmp_path, {URL_T: _seite_mit_posts([100, 101, 102])},
                   [(1, URL_T, kaputt, kaputt)])
    b = befund.belege[0]
    assert b.bezug_start.zustand == ZUSTAND_OBERHALB, b.bezug_start
    assert b.bezug_start.post_id is None, b.bezug_start
    assert b.bezug_start.nachkommen_zahl == 3, b.bezug_start
    assert b.bezug_start.erste_nummer == 100
    assert b.bezug_start.letzte_nummer == 102


def test_AD30_gegenprobe_ausserhalb_meldet_keine_container(tmp_path):
    """
    OHNE DIESE PROBE waere AD29 auch mit einer Fassung gruen, die IMMER
    'oberhalb' meldet. Ein Knoten im page-footer hat keine Beitraege unter
    sich und keinen ueber sich.
    """
    befund = _lauf(tmp_path, {URL_T: _seite_mit_posts([100, 101, 102])},
                   [(1, URL_T, NACH, NACH)])
    b = befund.belege[0]
    assert b.bezug_start.zustand == ZUSTAND_AUSSERHALB, b.bezug_start
    assert b.bezug_start.nachkommen_zahl == 0, b.bezug_start
    assert b.bezug_start.post_id is None


def test_AD31_die_seitenart_schaltet_die_erkennung_nicht_ab(tmp_path):
    """
    DIE ENTSCHEIDENDE PROBE ZUR SEITENART. '/forum/search.php' gilt als
    beitragsfrei. Wuerde die Erkennung anhand der Adresse UEBERSPRUNGEN,
    bliebe ein Abzug, der doch Beitraege traegt, unbemerkt - ein stiller
    Sprung (Grundregel 1). Gemessen wird trotzdem, und der Widerspruch wird
    benannt.
    """
    url = "/forum/search.php?action=show"
    befund = _lauf(tmp_path, {url: _seite_mit_posts([400])},
                   [(1, url, VOR, NACH)])
    s = befund.seiten[0]
    assert s.seitenklasse == "search", s.seitenklasse
    assert s.container_zahl == 1, "die Erkennung ist GELAUFEN"
    assert "beitragsfrei" in s.widerspruch, s.widerspruch
    assert befund.belege[0].fall == 4, befund.belege[0].fall


def test_AD32_die_faelle_eins_bis_sechs(tmp_path):
    """
    Die Fallzuordnung an gebauten Lagen. Sie ist die Grundlage der
    Entscheidung 'text range' gegen 'whole post' und damit die Zahl, auf die
    Etappe 4 aufsetzt.
    """
    zwei = "/forum/viewtopic.php?id=2"      # zwei Beitraege
    eins = "/forum/viewtopic.php?id=3"      # ein Beitrag
    drei = "/forum/viewtopic.php?id=4"      # drei Beitraege
    seiten = {
        zwei: _seite_mit_posts([200, 201]),
        eins: _seite_mit_posts([300]),
        drei: _seite_mit_posts([500, 501, 502]),
    }
    markierungen = [
        (1, zwei, _in_post(1), _in_post(1)),   # Fall 1
        (2, zwei, VOR, _in_post(1)),           # Fall 2
        (3, zwei, _in_post(2), NACH),          # Fall 3
        (4, eins, VOR, NACH),                  # Fall 4
        (5, eins, VOR, VOR),                   # Fall 5
        (6, drei, _in_post(1), _in_post(3)),   # Fall 6
    ]
    befund = _lauf(tmp_path, seiten, markierungen)
    nach_id = {b.beleg_id: b for b in befund.belege}
    erwartet = {1: (1, "text range", [200]),
                2: (2, "whole post", [200]),
                3: (3, "whole post", [201]),
                4: (4, "whole post", [300]),
                5: (5, "text range", []),
                6: (6, "whole post", [500, 501, 502])}
    for kennung, (fall, typ, posts) in erwartet.items():
        b = nach_id[kennung]
        assert b.fall == fall, (kennung, b.fall, b.fall_grund)
        assert b.fall_typ == typ, (kennung, b.fall_typ)
        assert b.fall_posts == posts, (kennung, b.fall_posts)
    # Fall 6 nennt den eingeschlossenen Beitrag ausdruecklich - ohne ihn
    # waere die Spanne eine blosse Behauptung.
    assert nach_id[6].spanne.posts_dazwischen == [501], \
        nach_id[6].spanne


def test_AD33_verschachtelte_container_mit_verschiedenen_nummern(tmp_path):
    """
    DER FALL, DEN VERSCHRAENKTER BB-CODE ERZEUGEN KANN. Er ist am Markup
    daran zu erkennen, dass die verschachtelten container VERSCHIEDENE
    Nummern tragen - im Unterschied zum Regelfall 'p<n>' / 'pp<n>'.
    """
    url = "/forum/viewtopic.php?id=7"
    befund = _lauf(tmp_path,
                   {url: _seite_mit_posts([600, 601], schachtel=True)},
                   [(1, url, VOR, NACH)])
    s = befund.seiten[0]
    paare = [(v.aussen, v.innen) for v in s.verschachtelungen]
    assert (600, 601) in paare, paare
    # GEGENPROBE IN DERSELBEN PROBE: das Paar (600, 600) - aussen 'p600',
    # innen 'pp600' - darf NICHT erscheinen.
    assert all(a != i for a, i in paare), paare


def test_AD34_uid_schraenkt_ein_und_die_json_ausgabe_ist_gueltig(
        tmp_path, capsys):
    """
    Der Verzeichnisbetrieb: ohne --uid laufen alle Bestaende, mit --uid nur
    die genannten. Und die JSON-Datei muss sich wieder einlesen lassen -
    eine Ausgabe, die nur fast JSON ist, hilft beim Zusammenfuehren nicht.
    """
    import tools.anker_diagnose as cli

    seiten = {URL_T: _seite_mit_posts([100, 101])}
    ev_dir, fo_dir = _bau(tmp_path, seiten,
                          [(1, URL_T, _in_post(1), _in_post(1))], uid="11")
    _bau(tmp_path, seiten, [(1, URL_T, _in_post(1), _in_post(2))], uid="12")

    ziel = tmp_path / "befund.json"
    code = cli.main(["--evidence-dir", str(ev_dir),
                     "--forensic-dir", str(fo_dir),
                     "--json", str(ziel)])
    capsys.readouterr()
    assert code == 0, code
    with open(ziel, "r", encoding="utf-8") as fh:
        inhalt = json.load(fh)
    kennungen = sorted(b["subject_id"] for b in inhalt["bestaende"])
    assert kennungen == ["11", "12"], kennungen

    ziel2 = tmp_path / "nur11.json"
    code = cli.main(["--evidence-dir", str(ev_dir),
                     "--forensic-dir", str(fo_dir),
                     "--uid", "11", "--json", str(ziel2)])
    capsys.readouterr()
    assert code == 0, code
    with open(ziel2, "r", encoding="utf-8") as fh:
        inhalt2 = json.load(fh)
    assert [b["subject_id"] for b in inhalt2["bestaende"]] == ["11"]


def test_AD35_seitenklasse_unterscheidet_beginner_von_viewtopic():
    """
    '/forum/beginner/viewtopic.php' traegt Beitraege und darf NICHT als
    beitragsfrei eingeordnet werden. Rot, sobald die Zuordnung nur auf den
    Dateinamen sieht.
    """
    assert seitenklasse("/forum/beginner/viewtopic.php?id=3") == \
        "beginner_viewtopic"
    assert seitenklasse("/forum/viewtopic.php?id=3") == "viewtopic"
    assert seitenklasse("/forum/search.php") == "search"
    assert seitenklasse("/forum/irgendwas.php") == "sonstige"
