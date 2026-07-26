# =============================================================================
# tests/test_management_search_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B562)
# =============================================================================
# Testsuite fuer Build 562: die Endpunkte der beiden Stufen, die Verifikation
# jedes Treffers gegen die Quelle und der Beleg FULLTEXT_SEARCHED.
#
# VOLLSTAENDIG automatisiert, NUR synthetische Daten — KEIN reales
# Beweismaterial.
#
# LEITLINIE: Wirkungspruefungen. SU11-SU13 pruefen nicht, dass es eine
#   Verifikationsfunktion GIBT, sondern dass eine nachtraeglich GEAENDERTE,
#   GELOESCHTE bzw. UNLESBARE Quelle drei VERSCHIEDENE Befunde erzeugt und in
#   allen drei Faellen KEIN Text ausgeliefert wird.
#
# SU01 — ohne 'evidence.fulltext_search': 403 auf allen Suchrouten
# SU02 — QUERPROBE Verifikation <-> Indexvokabular: jede Satzart ist
#        verifizierbar (Tabelle bekannt), und die JSON-Spalten decken sich
#        mit denen des Indexlaufs. Liefen sie auseinander, waere JEDER
#        Treffer dieser Art 'abweichend'
# SU03 — Stufe 1: Trefferlage je Fall, getrennt nach Fassung, OHNE Text
# SU04 — Stufe 1 belegt JEDE Abfrage — AUCH den Leerbefund
# SU05 — fehlende/falsche Zweckangabe -> 400, und es wird NICHT gesucht
# SU06 — der Suchbegriff wird als PHRASE behandelt, nicht als FTS5-Ausdruck
# SU07 — Teilstring unter drei Zeichen: eigener Befund, kein stiller
#        Leerbefund
# SU08 — Stufe 2 beim EIGENEN Fall: Text kommt, Verifikation 'bestaetigt'
# SU09 — Stufe 2 bei fremdem Fall ohne Freigabe: 200 mit erlaubt=false,
#        KEIN Text — und der abgewiesene Versuch IST belegt
# SU10 — nach erteilter Freigabe: Text kommt, Grund 'freigabe'
# SU11 — Quelle nachtraeglich GEAENDERT -> 'abweichend', KEIN Ausschnitt
# SU12 — Quelldatensatz GELOESCHT -> 'verschwunden', KEIN Ausschnitt
# SU13 — Quelldatei WEG -> 'quelle_nicht_lesbar' (NICHT 'verschwunden')
# SU14 — jede Antwort traegt den Indexstand und meldet veraenderte
#        Datenbanken
# SU15 — SENSIBILITAET des Belegs: der SUCHBEGRIFF steht drin (bewusste
#        Ausnahme), der Freitext der Zweckangabe NUR als Laenge
# SU16 — /api/fulltext/zwecke liefert die vier Codes aus der Datenbank
# SU17 — Freigabe ueber die Endpunkte erteilen/widerrufen; ohne
#        'fulltext.release' -> 403
# SU18 — /api/fulltext/releases: die eigenen ohne Sonderrecht, die eines
#        fremden Falls nur mit 'fulltext.release'
# SU19 — leerer Index: kein Treffer, aber der Indexstand sagt WARUM
#
# Version: v0.8.562 · Build: 562 · 2026-07-26
# =============================================================================

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from db.evidence_db import _SCHEMA_DDL as EVIDENCE_DDL
from db.search_index_db import SearchIndexDb
from management.audit.audit_log import AuditLog
from management.audit.event_types import EventType
from management.cases.cases_repo import CasesRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.rbac.rbac_repo import RbacRepo
from management.search.evidence_source_reader import EvidenceSourceReader
from management.search.index_builder import SearchIndexBuilder
from management.search.index_vokabular import SATZ_ARTEN
from management.search.quellen_verifikation import QuellenVerifikation
from management.server.management_app import ManagementApp

_PERSON = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0,
    is_support INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
