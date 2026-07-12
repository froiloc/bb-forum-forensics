# =============================================================================
# forensic_api/results_endpoint.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Ermittlungsergebnis
# =============================================================================
# Zweck:
#   GET  /_forensic/results         — Katalog + aktueller Stand + Historie +
#                                     provisorische Kennzahl
#   POST /_forensic/results/assess  — eine Bewertung erfassen (APPEND-ONLY)
#
#   Der Ermittler arbeitet am FORENSISCHEN Webserver, nicht am Cockpit. Er kann
#   /api/results/assess (Management-Server, Build 387) nicht aufrufen: anderer
#   Server, anderer Port, anderes Token. Also bekommt der forensische Server
#   eigene Endpunkte — die aber DIESELBEN Klassen benutzen (ResultsRepo,
#   AssessmentCatalogRepo, CoordinatorWriter, AuditLog, RbacResolver).
#   ES WIRD KEINE LOGIK DUPLIZIERT. Zwei Implementierungen derselben
#   Bewertungsregeln waeren die sicherste Art, sie auseinanderlaufen zu lassen.
#
# ── DREI FESTLEGUNGEN, DIE DIE KAPSELUNG TRAGEN ──────────────────────────────
#
# (1) DIE user_id KOMMT NICHT AUS DEM BODY.
#     Sie kommt aus dem ResolvedContext — also aus dem Fall, den dieser Server
#     ueberhaupt geoeffnet hat. Ein Bewerten FREMDER Faelle ist damit
#     STRUKTURELL unmoeglich, nicht nur durch eine Pruefung verhindert. Ein
#     'user_id' im Body wird ausdruecklich IGNORIERT (und protokolliert) —
#     nicht etwa uebernommen.
#
# (2) EIGENE VERBINDUNG FUER DEN SCHREIBPFAD.
#     Nicht die ATTACH-Verbindung des Bundles. CoordinatorWriter braucht
#     BEGIN IMMEDIATE und volle Kontrolle ueber die Transaktion; auf einer
#     geteilten Verbindung waere das der bekannte Win32-Mutex-Deadlock
#     (Produktionsbefund). Die Verbindung wird pro Anfrage geoeffnet und
#     geschlossen.
#
# (3) DIE RECHTE WERDEN AUCH HIER GEPRUEFT.
#     RbacResolver ueber context.investigator_id (person.id). Fehlt der Grant,
#     antwortet der Endpunkt mit 403 UND EINER BEGRUENDUNG — die Oberflaeche
#     zeigt sie an, statt eine leere Karte darzustellen. Ein Ermittler soll
#     wissen, WARUM er nichts sieht (Grundregel 1).
#     Ohne investigator_id (kein angemeldeter Ermittler ermittelbar) wird NICHT
#     geschrieben: ein Beleg ohne Handelnden ist kein Beleg.
#
# Version: v0.7.390 · Build: 390 · 2026-07-12
# =============================================================================

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any, Dict, Optional

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

CAP_VIEW = "results.view"
CAP_EDIT = "results.edit"


