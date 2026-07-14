# =============================================================================
# report_render/report_source.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Berichts-Ausgabe
# =============================================================================
# Zweck:
#   Baut aus den Datenbanken das format-neutrale ReportDocument. Dies ist die
#   EINZIGE Stelle, die Datenbanken liest; die Renderer sehen danach nur noch
#   das Modell (Bauplan Build 397 §2).
#
#   Serverunabhaengig: bekommt DB-Wrapper (EvidenceDb/AssetsDb/TemplatesDb) und
#   die forensische Verbindung (fdb) herein — KEIN http, KEIN ResolvedContext,
#   KEIN DatabaseBundle. Damit sowohl vom forensischen Webserver als auch vom
#   Management-Server nutzbar.
#
#   Entscheidungen (mc 2026-07-13):
#     §4.1 Berichtswahl: explizite report_id hat Vorrang; fehlt sie, wird der
#          Bericht mit der HOECHSTEN sequence_nr gewaehlt (Gleichstand ->
#          juengstes created_at). report_type filtert NICHT (nur Kopf-Info).
#     §4.2 Bilder: KEINE Bild-Bytes im Export (§§184b/184c — die Akte darf nicht
#          selbst Traeger inkriminierender Inhalte werden). Stattdessen ein
#          forensisch harter VERWEIS (url + Existenzpruefung). content_hash/
#          share_id: Restpunkt, siehe unten.
#
#   Grundregel 1: Ordnungslose Bloecke, fehlende Bilder, unaufloesbare Platzhalter
#   werden NIE still uebergangen, sondern landen als DocWarning im Dokument.
#
#   Migrationsvorbehalt: Dieses Modul LIEST NUR. Kein Schreibpfad in
#   evidence_<uid>.db -> kein Migrationsvorbehalt beruehrt.
#
#   Build 402: Aufloesung in BEIDE Modi (html+plain) via resolver.resolve_both;
#   BLOB-freie Bild-Anreicherung via AssetsDb.get_asset_reference.
#   Build 403: {{a:}}-Aufloesung ueber gemeinsamen Kern report_render/auto_query.py
#   (write_cache=False -> Export schreibt nicht in evidence_<uid>.db).
#
# Version: v0.7.403 · Build: 403 · 2026-07-14
# =============================================================================

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from report_render.report_document import (
    ReportDocument,
    RenderedBlock,
    WARN_UNORDERED_BLOCK,
    WARN_UNKNOWN_BLOCK_TYPE,
    WARN_MISSING_IMAGE,
)
from report_render.placeholder_resolver import PlaceholderResolver
from report_render.auto_query import AutoQueryResolver

# -----------------------------------------------------------------------------
# Die neun bekannten Blocktypen (Editor.js-Toolnamen).
# Beleg: Bauplan Build 397 §1 B5; forensic_api/editor_block.py Kopf.
# Ein zehnter Typ wird gemeldet, nicht uebersprungen (R3).
# -----------------------------------------------------------------------------
KNOWN_BLOCK_TYPES: frozenset[str] = frozenset({
    "paragraph", "header", "list", "table",
    "quote", "image", "delimiter", "marker", "evidence",
})


class NoReportError(Exception):
    """Wird geworfen, wenn kein exportierbarer Bericht existiert.
    Der aufrufende Server uebersetzt das in HTTP 404."""


