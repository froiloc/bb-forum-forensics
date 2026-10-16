# =============================================================================
# management/db_vorfall/db_vorfall_repo.py
# IT-Forensisches Ermittlungswerkzeug — Register "Datenbank-Vorfaelle" (Build 777)
# =============================================================================
# Zweck:
#   Lesen und Schreiben der Tabelle db_vorfall (M041). Lesen ohne Schreiber;
#   Schreiben ausschliesslich ueber CoordinatorWriter, damit jeder Eintrag und
#   jeder Pruefvermerk seinen audit_log-Beleg in DERSELBEN Transaktion hat
#   (Muster BildschleierRepo, Build 771).
#
# ── ERFASSEN IST IDEMPOTENT ─────────────────────────────────────────────────
#
#   Kennt das Register die vorfall_uid schon, wird NICHTS geschrieben und der
#   vorhandene Beleg zurueckgegeben — vorausgesetzt, der Inhalt stimmt
#   ueberein. Weicht er ab, ist das ein Widerspruch (zwei verschiedene Vorfaelle
#   mit einer Kennung) und wird mit DbVorfallFehler gemeldet; ueberschrieben
#   wird nie. Anlass: der Nachtrag aus dem Puffer (db_vorfall_puffer.py) kann
#   nach einem Eintrag scheitern, bevor die Pufferdatei geloescht ist.
#
# ── PRUEFEN: EINSEITIG, MIT NOTIZ, MIT RECHT ────────────────────────────────
#
#   als_geprueft() verlangt
#     * eine handelnde Person (actor_id),
#     * das Recht 'wartung.durchfuehren' — geprueft HIER und nicht nur im
#       Endpunkt: der Schreibweg ist die Stelle, an der eine Regel halten
#       muss, gleich wer ihn aufruft (Muster BildschleierRepo.setzen),
#     * eine Notiz, die sagt, WAS geprueft wurde. Ein Haken ohne Aussage ist
#       spaeter nicht zu verteidigen (Muster Promotion: Pflichtgrund).
#   Ein schon geprueft markierter Vorfall wird nicht erneut markiert; ein
#   Zuruecknehmen gibt es nicht.
#
# ── NUR sqlite3.Error WIRD BEIM LESEN ABGEFANGEN ────────────────────────────
#
#   Lehre aus Build 769. Ein unlesbarer Befund (kein gueltiges JSON) ist
#   dagegen kein Fehler der Sicht, sondern ein Befund: die Zeile wird mit dem
#   Rohtext und einer Fehlerangabe ausgeliefert, nicht weggelassen.
#
# Version: v0.8.777 · Build: 777 · 2026-10-14
# =============================================================================

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.db_vorfall.db_vorfall_fehler import DbVorfallFehler
from management.db_vorfall.db_vorfall_meldung import (
    ARTEN, ERGEBNISSE, DbVorfallMeldung,
)
from management.gateway.coordinator_writer import CoordinatorWriter
from management.rbac.rbac_resolver import RbacResolver

logger = logging.getLogger(__name__)

#: Das Recht, einen Vorfall als geprueft zu markieren (Seed M014).
RECHT_PRUEFEN = "wartung.durchfuehren"

#: Hoechstlaenge der Pruefnotiz (Zeichen). Laenger ist kein Vermerk mehr,
#: sondern ein Bericht — der gehoert in eine Datei, auf die die Notiz verweist.
NOTIZ_MAX = 4000

STATUS_OFFEN = "offen"
STATUS_GEPRUEFT = "geprueft"
STATUSWERTE = (STATUS_OFFEN, STATUS_GEPRUEFT)

_SPALTEN_LISTE = (
    "id, vorfall_uid, erkannt_at, erfasst_at, nachgetragen, art, ergebnis, "
    "subject_id, datei, host, person_id, befund_json, status, audit_seq, "
    "geprueft_von, geprueft_at, pruef_notiz, pruef_audit_seq")


