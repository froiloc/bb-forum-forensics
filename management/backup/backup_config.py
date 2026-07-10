# =============================================================================
# management/backup/backup_config.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Backup/PITR (Welle 0)
# =============================================================================
# BackupConfig — getippte, validierte Sicht auf die 'backup:'-Sektion der
# config.yaml. Eine eigene Klasse (Grundregel 10), damit Ziel und Rahmen-
# bedingungen an genau EINER Stelle interpretiert werden und der Planner/
# Executor nicht mit rohen config.get()-Aufrufen hantieren muss.
#
# Beleg: Bauplan B7 v1.1 §11 (Backup, Pfad aus config.yaml); config.yaml
#   'backup:' (kommentiert); mc 2026-07-10.
# Version: v0.7.352 · Build: 352 · 2026-07-10
# =============================================================================

from dataclasses import dataclass

#: Zulaessige Checkpoint-Modi. 'truncate' ist BEWUSST nicht dabei — ein
#: TRUNCATE-Checkpoint blockiert/gefaehrdet den Live-Betrieb (Bauplan §11).
VALID_CHECKPOINTS = ("passive", "none")


class BackupConfigError(Exception):
    """Ungueltige Backup-Konfiguration (klarer Fehler statt stillem Default)."""


@dataclass(frozen=True)
class BackupConfig:
    """
    Rahmenbedingungen der Datensicherung.

    dest_dir            — Zielverzeichnis (Prod: UNC/SMB).
    retention_count     — Anzahl behaltener Generationen je DB (>= 1).
    min_free_factor     — geforderter freier Platz als Vielfaches der
                          Gesamt-Quellgroesse (> 0; Reserve fuer VACUUM-Overhead).
    checkpoint          — 'passive' | 'none' (nie 'truncate').
    include_shared_dbs  — default.db/templates.db/translations.db mitsichern.
    """
    dest_dir: str
    retention_count: int
    min_free_factor: float
    checkpoint: str
    include_shared_dbs: bool

    @staticmethod
    def from_loader(cfg) -> "BackupConfig":
        """
        Baut BackupConfig aus einem ConfigLoader (oder jedem Objekt mit
        .get(dotted_key, default)). Werte werden getypt und geprueft; bei
        Unfug wird ein klarer BackupConfigError erhoben (kein stiller Fehlpfad).
        """
        dest_dir = cfg.get("backup.dest_dir", "./backups/")
        if not isinstance(dest_dir, str) or not dest_dir.strip():
            raise BackupConfigError(
                "backup.dest_dir muss ein nicht-leerer Pfad sein. "
                "Gefunden: %r" % (dest_dir,))

        try:
            retention = int(cfg.get("backup.retention_count", 7))
        except (TypeError, ValueError):
            raise BackupConfigError(
                "backup.retention_count muss eine ganze Zahl sein.")
        if retention < 1:
            raise BackupConfigError(
                "backup.retention_count muss >= 1 sein. Gefunden: %d"
                % retention)

        try:
            factor = float(cfg.get("backup.min_free_factor", 1.3))
        except (TypeError, ValueError):
            raise BackupConfigError(
                "backup.min_free_factor muss eine Zahl sein.")
        if factor <= 0:
            raise BackupConfigError(
                "backup.min_free_factor muss > 0 sein. Gefunden: %s" % factor)

        checkpoint = str(cfg.get("backup.checkpoint", "passive")).lower()
        if checkpoint not in VALID_CHECKPOINTS:
            raise BackupConfigError(
                "backup.checkpoint='%s' ist ungueltig. Zulaessig: %s "
                "('truncate' ist im Backup-Pfad verboten)."
                % (checkpoint, ", ".join(VALID_CHECKPOINTS)))

        include_shared = bool(cfg.get("backup.include_shared_dbs", True))

        return BackupConfig(
            dest_dir=dest_dir,
            retention_count=retention,
            min_free_factor=factor,
            checkpoint=checkpoint,
            include_shared_dbs=include_shared,
        )
