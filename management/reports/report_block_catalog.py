# =============================================================================
# management/reports/report_block_catalog.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — SF-3 Nachbesserung (Build 659, Vorgang 317481d3)
# =============================================================================
# Zweck:
#   Aus einem bereits aufgebauten ReportDocument die WAEHLBARE Blockliste
#   gewinnen, mit der die Lektorin ihren Kommentar verankert: Ordnungszahl,
#   Blockkennung, Typ in Klartext, ein kurzer Textauszug und die Zahl der
#   bereits an diesem Block haengenden Kommentare.
#
# ── WARUM ES DIESES MODUL GIBT (Vorgang 317481d3) ────────────────────────────
#
#   Die Maske verlangte die Blockkennung bis Build 658 als FREITEXT
#   (cockpit_lectorate.js:762-767, "Block-ID (optional)"). Die Kennung ist eine
#   UUID aus report_blocks.block_id und steht NIRGENDS in der Oberflaeche — die
#   Anlage kennt sie, die Anwenderin nicht. Das Feld war damit nicht bedienbar,
#   und da der Server jeden String annahm (management_app.py:4467-4469), landete
#   ein Vertipper STILL als Kommentar mit block_sha256=NULL in der Addendum-
#   Datei: ununterscheidbar vom Fall "evidence-Datei gerade nicht lesbar"
#   (management_app.py:_block_sha256 gibt in BEIDEN Faellen None). Grundregel 1.
#
# ── DIE ORDNUNGSZAHL IST NICHT GERECHNET, SONDERN GEERBT ─────────────────────
#
#   Die Nummer eines Eintrags ist seine Position in doc.blocks — und doc.blocks
#   ist GENAU die Liste, aus der HtmlRenderer die Vorschau im iframe baut
#   (management_app.py:_report_render). Die Nummer im Auswahlfeld und die
#   Reihenfolge im Vorschaufenster koennen deshalb nicht auseinanderlaufen: es
#   ist dieselbe Liste, nicht zwei Ableitungen derselben Quelle.
#
#   Das ist die Lehre aus Build 658 (dort: Namensmuster im Katalog statt im
#   Pruefer) — "zwei Ausdruecke fuer dieselbe Sache laufen beim naechsten Umbau
#   auseinander, und dann prueft der eine, was der andere nicht bildet".
#
# ── DER AUSZUG WIRD EINGESAMMELT, NICHT AUFGEZAEHLT ──────────────────────────
#
#   Fuer den Auszug wird zuerst der platzhalter-aufgeloeste Klartext genommen
#   (resolved_text_plain bzw. die _resolved_*_plain-Ableitungen des
#   ReportSource). Traegt ein Block keines dieser Felder — und das ist bei einem
#   ZEHNTEN, unbekannten Blocktyp der Normalfall, mit dem der Bestand
#   ausdruecklich rechnet (report_render/report_source.py:57) — faellt die
#   Gewinnung auf das rekursive Einsammeln aus management/search/block_text.py
#   zurueck. Ein unbekannter Block erscheint dadurch MIT Text in der Liste statt
#   als leerer Eintrag, den niemand zuordnen kann.
#
#   html_zu_klartext/json_klartext werden WIEDERVERWENDET und nicht
#   nachgebaut: Editor.js legt Inline-Auszeichnung als HTML im Text ab, und die
#   Begruendung fuer jede Einzelheit dieser Umwandlung (Tag durch EIN
#   Leerzeichen ersetzen, Entitaeten aufloesen, kein Parser) steht dort im
#   Modulkopf und soll nicht in einer zweiten Fassung veralten.
#
# ── WAS DIESES MODUL NICHT TUT ───────────────────────────────────────────────
#
#   Es oeffnet keine Datenbank. Es bekommt das fertige ReportDocument und eine
#   fertige Zaehlung und liefert reine Daten. Dadurch ist es ohne Datei und ohne
#   Server pruefbar; der Endpunkt (management_app.py:_report_blocks) traegt die
#   Datenbankarbeit.
#
# Grundregeln: GR1 (nichts still auslassen), GR6 (Intention kommentieren),
#              GR10 (eine Klasse je Datei).
# Version: v0.8.659 · Build: 659 · 2026-08-02
# =============================================================================

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Mapping, Optional

from management.search.block_text import html_zu_klartext, json_klartext

logger = logging.getLogger(__name__)

#: Vorgabelaenge des Textauszugs in ZEICHEN (nicht Bytes — das Forum ist
#  multilingual, eine Byte-Grenze zerschnitte Mehrbyte-Zeichen; Fallerkenntnis 2).
#  60 statt der im Vorgang vorgeschlagenen 20: Berichtsbausteine beginnen
#  formelhaft ("Der Beschuldigte ...", "Am 14.03.2024 ...") und waeren bei 20
#  Zeichen paarweise nicht unterscheidbar — die Auswahl waere dann so blind wie
#  das Freitextfeld, das sie ersetzt.
AUSZUG_LAENGE: int = 60