class DbVorfallRepo:
    """Register lesen und auditiert schreiben."""

    def __init__(self, con: sqlite3.Connection,
                 writer: Optional[CoordinatorWriter] = None) -> None:
        self._con = con
        self._writer = writer

    # ------------------------------------------------------------- Lesen ---
    def zaehler(self) -> Dict[str, int]:
        """{'offen': n, 'geprueft': m} — beide Schluessel immer vorhanden."""
        z = {s: 0 for s in STATUSWERTE}
        for status, anzahl in self._con.execute(
                "SELECT status, COUNT(*) FROM db_vorfall GROUP BY status"):
            z[status] = int(anzahl)
        return z

    def liste(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Alle Vorfaelle, neueste Erkennung zuerst; optional nach Status."""
        if status is not None and status not in STATUSWERTE:
            raise DbVorfallFehler(
                "Unbekannter Status %r (zulaessig: %s)."
                % (status, ", ".join(STATUSWERTE)))
        sql = "SELECT %s FROM db_vorfall" % _SPALTEN_LISTE
        args: tuple = ()
        if status is not None:
            sql += " WHERE status = ?"
            args = (status,)
        sql += " ORDER BY erkannt_at DESC, id DESC"
        cur = self._con.execute(sql, args)
        namen = [d[0] for d in cur.description]
        return [self._zeile(dict(zip(namen, r))) for r in cur.fetchall()]

    def holen(self, vorfall_id: int) -> Optional[Dict[str, Any]]:
        cur = self._con.execute(
            "SELECT %s FROM db_vorfall WHERE id = ?" % _SPALTEN_LISTE,
            (int(vorfall_id),))
        r = cur.fetchone()
        if r is None:
            return None
        return self._zeile(dict(zip([d[0] for d in cur.description], r)))

    @staticmethod
    def _zeile(z: Dict[str, Any]) -> Dict[str, Any]:
        """Zeile fuer Sicht und API: Befund geparst, Klartexte dazu."""
        roh = z.pop("befund_json")
        try:
            z["befund"] = json.loads(roh)
            z["befund_fehler"] = None
        except (TypeError, ValueError) as exc:
            # Kein Weglassen (Grundregel 1): Rohtext und Fehler ausliefern.
            z["befund"] = None
            z["befund_roh"] = roh
            z["befund_fehler"] = "Befund ist kein gueltiges JSON: %s" % exc
        z["nachgetragen"] = bool(z["nachgetragen"])
        z["art_klartext"] = ARTEN.get(z["art"], z["art"])
        z["ergebnis_klartext"] = ERGEBNISSE.get(z["ergebnis"], z["ergebnis"])
        return z

    # --------------------------------------------------------- Erfassen ---
    def erfassen(self, meldung: DbVorfallMeldung, *,
                 nachgetragen: bool = False,
                 jetzt: Optional[int] = None) -> int:
        """
        Traegt den Vorfall ein und schreibt EINEN Beleg (DB_VORFALL_ERFASST).
        Gibt die seq des Belegs zurueck — bei einem bereits bekannten,
        inhaltsgleichen Vorfall die seq des vorhandenen Belegs (nichts wird
        geschrieben).
        """
        if self._writer is None:
            raise DbVorfallFehler(
                "Kein Schreibweg: DbVorfallRepo wurde ohne CoordinatorWriter "
                "erzeugt.")
        meldung.pruefen()
        befund_json = meldung.befund_json()
        befund_sha = hashlib.sha256(befund_json.encode("utf-8")).hexdigest()

        seq_vorhanden = self._vorhanden(meldung, befund_json)
        if seq_vorhanden is not None:
            return seq_vorhanden

        now = int(time.time()) if jetzt is None else int(jetzt)
        uid = meldung.vorfall_uid

        def _w(con: sqlite3.Connection):
            # audit_seq zunaechst 0, im after_audit-Hook auf die echte seq
            # gesetzt — dieselbe Transaktion, atomar (Muster BildschleierRepo).
            con.execute(
                "INSERT INTO db_vorfall (vorfall_uid, erkannt_at, erfasst_at, "
                "nachgetragen, art, ergebnis, subject_id, datei, host, "
                "person_id, befund_json, status, audit_seq) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0)",
                (uid, meldung.erkannt_at, now, 1 if nachgetragen else 0,
                 meldung.art, meldung.ergebnis, meldung.subject_id,
                 meldung.datei, meldung.host, meldung.person_id,
                 befund_json, STATUS_OFFEN))
            return {
                "vorfall_uid": uid, "art": meldung.art,
                "ergebnis": meldung.ergebnis, "datei": meldung.datei,
                "subject_id": meldung.subject_id,
                "erkannt_at": meldung.erkannt_at,
                "nachgetragen": bool(nachgetragen),
                "befund_sha256": befund_sha,
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE db_vorfall SET audit_seq = ? "
                        "WHERE vorfall_uid = ?", (seq, uid))

        try:
            seq = self._writer.audited_write(
                do_write=_w, event_type=EventType.DB_VORFALL_ERFASST,
                actor_id=meldung.person_id, target_type="db_vorfall",
                target_id=uid, after_audit=_after)
        except sqlite3.IntegrityError:
            # Zwischen Nachsehen und Schreiben hat ein anderer Prozess
            # DENSELBEN Vorfall eingetragen (UNIQUE vorfall_uid). Die
            # Transaktion ist zurueckgerollt; es gilt der vorhandene Eintrag —
            # sofern er inhaltsgleich ist. Ist er es nicht, wirft _vorhanden.
            seq_vorhanden = self._vorhanden(meldung, befund_json)
            if seq_vorhanden is None:
                raise
            return seq_vorhanden
        logger.warning("DB-Vorfall eingetragen: %s %s %s (Fall %s, Beleg "
                       "seq=%d%s)", uid, meldung.art, meldung.ergebnis,
                       meldung.subject_id, seq,
                       ", nachgetragen" if nachgetragen else "")
        return seq

    def _vorhanden(self, meldung: DbVorfallMeldung,
                   befund_json: str) -> Optional[int]:
        """seq des vorhandenen, inhaltsgleichen Eintrags — oder None.
        Wirft DbVorfallFehler bei gleicher Kennung und anderem Inhalt."""
        r = self._con.execute(
            "SELECT audit_seq, art, ergebnis, datei, erkannt_at, befund_json, "
            "subject_id FROM db_vorfall WHERE vorfall_uid = ?",
            (meldung.vorfall_uid,)).fetchone()
        if r is None:
            return None
        ist = tuple(r[i] for i in range(1, 7))
        soll = (meldung.art, meldung.ergebnis, meldung.datei,
                meldung.erkannt_at, befund_json, meldung.subject_id)
        if ist != soll:
            raise DbVorfallFehler(
                "Vorfall %s ist bereits mit ANDEREM Inhalt eingetragen. Es "
                "wird nichts ueberschrieben." % meldung.vorfall_uid)
        logger.info("DB-Vorfall %s ist bereits eingetragen (Beleg seq=%s) — "
                    "nichts geschrieben.", meldung.vorfall_uid, r[0])
        return int(r[0])

    # ----------------------------------------------------------- Pruefen ---
    def als_geprueft(self, vorfall_id: int, *, actor_id: Optional[int],
                     notiz: str, jetzt: Optional[int] = None) -> int:
        """
        Markiert den Vorfall als geprueft und schreibt EINEN Beleg
        (DB_VORFALL_GEPRUEFT). Gibt die seq zurueck.
        """
        if self._writer is None:
            raise DbVorfallFehler(
                "Kein Schreibweg: DbVorfallRepo wurde ohne CoordinatorWriter "
                "erzeugt.")
        if actor_id is None:
            raise DbVorfallFehler(
                "Ein Pruefvermerk ohne handelnde Person ist kein Beleg "
                "(actor_id fehlt).")
        notiz = (notiz or "").strip() if isinstance(notiz, str) else ""
        if not notiz:
            raise DbVorfallFehler(
                "Die Notiz ist Pflicht: sie sagt, was geprueft wurde.")
        if len(notiz) > NOTIZ_MAX:
            raise DbVorfallFehler(
                "Die Notiz ist laenger als %d Zeichen (%d). Bitte kuerzen und "
                "auf eine Datei verweisen." % (NOTIZ_MAX, len(notiz)))
        if not RbacResolver(self._con).resolve(int(actor_id)).can(RECHT_PRUEFEN):
            raise DbVorfallFehler(
                "Person %d hat das Recht '%s' nicht." % (int(actor_id),
                                                         RECHT_PRUEFEN))
        zeile = self._con.execute(
            "SELECT vorfall_uid, status FROM db_vorfall WHERE id = ?",
            (int(vorfall_id),)).fetchone()
        if zeile is None:
            raise DbVorfallFehler("Vorfall %d ist nicht bekannt." % int(vorfall_id))
        uid, status = zeile[0], zeile[1]
        if status != STATUS_OFFEN:
            raise DbVorfallFehler(
                "Vorfall %d ist bereits als geprueft markiert." % int(vorfall_id))

        now = int(time.time()) if jetzt is None else int(jetzt)
        vid, aid = int(vorfall_id), int(actor_id)

        def _w(con: sqlite3.Connection):
            # Der Statuswechsel und der Pruefvermerk muessen gemeinsam
            # gesetzt werden (CHECK in M041); pruef_audit_seq zunaechst 0.
            cur = con.execute(
                "UPDATE db_vorfall SET status = ?, geprueft_von = ?, "
                "geprueft_at = ?, pruef_notiz = ?, pruef_audit_seq = 0 "
                "WHERE id = ? AND status = ?",
                (STATUS_GEPRUEFT, aid, now, notiz, vid, STATUS_OFFEN))
            if cur.rowcount != 1:
                # Zwischen Lesen und Schreiben hat jemand anderes geprueft.
                raise DbVorfallFehler(
                    "Vorfall %d wurde inzwischen bereits geprueft." % vid)
            return {"vorfall_uid": uid, "id": vid, "notiz": notiz}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE db_vorfall SET pruef_audit_seq = ? "
                        "WHERE id = ?", (seq, vid))

        seq = self._writer.audited_write(
            do_write=_w, event_type=EventType.DB_VORFALL_GEPRUEFT,
            actor_id=aid, target_type="db_vorfall", target_id=uid,
            after_audit=_after)
        logger.info("DB-Vorfall %s als geprueft markiert von Person %d "
                    "(Beleg seq=%d).", uid, aid, seq)
        return seq
