# =============================================================================
# report_render/vollzitat_bauer.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Beweismittelgruppen)
# =============================================================================
# Zweck:
#   AUS BELEG-IDS EINE FERTIGE VOLLZITAT-GRUPPE MACHEN. Diese Datei ist die
#   EINE Stelle, an der die vierte Darstellungsvariante entsteht. Sie holt
#   die Annotationen, bestimmt je Beleg die Quelle (quellen_kunde), findet den
#   umschliessenden Absatz im Seitenabzug (absatz_finder), loest den
#   Ermittlernamen auf (ermittler_namen), holt Farbe und Bezeichnung der
#   Kategorie (core/kategorie_farben) - und fasst zusammen, was
#   zusammengehoert.
#
#   Bildschirm und Bericht rufen HIER an. Der Berichtseditor bekommt dasselbe
#   Ergebnis ueber einen AJAX-Endpunkt, die vier Renderer ueber
#   report_source. Es gibt keine zweite Fassung.
#
# ── DIE ZUSAMMENFASSUNG (Anforderung 9) ──────────────────────────────────────
#
#   "Wenn moeglich, dann sollen Annotationen, die denselben Beitrag betreffen,
#   und die derselben Belegsammlung zugeordnet werden, in einen Unterblock
#   zusammengefasst werden."
#
#   Der Schluessel ist (Art, post_id) - und die ART GEHOERT DAZU. Forenbeitrag
#   und private Nachricht haben GETRENNTE, UEBERLAPPENDE ID-Raeume (s. Kopf
#   von quellen_kunde.py): Beitrag 44573 und Nachricht 44573 sind zwei
#   verschiedene Dinge. Ohne die Art im Schluessel wuerden sie in einem
#   Unterblock landen - mit EINER Quellenangabe fuer zwei verschiedene
#   Quellen. Das waere keine Formatierungspanne, sondern eine falsche
#   Zuschreibung in einer Akte.
#
#   Belege OHNE Beitragsbezug bekommen jeweils einen eigenen Unterblock.
#   Sie zusammenzufassen hiesse zu behaupten, sie stammten aus derselben
#   Quelle - und das weiss niemand.
#
#   "Derselben Belegsammlung" ist durch den Aufruf erfuellt: gebaut wird je
#   'evidence'-Block, und dessen block_data.evidence_ids IST die Sammlung.
#   Ueber Blockgrenzen hinweg wird NICHT zusammengefasst - der Bearbeiter hat
#   die Gruppen gebildet, und die Darstellung ordnet sie nicht um.
#
# ── DIE REIHENFOLGE IST DIE DES BEARBEITERS ──────────────────────────────────
#
#   Die Unterbloecke stehen in der Reihenfolge, in der ihr ERSTER Beleg in
#   evidence_ids vorkommt. Nicht nach Datum, nicht nach Kategorie. Der
#   Bearbeiter hat die Belege in eine Reihenfolge gebracht - womoeglich, weil
#   sie in dieser Reihenfolge eine Geschichte erzaehlen. Eine Umsortierung
#   waere eine stille Aenderung seiner Aussage.
#
# ── KEIN BELEG FAELLT WEG (GR1) ──────────────────────────────────────────────
#
#   Jede angeforderte Beleg-ID erscheint in der Ausgabe - auch wenn die
#   Annotation geloescht wurde, der Seitenabzug fehlt, der Absatz nicht
#   auffindbar ist oder die Kategorie unbekannt ist. Was fehlt, wird BENANNT:
#   im Befund selbst und in 'warnungen', die der Renderer in den Abschnitt
#   "Hinweise zur Erzeugung" hebt (R2).
#
# ── ES WIRD NICHTS GESCHRIEBEN ───────────────────────────────────────────────
#
#   Rein lesend auf evidence (annotations), fdb (uid_posts/uid_topics/
#   uid_pms_posts/pages) und cdb (person). Kein Schema, keine Migration,
#   kein Schreibzugriff - Migrationsvorbehalt ab 01.07.2026 nicht beruehrt.
#   Die Berichts-Siegel bleiben gueltig: ReportSealer hasht die Zeilen aus
#   report_blocks, nicht die gerenderte Ausgabe (report_sealer.py, Kopf
#   "UMFANG DES SIEGELS").
#
# Grundregeln: GR1, GR6, GR10.
# Version: v0.8.725 - Build: 725 - 2026-08-27
# =============================================================================

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from core import kategorie_farben
from core.logger import get_logger
from report_render.absatz_finder import (
    AbsatzFinder,
    Markierung,
    WEG_KEINER,
    WEG_TEXT,
    WEG_UEBERSETZUNG,
    WEG_XPATH,
    auswahl_text,
)
from report_render.ermittler_namen import ErmittlerNamen
from report_render.quellen_kunde import ART_BEITRAG, ART_PN, QuellenKunde
from report_render.vollzitat_satz import (
    Absatz,
    Befund,
    Unterblock,
    VollzitatGruppe,
)