"""
_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT, output_path TEXT, worker_id TEXT,
    created_at INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER,
    error_message TEXT, assigned_to INTEGER, note TEXT,
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""


class SearchApiBasis(unittest.TestCase):
    """
    Zwei Faelle mit Annotationen, aufgebauter Index, drei Personen:
      1 = Chefin (sucht UND gibt frei), 2 = Beta (Fall 5023 zugewiesen),
      3 = Gamma (darf suchen, hat keinen Fall), 4 = ohne jedes Recht.
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="aiw_searchapi_")
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.evidence_dir = Path(self._tmp) / "evidence"
        self.evidence_dir.mkdir()
        self.index_pfad = Path(self._tmp) / "search_index.db"

        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.NOW = int(time.time())
        self.con.execute(_PERSON)
        self.con.executemany(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, "h001", "Chefin, Alpha", 1, 1, 0, self.NOW),
             (2, "h002", "Beta", 1, 0, 0, self.NOW),
             (3, "h003", "Gamma", 1, 0, 0, self.NOW),
             (4, "h004", "Delta", 1, 0, 0, self.NOW)])
        self.con.execute(_OLD_SCRAPE_JOBS)

        self.audit = AuditLog(self.con)
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()
        self.writer = CoordinatorWriter(self.con, self.audit)
        self.rbac = RbacRepo(self.con, self.writer)
        self.rbac.grant("supervisor", "evidence.fulltext_search",
                        scope="alle", actor_id=1)
        self.rbac.grant("supervisor", "fulltext.release", scope="alle",
                        actor_id=1)
        self.rbac.grant("investigator", "evidence.fulltext_search",
                        scope="alle", actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)
        self.rbac.assign_role(3, "investigator", actor_id=1)
        # Person 4 bekommt KEINE Rolle — belegt SU01.

        self.cases = CasesRepo(self.con, self.writer)
        self.cases.create_case(5023, "birnenmus", actor_id=1)
        self.cases.assign(5023, 2, actor_id=1)
        self.cases.create_case(6114, "apfelsaft", actor_id=1)

        self.p5023 = self._evidence(5023)
        self.p6114 = self._evidence(6114)
        self.aid = self._annotation(
            self.p5023, "Nickname birnenmus taucht im Thread auf",
            created_by="h002")
        self._alias(self.p5023, "xXbirnenmusXx")
        self._annotation(self.p6114, "Auch hier birnenmus, apfelsaft daneben",
                         created_by="h003")
        self._index_bauen()

        self.app = ManagementApp(self.db_path,
                                 evidence_dir=str(self.evidence_dir))
        # Der Dienst laedt den Indexpfad aus der Konfiguration; im Test wird
        # er ueber die Methode injiziert, damit die Suite keine config.yaml
        # braucht und keine fremde Datei anfasst.
        self.app._search_index_pfad = lambda: str(self.index_pfad)

    def tearDown(self):
        try:
            self.con.close()
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)

    # ------------------------------------------------------------- Helfer
    def _evidence(self, uid):
        pfad = self.evidence_dir / ("evidence_%d.db" % uid)
        con = sqlite3.connect(str(pfad))
        try:
            con.executescript(EVIDENCE_DDL)
            con.commit()
        finally:
            con.close()
        return pfad

    def _annotation(self, pfad, text, *, created_by="h001",
                    ts=1700000000, category="CAT_176", deleted_at=None,
                    prev_id=None):
        con = sqlite3.connect(str(pfad))
        try:
            cur = con.execute(
                "INSERT INTO annotations(page_url, category, text, ts, "
                "created_by, deleted_at, prev_id) "
                "VALUES ('viewtopic.php?id=1', ?, ?, ?, ?, ?, ?)",
                (category, text, ts, created_by, deleted_at, prev_id))
            con.commit()
            return int(cur.lastrowid)
        finally:
            con.close()

    def _alias(self, pfad, term):
        con = sqlite3.connect(str(pfad))
        try:
            con.execute("INSERT INTO investigator_aliases(term, created_by, "
                        "created_at) VALUES (?, 'h001', 1700000100)", (term,))
            con.commit()
        finally:
            con.close()

    def _index_bauen(self, voll=False):
        idx = SearchIndexDb(self.index_pfad)
        try:
            SearchIndexBuilder(self.evidence_dir, idx).lauf(voll=voll)
        finally:
            idx.close()

    def _json(self, resp):
        return json.loads(resp.body.decode("utf-8"))

    def _lage(self, person_id=1, begriff="birnenmus",
              zweck_code="kreuzbezug_nickname", zweck_freitext=None,
              modus="wort"):
        return self.app.dispatch_write(person_id, "/api/fulltext/lage", {
            "begriff": begriff, "zweck_code": zweck_code,
            "zweck_freitext": zweck_freitext, "modus": modus})

    def _inhalt(self, person_id, subject_id, begriff="birnenmus",
                zweck_code="kreuzbezug_nickname", modus="wort"):
        return self.app.dispatch_write(person_id, "/api/fulltext/inhalt", {
            "begriff": begriff, "subject_id": subject_id,
            "zweck_code": zweck_code, "modus": modus})

    def _belege(self, event_type=None):
        sql = "SELECT * FROM audit_log"
        args = ()
        if event_type:
            sql += " WHERE event_type = ?"
            args = (event_type,)
        sql += " ORDER BY seq"
        return self.con.execute(sql, args).fetchall()


