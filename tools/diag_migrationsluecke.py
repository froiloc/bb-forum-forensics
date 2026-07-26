# =============================================================================
# tools/diag_migrationsluecke.py
# IT-Forensisches Ermittlungswerkzeug — Diagnose (kein Produktivcode)
# =============================================================================
# Zweck:
#   REPRODUKTION des Befunds aus
#   management/Vermerk_Migrationsluecke_Parallelbetrieb_v0_1.md:
#   Der MigrationRunner fuehrt einen HOECHSTSTAND (MAX(version)) statt einer
#   Menge angewandter Versionen. Wird die hoehere Nummer zuerst eingespielt,
#   werden alle niedrigeren, spaeter gelieferten Migrationen UEBERSPRUNGEN —
#   ohne Fehler, ohne Warnung, ohne Registry-Eintrag.
#
#   Aufruf:  python tools/diag_migrationsluecke.py
#
#   Erwartete Ausgabe (gemessen 2026-07-26, Container):
#     Lauf 1 (Instanz B liefert zuerst, nur m040): [40]
#     Lauf 2 (Instanz A liefert m033-m039 nach):   []
#     -> sieben Migrationen still verloren.
#
#   Rein synthetisch, In-Memory, KEINE Datei und KEINE echte Datenbank wird
#   angefasst. Diese Datei ist ein BELEG, kein Produktivcode.
# Version: v0.8.561 · Build: 561 · 2026-07-26
# =============================================================================

import logging
import pathlib
import sqlite3
import sys
import types
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
from management.migrations.runner import MigrationRunner

def mk(ver, name, sql):
    m = types.ModuleType("m%03d" % ver)
    m.__file__ = __file__
    m.VERSION = ver; m.NAME = name; m.KIND = "additive"
    m.up = lambda con, _s=sql: con.execute(_s)
    return m

con = sqlite3.connect(":memory:")
r1 = MigrationRunner(con, [mk(40, "B: fulltext_release", "CREATE TABLE fulltext_release(x)")])
print("Lauf 1 (Instanz B liefert zuerst, nur m040):", r1.run())
print("   current_version:", r1.current_version())

spaeter = [mk(v, "A: m%03d" % v, "CREATE TABLE a_%d(x)" % v) for v in range(33, 40)]
r2 = MigrationRunner(con, spaeter + [mk(40, "B", "CREATE TABLE fulltext_release(x)")])
print("Lauf 2 (Instanz A liefert m033-m039 nach):", r2.run())
print("   current_version:", r2.current_version())
print("   Tabellen:", sorted(r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")))
print("   registrierte Versionen:", [r[0] for r in con.execute(
    "SELECT version FROM schema_migrations ORDER BY version")])
