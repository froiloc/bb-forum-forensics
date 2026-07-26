# =============================================================================
# management/search/release_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B561)
# =============================================================================
# Zweck:
#   FulltextReleaseRepo — der AUDITIERTE SCHREIBPFAD zur Inhaltsfreigabe der
#   falluebergreifenden Volltextsuche und die Auskunft darueber, WER den
#   Trefferinhalt WELCHES Falls sehen darf (Stufe 2 des Modells B).
#
#   Grundregel 10: eine Klasse, eine Datei.
#
# ── DIE ENTSCHEIDENDE METHODE IST darf_inhalt_sehen() ──────────────────────
#
#   Sie ist die Stelle, an der Modell B wirksam wird. Sie liefert nicht nur
#   True/False, sondern einen BEFUND mit GRUND:
#
#     'eigener_fall'   — der Fall ist der Person zugewiesen (cases.assigned_to).
#                        Inhalt sofort, ohne Freigabe (Entscheidungen mc E-1).
#     'freigabe'       — eine gueltige fulltext_release liegt vor.
#     'gesperrt'       — weder noch. Die Sicht bietet dann die
#                        begruendungspflichtige Anfrage an.
#     'unbekannt_wer'  — es gibt keine handelnde Person. NICHT dasselbe wie
#                        'gesperrt', s. u.
#
#   WARUM EIN GRUND UND NICHT NUR EIN JA/NEIN: Der Endpunkt (Build 562)
#   antwortet bei einer Sperre mit 403 UND BEGRUENDUNG (Muster
#   forensic_api/results_endpoint.py). Eine Ablehnung ohne Grund waere fuer
#   die Ermittlerin nicht von einem Fehler zu unterscheiden — und sie wuesste
#   nicht, dass ihr der Weg ueber die Freigabe offensteht. Ausserdem geht der
#   Grund in den Beleg ein: 'gesehen, weil eigener Fall' und 'gesehen, weil
#   freigegeben am ... durch ...' sind verschiedene Sachverhalte.
#
#   'unbekannt_wer' IST EIN EIGENER BEFUND. Ohne Handelnden wird NICHTS
#   freigegeben — dieselbe Linie wie im auditierten Schreibpfad des
#   Forensik-Servers ("ohne Handelnden wird NICHTS geschrieben"). Ihn mit
#   'gesperrt' zusammenzuwerfen hiesse, einen Konfigurationsfehler wie eine
#   Zugriffsentscheidung aussehen zu lassen.
#
# ── WIDERRUF STATT LOESCHUNG ───────────────────────────────────────────────
#
#   Eine Freigabe wird NIE geloescht, sondern mit Pflichtgrund widerrufen; die
#   Zeile bleibt als Beleg stehen. Die Erkenntnis "diese Person durfte einmal
#   in diesen Fall sehen" ist die aufsichtsrelevante — sie zu loeschen waere
#   ein stiller Beweisverlust (Grundregel 1). Danach ist eine erneute Freigabe
#   moeglich; der partielle UNIQUE-Index (M040) laesst genau das zu.
#
# ── SENSIBILITAET ──────────────────────────────────────────────────────────
#
#   'begruendung', 'zweck_freitext' und 'revoke_reason' sind Freitexte und
#   stehen NIEMALS im audit_log-Payload (Muster M018/M022/M027) — dort nur
#   FAKTEN (release_id, subject_id, person_id, zweck_code) und TEXTLAENGEN.
#   Der ZWECKCODE steht ausdruecklich MIT im Payload: er ist kein Freitext,
#   und er ist die auswertbare Groesse, wegen der E-3 ueberhaupt eine
#   Auswahlliste verlangt hat.
#
# Version: v0.8.561 · Build: 561 · 2026-07-26
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.search.zweck_vokabular import ZweckFehler, klartext, pruefe

logger = logging.getLogger(__name__)

#: Befunde von darf_inhalt_sehen(). Reihenfolge = Vorrang bei der Pruefung.
GRUND_EIGENER_FALL = "eigener_fall"
GRUND_FREIGABE = "freigabe"
GRUND_GESPERRT = "gesperrt"
GRUND_UNBEKANNT_WER = "unbekannt_wer"

GRUND_KLARTEXT: Dict[str, str] = {
    GRUND_EIGENER_FALL: "Der Fall ist Ihnen zugewiesen — Inhalt frei.",
    GRUND_FREIGABE: "Eine gueltige Inhaltsfreigabe liegt vor.",
    GRUND_GESPERRT: ("Inhalt gesperrt — der Fall ist Ihnen nicht zugewiesen "
                     "und es liegt keine gueltige Freigabe vor. Eine "
                     "begruendungspflichtige Anfrage an die Chef-Ermittlerin "
                     "ist moeglich."),
    GRUND_UNBEKANNT_WER: ("Es ist keine handelnde Person bekannt. Ohne "
                          "Handelnden wird nichts freigegeben."),
}


