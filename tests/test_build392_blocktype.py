# =============================================================================
# tests/test_build392_blocktype.py
# IT-Forensisches Ermittlungswerkzeug — Regressionstests Build 392
# =============================================================================
# Prueft den DATENVERLUST-FIX:
#
#   1. classify()  -- Erkennung beschaedigter Bloecke (Reparaturskript)
#   2. repair_db() -- Wiederherstellung, Zweifelsfaelle bleiben unangetastet
#   3. Der Kern: ein save_block OHNE block_type darf den Typ eines
#      BESTEHENDEN Blocks nicht mehr ueberschreiben.
#
# Beleg: Bugbefund Projektgespraech 2026-07-12, Bauplan Build 392
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

from __future__ import annotations

import json
import os
import sqlite3
import tempfile

import pytest

from management.repair_block_types import classify, repair_db, scan_db


# =============================================================================
# 1) Erkennung
# =============================================================================

class TestClassify:

    def test_echte_tabelle_wird_als_defekt_erkannt(self):
        """Genau die Signatur, die der Fehler hinterlaesst."""
        data = json.dumps({
            "withHeadings": False,
            "content": [["Registrierungsdatum", "20.09.2022"], ["Beitraege", "0"]],
        })
        befund, grund = classify("paragraph", data)
        assert befund == "table"
        assert "2 Zeilen" in grund

    def test_liste_wird_als_defekt_erkannt(self):
        data = json.dumps({"style": "unordered", "items": ["a", "b"]})
        befund, _ = classify("paragraph", data)
        assert befund == "list"

    def test_echter_paragraph_bleibt_unangetastet(self):
        befund, _ = classify("paragraph", json.dumps({"text": "Ein Absatz."}))
        assert befund == "ok"

    def test_leerer_paragraph_bleibt_unangetastet(self):
        befund, _ = classify("paragraph", json.dumps({"text": ""}))
        assert befund == "ok"

    def test_intakter_table_block_wird_nicht_angefasst(self):
        """Ein Block, der noch korrekt 'table' heisst, ist nicht betroffen."""
        data = json.dumps({"withHeadings": False, "content": [["a", "b"]]})
        befund, _ = classify("table", data)
        assert befund == "ok"

    def test_header_block_wird_nicht_angefasst(self):
        befund, _ = classify("header", json.dumps({"text": "Titel", "level": 2}))
        assert befund == "ok"

    def test_widerspruch_text_UND_content_ist_unklar(self):
        """
        GRUNDREGEL 1: Lieber melden als raten. Ein Block mit text UND content
        ist kein Fall, den der Fehler erzeugt — den fassen wir nicht an.
        """
        data = json.dumps({"text": "Absatz", "content": [["a"]]})
        befund, grund = classify("paragraph", data)
        assert befund == "unklar"
        assert "text" in grund

    def test_kaputtes_json_ist_unklar(self):
        befund, grund = classify("paragraph", "{nicht json")
        assert befund == "unklar"
        assert "JSON" in grund

    def test_content_ohne_zeilen_arrays_ist_kein_table(self):
        """content als flache Liste ist KEINE Editor.js-Tabelle."""
        data = json.dumps({"content": ["a", "b"]})
        befund, _ = classify("paragraph", data)
        assert befund == "ok"


# =============================================================================
# 2) Reparatur
# =============================================================================

@pytest.fixture
def evidence_db():
    """Minimale evidence-DB mit gemischten Bloecken."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE report_blocks (
            block_id TEXT PRIMARY KEY, report_id INTEGER NOT NULL,
            author TEXT NOT NULL, created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL, block_type TEXT NOT NULL,
            block_data TEXT NOT NULL DEFAULT '{}',
            placeholder_values_json TEXT, module_id INTEGER);
    """)
    rows = [
        # Beschaedigte Tabelle (der eigentliche Schadensfall)
        ("b-tab", 1, "h001", 1, 1, "paragraph",
         json.dumps({"withHeadings": False,
                     "content": [["Beitraege", "{{a:user.posts_total|0}}"]]})),
        # Unbeteiligter Absatz
        ("b-par", 1, "h001", 1, 1, "paragraph", json.dumps({"text": "Text"})),
        # Unbeteiligte Ueberschrift
        ("b-hdr", 1, "h001", 1, 1, "header",
         json.dumps({"text": "Titel", "level": 2})),
        # Zweifelsfall
        ("b-unk", 1, "h001", 1, 1, "paragraph",
         json.dumps({"text": "x", "content": [["a"]]})),
    ]
    con.executemany(
        "INSERT INTO report_blocks (block_id, report_id, author, created_at, "
        "updated_at, block_type, block_data) VALUES (?,?,?,?,?,?,?)", rows
    )
    con.commit()
    con.close()
    yield path
    os.unlink(path)


