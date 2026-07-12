# =============================================================================
# management/reports/reports_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Berichts-Abnahme
# =============================================================================
# ReportsRepo — liest die Berichte ALLER Faelle (evidence_<uid>.db) fuer die
# Abnahme-Sicht. Rein lesend; die evidence-DBs werden ausschliesslich mit
# mode=ro geoeffnet (sie sind ab dem Produktivstart Ergebnis-DBs der Ermittler).
#
# CACHE-STRATEGIE (mc 2026-07-10):
#   Je Fall wird ein Fingerabdruck ueber ALLE DB-Dateien gebildet
#   (EvidenceScanner; WAL-sicher). Stimmt er mit dem in coordinator.db
#   gespeicherten (m009: evidence_scan_cache) ueberein, wird die evidence-DB
#   NICHT geoeffnet und die gecachte Berichtsliste verwendet. Sonst wird neu
#   eingelesen und der Cache aktualisiert.
#
#   Der Cache ist BERATEND: er beschleunigt, er beweist nichts. force=True
#   erzwingt den Vollscan (Cache wird ignoriert und neu geschrieben).
#
# GRUNDREGEL 1 (kein stiller Verlust): Eine nicht lesbare/defekte evidence-DB
#   wird NICHT uebersprungen, sondern als Fehlereintrag gemeldet (errors[]) und
#   im Cache mit 'error' vermerkt. Ein fehlender cases-Eintrag oder ein Fall
#   ohne DB ist ebenfalls ein sichtbarer Zustand, kein Schweigen.
#
# Version: v0.7.374 · Build: 374 · 2026-07-10
# =============================================================================

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from management.reports.evidence_scanner import EvidenceScanner

logger = logging.getLogger(__name__)

_REPORT_COLS = ("id", "report_type", "sequence_nr", "title", "created_by",
                "created_at", "status")


