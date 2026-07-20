# =============================================================================
# forensic_api/annotate.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/annotate
#
#   POST  — Annotation anlegen / aktualisieren (upsert via local_id)
#   DELETE — Annotation löschen (anhand Server-ID)
#
# POST Request-Body (JSON):
#   {
#     "page_url":      "/forum/viewtopic.php?id=42",   (Pflicht)
#     "category":      "CAT_PERSON",                   (Pflicht)
#     "text":          "Erwähnt Vorname Klaus",         (optional, Default "")
#     "element_id":    "p12345",                        (optional)
#     "local_id":      "uuid-v4-string",                (optional, Browser-UUID)
#     "post_id":       12345,                           (optional, Post-Markierung)
#     "tags":          ["pgp", "username"],             (optional, Array)
#     "selection": {                                    (optional, Textmarkierung)
#       "xpathStart":  "...",
#       "offsetStart": 14,
#       "xpathEnd":    "...",
#       "offsetEnd":   32,
#       "textContent": "BirnenKenner99"
#     }
#   }
#   Response: 200 {"id": <annotation_id>, "status": "ok"}
#
# DELETE Request-Body (JSON):
#   { "id": <annotation_id> }          (Pflicht — Server-ID aus POST-Response)
#   Response: 200 {"status": "ok", "deleted": true}
#            oder {"status": "not_found", "deleted": false} (id existiert nicht)
#
# Error-Response (beide Methoden):
#   400 {"error": "<Fehlermeldung>"}
#
# Änderungen:
#   Build 011 (2026-04-13): POST implementiert (Baustelle 3, §11.2 Bauplan).
#   Build 059 (2026-04-26): DELETE implementiert
#   Build 178 (2026-05-12): Soft-Delete (Bug 2.75) — DELETE setzt nur
#     deleted_at in evidence_db. Neuer Pfad POST /_forensic/annotate/restore
#     zum Wiederherstellen gelöschter Annotationen.
#     Neuer Pfad GET /_forensic/annotate/deleted für Wiederherstellungs-Modal. (OP-KN-9 — HoverMenuModule
#     löscht Annotationen ohne Server-Call, sie erscheinen nach Reload wieder).
#     Beleg: Analyse annotate.py + evidence_db.py — kein delete_annotation()
#     vorhanden. delete_annotation() in evidence_db.py gleichzeitig ergänzt.
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# =============================================================================

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import sqlite3
import time
from pathlib import Path
from typing import Optional

from core.logger import get_logger
from db.evidence_db import VALID_CATEGORIES, EvidenceDbError

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)


