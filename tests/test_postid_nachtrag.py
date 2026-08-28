# =============================================================================
# tests/test_postid_nachtrag.py
# IT-Forensisches Ermittlungswerkzeug - Nachtrag der Beitragsnummer
# =============================================================================
# Zweck:
#   Der Nachtrag greift in einen BESTEHENDEN Beweismittelbestand ein
#   (evidence_<uid>.db, seit 01.07.2026 unter Migrationsvorbehalt). Was hier
#   geprueft wird, ist deshalb nicht "laeuft es durch", sondern:
#
#     - schreibt es NUR, was es aus dem Abzug belegen kann (PN01, PN02, PN10)
#     - laesst es alles Mehrdeutige in Ruhe (PN03)
#     - ueberschreibt es nie etwas Vorhandenes (PN06, PN07)
#     - entsteht ohne Sicherung und ohne Hash-Kette gar nichts (PN08, PN09)
#     - steht jede einzelne Aenderung im Beleg (PN11) und ist die Kette
#       danach noch in Ordnung (PN12)
#     - bleibt die Trockenuebung wirklich trocken (PN05)
#     - ist der Lauf wiederholbar, ohne beim zweiten Mal etwas zu tun (PN13)
#
# GEGENPROBEN sind eigens ausgewiesen (PN14, PN15): ein Test, der auch dann
#   gruen bliebe, wenn die Pruefung fehlt, prueft nichts.
#
# Version: v0.8.728 - Build: 728 - 2026-08-28
# =============================================================================

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.maintenance.postid_nachtrag import (  # noqa: E402
    ERG_GETRAGEN,
    ERG_MEHRDEUTIG,
    ERG_NICHT_GEFUNDEN,
    ERG_RUECKFALL_AUS,
    ERG_SCHON_DA,
    ERG_WIDERSPRUCH,
    ERG_WUERDE,
    PostIdNachtrag,
    WEG_ANKER,
    WEG_UEBERSETZUNG,
    WEG_WORTLAUT,
    WEG_WORTLAUT_EINDEUTIG,
)

# --- Der Seitenabzug ---------------------------------------------------------
#
# ER BILDET DAS FORUM NACH, nicht irgendein HTML: aeussere Kennung am
# <article id="p...">, innere am <div class="box" id="pp...">. Beide traegt
# viewtopic0.php (Forenquelltext, Z. 975; s. db/forensic_db.py:291-307).
# Beitrag 4713 hat ZWEI Absaetze mit demselben Wort - das ist der Fall, in dem
# der Wortlaut mehrdeutig, die Beitragsnummer aber eindeutig ist.
BODY = """<div id="forensic-viewport">
<article class="post" id="p4711"><div class="blockpost">
<div class="postleft"><dl><dt><strong>alice</strong></dt></dl></div>
<div class="box" id="pp4711"><div class="postmsg">
<p>Wir treffen uns am Bahnhof in Musterstadt.</p>
<p>Das Wetter war schoen.</p>
</div></div></div></article>
<article class="post" id="p4712"><div class="blockpost">
<div class="box" id="pp4712"><div class="postmsg">
<p>Das Wetter war schoen.</p>
<p>Mein Bruder faehrt mit dem Rad.</p>
</div></div></div></article>
<article class="post" id="p4713"><div class="blockpost">
<div class="box" id="pp4713"><div class="postmsg">
<p>Ein reiner Innentreffer: Kirschbaum.</p>
<p>Und nochmal Kirschbaum.</p>
</div></div></div></article>
</div>"""

#: Ein Beitrag OHNE aeussere Kennung - nur '<div class="box" id="pp...">'.
#: Genau der Fall, fuer den Build 728 die innere Kennung annimmt.
BODY_NUR_INNEN = """<div id="forensic-viewport">
<div class="box" id="pp5150"><div class="postmsg">
<p>Nur die innere Kennung, kein article darum.</p>
</div></div>
</div>"""

