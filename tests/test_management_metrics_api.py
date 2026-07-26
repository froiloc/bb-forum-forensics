# =============================================================================
# tests/test_management_metrics_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3C
# =============================================================================
# Testsuite fuer Build 542: die Ermittler-Metriken und der Endpunkt
# GET /api/metrics.
#
# DIE WICHTIGSTEN TESTS DIESER SUITE PRUEFEN, WAS NICHT DA IST. Eine
# Zweckbindung, die nur im Fliesstext steht, ist eine Absichtserklaerung; eine,
# gegen die ein Test laeuft, ist eine Zusicherung.
#
# VOKABULAR:
#   MT01 — Die Zweckbindung steht im Code, nennt ausdruecklich 'keine Rangfolge
#          zwischen Personen' und unterscheidet sich von der QS-Zweckbindung
#          (zwei Sachverhalte, zwei Saetze).
#   MT02 — Jeder Kennzahlenblock hat eine BEDEUTUNG; ein unbekannter wird
#          benannt statt abgebildet.
#
# REPOSITORY:
#   MT03 — KEIN VERBOTENER SCHLUESSEL IN DER GANZEN ANTWORT, rekursiv geprueft
#          gegen VERBOTENE_KENNZAHLEN. Das ist der Kern der Zweckbindung.
#   MT04 — KEIN PERSONENBEZUG: in der ganzen Antwort kommt weder eine
#          person_id noch ein Systembenutzername vor.
#   MT05 — Der Bestand zaehlt GENERISCH je Status; ein neuer Zustand faellt
#          nicht aus der Summe.
#   MT06 — Die Abdeckung wird in Klassen ausgewiesen; die Summe der Klassen
#          ergibt die Zahl der Faelle.
#   MT07 — AUSREISSER: ein ABGESCHLOSSENER Fall ohne Bewertung wird benannt,
#          ein LAUFENDER ausdruecklich nicht (dort ist die Luecke ein
#          Zwischenstand).
#   MT08 — Die Anlaufzeit misst ZUWEISUNG -> erstes INHALTLICHES Ereignis.
#          Ein 'assigned' oder 'case_created' beendet die Spanne NICHT.
#   MT09 — Faelle OHNE inhaltliches Ereignis werden GETRENNT gezaehlt und
#          nicht als 0 Tage verbucht — sie sind die eigentliche Aussage.
#   MT10 — Median statt Mittelwert, und die Antwort sagt WARUM.
#   MT11 — OHNE Substanzblock: 'geprueft' false und der Hinweis sagt
#          ausdruecklich, dass NICHT NACHGESEHEN wurde.
#   MT12 — MIT Substanzblock: ein zugewiesener Fall ohne Annotation wird
#          benannt, einer mit Annotation nicht; eine fehlende evidence-Datei
#          wird GEZAEHLT und nicht als 'ohne Annotation' gewertet.
#   MT13 — Die Ausreisser sind nach subject_id sortiert und NICHT nach
#          Schwere — es gibt keine Schwere.
#   MT14 — Die Laufzeit faehrt mit; was nicht gelaufen ist, hat keine Dauer.
#
# ENDPUNKT:
#   MT15 — ohne Recht -> 403, nennt 'metrics.view'.
#   MT16 — mit Recht -> 200, Zweckbindung wortgleich, beide Zusicherungen.
#   MT17 — '?substanz=1' schaltet zu, '?substanz=quatsch' ist 400.
#   MT18 — Der Endpunkt schreibt NICHTS.
#   MT19 — M035 hat 'metrics.view' geseedet.
#
# Version: v0.8.542 · Build: 542 · 2026-07-26
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
import management.migrations.evidence as evidence_migrations       # noqa: E402
from management.audit.audit_log import AuditLog                     # noqa: E402
from management.cases.cases_repo import CasesRepo                   # noqa: E402
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
from management.metrics import metrics_vokabular as MV              # noqa: E402
from management.metrics.metrics_repo import MetricsRepo             # noqa: E402
from management.migrations.runner import MigrationRunner, discover  # noqa: E402
from management.qs.qs_vokabular import ZWECKBINDUNG as QS_ZWECK     # noqa: E402
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

_ANNOTATIONS = """
CREATE TABLE "annotations" (
    "id" INTEGER, "page_url" TEXT NOT NULL, "element_id" TEXT,
    "category" TEXT NOT NULL, "text" TEXT NOT NULL DEFAULT '',
    "ts" INTEGER NOT NULL, "investigator_id" INTEGER,
    "local_id" TEXT DEFAULT NULL, "version_nr" INTEGER NOT NULL DEFAULT 1,
    "prev_id" INTEGER DEFAULT NULL, "deleted_at" INTEGER DEFAULT NULL,
    PRIMARY KEY("id" AUTOINCREMENT)
);
"""

