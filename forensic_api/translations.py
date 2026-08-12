# =============================================================================
# forensic_api/translations.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/translations?topic_id=<topic_id> (GET)
#   Liefert die post_ids eines Topics, fuer die eine fertige KI-Uebersetzung
#   vorliegt. Die Toolbar ruft dies einmal je viewtopic-Seite auf (parallel
#   zum Seiten-Fetch), cached das Ergebnis als Set und injiziert nur dort eine
#   Flaggen-Schaltflaeche, wo die post_id enthalten ist.
#
#   Warum topic-basiert (nicht post_id-Liste): Die Toolbar kennt topic_id direkt
#   aus der URL (viewtopic.php?id=<topic_id>) und muss nicht auf das Post-DOM
#   warten (Viewport wird asynchron befuellt). Beleg: Bauplan Build 329 §2/§4.2.
#
# PRIVATE NACHRICHTEN (source=pms, Build 703, Vorgang da84f94f):
#   'topic_id' ist dann die DIALOG-ID (tid aus 'pmsnew.php?mdl=topic&tid=').
#   Der Weg ueber trdb.translations.topic_id steht hier NICHT zur Verfuegung:
#   der Uebersetzungslauf fuellt topic_id/forum_id nur fuer 'posts', bei 'pms'
#   bleiben sie leer (Datenprobe Alex, 12.08.2026). Aufgeloest wird deshalb
#   zweistufig:
#     1. fdb.pm_aliases: Dialog -> alle erfassten pm_post_ids (BEIDE Seiten
#        des Gespraechs, Beleg: Prepper stage1/query_blocks.py).
#     2. trdb.translations: welche davon haben eine Uebersetzung?
#   Die Zugehoerigkeit einer Nachricht zu einem Dialog kommt damit aus dem
#   forensischen Bestand und nicht aus der extern erzeugten Uebersetzungs-DB.
#
#   RUECKFALL: Liefert Weg (1)+(2) NICHTS, wird zusaetzlich der alte Weg ueber
#   trdb.translations.topic_id versucht. Er greift bei Bestaenden, in denen die
#   Spalte auch fuer PN gefuellt ist. Beide Wege werden protokolliert und im
#   Feld 'resolved_via' der Antwort benannt — ein Ergebnis, dessen Herkunft
#   offenbleibt, ist nicht ueberpruefbar (GR1).
#
# Response (200):
#   { "topic_id": 69192, "source": "posts", "post_ids": [706037, 706040],
#     "count": 2, "status": "ok", "resolved_via": "topic_id" }
#
# Fehlerfaelle:
#   - fehlender/ungueltiger topic_id  -> 400 { "error": ..., "status": "error" }
#   - trdb nicht angebunden           -> 200 leere Liste (kein Fehler; die DB
#                                        wird extern erst spaeter befuellt)
#
# Version: v0.8.703 · Build: 703 · 2026-08-12 (PN-Dialoge ueber pm_aliases)
# =============================================================================

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)