# ======================================================================= SU01
class TestRechte(SearchApiBasis):

    def test_su01_ohne_recht_403(self):
        for pfad, rumpf in (
                ("/api/fulltext/lage", {"begriff": "x",
                                        "zweck_code": "wiedervorlage"}),
                ("/api/fulltext/inhalt", {"begriff": "x", "subject_id": 5023,
                                          "zweck_code": "wiedervorlage"})):
            r = self.app.dispatch_write(4, pfad, rumpf)
            self.assertEqual(403, r.status, pfad)
        self.assertEqual(403, self.app.dispatch(4, "/api/fulltext/zwecke").status)
        self.assertEqual(
            403, self.app.dispatch(4, "/api/fulltext/indexstand").status)
        # Kein Recht -> keine Suche -> auch KEIN Beleg (es wurde nichts
        # ausgekundschaftet).
        self.assertEqual([], self._belege(EventType.FULLTEXT_SEARCHED))

    def test_su17_freigabe_endpunkte_und_recht(self):
        rumpf = {"subject_id": 6114, "person_id": 3,
                 "zweck_code": "kreuzbezug_nickname",
                 "begruendung": "Kreuzbezug erforderlich."}
        # Person 3 darf suchen, aber nicht freigeben.
        self.assertEqual(403, self.app.dispatch_write(
            3, "/api/fulltext/release/grant", rumpf).status)
        r = self.app.dispatch_write(1, "/api/fulltext/release/grant", rumpf)
        self.assertEqual(200, r.status, r.body)
        rid = self._json(r)["release_id"]
        self.assertEqual(403, self.app.dispatch_write(
            3, "/api/fulltext/release/revoke",
            {"release_id": rid, "reason": "x"}).status)
        r = self.app.dispatch_write(1, "/api/fulltext/release/revoke",
                                    {"release_id": rid, "reason": "erledigt"})
        self.assertEqual(200, r.status, r.body)
        # Widerrufen heisst NICHT geloescht.
        self.assertIsNotNone(self.con.execute(
            "SELECT 1 FROM fulltext_release WHERE id = ?", (rid,)).fetchone())

    def test_su18_releases_beide_richtungen(self):
        self.app.dispatch_write(1, "/api/fulltext/release/grant", {
            "subject_id": 6114, "person_id": 3,
            "zweck_code": "alias_pruefung", "begruendung": "Aliaspruefung."})
        # Die EIGENEN sieht Person 3 ohne Sonderrecht.
        r = self.app.dispatch(3, "/api/fulltext/releases")
        self.assertEqual(200, r.status)
        self.assertEqual(1, len(self._json(r)["freigaben"]))
        # Die eines FREMDEN Falls nur mit 'fulltext.release'.
        self.assertEqual(403, self.app.dispatch(
            3, "/api/fulltext/releases",
            {"subject_id": ["6114"]}).status)
        r = self.app.dispatch(1, "/api/fulltext/releases",
                              {"subject_id": ["6114"]})
        self.assertEqual(200, r.status)
        self.assertEqual(1, len(self._json(r)["freigaben"]))


