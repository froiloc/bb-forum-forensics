# =============================================================================
# maintenance/presence_beacon.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 435, Fundament)
# =============================================================================
# Zweck:
#   Praesenz-Beacon je laufendem Server (data/_maintenance/presence/...).
#   Jeder Langlaeufer schreibt beim Start ein Beacon und aktualisiert dessen
#   'letzter_touch' periodisch. Die Wartungs-CLI liest daraus, WER ACKen muss.
#
# Felder (Bauplan Abschnitt 3.2):
#   role, host, pid, subject_id, port, build, started_at, letzter_touch
#
# Intention:
#   Veraltete Beacons (letzter_touch weit in der Vergangenheit) werden von der
#   CLI als "vermutlich tot, unbestaetigt" gemeldet — nie still als tot
#   angenommen (Grundregel 1). Diese Klasse liefert dafuer nur die Rohdaten und
#   die Alters-Pruefung; die Bewertung/Meldung macht die CLU (Build D).
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# =============================================================================

from __future__ import annotations

from pathlib import Path
from typing import Optional

from maintenance.atomic_io import (erwarte, jetzt_epoch, lies_json,
                                   schreibe_json_atomar)
from maintenance.errors import MaintenanceProtocolError
from maintenance.paths import MaintenancePaths


class PresenceBeacon:
    """Praesenz-Beacon eines laufenden Servers."""

    def __init__(self, role: str, host: str, pid: int, build: int,
                 subject_id: Optional[int] = None, port: Optional[int] = None,
                 started_at: Optional[int] = None,
                 letzter_touch: Optional[int] = None) -> None:
        self.role = str(role)
        self.host = str(host)
        self.pid = int(pid)
        self.build = int(build)
        self.subject_id = int(subject_id) if subject_id is not None else None
        self.port = int(port) if port is not None else None
        self.started_at = int(started_at) if started_at is not None else jetzt_epoch()
        self.letzter_touch = (int(letzter_touch)
                              if letzter_touch is not None else self.started_at)

    def to_dict(self) -> dict:
        return {
            "role": self.role, "host": self.host, "pid": self.pid,
            "build": self.build, "subject_id": self.subject_id, "port": self.port,
            "started_at": self.started_at, "letzter_touch": self.letzter_touch,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PresenceBeacon":
        return cls(
            role=erwarte(d, "role"), host=erwarte(d, "host"),
            pid=erwarte(d, "pid"), build=erwarte(d, "build"),
            subject_id=d.get("subject_id"), port=d.get("port"),
            started_at=d.get("started_at"), letzter_touch=d.get("letzter_touch"),
        )

    # --- Persistenz ----------------------------------------------------------
    def datei(self, paths: MaintenancePaths) -> Path:
        return paths.presence_datei(self.host, self.pid, self.role)

    def schreiben(self, paths: MaintenancePaths) -> None:
        """Schreibt/aktualisiert das Beacon und setzt letzter_touch auf jetzt."""
        self.letzter_touch = jetzt_epoch()
        schreibe_json_atomar(self.datei(paths), self.to_dict())

    def touch(self, paths: MaintenancePaths) -> None:
        """Alias fuer schreiben() — periodischer Lebenszeichen-Schlag."""
        self.schreiben(paths)

    def entfernen(self, paths: MaintenancePaths) -> None:
        try:
            self.datei(paths).unlink()
        except FileNotFoundError:
            pass

    def ist_veraltet(self, max_alter_s: int, jetzt: Optional[int] = None) -> bool:
        now = jetzt if jetzt is not None else jetzt_epoch()
        return (now - self.letzter_touch) > max_alter_s

    @classmethod
    def alle_laden(cls, paths: MaintenancePaths,
                   fehler: Optional[list] = None) -> list:
        """
        Liest alle Praesenz-Beacons. Kaputte Dateien werden — falls 'fehler'
        uebergeben ist — als (Pfad, Grund) gesammelt und uebersprungen; sonst
        wird die MaintenanceProtocolError weitergereicht (GR1: nie still).
        """
        ergebnis: list = []
        if not paths.presence_dir.is_dir():
            return ergebnis
        for f in sorted(paths.presence_dir.glob("*.json")):
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
