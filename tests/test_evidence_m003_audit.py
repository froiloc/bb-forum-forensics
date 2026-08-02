# =============================================================================
# tests/test_evidence_m003_audit.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Testsuite fuer Build 533: die Evidence-Migration m003 (evidence_audit_log)
# und die Klasse EvidenceAuditLog.
#
# Diese Suite prueft eine Migration auf einer Datenbank, in der ab dem
# 01.07.2026 ERMITTLERDATEN liegen. Der Schwerpunkt liegt deshalb — wie bei
# TZ01-TZ12 zu m002 — nicht auf "die Tabelle ist da", sondern auf WIRKUNG:
#
#   EA01 — Die Migration laeuft ueber die ECHTE Migrationskette und wird in
#          'schema_migrations' als Version 3 / 'additive' registriert. Die
#          Kette ist damit [1, 2, 3, 4] (M004 seit Build 660).
#   EA02 — Der Spaltensatz stimmt mit ERWARTETE_SPALTEN ueberein, in der
#          Reihenfolge — und er ist deckungsgleich mit dem der coordinator-
#          Kette (audit_log), BIS AUF den FOREIGN KEY, den es in einer
#          evidence-Datei nicht geben kann.
#   EA03 — DIE WICHTIGSTE ZUSICHERUNG: 'annotations' UND 'annotation_tatzeit'
#          sind INHALTLICH unberuehrt (Inhaltshash, Muster TZ04).
#   EA04 — Nach dem Lauf enthaelt die Kette GENAU eine Zeile: die Genesis. Der
#          Runner schreibt fuer den evidence-Strang kein MIGRATION_APPLIED
#          (er laeuft dort ohne AuditLog).
#   EA05 — Die Append-only-Trigger GREIFEN: UPDATE und DELETE auf
#          evidence_audit_log werden abgewiesen.
#   EA06 — Zweiter Lauf ist folgenlos, und es entsteht KEINE zweite Genesis.
#   EA07 — DIE ENTSCHEIDENDE PROBE GEGEN DIVERGENZ: EvidenceAuditLog und
#          AuditLog erzeugen fuer DIESELBE Eingabe DENSELBEN row_hash. Beide
#          Klassen existieren nebeneinander (Begruendung im Modulkopf von
#          evidence_audit_log.py); dieser Test ist die Absicherung dagegen,
#          dass sie je auseinanderlaufen.
#   EA08 — verify_chain() DECKT EINE MANIPULATION AUF. Kein Existenztest: die
#          Kette wird unter Umgehung der Trigger veraendert und muss brechen.
#   EA09 — Das Migrationsmodul benutzt KEIN executescript() (Lehre aus dem
#          Fehler in Build 532, m002-Kopf Punkt 5a).
#   EA10 — Fehlt 'annotations', bricht die Migration ab und legt NICHTS an.
#   EA11 — Existiert 'evidence_audit_log' bereits mit ANDEREM Aufbau, bricht
#          die Migration ab statt ihn stillschweigend zu uebernehmen.
#
# Version: v0.8.533 · Build: 533 · 2026-07-26
# =============================================================================

import hashlib
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.evidence as evidence_migrations        # noqa: E402
from management.audit.audit_log import AuditLog                     # noqa: E402
from management.audit.evidence_audit_log import (                   # noqa: E402
    EvidenceAuditLog, EvidenceAuditLogError,
)
from management.audit.event_types import EventType                  # noqa: E402
from management.audit.hashing import GENESIS_PREV_HASH              # noqa: E402
from management.migrations.evidence import (                        # noqa: E402
    m003_evidence_audit_log as M003,
)
from management.migrations.runner import MigrationRunner, discover  # noqa: E402

#: Aufbau von 'annotations' — uebernommen aus tests/test_evidence_m002_tatzeit.py,
#  damit beide Suiten dieselbe Ausgangslage haben.
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