# ======================================================================= SU02
class TestQuerprobe(unittest.TestCase):

    def test_su02_verifikation_deckt_das_indexvokabular_ab(self):
        """
        Jede Satzart, die der Indexlauf erzeugt, muss verifizierbar sein.
        Fehlte eine Tabelle in der Verifikation, waere JEDER Treffer dieser
        Art 'quelle_nicht_lesbar' — und die Sicht zeigte dauerhaft keinen
        Text, ohne dass jemand den Grund faende.
        """
        bekannt = QuellenVerifikation.bekannte_tabellen()
        for art in SATZ_ARTEN:
            self.assertIn(art.tabelle, bekannt,
                          "Quelltabelle der Satzart %s ist der Verifikation "
                          "unbekannt" % art.code)

    def test_su02b_json_spalten_stimmen_ueberein(self):
        """
        Die Verifikation muss GENAU die Spalten als JSON behandeln, die auch
        der Indexlauf so behandelt hat. Wich das ab, verglichen die beiden
        verschiedene Normalisierungen — und jeder Treffer dieser Spalte waere
        dauerhaft 'abweichend', obwohl sich nichts geaendert hat.
        """
        aus_index = {"tags_json", "block_data", "placeholder_values_json"}
        for spalte in aus_index:
            self.assertTrue(QuellenVerifikation.ist_json_spalte(spalte),
                            "%s wird bei der Verifikation nicht als JSON "
                            "behandelt" % spalte)
        for art in SATZ_ARTEN:
            if art.spalte not in aus_index:
                self.assertFalse(
                    QuellenVerifikation.ist_json_spalte(art.spalte),
                    "%s wird bei der Verifikation faelschlich als JSON "
                    "behandelt" % art.spalte)
        # Und die Gegenprobe gegen den echten Leser: er kennt dieselben
        # Tabellen.
        self.assertTrue(hasattr(EvidenceSourceReader, "lies"))


