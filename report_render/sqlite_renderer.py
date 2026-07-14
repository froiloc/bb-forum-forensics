# =============================================================================
# report_render/sqlite_renderer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Berichts-Ausgabe
# =============================================================================
# Zweck:
#   Rendert ein ReportDocument in eine selbstenthaltende, selbsterklaerende
#   SQLite3-Datenbank (Fallakte-Bericht). Sieht NUR das ReportDocument (Bauplan §2).
#
#   INHALT (bericht-fokussiert): meta, report_blocks (in Ausgabereihenfolge, als
#   reiner Text), report_anchors, report_warnings (R2!), README.
#
#   BEWUSSTE ABGRENZUNG (dokumentiert, GR1 — nicht still):
#     Der Alt-Export v0.6.097 fuellte zusaetzlich profile_summary/known_aliases/
#     network_summary/activity_stats/timeline_summary aus der forensic_db (fdb).
#     Diese Tabellen sind NICHT Teil des blockbasierten Berichts und wurden aus
#     dem Modell (das nur den Bericht kennt) bewusst NICHT uebernommen — der
#     Renderer bleibt datenbank-neutral (Bauplan §2). Der Alt-Pfad war seit dem
#     Editor.js-Umbau ohnehin tot (Befund B1), es gibt also keinen funktionierenden
#     Stand, von dem hier abgewichen wuerde. Ob ein separater, fdb-gespeister
#     "Fallakte-Gesamtexport" gewuenscht ist, ist ein offener mc-Punkt (build.json 402).
#
#   R2: report_warnings enthaelt ALLE Warnungen — kein stiller Verlust.
#
# Version: v0.7.402 · Build: 402 · 2026-07-14
# =============================================================================

from __future__ import annotations

import sqlite3

from report_render.report_document import ReportDocument, RenderedBlock

CLASSIFICATION = "VERTRAULICH — IT-FORENSISCHES ERMITTLUNGSWERKZEUG NRW"
TOOL_VERSION = "aiw_webserver v0.7.402"