class TranslationsEndpoint:
    """
    Endpunkt /_forensic/translations (GET).

    Liest ausschliesslich aus trdb.translations (READ-ONLY, global geteilt).
    Beleg: Bauplan Build 329 §3.1
    """

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle = bundle
        self._context = context

    def handle(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        """Verarbeitet GET /_forensic/translations?topic_id=<topic_id>."""
        raw_vals = params.get("topic_id", [])
        raw = raw_vals[0] if raw_vals else ""

        try:
            topic_id = int(str(raw).strip())
        except (ValueError, TypeError):
            topic_id = -1

        if topic_id <= 0:
            body = json.dumps(
                {"error": "Ungueltiger oder fehlender topic_id",
                 "status": "error"},
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                400, body, content_type="application/json; charset=utf-8"
            )
            return

        # Build 331: source trennt 'posts' (Forum) von 'pms'. Default 'posts';
        # unbekannter Wert wird NICHT still ersetzt, sondern als 400 gemeldet (GR1).
        source_vals = params.get("source", [])
        source = source_vals[0] if source_vals else "posts"
        if source not in ("posts", "pms"):
            body = json.dumps(
                {"error": "Ungueltiger source (erlaubt: posts, pms)",
                 "status": "error"},
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                400, body, content_type="application/json; charset=utf-8"
            )
            return

        try:
            if source == "pms":
                post_ids, resolved_via = self._pms_dialog_aufloesen(topic_id)
            else:
                post_ids = self._bundle.translations.list_translated_post_ids(
                    topic_id, source
                )
                resolved_via = "topic_id"
        except Exception as exc:  # defensiv — niemals 500 ohne Log (GR1)
            logger.error(
                "TranslationsEndpoint: list_translated_post_ids(%r) Fehler: %s",
                topic_id, exc,
            )
            body = json.dumps(
                {"error": "Interner Fehler bei der Uebersetzungs-Abfrage",
                 "status": "error"},
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                500, body, content_type="application/json; charset=utf-8"
            )
            return

        logger.debug(
            "/_forensic/translations: topic_id=%d source=%s -> %d uebersetzte "
            "post_ids (Weg: %s).",
            topic_id, source, len(post_ids), resolved_via,
        )
        body_out = json.dumps(
            {"topic_id": topic_id, "source": source, "post_ids": post_ids,
             "count": len(post_ids), "status": "ok",
             "resolved_via": resolved_via},
            ensure_ascii=False,
        ).encode("utf-8")
        handler.send_response_body(
            200, body_out, content_type="application/json; charset=utf-8"
        )

    # ------------------------------------------------------------------
    # PN-Dialoge (Build 703, Vorgang da84f94f)
    # ------------------------------------------------------------------

    def _pms_dialog_aufloesen(self, pm_topic_id: int) -> "tuple[list[int], str]":
        """
        Liefert die uebersetzten Nachrichten EINES PN-Dialogs.

        Returns:
            (post_ids, Weg) — Weg ist 'pm_aliases', 'topic_id' oder
            'keiner'. Der Weg gehoert in die Antwort, weil die beiden Wege
            verschiedene Quellen haben: der eine den forensischen Bestand,
            der andere die extern erzeugte Uebersetzungs-DB. Welche von beiden
            eine Anzeige getragen hat, muss nachvollziehbar sein (GR1).
        """
        forensic = getattr(self._bundle, "forensic", None)
        pm_post_ids: list[int] = []
        if forensic is not None and hasattr(forensic, "list_pm_post_ids"):
            pm_post_ids = forensic.list_pm_post_ids(pm_topic_id)
        else:
            logger.warning(
                "/_forensic/translations: keine ForensicDb mit "
                "list_pm_post_ids() verfuegbar — PN-Dialog %r kann nicht "
                "ueber pm_aliases aufgeloest werden.", pm_topic_id,
            )

        if pm_post_ids:
            treffer = self._bundle.translations.filter_translated_post_ids(
                pm_post_ids, "pms"
            )
            if treffer:
                return treffer, "pm_aliases"
            logger.debug(
                "/_forensic/translations: Dialog %r hat %d erfasste "
                "Nachrichten, davon keine uebersetzt — Rueckfallweg wird "
                "geprueft.", pm_topic_id, len(pm_post_ids),
            )

        # Rueckfall: Bestaende, in denen translations.topic_id auch fuer PN
        # gefuellt ist. Kein stiller Weg — er wird benannt und protokolliert.
        alt = self._bundle.translations.list_translated_post_ids(
            pm_topic_id, "pms"
        )
        if alt:
            logger.info(
                "/_forensic/translations: PN-Dialog %r ueber "
                "translations.topic_id aufgeloest (%d Treffer); ueber "
                "fdb.pm_aliases war nichts zu finden (%d erfasste "
                "Nachrichten).", pm_topic_id, len(alt), len(pm_post_ids),
            )
            return alt, "topic_id"

        if not pm_post_ids:
            logger.warning(
                "/_forensic/translations: PN-Dialog %r ist weder in "
                "fdb.pm_aliases erfasst noch ueber translations.topic_id "
                "auffindbar — es werden keine Uebersetzungen angeboten.",
                pm_topic_id,
            )
        return [], "keiner" if not pm_post_ids else "pm_aliases"
