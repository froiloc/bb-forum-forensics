# -*- coding: utf-8 -*-
# =============================================================================
# tests/test_annotation_bestand.py
# Regressionstests zu management/maintenance/annotation_bestand.py
# und tools/annotationen_bestand.py
# =============================================================================
# Zweck:
#   Die Bestandsaufnahme ist Etappe 0 des Arbeitsblocks "Annotationen
#   verwendbar machen". Sie liefert die Zahlenbasis, auf der alle folgenden
#   Etappen aufsetzen. Eine Zaehlung, die still danebenliegt, verschiebt
#   damit jede spaetere Entscheidung.
#
# ── DIE ZWEI GEGENPROBEN, UM DIE ES HIER VOR ALLEM GEHT ──────────────────────
#
#   AB05 ist die Weisung Alex vom 01.09.2026: 'offsetEnd <= offsetStart',
#   NICHT '<'. Eine Auswahl der Laenge null traegt keinen Wortlaut und ist
#   damit ebenso sinnfrei wie eine mit vertauschten Grenzen. Bis Build 754
#   wurde nur '<' gezaehlt; faellt AB05 weg, ist die halbe Menge wieder
#   unsichtbar.
#
#   AB13 haelt fest, dass der SEITEN-BLOB nicht gelesen wird. Das ist der
#   ganze Grund, aus dem diese Messung der Auswertung vorausgeht: die
#   forensic_<uid>.db ist mehrfach neu erstellt worden und enthielt in
#   mindestens zwei Faellen leere BLOBs. Eine Zahlenbasis, die den Inhalt
#   liest, koennte durch genau diesen Defekt verfaelscht sein. Faellt AB13
#   weg, kann ein spaeterer Umbau die Abgrenzung unbemerkt aufheben.
#
#   Zu jedem Test steht, was ihn rot macht.
#
# Version: 0.8.755 - Build 755
# =============================================================================

from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import sys

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WURZEL not in sys.path:
    sys.path.insert(0, WURZEL)

from management.maintenance import annotation_bestand as AB      # noqa: E402
from tools import annotationen_bestand as ABT                    # noqa: E402


# ---------------------------------------------------------------------------
# Die Vorrichtung. Sie bildet genau die Lagen ab, die im echten Bestand
# vermutet werden - jede genau einmal, damit eine falsche Zaehlung sich
# nicht in einer Menge gleichartiger Faelle verstecken kann.
# ---------------------------------------------------------------------------

ANN_DDL = """
CREATE TABLE annotations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  page_url TEXT NOT NULL, element_id TEXT, category TEXT NOT NULL,
  text TEXT NOT NULL DEFAULT '', ts INTEGER NOT NULL, investigator_id INTEGER,
  selection_json TEXT, tags_json TEXT, local_id TEXT, post_id INTEGER,
  created_by TEXT NOT NULL DEFAULT '', deleted_at INTEGER,
  version_nr INTEGER NOT NULL DEFAULT 1, prev_id INTEGER, actual_uid INTEGER);
"""

PAGES_DDL = """
CREATE TABLE pages (id INTEGER PRIMARY KEY AUTOINCREMENT,
  url_canonical TEXT NOT NULL, html BLOB, title TEXT,
  fetched_at INTEGER NOT NULL, http_status INTEGER NOT NULL,
  scrape_context TEXT NOT NULL DEFAULT 'user',
  method TEXT NOT NULL DEFAULT 'GET', UNIQUE(url_canonical, method));
CREATE TABLE page_aliases (url_raw TEXT PRIMARY KEY, page_id INTEGER NOT NULL);
"""

U1 = "/forum/viewtopic.php?id=145446"
U2 = "/forum/viewtopic.php?id=145446&uid=901"
U3 = "/forum/pmsnew.php?mdl=topic&tid=64200"
U4 = "/forum/search.php?action=show_user_posts&user_id=901"
U5 = "/forum/viewforum.php?id=30"

XP_ART = "./div[1]/div[4]/article[8]/div[2]/div[2]/p[1]/text()[1]"
XP_DIV = "./div[1]/div[4]/div[17]/div[1]/div[1]/div[2]/p[1]/text()[2]"
XP_ALT = "//div[1]/div[4]/article[3]/#text[1]"


