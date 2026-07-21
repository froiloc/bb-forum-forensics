# =============================================================================
# management/templates_admin/report_template_extractor.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — Build 475: "Bericht als Vorlage uebernehmen"
# =============================================================================
# Zweck:
#   Erzeugt aus einem BESTEHENDEN Bericht (Baustelle 6, evidence_<uid>.db) den
#   ENTWURF einer wiederverwendbaren Dokumentvorlage (templates.db.report_templates).
#   Dieses Modul LIEST NUR — es schreibt weder evidence_<uid>.db noch templates.db.
#   Das Speichern erledigt der Mensch spaeter ueber den bestehenden auditierten
#   Pfad (POST /api/templates/document -> TemplateAuthorRepo.upsert). So bleibt
#   der einzige Schreib-/Audit-Weg zu templates.db unveraendert (kein zweiter
#   Schreibpfad), und der Migrationsvorbehalt ist nicht beruehrt.
#
# SANITISIERUNG (Kernentscheidung, Bauplan v0.2 §3.1; Festlegung mc 2026-07-21):
#   Der FALLBEZOGENE Inhalt eines Berichts lebt AUSSCHLIESSLICH in den
#   Platzhalter-WERTEN. Die aufgeloesten m:/o:-Overrides und die gecachten
#   {{a:}}-Query-Ergebnisse stehen in der SPALTE report_blocks.placeholder_values_json
#   (Beleg: forensic_api/placeholders.py:123, 201-244; report.py:391-421). Die
#   block_data selbst traegt nur die neutralen Platzhalter-TOKEN ({{a:}}/{{m:}}/
#   {{o:}}) und die (fallfreie) Struktur (Beleg: report_source.build() loest
#   data['text'] erst gegen 'values' aus placeholder_values_json auf).
#
#   Deshalb gilt: der Extraktor LIEST placeholder_values_json GAR NICHT und
#   uebernimmt je Block nur {block_type, block_data}. Damit sind ALLE
#   Platzhalter-Werte entfernt; die Vorlage zeigt spaeter leere {{...}}-Chips,
#   die im neuen Fall neu gefuellt werden (Round-Trip ueber
#   forensic_api/report.py::insert_template, das Platzhalter bewusst NICHT
#   aufloest).
#
#   SONDERFALL evidence-Block: dessen block_data traegt eine Liste 'evidence_ids'
#   (fallgebundene Verweise auf Annotationen; Beleg: report_render/html_renderer.py
#   :256-263). Das ist KEIN Platzhalter und wuerde beim bloszen "Platzhalter
#   leeren" ueberleben. Festlegung mc 2026-07-21: der evidence-WRAPPER
#   (Beweismittelgruppe) BLEIBT als Struktur erhalten, seine 'evidence_ids'
#   werden aber auf [] gesetzt. So zeigt die Vorlage "hier werden Belege
#   gesammelt dargestellt", ohne fallgebundene Verweise zu tragen.
#
# GRUNDREGEL 1 (kein stiller Verlust): JEDE Entfernung wird als 'finding'
#   gemeldet, ordnungslose/unbekannte Bloecke als 'warning'. Kein Block wird
#   still uebersprungen; unlesbare block_data wird als _raw erhalten und gemeldet.
#
# Version: v0.8.475 · Build: 475 · 2026-07-21
# =============================================================================

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

# Einzige Wahrheit fuer die zulaessigen Blocktypen (kein Duplikat-Katalog).
# Deckungsgleich mit template_validator/report_source (Beleg B2).
from report_render.report_source import KNOWN_BLOCK_TYPES

# Zulaessige Berichtstypen der Vorlage (Spiegel des report_templates-CHECK).
_VALID_REPORT_TYPES = ("interim", "final", "addendum")

# Neutraler, editierbarer Default-Schluessel (kein Fallbezug; Festlegung
# mc 2026-07-21). Zeichenraum deckungsgleich mit template_validator._KEY_RE.
DEFAULT_TEMPLATE_KEY = "vorlage-aus-bericht"


class NoReportForTemplateError(Exception):
    """Kein uebernehmbarer Bericht vorhanden. Der Aufrufer uebersetzt das in
    HTTP 404 (Grundregel 1: sichtbarer Zustand statt leerer Erfolg)."""


