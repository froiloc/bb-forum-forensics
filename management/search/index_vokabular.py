# =============================================================================
# management/search/index_vokabular.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B560)
# =============================================================================
# Zweck:
#   Das kontrollierte Vokabular des Suchindex an EINER Stelle: welche Spalten
#   der Beweismitteldatenbanken indiziert werden (SATZ_ARTEN), in welchem
#   Bearbeitungszustand ein Satz stehen kann (FASSUNGEN), welcher Befund je
#   Quelldatenbank moeglich ist (QUELL_BEFUNDE) und mit welchen Tokenizern der
#   Index arbeitet.
#
#   Kein Klassenmodul (Grundregel 10 betrifft Klassen) — hier stehen bewusst
#   nur Konstanten und reine Funktionen. Der Grund fuer die eigene Datei: das
#   Vokabular wird an VIER Stellen gebraucht — vom Quellenleser (560), vom
#   Indexbauer (560), von den Endpunkten (562) und von der Sicht (563). Vier
#   Kopien waeren die sicherste Art, sie auseinanderlaufen zu lassen.
#
# ── WAS INDIZIERT WIRD, UND WARUM AUSGERECHNET DAS ───────────────────────────
#
#   WICHTIGSTER BEFUND DER VORRECHERCHE (Klaerung_AP3E_..._v0_2.md §2):
#   In evidence_<uid>.db steht KEIN FORUMSINHALT. Die Original-Seiten liegen als
#   HTML-BLOB in forensic_<uid>.db (db/forensic_db.py:88-111), der gereinigte
#   Beitragstext und die Uebersetzungen in translations.db
#   (db/translations_db.py:294-305, :246-253). Was in evidence_<uid>.db an
#   Freitext steht, ist von ERMITTLER:INNEN geschrieben.
#
#   Daraus folgt die Zusammensetzung dieser Liste — und zugleich, was sie
#   AUSDRUECKLICH NICHT enthaelt: keinen Beitragstext, keine Uebersetzung, kein
#   HTML. Eine Suche ueber Forumsinhalt waere eine deutlich schaerfere Frage
#   (dann waeren Tatbeschreibungen durchsuchbar) und ist bewusst nicht Teil
#   dieses Arbeitspakets (Klaerung §7, Schlussabsatz).
#
#   Die acht Fundstellen der Klaerung §2 sind hier vollstaendig abgebildet;
#   'annotations.category' ist zusaetzlich als EIGENE Satzart gefuehrt, weil es
#   ein CODE ist und kein Freitext — als eigene Art laesst es sich in der Sicht
#   getrennt ausweisen oder ausschliessen, in einem Topf mit dem Annotationstext
#   waere das nie mehr moeglich.
#
# ── FASSUNGEN: WARUM UEBERHOLTES MITINDIZIERT WIRD (Entscheidung mc 2026-07-26)
#
#   annotations ist append-only: eine Bearbeitung legt einen NEUEN Datensatz an
#   (version_nr+1, prev_id = alte.id) und stempelt die alte Fassung mit
#   deleted_at (db/evidence_db.py:868-874). 'deleted_at' heisst dort also
#   GEAENDERT und nicht GELOESCHT — dieselbe Unterscheidung, die Build 535 in
#   TA09/TA11 gezogen hat.
#
#   mc hat am 2026-07-26 entschieden: ueberholte UND zurueckgenommene Fassungen
#   werden MITINDIZIERT und in Stufe 1 GETRENNT AUSGEWIESEN. Begruendung: gerade
#   der zurueckgenommene Befund ist fuer den Kreuzbezug wertvoll ("Kollege B hat
#   das schon geprueft und verworfen"); ihn stillschweigend wegzulassen waere
#   eine unmarkierte Auslassung (Grundregel 1). Der Preis — hoehere Trefferzahl —
#   wird durch die getrennte Ausweisung getragen.
#
#   Die Unterscheidung UEBERHOLT / ZURUECKGENOMMEN laeuft ueber 'prev_id', nicht
#   ueber 'local_id': ein Datensatz ist ueberholt, wenn ein ANDERER Datensatz
#   auf ihn zeigt (prev_id = seine id) — genau die Pruefung, die auch
#   db/evidence_db.py:989 fuer 'ist die Fassung aktuell?' benutzt. Ueber
#   'local_id' ginge es nicht: local_id ist optional ("anonyme Einmal-
#   Annotation", db/evidence_db.py:871), und eine geloeschte anonyme Annotation
#   waere dann nicht einzuordnen.
#
# ── DIE BEIDEN TOKENIZER (Entscheidung mc 2026-07-26) ────────────────────────
#
#   'unicode61 remove_diacritics 2' findet WOERTER und WORTANFAENGE. Das ist die
#   gute Rangfolge und der kleine Index — aber es findet 'birnenmus' NICHT in
#   'xXbirnenmusXx'. Nicknames stehen im Ermittlertext regelmaessig verklebt.
#   Eine reine Wortsuche wuerde solche Treffer LAUTLOS auslassen — und ein
#   Leerbefund saehe aus wie Vollstaendigkeit (Grundregel 1).
#
#   Deshalb liegen ZWEI FTS5-Tabellen in derselben, jederzeit verwerfbaren
#   search_index.db: 'index_wort' (unicode61) und 'index_teil' (trigram). Der
#   Modus ist bei der Abfrage waehlbar; 'wort' ist der Standard. Der Preis ist
#   Plattenplatz in einem HILFSMITTEL, kein Beweismittel — der guenstigste
#   Preis, den diese Wahl haben kann.
#
#   'remove_diacritics 2' ist die unicode-vollstaendige Variante (die aeltere
#   Stufe 1 laesst zusammengesetzte Zeichen aus). Das Forum ist multilingual
#   (Fallerkenntnis 2), und die Ermittlernotizen zitieren daraus.
#
#   TRIGRAM-GRENZE: FTS5-trigram kann nur Muster ab DREI Zeichen bedienen. Das
#   ist eine harte Eigenschaft der Erweiterung, keine Einstellung. Sie wird bei
#   der Abfrage (Build 562) im Klartext gemeldet, statt still nichts zu finden.
#
# Version: v0.8.560 · Build: 560 · 2026-07-26
# =============================================================================

