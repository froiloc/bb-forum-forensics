# =============================================================================
# tests/test_management_matrix_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3B
# =============================================================================
# Testsuite fuer Build 537: der Sammler MatrixRepo und der Endpunkt
# GET /api/matrix.
#
# Der Rechenkern ist in Build 536 einzeln geprueft (tests/test_urgency_matrix.py,
# 25 Tests ohne Datenbank). Diese Suite prueft AUSSCHLIESSLICH das, was erst mit
# echten Daten sichtbar wird: ob die richtigen Tatsachen an der richtigen Stelle
# ankommen, und ob ein Ausfall benannt statt verschwiegen wird.
#
# SAMMLER (MatrixRepo):
#   MX01 — Jeder Fall aus 'cases' erzeugt GENAU EINE Zelle. Auch der ohne
#          Bewertung, auch der unzugewiesene — sonst waere die Rangfolge
#          unvollstaendig, und zwar unsichtbar.
#   MX02 — 'unzugewiesen' kommt aus cases.assigned_to IS NULL an.
#   MX03 — Die Liegezeit kommt aus last_activity_at = max(updated_at,
#          MAX(case_events.created_at)) — NICHT aus dem letzten Ereignis
#          allein. Ein Fall ohne jedes Ereignis hat trotzdem eine Liegezeit.
#   MX04 — Ein UEBERFAELLIGER externer Vorgang schlaegt durch; ein
#          Vorgang in der Vorwarnfrist (gelb) NICHT. Sonst waere die
#          Vorwarnfrist eine zweite Faelligkeit.
#   MX05 — Ein ERLEDIGTER Vorgang mit laengst vergangenem Datum schlaegt NICHT
#          durch (Endzustaende sind nie ueberfaellig).
#   MX06 — Eskalationen kommen an, und SYSTEMISCHE Meldungen (subject_id=None)
#          werden keinem Fall zugerechnet.
#   MX07 — Die Identitaetszuordnung kommt mit ihrem eigenen Konfidenzcode an
#          und wird abgestuft gerechnet (M-3).
#   MX08 — 'identification' ist aus der Abdeckung heraus: n_kriterien_matrix
#          ist um eins kleiner als der Katalog.
#   MX09 — OHNE FRISTBEITRAEGE: jede Zelle traegt dringlichkeit_bestimmbar
#          false mit Grund 'nicht_geladen', und die Antwort sagt
#          fristen_geladen: false. Das ist NICHT dasselbe wie 'keine Frist'.
#   MX10 — Eine leere Auswahl (subject_ids=[]) bedeutet KEINE Faelle, nicht
#          'alle'.
#   MX11 — FAELLT EINE QUELLE AUS, wird sie BENANNT und der Fall bleibt in der
#          Liste. Ein stillschweigend fehlender Beitrag saehe aus wie 'trifft
#          nicht zu'.
#
# ENDPUNKT:
#   MX12 — ohne Recht -> 403, nennt 'matrix.view'.
#   MX13 — mit Recht -> 200, Zellen, Quadrantenzaehlung, Gewichtsangaben.
#   MX14 — Die Antwort traegt 'ist_keine_beweiswuerdigung' und
#          'schreibt_keine_prioritaet' — Muster
#          'stellt_keine_verjaehrung_fest' (Build 524).
#   MX15 — Die ZWECKBINDUNG faehrt wortgleich aus dem Gewichtungssatz mit.
#   MX16 — Scope 'eigene' genuegt: die Sicht ist NICHT scope-behaftet.
#   MX17 — Der Endpunkt schreibt NICHTS: die audit_log-Spitze bleibt gleich.
#   MX18 — M033 hat 'matrix.view' geseedet.
#   MX19 — Ein unbrauchbarer Gewichtungssatz gibt 503 und KEINE Matrix —
#          lieber gar keine Zahl als eine mit geratenen Gewichten.
#
# Version: v0.8.537 · Build: 537 · 2026-07-26
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
from management.crossref.identified_subject_repo import (           # noqa: E402
    IdentifiedSubjectRepo,
)
from management.external.external_matters_repo import (             # noqa: E402
    ExternalMattersRepo,
)
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
from management.migrations.runner import MigrationRunner, discover  # noqa: E402
from management.rbac.rbac_repo import RbacRepo                      # noqa: E402
from management.results.matrix_repo import MatrixRepo               # noqa: E402
from management.results.matrix_weights import load_weights          # noqa: E402
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