_JETZT = 1785000000
_TAG = 86400


def _schluessel_rekursiv(obj, gesammelt=None):
    """Alle dict-Schluessel eines verschachtelten Objekts."""
    gesammelt = gesammelt if gesammelt is not None else set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            gesammelt.add(str(k))
            _schluessel_rekursiv(v, gesammelt)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _schluessel_rekursiv(v, gesammelt)
    return gesammelt


class _Basis(unittest.TestCase):
    """coordinator.db mit zwei Personen und sechs Faellen."""

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
        for uname, dname, sup in (("NRW\\chefin", "Chefin", 1),
                                  ("NRW\\ermittler", "Ermittler", 0)):
            con.execute(
                "INSERT INTO person (system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?,?,?,?,0,?)", (uname, dname, 0 if sup else 1,
                                         sup, now))

        self.audit = AuditLog(con)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()
        self.writer = CoordinatorWriter(con, self.audit)

        rbac = RbacRepo(con, self.writer)
        rbac.grant("supervisor", "metrics.view", scope="alle", actor_id=1)
        rbac.assign_role(1, "supervisor", actor_id=1)
        # Person 2 bekommt nichts.

        cases = CasesRepo(con, self.writer)
        for uid in (101, 102, 103, 104, 105, 106):
            cases.create_case(uid, "demo_%d" % uid, actor_id=1)
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
    def _repo(self, mit_evidence=True):
        return MetricsRepo(self.con,
                           str(self.evidence) if mit_evidence else None)

    def _bericht(self, **kw):
        return self._repo().compute(now_ts=_JETZT, **kw)

    def _evidence_db(self, sid, annotationen=0):
        pfad = self.evidence / ("evidence_%d.db" % sid)
        con = sqlite3.connect(str(pfad))
        try:
            con.executescript(_ANNOTATIONS)
            con.commit()
            MigrationRunner(
                con, [m for m in discover(evidence_migrations)
                      if m.VERSION <= 2]).run()
            for i in range(annotationen):
                con.execute(
                    'INSERT INTO "annotations" (page_url, category, text, ts, '
                    'investigator_id, version_nr) VALUES (?,?,?,?,?,1)',
                    ("/x", "CAT_176", "t", 1700000000 + i, 2))
            con.commit()
        finally:
            con.close()

    def _ereignis(self, sid, kind, ts, created_by=2):
        self.con.execute(
            "INSERT INTO case_events (subject_id, event_kind, payload, "
            "created_by, created_at, audit_seq) VALUES (?,?,'',?,?,1)",
            (sid, kind, created_by, ts))


class TestVokabular(unittest.TestCase):
    """MT01-MT02."""

    def test_MT01_zweckbindung(self):
        self.assertIn("keine Rangfolge zwischen Personen", MV.ZWECKBINDUNG)
        self.assertIn("KEIN MITARBEITER-BEWERTUNGSINSTRUMENT", MV.ZWECKBINDUNG)
        self.assertNotEqual(
            MV.ZWECKBINDUNG, QS_ZWECK,
            "Zwei Sachverhalte, zwei Saetze — eine gemeinsame Formulierung "
            "waere fuer beide ungenau.")

    def test_MT02_jeder_block_hat_eine_bedeutung(self):
        for code in MV.KENNZAHLEN:
            self.assertTrue(MV.KENNZAHL_BEDEUTUNG.get(code), code)
        self.assertIn("gibtsnicht", MV.kennzahl_bedeutung("gibtsnicht"))


