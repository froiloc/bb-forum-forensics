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


XP_A = ("./donate[1]/div[1]/div[3]/div[1]/div[1]/div[1]/div[1]/div[2]/"
        "div[4]/h2[1]/span[1]/a[1]/text()[1]")
XP_B = ("./donate[1]/div[1]/div[3]/div[1]/div[1]/div[1]/div[1]/div[2]/"
        "div[6]/div[1]/div[1]/div[1]/div[2]/div[1]/p[1]/text()[2]")


def _evidence_904(pfad: str) -> None:
    """
    Der Bestand fuer die Faelle, an denen Build 755 gescheitert ist.

    Zeile 1 ist Alex' echter Fall aus Bestand 1704143: zwei VERSCHIEDENE
    Knoten, offsetEnd (19) kleiner als offsetStart (25). Build 755 hat das
    als sinnfrei gemeldet. Es ist keine Beanstandung, sondern eine ueber
    zwei Knoten laufende Markierung.
    """
    con = sqlite3.connect(pfad)
    con.executescript(ANN_DDL)
    zeilen = [
        # 1: verschiedene Knoten, Ende < Anfang -> KEINE Beanstandung
        (U1, None, _ts("2026-07-10 08:00:00"),
         _sel(xpathStart=XP_A, offsetStart=25, xpathEnd=XP_B, offsetEnd=19,
              textContent="ein echter Wortlaut ueber zwei Knoten"),
         "h082317", None),
        # 2: selber Knoten, Ende < Anfang -> BEANSTANDUNG
        (U1, None, _ts("2026-07-10 08:01:00"),
         _sel(xpathStart=XP_A, offsetStart=25, xpathEnd=XP_A, offsetEnd=19,
              textContent="wirklich verdreht"), "H0D899", None),
        # 3: selber Knoten, Laenge null -> BEANSTANDUNG
        (U1, None, _ts("2026-07-10 08:02:00"),
         _sel(xpathStart=XP_A, offsetStart=7, xpathEnd=XP_A, offsetEnd=7,
              textContent="Laenge null"), "H0D899", None),
        # 4: nur Zeichensetzung -> ohne Wortzeichen
        (U1, None, _ts("2026-07-10 08:03:00"),
         _sel(xpathStart=XP_A, offsetStart=0, xpathEnd=XP_A, offsetEnd=3,
              textContent="---"), "h082317", None),
        # 5: kyrillisch -> MUSS als Wortlaut gelten
        (U1, None, _ts("2026-07-10 08:04:00"),
         _sel(xpathStart=XP_A, offsetStart=0, xpathEnd=XP_A, offsetEnd=6,
              textContent="\u041f\u0440\u0438\u0432\u0435\u0442"),
         "h082317", None),
        # 6: arabisch -> MUSS als Wortlaut gelten
        (U1, None, _ts("2026-07-10 08:05:00"),
         _sel(xpathStart=XP_A, offsetStart=0, xpathEnd=XP_A, offsetEnd=5,
              textContent="\u0645\u0631\u062d\u0628\u0627"),
         "H0D899", None),
        # 7: Alex' Produktivkonto -> ausgenommen
        (U1, None, _ts("2026-07-10 08:06:00"),
         _sel(xpathStart=XP_A, offsetStart=0, xpathEnd=XP_A, offsetEnd=4,
              textContent="Test"), "H0A2898", None),
        # 8: Alex' Entwicklungskonto -> ausgenommen
        (U1, None, _ts("2026-05-10 08:07:00"),
         _sel(xpathStart=XP_A, offsetStart=0, xpathEnd=XP_A, offsetEnd=4,
              textContent="Test"), "paul", None),
        # 9: faelschliche Entwicklungskennung -> ausgenommen
        (U1, None, _ts("2026-05-10 08:08:00"),
         _sel(xpathStart=XP_A, offsetStart=0, xpathEnd=XP_A, offsetEnd=4,
              textContent="Test"), "uid_538299", None),
        # 10: leere Kennung -> ungueltig
        (U1, None, _ts("2026-07-10 08:09:00"),
         _sel(xpathStart=XP_A, offsetStart=0, xpathEnd=XP_A, offsetEnd=4,
              textContent="ohne Kennung"), "", None),
        # 11: Variante 1 'whole post' -> selection_json NULL, post_id gesetzt
        (U1, "p9001", _ts("2026-07-10 08:10:00"), None, "h082317", 9001),
        # 12: weder noch -> darf es nicht geben
        (U1, None, _ts("2026-07-10 08:11:00"), None, "h082317", None),
    ]
    for page, eid, tsw, seljson, urheber, pid in zeilen:
        con.execute(
            "INSERT INTO annotations (page_url, element_id, category, text, "
            "ts, selection_json, created_by, post_id) "
            "VALUES (?,?,'belastend','',?,?,?,?)",
            (page, eid, tsw, seljson, urheber, pid))
    con.commit()
    con.close()