def _ts(s: str) -> int:
    return int(_dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
               .replace(tzinfo=_dt.timezone.utc).timestamp())


def _sel(**kw) -> str:
    return json.dumps(kw)


def _evidence_901(pfad: str) -> None:
    con = sqlite3.connect(pfad)
    con.executescript(ANN_DDL)
    zeilen = [
        (U1, "p8801", "belastend", _ts("2026-05-08 11:31:15"),
         _sel(xpathStart=XP_ART, offsetStart=10, xpathEnd=XP_ART,
              offsetEnd=40, textContent="ein belegter Wortlaut"),
         8801, None),
        (U1, None, "belastend", _ts("2026-06-12 09:00:00"),
         _sel(xpathStart=XP_ART, offsetStart=5, xpathEnd=XP_ART, offsetEnd=5,
              textContent="Laenge null"), None, None),
        (U1, None, "hinweis", _ts("2026-07-03 10:31:14"),
         _sel(xpathStart=XP_ART, offsetStart=30, xpathEnd=XP_ART,
              offsetEnd=12, textContent="vertauscht"), None, None),
        (U2, "p8802", "belastend", _ts("2026-07-15 08:00:00"),
         _sel(xpathStart=XP_ART, offsetStart=0, xpathEnd=XP_ART, offsetEnd=20,
              textContent="zweite Adresse"), 9999, None),
        (U3, None, "belastend", _ts("2026-07-20 14:00:00"),
         _sel(xpathStart=XP_DIV, offsetStart=0, xpathEnd=XP_DIV, offsetEnd=15,
              textContent="PN-Markierung"), None, None),
        (U3, None, "belastend", _ts("2026-07-20 14:05:00"),
         _sel(xpathStart=XP_ALT, offsetStart=0, xpathEnd=XP_ALT, offsetEnd=9,
              textContent="Altform"), None, None),
        (U3, None, "notiz", _ts("2026-07-21 07:00:00"),
         _sel(xpathStart=XP_DIV, offsetStart=0, xpathEnd=XP_DIV, offsetEnd=8,
              textContent="   "), None, None),
        (U4, None, "notiz", _ts("2026-08-01 12:00:00"),
         _sel(postId=8803, charStart=4, charEnd=44, textLen=200,
              textHash=123, textContent="Uebersetzungsform", model="m",
              created="c"), None, None),
        (U5, None, "belastend", _ts("2026-08-02 12:00:00"),
         _sel(xpathStart=XP_ART, offsetStart=1, xpathEnd=XP_ART, offsetEnd=9,
              textContent="Seite fehlt"), None, None),
        (U1, None, "belastend", _ts("2026-08-03 12:00:00"), None, None, None),
        (U1, None, "belastend", _ts("2026-08-04 12:00:00"), "{kaputt", None,
         None),
        (U1, None, "belastend", _ts("2026-04-01 06:00:00"),
         _sel(xpathStart=XP_ART, offsetStart=1, xpathEnd=XP_ART, offsetEnd=9,
              textContent="geloescht"), None, _ts("2026-08-05 12:00:00")),
    ]
    for r in zeilen:
        con.execute(
            "INSERT INTO annotations (page_url, element_id, category, text, "
            "ts, selection_json, post_id, deleted_at, created_by) "
            "VALUES (?,?,?,'',?,?,?,?,'pruefer')", r)
    # Zweite Generation von Zeile 1 - Zeile 1 gilt damit als ueberholt.
    con.execute(
        "INSERT INTO annotations (page_url, element_id, category, text, ts, "
        "selection_json, post_id, version_nr, prev_id, created_by) "
        "VALUES (?,?,?,'',?,?,?,2,1,'pruefer')",
        (U1, "p8801", "belastend", _ts("2026-08-20 09:00:00"),
         _sel(xpathStart=XP_ART, offsetStart=10, xpathEnd=XP_ART,
              offsetEnd=40, textContent="ein belegter Wortlaut"), 8801))
    # Kettenbruch: prev_id zeigt auf eine Zeile, die es nicht gibt.
    con.execute(
        "INSERT INTO annotations (page_url, category, text, ts, "
        "selection_json, version_nr, prev_id, created_by) "
        "VALUES (?,?,'',?,?,2,9999,'pruefer')",
        (U3, "notiz", _ts("2026-08-21 09:00:00"),
         _sel(xpathStart=XP_DIV, offsetStart=0, xpathEnd=XP_DIV, offsetEnd=4,
              textContent="Bruch")))
    con.commit()
    con.close()