class TestRepair:

    def test_scan_findet_nur_die_betroffenen(self, evidence_db):
        funde = {f["block_id"]: f for f in scan_db(evidence_db)}
        assert set(funde) == {"b-tab", "b-unk"}
        assert funde["b-tab"]["soll"] == "table"
        assert funde["b-unk"]["befund"] == "unklar"

    def test_reparatur_stellt_den_typ_wieder_her(self, evidence_db):
        funde = scan_db(evidence_db)
        n = repair_db(evidence_db, funde)
        assert n == 1

        con = sqlite3.connect(evidence_db)
        con.row_factory = sqlite3.Row
        typen = {
            r["block_id"]: r["block_type"]
            for r in con.execute("SELECT block_id, block_type FROM report_blocks")
        }
        con.close()

        assert typen["b-tab"] == "table"      # wiederhergestellt
        assert typen["b-par"] == "paragraph"  # unangetastet
        assert typen["b-hdr"] == "header"     # unangetastet
        assert typen["b-unk"] == "paragraph"  # Zweifelsfall: NICHT angefasst

    def test_inhalt_bleibt_unveraendert(self, evidence_db):
        """
        Die Reparatur ist verlustfrei: nur block_type wird korrigiert,
        block_data bleibt Zeichen fuer Zeichen gleich.
        """
        con = sqlite3.connect(evidence_db)
        vorher = con.execute(
            "SELECT block_data FROM report_blocks WHERE block_id='b-tab'"
        ).fetchone()[0]
        con.close()

        repair_db(evidence_db, scan_db(evidence_db))

        con = sqlite3.connect(evidence_db)
        nachher = con.execute(
            "SELECT block_data FROM report_blocks WHERE block_id='b-tab'"
        ).fetchone()[0]
        con.close()
        assert nachher == vorher

    def test_reparatur_ist_idempotent(self, evidence_db):
        repair_db(evidence_db, scan_db(evidence_db))
        # Zweiter Durchlauf: nichts mehr zu tun (der Block heisst jetzt 'table').
        rest = [f for f in scan_db(evidence_db) if f["befund"] == "table"]
        assert rest == []


# =============================================================================
# 3) Der Kern: save_block darf den Typ nicht mehr ueberschreiben
# =============================================================================

