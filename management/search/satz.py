# =============================================================================
# management/search/satz.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B560)
# =============================================================================
# Zweck:
#   Satz — EIN indizierter Textfund aus genau einer Spalte einer genau einen
#   Datensatzes einer evidence_<uid>.db. Die kleinste Einheit, die der Index
#   fuehrt, und zugleich der Rueckweg zur Quelle.
#
#   Eigene Datei nach Grundregel 10. Der praktische Nutzen ist hier greifbar:
#   Quellenleser (evidence_source_reader.py), Indexbauer (index_builder.py) und
#   spaeter die Abfrage (Build 562) reichen genau diese Struktur durch. Laege
#   sie in einem der drei Module, importierten die beiden anderen es nur wegen
#   eines NamedTuple mit — und zoegen dabei dessen Abhaengigkeiten nach.
#
# ── WARUM JEDER SATZ SEINEN RUECKWEG TRAEGT ──────────────────────────────────
#
#   Der Index ist HILFSMITTEL, KEIN BEWEISMITTEL (Klaerung §6 Nr. 3): jeder
#   Treffer wird vor der Anzeige gegen die Quelle verifiziert. Das ist nur
#   moeglich, wenn der Satz weiss, WOHER er stammt — Fall, Tabelle, Spalte und
#   Schluessel des Quelldatensatzes. Ohne diese vier Angaben waere der Index
#   eine Behauptung ohne Beleg, und genau das laesst dieses Projekt nicht zu.
#
#   'quell_schluessel' ist TEXT und nicht INTEGER, weil die Quelltabellen
#   verschiedene Primaerschluesselarten haben: annotations.id ist INTEGER,
#   report_blocks.block_id ist TEXT (db/evidence_db.py:288-298). Ein
#   gemeinsames Feld muss die weitere Form tragen; die engere hineinzuzwingen
#   hiesse, die Berichtsbausteine gar nicht erst aufnehmen zu koennen.
#
# ── ts DARF None SEIN, UND DAS IST KEIN MANGEL ───────────────────────────────
#
#   Stufe 1 der Suche nennt den ZEITRAUM der Treffer je Fall (Entscheidung mc,
#   Modell B). Nicht jede Quellspalte traegt einen Zeitstempel:
#   investigator_aliases hat created_at, report_anchors hat created_at,
#   annotations hat ts — aber ein Satz aus einer Spalte ohne eigenen Zeitpunkt
#   erbt keinen. Statt einen Ersatzwert zu erfinden (0 oder 'jetzt' — beides
#   waere eine unmarkierte Behauptung), bleibt das Feld None, und die
#   Zeitraumangabe der Stufe 1 nennt, wie viele Saetze ohne Zeitpunkt
#   eingegangen sind.
#
# Version: v0.8.560 · Build: 560 · 2026-07-26
# =============================================================================

from typing import NamedTuple, Optional


class Satz(NamedTuple):
    """
    Ein indizierter Textfund samt vollstaendigem Rueckweg zur Quelle.

    Felder:
      subject_id       — Fall (aus dem Dateinamen evidence_<uid>.db).
      satz_art         — Code aus index_vokabular.SATZ_ARTEN.
      quell_tabelle    — Tabelle in evidence_<uid>.db (redundant zur Satzart,
                         aber MITGEFUEHRT: die Satzart kann spaeter umgebaut
                         werden, die Herkunft des einzelnen Satzes nicht mehr).
      quell_spalte     — Spalte in dieser Tabelle.
      quell_schluessel — Primaerschluessel des Quelldatensatzes, als Text.
      fassung          — aktuell | ueberholt | zurueckgenommen.
      ts               — Zeitpunkt des Quelldatensatzes (Unix-Sekunden) oder
                         None, wenn die Quelle keinen fuehrt.
      urheber          — wer den Satz geschrieben hat (created_by/author/...),
                         oder None. Dient in Stufe 1 der Frage "mit wem rede
                         ich darueber?" — dem eigentlichen Zweck der Funktion.
      text             — der indizierte Klartext.
    """

    subject_id: int
    satz_art: str
    quell_tabelle: str
    quell_spalte: str
    quell_schluessel: str
    fassung: str
    ts: Optional[int]
    urheber: Optional[str]
    text: str
