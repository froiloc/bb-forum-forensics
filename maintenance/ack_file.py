# =============================================================================
# maintenance/ack_file.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 435, Fundament)
# =============================================================================
# Zweck:
#   Quiesce-Bestaetigung je Server (data/_maintenance/ack/...ack). Ein
#   Normalserver schreibt seine ACK-Datei, NACHDEM er alle DB-Verbindungen
#   geschlossen (Sperren freigegeben) hat.
#
# Felder (Bauplan Abschnitt 3.3):
#   role, host, pid, quiesced_am, window_id
#
# Intention:
#   Die ACK ist die freiwillige Meldung des Servers "ich habe losgelassen". Sie
#   ist ein Baustein, aber NICHT der Beweis: die Wartungs-CLI verifiziert die
#   Ruhigstellung zusaetzlich durch einen Exklusiv-Lock-Erwerb auf die Ziel-DB
#   (Messen, nicht rechnen). 'window_id' bindet die ACK an genau ein Fenster,
#   damit alte ACKs eines frueheren Fensters nicht faelschlich zaehlen.
#
# Version: v0.7.435 · Build: 435 · 2026-07-19
# =============================================================================

from __future__ import annotations

from pathlib import Path
from typing import Optional

from maintenance.atomic_io import (erwarte, jetzt_epoch, lies_json,
                                   schreibe_json_atomar)
from maintenance.errors import MaintenanceProtocolError
from maintenance.paths import MaintenancePaths


class AckFile:
    """Quiesce-Bestaetigung eines Servers fuer ein bestimmtes Fenster."""

    def __init__(self, role: str, host: str, pid: int, window_id: str,
                 quiesced_am: Optional[int] = None) -> None:
        self.role = str(role)
        self.host = str(host)
        self.pid = int(pid)
        self.window_id = str(window_id)
        self.quiesced_am = (int(quiesced_am)
                            if quiesced_am is not None else jetzt_epoch())

    def to_dict(self) -> dict:
        return {
            "role": self.role, "host": self.host, "pid": self.pid,
            "window_id": self.window_id, "quiesced_am": self.quiesced_am,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AckFile":
        return cls(
            role=erwarte(d, "role"), host=erwarte(d, "host"),
            pid=erwarte(d, "pid"), window_id=erwarte(d, "window_id"),
            quiesced_am=d.get("quiesced_am"),
        )

    # --- Persistenz ----------------------------------------------------------
    def datei(self, paths: MaintenancePaths) -> Path:
        return paths.ack_datei(self.host, self.pid, self.role)

    def schreiben(self, paths: MaintenancePaths) -> None:
        schreibe_json_atomar(self.datei(paths), self.to_dict())

    def entfernen(self, paths: MaintenancePaths) -> None:
        try:
            self.datei(paths).unlink()
        except FileNotFoundError:
            pass

    @classmethod
    def alle_laden(cls, paths: MaintenancePaths,
                   fehler: Optional[list] = None) -> list:
        ergebnis: list = []
        if not paths.ack_dir.is_dir():
            return ergebnis
        for f in sorted(paths.ack_dir.glob("*.ack")):
            try:
                d = lies_json(f)
                if d is not None:
                    ergebnis.append(cls.from_dict(d))
            except MaintenanceProtocolError as exc:
                if fehler is not None:
                    fehler.append((f, str(exc)))
                else:
                    raise
        return ergebnis

    @classmethod
    def fuer_fenster(cls, paths: MaintenancePaths, window_id: str,
                     fehler: Optional[list] = None) -> list:
        """Nur die ACKs, die zu genau diesem Fenster gehoeren."""
        return [a for a in cls.alle_laden(paths, fehler)
                if a.window_id == str(window_id)]
