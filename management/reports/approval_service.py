# =============================================================================
# management/reports/approval_service.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Berichts-Versiegelung
# =============================================================================
# ApprovalService — fuehrt die FREIGABE (Versiegelung) eines Berichts durch und
# prueft ein bestehendes Siegel nach.
#
# DAS ZWEI-DATENBANKEN-PROBLEM (offen benannt, nicht versteckt):
#   Der Beleg (audit_log) liegt in coordinator.db, der Bericht in
#   evidence_<uid>.db, das Siegel in approved_reports.db. Es gibt KEINE
#   gemeinsame Transaktion ueber drei SQLite-Dateien. Ein "atomares" Versprechen
#   waere gelogen. Statt es zu verschweigen, machen wir die Reihenfolge
#   nachvollziehbar und jeden Teilfehler SICHTBAR (Grundregel 1):
#
#     Schritt 1  Bericht lesen + Inhaltshash bilden      (evidence, read-only)
#     Schritt 2  BELEG schreiben (REPORT_APPROVED)       (coordinator, auditiert)
#     Schritt 3  SIEGEL ablegen (Abbild + Hash)          (approved_reports.db)
#     Schritt 4  DURCHSETZUNG: status + report_approvals (evidence, schreibend)
#
#   Reihenfolge-Begruendung: Der Beleg steht ZUERST — er dokumentiert die
#   Absicht und traegt die audit_seq, auf die sich das Siegel beruft. Scheitert
#   Schritt 3 oder 4, bleibt der Beleg stehen (das ist richtig: der Versuch HAT
#   stattgefunden) und der Aufrufer bekommt einen expliziten Fehler mit der
#   Angabe, was gelungen ist. Ein erneuter Aufruf vervollstaendigt (Schritt 4
#   ist idempotent). Ein "stiller Teilerfolg" ist ausgeschlossen.
#
# WAS DAS SIEGEL LEISTET: Die evidence-seitige Sperre (status=approved/final)
#   schuetzt gegen den NORMALEN Weg (die Anwendung; Build 378). Gegen eine
#   direkte Manipulation der evidence-DB mit einem SQLite-Werkzeug schuetzt sie
#   NICHT — dagegen wirkt der zentrale Hash: verify() hasht den Bericht neu und
#   vergleicht. ABWEICHUNG = MANIPULATION, nachweisbar.
#
# Build 380: return_to_draft() — Rueckgabe zur Nachbesserung (submitted -> draft)
#   durch Lektor/Chef-Ermittlerin, auditiert (REPORT_RETURNED).
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

from management.audit.audit_log import AuditLog
from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter
from management.reports.approved_reports_db import ApprovedReportsDb
from management.reports.report_sealer import ReportSealer, ReportSealError

logger = logging.getLogger(__name__)

# Aus diesen Zustaenden heraus darf freigegeben werden.
_APPROVABLE = ("submitted",)
# 'final' ist die Aufwertung einer bestehenden Freigabe.
_FINALIZABLE = ("approved",)


class ApprovalError(Exception):
    """Fachlicher Fehler (Vorbedingung verletzt) — mit klarer Begruendung."""


