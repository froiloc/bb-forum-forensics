# =============================================================================
# tests/test_evidence_m004_sort_index.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Migration
# Build 660 — Vorgang 99bf0eb5 (report_block_order.sort_index TEXT -> INTEGER)
# =============================================================================
# Deckt ab: management/migrations/evidence/m004_sort_index_integer.py und
#           tools/pruefe_sort_index.py.
#
#   SI01 — Registrierung: die evidence-Kette ist danach [1,2,3,4]; M004 steht
#          als 'destructive' mit Vorher-/Nachher-Zeilenzahl im Register.
#   SI02 — DIE WIRKUNG, UM DIE ES GEHT: die Ausgabereihenfolge ueber zehn
#          Bausteine ist vorher lexikographisch FALSCH und danach richtig.
#          Geprueft ueber DENSELBEN Ausdruck, den get_blocks_for_report
#          benutzt (db/evidence_db.py:1819).
#   SI03 — ZWEITE, BISHER NICHT VERZEICHNETE FOLGE: ein Block OHNE
#          Sortierungseintrag steht vorher am ANFANG des Berichts und danach
#          am Ende — wie es der Docstring von get_blocks_for_report zusagt.
#   SI04 — VERLUSTFREIHEIT je Zeile: jede block_id traegt danach genau die
#          Zahl, die ihr Text vorher bezeichnete.
#   SI05 — ON DELETE CASCADE UEBERLEBT. Das ist der Fall, den eine
#          nachgeschriebene DDL still zerstoert haette: die Falldateien tragen
#          die Kaskade, db/evidence_db.py:300 nicht.
#   SI06 — Struktur im Uebrigen unveraendert: Spalten, notnull, Vorgabewerte,
#          Primaerschluessel und Index sind vor und nach dem Umbau gleich.
#   SI07 — IDEMPOTENZ: ein zweiter Lauf aendert nichts; eine Datei, die
#          bereits INTEGER traegt, wird nicht angefasst.
#   SI08 — Ein Zweifelsfall wird UEBERNOMMEN und in evidence_audit_log
#          BELEGT (Festlegung mc 2026-08-02), nicht nur ins Log geschrieben.
#   SI09 — GRENZE DER FESTLEGUNG: Zweifelsfall UND keine Hash-Kette -> Abbruch.
#          Eine Umwandlung ohne dauerhaften Beleg findet nicht statt.
#   SI10 — Fremde Datei (ohne 'annotations') -> Abbruch ohne Aenderung.
#   SI11 — Fehlende report_block_order -> kein Abbruch, aber eine Meldung.
#   SI12 — Unerwarteter Spaltentyp -> Abbruch statt Raten.
#   SI13 — verify(): geaenderte Zeilenzahl wirft (Klammer des Runners).
#   PS01 — Pruefwerkzeug: erkennt TEXT- und INTEGER-Dateien und zaehlt richtig.
#   PS02 — Pruefwerkzeug: Rueckgabewert 3 bei einem Zweifelsfall, 2 ohne.
#   PS03 — Pruefwerkzeug: meldet, ob sich die Reihenfolge ueberhaupt aendert.
#   PS04 — Pruefwerkzeug: eine unlesbare Datei wird GENANNT (Rueckgabewert 4).
#   PS05 — Pruefwerkzeug: Dateien ausserhalb der Form evidence_<uid>.db werden
#          uebergangen UND genannt (Transportdateien, Build 658).
#   PS06 — Pruefwerkzeug schreibt NICHTS: MD5 vor == nach.
#   PS07 — Die kanonische Form ist in Migration und Pruefwerkzeug DIESELBE.
#
# Version: v0.8.660 · Build: 660 · 2026-08-02
# =============================================================================

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.evidence as evidence_migrations
from management.migrations.runner import MigrationRunner, discover
from management.migrations.evidence import m004_sort_index_integer as M4
from management.audit.evidence_audit_log import EvidenceAuditLog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "pruefe_sort_index",
    str(Path(__file__).resolve().parent.parent / "tools" / "pruefe_sort_index.py"))
PS = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(PS)