#: Anhang, wenn der Auszug gekuerzt wurde. Sichtbares Zeichen dafuer, dass mehr
#  Text vorhanden ist (GR1: die Kuerzung wird zusaetzlich als 'truncated'
#  gemeldet, damit sie auch maschinell erkennbar bleibt).
AUSZUG_ANHANG: str = " …"

#: Ersatztext fuer Bloecke ohne jeden Text (z.B. Trennlinie, Bild ohne
#  Bildunterschrift). KEIN leerer Eintrag: ein namenloser Eintrag in einer
#  Auswahlliste ist nicht waehlbar, und "nicht waehlbar" waere hier dasselbe
#  Versaeumnis wie das Freitextfeld.
AUSZUG_LEER: str = "(ohne Text)"

#: Blocktyp -> deutsche Bezeichnung. Die neun bekannten Typen stammen aus
#  report_render/report_source.py:59-62 (Editor.js-Toolnamen).
#  BEWUSST SERVERSEITIG: Die Bezeichnung wird MITGELIEFERT und nicht im
#  Browser nachgeschlagen. Eine zweite Tabelle im JavaScript waere die
#  Doppelbildung, die Build 658 in der Startpruefung gekostet hat.
TYP_BEZEICHNUNG: Dict[str, str] = {
    "paragraph": "Absatz",
    "header":    "Überschrift",
    "list":      "Liste",
    "table":     "Tabelle",
    "quote":     "Zitat",
    "image":     "Bild",
    "delimiter": "Trennlinie",
    "marker":    "Hervorhebung",
    "evidence":  "Belegverweis",
}

#: Bezeichnung fuer einen Typ ausserhalb der neun bekannten. Er wird BENANNT
#  und nicht verschwiegen — der Bestand rechnet ausdruecklich mit einem zehnten
#  Typ (report_source.py:57 "Ein zehnter Typ wird gemeldet, nicht uebersprungen").
TYP_UNBEKANNT_MUSTER: str = "unbekannter Typ '%s'"


