# =============================================================================
# tests/test_build388_vorlagen.py
# IT-Forensisches Ermittlungswerkzeug — Regressionstests Build 388
# =============================================================================
# Prueft die drei Neuerungen von Build 388 gegen die ECHTEN Funktionen
# (kein nachgebauter Ersatzcode — 'gruen aber tot' waere hier besonders
# gefaehrlich, weil an der Spurennummer die Verwertbarkeit des Vermerks haengt):
#
#   1. core/validation_rules.py   -- zentraler Regel-Katalog aus config.yaml
#   2. core/placeholder_syntax.py -- Platzhalter-Extraktion inkl. Tabellenzellen
#   3. db/evidence_db.py::save_blocks_bulk -- transaktionales Einfuegen
#   4. management/migrate_templates_full_templates.py -- idempotenter Seed
#
# Beleg: Bauplan Build 388, Projektgespraech 2026-07-12
# =============================================================================

from __future__ import annotations

import json
import sqlite3

import pytest

from core.placeholder_syntax import PlaceholderSyntax
from core.validation_rules import ValidationRules
from management.migrate_templates_full_templates import (
    TEMPLATE_KEY,
    _NEW_QUERIES,
    apply_migration,
)


# =============================================================================
# Hilfen
# =============================================================================

class _FakeConfig:
    """Minimaler ConfigLoader-Ersatz: nur get() mit gepunktetem Schluessel."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def get(self, key: str, default=None):
        node = self._data
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def _rules_from_production_config() -> ValidationRules:
    """
    Laedt die Regeln aus der ECHTEN config.yaml des Repositorys.
    Damit schlaegt ein Tippfehler im ausgelieferten Muster im Test fehl —
    nicht erst beim Ermittler.
    """
    import os
    import yaml

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "config.yaml"), "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return ValidationRules(_FakeConfig(cfg))


# =============================================================================
# 1) Validierungsregeln
# =============================================================================

class TestValidationRules:

    def test_spurennummer_regel_ist_ausgeliefert(self):
        """Die Regel muss in der PRODUKTIVEN config.yaml stehen, nicht nur im Test."""
        rules = _rules_from_production_config()
        assert rules.has("spurennummer"), (
            "validation.rules.spurennummer fehlt in config.yaml — der "
            "Spurenvermerk-Baustein verweist darauf und wuerde beim "
            "Einreichen abgelehnt."
        )

    @pytest.mark.parametrize("eingabe,erwartet", [
        ("AIW12345", "AIW12345"),
        ("aiw12345", "AIW12345"),      # Uppercase-Normalisierung
        ("  r3x7 ", "R3X7"),           # strip + upper
        ("fbl001", "FBL001"),
        ("amz42", "AMZ42"),
        ("bru9", "BRU9"),
    ])
    def test_gueltige_spurennummern_werden_normalisiert(self, eingabe, erwartet):
        rules = _rules_from_production_config()
        res = rules.validate("spurennummer", eingabe)
        assert res.ok, res.message
        # Der NORMALISIERTE Wert ist der, der gespeichert wird.
        assert res.value == erwartet

    @pytest.mark.parametrize("eingabe", [
        "XYZ12345",      # unbekanntes Behoerdenkuerzel
        "AIW",           # keine Ziffern
        "12345",         # kein Kuerzel
        "AIW 12345",     # Leerzeichen im Inneren
        "AIW12345X",     # Nachlauf
        "",              # leer
    ])
    def test_ungueltige_spurennummern_werden_abgelehnt(self, eingabe):
        rules = _rules_from_production_config()
        res = rules.validate("spurennummer", eingabe)
        assert not res.ok
        assert res.message  # Es MUSS eine Begruendung geben (Grundregel 1)

    def test_unbekannte_regel_wird_nicht_still_durchgewunken(self):
        """
        GRUNDREGEL 1: Verweist ein Baustein auf eine Regel, die es nicht gibt,
        darf der Wert NICHT als gueltig gelten.
        """
        rules = _rules_from_production_config()
        res = rules.validate("gibt_es_nicht", "beliebig")
        assert not res.ok
        assert "gibt_es_nicht" in res.message

    def test_kaputte_regex_wird_verworfen_statt_zu_taeuschen(self):
        rules = ValidationRules(_FakeConfig({
            "validation": {"rules": {"kaputt": {"pattern": "^([A-Z"}}}
        }))
        assert not rules.has("kaputt")
        assert not rules.validate("kaputt", "irgendwas").ok

    def test_katalog_fuer_client_enthaelt_kein_regex_objekt(self):
        rules = _rules_from_production_config()
        pub = rules.as_public_dict()
        assert set(pub["spurennummer"]) == {"pattern", "transform", "hint"}
        assert pub["spurennummer"]["transform"] == "upper"
        assert pub["spurennummer"]["hint"], "Ohne Hinweistext sieht der Ermittler nur die Regex."


# =============================================================================
# 2) Platzhalter-Syntax
# =============================================================================

class TestPlaceholderSyntax:

    def test_extraktion_aus_paragraph(self):
        fields = PlaceholderSyntax.extract_from_block(
            {"text": "Nutzer {{a:user.username}} ({{a:user.id}})"}
        )
        assert [f.name for f in fields] == ["user.username", "user.id"]
        assert all(f.type == "a" for f in fields)

    def test_extraktion_aus_tabellenzellen(self):
        """
        Der Kern von Build 388/389: Ohne diese Faehigkeit bliebe ein
        Pflichtfeld in einer Tabellenzelle serverseitig UNGEPRUEFT.
        """
        block = {
            "withHeadings": False,
            "content": [
                ["Registrierungsdatum", "{{a:user.registered_datetime|unbekannt}}"],
                ["Genutztes Passwort", "{{o:passwort|unbekannt|Hinweis}}"],
            ],
        }
        fields = {f.name: f for f in PlaceholderSyntax.extract_from_block(block)}
        assert set(fields) == {"user.registered_datetime", "passwort"}
        assert fields["passwort"].type == "o"
        assert fields["passwort"].default == "unbekannt"

    def test_regelverweis_wird_erkannt(self):
        fields = PlaceholderSyntax.extract_from_block(
            {"text": "{{m:spurennummer||Hilfetext|rule:spurennummer}}"}
        )
        assert len(fields) == 1
        assert fields[0].type == "m"
        assert fields[0].rule_name == "spurennummer"

    def test_base64_altform_liefert_keinen_regelnamen(self):
        """Abwaertskompatibilitaet: die Alt-Form bleibt Client-Sache."""
        fields = PlaceholderSyntax.extract_from_block(
            {"text": "{{m:alt||Hilfe|XlxkKyQ=}}"}
        )
        assert fields[0].rule_name == ""

    def test_langformen_werden_normalisiert(self):
        fields = PlaceholderSyntax.extract_from_block(
            {"text": "{{mandatory:a}} {{optional:b}} {{auto:c}}"}
        )
        assert [f.type for f in fields] == ["m", "o", "a"]

    def test_listenblock_wird_beruecksichtigt(self):
        fields = PlaceholderSyntax.extract_from_block(
            {"items": ["Punkt {{o:eins}}", {"content": "Punkt {{o:zwei}}"}]}
        )
        assert {f.name for f in fields} == {"eins", "zwei"}


# =============================================================================
# 3) Seed-Skript (templates.db)
# =============================================================================

@pytest.fixture
def templates_con():
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE report_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            description TEXT, role TEXT NOT NULL, topic TEXT NOT NULL,
            body TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
        CREATE TABLE placeholder_queries (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
            sql_query TEXT NOT NULL, tags TEXT, return_type TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
        CREATE TABLE templates_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
            target_id TEXT NOT NULL, target_type TEXT NOT NULL,
            changed_by TEXT NOT NULL, changed_at INTEGER NOT NULL,
            old_value TEXT, new_value TEXT);
    """)
    con.row_factory = sqlite3.Row
    yield con
    con.close()