def _forensic_901(pfad: str) -> None:
    con = sqlite3.connect(pfad)
    con.executescript(PAGES_DDL)
    con.execute("INSERT INTO pages (url_canonical, html, title, fetched_at, "
                "http_status, method) VALUES (?,?,?,?,200,'GET')",
                (U1, b"<html><body>" + b"x" * 5000 + b"</body></html>",
                 "Thema 145446 - AiW Forum", _ts("2026-08-28 08:48:09")))
    con.execute("INSERT INTO pages (url_canonical, html, title, fetched_at, "
                "http_status, method) VALUES (?,NULL,?,?,200,'GET')",
                (U3, "PN 64200 - AiW Forum", _ts("2026-08-28 08:47:53")))
    con.execute("INSERT INTO pages (url_canonical, html, title, fetched_at, "
                "http_status, method) VALUES (?,?,?,?,200,'GET')",
                (U4, b"", "Suche - AiW Forum", _ts("2026-08-28 08:49:00")))
    con.execute("INSERT INTO pages (url_canonical, html, title, fetched_at, "
                "http_status, method) VALUES (?,?,?,?,200,'GET')",
                ("/forum/login.php",
                 b"<html><body>" + b"y" * 900 + b"</body>",
                 "Anmeldung erforderlich", _ts("2026-08-28 08:50:00")))
    con.execute("INSERT INTO page_aliases (url_raw, page_id) VALUES (?,1)",
                (U2,))
    con.commit()
    con.close()


def _bestand(tmp_path):
    """Baut den Wegwerf-Bestand und gibt (evidence_dir, forensic_dir)."""
    ev = tmp_path / "evidence"
    fo = tmp_path / "forensic"
    ev.mkdir()
    fo.mkdir()
    _evidence_901(str(ev / "evidence_901.db"))
    _forensic_901(str(fo / "forensic_901.db"))
    # Bestand 902: vorhanden, aber OHNE forensic_902.db.
    con = sqlite3.connect(str(ev / "evidence_902.db"))
    con.executescript(ANN_DDL)
    con.execute("INSERT INTO annotations (page_url, category, text, ts, "
                "selection_json, created_by) VALUES (?,?,'',?,?,'pruefer')",
                (U1, "belastend", _ts("2026-08-10 10:00:00"),
                 _sel(xpathStart=XP_ART, offsetStart=0, xpathEnd=XP_ART,
                      offsetEnd=5, textContent="allein")))
    con.commit()
    con.close()
    return str(ev), str(fo)


def _befund_901(tmp_path):
    ev, fo = _bestand(tmp_path)
    return AB.BestandsAufnahme(
        "901", os.path.join(ev, "evidence_901.db"),
        os.path.join(fo, "forensic_901.db")).erheben()


# ---------------------------------------------------------------------------
# M1 - Zeilenbestand
# ---------------------------------------------------------------------------

def test_ab01_aktuell_schliesst_geloeschte_und_ueberholte_aus(tmp_path):
    """
    ROT, wenn 'aktuell' geloeschte oder ueberholte Zeilen mitzaehlt.

    Das ist die Zahl, ueber die in Etappe 4 entschieden wird. In allen
    Laeufen der Builds 727 bis 754 war von '477 Annotationen' die Rede,
    ohne dass feststand, ob geloeschte und ueberholte darin enthalten sind.
    """
    m1 = _befund_901(tmp_path).m1_zeilenbestand
    assert m1["zeilen_gesamt"] == 14
    assert m1["geloescht"] == 1
    assert m1["ueberholt"] == 1
    assert m1["aktuell"] == 12
    # GEGENPROBE: gesamt minus geloescht minus ueberholt muss aufgehen.
    assert (m1["zeilen_gesamt"] - m1["geloescht"] - m1["ueberholt"]
            == m1["aktuell"])


