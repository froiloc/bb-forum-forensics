# =============================================================================
# core/hosts_manager.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Verwaltet den hosts-Eintrag für den Forumshostnamen.
#
#   DEV/Linux  (hosts_management.enabled = false):
#     No-op. Der Eintrag wird manuell in /etc/hosts gesetzt.
#     Beim Start wird geprüft ob der Eintrag bereits existiert
#     und eine Warnung ausgegeben wenn nicht — aber kein Abbruch.
#
#   PROD/Windows (hosts_management.enabled = true):
#     Automatische Verwaltung des Eintrags in
#     C:\Windows\System32\drivers\etc\hosts.
#     Beim Start: Eintrag hinzufügen (falls nicht vorhanden).
#     Beim sauberen Stop: Eintrag entfernen (cleanup).
#     Erfordert Administratorrechte — Prüfung beim Start.
#
# hosts-Eintrag-Format:
#   <target_ip>  <forum_hostname>  # forensic-tool
#
#   Der Kommentar "# forensic-tool" dient als Markierung, damit nur
#   von diesem Tool selbst gesetzte Einträge wieder entfernt werden.
#   Manuell gesetzte Einträge (ohne diesen Kommentar) werden nie
#   angefasst — Grundregel: kein stiller Eingriff ohne Beleg.
#
# Forensische Relevanz:
#   Der hosts-Eintrag leitet alle Browseranfragen an das Original-Forum
#   auf 127.0.0.2 um. Das ermöglicht dem Ermittler, dieselbe URL zu sehen,
#   die der Beschuldigte gesehen hat — forensisch notwendig für die
#   Nachvollziehbarkeit der Beweismittel.
#
#   Windows-Pfad: C:\Windows\System32\drivers\etc\hosts
#   Linux-Pfad  : /etc/hosts (nur Prüfung, keine automatische Änderung)
#
# Fehlerbehandlung:
#   Jeder Fehler beim Setzen des Eintrags führt zu einem harten Abbruch
#   (HostsManagerError) — kein stiller Betrieb mit falscher Netzwerkkonfiguration
#   (Grundregel 1: kein Beleg darf ausgelassen werden).
#   Ausnahme: In DEV (enabled=false) ist das Fehlen des Eintrags nur eine
#   Warnung, da der Ermittler ihn manuell setzen kann.
#
# Abhängigkeiten: os, sys, platform, pathlib — ausschließlich Stdlib
# Version: v0.1.0 · Build: 011 · 2026-04-11
# =============================================================================

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Optional

from core.config_loader import ConfigLoader
from core.logger import get_logger

logger = get_logger(__name__)

# Kommentar-Markierung für von diesem Tool gesetzte hosts-Einträge.
# Nur Zeilen mit diesem Suffix werden beim Cleanup entfernt.
_MARKER = "# forensic-tool"

# Plattformspezifische hosts-Pfade
_HOSTS_PATH_WINDOWS = Path(r"C:\Windows\System32\drivers\etc\hosts")
_HOSTS_PATH_LINUX   = Path("/etc/hosts")


class HostsManagerError(Exception):
    """
    Wird geworfen, wenn der hosts-Eintrag nicht gesetzt oder entfernt
    werden kann. Führt im PROD-Betrieb zu einem harten Serverabbruch.

    Typische Ursachen:
    - Fehlende Administratorrechte (Windows PROD)
    - hosts-Datei nicht beschreibbar
    - Ungültige Konfiguration (leerer forum_hostname oder target_ip)
    """