class TestSeedMigration:

    def test_erster_lauf_legt_alles_an(self, templates_con):
        rep = apply_migration(templates_con)
        assert rep["table_created"] is True
        assert rep["template_added"] is True
        assert len(rep["queries_added"]) == 4

    def test_idempotent(self, templates_con):
        apply_migration(templates_con)
        rep = apply_migration(templates_con)
        assert rep["table_created"] is False
        assert rep["template_added"] is False
        assert rep["template_skipped"] is True
        assert rep["queries_added"] == []
        assert len(rep["queries_skipped"]) == 4
        # Genau EINE Vorlage — kein Duplikat.
        n = templates_con.execute(
            "SELECT COUNT(*) FROM report_templates WHERE template_key = ?",
            (TEMPLATE_KEY,),
        ).fetchone()[0]
        assert n == 1

    def test_bestehende_query_wird_nicht_ueberschrieben(self, templates_con):
        """Eine im Betrieb angepasste Query darf nicht stillschweigend zurueckfallen."""
        templates_con.execute(
            "INSERT INTO placeholder_queries "
            "(id, title, description, sql_query, tags, return_type, is_active, "
            " created_by, created_at, updated_at) "
            "VALUES ('user.shares_total','ANGEPASST','x','SELECT 99','t','scalar',"
            "1,'mensch',1,1)"
        )
        rep = apply_migration(templates_con)
        assert "user.shares_total" in rep["queries_skipped"]
        row = templates_con.execute(
            "SELECT title, sql_query FROM placeholder_queries WHERE id='user.shares_total'"
        ).fetchone()
        assert row["title"] == "ANGEPASST"
        assert row["sql_query"] == "SELECT 99"

    def test_vorlage_hat_erwarteten_aufbau(self, templates_con):
        apply_migration(templates_con)
        row = templates_con.execute(
            "SELECT * FROM report_templates WHERE template_key = ?", (TEMPLATE_KEY,)
        ).fetchone()
        assert row["report_type"] == "final"

        blocks = json.loads(row["blocks_json"])
        types = [b["block_type"] for b in blocks]
        assert types == ["header", "paragraph", "header", "paragraph",
                         "header", "table", "paragraph"]

        # Genau EINE Tabelle mit 9 Feststellungszeilen à 2 Spalten.
        table = [b for b in blocks if b["block_type"] == "table"][0]
        content = table["block_data"]["content"]
        assert len(content) == 9
        assert all(len(r) == 2 for r in content)

    def test_vorlage_hat_genau_ein_pflichtfeld_mit_regel(self, templates_con):
        """
        Der Entwickler hat festgelegt: Spurennummer = einziges Pflichtfeld.
        Kaeme unbemerkt ein zweites hinzu, wuerde der Vermerk fuer den
        Ermittler ohne Not blockieren.
        """
        apply_migration(templates_con)
        blocks = json.loads(templates_con.execute(
            "SELECT blocks_json FROM report_templates WHERE template_key = ?",
            (TEMPLATE_KEY,),
        ).fetchone()["blocks_json"])

        mandatory = []
        for b in blocks:
            mandatory += [f for f in PlaceholderSyntax.extract_from_block(b["block_data"])
                          if f.type == "m"]
        assert len(mandatory) == 1
        assert mandatory[0].name == "spurennummer"
        assert mandatory[0].rule_name == "spurennummer"

    def test_optionale_felder_haben_default_unbekannt(self, templates_con):
        apply_migration(templates_con)
        blocks = json.loads(templates_con.execute(
            "SELECT blocks_json FROM report_templates WHERE template_key = ?",
            (TEMPLATE_KEY,),
        ).fetchone()["blocks_json"])
        optional = {}
        for b in blocks:
            for f in PlaceholderSyntax.extract_from_block(b["block_data"]):
                if f.type == "o":
                    optional[f.name] = f.default
        assert optional == {
            "logins_erfolgreich": "unbekannt",
            "passwort": "unbekannt",
            "username_andere_foren": "unbekannt",
        }

    def test_aliases_default_ist_keine_bekannt(self, templates_con):
        """Entwicklerfestlegung 2026-07-12."""
        apply_migration(templates_con)
        blocks = json.loads(templates_con.execute(
            "SELECT blocks_json FROM report_templates WHERE template_key = ?",
            (TEMPLATE_KEY,),
        ).fetchone()["blocks_json"])
        found = None
        for b in blocks:
            for f in PlaceholderSyntax.extract_from_block(b["block_data"]):
                if f.name == "user.aliases":
                    found = f
        assert found is not None
        assert found.default == "keine bekannt"

    def test_audit_eintrag_wird_geschrieben(self, templates_con):
        apply_migration(templates_con)
        n = templates_con.execute(
            "SELECT COUNT(*) FROM templates_audit_log WHERE action='add_template'"
        ).fetchone()[0]
        assert n == 1


