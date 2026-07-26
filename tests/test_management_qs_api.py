# =============================================================================
# tests/test_management_qs_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3C
# =============================================================================
# Testsuite fuer Build 541: der SCHREIBPFAD der QS-Stichprobe, die
# Selbstpruefungssperre und die drei Endpunkte.
#
# Die reine Ziehung ist in Build 540 geprueft (tests/test_qs_sampler.py, 24
# Tests, davon 17 ohne Datenbank). Diese Suite prueft ausschliesslich das, was
# erst mit echten Daten und echten Personen sichtbar wird.
#
# REPOSITORY:
#   QR01 — Eine Ziehung schreibt qs_sample UND qs_sample_item in EINER
#          Transaktion; die Positionen tragen die Ziehungsreihenfolge.
#   QR02 — Der KEIM steht in der Zeile UND im Audit-Beleg. Ohne ihn im Beleg
#          waere die Reproduzierbarkeit eine Eigenschaft der Datenbank und
#          keine des Protokolls.
#   QR03 — Gezogen wird NUR aus abgeschlossenen Faellen. Ein laufender Fall
#          gehoert nicht in die Grundgesamtheit — dort waere eine Luecke ein
#          Zwischenstand und kein Befund.
#   QR04 — DIE SELBSTPRUEFUNGSSPERRE greift bei ALLEN DREI Beruehrungsarten:
#          aktuelle Zuweisung, Fallhistorie (case_events), Ergebnisbewertung.
#   QR05 — SIE UEBERLEBT EINE UMZUWEISUNG. Wer nur cases.assigned_to prueft,
#          macht die frueher zustaendige Person zur Prueferin ihrer eigenen
#          Arbeit — genau diese Luecke schliesst der Test.
#   QR05b— MITWIRKUNGS_ und STEUERUNGS_EVENT_KINDS ergeben ZUSAMMEN genau das
#          Vokabular von case_events. Sonst fiele eine Ereignisart aus der
#          Betrachtung, ohne dass jemand darueber entschieden haette.
#   QR06 — Wer den Fall NICHT beruehrt hat, darf pruefen.
#   QR07 — Ein Pruefergebnis ohne Begruendung wird abgewiesen, ein unbekanntes
#          Ergebnis ebenso.
#   QR08 — Ein Ergebnis zu einem NICHT gezogenen Fall ist ZULAESSIG, traegt
#          aber 'ausserhalb_der_ziehung' — in der Zeile UND im Audit-Beleg.
#   QR09 — IM AUDIT-BELEG STEHT NIE DER WORTLAUT DER BEGRUENDUNG, nur ihre
#          Laenge.
#   QR10 — Zwei Ergebnisse zu demselben Fall derselben Ziehung: abgewiesen,
#          mit einer Meldung, die den Weg nennt (neue Ziehung).
#   QR11 — Ohne CoordinatorWriter gibt es KEINEN Schreibweg.
#   QR12 — nachziehen() bestaetigt eine unveraenderte Lage und benennt eine
#          veraenderte im Klartext.
#   QR13 — liste() weist den Fortschritt aus (geprueft/offen) und traegt die
#          Zweckbindung mit.
#
# ENDPUNKTE:
#   QE01 — GET /api/qs ohne Recht -> 403, nennt 'qs.view'.
#   QE02 — GET /api/qs mit Recht -> 200, Zweckbindung wortgleich, je Fall
#          'darf_pruefen' + Sperrgruende.
#   QE03 — POST /api/qs/draw ohne 'qs.edit' -> 403 (auch mit 'qs.view').
#   QE04 — POST /api/qs/draw ohne Keim erzeugt einen und schreibt ihn mit —
#          es entsteht NIE eine Ziehung ohne Keim.
#   QE05 — POST /api/qs/review bei SELBSTPRUEFUNG -> 403 (NICHT 400): an der
#          Eingabe ist nichts zu bessern.
#   QE06 — POST /api/qs/review mit fehlender Begruendung -> 400.
#   QE07 — GET /api/qs/recheck -> 200 mit 'stimmt'; ohne sample_id -> 400.
#   QE08 — GET /api/qs schreibt NICHTS (audit_log-Spitze unveraendert).
#   QE09 — M034 hat 'qs.view' und 'qs.edit' geseedet.
#
# Version: v0.8.541 · Build: 541 · 2026-07-26
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

