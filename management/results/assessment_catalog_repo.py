# =============================================================================
# management/results/assessment_catalog_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Der KATALOG der Bewertung: Skalen, Skalenpunkte, Kriterien.
#
#   Anders als EventType oder matter_kinds lebt dieses Vokabular in der
#   DATENBANK, nicht im Code (mc 2026-07-12): die Ermittlung steht am Anfang,
#   und welche Kriterien und Abstufungen sich bewaehren, weiss heute niemand.
#   Ein neues Kriterium ist deshalb ein auditierter SCHREIBVORGANG — kein
#   Schema-Eingriff an produktiven Ermittlungsdaten.
#
# APPEND-ONLY:
#   Nichts wird geloescht. Ein ueberholter Skalenpunkt bekommt 'deprecated_at'
#   und verschwindet aus den AUSWAHLLISTEN — bleibt aber lesbar, weil
#   bestehende Bewertungen auf ihn zeigen. Ein hartes DELETE wuerde
#   Ermittlungsergebnisse ins Leere zeigen lassen.
#
# KATALOGVERSION:
#   JEDE Katalogaenderung erhoeht assessment_catalog_version.version um 1. Jede
#   Bewertung merkt sich, gegen WELCHE Version sie erfasst wurde. Damit ist
#   spaeter nachvollziehbar, dass eine Zahl von 2027 gegen einen anderen
#   Katalog erhoben wurde als eine von 2026 — statt dass beide stillschweigend
#   in denselben Topf wandern.
#
# Version: v0.7.387 · Build: 387 · 2026-07-12
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter

logger = logging.getLogger(__name__)


class CatalogError(Exception):
    """Fachlicher Fehler im Bewertungs-Katalog."""


