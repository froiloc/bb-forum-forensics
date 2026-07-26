# =============================================================================
# forensic_api/tatzeit_endpoint.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A, Build 533)
# =============================================================================
# Zweck:
#   GET  /_forensic/tatzeit        — Vokabular + erfasste Tatzeitangaben zu
#                                    einer Annotation
#   POST /_forensic/tatzeit        — eine Tatzeitangabe erfassen oder durch
#                                    eine neue Version ersetzen (APPEND-ONLY)
#   POST /_forensic/tatzeit/clear  — eine Tatzeitangabe zuruecknehmen
#
#   Die Ermittlerin arbeitet am FORENSISCHEN Webserver, nicht am Cockpit — die
#   Tatzeit gehoert in die Annotation, und die Annotation entsteht beim Lesen
#   der Forumsseite (Entscheidung mc 2026-07-26, Uebergabe §2.2 Nr. 6).
#   Aufbau und Reihenfolge der Pruefungen sind bewusst deckungsgleich mit
#   forensic_api/results_endpoint.py; wo dort etwas anders ist, steht der
#   Grund dabei.
#
# ── VIER FESTLEGUNGEN, DIE DIE KAPSELUNG TRAGEN ──────────────────────────────
#
# (1) DIE subject_id KOMMT NICHT AUS DEM RUMPF.
#     Wie bei results_endpoint.py:20-27. Dieser Server hat genau EINEN Fall
#     geoeffnet; die Tatzeit landet zwangslaeufig in DESSEN evidence-Datei. Ein
#     Beschreiben fremder Faelle ist damit STRUKTURELL unmoeglich und nicht
#     nur durch eine Pruefung verhindert. Genau deshalb ist 'tatzeit.edit'
#     nicht scope-behaftet (M032-Kopf).
#
# (2) DER SCHREIBPFAD BENUTZT DIE GETEILTE VERBINDUNG — anders als results.
#     ResultsEndpoint oeffnet fuer den Write eine EIGENE Verbindung
#     (results_endpoint.py:28-33), weil coordinator.db am Bundle nur als ATTACH
#     haengt. Hier ist es umgekehrt: evidence_<uid>.db IST die Hauptverbindung
#     des Servers (db/connection_manager.py:203). Eine zweite Verbindung darauf
#     waere ein zweiter Schreiber auf derselben Datei — ausdruecklich verboten
#     (db/review_addendum_db.py:8-11). EvidenceWriter benutzt deshalb die
#     geteilte Verbindung und haelt fuer die Dauer der Transaktion deren
#     oeffentlichen Lock (db/locking_connection.py:34-35).
#
# (3) IM SUPPORT-MODUS WIRD NICHT GESCHRIEBEN, UND ZWAR LAUT.
#     Im Live-Beistand ist die Hauptverbindung eine TEMP-DB, und die echte
#     evidence-Datei haengt READ-ONLY als 'edb' daran
#     (db/connection_manager.py:363-366, :415-417). Ein Schreibversuch liefe
#     entweder ins Leere oder in die TEMP-Datei, die beim Sitzungsende geloescht
#     wird (:126-128). Beides waere ein LAUTLOS verlorener Beleg. Der Endpunkt
#     antwortet deshalb mit 409 und einer Begruendung.
#
# (4) DIE RECHTE WERDEN GEPRUEFT — GEGEN coordinator.db.
#     RbacResolver ueber context.investigator_id, mit einer eigenen ro-
#     Verbindung auf coordinator.db (Muster results_endpoint.py:107-113). Sie
#     ist noetig, weil RbacResolver unqualifizierte Tabellennamen benutzt, die
#     am Bundle nur unter dem ATTACH-Praefix 'cdb.' erreichbar waeren.
#     Fehlt der Grant: 403 MIT BEGRUENDUNG, damit die Ermittlerin weiss, WARUM
#     sie nichts erfassen kann. Ohne aufloesbaren Handelnden wird NICHTS
#     geschrieben — ein Beleg ohne Handelnden ist kein Beleg.
#
# ── LESEN BRAUCHT KEIN EIGENES RECHT ─────────────────────────────────────────
#
#   GET ist an die Annotation gebunden, nicht an ein eigenes Recht (Begruendung
#   im Katalog, catalog.py bei 'tatzeit.edit'). Die Antwort traegt 'can_edit'
#   mit, damit die Maske die Felder gesperrt statt unsichtbar zeigen kann —
#   eine unsichtbare Funktion sieht aus wie eine fehlende.
#
# Version: v0.8.533 · Build: 533 · 2026-07-26
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

