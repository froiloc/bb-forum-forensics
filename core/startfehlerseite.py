# =============================================================================
# core/startfehlerseite.py
# IT-Forensisches Ermittlungswerkzeug — Fehlerseite bei verweigertem Start
# =============================================================================
# Zweck:
#   Schreibt eine eigenstaendige HTML-Seite, die erklaert, warum der Fall
#   nicht geoeffnet wurde und was jetzt zu tun ist. main.py oeffnet sie im
#   Browser, wenn der Start verweigert wird und --open-browser gesetzt ist.
#
# ── WARUM ES DAS BRAUCHT ────────────────────────────────────────────────────
#
#   Das Portal startet den Webserver eines Falls OHNE Konsole (stdout und
#   stderr nach DEVNULL, management/cases/case_launcher.py). Ein verweigerter
#   Start war fuer die Ermittlerin bzw. den Ermittler bisher unsichtbar: es
#   ging einfach kein Fenster auf. Festlegung Alex 14.10.2026: "Wenn das
#   fehlschlaegt, dann oeffnest du die Hilfe dazu."
#
# ── BAUART ──────────────────────────────────────────────────────────────────
#
#   * Eine Datei, kein Server: der Webserver laeuft ja gerade NICHT. Die
#     Seite liegt im Protokollordner (logging.logfile), notfalls im
#     temporaeren Ordner, und wird als file:-Adresse geoeffnet.
#   * Kein JavaScript, kein externer Bezug (das Werkzeug ist statisch).
#   * Jeder variable Text wird mit html.escape maskiert — die Meldung kann
#     Pfade und SQLite-Texte enthalten.
#   * Der vollstaendige Meldungstext steht immer dabei; die Hilfeabsaetze
#     kommen aus der Ausnahme (EvidenceStartpruefungFehler.hilfe), sonst
#     allgemeine Hinweise.
#
# Version: v0.8.778 · Build: 778 · 2026-10-14
# =============================================================================

from __future__ import annotations

import html
import os
import tempfile
import time
from typing import Any, List, Optional

HILFE_ALLGEMEIN = [
    "Eine der Prüfungen beim Öffnen des Falls ist gescheitert. Damit nichts "
    "Falsches angezeigt oder gespeichert wird, wurde der Fall nicht geöffnet.",
    "Schließen Sie andere Fenster dieses Falls und versuchen Sie es erneut.",
    "Bleibt die Meldung, wenden Sie sich an die Leitung oder den Betrieb und "
    "geben Sie den Text unten sowie die Uhrzeit weiter.",
]


class Startfehlerseite:
    """Fehlerseite fuer einen verweigerten Start schreiben."""

    def __init__(self, verzeichnis: str) -> None:
        self.verzeichnis = os.path.abspath(verzeichnis)

    @classmethod
    def aus_konfiguration(cls, config: Any) -> "Startfehlerseite":
        """Protokollordner aus logging.logfile; sonst der temporaere Ordner."""
        try:
            logdatei = config.get("logging.logfile",
                                  "./logs/forensic_server.log")
            ordner = os.path.dirname(os.path.abspath(str(logdatei)))
        except Exception:                                   # noqa: BLE001
            ordner = tempfile.gettempdir()
        return cls(ordner)

    def html(self, fehler: BaseException, *, logdatei: Optional[str] = None,
             zeit: Optional[str] = None) -> str:
        """Die Seite als Text (rein, fuer Tests)."""
        e = html.escape
        zeit = zeit or time.strftime("%d.%m.%Y %H:%M:%S")
        hilfe: List[str] = list(getattr(fehler, "hilfe", None) or HILFE_ALLGEMEIN)
        melde = getattr(fehler, "melde_ergebnis", None)
        teile = [
            "<!DOCTYPE html>",
            '<html lang="de"><head><meta charset="utf-8">',
            "<title>Fall nicht geöffnet</title>",
            "<style>body{font-family:sans-serif;max-width:56em;margin:2em auto;"
            "padding:0 1em;line-height:1.45}h1{color:#c0392b}"
            "pre{background:#f4f4f4;padding:1em;white-space:pre-wrap;"
            "word-break:break-word}.klein{color:#555;font-size:.9em}</style>",
            "</head><body>",
            "<h1>Der Fall wurde nicht geöffnet</h1>",
            '<p class="klein">Zeitpunkt: %s</p>' % e(zeit),
            "<h2>Was Sie jetzt tun können</h2>",
            "<ul>%s</ul>" % "".join("<li>%s</li>" % e(h) for h in hilfe),
        ]
        if melde is not None and hasattr(melde, "klartext"):
            teile += ["<h2>Benachrichtigung der Leitung</h2>",
                      "<p>%s</p>" % e(melde.klartext())]
        teile += ["<h2>Meldung</h2>", "<pre>%s</pre>" % e(str(fehler))]
        if logdatei:
            teile.append('<p class="klein">Einzelheiten im Protokoll: %s</p>'
                         % e(str(logdatei)))
        teile.append("</body></html>")
        return "\n".join(teile) + "\n"

    @classmethod
    def anzeigen(cls, config: Any, fehler: BaseException, *,
                 project_root: Any = None, launcher: Any = None) -> Optional[str]:
        """
        Seite schreiben und im Browser oeffnen (main.py, Schritt 6, nur mit
        --open-browser). Gibt den Pfad zurueck; WIRFT NIE — ein Fehler hier
        darf die eigentliche Meldung nicht verdecken, er wird protokolliert.
        """
        from pathlib import Path
        from core.logger import get_logger
        log = get_logger(__name__)
        try:
            logdatei = str(config.get("logging.logfile",
                                      "./logs/forensic_server.log"))
            pfad = cls.aus_konfiguration(config).schreiben(fehler,
                                                          logdatei=logdatei)
            log.info("Fehlerseite: %s", pfad)
            if launcher is None:
                from core.browser_launcher import BrowserLauncher
                launcher = BrowserLauncher(config, project_root=project_root)
            launcher.open(Path(pfad).resolve().as_uri())
            return pfad
        except Exception as exc:                            # noqa: BLE001
            log.warning("Fehlerseite konnte nicht geöffnet werden: %s", exc)
            return None

    def schreiben(self, fehler: BaseException, *,
                  logdatei: Optional[str] = None) -> str:
        """Schreibt die Seite und gibt ihren Pfad zurueck. Ist der
        Protokollordner nicht beschreibbar, wird der temporaere Ordner
        genommen."""
        name = "startfehler_%s.html" % time.strftime("%Y%m%d_%H%M%S")
        text = self.html(fehler, logdatei=logdatei)
        for ordner in (self.verzeichnis, tempfile.gettempdir()):
            try:
                os.makedirs(ordner, exist_ok=True)
                pfad = os.path.join(ordner, name)
                with open(pfad, "w", encoding="utf-8") as fh:
                    fh.write(text)
                return pfad
            except OSError:
                continue
        raise OSError("Fehlerseite in keinem Ordner schreibbar (%s, %s)"
                      % (self.verzeichnis, tempfile.gettempdir()))
