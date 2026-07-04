# =============================================================================
# management/migrations/evidence/m001_baseline.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Baseline-Migration (Build 319) fuer evidence_<uid>.db.
#
#   Zweck: die Beweis-DB SELBSTBESCHREIBEND machen. Der Runner legt via
#   ensure_registry() die Tabelle schema_migrations an und stempelt beim
#   Anwenden dieser Migration Version 1 — ab dann ist der autoritative
#   "welche Migration ist angewandt"-Zustand in der DB selbst hinterlegt
#   (Leitfaden v0.2 §6.0).
#
#   ADDITIV / DATENNEUTRAL: KEINE strukturelle Aenderung. Die fachlichen
#   Tabellen stammen aus dem Prepper und bleiben unangetastet. up() fuehrt nur
#   einen schema-agnostischen Leicht-Guard aus (mc 2026-07-03: bewusster
#   Verzicht auf strukturelle Assertions, da fuer forensic_* keine eigene
#   Schemadatei vorliegt).
#
#   Self-contained/frozen: bewusst OHNE Import aus gemeinsamen Modulen — der
#   Modul-Quelltext ist die Pruefsumme (runner._module_checksum); geteilter,
#   spaeter veraenderlicher Code wuerde die Belegbarkeit unterlaufen.
#
# Beleg: Bauplan Build 319 v0.1 §1, Datenmigrationsleitfaden_AIW.md v0.2 §6.0,
#        management/migrations/runner.py (ensure_registry/_apply), mc 2026-07-03.
# Version: v0.7.319 · Build: 319 · 2026-07-03
# =============================================================================

VERSION = 1
NAME = "baseline evidence (schema_migrations-Registry, additiv/datenneutral)"
KIND = "additive"


def up(con):
    # Leicht-Guard (schema-agnostisch): Es muss mindestens eine FACHLICHE
    # Nutzertabelle existieren (schema_migrations ausgenommen, da vom Runner
    # zuvor angelegt). So wird keine leere/falsche Datei als evidence-DB
    # gebaselined.
    row = con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' AND name <> 'schema_migrations'"
    ).fetchone()
    if row[0] < 1:
        raise RuntimeError(
            "Baseline abgebrochen: keine fachliche Nutzertabelle gefunden — "
            "keine gueltige evidence-DB."
        )
    # Keine strukturelle Aenderung. Das Stempeln von Version 1 uebernimmt der
    # Runner (INSERT in schema_migrations).