class TestSaveBlockBewahrtTypEchtDurchDenEndpunkt:
    """
    Stellt den Schadenshergang exakt nach — durch den ECHTEN Endpunkt
    (ReportEndpoint.handle_post), nicht durch nachgebaute Logik:

      1. Eine Vorlage legt einen TABLE-Block an.
      2. _resolveAutoPlaceholders (report_editor.js:753) bzw.
         _onPlaceholderFieldSave (report_editor.js:2058) schreiben den Block
         zurueck — OHNE block_type, weil sie nur Werte nachtragen wollen.
      3. Bis Build 391 setzte _action_save_block den Typ dabei auf
         'paragraph'. Die Tabelle war beim naechsten Laden verschwunden.

    Geprueft wird, was TATSAECHLICH IN DER DATENBANK STEHT.
    """

    def setup_method(self):
        import sys
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        from unittest.mock import MagicMock
        from db.evidence_db import EvidenceDb
        from forensic_api.report import ReportEndpoint

        self.con = sqlite3.connect(":memory:", check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.edb = EvidenceDb(self.con)

        bundle = MagicMock()
        bundle.evidence = self.edb
        context = MagicMock()
        context.investigator_username = "h001"
        context.username = "h001"
        context.subject_id = 42
        config = MagicMock()
        config.get = MagicMock(return_value={})
        self.ep = ReportEndpoint(bundle, context, config)

        self.report_id = self.edb.create_report("final", "Spurenvermerk", "h001")
        self.lock_id = self.edb.acquire_lock(
            report_id=self.report_id, locked_by="h001", sse_client="sse-392"
        )
        assert self.lock_id

        # Der Tabellenblock, wie ihn die Spurenvermerk-Vorlage anlegt.
        self.tabelle = {
            "withHeadings": False,
            "content": [["Anzahl Beitraege", "{{a:user.posts_total|0}}"]],
        }
        self.edb.save_block(
            block_id="t-1", report_id=self.report_id, author="h001",
            block_type="table",
            block_data=json.dumps(self.tabelle, ensure_ascii=False),
            sort_index=0,
        )
        assert self.edb.get_block("t-1").block_type == "table"

    def teardown_method(self):
        self.con.close()

    def _post(self, payload: dict):
        from unittest.mock import MagicMock
        antworten = []
        handler = MagicMock()
        handler.headers = {"X-Forensic-Lock-Id": self.lock_id}
        handler.send_response_body = lambda status, body, **kw: antworten.append(
            (status, json.loads(body.decode("utf-8")) if body else {})
        )
        self.ep.handle_post(handler, json.dumps(payload).encode("utf-8"))
        return antworten

    def test_KERNTEST_auto_platzhalter_nachtrag_zerstoert_die_tabelle_nicht(self):
        """
        DER Regressionstest zu diesem Bug. Payload wortgleich zu
        report_editor.js:753 (_resolveAutoPlaceholders) — OHNE block_type.
        """
        antworten = self._post({
            "action": "save_block",
            "block_id": "t-1",
            "report_id": self.report_id,
            "block_data": self.tabelle,
            "owner": "h001",
            "placeholder_values_json": json.dumps({"auto:user.posts_total": "17"}),
        })
        assert antworten[0][0] == 201, antworten

        blk = self.edb.get_block("t-1")
        assert blk.block_type == "table", (
            "REGRESSION: Der Blocktyp wurde auf '%s' zurueckgesetzt. Die "
            "Tabelle verschwindet damit aus dem Bericht." % blk.block_type
        )
        # Der Inhalt muss ebenfalls unversehrt sein.
        assert json.loads(blk.block_data)["content"] == self.tabelle["content"]
        assert "17" in (blk.placeholder_values_json or "")

    def test_KERNTEST_formularwert_nachtrag_zerstoert_die_tabelle_nicht(self):
        """
        Payload wortgleich zu report_editor.js:2058 (_onPlaceholderFieldSave).
        Das trifft JEDEN Ermittler, der ein Feld in der Tabelle ausfuellt.
        """
        self._post({
            "action": "save_block",
            "block_id": "t-1",
            "report_id": self.report_id,
            "block_data": self.tabelle,
            "owner": "h001",
            "placeholder_values_json": json.dumps({"passwort": "unbekannt"}),
        })
        assert self.edb.get_block("t-1").block_type == "table"

    def test_typwechsel_per_toolbar_bleibt_moeglich(self):
        """
        Der Fix darf den legitimen Typwechsel NICHT verhindern: sendet der
        Client ausdruecklich einen Typ, gewinnt dieser.
        """
        self.edb.save_block(
            block_id="p-1", report_id=self.report_id, author="h001",
            block_type="paragraph", block_data=json.dumps({"text": "Titel"}),
        )
        self._post({
            "action": "save_block",
            "block_id": "p-1",
            "report_id": self.report_id,
            "block_type": "header",
            "block_data": {"text": "Titel", "level": 2},
            "owner": "h001",
        })
        assert self.edb.get_block("p-1").block_type == "header"

    def test_neuer_block_ohne_typ_wird_paragraph(self):
        """Verhalten fuer NEUE Bloecke bleibt unveraendert (aber protokolliert)."""
        self._post({
            "action": "save_block",
            "block_id": "neu-1",
            "report_id": self.report_id,
            "block_data": {"text": "frisch"},
            "owner": "h001",
        })
        assert self.edb.get_block("neu-1").block_type == "paragraph"

    def test_header_block_behaelt_seinen_typ(self):
        """
        Auch die Ueberschrift mit der Spurennummer ist betroffen: sie ist ein
        header-Block, und der Wizard schreibt dort den Formularwert zurueck.
        """
        self.edb.save_block(
            block_id="h-1", report_id=self.report_id, author="h001",
            block_type="header",
            block_data=json.dumps({"text": "Spurenvermerk {{m:spurennummer}}",
                                   "level": 2}),
        )
        self._post({
            "action": "save_block",
            "block_id": "h-1",
            "report_id": self.report_id,
            "block_data": {"text": "Spurenvermerk {{m:spurennummer}}", "level": 2},
            "owner": "h001",
            "placeholder_values_json": json.dumps({"spurennummer": "AIW12345"}),
        })
        blk = self.edb.get_block("h-1")
        assert blk.block_type == "header"
        assert json.loads(blk.block_data)["level"] == 2