class ReportSource:
    """Liest die Datenbanken und erzeugt ein ReportDocument.

    Args:
        evidence:     EvidenceDb-Instanz (report_blocks, report_block_order, Anker, Cache).
        templates:    TemplatesDb-Instanz (placeholder_queries) — darf None sein.
        assets:       AssetsDb-Instanz (Bild-Existenzpruefung) — darf None sein.
        forensic_con: sqlite3.Connection mit ATTACH-Alias 'fdb' fuer {{a:}}-Queries
                      — darf None sein (dann sind {{a:}} nicht auflösbar -> Warnung).
        uid:          User-ID des Beschuldigten (fuer Cache/Query-Parametrisierung).
        username:     Anzeigename fuer den Statuskopf.
        generated_at: Unix-Zeitstempel (von aussen gesetzt — das Modul ruft nie now()).
    """

    def __init__(
        self,
        evidence: Any,
        templates: Any,
        assets: Any,
        forensic_con: Optional[sqlite3.Connection],
        uid: int,
        username: str,
        generated_at: int,
    ) -> None:
        self._edb = evidence
        self._tdb = templates
        self._adb = assets
        self._fcon = forensic_con
        self._uid = uid
        self._username = username
        self._generated_at = generated_at
        # Build 403: gemeinsamer {{a:}}-Kern. write_cache=False -> der Export LIEST
        # den placeholder_cache nur, SCHREIBT aber NICHT in evidence_<uid>.db
        # (streng lese-only, respektiert den Migrationsvorbehalt).
        self._auto = AutoQueryResolver(evidence, templates, forensic_con, write_cache=False)

    # ------------------------------------------------------------------
    # Auto-Aufloesung {{a:name}} — delegiert an den gemeinsamen Kern
    # report_render/auto_query.py (Build 403, De-Duplizierung gegen
    # forensic_api/placeholders.py). None => nicht auflösbar (unresolved, R2).
    # ------------------------------------------------------------------
    def _resolve_auto(self, name: str) -> Optional[str]:
        """Wert eines {{a:name}} oder None (no_query/sql_error). "" bei leerem
        Query-Ergebnis. Schreibt NICHT in den Cache (write_cache=False)."""
        return self._auto.resolve_value_or_none(name, self._uid)

    # ------------------------------------------------------------------
    # Berichtswahl (§4.1)
    # ------------------------------------------------------------------
    def _select_report(self, report_id: Optional[int]) -> Any:
        if report_id is not None:
            rec = self._edb.get_report(report_id)
            if rec is None:
                raise NoReportError(f"Bericht mit report_id={report_id} nicht gefunden.")
            return rec
        reports = self._edb.get_reports()
        if not reports:
            raise NoReportError("Kein Bericht vorhanden.")
        # Hoechste sequence_nr; Gleichstand -> juengstes created_at (mc §4.1).
        return max(reports, key=lambda r: (r.sequence_nr, r.created_at))

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def build(self, report_id: Optional[int] = None) -> ReportDocument:
        """Erzeugt das ReportDocument fuer den gewaehlten Bericht."""
        rec = self._select_report(report_id)

        doc = ReportDocument(
            report_id=rec.id,
            report_type=rec.report_type,
            sequence_nr=rec.sequence_nr,
            title=rec.title,
            status=rec.status,
            uid=self._uid,
            username=self._username,
            generated_at=self._generated_at,
        )

        # Ein Resolver je Dokument (dokumentinterner {{a:}}-Cache).
        resolver = PlaceholderResolver(resolve_auto=self._resolve_auto)

        # Bloecke (bereits sort_index-sortiert; ordnungslose ans Ende).
        blocks = self._edb.get_blocks_for_report(rec.id)

        # Menge der Bloecke MIT Sortierungseintrag -> ordnungslose erkennen (R2).
        ordered_ids = {
            e["block_id"] for e in self._edb.get_block_order_for_report(rec.id)
        }

        for blk in blocks:
            if blk.block_id not in ordered_ids:
                doc.add_warning(
                    WARN_UNORDERED_BLOCK,
                    f"Block ohne Sortierungseintrag (block_type={blk.block_type})",
                    block_id=blk.block_id,
                )
            doc.blocks.append(self._build_block(blk, resolver, doc))

        return doc

    # ------------------------------------------------------------------
    def _build_block(self, blk: Any, resolver: PlaceholderResolver, doc: ReportDocument) -> RenderedBlock:
        """Baut einen RenderedBlock inkl. Platzhalter-Aufloesung und Ankern."""
        # block_data (JSON) defensiv parsen.
        try:
            data = json.loads(blk.block_data) if blk.block_data else {}
            if not isinstance(data, dict):
                data = {"_raw": blk.block_data}
        except (ValueError, TypeError):
            data = {"_raw": blk.block_data}

        # placeholder_values_json defensiv parsen.
        try:
            values = json.loads(blk.placeholder_values_json) if blk.placeholder_values_json else {}
            if not isinstance(values, dict):
                values = {}
        except (ValueError, TypeError):
            values = {}

        is_known = blk.block_type in KNOWN_BLOCK_TYPES
        if not is_known:
            # R3: unbekannter Blocktyp -> gemeldet, nicht uebersprungen.
            doc.add_warning(
                WARN_UNKNOWN_BLOCK_TYPE,
                f"Unbekannter Blocktyp '{blk.block_type}'",
                block_id=blk.block_id,
            )

        rb = RenderedBlock(
            block_id=blk.block_id,
            block_type=blk.block_type,
            data=dict(data),   # Kopie; wir ergaenzen _resolved_* Felder
            is_known_type=is_known,
        )

        # Anker (Fussnoten) laden.
        try:
            rb.anchors = self._edb.get_anchors_for_block(blk.block_id)
        except Exception:
            rb.anchors = []

        # Kleiner Helfer: String in BEIDE Modi aufloesen (Build 402) und Warnungen
        # einsammeln. Rueckgabe (html, plain). resolve_both loest {{a:}} nur einmal auf.
        def rs(text: Any) -> tuple[str, str]:
            if text is None:
                return "", ""
            h, p, warns = resolver.resolve_both(str(text), values, block_id=blk.block_id)
            doc.warnings.extend(warns)
            return h, p

        bt = blk.block_type
        # Einfache Textbloecke -> resolved_text (+ _plain fuer DOCX/SQLite).
        if bt in ("paragraph", "header", "quote", "marker"):
            rb.resolved_text, rb.resolved_text_plain = rs(data.get("text", ""))
            if bt == "quote":
                ch, cp = rs(data.get("caption", ""))
                rb.data["_resolved_caption"] = ch
                rb.data["_resolved_caption_plain"] = cp
        # Liste -> jedes Item aufloesen (html + plain).
        elif bt == "list":
            items = data.get("items", []) if isinstance(data.get("items"), list) else []
            pairs = [rs(it) for it in items]
            rb.data["_resolved_items"] = [h for h, _ in pairs]
            rb.data["_resolved_items_plain"] = [p for _, p in pairs]
        # Tabelle -> jede Zelle aufloesen (html + plain).
        elif bt == "table":
            content = data.get("content", []) if isinstance(data.get("content"), list) else []
            grid = [[rs(cell) for cell in row] for row in content]
            rb.data["_resolved_rows"] = [[h for h, _ in row] for row in grid]
            rb.data["_resolved_rows_plain"] = [[p for _, p in row] for row in grid]
        # Bild -> VERWEIS statt Einbettung (§4.2).
        elif bt == "image":
            self._build_image_reference(rb, data, doc, rs)
        # delimiter -> kein Inhalt.
        # evidence -> Verweise auf Annotationen; Text (falls vorhanden) aufloesen.
        elif bt == "evidence":
            rb.resolved_text, rb.resolved_text_plain = rs(data.get("text", ""))
            # evidence_ids unveraendert im data-Feld belassen (Renderer listet sie).
        else:
            # unbekannter Typ: vorhandenen 'text' defensiv aufloesen (GR1).
            if "text" in data:
                rb.resolved_text, rb.resolved_text_plain = rs(data.get("text", ""))

        return rb

    # ------------------------------------------------------------------
    def _build_image_reference(self, rb: RenderedBlock, data: dict, doc: ReportDocument, rs: Any) -> None:
        """§4.2: Bild NICHT einbetten, sondern forensisch harten Verweis erzeugen.

        - url: Quelle aus dem Editor.js-SimpleImage-Block (data['url'] bzw.
               data['file']['url']).
        - caption wird (falls vorhanden) platzhalter-aufgeloest (html + plain).
        - BLOB-FREIE Anreicherung (Build 402, mc §9.3): ueber
          AssetsDb.get_asset_reference(url) werden url_hash, asset_id, mime_type
          und file_size geladen — OHNE die Bild-Bytes (a.data) zu ziehen. Das ist
          im §§184b/184c-Kontext bewusst so: der Export-Prozess beruehrt den
          inkriminierenden Inhalt nie. url_hash + asset_id + file_size bilden den
          stabilen, re-lokalisierbaren Anker. (Ein separater 'content_hash'/
          'share_id'-Spaltenname ist im zugaenglichen assets_<uid>.db-Schema nicht
          belegt — asset_urls: url,url_hash,asset_id,url_context,page_id;
          assets: id,data,mime_type,file_size. Beleg: db/assets_db.py Kopf/Join.)
        - Fehlt das Asset -> WARN_MISSING_IMAGE (GR1).
        """
        url = data.get("url")
        if not url and isinstance(data.get("file"), dict):
            url = data["file"].get("url")
        url = str(url or "")
        rb.data["_image_url"] = url
        ch, cp = rs(data.get("caption", ""))
        rb.data["_resolved_caption"] = ch
        rb.data["_resolved_caption_plain"] = cp

        ref = None
        if url and self._adb is not None:
            # Bevorzugt die BLOB-freie Referenzmethode (Build 402); faellt auf
            # has_asset() zurueck, falls eine aeltere AssetsDb im Einsatz ist.
            getref = getattr(self._adb, "get_asset_reference", None)
            try:
                if callable(getref):
                    ref = getref(url)
                elif hasattr(self._adb, "has_asset") and self._adb.has_asset(url):
                    ref = {}
            except Exception:
                ref = None

        exists = ref is not None
        rb.data["_image_available"] = exists
        if exists and isinstance(ref, dict):
            # Nur belegte, BLOB-freie Anker uebernehmen.
            rb.data["_image_url_hash"] = ref.get("url_hash")
            rb.data["_image_asset_id"] = ref.get("asset_id")
            rb.data["_image_mime"] = ref.get("mime_type")
            rb.data["_image_size"] = ref.get("file_size")
        if not exists:
            doc.add_warning(
                WARN_MISSING_IMAGE,
                f"Bild-Verweis nicht in assets_<uid>.db auffindbar: {url or '(keine URL)'}",
                block_id=rb.block_id,
            )
