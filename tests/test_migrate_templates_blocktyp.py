# =============================================================================
# tests/test_migrate_templates_blocktyp.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Verwaltung / templates.db
# =============================================================================
# Gegenstand: management/migrate_templates_blocktyp.py (Build 655,
# Ticket 5d81a0c7) — die additive Migration von report_modules um block_type
# und block_data.
#
# DIES IST DER EINZIGE SCHRITT DER REIHE MIT DATENRISIKO (Claude-Kommentar im
# Ticket). Die Faelle pruefen deshalb nicht nur, DASS die Spalten entstehen,
# sondern vor allem, dass DABEI NICHTS ANDERES PASSIERT.
#
# BT01 — leere DB: beide Spalten entstehen, integrity_check ist 'ok'.
# BT02 — Bestand mit Zeilen: KEIN body, KEIN updated_at veraendert
#        (Fingerabdruck vorher/nachher).
# BT03 — Idempotenz: zweiter Lauf aendert nichts und schreibt keine Audit-Zeile.
# BT04 — Teilzustand: fehlt nur EINE Spalte, wird nur diese ergaenzt.
# BT05 — Audit-Zeile mit action='migrate' und dem Wertevorrat im Nachher-Wert.
# BT06 — der CHECK greift wirklich (und der Default erfuellt ihn).
# BT07 — fehlende Tabelle -> ausdruecklicher Abbruch, kein stiller No-op.
# BT08 — templates_db_status meldet die Migration vorher offen, nachher erledigt.
# BT09 — DER DATENVERLUSTPFAD: ein Upsert OHNE block_data laesst vorhandene
#        Blockdaten stehen. Ohne diesen Fall loeschte jedes Speichern aus der
#        Maske aus Build 654 die Blockdaten eines Bausteins, der sie hat.
#
# Version: v0.8.655 · Build: 655 · 2026-08-02
# =============================================================================

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest

from management.migrate_templates_blocktyp import (
    BLOCK_TYPEN,
    apply_migration,
    fehlende_spalten,
)

# Der Zustand VOR Build 655 — woertlich der aus templates.db.schema.sql, nur
# ohne die beiden neuen Spalten. Nicht abgekuerzt: die CHECK-Constraints
# muessen mitkommen, sonst prueft der Fall gegen eine Tabelle, die es so nie
# gab (die Lehre aus Build 584).
_DDL_VOR_655 = """
CREATE TABLE report_modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT,
    role TEXT NOT NULL CHECK (role IN ('intro','conclusion','body','legal',
                                       'appendix','closing')),
    topic TEXT NOT NULL, body TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0, is_active INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL, created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL, module_key TEXT
);
CREATE UNIQUE INDEX ux_report_modules_key ON report_modules (module_key)
    WHERE module_key IS NOT NULL;
CREATE TABLE templates_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('module','query',
                                                     'template','placeholder')),
    changed_by TEXT NOT NULL, changed_at INTEGER NOT NULL,
    old_value TEXT, new_value TEXT
);
"""


def _con(mit_zeilen: bool = False, ohne_audit: bool = False) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    ddl = _DDL_VOR_655
    if ohne_audit:
        ddl = ddl.split("CREATE TABLE templates_audit_log")[0]
    con.executescript(ddl)
    if mit_zeilen:
        for i, (key, rolle, text) in enumerate((
                ("intro.start", "intro", "Guten Tag {{a:username}}."),
                ("body.aktiv", "body", "Aktivität — mit Umlaut und 中文."),
                (None, "legal", "Altzeile ohne Kennung."))):
            con.execute(
                "INSERT INTO report_modules (title, description, role, topic, "
                " body, sort_order, is_active, created_by, created_at, "
                " updated_at, module_key) "
                "VALUES (?, '', ?, 'Thema', ?, 0, 1, 'red01', 1000, 2000, ?)",
                ("Titel %d" % i, rolle, text, key))
        con.commit()
    return con


def _fingerabdruck(con: sqlite3.Connection) -> list:
    """
    Der Inhalt, der die Migration UEBERLEBEN muss - Zeile fuer Zeile.
    Bewusst OHNE die neuen Spalten: geprueft wird, dass der ALTE Bestand
    unberuehrt bleibt, nicht was hinzukommt.
    """
    return [tuple(r) for r in con.execute(
        "SELECT id, title, description, role, topic, body, sort_order, "
        "       is_active, created_by, created_at, updated_at, module_key "
        "FROM report_modules ORDER BY id")]


