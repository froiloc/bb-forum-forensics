#!/usr/bin/env python3
# =============================================================================
# core/browser_launcher.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Plattformübergreifendes (Windows + Linux) Auffinden und Starten eines
#   Webbrowsers, der die Ermittler-Oberfläche öffnet.
#
#   Hintergrund (Beleg: Projektgespräch 2026-06-24):
#   Bisher startete start.bat den Browser FEST mit hartkodiertem Pfad
#   ('..\\GoogleChromePortable64\\GoogleChromePortable.exe') und VOR dem
#   Server. Für die Auslieferung einer Light-Version an andere Behörden ist
#   das zu unflexibel: Der Browser-Pfad ist dort unbekannt, und bei der neuen
#   Auto-Port-Logik kennt das Start-Skript den tatsächlichen Port nicht mehr.
#
#   Lösung:
#   - Der Server bestimmt selbst den (ggf. automatisch gewählten) Port.
#   - NACHDEM der Socket gebunden ist, öffnet der Server selbst den Browser
#     auf der korrekten URL (http://<host>:<port>/). Dadurch ist garantiert,
#     dass der Server zuerst läuft und der Browser die richtige Seite trifft.
#
# Auflösungsreihenfolge des Browser-Programms (erster Treffer gewinnt):
#   1. config.yaml -> browser.path   (explizit konfigurierter Pfad)
#   2. Portabler Browser relativ zum Projektroot (Windows-Deployment-Layout)
#   3. OS-spezifische Auto-Erkennung über shutil.which()
#   4. Fallback: Python-Stdlib webbrowser.open() (System-Standardbrowser)
#
# Forensische Relevanz:
#   Das Öffnen des Browsers ist eine reine Komfort-/Bedienfunktion und berührt
#   KEINE Beweisdaten. Schlägt der Start fehl, ist das nicht-fatal: Der Server
#   läuft weiter, der Ermittler kann die URL manuell aufrufen. Es wird daher
#   nie ein harter Abbruch ausgelöst — lediglich eine Warnung geloggt.
#
# Abhängigkeiten: shutil, subprocess, webbrowser, platform, os, sys (Stdlib)
# Version: v0.6.299 · Build: 299 · 2026-06-24
# Beleg: Projektgespräch 2026-06-24 (Light-Version / Auto-Port / Browser-Start)
# =============================================================================

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)


# -----------------------------------------------------------------------------
# Kandidatenlisten je Betriebssystem.
# Reihenfolge = Präferenz. Reine Programmnamen werden über shutil.which()
# im PATH gesucht; absolute Pfade werden direkt auf Existenz geprüft.
# -----------------------------------------------------------------------------
_LINUX_CANDIDATES = [
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "brave-browser",
    "microsoft-edge",
    "firefox-esr",
    "firefox",
]

# Auf Windows liegen Browser oft NICHT im PATH. Daher zusätzlich zu den
# which()-Namen auch typische Installationspfade prüfen.
_WINDOWS_CANDIDATES_WHICH = [
    "chrome",
    "msedge",
    "brave",
    "firefox",
]
_WINDOWS_CANDIDATES_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Mozilla Firefox\firefox.exe",
    r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
]

# Portables Deployment-Layout (relativ zum Projektroot) — entspricht dem,
# was die alte start.bat verwendet hat. Wird geprüft, falls vorhanden.
# Beleg: alte start.bat, Build 298.
_PORTABLE_RELATIVE = [
    Path("..") / "GoogleChromePortable64" / "GoogleChromePortable.exe",
    Path("..") / "FirefoxPortable" / "FirefoxPortable.exe",
]