def test_ab02_kettenbruch_wird_benannt(tmp_path):
    """
    ROT, wenn ein prev_id auf eine nicht vorhandene Zeile unbemerkt bleibt.

    Die Rueckverfolgbarkeit der Generationen ist der Grund, aus dem es die
    Spalte gibt. Ein Bruch darin ist ein Befund (Grundregel 1).
    """
    m1 = _befund_901(tmp_path).m1_zeilenbestand
    assert m1["kettenbruch_anzahl"] == 1
    assert m1["kettenbruch_ids"] == [14]


# ---------------------------------------------------------------------------
# M2 - Spaltenbelegung
# ---------------------------------------------------------------------------

def test_ab03_element_id_form_und_widerspruch_zu_post_id(tmp_path):
    """
    ROT, wenn die Form von element_id nicht ausgewertet oder ein
    Widerspruch zwischen element_id und post_id verschluckt wird.

    element_id ist laut forensic_api/annotate.py Z. 16 der
    Beitragsbehaelter ('p12345'). Wo sie gesetzt ist, ist die post_id OHNE
    Ableitung da - deshalb zaehlt die Zahl, und deshalb zaehlt auch, ob
    beide Angaben dasselbe sagen.
    """
    m2 = _befund_901(tmp_path).m2_spalten
    assert m2["element_id"]["gesetzt"] == 3
    assert m2["element_id_form"]["p_zahl"] == 3
    assert m2["element_id_form"]["sonstige"] == 0
    g = m2["element_id_gegen_post_id"]
    assert g["beide_gesetzt"] == 3
    assert g["gleich"] == 2
    assert g["ungleich"] == 1


# ---------------------------------------------------------------------------
# M3 - page_url
# ---------------------------------------------------------------------------

def test_ab04_dieselbe_seite_unter_zwei_adressen(tmp_path):
    """
    ROT, wenn die Teilmengenpruefung ausfaellt.

    Bei Bestand 515056 steht dieselbe Seite zweimal, einmal mit und einmal
    ohne '&uid='. Wer solche Paare nicht findet, zaehlt eine Seite doppelt
    und sucht spaeter zwei Abzuege, wo es einen gibt.
    """
    m3 = _befund_901(tmp_path).m3_page_url
    assert m3["adressen_verschieden"] == 5
    assert m3["teilmengenpaare_anzahl"] == 1
    paar = m3["teilmengenpaare"][0]
    assert paar["kurz"] == U1 and paar["lang"] == U2
    assert paar["zusatz"] == ["uid=901"]
    assert m3["je_skript"]["viewtopic.php"] == 8


# ---------------------------------------------------------------------------
# M4 - selection_json
# ---------------------------------------------------------------------------

def test_ab05_offsetende_gleich_offsetstart_gilt_als_sinnfrei(tmp_path):
    """
    ROT, wenn nur 'offsetEnd < offsetStart' gezaehlt wird.

    WEISUNG ALEX, 01.09.2026: '<=' und nicht '<'. Eine Auswahl der Laenge
    null traegt keinen Wortlaut und ist ebenso sinnfrei wie eine mit
    vertauschten Grenzen. Faellt dieser Test weg, verschwindet die Haelfte
    der Menge lautlos - genau die Art von stiller Auslassung, die
    Grundregel 1 verbietet.
    """
    m4 = _befund_901(tmp_path).m4_selection
    assert m4["offset_gleich"] == 1
    assert m4["offset_vertauscht"] == 1
    assert m4["offset_sinnfrei"] == 2
    # GEGENPROBE: die Summe der beiden Einzelzaehler muss den Gesamtzaehler
    # ergeben - sonst zaehlt einer von beiden etwas anderes.
    assert m4["offset_gleich"] + m4["offset_vertauscht"] == \
        m4["offset_sinnfrei"]