def _befund_904(tmp_path, ausgenommen=None):
    ev = tmp_path / "evidence904"
    ev.mkdir()
    pfad = str(ev / "evidence_904.db")
    _evidence_904(pfad)
    return AB.BestandsAufnahme("904", pfad, None,
                               ausgenommen=ausgenommen).erheben()


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

def test_ab05_offsets_werden_nur_im_selben_knoten_verglichen(tmp_path):
    """
    ROT, wenn Offsets ueber Knotengrenzen hinweg verglichen werden.

    DAS IST DER FEHLER AUS BUILD 755. 'offsetStart' zaehlt Zeichen IM KNOTEN
    von 'xpathStart', 'offsetEnd' IM KNOTEN von 'xpathEnd'. Bei
    verschiedenen Knoten fehlt der gemeinsame Bezugspunkt; ihr
    Groessenverhaeltnis sagt nichts.

    Zeile 1 des Pruefbestands ist Alex' echter Fall aus Bestand 1704143:
    zwei verschiedene Knoten, offsetEnd=19 < offsetStart=25, aber ein
    vollstaendig gueltiger Wortlaut. Build 755 hat ihn beanstandet. Von 25
    damals gemeldeten Faellen waren mindestens 12 auf diese Weise falsch.
    """
    m4 = _befund_904(tmp_path).m4_selection
    off = m4["offsets"]
    assert off["nicht_vergleichbar_andere_knoten"] == 1
    assert off["beanstandet"] == 2          # NICHT 3
    assert off["ende_vor_anfang"] == 1      # nur die Zeile im SELBEN Knoten
    assert off["laenge_null"] == 1
    ids = sorted(d["id"] for d in off["faelle"])
    assert ids == [2, 3], "Zeile 1 darf NICHT beanstandet werden"
    # GEGENPROBE: die drei Gruppen muessen die gueltigen Zeilen ausschoepfen.
    assert (off["vergleichbar_selber_knoten"]
            + off["nicht_vergleichbar_andere_knoten"]
            + off["ohne_offsets"]) == m4["gueltig"]


def test_ab06_beanstandete_zeilen_werden_namentlich_genannt(tmp_path):
    """
    ROT, wenn eine Beanstandung ohne annotations.id gemeldet wird.

    Build 755 lieferte nur Zaehlwerte. Als Alex die Faelle nachpruefen
    wollte, konnte das Werkzeug sie nicht benennen - er musste dem Ergebnis
    glauben, statt es pruefen zu koennen. Bei einer forensischen Messung ist
    das nicht hinnehmbar.
    """
    m4 = _befund_904(tmp_path).m4_selection
    for d in m4["offsets"]["faelle"]:
        assert isinstance(d["id"], int) and d["id"] > 0
        assert d["art"] in ("ende_vor_anfang", "laenge_null")
    for d in m4["wortlaut"]["faelle"]:
        assert isinstance(d["id"], int) and d["id"] > 0
    assert [d["id"] for d in m4["wortlaut"]["faelle"]] == [4]


def test_ab07_wortzeichen_werden_unicode_ausgewertet(tmp_path):
    """
    ROT, wenn '\\w' nur ASCII erfasst.

    DAS IST DER GEFAEHRLICHSTE EINZELFEHLER IN DIESEM BLOCK. Das Forum ist
    multilingual. Wertete die Leerpruefung '\\w' als ASCII aus, meldete sie
    kyrillische, arabische und CJK-Markierungen als leer - und die Regel
    'Markierungen ohne Wortzeichen werden endgueltig geloescht' vernichtete
    dann echte Beweismittel ganzer Sprachraeume.

    Zeile 4 ist '---' und MUSS beanstandet werden. Zeile 5 ist kyrillisch,
    Zeile 6 arabisch; beide MUESSEN unbeanstandet bleiben.
    """
    wl = _befund_904(tmp_path).m4_selection["wortlaut"]
    assert wl["ohne_wortzeichen"] == 1
    assert wl["beanstandet"] == 1
    assert [d["id"] for d in wl["faelle"]] == [4]
    assert wl["fehlt"] == 0 and wl["leer"] == 0 and wl["nur_leerraum"] == 0