def _inhalts_fingerabdruck(con, tabelle: str) -> str:
    """
    Inhaltshash einer Tabelle — indexunabhaengig, nach rowid.

    Ein Vergleich der DATEI-Pruefsumme waere untauglich: die Datei aendert sich
    zwangslaeufig, weil eine Tabelle hinzukommt. Was gleich bleiben MUSS, ist
    der Inhalt der Bestandstabellen. (Muster TZ04 aus Build 532.)
    """
    h = hashlib.sha256()
    spalten = [str(r[1]) for r in con.execute('PRAGMA table_info("%s")' % tabelle)]
    h.update((",".join(spalten)).encode("utf-8"))
    liste = ", ".join('"%s"' % s for s in spalten)
    for zeile in con.execute('SELECT %s FROM "%s" ORDER BY rowid'
                             % (liste, tabelle)):
        h.update(repr(tuple(zeile)).encode("utf-8", "surrogatepass"))
    return h.hexdigest()


class TestEvidenceM003Audit(unittest.TestCase):

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.pfad = self.dir / "evidence_4711.db"
        self.con = sqlite3.connect(str(self.pfad))
        self.con.row_factory = sqlite3.Row
        self.con.executescript(_ANNOTATIONS)
        # Zwei Bestandszeilen: ohne sie waere EA03 ein Leerbefund.
        self.con.execute(
            'INSERT INTO "annotations" (page_url, category, text, ts, '
            'investigator_id, local_id) VALUES (?,?,?,?,?,?)',
            ("/viewtopic.php?id=1", "§ 184b", "Verweis auf Material",
             1700000000, 3, "abc-123"))
        self.con.execute(
            'INSERT INTO "annotations" (page_url, category, text, ts, '
            'investigator_id, local_id) VALUES (?,?,?,?,?,?)',
            ("/viewtopic.php?id=2", "Sonstiges", "Zeitangabe im Text",
             1700000100, 3, None))
        self.con.commit()
        self.mods = discover(evidence_migrations)

    def tearDown(self):
        try:
            self.con.close()
        except sqlite3.Error:
            pass
        shutil.rmtree(self.dir, ignore_errors=True)

    def _lauf(self, con=None):
        return MigrationRunner(con or self.con, self.mods).run()

    def _spalten(self, con, tabelle):
        return tuple(str(r[1]) for r in
                     con.execute('PRAGMA table_info("%s")' % tabelle))

    # ===================================================================== EA01
    def test_EA01_migration_wird_registriert(self):
        angewandt = self._lauf()
        # Build 660: M004 (sort_index TEXT->INTEGER) ist hinzugekommen.
        # Die Liste wird MITGEZOGEN und nicht auf ">= [1,2,3]" aufgeweicht -
        # eine Erwartung, die jede kuenftige Migration stillschweigend
        # durchliesse, pruefte die Kette nicht mehr.
        self.assertEqual(angewandt, [1, 2, 3, 4],
                         "Die evidence-Kette muss nach Build 660 "
                         "[1,2,3,4] sein.")
        reg = self.con.execute(
            "SELECT version, kind FROM schema_migrations WHERE version = 3"
        ).fetchone()
        self.assertIsNotNone(reg, "M003 ist nicht registriert.")
        self.assertEqual(reg["kind"], "additive")

    # ===================================================================== EA02
    def test_EA02_spalten_und_deckungsgleich_mit_coordinator_kette(self):
        self._lauf()
        self.assertEqual(self._spalten(self.con, EvidenceAuditLog.TABLE),
                         M003.ERWARTETE_SPALTEN)

        # Und jetzt die eigentliche Aussage: derselbe Spaltensatz wie in der
        # coordinator-Kette. Die Hash-Formel haengt an dieser Feldmenge — eine
        # Abweichung machte die beiden Ketten unvergleichbar.
        andere = sqlite3.connect(":memory:")
        andere.row_factory = sqlite3.Row
        andere.execute(
            "CREATE TABLE person (id INTEGER PRIMARY KEY AUTOINCREMENT)")
        AuditLog.create_schema(andere)
        self.assertEqual(self._spalten(self.con, EvidenceAuditLog.TABLE),
                         self._spalten(andere, "audit_log"))

        # Der Unterschied, der bleiben MUSS: kein FOREIGN KEY, denn in einer
        # evidence-Datei gibt es keine Tabelle 'person'.
        fks = self.con.execute(
            'PRAGMA foreign_key_list("%s")' % EvidenceAuditLog.TABLE).fetchall()
        self.assertEqual(len(fks), 0,
                         "evidence_audit_log darf keinen FK nach person haben "
                         "— die Tabelle existiert in dieser Datei nicht.")
        andere.close()

    # ===================================================================== EA03
    def test_EA03_bestandstabellen_bleiben_inhaltlich_unberuehrt(self):
        # m001+m002 zuerst anwenden, damit 'annotation_tatzeit' existiert und
        # mitgeprueft werden kann.
        MigrationRunner(self.con, [m for m in self.mods if m.VERSION <= 2]).run()
        self.con.execute(
            'INSERT INTO "annotation_tatzeit" (annotation_id, art, von_ts, '
            'quelle, erfasst_von, erfasst_at) VALUES (?,?,?,?,?,?)',
            (1, "hart", 1600000000, "beitragstext", 3, 1700000200))
        self.con.commit()

        vorher_ann = _inhalts_fingerabdruck(self.con, "annotations")
        vorher_tz = _inhalts_fingerabdruck(self.con, "annotation_tatzeit")

        angewandt = self._lauf()
        self.assertEqual(angewandt, [3, 4])

        self.assertEqual(_inhalts_fingerabdruck(self.con, "annotations"),
                         vorher_ann,
                         "m003 hat 'annotations' veraendert — additiv verletzt.")
        self.assertEqual(_inhalts_fingerabdruck(self.con, "annotation_tatzeit"),
                         vorher_tz,
                         "m003 hat 'annotation_tatzeit' veraendert.")

    # ===================================================================== EA04
    def test_EA04_kette_enthaelt_genau_die_genesis(self):
        self._lauf()
        zeilen = self.con.execute(
            "SELECT seq, event_type, target_type, target_id, prev_hash "
            "FROM evidence_audit_log ORDER BY seq").fetchall()
        self.assertEqual(len(zeilen), 1,
                         "Nach m003 darf GENAU die Genesis in der Kette "
                         "stehen — der Runner schreibt fuer evidence kein "
                         "MIGRATION_APPLIED (er laeuft dort ohne AuditLog).")
        g = zeilen[0]
        self.assertEqual(int(g["seq"]), 1)
        self.assertEqual(g["event_type"], EventType.GENESIS)
        self.assertEqual(g["target_type"], "chain")
        self.assertEqual(g["target_id"], "evidence",
                         "Die Genesis muss ihre Kette benennen — sonst ist "
                         "einer einzelnen Zeile nicht anzusehen, woher sie "
                         "stammt.")
        self.assertEqual(g["prev_hash"], GENESIS_PREV_HASH)

        self.assertTrue(EvidenceAuditLog(self.con).verify_chain().ok)

    # ===================================================================== EA05
    def test_EA05_append_only_trigger_greifen(self):
        self._lauf()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.con.execute(
                "UPDATE evidence_audit_log SET event_type = 'x' WHERE seq = 1")
        self.assertIn("append-only", str(ctx.exception))

        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("DELETE FROM evidence_audit_log WHERE seq = 1")

    # ===================================================================== EA06
    def test_EA06_zweiter_lauf_ist_folgenlos_und_ohne_zweite_genesis(self):
        self._lauf()
        vorher = self.con.execute(
            "SELECT COUNT(*) FROM evidence_audit_log").fetchone()[0]
        self.assertEqual(self._lauf(), [],
                         "Zweiter Lauf darf nichts anwenden.")
        self.assertEqual(
            self.con.execute(
                "SELECT COUNT(*) FROM evidence_audit_log").fetchone()[0],
            vorher, "Ein zweiter Lauf hat die Kette veraendert.")

        # Und die Klasse selbst laesst keine zweite Genesis zu.
        with self.assertRaises(EvidenceAuditLogError):
            EvidenceAuditLog(self.con).write_genesis({"x": 1})

    # ===================================================================== EA07
    def test_EA07_beide_ketten_hashen_identisch(self):
        """
        Die Absicherung gegen Divergenz. EvidenceAuditLog ist eine eigene
        Klasse (Begruendung: evidence_audit_log.py, Abschnitt "WAS GETEILT
        WIRD"). Damit sie nie von AuditLog abweicht, wird hier fuer dieselbe
        Eingabe DERSELBE row_hash verlangt.

        Der Test prueft die WIRKUNG (den Hash), nicht die Struktur — die Lehre
        aus den beiden Fehlern von Build 532.
        """
        self._lauf()

        # (a) coordinator-Kette in einer eigenen Datei aufbauen.
        cpath = self.dir / "coordinator.db"
        ccon = sqlite3.connect(str(cpath))
        ccon.row_factory = sqlite3.Row
        ccon.execute("CREATE TABLE person (id INTEGER PRIMARY KEY AUTOINCREMENT)")
        AuditLog.create_schema(ccon)
        cl = AuditLog(ccon)
        cl.write_genesis({"db": "coordinator", "schema": "M001",
                          "created_at": 1700000000}, ts=1700000000)

        # (b) Dieselbe evidence-Kette mit derselben Genesis-Nutzlast neu bauen,
        #     damit ab seq=2 beide Ketten denselben prev_hash tragen.
        epath = self.dir / "evidence_probe.db"
        econ = sqlite3.connect(str(epath))
        econ.row_factory = sqlite3.Row
        EvidenceAuditLog.create_schema(econ)
        el = EvidenceAuditLog(econ)
        el._insert(                                   # noqa: SLF001
            seq=1, ts=1700000000, actor_id=None,
            event_type=EventType.GENESIS, target_type="chain",
            target_id="coordinator",
            payload={"db": "coordinator", "schema": "M001",
                     "created_at": 1700000000},
            meta=None, prev_hash=GENESIS_PREV_HASH,
        )
        self.assertEqual(
            econ.execute("SELECT row_hash FROM evidence_audit_log "
                         "WHERE seq=1").fetchone()["row_hash"],
            ccon.execute("SELECT row_hash FROM audit_log "
                         "WHERE seq=1").fetchone()["row_hash"],
            "Schon die Genesis-Zeile hasht unterschiedlich — die Formel ist "
            "auseinandergelaufen.")

        # (c) Ein echtes Ereignis, Feld fuer Feld gleich.
        args = dict(event_type=EventType.TATZEIT_SET, actor_id=7,
                    target_type="annotation", target_id="42",
                    payload={"b": 2, "a": 1}, meta={"z": "ü"}, ts=1700000500)
        cl.append(**args)
        el.append(**args)
        self.assertEqual(
            econ.execute("SELECT row_hash FROM evidence_audit_log "
                         "WHERE seq=2").fetchone()["row_hash"],
            ccon.execute("SELECT row_hash FROM audit_log "
                         "WHERE seq=2").fetchone()["row_hash"],
            "Die beiden Ketten hashen dasselbe Ereignis unterschiedlich.")
        ccon.close()
        econ.close()

    # ===================================================================== EA08
    def test_EA08_verify_deckt_manipulation_auf(self):
        """
        Wirkungspruefung: Die Trigger sind eine Leitplanke, die Kette ist der
        Beweis. Hier wird die Leitplanke umgangen (Trigger geloescht) und die
        Zeile veraendert — verify_chain() MUSS das finden.
        """
        self._lauf()
        el = EvidenceAuditLog(self.con)
        el.append(event_type=EventType.TATZEIT_SET, actor_id=7,
                  target_type="annotation", target_id="1",
                  payload={"tatzeit_id": 1})
        self.assertTrue(el.verify_chain().ok)

        self.con.execute("DROP TRIGGER evidence_audit_log_no_update")
        self.con.execute(
            "UPDATE evidence_audit_log SET target_id = '999' WHERE seq = 2")
        self.con.commit()

        res = el.verify_chain()
        self.assertFalse(res.ok, "Eine manipulierte Zeile blieb unentdeckt.")
        self.assertEqual(res.first_bad_seq, 2)

    # ===================================================================== EA09
    def test_EA09_kein_executescript_im_migrationsmodul(self):
        """
        Pythons sqlite3 committet vor executescript() IMPLIZIT und beendet
        damit die Transaktion des Runners. Der Fehler ist in Build 532 einmal
        passiert; dieser Test haelt den Quelltext fest, damit er nicht durch
        spaeteres 'Aufraeumen' zurueckkommt.
        """
        quelle = Path(M003.__file__).read_text(encoding="utf-8")
        code = "\n".join(
            z for z in quelle.splitlines() if not z.lstrip().startswith("#"))
        self.assertNotIn("executescript", code)

    # ===================================================================== EA10
    def test_EA10_ohne_annotations_bricht_die_migration_ab(self):
        pfad = self.dir / "fremd.db"
        con = sqlite3.connect(str(pfad))
        con.row_factory = sqlite3.Row
        con.execute("CREATE TABLE irgendwas (id INTEGER)")
        con.commit()
        with self.assertRaises(Exception):
            MigrationRunner(con, self.mods).run()
        namen = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn(EvidenceAuditLog.TABLE, namen,
                         "Nach dem Abbruch darf KEIN Teilzustand bleiben.")
        con.close()

    # ===================================================================== EA11
    def test_EA11_abweichender_bestand_wird_nicht_uebernommen(self):
        MigrationRunner(self.con, [m for m in self.mods if m.VERSION <= 2]).run()
        # Eine Tabelle gleichen Namens, aber mit anderem Aufbau.
        self.con.execute(
            'CREATE TABLE "%s" (seq INTEGER, irgendwas TEXT)'
            % EvidenceAuditLog.TABLE)
        self.con.commit()

        with self.assertRaises(Exception) as ctx:
            self._lauf()
        self.assertIn("abweichendem Aufbau", str(ctx.exception))

        # Der Bestand bleibt, wie er war — kein stiller Umbau.
        self.assertEqual(self._spalten(self.con, EvidenceAuditLog.TABLE),
                         ("seq", "irgendwas"))
        self.assertIsNone(self.con.execute(
            "SELECT 1 FROM schema_migrations WHERE version = 3").fetchone())

    # ===================================================================== EA12
    def test_EA12_row_factory_der_verbindung_bleibt_unangetastet(self):
        """
        GEGENPROBE ZU EINEM ECHTEN FEHLER (2026-07-26).

        Der erste Entwurf setzte im Konstruktor 'con.row_factory =
        sqlite3.Row' — abgeschrieben von AuditLog (audit_log.py:100-101), wo es
        unschaedlich ist. Auf der evidence-Verbindung ist es das nicht: sie
        gehoert dem forensischen Server und wird von rund 150 Stellen
        mitbenutzt. Ein Konstruktoraufruf stellte deren Lesart global um.

        Gefunden hat es kein Test dieses Builds, sondern TZ10 und TZ11 aus
        Build 532 — deren Verbindung liefert Tupel, und nach dem Lauf von m003
        ploetzlich Rows. Dieser Test haelt die Korrektur fest, damit sie nicht
        durch ein spaeteres 'Vereinheitlichen mit AuditLog' zurueckgebaut wird.
        """
        con = sqlite3.connect(":memory:")
        con.executescript(_ANNOTATIONS)
        self.assertIsNone(con.row_factory)

        MigrationRunner(con, self.mods).run()
        self.assertIsNone(
            con.row_factory,
            "m003 hat die row_factory der Verbindung veraendert — damit "
            "liefert jede andere Abfrage des Servers plötzlich Rows statt "
            "Tupel.")

        el = EvidenceAuditLog(con)
        el.append(event_type=EventType.TATZEIT_SET, actor_id=7,
                  target_type="annotation", target_id="1", payload={})
        self.assertTrue(el.verify_chain().ok)
        self.assertIsNone(
            con.row_factory,
            "EvidenceAuditLog hat die row_factory der Verbindung veraendert.")

        # Und die Gegenprobe, dass die Verbindung wirklich noch Tupel liefert.
        zeile = con.execute(
            "SELECT seq FROM evidence_audit_log ORDER BY seq LIMIT 1"
        ).fetchone()
        self.assertIsInstance(zeile, tuple)
        con.close()


if __name__ == "__main__":
    unittest.main()
