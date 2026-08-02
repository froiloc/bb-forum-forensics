# =============================================================================
# management/migration_fleet/harness/rowcount.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# RowcountVerifier — Phase-2-Primitive: Zeilenzahlen je Tabelle und Vergleich
# vorher/nachher gegen ERWARTETE Deltas. Rein lesend.
#
#   Kernaussage der Verlustfreiheit: Wo eine Migration nichts entfernen darf
#   (erwartetes Delta 0), ist jeder Verlust ein Fehler; wo sie bewusst etwas
#   aendert, wird das erwartete Delta vorab deklariert. Jede Abweichung landet
#   im Report — kein stilles Uebergehen (Grundregel 1).
#
#   new_tables / dropped_tables werden INFORMATIV gemeldet (additive Migration
#   darf Tabellen anlegen; destruktive kann welche entfernen/rebuilden). Ob das
#   zulaessig ist, entscheidet NICHT dieses Primitiv, sondern Executor/Mensch.
#
# Beleg: Datenmigrationsleitfaden_AIW.md v0.2 §3 Phase 2/§8; analog
#        schema_migrations.row_count_before/after (runner.py). mc 2026-07-03.
# Version: v0.7.317 · Build: 317 · 2026-07-03
# =============================================================================

import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _nur_lesend(path: str) -> sqlite3.Connection:
    """
    Oeffnet die Datei NUR LESEND - und das ist hier kein Feinschliff.

    BEFUND, GEMESSEN AM 2026-08-01 (Vorgang f51fd838, viertes und fuenftes
    Auftreten des Musters): Alle Pruefungen dieses Pruefstands sagen in ihrem
    eigenen Kopf "Rein lesend" und haben die Datei trotzdem gewoehnlich
    geoeffnet. Bei SQLite ist das NICHT folgenlos:

        integrity_check auf einer NICHT VORHANDENEN Datei
            -> IntegrityResult(ok=True, messages=[])
            -> und die Datei ist danach da, 0 Byte gross.

    Der Pruefstand hat also die Unversehrtheit einer Datenbank BESTAETIGT,
    die er im selben Atemzug selbst angelegt hat. Dasselbe galt fuer
    table_rowcounts ('{}') und read_instance_version ('0').

    WARUM DAS HIER BESONDERS SCHWER WIEGT: Dieser Pruefstand ist der
    Vorher/Nachher-Vergleich einer Migration - er soll BELEGEN, dass nichts
    verlorengegangen ist. Ein vertippter Pfad ergab eine leere
    Vorher-Aufnahme, und jeder Nachher-Vergleich gegen sie sah danach wie ein
    ZUGEWINN aus. Ein Verlust konnte so nicht auffallen.

    Mit 'mode=ro' scheitert der Zugriff auf eine nicht vorhandene Datei mit
    einem klaren Fehler - und das ist die richtige Antwort. Der Pfad, der
    geprueft werden soll, muss existieren.
    """
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True)

@dataclass(frozen=True)
class RowcountDiscrepancy:
    table: str
    before: int
    after: int
    expected_delta: int
    actual_delta: int


@dataclass
class RowcountReport:
    ok: bool
    discrepancies: List[RowcountDiscrepancy] = field(default_factory=list)
    new_tables: List[str] = field(default_factory=list)
    dropped_tables: List[str] = field(default_factory=list)


def _user_tables(con: sqlite3.Connection) -> List[str]:
    return [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


class RowcountVerifier:
    """Zeilenzahlen je Tabelle und verlustfreie Vergleichslogik."""

    @staticmethod
    def table_rowcounts(path: str) -> Dict[str, int]:
        con = _nur_lesend(path)
        try:
            out: Dict[str, int] = {}
            for t in _user_tables(con):
                # Tabellennamen aus sqlite_master sind vertrauenswuerdig; zur
                # Sicherheit dennoch in doppelte Anfuehrungszeichen gefasst.
                out[t] = con.execute(
                    'SELECT COUNT(*) FROM "%s"' % t.replace('"', '""')
                ).fetchone()[0]
            return out
        finally:
            con.close()

    @staticmethod
    def compare(before: Dict[str, int], after: Dict[str, int],
                expected_deltas: Optional[Dict[str, int]] = None
                ) -> RowcountReport:
        expected_deltas = expected_deltas or {}
        report = RowcountReport(ok=True)
        report.new_tables = sorted(set(after) - set(before))
        report.dropped_tables = sorted(set(before) - set(after))
        for t in sorted(set(before) & set(after)):
            actual = after[t] - before[t]
            expected = expected_deltas.get(t, 0)
            if actual != expected:
                report.discrepancies.append(RowcountDiscrepancy(
                    table=t, before=before[t], after=after[t],
                    expected_delta=expected, actual_delta=actual))
        # ok = keine Abweichung bei den GETRAGENEN (gemeinsamen) Tabellen.
        # new_/dropped_tables sind informativ und setzen ok NICHT allein auf False.
        report.ok = not report.discrepancies
        return report