class ReportsRepo:
    """Berichtsuebersicht ueber alle evidence-DBs (read-only, cache-gestuetzt)."""

    def __init__(self, con: sqlite3.Connection, evidence_dir: str) -> None:
        # con: coordinator.db — SCHREIBEND noetig (Cache-Aktualisierung), aber
        # der Cache traegt keine Ermittlungsergebnisse (siehe m009).
        self._con = con
        self._scanner = EvidenceScanner(evidence_dir)
        # Einmalig gemerkter Cache-Fehler (Build 376): z. B. fehlende Tabelle,
        # weil Migration m009 nicht angewandt wurde. Wird in list_reports()
        # als 'cache_error' zurueckgegeben und im Cockpit ANGEZEIGT — statt je
        # Fall eine beilaeufige Logzeile zu erzeugen.
        self._cache_error = None

    # ---------------------------------------------------------------- public
    def list_reports(self, *, force: bool = False) -> Dict[str, Any]:
        cases = self._scanner.list_cases()
        cached = self._load_cache()
        usernames = self._case_usernames()
        assignees = self._case_assignees()

        reports: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        rescanned = 0

        for user_id, path in cases:
            fp = EvidenceScanner.fingerprint(path)
            hit = cached.get(user_id)
            if (not force) and hit and hit["fingerprint"] == fp:
                # Cache-Treffer: DB NICHT anfassen.
                if hit["error"]:
                    errors.append({"user_id": user_id, "error": hit["error"],
                                   "cached": True})
                    continue
                rows = json.loads(hit["reports_json"])
            else:
                rows, err = self._read_evidence(path)
                rescanned += 1
                # WICHTIG (gemessen, Build 374): Der ERSTE Lesezugriff LEGT die
                # -wal-Datei an. Wuerden wir den VOR dem Lesen gebildeten Abdruck
                # speichern, waeren die Dateien danach anders als gespeichert —
                # der naechste Scan wuerde erneut alles einlesen (Cache wirkungs-
                # los). Daher: Abdruck NACH dem Lesen bilden und ablegen.
                fp_after = EvidenceScanner.fingerprint(path)
                self._store_cache(user_id, fp_after, rows, err)
                if err:
                    errors.append({"user_id": user_id, "error": err,
                                   "cached": False})
                    continue

            for r in rows:
                item = dict(r)
                item["user_id"] = user_id
                item["username"] = usernames.get(user_id)
                item["assigned_to"] = assignees.get(user_id)
                reports.append(item)

        # Faelle, die in coordinator.db bekannt sind, aber KEINE evidence-DB
        # haben: sichtbar machen (kein Schweigen).
        have = {uid for uid, _ in cases}
        missing = [uid for uid in usernames if uid not in have]

        reports.sort(key=lambda r: (r["user_id"], r.get("sequence_nr") or 0,
                                    r.get("id") or 0))
        return {
            "evidence_dir": str(self._scanner.directory),
            "case_db_count": len(cases),
            "rescanned": rescanned,
            "count": len(reports),
            "reports": reports,
            "errors": errors,
            "cases_without_db": sorted(missing),
            # None = Cache in Ordnung; sonst der Grund (Betriebshinweis).
            "cache_error": self._cache_error,
        }

    # ------------------------------------------------------------- internals
    def _read_evidence(self, path: Path):
        """Liest die Berichte EINER evidence-DB (read-only). -> (rows, error)"""
        try:
            con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        except sqlite3.Error as exc:
            logger.warning("evidence-DB nicht oeffenbar: %s (%s)", path, exc)
            return [], "nicht oeffenbar: %s" % exc
        try:
            has = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='reports'").fetchone()
            if has is None:
                return [], "Tabelle 'reports' fehlt"

            cur = con.execute(
                "SELECT %s FROM reports ORDER BY sequence_nr ASC, id ASC"
                % ", ".join('"%s"' % c for c in _REPORT_COLS))
            rows = [dict(zip(_REPORT_COLS, r)) for r in cur.fetchall()]

            # Freigaben (falls vorhanden) je Bericht anzaehlen/anhaengen.
            if con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='report_approvals'").fetchone():
                for r in rows:
                    ap = con.execute(
                        "SELECT approved_by, approved_at, is_final, note "
                        "FROM report_approvals WHERE report_id=? "
                        "ORDER BY approved_at ASC", (r["id"],)).fetchall()
                    r["approvals"] = [
                        {"approved_by": a[0], "approved_at": a[1],
                         "is_final": bool(a[2]), "note": a[3]} for a in ap]
            else:
                for r in rows:
                    r["approvals"] = []
            return rows, None
        except sqlite3.Error as exc:
            logger.warning("evidence-DB nicht lesbar: %s (%s)", path, exc)
            return [], "nicht lesbar: %s" % exc
        finally:
            try:
                con.close()
            except Exception:
                pass

    def _load_cache(self) -> Dict[int, Dict[str, Any]]:
        try:
            cur = self._con.execute(
                "SELECT user_id, fingerprint, reports_json, error "
                "FROM evidence_scan_cache")
        except sqlite3.Error:
            return {}
        return {r[0]: {"fingerprint": r[1], "reports_json": r[2],
                       "error": r[3]} for r in cur.fetchall()}

    def _store_cache(self, user_id: int, fingerprint: str,
                     rows: List[Dict[str, Any]], error: Optional[str]) -> None:
        try:
            self._con.execute(
                "INSERT INTO evidence_scan_cache "
                "(user_id, fingerprint, reports_json, scanned_at, error) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "  fingerprint=excluded.fingerprint, "
                "  reports_json=excluded.reports_json, "
                "  scanned_at=excluded.scanned_at, error=excluded.error",
                (user_id, fingerprint, json.dumps(rows, ensure_ascii=False),
                 int(time.time()), error))
        except sqlite3.Error as exc:
            # Cache-Fehler duerfen die Sicht nicht kippen — aber sie werden
            # protokolliert UND (Build 376) einmalig gemerkt, damit der Aufrufer
            # den Zustand SICHTBAR machen kann, statt ihn je Fall beilaeufig zu
            # loggen. Typischer Fall: Migration m009 nicht angewandt.
            if self._cache_error is None:
                self._cache_error = str(exc)
                logger.warning("Scan-Cache nicht schreibbar: %s "
                               "(Migrationen angewandt? "
                               "'python -m management.migrate')", exc)

    def _case_usernames(self) -> Dict[int, str]:
        try:
            return {r[0]: r[1] for r in self._con.execute(
                "SELECT user_id, username FROM cases")}
        except sqlite3.Error:
            return {}

    def _case_assignees(self) -> Dict[int, Optional[int]]:
        try:
            return {r[0]: r[1] for r in self._con.execute(
                "SELECT user_id, assigned_to FROM cases")}
        except sqlite3.Error:
            return {}