class TestMetricsRepo(_Basis):
    """MT03-MT14."""

    # ===================================================================== MT03
    def test_MT03_kein_verbotener_schluessel(self):
        """
        DER KERN DER ZWECKBINDUNG. Taucht je eine Leistungskennzahl in der
        Antwort auf, bricht dieser Test — das ist der Unterschied zwischen
        'wir wollen das nicht' und 'das kann nicht passieren'.
        """
        self._evidence_db(101, annotationen=0)
        self.con.execute(
            "UPDATE cases SET assigned_to = 2 WHERE subject_id = 101")
        b = self._bericht(mit_substanz=True)
        schluessel = {k.lower() for k in _schluessel_rekursiv(b)}
        treffer = schluessel & MV.VERBOTEN_SET
        self.assertEqual(treffer, set(),
                         "Verbotene Kennzahl(en) in der Antwort: %r" % treffer)
        # Und auch kein Schluessel, der einen der Begriffe ENTHAELT.
        for verboten in MV.VERBOTENE_KENNZAHLEN:
            for k in schluessel:
                self.assertNotIn(verboten, k,
                                 "Schluessel '%s' enthaelt '%s'."
                                 % (k, verboten))

    # ===================================================================== MT04
    def test_MT04_kein_personenbezug(self):
        b = self._bericht()
        roh = json.dumps(b, ensure_ascii=False)
        self.assertNotIn("NRW\\\\chefin", roh)
        self.assertNotIn("Chefin", roh)
        self.assertNotIn("person_id", roh)
        self.assertNotIn("assigned_to", roh)
        self.assertTrue(b["keine_personenrangfolge"])

    # ===================================================================== MT05
    def test_MT05_bestand_generisch(self):
        self.con.execute(
            "UPDATE cases SET status = 'closed' WHERE subject_id IN (101,102)")
        b = self._bericht()["bestand"]
        self.assertEqual(b["faelle_gesamt"], 6)
        self.assertEqual(b["je_status"].get("closed"), 2)
        self.assertEqual(sum(b["je_status"].values()), 6)
        self.assertEqual(b["unzugewiesen"], 6)

    # ===================================================================== MT06
    def test_MT06_abdeckung_in_klassen(self):
        b = self._bericht()["abdeckung"]
        self.assertEqual(sum(b["klassen"].values()), b["faelle_gesamt"])
        self.assertEqual(b["nie_bewertet"], 6)
        self.assertEqual(b["klassen"]["nie_bewertet"], 6)
        self.assertEqual(len(b["klassengrenzen"]), len(MV.ABDECKUNG_KLASSEN))

    # ===================================================================== MT07
    def test_MT07_ausreisser_nur_bei_abgeschlossenen_faellen(self):
        self.con.execute(
            "UPDATE cases SET status = 'closed' WHERE subject_id = 101")
        b = self._bericht()
        arten = {(a["subject_id"], a["art"]) for a in b["ausreisser"]}
        self.assertIn((101, "abgeschlossen_ohne_bewertung"), arten)
        # 102 laeuft noch -> KEIN Ausreisser, obwohl ebenfalls unbewertet.
        self.assertNotIn((102, "abgeschlossen_ohne_bewertung"), arten)
        # Der Hinweis nennt die Deutung ausdruecklich.
        self.assertTrue(any("PRUEFBEDARF AN DER AUSWERTUNG" in h
                            for h in b["hinweise"]), b["hinweise"])

    # ===================================================================== MT08
    def test_MT08_anlaufzeit_nur_bis_zum_inhaltlichen_ereignis(self):
        # Zuweisung vor 100 Tagen, dann NUR Steuerungsereignisse, dann nach
        # 10 Tagen ein inhaltliches.
        self._ereignis(101, "assigned", _JETZT - 100 * _TAG)
        self._ereignis(101, "status_changed", _JETZT - 95 * _TAG)
        self._ereignis(101, "manual", _JETZT - 90 * _TAG)
        b = self._bericht()["anlaufzeit"]
        self.assertEqual(b["faelle_mit_zuweisung"], 1)
        self.assertEqual(b["faelle_mit_anlaufzeit"], 1)
        self.assertEqual(b["median_tage"], 10,
                         "Ein 'status_changed' ist Steuerung und beendet die "
                         "Anlaufzeit nicht.")

    # ===================================================================== MT09
    def test_MT09_faelle_ohne_inhaltliches_ereignis_getrennt(self):
        self._ereignis(101, "assigned", _JETZT - 100 * _TAG)
        self._ereignis(102, "assigned", _JETZT - 5 * _TAG)
        b = self._bericht()
        a = b["anlaufzeit"]
        self.assertEqual(a["faelle_ohne_inhaltliches_ereignis"], 2)
        self.assertEqual(a["faelle_mit_anlaufzeit"], 0)
        self.assertIsNone(a["median_tage"],
                          "Ohne Spanne gibt es keinen Median — und keine 0.")
        # Nur der ALTE Fall wird als Ausreisser benannt.
        arten = {(x["subject_id"], x["art"]) for x in b["ausreisser"]}
        self.assertIn((101, "ohne_inhaltliches_ereignis"), arten)
        self.assertNotIn((102, "ohne_inhaltliches_ereignis"), arten)

    # ===================================================================== MT10
    def test_MT10_median_statt_mittelwert(self):
        a = self._bericht()["anlaufzeit"]
        self.assertIn("kein_mittelwert", a)
        self.assertIn("MEDIAN", a["kein_mittelwert"])
        self.assertNotIn("mittelwert_tage", a)
        self.assertNotIn("durchschnitt_tage", a)

    # ===================================================================== MT11
    def test_MT11_ohne_substanz_wird_das_gesagt(self):
        b = self._bericht()
        self.assertFalse(b["substanz"]["geprueft"])
        self.assertIn("NICHT NACHGESEHEN", b["substanz"]["hinweis"])
        self.assertIn("NICHT dasselbe", b["substanz"]["hinweis"])
        self.assertTrue(any("nicht angefordert" in q
                            for q in b["fehlende_quellen"]),
                        b["fehlende_quellen"])
        self.assertIsNone(b["dauer_substanz_ms"])

    # ===================================================================== MT12
    def test_MT12_substanz(self):
        self.con.execute(
            "UPDATE cases SET assigned_to = 2 WHERE subject_id IN "
            "(101, 102, 103)")
        self._evidence_db(101, annotationen=0)    # zugewiesen, KEINE Annotation
        self._evidence_db(102, annotationen=3)    # zugewiesen, mit Annotation
        # 103 bekommt gar keine Datei.
        b = self._bericht(mit_substanz=True)
        s = b["substanz"]
        self.assertTrue(s["geprueft"])
        self.assertEqual(s["faelle_zugewiesen"], 3)
        self.assertEqual(s["ohne_annotation"], 1)
        self.assertEqual(s["mit_annotation"], 1)
        self.assertEqual(s["ohne_evidence_datei"], 1,
                         "Eine fehlende Datei ist NICHT dasselbe wie 'keine "
                         "Annotation'.")
        arten = {(a["subject_id"], a["art"]) for a in b["ausreisser"]}
        self.assertIn((101, "zugewiesen_ohne_annotation"), arten)
        self.assertNotIn((103, "zugewiesen_ohne_annotation"), arten)

    # ===================================================================== MT13
    def test_MT13_ausreisser_nach_subject_id_nicht_nach_schwere(self):
        self.con.execute(
            "UPDATE cases SET status = 'closed' WHERE subject_id IN "
            "(101, 103, 105)")
        b = self._bericht()
        ids = [a["subject_id"] for a in b["ausreisser"]]
        self.assertEqual(ids, sorted(ids))
        for a in b["ausreisser"]:
            self.assertNotIn("schwere", a)
            self.assertNotIn("punkte", a)
            self.assertTrue(a["grund"])

    # ===================================================================== MT14
    def test_MT14_laufzeit(self):
        b = self._bericht()
        self.assertIsInstance(b["dauer_gesamt_ms"], int)
        self.assertIsNone(b["dauer_substanz_ms"])
        b2 = self._bericht(mit_substanz=True)
        self.assertIsNotNone(b2["dauer_substanz_ms"])