class FulltextReleaseFehler(RuntimeError):
    """
    Die Freigabe konnte nicht erteilt oder widerrufen werden.

    EIGENE Ausnahme, damit der Endpunkt (Build 562) den Fachfehler von einem
    Programmfehler unterscheiden und mit Klartext beantworten kann.
    """


class FulltextReleaseRepo:
    """Lesen und auditiertes Schreiben der Inhaltsfreigaben (fulltext_release)."""

    def __init__(self, con: sqlite3.Connection,
                 writer: Optional[Any] = None) -> None:
        self._con = con
        self._writer = writer

    def _require_writer(self):
        """
        Ohne Gateway wird NICHT geschrieben.

        CoordinatorWriter.audited_write bindet Fachwrite und Beleg in EINE
        Transaktion. Ein Schreibweg daran vorbei erzeugte eine Freigabe ohne
        Beleg — genau den Zustand, den dieses Werkzeug ausschliessen soll.
        """
        if self._writer is None:
            raise FulltextReleaseFehler(
                "Kein CoordinatorWriter gesetzt — eine Freigabe ohne Beleg "
                "wird nicht geschrieben.")
        return self._writer

    # --------------------------------------------------------------- Helfer
    @staticmethod
    def _tlen(text: Optional[str]) -> int:
        """Textlaenge fuer den Audit-Payload (statt des Textes selbst)."""
        return len(text or "")

    @staticmethod
    def table_exists(con: sqlite3.Connection) -> bool:
        """
        True, wenn M040 angewandt ist.

        Der Aufrufer MUSS das unterscheiden koennen: 'keine Freigaben' und
        'die Tabelle gibt es noch nicht' sehen sonst gleich aus, und das
        zweite ist ein Betriebsbefund (Migration fehlt), kein Sachverhalt.
        """
        return con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='fulltext_release'").fetchone() is not None

    def _row(self, con: sqlite3.Connection, release_id: int):
        cur = con.execute("SELECT * FROM fulltext_release WHERE id = ?",
                          (int(release_id),))
        cur.row_factory = sqlite3.Row
        return cur.fetchone()

    def _aktive(self, con: sqlite3.Connection, subject_id: int,
                person_id: int):
        cur = con.execute(
            "SELECT * FROM fulltext_release "
            "WHERE subject_id = ? AND person_id = ? AND is_active = 1",
            (int(subject_id), int(person_id)))
        cur.row_factory = sqlite3.Row
        return cur.fetchone()

    @staticmethod
    def _zu_dict(row) -> Dict[str, Any]:
        d = {k: row[k] for k in row.keys()}
        d["is_active"] = bool(d.get("is_active"))
        d["zweck_klartext"] = klartext(d.get("zweck_code"),
                                       d.get("zweck_freitext"))
        return d

    # ----------------------------------------------------------- Zweckkatalog
    def zweck_katalog(self) -> List[Dict[str, Any]]:
        """
        Der Zweckkatalog AUS DER DATENBANK (nicht aus dem Code).

        Absichtlich aus der Datenbank: die Sicht soll das anbieten, was der
        Fremdschluessel auch akzeptiert. Laufen Code und Seed auseinander,
        soll das an der Auswahlliste auffallen und nicht erst beim Schreiben.
        Der Test FR02 haelt beide gegeneinander.
        """
        if not self.table_exists(self._con):
            return []
        cur = self._con.execute(
            "SELECT code, label, beschreibung, freitext_pflicht "
            "FROM fulltext_zweck ORDER BY rowid")
        return [{"code": r[0], "label": r[1], "beschreibung": r[2],
                 "freitext_pflicht": bool(r[3])} for r in cur.fetchall()]

    # -------------------------------------------------------------- Auskunft
    def darf_inhalt_sehen(self, *, subject_id: Any,
                          person_id: Optional[Any]) -> Dict[str, Any]:
        """
        Die Stufe-2-Entscheidung: darf diese Person den Trefferinhalt sehen?

        Rueckgabe: {'erlaubt': bool, 'grund': <Code>, 'klartext': str,
                    'release_id': int|None, 'freigegeben_von': int|None,
                    'freigegeben_at': int|None}

        Die Pruefreihenfolge ist EIGENER FALL vor FREIGABE. Das ist keine
        Optimierung, sondern eine Aussage: wer den Fall bearbeitet, sieht
        seinen Inhalt aus eigenem Recht, nicht aus geliehenem. Waere es
        umgekehrt, traege der Beleg bei einer zufaellig vorhandenen Freigabe
        einen falschen Grund.
        """
        if person_id is None:
            return {"erlaubt": False, "grund": GRUND_UNBEKANNT_WER,
                    "klartext": GRUND_KLARTEXT[GRUND_UNBEKANNT_WER],
                    "release_id": None, "freigegeben_von": None,
                    "freigegeben_at": None}
        sid, pid = int(subject_id), int(person_id)

        eigen = self._con.execute(
            "SELECT 1 FROM cases WHERE subject_id = ? AND assigned_to = ?",
            (sid, pid)).fetchone()
        if eigen is not None:
            return {"erlaubt": True, "grund": GRUND_EIGENER_FALL,
                    "klartext": GRUND_KLARTEXT[GRUND_EIGENER_FALL],
                    "release_id": None, "freigegeben_von": None,
                    "freigegeben_at": None}

        if self.table_exists(self._con):
            row = self._aktive(self._con, sid, pid)
            if row is not None:
                return {"erlaubt": True, "grund": GRUND_FREIGABE,
                        "klartext": GRUND_KLARTEXT[GRUND_FREIGABE],
                        "release_id": int(row["id"]),
                        "freigegeben_von": row["granted_by"],
                        "freigegeben_at": row["granted_at"]}

        return {"erlaubt": False, "grund": GRUND_GESPERRT,
                "klartext": GRUND_KLARTEXT[GRUND_GESPERRT],
                "release_id": None, "freigegeben_von": None,
                "freigegeben_at": None}

    def fuer_person(self, person_id: Any, *,
                    nur_aktive: bool = True) -> List[Dict[str, Any]]:
        """'Was darf diese Person sehen?' — die Sicht der Ermittlerin."""
        if not self.table_exists(self._con):
            return []
        sql = ("SELECT * FROM fulltext_release WHERE person_id = ?"
               + (" AND is_active = 1" if nur_aktive else "")
               + " ORDER BY granted_at DESC, id DESC")
        cur = self._con.execute(sql, (int(person_id),))
        cur.row_factory = sqlite3.Row
        return [self._zu_dict(r) for r in cur.fetchall()]

    def fuer_fall(self, subject_id: Any, *,
                  nur_aktive: bool = True) -> List[Dict[str, Any]]:
        """'Wer darf in diesen Fall sehen?' — die Aufsichtsrichtung."""
        if not self.table_exists(self._con):
            return []
        sql = ("SELECT * FROM fulltext_release WHERE subject_id = ?"
               + (" AND is_active = 1" if nur_aktive else "")
               + " ORDER BY granted_at DESC, id DESC")
        cur = self._con.execute(sql, (int(subject_id),))
        cur.row_factory = sqlite3.Row
        return [self._zu_dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------ Schreibpfad
    def erteile(self, *, subject_id: Any, person_id: Any, zweck_code: str,
                zweck_freitext: Optional[str] = None, begruendung: str,
                actor_id: Optional[int] = None,
                meta: Optional[Any] = None) -> Dict[str, Any]:
        """
        Inhaltsfreigabe erteilen. Auditiert (EIN Beleg je Freigabe).

        BEGRUENDUNG IST PFLICHT. Eine Freigabe ohne Begruendung belegte nur,
        dass jemand geklickt hat — nicht, dass eine Aufsichtsentscheidung
        getroffen wurde. Letzteres ist der Zweck dieses Schreibpfads.

        EINE FREIGABE JE FALL UND PERSON (E-1). Besteht bereits eine gueltige,
        wird NICHT still eine zweite angelegt: der Aufrufer erfaehrt, dass es
        sie gibt. Zwei gleichzeitige Freigaben mit verschiedenen Zwecken waeren
        eine Auskunft, die sich selbst widerspricht.
        """
        writer = self._require_writer()
        sid, pid = int(subject_id), int(person_id)
        if actor_id is None:
            raise FulltextReleaseFehler(
                "Ohne Handelnden wird keine Freigabe erteilt.")
        try:
            code, freitext = pruefe(zweck_code, zweck_freitext)
        except ZweckFehler as exc:
            raise FulltextReleaseFehler(str(exc)) from exc
        grund_txt = (begruendung or "").strip()
        if not grund_txt:
            raise FulltextReleaseFehler(
                "Begruendung ist Pflicht: eine Freigabe ohne Begruendung "
                "belegt nur einen Klick, keine Entscheidung.")
        if sid == 0 or pid == 0:
            raise FulltextReleaseFehler(
                "subject_id und person_id sind Pflicht.")

        now = int(time.time())
        state: Dict[str, Any] = {"row_id": None}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            # Fachregel INNERHALB der Transaktion (BEGIN IMMEDIATE) pruefen.
            # Der partielle UNIQUE-Index aus M040 wuerde sie ebenfalls
            # durchsetzen — aber mit einer Meldung, die niemandem hilft.
            vorhanden = self._aktive(con, sid, pid)
            if vorhanden is not None:
                raise FulltextReleaseFehler(
                    "Fuer Fall %d und Person %d besteht bereits eine "
                    "gueltige Freigabe (#%d, erteilt am %s). Sie ist zuerst "
                    "zu widerrufen."
                    % (sid, pid, int(vorhanden["id"]),
                       vorhanden["granted_at"]))
            cur = con.execute(
                "INSERT INTO fulltext_release "
                "(subject_id, person_id, zweck_code, zweck_freitext, "
                " begruendung, granted_by, granted_at, audit_seq, is_active) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 0, 1)",
                (sid, pid, code, freitext, grund_txt, int(actor_id), now))
            state["row_id"] = int(cur.lastrowid or 0)
            # Payload: FAKTEN + Zweckcode + Textlaengen, KEIN Freitext.
            return {
                "release_id": state["row_id"],
                "subject_id": sid,
                "person_id": pid,
                "zweck_code": code,
                "zweck_freitext_len": self._tlen(freitext),
                "begruendung_len": self._tlen(grund_txt),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "UPDATE fulltext_release SET audit_seq = ? WHERE id = ?",
                (seq, state["row_id"]))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.FULLTEXT_RELEASE_GRANTED,
            actor_id=int(actor_id), target_type="fulltext_release",
            target_id=str(sid), meta=meta, after_audit=_after)
        logger.info("Inhaltsfreigabe Fall %d fuer Person %d erteilt "
                    "(Zweck %s, Freigabe #%s, Beleg #%d).",
                    sid, pid, code, state["row_id"], seq)
        return {"release_id": state["row_id"], "subject_id": sid,
                "person_id": pid, "zweck_code": code, "audit_seq": seq}

    def widerrufe(self, *, release_id: Any, reason: str,
                  actor_id: Optional[int] = None,
                  meta: Optional[Any] = None) -> Dict[str, Any]:
        """
        Freigabe WIDERRUFEN (soft): is_active=0 + Pflichtgrund.

        Die Zeile BLEIBT. Ein stilles Loeschen vernichtete die Erkenntnis
        "es wurde einmal freigegeben" — und gerade die ist die
        aufsichtsrelevante (Grundregel 1).
        """
        writer = self._require_writer()
        rid = int(release_id)
        if actor_id is None:
            raise FulltextReleaseFehler(
                "Ohne Handelnden wird keine Freigabe widerrufen.")
        reason_txt = (reason or "").strip()
        if not reason_txt:
            raise FulltextReleaseFehler(
                "Grund ist Pflicht: eine Freigabe darf nicht ohne "
                "nachvollziehbaren Grund widerrufen werden.")
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._row(con, rid)
            if row is None:
                raise FulltextReleaseFehler("Unbekannte Freigabe #%d." % rid)
            if int(row["is_active"]) != 1:
                raise FulltextReleaseFehler(
                    "Freigabe #%d ist bereits widerrufen — ein zweiter "
                    "Widerruf erzeugte einen irrefuehrenden Beleg." % rid)
            con.execute(
                "UPDATE fulltext_release SET is_active = 0, revoked_at = ?, "
                "revoked_by = ?, revoke_reason = ? WHERE id = ?",
                (now, int(actor_id), reason_txt, rid))
            return {
                "release_id": rid,
                "subject_id": int(row["subject_id"]),
                "person_id": int(row["person_id"]),
                "zweck_code": row["zweck_code"],
                "revoke_reason_len": self._tlen(reason_txt),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "UPDATE fulltext_release SET revoke_audit_seq = ? "
                "WHERE id = ?", (seq, rid))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.FULLTEXT_RELEASE_REVOKED,
            actor_id=int(actor_id), target_type="fulltext_release",
            target_id=str(rid), meta=meta, after_audit=_after)
        logger.info("Inhaltsfreigabe #%d widerrufen (Beleg #%d).", rid, seq)
        return {"release_id": rid, "audit_seq": seq}