class ApprovalService:
    """Freigabe (Versiegelung) und Nachpruefung von Berichten."""

    def __init__(self, coordinator_con: sqlite3.Connection,
                 evidence_dir: str, approved_db_path: str) -> None:
        self._con = coordinator_con
        self._evidence_dir = Path(evidence_dir)
        self._sealdb = ApprovedReportsDb(approved_db_path)

    # ---------------------------------------------------------------- public
    def approve(self, *, subject_id: int, report_id: int, actor_id: int,
                actor_username: str, is_final: bool = False,
                note: Optional[str] = None) -> Dict[str, Any]:
        ev = self._evidence_path(subject_id)
        sealer = ReportSealer(ev)

        # --- Schritt 1: lesen + hashen (read-only) --------------------------
        try:
            status = sealer.status_of(report_id)
            if status is None:
                raise ApprovalError("Bericht %s in Fall %s nicht gefunden."
                                    % (report_id, subject_id))
            if is_final and status not in _FINALIZABLE:
                raise ApprovalError(
                    "Endgueltige Freigabe nur aus Status %s moeglich "
                    "(aktuell: %s)." % ("/".join(_FINALIZABLE), status))
            if (not is_final) and status not in _APPROVABLE:
                raise ApprovalError(
                    "Freigabe nur aus Status %s moeglich (aktuell: %s)."
                    % ("/".join(_APPROVABLE), status))
            snap = sealer.snapshot(report_id)
        except ReportSealError as exc:
            raise ApprovalError(str(exc))

        digest = snap["content_sha256"]
        new_status = "final" if is_final else "approved"

        # --- Schritt 2: BELEG (coordinator, auditiert) ----------------------
        writer = CoordinatorWriter(self._con, AuditLog(self._con))

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            # Der Beleg selbst traegt die Nutzlast; es gibt keine eigene
            # coordinator-Tabelle fuer Freigaben (das Siegel liegt zentral).
            return {"subject_id": subject_id, "report_id": report_id,
                    "content_sha256": digest, "is_final": bool(is_final),
                    "new_status": new_status, "note": note}

        audit_seq = writer.audited_write(
            do_write=_w, event_type=EventType.REPORT_APPROVED,
            actor_id=actor_id, target_type="report",
            target_id="%d/%d" % (subject_id, report_id),
            meta={"content_sha256": digest, "is_final": bool(is_final)})

        # --- Schritt 3: SIEGEL zentral ablegen ------------------------------
        try:
            seal_id = self._sealdb.seal(
                subject_id=subject_id, report_id=report_id, content_sha256=digest,
                snapshot_json=ReportSealer.snapshot_json(snap),
                report=snap["report"], approved_by=actor_username,
                approved_by_id=actor_id, is_final=is_final, note=note,
                audit_seq=audit_seq)
        except sqlite3.Error as exc:
            logger.exception("Siegel konnte nicht abgelegt werden")
            raise ApprovalError(
                "Beleg #%d geschrieben, aber das zentrale Siegel konnte NICHT "
                "abgelegt werden (%s). Der Bericht ist NICHT freigegeben. "
                "Bitte erneut versuchen." % (audit_seq, exc))

        # --- Schritt 4: DURCHSETZUNG in evidence ----------------------------
        try:
            self._write_evidence(ev, report_id, new_status, actor_username,
                                 is_final, note)
        except sqlite3.Error as exc:
            logger.exception("evidence-Sperre fehlgeschlagen")
            raise ApprovalError(
                "Beleg #%d und Siegel #%d liegen vor, aber der Status in der "
                "evidence-DB konnte NICHT gesetzt werden (%s). Der Bericht ist "
                "damit noch NICHT gegen Aenderungen gesperrt. Bitte erneut "
                "versuchen." % (audit_seq, seal_id, exc))

        return {"ok": True, "subject_id": subject_id, "report_id": report_id,
                "status": new_status, "content_sha256": digest,
                "audit_seq": audit_seq, "seal_id": seal_id}

    def return_to_draft(self, *, subject_id: int, report_id: int, actor_id: int,
                        actor_username: str,
                        note: Optional[str] = None) -> Dict[str, Any]:
        """
        RUECKGABE ZUR NACHBESSERUNG (Build 380): submitted -> draft.

        Nur aus 'submitted'. Ein 'approved' oder 'final' Bericht wird NIE
        zurueckgestuft (BERICHTS-STATUSMODELL, mc 2026-07-10) — inhaltliche
        Schwaechen eines abgenommenen Berichts werden ueber einen
        NACHTRAGSBERICHT (report_type='addendum') behandelt.

        Berechtigt sind Lektor (reports.review) und Chef-Ermittlerin
        (reports.approve, impliziert review). Der AUTOR kann sich NICHT selbst
        zurueckholen — das ist der Sinn der Sperre.

        Nur EINE Datenbank ist betroffen (evidence) plus der Beleg
        (coordinator): der Beleg wird ZUERST geschrieben, dann der Status
        gesetzt. Scheitert der zweite Schritt, bleibt der Beleg stehen (der
        Versuch hat stattgefunden) und der Aufrufer bekommt einen expliziten
        Fehler (Grundregel 1).
        """
        ev = self._evidence_path(subject_id)
        sealer = ReportSealer(ev)

        try:
            status = sealer.status_of(report_id)
        except ReportSealError as exc:
            raise ApprovalError(str(exc))
        if status is None:
            raise ApprovalError("Bericht %s in Fall %s nicht gefunden."
                                % (report_id, subject_id))
        if status != "submitted":
            raise ApprovalError(
                "Rueckgabe nur aus Status 'submitted' moeglich (aktuell: '%s'). "
                "Abgenommene ('approved') und versandte ('final') Berichte "
                "werden nicht zurueckgestuft; inhaltliche Schwaechen werden "
                "ueber einen Nachtragsbericht behandelt." % status)

        writer = CoordinatorWriter(self._con, AuditLog(self._con))

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            return {"subject_id": subject_id, "report_id": report_id,
                    "from_status": status, "to_status": "draft", "note": note}

        audit_seq = writer.audited_write(
            do_write=_w, event_type=EventType.REPORT_RETURNED,
            actor_id=actor_id, target_type="report",
            target_id="%d/%d" % (subject_id, report_id),
            meta={"returned_by": actor_username, "note": note})

        try:
            self._set_evidence_status(ev, report_id, "draft")
        except sqlite3.Error as exc:
            logger.exception("Rueckgabe fehlgeschlagen")
            raise ApprovalError(
                "Beleg #%d geschrieben, aber der Status konnte NICHT auf "
                "'draft' gesetzt werden (%s). Der Bericht ist damit noch NICHT "
                "zurueckgegeben. Bitte erneut versuchen." % (audit_seq, exc))

        return {"ok": True, "subject_id": subject_id, "report_id": report_id,
                "status": "draft", "audit_seq": audit_seq}

    @staticmethod
    def _set_evidence_status(ev: Path, report_id: int, status: str) -> None:
        """
        Setzt den Status direkt (Management-Pfad). Bewusst NICHT ueber
        EvidenceDb.update_report_status: dessen Zustandsmaschine (Build 379)
        schuetzt den ERMITTLER-Pfad; der Management-Pfad ist der autorisierte
        Weg, der genau diese Uebergaenge vornehmen DARF (und dabei auditiert).
        """
        con = sqlite3.connect(str(ev))
        try:
            con.isolation_level = None
            con.execute("BEGIN IMMEDIATE")
            con.execute("UPDATE reports SET status=? WHERE id=?",
                        (status, report_id))
            con.execute("COMMIT")
        except Exception:
            try:
                con.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            con.close()

    def verify(self, *, subject_id: int, report_id: int) -> Dict[str, Any]:
        """
        Nachpruefung: aktuellen Berichtsinhalt neu hashen und mit dem zentral
        hinterlegten Siegel vergleichen. ABWEICHUNG = MANIPULATION.
        """
        seal = self._sealdb.latest_seal(subject_id, report_id)
        result: Dict[str, Any] = {
            "subject_id": subject_id, "report_id": report_id,
            "sealed": seal is not None, "checked_at": int(time.time()),
        }
        if seal is None:
            result["match"] = None
            result["detail"] = "Kein Siegel vorhanden (nicht freigegeben)."
            return result

        result["sealed_sha256"] = seal["content_sha256"]
        result["approved_by"] = seal["approved_by"]
        result["approved_at"] = seal["approved_at"]
        result["is_final"] = bool(seal["is_final"])
        result["audit_seq"] = seal["audit_seq"]

        try:
            current = ReportSealer(
                self._evidence_path(subject_id)).content_hash(report_id)
        except ReportSealError as exc:
            result["match"] = False
            result["detail"] = ("Bericht nicht mehr lesbar: %s" % exc)
            return result

        result["current_sha256"] = current
        result["match"] = (current == seal["content_sha256"])
        result["detail"] = ("Inhalt entspricht dem Siegel."
                            if result["match"] else
                            "ABWEICHUNG: Der Berichtsinhalt weicht vom "
                            "versiegelten Stand ab.")
        return result

    # ------------------------------------------------------------- internals
    def _evidence_path(self, subject_id: int) -> Path:
        return self._evidence_dir / ("evidence_%d.db" % subject_id)

    @staticmethod
    def _write_evidence(ev: Path, report_id: int, new_status: str,
                        approved_by: str, is_final: bool,
                        note: Optional[str]) -> None:
        """
        Durchsetzung in der evidence-DB: report_approvals + reports.status.
        NUR bestehende Tabellen/Spalten — KEINE Schemaaenderung (evidence steht
        unter Migrationsvorbehalt). Idempotent genug: ein erneuter Aufruf setzt
        denselben Status und legt einen weiteren (belegten) Approval-Eintrag an.
        """
        con = sqlite3.connect(str(ev))
        try:
            con.isolation_level = None
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                "INSERT INTO report_approvals "
                "(report_id, approved_by, approved_at, note, is_final) "
                "VALUES (?, ?, ?, ?, ?)",
                (report_id, approved_by, int(time.time()), note,
                 1 if is_final else 0))
            con.execute("UPDATE reports SET status=? WHERE id=?",
                        (new_status, report_id))
            con.execute("COMMIT")
        except Exception:
            try:
                con.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            con.close()
