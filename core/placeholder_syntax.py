# =============================================================================
# core/placeholder_syntax.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Zweck:
#   SERVERSEITIGE Wahrheit ueber die Platzhalter-Syntax der Berichtsbausteine.
#
#   Bis Build 387 existierte diese Syntax NUR im Browser
#   (userinfo/placeholder_chips.js, _CHIP_RE). Der Server hat Modultexte
#   lediglich durchgereicht und {{a:...}} in forensic_api/placeholders.py mit
#   einer EIGENEN, engeren Regex aufgeloest. Damit konnte der Server nicht
#   pruefen, ob ein Pflichtfeld gefuellt und formal gueltig ist — die Pruefung
#   lag allein im Client und war damit umgehbar.
#
#   Build 388 fuehrt diese Klasse ein, damit die Einreichung eines Berichts
#   (submit_report) serverseitig gegen den Regel-Katalog geprueft werden kann.
#   Ein gerichtsverwertbares Dokument darf sich nicht auf eine Pruefung
#   verlassen, die im Browser des Ermittlers stattfindet.
#
# Syntax (identisch zu placeholder_chips.js:73 _CHIP_RE — MUSS synchron bleiben):
#   {{TYP:name|default|description|rule}}
#     Gruppe 1: TYP   -- a|auto  (automatisch)  m|mandatory (Pflicht)
#                        o|optional (optional)
#     Gruppe 2: name  -- Feld- bzw. Query-Kennung
#     Gruppe 3: default      (optional)
#     Gruppe 4: description  (optional)
#     Gruppe 5: rule         (optional) -- Base64-Regex (Alt-Form, bis B387)
#                                          ODER 'rule:<name>' (NEU ab B388):
#                                          Verweis in den zentralen Katalog
#                                          config.yaml -> validation.rules
#
# Blocktypen:
#   Platzhalter koennen in JEDEM Editor.js-Block stecken. Der Text liegt je
#   nach Blocktyp an unterschiedlicher Stelle:
#     paragraph/header/quote : block_data['text']       (String)
#     list                   : block_data['items']      (Liste von Strings)
#     table                  : block_data['content']    (2D-Liste von Strings)
#   iter_texts() kapselt genau diese Fallunterscheidung an EINER Stelle, damit
#   sie nicht ueber den Code verstreut wird (Bug-Historie Build 132-294).
#
# Beleg: Bauplan Build 388 §2, Projektgespraech 2026-07-12
# Version: v0.7.388 · Build: 388 · 2026-07-12
# =============================================================================

from __future__ import annotations

import re
from typing import Iterator, NamedTuple

# Prefix fuer den Verweis in den zentralen Regel-Katalog (config.yaml).
RULE_PREFIX = "rule:"


class PlaceholderField(NamedTuple):
    """Ein einzelner, im Baustein-Text gefundener Platzhalter."""
    type: str          # 'a' | 'm' | 'o' (normalisiert)
    name: str          # Feld-/Query-Kennung
    default: str       # Default-Wert (leer wenn nicht angegeben)
    description: str   # Hilfetext (leer wenn nicht angegeben)
    rule: str          # 5. Feld roh (leer wenn nicht angegeben)

    @property
    def rule_name(self) -> str:
        """
        Name der zentralen Validierungsregel, oder '' wenn keine referenziert
        wird. Die Alt-Form (Base64-Regex) liefert bewusst '' — sie wird
        weiterhin NUR im Client ausgewertet (Abwaertskompatibilitaet).
        """
        if self.rule.startswith(RULE_PREFIX):
            return self.rule[len(RULE_PREFIX):].strip()
        return ""


