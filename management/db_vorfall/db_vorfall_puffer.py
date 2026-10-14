# =============================================================================
# management/db_vorfall/db_vorfall_puffer.py
# IT-Forensisches Ermittlungswerkzeug — Register "Datenbank-Vorfaelle" (Build 777)
# =============================================================================
# Zweck:
#   Ablage fuer Vorfaelle, die nicht sofort ins Register koennen, weil
#   coordinator.db nicht erreichbar ist (gesperrt, Netzlaufwerk weg,
#   beschaedigt). Festlegung 14.10.2026: "Wenn coordinator.db nicht
#   erreichbar ist: Vorfall ins Protokoll, Eintrag spaeter nachholen."
#
#   EINE DATEI JE VORFALL: <verzeichnis>/db_vorfall_<vorfall_uid>.json mit dem
#   vollstaendigen Abbild der Meldung (DbVorfallMeldung.als_dict). Nach dem
#   erfolgreichen Nachtrag loescht der Melder die Datei; gelingt das Loeschen
#   nicht, schadet es nicht — der naechste Nachtrag findet den Vorfall schon
#   im Register und schreibt nichts (Idempotenz ueber vorfall_uid, M041).
#
# ── WO DER PUFFER LIEGT ─────────────────────────────────────────────────────
#
#   <backup.dest_dir>/defekt/ausstehende_vorfaelle — neben der Sicherung der
#   beschaedigten Datei und dem Reparaturprotokoll (db/reparatur/
#   reparatur_ziel.py). Alles zu einem Vorfall liegt damit an EINEM Ort, und
#   der Ort ist von jedem Rechner aus derselbe (zentrale Sicherungsablage),
#   sodass der naechste Start IRGENDEINES Falls den Nachtrag leisten kann.
#
# ── SCHREIBEN OHNE HALBE DATEI ──────────────────────────────────────────────
#
#   Erst <name>.tmp schreiben, flush + fsync, dann os.replace auf den
#   endgueltigen Namen. Ein Abbruch hinterlaesst hoechstens eine .tmp-Datei,
#   nie eine halbe .json, die beim Nachtrag als unlesbar erschiene. eintraege()
#   meldet uebrig gebliebene .tmp-Dateien trotzdem (Grundregel 1).
#
# Version: v0.8.777 · Build: 777 · 2026-10-14
# =============================================================================

from __future__ import annotations

import json
import os
from typing import Any, List, Optional, Tuple

from management.db_vorfall.db_vorfall_fehler import DbVorfallFehler
from management.db_vorfall.db_vorfall_meldung import DbVorfallMeldung

#: Unterordner unter dem Ordner fuer beschaedigte Dateien (<dest_dir>/defekt).
UNTERORDNER = "ausstehende_vorfaelle"
_PRAEFIX = "db_vorfall_"
_ENDUNG = ".json"


class DbVorfallPuffer:
    """Ablage noch nicht eingetragener Vorfaelle, eine JSON-Datei je Vorfall."""

    def __init__(self, verzeichnis: str) -> None:
        self.verzeichnis = os.path.abspath(str(verzeichnis))

    @classmethod
    def aus_konfiguration(cls, cfg: Any) -> "DbVorfallPuffer":
        """<backup.dest_dir>/defekt/ausstehende_vorfaelle aus config.yaml.
        Wirft ReparaturZielFehler, wenn backup.dest_dir fehlt."""
        from db.reparatur.reparatur_ziel import ReparaturZiel
        ziel, _herkunft = ReparaturZiel.aus_konfiguration(cfg)
        return cls(os.path.join(ziel, UNTERORDNER))

    def pfad_fuer(self, vorfall_uid: str) -> str:
        return os.path.join(self.verzeichnis, _PRAEFIX + vorfall_uid + _ENDUNG)

    # ------------------------------------------------------------ Ablegen ---
    def ablegen(self, meldung: DbVorfallMeldung) -> str:
        """Legt die Meldung ab und gibt den Pfad zurueck. Wirft OSError, wenn
        der Ordner nicht beschreibbar ist, DbVorfallFehler bei einer
        unzulaessigen Meldung."""
        meldung.pruefen()
        os.makedirs(self.verzeichnis, exist_ok=True)
        ziel = self.pfad_fuer(meldung.vorfall_uid)
        tmp = ziel + ".tmp"
        text = json.dumps(meldung.als_dict(), ensure_ascii=False,
                          sort_keys=True, indent=1)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, ziel)
        return ziel

    # ------------------------------------------------------------- Lesen ---
    def eintraege(self) -> List[Tuple[str, Optional[DbVorfallMeldung],
                                      Optional[str]]]:
        """
        Alle Dateien im Puffer, nach Namen sortiert:
        (pfad, meldung, None) fuer eine lesbare Meldung,
        (pfad, None, fehlertext) fuer eine unlesbare oder eine .tmp-Datei.
        Ein fehlender Ordner ist ein leerer Puffer.
        """
        if not os.path.isdir(self.verzeichnis):
            return []
        aus: List[Tuple[str, Optional[DbVorfallMeldung], Optional[str]]] = []
        for name in sorted(os.listdir(self.verzeichnis)):
            if not name.startswith(_PRAEFIX):
                continue
            pfad = os.path.join(self.verzeichnis, name)
            if name.endswith(_ENDUNG + ".tmp"):
                aus.append((pfad, None, "unvollstaendig geschrieben (.tmp) — "
                                        "bitte von Hand pruefen"))
                continue
            if not name.endswith(_ENDUNG):
                continue
            try:
                with open(pfad, "r", encoding="utf-8") as fh:
                    meldung = DbVorfallMeldung.aus_dict(json.load(fh))
                meldung.pruefen()
                erwartet = _PRAEFIX + meldung.vorfall_uid + _ENDUNG
                if name != erwartet:
                    raise DbVorfallFehler(
                        "Dateiname passt nicht zur Kennung %s"
                        % meldung.vorfall_uid)
            except (OSError, ValueError, DbVorfallFehler) as exc:
                aus.append((pfad, None, "%s: %s" % (type(exc).__name__, exc)))
                continue
            aus.append((pfad, meldung, None))
        return aus

    def anzahl(self) -> int:
        """Zahl der Dateien im Puffer (lesbare und unlesbare)."""
        return len(self.eintraege())

    # --------------------------------------------------------- Entfernen ---
    def entfernen(self, pfad: str) -> None:
        """Loescht eine nachgetragene Datei. Nur Dateien IN diesem Puffer."""
        pfad = os.path.abspath(pfad)
        if os.path.dirname(pfad) != self.verzeichnis:
            raise DbVorfallFehler(
                "%s liegt nicht im Puffer %s." % (pfad, self.verzeichnis))
        os.remove(pfad)