class TestMetricsEndpunkt(_Basis):
    """MT15-MT19."""

    def _get(self, person_id, query=None):
        return self.app.dispatch(person_id, "/api/metrics", query or {})

    # ===================================================================== MT15
    def test_MT15_ohne_recht_403(self):
        r = self._get(2)
        self.assertEqual(r.status, 403)
        self.assertEqual(json.loads(r.body)["capability"], "metrics.view")

    # ===================================================================== MT16
    def test_MT16_mit_recht_200(self):
        r = self._get(1)
        self.assertEqual(r.status, 200)
        b = json.loads(r.body)
        self.assertEqual(b["zweckbindung"], MV.ZWECKBINDUNG)
        self.assertTrue(b["ist_kein_bewertungsinstrument"])
        self.assertTrue(b["keine_personenrangfolge"])
        self.assertEqual(b["kennzahlen"], list(MV.KENNZAHLEN))

    # ===================================================================== MT17
    def test_MT17_substanz_schalter(self):
        aus = json.loads(self._get(1, {"substanz": ["0"]}).body)
        self.assertFalse(aus["substanz"]["geprueft"])
        an = json.loads(self._get(1, {"substanz": ["1"]}).body)
        self.assertTrue(an["substanz"]["geprueft"])
        r = self._get(1, {"substanz": ["quatsch"]})
        self.assertEqual(r.status, 400)
        self.assertIn("substanz", json.loads(r.body)["detail"])

    # ===================================================================== MT18
    def test_MT18_schreibt_nichts(self):
        vorher = self.con.execute(
            "SELECT MAX(seq) FROM audit_log").fetchone()[0]
        self.assertEqual(self._get(1).status, 200)
        self.assertEqual(self._get(1, {"substanz": ["1"]}).status, 200)
        self.assertEqual(self.con.execute(
            "SELECT MAX(seq) FROM audit_log").fetchone()[0], vorher)

    # ===================================================================== MT19
    def test_MT19_m035_hat_geseedet(self):
        caps = {r[0] for r in self.con.execute(
            "SELECT code FROM rbac_capability").fetchall()}
        self.assertIn("metrics.view", caps)


if __name__ == "__main__":
    unittest.main()