import management.migrations.coordinator as coordinator_migrations  # noqa: E402
from management.audit.audit_log import AuditLog                     # noqa: E402
from management.cases.cases_repo import CasesRepo                   # noqa: E402
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
from management.migrations.runner import MigrationRunner, discover  # noqa: E402
from management.qs.qs_repo import (                                 # noqa: E402
    QsError,
    QsRepo,
    QsSelbstpruefungError,
)
from management.qs.qs_vokabular import ZWECKBINDUNG                 # noqa: E402
from management.rbac.rbac_repo import RbacRepo                      # noqa: E402
from management.results.results_repo import ResultsRepo             # noqa: E402
from management.server.management_app import ManagementApp          # noqa: E402

_PERSON = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT, system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL, is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0, is_support INTEGER NOT NULL DEFAULT 0,
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


class _Basis(unittest.TestCase):
    """
    coordinator.db mit drei Personen und sechs Faellen.

    Person 1 = Chefin (qs.view + qs.edit), Person 2 = Ermittler (bearbeitet
    Faelle), Person 3 = nur qs.view.
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.forensic = Path(self._tmp) / "forensic"
        self.evidence = Path(self._tmp) / "evidence"
        self.forensic.mkdir()
        self.evidence.mkdir()

        con = sqlite3.connect(self.db_path)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.executescript(_PERSON)
        con.executescript(_OLD_SCRAPE_JOBS)
        now = int(time.time())
        for uname, dname, inv, sup in (
                ("NRW\\chefin", "Chef-Ermittlerin", 0, 1),
                ("NRW\\ermittler", "Ermittler", 1, 0),
                ("NRW\\lektor", "Lektor", 0, 0)):
            con.execute(
                "INSERT INTO person (system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?,?,?,?,0,?)", (uname, dname, inv, sup, now))

        self.audit = AuditLog(con)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()
        self.writer = CoordinatorWriter(con, self.audit)

        rbac = RbacRepo(con, self.writer)
        rbac.grant("supervisor", "qs.view", scope="alle", actor_id=1)
        rbac.grant("supervisor", "qs.edit", scope="alle", actor_id=1)
        rbac.assign_role(1, "supervisor", actor_id=1)
        # Person 3 darf SEHEN, aber nicht pruefen — das ist die Trennung, die
        # Vier-Augen ueberhaupt erst moeglich macht.
        rbac.grant("lector", "qs.view", scope="alle", actor_id=1)
        rbac.assign_role(3, "lector", actor_id=1)
        # Person 2 bekommt nichts.

        cases = CasesRepo(con, self.writer)
        for uid in (101, 102, 103, 104, 105, 106):
            cases.create_case(uid, "demo_%d" % uid, actor_id=1)
        # Vier abgeschlossene Faelle bilden die Grundgesamtheit; 105/106
        # bleiben offen und duerfen NICHT gezogen werden (QR03).
        for uid in (101, 102, 103, 104):
            con.execute("UPDATE cases SET status = 'closed' WHERE "
                        "subject_id = ?", (uid,))

        self.con = con
        self.app = ManagementApp(self.db_path,
                                 forensic_dir=str(self.forensic),
                                 evidence_dir=str(self.evidence))

    def tearDown(self):
        try:
            self.con.close()
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)

    # ------------------------------------------------------------------ Hilfen
    def _repo(self):
        return QsRepo(self.con, self.writer)

    def _ro_repo(self):
        con = sqlite3.connect("file:%s?mode=ro" % self.db_path, uri=True)
        con.row_factory = sqlite3.Row
        return con, QsRepo(con)

    def _spitze(self):
        return self.con.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]

    def _payload(self, seq):
        """
        Der Audit-Payload. Die Spalte heisst 'content' (audit_log.py:71) —
        der EINGEFRORENE Spaltensatz der Hash-Kette; 'payload' gibt es dort
        nicht.
        """
        row = self.con.execute(
            "SELECT content FROM audit_log WHERE seq = ?", (seq,)).fetchone()
        return json.loads(row[0]) if row and row[0] else {}

    def _roh_payload(self, seq):
        return self.con.execute(
            "SELECT content FROM audit_log WHERE seq = ?", (seq,)).fetchone()[0]


class TestQsRepo(_Basis):
    """QR01-QR13."""

    # ===================================================================== QR01
    def test_QR01_ziehung_schreibt_kopf_und_positionen(self):
        z = self._repo().ziehen(seed=1, anteil=1.0, hoechstens=3, actor_id=1)
        sid = z["sample_id"]
        kopf = self.con.execute(
            "SELECT * FROM qs_sample WHERE id = ?", (sid,)).fetchone()
        self.assertIsNotNone(kopf)
        self.assertEqual(kopf["stichprobe_n"], 3)
        self.assertEqual(kopf["grundgesamtheit_n"], 4)

        pos = [(r["position"], r["subject_id"]) for r in self.con.execute(
            "SELECT position, subject_id FROM qs_sample_item "
            "WHERE sample_id = ? ORDER BY position", (sid,)).fetchall()]
        self.assertEqual([p for p, _ in pos], [0, 1, 2])
        self.assertEqual([s for _, s in pos], list(z["subject_ids"]))

    # ===================================================================== QR02
    def test_QR02_keim_steht_in_zeile_und_beleg(self):
        z = self._repo().ziehen(seed=4711, anteil=1.0, hoechstens=2, actor_id=1)
        self.assertEqual(self.con.execute(
            "SELECT seed FROM qs_sample WHERE id = ?",
            (z["sample_id"],)).fetchone()[0], 4711)
        p = self._payload(z["audit_seq"])
        self.assertEqual(p["seed"], 4711)
        self.assertEqual(p["grundgesamtheit_n"], 4)
        self.assertEqual(p["subject_ids"], list(z["subject_ids"]))
        self.assertIn("filter", p)

    # ===================================================================== QR03
    def test_QR03_nur_abgeschlossene_faelle(self):
        g = {int(f["subject_id"]) for f in self._repo().grundgesamtheit()}
        self.assertEqual(g, {101, 102, 103, 104})
        self.assertNotIn(105, g,
                         "An einem laufenden Fall waere eine Luecke ein "
                         "Zwischenstand und kein Befund.")

    # ===================================================================== QR04
    def test_QR04_sperre_greift_bei_allen_drei_beruehrungsarten(self):
        repo = self._repo()
        # (a) aktuelle Zuweisung
        CasesRepo(self.con, self.writer).assign(101, 2, actor_id=1)
        darf, gruende = repo.darf_pruefen(101, 2)
        self.assertFalse(darf)
        self.assertTrue(any("zugewiesen" in g for g in gruende), gruende)

        # (b) Fallhistorie: ein INHALTLICHES Ereignis von Person 2. Ein
        #     'case_created' zaehlt ausdruecklich NICHT (s. Kopf von
        #     qs_repo.py) — sonst waere die Chefin mit jedem Fall beruehrt.
        self.con.execute(
            "UPDATE case_events SET created_by = 2, event_kind = 'manual' "
            "WHERE subject_id = 102")
        darf2, gruende2 = repo.darf_pruefen(102, 2)
        self.assertFalse(darf2)
        self.assertTrue(any("Ereignis" in g for g in gruende2), gruende2)

        # (c) Ergebnisbewertung
        ResultsRepo(self.con, self.writer).assess(
            subject_id=103, criterion_code="identification", extrem="schwerste",
            confidence_code="verdacht", quality_code=None, note="",
            actor_id=2)
        darf3, gruende3 = repo.darf_pruefen(103, 2)
        self.assertFalse(darf3)
        self.assertTrue(any("Ergebnisbewertung" in g for g in gruende3),
                        gruende3)

    # ===================================================================== QR05
    def test_QR05_sperre_ueberlebt_umzuweisung(self):
        """
        DIE LUECKE, DIE DIESER TEST SCHLIESST: nach einer Umzuweisung waere die
        frueher zustaendige Person wieder pruefberechtigt fuer genau den Fall,
        den sie selbst bearbeitet hat — wenn nur cases.assigned_to geprueft
        wird.
        """
        cases = CasesRepo(self.con, self.writer)
        cases.assign(104, 2, actor_id=1)
        # Das Zuweisungsereignis stammt von der Chefin; hier wird die ARBEIT
        # von Person 2 nachgestellt (inhaltliche Ereignisart).
        self.con.execute(
            "UPDATE case_events SET created_by = 2, event_kind = 'manual' "
            "WHERE subject_id = 104")
        cases.assign(104, 3, actor_id=1)      # umgewiesen an Person 3

        self.assertIsNone(None)
        darf, gruende = self._repo().darf_pruefen(104, 2)
        self.assertFalse(darf,
                         "Die Historie zaehlt, nicht nur der aktuelle Stand.")
        self.assertTrue(any("Fallhistorie" in g for g in gruende), gruende)

    # ==================================================================== QR05b
    def test_QR05b_listen_decken_das_vokabular_vollstaendig(self):
        """
        MITWIRKUNGS_ + STEUERUNGS_EVENT_KINDS muessen ZUSAMMEN genau das
        Vokabular von case_events ergeben. Sonst faellt eine Ereignisart aus
        der Betrachtung, ohne dass jemand darueber entschieden haette — und
        die Sperre haette eine unbemerkte Luecke oder eine unbemerkte
        Ausweitung.
        """
        from management.case_events.case_events_repo import EVENT_KINDS
        from management.qs.qs_repo import (
            MITWIRKUNGS_EVENT_KINDS, STEUERUNGS_EVENT_KINDS,
        )
        beide = set(MITWIRKUNGS_EVENT_KINDS) | set(STEUERUNGS_EVENT_KINDS)
        self.assertEqual(beide, set(EVENT_KINDS))
        self.assertEqual(
            set(MITWIRKUNGS_EVENT_KINDS) & set(STEUERUNGS_EVENT_KINDS), set())

    # ===================================================================== QR06
    def test_QR06_unbeteiligte_duerfen_pruefen(self):
        darf, gruende = self._repo().darf_pruefen(101, 1)
        self.assertTrue(darf, gruende)
        self.assertEqual(gruende, [])

    # ===================================================================== QR07
    def test_QR07_eingabepruefung(self):
        repo = self._repo()
        z = repo.ziehen(seed=1, anteil=1.0, hoechstens=4, actor_id=1)
        sid = z["sample_id"]
        with self.assertRaises(QsError) as c1:
            repo.pruefen(sample_id=sid, subject_id=101, ergebnis="in_ordnung",
                         begruendung="   ", actor_id=1)
        self.assertIn("Begruendung", str(c1.exception))
        with self.assertRaises(QsError) as c2:
            repo.pruefen(sample_id=sid, subject_id=101, ergebnis="mangelhaft",
                         begruendung="x", actor_id=1)
        self.assertIn("Unbekanntes Ergebnis", str(c2.exception))
        # Und ein Fall, den es nicht gibt.
        with self.assertRaises(QsError):
            repo.pruefen(sample_id=sid, subject_id=999, ergebnis="in_ordnung",
                         begruendung="x", actor_id=1)

    # ===================================================================== QR08
    def test_QR08_ausserhalb_der_ziehung_ist_zulaessig_und_wird_vermerkt(self):
        repo = self._repo()
        z = repo.ziehen(seed=1, anteil=0.25, hoechstens=1, actor_id=1)
        gezogen = set(z["subject_ids"])
        nicht_gezogen = sorted({101, 102, 103, 104} - gezogen)[0]

        r = repo.pruefen(sample_id=z["sample_id"], subject_id=nicht_gezogen,
                         ergebnis="in_ordnung",
                         begruendung="Zusaetzlich mitgeprueft.", actor_id=1)
        self.assertTrue(r["ausserhalb_der_ziehung"])
        self.assertEqual(self.con.execute(
            "SELECT ausserhalb_der_ziehung FROM qs_review WHERE id = ?",
            (r["review_id"],)).fetchone()[0], 1)
        self.assertTrue(self._payload(r["audit_seq"])
                        ["ausserhalb_der_ziehung"])

        # Ein GEZOGENER Fall traegt die Kennzeichnung NICHT.
        r2 = repo.pruefen(sample_id=z["sample_id"],
                          subject_id=sorted(gezogen)[0],
                          ergebnis="in_ordnung", begruendung="traegt",
                          actor_id=1)
        self.assertFalse(r2["ausserhalb_der_ziehung"])

    # ===================================================================== QR09
    def test_QR09_kein_wortlaut_im_audit_beleg(self):
        repo = self._repo()
        z = repo.ziehen(seed=1, anteil=1.0, hoechstens=4, actor_id=1)
        geheim = "Die Auswertung uebergeht die Chatverlaeufe von Herrn X."
        r = repo.pruefen(sample_id=z["sample_id"], subject_id=101,
                         ergebnis="nachzuarbeiten", begruendung=geheim,
                         actor_id=1)
        p = self._payload(r["audit_seq"])
        self.assertEqual(p["begruendung_len"], len(geheim))
        self.assertNotIn("begruendung", p)
        # Und der Wortlaut steht NIRGENDS im Protokoll.
        self.assertNotIn("Herrn X", self._roh_payload(r["audit_seq"]))
        # Er steht aber in der Tabelle — dort gehoert er hin.
        self.assertEqual(self.con.execute(
            "SELECT begruendung FROM qs_review WHERE id = ?",
            (r["review_id"],)).fetchone()[0], geheim)

    # ===================================================================== QR10
    def test_QR10_zweites_ergebnis_wird_abgewiesen(self):
        repo = self._repo()
        z = repo.ziehen(seed=1, anteil=1.0, hoechstens=4, actor_id=1)
        repo.pruefen(sample_id=z["sample_id"], subject_id=101,
                     ergebnis="in_ordnung", begruendung="traegt", actor_id=1)
        with self.assertRaises(QsError) as ctx:
            repo.pruefen(sample_id=z["sample_id"], subject_id=101,
                         ergebnis="nachzuarbeiten", begruendung="doch nicht",
                         actor_id=1)
        self.assertIn("neue Ziehung", str(ctx.exception))

    # ===================================================================== QR11
    def test_QR11_kein_schreibweg_ohne_writer(self):
        con, repo = self._ro_repo()
        try:
            with self.assertRaises(QsError):
                repo.ziehen(seed=1, actor_id=1)
            with self.assertRaises(QsError):
                repo.pruefen(sample_id=1, subject_id=101,
                             ergebnis="in_ordnung", begruendung="x",
                             actor_id=1)
        finally:
            con.close()

    # ===================================================================== QR12
    def test_QR12_nachziehen(self):
        repo = self._repo()
        z = repo.ziehen(seed=99, anteil=0.5, hoechstens=2, actor_id=1)
        r = repo.nachziehen(z["sample_id"])
        self.assertTrue(r["stimmt"], r["abweichungen"])
        self.assertEqual(r["seed"], 99)

        # Ein weiterer abgeschlossener Fall veraendert die Grundgesamtheit.
        self.con.execute(
            "UPDATE cases SET status = 'closed' WHERE subject_id = 105")
        r2 = repo.nachziehen(z["sample_id"])
        self.assertFalse(r2["stimmt"])
        self.assertTrue(any("Grundgesamtheit" in a for a in r2["abweichungen"]),
                        r2["abweichungen"])
        self.assertIn("nicht ohne Weiteres ein Verstoss", r2["hinweis"])

    # ===================================================================== QR13
    def test_QR13_liste_weist_den_fortschritt_aus(self):
        repo = self._repo()
        z = repo.ziehen(seed=1, anteil=1.0, hoechstens=4, actor_id=1)
        repo.pruefen(sample_id=z["sample_id"], subject_id=z["subject_ids"][0],
                     ergebnis="in_ordnung", begruendung="traegt", actor_id=1)
        b = repo.liste()
        self.assertEqual(b["ziehungen_gesamt"], 1)
        zz = b["ziehungen"][0]
        self.assertEqual(zz["geprueft_n"], 1)
        self.assertEqual(zz["offen_n"], 3)
        self.assertEqual(zz["zaehler"], {"in_ordnung": 1})
        self.assertEqual(b["zweckbindung"], ZWECKBINDUNG)
        self.assertTrue(b["ist_kein_bewertungsinstrument"])
        self.assertTrue(b["prueflinge_sind_vorschlag"])


class TestQsEndpunkte(_Basis):
    """QE01-QE09."""

    def _get(self, person_id, pfad="/api/qs", query=None):
        return self.app.dispatch(person_id, pfad, query or {})

    def _post(self, person_id, pfad, payload):
        return self.app.dispatch_write(person_id, pfad, payload)

    # ===================================================================== QE01
    def test_QE01_ohne_recht_403(self):
        r = self._get(2)
        self.assertEqual(r.status, 403)
        self.assertEqual(json.loads(r.body)["capability"], "qs.view")

    # ===================================================================== QE02
    def test_QE02_mit_recht_200_und_zweckbindung(self):
        self._repo().ziehen(seed=1, anteil=1.0, hoechstens=4, actor_id=1)
        r = self._get(1)
        self.assertEqual(r.status, 200)
        b = json.loads(r.body)
        self.assertEqual(b["zweckbindung"], ZWECKBINDUNG)
        self.assertTrue(b["darf_pruefen_recht"])
        fall = b["ziehungen"][0]["faelle"][0]
        self.assertIn("darf_pruefen", fall)
        self.assertIn("sperrgruende", fall)

        # Person 3 sieht dieselbe Liste, darf aber NICHT pruefen.
        r3 = self._get(3)
        self.assertEqual(r3.status, 200)
        self.assertFalse(json.loads(r3.body)["darf_pruefen_recht"])

    # ===================================================================== QE03
    def test_QE03_ziehen_braucht_qs_edit(self):
        r = self._post(3, "/api/qs/draw", {})
        self.assertEqual(r.status, 403)
        self.assertEqual(json.loads(r.body)["capability"], "qs.edit")

    # ===================================================================== QE04
    def test_QE04_ohne_keim_wird_einer_erzeugt(self):
        r = self._post(1, "/api/qs/draw", {"anteil": 1.0, "hoechstens": 2})
        self.assertEqual(r.status, 200, r.body)
        b = json.loads(r.body)
        self.assertIsInstance(b["seed"], int)
        self.assertIsNotNone(self.con.execute(
            "SELECT seed FROM qs_sample WHERE id = ?",
            (b["sample_id"],)).fetchone()[0])

    # ===================================================================== QE05
    def test_QE05_selbstpruefung_ist_403_und_nicht_400(self):
        z = self._repo().ziehen(seed=1, anteil=1.0, hoechstens=4, actor_id=1)
        # Die Chefin hat den Fall ANGELEGT — das allein sperrt sie NICHT
        # (Steuerung, keine Auswertung). Erst eine eigene BEWERTUNG tut es.
        r_vorher = self._post(1, "/api/qs/review", {
            "sample_id": z["sample_id"], "subject_id": 101,
            "ergebnis": "in_ordnung", "begruendung": "Anlegen sperrt nicht."})
        self.assertEqual(r_vorher.status, 200, r_vorher.body)

        ResultsRepo(self.con, self.writer).assess(
            subject_id=102, criterion_code="identification",
            extrem="schwerste", confidence_code="verdacht", quality_code=None,
            note="", actor_id=1)
        r = self._post(1, "/api/qs/review", {
            "sample_id": z["sample_id"], "subject_id": 102,
            "ergebnis": "in_ordnung", "begruendung": "sieht gut aus"})
        self.assertEqual(r.status, 403,
                         "An der Eingabe ist nichts zu bessern — ein 400 waere "
                         "irrefuehrend.")
        b = json.loads(r.body)
        self.assertEqual(b["error"], "qs_selbstpruefung")
        self.assertIn("SELBSTPRUEFUNG IST GESPERRT", b["detail"])

    # ===================================================================== QE06
    def test_QE06_fehlende_begruendung_ist_400(self):
        z = self._repo().ziehen(seed=1, anteil=1.0, hoechstens=4, actor_id=1)
        r = self._post(1, "/api/qs/review", {
            "sample_id": z["sample_id"], "subject_id": z["subject_ids"][0],
            "ergebnis": "in_ordnung", "begruendung": ""})
        self.assertEqual(r.status, 400)
        self.assertIn("Begruendung", json.loads(r.body)["detail"])

    # ===================================================================== QE07
    def test_QE07_nachziehen_am_endpunkt(self):
        z = self._repo().ziehen(seed=7, anteil=1.0, hoechstens=2, actor_id=1)
        r = self._get(1, "/api/qs/recheck",
                      {"sample_id": [str(z["sample_id"])]})
        self.assertEqual(r.status, 200, r.body)
        self.assertTrue(json.loads(r.body)["stimmt"])

        self.assertEqual(self._get(1, "/api/qs/recheck", {}).status, 400)
        self.assertEqual(self._get(1, "/api/qs/recheck",
                                   {"sample_id": ["abc"]}).status, 400)

    # ===================================================================== QE08
    def test_QE08_lesen_schreibt_nichts(self):
        self._repo().ziehen(seed=1, anteil=1.0, hoechstens=4, actor_id=1)
        vorher = self._spitze()
        self.assertEqual(self._get(1).status, 200)
        self.assertEqual(self._get(1, "/api/qs/recheck",
                                   {"sample_id": ["1"]}).status, 200)
        self.assertEqual(self._spitze(), vorher)

    # ===================================================================== QE09
    def test_QE09_m034_hat_geseedet(self):
        caps = {r[0] for r in self.con.execute(
            "SELECT code FROM rbac_capability").fetchall()}
        self.assertIn("qs.view", caps)
        self.assertIn("qs.edit", caps)


if __name__ == "__main__":
    unittest.main()