class ReportBlockCatalog:
    """
    Baut die waehlbare Blockliste eines Berichts aus einem ReportDocument.

    Reine Umwandlung ohne Datenbankzugriff — der Aufrufer bringt das Dokument
    und (optional) die Kommentarzahlen mit.
    """

    def __init__(self, *, auszug_laenge: int = AUSZUG_LAENGE) -> None:
        """
        auszug_laenge — Zeichen des Textauszugs. Als Parameter gefuehrt, damit
        die Regression die Kuerzung an einer kurzen Grenze pruefen kann, ohne
        Testtexte von 60 Zeichen bauen zu muessen.
        """
        if int(auszug_laenge) < 1:
            raise ValueError("auszug_laenge muss mindestens 1 sein.")
        self._laenge = int(auszug_laenge)

    # ------------------------------------------------------------------
    def bauen(self, doc: Any,
              kommentar_zahlen: Optional[Mapping[str, int]] = None
              ) -> List[Dict[str, Any]]:
        """
        Liefert die Blockliste in AUSGABEREIHENFOLGE.

        doc              — ReportDocument (report_render.report_document).
        kommentar_zahlen — Abbildung block_id -> Anzahl bereits vorhandener
                           Kommentare. Fehlt sie, steht ueberall 0.

        Je Eintrag:
            ordinal        1-basierte Position (= Position in der Vorschau)
            block_id       Blockkennung (report_blocks.block_id)
            block_type     roher Editor.js-Toolname
            type_label     deutsche Bezeichnung des Typs
            excerpt        gekuerzter Klartextauszug
            truncated      True, wenn der Auszug gekuerzt wurde
            comment_count  Zahl der bereits an diesem Block haengenden Kommentare
            is_known_type  False bei einem Typ ausserhalb der neun bekannten
        """
        zahlen = dict(kommentar_zahlen or {})
        eintraege: List[Dict[str, Any]] = []

        for nummer, blk in enumerate(getattr(doc, "blocks", []) or [], start=1):
            block_id = str(getattr(blk, "block_id", "") or "")
            block_type = str(getattr(blk, "block_type", "") or "")
            voller_text = self._klartext(blk)
            auszug, gekuerzt = self._kuerzen(voller_text)

            eintraege.append({
                "ordinal":       nummer,
                "block_id":      block_id,
                "block_type":    block_type,
                "type_label":    self.typ_bezeichnung(block_type),
                "excerpt":       auszug,
                "truncated":     gekuerzt,
                "comment_count": int(zahlen.get(block_id, 0)),
                "is_known_type": bool(getattr(blk, "is_known_type", True)),
            })

        return eintraege

    # ------------------------------------------------------------------
    @staticmethod
    def typ_bezeichnung(block_type: str) -> str:
        """Deutsche Bezeichnung; ein unbekannter Typ wird benannt, nicht ersetzt."""
        bt = str(block_type or "")
        if bt in TYP_BEZEICHNUNG:
            return TYP_BEZEICHNUNG[bt]
        return TYP_UNBEKANNT_MUSTER % (bt or "?")

    # ------------------------------------------------------------------
    @staticmethod
    def zaehle_kommentare(kommentare: Any) -> Dict[str, int]:
        """
        Zaehlt Kommentare je block_id aus der Liste des ReviewCommentReader.

        Kommentare OHNE Anker (block_id NULL) werden bewusst NICHT gezaehlt:
        sie gehoeren zu keinem Eintrag der Liste. Sie verschwinden dadurch aber
        nicht — der Endpunkt fuehrt sie getrennt unter 'unanchored_comments',
        damit ihre Zahl benannt bleibt (GR1). Bis Build 658 konnte die Maske
        solche Kommentare erzeugen; ab Build 659 nicht mehr.
        """
        zahlen: Dict[str, int] = {}
        for k in (kommentare or []):
            if not isinstance(k, Mapping):
                continue
            bid = k.get("block_id")
            if bid is None or str(bid) == "":
                continue
            schluessel = str(bid)
            zahlen[schluessel] = zahlen.get(schluessel, 0) + 1
        return zahlen

    # ------------------------------------------------------------------
    @staticmethod
    def zaehle_ankerlose(kommentare: Any) -> int:
        """Zahl der Kommentare ohne Anker — benannt statt verschwiegen (GR1)."""
        anzahl = 0
        for k in (kommentare or []):
            if not isinstance(k, Mapping):
                continue
            bid = k.get("block_id")
            if bid is None or str(bid) == "":
                anzahl += 1
        return anzahl

    # ------------------------------------------------------------------
    # innere Hilfen
    # ------------------------------------------------------------------
    def _klartext(self, blk: Any) -> str:
        """
        Klartext eines Blocks in drei Stufen — die spaetere greift nur, wenn die
        frueheren nichts liefern.

        (1) resolved_text_plain: der platzhalter-aufgeloeste Text der einfachen
            Textbloecke (paragraph/header/quote/marker/evidence).
        (2) die _resolved_*_plain-Ableitungen fuer die strukturierten Typen
            (list/table/quote-caption/image-caption).
        (3) rekursives Einsammeln aus dem Rohdatenobjekt. DIESE STUFE IST DER
            GRUND, WARUM EIN UNBEKANNTER BLOCKTYP HIER NICHT LEER BLEIBT.
        """
        # (1) einfache Textbloecke
        text = html_zu_klartext(getattr(blk, "resolved_text_plain", "") or "")
        if text:
            return text

        data = getattr(blk, "data", None)
        if not isinstance(data, dict):
            return ""

        # (2) strukturierte Typen ueber die Ableitungen des ReportSource
        teile: List[str] = []
        for wert in (data.get("_resolved_items_plain") or []):
            teile.append(html_zu_klartext(str(wert)))
        for zeile in (data.get("_resolved_rows_plain") or []):
            if isinstance(zeile, (list, tuple)):
                for zelle in zeile:
                    teile.append(html_zu_klartext(str(zelle)))
        beschriftung = data.get("_resolved_caption_plain")
        if beschriftung:
            teile.append(html_zu_klartext(str(beschriftung)))
        zusammen = " ".join(t for t in teile if t).strip()
        if zusammen:
            return zusammen

        # (3) Auffangstufe fuer alles Uebrige, einschliesslich unbekannter Typen.
        #     json_klartext ueberspringt Schluessel mit fuehrendem '_' — es
        #     sammelt also die ROHfelder ein und nicht noch einmal die bereits
        #     geprueften Ableitungen.
        try:
            return json_klartext(json.dumps(data, ensure_ascii=False))
        except (TypeError, ValueError) as exc:
            # Nicht serialisierbares data-Objekt: gemeldet, nicht verschwiegen.
            logger.warning(
                "Blockdaten nicht als JSON darstellbar (block_id=%s): %s",
                getattr(blk, "block_id", "?"), exc,
            )
            return ""

    # ------------------------------------------------------------------
    def _kuerzen(self, text: str) -> tuple[str, bool]:
        """
        Auf die Auszugslaenge kuerzen. Rueckgabe (auszug, wurde_gekuerzt).

        Gekuerzt wird an der ZEICHENgrenze und, wenn moeglich, am letzten
        Wortende davor — ein mitten im Wort abgeschnittener Auszug liest sich
        wie ein Datenfehler. Gibt es im Auszug keinen Zwischenraum (lange
        zusammengesetzte Woerter, Sprachen ohne Wortabstand), wird hart an der
        Zeichengrenze geschnitten; das ist die harmlose Richtung.
        """
        sauber = (text or "").strip()
        if not sauber:
            return AUSZUG_LEER, False
        if len(sauber) <= self._laenge:
            return sauber, False

        schnitt = sauber[:self._laenge]
        letzte_luecke = schnitt.rfind(" ")
        # Nur am Wortende schneiden, wenn dabei nicht mehr als die Haelfte des
        # Auszugs verlorengeht — sonst ist der harte Schnitt der informativere.
        if letzte_luecke >= self._laenge // 2:
            schnitt = schnitt[:letzte_luecke]
        return schnitt.rstrip() + AUSZUG_ANHANG, True