class SqliteRenderer:
    """ReportDocument -> bytes (selbstenthaltende SQLite3-.db)."""

    def render(self, doc: ReportDocument) -> bytes:
        con = sqlite3.connect(":memory:")
        try:
            self._build(con, doc)
            con.commit()
            return self._serialize(con)
        finally:
            con.close()

    # ------------------------------------------------------------------
    def _build(self, con: sqlite3.Connection, doc: ReportDocument) -> None:
        con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        for k, v in [
            ("uid", str(doc.uid)), ("username", doc.username),
            ("report_id", str(doc.report_id)), ("report_type", doc.report_type),
            ("sequence_nr", str(doc.sequence_nr)), ("title", doc.title),
            ("status", doc.status), ("generated_at", str(doc.generated_at)),
            ("block_count", str(len(doc.blocks))), ("anchor_count", str(doc.anchor_count)),
            ("warning_count", str(len(doc.warnings))),
            ("tool_version", TOOL_VERSION), ("classification", CLASSIFICATION),
        ]:
            con.execute("INSERT INTO meta VALUES (?, ?)", (k, v))

        con.execute(
            "CREATE TABLE report_blocks ("
            " position INTEGER NOT NULL,"      # Ausgabereihenfolge (0-basiert)
            " block_id TEXT NOT NULL,"
            " block_type TEXT NOT NULL,"
            " is_known_type INTEGER NOT NULL," # 1=bekannt, 0=unbekannt (R3)
            " content TEXT,"                   # reiner Text (Platzhalter aufgeloest)
            " image_url TEXT,"                 # nur bei block_type='image' (Verweis, §4.2)
            " image_available INTEGER)"        # 1/0/NULL
        )
        for pos, blk in enumerate(doc.blocks):
            img_url = blk.data.get("_image_url") if blk.block_type == "image" else None
            img_av = None
            if blk.block_type == "image":
                img_av = 1 if blk.data.get("_image_available") else 0
            con.execute(
                "INSERT INTO report_blocks VALUES (?, ?, ?, ?, ?, ?, ?)",
                (pos, blk.block_id, blk.block_type,
                 1 if blk.is_known_type else 0,
                 self._block_plain(blk), img_url, img_av),
            )

        con.execute(
            "CREATE TABLE report_anchors ("
            " block_id TEXT NOT NULL, anchor_id INTEGER, annotation_id INTEGER,"
            " anchor_text TEXT)"
        )
        for blk in doc.blocks:
            for a in blk.anchors:
                con.execute(
                    "INSERT INTO report_anchors VALUES (?, ?, ?, ?)",
                    (blk.block_id, getattr(a, "id", None),
                     getattr(a, "annotation_id", None), getattr(a, "anchor_text", "")),
                )

        con.execute(
            "CREATE TABLE report_warnings (kind TEXT NOT NULL, detail TEXT, block_id TEXT)"
        )
        for w in doc.warnings:
            con.execute("INSERT INTO report_warnings VALUES (?, ?, ?)",
                        (w.kind, w.detail, w.block_id))

        con.execute("CREATE TABLE README (key TEXT PRIMARY KEY, value TEXT)")
        for k, v in [
            ("beschreibung",
             "Selbstenthaltender Berichts-Export des IT-forensischen Ermittlungs"
             "werkzeugs NRW. Enthaelt den Bericht eines Beschuldigten als reinen "
             "Text (Platzhalter aufgeloest), seine Beweisanker und die "
             "Erzeugungs-Warnungen."),
            ("tabelle_meta", "Metadaten des Berichts und des Exports."),
            ("tabelle_report_blocks",
             "Alle Bloecke in Ausgabereihenfolge (position). content = reiner Text. "
             "Bilder sind VERWEISE (image_url), NICHT eingebettet (§§184b/184c)."),
            ("tabelle_report_anchors", "Beweisanker je Block (Verweise auf Annotationen)."),
            ("tabelle_report_warnings",
             "Alle Warnungen der Erzeugung (nicht auflösbare Platzhalter, "
             "ordnungslose Bloecke, unbekannte Blocktypen, fehlende Bilder). "
             "Kein Beleg wird still uebergangen."),
            ("hinweis_fdb_tabellen",
             "profile_summary/known_aliases/network_summary/activity_stats/"
             "timeline_summary des Alt-Exports sind hier NICHT enthalten — sie "
             "sind nicht Teil des blockbasierten Berichts (offener mc-Punkt)."),
            ("klassifizierung", CLASSIFICATION),
        ]:
            con.execute("INSERT INTO README VALUES (?, ?)", (k, v))

    # ------------------------------------------------------------------
    def _block_plain(self, blk: RenderedBlock) -> str:
        """Reiner-Text-Inhalt eines Blocks fuer die DB-Spalte 'content'."""
        bt = blk.block_type
        if bt in ("paragraph", "header", "marker", "evidence"):
            base = blk.resolved_text_plain
            if bt == "evidence":
                ev = blk.data.get("evidence_ids", [])
                if isinstance(ev, list) and ev:
                    base = (base + "\n" if base else "") + "Beweis-IDs: " + ", ".join(str(e) for e in ev)
            return base
        if bt == "quote":
            cap = blk.data.get("_resolved_caption_plain", "")
            return blk.resolved_text_plain + (f"\n— {cap}" if cap else "")
        if bt == "list":
            items = blk.data.get("_resolved_items_plain", [])
            return "\n".join(f"- {it}" for it in items)
        if bt == "table":
            rows = blk.data.get("_resolved_rows_plain", [])
            return "\n".join("\t".join(r) for r in rows)
        if bt == "image":
            url = blk.data.get("_image_url", "")
            av = blk.data.get("_image_available", False)
            cap = blk.data.get("_resolved_caption_plain", "")
            s = f"[Bildverweis: {url or '(keine URL)'} | verfuegbar={bool(av)}]"
            return s + (f"\n{cap}" if cap else "")
        if bt == "delimiter":
            return "———"
        # unbekannter/sonstiger Typ
        return blk.resolved_text_plain or ""

    # ------------------------------------------------------------------
    def _serialize(self, con: sqlite3.Connection) -> bytes:
        """SQLite-DB als Bytes. serialize() ab Python 3.11+; sonst tempfile-Fallback."""
        try:
            return con.serialize()
        except AttributeError:      # pragma: no cover - sehr alte Python
            import os
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                bck = sqlite3.connect(tmp_path)
                con.backup(bck)
                bck.close()
                with open(tmp_path, "rb") as f:
                    return f.read()
            finally:
                os.unlink(tmp_path)