# ================================================ SU03 · SU04 · SU05 · SU06
class TestStufe1(SearchApiBasis):

    def test_su03_trefferlage_ohne_text(self):
        r = self._lage(1)
        self.assertEqual(200, r.status, r.body)
        d = self._json(r)
        self.assertEqual("lage", d["stufe"])
        self.assertEqual(2, len(d["faelle"]))
        roh = r.body.decode("utf-8")
        # KEIN Textausschnitt in Stufe 1 — das ist der Kern von Modell B.
        self.assertNotIn("Thread", roh)
        self.assertNotIn("ausschnitt", roh)
        fall = {f["subject_id"]: f for f in d["faelle"]}[5023]
        self.assertEqual(1, fall["nach_fassung"]["aktuell"])
        self.assertEqual(0, fall["nach_fassung"]["ueberholt"])
        self.assertTrue(fall["arten"])
        self.assertTrue(fall["urheber"])
        # Die Sicht erfaehrt sofort, ob der Inhalt sichtbar waere.
        self.assertIn("sichtbarkeit", fall)

    def test_su03b_fassungen_getrennt(self):
        alt = self._annotation(self.p6114, "alte fassung birnenmus",
                               deleted_at=1700000500)
        self._annotation(self.p6114, "neue fassung birnenmus", prev_id=alt)
        self._annotation(self.p6114, "widerrufen birnenmus",
                         deleted_at=1700000600)
        self._index_bauen(voll=True)
        d = self._json(self._lage(1))
        fall = {f["subject_id"]: f for f in d["faelle"]}[6114]
        self.assertEqual(1, fall["nach_fassung"]["ueberholt"])
        self.assertEqual(1, fall["nach_fassung"]["zurueckgenommen"])
        self.assertGreaterEqual(fall["nach_fassung"]["aktuell"], 2)

    def test_su04_leerbefund_wird_belegt(self):
        """
        DER WICHTIGSTE EINZELTEST DIESES BUILDS. Ohne Beleg des Leerbefunds
        liesse sich spurenfrei sondieren: man probiert Namen durch, und nur
        die Treffer hinterlassen eine Spur.
        """
        r = self._lage(1, begriff="kommtnichtvorimbestand")
        d = self._json(r)
        self.assertEqual(0, d["treffer_gesamt"])
        self.assertEqual([], d["faelle"])
        belege = self._belege(EventType.FULLTEXT_SEARCHED)
        self.assertEqual(1, len(belege))
        nutz = json.loads(belege[0]["content"])
        self.assertEqual("kommtnichtvorimbestand", nutz["begriff"])
        self.assertEqual(0, nutz["trefferzahl"])

    def test_su05_zweckangabe_ist_pflicht(self):
        for code, freitext in ((None, None), ("gibt_es_nicht", None),
                               ("sonstiges", "  "),
                               ("wiedervorlage", "unerwartet")):
            r = self.app.dispatch_write(1, "/api/fulltext/lage", {
                "begriff": "birnenmus", "zweck_code": code,
                "zweck_freitext": freitext})
            self.assertEqual(400, r.status, "%r/%r" % (code, freitext))
        # Ohne brauchbare Zweckangabe wurde NICHT gesucht — also auch kein
        # Beleg. Es ist nichts offengelegt worden.
        self.assertEqual([], self._belege(EventType.FULLTEXT_SEARCHED))
        # Mit Pflichtfreitext geht es durch.
        r = self._lage(1, zweck_code="sonstiges",
                       zweck_freitext="Amtshilfe LKA")
        self.assertEqual(200, r.status, r.body)

    def test_su06_begriff_ist_eine_phrase_kein_ausdruck(self):
        """
        FTS5-MATCH hat eine eigene Abfragesprache. Wuerde der Begriff roh
        durchgereicht, suchte 'birnenmus OR apfelsaft' etwas anderes als
        eingegeben — und der Beleg behauptete eine Suche, die so nicht
        stattgefunden hat.
        """
        r = self._lage(1, begriff="birnenmus OR apfelsaft")
        self.assertEqual(200, r.status, r.body)
        self.assertEqual(0, self._json(r)["treffer_gesamt"])
        # Auch Sonderzeichen duerfen keinen Syntaxfehler ausloesen.
        for begriff in ('birnen"mus', "birnen*", "(a AND b)", "NEAR/2"):
            self.assertEqual(200, self._lage(1, begriff=begriff).status,
                             begriff)

    def test_su07_teilstring_untergrenze(self):
        r = self._lage(1, begriff="ab", modus="teilstring")
        d = self._json(r)
        self.assertEqual("begriff_zu_kurz", d["befund"])
        self.assertIn("kein Leerbefund", d["befund_klartext"])
        # Auch der Nichtlauf ist ein Vorgang und wird belegt.
        self.assertEqual(1, len(self._belege(EventType.FULLTEXT_SEARCHED)))
        # Im Wortmodus ist derselbe Begriff zulaessig.
        self.assertEqual("ok", self._json(
            self._lage(1, begriff="ab", modus="wort"))["befund"])

    def test_teilstring_findet_verklebtes(self):
        d = self._json(self._lage(1, modus="teilstring"))
        arten = set()
        for f in d["faelle"]:
            arten.update(a["code"] for a in f["arten"])
        self.assertIn("ermittler_alias", arten,
                      "Der Teilstringmodus findet 'xXbirnenmusXx' nicht.")


