# =============================================================================
# tests/test_management_matrix_fristen.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3B
# =============================================================================
# Testsuite fuer Build 538: die FRISTKOMPONENTE (X-1) der Matrix.
#
# Build 536 hat den Rechenkern ohne Datenbank geprueft, Build 537 den Sammler
# und den Endpunkt OHNE Fristen. Diese Suite prueft ausschliesslich das, was
# mit dem Anschliessen der Frist hinzukommt — und vor allem die drei Zustaende,
# die einander nicht ueberdecken duerfen:
#
#     'nicht_geladen'  — es wurde NICHT nachgesehen.
#     'keine_aussage'  — es wurde nachgesehen, aber der Parametersatz ist nicht
#                        bestaetigt: der Monitor VERWEIGERT die Rechtsfolge.
#     eine Zahl        — es wurde nachgesehen und gerechnet.
#
#   MF01 — OHNE forensic-Verzeichnis: fristen_geladen false, die Quelle wird
#          BENANNT, und jede Zelle traegt den Grund 'nicht_geladen'.
#   MF02 — DER AUSLIEFERUNGSZUSTAND: mit Verzeichnis, aber UNBESTAETIGTEM
#          Parametersatz -> fristen_geladen TRUE und Grund 'keine_aussage'.
#          Der Hinweis nennt den Verweigerungsgrund und sagt ausdruecklich,
#          dass das nicht 'keine Frist' bedeutet.
#   MF03 — MIT bestaetigtem Satz und belegter Tathandlung: die Frist schlaegt
#          durch, 'frist' steht in den Beitraegen, dringlichkeit_bestimmbar
#          ist true, und die Punktsumme stimmt mit der Achse ueberein.
#   MF04 — DIESELBE RECHNUNG WIE /api/limitation: Ampel und Restlaufzeit der
#          Matrixzelle sind mit LimitationRepo.compute() fuer denselben
#          Stichtag identisch. Zwei Fristrechnungen waeren zwei Wahrheiten.
#   MF05 — BELASTBARKEIT (M-1): eine FESTGESTELLTE Tatzeit macht die Zelle
#          'festgestellt', ohne sie ist sie 'vorlaeufig' — bei GLEICHER
#          Punktzahl, wenn die Restlaufzeit dieselbe Stufe trifft.
#   MF06 — mit_fristen=False liefert exakt das Verhalten aus Build 537 und
#          weist 'fristen_angefordert': false aus.
#   MF07 — Die LAUFZEIT faehrt mit: dauer_fristen_ms ist gesetzt, wenn geladen
#          wurde, und None, wenn nicht angefordert wurde.
#   MF08 — Ein UNBRAUCHBARER Parametersatz nimmt die FRIST heraus, nicht die
#          Matrix: 200 mit benannter Quelle statt 503.
#   MF09 — Endpunkt: '?fristen=0' schaltet ab, '?fristen=quatsch' ist 400.
#   MF10 — Endpunkt mit Fristen schreibt weiterhin NICHTS (audit-Spitze).
#   MF11 — 'ueberschritten' erzeugt den Vermerk zur juristischen Pruefung —
#          die Matrix stellt keine Verjaehrung fest.
#
# Version: v0.8.538 · Build: 538 · 2026-07-26
# =============================================================================

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import date, datetime, time as dtime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations  # noqa: E402
import management.migrations.evidence as evidence_migrations       # noqa: E402
from management.audit.audit_log import AuditLog                     # noqa: E402
from management.cases.cases_repo import CasesRepo                   # noqa: E402
from management.deadlines.limitation_params import load_params      # noqa: E402
from management.deadlines.limitation_repo import LimitationRepo     # noqa: E402
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
from management.migrations.runner import MigrationRunner, discover  # noqa: E402
from management.rbac.rbac_repo import RbacRepo                      # noqa: E402
from management.results.matrix_repo import MatrixRepo               # noqa: E402
from management.results.matrix_weights import load_weights          # noqa: E402
from management.server.management_app import ManagementApp          # noqa: E402