class AssessmentCatalogRepo:
    """Auditierte Lese-/Schreibmethoden auf dem Bewertungs-Katalog."""

    def __init__(self, con: sqlite3.Connection,
                 writer: Optional[CoordinatorWriter] = None) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        # writer=None -> rein lesende Nutzung (mode=ro). Jeder Schreibweg
        # prueft das und scheitert LAUT, statt still zu wirken.
        self._writer = writer

    def _require_writer(self) -> CoordinatorWriter:
        if self._writer is None:
            raise CatalogError(
                "Schreibzugriff ohne CoordinatorWriter — kein unauditierter "
                "Schreibpfad zulaessig.")
        return self._writer

    # ------------------------------------------------------------------- Lesen
    def version(self) -> int:
        row = self._con.execute(
            "SELECT version FROM assessment_catalog_version WHERE id = 1"
        ).fetchone()
        if row is None:
            raise CatalogError(
                "Katalogversion fehlt — Migration M011 nicht angewandt.")
        return int(row[0])

    def scales(self, *, include_deprecated: bool = False
               ) -> List[Dict[str, Any]]:
        sql = ("SELECT code, label, beschreibung, deprecated_at "
               "FROM assessment_scale")
        if not include_deprecated:
            sql += " WHERE deprecated_at IS NULL"
        sql += " ORDER BY code"
        return [dict(r) for r in self._con.execute(sql).fetchall()]

    def items(self, scale_code: str, *, include_deprecated: bool = False
              ) -> List[Dict[str, Any]]:
        sql = ("SELECT id, scale_code, code, label, ordinal, sort, "
               "deprecated_at FROM assessment_scale_item WHERE scale_code = ?")
        if not include_deprecated:
            sql += " AND deprecated_at IS NULL"
        sql += " ORDER BY sort, ordinal, id"
        return [dict(r) for r in
                self._con.execute(sql, (scale_code,)).fetchall()]

    def criteria(self, *, include_deprecated: bool = False
                 ) -> List[Dict[str, Any]]:
        sql = ("SELECT code, label, quality_scale, sort, deprecated_at "
               "FROM assessment_criterion")
        if not include_deprecated:
            sql += " WHERE deprecated_at IS NULL"
        sql += " ORDER BY sort, code"
        return [dict(r) for r in self._con.execute(sql).fetchall()]

    def item(self, scale_code: str, item_code: str) -> Dict[str, Any]:
        """
        Einen Skalenpunkt lesen — auch einen DEPRECATED. Beim LESEN alter
        Bewertungen muss er auffindbar bleiben; nur die AUSWAHLLISTEN blenden
        ihn aus.
        """
        row = self._con.execute(
            "SELECT * FROM assessment_scale_item "
            "WHERE scale_code = ? AND code = ?",
            (scale_code, item_code)).fetchone()
        if row is None:
            raise CatalogError(
                "Skalenpunkt '%s' existiert in Skala '%s' nicht."
                % (item_code, scale_code))
        return dict(row)

    def criterion(self, code: str) -> Dict[str, Any]:
        row = self._con.execute(
            "SELECT * FROM assessment_criterion WHERE code = ?",
            (code,)).fetchone()
        if row is None:
            raise CatalogError("Unbekanntes Kriterium '%s'." % code)
        return dict(row)

    def full(self, *, include_deprecated: bool = False) -> Dict[str, Any]:
        """
        Der GANZE Katalog fuer Oberflaeche und CLI: Kriterien mit ihrer
        Konfidenz- und (falls vorhanden) Qualitaetsskala, jeweils samt
        Skalenpunkten. Genau das braucht die Erfassungsmaske fuer ihre
        Auswahlfelder.
        """
        conf = self.items("confidence", include_deprecated=include_deprecated)
        scale_map = {s["code"]: s for s in
                     self.scales(include_deprecated=include_deprecated)}
        out_crit = []
        for c in self.criteria(include_deprecated=include_deprecated):
            q = c["quality_scale"]
            out_crit.append({
                "code": c["code"],
                "label": c["label"],
                "quality_scale": q,
                "quality_label": (scale_map.get(q, {}) or {}).get("label"),
                # Die Semantik-Warnung der Skala wird MITGELIEFERT — wer die
                # Zahl sieht, soll wissen, was sie misst.
                "quality_beschreibung": (scale_map.get(q, {}) or {})
                    .get("beschreibung"),
                "quality_items": (self.items(
                    q, include_deprecated=include_deprecated) if q else []),
                "sort": c["sort"],
            })
        return {
            "catalog_version": self.version(),
            "confidence_items": conf,
            "extreme": ["schwerste", "beste"],
            "criteria": out_crit,
        }

    # --------------------------------------------------------------- Schreiben
    def _bump(self, con: sqlite3.Connection) -> int:
        con.execute(
            "UPDATE assessment_catalog_version SET version = version + 1 "
            "WHERE id = 1")
        return int(con.execute(
            "SELECT version FROM assessment_catalog_version WHERE id = 1"
        ).fetchone()[0])

    def add_scale(self, code: str, label: str, *, beschreibung: str = "",
                  actor_id: Optional[int] = None) -> int:
        writer = self._require_writer()
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            if con.execute("SELECT 1 FROM assessment_scale WHERE code=?",
                           (code,)).fetchone():
                raise CatalogError("Skala '%s' existiert bereits." % code)
            con.execute(
                "INSERT INTO assessment_scale "
                "(code, label, beschreibung, audit_seq, created_by, created_at) "
                "VALUES (?, ?, ?, 0, ?, ?)",
                (code, label, beschreibung, actor_id, now))
            v = self._bump(con)
            return {"scale": code, "label": label, "catalog_version": v}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE assessment_scale SET audit_seq=? WHERE code=?",
                        (seq, code))

        return writer.audited_write(
            do_write=_w, event_type=EventType.CATALOG_SCALE_ADDED,
            actor_id=actor_id, target_type="assessment_scale",
            target_id=code, after_audit=_after)

    def add_item(self, scale_code: str, code: str, label: str, *,
                 ordinal: int, sort: int = 0,
                 actor_id: Optional[int] = None) -> int:
        writer = self._require_writer()
        now = int(time.time())
        state: Dict[str, Any] = {}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            if not con.execute("SELECT 1 FROM assessment_scale WHERE code=?",
                               (scale_code,)).fetchone():
                raise CatalogError("Unbekannte Skala '%s'." % scale_code)
            if con.execute(
                    "SELECT 1 FROM assessment_scale_item "
                    "WHERE scale_code=? AND code=?",
                    (scale_code, code)).fetchone():
                raise CatalogError(
                    "Skalenpunkt '%s' existiert in '%s' bereits (append-only: "
                    "vorhandene Punkte werden nicht ueberschrieben)."
                    % (code, scale_code))
            cur = con.execute(
                "INSERT INTO assessment_scale_item "
                "(scale_code, code, label, ordinal, sort, audit_seq, "
                " created_by, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                (scale_code, code, label, int(ordinal), int(sort),
                 actor_id, now))
            state["id"] = int(cur.lastrowid)
            v = self._bump(con)
            return {"scale": scale_code, "item": code,
                    "ordinal": int(ordinal), "catalog_version": v}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE assessment_scale_item SET audit_seq=? "
                        "WHERE id=?", (seq, state["id"]))

        return writer.audited_write(
            do_write=_w, event_type=EventType.CATALOG_ITEM_ADDED,
            actor_id=actor_id, target_type="assessment_scale_item",
            target_id="%s/%s" % (scale_code, code), after_audit=_after)

    def add_criterion(self, code: str, label: str, *,
                      quality_scale: Optional[str] = None, sort: int = 0,
                      actor_id: Optional[int] = None) -> int:
        writer = self._require_writer()
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            if con.execute("SELECT 1 FROM assessment_criterion WHERE code=?",
                           (code,)).fetchone():
                raise CatalogError("Kriterium '%s' existiert bereits." % code)
            if quality_scale and not con.execute(
                    "SELECT 1 FROM assessment_scale WHERE code=?",
                    (quality_scale,)).fetchone():
                raise CatalogError(
                    "Unbekannte Qualitaetsskala '%s'." % quality_scale)
            con.execute(
                "INSERT INTO assessment_criterion "
                "(code, label, quality_scale, sort, audit_seq, created_by, "
                " created_at) VALUES (?, ?, ?, ?, 0, ?, ?)",
                (code, label, quality_scale, int(sort), actor_id, now))
            v = self._bump(con)
            return {"criterion": code, "quality_scale": quality_scale,
                    "catalog_version": v}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE assessment_criterion SET audit_seq=? "
                        "WHERE code=?", (seq, code))

        return writer.audited_write(
            do_write=_w, event_type=EventType.CATALOG_CRITERION_ADDED,
            actor_id=actor_id, target_type="assessment_criterion",
            target_id=code, after_audit=_after)

    def set_quality_scale(self, criterion_code: str, scale_code: str, *,
                          actor_id: Optional[int] = None) -> int:
        """
        Einem Kriterium NACHTRAEGLICH eine Qualitaetsskala geben (der
        ausdruecklich vorgesehene Weg fuer die sieben CP/JP-Kriterien, sobald
        die Chef-Ermittlerin die Abstufungen festgelegt hat — OHNE Migration).

        Eine BESTEHENDE Skala wird NICHT ueberschrieben: alte Bewertungen
        wuerden sonst auf Punkte einer fremden Skala zeigen. Ein Wechsel
        verlangt ein NEUES Kriterium.
        """
        writer = self._require_writer()

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = con.execute(
                "SELECT quality_scale FROM assessment_criterion WHERE code=?",
                (criterion_code,)).fetchone()
            if row is None:
                raise CatalogError(
                    "Unbekanntes Kriterium '%s'." % criterion_code)
            if row[0] is not None:
                raise CatalogError(
                    "Kriterium '%s' hat bereits die Skala '%s'. Ein WECHSEL "
                    "wuerde bestehende Bewertungen auf Punkte einer fremden "
                    "Skala zeigen lassen — dafuer ist ein NEUES Kriterium "
                    "anzulegen." % (criterion_code, row[0]))
            if not con.execute("SELECT 1 FROM assessment_scale WHERE code=?",
                               (scale_code,)).fetchone():
                raise CatalogError("Unbekannte Skala '%s'." % scale_code)
            con.execute(
                "UPDATE assessment_criterion SET quality_scale=? WHERE code=?",
                (scale_code, criterion_code))
            v = self._bump(con)
            return {"criterion": criterion_code, "quality_scale": scale_code,
                    "catalog_version": v}

        return writer.audited_write(
            do_write=_w, event_type=EventType.CATALOG_CRITERION_ADDED,
            actor_id=actor_id, target_type="assessment_criterion",
            target_id=criterion_code)

    def deprecate(self, tabelle: str, key: str, *,
                  scale_code: Optional[str] = None,
                  actor_id: Optional[int] = None) -> int:
        """
        Einen Katalogeintrag AUSSER DIENST stellen (kein DELETE!). Er
        verschwindet aus den Auswahllisten, bleibt aber lesbar — bestehende
        Bewertungen zeigen weiter auf ihn.
        """
        writer = self._require_writer()
        now = int(time.time())
        if tabelle not in ("scale", "item", "criterion"):
            raise CatalogError("Unbekannte Katalog-Tabelle '%s'." % tabelle)

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            if tabelle == "scale":
                cur = con.execute(
                    "UPDATE assessment_scale SET deprecated_at=? "
                    "WHERE code=? AND deprecated_at IS NULL", (now, key))
            elif tabelle == "criterion":
                cur = con.execute(
                    "UPDATE assessment_criterion SET deprecated_at=? "
                    "WHERE code=? AND deprecated_at IS NULL", (now, key))
            else:
                if not scale_code:
                    raise CatalogError(
                        "Fuer einen Skalenpunkt ist scale_code noetig.")
                cur = con.execute(
                    "UPDATE assessment_scale_item SET deprecated_at=? "
                    "WHERE scale_code=? AND code=? AND deprecated_at IS NULL",
                    (now, scale_code, key))
            if cur.rowcount == 0:
                raise CatalogError(
                    "Nichts ausser Dienst gestellt: '%s' existiert nicht oder "
                    "ist es bereits." % key)
            v = self._bump(con)
            return {"tabelle": tabelle, "key": key, "scale": scale_code,
                    "catalog_version": v}

        return writer.audited_write(
            do_write=_w, event_type=EventType.CATALOG_DEPRECATED,
            actor_id=actor_id, target_type="assessment_" + tabelle,
            target_id=key)