class HostsManager:
    """
    Verwaltet den hosts-Eintrag für den Forumshostnamen.

    Verwendung in main.py:
        mgr = HostsManager(config)
        mgr.setup()        # Beim Start — Eintrag setzen oder prüfen
        mgr.cleanup()      # Beim Stop — Eintrag entfernen (nur PROD)

    Im DEV-Modus (enabled=false) tun beide Methoden nichts Destruktives —
    setup() loggt eine Warnung wenn der Eintrag fehlt, cleanup() ist no-op.
    """

    def __init__(self, config: ConfigLoader) -> None:
        self._config   = config
        self._enabled  = bool(config.get("hosts_management.enabled", False))
        self._hostname = str(config.get("hosts_management.forum_hostname", "")).strip()
        self._target   = str(config.get("hosts_management.target_ip", "127.0.0.2")).strip()
        self._is_windows = platform.system() == "Windows"
        self._hosts_path: Path = (
            _HOSTS_PATH_WINDOWS if self._is_windows else _HOSTS_PATH_LINUX
        )
        # Merker ob dieser Run den Eintrag gesetzt hat —
        # nur dann wird er im cleanup() wieder entfernt.
        self._entry_added_by_us: bool = False

    # ------------------------------------------------------------------
    # Öffentliche Schnittstelle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """
        Setzt oder prüft den hosts-Eintrag.

        DEV (enabled=false):
            Prüft ob der Eintrag manuell gesetzt wurde.
            Warnung wenn nicht — kein Abbruch.

        PROD/Windows (enabled=true):
            Prüft Administratorrechte.
            Fügt den Eintrag hinzu, falls nicht vorhanden.
            Harter Abbruch (HostsManagerError) bei jedem Fehler.

        Raises:
            HostsManagerError: Im PROD-Modus bei jedem Fehler.
        """
        if not self._hostname:
            if self._enabled:
                raise HostsManagerError(
                    "hosts_management.forum_hostname ist leer. "
                    "Bitte den Hostnamen des Forums in config.yaml eintragen."
                )
            # DEV ohne hostname: nichts zu tun
            logger.debug("HostsManager: forum_hostname nicht konfiguriert — no-op.")
            return

        if self._enabled:
            self._setup_prod()
        else:
            self._setup_dev()

    def cleanup(self) -> None:
        """
        Entfernt den hosts-Eintrag, wenn dieser Run ihn gesetzt hat.

        DEV (enabled=false): no-op.
        PROD (enabled=true): Entfernt nur Zeilen, die mit _MARKER enden
                             und die von diesem Run hinzugefügt wurden.
        """
        if not self._enabled or not self._entry_added_by_us:
            return

        logger.info(
            "HostsManager: Entferne hosts-Eintrag '%s → %s'.",
            self._hostname, self._target,
        )
        try:
            self._remove_entry()
        except HostsManagerError as exc:
            # Cleanup-Fehler ist kein harter Abbruch — aber er wird laut geloggt.
            # Der Eintrag bleibt in hosts; der Ermittler muss ihn manuell entfernen.
            logger.error(
                "HostsManager: Eintrag konnte nicht entfernt werden: %s "
                "Bitte hosts-Datei manuell bereinigen: %s",
                exc, self._hosts_path,
            )

    # ------------------------------------------------------------------
    # DEV-Modus (enabled=false)
    # ------------------------------------------------------------------

    def _setup_dev(self) -> None:
        """
        DEV-Modus: Prüft ob der Eintrag manuell existiert.
        Gibt eine Warnung aus wenn nicht — kein Abbruch.
        """
        logger.debug(
            "HostsManager: DEV-Modus (enabled=false). "
            "Prüfe ob hosts-Eintrag manuell gesetzt ist."
        )
        if self._entry_exists():
            logger.info(
                "HostsManager: hosts-Eintrag gefunden: '%s → %s'. OK.",
                self._hostname, self._target,
            )
        else:
            logger.warning(
                "HostsManager: Kein hosts-Eintrag für '%s' gefunden. "
                "Bitte manuell in '%s' eintragen: %s  %s",
                self._hostname, self._hosts_path,
                self._target, self._hostname,
            )

    # ------------------------------------------------------------------
    # PROD-Modus (enabled=true, Windows)
    # ------------------------------------------------------------------

    def _setup_prod(self) -> None:
        """
        PROD-Modus: Prüft Rechte und setzt den Eintrag.

        Raises:
            HostsManagerError: Bei fehlenden Rechten oder I/O-Fehler.
        """
        logger.info(
            "HostsManager: PROD-Modus — verwalte hosts-Eintrag "
            "'%s → %s' in '%s'.",
            self._hostname, self._target, self._hosts_path,
        )

        self._check_admin_rights()

        if self._entry_exists():
            logger.info(
                "HostsManager: hosts-Eintrag für '%s' bereits vorhanden — "
                "keine Änderung.",
                self._hostname,
            )
            return

        logger.info(
            "HostsManager: Füge hosts-Eintrag hinzu: '%s  %s  %s'.",
            self._target, self._hostname, _MARKER,
        )
        self._add_entry()
        self._entry_added_by_us = True
        logger.info("HostsManager: hosts-Eintrag erfolgreich gesetzt.")

    def _check_admin_rights(self) -> None:
        """
        Prüft ob der Prozess mit Administratorrechten läuft.
        Nur relevant im PROD/Windows-Modus.

        Raises:
            HostsManagerError: Wenn keine Administratorrechte vorhanden sind.
        """
        if self._is_windows:
            # Windows: ctypes.windll.shell32.IsUserAnAdmin()
            try:
                import ctypes
                is_admin: bool = bool(ctypes.windll.shell32.IsUserAnAdmin())
            except Exception as exc:
                raise HostsManagerError(
                    f"Administratorrechte konnten nicht geprüft werden: {exc}.\n"
                    f"Bitte den Server als Administrator starten."
                ) from exc
            if not is_admin:
                raise HostsManagerError(
                    "Der Server muss als Administrator gestartet werden, um den "
                    "hosts-Eintrag automatisch setzen zu können.\n"
                    f"Bitte 'Als Administrator ausführen' verwenden.\n"
                    f"Alternativ: hosts_management.enabled = false setzen und "
                    f"den Eintrag manuell in '{self._hosts_path}' eintragen:\n"
                    f"  {self._target}  {self._hostname}"
                )
        else:
            # Linux/PROD: euid == 0 (root) oder schreibbarer Zugriff
            if os.geteuid() != 0:
                raise HostsManagerError(
                    f"Root-Rechte erforderlich um '{self._hosts_path}' zu "
                    f"schreiben.\nAlternativ: hosts_management.enabled = false "
                    f"und Eintrag manuell setzen."
                )

    # ------------------------------------------------------------------
    # hosts-Datei-Operationen
    # ------------------------------------------------------------------

    def _entry_exists(self) -> bool:
        """
        Prüft ob ein aktiver (nicht auskommentierter) Eintrag für den
        Hostnamen in der hosts-Datei existiert — unabhängig ob von
        diesem Tool oder manuell gesetzt.

        Gibt False zurück wenn die Datei nicht gelesen werden kann —
        das ist kein harter Fehler im DEV-Modus.
        """
        try:
            content = self._hosts_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.debug(
                "HostsManager: hosts-Datei nicht lesbar ('%s'): %s",
                self._hosts_path, exc,
            )
            return False

        for line in content.splitlines():
            stripped = line.strip()
            # Auskommentierte Zeilen überspringen
            if stripped.startswith("#"):
                continue
            # Zeile enthält den Hostnamen und die Ziel-IP?
            parts = stripped.split()
            if len(parts) >= 2 and parts[0] == self._target and self._hostname in parts[1:]:
                return True
        return False

    def _add_entry(self) -> None:
        """
        Fügt den markierten hosts-Eintrag am Ende der hosts-Datei hinzu.

        Raises:
            HostsManagerError: Bei I/O-Fehlern.
        """
        new_line = f"{self._target}  {self._hostname}  {_MARKER}\n"
        try:
            # Sicherstellen dass die Datei mit einer Leerzeile endet
            # bevor wir unseren Eintrag anhängen — cosmetics, aber
            # verhindert dass unser Eintrag an eine bestehende Zeile
            # ohne abschließendes Newline angehängt wird.
            existing = self._hosts_path.read_text(encoding="utf-8", errors="replace")
            separator = "" if existing.endswith("\n") else "\n"
            with self._hosts_path.open("a", encoding="utf-8") as fh:
                fh.write(separator + new_line)
        except OSError as exc:
            raise HostsManagerError(
                f"hosts-Eintrag konnte nicht geschrieben werden "
                f"('{self._hosts_path}'): {exc}"
            ) from exc

    def _remove_entry(self) -> None:
        """
        Entfernt alle Zeilen aus der hosts-Datei, die mit _MARKER enden
        und den konfigurierten Hostnamen enthalten.

        Nur Zeilen, die von diesem Tool gesetzt wurden (Marker-Kommentar),
        werden entfernt. Manuell gesetzte Zeilen bleiben unangetastet.

        Raises:
            HostsManagerError: Bei I/O-Fehlern.
        """
        try:
            content = self._hosts_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise HostsManagerError(
                f"hosts-Datei nicht lesbar ('{self._hosts_path}'): {exc}"
            ) from exc

        new_lines: list[str] = []
        removed = 0
        for line in content.splitlines(keepends=True):
            # Entfernen wenn: Marker vorhanden UND Hostname in Zeile
            stripped = line.strip()
            if _MARKER in stripped and self._hostname in stripped:
                removed += 1
                logger.debug("HostsManager: Entferne Zeile: %r", stripped)
                continue
            new_lines.append(line)

        if removed == 0:
            # Eintrag bereits weg — kein Fehler, nur Info
            logger.info(
                "HostsManager: Kein markierter Eintrag zum Entfernen gefunden."
            )
            return

        try:
            self._hosts_path.write_text("".join(new_lines), encoding="utf-8")
            logger.info(
                "HostsManager: %d Eintrag/Einträge aus hosts-Datei entfernt.", removed
            )
        except OSError as exc:
            raise HostsManagerError(
                f"hosts-Datei konnte nicht geschrieben werden "
                f"('{self._hosts_path}'): {exc}"
            ) from exc
