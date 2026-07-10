# =============================================================================
# management/backup/backup_planner.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Backup/PITR (Welle 0)
# =============================================================================
# BackupPlanner — Phase VOR dem Schreiben. Enumeriert ALLE zu sichernden
# Datenbanken aus den config.yaml-Pfaden und fuehrt die SPEICHERPLATZ-
# VORABPRUEFUNG durch. Diese Pruefung ist vorfall-getrieben: am 2026-07-01
# lief die Platte beim Fallanlegen voll und 'default.db' wurde 'malformed'
# (Beleg: Bauplan B7 v1.1 §7.5.3). Ein Backup darf NIE begonnen werden, wenn
# am Ziel nicht genug Platz ist — sonst entstehen halbe, unbrauchbare Kopien.
#
# Rein lesend: os.stat/os.listdir/shutil.disk_usage. Kein Schreiben, kein
# VACUUM (das folgt im Executor, Build 353). Kein stiller Fehlpfad: fehlende
# Einzel-DBs und fehlende Verzeichnisse werden im Plan SICHTBAR gemacht
# (Grundregel 1).
#
# Beleg: Bauplan B7 v1.1 §11/§7.5.3; mc 2026-07-10.
# Version: v0.7.352 · Build: 352 · 2026-07-10
# =============================================================================

import math
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from management.backup.backup_config import BackupConfig


@dataclass(frozen=True)
class BackupSource:
    """Eine zu sichernde Quell-Datenbank."""
    label: str   # eindeutiges Kuerzel, z.B. 'coordinator', 'evidence_18'
    path: str    # absoluter/relativer Pfad zur .db-Datei
    size: int    # Groesse in Bytes (Momentaufnahme)


@dataclass(frozen=True)
class BackupPlan:
    """
    Ergebnis der Planung + Vorabpruefung.

    ok=True bedeutet: es gibt Quellen UND am Ziel ist genug Platz. ok=False
    liefert in 'reason' eine klare Begruendung. 'missing' listet konfigurierte,
    aber nicht vorhandene Einzel-DBs bzw. fehlende Verzeichnisse (sichtbar,
    nicht fatal).
    """
    sources: List[BackupSource]
    missing: List[str]
    total_size: int
    required_free: int
    free_at_dest: int
    dest_dir: str
    ok: bool
    reason: str


class BackupPlanner:
    """
    Plant ein Voll-Backup aller Datenbanken und prueft den Speicherplatz.

    paths: dict mit den config.yaml-'paths'-Werten (coordinator_db,
      forensic_db_dir, evidence_db_dir, assets_db_dir, default_db, templates_db,
      translations_db). Fehlende Schluessel sind erlaubt (werden uebersprungen
      bzw. als fehlend vermerkt).
    """

    #: Verzeichnisse mit fallbezogenen '<label>_<uid>.db' (immer gesichert).
    _PER_UID_DIRS = ("forensic_db_dir", "evidence_db_dir", "assets_db_dir")

    def __init__(self, paths: Dict[str, str], backup_cfg: BackupConfig) -> None:
        self._paths = paths or {}
        self._cfg = backup_cfg

    # ------------------------------------------------------------- enumerate
    def enumerate_sources(self) -> Tuple[List[BackupSource], List[str]]:
        """
        Alle Quell-DBs ermitteln. Rueckgabe: (sources, missing).
        Reihenfolge: coordinator, (shared: default/templates/translations),
        dann je Verzeichnis die '*.db' alphabetisch.
        """
        sources: List[BackupSource] = []
        missing: List[str] = []

        # Einzel-DBs: coordinator immer; shared nur wenn konfiguriert.
        singles = [("coordinator", self._paths.get("coordinator_db"))]
        if self._cfg.include_shared_dbs:
            singles += [
                ("default", self._paths.get("default_db")),
                ("templates", self._paths.get("templates_db")),
                ("translations", self._paths.get("translations_db")),
            ]
        for label, p in singles:
            if p and os.path.isfile(p):
                sources.append(BackupSource(label, p, os.path.getsize(p)))
            else:
                missing.append("Einzel-DB '%s': %s" % (label, p))

        # Fallbezogene DBs aus den drei Verzeichnissen.
        for dir_key in self._PER_UID_DIRS:
            d = self._paths.get(dir_key)
            if not d or not os.path.isdir(d):
                missing.append("Verzeichnis '%s': %s" % (dir_key, d))
                continue
            for name in sorted(os.listdir(d)):
                if not name.endswith(".db"):
                    continue
                fp = os.path.join(d, name)
                if os.path.isfile(fp):
                    label = os.path.splitext(name)[0]  # 'evidence_18'
                    sources.append(
                        BackupSource(label, fp, os.path.getsize(fp)))

        return sources, missing

    # ------------------------------------------------------------- free space
    def _free_at_dest(self, dest_dir: str) -> Tuple[Optional[int], Optional[str]]:
        """
        Freien Platz am Ziel ermitteln. Das Zielverzeichnis muss noch nicht
        existieren (es wird spaeter angelegt) — dann wird GENAU EINE Ebene
        zurueckgegriffen: das direkte Elternverzeichnis (z.B. der UNC-Share
        existiert, der 'backups'-Unterordner noch nicht). Existiert weder das
        Ziel noch sein Elternverzeichnis, gilt das Ziel als unerreichbar
        (bewusst NICHT weiter hochlaufen: das wuerde auf einen ganz anderen
        Datentraeger zeigen und die Pruefung aushebeln). Rueckgabe:
        (free_bytes, None) oder (None, grund).
        """
        probe = Path(dest_dir)
        for candidate in (probe, probe.parent):
            if candidate.exists():
                try:
                    return shutil.disk_usage(str(candidate)).free, None
                except OSError as exc:
                    return None, ("Freier Platz nicht ermittelbar fuer '%s': %s"
                                  % (candidate, exc))
        return None, ("Zielverzeichnis und dessen Elternverzeichnis nicht "
                      "erreichbar: %s" % dest_dir)

    # ------------------------------------------------------------------- plan
    def plan(self) -> BackupPlan:
        """Enumeration + Vorabpruefung zu einem BackupPlan zusammenfuehren."""
        sources, missing = self.enumerate_sources()
        total = sum(s.size for s in sources)
        required = int(math.ceil(total * self._cfg.min_free_factor))

        free, err = self._free_at_dest(self._cfg.dest_dir)
        if err is not None:
            return BackupPlan(sources, missing, total, required, 0,
                              self._cfg.dest_dir, False, err)

        if not sources:
            return BackupPlan(sources, missing, total, required, free,
                              self._cfg.dest_dir, False,
                              "Keine Quell-Datenbanken gefunden.")

        if free < required:
            reason = ("Zu wenig Speicher am Ziel: benoetigt %d Bytes "
                      "(%.2fx von %d Bytes Quelldaten), frei %d Bytes."
                      % (required, self._cfg.min_free_factor, total, free))
            return BackupPlan(sources, missing, total, required, free,
                              self._cfg.dest_dir, False, reason)

        return BackupPlan(sources, missing, total, required, free,
                          self._cfg.dest_dir, True, "")
