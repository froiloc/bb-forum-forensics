# =============================================================================
# maintenance/window_flag.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 435, Fundament)
# =============================================================================
# Zweck:
#   Das Wartungsfenster-Flag (data/_maintenance/window.json). Seine EXISTENZ
#   (sofern nicht abgelaufen) bedeutet "Wartung aktiv".
#
# Felder (Bauplan Abschnitt 3.1):
#   window_id        eindeutige ID des Fensters (uuid4)
#   angefordert_von  Systembenutzer, der die Wartung ausloest
#   angefordert_am   Epoch-Sekunden
#   grund            Klartext
#   ziel             Liste: ["all"] oder z.B. ["coordinator", "evidence:1488"]
#   bei_aktivierung  "pause" | "beenden" — Verhalten der Normalserver
#   min_build        Versions-Waechter (0 = keine Anforderung)
#   ablauf_am        optional; abgelaufenes Fenster gilt als inaktiv
#
# Intention:
#   'bei_aktivierung' und 'min_build' liegen bewusst IM Flag, nicht im Servercode:
#   So entscheidet die wartende Person je Fenster, ob laufende Server pausieren
#   oder sich beenden (z.B. nach einer Migration, damit keine alte Version mit
#   neuen Daten arbeitet).
#
# Version: v0.7.435 · Build: 435 · 2026-07-19
# =============================================================================

from __future__ import annotations

import uuid as _uuid
from pathlib import Path
from typing import Optional

from maintenance.atomic_io import (erwarte, jetzt_epoch, lies_json,
                                   schreibe_json_atomar)
from maintenance.errors import MaintenanceProtocolError
from maintenance.paths import MaintenancePaths


class WindowFlag:
    """Das Wartungsfenster-Flag (window.json)."""

    BEI_AKTIVIERUNG = ("pause", "beenden")

    def __init__(self, window_id: str, angefordert_von: str, grund: str,
                 ziel, bei_aktivierung: str = "pause", min_build: int = 0,
                 ablauf_am: Optional[int] = None,
                 angefordert_am: Optional[int] = None) -> None:
        if bei_aktivierung not in self.BEI_AKTIVIERUNG:
            raise MaintenanceProtocolError(
                f"bei_aktivierung ungueltig: {bei_aktivierung!r} "
                f"(erlaubt: {self.BEI_AKTIVIERUNG})")
        if not isinstance(ziel, (list, tuple)) or not ziel:
            raise MaintenanceProtocolError(
                "ziel muss eine nichtleere Liste sein")
        self.window_id = str(window_id)
        self.angefordert_von = str(angefordert_von)
        self.angefordert_am = (int(angefordert_am)
                               if angefordert_am is not None else jetzt_epoch())
        self.grund = str(grund)
        self.ziel = [str(z) for z in ziel]
        self.bei_aktivierung = bei_aktivierung
        self.min_build = int(min_build)
        self.ablauf_am = int(ablauf_am) if ablauf_am is not None else None

    # --- Erzeugung / (De-)Serialisierung ------------------------------------
    @classmethod
    def neu(cls, angefordert_von: str, grund: str, ziel,
            bei_aktivierung: str = "pause", min_build: int = 0,
            ablauf_am: Optional[int] = None) -> "WindowFlag":
        return cls(window_id=str(_uuid.uuid4()), angefordert_von=angefordert_von,
                   grund=grund, ziel=ziel, bei_aktivierung=bei_aktivierung,
                   min_build=min_build, ablauf_am=ablauf_am)

    def to_dict(self) -> dict:
        return {
            "window_id": self.window_id,
            "angefordert_von": self.angefordert_von,
            "angefordert_am": self.angefordert_am,
            "grund": self.grund,
            "ziel": list(self.ziel),
            "bei_aktivierung": self.bei_aktivierung,
            "min_build": self.min_build,
            "ablauf_am": self.ablauf_am,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WindowFlag":
        return cls(
            window_id=erwarte(d, "window_id"),
            angefordert_von=erwarte(d, "angefordert_von"),
            angefordert_am=erwarte(d, "angefordert_am"),
            grund=erwarte(d, "grund"),
            ziel=erwarte(d, "ziel"),
            bei_aktivierung=d.get("bei_aktivierung", "pause"),
            min_build=d.get("min_build", 0),
            ablauf_am=d.get("ablauf_am"),
        )

    # --- Persistenz ----------------------------------------------------------
    def schreiben(self, paths: MaintenancePaths) -> None:
        schreibe_json_atomar(paths.window_datei, self.to_dict())

    @classmethod
    def laden(cls, paths: MaintenancePaths) -> Optional["WindowFlag"]:
        d = lies_json(paths.window_datei)
        return cls.from_dict(d) if d is not None else None

    @staticmethod
    def entfernen(paths: MaintenancePaths) -> None:
        try:
            paths.window_datei.unlink()
        except FileNotFoundError:
            pass

    @classmethod
    def aktives_fenster(cls, paths: MaintenancePaths,
                        jetzt: Optional[int] = None) -> Optional["WindowFlag"]:
        """Liefert das Fenster nur, wenn es existiert UND nicht abgelaufen ist."""
        flag = cls.laden(paths)
        if flag is None:
            return None
        return flag if flag.ist_aktiv(jetzt) else None

    # --- Zustandsabfragen ----------------------------------------------------
    def ist_abgelaufen(self, jetzt: Optional[int] = None) -> bool:
        if self.ablauf_am is None:
            return False
        return (jetzt if jetzt is not None else jetzt_epoch()) >= self.ablauf_am

    def ist_aktiv(self, jetzt: Optional[int] = None) -> bool:
        return not self.ist_abgelaufen(jetzt)

    def betrifft(self, db_name: str) -> bool:
        """
        Prueft, ob eine DB-Datei im Zielbereich des Fensters liegt.
        'all' trifft alles; 'coordinator' -> coordinator.db;
        'evidence:1488' -> evidence_1488.db.
        """
        if "all" in self.ziel:
            return True
        stem = Path(db_name).stem
        for token in self.ziel:
            if ":" in token:
                name, uid = token.split(":", 1)
                if stem == f"{name}_{uid}":
                    return True
            elif stem == token:
                return True
        return False
