# =============================================================================
# report_render/placeholder_resolver.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Berichts-Ausgabe
# =============================================================================
# Zweck:
#   Serverseitige Aufloesung der Berichts-Platzhalter {{a:}} / {{m:}} / {{o:}}.
#   PARITAETS-ANGELPUNKT der Ausgabe (Bauplan Build 397 §6): weicht die
#   serverseitige Aufloesung von der Client-Aufloesung ab, weicht die Akte vom
#   Bildschirm des Ermittlers ab — forensisch fatal.
#
#   1:1-Portierung der maßgeblichen Client-Wahrheit userinfo/placeholder_chips.js
#   (Belegstellen in den Kommentaren):
#     _CHIP_RE (placeholder_chips.js:73), _normalizeType (:80),
#     _renderChip a/m/o (:180-256), _esc (:90),
#     Text-Segment ohne Re-Escaping (:166-171, Bugfix 131).
#
#   Build 402 — NEU: NEUTRALER SEGMENTSTROM als gemeinsamer Kern.
#     _segments() zerlegt den Text EINMAL in Text- und Wert-Segmente. Daraus
#     serialisieren zwei Modi:
#       mode="html"  (Build 399): Textsegmente Editor.js-HTML (nur \n -> <br>),
#                    Wert-Segmente escaped. BYTE-IDENTISCH zum bisherigen Verhalten.
#       mode="text"  (Build 402): Textsegmente als reiner Text (Tags entfernt,
#                    Entities aufgeloest, \n erhalten), Wert-Segmente roh.
#                    Wird von DocxRenderer/SqliteRenderer genutzt.
#     resolve_both() liefert beide Serialisierungen aus EINER Zerlegung — der
#     {{a:}}-DB-Zugriff (ueber resolve_auto) faellt so nur einmal an.
#
#   Serverunabhaengig: kein http, kein DB-Zugriff. Der {{a:}}-Wert wird ueber die
#   injizierte Funktion resolve_auto(name) -> Optional[str] beschafft.
#
# Grundregeln: GR6 (Intention kommentiert), GR9 (syntaxgeprueft).
# Version: v0.7.402 · Build: 402 · 2026-07-14
# =============================================================================

from __future__ import annotations

import html as _htmllib
import re
from typing import Callable, Optional

from report_render.report_document import (
    DocWarning,
    WARN_UNRESOLVED_PLACEHOLDER,
    WARN_UNKNOWN_PLACEHOLDER,
)

# Regex — ZEICHENGLEICH zu userinfo/placeholder_chips.js:73 (_CHIP_RE).
# Gruppen: 1=Typ, 2=name, 3=default, 4=description, 5=b64regex.
_CHIP_RE = re.compile(
    r"\{\{(a|auto|m|mandatory|o|optional):([A-Za-z0-9._-]+)"
    r"(?:\|([^|}\n]*))?(?:\|([^|}\n]*))?(?:\|([^|}\n]*))?\}\}"
)

#: Erkennung *stehen gebliebener* {{...}} (R2: unbekannter Platzhalter).
_ANY_BRACES_RE = re.compile(r"\{\{[^{}]*\}\}")

#: HTML-Tag-Entfernung fuer den Text-Modus (DOCX/SQLite).
_TAG_RE = re.compile(r"<[^>]+>")


def _normalize_type(raw: str) -> str:
    """a/auto->'a', m/mandatory->'m', o/optional->'o' (placeholder_chips.js:80)."""
    if raw in ("a", "auto"):
        return "a"
    if raw in ("m", "mandatory"):
        return "m"
    if raw in ("o", "optional"):
        return "o"
    return raw


def _esc(s: str) -> str:
    """HTML-Escaping IDENTISCH zu placeholder_chips.js:90 (& < > ")."""
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _to_plain(seg: str) -> str:
    """Textsegment (Editor.js-HTML) -> reiner Text fuer DOCX/SQLite.

    <br> wird zu \\n, uebrige Tags werden entfernt, HTML-Entities werden
    aufgeloest (&amp; -> &). \\n bleibt erhalten (keine <br>-Ersetzung).
    """
    if not seg:
        return ""
    tmp = seg.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    tmp = _TAG_RE.sub("", tmp)
    return _htmllib.unescape(tmp)


