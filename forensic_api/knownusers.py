# =============================================================================
# forensic_api/knownusers.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 3: Toolbar
# =============================================================================
# Zweck:
#   Endpunkt GET /_forensic/knownusers?q=<suchbegriff>
#
#   Sucht in default.db (known_users + known_aliases) nach Forum-Benutzern,
#   die dem Suchbegriff entsprechen. Wird vom Annotations-Popup (Bug 2.78)
#   als Typeahead-Suche verwendet, damit der Ermittler eine Annotation einem
#   anderen Benutzer zuordnen kann.
#
# Suchverhalten:
#   - Parameter q: Pflicht, mind. 4 Zeichen (wegen 500k+ Einträgen in DB).
#     Bei weniger als 4 Zeichen → HTTP 200, leere users-Liste (kein Fehler).
#   - Suche gegen known_users.username LIKE '%q%' COLLATE NOCASE
#     UND known_aliases.alias LIKE '%q%' COLLATE NOCASE (JOIN auf known_users).
#   - Index-Voraussetzung (vom aiw_sqlite_prepper angelegt):
#       known_users_username_idx ON known_users(username COLLATE NOCASE)
#       known_aliases_alias_idx  ON known_aliases(alias  COLLATE NOCASE)
#
# Response (JSON):
#   {
#     "users": [
#       { "user_id": 538299, "username": "SomeUser", "matched_alias": null },
#       { "user_id": 123456, "username": "Other",    "matched_alias": "Panther" },
#       ...
#     ],
#     "query":   "pant",
#     "limited": true   -- true wenn Trefferliste auf limit abgeschnitten wurde
#   }
#
# Fehler-Response:
#   400  { "error": "..." }   -- nur bei fehlendem/leerem q-Parameter
#
# Änderungen:
#   Build 175: Erstimplementierung als Volllist-Endpunkt (scrape_jobs).
#   Build 176: Überarbeitung als Suchendpunkt gegen default.db (known_users +
#     known_aliases). Volliste war nicht skalierbar (500k+ Nutzer).
#     Beleg: Projektgespräch 2026-05-12 — Bug 2.78/2.82/2.83 (BS3/BS0).
#
# Version: v0.6.176 · Build: 176 · 2026-05-12
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

# Maximale Trefferzahl pro Anfrage
_SEARCH_LIMIT = 20

# Mindestlänge des Suchbegriffs (Performance-Schutz bei 500k+ Einträgen)
_MIN_QUERY_LEN = 4


class KnownUsersEndpoint:
    """
    GET /_forensic/knownusers?q=<suchbegriff>
    Sucht in default.db nach bekannten Forum-Benutzern (Typeahead).
    Beleg: Projektgespräch 2026-05-12 — Bug 2.78/2.82/2.83
    """

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle  = bundle
        self._context = context

    def handle(self, handler: "ForensicRequestHandler", params: dict) -> None:
        """Verarbeitet GET /_forensic/knownusers?q=<suchbegriff>"""
        # q-Parameter auslesen (parse_qs liefert Listen)
        q_list = params.get("q", [])
        query  = q_list[0].strip() if q_list else ""

        # Zu kurze Anfragen: kein Fehler, aber leere Liste
        # (verhindert Volltabellenscans bei 500k+ Einträgen).
        # Build 177: %-Zeichen nicht mitzählen — "%pant" hat 4 Nutzzeichen.
        query_content_len = len(query.replace("%", ""))
        if query_content_len < _MIN_QUERY_LEN:
            body = json.dumps(
                {"users": [], "query": query, "limited": False},
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                200, body, content_type="application/json; charset=utf-8"
            )
            logger.debug(
                "/_forensic/knownusers: Suchbegriff zu kurz "
                "(%d Nutzzeichen < %d, query=%r)",
                query_content_len, _MIN_QUERY_LEN, query,
            )
            return

        # Suche in default.db via DefaultDb.search_known_users()
        try:
            ddb = getattr(self._bundle, "default", None)
            if ddb is None:
                logger.warning("KnownUsersEndpoint: default.db (ddb) nicht verfügbar")
                users = []
            else:
                users = ddb.search_known_users(query, limit=_SEARCH_LIMIT)
        except Exception as exc:
            logger.error("KnownUsersEndpoint: Datenbankfehler: %s", exc)
            users = []

        limited = len(users) >= _SEARCH_LIMIT

        body = json.dumps(
            {"users": users, "query": query, "limited": limited},
            ensure_ascii=False,
        ).encode("utf-8")
        handler.send_response_body(
            200, body, content_type="application/json; charset=utf-8"
        )
        logger.debug(
            "/_forensic/knownusers: q=%r → %d Treffer (limited=%s)",
            query, len(users), limited,
        )

    def handle_resolve(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        """
        GET /_forensic/knownusers/resolve?uid=<user_id>
        Schlaegt einen einzelnen username anhand seiner user_id nach.
        Wird vom Annotation-Popup (Bug 2.92) verwendet wenn actual_uid gesetzt ist.
        Response: {"user_id": N, "username": "...", "found": true/false}
        Beleg: Projektgespraech 2026-05-12 — Bug 2.92 (BS3).
        """
        import json as _json
        uid_list = params.get("uid", [])
        if not uid_list:
            body = _json.dumps({"error": "uid fehlt"}).encode("utf-8")
            handler.send_response_body(400, body,
                                       content_type="application/json; charset=utf-8")
            return
        try:
            uid = int(uid_list[0])
        except (TypeError, ValueError):
            body = _json.dumps({"error": "uid muss Ganzzahl sein"}).encode("utf-8")
            handler.send_response_body(400, body,
                                       content_type="application/json; charset=utf-8")
            return

        ddb = getattr(self._bundle, "default", None)
        username = None
        if ddb is not None:
            try:
                username = ddb.get_username_by_uid(uid)
            except Exception as exc:
                logger.warning("handle_resolve: Fehler: %s", exc)

        body = _json.dumps({
            "user_id":  uid,
            "username": username or f"uid_{uid}",
            "found":    username is not None,
        }, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(200, body,
                                   content_type="application/json; charset=utf-8")
        logger.debug("/_forensic/knownusers/resolve: uid=%d → %r", uid, username)