_JETZT = 1785000000            # fester Stichtag, damit alles nachrechenbar ist
_TAG = 86400


def _iso(ts):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


class _Basis(unittest.TestCase):
    """Gemeinsame Vorrichtung: coordinator.db mit vier Faellen."""

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
                ("NRW\\ohne", "Ohne Rechte", 0, 0)):
            con.execute(
                "INSERT INTO person (system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?,?,?,?,0,?)", (uname, dname, inv, sup, now))

        self.audit = AuditLog(con)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()
        self.writer = CoordinatorWriter(con, self.audit)

        rbac = RbacRepo(con, self.writer)
        rbac.grant("supervisor", "matrix.view", scope="alle", actor_id=1)
        rbac.assign_role(1, "supervisor", actor_id=1)
        # Person 2 bekommt dasselbe Recht mit Scope 'eigene' — die Sicht ist
        # NICHT scope-behaftet und muss trotzdem antworten (MX16).
        rbac.grant("investigator", "matrix.view", scope="eigene", actor_id=1)
        rbac.assign_role(2, "investigator", actor_id=1)
        # Person 3: nichts.

        cases = CasesRepo(con, self.writer)
        for uid, name in ((101, "zugewiesen"), (102, "unzugewiesen"),
                          (103, "mit_vorgang"), (104, "identifiziert")):
            cases.create_case(uid, name, actor_id=1)
        cases.assign(101, 2, actor_id=1)
        cases.assign(103, 2, actor_id=1)
        cases.assign(104, 2, actor_id=1)

        self.con = con
        self.gewichte = load_weights()
        self.app = ManagementApp(self.db_path,
                                 forensic_dir=str(self.forensic),
                                 evidence_dir=str(self.evidence))

    def tearDown(self):
        try:
            self.con.close()
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)

    # ------------------------------------------------------------------ Hilfen
    def _liegezeit(self, subject_id, tage):
        """
        Setzt die Liegezeit eines Falls.

        BELEG (management/dashboard/dashboard_repo.py:218):
            last_activity_at = max(updated_at, last_event_at)
        Es genuegt also NICHT, cases.updated_at zurueckzudatieren — die
        Fallanlage hat bereits ein case_events-Ereignis mit der echten Uhrzeit
        geschrieben, und dieses Ereignis wuerde den Fall weiterhin als
        'gerade eben angefasst' ausweisen. Beide Quellen muessen zurueck.
        """
        ts = _JETZT - tage * _TAG
        self.con.execute("UPDATE cases SET updated_at = ? WHERE subject_id = ?",
                         (ts, subject_id))
        self.con.execute(
            "UPDATE case_events SET created_at = ? WHERE subject_id = ?",
            (ts, subject_id))

    def _vorgang(self, subject_id, *, wiedervorlage, status="offen",
                 vorwarn=7):
        """
        Legt einen externen Vorgang ueber den ECHTEN Weg an.

        Ein direktes INSERT ist hier nicht moeglich und waere auch falsch:
        external_matters.audit_seq/created_audit_seq sind NOT NULL mit FK auf
        audit_log (M010) — ein Vorgang OHNE Auditeintrag ist im Schema gar
        nicht vorgesehen. Der Zielzustand 'erledigt' wird ueber die zulaessige
        Kette offen -> beantwortet -> erledigt erreicht
        (management/external/matter_status.py:71).
        """
        repo = ExternalMattersRepo(self.con, self.writer)
        res = repo.create(
            subject_id=subject_id, kind="bestandsdaten", betreff="Betreff",
            adressat="Provider", angefordert_am=_iso(_JETZT - 60 * _TAG),
            wiedervorlage_am=wiedervorlage, vorwarnfrist_tage=vorwarn,
            actor_id=1)
        mid = res["matter_id"]
        if status == "beantwortet":
            repo.answer(mid, ergebnis="", actor_id=1)
        elif status in ("erledigt", "erfolglos"):
            if status == "erledigt":
                repo.answer(mid, ergebnis="", actor_id=1)
            repo.close(mid, status=status, ergebnis="x", actor_id=1)
        elif status != "offen":
            raise AssertionError("Unbekannter Zustand '%s'." % status)
        return mid

    def _bewertung(self, subject_id, criterion, conf, ordinal):
        ResultsRepo(self.con, self.writer).assess(
            subject_id=subject_id, criterion_code=criterion,
            extrem="schwerste", confidence_code=conf, quality_code=None,
            note="", actor_id=1)

    def _repo(self):
        con = sqlite3.connect("file:%s?mode=ro" % self.db_path, uri=True)
        con.row_factory = sqlite3.Row
        return con, MatrixRepo(con, self.gewichte)

    def _matrix(self, subject_ids=None):
        con, repo = self._repo()
        try:
            return repo.compute(now_ts=_JETZT, subject_ids=subject_ids)
        finally:
            con.close()

    @staticmethod
    def _zelle(bericht, subject_id):
        for z in bericht["zellen"]:
            if z["subject_id"] == subject_id:
                return z
        raise AssertionError("Fall %d fehlt in der Matrix." % subject_id)


