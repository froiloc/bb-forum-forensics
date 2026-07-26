# =============================================================================
# tests/test_tatzeit_endpoint.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Testsuite fuer Build 533: TatzeitEndpoint am FORENSISCHEN Server.
#
# Aufbau bewusst nach dem Muster von tests/test_userinfo_results.py (UE01-UE09),
# damit beide Endpunkte mit demselben Blick geprueft werden. Die Besonderheiten
# dieses Endpunkts sind TE06 (Support-Modus) und TE08 (Kette fehlt) — beides
# Faelle, die es bei ResultsEndpoint nicht gibt, weil der in coordinator.db
# schreibt.
#
#   TE01 — GET liefert Vokabular, Plausibilitaetsrahmen und die Eintraege; und
#          es sagt ausdruecklich, dass der Monitor damit NOCH NICHT rechnet
#          (wird_berechnet=False) — Build 535 schaltet das um.
#   TE02 — GET braucht KEIN eigenes Recht (die Tatzeit steht in der Annotation),
#          meldet aber can_edit=false. Eine unsichtbare Funktion saehe aus wie
#          eine fehlende.
#   TE03 — POST erfasst: Fachzeile und Beleg liegen in DERSELBEN Datei, die
#          Kette verifiziert.
#   TE04 — POST ohne 'tatzeit.edit' -> 403 MIT BEGRUENDUNG, es wird NICHTS
#          geschrieben.
#   TE05 — POST ohne aufloesbaren Ermittler -> 403 (kein Beleg ohne Handelnden).
#   TE06 — DIE KAPSELUNGSPROBE: eine 'subject_id' im Rumpf wird IGNORIERT.
#   TE07 — SUPPORT-MODUS: 409 und NICHTS geschrieben. Im Live-Beistand ist die
#          evidence-Datei nur lesend angebunden; ein Schreibversuch liefe in
#          eine TEMP-Datei, die beim Sitzungsende geloescht wird — ein lautlos
#          verlorener Beleg.
#   TE08 — FEHLT DIE BELEG-KETTE (m003 nicht angewandt), wird NICHT geschrieben
#          und der Grund genannt. Ohne Kette gibt es keinen Beleg.
#   TE09 — FEHLT DIE TABELLE (m002 nicht angewandt), meldet GET das — eine
#          leere Liste saehe aus wie "nichts erfasst".
#   TE10 — POST /_forensic/tatzeit/clear nimmt zurueck und belegt es.
#
# Version: v0.8.533 · Build: 533 · 2026-07-26
# =============================================================================

import json
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations  # noqa: E402
import management.migrations.evidence as evidence_migrations        # noqa: E402
from forensic_api.tatzeit_endpoint import TatzeitEndpoint           # noqa: E402
from management.audit.audit_log import AuditLog                     # noqa: E402
from management.audit.evidence_audit_log import EvidenceAuditLog    # noqa: E402
from management.audit.event_types import EventType                  # noqa: E402
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
from management.migrations.runner import MigrationRunner, discover  # noqa: E402
from management.rbac.rbac_repo import RbacRepo                      # noqa: E402