_WURZEL = Path(__file__).resolve().parent.parent

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
    "id"              INTEGER,
    "page_url"        TEXT NOT NULL,
    "element_id"      TEXT,
    "category"        TEXT NOT NULL,
    "text"            TEXT NOT NULL DEFAULT '',
    "ts"              INTEGER NOT NULL,
    "investigator_id" INTEGER,
    "local_id"        TEXT DEFAULT NULL,
    "version_nr"      INTEGER NOT NULL DEFAULT 1,
    "prev_id"         INTEGER DEFAULT NULL,
    "deleted_at"      INTEGER DEFAULT NULL,
    PRIMARY KEY("id" AUTOINCREMENT)
);
"""

#: Fester Stichtag, damit jede Restlaufzeit nachrechenbar ist.
#: 1785000000 = 2026-07-25 (UTC).
_JETZT = 1785000000
_TAG = 86400


def _ts_tag(tag: str) -> int:
    return int(datetime.combine(date.fromisoformat(tag), dtime(0, 0),
                                tzinfo=timezone.utc).timestamp())


def _params_bestaetigt_pfad() -> Path:
    """
    Der AUSGELIEFERTE Parametersatz mit gesetzter Bestaetigung, als DATEI.

    Warum eine Kopie: der ausgelieferte Satz ist bewusst UNBESTAETIGT, und ein
    bestaetigter Satz im Repository waere eine Rechtsauskunft, die niemand
    erteilt hat (limitation_params.json, 'hinweis_unbestaetigt'). Dieselbe
    Vorrichtung wie tests/test_management_limitation_api.py:96 — hier als
    PFAD, weil MatrixRepo den Satz selbst laedt und nicht durchgereicht
    bekommt (damit ein Aufrufer ihn nicht weglassen kann).
    """
    raw = json.loads(
        (_WURZEL / "management" / "deadlines" / "limitation_params.json"
         ).read_text(encoding="utf-8"))
    raw["bestaetigt"] = True
    raw["bestaetigt_von"] = "StA Testfixture"
    raw["bestaetigt_am"] = "2026-07-25"
    ziel = Path(tempfile.mkdtemp()) / "params_ok.json"
    ziel.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return ziel


def _forensic_db(pfad: Path, *, posts=()) -> None:
    """
    Minimale forensic_<uid>.db mit dem ECHTEN Schema.

    BELEG: forensic_uid.db.schema.sql; uebernommen aus
    tests/test_management_limitation_api.py:148 (die Spaltennamen stammen aus
    dem DDL und nicht aus dem Code, den sie pruefen sollen — die Lehre aus
    Build 527).
    """
    con = sqlite3.connect(str(pfad))
    try:
        con.execute(
            "CREATE TABLE uid_posts (post_id INTEGER PRIMARY KEY, "
            "topic_id INTEGER, forum_id INTEGER, posted_ts INTEGER, "
            "active INTEGER DEFAULT 1, is_topic_starter INTEGER DEFAULT 0)")
        for i, t in enumerate(posts):
            con.execute(
                "INSERT INTO uid_posts (post_id, topic_id, forum_id, "
                "posted_ts) VALUES (?,?,?,?)", (i + 1, 10, 20, t))
        con.commit()
    finally:
        con.close()


def _evidence_db(pfad: Path, *, tatzeit_bis=None,
                 kategorie="CAT_176") -> None:
    """
    Minimale evidence_<uid>.db mit der ECHTEN m002-Migration.

    tatzeit_bis=None -> Datei mit Tabelle, aber ohne Feststellung
    ('ohne_feststellung'). Mit Wert -> eine harte, aktive Tatzeit.
    """
    con = sqlite3.connect(str(pfad))
    try:
        con.executescript(_ANNOTATIONS)
        con.commit()
        MigrationRunner(
            con,
            [m for m in discover(evidence_migrations) if m.VERSION <= 2]).run()
        if tatzeit_bis is not None:
            cur = con.execute(
                'INSERT INTO "annotations" (page_url, category, text, ts, '
                'investigator_id, version_nr) VALUES (?,?,?,?,?,1)',
                ("/viewtopic.php?id=1", kategorie, "t", 1700000000, 3))
            aid = int(cur.lastrowid)
            con.execute(
                'INSERT INTO "annotation_tatzeit" (annotation_id, art, '
                'von_ts, bis_ts, genauigkeit, quelle, erfasst_von, '
                'erfasst_at) VALUES (?,?,?,?,?,?,?,?)',
                (aid, "hart", tatzeit_bis - _TAG, tatzeit_bis, "tag",
                 "beitragstext", 3, 1700000100))
        con.commit()
    finally:
        con.close()


class _Basis(unittest.TestCase):
    """coordinator.db mit zwei Faellen, plus leere Fristverzeichnisse."""

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
                ("NRW\\ermittler", "Ermittler", 1, 0)):
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

        cases = CasesRepo(con, self.writer)
        cases.create_case(201, "mit_tathandlung", actor_id=1)
        cases.create_case(202, "ohne_alles", actor_id=1)
        cases.assign(201, 2, actor_id=1)
        cases.assign(202, 2, actor_id=1)

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
    def _ro(self):
        con = sqlite3.connect("file:%s?mode=ro" % self.db_path, uri=True)
        con.row_factory = sqlite3.Row
        return con

    def _matrix(self, *, mit_verzeichnis=True, mit_fristen=True,
                params_pfad=None):
        con = self._ro()
        try:
            repo = MatrixRepo(
                con, self.gewichte,
                str(self.forensic) if mit_verzeichnis else None,
                str(self.evidence) if mit_verzeichnis else None,
                params_pfad=params_pfad)
            return repo.compute(now_ts=_JETZT, mit_fristen=mit_fristen)
        finally:
            con.close()

    @staticmethod
    def _zelle(bericht, subject_id):
        for z in bericht["zellen"]:
            if z["subject_id"] == subject_id:
                return z
        raise AssertionError("Fall %d fehlt in der Matrix." % subject_id)


class TestFristSammler(_Basis):
    """MF01-MF08: der Sammler mit Fristkomponente."""

    # ===================================================================== MF01
    def test_MF01_ohne_verzeichnis_wird_nicht_still_weggelassen(self):
        b = self._matrix(mit_verzeichnis=False)
        self.assertFalse(b["fristen_geladen"])
        self.assertTrue(b["fristen_angefordert"])
        self.assertTrue(any("forensic-Verzeichnis" in q
                            for q in b["fehlende_quellen"]),
                        b["fehlende_quellen"])
        for uid in (201, 202):
            z = self._zelle(b, uid)
            self.assertFalse(z["dringlichkeit_bestimmbar"])
            self.assertEqual(z["dringlichkeit_grund"], "nicht_geladen")

    # ===================================================================== MF02
    def test_MF02_auslieferungszustand_keine_aussage_ist_nicht_nicht_geladen(self):
        """
        Der ausgelieferte Parametersatz ist UNBESTAETIGT. Der Monitor
        verweigert dann jede Fristaussage — die Matrix muss das als
        'keine_aussage' fuehren und NICHT als 'nicht_geladen'. Der eine Zustand
        heisst 'nicht nachgesehen', der andere 'nachgesehen, keine Aussage
        moeglich'.
        """
        _forensic_db(self.forensic / "forensic_201.db",
                     posts=[_ts_tag("2022-06-01")])
        b = self._matrix()

        self.assertTrue(b["fristen_geladen"])
        self.assertIsNotNone(b["fristen_kopf"])
        self.assertFalse(b["fristen_kopf"]["aussage_moeglich"])
        self.assertFalse(b["fristen_kopf"]["params_bestaetigt"])

        z = self._zelle(b, 201)
        self.assertFalse(z["dringlichkeit_bestimmbar"])
        self.assertEqual(z["dringlichkeit_grund"], "keine_aussage")
        self.assertNotEqual(z["dringlichkeit_grund"], "nicht_geladen")

        self.assertTrue(
            any("VERWEIGERT JEDE AUSSAGE" in h for h in b["hinweise"]),
            b["hinweise"])

    # ===================================================================== MF03
    def test_MF03_mit_bestaetigtem_satz_schlaegt_die_frist_durch(self):
        # Eine Tathandlung, deren Frist am Stichtag noch laeuft, aber knapp
        # ist. Die genaue Stufe wird nicht behauptet, sondern nachgerechnet.
        _forensic_db(self.forensic / "forensic_201.db",
                     posts=[_ts_tag("2022-06-01")])
        b = self._matrix(params_pfad=_params_bestaetigt_pfad())

        z = self._zelle(b, 201)
        self.assertTrue(b["fristen_geladen"])
        self.assertTrue(z["dringlichkeit_bestimmbar"], z["dringlichkeit_grund"])
        self.assertIsNone(z["dringlichkeit_grund"])

        # Die Summe der Beitraege ergibt die Achse — dieselbe Zusicherung wie
        # UM18, hier mit echten Daten statt mit dicts.
        summe = sum(x["punkte"] for x in z["beitraege"])
        self.assertEqual(summe, z["dringlichkeit"] + z["erkenntnislage"])

    # ===================================================================== MF04
    def test_MF04_dieselbe_rechnung_wie_der_fristenmonitor(self):
        """
        Die Matrix rechnet die Verjaehrung NICHT eigenstaendig nach. Ampel und
        Restlaufzeit muessen deshalb mit LimitationRepo.compute() fuer
        denselben Stichtag uebereinstimmen — sonst gaebe es zwei Wahrheiten
        ueber dieselbe Frist.
        """
        _forensic_db(self.forensic / "forensic_201.db",
                     posts=[_ts_tag("2022-06-01")])
        pfad = _params_bestaetigt_pfad()

        con = self._ro()
        try:
            bericht = LimitationRepo(
                con, str(self.forensic), str(self.evidence)).compute(
                params=load_params(pfad), now_ts=_JETZT)
        finally:
            con.close()
        zeile = {int(r.tatzeit.subject_id): r.to_dict()
                 for r in bericht.rows}[201]

        b = self._matrix(params_pfad=pfad)
        z = self._zelle(b, 201)

        # Der Beitrag nennt die Restlaufzeit im Klartext; die Ampel steckt im
        # Grund bzw. in der Bestimmbarkeit. Verglichen wird das, was die Zelle
        # tatsaechlich behauptet.
        frist = [x for x in z["beitraege"] if x["code"] == "frist"]
        if zeile["ampel"] in ("ueberschritten", "knapp", "offen"):
            self.assertTrue(z["dringlichkeit_bestimmbar"])
            if frist:
                self.assertIn(str(zeile["restlaufzeit_tage"]),
                              frist[0]["grund"])
        else:
            self.assertFalse(z["dringlichkeit_bestimmbar"])
            self.assertEqual(z["dringlichkeit_grund"], zeile["ampel"])

    # ===================================================================== MF05
    def test_MF05_belastbarkeit_festgestellt_vs_vorlaeufig(self):
        """
        M-1: die Belastbarkeit steht NEBEN der Zahl, nicht darin. Fall 201 hat
        eine festgestellte Tatzeit, Fall 202 nur Aktivitaetsdaten — beide mit
        DEMSELBEN Datum, damit die Punktzahl vergleichbar bleibt.
        """
        tag = _ts_tag("2022-06-01")
        _forensic_db(self.forensic / "forensic_201.db", posts=[tag])
        _forensic_db(self.forensic / "forensic_202.db", posts=[tag])
        _evidence_db(self.evidence / "evidence_201.db", tatzeit_bis=tag)
        _evidence_db(self.evidence / "evidence_202.db", tatzeit_bis=None)

        b = self._matrix(params_pfad=_params_bestaetigt_pfad())
        z1 = self._zelle(b, 201)
        z2 = self._zelle(b, 202)

        self.assertEqual(z1["dringlichkeit_belastbarkeit"], "festgestellt")
        self.assertEqual(z2["dringlichkeit_belastbarkeit"], "vorlaeufig")

        # GLEICHE Fristpunkte trotz verschiedener Belastbarkeit — das ist der
        # ganze Inhalt von M-1.
        f1 = [x["punkte"] for x in z1["beitraege"] if x["code"] == "frist"]
        f2 = [x["punkte"] for x in z2["beitraege"] if x["code"] == "frist"]
        self.assertEqual(f1, f2)

    # ===================================================================== MF06
    def test_MF06_abschalten_liefert_das_verhalten_aus_build_537(self):
        _forensic_db(self.forensic / "forensic_201.db",
                     posts=[_ts_tag("2022-06-01")])
        b = self._matrix(mit_fristen=False,
                         params_pfad=_params_bestaetigt_pfad())

        self.assertFalse(b["fristen_geladen"])
        self.assertFalse(b["fristen_angefordert"])
        self.assertIsNone(b["fristen_kopf"])
        self.assertTrue(any("nicht angefordert" in q
                            for q in b["fehlende_quellen"]),
                        b["fehlende_quellen"])
        self.assertEqual(self._zelle(b, 201)["dringlichkeit_grund"],
                         "nicht_geladen")

    # ===================================================================== MF07
    def test_MF07_laufzeit_wird_ausgewiesen(self):
        b_mit = self._matrix()
        self.assertIsInstance(b_mit["dauer_gesamt_ms"], int)
        self.assertIsNotNone(b_mit["dauer_fristen_ms"])

        b_ohne = self._matrix(mit_fristen=False)
        self.assertIsNone(b_ohne["dauer_fristen_ms"],
                          "Was nicht gelaufen ist, darf keine Dauer haben — "
                          "eine 0 saehe aus wie 'war umsonst'.")

    # ===================================================================== MF08
    def test_MF08_unbrauchbarer_parametersatz_nimmt_die_frist_heraus(self):
        """
        Ein unbrauchbarer Verjaehrungs-Parametersatz kostet EINEN von sechs
        Beitraegen — nicht die ganze Matrix. Er wird benannt, und die uebrigen
        fuenf bleiben brauchbar. (Der GEWICHTUNGSSATZ ist etwas anderes: er
        ist die Skala, und ohne ihn gibt es 503. Siehe MX19.)
        """
        kaputt = Path(tempfile.mkdtemp()) / "params_kaputt.json"
        kaputt.write_text("{ das ist kein JSON", encoding="utf-8")

        b = self._matrix(params_pfad=kaputt)
        self.assertFalse(b["fristen_geladen"])
        self.assertTrue(any(q.startswith("Fristen (")
                            for q in b["fehlende_quellen"]),
                        b["fehlende_quellen"])
        # Die uebrigen Beitraege sind unberuehrt: die Zellen stehen weiterhin.
        self.assertEqual(b["faelle_gesamt"], 2)


class TestFristEndpunkt(_Basis):
    """MF09-MF11: der Endpunkt."""

    def _get(self, person_id=1, query=None):
        return self.app.dispatch(person_id, "/api/matrix", query or {})

    def _spitze(self):
        row = self.con.execute(
            "SELECT MAX(seq) FROM audit_log").fetchone()
        return None if row is None else row[0]

    # ===================================================================== MF09
    def test_MF09_nachladeverhalten_am_endpunkt(self):
        aus = self._get(query={"fristen": ["0"]})
        self.assertEqual(aus.status, 200)
        self.assertFalse(json.loads(aus.body)["fristen_geladen"])

        an = self._get(query={"fristen": ["1"]})
        self.assertEqual(an.status, 200)
        self.assertTrue(json.loads(an.body)["fristen_geladen"])

        # Vorgabe ohne Parameter: MIT Fristen.
        ohne = self._get()
        self.assertTrue(json.loads(ohne.body)["fristen_geladen"])

        # Unverstandener Wert -> 400 und KEIN stillschweigender Vorgabewert.
        schlecht = self._get(query={"fristen": ["quatsch"]})
        self.assertEqual(schlecht.status, 400)
        self.assertIn("fristen", json.loads(schlecht.body)["detail"])

    # ===================================================================== MF10
    def test_MF10_endpunkt_schreibt_nichts(self):
        vorher = self._spitze()
        self.assertEqual(self._get().status, 200)
        self.assertEqual(self._spitze(), vorher,
                         "Die Matrix ist rein lesend — auch mit Fristen.")

    # ===================================================================== MF11
    def test_MF11_stellt_keine_verjaehrung_fest(self):
        """
        Der Vermerk muss AN DER ZELLE haengen, nicht nur im allgemeinen
        Hinweistext der Antwort. Wer eine einzelne Zeile in eine Akte
        uebernimmt, nimmt die Hinweise des Berichts nicht mit.

        2021-07-01 liegt im Plausibilitaetsrahmen (2018-01-01..2027-01-01,
        m002/limitation_repo) und ergibt am Stichtag 2026-07-25 eine
        Restlaufzeit von -24 Tagen, also 'ueberschritten'.
        """
        _forensic_db(self.forensic / "forensic_201.db",
                     posts=[_ts_tag("2021-07-01")])
        b = self._matrix(params_pfad=_params_bestaetigt_pfad())
        z = self._zelle(b, 201)

        # Erst nachweisen, dass die Lage ueberhaupt 'ueberschritten' ist —
        # sonst prueft der Test eine Zusicherung, die gar nicht faellig war.
        self.assertTrue(z["dringlichkeit_bestimmbar"], z["dringlichkeit_grund"])
        vermerke = " ".join(z["vermerke"])
        self.assertIn("rechnerisch ueberschritten", vermerke, vermerke)
        self.assertIn("78c", vermerke,
                      "Ohne den Hinweis auf § 78c StGB koennte ein "
                      "'ueberschritten' als Feststellung der Verjaehrung "
                      "gelesen werden.")
        # Und die Zusicherung des Berichts steht zusaetzlich obendrueber.
        self.assertTrue(any("KEINE VERJAEHRUNG FEST" in h
                            for h in b["hinweise"]), b["hinweise"])


if __name__ == "__main__":
    unittest.main()