class ResultsEndpoint:
    """Ergebnisbewertung im Nutzerinfo-Tab (Baustelle 4, Backend zu Build 387)."""

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle = bundle
        self._context = context
        self._config = config

    # ------------------------------------------------------------------ Hilfen
    def _coordinator_path(self) -> Optional[str]:
        try:
            p = self._config.get("paths.coordinator_db")
            return str(p) if p else None
        except Exception as exc:                       # noqa: BLE001
            logger.error("results: coordinator.db-Pfad nicht lesbar: %s", exc)
            return None

    def _con(self, *, write: bool) -> sqlite3.Connection:
        path = self._coordinator_path()
        if not path:
            raise RuntimeError(
                "Kein coordinator.db-Pfad (paths.coordinator_db in config.yaml).")
        if write:
            con = sqlite3.connect(path)
            con.isolation_level = None
        else:
            con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _json(handler: "ForensicRequestHandler", status: int,
              payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            status, body, content_type="application/json; charset=utf-8")

    def _policy(self, con: sqlite3.Connection):
        from management.rbac.rbac_resolver import RbacResolver
        pid = getattr(self._context, "investigator_id", None)
        if pid is None:
            return None
        return RbacResolver(con).resolve(int(pid))

    # -------------------------------------------------------------------- GET
    def handle(self, handler: "ForensicRequestHandler", params=None) -> None:
        """GET /_forensic/results — alles, was die Maske braucht, in EINEM Abruf."""
        from management.results.assessment_catalog_repo import (
            AssessmentCatalogRepo, CatalogError,
        )
        from management.results.priority_scorer import PriorityScorer
        from management.results.results_repo import ResultsRepo

        user_id = int(self._context.user_id)

        try:
            con = self._con(write=False)
        except Exception as exc:                       # noqa: BLE001
            logger.error("results GET: %s", exc)
            self._json(handler, 500, {
                "error": "coordinator_unavailable", "detail": str(exc)})
            return

        try:
            policy = self._policy(con)
            if policy is None:
                # Kein angemeldeter Ermittler aufloesbar -> NICHT still leer.
                self._json(handler, 403, {
                    "error": "no_investigator",
                    "detail": "Der angemeldete Ermittler konnte nicht "
                              "aufgeloest werden (person.id). Ohne Handelnden "
                              "gibt es keine Bewertung."})
                return
            if not policy.can(CAP_VIEW):
                self._json(handler, 403, {
                    "error": "forbidden", "capability": CAP_VIEW,
                    "detail": "Die Faehigkeit '%s' ist nicht vergeben. Bitte "
                              "an die Chef-Ermittlerin wenden." % CAP_VIEW})
                return

            cat = AssessmentCatalogRepo(con)
            repo = ResultsRepo(con)
            catalog = cat.full()
            current = repo.current(user_id)
            history = repo.history(user_id)
            alle = [c["code"] for c in cat.criteria()]
            score = PriorityScorer().score_with_gaps(current, alle)

        except CatalogError as exc:
            # Migration M011 fehlt o. Ae. — MELDEN, nicht verschweigen.
            logger.error("results GET: Katalog nicht lesbar: %s", exc)
            self._json(handler, 500, {
                "error": "catalog_unavailable", "detail": str(exc)})
            return
        except Exception as exc:                       # noqa: BLE001
            logger.exception("results GET fehlgeschlagen")
            self._json(handler, 500, {"error": "results_failed",
                                      "detail": str(exc)})
            return
        finally:
            con.close()

        self._json(handler, 200, {
            "user_id": user_id,
            "can_edit": bool(policy.can(CAP_EDIT)),
            "catalog": catalog,
            "current": current,
            "history": history,
            "score": score,
        })
        logger.debug("/_forensic/results: Fall %d, %d aktuelle Bewertungen, "
                     "%d Historieneintraege", user_id, len(current),
                     len(history))

    # ------------------------------------------------------------------- POST
    def handle_assess(self, handler: "ForensicRequestHandler",
                      body: bytes) -> None:
        """
        POST /_forensic/results/assess — eine Bewertung erfassen.

        APPEND-ONLY: jede Erfassung ist eine NEUE Zeile mit eigenem Beleg.
        Die user_id kommt AUSSCHLIESSLICH aus dem Kontext (s. Kopfkommentar).
        """
        from management.audit.audit_log import AuditLog
        from management.gateway.coordinator_writer import CoordinatorWriter
        from management.results.assessment_catalog_repo import CatalogError
        from management.results.results_repo import ResultsError, ResultsRepo

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (ValueError, UnicodeDecodeError) as exc:
            self._json(handler, 400, {"error": "bad_json", "detail": str(exc)})
            return
        if not isinstance(payload, dict):
            self._json(handler, 400, {
                "error": "bad_request", "detail": "JSON-Objekt erwartet."})
            return

        user_id = int(self._context.user_id)

        # (1) Ein 'user_id' im Body wird IGNORIERT — und das wird protokolliert.
        #     Es koennte ein Versuch sein, einen fremden Fall zu bewerten.
        if "user_id" in payload and int(payload["user_id"] or 0) != user_id:
            logger.warning(
                "/_forensic/results/assess: user_id=%s im Rumpf wird IGNORIERT "
                "— bewertet wird ausschliesslich der geoeffnete Fall %d.",
                payload.get("user_id"), user_id)

        pid = getattr(self._context, "investigator_id", None)
        if pid is None:
            self._json(handler, 403, {
                "error": "no_investigator",
                "detail": "Kein Handelnder aufloesbar — ein Beleg ohne "
                          "Handelnden ist kein Beleg. Es wurde NICHTS "
                          "geschrieben."})
            return

        try:
            con = self._con(write=True)
        except Exception as exc:                       # noqa: BLE001
            logger.error("results POST: %s", exc)
            self._json(handler, 500, {
                "error": "coordinator_unavailable", "detail": str(exc)})
            return

        try:
            policy = self._policy(con)
            if policy is None or not policy.can(CAP_EDIT):
                self._json(handler, 403, {
                    "error": "forbidden", "capability": CAP_EDIT,
                    "detail": "Die Faehigkeit '%s' ist nicht vergeben. Es "
                              "wurde NICHTS geschrieben." % CAP_EDIT})
                return

            repo = ResultsRepo(con, CoordinatorWriter(con, AuditLog(con)))
            res = repo.assess(
                user_id=user_id,
                criterion_code=str(payload.get("criterion_code", "")),
                extrem=str(payload.get("extrem", "")),
                confidence_code=str(payload.get("confidence_code", "")),
                quality_code=(payload.get("quality_code") or None),
                note=str(payload.get("note", "")),
                actor_id=int(pid),
            )
        except (ResultsError, CatalogError) as exc:
            self._json(handler, 400, {"error": "bad_request",
                                      "detail": str(exc)})
            return
        except Exception as exc:                       # noqa: BLE001
            logger.exception("results POST fehlgeschlagen")
            self._json(handler, 500, {"error": "assess_failed",
                                      "detail": str(exc)})
            return
        finally:
            con.close()

        logger.info("/_forensic/results/assess: Fall %d, %s/%s -> %s "
                    "(Bewertung %s, Beleg #%s)", user_id,
                    payload.get("criterion_code"), payload.get("extrem"),
                    payload.get("confidence_code"), res["result_id"],
                    res["audit_seq"])
        self._json(handler, 200, {"ok": True, **res})