class AnnotateEndpoint:
    """Endpunkt /_forensic/annotate — speichert Annotationen in evidence_db."""

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle  = bundle
        self._context = context
        # Build 184 (Bug 2.91): self._config war nicht zugewiesen — Pfadberechnung
        # für Transportdatei schlug fehl mit "has no attribute '_config'".
        # Beleg: Webserver-Log 2026-05-12.
        self._config  = config

    def handle(
        self,
        handler: "ForensicRequestHandler",
        body: bytes,
    ) -> None:
        """
        Verarbeitet POST und DELETE /_forensic/annotate

        POST  → Annotation speichern (upsert via local_id)
        DELETE → Annotation löschen (anhand Server-ID)

        Args:
            handler: ForensicRequestHandler-Instanz.
            body:    Request-Body als bytes (JSON).
        """
        if handler.command == "DELETE":
            self._handle_delete(handler, body)
            return

        # --- POST-Pfad ---
        # JSON parsen
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, ValueError) as exc:
            self._error(handler, f"Ungültiges JSON: {exc}")
            return

        # Pflichtfelder prüfen
        page_url = data.get("page_url", "").strip()
        category = data.get("category", "").strip()
        text     = data.get("text", "")

        if not page_url:
            self._error(handler, "Feld 'page_url' fehlt oder leer")
            return
        if not category:
            self._error(handler, "Feld 'category' fehlt oder leer")
            return
        if category not in VALID_CATEGORIES:
            self._error(
                handler,
                f"Ungültige Kategorie '{category}'. "
                f"Zulässig: {sorted(VALID_CATEGORIES)}"
            )
            return

        element_id = data.get("element_id") or None
        local_id   = data.get("local_id") or None

        # post_id: numerisch oder None
        post_id_raw = data.get("post_id")
        try:
            post_id = int(post_id_raw) if post_id_raw is not None else None
        except (TypeError, ValueError):
            post_id = None

        # selection: Objekt → JSON-String
        selection_raw = data.get("selection")
        selection_json = None
        if selection_raw is not None and isinstance(selection_raw, dict):
            # XPath-Anker (Originaltext) — bisherige Pflichtfelder.
            xpath_fields = {"xpathStart", "offsetStart", "xpathEnd", "offsetEnd", "textContent"}
            # Build 336: Uebersetzungs-Offset-Anker (Baustelle 3, Build 329/333)
            # zusaetzlich akzeptieren. Diese Marken verankern per Zeichen-Offset im
            # translated_text (stabil ueber Reload) statt per XPath in das dynamisch
            # injizierte Panel. Ohne diese Ergaenzung verwarf der Endpoint die
            # Selektion still (selection_json=None) -> Marke ohne Anker.
            # Beleg: Live-Diagnose 2026-07-07 (/annotate-POST-Probe + annotate.py).
            translation_fields = {"postId", "charStart", "charEnd", "textLen", "textHash"}
            is_xpath = xpath_fields.issubset(selection_raw.keys())
            is_translation = (
                selection_raw.get("target") == "translation"
                and translation_fields.issubset(selection_raw.keys())
            )
            if is_xpath or is_translation:
                selection_json = json.dumps(selection_raw, ensure_ascii=False)
            else:
                logger.warning(
                    "selection-Objekt unvollständig (Felder fehlen): %s", selection_raw
                )

        # tags: Array → JSON-String
        tags_raw = data.get("tags")
        tags_json = None
        if tags_raw is not None and isinstance(tags_raw, list):
            # Nur Strings übernehmen, leere herausfiltern
            clean_tags = [str(t).strip() for t in tags_raw if str(t).strip()]
            tags_json = json.dumps(clean_tags, ensure_ascii=False)

        # Bug 2.85 (Build 176): created_by = SAMAccountName des ERMITTLERS.
        created_by = getattr(self._context, "investigator_username", "") or \
                     getattr(self._context, "username", "") or ""

        # Bug 2.78 (Build 182): Fremd-Annotation — target_user_id gesetzt
        # wenn Ermittler die Annotation einem anderen Forenbenutzer zuordnet.
        # Build 183 (Bug 2.91): Umfangreiches Debug-Logging fuer Fehleranalyse.
        logger.debug(
            "[2.91-DBG] annotate POST empfangen: page_url=%r category=%r "
            "local_id=%r target_user_id_raw=%r investigator_id=%r subject_id=%r",
            data.get("page_url"), data.get("category"), data.get("local_id"),
            data.get("target_user_id"), self._context.investigator_id,
            self._context.subject_id,
        )
        target_user_id_raw = data.get("target_user_id")
        target_user_id: Optional[int] = None
        if target_user_id_raw is not None:
            try:
                target_user_id = int(target_user_id_raw)
            except (TypeError, ValueError):
                pass
        # Wenn target_user_id == aktuelle subject_id oder None → Normalpfad
        is_cross = (
            target_user_id is not None
            and target_user_id != self._context.subject_id
        )
        logger.debug(
            "[2.91-DBG] Pfad-Entscheidung: target_user_id=%r current_uid=%r "
            "is_cross=%r",
            target_user_id, self._context.subject_id, is_cross,
        )

        # Annotation speichern
        # Build 182 (Bug 2.78): Bei Fremd-Annotation (is_cross=True) wird
        # die Annotation in der lokalen evidence_db mit actual_uid=target_user_id
        # gespeichert UND als Transportkopie in evidence_<uid2>_<iid>.db.
        actual_uid = target_user_id if is_cross else None
        try:
            annotation_id = self._bundle.evidence.save_annotation(
                page_url=page_url,
                category=category,
                text=str(text),
                element_id=element_id,
                investigator_id=self._context.investigator_id,
                selection_json=selection_json,
                tags_json=tags_json,
                local_id=local_id,
                post_id=post_id,
                created_by=created_by,
                actual_uid=actual_uid,
            )
        except EvidenceDbError as exc:
            self._error(handler, str(exc))
            return
        except Exception as exc:
            logger.error("Annotation konnte nicht gespeichert werden: %s", exc)
            self._error(handler, "Interner Fehler beim Speichern")
            return

        logger.debug(
            "[2.91-DBG] save_annotation Ergebnis: annotation_id=%r "
            "actual_uid=%r is_cross=%r local_id=%r",
            annotation_id, actual_uid, is_cross, local_id,
        )
        # Fremd-Annotation: Transportkopie anlegen
        if is_cross and local_id:
            self._write_cross_annotation(
                page_url=page_url,
                category=category,
                text=str(text),
                element_id=element_id,
                selection_json=selection_json,
                tags_json=tags_json,
                local_id=local_id,
                post_id=post_id,
                created_by=created_by,
                target_user_id=target_user_id,
                actual_uid=actual_uid,
            )

        logger.info(
            "Annotation gespeichert: id=%d, page='%s', cat=%s, element=%s, post_id=%s",
            annotation_id, page_url, category, element_id, post_id,
        )

        body_out = json.dumps(
            {"id": annotation_id, "status": "ok"}, ensure_ascii=False
        ).encode("utf-8")
        handler.send_response_body(
            200, body_out, content_type="application/json; charset=utf-8"
        )

    def _handle_delete(
        self,
        handler: "ForensicRequestHandler",
        body: bytes,
    ) -> None:
        """
        Verarbeitet DELETE /_forensic/annotate

        Erwartet JSON-Body: {"id": <annotation_id>}

        Gibt {"status": "ok", "deleted": true} zurück wenn erfolgreich,
        {"status": "not_found", "deleted": false} wenn ID nicht existiert.

        Beleg: OP-KN-9 — ohne Server-DELETE erscheinen gelöschte Annotationen
        nach jedem loadAnnotations()-Aufruf wieder.
        """
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, ValueError) as exc:
            self._error(handler, f"Ungültiges JSON: {exc}")
            return

        ann_id_raw = data.get("id")
        if ann_id_raw is None:
            self._error(handler, "Feld 'id' fehlt")
            return
        try:
            ann_id = int(ann_id_raw)
        except (TypeError, ValueError):
            self._error(handler, f"Feld 'id' muss eine Ganzzahl sein, erhalten: {ann_id_raw!r}")
            return

        try:
            deleted = self._bundle.evidence.delete_annotation(ann_id)
        except Exception as exc:
            logger.error("Annotation konnte nicht gelöscht werden: %s", exc)
            self._error(handler, "Interner Fehler beim Löschen")
            return

        if deleted:
            logger.info("Annotation gelöscht: id=%d", ann_id)
            status = "ok"
        else:
            logger.warning("DELETE /_forensic/annotate: id=%d nicht gefunden", ann_id)
            status = "not_found"

        body_out = json.dumps(
            {"status": status, "deleted": deleted}, ensure_ascii=False
        ).encode("utf-8")
        handler.send_response_body(
            200, body_out, content_type="application/json; charset=utf-8"
        )

    def _write_cross_annotation(
        self,
        page_url: str,
        category: str,
        text: str,
        element_id,
        selection_json,
        tags_json,
        local_id: str,
        post_id,
        created_by: str,
        target_user_id: int,
        actual_uid,
    ) -> None:
        """
        Schreibt Fremd-Annotation in Transportdatei evidence_<uid2>_<iid>.db
        und traegt pending_cross_annotations in coordinator.db ein.

        Build 182 (Bug 2.78):
          1. Transportdatei oeffnen/anlegen
          2. Annotation + Page-BLOB hineinschreiben
          3. coordinator.db: add_pending_cross_annotation()

        Fehler hier sind nicht fatal — lokale Annotation ist bereits gespeichert.
        Beleg: Projektgespraech 2026-05-12.
        """
        iid = self._context.investigator_id
        logger.debug(
            "[2.91-DBG] _write_cross_annotation: target_uid=%r iid=%r "
            "local_id=%r page_url=%r",
            target_user_id, iid, local_id, page_url,
        )
        if iid is None:
            logger.warning(
                "_write_cross_annotation: investigator_id nicht gesetzt — Transportkopie nicht angelegt"
            )
            return

        # Pfad zur Transportdatei
        try:
            from core.mode_resolver import ModeResolver
            cross_path = Path(
                self._config.get("paths.evidence_db_dir")
            ) / f"evidence_{target_user_id}_{iid}.db"
            cross_path = cross_path.resolve()
            logger.debug(
                "[2.91-DBG] Transportdatei-Pfad: '%s' (existiert: %s)",
                cross_path, cross_path.exists(),
            )
        except Exception as exc:
            logger.error("_write_cross_annotation: Pfadberechnung fehlgeschlagen: %s", exc)
            return

        # Transportdatei oeffnen (anlegen wenn nicht vorhanden)
        try:
            t_con = sqlite3.connect(str(cross_path))
            t_con.row_factory = sqlite3.Row
            # Minimales Schema: annotations + pages
            t_con.executescript("""
                CREATE TABLE IF NOT EXISTS annotations (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    page_url        TEXT    NOT NULL,
                    element_id      TEXT,
                    category        TEXT    NOT NULL,
                    text            TEXT    NOT NULL DEFAULT '',
                    ts              INTEGER NOT NULL,
                    investigator_id INTEGER,
                    selection_json  TEXT    DEFAULT NULL,
                    tags_json       TEXT    DEFAULT NULL,
                    local_id        TEXT    DEFAULT NULL,
                    post_id         INTEGER DEFAULT NULL,
                    created_by      TEXT    NOT NULL DEFAULT '',
                    deleted_at      INTEGER DEFAULT NULL,
                    version_nr      INTEGER NOT NULL DEFAULT 1,
                    prev_id         INTEGER DEFAULT NULL,
                    actual_uid      INTEGER DEFAULT NULL
                );
                CREATE TABLE IF NOT EXISTS pages (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    url_canonical   TEXT    NOT NULL UNIQUE,
                    html_blob       BLOB,
                    http_status     INTEGER,
                    scrape_context  TEXT,
                    fetched_at      INTEGER,
                    title           TEXT,
                    in_scope        INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS t_ann_local_id_idx ON annotations (local_id);
                CREATE INDEX IF NOT EXISTS t_pages_url_idx    ON pages (url_canonical);
            """)
        except Exception as exc:
            logger.error("_write_cross_annotation: Transportdatei kann nicht angelegt werden: %s", exc)
            return

        try:
            ts_now = int(time.time())

            # Annotation schreiben (idempotent via local_id)
            existing = t_con.execute(
                "SELECT id FROM annotations WHERE local_id = ? AND deleted_at IS NULL",
                (local_id,),
            ).fetchone()
            if not existing:
                t_con.execute(
                    "INSERT INTO annotations "
                    "(page_url, element_id, category, text, ts, investigator_id, "
                    " selection_json, tags_json, local_id, post_id, created_by, actual_uid) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        page_url, element_id, category, text, ts_now,
                        iid, selection_json, tags_json, local_id,
                        post_id, created_by, actual_uid,
                    ),
                )

            # Page-BLOB aus forensic_db holen und in Transportdatei kopieren
            page_exists = t_con.execute(
                "SELECT id FROM pages WHERE url_canonical = ?", (page_url,)
            ).fetchone()
            if not page_exists:
                try:
                    page_row = self._bundle.forensic.get_page_by_url(page_url)
                    if page_row:
                        t_con.execute(
                            "INSERT OR IGNORE INTO pages "
                            "(url_canonical, html_blob, http_status, scrape_context, "
                            " fetched_at, title, in_scope) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (
                                page_url,
                                page_row.get("html_blob"),
                                page_row.get("http_status"),
                                page_row.get("scrape_context"),
                                page_row.get("fetched_at"),
                                page_row.get("title"),
                                page_row.get("in_scope", 1),
                            ),
                        )
                except Exception as exc:
                    logger.warning(
                        "_write_cross_annotation: Page-BLOB fuer '%s' nicht gefunden: %s",
                        page_url, exc,
                    )

            t_con.commit()
            logger.info(
                "[2.91-DBG] _write_cross_annotation: Transportkopie geschrieben: "
                "local_id=%r → '%s'", local_id, cross_path,
            )
            # Annotation-Zählung zur Verifikation
            ann_count = t_con.execute(
                "SELECT COUNT(*) FROM annotations WHERE local_id = ?", (local_id,)
            ).fetchone()[0]
            logger.debug(
                "[2.91-DBG] Transportdatei nach Commit: annotations mit local_id=%r: %d",
                local_id, ann_count,
            )

            # coordinator.db eintragen
            cdb = self._bundle.coordinator
            logger.debug(
                "[2.91-DBG] coordinator.db verfuegbar: %s", cdb is not None
            )
            if cdb:
                try:
                    cdb.add_pending_cross_annotation(
                        source_iid=iid,
                        target_uid=target_user_id,
                        db_path=str(cross_path),
                        annotation_local_id=local_id,
                    )
                except Exception as exc:
                    logger.error(
                        "_write_cross_annotation: add_pending_cross_annotation fehlgeschlagen: %s",
                        exc,
                    )
        except Exception as exc:
            logger.error("_write_cross_annotation: unerwarteter Fehler: %s", exc)
        finally:
            t_con.close()

    def handle_restore(
        self,
        handler: "ForensicRequestHandler",
        body: bytes,
    ) -> None:
        """
        POST /_forensic/annotate/restore — Gelöschte Annotation wiederherstellen.

        Erwartet JSON-Body: {"id": <annotation_id>}
        Gibt {"status": "ok", "restored": true} oder
             {"status": "not_found"/"has_successor", "restored": false} zurück.
        Beleg: Projektgespräch 2026-05-12 — Bug 2.75 (BS3).
        """
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, ValueError) as exc:
            self._error(handler, f"Ungültiges JSON: {exc}")
            return

        ann_id_raw = data.get("id")
        if ann_id_raw is None:
            self._error(handler, "Feld 'id' fehlt")
            return
        try:
            ann_id = int(ann_id_raw)
        except (TypeError, ValueError):
            self._error(handler, f"Feld 'id' muss Ganzzahl sein, erhalten: {ann_id_raw!r}")
            return

        try:
            restored = self._bundle.evidence.restore_annotation(ann_id)
        except Exception as exc:
            logger.error("Annotation konnte nicht wiederhergestellt werden: %s", exc)
            self._error(handler, "Interner Fehler beim Wiederherstellen")
            return

        if restored:
            logger.info("Annotation wiederhergestellt: id=%d", ann_id)
            status = "ok"
        else:
            # Entweder nicht gefunden oder hat Nachfolger (nur alte Version)
            status = "not_restorable"

        body_out = json.dumps(
            {"status": status, "restored": restored}, ensure_ascii=False
        ).encode("utf-8")
        handler.send_response_body(
            200, body_out, content_type="application/json; charset=utf-8"
        )

    def handle_deleted(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        """
        GET /_forensic/annotate/deleted?url=<page_url>
        Liefert tatsächlich gelöschte Annotationen (ohne Nachfolger) für das
        Wiederherstellungs-Modal im Frontend.
        Beleg: Projektgespräch 2026-05-12 — Bug 2.75 (BS3).
        """
        import urllib.parse
        url_list = params.get("url", [])
        page_url = urllib.parse.unquote(url_list[0]) if url_list else None

        try:
            records = self._bundle.evidence.get_deleted_annotations(page_url)
        except Exception as exc:
            logger.error("Gelöschte Annotationen: Datenbankfehler: %s", exc)
            self._error(handler, "Interner Fehler beim Laden gelöschter Annotationen")
            return

        out = []
        for rec in records:
            tags = []
            if rec.tags_json:
                try:
                    tags = json.loads(rec.tags_json)
                    if not isinstance(tags, list):
                        tags = []
                except (json.JSONDecodeError, ValueError):
                    pass
            out.append({
                "id":         rec.id,
                "pageUrl":    rec.page_url,
                "category":   rec.category,
                "text":       rec.text,
                "tags":       tags,
                "elementId":  rec.element_id,
                "postId":     rec.post_id,
                "localId":    rec.local_id,
                "createdAt":  rec.ts * 1000,
                "createdBy":  rec.created_by,
                "deletedAt":  rec.deleted_at * 1000 if rec.deleted_at else None,
                "versionNr":  rec.version_nr,
            })

        body_out = json.dumps(
            {"annotations": out, "status": "ok"}, ensure_ascii=False
        ).encode("utf-8")
        handler.send_response_body(
            200, body_out, content_type="application/json; charset=utf-8"
        )
        logger.debug(
            "/_forensic/annotate/deleted: url=%r → %d gelöschte Annotationen",
            page_url, len(out),
        )

    @staticmethod
    def _error(handler: "ForensicRequestHandler", message: str) -> None:
        body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            400, body, content_type="application/json; charset=utf-8"
        )