# --- DIE BEIDEN ECHTEN AUFBAUTEN ---------------------------------------------
#
# Uebergeben von Alex am 28.08.2026, gekuerzt und ohne Inhalte, aber in der
# Schachtelung UNVERAENDERT. Sie sind der Beleg, an dem die Erkennung haengt -
# und sie sind VERSCHIEDEN:
#
#   Forenbeitrag (viewtopic):  <article id="p<N>"> … <div class="box"
#                              id="pp<N>"> … <div class="postmsg">
#                              -> BEIDE Kennungen, die innere zuerst erreicht
#
#   Private Nachricht (pmsnew): <div id="p<N>" class="blockpost"> … <div
#                              class="box"> … <div class="postmsg">
#                              -> die '.box' hat dort GAR KEINE Kennung; die
#                                 Nummer steht nur an der AEUSSEREN
#
# DARAUS FOLGT UNMITTELBAR, dass beide Formen gelten muessen. Haette man
# Alex' Weisung ("Suche nach <div class='box' id='pp<post_id>'>") woertlich
# als EINZIGEN Weg genommen, waeren die privaten Nachrichten leer geblieben -
# und gerade dort haengt am post_id der Gespraechspartner.
BODY_ECHT_FORUM = """<div id="forensic-viewport">
<article class="post" style="" id="p1164441">
  <div class="blockpost">
    <h2 id="_vt_2vgfi4"><strong><a href="user.php?id=544948">POSTER</a></strong>
      <span><a href="/forum/viewtopic.php?pid=1164441#p1164441">Re: THEMA</a>
      <i><i title="3 years ago">Fri., 16.12.2022 19:08:03</i></i></span></h2>
    <div class="box" id="pp1164441">
      <div class="inbox">
        <div class="postbody" id="_vt_4s14zr">
          <div class="postleft"><dl>
            <dd class="usertitle"><strong>Senior Member</strong></dd>
            <dd><span>Posts: 114</span></dd>
          </dl></div>
          <div class="postright">
            <h3>Re: THEMA</h3>
            <div class="postmsg"><p>Der Zug faehrt ab Hauptbahnhof.</p></div>
          </div>
        </div>
      </div>
      <div class="inbox"><div class="postfoot"><div class="postfootright">
        <ul><li class="postquote"><span><a href="post.php">Reply</a></span></li>
        </ul></div></div></div>
    </div>
  </div>
</article>
</div>"""

BODY_ECHT_PN = """<div id="forensic-viewport">
<div class="block2col"><div class="block">
  <h2 style="color:#115098;" id="_vt_0pivwv">TITEL DER UNTERHALTUNG</h2>
</div></div>
<div id="p120862" class="blockpost roweven contains_traces">
  <h2 id="_vt_jgki2o"><span><span class="conr">#2</span>
    <a href="pmsnew.php?mdl=topic&amp;pid=120862#p120862">Mon., 26.04.2021
    20:36:03</a></span></h2>
  <div class="box">
    <div class="inbox"><div class="postbody" id="_vt_4g42vk">
      <div class="postleft"><dl>
        <dt><strong class="gender male"><a href="profile.php?id=155955">INHABER
        </a></strong></dt>
        <dd><span>Posts: 20</span></dd>
      </dl></div>
      <div class="postright"><div class="postmsg">
        <p>Ich bin ab Freitag in Koeln.</p>
      </div></div>
    </div></div>
    <div class="inbox"><div class="postfoot clearb">
      <div class="postfootleft"><p></p></div></div></div>
  </div>
  <div class="aiw-flag-fallback aux-part"><span
    class="aiw-translate-item aux-part"><button type="button"
    class="aiw-translate-flag aux-part" data-post-id="120862"><span
    class="aiw-flag-de"></span></button></span></div>
</div>
</div>"""

SEITE = "/forum/viewtopic.php?id=99"
SEITE_INNEN = "/forum/viewtopic.php?id=100"
SEITE_ECHT_FORUM = "/forum/viewtopic.php?id=120200"
SEITE_ECHT_PN = "/forum/pmsnew.php?mdl=topic&tid=42"

WURZEL = Path(__file__).resolve().parent.parent


def _html(body: str) -> bytes:
    return ("<html><head><title>t</title></head><body>%s</body></html>"
            % body).encode("utf-8")


def _auswahl(xpath: str, text: str, versatz: int = 0, **weiteres) -> str:
    d = {"xpathStart": xpath, "xpathEnd": xpath,
         "startOffset": versatz, "endOffset": versatz + len(text),
         "textContent": text}
    d.update(weiteres)
    return json.dumps(d)


#: Der Anker auf 'Bahnhof' im ersten Absatz von Beitrag 4711. Er loest im
#: Abzug oben wirklich auf - gepruefte Angabe, kein geschaetzter Pfad.
ANKER_4711 = "./div[1]/article[1]/div[1]/div[2]/div[1]/p[1]/text()[1]"
#: Ein Anker, der NICHT aufloest (es gibt kein neuntes <article>).
ANKER_KAPUTT = "./div[1]/article[9]/p[3]/text()[1]"