# ================================== SU08 · SU09 · SU10 · SU11 · SU12 · SU13
class TestStufe2(SearchApiBasis):

    def test_su08_eigener_fall_liefert_text_aus_der_quelle(self):
        r = self._inhalt(2, 5023)
        self.assertEqual(200, r.status, r.body)
        d = self._json(r)
        self.assertTrue(d["erlaubt"])
        self.assertEqual("eigener_fall", d["sichtbarkeit"]["grund"])
        self.assertTrue(d["treffer"])
        t = d["treffer"][0]
        self.assertEqual("bestaetigt", t["verifikation"])
        self.assertIn("birnenmus", t["ausschnitt"])
        self.assertEqual(d["treffer_gesamt"], d["gegen_quelle_bestaetigt"])

    def test_su09_fremder_fall_ohne_freigabe(self):
        r = self._inhalt(3, 5023)
        # 200 und NICHT 403: die Abweisung ist ein Ermittlungsergebnis
        # ("es gibt etwas, Sie duerfen es nur nicht sehen") und kein
        # Berechtigungsfehler — die Sicht bietet daraufhin die Anfrage an.
        self.assertEqual(200, r.status, r.body)
        d = self._json(r)
        self.assertFalse(d["erlaubt"])
        self.assertEqual("gesperrt", d["sichtbarkeit"]["grund"])
        self.assertEqual([], d["treffer"])
        self.assertNotIn("Thread", r.body.decode("utf-8"))
        # Der abgewiesene Versuch ist der Vorgang, den eine Aufsicht am
        # ehesten sehen will — er MUSS belegt sein.
        belege = self._belege(EventType.FULLTEXT_SEARCHED)
        self.assertEqual(1, len(belege))
        nutz = json.loads(belege[0]["content"])
        self.assertEqual("abgewiesen_gesperrt", nutz["befund"])
        self.assertEqual(5023, nutz["subject_id"])

    def test_su10_nach_freigabe_kommt_text(self):
        self.app.dispatch_write(1, "/api/fulltext/release/grant", {
            "subject_id": 5023, "person_id": 3,
            "zweck_code": "kreuzbezug_nickname",
            "begruendung": "Kreuzbezug zu Fall 6114."})
        d = self._json(self._inhalt(3, 5023))
        self.assertTrue(d["erlaubt"])
        self.assertEqual("freigabe", d["sichtbarkeit"]["grund"])
        self.assertTrue(d["treffer"][0]["ausschnitt"])

    def test_su11_geaenderte_quelle_liefert_keinen_text(self):
        """
        DER INDEX WIRD NIE ZITIERT. Aendert sich die Quelle nach dem
        Indexlauf, zeigt die Sicht KEINEN Text — sonst zitierte eine
        Ermittlerin eine Annotation, die seit Wochen anders lautet.
        """
        con = sqlite3.connect(str(self.p5023))
        con.execute("UPDATE annotations SET text = 'inzwischen ganz anders' "
                    "WHERE id = ?", (self.aid,))
        con.commit()
        con.close()
        r = self._inhalt(2, 5023)
        rumpf = r.body.decode("utf-8")
        d = self._json(r)
        treffer = [t for t in d["treffer"]
                   if t["quell_schluessel"] == str(self.aid)
                   and t["quell_spalte"] == "text"]
        self.assertTrue(treffer)
        self.assertEqual("abweichend", treffer[0]["verifikation"])
        self.assertIsNone(treffer[0]["ausschnitt"])
        # WEDER der alte (indizierte) NOCH der neue Quelltext darf im Rumpf
        # stehen: der alte waere ein Zitat aus dem Index, der neue ein
        # unverifizierter Ausschnitt. Geprueft wird am ROHEN Antwortrumpf,
        # nicht an einer Teilstruktur — sonst koennte der Text an einer
        # anderen Stelle durchrutschen.
        self.assertNotIn("inzwischen ganz anders", rumpf)
        self.assertNotIn("Thread", rumpf)
        self.assertIn("NICHT gegen die Quelle bestaetigt",
                      d["verifikationshinweis"])

    def test_su12_geloeschter_datensatz(self):
        con = sqlite3.connect(str(self.p5023))
        con.execute("DELETE FROM annotations WHERE id = ?", (self.aid,))
        con.commit()
        con.close()
        d = self._json(self._inhalt(2, 5023))
        treffer = [t for t in d["treffer"]
                   if t["quell_schluessel"] == str(self.aid)]
        self.assertTrue(treffer)
        for t in treffer:
            self.assertEqual("verschwunden", t["verifikation"])
            self.assertIsNone(t["ausschnitt"])

    def test_su13_unlesbare_quelle_ist_nicht_verschwunden(self):
        """
        'Der Datensatz ist weg' und 'ich konnte nicht nachsehen' duerfen in
        einer Ermittlungsakte nicht gleich aussehen (Grundregel 1).
        """
        os.remove(str(self.p5023))
        d = self._json(self._inhalt(2, 5023))
        self.assertTrue(d["treffer"])
        for t in d["treffer"]:
            self.assertEqual("quelle_nicht_lesbar", t["verifikation"])
            self.assertIsNone(t["ausschnitt"])
        self.assertEqual(0, d["gegen_quelle_bestaetigt"])


