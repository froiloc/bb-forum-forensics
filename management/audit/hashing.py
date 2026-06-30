# =============================================================================
# management/audit/hashing.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Reine, zustandslose Hilfsfunktionen für das hash-verkettete Audit-Log.
#   Hier — und NUR hier — ist die kanonische Serialisierung und die exakte
#   Hash-Formel definiert. Die Formel ist ab Zeile 1 der Kette EINGEFROREN:
#   eine Änderung würde alle Folge-Hashes verschieben und den Manipulations-
#   nachweis zerstören.
#
# Designentscheidungen (Beleg: Bauplan B7 v0.2 §2.3, mc 2026-07-01):
#   - content/meta werden deterministisch serialisiert: json.dumps mit
#     sort_keys=True und kompakten Separatoren. Damit ist die Byte-Repräsentation
#     reproduzierbar, unabhängig von Dict-Einfügereihenfolge.
#   - Felder werden mit dem Unit-Separator 0x1F verbunden. Dieses Steuerzeichen
#     kommt in JSON/Text praktisch nicht vor und verhindert Feld-Injektion
#     (z. B. dass "a"+"bc" und "ab"+"c" denselben Hash ergeben).
#   - 'meta' ist von Beginn an Teil der Formel (Default ""). Künftige Zusatzinfo
#     wandert nach 'meta', OHNE dass Formel oder Spaltensatz geändert werden
#     müssen — alte Zeilen bleiben gültig (sie haben meta="" gehasht).
#
# Version: v0.7.306 · Build: 306 · 2026-07-01
# =============================================================================

import hashlib
import json
from typing import Any, Optional

# Genesis-Vorgänger-Hash: 64 Nullen (SHA-256-Breite in Hex).
GENESIS_PREV_HASH: str = "0" * 64

# Unit-Separator (ASCII 0x1F) als Feldtrenner für die Hash-Eingabe.
_USEP: str = "\x1f"


def canonical(obj: Any) -> str:
    """
    Deterministische JSON-Serialisierung für content/meta.

    None  -> ""  (leeres Feld; in der Formel als "" gehasht)
    sonst -> kompaktes JSON mit sortierten Schlüsseln, UTF-8-fähig.
    """
    if obj is None:
        return ""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_row_hash(
    prev_hash: str,
    seq: int,
    ts: int,
    actor_id: Optional[int],
    event_type: str,
    target_type: Optional[str],
    target_id: Optional[str],
    content_canonical: str,
    meta_canonical: str,
) -> str:
    """
    Berechnet den row_hash einer Audit-Zeile.

    EINGEFRORENE Formel:
        sha256(
            prev_hash 0x1F seq 0x1F ts 0x1F actor_id 0x1F event_type 0x1F
            target_type 0x1F target_id 0x1F content_canonical 0x1F meta_canonical
        )

    NULL/None-Felder (actor_id, target_type, target_id) gehen als "" ein.
    content_canonical und meta_canonical sind bereits kanonische Strings
    (siehe canonical()).
    """
    parts = [
        prev_hash,
        str(seq),
        str(ts),
        "" if actor_id is None else str(actor_id),
        event_type,
        "" if target_type is None else str(target_type),
        "" if target_id is None else str(target_id),
        content_canonical,
        meta_canonical,
    ]
    payload = _USEP.join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
