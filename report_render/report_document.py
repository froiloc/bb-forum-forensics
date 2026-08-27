# =============================================================================
# report_render/report_document.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Berichts-Ausgabe
# =============================================================================
# Zweck:
#   Das *neutrale Zwischenmodell* der Berichts-Ausgabe. Es ist der Angelpunkt
#   der Architektur (Bauplan Build 397 §2): Jeder Renderer (HTML in Build 399,
#   DOCX/SQLite in 402, PDF in 404) sieht AUSSCHLIESSLICH dieses Modell und
#   NIE eine Datenbank. Ein neues Ausgabeformat ist damit eine neue Datei und
#   kein Umbau.
#
#   Bewusste Entwurfsentscheidung (serverunabhaengig):
#     Dieses Modul importiert weder http_server noch ResolvedContext noch
#     DatabaseBundle. Es kennt nur Standard-Datentypen. Dadurch ist es sowohl
#     vom forensischen Webserver (forensic_api/export.py) als auch spaeter vom
#     Management-Server nutzbar, ohne dass Renderlogik dupliziert wird.
#     Beleg: Bauplan Build 397 §2 ("ein Modul, zwei Server").
#
#   Zeitstempel-Invariante:
#     'generated_at' wird von AUSSEN gesetzt (der aufrufende Server liefert den
#     Unix-Zeitstempel). Das Modul ruft selbst NIE datetime.now() auf — so bleibt
#     es rein und deterministisch testbar.
#
# Grundregeln: GR6 (Kommentieren von Intention), GR10 (eine Klasse je Datei-Zweck).
# Beleg: mc-Festlegungen 2026-07-13; Feinabnahme Build 399 v0.1 §2.
# Version: v0.7.402 · Build: 402 · 2026-07-14 (RenderedBlock.resolved_text_plain ergaenzt)
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# -----------------------------------------------------------------------------
# Warnungs-Arten.
# Zweck: Grundregel 1 ("Kein Beleg darf je still uebersprungen werden") wird
# technisch durchgesetzt, indem JEDE Auffaelligkeit als DocWarning sichtbar am
# Dokumentende landet, statt still zu verschwinden.
# Beleg: Bauplan Build 397 §3 R2/R3.
# -----------------------------------------------------------------------------
WARN_UNRESOLVED_PLACEHOLDER = "unresolved_placeholder"  # {{a:}}/{{m:}} ohne Wert -> Default
WARN_UNKNOWN_PLACEHOLDER    = "unknown_placeholder"     # {{...}} das dem Muster nicht entspricht
WARN_UNORDERED_BLOCK        = "unordered_block"         # Block ohne report_block_order-Eintrag
WARN_UNKNOWN_BLOCK_TYPE     = "unknown_block_type"      # Blocktyp ausserhalb der 9 bekannten (B5)
WARN_MISSING_IMAGE          = "missing_image"           # image-Verweis nicht in assets_<uid>.db
# Build 725 (Vollzitat): alles, was beim Aufbau einer Beweismittelgruppe
# unvollstaendig blieb - ein Beleg ohne Annotation, ein nicht auffindbarer
# Absatz, ein fehlender Themenbetreff, ein nicht benennbarer PN-Partner.
#
# EINE EIGENE ART UND KEINE VERTEILUNG AUF DIE BESTEHENDEN: Diese Warnungen
# betreffen die BELEGLAGE, nicht die Erzeugung des Dokuments. Wer eine Akte
# prueft, liest sie anders als einen nicht aufgeloesten Platzhalter - sie
# sagen, welche Aussage im Bericht auf welcher Grundlage steht. Sie in
# 'unresolved_placeholder' zu werfen haette sie darin verschwinden lassen.
WARN_EVIDENCE_GAP           = "evidence_gap"            # Beleglage unvollstaendig (Vollzitat)

#: Alle gueltigen Warn-Arten (fuer Validierung/Tests).
VALID_WARNING_KINDS: frozenset[str] = frozenset({
    WARN_UNRESOLVED_PLACEHOLDER,
    WARN_UNKNOWN_PLACEHOLDER,
    WARN_UNORDERED_BLOCK,
    WARN_UNKNOWN_BLOCK_TYPE,
    WARN_MISSING_IMAGE,
    WARN_EVIDENCE_GAP,
})


@dataclass
class DocWarning:
    """Eine sichtbar zu machende Auffaelligkeit bei der Berichtserzeugung.

    kind     — eine der WARN_*-Konstanten.
    detail   — menschenlesbarer Text, z.B. "{{a:user.username}}" oder ein Blocktyp.
    block_id — betroffener Block (falls zuordenbar), sonst None.
    """
    kind:     str
    detail:   str
    block_id: Optional[str] = None


@dataclass
class RenderedBlock:
    """Ein fuer die Ausgabe aufbereiteter Berichtsblock.

    block_type    — Editor.js-Toolname (einer der 9 aus B5) oder ein unbekannter.
    resolved_text — der bereits platzhalter-aufgeloeste Rohtext (NICHT HTML-escaped!);
                    die Escaping-Verantwortung liegt beim jeweiligen Renderer, damit
                    jedes Format (HTML/DOCX/PDF) korrekt und einmalig escapen kann.
                    Fuer strukturierte Bloecke (list/table/image ...) bleibt dieses
                    Feld leer und 'data' traegt die Struktur.
    data          — das (ggf. platzhalter-aufgeloeste) Editor.js-Datenobjekt des Blocks.
    anchors       — Beweisanker (ReportAnchorRecord-aehnliche Objekte) dieses Blocks.
    is_known_type — False, wenn block_type keiner der 9 bekannten Typen ist (R3).
    """
    block_id:      str
    block_type:    str
    resolved_text: str = ""            # HTML-Fragment (mode='html')
    resolved_text_plain: str = ""      # reiner Text (mode='text', Build 402: DOCX/SQLite)
    data:          dict = field(default_factory=dict)
    anchors:       list = field(default_factory=list)
    is_known_type: bool = True


@dataclass
class ReportDocument:
    """Das vollstaendige, format-neutrale Berichtsdokument.

    Enthaelt alle Metadaten fuer den Statuskopf (R1), die aufbereiteten Bloecke
    in Ausgabereihenfolge und die gesammelten Warnungen fuer den Abschnitt
    "Hinweise zur Erzeugung" (R2).
    """
    # --- Metadaten (Statuskopf R1) ---
    report_id:    int
    report_type:  str          # 'interim' | 'final' | 'addendum'
    sequence_nr:  int
    title:        str
    status:       str          # 'draft' | 'submitted' | 'approved' | 'final'
    uid:          int
    username:     str
    generated_at: int          # Unix-Zeitstempel, von aussen gesetzt (siehe Kopfkommentar)

    # --- Inhalt ---
    blocks:   list = field(default_factory=list)   # list[RenderedBlock]
    warnings: list = field(default_factory=list)   # list[DocWarning]

    # -- kleine, formatunabhaengige Hilfen (keine Renderlogik!) --

    def add_warning(self, kind: str, detail: str, block_id: Optional[str] = None) -> None:
        """Haengt eine Warnung an. Zentral, damit kein Aufrufer sie 'vergisst'."""
        self.warnings.append(DocWarning(kind=kind, detail=detail, block_id=block_id))

    @property
    def anchor_count(self) -> int:
        """Gesamtzahl der Beweisanker ueber alle Bloecke (fuer die Hinweise)."""
        return sum(len(b.anchors) for b in self.blocks)
