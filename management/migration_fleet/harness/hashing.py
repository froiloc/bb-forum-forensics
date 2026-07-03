# =============================================================================
# management/migration_fleet/harness/hashing.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Datei- und BLOB-Hashing fuer den Verify-Harness.
#
#   sha512_file  : SHA512 einer Datei (Backup-Integritaet, Leitfaden Phase 1).
#   blob_sha256  : SHA256 eines einzelnen BLOB-Werts (Bitidentitaet, Phase 2).
#
# Bewusst NEU angelegt und NICHT aus management/audit/hashing.py uebernommen:
# jene liefert canonical()/compute_row_hash() (SHA256 kanonischer AUDIT-Zeilen)
# — ein anderer Zweck. Datei-/BLOB-Hashing existierte im Repo nicht (geprueft).
#
# Beleg: Datenmigrationsleitfaden_AIW.md v0.2 §3 (SHA512, BLOB-Bitidentitaet),
#        mc 2026-07-03.
# Version: v0.7.317 · Build: 317 · 2026-07-03
# =============================================================================

import hashlib
from typing import Optional, Union

_CHUNK = 1 << 20  # 1 MiB

#: Eindeutige Markierung fuer einen SQL-NULL-BLOB. Nie ein gueltiger Hex-Digest,
#: damit ein Wechsel NULL <-> Wert zuverlaessig als Aenderung erkannt wird.
NULL_MARKER = "NULL"


def sha512_file(path: str, *, chunk_size: int = _CHUNK) -> str:
    """SHA512-Hexdigest einer Datei (streamend, speicherschonend)."""
    h = hashlib.sha512()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def blob_sha256(data: Optional[Union[bytes, str]]) -> str:
    """
    SHA256-Hexdigest eines BLOB-Werts. NULL -> NULL_MARKER (unterscheidbar von
    jedem Digest). str (falls eine BLOB-Spalte Text traegt) wird UTF-8-kodiert.
    """
    if data is None:
        return NULL_MARKER
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()