def test_ab20_urheber_werden_in_drei_klassen_getrennt(tmp_path):
    """
    ROT, wenn die Einordnung von 'created_by' danebenliegt.

    Weisung Alex, 02.09.2026: gueltig ist, was mit 'H0' oder 'h0' beginnt.
    Ausgenommen sind sein Produktivkonto 'H0A2898', sein Entwicklungskonto
    'paul' und die faelschlich existierende Kennung 'uid_<Ziffern>'. Leer
    und NULL gelten als ungueltig.

    DIE REIHENFOLGE DER PRUEFUNG IST WESENTLICH: 'H0A2898' erfuellt die
    Formregel. Stuende die Formpruefung vorn, zaehlte Alex' eigenes
    Testkonto als Ermittlerarbeit.
    """
    m8 = _befund_904(tmp_path).m8_urheber
    assert m8["gueltige_kennung"] == 8      # h082317 5x + H0D899 3x
    assert m8["ausgenommen"] == 3           # H0A2898, paul, uid_538299
    assert m8["ungueltige_kennung"] == 1    # leere Kennung
    assert m8["leer_oder_null"] == 1
    assert m8["gueltige_kennung"] + m8["ausgenommen"] \
        + m8["ungueltige_kennung"] == 12


def test_ab21_ausschlussliste_wird_ergaenzt_nicht_ersetzt(tmp_path):
    """
    ROT, wenn '--ausschluss' die eingebaute Liste verdraengt.

    Wer eine eigene Liste uebergibt, soll ZUSAETZLICHE Kennungen ausnehmen
    koennen - aber nicht versehentlich Alex' Testkonten wieder als
    Ermittlerarbeit einstufen. Eine Ausschlussliste, die sich per Argument
    LEEREN laesst, waere ein stiller Weg, Testdaten zu Beweismitteln zu
    machen.
    """
    m8 = _befund_904(tmp_path, ausgenommen=("H0D899",)).m8_urheber
    assert "H0A2898" in m8["ausschlussliste"]
    assert "paul" in m8["ausschlussliste"]
    assert "H0D899" in m8["ausschlussliste"]
    assert m8["ausgenommen"] == 6           # 3 wie zuvor + 3x H0D899
    assert m8["gueltige_kennung"] == 5      # nur noch h082317


def test_ab22_zeitverteilung_je_kennung(tmp_path):
    """
    ROT, wenn die Zeitangabe je Kennung fehlt.

    Eine gueltige Kennung, die ausschliesslich vor dem 01.07.2026 gearbeitet
    hat, ist ein anderer Fall als eine, die durchgehend gearbeitet hat.
    Beides zusammen sagt mehr als jedes fuer sich.
    """
    m8 = _befund_904(tmp_path).m8_urheber
    nach = {d["wert"]: d for d in m8["je_wert"]}
    assert nach["paul"]["vor_produktivbetrieb"] == 1
    assert nach["paul"]["ab_produktivbetrieb"] == 0
    assert nach["h082317"]["ab_produktivbetrieb"] == 5
    assert nach["h082317"]["vor_produktivbetrieb"] == 0
    assert nach["(leer oder NULL)"]["klasse"] == "ungueltig"


def test_ab23_die_beiden_annotationsvarianten_werden_getrennt(tmp_path):
    """
    ROT, wenn 'whole post' und 'text range' zusammenfallen.

    Beleg (Alex, 02.09.2026): Variante 1 markiert einen ganzen Beitrag -
    kein selection_json, nur post_id. Variante 2 markiert eine Textpassage -
    mit selection_json. Build 755 hatte den Verdacht nur aus GLEICHEN
    ANZAHLEN geschoepft (14/14, 2/2, 3/3), was kein Beweis ist; Alex musste
    es von Hand nachpruefen. Diese Messung nimmt ihm die Handarbeit ab.

    'beides' und 'weder noch' duerfte es nach der Beschreibung nicht geben -
    genau deshalb werden sie gezaehlt UND namentlich genannt.
    """
    m9 = _befund_904(tmp_path).m9_variante
    assert m9["whole_post"] == 1
    assert m9["text_range"] == 10
    assert m9["text_range_ohne_ort"] == 10
    assert m9["text_range_mit_ort"] == 0
    assert m9["weder_noch"] == 1
    assert m9["weder_noch_ids"] == [12]
    assert (m9["whole_post"] + m9["text_range"] + m9["weder_noch"]) == 12


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
    assert b901["m4_selection"]["offsets"]["beanstandet"] == 2
    assert any("BEANSTANDET (nur aus der ersten Gruppe)    2" in z
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
    # Spalten: SUMME Zeilen AKTUELL wholeP textR ERMITTL ausgen unguelt
    # 14 Zeilen in 901 + 1 Zeile in 902 = 15; aktuell 12 + 1 = 13.
    werte = summe[0].split()
    assert werte[1] == "15"
    assert werte[2] == "13"
    # Beide Bestaende tragen created_by='pruefer' - keine gueltige Kennung.
    assert werte[5] == "0"
