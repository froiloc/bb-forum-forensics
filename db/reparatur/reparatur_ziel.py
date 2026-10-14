# =============================================================================
# db/reparatur/reparatur_ziel.py
# IT-Forensisches Ermittlungswerkzeug — Ordner fuer beschaedigte Dateien
# =============================================================================
# Zweck:
#   Ermittelt und prueft den Ordner, in den Sicherung, neue Datei und
#   Protokoll einer Reparatur geschrieben werden:
#       <backup.dest_dir aus config.yaml>/defekt
#   Das Unterverzeichnis 'defekt' trennt beschaedigte Dateien von den
#   regulaeren Sicherungen (Vorgabe Alex, 14.10.2026). Der Sicherungslauf
#   (management/backup/backup_executor.py) beachtet es nicht: seine Muster
#   enden auf '.backup.db' bzw. '.backup.db.defekt' (gemessen, Build 775).
#
# GEPRUEFT WIRD VOR JEDEM SCHREIBEN (Befunde PROD 14.10.2026, Fassung 1.1 des
# Reparaturskripts):
#   F2 Zielordner anlegbar und beschreibbar (Probedatei schreiben, loeschen).
#   F3 Ein Pfad mit '/' oder '\' ohne Laufwerk und ohne '\\server' bezieht
#      Windows auf die Wurzel des aktuellen Laufwerks — das wird angezeigt.
#   F4 Der Zielordner ist NICHT der Ordner des Originals: Sicherung und neue
#      Datei heissen evidence_*.db und wuerden dort von Werkzeugen des
#      Bestands als Fall-Datenbanken gefunden (management/repair_block_types.py
#      Z. 265, tools/diag_sqlite_netdrive2.py Z. 215,
#      tools/diag_matrix_laufzeit.py Z. 170).
#
# Version: v0.8.776 · Build: 776 · 2026-10-14
# =============================================================================
from __future__ import annotations

import os
from typing import Any, Optional, Tuple


class ReparaturZielFehler(Exception):
    """Zielordner nicht ermittelbar oder nicht zulaessig — VOR jedem Schreiben."""


class ReparaturZiel:
    """Ermittlung und Pruefung des Ordners fuer beschaedigte Dateien."""

    UNTERORDNER = "defekt"

    @staticmethod
    def laufwerksbezug(roh: str, windows: Optional[bool] = None) -> Optional[str]:
        """F3: Hinweistext fuer einen Pfad an der Wurzel des aktuellen Laufwerks."""
        if windows is None:
            windows = os.name == "nt"
        if not windows:
            return None
        t = roh.replace("/", "\\")
        # Gemeint: '\x' ja; '\\server\freigabe' (UNC) nein; 'G:\x' beginnt
        # nicht mit '\' und faellt ohnehin heraus.
        if t.startswith("\\") and not t.startswith("\\\\"):
            return ("Der Pfad %r beginnt mit '/' bzw. '\\' ohne Laufwerksbuch"
                    "staben. Windows bezieht ihn auf die Wurzel des aktuellen "
                    "Laufwerks (hier: %s)." % (roh, os.path.splitdrive(
                        os.getcwd())[0] or "Laufwerk des Arbeitsverzeichnisses"))
        return None

    @classmethod
    def aus_konfiguration(cls, cfg: Any) -> Tuple[str, str]:
        """-> (ziel, herkunft) aus backup.dest_dir."""
        roh = cfg.get("backup.dest_dir")
        if not isinstance(roh, str) or not roh.strip():
            raise ReparaturZielFehler(
                "backup.dest_dir fehlt oder ist leer in config.yaml.")
        ziel = os.path.abspath(os.path.join(roh, cls.UNTERORDNER))
        herkunft = "config.yaml backup.dest_dir = %r, Unterordner '%s'" % (
            roh, cls.UNTERORDNER)
        hinweis = cls.laufwerksbezug(roh)
        if hinweis:
            herkunft += "\n  HINWEIS: " + hinweis
        return ziel, herkunft

    @staticmethod
    def _gleicher_ordner(a: str, b: str) -> bool:
        return os.path.normcase(os.path.normpath(os.path.abspath(a))) == \
            os.path.normcase(os.path.normpath(os.path.abspath(b)))

    @classmethod
    def pruefen(cls, original: str, ziel: str, herkunft: str) -> None:
        """F2, F4 — wirft ReparaturZielFehler; schreibt nur eine Probedatei."""
        if not os.path.isfile(original):
            raise ReparaturZielFehler("Datei nicht gefunden: %s" % original)
        if cls._gleicher_ordner(os.path.dirname(os.path.abspath(original)), ziel):
            raise ReparaturZielFehler(
                "Zielordner %s ist der Ordner des Originals. Das ist nicht "
                "zulaessig: Sicherung und neue Datei hiessen evidence_*.db und "
                "wuerden dort von anderen Werkzeugen als weitere Fall-Datenbanken "
                "gefunden. Bitte einen anderen Ordner angeben." % ziel)
        try:
            os.makedirs(ziel, exist_ok=True)
            probe = os.path.join(ziel, ".evidence_reparatur_probe_%d" % os.getpid())
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("probe")
            os.remove(probe)
        except OSError as exc:
            raise ReparaturZielFehler(
                "Zielordner nicht anlegbar oder nicht beschreibbar.\n"
                "  Ermittelter Pfad: %s\n"
                "  Herkunft        : %s\n"
                "  Fehler          : %s\n"
                "Es wurde NICHTS geschrieben." % (ziel, herkunft, exc))
