# =============================================================================
# management/server/static_assets.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Sichere Auslieferung statischer Assets des Management-Servers (Cockpit-
#   Shell + management-lokale Vendor-Bibliotheken) aus einem festen Basis-
#   Verzeichnis. Reiner Lesepfad; keine DB, kein Schreibzugriff.
#   Beleg: Bauplan B7 v1.1 §11.2 ("/static/<f> -> cockpit.* + Vendor").
#
# Warum eine eigene, gekapselte Klasse (Grundregel 10):
#   Die Auslieferungslogik (Pfad-Normierung, Traversal-Abwehr, MIME-Zuordnung)
#   ist sicherheitskritisch und soll SEPARAT und pytest-testbar sein — nicht in
#   der Dispatch-Verzweigung der ManagementApp verstreut. So laesst sich die
#   Abwehr (../, fuehrendes /, Backslash, Ausbruch aus dem Basisverzeichnis)
#   gezielt pruefen.
#
# Sicherheitsentscheidungen (Beleg: forensic_api/static.handle_vendor_asset,
#   Build 084, gleiches Muster):
#   1) MIME-WHITELIST statt Blacklist: nur bekannte, harmlose Endungen werden
#      ausgeliefert. Alles andere -> 404 (nicht Teil des Cockpits).
#   2) DOPPELTE Traversal-Abwehr: (a) String-Pruefung ('..', fuehrendes '/',
#      Backslash) fuer schnelle, klare Ablehnung mit 400; (b) realpath-
#      Containment-Pruefung als Fangnetz gegen Symlinks/Normalisierungs-Tricks.
#   3) Kein stiller Fehlpfad (Grundregel 1): jeder Ablehnungsgrund liefert einen
#      eindeutigen Status (400 = boesartiger Pfad, 404 = nicht vorhanden/kein
#      erlaubter Typ) mit maschinenlesbarem JSON-Fehlerkoerper.
#
# Rueckgabe: (status, content_type, body_bytes)-Tripel. Bewusst KEIN Import der
#   ManagementApp.Response (vermeidet Zirkularimport); die App wickelt das
#   Tripel in ihre Response.
#
# Version: v0.7.347 · Build: 347 · 2026-07-10
# =============================================================================

import json
import logging
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

#: Erlaubte Datei-Endungen -> Content-Type. Whitelist (siehe Sicherheit 1).
_MIME: Dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".svg": "image/svg+xml; charset=utf-8",
}

#: Ergebnistyp: (HTTP-Status, Content-Type, Body als Bytes).
ServeResult = Tuple[int, str, bytes]


def _err(status: int, detail: str) -> ServeResult:
    """Einheitlicher JSON-Fehlerkoerper (kein stiller Fehlpfad)."""
    payload = {"error": "static", "detail": detail}
    return (status, "application/json; charset=utf-8",
            json.dumps(payload, ensure_ascii=False).encode("utf-8"))


class StaticAssets:
    """
    Liefert statische Dateien aus einem festen Basisverzeichnis aus.

    Der relative Pfad stammt aus der URL (Teil hinter '/static/'). Er wird
    gegen Traversal geprueft und muss innerhalb des Basisverzeichnisses
    aufloesen. Nur Endungen aus _MIME werden ausgeliefert.
    """

    def __init__(self, base_dir: Path) -> None:
        # Basisverzeichnis EINMAL aufloesen (realpath); alle Vergleiche danach
        # gegen diese kanonische Wurzel (Containment-Pruefung).
        self._base = Path(base_dir).resolve()

    # ------------------------------------------------------------------ serve
    def serve(self, rel: str) -> ServeResult:
        """
        Loest 'rel' (z.B. 'cockpit.js' oder 'vendor/tabulator/tabulator.min.js')
        gegen das Basisverzeichnis auf und liefert das (status, ctype, body)-
        Tripel. Reihenfolge der Pruefungen bewusst: erst die schnellen,
        eindeutigen String-Abwehren (400), dann Typ-Whitelist (404), dann das
        realpath-Fangnetz (400), zuletzt der Dateizugriff (404 bei fehlend).
        """
        # (a) String-Traversal-Abwehr — klare Ablehnung boesartiger Pfade.
        if (not rel) or (".." in rel) or rel.startswith("/") \
                or ("\\" in rel):
            logger.warning("StaticAssets: abgewiesener Pfad '%s'", rel)
            return _err(400, "Ungueltiger Pfad.")

        # (b) MIME-Whitelist: nur bekannte, harmlose Endungen.
        suffix = Path(rel).suffix.lower()
        ctype = _MIME.get(suffix)
        if ctype is None:
            logger.debug("StaticAssets: Endung nicht erlaubt: '%s'", rel)
            return _err(404, "Kein ausgelieferter Asset-Typ.")

        # (c) realpath-Containment als Fangnetz (Symlink/Normalisierung).
        candidate = (self._base / rel).resolve()
        try:
            candidate.relative_to(self._base)
        except ValueError:
            logger.warning(
                "StaticAssets: Ausbruch aus Basisverzeichnis: '%s'", rel)
            return _err(400, "Pfad ausserhalb des Asset-Verzeichnisses.")

        # (d) Dateizugriff.
        try:
            data = candidate.read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            logger.debug("StaticAssets: nicht gefunden: '%s'", rel)
            return _err(404, "Asset nicht gefunden.")

        logger.debug("StaticAssets: '%s' ausgeliefert (%d Bytes)",
                     rel, len(data))
        return (200, ctype, data)