class PlaceholderResolver:
    """Loest Platzhalter in Berichtstexten auf — deckungsgleich zum Client.

    resolve_auto(name) -> Optional[str]:
        Wert eines {{a:name}} oder None (keine Query-Def / Fehler).
        "" = Query lief, lieferte nichts. Der Aufrufer kapselt Cache und SQL.
    """

    def __init__(self, resolve_auto: Optional[Callable[[str], Optional[str]]] = None) -> None:
        self._resolve_auto = resolve_auto
        self._auto_cache: dict[str, Optional[str]] = {}

    # ------------------------------------------------------------------
    # Oeffentliche API
    # ------------------------------------------------------------------
    def resolve(
        self,
        text: str,
        values: Optional[dict] = None,
        block_id: Optional[str] = None,
        mode: str = "html",
    ) -> tuple[str, list[DocWarning]]:
        """Loest 'text' in EINEM Modus auf. mode in {'html','text'}."""
        segs, warns = self._segments(text or "", values or {}, block_id)
        if mode == "html":
            return self._serialize_html(segs), warns
        if mode == "text":
            return self._serialize_text(segs), warns
        raise NotImplementedError(
            f"PlaceholderResolver: mode={mode!r} unbekannt (nur 'html'|'text')."
        )

    def resolve_both(
        self,
        text: str,
        values: Optional[dict] = None,
        block_id: Optional[str] = None,
    ) -> tuple[str, str, list[DocWarning]]:
        """Liefert (html, text, warnings) aus EINER Zerlegung — {{a:}} nur 1x aufgeloest."""
        segs, warns = self._segments(text or "", values or {}, block_id)
        return self._serialize_html(segs), self._serialize_text(segs), warns

    # ------------------------------------------------------------------
    # Neutraler Segmentstrom
    # ------------------------------------------------------------------
    def _segments(self, text: str, values: dict, block_id: Optional[str]):
        """Zerlegt 'text' in [('text', str) | ('value', str)] + Warnungen.

        Ein 'value'-Segment traegt den ROHEN Anzeigewert (unescaped); das
        Escaping erfolgt erst bei der HTML-Serialisierung.
        """
        segs: list[tuple[str, str]] = []
        warns: list[DocWarning] = []
        last_end = 0

        for m in _CHIP_RE.finditer(text):
            if m.start() > last_end:
                piece = text[last_end:m.start()]
                self._scan_stray(piece, warns, block_id)
                segs.append(("text", piece))

            chip_type = _normalize_type(m.group(1))
            name      = m.group(2)
            default   = m.group(3) or ""
            desc      = m.group(4) or ""
            display, warn = self._chip_display(chip_type, name, default, desc, values, block_id)
            if warn is not None:
                warns.append(warn)
            segs.append(("value", display))
            last_end = m.end()

        if last_end < len(text):
            piece = text[last_end:]
            self._scan_stray(piece, warns, block_id)
            segs.append(("text", piece))

        return segs, warns

    def _scan_stray(self, piece: str, warns: list[DocWarning], block_id: Optional[str]) -> None:
        """Stehen gebliebene {{...}} in die Warnliste (R2); Text bleibt unveraendert."""
        for stray in _ANY_BRACES_RE.finditer(piece):
            warns.append(DocWarning(
                kind=WARN_UNKNOWN_PLACEHOLDER, detail=stray.group(0), block_id=block_id,
            ))

    def _resolve_auto_cached(self, name: str) -> Optional[str]:
        if name in self._auto_cache:
            return self._auto_cache[name]
        val = self._resolve_auto(name) if self._resolve_auto else None
        self._auto_cache[name] = val
        return val

    def _chip_display(self, chip_type, name, default, desc, values, block_id):
        """(raw_display, DocWarning|None) — Regeln 1:1 aus placeholder_chips.js:180-256."""
        if chip_type == "a":
            resolved = self._resolve_auto_cached(name)
            display = resolved if resolved is not None else default
            if display == "" or display is None:
                display = name
            if resolved is None or resolved == "":
                return display, DocWarning(WARN_UNRESOLVED_PLACEHOLDER, f"{{{{a:{name}}}}}", block_id)
            return display, None

        if chip_type == "m":
            val = values.get(name)
            if val is not None and str(val).strip() != "":
                return str(val), None
            return (desc or name) + " *", DocWarning(
                WARN_UNRESOLVED_PLACEHOLDER, f"{{{{m:{name}}}}} (Pflichtfeld nicht ausgefuellt)", block_id)

        if chip_type == "o":
            val = values.get(name)
            if val is not None and str(val).strip() != "":
                return str(val), None
            return (desc or name), None   # optional leer -> keine Warnung

        return name, None

    # ------------------------------------------------------------------
    # Serialisierung
    # ------------------------------------------------------------------
    def _serialize_html(self, segs) -> str:
        """Textsegmente: nur \\n -> <br> (Editor.js-HTML, kein Re-Escape).
        Wert-Segmente: escaped. -> BYTE-IDENTISCH zu Build 399."""
        out = []
        for kind, content in segs:
            if kind == "text":
                out.append(content.replace("\n", "<br>"))
            else:
                out.append(_esc(content))
        return "".join(out)

    def _serialize_text(self, segs) -> str:
        """Textsegmente: reiner Text (Tags weg, Entities aufgeloest).
        Wert-Segmente: roh."""
        out = []
        for kind, content in segs:
            out.append(_to_plain(content) if kind == "text" else content)
        return "".join(out)
