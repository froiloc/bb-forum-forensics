# =============================================================================
# tests/test_management_migration_harness.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 317: Backup-/Verify-Harness. VOLLSTAENDIG automatisiert,
# ausschliesslich gegen SYNTHETISCHE, evidenz-/assets-foermige SQLite-DBs —
# KEIN reales Beweismaterial, KEINE Migration wird ausgefuehrt (Bauplan §3.5).
#
# H01 — create_backup: konsistente Kopie (integrity ok), SHA512 reproduzierbar,
#       Quelle unveraendert
# H02 — VACUUM INTO auch bei aktivem WAL konsistent
# H03 — sha512_file deterministisch; andere Inhalte -> andere Hashes
# H04 — integrity_check: intakt ok; gezielt beschaedigt -> nicht ok
# H05 — foreign_key_check: intakt keine Verletzung; gezielte Verletzung erkannt
# H06 — table_rowcounts korrekt ueber alle Tabellen (schema-agnostisch)
# H07 — RowcountVerifier.compare: unerwarteter Verlust erkannt; erwartetes Delta ok
# H08 — BlobVerifier entdeckt BLOB-Spalten dynamisch (assets-foermig: data BLOB)
# H09 — BLOB-Vergleich: bit-identisch ok; ein gekipptes Byte -> erkannt
# H10 — kompletter Harness-Durchlauf fasst die Quelle NIE schreibend an
# H11 — leere DB / DB ohne BLOB-Spalten -> robuste Leerergebnisse, kein Fehler
# H12 — verify_backup bestaetigt Uebereinstimmung und erkennt Manipulation
#
# Version: v0.7.317 · Build: 317 · 2026-07-03
# =============================================================================

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.migration_fleet.harness.backup import BackupTool
from management.migration_fleet.harness.blob import BlobVerifier
from management.migration_fleet.harness.hashing import (
    NULL_MARKER,
    blob_sha256,
    sha512_file,
)
from management.migration_fleet.harness.harness import MigrationHarness
from management.migration_fleet.harness.integrity import IntegrityChecker
from management.migration_fleet.harness.rowcount import RowcountVerifier


class MigrationHarnessTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()

    def tearDown(self):
        for root, _dirs, files in os.walk(self._tmp, topdown=False):
            for fn in files:
                try:
                    os.remove(os.path.join(root, fn))
                except OSError:
                    pass
            try:
                os.rmdir(root)
            except OSError:
                pass

    # ---- synthetische Fixtures --------------------------------------------
    def _evidence_like(self, name="evidence_18.db", n=500, wal=False):
        """Evidenz-foermige DB (Strukturdaten, keine BLOBs)."""
        path = os.path.join(self._tmp, name)
        con = sqlite3.connect(path)
        con.isolation_level = None
        if wal:
            con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE annotations(id INTEGER PRIMARY KEY, "
                    "post_id INTEGER, text TEXT, version_nr INTEGER DEFAULT 1)")
        con.execute("CREATE TABLE reports(id INTEGER PRIMARY KEY, title TEXT)")
        con.executemany("INSERT INTO annotations(post_id, text) VALUES(?, ?)",
                        [(i, "Befund %d %s" % (i, "x" * 80)) for i in range(n)])
        con.executemany("INSERT INTO reports(title) VALUES(?)",
                        [("Bericht %d" % i,) for i in range(5)])
        con.close()
        return path

    def _assets_like(self, name="assets_18.db"):
        """Assets-foermige DB mit BLOB-Spalte (assets.data BLOB)."""
        path = os.path.join(self._tmp, name)
        con = sqlite3.connect(path)
        con.isolation_level = None
        con.execute("CREATE TABLE assets(id INTEGER PRIMARY KEY, "
                    "url TEXT, data BLOB)")
        con.execute("INSERT INTO assets(id, url, data) VALUES(1, 'a', ?)",
                    (b"\x89PNG\x00\x01\x02\x03blob-eins",))
        con.execute("INSERT INTO assets(id, url, data) VALUES(2, 'b', ?)",
                    (b"GIF89a\xff\xfeblob-zwei",))
        con.execute("INSERT INTO assets(id, url, data) VALUES(3, 'c', NULL)")
        con.close()
        return path

    def _corrupt_file(self, path):
        """Ueberschreibt zwei Datenseiten mit 0xFF -> B-Tree defekt."""
        with open(path, "r+b") as f:
            f.seek(2 * 4096)
            f.write(b"\xFF" * (2 * 4096))

    # H01 -------------------------------------------------------------------
    def test_h01_backup_consistent_and_source_untouched(self):
        src = self._evidence_like()
        src_hash_before = sha512_file(src)
        res = BackupTool.create_backup(src, os.path.join(self._tmp, "bk"),
                                       db_label="evidence_18", version=4)
        self.assertTrue(os.path.exists(res.path))
        self.assertTrue(res.path.endswith(".backup.db"))
        # Backup ist intakt.
        self.assertTrue(IntegrityChecker.integrity_check(res.path).ok)
        # SHA512 reproduzierbar.
        self.assertEqual(res.sha512, sha512_file(res.path))
        # Quelle voellig unveraendert.
        self.assertEqual(sha512_file(src), src_hash_before)

    # H02 -------------------------------------------------------------------
    def test_h02_backup_with_wal(self):
        src = self._evidence_like(name="evidence_wal.db", wal=True)
        res = BackupTool.create_backup(src, self._tmp, db_label="evidence_wal",
                                       version=1)
        self.assertTrue(IntegrityChecker.integrity_check(res.path).ok)
        # Rowcounts der Kopie == Quelle.
        self.assertEqual(RowcountVerifier.table_rowcounts(res.path),
                         RowcountVerifier.table_rowcounts(src))

    # H03 -------------------------------------------------------------------
    def test_h03_sha512_deterministic(self):
        a = os.path.join(self._tmp, "a.bin"); open(a, "wb").write(b"hallo")
        b = os.path.join(self._tmp, "b.bin"); open(b, "wb").write(b"hallo")
        c = os.path.join(self._tmp, "c.bin"); open(c, "wb").write(b"hallX")
        self.assertEqual(sha512_file(a), sha512_file(b))
        self.assertNotEqual(sha512_file(a), sha512_file(c))
        # BLOB-Hash: NULL unterscheidbar.
        self.assertEqual(blob_sha256(None), NULL_MARKER)
        self.assertNotEqual(blob_sha256(b""), blob_sha256(None))

    # H04 -------------------------------------------------------------------
    def test_h04_integrity_detects_corruption(self):
        src = self._evidence_like(name="ev_corrupt.db", n=1000)
        self.assertTrue(IntegrityChecker.integrity_check(src).ok)
        self._corrupt_file(src)
        result = IntegrityChecker.integrity_check(src)
        self.assertFalse(result.ok)
        self.assertTrue(result.messages)

    # H05 -------------------------------------------------------------------
    def test_h05_foreign_key_check(self):
        path = os.path.join(self._tmp, "fk.db")
        con = sqlite3.connect(path); con.isolation_level = None
        con.execute("CREATE TABLE parent(id INTEGER PRIMARY KEY)")
        con.execute("CREATE TABLE child(id INTEGER PRIMARY KEY, "
                    "pid INTEGER REFERENCES parent(id))")
        con.execute("INSERT INTO parent(id) VALUES(1)")
        con.execute("INSERT INTO child(id, pid) VALUES(1, 1)")
        con.close()
        self.assertEqual(IntegrityChecker.foreign_key_check(path), [])
        # Gezielte Verletzung bei ausgeschalteten FKs einfuegen.
        con = sqlite3.connect(path); con.isolation_level = None
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("INSERT INTO child(id, pid) VALUES(2, 999)")
        con.close()
        violations = IntegrityChecker.foreign_key_check(path)
        self.assertTrue(violations)
        self.assertEqual(violations[0].table, "child")

    # H06 -------------------------------------------------------------------
    def test_h06_table_rowcounts(self):
        src = self._evidence_like(n=42)
        rc = RowcountVerifier.table_rowcounts(src)
        self.assertEqual(rc, {"annotations": 42, "reports": 5})

    # H07 -------------------------------------------------------------------
    def test_h07_rowcount_compare(self):
        before = {"annotations": 100, "reports": 5}
        # Unerwarteter Verlust in annotations.
        after_loss = {"annotations": 90, "reports": 5}
        rep = RowcountVerifier.compare(before, after_loss)
        self.assertFalse(rep.ok)
        self.assertEqual(rep.discrepancies[0].table, "annotations")
        self.assertEqual(rep.discrepancies[0].actual_delta, -10)
        # Mit erwartetem Delta -10 -> ok.
        rep2 = RowcountVerifier.compare(before, after_loss,
                                        expected_deltas={"annotations": -10})
        self.assertTrue(rep2.ok)
        # Neue Tabelle additiv -> informativ, ok bleibt True.
        rep3 = RowcountVerifier.compare(before, {**before, "case_events": 3})
        self.assertTrue(rep3.ok)
        self.assertIn("case_events", rep3.new_tables)

    # H08 -------------------------------------------------------------------
    def test_h08_blob_discovery(self):
        src = self._assets_like()
        digests = BlobVerifier.blob_digests(src)
        # Zwei nicht-NULL BLOBs + ein NULL.
        keys = sorted(digests)
        self.assertEqual(len(keys), 3)
        self.assertTrue(all(k.startswith("assets|data|") for k in keys))
        self.assertIn(NULL_MARKER, digests.values())

    # H09 -------------------------------------------------------------------
    def test_h09_blob_bit_identity(self):
        src = self._assets_like()
        before = BlobVerifier.blob_digests(src)
        # bit-identisch (nichts geaendert).
        self.assertTrue(BlobVerifier.compare(before,
                        BlobVerifier.blob_digests(src)).ok)
        # Ein einziges Byte in id=1 kippen.
        con = sqlite3.connect(src); con.isolation_level = None
        con.execute("UPDATE assets SET data=? WHERE id=1",
                    (b"\x89PNG\x00\x01\x02\x03blob-EINS",))
        con.close()
        rep = BlobVerifier.compare(before, BlobVerifier.blob_digests(src))
        self.assertFalse(rep.ok)
        self.assertTrue(any("assets|data|1" == k for k in rep.changed))

    # H10 -------------------------------------------------------------------
    def test_h10_full_run_source_immutable(self):
        src = self._assets_like(name="assets_run.db")
        src_before = sha512_file(src)
        pre = MigrationHarness.snapshot(src)
        BackupTool.create_backup(src, os.path.join(self._tmp, "bk2"),
                                 db_label="assets_run", version=1)
        report = MigrationHarness.verify_against(src, pre)  # keine Migration -> ok
        self.assertTrue(report.ok)
        # Quelle nach snapshot + backup + verify unveraendert.
        self.assertEqual(sha512_file(src), src_before)

    # H11 -------------------------------------------------------------------
    def test_h11_empty_and_no_blob(self):
        empty = os.path.join(self._tmp, "empty.db")
        sqlite3.connect(empty).close()
        self.assertEqual(RowcountVerifier.table_rowcounts(empty), {})
        self.assertEqual(BlobVerifier.blob_digests(empty), {})
        # evidence-foermig (keine BLOBs) -> leere BLOB-Digests, kein Fehler.
        ev = self._evidence_like(name="ev_noblob.db", n=3)
        self.assertEqual(BlobVerifier.blob_digests(ev), {})
        snap = MigrationHarness.snapshot(ev)
        self.assertTrue(snap.integrity.ok)
        self.assertEqual(snap.blob_digests, {})

    # H12 -------------------------------------------------------------------
    def test_h12_verify_backup(self):
        src = self._evidence_like(name="ev_vb.db", n=20)
        res = BackupTool.create_backup(src, self._tmp, db_label="ev_vb", version=1)
        self.assertTrue(BackupTool.verify_backup(res.path, res.sha512))
        self.assertFalse(BackupTool.verify_backup(res.path, "deadbeef"))


if __name__ == "__main__":
    unittest.main()