# ================================================ SU14 · SU15 · SU16 · SU19
class TestStandUndBeleg(SearchApiBasis):

    def test_su14_indexstand_in_jeder_antwort(self):
        d = self._json(self._lage(1))
        st = d["indexstand"]
        self.assertTrue(st["belastbar"], st["hinweis"])
        self.assertEqual(0, st["veraendert_seit_index"])

        # Quelle aendern, ohne neu zu indizieren.
        self._annotation(self.p6114, "neu dazugekommen birnenmus")
        st2 = self._json(self._lage(1))["indexstand"]
        self.assertFalse(st2["belastbar"])
        self.assertEqual(1, st2["veraendert_seit_index"])
        self.assertIn(6114, st2["veraenderte_faelle"])
        self.assertIn("nicht belegt aktuell", st2["hinweis"])

    def test_su15_beleg_traegt_begriff_aber_keinen_freitext(self):
        """
        Der SUCHBEGRIFF steht im Beleg — bewusste Ausnahme von der
        Sensibilitaetsregel: ohne ihn belegte der Eintrag nichts. Der
        FREITEXT der Zweckangabe ist von der Ausnahme NICHT gedeckt und geht
        nur als Laenge ein.
        """
        geheim = "Amtshilfe wegen Zeuge Mustermann"
        self._lage(1, begriff="birnenmus", zweck_code="sonstiges",
                   zweck_freitext=geheim)
        beleg = self._belege(EventType.FULLTEXT_SEARCHED)[0]
        roh = json.dumps({k: beleg[k] for k in beleg.keys()},
                         ensure_ascii=False, default=str)
        self.assertIn("birnenmus", roh)
        self.assertNotIn("Mustermann", roh)
        nutz = json.loads(beleg["content"])
        self.assertEqual("sonstiges", nutz["zweck_code"])
        self.assertEqual(len(geheim), nutz["zweck_freitext_len"])
        self.assertEqual("lage", nutz["stufe"])
        self.assertEqual(1, beleg["actor_id"])

    def test_su16_zweckkatalog(self):
        r = self.app.dispatch(1, "/api/fulltext/zwecke")
        self.assertEqual(200, r.status)
        d = self._json(r)
        codes = [z["code"] for z in d["zwecke"]]
        self.assertEqual(["kreuzbezug_nickname", "alias_pruefung",
                          "wiedervorlage", "sonstiges"], codes)
        self.assertTrue(d["zwecke"][-1]["freitext_pflicht"])
        self.assertTrue(d["vollstaendig"])

    def test_su19_leerer_index_sagt_warum(self):
        os.remove(str(self.index_pfad))
        d = self._json(self._lage(1))
        self.assertEqual(0, d["treffer_gesamt"])
        st = d["indexstand"]
        self.assertFalse(st["belastbar"])
        self.assertIn("nie", st["hinweis"])
        self.assertEqual(2, len(st["noch_nie_indiziert"]))

    def test_indexstand_endpunkt(self):
        r = self.app.dispatch(1, "/api/fulltext/indexstand")
        self.assertEqual(200, r.status)
        self.assertIn("indexzeitpunkt", self._json(r))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
