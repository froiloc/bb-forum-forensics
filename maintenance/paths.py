# =============================================================================
# maintenance/paths.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 435, Fundament)
# =============================================================================
# Zweck:
#   Zentrale, einzige Quelle fuer alle Pfade des Wartungs-Dateiprotokolls unter
#   dem geteilten Datenverzeichnis.
#
# Layout (siehe Bauplan Wartungsmodus, Abschnitt 3):
#   data/_maintenance/
#       window.json                    -> das Wartungsfenster-Flag
#       presence/<host>__<pid>__<role> -> Praesenz-Beacon je laufendem Server
#       ack/<host>__<pid>__<role>.ack  -> Quiesce-Bestaetigung je Server
#       servers/<uuid>.json            -> Anmeldung je --maintenance-Server
#
# Intention:
#   Dateibasiert und DB-unabhaengig — das Signal darf nicht in einer DB liegen,
#   die man gerade stillstellen will (Henne-Ei). Dateinamen werden
#   Windows-sicher kodiert (der Rollenname enthaelt ':' wie 'webserver:1488',
#   das ist unter NTFS in Dateinamen unzulaessig).
#
# Version: v0.7.435 · Build: 435 · 2026-07-19
# =============================================================================

from __future__ import annotations

from pathlib import Path

# Unter Windows in Dateinamen unzulaessige Zeichen.
_UNSICHER = '<>:"/\\|?*'


class MaintenancePaths:
    """Berechnet alle Pfade des Wartungsprotokolls relativ zum Datenverzeichnis."""

    WURZEL_NAME = "_maintenance"

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.wurzel = self.data_dir / self.WURZEL_NAME
        self.window_datei = self.wurzel / "window.json"
        self.presence_dir = self.wurzel / "presence"
        self.ack_dir = self.wurzel / "ack"
        self.servers_dir = self.wurzel / "servers"

    def verzeichnisse_anlegen(self) -> None:
        """Legt die vier Verzeichnisse an (idempotent)."""
        for d in (self.wurzel, self.presence_dir, self.ack_dir, self.servers_dir):
            d.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def dateisicher(text: object) -> str:
        """Ersetzt unter Windows unzulaessige Zeichen durch '-'."""
        return "".join("-" if c in _UNSICHER else c for c in str(text))

    def presence_datei(self, host: str, pid: int, role: str) -> Path:
        name = f"{self.dateisicher(host)}__{int(pid)}__{self.dateisicher(role)}.json"
        return self.presence_dir / name

    def ack_datei(self, host: str, pid: int, role: str) -> Path:
        name = f"{self.dateisicher(host)}__{int(pid)}__{self.dateisicher(role)}.ack"
        return self.ack_dir / name

    def server_datei(self, uuid: str) -> Path:
        return self.servers_dir / f"{self.dateisicher(uuid)}.json"
