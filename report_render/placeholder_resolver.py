# =============================================================================
# report_render/placeholder_resolver.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Berichts-Ausgabe
# =============================================================================
# Zweck:
#   Serverseitige Aufloesung der Berichts-Platzhalter {{a:}} / {{m:}} / {{o:}}.
#   Dies ist der PARITAETS-ANGELPUNKT der Ausgabe (Bauplan Build 397 §6):
#
#     "Weicht die serverseitige Aufloesung von der Client-Aufloesung ab, weicht
#      das Dokument, das zur Staatsanwaltschaft geht, von dem ab, was der
#      Ermittler auf dem Bildschirm gesehen und verantwortet hat.
#      Das waere forensisch fatal."
#
#   Deshalb ist dieses Modul eine 1:1-Portierung der maßgeblichen Client-Wahrheit
#   userinfo/placeholder_chips.js — MIT BELEGSTELLEN in den Kommentaren:
#     - _CHIP_RE               (placeholder_chips.js:73)  -> identische Regex
#     - _normalizeType         (placeholder_chips.js:80)  -> a/m/o
#     - _renderChip a/m/o       (placeholder_chips.js:180-256) -> Anzeigewert-Regeln
#     - _esc                   (placeholder_chips.js:90)  -> & < > "
#     - Text-Segment ohne Re-Escaping (placeholder_chips.js:166-171, Bugfix 131)
#
#   UNTERSCHIED zur Chip-Darstellung im Editor: fuer die FERTIGE Akte werden
#   KEINE <span class="ph-chip">-Wrapper erzeugt (das sind Editor-Bedienelemente).
#   Der aufgeloeste WERT steht direkt im Text. Die Auswahl des Anzeigewerts ist
#   jedoch exakt dieselbe wie im Client (siehe Regeln unten) -> Parität.
#
#   Befund (Feinabnahme Build 399 §0, gemessen): Der bereits existierende
#   Server-Resolver forensic_api/placeholders.py kennt NUR {{a:}} mit zwei
#   Feldern (placeholders.py:58). Er ist damit fuer die Ausgabe unzureichend.
#   Dieses Modul ist der vollstaendige, gemeinsame Kern. Die De-Duplizierung von
#   placeholders.py gegen diesen Kern ist als Restpunkt fuer Build 402 vermerkt
#   (NICHT still: build.json 399).
#
# Modus:
#   resolve(..., mode="html") — Build 399 (HTML-Ausgabe). Textsegmente sind
#   Editor.js-HTML und werden NICHT erneut escaped (nur \n -> <br>); Chip-WERTE
#   werden escaped. Andere Modi (z.B. reiner Text fuer DOCX/PDF) sind bewusst
#   noch NICHT implementiert und werfen NotImplementedError (kein stiller
#   Fehlmodus). Beleg: Feinabnahme Build 399 §3, GR1.
#
# Serverunabhaengig: kein http, kein DB-Zugriff. Der {{a:}}-Wert wird ueber die
# injizierte Funktion resolve_auto(name) -> Optional[str] beschafft (der Aufrufer
# kapselt Cache/Query). Dadurch bleibt das Modul rein und deterministisch testbar.
#
# Grundregeln: GR6 (Intention kommentiert), GR9 (syntaxgeprueft).
# Version: v0.7.399 · Build: 399 · 2026-07-13
# =============================================================================

from __future__ import annotations

import re
from typing import Callable, Optional

from report_render.report_document import (
    DocWarning,
    WARN_UNRESOLVED_PLACEHOLDER,
    WARN_UNKNOWN_PLACEHOLDER,
)

# -----------------------------------------------------------------------------
# Regex — ZEICHENGLEICH zu userinfo/placeholder_chips.js:73 (_CHIP_RE).
# Gruppen: 1=Typ (a|auto|m|mandatory|o|optional), 2=name,
#          3=default (optional), 4=description (optional), 5=b64regex (optional).
# Das negierte [^|}\n] verhindert, dass '|' innerhalb eines Feldes matcht.
# WICHTIG: Bei jeder Aenderung an placeholder_chips.js MUSS diese Regex
# nachgezogen werden — der Paritaetstest (tests/test_report_render.py) faellt
# sonst absichtlich durch (kein stilles Auseinanderlaufen).
# -----------------------------------------------------------------------------
_CHIP_RE = re.compile(
    r"\{\{(a|auto|m|mandatory|o|optional):([A-Za-z0-9._-]+)"
    r"(?:\|([^|}\n]*))?(?:\|([^|}\n]*))?(?:\|([^|}\n]*))?\}\}"
)