class BlocktypMigrationTests(unittest.TestCase):

    # BT01 -----------------------------------------------------------------
    def test_bt01_spalten_entstehen(self):
        con = _con()
        self.assertEqual(fehlende_spalten(con), ["block_type", "block_data"])

        res = apply_migration(con, changed_by="tester")
        self.assertFalse(res["already_migrated"])
        self.assertEqual(res["added"], ["block_type", "block_data"])
        self.assertEqual(fehlende_spalten(con), [])
        self.assertEqual(
            con.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    # BT02 -----------------------------------------------------------------
    def test_bt02_kein_bestand_wird_veraendert(self):
        """
        DER WICHTIGSTE FALL. Verlustfreiheit heisst hier nicht 'nichts geht
        kaputt', sondern 'es wird gar nichts angefasst'.
        """
        con = _con(mit_zeilen=True)
        vorher = _fingerabdruck(con)
        self.assertEqual(len(vorher), 3)

        apply_migration(con, changed_by="tester")

        self.assertEqual(_fingerabdruck(con), vorher)
        # Und im Einzelnen, damit die Meldung im Fehlerfall etwas sagt:
        for zeile in con.execute(
                "SELECT id, body, updated_at, block_type, block_data "
                "FROM report_modules ORDER BY id"):
            self.assertEqual(zeile["updated_at"], 2000, zeile["id"])
            # block_data IS NULL bedeutet ausdruecklich: 'Inhalt steht in
            # body'. Ein Backfill haette hier etwas eingetragen - und genau
            # das soll NICHT geschehen.
            self.assertIsNone(zeile["block_data"], zeile["id"])
            self.assertEqual(zeile["block_type"], "paragraph", zeile["id"])
        # Auch das mehrsprachige Feld ist unangetastet (UTF-8, Grundregel:
        # das Forum ist multilingual).
        self.assertIn("中文", con.execute(
            "SELECT body FROM report_modules WHERE module_key='body.aktiv'"
        ).fetchone()[0])

    # BT03 -----------------------------------------------------------------
    def test_bt03_idempotent(self):
        con = _con(mit_zeilen=True)
        apply_migration(con, changed_by="tester")
        nach_erstem = _fingerabdruck(con)
        audit_erst = con.execute(
            "SELECT COUNT(*) FROM templates_audit_log").fetchone()[0]
        self.assertEqual(audit_erst, 1)

        res = apply_migration(con, changed_by="tester")

        self.assertTrue(res["already_migrated"])
        self.assertEqual(res["added"], [])
        self.assertFalse(res["audited"])
        self.assertEqual(_fingerabdruck(con), nach_erstem)
        # KEINE zweite Audit-Zeile: ein No-op ist kein Vorgang.
        self.assertEqual(con.execute(
            "SELECT COUNT(*) FROM templates_audit_log").fetchone()[0], 1)

    # BT04 -----------------------------------------------------------------
    def test_bt04_teilzustand_wird_aufgeloest(self):
        """
        Der Zustand nach einem Abbruch mitten im Lauf. Er ist nicht
        vorgesehen, aber moeglich - und dann muss der zweite Lauf ihn
        AUFLOESEN und nicht daran scheitern.
        """
        con = _con(mit_zeilen=True)
        con.execute("ALTER TABLE report_modules ADD COLUMN block_data TEXT")
        con.commit()
        self.assertEqual(fehlende_spalten(con), ["block_type"])

        res = apply_migration(con, changed_by="tester")

        self.assertEqual(res["added"], ["block_type"])
        self.assertEqual(fehlende_spalten(con), [])

    # BT05 -----------------------------------------------------------------
    def test_bt05_audit_nennt_den_wertevorrat(self):
        con = _con(mit_zeilen=True)
        res = apply_migration(con, changed_by="pruefer")
        self.assertTrue(res["audited"])

        row = con.execute(
            "SELECT action, target_id, target_type, changed_by, new_value "
            "FROM templates_audit_log").fetchone()
        self.assertEqual(row["action"], "migrate")
        self.assertEqual(row["target_id"], "report_modules")
        self.assertEqual(row["target_type"], "module")
        self.assertEqual(row["changed_by"], "pruefer")
        nach = json.loads(row["new_value"])
        self.assertEqual(nach["added_columns"], ["block_type", "block_data"])
        self.assertEqual(nach["block_type_default"], "paragraph")
        # Der Wertevorrat steht IN DER AKTE. Wer spaeter fragt, welche
        # Blockarten damals festgeschrieben wurden, muss nicht den Quelltext
        # der Migration suchen.
        self.assertEqual(nach["block_type_check"], list(BLOCK_TYPEN))

    # BT05b ----------------------------------------------------------------
    def test_bt05b_ohne_audittabelle_laeuft_es_trotzdem(self):
        con = _con(ohne_audit=True)
        res = apply_migration(con, changed_by="tester")
        self.assertFalse(res["audited"])
        self.assertEqual(fehlende_spalten(con), [])

    # BT06 -----------------------------------------------------------------
    def test_bt06_der_check_greift(self):
        """
        Der CHECK ist eine Entscheidung mit Preis (mc, 2026-08-02). Wenn er
        schon da ist, muss er auch wirken - sonst waere der Preis umsonst
        bezahlt.
        """
        con = _con()
        apply_migration(con, changed_by="tester")

        def _insert(typ):
            con.execute(
                "INSERT INTO report_modules (title, description, role, topic, "
                " body, sort_order, is_active, created_by, created_at, "
                " updated_at, module_key, block_type) "
                "VALUES ('T', '', 'intro', 'Thema', 'x', 0, 1, 'red01', 1, 1, "
                "        ?, ?)", ("key." + typ, typ))

        for typ in BLOCK_TYPEN:
            _insert(typ)                      # alle sechs sind zulaessig
        with self.assertRaises(sqlite3.IntegrityError):
            _insert("gibtsnicht")

        # Und der Default erfuellt den CHECK - sonst waere die Migration auf
        # einem Bestand mit Zeilen gar nicht durchgelaufen.
        con.execute(
            "INSERT INTO report_modules (title, description, role, topic, "
            " body, sort_order, is_active, created_by, created_at, updated_at, "
            " module_key) VALUES ('T', '', 'intro', 'Thema', 'x', 0, 1, "
            "                     'red01', 1, 1, 'key.default')")
        self.assertEqual(con.execute(
            "SELECT block_type FROM report_modules WHERE module_key='key.default'"
        ).fetchone()[0], "paragraph")

    # BT07 -----------------------------------------------------------------
    def test_bt07_fehlende_tabelle_bricht_ab(self):
        con = sqlite3.connect(":memory:")
        with self.assertRaises(RuntimeError) as ctx:
            apply_migration(con, changed_by="tester")
        # Die Meldung muss sagen, was zu tun ist - sonst kostet sie so viel
        # Zeit wie gar keine.
        self.assertIn("setup_templates.py", str(ctx.exception))

    # BT08 -----------------------------------------------------------------
    def test_bt08_standsbericht_kennt_die_migration(self):
        from management.templates_db_status import bericht

        pfad = os.path.join(tempfile.mkdtemp(), "templates.db")
        con = sqlite3.connect(pfad)
        con.executescript(_DDL_VOR_655)
        con.commit()

        anzahl_vor, zeilen_vor = bericht(con, pfad)
        text_vor = "\n".join(zeilen_vor)
        self.assertIn("migrate_templates_blocktyp.py", text_vor)
        self.assertIn("[ ] Build 655", text_vor)

        apply_migration(con, changed_by="tester")

        anzahl_nach, zeilen_nach = bericht(con, pfad)
        self.assertEqual(anzahl_nach, anzahl_vor - 1)
        self.assertIn("[x] Build 655", "\n".join(zeilen_nach))
        con.close()
        os.remove(pfad)
        os.rmdir(os.path.dirname(pfad))


class UpsertBestandsschutzTests(unittest.TestCase):
    """
    BT09 — DER DATENVERLUSTPFAD.

    Die Maske aus Build 654 sendet block_type/block_data noch gar nicht; die
    Eingabe dafuer kommt erst mit Build 656. Deutete das Repo ein fehlendes
    Feld als 'leer', dann loeschte JEDES Speichern aus der alten Maske die
    Blockdaten eines Bausteins, der sie schon hat - ein Redakteur, der nur
    den Titel korrigiert, verlöre den Tabelleninhalt, und zwar still.

    Der Fall misst die Unterscheidung zwischen 'Feld nicht dabei' (Bestand
    behalten) und 'Feld dabei, aber leer' (ausdrueckliches Loeschen).
    """

    def setUp(self):
        self.con = _con()
        apply_migration(self.con, changed_by="tester")
        from management.templates_admin.module_repo import ModuleAuthorRepo
        self.repo = ModuleAuthorRepo(self.con)
        self.repo.upsert({
            "module_key": "body.tabelle", "title": "Tabellen-Baustein",
            "description": "", "role": "body", "topic": "Thema",
            "body": "Ersatztext", "sort_order": 0,
            "block_type": "table",
            "block_data": {"content": [["a", "b"], ["c", "d"]]},
        }, changed_by="red01", ts=1000)

    def _zeile(self):
        return self.repo.get_by_key("body.tabelle")

    def test_bt09a_anlegen_speichert_typ_und_daten(self):
        z = self._zeile()
        self.assertEqual(z["block_type"], "table")
        # Die Speicherform ist TEXT (JSON) - die Umformung in ein Objekt
        # gehoert an die Ausgabestelle, nicht in die Ablage.
        self.assertEqual(json.loads(z["block_data"]),
                         {"content": [["a", "b"], ["c", "d"]]})

    def test_bt09b_upsert_ohne_die_felder_laesst_sie_stehen(self):
        """DER FALL, DER EINEN STILLEN DATENVERLUST VERHINDERT."""
        self.repo.upsert({
            "module_key": "body.tabelle", "title": "Titel korrigiert",
            "description": "", "role": "body", "topic": "Thema",
            "body": "Ersatztext", "sort_order": 0,
            # block_type und block_data FEHLEN - genau wie es die Maske aus
            # Build 654 sendet.
        }, changed_by="red01", ts=2000)

        z = self._zeile()
        self.assertEqual(z["title"], "Titel korrigiert")
        self.assertEqual(z["block_type"], "table")
        self.assertEqual(json.loads(z["block_data"]),
                         {"content": [["a", "b"], ["c", "d"]]})

    def test_bt09c_leeres_feld_loescht_ausdruecklich(self):
        """
        Die Gegenprobe zu BT09b: wer die Felder MITSENDET und leer laesst,
        will loeschen. Ohne diesen Fall waere BT09b auch dann gruen, wenn das
        Repo die Felder schlicht nie schriebe.
        """
        self.repo.upsert({
            "module_key": "body.tabelle", "title": "T", "description": "",
            "role": "body", "topic": "Thema", "body": "Ersatztext",
            "sort_order": 0,
            "block_type": "paragraph", "block_data": None,
        }, changed_by="red01", ts=3000)

        z = self._zeile()
        self.assertEqual(z["block_type"], "paragraph")
        self.assertIsNone(z["block_data"])

    def test_bt09d_validator_faengt_den_falschen_typ_vor_der_datenbank(self):
        from management.templates_admin.module_validator import validate_static

        gut = {"module_key": "a.b", "title": "T", "role": "intro",
               "topic": "X", "body": "Y"}
        self.assertEqual(validate_static(gut), [])
        # Fehlende Felder sind KEIN Fehler - die alte Maske sendet sie nicht.
        self.assertEqual(validate_static({**gut, "block_type": "table"}), [])

        fehler = validate_static({**gut, "block_type": "gibtsnicht"})
        self.assertEqual(len(fehler), 1)
        # Die Meldung nennt den Wertevorrat; 'CHECK constraint failed' taete
        # das nicht.
        self.assertIn("paragraph", fehler[0])

        # block_data muss ein JSON-OBJEKT sein: Editor.js reicht je Block ein
        # Objekt an sein Werkzeug durch.
        self.assertEqual(validate_static({**gut, "block_data": '{"text":"x"}'}),
                         [])
        self.assertTrue(validate_static({**gut, "block_data": "kein json"}))
        self.assertIn("JSON-OBJEKT",
                      validate_static({**gut, "block_data": "[1,2]"})[0])


if __name__ == "__main__":
    unittest.main()