from typing import Dict, FrozenSet, NamedTuple, Optional, Tuple


class SatzArt(NamedTuple):
    """Eine indizierte Fundstelle: stabiler Code + Herkunft + Anzeigelabel."""

    code: str
    label: str
    tabelle: str
    spalte: str
    #: True, wenn der Inhalt ein CODE ist und kein Freitext (Anzeige/Filter).
    ist_code: bool


# --- Was indiziert wird (Beleg: Klaerung_AP3E_..._v0_2.md §2, Tabelle) -------
#   Reihenfolge = Anzeigereihenfolge. Codes sind stabile Bezeichner: sie werden
#   ERGAENZT, niemals umbenannt oder wiederverwendet (dieselbe Regel wie beim
#   RBAC-Katalog und bei den EventTypes). Ein Umbenennen entwertete jeden
#   bereits erzeugten Beleg einer Suche.
SATZ_ARTEN: Tuple[SatzArt, ...] = (
    SatzArt("annotation_text", "Annotation (Text)",
            "annotations", "text", False),
    SatzArt("annotation_kategorie", "Annotation (Kategorie)",
            "annotations", "category", True),
    SatzArt("annotation_schlagworte", "Annotation (Schlagworte)",
            "annotations", "tags_json", False),
    SatzArt("bericht_titel", "Bericht/Vermerk (Titel)",
            "reports", "title", False),
    SatzArt("berichtsbaustein", "Berichtstext (Baustein)",
            "report_blocks", "block_data", False),
    SatzArt("platzhalterwert", "Eingesetzter Platzhalterwert",
            "report_blocks", "placeholder_values_json", False),
    SatzArt("berichtsanker", "Zitierter Ankertext",
            "report_anchors", "anchor_text", False),
    SatzArt("gegenlesen_kommentar", "Gegenlesen (Kommentar)",
            "report_comments", "comment_text", False),
    SatzArt("gegenlesen_vorschlag", "Gegenlesen (Formulierungsvorschlag)",
            "report_comments", "suggested_content", False),
    SatzArt("freigabevermerk", "Freigabevermerk",
            "report_approvals", "note", False),
    SatzArt("ermittler_alias", "Fallbezogene Alias-Notiz",
            "investigator_aliases", "term", False),
)

SATZ_ART_CODES: FrozenSet[str] = frozenset(a.code for a in SATZ_ARTEN)