class BrowserLauncher:
    """
    Findet und startet einen Webbrowser für die Ermittler-Oberfläche.

    Die Klasse ist bewusst defensiv: Jeder Fehler beim Browser-Start ist
    nicht-fatal (Komfortfunktion, keine Beweisrelevanz). Der Server-Betrieb
    hängt nicht vom Erfolg dieser Klasse ab.

    Verwendung:
        launcher = BrowserLauncher(config, project_root)
        launcher.open("http://127.0.0.2:8080/")
    """

    def __init__(self, config=None, project_root: Optional[Path] = None) -> None:
        """
        Args:
            config:       ConfigLoader-Instanz (optional). Es wird der
                          Schlüssel 'browser.path' ausgewertet, falls gesetzt.
            project_root: Wurzelverzeichnis des Projekts (für die Auflösung
                          portabler Relativpfade). Default: Elternverzeichnis
                          dieses Moduls.
        """
        self._config = config
        self._project_root = (
            project_root.resolve()
            if project_root is not None
            else Path(__file__).resolve().parent.parent
        )

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------
    def open(self, url: str) -> bool:
        """
        Öffnet die übergebene URL in einem verfügbaren Browser.

        Args:
            url: Vollständige URL, z.B. 'http://127.0.0.2:8080/'.

        Returns:
            True, wenn ein Browser-Prozess gestartet werden konnte
            (bzw. webbrowser.open() True meldet), sonst False.
            Der Rückgabewert ist informativ — der Aufrufer löst bei False
            KEINEN Abbruch aus.
        """
        browser_path = self._resolve_browser()

        if browser_path is not None:
            return self._launch_explicit(browser_path, url)

        # Letzter Ausweg: System-Standardbrowser über die Stdlib.
        logger.info(
            "BrowserLauncher: kein konkreter Browser gefunden — "
            "versuche System-Standardbrowser (webbrowser.open)."
        )
        try:
            ok = webbrowser.open(url, new=2)  # new=2: möglichst neuer Tab
            if ok:
                logger.info("BrowserLauncher: Standardbrowser geöffnet auf '%s'.", url)
            else:
                logger.warning(
                    "BrowserLauncher: webbrowser.open() meldete Fehlschlag. "
                    "Bitte URL manuell aufrufen: %s", url
                )
            return ok
        except Exception as exc:  # pragma: no cover — sehr selten
            logger.warning(
                "BrowserLauncher: Standardbrowser konnte nicht geöffnet werden: %s. "
                "Bitte URL manuell aufrufen: %s", exc, url
            )
            return False

    # ------------------------------------------------------------------
    # Auflösung des Browser-Programms
    # ------------------------------------------------------------------
    def _resolve_browser(self) -> Optional[str]:
        """
        Ermittelt den Pfad zum zu startenden Browser nach der dokumentierten
        Reihenfolge. Gibt None zurück, wenn nichts Konkretes gefunden wurde
        (dann greift der webbrowser-Fallback in open()).
        """
        # 1) Explizit konfigurierter Pfad (config.yaml -> browser.path)
        configured = self._configured_path()
        if configured:
            if Path(configured).exists():
                logger.info("BrowserLauncher: nutze konfigurierten Browser '%s'.", configured)
                return configured
            logger.warning(
                "BrowserLauncher: browser.path '%s' existiert nicht — "
                "versuche Auto-Erkennung.", configured
            )

        # 2) Portabler Browser relativ zum Projektroot
        for rel in _PORTABLE_RELATIVE:
            candidate = (self._project_root / rel).resolve()
            if candidate.exists():
                logger.info("BrowserLauncher: nutze portablen Browser '%s'.", candidate)
                return str(candidate)

        # 3) OS-spezifische Auto-Erkennung
        detected = self._detect_by_os()
        if detected:
            logger.info("BrowserLauncher: erkannter Browser '%s'.", detected)
            return detected

        return None

    def _configured_path(self) -> Optional[str]:
        """Liest browser.path aus der Config (falls vorhanden)."""
        if self._config is None:
            return None
        try:
            value = self._config.get("browser.path", None)
        except Exception:
            return None
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    def _detect_by_os(self) -> Optional[str]:
        """
        Sucht einen installierten Browser anhand OS-spezifischer Kandidaten.

        Linux:   shutil.which() über bekannte Programmnamen.
                 (Entspricht der bisherigen Logik
                  'which chromium-browser || which firefox || which google-chrome',
                  jedoch erweitert und in Python.)
        Windows: shutil.which() + Prüfung typischer Installationspfade.
        """
        system = platform.system().lower()

        if system == "linux":
            for name in _LINUX_CANDIDATES:
                found = shutil.which(name)
                if found:
                    return found
            return None

        if system == "windows":
            for name in _WINDOWS_CANDIDATES_WHICH:
                found = shutil.which(name)
                if found:
                    return found
            for path in _WINDOWS_CANDIDATES_PATHS:
                if Path(path).exists():
                    return path
            return None

        # Andere Systeme (z.B. macOS) — nicht Teil des Zielbetriebs.
        logger.info(
            "BrowserLauncher: Auto-Erkennung für OS '%s' nicht implementiert — "
            "nutze später webbrowser-Fallback.", system
        )
        return None

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------
    def _launch_explicit(self, browser_path: str, url: str) -> bool:
        """
        Startet einen konkreten Browser als nicht-blockierenden Hintergrund-
        prozess. Der Server-Prozess läuft sofort weiter (serve_forever).

        Args:
            browser_path: Pfad/Name des Browser-Programms.
            url:          Aufzurufende URL.

        Returns:
            True bei erfolgreichem Prozessstart, sonst False.
        """
        try:
            # Detached starten, damit der Browser nicht an den Server-Prozess
            # gebunden ist und dessen stdout/stderr nicht blockiert.
            # Windows: DETACHED_PROCESS, damit kein Konsolenfenster aufpoppt.
            kwargs = {}
            if platform.system().lower() == "windows":
                # 0x00000008 = DETACHED_PROCESS
                kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            else:
                # Vom Terminal lösen, damit Strg+C im Server den Browser nicht killt.
                kwargs["start_new_session"] = True

            subprocess.Popen(
                [browser_path, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **kwargs,
            )
            logger.info("BrowserLauncher: Browser '%s' gestartet auf '%s'.",
                        browser_path, url)
            return True
        except Exception as exc:
            logger.warning(
                "BrowserLauncher: Browser '%s' konnte nicht gestartet werden: %s. "
                "Versuche Standardbrowser …", browser_path, exc
            )
            # Fallback auf Stdlib
            try:
                return bool(webbrowser.open(url, new=2))
            except Exception as exc2:  # pragma: no cover
                logger.warning(
                    "BrowserLauncher: auch Standardbrowser fehlgeschlagen: %s. "
                    "Bitte URL manuell aufrufen: %s", exc2, url
                )
                return False