_PERSON = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT, system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL, is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0, is_support INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
"""

#: Ausgangsbestand, den die coordinator-Migration M002 erwartet (sie zaehlt
#  scrape_jobs). Uebernommen aus tests/test_userinfo_results.py:57-68.
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

_VON = 1600000000
_BIS = 1600086400


class _Handler:
    """Minimaler Ersatz fuer ForensicRequestHandler: faengt die Antwort ab."""

    def __init__(self):
        self.status = None
        self.body = None
        self.content_type = None

    def send_response_body(self, status, body, content_type=None,
                           extra_headers=None):
        self.status = status
        self.body = body
        self.content_type = content_type

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class TestTatzeitEndpoint(unittest.TestCase):

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

        # --- coordinator.db (nur fuer RBAC) ---------------------------------
        self.cpath = str(self.dir / "coordinator.db")
        ccon = sqlite3.connect(self.cpath)
        ccon.isolation_level = None
        ccon.row_factory = sqlite3.Row
        ccon.execute(_PERSON)
        now = int(time.time())
        for pid, kennung, name, sup in ((1, "h0a2898", "Chefin", 1),
                                        (2, "h002", "Mueller", 0),
                                        (3, "h003", "Schmitz", 0)):
            ccon.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?, ?, ?, 1, ?, 0, ?)", (pid, kennung, name, sup, now))
        ccon.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(ccon, discover(coordinator_migrations),
                        audit=AuditLog(ccon), deployed_by="tester").run()
        rbac = RbacRepo(ccon, CoordinatorWriter(ccon, AuditLog(ccon)))
        # NICHT scope-behaftet — Begruendung im Kopf von M032.
        rbac.grant("investigator", "tatzeit.edit", actor_id=1)
        rbac.assign_role(2, "investigator", actor_id=1)
        # Schmitz (3) bleibt OHNE Rolle — die Gegenprobe.
        ccon.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.ccon = ccon

        # --- evidence_<uid>.db ----------------------------------------------
        self.epath = self.dir / "evidence_4711.db"
        econ = sqlite3.connect(str(self.epath), check_same_thread=False)
        econ.row_factory = sqlite3.Row
        econ.executescript(_ANNOTATIONS)
        econ.execute(
            'INSERT INTO "annotations" (page_url, category, text, ts, '
            'investigator_id, local_id) VALUES (?,?,?,?,?,?)',
            ("/viewtopic.php?id=1", "§ 184b", "das war 2020", 1700000000,
             2, "abc-123"))
        econ.commit()
        self.econ = econ
        self._migriere_evidence()

    def _migriere_evidence(self, bis_version=99):
        MigrationRunner(
            self.econ,
            [m for m in discover(evidence_migrations) if m.VERSION <= bis_version]
        ).run()

    def tearDown(self):
        for con in (getattr(self, "ccon", None), getattr(self, "econ", None)):
            try:
                con.close()
            except Exception:                          # noqa: BLE001
                pass
        shutil.rmtree(self.dir, ignore_errors=True)

    # ------------------------------------------------------------------ Hilfen
    def _endpoint(self, *, investigator_id=2, mode="cli", subject_id=4711):
        cfg = MagicMock()
        cfg.get.side_effect = lambda key, *a: (
            self.cpath if key == "paths.coordinator_db" else None)
        ctx = MagicMock()
        ctx.subject_id = subject_id
        ctx.investigator_id = investigator_id
        ctx.mode = mode
        bundle = MagicMock()
        bundle.connection = self.econ
        return TatzeitEndpoint(bundle, ctx, cfg)

    def _post(self, ep, payload, *, clear=False):
        h = _Handler()
        body = json.dumps(payload).encode("utf-8")
        if clear:
            ep.handle_clear(h, body)
        else:
            ep.handle_set(h, body)
        return h

    def _get(self, ep, params=None):
        h = _Handler()
        ep.handle(h, params or {"annotation_id": ["1"]})
        return h

    def _zeilen(self):
        return self.econ.execute(
            'SELECT * FROM "annotation_tatzeit" ORDER BY id').fetchall()

    @staticmethod
    def _gueltig(**over):
        p = {"annotation_id": 1, "local_id": "abc-123", "art": "hart",
             "von_ts": _VON, "bis_ts": _BIS, "genauigkeit": "tag",
             "quelle_code": "beitragstext"}
        p.update(over)
        return p

    # ===================================================================== TE01
    def test_TE01_get_liefert_vokabular_und_rahmen(self):
        h = self._get(self._endpoint())
        self.assertEqual(h.status, 200)
        d = h.json()
        self.assertTrue(d["ok"])
        self.assertTrue(d["can_edit"])
        self.assertEqual(d["eintraege"], [])
        self.assertEqual(d["plausibel_von"], 1514764800)
        self.assertEqual(d["plausibel_bis"], 1798761600)
        self.assertFalse(
            d["wird_berechnet"],
            "Der Monitor rechnet in Build 533 noch NICHT mit der Tatzeit. Die "
            "Maske muss das sagen, damit niemand eine Wirkung erwartet, die "
            "es erst ab Build 535 gibt.")
        codes = [q["code"] for q in d["vokabular"]["quellen"]]
        self.assertIn("beitragstext", codes)
        self.assertIn("sonstiges", codes)
        pflicht = {q["code"]: q["freitext_pflicht"]
                   for q in d["vokabular"]["quellen"]}
        self.assertTrue(pflicht["sonstiges"])
        self.assertFalse(pflicht["beitragstext"])

    # ===================================================================== TE02
    def test_TE02_lesen_ohne_recht_aber_can_edit_false(self):
        h = self._get(self._endpoint(investigator_id=3))
        self.assertEqual(h.status, 200,
                         "Lesen braucht kein eigenes Recht — die Tatzeit steht "
                         "in der Annotation.")
        self.assertFalse(h.json()["can_edit"])

    # ===================================================================== TE03
    def test_TE03_post_erfasst_und_belegt(self):
        h = self._post(self._endpoint(), self._gueltig())
        self.assertEqual(h.status, 200, h.body)
        d = h.json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["version_nr"], 1)

        zeilen = self._zeilen()
        self.assertEqual(len(zeilen), 1)
        self.assertEqual(zeilen[0]["von_ts"], _VON)
        self.assertEqual(zeilen[0]["erfasst_von"], 2)

        beleg = self.econ.execute(
            "SELECT event_type, actor_id FROM evidence_audit_log "
            "WHERE seq = ?", (d["audit_seq"],)).fetchone()
        self.assertEqual(beleg["event_type"], EventType.TATZEIT_SET)
        self.assertEqual(int(beleg["actor_id"]), 2)
        self.assertTrue(EvidenceAuditLog(self.econ).verify_chain().ok)

        # Der Beleg liegt in DERSELBEN Datei wie die Fachzeile — nicht in
        # coordinator.db. Genau dafuer gibt es m003.
        self.assertIsNone(self.ccon.execute(
            "SELECT 1 FROM audit_log WHERE event_type = ?",
            (EventType.TATZEIT_SET,)).fetchone())

    # ===================================================================== TE04
    def test_TE04_ohne_recht_wird_nichts_geschrieben(self):
        h = self._post(self._endpoint(investigator_id=3), self._gueltig())
        self.assertEqual(h.status, 403)
        d = h.json()
        self.assertEqual(d["capability"], "tatzeit.edit")
        self.assertIn("NICHTS geschrieben", d["detail"])
        self.assertEqual(len(self._zeilen()), 0)
        self.assertEqual(
            self.econ.execute(
                "SELECT COUNT(*) AS c FROM evidence_audit_log").fetchone()["c"],
            1, "Es blieb ein Beleg zurueck, obwohl nichts geschrieben wurde.")

    # ===================================================================== TE05
    def test_TE05_ohne_handelnden_wird_nichts_geschrieben(self):
        h = self._post(self._endpoint(investigator_id=None), self._gueltig())
        self.assertEqual(h.status, 403)
        self.assertEqual(h.json()["error"], "no_investigator")
        self.assertEqual(len(self._zeilen()), 0)

    # ===================================================================== TE06
    def test_TE06_subject_id_im_rumpf_wird_ignoriert(self):
        """
        Die Kapselungsprobe (Muster UE07). Der Server hat GENAU EINEN Fall
        geoeffnet; die Tatzeit landet zwangslaeufig in dessen evidence-Datei.
        Ein 'subject_id' im Rumpf darf daran nichts aendern — und genau
        deshalb ist 'tatzeit.edit' nicht scope-behaftet.
        """
        h = self._post(self._endpoint(subject_id=4711),
                       self._gueltig(subject_id=9999))
        self.assertEqual(h.status, 200, h.body)
        # Geschrieben wurde in die geoeffnete Datei — es gibt gar keine andere.
        self.assertEqual(len(self._zeilen()), 1)
        self.assertEqual(self._get(self._endpoint())
                         .json()["subject_id"], 4711)

    # ===================================================================== TE07
    def test_TE07_support_modus_schreibt_nicht(self):
        ep = self._endpoint(mode="support")
        h = self._post(ep, self._gueltig())
        self.assertEqual(h.status, 409)
        self.assertEqual(h.json()["error"], "support_mode")
        self.assertIn("lautlos verloren", h.json()["detail"])
        self.assertEqual(len(self._zeilen()), 0)

        # Und die Sicht sagt, WARUM sie gesperrt ist.
        g = self._get(ep).json()
        self.assertFalse(g["can_edit"])
        self.assertEqual(g["readonly_grund"], "support")

    # ===================================================================== TE08
    def test_TE08_ohne_beleg_kette_wird_nicht_geschrieben(self):
        """
        Eine evidence-Datei, auf der m002 angewandt ist, m003 aber nicht. Ohne
        Kette gibt es keinen Beleg — und ohne Beleg wird nicht geschrieben
        (Grundregel 1). Der Fall ist real: die Fleet faehrt die Migrationen
        einzeln.
        """
        pfad = self.dir / "evidence_ohne_kette.db"
        con = sqlite3.connect(str(pfad), check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.executescript(_ANNOTATIONS)
        con.execute(
            'INSERT INTO "annotations" (page_url, category, text, ts, '
            'investigator_id, local_id) VALUES (?,?,?,?,?,?)',
            ("/x", "§ 184b", "t", 1700000000, 2, "abc-123"))
        con.commit()
        MigrationRunner(
            con, [m for m in discover(evidence_migrations) if m.VERSION <= 2]
        ).run()

        ep = self._endpoint()
        ep._bundle.connection = con                    # noqa: SLF001
        h = self._post(ep, self._gueltig())
        self.assertEqual(h.status, 500)
        self.assertEqual(h.json()["error"], "audit_chain_missing")
        self.assertEqual(
            con.execute('SELECT COUNT(*) AS c FROM "annotation_tatzeit"'
                        ).fetchone()["c"], 0,
            "Es wurde eine Fachzeile ohne Beleg geschrieben.")
        con.close()

    # ===================================================================== TE09
    def test_TE09_fehlende_tabelle_wird_gemeldet_nicht_verschwiegen(self):
        pfad = self.dir / "evidence_roh.db"
        con = sqlite3.connect(str(pfad), check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.executescript(_ANNOTATIONS)
        con.commit()

        ep = self._endpoint()
        ep._bundle.connection = con                    # noqa: SLF001
        h = self._get(ep)
        self.assertEqual(h.status, 500,
                         "Eine leere Liste saehe aus wie 'nichts erfasst'.")
        self.assertEqual(h.json()["error"], "tatzeit_table_missing")
        con.close()

    # ===================================================================== TE10
    def test_TE10_clear_nimmt_zurueck_und_belegt(self):
        grund = "Datum war eine Verwechslung"
        gesetzt = self._post(self._endpoint(), self._gueltig()).json()
        h = self._post(self._endpoint(),
                       {"tatzeit_id": gesetzt["tatzeit_id"],
                        "grund": grund},
                       clear=True)
        self.assertEqual(h.status, 200, h.body)

        zeile = self._zeilen()[0]
        self.assertIsNotNone(zeile["deleted_at"])
        beleg = self.econ.execute(
            "SELECT event_type, content FROM evidence_audit_log WHERE seq = ?",
            (h.json()["audit_seq"],)).fetchone()
        self.assertEqual(beleg["event_type"], EventType.TATZEIT_CLEARED)
        self.assertNotIn("Verwechslung", beleg["content"],
                         "Der Freitext des Grundes gehoert nicht in den Beleg.")
        # Die Laenge belegt, DASS ein Grund angegeben war, ohne ihn in den
        # Beleg zu tragen. Berechnet statt hart eingetragen — eine
        # abgeschriebene Zahl prueft nur die Abschrift.
        self.assertIn('"grund_len":%d' % len(grund), beleg["content"])

        # Zweites Zuruecknehmen -> 400, nichts aendert sich.
        h2 = self._post(self._endpoint(),
                        {"tatzeit_id": gesetzt["tatzeit_id"]}, clear=True)
        self.assertEqual(h2.status, 400)
        self.assertTrue(EvidenceAuditLog(self.econ).verify_chain().ok)


if __name__ == "__main__":
    unittest.main()