#: Schneller Zugriff Code -> SatzArt (Anzeige, Pruefung).
SATZ_ART_NACH_CODE: Dict[str, SatzArt] = {a.code: a for a in SATZ_ARTEN}

#: Die beruehrten Quelltabellen — fuer den Leser, damit er nur oeffnet, was er
#  braucht, und fuer den Test, der Vokabular gegen Schema haelt.
QUELL_TABELLEN: Tuple[str, ...] = tuple(
    sorted({a.tabelle for a in SATZ_ARTEN}))


# --- Bearbeitungszustand eines Satzes ----------------------------------------
#   'aktuell'          — gueltige, nicht zurueckgenommene Fassung.
#   'ueberholt'        — durch eine neuere Fassung ersetzt (ein anderer
#                        Datensatz zeigt mit prev_id auf diesen).
#   'zurueckgenommen'  — geloescht/widerrufen, OHNE Nachfolger.
#
#   Die drei Werte sind NICHT gleichwertig und duerfen in der Sicht nie
#   zusammengezaehlt werden: 'aktuell' ist Arbeitsstand, die beiden anderen sind
#   Historie. Eine gemeinsame Zahl behauptete eine Trefferlage, die es so nicht
#   gibt.
FASSUNG_AKTUELL = "aktuell"
FASSUNG_UEBERHOLT = "ueberholt"
FASSUNG_ZURUECKGENOMMEN = "zurueckgenommen"

FASSUNGEN: Tuple[str, ...] = (
    FASSUNG_AKTUELL,
    FASSUNG_UEBERHOLT,
    FASSUNG_ZURUECKGENOMMEN,
)

FASSUNG_BEZEICHNUNG: Dict[str, str] = {
    FASSUNG_AKTUELL: "aktuelle Fassung",
    FASSUNG_UEBERHOLT: "ueberholt (durch neuere Fassung ersetzt)",
    FASSUNG_ZURUECKGENOMMEN: "zurueckgenommen",
}


# --- Befund je Quelldatenbank ------------------------------------------------
#   KEIN STILLER TEILTREFFER (Klaerung §6 Nr. 4): Eine Datenbank, die nicht
#   gelesen werden konnte, wird GEZAEHLT UND BENANNT. Sonst saehe eine Suche,
#   die 3 von 40 Datenbanken nicht lesen konnte, aus wie ein vollstaendiger
#   Befund.
#
#   'ohne_tabelle' ist ausdruecklich ein EIGENER Wert und nicht 'gelesen':
#   eine evidence-DB ohne die erwartete Tabelle ist etwas anderes als eine, in
#   der die Tabelle leer ist. Dieselbe Trennschaerfe wie bei
#   'nicht_geprueft' / 'ohne_feststellung' im Fristenmonitor (Build 535, TA16).
BEFUND_GELESEN = "gelesen"
BEFUND_NICHT_OEFFENBAR = "nicht_oeffenbar"
BEFUND_NICHT_LESBAR = "nicht_lesbar"
BEFUND_OHNE_TABELLE = "ohne_tabelle"
BEFUND_FEHLT = "fehlt"

QUELL_BEFUNDE: Tuple[str, ...] = (
    BEFUND_GELESEN,
    BEFUND_NICHT_OEFFENBAR,
    BEFUND_NICHT_LESBAR,
    BEFUND_OHNE_TABELLE,
    BEFUND_FEHLT,
)

BEFUND_BEZEICHNUNG: Dict[str, str] = {
    BEFUND_GELESEN: "gelesen",
    BEFUND_NICHT_OEFFENBAR: "Datenbank nicht oeffenbar",
    BEFUND_NICHT_LESBAR: "Datenbank nicht lesbar",
    BEFUND_OHNE_TABELLE: "erwartete Tabelle(n) fehlen — NICHT: nichts gefunden",
    BEFUND_FEHLT: "Datei fehlt",
}

#: Befunde, bei denen der Indexstand fuer diesen Fall UNVOLLSTAENDIG ist. Die
#  Abfrage muss sie in jeder Antwort benennen (Build 562).
BEFUNDE_UNVOLLSTAENDIG: FrozenSet[str] = frozenset({
    BEFUND_NICHT_OEFFENBAR, BEFUND_NICHT_LESBAR,
    BEFUND_OHNE_TABELLE, BEFUND_FEHLT,
})