def test_ab06_zwei_schluesselsignaturen_bleiben_getrennt(tmp_path):
    """
    ROT, wenn die Formen von selection_json zusammenfallen.

    Im Quelltext stehen zwei Formen: die Fuenf-Feld-Form (toolbar.js
    Z. 1129-1135) und die Uebersetzungsform (Z. 1115-1126). OB im Bestand
    weitere liegen, weiss nur der Bestand - deshalb wird die Signatur
    gemessen und nicht aus dem Quelltext angenommen.
    """
    m4 = _befund_901(tmp_path).m4_selection
    assert m4["gueltig"] == 12
    assert m4["null"] == 1
    assert m4["ungueltig"] == 1
    assert m4["signaturen_anzahl"] == 2
    sig = {d["signatur"]: d["anzahl"] for d in m4["signaturen"]}
    assert sig["offsetEnd|offsetStart|textContent|xpathEnd|xpathStart"] == 11
    assert sig["charEnd|charStart|created|model|postId|textContent|"
               "textHash|textLen"] == 1


def test_ab07_wortlaut_aus_leerraum_wird_eigens_gezaehlt(tmp_path):
    """
    ROT, wenn eine Markierung aus reinem Leerraum als gueltiger Wortlaut
    durchgeht. Sie ist sinnfrei - aber auf einem anderen Weg als ein
    vertauschter Offset, und beide Wege werden getrennt gefuehrt, weil
    ihre Schnittmenge selbst eine Aussage ist.
    """
    m4 = _befund_901(tmp_path).m4_selection
    assert m4["textcontent_nur_leerraum"] == 1
    assert m4["textcontent_leer"] == 0


# ---------------------------------------------------------------------------
# M5 - Syntax der XPath-Ausdruecke
# ---------------------------------------------------------------------------

def test_ab08_altform_aus_build_029_wird_erkannt(tmp_path):
    """
    ROT, wenn Praefix '//' oder Textknoten '#text[n]' nicht auffallen.

    toolbar.js ersetzt beides beim Auflesen im Browser (_nodeFromXpath,
    Z. 1013 ff.). Im BESTAND kann es noch stehen - wie oft, war bis heute
    ungemessen. Jedes Werkzeug ausserhalb des Browsers muss die Ersetzung
    selbst vornehmen, und dafuer muss die Menge bekannt sein.
    """
    m5 = _befund_901(tmp_path).m5_xpath
    assert m5["praefix"]["doppel"] == 1
    assert m5["praefix"]["punkt"] == 10
    assert m5["textknoten_altform"] == 1
    assert m5["textknoten_neuform"] == 10
    assert m5["ohne_xpathstart"] == 3      # NULL, ungueltig, Uebersetzungsform
    assert m5["tagnamen"]["article"] == 8


# ---------------------------------------------------------------------------
# M6 - Zeit
# ---------------------------------------------------------------------------

def test_ab09_trennlinie_produktivbetrieb_trennt_und_filtert_nicht(tmp_path):
    """
    ROT, wenn die Linie 01.07.2026 falsch liegt oder Zeilen wegfallen.

    Weisung Alex: ab dem 01.07.2026 gesetzte Annotationen sind in jedem
    Fall echt; davor kann ebenfalls Echtes liegen. Die Linie TRENNT die
    Ausgabe, sie FILTERT nichts - vor plus ab muss die Gesamtzahl ergeben.
    """
    m6 = _befund_901(tmp_path).m6_zeit
    assert m6["vor_produktivbetrieb"] == 3
    assert m6["ab_produktivbetrieb"] == 11
    assert m6["vor_produktivbetrieb"] + m6["ab_produktivbetrieb"] == 14
    assert m6["ohne_zeitstempel"] == 0