logger = get_logger(__name__)


def _esc(s: Any) -> str:
    """HTML-Escaping fuer Klartext, der in ein Fragment eingesetzt wird."""
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


class VollzitatBauer:
    """
    Baut Vollzitat-Gruppen. Eine Instanz je Berichtsaufbau.

    Zusammenspiel der Zwischenspeicher (alle nur fuer die Lebensdauer der
    Instanz): Annotationen werden EINMAL geholt, Seitenabzuege je Adresse
    EINMAL zerlegt, Ermittlernamen und Quellen je Schluessel EINMAL
    aufgeloest. Ohne das zerlegte ein Bericht mit fuenfzig Belegen derselben
    Themenseite dieselbe Seite fuenfzigmal - bei bis zu 500 Beitraegen je
    Seite ist das der teuerste Einzelschritt.
    """

    def __init__(
        self,
        *,
        evidence: Any,
        forensic: Any = None,
        con: Optional[sqlite3.Connection] = None,
    ) -> None:
        """
        evidence - EvidenceDb (annotations)
        forensic - ForensicDb (Seitenabzuege ueber get_page). DARF None SEIN;
                   dann gibt es keine Absaetze, und das wird gesagt.
        con      - die Buendelverbindung (Traeger der ATTACHs fdb und cdb)

        WARUM ForensicDb UEBERGEBEN UND NICHT HIER GEBAUT WIRD: Der
        Konstruktor von ForensicDb legt die TEMP-VIEW 'blob_lookup' NEU an
        und wirft die vorhandene vorher weg (db/forensic_db.py, _setup_view).
        Im Webserver ist die Buendelverbindung dieselbe, ueber die gerade
        Seiten ausgeliefert werden - ein Berichtsexport wuerde dem
        Auslieferungspfad mitten im Betrieb die Sicht unter den Fuessen
        wegziehen. Der Aufrufer reicht deshalb die BESTEHENDE Instanz durch.
        """
        self._evidence = evidence
        self._forensic = forensic
        self._con = con
        self._namen = ErmittlerNamen(con)
        self._quellen = QuellenKunde(con)
        self._annotationen: Optional[Dict[int, Any]] = None
        self._finder: Dict[str, AbsatzFinder] = {}
        self._seiten_gemeldet: set = set()

    # ------------------------------------------------------------------
    def _alle_annotationen(self) -> Dict[int, Any]:
        if self._annotationen is None:
            self._annotationen = {}
            if self._evidence is not None:
                try:
                    for rec in self._evidence.get_all_annotations():
                        self._annotationen[int(rec.id)] = rec
                except Exception as exc:  # pragma: no cover - defensiv
                    logger.warning(
                        "Vollzitat: Annotationen nicht lesbar (%s).", exc)
        return self._annotationen

    # ------------------------------------------------------------------
    def _seite(self, page_url: str) -> AbsatzFinder:
        """Den Finder zu einer Adresse holen - je Adresse genau einmal."""
        schluessel = str(page_url or "")
        if schluessel in self._finder:
            return self._finder[schluessel]

        roh = None
        if self._forensic is not None and schluessel:
            try:
                seite = self._forensic.get_page(schluessel)
                roh = getattr(seite, "html", None) if seite else None
            except Exception as exc:
                logger.warning(
                    "Vollzitat: Seitenabzug %r nicht lesbar (%s).",
                    schluessel, exc)
        finder = AbsatzFinder.aus_seiten_html(roh)
        self._finder[schluessel] = finder
        return finder

    # ------------------------------------------------------------------
    def baue(
        self,
        evidence_ids: Any,
        beschriftung: str = "",
    ) -> VollzitatGruppe:
        """
        Die Vollzitat-Gruppe zu einer Liste von Beleg-IDs bauen.

        Nicht-ganzzahlige Eintraege in evidence_ids werden BENANNT
        uebergangen, nicht wortlos: block_data ist JSON aus dem Browser und
        kann alles enthalten.
        """
        gruppe = VollzitatGruppe(beschriftung=str(beschriftung or ""))

        ids: List[int] = []
        for roh in (evidence_ids if isinstance(evidence_ids, list) else []):
            try:
                ids.append(int(roh))
            except (TypeError, ValueError):
                gruppe.warnungen.append(
                    "Beweismittelgruppe: Eintrag %r ist keine Beleg-Nummer "
                    "und konnte nicht aufgeloest werden." % (roh,))
        gruppe.beleg_anzahl = len(ids)
        if not ids:
            return gruppe

        annotationen = self._alle_annotationen()

        # Schluessel -> Unterblock, in Reihenfolge des ersten Vorkommens.
        bloecke: Dict[Tuple, Unterblock] = {}
        # Je Unterblock: Absatz-Element (Identitaet) -> Absatz-Eintrag,
        # damit zwei Belege im selben Absatz EINEN Absatz ergeben.
        absatz_index: Dict[Tuple, Dict[int, Tuple[Any, List[Markierung]]]] = {}

        for beleg_id in ids:
            rec = annotationen.get(beleg_id)
            if rec is None:
                # GR1: der Beleg verschwindet nicht - er bekommt einen eigenen
                # Unterblock, der sagt, dass es ihn nicht (mehr) gibt.
                self._fehlbeleg(gruppe, bloecke, beleg_id)
                continue
            self._einordnen(gruppe, bloecke, absatz_index, beleg_id, rec)

        # Absaetze rendern - erst jetzt, wenn ALLE Markierungen je Absatz
        # bekannt sind. Frueher zu rendern hiesse, denselben Absatz mehrfach
        # zu drucken, jedes Mal mit nur einer Markierung.
        from report_render.absatz_finder import _klartext

        for schluessel, block in bloecke.items():
            for finder, element, markierungen in \
                    absatz_index.get(schluessel, {}).values():
                nummern = sorted(m.nummer for m in markierungen)
                block.absaetze.append(
                    Absatz(html=finder.rendere(element, markierungen),
                           text=_klartext(element),
                           nummern=nummern, ersatz=False))
            # NACH DER VERWEISNUMMER SORTIEREN, nicht nach Fundzeitpunkt.
            # Ersatzabsaetze (kein Absatz gefunden) entstehen waehrend des
            # Einordnens, die echten erst hier - ohne diese Zeile stuenden
            # sie in der Ausgabe vor den echten, und die Hochzahlen im
            # Unterblock liefen 3, 1, 2. Der Leser soll den Befunden von oben
            # nach unten folgen koennen.
            block.absaetze.sort(key=lambda a: min(a.nummern) if a.nummern else 0)

        gruppe.unterbloecke = list(bloecke.values())
        return gruppe

    # ------------------------------------------------------------------
    def _fehlbeleg(self, gruppe, bloecke, beleg_id: int) -> None:
        from report_render.quellen_kunde import Quelle
        schluessel = ("fehlt", beleg_id)
        block = Unterblock(quelle=Quelle(art=ART_BEITRAG))
        block.befunde.append(Befund(
            nummer=1, annotation_id=beleg_id,
            kategorie="", kategorie_text=kategorie_farben.UNBEKANNT_NAME,
            css_klasse=kategorie_farben.css_klasse(None),
            farbe=kategorie_farben.UNBEKANNT_HINTERLEGUNG,
            markierung="", notiz="", ermittler="",
            name_quelle="kuerzel", absatz_weg=WEG_KEINER,
            hinweis="Zu dieser Beleg-Nummer gibt es in der "
                    "Beweismitteldatenbank keine aktive Annotation."))
        bloecke[schluessel] = block
        gruppe.warnungen.append(
            "Beleg #%d ist in der Beweismittelgruppe verzeichnet, in "
            "annotations aber nicht (mehr) vorhanden - er wurde geloescht "
            "oder stammt aus einer anderen Beweismitteldatenbank. Der Beleg "
            "wird im Bericht als fehlend ausgewiesen und nicht "
            "uebersprungen." % beleg_id)

    # ------------------------------------------------------------------
    def _einordnen(self, gruppe, bloecke, absatz_index, beleg_id, rec) -> None:
        from forensic_api.annotations import _derive_post_id

        post_id = _derive_post_id(rec)
        quelle = self._quellen.ermitteln(
            page_url=rec.page_url, post_id=post_id,
            element_id=rec.element_id)

        # Der Unterblock-Schluessel - s. Kopf, "DIE ZUSAMMENFASSUNG".
        if post_id is None:
            schluessel = ("einzeln", beleg_id)
        else:
            schluessel = (quelle.art, post_id)

        block = bloecke.get(schluessel)
        if block is None:
            block = Unterblock(quelle=quelle)
            bloecke[schluessel] = block
            absatz_index[schluessel] = {}
            # Die Quellenwarnungen gehoeren zum Unterblock, nicht zum Beleg -
            # sie gelten fuer alle Belege derselben Quelle. Sie werden
            # deshalb genau einmal je Unterblock uebernommen.
            for w in quelle.warnungen:
                gruppe.warnungen.append("Beleg #%d: %s" % (beleg_id, w))

        nummer = len(block.befunde) + 1

        selection = self._selection(rec)
        finder = self._seite(rec.page_url)
        fundstelle = finder.finde(selection, rec.element_id)

        kategorie = rec.category or ""
        if not kategorie_farben.ist_bekannt(kategorie):
            gruppe.warnungen.append(
                "Beleg #%d traegt die Kategorie %r, die das Werkzeug nicht "
                "kennt. Der Beleg erscheint im Bericht mit seinem Rohwert "
                "und in neutraler Farbe." % (beleg_id, kategorie))

        name = self._namen.aufloesen(getattr(rec, "created_by", ""))

        befund = Befund(
            nummer=nummer,
            annotation_id=beleg_id,
            kategorie=kategorie,
            kategorie_text=kategorie_farben.bezeichnung(kategorie),
            css_klasse=kategorie_farben.css_klasse(kategorie),
            farbe=kategorie_farben.hinterlegung(kategorie),
            markierung=fundstelle.text or auswahl_text(selection),
            notiz=rec.text or "",
            ermittler=name.anzeige,
            name_quelle=name.quelle,
            absatz_weg=fundstelle.weg,
            hinweis=fundstelle.hinweis,
        )
        block.befunde.append(befund)

        if fundstelle.hinweis:
            gruppe.warnungen.append(
                "Beleg #%d: %s" % (beleg_id, fundstelle.hinweis))

        if fundstelle.block is not None:
            eintrag = absatz_index[schluessel].setdefault(
                id(fundstelle.block), (finder, fundstelle.block, []))
            eintrag[2].append(Markierung(
                von=fundstelle.von, bis=fundstelle.bis,
                css_klasse=befund.css_klasse, farbe=befund.farbe,
                nummer=nummer))
        else:
            # Kein Absatz - die markierte Stelle wird ALLEIN wiedergegeben,
            # sichtbar als Ersatz gekennzeichnet. Nichts zu zeigen waere ein
            # still uebersprungener Beleg (GR1).
            block.absaetze.append(self._ersatzabsatz(befund))

    # ------------------------------------------------------------------
    @staticmethod
    def _ersatzabsatz(befund: Befund) -> Absatz:
        if befund.markierung:
            html = ('<span class="vz-mark %s" style="background-color: %s;" '
                    'data-beleg="%d">%s</span>'
                    % (_esc(befund.css_klasse), _esc(befund.farbe),
                       befund.nummer, _esc(befund.markierung)))
            text = befund.markierung
        else:
            html = ('<em class="vz-ohne-wortlaut">(Die Annotation traegt '
                    'keinen markierten Wortlaut.)</em>')
            text = "(kein markierter Wortlaut)"
        return Absatz(html=html, text=text, nummern=[befund.nummer],
                      ersatz=True)

    # ------------------------------------------------------------------
    @staticmethod
    def _selection(rec) -> Any:
        roh = getattr(rec, "selection_json", None)
        if not roh:
            return None
        try:
            return json.loads(roh)
        except (ValueError, TypeError):
            # Unlesbares JSON ist kein Absturzgrund, aber auch kein Nichts:
            # der Absatz wird dann nicht gefunden und der Beleg erscheint mit
            # dem entsprechenden Hinweis.
            logger.warning(
                "Vollzitat: selection_json der Annotation %s ist kein "
                "gueltiges JSON.", getattr(rec, "id", "?"))
            return None