# =============================================================================
# 4) Die neuen SQL-Queries gegen echte Forensik-Tabellen
# =============================================================================

class TestNeueQueries:

    @pytest.fixture
    def fdb(self):
        con = sqlite3.connect(":memory:")
        con.executescript("""
            CREATE TABLE uid_profile(id INTEGER, registered INTEGER, last_active INTEGER);
            CREATE TABLE uid_posts(id INTEGER, posted INTEGER);
            CREATE TABLE uid_stats(stat_key TEXT PRIMARY KEY, val_reported INT, val_computed INT);
            INSERT INTO uid_profile VALUES (4711, 1663681740, 1710460800);
            INSERT INTO uid_posts VALUES (1, 1664000000), (2, 1700000000);
            INSERT INTO uid_stats VALUES ('pm_topics_total', NULL, 7),
                                         ('shares_total', NULL, 4);
        """)
        yield con
        con.close()

    def _sql(self, qid: str) -> str:
        return [q for q in _NEW_QUERIES if q["id"] == qid][0]["sql_query"]

    def test_registrierungszeitpunkt_mit_uhrzeit_und_zeitzone(self, fdb):
        val = fdb.execute(self._sql("user.registered_datetime"), {"uid": 4711}).fetchone()[0]
        assert val == "20.09.2022, 13:49 Uhr (UTC)"
        # Die Zeitzone MUSS im Wert stehen — sonst ist die Uhrzeit wertlos.
        assert "(UTC)" in val

    def test_aktivitaetszeitraum(self, fdb):
        val = fdb.execute(self._sql("user.activity_range"), {"uid": 4711}).fetchone()[0]
        assert val == "24.09.2022 bis 15.03.2024"

    def test_aktivitaetszeitraum_ohne_beitraege_ist_leer(self, fdb):
        """
        Konto ohne Beitrag: kein belegbarer Zeitraum. Die Query liefert einen
        Leerstring, damit der Platzhalter auf seinen Default 'unbekannt'
        faellt — ein erfundener Zeitraum waere schlimmer.
        """
        fdb.execute("DELETE FROM uid_posts")
        val = fdb.execute(self._sql("user.activity_range"), {"uid": 4711}).fetchone()[0]
        assert val == ""

    def test_konversationen_und_verbreitungshandlungen(self, fdb):
        assert fdb.execute(self._sql("user.pm_conversations")).fetchone()[0] == 7
        assert fdb.execute(self._sql("user.shares_total")).fetchone()[0] == 4


