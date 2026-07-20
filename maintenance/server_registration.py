# =============================================================================
# maintenance/server_registration.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 435, Fundament)
# =============================================================================
# Zweck:
#   Anmeldung eines im Wartungsmodus gestarteten Test-Servers
#   (data/_maintenance/servers/<uuid>.json). Unter dieser UUID ist der Server
#   auffindbar und — ueber das dateivermittelte Kill-Feld — beendbar.
#
# Felder (Bauplan Abschnitt 3.4):
#   uuid, role, host, pid, port, subject_id, build, config, started_am, window_id,
#   kill_angefordert, kill_von, kill_am
#
# Intention:
#   Der Kill-Kanal ist bewusst DATEIVERMITTELT (kill_angefordert im JSON), damit
#   er ueber den geteilten Share hinweg ohne Netzverbindung funktioniert: Das
#   Kill-Werkzeug (Build D) setzt kill_angefordert=true; der Server pollt seine
#   eigene Anmeldung, erkennt das, gibt DBs frei, beendet sich und entfernt seine
#   Anmeldedatei. Deren Verschwinden ist die Bestaetigung.
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# =============================================================================

from __future__ import annotations

import uuid as _uuid
from pathlib import Path
from typing import Optional

from maintenance.atomic_io import (erwarte, jetzt_epoch, lies_json,
                                   schreibe_json_atomar)
from maintenance.errors import MaintenanceProtocolError
from maintenance.paths import MaintenancePaths


class ServerRegistration:
    """Anmeldung eines --maintenance-Test-Servers."""

    def __init__(self, uuid: str, role: str, host: str, pid: int, build: int,
                 window_id: str, port: Optional[int] = None,
                 subject_id: Optional[int] = None, config: Optional[str] = None,
                 started_am: Optional[int] = None,
                 kill_angefordert: bool = False, kill_von: Optional[str] = None,
                 kill_am: Optional[int] = None) -> None:
        self.uuid = str(uuid)
        self.role = str(role)
        self.host = str(host)
        self.pid = int(pid)
        self.build = int(build)
        self.window_id = str(window_id)
        self.port = int(port) if port is not None else None
        self.subject_id = int(subject_id) if subject_id is not None else None
        self.config = str(config) if config is not None else None
        self.started_am = int(started_am) if started_am is not None else jetzt_epoch()
        self.kill_angefordert = bool(kill_angefordert)
        self.kill_von = str(kill_von) if kill_von is not None else None
        self.kill_am = int(kill_am) if kill_am is not None else None

    # --- Erzeugung / (De-)Serialisierung ------------------------------------
    @classmethod
    def neu(cls, role: str, host: str, pid: int, build: int, window_id: str,
            port: Optional[int] = None, subject_id: Optional[int] = None,
            config: Optional[str] = None) -> "ServerRegistration":
        return cls(uuid=str(_uuid.uuid4()), role=role, host=host, pid=pid,
                   build=build, window_id=window_id, port=port, subject_id=subject_id,
                   config=config)

    def to_dict(self) -> dict:
        return {
            "uuid": self.uuid, "role": self.role, "host": self.host,
            "pid": self.pid, "build": self.build, "window_id": self.window_id,
            "port": self.port, "subject_id": self.subject_id, "config": self.config,
            "started_am": self.started_am,
            "kill_angefordert": self.kill_angefordert,
            "kill_von": self.kill_von, "kill_am": self.kill_am,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ServerRegistration":
        return cls(
            uuid=erwarte(d, "uuid"), role=erwarte(d, "role"),
            host=erwarte(d, "host"), pid=erwarte(d, "pid"),
            build=erwarte(d, "build"), window_id=erwarte(d, "window_id"),
            port=d.get("port"), subject_id=d.get("subject_id"), config=d.get("config"),
            started_am=d.get("started_am"),
            kill_angefordert=d.get("kill_angefordert", False),
            kill_von=d.get("kill_von"), kill_am=d.get("kill_am"),
        )

    # --- Persistenz ----------------------------------------------------------
    def datei(self, paths: MaintenancePaths) -> Path:
        return paths.server_datei(self.uuid)

    def schreiben(self, paths: MaintenancePaths) -> None:
        schreibe_json_atomar(self.datei(paths), self.to_dict())

    def entfernen(self, paths: MaintenancePaths) -> None:
        try:
            self.datei(paths).unlink()
        except FileNotFoundError:
            pass

    @classmethod
    def laden(cls, paths: MaintenancePaths,
              uuid: str) -> Optional["ServerRegistration"]:
        d = lies_json(paths.server_datei(uuid))
        return cls.from_dict(d) if d is not None else None

    @classmethod
    def alle_laden(cls, paths: MaintenancePaths,
                   fehler: Optional[list] = None) -> list:
        ergebnis: list = []
        if not paths.servers_dir.is_dir():
            return ergebnis
        for f in sorted(paths.servers_dir.glob("*.json")):
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

    # --- Kill-Kanal (dateivermittelt) ---------------------------------------
    def kill_anfordern(self, paths: MaintenancePaths, von: str) -> None:
        """Setzt das Kill-Feld und schreibt die Anmeldung atomar neu."""
        self.kill_angefordert = True
        self.kill_von = str(von)
        self.kill_am = jetzt_epoch()
        self.schreiben(paths)

    def ist_kill_angefordert(self, paths: MaintenancePaths) -> bool:
        """
        Liest die eigene Anmeldedatei frisch und meldet, ob ein Kill ansteht.
        Ist die Datei verschwunden, gilt das als 'kein aktiver Auftrag' (False).
        """
        aktuell = self.laden(paths, self.uuid)
        return bool(aktuell and aktuell.kill_angefordert)
