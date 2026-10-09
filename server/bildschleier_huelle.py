# =============================================================================
# server/bildschleier_huelle.py
# IT-Forensisches Ermittlungswerkzeug — Bildschleier (Build 773)
# =============================================================================
# Zweck:
#   Schliesst den Weg, auf dem ein Bild am Schleier vorbei erscheint: den
#   DIREKTAUFRUF. Ein Klick auf einen Bildlink (BB-Code-Bilder sind in
#   <a href=… target="_blank"> gefasst, forum/html/include/parser.php
#   Z. 523-525), "Link in neuem Tab oeffnen", "Grafik in neuem Tab oeffnen"
#   oder das Ziehen eines Bildes in die Adresszeile laedt das Bild als EIGENES
#   Dokument — ohne Shell, ohne Stylesheet, unverschleiert (Bauplan §5.4,
#   Festlegung F8).
#
# ── WIE DER SERVER DEN DIREKTAUFRUF ERKENNT ─────────────────────────────────
#
#   Der Browser kennzeichnet jede Anfrage mit 'Sec-Fetch-Dest':
#     <img> in einer Seite laedt ein Bild     -> 'image'
#     Navigation (neuer Tab, Klick, Adresse)  -> 'document'
#   Chromium sendet den Kopf seit Version 80 (2020); PROD laeuft auf einem
#   Chromium vom August 2026 (Alex, 09.10.2026). Fehlt er, entscheidet
#   hilfsweise 'Accept': Navigationen fordern 'text/html' an, <img>-Anfragen
#   nicht.
#
# ── WAS DANN GELIEFERT WIRD ─────────────────────────────────────────────────
#
#   Statt der Bildbytes eine kleine HTML-Seite: <img src="dieselbe URL"> in
#   einem #forensic-viewport, <html class="aiw-image-veil"> und die
#   Grundregel. Diese Seite laedt das Bild IHRERSEITS mit
#   'Sec-Fetch-Dest: image' — und bekommt die unveraenderten Bytes. Es wird
#   nichts gerechnet; der Server entscheidet nur, OB er Bytes oder Huelle
#   schickt. Das Umschalten fuer normale Ermittler:innen bleibt damit
#   unberuehrt.
#
#   Die Huelle traegt 'Cache-Control: no-store'. Jede Bildantwort traegt
#   'Vary: Sec-Fetch-Dest, Accept', damit der Browser eine zwischengespeicherte
#   <img>-Antwort nicht fuer eine Navigation wiederverwendet
#   (forensic_api/fileasset.py liefert mit 'max-age=3600, immutable').
#   Ob Chromium das einhaelt, prueft PoC P3 in PROD.
#
# ── WAS DIE HUELLE NICHT KANN ───────────────────────────────────────────────
#
#   "Bild speichern unter", Kopieren und die Entwicklerwerkzeuge liefern
#   weiterhin das Original. Das ist gewollt (Alex, 09.10.2026): der Schleier
#   ist optischer Selbstschutz, keine Zugangssperre.
#
# Version: v0.8.773 · Build: 773 · 2026-10-09
# =============================================================================

from __future__ import annotations

import html
from typing import Any, Mapping, Optional

from core.bildschleier_css import HTML_KLASSE

#: Der Kopf, an dem alle Bildantworten unterscheidbar werden.
VARY = "Sec-Fetch-Dest, Accept"


def _kopf(headers: Any, name: str) -> Optional[str]:
    if headers is None:
        return None
    try:
        wert = headers.get(name)
    except Exception:                                   # noqa: BLE001
        return None
    return str(wert) if wert is not None else None


class BildschleierHuelle:
    """Erkennt Direktaufrufe und baut die verschleiernde HTML-Huelle."""

    @staticmethod
    def ist_dokumentanfrage(headers: Optional[Mapping[str, str]]) -> bool:
        dest = _kopf(headers, "Sec-Fetch-Dest")
        if dest is not None and dest.strip():
            return dest.strip().lower() in ("document", "iframe", "frame",
                                            "embed", "object")
        accept = _kopf(headers, "Accept") or ""
        return "text/html" in accept.lower()

    @staticmethod
    def ist_bild(mime: Optional[str]) -> bool:
        return bool(mime) and mime.split(";")[0].strip().lower().startswith("image/")

    @staticmethod
    def html(bild_url: str) -> bytes:
        """Die Huelle fuer 'bild_url' (Pfad + Query der Anfrage)."""
        quelle = html.escape(bild_url, quote=True)
        seite = (
            "<!DOCTYPE html>\n"
            '<html class="%s">\n<head>\n<meta charset="utf-8">\n'
            '<link rel="stylesheet" href="/_forensic/image-veil.css">\n'
            "<title>Bild (verschleiert)</title>\n"
            "<style>body{margin:0;background:#f4f4f4;font:14px sans-serif;"
            "color:#555}p{margin:12px}#forensic-viewport{padding:12px}"
            "</style>\n</head>\n<body>\n"
            "<p>Bildschleier aktiv — das Bild wird verschleiert angezeigt.</p>\n"
            '<div id="forensic-viewport"><img src="%s" alt=""></div>\n'
            "</body>\n</html>\n" % (HTML_KLASSE, quelle))
        return seite.encode("utf-8")
