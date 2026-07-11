# =============================================================================
# management/reports/evidence_scanner.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Berichts-Abnahme
# =============================================================================
# EvidenceScanner — findet die evidence_<uid>.db-Dateien und bildet je Fall
# einen FINGERABDRUCK, mit dem der Scan-Cache (m009) entscheidet, ob eine DB
# neu eingelesen werden muss.
#
# WAL-FALLE (gemessen, Build 374 — der Grund fuer dieses Modul):
#   Ein UPDATE im WAL-Modus aendert mtime UND Groesse der .db-Datei NICHT.
#   Nur die -wal-Datei aendert sich. Ein Fingerabdruck nur ueber die .db wuerde
#   geaenderte Berichte STILL uebersehen (Grundregel 1: kein stiller Verlust).
#   -> Der Fingerabdruck umfasst ALLE zur Datenbank gehoerenden Dateien:
#      evidence_<uid>.db, evidence_<uid>.db-wal, evidence_<uid>.db-shm
#      (je Groesse + mtime_ns). Fehlt eine Datei, geht das als 'None' in den
#      Abdruck ein — auch ihr Verschwinden ist eine Aenderung.
#
# BERATENDER CHARAKTER (mc): Der Fingerabdruck ist ein BESCHLEUNIGER, nie ein
#   Beweismittel. In PROD (Windows/UNC/SMB) kann mtime grob oder verzoegert
#   sein; ein Fehltreffer kostet nur Zeit (Neulesen), ein Treffer spart sie.
#   Fuer Beweisrelevantes (Siegel, Build 376) gilt AUSSCHLIESSLICH der
#   Inhaltshash — niemals mtime.
#
# Beleg: mc 2026-07-10; Messung Build 374 (300 DBs Vollscan ~161 ms).
# Version: v0.7.374 · Build: 374 · 2026-07-10
# =============================================================================

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# evidence_<uid>.db — Cross-Evidence-DBs (evidence_<uid>_<iid>.db) sind KEINE
# Fall-Berichts-DBs und werden bewusst NICHT erfasst (anderer Zweck).
_EVIDENCE_RE = re.compile(r"^evidence_(\d+)\.db$")

# Dateien, die in den Fingerabdruck eingehen: .db und -wal.
#
# WARUM -shm NICHT (gemessen, Build 374): Die -shm-Datei ist der abgeleitete
#   Shared-Memory-Index des WAL. Sie enthaelt KEINE Daten und wird bei JEDEM
#   Zugriff neu geschrieben — auch bei einem reinen LESEZUGRIFF. Nimmt man sie
#   in den Abdruck auf, invalidiert der Cache sich SELBST (unser eigenes Lesen
#   aendert ihn), und jeder Scan wuerde alle DBs neu einlesen.
#   Messung: Abdruck MIT -shm nach zwei reinen Lesezugriffen -> verschieden;
#            Abdruck OHNE -shm -> stabil, erkennt echte Aenderungen weiterhin.
_SUFFIXES = ("", "-wal")


class EvidenceScanner:
    """Findet evidence_<uid>.db und bildet WAL-sichere Fingerabdruecke."""

    def __init__(self, evidence_dir: str) -> None:
        self._dir = Path(evidence_dir)

    @property
    def directory(self) -> Path:
        return self._dir

    def list_cases(self) -> List[Tuple[int, Path]]:
        """
        Alle Fall-DBs im Verzeichnis: [(user_id, pfad), ...], nach user_id.
        Existiert das Verzeichnis nicht, ist die Liste leer (der Aufrufer
        meldet das; kein stiller Fehlpfad).
        """
        if not self._dir.is_dir():
            return []
        out: List[Tuple[int, Path]] = []
        for entry in os.listdir(self._dir):
            m = _EVIDENCE_RE.match(entry)
            if m:
                out.append((int(m.group(1)), self._dir / entry))
        out.sort(key=lambda t: t[0])
        return out

    @staticmethod
    def fingerprint(db_path: Path) -> str:
        """
        Kanonischer Fingerabdruck ueber die datenrelevanten DB-Dateien
        (.db und -wal): 'name:size:mtime_ns|...' — fehlende Datei -> 'name:-:-'.
        Deterministisch (feste Reihenfolge). -shm bleibt bewusst aussen vor
        (siehe _SUFFIXES: aendert sich schon beim Lesen).
        """
        parts: List[str] = []
        for suf in _SUFFIXES:
            p = Path(str(db_path) + suf)
            try:
                st = p.stat()
                parts.append("%s:%d:%d" % (suf or ".db", st.st_size,
                                           st.st_mtime_ns))
            except OSError:
                parts.append("%s:-:-" % (suf or ".db",))
        return "|".join(parts)

    def fingerprints(self) -> Dict[int, str]:
        """Fingerabdruck je Fall (user_id -> fingerprint)."""
        return {uid: self.fingerprint(path)
                for uid, path in self.list_cases()}
