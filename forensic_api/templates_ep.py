# =============================================================================
# forensic_api/templates_ep.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Zweck:
#   Endpunkte fuer Berichtsmodul-Abfragen (lesend).
#
#   GET /_forensic/templates
#     Liefert gefilterte Modulliste fuer das Modul-Auswahl-Panel (§4.4).
#     Query-Parameter: ?role=body&topic=Identifikation&search=...
#     Zusaetzlich: ?topics=1 liefert alle vorhandenen topic-Werte.
#
#   GET /_forensic/templates/<id>
#     Liefert ein einzelnes Modul mit vollstaendigem Body (fuer Vorschau).
#
# Beleg: Bauplan B6 v0.3 §4.4, §5, Ausdefinitionsgespraech 2026-05-05
# Version: v0.6.089 · Build: 089 · 2026-05-05
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


def _json_ok(data) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def _json_err(msg: str, code: str = "ERROR") -> bytes:
    return json.dumps({"error": msg, "code": code}, ensure_ascii=False).encode("utf-8")


class TemplatesListEndpoint:
    """
    Lesender Zugriff auf Berichtsmodule aus templates.db.
    Beleg: Bauplan B6 v0.3 §4.4, §5
    """

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle  = bundle
        self._context = context
        self._config  = config

    def handle_get(
        self,
        handler: "ForensicRequestHandler",
        url_path: str,
        params: dict,
    ) -> None:
        """
        Routing fuer GET /_forensic/templates und /_forensic/templates/<id>.
        """
        # BUILD 578: EINE HUELLE FUER ALLE FUENF ZWEIGE.
        #
        # Vorher rief jeder Handler die templates.db ohne Fehlerbehandlung.
        # Fehlte die Datei, flog die Ausnahme aus dem Handler, die Verbindung
        # starb, und der Browser meldete nur 'Failed to fetch' - ohne Status,
        # ohne Hinweis. Genau das ist am 2026-07-30 passiert und hat eine
        # Gespraechsrunde gekostet.
        #
        # Die Huelle sitzt am VERTEILER und nicht in jedem Handler: fuenf
        # try/except waeren fuenf Stellen, an denen die naechste vergessen
        # wird. Gefangen werden ausdruecklich NUR Datenbank- und
        # Dateisystemfehler - ein Programmierfehler bleibt ein
        # Programmierfehler (s. db_guard.py).
        from forensic_api.db_guard import db_fehler_koerper, geschuetzt

        # BUILD 579 - EHRLICHE ANTWORT STATT LEERER LISTE.
        #
        # Die Huelle aus Build 578 faengt Ausnahmen. Sie kam nie zum Zuge,
        # weil TemplatesDb den Fehler eine Ebene tiefer SCHLUCKT und eine
        # leere Liste zurueckgibt: eine fehlende templates.db ergab HTTP 200
        # mit [] - fuer den Browser ununterscheidbar von 'keine Vorlagen
        # angelegt'. Belegt am 2026-07-30 im Log von mc: 'GET
        # /_forensic/templates ... 200'.
        #
        # Deshalb wird der Zustand VOR dem Verteilen gefragt. Ist die Quelle
        # nicht lesbar, antwortet der Endpunkt benannt (503) - und der
        # Redakteur sieht, dass er nicht 'nichts' hat, sondern 'nicht
        # nachsehen kann'. Die Huelle bleibt als zweites Netz fuer echte
        # Ausnahmen darunter.
        zustand, meldung = self._quellzustand()
        if zustand != "ok":
            logger.error(
                "GET %s: templates.db nicht nutzbar (%s: %s) — Pfad: %s",
                url_path, zustand, meldung, self._templates_db_pfad() or "?")
            handler.send_response_body(
                503, db_fehler_koerper("templates.db", zustand,
                                       massnahme=meldung),
                content_type="application/json; charset=utf-8",
            )
            return

        geschuetzt(handler, "templates.db",
                   lambda: self._verteile(handler, url_path, params),
                   pfad=self._templates_db_pfad())

    def _quellzustand(self):
        """
        Zustand der templates.db, frisch geprueft. Kann die Quelle nichts
        ueber sich sagen (aeltere Fassung ohne zustand()), wird 'ok'
        angenommen - lieber die bisherige Auskunft als ein erfundener Fehler.
        """
        quelle = getattr(self._bundle, "templates", None)
        if quelle is None or not hasattr(quelle, "zustand"):
            return ("ok", "")
        try:
            return quelle.zustand()
        except Exception as exc:                            # noqa: BLE001
            return ("fehler", str(exc))

    def _templates_db_pfad(self):
        """
        Der Pfad der templates.db, nur fuers PROTOKOLL. Faellt die Ermittlung
        aus, ist das kein Grund zu scheitern - dann steht im Protokoll eben
        kein Pfad, und die Antwort ist trotzdem brauchbar.
        """
        try:
            return str(getattr(self._bundle.templates, "db_path", "") or "")
        except Exception:                                    # noqa: BLE001
            return ""

    def _verteile(
        self,
        handler: "ForensicRequestHandler",
        url_path: str,
        params: dict,
    ) -> None:
        """Die eigentliche Verteilung (von handle_get umhuellt aufgerufen)."""
        if url_path == "/_forensic/templates":
            self._handle_list(handler, params)
        # Build 388: VORLAGEN (vollstaendige Berichtsgerueste).
        # ACHTUNG Reihenfolge: '/templates/full' MUSS vor dem allgemeinen
        # '/templates/<id>'-Zweig stehen — sonst landet 'full' in _handle_single
        # und scheitert dort an int('full').
        elif url_path == "/_forensic/templates/full":
            self._handle_template_list(handler, params)
        elif url_path.startswith("/_forensic/templates/full/"):
            key = url_path[len("/_forensic/templates/full/"):]
            self._handle_template_single(handler, key)
        elif url_path.startswith("/_forensic/templates/"):
            id_str = url_path[len("/_forensic/templates/"):]
            self._handle_single(handler, id_str)
        else:
            handler.send_response_body(
                404, _json_err("Endpunkt nicht bekannt."),
                content_type="application/json; charset=utf-8",
            )

    def _handle_list(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        """GET /_forensic/templates — Modulliste mit optionalem Filter."""
        # Sondermodus: ?topics=1 liefert nur die topic-Werte
        if params.get("topics", [None])[0] == "1":
            topics = self._bundle.templates.list_topics()
            handler.send_response_body(
                200, _json_ok({"topics": topics}),
                content_type="application/json; charset=utf-8",
            )
            return

        role   = params.get("role",   [None])[0]
        topic  = params.get("topic",  [None])[0]
        search = params.get("search", [None])[0]

        modules = self._bundle.templates.list_modules(
            role=role, topic=topic, search=search
        )

        result = [
            {
                "id":          m.id,
                "title":       m.title,
                "description": m.description,
                "role":        m.role,
                "topic":       m.topic,
                "sort_order":  m.sort_order,
                # body wird im Listenview nicht uebertragen (zu gross)
                # Fuer den Body: GET /_forensic/templates/<id>
            }
            for m in modules
        ]

        handler.send_response_body(
            200, _json_ok(result),
            content_type="application/json; charset=utf-8",
        )

    def _handle_single(
        self,
        handler: "ForensicRequestHandler",
        id_str: str,
    ) -> None:
        """GET /_forensic/templates/<id> — Einzelmodul mit Body."""
        try:
            module_id = int(id_str)
        except ValueError:
            handler.send_response_body(
                400, _json_err(f"Ungueltiger Modul-ID-Wert: '{id_str}'"),
                content_type="application/json; charset=utf-8",
            )
            return

        m = self._bundle.templates.get_module(module_id)
        if m is None:
            handler.send_response_body(
                404,
                _json_err(f"Modul {module_id} nicht gefunden.", "NOT_FOUND"),
                content_type="application/json; charset=utf-8",
            )
            return

        handler.send_response_body(
            200,
            _json_ok({
                "id":          m.id,
                "title":       m.title,
                "description": m.description,
                "role":        m.role,
                "topic":       m.topic,
                "body":        m.body,
                "sort_order":  m.sort_order,
            }),
            content_type="application/json; charset=utf-8",
        )

    # ------------------------------------------------------------------
    # Vorlagen (Build 388)
    # ------------------------------------------------------------------
    # Eine VORLAGE ist ein vollstaendiges Berichtsgerueste aus mehreren
    # typisierten Bloecken — im Unterschied zu einem MODUL (genau ein
    # paragraph-Block). Sie wird nicht ueber save_block eingefuegt, sondern
    # ueber die Aktion 'insert_template' (transaktional, alles oder nichts).
    # ------------------------------------------------------------------

    def _handle_template_list(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        """GET /_forensic/templates/full — Liste der Vorlagen (ohne blocks_json)."""
        search = params.get("search", [None])[0]
        templates = self._bundle.templates.list_templates(search=search)

        result = [
            {
                "template_key": t.template_key,
                "title":        t.title,
                "description":  t.description,
                "report_type":  t.report_type,
                "sort_order":   t.sort_order,
            }
            for t in templates
        ]
        handler.send_response_body(
            200, _json_ok(result),
            content_type="application/json; charset=utf-8",
        )

    def _handle_template_single(
        self,
        handler: "ForensicRequestHandler",
        template_key: str,
    ) -> None:
        """
        GET /_forensic/templates/full/<template_key> — Vorlage MIT blocks_json.

        Dient der Vorschau im Reiter 'Vorlagen'. Das EINFUEGEN laeuft NICHT
        ueber diesen Endpunkt, sondern serverseitig ueber 'insert_template' —
        der Client soll die Bloecke nicht selbst einzeln schreiben (sonst
        koennen halbe Vorlagen entstehen; GRUNDREGEL 1).
        """
        import urllib.parse as _urlparse
        key = _urlparse.unquote(template_key or "").strip()

        if not key:
            handler.send_response_body(
                400, _json_err("template_key fehlt.", "MISSING_TEMPLATE_KEY"),
                content_type="application/json; charset=utf-8",
            )
            return

        tpl = self._bundle.templates.get_template_by_key(key)
        if tpl is None:
            handler.send_response_body(
                404,
                _json_err("Vorlage '%s' nicht gefunden." % key,
                          "TEMPLATE_NOT_FOUND"),
                content_type="application/json; charset=utf-8",
            )
            return

        handler.send_response_body(
            200,
            _json_ok({
                "template_key": tpl.template_key,
                "title":        tpl.title,
                "description":  tpl.description,
                "report_type":  tpl.report_type,
                "blocks_json":  tpl.blocks_json,
            }),
            content_type="application/json; charset=utf-8",
        )