#: Die DDL, wie sie in echten Falldatenbanken steht — MIT ON DELETE CASCADE.
#  Abgeschrieben aus evidence_uid.db.schema.sql:77-85 (Abzug einer echten
#  Prepper-Datei). Genau diese Form muss der Umbau erhalten.
_DDL_ALT = '''
CREATE TABLE IF NOT EXISTS "report_block_order" (
	"block_id"	TEXT NOT NULL,
	"sort_index"	TEXT NOT NULL,
	"last_modified_by"	TEXT NOT NULL,
	"last_modified_at"	INTEGER NOT NULL,
	PRIMARY KEY("block_id"),
	FOREIGN KEY("block_id") REFERENCES "report_blocks"("block_id") ON DELETE CASCADE
)'''

#: Der Ausdruck, mit dem der Server die Bloecke sortiert. WOERTLICH aus
#  db/evidence_db.py:1817-1819 uebernommen — ein nachgebauter Ausdruck
#  pruefte etwas anderes, als der Server tut.
_ORDER_SQL = (
    "SELECT rb.block_id FROM report_blocks rb "
    "LEFT JOIN report_block_order rbo ON rbo.block_id = rb.block_id "
    "WHERE rb.report_id = 1 "
    "ORDER BY COALESCE(rbo.sort_index, 999999) ASC, rb.created_at ASC")


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _baue_evidence(pfad: Path, *, sort_typ="TEXT", werte=None,
                   ohne_ordnung=False, mit_kette=True,
                   ohne_block_order=False, ohne_annotations=False):
    """Legt eine schlanke, aber ECHTE evidence-Datei an."""
    con = sqlite3.connect(str(pfad))
    con.isolation_level = None
    con.execute("PRAGMA journal_mode=delete")
    if not ohne_annotations:
        con.execute("CREATE TABLE annotations (id INTEGER PRIMARY KEY, "
                    "page_url TEXT NOT NULL)")
    con.execute("CREATE TABLE reports (id INTEGER PRIMARY KEY, title TEXT)")
    con.execute("CREATE TABLE report_blocks (block_id TEXT PRIMARY KEY, "
                "report_id INTEGER, created_at INTEGER)")
    if not ohne_block_order:
        con.execute(_DDL_ALT.replace('"sort_index"	TEXT',
                                     '"sort_index"	%s' % sort_typ))
        con.execute('CREATE INDEX IF NOT EXISTS "rbo_sort_idx" '
                    'ON "report_block_order" ("sort_index")')
    if werte is None:
        werte = [0, 1, 2, 9, 10, 11, 20]
    for i, w in enumerate(werte):
        bid = "b%02d" % i
        con.execute("INSERT INTO report_blocks VALUES (?,1,?)", (bid, 1000 + i))
        if not ohne_block_order:
            con.execute("INSERT INTO report_block_order VALUES (?,?,'inv',1000)",
                        (bid, w))
    if ohne_ordnung:
        con.execute("INSERT INTO report_blocks VALUES ('OHNE',1,9999)")
    if mit_kette:
        con.execute("BEGIN IMMEDIATE")
        EvidenceAuditLog.create_schema(con)
        EvidenceAuditLog(con).write_genesis({"db": "evidence", "schema": "T"})
        con.execute("COMMIT")
    con.commit()
    con.close()


def _lauf(pfad: Path):
    """Faehrt die volle evidence-Kette (M001..M004) auf der Datei."""
    con = sqlite3.connect(str(pfad))
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    try:
        return MigrationRunner(con, discover(evidence_migrations),
                               audit=None, deployed_by="test").run(), con
    except Exception:
        con.close()
        raise


def _nur_m004(con: sqlite3.Connection):
    """Faehrt AUSSCHLIESSLICH M004 in einer Transaktion (wie der Runner)."""
    con.execute("BEGIN IMMEDIATE")
    try:
        before = M4.precount(con)
        M4.up(con)
        after = M4.postcount(con)
        M4.verify(con, before, after)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return before, after