class PlaceholderSyntax:
    """
    Parser fuer die Platzhalter-Syntax der Berichtsbausteine.

    Reine Lesefunktionen — kein Zustand, keine Datenbank. Bewusst als Klasse
    mit Klassenmethoden (Grundregel 10: eine Klasse je Datei), damit die
    Syntax an genau einer Stelle definiert ist.
    """

    # Muss zeichengleich zu placeholder_chips.js:73 (_CHIP_RE) sein.
    # Beleg: userinfo/placeholder_chips.js:73
    PATTERN = re.compile(
        r"\{\{(a|auto|m|mandatory|o|optional):([A-Za-z0-9._-]+)"
        r"(?:\|([^|}\n]*))?"
        r"(?:\|([^|}\n]*))?"
        r"(?:\|([^|}\n]*))?\}\}"
    )

    _TYPE_MAP = {
        "a": "a", "auto": "a",
        "m": "m", "mandatory": "m",
        "o": "o", "optional": "o",
    }

    # ------------------------------------------------------------------
    # Textstellen eines Blocks
    # ------------------------------------------------------------------

    @classmethod
    def iter_texts(cls, block_data: dict) -> Iterator[str]:
        """
        Liefert alle Textstellen eines Editor.js-Blocks, in denen Platzhalter
        stehen koennen.

        GRUNDREGEL 1: Unbekannte Blocktypen werden NICHT still uebergangen.
        Wir greifen deshalb nicht auf eine Whitelist von Blocktypen zurueck,
        sondern werten jedes bekannte Textfeld aus, das vorhanden ist. Ein
        Blocktyp, der seinen Text anders ablegt, faellt so zwar durch — er
        wuerde aber auch im Client keine Chips rendern; die Wahrheit bleibt
        an dieser einen Stelle korrigierbar.

        BUILD 710 — ZWEI TEXTSTELLEN FEHLTEN, UND SIE FEHLTEN AUF BEIDEN
        SEITEN. Gemessen am 12.08.2026:

          Liste, VERSCHACHTELTER Eintrag (items[].items[]) .... nicht gesehen
          Zitat, QUELLENANGABE (caption) ..................... nicht gesehen

        Beides sind belegte Textstellen: klartextAus() in
        cockpit_baustein_eingabe.js geht rekursiv in Unterlisten und liest
        'caption'; editor/html_renderer.py:127-151 rendert 'caption' als
        <cite> in den Vermerk. Ein Platzhalter dort steht also im
        unterschriebenen Dokument - er wurde nur nie gefunden.

        WAS DAS GEKOSTET HAT: Diese Methode traegt ueber extract_from_block()
        die serverseitige Feldpruefung eines Vermerks
        (forensic_api/report.py:2063). Auf der Clientseite traegt ihr
        Gegenstueck den Ausfuell-Assistenten der Ermittler
        (userinfo/placeholder_wizard.js:241,636). Ein {{m:...}} an einer der
        beiden Stellen wurde dem Ermittler NIE zum Ausfuellen angeboten und
        serverseitig NIE geprueft - der Vermerk ging mit rohem
        Vorlagentext hinaus.

        DIE AENDERUNG WEITET DIE PRUEFUNG AUS. Ein Vermerk, der bisher
        durchging, kann jetzt einen Verstoss melden. Das ist die richtige
        Richtung - geprueft wird mehr, nie weniger -, aber es ist eine
        Verhaltensaenderung und keine reine Reparatur.

        Die Entsprechung im Client (placeholder_chips.js::mapBlockTexts) ist
        WORTGLEICH mitgezogen. Beide Seiten MUESSEN dieselben Textstellen
        sehen; laufen sie auseinander, prueft der Server Felder, die der
        Client nie angeboten hat.
        """
        if not isinstance(block_data, dict):
            return

        # paragraph / header / quote
        text = block_data.get("text")
        if isinstance(text, str):
            yield text

        # quote: die Quellenangabe (Build 710). Sie wird von
        # html_renderer.py als <cite> in den Vermerk gerendert und ist damit
        # vollwertiger Berichtsinhalt.
        caption = block_data.get("caption")
        if isinstance(caption, str):
            yield caption

        # list (Editor.js NestedList: items koennen Strings oder Dicts sein).
        # REKURSIV ab Build 710: NestedList schachtelt ueber item['items'].
        yield from cls._iter_list_items(block_data.get("items"))

        # table
        content = block_data.get("content")
        if isinstance(content, list):
            for row in content:
                if not isinstance(row, list):
                    continue
                for cell in row:
                    if isinstance(cell, str):
                        yield cell

    @classmethod
    def _iter_list_items(cls, items, _tiefe: int = 0) -> Iterator[str]:
        """
        Die Eintraege einer (moeglicherweise verschachtelten) Liste.

        TIEFENGRENZE: Editor.js schachtelt in der Bedienung nicht beliebig
        tief, aber block_data kommt aus einer Datenbank und ist damit nicht
        vertrauenswuerdig. Eine im Kreis zeigende Struktur (von Hand oder
        durch einen Fehler entstanden) wuerde diese Methode sonst nicht
        beenden - in einem Pfad, der beim SPEICHERN eines Vermerks laeuft.
        Die Grenze ist grosszuegig und wird in der Praxis nie erreicht.
        """
        if not isinstance(items, list) or _tiefe > 32:
            return
        for item in items:
            if isinstance(item, str):
                yield item
            elif isinstance(item, dict):
                inner = item.get("content")
                if isinstance(inner, str):
                    yield inner
                yield from cls._iter_list_items(item.get("items"), _tiefe + 1)

    # ------------------------------------------------------------------
    # Extraktion
    # ------------------------------------------------------------------

    @classmethod
    def extract(cls, text: str) -> list[PlaceholderField]:
        """Alle Platzhalter eines einzelnen Textes, in Fundreihenfolge."""
        if not text:
            return []
        found: list[PlaceholderField] = []
        for m in cls.PATTERN.finditer(text):
            raw_type = (m.group(1) or "").lower()
            found.append(PlaceholderField(
                type=cls._TYPE_MAP.get(raw_type, raw_type),
                name=m.group(2) or "",
                default=(m.group(3) or "").strip(),
                description=(m.group(4) or "").strip(),
                rule=(m.group(5) or "").strip(),
            ))
        return found

    @classmethod
    def extract_from_block(cls, block_data: dict) -> list[PlaceholderField]:
        """
        Alle Platzhalter eines Blocks ueber ALLE Textstellen hinweg
        (inkl. Tabellenzellen — Build 388/389).

        Mehrfachnennungen desselben Feldnamens werden zusammengefasst; es
        gewinnt der ERSTE Fund, weil der Client denselben Wert aus
        placeholder_values_json in alle Vorkommen rendert (ein Feldname =
        ein Wert je Block).
        """
        seen: dict[str, PlaceholderField] = {}
        for text in cls.iter_texts(block_data):
            for field in cls.extract(text):
                if field.name not in seen:
                    seen[field.name] = field
        return list(seen.values())