def test_ab10_millisekunden_werden_als_solche_gezaehlt(tmp_path):
    """
    ROT, wenn ein Zeitstempel in Millisekunden als Sekunden gelesen wird.

    Er landete dann im Jahr 57000 und faellt in der Monatsauswertung als
    eigener Eimer auf, ohne dass jemand die Ursache sieht.
    """
    ev, fo = _bestand(tmp_path)
    pfad = os.path.join(ev, "evidence_903.db")
    con = sqlite3.connect(pfad)
    con.executescript(ANN_DDL)
    con.execute("INSERT INTO annotations (page_url, category, text, ts, "
                "selection_json, created_by) VALUES (?,?,'',?,?,'p')",
                (U1, "belastend", _ts("2026-08-10 10:00:00") * 1000,
                 _sel(xpathStart=XP_ART, offsetStart=0, xpathEnd=XP_ART,
                      offsetEnd=5, textContent="ms")))
    con.commit()
    con.close()
    m6 = AB.BestandsAufnahme("903", pfad).erheben().m6_zeit
    assert m6["in_millisekunden"] == 1
    assert m6["je_monat"] == {"2026-08": 1}      # nicht Jahr 57000
    assert m6["ab_produktivbetrieb"] == 1


# ---------------------------------------------------------------------------
# M7 - Seitenkopfdaten
# ---------------------------------------------------------------------------

def test_ab11_leere_seiten_werden_nach_null_und_laenge_null_getrennt(tmp_path):
    """
    ROT, wenn 'html IS NULL' und 'length(html) = 0' zusammenfallen.

    Zwei verschiedene Defekte: im einen Fall wurde nichts gespeichert, im
    anderen etwas Leeres. Beide traten bei Neuerstellungen der
    forensic_<uid>.db auf (Befund Alex, 01.09.2026); die Ursachen koennen
    verschieden sein und muessen unterscheidbar bleiben.
    """
    m7 = _befund_901(tmp_path).m7_seiten
    assert m7["vorhanden"] is True
    assert m7["seiten_gesamt"] == 4
    assert m7["html_null"] == 1
    assert m7["html_leer"] == 1
    assert m7["laenge"]["min"] == 0


def test_ab12_annotation_ohne_seite_und_alias_werden_erkannt(tmp_path):
    """
    ROT, wenn die Zuordnung Annotation -> Seite ausfaellt.

    Zwei Faelle in einem: U5 hat KEINE Seite (das ist zu melden), und U2
    findet seine Seite ueber 'page_aliases' (das darf NICHT als fehlend
    gelten). Die vier Abfragen und ihre Reihenfolge sind wortgleich die
    aus postid_nachtrag._blob() - ein Werkzeug, das eine ANDERE Seite
    findet als die Auswertung, zaehlt etwas anderes.
    """
    m7 = _befund_901(tmp_path).m7_seiten
    assert m7["adressen_ohne_seite"] == 1
    assert m7["fehlende_adressen"][0]["url"] == U5
    assert m7["adressen_mit_seite"] == 4          # U2 ueber den Alias
    assert m7["annotationen_auf_leerer_seite"] == 5