class Aufbau:
    """Baut ein Wegwerf-Paar aus evidence_ und forensic_ Datenbank."""

    def __init__(self, verzeichnis: Path, *, mit_kette: bool = True) -> None:
        self.evidence = verzeichnis / "evidence_700.db"
        self.forensic = verzeichnis / "forensic_700.db"
        self._forensic_bauen()
        self._evidence_bauen(mit_kette)

    def _forensic_bauen(self) -> None:
        con = sqlite3.connect(str(self.forensic))
        con.executescript("""
        CREATE TABLE pages(id INTEGER PRIMARY KEY, url_canonical TEXT,
                           html BLOB, fetched_at INTEGER, http_status INTEGER,
                           scrape_context TEXT, method TEXT);
        CREATE TABLE page_aliases(page_id INTEGER, url_raw TEXT);
        CREATE TABLE uid_posts(post_id INTEGER PRIMARY KEY, topic_id INTEGER,
                               forum_id INTEGER, posted_ts INTEGER);
        CREATE TABLE post_aliases(post_id INTEGER PRIMARY KEY,
                                  topic_id INTEGER, forum_id INTEGER,
                                  page INTEGER);
        CREATE TABLE uid_pms_posts(pm_post_id INTEGER PRIMARY KEY,
                                   pm_topic_id INTEGER, posted_ts INTEGER);
        CREATE TABLE pm_aliases(pm_post_id INTEGER PRIMARY KEY,
                                pm_topic_id INTEGER);
        """)
        con.execute("INSERT INTO pages VALUES(1,?,?,0,200,'','GET')",
                    (SEITE, _html(BODY)))
        con.execute("INSERT INTO pages VALUES(2,?,?,0,200,'','GET')",
                    (SEITE_INNEN, _html(BODY_NUR_INNEN)))
        con.execute("INSERT INTO pages VALUES(5,?,?,0,200,'','GET')",
                    (SEITE_ECHT_FORUM, _html(BODY_ECHT_FORUM)))
        con.execute("INSERT INTO pages VALUES(6,?,?,0,200,'','GET')",
                    (SEITE_ECHT_PN, _html(BODY_ECHT_PN)))
        # 4711 gehoert dem untersuchten Benutzer, 4712 nur einem Fremden
        # (Alias-Tabelle), 4713 steht in KEINER der beiden - der Regelfall
        # fuer den Beitrag eines Dritten. Damit sind alle drei Antworten der
        # Gegenprobe im Aufbau vertreten.
        con.execute("INSERT INTO uid_posts VALUES(4711,99,3,1700000000)")
        con.execute("INSERT INTO post_aliases VALUES(4712,99,3,1)")
        con.commit()
        con.close()

    def _evidence_bauen(self, mit_kette: bool) -> None:
        con = sqlite3.connect(str(self.evidence))
        con.executescript(
            (WURZEL / "evidence_uid.db.schema.sql").read_text(encoding="utf-8"))
        if mit_kette:
            from management.migrations.runner import MigrationRunner, discover
            import management.migrations.evidence as paket
            MigrationRunner(
                con, [m for m in discover(paket) if m.VERSION == 3]).run()
        con.isolation_level = ""
        con.commit()
        con.close()

    def annotation(self, *, seite: str = SEITE, kategorie: str = "CAT_PERSON",
                   text: str = "", auswahl: str = None,
                   post_id: int = None, element_id: str = None,
                   geloescht: bool = False) -> int:
        con = sqlite3.connect(str(self.evidence))
        jetzt = int(time.time())
        zeiger = con.execute(
            "INSERT INTO annotations (page_url, element_id, category, text, "
            "ts, selection_json, local_id, created_by, version_nr, post_id, "
            "deleted_at) VALUES (?,?,?,?,?,?,?,?,1,?,?)",
            (seite, element_id, kategorie, text, jetzt, auswahl,
             "l%d" % jetzt, "mmuster", post_id,
             jetzt if geloescht else None))
        con.commit()
        neu = int(zeiger.lastrowid)
        con.close()
        return neu

    def post_id_von(self, annotation_id: int):
        con = sqlite3.connect(str(self.evidence))
        zeile = con.execute("SELECT post_id FROM annotations WHERE id = ?",
                            (annotation_id,)).fetchone()
        con.close()
        return None if zeile is None else zeile[0]

    def kette(self):
        con = sqlite3.connect(str(self.evidence))
        con.row_factory = sqlite3.Row
        zeilen = [dict(r) for r in con.execute(
            "SELECT seq, event_type, content FROM evidence_audit_log "
            "ORDER BY seq")]
        con.close()
        return zeilen


class PostIdNachtragTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.auf = Aufbau(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def _nachtrag(self, **kw) -> PostIdNachtrag:
        return PostIdNachtrag(evidence=self.auf.evidence,
                              forensic=self.auf.forensic, **kw)

    def _befund_zu(self, befund, annotation_id: int):
        for z in befund.zeilen:
            if z.annotation_id == annotation_id:
                return z
        self.fail("Beleg #%d kommt im Befund nicht vor - er waere still "
                  "uebersprungen (GR1)." % annotation_id)

    # --- PN01 --------------------------------------------------------------
    def test_pn01_der_anker_ist_der_sollweg(self):
        """
        PN01: Loest der Anker auf, wird die Nummer daraus gelesen - und der
        Weg wird als 'anker' ausgewiesen.
        """
        nr = self.auf.annotation(
            auswahl=_auswahl(ANKER_4711, "Bahnhof", 20))
        befund = self._nachtrag().lauf(ausfuehren=True, operator="pruefer")
        z = self._befund_zu(befund, nr)
        self.assertEqual(WEG_ANKER, z.weg)
        self.assertEqual(4711, z.post_id)
        self.assertEqual(ERG_GETRAGEN, z.ergebnis)
        self.assertEqual(4711, self.auf.post_id_von(nr))

    # --- PN02 --------------------------------------------------------------
    def test_pn02_der_wortlaut_ist_der_rueckfall(self):
        """
        PN02: Loest der Anker nicht auf und kommt der Wortlaut genau einmal
        vor, wird die Nummer ueber ihn gefunden - ausgewiesen als 'wortlaut'.

        Weisung Alex 28.08.2026: "die Heuristik mit der Suche nach dem
        markierten Begriff im BLOB nur als Fallback".
        """
        nr = self.auf.annotation(
            auswahl=_auswahl(ANKER_KAPUTT, "Musterstadt"))
        befund = self._nachtrag().lauf(ausfuehren=True)
        z = self._befund_zu(befund, nr)
        self.assertEqual(WEG_WORTLAUT, z.weg)
        self.assertEqual(4711, z.post_id)
        self.assertEqual(4711, self.auf.post_id_von(nr))

    # --- PN03 --------------------------------------------------------------
    def test_pn03_mehrere_beitraege_schreiben_nichts(self):
        """
        PN03: Kommt der Wortlaut in VERSCHIEDENEN Beitraegen vor, bleibt das
        Feld leer. Eine geratene Nummer braechte falschen Betreff, falsches
        Datum und falsche Gruppierung mit - und saehe unauffaellig aus.
        """
        nr = self.auf.annotation(
            auswahl=_auswahl(ANKER_KAPUTT, "Das Wetter war schoen"))
        befund = self._nachtrag().lauf(ausfuehren=True)
        z = self._befund_zu(befund, nr)
        self.assertEqual(ERG_MEHRDEUTIG, z.ergebnis)
        self.assertIsNone(z.post_id)
        self.assertIsNone(self.auf.post_id_von(nr))
        self.assertIn("4711", z.bemerkung)
        self.assertIn("4712", z.bemerkung)

    # --- PN04 --------------------------------------------------------------
    def test_pn04_mehrfach_im_selben_beitrag_ist_eindeutig(self):
        """
        PN04: Kommt der Wortlaut mehrfach vor, liegen aber alle Fundstellen
        im SELBEN Beitrag, ist die Beitragsnummer eindeutig - unabhaengig
        davon, welche Fundstelle gemeint war. Sie wird eingetragen und der
        Weg eigens benannt.
        """
        nr = self.auf.annotation(
            auswahl=_auswahl(ANKER_KAPUTT, "Kirschbaum"))
        befund = self._nachtrag().lauf(ausfuehren=True)
        z = self._befund_zu(befund, nr)
        self.assertEqual(WEG_WORTLAUT_EINDEUTIG, z.weg)
        self.assertEqual(4713, z.post_id)
        self.assertEqual(4713, self.auf.post_id_von(nr))

    # --- PN05 --------------------------------------------------------------
    def test_pn05_die_trockenuebung_bleibt_trocken(self):
        """
        PN05: Ohne ausfuehren=True darf sich in der Datenbank NICHTS aendern -
        und zwar auch dann nicht, wenn ein Zweig es versuchen wuerde: die
        Verbindung ist 'mode=ro'.
        """
        nr = self.auf.annotation(
            auswahl=_auswahl(ANKER_4711, "Bahnhof", 20))
        befund = self._nachtrag().lauf(ausfuehren=False)
        z = self._befund_zu(befund, nr)
        self.assertEqual(ERG_WUERDE, z.ergebnis)
        self.assertEqual(4711, z.post_id, "Die Auskunft soll dieselbe sein.")
        self.assertIsNone(self.auf.post_id_von(nr),
                          "Die Trockenuebung hat geschrieben.")
        self.assertIsNone(befund.sicherung,
                          "Eine Trockenuebung braucht keine Sicherung.")
        self.assertEqual(1, len(self.auf.kette()),
                         "Die Trockenuebung hat einen Beleg geschrieben.")

    # --- PN06 --------------------------------------------------------------
    def test_pn06_vorhandene_nummer_wird_nie_ueberschrieben(self):
        """
        PN06: Traegt die Zeile bereits eine ANDERE Nummer, wird nichts
        geaendert. Das ist ein Befund, keine Aufraeumarbeit.
        """
        nr = self.auf.annotation(
            auswahl=_auswahl(ANKER_4711, "Bahnhof", 20), post_id=9999)
        befund = self._nachtrag(beleg=nr).lauf(ausfuehren=True)
        z = self._befund_zu(befund, nr)
        self.assertEqual(ERG_WIDERSPRUCH, z.ergebnis)
        self.assertEqual(9999, self.auf.post_id_von(nr))

    # --- PN07 --------------------------------------------------------------
    def test_pn07_gleiche_nummer_ist_kein_widerspruch(self):
        """PN07: Steht schon dieselbe Nummer da, ist nichts zu tun."""
        nr = self.auf.annotation(
            auswahl=_auswahl(ANKER_4711, "Bahnhof", 20), post_id=4711)
        befund = self._nachtrag(beleg=nr).lauf(ausfuehren=True)
        self.assertEqual(ERG_SCHON_DA, self._befund_zu(befund, nr).ergebnis)
        self.assertEqual(0, befund.geschrieben)

    # --- PN08 --------------------------------------------------------------
    def test_pn08_ohne_hash_kette_wird_nichts_geschrieben(self):
        """
        PN08: Fehlt 'evidence_audit_log' (Migration M003 nicht angewandt),
        bricht der Lauf ab. Eine unbelegte Aenderung an einem Beweismittel
        darf es nicht geben - dieselbe Regel, nach der M004 im Zweifel lieber
        abbricht als zu konvertieren (SI09).
        """
        ecke = self.dir / "ohnekette"
        ecke.mkdir()
        auf = Aufbau(ecke, mit_kette=False)
        nr = auf.annotation(auswahl=_auswahl(ANKER_4711, "Bahnhof", 20))
        befund = PostIdNachtrag(evidence=auf.evidence,
                                forensic=auf.forensic).lauf(ausfuehren=True)
        self.assertIn("evidence_audit_log", befund.abgebrochen)
        self.assertIsNone(auf.post_id_von(nr))

    # --- PN09 --------------------------------------------------------------
    def test_pn09_der_scharfe_lauf_sichert_vorher(self):
        """
        PN09: Vor der ersten Aenderung liegt eine Kopie daneben. Weisung
        Alex: "unabdingbare Vorbedingung".
        """
        self.auf.annotation(auswahl=_auswahl(ANKER_4711, "Bahnhof", 20))
        befund = self._nachtrag().lauf(ausfuehren=True)
        self.assertIsNotNone(befund.sicherung)
        kopie = Path(befund.sicherung)
        self.assertTrue(kopie.is_file())
        # Die Kopie ist der Zustand VORHER - in ihr ist die Spalte noch leer.
        con = sqlite3.connect(str(kopie))
        offen = con.execute("SELECT COUNT(*) FROM annotations "
                            "WHERE post_id IS NULL").fetchone()[0]
        con.close()
        self.assertEqual(1, offen,
                         "Die Sicherung entstand nicht VOR der Aenderung.")

    # --- PN10 --------------------------------------------------------------
    def test_pn10_die_innere_kennung_allein_genuegt(self):
        """
        PN10: Ein Beitrag ohne aeusseren '<article id="p...">' wird ueber die
        innere Kennung '<div class="box" id="pp...">' erkannt. Das ist der
        Weg, den Alex am 28.08.2026 ausdruecklich genannt hat, und bis
        Build 727 haette er nicht getragen.
        """
        nr = self.auf.annotation(
            seite=SEITE_INNEN,
            auswahl=_auswahl("./div[1]/div[1]/div[1]/p[1]/text()[1]",
                             "innere Kennung", 9))
        befund = self._nachtrag().lauf(ausfuehren=True)
        z = self._befund_zu(befund, nr)
        self.assertEqual(5150, z.post_id,
                         "Die innere Kennung 'pp5150' wurde nicht gelesen.")

    # --- PN11 --------------------------------------------------------------
    def test_pn11_jede_aenderung_steht_im_beleg(self):
        """
        PN11: Der Eintrag in der Hash-Kette nennt JEDE geaenderte Zeile mit
        ihrer Nummer und dem Weg (GR1) - und er nennt WEDER den Wortlaut NOCH
        die Notiz (Sensibilitaetsregel wie M018/M022).
        """
        a = self.auf.annotation(auswahl=_auswahl(ANKER_4711, "Bahnhof", 20),
                                text="Notiz des Ermittlers")
        b = self.auf.annotation(
            auswahl=_auswahl(ANKER_KAPUTT, "Musterstadt"))
        self._nachtrag().lauf(ausfuehren=True, operator="pruefer")

        eintraege = [z for z in self.auf.kette()
                     if z["event_type"] == "annotation_postid_backfilled"]
        self.assertEqual(1, len(eintraege), "Genau ein Eintrag je Lauf.")
        nutzlast = json.loads(eintraege[0]["content"])
        ids = {e["id"]: e for e in nutzlast["aenderungen"]}
        self.assertEqual({a, b}, set(ids))
        self.assertEqual(4711, ids[a]["post_id"])
        self.assertEqual(WEG_ANKER, ids[a]["weg"])
        self.assertEqual(WEG_WORTLAUT, ids[b]["weg"])
        self.assertEqual("pruefer", nutzlast["operator"])

        roh = eintraege[0]["content"]
        for verboten in ("Bahnhof", "Musterstadt", "Notiz des Ermittlers",
                         SEITE):
            self.assertNotIn(
                verboten, roh,
                "Der Beleg traegt %r. Im unveraenderlichen Protokoll haben "
                "Inhalte aus einem Verfahren nach §§ 176, 184b StGB nichts "
                "zu suchen." % verboten)

    # --- PN12 --------------------------------------------------------------
    def test_pn12_die_kette_ist_danach_in_ordnung(self):
        """PN12: Der angehaengte Beleg zerstoert die Verkettung nicht."""
        from management.audit.evidence_audit_log import EvidenceAuditLog
        self.auf.annotation(auswahl=_auswahl(ANKER_4711, "Bahnhof", 20))
        self._nachtrag().lauf(ausfuehren=True)
        con = sqlite3.connect(str(self.auf.evidence))
        try:
            ergebnis = EvidenceAuditLog(con).verify_chain()
        finally:
            con.close()
        self.assertTrue(ergebnis.ok, ergebnis.detail)

    # --- PN13 --------------------------------------------------------------
    def test_pn13_der_zweite_lauf_tut_nichts(self):
        """
        PN13: Wiederholbarkeit. Der zweite Lauf findet nichts mehr zu tun und
        haengt keinen zweiten Beleg an - sonst stuende in der Kette eine
        Aenderung, die es nicht gab.
        """
        self.auf.annotation(auswahl=_auswahl(ANKER_4711, "Bahnhof", 20))
        self._nachtrag().lauf(ausfuehren=True)
        vorher = len(self.auf.kette())
        zweiter = self._nachtrag().lauf(ausfuehren=True)
        self.assertEqual(0, zweiter.geschrieben)
        self.assertEqual(vorher, len(self.auf.kette()))

    # --- PN14: GEGENPROBE zu PN03 ------------------------------------------
    def test_pn14_die_mehrdeutigkeit_wird_wirklich_erkannt(self):
        """
        PN14: Ein Test, der auch ohne die Pruefung gruen bliebe, prueft
        nichts. Derselbe Wortlaut, aber auf einer Seite mit NUR EINEM
        Beitrag - dann muss dieselbe Eingabe sehr wohl zu einer Nummer
        fuehren. Erst dieser Gegenbeweis zeigt, dass PN03 an der
        Mehrdeutigkeit haengt und nicht am Wortlaut.
        """
        con = sqlite3.connect(str(self.auf.forensic))
        einer = BODY[:BODY.index('<article class="post" id="p4712"')] + "</div>"
        con.execute("INSERT INTO pages VALUES(3,'/forum/x.php',?,0,200,'','GET')",
                    (_html(einer),))
        con.commit()
        con.close()
        nr = self.auf.annotation(
            seite="/forum/x.php",
            auswahl=_auswahl(ANKER_KAPUTT, "Das Wetter war schoen"))
        befund = self._nachtrag(beleg=nr).lauf(ausfuehren=False)
        z = self._befund_zu(befund, nr)
        self.assertEqual(4711, z.post_id,
                         "Auf einer Seite mit nur einem Beitrag darf derselbe "
                         "Wortlaut sehr wohl zur Nummer fuehren.")

    # --- PN15: GEGENPROBE zu PN10 ------------------------------------------
    def test_pn15_ohne_jede_kennung_wird_nichts_erfunden(self):
        """
        PN15: Gegenprobe zu PN10. Traegt KEIN Vorfahr eine Beitragskennung
        (Uebersichts-, Such- und Profilseiten), bleibt das Feld leer.
        Andernfalls waere PN10 nur der Nachweis, dass irgendetwas
        zurueckkommt.
        """
        con = sqlite3.connect(str(self.auf.forensic))
        con.execute(
            "INSERT INTO pages VALUES(4,'/forum/search.php',?,0,200,'','GET')",
            (_html('<div id="forensic-viewport"><div class="box">'
                   '<p>Treffer ohne Beitragskennung.</p></div></div>'),))
        con.commit()
        con.close()
        nr = self.auf.annotation(
            seite="/forum/search.php",
            auswahl=_auswahl("./div[1]/div[1]/p[1]/text()[1]", "Treffer"))
        befund = self._nachtrag(beleg=nr).lauf(ausfuehren=True)
        z = self._befund_zu(befund, nr)
        self.assertEqual(ERG_NICHT_GEFUNDEN, z.ergebnis)
        self.assertIsNone(self.auf.post_id_von(nr))

    # --- PN16 --------------------------------------------------------------
    def test_pn16_uebersetzung_nimmt_die_nummer_aus_der_auswahl(self):
        """
        PN16: Markierungen in einer maschinellen Uebersetzung stehen nicht im
        Abzug. toolbar.js hat ihnen aber immer schon die Nummer mitgegeben;
        sie wird uebernommen und nicht hergeleitet.
        """
        nr = self.auf.annotation(
            auswahl=_auswahl("./div[1]/p[1]/text()[1]", "irgendwas",
                             target="translation", postId=4712))
        befund = self._nachtrag().lauf(ausfuehren=True)
        z = self._befund_zu(befund, nr)
        self.assertEqual(WEG_UEBERSETZUNG, z.weg)
        self.assertEqual(4712, z.post_id)

    # --- PN17 --------------------------------------------------------------
    def test_pn17_nur_anker_schaltet_den_rueckfall_ab(self):
        """
        PN17: Mit nur_anker=True wird ueber den Wortlaut NICHTS eingetragen -
        aber die Zeile verschwindet nicht, sie wird als 'Rueckfall
        abgeschaltet' ausgewiesen (GR1).
        """
        nr = self.auf.annotation(
            auswahl=_auswahl(ANKER_KAPUTT, "Musterstadt"))
        befund = self._nachtrag(nur_anker=True).lauf(ausfuehren=True)
        z = self._befund_zu(befund, nr)
        self.assertEqual(ERG_RUECKFALL_AUS, z.ergebnis)
        self.assertIsNone(self.auf.post_id_von(nr))

    # --- PN18 --------------------------------------------------------------
    def test_pn18_die_gegenprobe_im_paket_urteilt_nicht(self):
        """
        PN18: Beitrag 4713 steht in KEINER Tabelle des Pakets - das ist der
        Regelfall fuer den Beitrag eines Dritten, weil fdb.uid_posts nur die
        Beitraege des untersuchten Benutzers fuehrt. Die Gegenprobe meldet
        'nein' UND die Nummer wird trotzdem eingetragen: der versiegelte
        Abzug ist der staerkere Beleg.
        """
        nr = self.auf.annotation(
            auswahl=_auswahl(ANKER_KAPUTT, "Kirschbaum"))
        befund = self._nachtrag().lauf(ausfuehren=True)
        z = self._befund_zu(befund, nr)
        self.assertEqual("nein", z.im_paket)
        self.assertEqual(4713, self.auf.post_id_von(nr))

    # --- PN19 --------------------------------------------------------------
    def test_pn19_ersetzte_versionen_bleiben_in_ruhe(self):
        """
        PN19: Vorgabe ist 'nur aktive'. Eine ersetzte Version ist
        Vergangenheit; sie anzufassen waere eine Aenderung an etwas, das
        niemand mehr liest.
        """
        alt = self.auf.annotation(
            auswahl=_auswahl(ANKER_4711, "Bahnhof", 20), geloescht=True)
        self._nachtrag().lauf(ausfuehren=True)
        self.assertIsNone(self.auf.post_id_von(alt))
        # ... und mit auch_ersetzte=True sehr wohl.
        self._nachtrag(auch_ersetzte=True).lauf(ausfuehren=True)
        self.assertEqual(4711, self.auf.post_id_von(alt))

    # --- PN25 --------------------------------------------------------------
    def test_pn25_der_echte_forenbeitrag(self):
        """
        PN25: Der Aufbau eines Forenbeitrags, wie Alex ihn am 28.08.2026
        uebergeben hat - beide Kennungen, die innere zuerst erreicht.
        """
        nr = self.auf.annotation(
            seite=SEITE_ECHT_FORUM,
            auswahl=_auswahl("./div[1]/x", "Hauptbahnhof"))
        befund = self._nachtrag(beleg=nr).lauf(ausfuehren=True)
        z = self._befund_zu(befund, nr)
        self.assertEqual("beitrag", z.art)
        self.assertEqual(1164441, z.post_id)

    # --- PN26 --------------------------------------------------------------
    def test_pn26_die_echte_private_nachricht(self):
        """
        PN26: Der Aufbau einer privaten Nachricht (pmsnew), ebenfalls von
        Alex am 28.08.2026.

        DAS IST DER FALL, DER DIE WEISUNG RELATIVIERT. Alex hat als Weg die
        INNERE Kennung genannt ('<div class="box" id="pp<post_id>">'). Hier
        traegt die '.box' GAR KEINE Kennung - die Nummer steht nur am
        aeusseren '<div id="p120862" class="blockpost">'. Haette man die
        Weisung woertlich als einzigen Weg genommen, waeren ausgerechnet die
        privaten Nachrichten leer geblieben, und dort haengt am post_id der
        Gespraechspartner. Beide Formen gelten deshalb.

        Zugleich: die Adresse beginnt mit '/forum/pmsnew.php', die Art muss
        also 'pn' sein - sonst wuerde die Nummer spaeter in der falschen
        Zeittabelle gesucht (uid_posts statt uid_pms_posts; getrennte,
        UEBERLAPPENDE ID-Raeume).
        """
        nr = self.auf.annotation(
            seite=SEITE_ECHT_PN,
            auswahl=_auswahl("./div[1]/x", "ab Freitag in Koeln"))
        befund = self._nachtrag(beleg=nr).lauf(ausfuehren=True)
        z = self._befund_zu(befund, nr)
        self.assertEqual("pn", z.art,
                         "'/forum/pmsnew.php' muss als PN erkannt werden.")
        self.assertEqual(120862, z.post_id)

    # --- PN27: GEGENPROBE zu PN26 ------------------------------------------
    def test_pn27_die_leere_box_wird_nicht_zur_nummer(self):
        """
        PN27: Gegenprobe. In der PN-Ansicht liegt zwischen der Markierung und
        der Kennung eine '<div class="box">' OHNE id. Sie darf den Aufstieg
        weder abbrechen noch selbst eine Nummer liefern. Ohne diese Probe
        waere PN26 auch mit einer Erkennung gruen, die die erste beste
        '.box' nimmt.
        """
        from report_render.absatz_finder import AbsatzFinder
        finder = AbsatzFinder.aus_seiten_html(_html(BODY_ECHT_PN))
        kaesten = finder._wurzel.xpath('//div[@class="box"]')
        self.assertEqual(1, len(kaesten),
                         "Der Aufbau ist nicht mehr der uebergebene.")
        self.assertEqual("", kaesten[0].get("id") or "",
                         "Die '.box' der PN-Ansicht traegt KEINE Kennung - "
                         "genau darum muss die aeussere gelten.")
        self.assertEqual(120862, AbsatzFinder.post_id_von(kaesten[0]))

    # --- PN20 --------------------------------------------------------------
    def test_pn20_ohne_seitenabzug_wird_nichts_erfunden(self):
        """PN20: Keine Seite, keine Nummer - und der Beleg sagt es."""
        nr = self.auf.annotation(
            seite="/forum/gibtsnicht.php",
            auswahl=_auswahl(ANKER_4711, "Bahnhof", 20))
        befund = self._nachtrag().lauf(ausfuehren=False)
        z = self._befund_zu(befund, nr)
        self.assertIn("Seitenabzug", z.ergebnis + z.bemerkung)
        self.assertIsNone(z.post_id)


class WerkzeugTests(unittest.TestCase):
    """
    Das Werkzeug selbst - Rueckgabewerte und Protokoll.

    ES WIRD OHNE '--ausfuehren' GEFAHREN. Der scharfe Weg fuehrt durch den
    Wartungsvorbehalt (maintenance/wartungsvorbehalt.py); der verlangt ein
    Wartungsfenster oder ein Terminal und gehoert zu jenem Modul, nicht
    hierher. Was dieser Test prueft, ist die Verdrahtung: Argumente,
    Ausgabe, Rueckgabewert.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.auf = Aufbau(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def _fahren(self, *argumente):
        import io
        import contextlib
        from tools import postid_nachtragen
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            code = postid_nachtragen.main(list(argumente))
        return code, puffer.getvalue()

    # --- PN21 --------------------------------------------------------------
    def test_pn21_offene_faelle_geben_rueckgabewert_1(self):
        """
        PN21: Ein Lauf, in dem etwas ungeklaert bleibt, meldet das ueber den
        Rueckgabewert. Wer nur auf 0 prueft, soll den Unterschied sehen.
        """
        self.auf.annotation(
            auswahl=_auswahl(ANKER_KAPUTT, "Das Wetter war schoen"))
        code, text = self._fahren("--evidence", str(self.auf.evidence),
                                  "--forensic", str(self.auf.forensic))
        self.assertEqual(1, code)
        self.assertIn("VON HAND ZU KLAEREN", text)

    # --- PN22 --------------------------------------------------------------
    def test_pn22_das_protokoll_ist_die_konsole(self):
        """
        PN22: '--protokoll' schreibt DIESELBEN Zeilen, die auf der Konsole
        standen. Zwei Protokolle, die sich unterscheiden koennen, waeren
        zwei Wahrheiten (Weisung Alex: "das ich mir aber auch per tee von
        der Konsole holen kann").
        """
        self.auf.annotation(auswahl=_auswahl(ANKER_4711, "Bahnhof", 20))
        datei = self.dir / "lauf.log"
        _code, text = self._fahren("--evidence", str(self.auf.evidence),
                                   "--forensic", str(self.auf.forensic),
                                   "--protokoll", str(datei))
        self.assertTrue(datei.is_file())
        self.assertEqual(text.rstrip("\n").split("\n"),
                         datei.read_text(encoding="utf-8").rstrip("\n").split("\n"))

    # --- PN23 --------------------------------------------------------------
    def test_pn23_fehlende_datei_bricht_ab_und_sagt_es(self):
        """PN23: Kein Seitenabzug, kein Lauf - und die Meldung nennt ihn."""
        code, text = self._fahren("--evidence", str(self.auf.evidence),
                                  "--forensic", str(self.dir / "fehlt.db"))
        self.assertEqual(2, code)
        self.assertIn("ABGEBROCHEN", text)

    # --- PN24 --------------------------------------------------------------
    def test_pn24_jede_gepruefte_zeile_steht_im_protokoll(self):
        """
        PN24: GR1 auf der Ausgabeseite. Auch die Zeilen, zu denen nichts
        gefunden wurde, stehen einzeln da - sonst waere der Lauf am Ende
        eine Zahl ohne Belege.
        """
        gut = self.auf.annotation(auswahl=_auswahl(ANKER_4711, "Bahnhof", 20))
        schlecht = self.auf.annotation(
            auswahl=_auswahl(ANKER_KAPUTT, "Zeppelin ueber Wanne-Eickel"))
        _code, text = self._fahren("--evidence", str(self.auf.evidence),
                                   "--forensic", str(self.auf.forensic))
        self.assertIn("#%-7d" % gut, text)
        self.assertIn("#%-7d" % schlecht, text)


if __name__ == "__main__":
    unittest.main()
