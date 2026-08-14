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
# Build 721: Der Planer erhebt zusaetzlich eine BESTANDSAUFNAHME der
#   Fall-Verzeichnisse (Vorgang dc63928d). Sie ist die Vorher-Aufnahme,
#   gegen die der Executor nach dem Lauf die Nachzuegler bestimmt.
# Version: v0.8.721 · Build: 721 · 2026-08-14
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
    # ----------------------------------------------------------------------
    # BUILD 721 - DIE BESTANDSAUFNAHME (Vorgang dc63928d, dritte Forderung).
    #
    # WOZU: Der Executor soll nach dem Lauf sagen koennen, welche
    # Fall-Datenbank WAEHREND des Laufs entstanden ist. Dafuer braucht er
    # einen Vorher-Stand, und den kann nur der Planer liefern - er ist die
    # Stelle, die die Verzeichnisse VOR dem Lauf liest. Sein Blick IST der
    # Vorher-Zeitpunkt.
    #
    # WARUM BEIDE FELDER: 'fall_verzeichnisse' sagt, WO nachzusehen ist, und
    # zwar unabhaengig davon, ob dort etwas gefunden wurde. Genau daran ist
    # die erste Fassung gescheitert: sie leitete die Verzeichnisse aus den
    # gefundenen Quellen ab, und ein beim Planen LEERES Fall-Verzeichnis kam
    # darin gar nicht vor - die erste Datenbank eines Verzeichnisses konnte
    # also nie als Nachzuegler auffallen (gemessen 14.08.2026, Lage C).
    # 'vorgefunden' sagt, WAS dort lag.
    #
    # VORGABEWERTE, damit jeder bestehende Aufruf von BackupPlan(...) - auch
    # in den Tests - unveraendert gueltig bleibt. Ein Plan ohne
    # Bestandsaufnahme fuehrt dann zu einer LEEREN Nachzueglerliste und nicht
    # zu einer falschen; der Executor sagt das ausdruecklich.
    fall_verzeichnisse: Tuple[str, ...] = ()
    vorgefunden: Tuple[str, ...] = ()


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
        Alle Quell-DBs ermitteln.

        Rueckgabe seit Build 721 VIER Werte:
          (sources, missing, fall_verzeichnisse, vorgefunden)
        Die beiden hinteren sind die Bestandsaufnahme fuer die
        Nachzueglererkennung (Vorgang dc63928d) - siehe BackupPlan.

        Reihenfolge der Quellen: coordinator, (shared:
        default/templates/translations), dann je Verzeichnis die '*.db'
        alphabetisch.

        DIE ERWEITERUNG DER RUECKGABE IST EIN BRUCH, und zwar ein bewusster:
        ein optionales fuenftes Feld haette die Bestandsaufnahme zu einer
        Sache gemacht, die man vergessen kann. Sie darf man nicht vergessen -
        ohne sie ist die Nachzueglerliste still leer. Der einzige Aufrufer im
        Bestand ist plan() in dieser Datei.
        """
        sources: List[BackupSource] = []
        missing: List[str] = []
        # Build 721: die Bestandsaufnahme der Fall-Verzeichnisse.
        fall_dirs: List[str] = []
        vorgefunden: List[str] = []

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
        #
        # BUILD 721: DABEI ENTSTEHT ZUGLEICH DIE BESTANDSAUFNAHME (Vorgang
        # dc63928d). Sie ist NICHT dasselbe wie die Quellenliste - ein
        # Verzeichnis, das erreichbar aber leer ist, steuert keine Quelle bei
        # und gehoert trotzdem in die Liste der zu beobachtenden Orte.
        for dir_key in self._PER_UID_DIRS:
            d = self._paths.get(dir_key)
            if not d or not os.path.isdir(d):
                missing.append("Verzeichnis '%s': %s" % (dir_key, d))
                continue
            fall_dirs.append(os.path.abspath(d))
            for name in sorted(os.listdir(d)):
                if not name.endswith(".db"):
                    continue
                fp = os.path.join(d, name)
                if os.path.isfile(fp):
                    vorgefunden.append(os.path.abspath(fp))
                    label = os.path.splitext(name)[0]  # 'evidence_18'
                    sources.append(
                        BackupSource(label, fp, os.path.getsize(fp)))

        return sources, missing, fall_dirs, vorgefunden

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
        sources, missing, fall_dirs, vorgefunden = self.enumerate_sources()
        total = sum(s.size for s in sources)
        required = int(math.ceil(total * self._cfg.min_free_factor))

        free, err = self._free_at_dest(self._cfg.dest_dir)
        if err is not None:
            return BackupPlan(sources, missing, total, required, 0,
                              self._cfg.dest_dir, False, err,
                              tuple(fall_dirs), tuple(vorgefunden))

        if not sources:
            return BackupPlan(sources, missing, total, required, free,
                              self._cfg.dest_dir, False,
                              "Keine Quell-Datenbanken gefunden.",
                              tuple(fall_dirs), tuple(vorgefunden))

        if free < required:
            reason = ("Zu wenig Speicher am Ziel: benoetigt %d Bytes "
                      "(%.2fx von %d Bytes Quelldaten), frei %d Bytes."
                      % (required, self._cfg.min_free_factor, total, free))
            return BackupPlan(sources, missing, total, required, free,
                              self._cfg.dest_dir, False, reason,
                              tuple(fall_dirs), tuple(vorgefunden))

        return BackupPlan(sources, missing, total, required, free,
                          self._cfg.dest_dir, True, "",
                          tuple(fall_dirs), tuple(vorgefunden))