def test_ab13_der_blob_inhalt_wird_nicht_gelesen():
    """
    ROT, wenn irgendwo die Spalte 'html' im Klartext selektiert wird.

    DAS IST DIE ABGRENZUNG, DIE DIESE ETAPPE UEBERHAUPT TRAEGT: Der
    Seiten-BLOB ist die eine Groesse, deren Verlaesslichkeit selbst in
    Frage steht. Eine Zahlenbasis, die auf seinem INHALT aufsetzt, koennte
    durch genau den Defekt verfaelscht sein, den sie messen soll. Erlaubt
    sind ausschliesslich 'typeof(html)' und 'length(html)'.
    """
    import ast

    quelle = open(AB.__file__, encoding="utf-8").read()

    # NUR DIE SQL-ZEICHENKETTEN, nicht der Fliesstext. Eine Pruefung ueber
    # die ganze Datei schluege auch bei einem Kommentar an, der das Wort
    # 'html' erwaehnt - und waere damit ein Waechter, den man wegkommentiert
    # statt ihn ernst zu nehmen. Gesucht wird deshalb im Syntaxbaum nach
    # Zeichenketten, die eine Abfrage sind.
    sql_stellen = []
    for knoten in ast.walk(ast.parse(quelle)):
        if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
            wert = knoten.value
            # Abfragen UND Feldlisten. Die Feldlisten stehen als eigene
            # Zeichenkette da und werden erst per '%' eingesetzt - eine
            # Suche nur nach 'SELECT' wuerde sie uebersehen, und genau in
            # ihnen stehen die Spaltenausdruecke.
            if "html" in wert and ("SELECT" in wert or "AS htyp" in wert
                                   or "AS hlen" in wert):
                sql_stellen.append(wert)
    assert sql_stellen, "keine SQL-Zeichenkette gefunden - Test greift ins Leere"

    zusammen = " ".join(sql_stellen)
    import re
    for treffer in re.finditer(r"\bhtml\b", zusammen):
        umfeld = zusammen[max(0, treffer.start() - 12):treffer.end() + 1]
        assert ("typeof(html" in umfeld or "length(html" in umfeld
                or "typeof(p.html" in umfeld or "length(p.html" in umfeld), \
            "Nacktes 'html' in einer Abfrage: %r" % umfeld

    # GEGENPROBE ZUR GEGENPROBE: die erlaubten Formen muessen wirklich
    # vorkommen. Sonst waere der Test auch dann gruen, wenn M7 gar nichts
    # mehr misst.
    assert "typeof(html)" in zusammen and "length(html)" in zusammen
    assert "typeof(p.html)" in zusammen and "length(p.html)" in zusammen


def test_ab14_bestand_ohne_seitendaten_wird_gemeldet_nicht_uebersprungen(
        tmp_path):
    """
    ROT, wenn ein Bestand ohne forensic_<uid>.db stillschweigend entfaellt.

    Grundregel 1. Eine fehlende Seitendatenbank ist ein Befund - die
    Annotationen sind ja da und muessen gezaehlt werden.
    """
    ev, fo = _bestand(tmp_path)
    b = AB.BestandsAufnahme(
        "902", os.path.join(ev, "evidence_902.db"),
        os.path.join(fo, "forensic_902.db")).erheben()
    assert b.evidence_lesbar is True
    assert b.m1_zeilenbestand["zeilen_gesamt"] == 1
    assert b.m7_seiten["vorhanden"] is False
    assert "gibt es nicht" in b.m7_seiten["hinweis"]


def test_ab15_testbestand_wird_gekennzeichnet_aber_nicht_ausgeblendet(
        tmp_path):
    """
    ROT, wenn ein Testbestand herausgerechnet wird.

    Weisung Alex: subject_id=2948078 wurde fuer Testzwecke benutzt - aber
    auch im Testbetrieb koennen verwertbare Spuren erhoben worden sein. Ob
    eine dort gesetzte Annotation zu erhalten ist, ist eine
    Einzelfallentscheidung des Ermittlers und keine des Werkzeugs.
    """
    assert "2948078" in AB.TESTBESTAENDE
    ev, _fo = _bestand(tmp_path)
    quelle = os.path.join(ev, "evidence_901.db")
    ziel = os.path.join(ev, "evidence_2948078.db")
    with open(quelle, "rb") as a, open(ziel, "wb") as b:
        b.write(a.read())
    befund = AB.BestandsAufnahme("2948078", ziel).erheben()
    assert befund.testbestand is True
    assert befund.m1_zeilenbestand["zeilen_gesamt"] == 14   # nichts entfaellt


def test_ab16_verbindung_ist_schreibgeschuetzt(tmp_path):
    """
    ROT, wenn 'mode=ro' entfaellt.

    Der Schreibschutz haengt an der VERBINDUNG und nicht am Vorsatz.
    """
    ev, _fo = _bestand(tmp_path)
    con = AB.BestandsAufnahme._oeffne_ro(os.path.join(ev, "evidence_901.db"))
    try:
        try:
            con.execute("UPDATE annotations SET category = 'x'")
            raise AssertionError("Schreibzugriff war moeglich - mode=ro fehlt")
        except sqlite3.OperationalError:
            pass
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Die Befehlszeile
# ---------------------------------------------------------------------------