CAP_EDIT = "tatzeit.edit"


class TatzeitEndpoint:
    """Erfassung des Tatzeitraums zu einer Annotation (AP-3A, Build 533)."""

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
    @staticmethod
    def _json(handler: "ForensicRequestHandler", status: int,
              payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            status, body, content_type="application/json; charset=utf-8")

    def _coordinator_path(self) -> Optional[str]:
        try:
            p = self._config.get("paths.coordinator_db")
            return str(p) if p else None
        except Exception as exc:                       # noqa: BLE001
            logger.error("tatzeit: coordinator.db-Pfad nicht lesbar: %s", exc)
            return None

    def _coordinator_ro(self) -> sqlite3.Connection:
        """Eigene READ-ONLY-Verbindung auf coordinator.db (nur fuer RBAC)."""
        path = self._coordinator_path()
        if not path:
            raise RuntimeError(
                "Kein coordinator.db-Pfad (paths.coordinator_db in config.yaml).")
        con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        con.row_factory = sqlite3.Row
        return con

    def _policy(self, con: sqlite3.Connection):
        from management.rbac.rbac_resolver import RbacResolver
        pid = getattr(self._context, "investigator_id", None)
        if pid is None:
            return None
        return RbacResolver(con).resolve(int(pid))

    def _darf_schreiben(self) -> bool:
        """
        True, wenn der angemeldete Ermittler 'tatzeit.edit' hat.
        Fehler beim Aufloesen werden als 'nein' gewertet UND protokolliert —
        nicht als 'ja'. Im Zweifel wird nicht geschrieben.
        """
        try:
            con = self._coordinator_ro()
        except Exception as exc:                       # noqa: BLE001
            logger.error("tatzeit: RBAC nicht pruefbar: %s", exc)
            return False
        try:
            policy = self._policy(con)
            return bool(policy is not None and policy.can(CAP_EDIT))
        except Exception:                              # noqa: BLE001
            logger.exception("tatzeit: RBAC-Aufloesung fehlgeschlagen")
            return False
        finally:
            con.close()

    def _ist_support(self) -> bool:
        return str(getattr(self._context, "mode", "")) == "support"

    def _repo(self, *, write: bool):
        """
        TatzeitRepo auf der GETEILTEN evidence-Verbindung (s. Festlegung 2).
        Ohne write=True bekommt es keinen EvidenceWriter und ist damit
        strukturell lesend.
        """
        from db.tatzeit_repo import TatzeitRepo
        con = self._bundle.connection
        if not write:
            return TatzeitRepo(con)
        from management.audit.evidence_audit_log import EvidenceAuditLog
        from management.gateway.evidence_writer import EvidenceWriter
        return TatzeitRepo(con, EvidenceWriter(con, EvidenceAuditLog(con)))

    @staticmethod
    def _kette_fehlt_hinweis() -> Dict[str, Any]:
        return {
            "error": "audit_chain_missing",
            "detail": "Die Beleg-Kette in dieser Beweismitteldatenbank fehlt "
                      "(evidence-Migration m003 nicht angewandt). Ohne Kette "
                      "gibt es keinen Beleg, und ohne Beleg wird nicht "
                      "geschrieben. Es wurde NICHTS geschrieben.",
        }

    # -------------------------------------------------------------------- GET
    def handle(self, handler: "ForensicRequestHandler", params=None) -> None:
        """
        GET /_forensic/tatzeit?annotation_id=<n>[&local_id=<s>][&historie=1]

        Liefert alles, was die Maske braucht, in EINEM Abruf: das kontrollierte
        Vokabular, den Plausibilitaetsrahmen und die erfassten Angaben.
        """
        from db.tatzeit_repo import TatzeitError
        from db.tatzeit_vokabular import (
            ANGABE_SCHLUESSEL, ARTEN, GENAUIGKEITEN, quellen_katalog,
        )
        from management.deadlines.limitation_repo import (
            PLAUSIBEL_BIS, PLAUSIBEL_VON,
        )

        params = params or {}
        roh_ann = (params.get("annotation_id") or [None])[0]
        roh_loc = (params.get("local_id") or [None])[0]
        historie = (params.get("historie") or ["0"])[0] in ("1", "true", "ja")

        annotation_id: Optional[int] = None
        if roh_ann is not None:
            try:
                annotation_id = int(roh_ann)
            except (TypeError, ValueError):
                self._json(handler, 400, {
                    "error": "bad_request",
                    "detail": "annotation_id ist keine Ganzzahl: %r" % roh_ann})
                return

        try:
            eintraege = self._repo(write=False).liste(
                annotation_id=annotation_id,
                annotation_local_id=roh_loc,
                mit_historie=historie,
            )
        except TatzeitError as exc:
            self._json(handler, 400, {"error": "bad_request",
                                      "detail": str(exc)})
            return
        except sqlite3.OperationalError as exc:
            # Tabelle fehlt -> m002 nicht angewandt. MELDEN, nicht verschweigen:
            # eine leere Liste saehe aus wie "nichts erfasst".
            logger.error("tatzeit GET: %s", exc)
            self._json(handler, 500, {
                "error": "tatzeit_table_missing",
                "detail": "Die Tabelle 'annotation_tatzeit' ist in dieser "
                          "Beweismitteldatenbank nicht vorhanden "
                          "(evidence-Migration m002 nicht angewandt): %s" % exc})
            return
        except Exception as exc:                       # noqa: BLE001
            logger.exception("tatzeit GET fehlgeschlagen")
            self._json(handler, 500, {"error": "tatzeit_failed",
                                      "detail": str(exc)})
            return

        self._json(handler, 200, {
            "ok": True,
            "subject_id": int(self._context.subject_id),
            "annotation_id": annotation_id,
            "local_id": roh_loc,
            "can_edit": self._darf_schreiben() and not self._ist_support(),
            "readonly_grund": ("support" if self._ist_support() else None),
            "vokabular": {
                "arten": sorted(ARTEN),
                "genauigkeiten": sorted(GENAUIGKEITEN),
                "angabe_schluessel": sorted(ANGABE_SCHLUESSEL),
                "quellen": list(quellen_katalog()),
            },
            "plausibel_von": PLAUSIBEL_VON,
            "plausibel_bis": PLAUSIBEL_BIS,
            # Der Monitor rechnet mit dieser Angabe noch NICHT. Die Maske sagt
            # das der Ermittlerin, damit sie keine Wirkung erwartet, die es
            # erst ab Build 535 gibt.
            "wird_berechnet": False,
            "eintraege": eintraege,
        })

    # ------------------------------------------------------------------- POST
    def handle_set(self, handler: "ForensicRequestHandler",
                   body: bytes) -> None:
        """POST /_forensic/tatzeit — erfassen oder durch neue Version ersetzen."""
        from db.tatzeit_repo import TatzeitError
        from management.gateway.evidence_writer import EvidenceWriteError

        payload = self._rumpf(handler, body)
        if payload is None:
            return

        pid = self._handelnder(handler)
        if pid is None:
            return
        if self._blockiert(handler):
            return

        try:
            res = self._repo(write=True).setzen(
                annotation_id=int(payload.get("annotation_id") or 0),
                annotation_local_id=(payload.get("local_id") or None),
                art=str(payload.get("art", "")),
                quelle_code=str(payload.get("quelle_code", "")),
                quelle_freitext=(payload.get("quelle_freitext") or None),
                actor_id=int(pid),
                von_ts=payload.get("von_ts"),
                bis_ts=payload.get("bis_ts"),
                genauigkeit=(payload.get("genauigkeit") or None),
                angabe_schluessel=(payload.get("angabe_schluessel") or None),
                angabe_wert=(payload.get("angabe_wert") or None),
                wortlaut=(payload.get("wortlaut") or None),
                ersetzt_id=(int(payload["ersetzt_id"])
                            if payload.get("ersetzt_id") else None),
            )
        except TatzeitError as exc:
            self._json(handler, 400, {"error": "bad_request",
                                      "detail": str(exc)})
            return
        except EvidenceWriteError as exc:
            self._json(handler, 409, {"error": "write_refused",
                                      "detail": str(exc)})
            return
        except sqlite3.OperationalError as exc:
            if "evidence_audit_log" in str(exc):
                self._json(handler, 500, self._kette_fehlt_hinweis())
                return
            logger.exception("tatzeit POST fehlgeschlagen")
            self._json(handler, 500, {"error": "tatzeit_failed",
                                      "detail": str(exc)})
            return
        except Exception as exc:                       # noqa: BLE001
            logger.exception("tatzeit POST fehlgeschlagen")
            self._json(handler, 500, {"error": "tatzeit_failed",
                                      "detail": str(exc)})
            return

        logger.info("/_forensic/tatzeit: Fall %s, Annotation %s -> Tatzeit #%s "
                    "(Version %s, Beleg seq=%s)",
                    self._context.subject_id, payload.get("annotation_id"),
                    res["tatzeit_id"], res["version_nr"], res["audit_seq"])
        self._json(handler, 200, {"ok": True, **res})

    def handle_clear(self, handler: "ForensicRequestHandler",
                     body: bytes) -> None:
        """POST /_forensic/tatzeit/clear — eine Angabe zuruecknehmen."""
        from db.tatzeit_repo import TatzeitError
        from management.gateway.evidence_writer import EvidenceWriteError

        payload = self._rumpf(handler, body)
        if payload is None:
            return

        pid = self._handelnder(handler)
        if pid is None:
            return
        if self._blockiert(handler):
            return

        try:
            res = self._repo(write=True).zuruecknehmen(
                tatzeit_id=int(payload.get("tatzeit_id") or 0),
                actor_id=int(pid),
                grund=(payload.get("grund") or None),
            )
        except TatzeitError as exc:
            self._json(handler, 400, {"error": "bad_request",
                                      "detail": str(exc)})
            return
        except EvidenceWriteError as exc:
            self._json(handler, 409, {"error": "write_refused",
                                      "detail": str(exc)})
            return
        except Exception as exc:                       # noqa: BLE001
            logger.exception("tatzeit clear fehlgeschlagen")
            self._json(handler, 500, {"error": "tatzeit_failed",
                                      "detail": str(exc)})
            return

        logger.info("/_forensic/tatzeit/clear: Tatzeit #%s zurueckgenommen "
                    "(Beleg seq=%s)", res["tatzeit_id"], res["audit_seq"])
        self._json(handler, 200, {"ok": True, **res})

    # ------------------------------------------------- gemeinsame Vorpruefungen
    def _rumpf(self, handler: "ForensicRequestHandler",
               body: bytes) -> Optional[Dict[str, Any]]:
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (ValueError, UnicodeDecodeError) as exc:
            self._json(handler, 400, {"error": "bad_json", "detail": str(exc)})
            return None
        if not isinstance(payload, dict):
            self._json(handler, 400, {
                "error": "bad_request", "detail": "JSON-Objekt erwartet."})
            return None

        # Ein 'subject_id' im Rumpf wird IGNORIERT — und das wird protokolliert.
        # Es koennte ein Versuch sein, einen fremden Fall zu beschreiben
        # (Muster results_endpoint.py:214-220).
        subject_id = int(self._context.subject_id)
        if "subject_id" in payload and int(payload["subject_id"] or 0) != subject_id:
            logger.warning(
                "/_forensic/tatzeit: subject_id=%s im Rumpf wird IGNORIERT — "
                "geschrieben wird ausschliesslich in den geoeffneten Fall %d.",
                payload.get("subject_id"), subject_id)
        return payload

    def _handelnder(self, handler: "ForensicRequestHandler") -> Optional[int]:
        pid = getattr(self._context, "investigator_id", None)
        if pid is None:
            self._json(handler, 403, {
                "error": "no_investigator",
                "detail": "Kein Handelnder aufloesbar — ein Beleg ohne "
                          "Handelnden ist kein Beleg. Es wurde NICHTS "
                          "geschrieben."})
            return None
        return int(pid)

    def _blockiert(self, handler: "ForensicRequestHandler") -> bool:
        """True, wenn nicht geschrieben werden darf (Antwort ist dann raus)."""
        if self._ist_support():
            self._json(handler, 409, {
                "error": "support_mode",
                "detail": "Im Live-Beistand ist die Beweismitteldatenbank nur "
                          "lesend angebunden; die Hauptverbindung ist eine "
                          "TEMP-Datei, die beim Sitzungsende geloescht wird. "
                          "Eine hier erfasste Tatzeit waere lautlos verloren. "
                          "Es wurde NICHTS geschrieben."})
            return True
        if not self._darf_schreiben():
            self._json(handler, 403, {
                "error": "forbidden", "capability": CAP_EDIT,
                "detail": "Die Faehigkeit '%s' ist nicht vergeben. Bitte an "
                          "die Chef-Ermittlerin wenden. Es wurde NICHTS "
                          "geschrieben." % CAP_EDIT})
            return True
        return False
