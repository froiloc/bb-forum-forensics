# =============================================================================
# management/migration_fleet/harness/blob.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# BlobVerifier — Phase-2-Primitive: Bitidentitaet getragener BLOBs.
#
#   SCHEMA-AGNOSTISCH: entdeckt BLOB-Spalten und Primaerschluessel je Tabelle
#   zur Laufzeit ueber PRAGMA table_info. Damit funktioniert er fuer
#   evidence/assets/forensic gleichermaassen, ohne hartkodierte Schemakenntnis
#   (Bauplan §2). Fehlt ein expliziter PK, wird rowid als Schluessel genutzt.
#
#   Ein getragener (nicht transformierter) BLOB MUSS bit-identisch bleiben;
#   jede Abweichung ist ein Fehler. added/removed (Zeilen kamen/gingen) sind
#   informativ — ob zulaessig, entscheidet Executor/Mensch, nicht dieses Primitiv.
#
# Beleg: Datenmigrationsleitfaden_AIW.md v0.2 §3 Phase 2 (BLOB-Bitidentitaet),
#        assets_schema_db.sql (assets.data BLOB), mc 2026-07-03.
# Version: v0.7.317 · Build: 317 · 2026-07-03
# =============================================================================

import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from management.migration_fleet.harness.hashing import blob_sha256


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

@dataclass
class BlobReport:
    ok: bool
    changed: List[str] = field(default_factory=list)   # Digest weicht ab
    added: List[str] = field(default_factory=list)      # nur nachher vorhanden
    removed: List[str] = field(default_factory=list)    # nur vorher vorhanden


def _quote(ident: str) -> str:
    return '"%s"' % ident.replace('"', '""')


def _blob_and_key_columns(con: sqlite3.Connection, table: str
                          ) -> Tuple[List[str], List[str]]:
    """
    Liefert (blob_spalten, schluessel_spalten) einer Tabelle.
    PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk).
    Schluessel = Spalten mit pk>0 (nach pk-Reihenfolge); sonst ['rowid'].
    """
    cols = con.execute("PRAGMA table_info(%s)" % _quote(table)).fetchall()
    blob_cols = [c[1] for c in cols if str(c[2] or "").upper() == "BLOB"]
    pk_cols = [c[1] for c in sorted(
        [c for c in cols if c[5]], key=lambda c: c[5])]
    key_cols = pk_cols if pk_cols else ["rowid"]
    return blob_cols, key_cols


class BlobVerifier:
    """Bitidentitaet getragener BLOBs (schema-agnostisch)."""

    @staticmethod
    def blob_digests(path: str) -> Dict[str, str]:
        """
        Map "table|column|pk" -> SHA256 (bzw. NULL_MARKER) fuer jeden BLOB-Wert.
        """
        con = _nur_lesend(path)
        try:
            digests: Dict[str, str] = {}
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'")]
            for t in tables:
                blob_cols, key_cols = _blob_and_key_columns(con, t)
                if not blob_cols:
                    continue
                sel = ", ".join(_quote(c) for c in (key_cols + blob_cols))
                for row in con.execute(
                        'SELECT %s FROM %s' % (sel, _quote(t))):
                    keyvals = row[:len(key_cols)]
                    blobvals = row[len(key_cols):]
                    pk_str = ",".join(str(v) for v in keyvals)
                    for i, col in enumerate(blob_cols):
                        k = "%s|%s|%s" % (t, col, pk_str)
                        digests[k] = blob_sha256(blobvals[i])
            return digests
        finally:
            con.close()

    @staticmethod
    def compare(before: Dict[str, str], after: Dict[str, str]) -> BlobReport:
        report = BlobReport(ok=True)
        report.added = sorted(set(after) - set(before))
        report.removed = sorted(set(before) - set(after))
        for k in sorted(set(before) & set(after)):
            if before[k] != after[k]:
                report.changed.append(k)
        report.ok = not report.changed  # getragene BLOBs muessen bit-identisch sein
        return report
