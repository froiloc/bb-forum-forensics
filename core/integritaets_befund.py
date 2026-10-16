# =============================================================================
# core/integritaets_befund.py
# IT-Forensisches Ermittlungswerkzeug — Startpruefung der evidence_<uid>.db
# =============================================================================
# Zweck:
#   Ergebnis EINER Integritaetspruefung (EvidenceStartpruefung.pruefen).
#
#   art:
#     'ok'              PRAGMA integrity_check meldet 'ok'
#     'defekt'          integrity_check meldet Fehler, oder die Datei ist als
#                       SQLite nicht lesbar (DatabaseError beim Oeffnen/Lesen)
#     'heisses_journal' die Datei hat ein '-journal' einer unterbrochenen
#                       Transaktion; nur lesend geoeffnet scheitert SQLite mit
#                       'attempt to write a readonly database' (gemessen Build
#                       776), weil es zuerst zurueckrollen muesste
#     'gesperrt'        ein anderer Prozess haelt die Datei gesperrt oder sie
#                       ist nicht zu oeffnen ('database is locked', 'unable to
#                       open'). KEIN Schaden an der Datei — aber auch keine
#                       Aussage ueber sie.
#     'unklar'          ein anderer SQLite-Fehler, z. B. SQLITE_IOERR auf dem
#                       Netzlaufwerk. Keine Aussage ueber die Datei; es wird
#                       NICHT eingegriffen (Befund der Durchsicht, Build 778).
#
#   zeilen — die Meldungen von integrity_check (hoechstens GRENZE Zeilen) bzw.
#            die Fehlermeldung; fehler — Ausnahmetyp, falls eine auftrat.
#
# Version: v0.8.778 · Build: 778 · 2026-10-14
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

ARTEN = ("ok", "defekt", "heisses_journal", "gesperrt", "unklar")


@dataclass
class IntegritaetsBefund:
    """Ergebnis einer Integritaetspruefung."""

    art: str
    zeilen: List[str] = field(default_factory=list)
    fehler: Optional[str] = None
    dauer_s: float = 0.0
    grenze: int = 0

    @property
    def ok(self) -> bool:
        return self.art == "ok"

    def als_dict(self) -> Dict[str, Any]:
        """Fuer den Befund im Register (JSON)."""
        return {"art": self.art, "integrity_check": list(self.zeilen),
                "zeilen_begrenzt_auf": self.grenze, "fehler": self.fehler,
                "dauer_s": round(self.dauer_s, 3)}