class M004Tests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.pfad = Path(self._tmp) / "evidence_1488.db"

    def tearDown(self):
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def _typ(self, con):
        return M4._deklarierter_typ(con)

    # SI01 -------------------------------------------------------------------
    def test_si01_registrierung(self):
        _baue_evidence(self.pfad)
        angewandt, con = _lauf(self.pfad)
        try:
            self.assertEqual(angewandt, [1, 2, 3, 4])
            reg = con.execute("SELECT kind, row_count_before, row_count_after "
                              "FROM schema_migrations WHERE version = 4"
                              ).fetchone()
            self.assertIsNotNone(reg, "M004 ist nicht registriert.")
            self.assertEqual(reg["kind"], "destructive")
            # Die Zeilenzahlen sind der maschinelle Verlustfreiheits-Beleg
            # (Leitfaden Phase 2, Differenzbericht).
            self.assertEqual(reg["row_count_before"], 7)
            self.assertEqual(reg["row_count_after"], 7)
        finally:
            con.close()

    # SI02 -------------------------------------------------------------------
    def test_si02_reihenfolge_wird_richtig(self):
        """DER KERN DES VORGANGS."""
        _baue_evidence(self.pfad)
        con = sqlite3.connect(str(self.pfad))
        con.isolation_level = None
        try:
            vorher = [r[0] for r in con.execute(_ORDER_SQL)]
            # Gegenprobe: der Zustand VOR der Migration ist nachweislich falsch.
            self.assertEqual(
                vorher, ["b00", "b01", "b04", "b05", "b02", "b06", "b03"],
                "Der Ausgangszustand muss die lexikographische (falsche) "
                "Ordnung zeigen — sonst prueft SI02 nichts.")
            _nur_m004(con)
            nachher = [r[0] for r in con.execute(_ORDER_SQL)]
            self.assertEqual(
                nachher, ["b00", "b01", "b02", "b03", "b04", "b05", "b06"],
                "Nach der Migration muss die numerische Ordnung gelten.")
        finally:
            con.close()

    # SI03 -------------------------------------------------------------------
    def test_si03_block_ohne_ordnung_wandert_ans_ende(self):
        """
        Zweite, im Vorgang nicht verzeichnete Folge: COALESCE(...,999999)
        vergleicht ein INTEGER-Literal mit TEXT-Werten, und SQLite ordnet
        INTEGER VOR TEXT. Der ordnungslose Block fuehrt den Bericht an,
        statt ihn zu beschliessen (db/evidence_db.py:1810 sagt das Gegenteil).
        """
        _baue_evidence(self.pfad, werte=[0, 1, 2, 10], ohne_ordnung=True)
        con = sqlite3.connect(str(self.pfad))
        con.isolation_level = None
        try:
            vorher = [r[0] for r in con.execute(_ORDER_SQL)]
            self.assertEqual(vorher[0], "OHNE",
                             "Vor der Migration muss der ordnungslose Block "
                             "den Bericht ANFUEHREN — das ist der Befund.")
            _nur_m004(con)
            nachher = [r[0] for r in con.execute(_ORDER_SQL)]
            self.assertEqual(nachher[-1], "OHNE",
                             "Nach der Migration gehoert er ans Ende, wie es "
                             "get_blocks_for_report zusagt.")
            self.assertEqual(nachher[:-1], ["b00", "b01", "b02", "b03"])
        finally:
            con.close()

    # SI04 -------------------------------------------------------------------
    def test_si04_verlustfrei_je_zeile(self):
        _baue_evidence(self.pfad, werte=[0, 1, 2, 9, 10, 11, 20])
        con = sqlite3.connect(str(self.pfad))
        con.isolation_level = None
        try:
            vorher = {b: str(s) for b, s in con.execute(
                "SELECT block_id, sort_index FROM report_block_order")}
            _nur_m004(con)
            nachher = {b: s for b, s in con.execute(
                "SELECT block_id, sort_index FROM report_block_order")}
            self.assertEqual(set(vorher), set(nachher))
            for b, roh in vorher.items():
                self.assertEqual(nachher[b], int(roh),
                                 "block_id=%s: %r -> %r" % (b, roh, nachher[b]))
                self.assertIsInstance(nachher[b], int)
        finally:
            con.close()

    # SI05 -------------------------------------------------------------------
    def test_si05_on_delete_cascade_ueberlebt(self):
        """
        Der Fall, den eine nachgeschriebene DDL still zerstoert haette:
        die Falldateien tragen ON DELETE CASCADE, db/evidence_db.py:300 nicht.
        """
        _baue_evidence(self.pfad)
        con = sqlite3.connect(str(self.pfad))
        con.isolation_level = None
        try:
            vorher = M4._fk_liste(con, "report_block_order")
            self.assertTrue(any(fk[4] == "CASCADE" for fk in vorher),
                            "Die Vorrichtung muss die Kaskade tragen, sonst "
                            "prueft SI05 nichts: %r" % (vorher,))
            _nur_m004(con)
            nachher = M4._fk_liste(con, "report_block_order")
            self.assertEqual(nachher, vorher)
            self.assertIn("ON DELETE CASCADE", con.execute(
                "SELECT sql FROM sqlite_master WHERE name='report_block_order'"
            ).fetchone()[0])
            # Und sie WIRKT auch: das ist der Unterschied zwischen einer
            # erhaltenen Klausel und einer erhaltenen Zeichenkette.
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("DELETE FROM report_blocks WHERE block_id = 'b00'")
            uebrig = con.execute("SELECT COUNT(*) FROM report_block_order "
                                 "WHERE block_id = 'b00'").fetchone()[0]
            self.assertEqual(uebrig, 0, "Die Kaskade muss wirken.")
        finally:
            con.close()

    # SI06 -------------------------------------------------------------------
    def test_si06_struktur_sonst_unveraendert(self):
        _baue_evidence(self.pfad)
        con = sqlite3.connect(str(self.pfad))
        con.isolation_level = None
        try:
            alt_info = M4._table_info(con, "report_block_order")
            alt_idx = M4._index_liste(con, "report_block_order")
            _nur_m004(con)
            neu_info = M4._table_info(con, "report_block_order")
            self.assertEqual(
                neu_info,
                tuple((n, "INTEGER" if n == "sort_index" else t, nn, df, pk)
                      for (n, t, nn, df, pk) in alt_info))
            self.assertEqual(M4._index_liste(con, "report_block_order"), alt_idx)
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(),
                             [])
            # Der Arbeitsname darf nicht zurueckbleiben.
            rest = con.execute(
                "SELECT 1 FROM sqlite_master WHERE name=?",
                (M4.ARBEITSNAME,)).fetchone()
            self.assertIsNone(rest, "Die Arbeitstabelle wurde nicht umbenannt.")
        finally:
            con.close()

    # SI07 -------------------------------------------------------------------
    def test_si07_idempotent(self):
        _baue_evidence(self.pfad)
        con = sqlite3.connect(str(self.pfad))
        con.isolation_level = None
        try:
            _nur_m004(con)
            stand = con.execute(
                "SELECT sql FROM sqlite_master WHERE name='report_block_order'"
            ).fetchone()[0]
            werte = dict(con.execute(
                "SELECT block_id, sort_index FROM report_block_order"))
            _nur_m004(con)   # zweiter Lauf
            self.assertEqual(con.execute(
                "SELECT sql FROM sqlite_master WHERE name='report_block_order'"
            ).fetchone()[0], stand)
            self.assertEqual(dict(con.execute(
                "SELECT block_id, sort_index FROM report_block_order")), werte)
        finally:
            con.close()

        # Eine Datei, die von Anfang an INTEGER traegt, wird nicht angefasst.
        p2 = Path(self._tmp) / "evidence_2.db"
        _baue_evidence(p2, sort_typ="INTEGER")
        vorher = _md5(p2)
        con2 = sqlite3.connect(str(p2))
        con2.isolation_level = None
        try:
            _nur_m004(con2)
        finally:
            con2.close()
        self.assertEqual(_md5(p2), vorher,
                         "Eine bereits richtige Datei darf sich nicht aendern.")

    # SI08 -------------------------------------------------------------------
    def test_si08_zweifelsfall_wird_uebernommen_und_belegt(self):
        """Festlegung mc 2026-08-02: umwandeln und vermerken. Der Vermerk
        gehoert in die Datei, nicht nur ins Maschinenprotokoll."""
        _baue_evidence(self.pfad, werte=[0, 1, 2])
        con = sqlite3.connect(str(self.pfad))
        con.isolation_level = None
        try:
            con.execute("UPDATE report_block_order SET sort_index = 'drei' "
                        "WHERE block_id = 'b02'")
            _, seq_vorher = EvidenceAuditLog(con).tip()
            _nur_m004(con)

            # Uebernommen: CAST('drei') = 0.
            self.assertEqual(con.execute(
                "SELECT sort_index FROM report_block_order WHERE block_id='b02'"
            ).fetchone()[0], 0)

            # Und BELEGT — in der Hash-Kette der Datei selbst.
            _, seq_nachher = EvidenceAuditLog(con).tip()
            self.assertEqual(seq_nachher, seq_vorher + 1,
                             "Der Zweifelsfall muss EINE Zeile in der "
                             "evidence_audit_log erzeugen.")
            row = con.execute(
                "SELECT event_type, content FROM evidence_audit_log "
                "ORDER BY seq DESC LIMIT 1").fetchone()
            self.assertEqual(row[0], "migration_applied")
            nutz = json.loads(row[1])
            self.assertEqual(nutz["migration"], "M004")
            self.assertEqual(len(nutz["zweifelsfaelle"]), 1)
            self.assertEqual(nutz["zweifelsfaelle"][0]["block_id"], "b02")
            self.assertEqual(nutz["zweifelsfaelle"][0]["roh"], "drei")
            self.assertEqual(nutz["zweifelsfaelle"][0]["uebernommen"], 0)
            # Die Kette muss sich weiterhin nachrechnen lassen.
            self.assertTrue(EvidenceAuditLog(con).verify_chain().ok)
        finally:
            con.close()

    # SI09 -------------------------------------------------------------------
    def test_si09_zweifelsfall_ohne_kette_bricht_ab(self):
        """Die Grenze der Festlegung: keine Umwandlung ohne dauerhaften Beleg."""
        _baue_evidence(self.pfad, werte=[0, 1, 2], mit_kette=False)
        con = sqlite3.connect(str(self.pfad))
        con.isolation_level = None
        try:
            con.execute("UPDATE report_block_order SET sort_index = 'x' "
                        "WHERE block_id = 'b01'")
            with self.assertRaises(RuntimeError) as ctx:
                _nur_m004(con)
            self.assertIn("evidence_audit_log", str(ctx.exception))
            # Nach dem Rollback ist die Datei unveraendert.
            self.assertEqual(self._typ(con), "TEXT")
            self.assertEqual(con.execute(
                "SELECT sort_index FROM report_block_order WHERE block_id='b01'"
            ).fetchone()[0], "x")
        finally:
            con.close()

    # SI10 -------------------------------------------------------------------
    def test_si10_fremde_datei_bricht_ab(self):
        _baue_evidence(self.pfad, ohne_annotations=True, mit_kette=False)
        con = sqlite3.connect(str(self.pfad))
        con.isolation_level = None
        try:
            with self.assertRaises(RuntimeError) as ctx:
                _nur_m004(con)
            self.assertIn("annotations", str(ctx.exception))
            self.assertEqual(self._typ(con), "TEXT", "Nichts darf geschehen sein.")
        finally:
            con.close()

    # SI11 -------------------------------------------------------------------
    def test_si11_ohne_tabelle_kein_abbruch_aber_meldung(self):
        _baue_evidence(self.pfad, ohne_block_order=True, mit_kette=False)
        con = sqlite3.connect(str(self.pfad))
        con.isolation_level = None
        try:
            with self.assertLogs(M4.logger, level="WARNING") as protokoll:
                _nur_m004(con)
            self.assertTrue(
                any("report_block_order" in z for z in protokoll.output),
                "Das Fehlen muss GENANNT werden: %r" % protokoll.output)
        finally:
            con.close()

    # SI12 -------------------------------------------------------------------
    def test_si12_unerwarteter_typ_bricht_ab(self):
        _baue_evidence(self.pfad, sort_typ="REAL", mit_kette=False)
        con = sqlite3.connect(str(self.pfad))
        con.isolation_level = None
        try:
            with self.assertRaises(RuntimeError) as ctx:
                _nur_m004(con)
            self.assertIn("REAL", str(ctx.exception))
        finally:
            con.close()

    # SI13 -------------------------------------------------------------------
    def test_si13_verify_haelt_die_zeilenzahl(self):
        con = sqlite3.connect(":memory:")
        with self.assertRaises(RuntimeError):
            M4.verify(con, 7, 6)
        with self.assertRaises(RuntimeError):
            M4.verify(con, None, 7)
        M4.verify(con, 7, 7)     # wirft nicht
        con.close()


class PruefeSortIndexTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.dir = Path(self._tmp) / "evidence"
        self.dir.mkdir(parents=True)

    def tearDown(self):
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.chmod(os.path.join(root, f), 0o600)
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    # PS01 / PS03 ------------------------------------------------------------
    def test_ps01_erkennt_typen_und_ordnungsaenderung(self):
        _baue_evidence(self.dir / "evidence_1.db", werte=[0, 1, 2, 10])
        _baue_evidence(self.dir / "evidence_2.db", sort_typ="INTEGER")
        _baue_evidence(self.dir / "evidence_3.db", werte=[0, 1, 2])
        e = PS.erhebe(self.dir)
        nach_name = {b["datei"]: b for b in e["befunde"]}
        self.assertEqual(nach_name["evidence_1.db"]["lage"], "zu_migrieren")
        self.assertEqual(nach_name["evidence_2.db"]["lage"], "ok")
        # PS03: bei 0,1,2,10 aendert sich die Ordnung, bei 0,1,2 nicht.
        self.assertTrue(nach_name["evidence_1.db"]["ordnung_aendert_sich"])
        self.assertFalse(nach_name["evidence_3.db"]["ordnung_aendert_sich"])
        self.assertEqual(PS._exit_code(e), 2)

    # PS02 -------------------------------------------------------------------
    def test_ps02_zweifelsfall_eigener_rueckgabewert(self):
        p = self.dir / "evidence_1.db"
        _baue_evidence(p, werte=[0, 1, 2])
        con = sqlite3.connect(str(p))
        con.execute("UPDATE report_block_order SET sort_index='drei' "
                    "WHERE block_id='b02'")
        con.commit()
        con.close()
        e = PS.erhebe(self.dir)
        self.assertEqual(len(e["befunde"][0]["zweifel"]), 1)
        self.assertEqual(e["befunde"][0]["zweifel"][0]["wuerde_werden"], 0)
        self.assertEqual(PS._exit_code(e), 3,
                         "'zu migrieren' und 'zu migrieren, aber hinsehen' "
                         "duerfen im Skript nicht gleich aussehen.")
        self.assertIn("ZWEIFELSFALL", PS._ausgabe_text(e))

    # PS04 -------------------------------------------------------------------
    def test_ps04_unlesbare_datei_wird_genannt(self):
        _baue_evidence(self.dir / "evidence_1.db")
        (self.dir / "evidence_9.db").write_bytes(b"kein SQLite")
        e = PS.erhebe(self.dir)
        lagen = {b["datei"]: b["lage"] for b in e["befunde"]}
        self.assertEqual(lagen["evidence_9.db"], "unlesbar")
        self.assertEqual(PS._exit_code(e), 4,
                         "Ein unvollstaendiger Befund schlaegt jeden "
                         "vollstaendigen.")
        self.assertIn("evidence_9.db", PS._ausgabe_text(e))

    # PS05 -------------------------------------------------------------------
    def test_ps05_fremde_dateiformen_werden_genannt(self):
        _baue_evidence(self.dir / "evidence_1.db", sort_typ="INTEGER")
        (self.dir / "evidence_1486482_3.db").write_bytes(b"")   # Transportdatei
        (self.dir / "irgendwas.db").write_bytes(b"")
        e = PS.erhebe(self.dir)
        self.assertEqual(len(e["befunde"]), 1)
        self.assertEqual(sorted(e["uebergangen"]),
                         ["evidence_1486482_3.db", "irgendwas.db"])
        self.assertIn("uebergangen", PS._ausgabe_text(e))

    # PS06 -------------------------------------------------------------------
    def test_ps06_schreibt_nichts(self):
        p = self.dir / "evidence_1.db"
        _baue_evidence(p)
        vorher = _md5(p)
        PS.erhebe(self.dir)
        self.assertEqual(_md5(p), vorher)

    # PS07 -------------------------------------------------------------------
    def test_ps07_kanonische_form_ist_dieselbe(self):
        """Zwei Ausdruecke fuer dieselbe Sache laufen beim naechsten Umbau
        auseinander (Lehre aus Build 658) — hier werden sie gehalten."""
        self.assertEqual(M4._KANONISCH.pattern, PS._KANONISCH.pattern)
        for gut in ("0", "7", "-2", "1234"):
            self.assertTrue(M4._KANONISCH.match(gut), gut)
        for schlecht in ("007", " 3", "3.9", "1e3", "abc", "", "-0", "+7"):
            self.assertIsNone(M4._KANONISCH.match(schlecht), schlecht)


if __name__ == "__main__":
    unittest.main()