class ReportTemplateExtractor:
    """Baut aus einem Bericht (evidence_<uid>.db) einen Vorlagen-ENTWURF.

    Args:
        evidence: EvidenceDb-Instanz (read-only genuegt) — liefert get_report(s),
                  get_blocks_for_report, get_block_order_for_report.
    """

    def __init__(self, evidence: Any) -> None:
        self._edb = evidence

    # ------------------------------------------------------------------
    # Berichtswahl — Paritaet zu report_render.report_source._select_report:
    # explizite report_id hat Vorrang; sonst hoechste sequence_nr, Gleichstand
    # -> juengstes created_at. (Beleg: report_source.py §4.1.)
    # ------------------------------------------------------------------
    def _select_report(self, report_id: Optional[int]) -> Any:
        if report_id is not None:
            rec = self._edb.get_report(report_id)
            if rec is None:
                raise NoReportForTemplateError(
                    "Bericht mit report_id=%s nicht gefunden." % report_id)
            return rec
        reports = self._edb.get_reports()
        if not reports:
            raise NoReportForTemplateError("Kein Bericht vorhanden.")
        return max(reports, key=lambda r: (r.sequence_nr, r.created_at))

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_block_data(raw: Optional[str]) -> tuple[Dict[str, Any], bool]:
        """block_data (JSON-String) defensiv als dict parsen. Gibt (data, ok).
        Unlesbares/nicht-objektartiges JSON -> ({'_raw': raw}, False), damit der
        Inhalt NICHT still verloren geht (GR1) und der Block dennoch als Objekt
        (template_validator verlangt block_data: dict) speicherbar bleibt."""
        if raw is None or str(raw).strip() == "":
            return {}, True
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return {"_raw": str(raw)}, False
        if not isinstance(parsed, dict):
            return {"_raw": str(raw)}, False
        return parsed, True

    @staticmethod
    def _count_placeholder_values(raw: Optional[str]) -> int:
        """Zaehlt die (fallbezogenen) Platzhalter-Werte eines Blocks — nur fuer
        den Befund ('so viele Werte wurden NICHT uebernommen'). Rein informativ;
        die Werte selbst werden nie in die Vorlage geschrieben."""
        if not raw:
            return 0
        try:
            values = json.loads(raw)
        except (ValueError, TypeError):
            return 0
        return len(values) if isinstance(values, dict) else 0

    @staticmethod
    def _suggest_title(report_title: Optional[str]) -> str:
        t = str(report_title or "").strip()
        return ("Vorlage aus Bericht: %s" % t) if t else "Vorlage aus Bericht"

    # ------------------------------------------------------------------
    def build_draft(self, report_id: Optional[int] = None) -> Dict[str, Any]:
        """Erzeugt den Vorlagen-Entwurf. Rueckgabe:
            {report_id, draft:{template_key,title,report_type,blocks},
             findings:[...], warnings:[...]}
        findings dokumentieren jede Sanitisierung (GR1), warnings jede
        Auffaelligkeit (ordnungslos/unbekannt/unlesbar)."""
        rec = self._select_report(report_id)

        blocks = self._edb.get_blocks_for_report(rec.id)
        # Menge der Bloecke MIT Sortierungseintrag -> ordnungslose erkennen (GR1),
        # Paritaet zu report_source.build().
        ordered_ids = {
            e["block_id"] for e in self._edb.get_block_order_for_report(rec.id)
        }

        draft_blocks: List[Dict[str, Any]] = []
        findings: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []

        for idx, blk in enumerate(blocks):
            btype = blk.block_type

            if blk.block_id not in ordered_ids:
                warnings.append({
                    "block_index": idx, "block_type": btype,
                    "code": "unordered_block",
                    "detail": "Block ohne Sortierungseintrag (ans Ende gestellt).",
                })
            if btype not in KNOWN_BLOCK_TYPES:
                # R3/GR1: unbekannter Typ wird gemeldet, NICHT verworfen.
                warnings.append({
                    "block_index": idx, "block_type": btype,
                    "code": "unknown_block_type",
                    "detail": "Unbekannter Blocktyp '%s'." % btype,
                })

            data, ok = self._parse_block_data(blk.block_data)
            if not ok:
                warnings.append({
                    "block_index": idx, "block_type": btype,
                    "code": "block_data_unparsable",
                    "detail": "block_data war unlesbar und wurde als _raw erhalten.",
                })

            # KERNREGEL: placeholder_values_json wird NICHT gelesen/uebernommen
            # -> alle fallbezogenen Platzhalter-Werte sind entfernt. Nur ein
            # informativer Befund, wie viele Werte das betraf.
            n_vals = self._count_placeholder_values(blk.placeholder_values_json)
            if n_vals:
                findings.append({
                    "block_index": idx, "block_type": btype,
                    "action": "placeholder_values_cleared",
                    "detail": "%d Platzhalter-Wert(e) nicht uebernommen." % n_vals,
                })

            # SONDERFALL evidence: Wrapper behalten, evidence_ids leeren.
            if btype == "evidence" and isinstance(data.get("evidence_ids"), list):
                n_ev = len(data["evidence_ids"])
                if n_ev:
                    findings.append({
                        "block_index": idx, "block_type": "evidence",
                        "action": "evidence_ids_cleared",
                        "detail": "%d Beleg-Verweis(e) entfernt (Wrapper bleibt)."
                                  % n_ev,
                    })
                data["evidence_ids"] = []

            draft_blocks.append({"block_type": btype, "block_data": data})

        report_type = rec.report_type if rec.report_type in _VALID_REPORT_TYPES \
            else "interim"

        draft = {
            "template_key": DEFAULT_TEMPLATE_KEY,
            "title": self._suggest_title(rec.title),
            "report_type": report_type,
            "blocks": draft_blocks,
        }
        return {
            "report_id": rec.id,
            "draft": draft,
            "findings": findings,
            "warnings": warnings,
        }
