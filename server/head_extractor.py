# =============================================================================
# server/head_extractor.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Parst den <head>-Bereich eines HTML-BLOBs und extrahiert die Elemente,
#   die für den Shell-Wrapper benötigt werden. Alle anderen <head>-Elemente
#   werden verworfen.
#
# Extrahiert werden:
#   <title>              — Seitentitel für den Shell-<head>
#   <base href="...">    — Basis-URL für relative Pfade (hosts-Umlenkung)
#   <link rel="stylesheet" href="...">  — CSS-Einbindungen des Forums
#   <style>...</style>   — Inline-CSS-Blöcke (kommen gelegentlich vor)
#
# Aktiv entfernt (nicht weitergegeben):
#   <meta http-equiv="refresh">  — würde zu unerwünschten Weiterleitungen führen
#
# Ignoriert (kein Fehler, werden stillschweigend verworfen):
#   Alle anderen <head>-Elemente: externe JS-Einbindungen, Fonts, Favicons,
#   CSP-Meta-Tags, Viewport-Meta usw.
#   Begründung: Die gespeicherten Seiten sind statisch und kommen ohne
#   JavaScript aus. Externe Ressourcen sind in der Offline-Umgebung nicht
#   erreichbar.
#
# Parser:
#   html.parser aus der Python-Standardbibliothek — keine externe Abhängigkeit.
#   Wahl begründet: keine zusätzliche Abhängigkeit, für das vorliegende
#   statische HTML vollständig ausreichend.
#
# Zeichensatz:
#   Das Forum ist UTF-8-kodiert. Der Parser wird mit UTF-8-Strings aufgerufen.
#   Bytes-Eingabe wird vor dem Parsen mit UTF-8 dekodiert (errors='replace').
#
# Forensische Relevanz:
#   Der Extractor verändert den BLOB nicht. Er liest nur. Alle Änderungen
#   an der Darstellung geschehen im Shell-Wrapper, niemals im gespeicherten
#   BLOB selbst.
#
# Abhängigkeiten: html.parser — ausschließlich Stdlib
# Version: v0.1.0 · Build: 005 · 2026-04-10
# =============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ExtractedHead:
    """
    Ergebnisobjekt des HeadExtractor.

    Felder:
        title        — Inhalt des <title>-Elements oder None
        base_href    — Wert des href-Attributs von <base> oder None
        stylesheets  — Liste der href-Werte aller <link rel="stylesheet">
        inline_styles — Liste der Inhalte aller <style>-Blöcke
        refresh_removed — True wenn mindestens ein <meta http-equiv="refresh">
                          entfernt wurde (für forensische Protokollierung)
    """
    title:           Optional[str]       = None
    base_href:       Optional[str]       = None
    stylesheets:     list[str]           = field(default_factory=list)
    inline_styles:   list[str]           = field(default_factory=list)
    refresh_removed: bool                = False

    def to_html(self) -> str:
        """
        Gibt die extrahierten <head>-Elemente als HTML-Fragment zurück.
        Dieses Fragment wird in den Shell-<head> eingebettet.

        Die Reihenfolge ist semantisch korrekt:
        1. <base> muss vor allen relativen URLs stehen
        2. <title>
        3. <link rel="stylesheet"> (externe CSS)
        4. <style> (inline CSS)

        Returns:
            HTML-String der extrahierten Elemente (ohne <head>-Tags).
        """
        parts: list[str] = []

        if self.base_href is not None:
            # base_href HTML-enkodieren um Attribut-Injection zu verhindern
            safe_href = self.base_href.replace('"', '&quot;')
            parts.append(f'<base href="{safe_href}">')

        if self.title is not None:
            # Titel HTML-enkodieren
            safe_title = (
                self.title
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            parts.append(f"<title>{safe_title}</title>")

        for href in self.stylesheets:
            safe_href = href.replace('"', '&quot;')
            parts.append(f'<link rel="stylesheet" href="{safe_href}">')

        for style_content in self.inline_styles:
            parts.append(f"<style>\n{style_content}\n</style>")

        return "\n".join(parts)


class _HeadParser(HTMLParser):
    """
    Interner html.parser-basierter Parser.
    Liest nur den <head>-Bereich — bricht nach </head> ab.

    Nicht für direkte Verwendung außerhalb dieses Moduls gedacht.
    Öffentliche Schnittstelle ist HeadExtractor.extract().
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_head: bool = False
        self._in_title: bool = False
        self._in_style: bool = False
        self._current_style: list[str] = []
        self._title_parts: list[str] = []
        self._done: bool = False          # True nach </head>

        # Ergebnis-Container
        self.result = ExtractedHead()

    def handle_starttag(self, tag: str, attrs: list[tuple]) -> None:
        if self._done:
            return

        tag_lower = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        if tag_lower == "head":
            self._in_head = True
            return

        if not self._in_head:
            return

        if tag_lower == "title":
            self._in_title = True
            self._title_parts = []

        elif tag_lower == "base":
            href = attr_dict.get("href", "").strip()
            if href and self.result.base_href is None:
                # Nur das erste <base>-Element wird übernommen (HTML-Spezifikation)
                self.result.base_href = href

        elif tag_lower == "link":
            rel = attr_dict.get("rel", "").lower().strip()
            href = attr_dict.get("href", "").strip()
            if rel == "stylesheet" and href:
                self.result.stylesheets.append(href)

        elif tag_lower == "meta":
            http_equiv = attr_dict.get("http-equiv", "").lower().strip()
            if http_equiv == "refresh":
                # Aktiv entfernen: nicht in Ergebnis übernehmen, Flag setzen
                self.result.refresh_removed = True
                logger.debug(
                    "<meta http-equiv='refresh'> erkannt und entfernt "
                    "(verhindert ungewollte Weiterleitung)"
                )

        elif tag_lower == "style":
            self._in_style = True
            self._current_style = []

    def handle_endtag(self, tag: str) -> None:
        if self._done:
            return

        tag_lower = tag.lower()

        if tag_lower == "head":
            # Ende des <head>-Bereichs — alles danach ignorieren
            self._in_head = False
            self._done = True
            # Laufenden <title>-Inhalt abschließen falls kein </title> kam
            if self._in_title and self._title_parts:
                self.result.title = "".join(self._title_parts).strip()
                self._in_title = False
            return

        if not self._in_head:
            return

        if tag_lower == "title":
            self.result.title = "".join(self._title_parts).strip() or None
            self._in_title = False
            self._title_parts = []

        elif tag_lower == "style":
            content = "".join(self._current_style).strip()
            if content:
                self.result.inline_styles.append(content)
            self._in_style = False
            self._current_style = []

    def handle_data(self, data: str) -> None:
        if self._done or not self._in_head:
            return
        if self._in_title:
            self._title_parts.append(data)
        elif self._in_style:
            self._current_style.append(data)

    def error(self, message: str) -> None:
        # html.parser ruft error() bei schwerwiegenden Fehlern auf.
        # Wir protokollieren und fahren fort — robustes Parsen ist wichtiger
        # als strenge Fehlerbehandlung bei forensischen BLOBs.
        logger.warning("HTML-Parser-Fehler (nicht fatal): %s", message)


class HeadExtractor:
    """
    Extrahiert forensisch relevante <head>-Elemente aus einem HTML-BLOB.

    Verwendung:
        extractor = HeadExtractor()
        result = extractor.extract(html_bytes_or_str)
        print(result.title)
        print(result.to_html())   # Für Shell-<head>-Einbettung

    Die Instanz ist zustandslos und kann für mehrere BLOBs wiederverwendet
    werden. Jeder extract()-Aufruf erstellt intern einen neuen Parser.
    """

    def extract(self, html: bytes | str) -> ExtractedHead:
        """
        Parst den <head>-Bereich des HTML und gibt ein ExtractedHead zurück.

        Args:
            html: HTML-Inhalt als bytes (wird UTF-8 dekodiert) oder str.
                  bytes-Eingabe verwendet UTF-8 mit errors='replace' —
                  ungültige Bytes werden durch das Unicode-Ersatzzeichen (U+FFFD)
                  ersetzt und protokolliert.

        Returns:
            ExtractedHead mit allen extrahierten Elementen.
            Fehlende Elemente sind None bzw. leere Listen — kein Fehler.
        """
        if isinstance(html, bytes):
            html_str = html.decode("utf-8", errors="replace")
            if "\ufffd" in html_str:
                logger.warning(
                    "HTML-BLOB enthält ungültige UTF-8-Sequenzen — "
                    "ersetzt durch U+FFFD (Ersatzzeichen)"
                )
        else:
            html_str = html

        parser = _HeadParser()
        try:
            parser.feed(html_str)
        except Exception as exc:
            # html.parser kann bei sehr kaputtem HTML in seltenen Fällen
            # eine Exception werfen. Wir geben zurück, was bisher gesammelt wurde.
            logger.warning(
                "HTML-Parsing abgebrochen (unerwartete Ausnahme): %s — "
                "Teilergebnis wird verwendet", exc
            )

        result = parser.result
        logger.debug(
            "Head extrahiert: title=%r, base=%r, %d CSS, %d inline-style(s), "
            "refresh_removed=%s",
            result.title,
            result.base_href,
            len(result.stylesheets),
            len(result.inline_styles),
            result.refresh_removed,
        )
        return result