# --- Tokenizer und Suchmodi --------------------------------------------------
TOKENIZER_WORT = "unicode61 remove_diacritics 2"
TOKENIZER_TEIL = "trigram"

MODUS_WORT = "wort"
MODUS_TEILSTRING = "teilstring"

SUCHMODI: Tuple[str, ...] = (MODUS_WORT, MODUS_TEILSTRING)

MODUS_BEZEICHNUNG: Dict[str, str] = {
    MODUS_WORT: "Wortsuche (Wortanfaenge, Standard)",
    MODUS_TEILSTRING: "Teilstringsuche (findet auch verklebte Fundstellen)",
}

#: Zu welcher FTS5-Tabelle ein Suchmodus greift.
MODUS_TABELLE: Dict[str, str] = {
    MODUS_WORT: "index_wort",
    MODUS_TEILSTRING: "index_teil",
}

#: Harte Eigenschaft von FTS5-trigram, keine Einstellung. Wird bei der Abfrage
#  im Klartext gemeldet (Build 562), statt still leer zu antworten.
MIN_TEILSTRING_LAENGE = 3


# --- Pruefungen ---------------------------------------------------------------

def ist_satz_art(code: object) -> bool:
    """True, wenn code eine bekannte Satzart ist."""
    return isinstance(code, str) and code in SATZ_ART_CODES


def ist_fassung(wert: object) -> bool:
    """True, wenn wert einer der drei Bearbeitungszustaende ist."""
    return isinstance(wert, str) and wert in FASSUNGEN


def ist_befund(wert: object) -> bool:
    """True, wenn wert ein bekannter Quellbefund ist."""
    return isinstance(wert, str) and wert in QUELL_BEFUNDE


def ist_suchmodus(wert: object) -> bool:
    """True, wenn wert ein bekannter Suchmodus ist."""
    return isinstance(wert, str) and wert in SUCHMODI


def normalisiere_suchmodus(wert: Optional[str]) -> str:
    """
    Bekannter Modus -> derselbe Wert; alles andere -> MODUS_WORT.

    BEWUSST NACHSICHTIG, und nur an dieser einen Stelle: der Modus kommt aus
    einer Auswahlliste der Oberflaeche und ist kein Beleg. Ein unbekannter Wert
    darf nicht dazu fuehren, dass gar nicht gesucht wird — er faellt auf den
    Standard zurueck. Fuer alles, was in einen Beleg wandert (Zweckcode,
    Suchbegriff), gilt das AUSDRUECKLICH NICHT; dort wird hart geprueft.
    """
    return wert if ist_suchmodus(wert) else MODUS_WORT


def _pruefe_vokabular() -> None:
    """
    Selbstpruefung beim Import — ein Tippfehler faellt beim SERVERSTART auf und
    nicht erst beim ersten Indexlauf.

    Geprueft wird, was sich still auswirken wuerde:
      * doppelte Satzart-Codes (die spaetere Zaehlung waere falsch),
      * Codes mit Doppelpunkt (der Doppelpunkt trennt in der Ablage von
        Zweckcodes Code und Freitext — dieselbe Konvention wie in
        db/tatzeit_vokabular.py),
      * ein Suchmodus ohne zugeordnete FTS5-Tabelle (die Abfrage liefe ins
        Leere und saehe aus wie 'nichts gefunden').
    """
    codes = [a.code for a in SATZ_ARTEN]
    if len(codes) != len(set(codes)):
        raise ValueError("index_vokabular: doppelter Satzart-Code in SATZ_ARTEN")
    for c in codes:
        if ":" in c:
            raise ValueError(
                "index_vokabular: Satzart-Code enthaelt einen Doppelpunkt: %r" % c)
    for m in SUCHMODI:
        if m not in MODUS_TABELLE:
            raise ValueError(
                "index_vokabular: Suchmodus ohne FTS5-Tabelle: %r" % m)
    for f in FASSUNGEN:
        if f not in FASSUNG_BEZEICHNUNG:
            raise ValueError(
                "index_vokabular: Fassung ohne Bezeichnung: %r" % f)
    for b in QUELL_BEFUNDE:
        if b not in BEFUND_BEZEICHNUNG:
            raise ValueError(
                "index_vokabular: Befund ohne Bezeichnung: %r" % b)


_pruefe_vokabular()