class TestMatrixRepo(_Basis):
    """MX01-MX11: der Sammler."""

    # ===================================================================== MX01
    def test_MX01_jeder_fall_genau_eine_zelle(self):
        b = self._matrix()
        self.assertEqual(b["faelle_gesamt"], 4)
        self.assertEqual(sorted(z["subject_id"] for z in b["zellen"]),
                         [101, 102, 103, 104])
        self.assertEqual(sum(b["quadranten"].values()), 4)

    # ===================================================================== MX02
    def test_MX02_unzugewiesen_kommt_an(self):
        b = self._matrix()
        codes = {x["code"] for x in self._zelle(b, 102)["beitraege"]}
        self.assertIn("unzugewiesen", codes)
        self.assertNotIn("unzugewiesen",
                         {x["code"] for x in self._zelle(b, 101)["beitraege"]})

    # ===================================================================== MX03
    def test_MX03_liegezeit_aus_last_activity_nicht_aus_ereignissen(self):
        """
        Ein Fall OHNE jedes Ereignis hat trotzdem eine Liegezeit — sie kommt
        aus cases.updated_at. Wer nur MAX(case_events.created_at) nimmt,
        uebersieht genau die Faelle, die nie angefasst wurden.
        """
        self._liegezeit(101, 200)     # ueber der Schwelle 90
        self._liegezeit(102, 10)      # darunter
        b = self._matrix()

        alt = [x for x in self._zelle(b, 101)["beitraege"]
               if x["code"] == "liegezeit"]
        self.assertEqual(len(alt), 1)
        self.assertIn("200 Tagen", alt[0]["grund"])

        self.assertEqual(
            [x for x in self._zelle(b, 102)["beitraege"]
             if x["code"] == "liegezeit"], [])

    # ===================================================================== MX04
    def test_MX04_ueberfaelliger_vorgang_ja_vorwarnung_nein(self):
        self._vorgang(103, wiedervorlage=_iso(_JETZT - 5 * _TAG))   # rot
        self._vorgang(101, wiedervorlage=_iso(_JETZT + 3 * _TAG),
                      vorwarn=7)                                     # gelb
        b = self._matrix()

        self.assertIn("wiedervorlage",
                      {x["code"] for x in self._zelle(b, 103)["beitraege"]})
        self.assertNotIn(
            "wiedervorlage",
            {x["code"] for x in self._zelle(b, 101)["beitraege"]},
            "Ein Vorgang in der VORWARNFRIST ist nicht ueberfaellig — sonst "
            "waere die Vorwarnfrist eine zweite Faelligkeit.")

    # ===================================================================== MX05
    def test_MX05_erledigter_vorgang_ist_nie_ueberfaellig(self):
        self._vorgang(103, wiedervorlage=_iso(_JETZT - 400 * _TAG),
                      status="erledigt")
        b = self._matrix()
        self.assertNotIn("wiedervorlage",
                         {x["code"] for x in self._zelle(b, 103)["beitraege"]})

    # ===================================================================== MX06
    def test_MX06_eskalationen_kommen_an_systemische_nicht(self):
        """
        R1 'fall_ueberfaellig' greift bei rotem Ampelzustand und langer
        Inaktivitaet. R3 'rueckstau_hoch' ist SYSTEMISCH (subject_id=None) und
        darf keinem Fall zugerechnet werden — das waere eine Erfindung.
        """
        # 102 ist offen UND unzugewiesen -> Ampel rot; lange inaktiv -> R1.
        self._liegezeit(102, 400)
        b = self._matrix()

        esk = [x for x in self._zelle(b, 102)["beitraege"]
               if x["code"] == "eskalation"]
        self.assertEqual(len(esk), 1)
        self.assertIn("Quittierte zaehlen MIT", esk[0]["grund"])

        # Die Summe der zugerechneten Meldungen darf die Zahl der Faelle nicht
        # ueberschreiten — systemische sind nicht dabei.
        mit_esk = sum(1 for z in b["zellen"]
                      if any(x["code"] == "eskalation" for x in z["beitraege"]))
        self.assertLessEqual(mit_esk, b["faelle_gesamt"])

    # ===================================================================== MX07
    def test_MX07_identitaet_abgestuft(self):
        repo = IdentifiedSubjectRepo(self.con, self.writer)
        repo.upsert(subject_id=104, real_identity="Muster, Max",
                    confidence_code="gesichert", basis="Meldeauskunft",
                    note="", actor_id=1)
        b = self._matrix()

        ident = [x for x in self._zelle(b, 104)["beitraege"]
                 if x["code"] == "identitaet"]
        self.assertEqual(len(ident), 1)
        self.assertEqual(ident[0]["punkte"], 20)      # 'gesichert'
        self.assertEqual(
            [x for x in self._zelle(b, 101)["beitraege"]
             if x["code"] == "identitaet"], [])

    # ===================================================================== MX08
    def test_MX08_identification_ist_aus_der_abdeckung_heraus(self):
        from management.results.assessment_catalog_repo import (
            AssessmentCatalogRepo,
        )
        n_katalog = len(AssessmentCatalogRepo(self.con).criteria())
        b = self._matrix()
        self.assertEqual(self._zelle(b, 101)["n_kriterien_matrix"],
                         n_katalog - 1,
                         "'identification' muss aus der Abdeckung heraus sein "
                         "(M-3) — sonst zaehlt dieselbe Erkenntnis zweimal.")

        # Und eine Bewertung AUF 'identification' erzeugt keine Abdeckung.
        self._bewertung(101, "identification", "gerichtsfest", 5)
        b2 = self._matrix()
        self.assertEqual(
            [x for x in self._zelle(b2, 101)["beitraege"]
             if x["code"] == "abdeckung"], [])

    # ===================================================================== MX09
    def test_MX09_ohne_fristbeitraege_ist_nicht_ohne_frist(self):
        b = self._matrix()
        self.assertFalse(b["fristen_geladen"])
        for z in b["zellen"]:
            self.assertFalse(z["dringlichkeit_bestimmbar"])
            self.assertEqual(z["dringlichkeit_grund"], "nicht_geladen",
                             "'nicht geladen' und 'keine Frist' duerfen nicht "
                             "gleich aussehen.")
            self.assertIsNone(z["dringlichkeit"])
            self.assertEqual(z["quadrant"], "nicht_bestimmbar")
        self.assertTrue(any("UNTERGRENZE" in h for h in b["hinweise"]))

    # ===================================================================== MX10
    def test_MX10_leere_auswahl_ist_keine_auswahl_ueber_alle(self):
        self.assertEqual(self._matrix(subject_ids=[])["faelle_gesamt"], 0)
        self.assertEqual(self._matrix(subject_ids=[101, 102])["faelle_gesamt"],
                         2)
        self.assertEqual(self._matrix()["faelle_gesamt"], 4)

    # ===================================================================== MX11
    def test_MX11_ausgefallene_quelle_wird_benannt(self):
        """
        Grundregel 1. Faellt eine Quelle aus, bleibt der Fall in der Liste, der
        Beitrag entfaellt — und der Ausfall wird BENANNT. Ein stillschweigend
        fehlender Beitrag saehe aus wie 'trifft nicht zu', und der Fall waere
        harmloser, als er ist.
        """
        self.con.execute("DROP TABLE external_matters")
        b = self._matrix()

        self.assertEqual(b["faelle_gesamt"], 4, "Kein Fall darf verschwinden.")
        self.assertTrue(b["fehlende_quellen"])
        self.assertTrue(any("Vorgaenge" in q for q in b["fehlende_quellen"]))
        self.assertTrue(any("NICHT LESBAR" in h for h in b["hinweise"]))
        self.assertTrue(any("harmloser aussehen" in h for h in b["hinweise"]))