def test_ab17_sauberer_bestand_ergibt_rueckgabewert_null(tmp_path):
    """
    ROT, wenn das Werkzeug IMMER einen Befund meldet.

    Ohne diesen Test waere ein Rueckgabewert 1 nichtssagend: er kaeme auch
    dann, wenn gar nichts zu beanstanden ist.
    """
    ev = tmp_path / "evidence"
    fo = tmp_path / "forensic"
    ev.mkdir()
    fo.mkdir()
    con = sqlite3.connect(str(ev / "evidence_910.db"))
    con.executescript(ANN_DDL)
    con.execute("INSERT INTO annotations (page_url, element_id, category, "
                "text, ts, selection_json, post_id, created_by) "
                "VALUES (?,?,?,'',?,?,?,'p')",
                (U1, "p8801", "belastend", _ts("2026-08-10 10:00:00"),
                 _sel(xpathStart=XP_ART, offsetStart=0, xpathEnd=XP_ART,
                      offsetEnd=5, textContent="heil"), 8801))
    con.commit()
    con.close()
    con = sqlite3.connect(str(fo / "forensic_910.db"))
    con.executescript(PAGES_DDL)
    con.execute("INSERT INTO pages (url_canonical, html, title, fetched_at, "
                "http_status, method) VALUES (?,?,?,?,200,'GET')",
                (U1, b"<html>" + b"x" * 4000 + b"</html>", "Thema",
                 _ts("2026-08-28 08:48:09")))
    con.commit()
    con.close()
    zeilen = []
    rueck = ABT.lauf(str(ev), str(fo), [], zeilen.append, 20, None)
    assert rueck == ABT.RUECK_OHNE_BEFUND
    assert any("BEFUNDE, DIE EINE ENTSCHEIDUNG VERLANGEN: 0" in z
               for z in zeilen)


def test_ab18_klartext_und_json_tragen_dieselben_zahlen(tmp_path):
    """
    ROT, wenn die JSON-Fassung aus dem Text nachgebaut wird oder umgekehrt.

    Zwei Darstellungen, von denen eine aus der anderen abgeleitet wird,
    weichen frueher oder spaeter ab. Beide entstehen aus demselben Befund -
    dieser Test haelt das fest, indem er die Zahl aus dem JSON gegen die
    Zeile im Klartext haelt.
    """
    ev, fo = _bestand(tmp_path)
    ziel = str(tmp_path / "bestand.json")
    zeilen = []
    rueck = ABT.lauf(ev, fo, [], zeilen.append, 20, ziel)
    assert rueck == ABT.RUECK_BEFUND
    daten = json.load(open(ziel, encoding="utf-8"))
    assert len(daten["bestaende"]) == 2
    b901 = [b for b in daten["bestaende"] if b["uid"] == "901"][0]
    assert b901["m1_zeilenbestand"]["aktuell"] == 12
    assert any("AKTUELL (nicht geloescht, nicht ueberholt) 12" in z
               for z in zeilen)
    assert b901["m4_selection"]["offset_sinnfrei"] == 2
    assert any("offsetEnd <= offsetStart (gesamt)          2" in z
               for z in zeilen)
    # Die JSON-Fassung muss ASCII-rein sein (Projektvorgabe fuer
    # maschinenlesbare Ausgaben, vgl. build.json).
    with open(ziel, "rb") as fh:
        assert all(byte < 128 for byte in fh.read())


def test_ab19_gesamtbilanz_summiert_ueber_alle_bestaende(tmp_path):
    """
    ROT, wenn ein Bestand aus der Summe faellt.

    Die Gesamtbilanz ist die Zahl, die im Protokoll landet. Faellt dort ein
    Bestand heraus, merkt es niemand - die Einzelblocks stehen ja darueber.
    """
    ev, fo = _bestand(tmp_path)
    zeilen = []
    ABT.lauf(ev, fo, [], zeilen.append, 20, None)
    summe = [z for z in zeilen if z.strip().startswith("SUMME")]
    assert len(summe) == 1
    # 14 Zeilen in 901 + 1 Zeile in 902 = 15; aktuell 12 + 1 = 13.
    werte = summe[0].split()
    assert werte[1] == "15"
    assert werte[4] == "13"