# =============================================================================
# 5) save_blocks_bulk — transaktionales Einfuegen der Vorlage
# =============================================================================

@pytest.fixture
def edb_with_report():
    """Frische evidence_db mit einem Bericht im Status 'draft'."""
    import os
    import sys
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    from db.evidence_db import EvidenceDb

    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    edb = EvidenceDb(con)
    con.execute(
        "INSERT INTO reports (report_type, sequence_nr, title, created_by, created_at)"
        " VALUES ('final', 1, 'Spurenvermerk', 'h001', 1700000000)"
    )
    con.commit()
    yield edb
    con.close()


def _blocks(n: int) -> list[dict]:
    return [
        {
            "block_id":   "blk-%d" % i,
            "block_type": "paragraph",
            "block_data": json.dumps({"text": "Absatz %d" % i}),
        }
        for i in range(n)
    ]


class TestSaveBlocksBulk:

    def test_legt_alle_bloecke_in_reihenfolge_an(self, edb_with_report):
        ids = edb_with_report.save_blocks_bulk(1, "h001", _blocks(7))
        assert ids == ["blk-%d" % i for i in range(7)]

        blocks = edb_with_report.get_blocks_for_report(1)
        assert [b.block_id for b in blocks] == ids, (
            "Die Reihenfolge der Vorlage muss erhalten bleiben — sonst steht "
            "die Tabelle vor der Ueberschrift."
        )
        assert all(b.author == "h001" for b in blocks)

    def test_zweiter_einfuegevorgang_haengt_hinten_an(self, edb_with_report):
        edb_with_report.save_blocks_bulk(1, "h001", _blocks(3))
        weitere = [
            {"block_id": "z-%d" % i, "block_type": "paragraph",
             "block_data": json.dumps({"text": "spaeter %d" % i})}
            for i in range(2)
        ]
        edb_with_report.save_blocks_bulk(1, "h001", weitere)
        ids = [b.block_id for b in edb_with_report.get_blocks_for_report(1)]
        assert ids == ["blk-0", "blk-1", "blk-2", "z-0", "z-1"]

    def test_fehlerhafter_block_verhindert_JEDES_einfuegen(self, edb_with_report):
        """
        GRUNDREGEL 1 — der Kern dieses Tests: Ein Fehler im 3. von 5 Bloecken
        darf KEINEN halben Spurenvermerk hinterlassen. Ein halber Vermerk
        saehe fuer den Ermittler aus wie ein vollstaendiger.
        """
        from db.evidence_db import EvidenceDbError

        blocks = _blocks(5)
        del blocks[2]["block_type"]  # 3. Block kaputt

        with pytest.raises(EvidenceDbError):
            edb_with_report.save_blocks_bulk(1, "h001", blocks)

        assert edb_with_report.get_blocks_for_report(1) == [], (
            "Es wurde ein Teil der Vorlage gespeichert — genau das darf nicht "
            "passieren."
        )

    def test_leere_blockliste_wird_abgelehnt(self, edb_with_report):
        from db.evidence_db import EvidenceDbError
        with pytest.raises(EvidenceDbError):
            edb_with_report.save_blocks_bulk(1, "h001", [])

    def test_leerer_autor_wird_abgelehnt(self, edb_with_report):
        from db.evidence_db import EvidenceDbError
        with pytest.raises(EvidenceDbError):
            edb_with_report.save_blocks_bulk(1, "   ", _blocks(2))

    def test_tabellenblock_ueberlebt_die_rundreise(self, edb_with_report):
        """Der Tabellenblock muss als Tabelle zurueckkommen — mit Platzhaltern."""
        table_data = {
            "withHeadings": False,
            "content": [["Registrierungsdatum", "{{a:user.registered_datetime|unbekannt}}"]],
        }
        edb_with_report.save_blocks_bulk(1, "h001", [{
            "block_id": "t-1",
            "block_type": "table",
            "block_data": json.dumps(table_data, ensure_ascii=False),
        }])
        blk = edb_with_report.get_blocks_for_report(1)[0]
        assert blk.block_type == "table"
        wieder = json.loads(blk.block_data)
        assert wieder == table_data
        felder = PlaceholderSyntax.extract_from_block(wieder)
        assert [f.name for f in felder] == ["user.registered_datetime"]