class TestMatrixEndpunkt(_Basis):
    """MX12-MX19: der Endpunkt."""

    def _get(self, person_id, query=None):
        return self.app.dispatch(person_id, "/api/matrix", query or {})

    # ===================================================================== MX12
    def test_MX12_ohne_recht_403(self):
        r = self._get(3)
        self.assertEqual(r.status, 403)
        self.assertIn("matrix.view", r.body.decode("utf-8"))

    # ===================================================================== MX13
    def test_MX13_mit_recht_200(self):
        r = self._get(1)
        self.assertEqual(r.status, 200, r.body)
        b = json.loads(r.body.decode("utf-8"))
        self.assertEqual(b["faelle_gesamt"], 4)
        self.assertEqual(len(b["zellen"]), 4)
        self.assertEqual(sum(b["quadranten"].values()), 4)
        # Die Gewichtsangaben fahren mit, damit jede Zahl nachrechenbar ist.
        self.assertEqual(b["dringlichkeit_max"], 90)
        self.assertEqual(b["erkenntnislage_max"], 100)
        self.assertIn("konfidenz_punkte", b)
        self.assertEqual(b["ausgeschlossene_kriterien"], ["identification"])

    # ===================================================================== MX14
    def test_MX14_die_zusicherungen_fahren_mit(self):
        b = json.loads(self._get(1).body.decode("utf-8"))
        self.assertTrue(b["ist_keine_beweiswuerdigung"])
        self.assertTrue(b["schreibt_keine_prioritaet"])

    # ===================================================================== MX15
    def test_MX15_zweckbindung_wortgleich(self):
        b = json.loads(self._get(1).body.decode("utf-8"))
        self.assertEqual(b["zweckbindung"], self.gewichte.zweckbindung)
        self.assertIn("261", b["zweckbindung"])
        self.assertGreaterEqual(len(b["vorbehalte"]), 1)

    # ===================================================================== MX16
    def test_MX16_scope_eigene_genuegt(self):
        r = self._get(2)
        self.assertEqual(r.status, 200)
        b = json.loads(r.body.decode("utf-8"))
        self.assertEqual(b["faelle_gesamt"], 4,
                         "Die Sicht ist NICHT scope-behaftet — die "
                         "gefaehrlichsten Faelle sind die unzugewiesenen.")

    # ===================================================================== MX17
    def test_MX17_der_endpunkt_schreibt_nichts(self):
        vorher = self.audit.tip()
        self._get(1)
        self.assertEqual(self.audit.tip(), vorher,
                         "Ein Lesezugriff hat die Audit-Kette bewegt.")

    # ===================================================================== MX18
    def test_MX18_m033_hat_das_recht_geseedet(self):
        row = self.con.execute(
            "SELECT label FROM rbac_capability WHERE code = 'matrix.view'"
        ).fetchone()
        self.assertIsNotNone(row, "M033 ist nicht angewandt.")
        self.assertIn("Dringlichkeitsmatrix", row["label"])

    # ===================================================================== MX19
    def test_MX19_unbrauchbarer_gewichtungssatz_gibt_503(self):
        """
        Lieber gar keine Zahl als eine mit geratenen Gewichten — dieselbe
        Haltung wie beim Verjaehrungs-Parametersatz (503 statt 200).
        """
        import management.results.matrix_weights as mw
        from management.results.matrix_weights import MatrixWeightsError

        echt = mw.load_weights

        def kaputt(pfad=None):
            raise MatrixWeightsError("Testfall: Gewicht negativ")

        mw.load_weights = kaputt
        try:
            r = self._get(1)
        finally:
            mw.load_weights = echt

        self.assertEqual(r.status, 503)
        b = json.loads(r.body.decode("utf-8"))
        self.assertEqual(b["error"], "matrix_weights_invalid")
        self.assertIn("geratenen Gewichten", b["hinweis"])


if __name__ == "__main__":
    unittest.main()