#: Muster fuer die Erkennung *stehen gebliebener* {{...}}, die dem Chip-Muster
#: NICHT entsprechen (R2: "unbekannter Platzhalter"). Sie werden fuer die
#: Warnliste erfasst, der Text selbst aber unveraendert gelassen (Parität:
#: der Client zeigt sie ebenfalls als Rohtext).
_ANY_BRACES_RE = re.compile(r"\{\{[^{}]*\}\}")


def _normalize_type(raw: str) -> str:
    """a/auto -> 'a', m/mandatory -> 'm', o/optional -> 'o'.
    Portierung von placeholder_chips.js:80 (_normalizeType).
    """
    if raw in ("a", "auto"):
        return "a"
    if raw in ("m", "mandatory"):
        return "m"
    if raw in ("o", "optional"):
        return "o"
    return raw  # kann bei dieser Regex nicht auftreten; defensiv belassen


def _esc(s: str) -> str:
    """HTML-Escaping IDENTISCH zu placeholder_chips.js:90 (_esc): & < > "
    (das einfache Anfuehrungszeichen wird bewusst NICHT ersetzt — Parität).
    """
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


class PlaceholderResolver:
    """Loest Platzhalter in Berichtstexten auf — deckungsgleich zum Client.

    Verwendung:
        resolver = PlaceholderResolver(resolve_auto=my_auto_fn)
        html_fragment, warnings = resolver.resolve(text, values, block_id="b1")

    resolve_auto(name) -> Optional[str]:
        Liefert den automatisch aufgeloesten Wert eines {{a:name}} oder None,
        wenn keine Query-Definition existiert bzw. die Query fehlschlaegt.
        Ein leerer String "" bedeutet: Query lief, lieferte aber nichts.
        (Der Aufrufer kapselt Cache und SQL — vgl. forensic_api/placeholders.py.)
        Wird KEINE Funktion uebergeben, gelten alle {{a:}} als nicht auflösbar.
    """

    def __init__(self, resolve_auto: Optional[Callable[[str], Optional[str]]] = None) -> None:
        self._resolve_auto = resolve_auto
        # Innerhalb einer Dokumenterzeugung wird derselbe {{a:name}} oft mehrfach
        # verwendet. Wir merken uns die Aufloesung, um doppelte Queries zu sparen
        # und Konsistenz innerhalb des Dokuments zu garantieren.
        self._auto_cache: dict[str, Optional[str]] = {}

    # ------------------------------------------------------------------
    def resolve(
        self,
        text: str,
        values: Optional[dict] = None,
        block_id: Optional[str] = None,
        mode: str = "html",
    ) -> tuple[str, list[DocWarning]]:
        """Loest alle Platzhalter in 'text' auf.

        Returns:
            (fragment, warnings)
            fragment  — HTML-Fragment (mode="html"): Editor.js-Textsegmente
                        unveraendert (nur \\n -> <br>), Chip-WERTE escaped.
            warnings  — Liste von DocWarning (R2).
        """
        if mode != "html":
            # Kein stiller Fehlmodus: reiner Text (DOCX/PDF) folgt in Build 402/404.
            raise NotImplementedError(
                f"PlaceholderResolver: mode={mode!r} noch nicht implementiert "
                f"(nur 'html' in Build 399). Beleg: Feinabnahme Build 399 §3."
            )

        values = values or {}
        warnings: list[DocWarning] = []
        if not text:
            return "", warnings

        out_parts: list[str] = []
        last_end = 0

        for m in _CHIP_RE.finditer(text):
            # Text VOR dem Chip: Editor.js-HTML, NICHT erneut escapen
            # (placeholder_chips.js:166-171, Bugfix Build 131). Nur \n -> <br>.
            if m.start() > last_end:
                out_parts.append(self._render_text_segment(text[last_end:m.start()], warnings, block_id))

            chip_type = _normalize_type(m.group(1))
            name      = m.group(2)
            default   = m.group(3) or ""
            desc      = m.group(4) or ""
            # b64regex (Gruppe 5) ist fuer die Ausgabe ohne Belang.

            out_parts.append(self._render_chip_value(chip_type, name, default, desc, values, warnings, block_id))
            last_end = m.end()

        # Rest-Text nach dem letzten Chip
        if last_end < len(text):
            out_parts.append(self._render_text_segment(text[last_end:], warnings, block_id))

        return "".join(out_parts), warnings

    # ------------------------------------------------------------------
    def _render_text_segment(self, seg: str, warnings: list[DocWarning], block_id: Optional[str]) -> str:
        """Ein Textsegment (Editor.js-HTML) -> unveraendert, nur \\n -> <br>.

        Zusaetzlich: stehen gebliebene {{...}}, die dem Chip-Muster NICHT
        entsprechen, werden als 'unbekannter Platzhalter' in die Warnliste
        aufgenommen (R2). Der Text selbst bleibt unveraendert (Parität: der
        Client zeigt sie ebenfalls als Rohtext) — die sichtbare Kennzeichnung
        erfolgt gesammelt im Abschnitt 'Hinweise zur Erzeugung'.
        Diese bewusste Abweichung von der woertlichen R2-Formulierung
        ("sichtbare Markierung im Text") zugunsten der staerkeren §6-Parität
        ist als Restpunkt fuer mc vermerkt (build.json 399).
        """
        for stray in _ANY_BRACES_RE.finditer(seg):
            warnings.append(DocWarning(
                kind=WARN_UNKNOWN_PLACEHOLDER,
                detail=stray.group(0),
                block_id=block_id,
            ))
        return seg.replace("\n", "<br>")

    # ------------------------------------------------------------------
    def _resolve_auto_cached(self, name: str) -> Optional[str]:
        """Auto-Aufloesung mit dokumentinternem Cache."""
        if name in self._auto_cache:
            return self._auto_cache[name]
        val = self._resolve_auto(name) if self._resolve_auto else None
        self._auto_cache[name] = val
        return val

    # ------------------------------------------------------------------
    def _render_chip_value(
        self,
        chip_type: str,
        name: str,
        default: str,
        desc: str,
        values: dict,
        warnings: list[DocWarning],
        block_id: Optional[str],
    ) -> str:
        """Liefert den escapten Anzeige-WERT eines Chips — Regeln 1:1 aus
        placeholder_chips.js:180-256 (_renderChip)."""

        # --- {{a:}} automatisch (placeholder_chips.js:193-201) ---
        if chip_type == "a":
            resolved = self._resolve_auto_cached(name)
            # Client: displayVal = (resolved ?? defaultVal) || name
            display = resolved if resolved is not None else default
            if display == "" or display is None:
                display = name
            # R2-Warnungen: nicht auflösbar (None) ODER Query lieferte nichts ("")
            if resolved is None or resolved == "":
                warnings.append(DocWarning(
                    kind=WARN_UNRESOLVED_PLACEHOLDER,
                    detail=f"{{{{a:{name}}}}}",
                    block_id=block_id,
                ))
            return _esc(display)

        # --- {{m:}} Pflichtfeld (placeholder_chips.js:203-218) ---
        if chip_type == "m":
            val = values.get(name)
            is_filled = val is not None and str(val).strip() != ""
            if is_filled:
                return _esc(str(val))
            # leer -> Client zeigt "(description||name) *". R2: Warnung (Pflichtfeld leer).
            warnings.append(DocWarning(
                kind=WARN_UNRESOLVED_PLACEHOLDER,
                detail=f"{{{{m:{name}}}}} (Pflichtfeld nicht ausgefuellt)",
                block_id=block_id,
            ))
            return _esc((desc or name) + " *")

        # --- {{o:}} optional (placeholder_chips.js:220-235) ---
        if chip_type == "o":
            val = values.get(name)
            is_filled = val is not None and str(val).strip() != ""
            if is_filled:
                return _esc(str(val))
            # leer -> Client zeigt "(description||name)". Optional -> KEINE Warnung.
            return _esc(desc or name)

        # Unerreichbar bei dieser Regex; defensiv: Rohname.
        return _esc(name)
