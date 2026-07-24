# =============================================================================
# management/crossref/subject_alias_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Identitaet (AP-2A)
# =============================================================================
# Zweck (Idee 8, Build 504):
#   Zugriffsschicht auf 'subject_alias' (M022) — den GLOBALEN ALIAS-KATALOG:
#   "Forenkonto <subject_id> tritt AUSSERDEM unter dem Namen <alias> auf".
#   Fall-UEBERGREIFEND, weil ein Zweitname genau dann wertvoll ist, wenn er in
#   einem ANDEREN Fall auftaucht als dem, in dem er gefunden wurde.
#
#   SCHREIBEN ausschliesslich ueber das CoordinatorWriter-Gateway: fachlicher
#   Write + audit_log-Beleg committen in EINER Transaktion oder gar nicht.
#   Keine Erkenntnis ohne lueckenlosen Beleg (Grundregel 1).
#
# ABGRENZUNG (kein Duplizieren, belegt):
#   forensic_api/aliases.py = fallbezogener Ermittler-SUCHBEGRIFF in der
#   evidence_<uid>.db (Baustelle 3). identified_subject (M018) = "Konto ->
#   REALE PERSON". HIER = "Konto -> WEITERER FORENNAME".
#
# ci-NORMALISIERUNG (die zentrale fachliche Entscheidung dieses Moduls):
#   'alias_norm' = alias.strip().casefold(). Die Kollations-Leitlinie des Falls
#   richtet alles an users.username (utf8mb4_unicode_ci) aus — Matching ist
#   case-INsensitiv (mc 2026-07-20). SQLite bietet nur ASCII-NOCASE; in einem
#   multilingualen Forum (Fall-Erkenntnis 2) waeren damit 'Ярослав'/'ЯРОСЛАВ'
#   oder 'STRASSE'/'strasse' still zu getrennten Eintraegen geworden — ein
#   Duplikat, das der Ermittlerin einen Zusammenhang VERBERGEN wuerde.
#   casefold() ist die Unicode-korrekte Normalform (und faltet u. a. das
#   deutsche 'ß' auf 'ss'). Die ORIGINALSCHREIBWEISE bleibt in 'alias'
#   erhalten: sie ist selbst ein Beweismittel (Schreibgewohnheiten koennen
#   Zuordnungsindizien sein).
#
# ALIASTEXT IST UNVERAENDERLICH (Entwurfsentscheidung, zur Abnahme):
#   update() aendert Art/Basis/Notiz, NICHT den Aliastext. Ein anderer Text ist
#   eine ANDERE Erkenntnis — sie entsteht durch retract() des falschen und
#   add() des richtigen Eintrags. So bleibt im Katalog sichtbar, dass jemand
#   den Namen X einmal fuer belegt hielt; ein stilles Ueberschreiben haette
#   diesen Zwischenstand geloescht (Grundregel 1).
#
# WIDERRUF STATT LOESCHUNG: retract() setzt is_active=0 und speichert den
#   Pflicht-Grund. Die Zeile bleibt. Der partielle UNIQUE-Index (M022) laesst
#   danach eine Neuvergabe desselben Namens zu.
#
# SENSIBILITAETSREGEL (streng, Muster M018): alias/basis/note/retracted_reason
#   gehen NIE als Klartext in den audit_log-Payload — dort stehen nur FAKTEN
#   (subject_id, alias_id, kind_code, is_active) + TEXTLAENGEN. Damit bleibt
#   der Beleg pruefbar, ohne die sensiblen Inhalte zu spiegeln.
#   ANMERKUNG ZUR ABNAHME: ein Forenname ist schwaechere PII als ein Klarname.
#   Ich behandle ihn dennoch gleich streng, weil ein Alias eine reale Person
#   identifizierbar machen KANN. Soll der Alias im Klartext im Beleg stehen,
#   ist das eine Ein-Zeilen-Aenderung in _payload_add/_payload_state.
#
# NEBENLAEUFIGKEIT: alle Kollisionspruefungen laufen INNERHALB der Transaktion
#   (BEGIN IMMEDIATE haelt die Schreibsperre) — kein TOCTOU-Fenster gegen
#   konkurrierende Schreiber (Muster IdentifiedSubjectRepo/PersonRepo).
#
# Version: v0.8.504 · Build: 504 · 2026-07-24
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.crossref.identified_subject_repo import CrossrefError
from management.gateway.coordinator_writer import CoordinatorWriter

logger = logging.getLogger(__name__)

#: Geschlossene Menge der Alias-Arten. Muss zur CHECK-Klausel in m022 passen
#  (dort LITERAL, m005-Prinzip: die Migration importiert dieses Modul NICHT).
#  Reihenfolge = Anzeigereihenfolge in der Oberflaeche.
ALIAS_KINDS: Dict[str, str] = {
    "forenname": "weiterer Forenname",
    "handle": "Handle/Nickname ausserhalb des Forums",
    "signatur": "Name aus einer Signatur",
    "kontakt": "Kontaktkennung (Messenger, Mail, o. ae.)",
    "sonstiges": "sonstiger Bezug",
}

#: Freitextfelder — im Audit-Payload NUR als Laenge, nie als Inhalt.
_TEXT_FIELDS = ("alias", "basis", "note")


class SubjectAliasRepo:
    """Auditierte Lese-/Schreibmethoden auf 'subject_alias' (M022)."""

    def __init__(self, con: sqlite3.Connection,
                 writer: Optional[CoordinatorWriter] = None) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._writer = writer

    # ------------------------------------------------------------------ Hilfen
    def _require_writer(self) -> CoordinatorWriter:
        if self._writer is None:
            raise CrossrefError(
                "Schreibzugriff ohne CoordinatorWriter — kein unauditierter "
                "Schreibpfad zulaessig.")
        return self._writer

    @staticmethod
    def normalize(alias: str) -> str:
        """
        Unicode-korrekte, case-insensitive Normalform eines Alias.
        REIN (kein DB-Zugriff) und damit direkt pruefbar. Siehe Kopfkommentar:
        casefold() statt lower()/NOCASE, weil das Forum multilingual ist.
        """
        return (alias or "").strip().casefold()

    @staticmethod
    def _tlen(text: Optional[str]) -> int:
        return len(text or "")

    @staticmethod
    def _require_kind(kind_code: str) -> str:
        """Prueft die Alias-Art gegen die geschlossene Menge. Der Repo laesst
        KEINE Art zu, die die DDL-CHECK spaeter ablehnte."""
        if kind_code not in ALIAS_KINDS:
            raise CrossrefError(
                "Ungueltige Alias-Art %r (erlaubt: %s)."
                % (kind_code, ", ".join(ALIAS_KINDS)))
        return kind_code

    @staticmethod
    def _row_by_id(con: sqlite3.Connection,
                   alias_id: int) -> Optional[sqlite3.Row]:
        return con.execute(
            "SELECT * FROM subject_alias WHERE id = ?", (alias_id,)).fetchone()

    @staticmethod
    def _active_collision(con: sqlite3.Connection, subject_id: int,
                          alias_norm: str,
                          except_id: Optional[int] = None) -> Optional[int]:
        """id eines AKTIVEN Eintrags mit gleicher (subject_id, Normform) oder
        None. 'except_id' blendet die eigene Zeile aus (fuer reinstate)."""
        sql = ("SELECT id FROM subject_alias WHERE subject_id = ? "
               "AND alias_norm = ? AND is_active = 1")
        params: List[Any] = [subject_id, alias_norm]
        if except_id is not None:
            sql += " AND id <> ?"
            params.append(except_id)
        row = con.execute(sql, params).fetchone()
        return int(row["id"]) if row is not None else None

    # ------------------------------------------------------------------- Lesen
    def list(self, subject_id: Optional[int] = None,
             include_retracted: bool = False) -> List[Dict[str, Any]]:
        """
        Aliasse; ohne 'subject_id' der ganze Katalog. Aktive zuerst, dann nach
        Konto und Normform — die Reihenfolge, in der man einen Katalog liest.
        Widerrufene erscheinen NUR mit include_retracted (sie sind kein
        Leerbefund, sondern ein anderer Erkenntnisstand).
        """
        where: List[str] = []
        params: List[Any] = []
        if subject_id is not None:
            where.append("subject_id = ?")
            params.append(int(subject_id))
        if not include_retracted:
            where.append("is_active = 1")
        sql = "SELECT * FROM subject_alias"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY is_active DESC, subject_id ASC, alias_norm ASC"
        return [self._as_dict(r) for r in self._con.execute(sql, params)]

    def search(self, term: str,
               include_retracted: bool = False) -> List[Dict[str, Any]]:
        """
        RUECKWAERTSSUCHE: "welche Konten fuehren diesen Namen?" — der eigentliche
        Ermittlungsnutzen des Katalogs. Sucht ueber die Normform (Teilstring,
        case-insensitiv durch die Normalisierung BEIDER Seiten).
        Leerer Suchbegriff -> leere Liste (KEIN stiller Gesamtabzug: wer nichts
        sucht, soll nicht versehentlich alles bekommen).
        """
        norm = self.normalize(term)
        if not norm:
            return []
        sql = "SELECT * FROM subject_alias WHERE alias_norm LIKE ? ESCAPE '\\'"
        if not include_retracted:
            sql += " AND is_active = 1"
        sql += " ORDER BY is_active DESC, alias_norm ASC, subject_id ASC"
        # LIKE-Sonderzeichen im Suchbegriff entschaerfen, damit '%' nicht
        # unbeabsichtigt als Platzhalter wirkt.
        escaped = norm.replace("\\", "\\\\").replace("%", "\\%") \
                      .replace("_", "\\_")
        rows = self._con.execute(sql, ("%" + escaped + "%",)).fetchall()
        return [self._as_dict(r) for r in rows]

    def counts(self) -> Dict[str, int]:
        """Gesamt / aktiv / widerrufen / Anzahl betroffener Konten (aktiv)."""
        row = self._con.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS aktiv, "
            "SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) AS widerrufen "
            "FROM subject_alias").fetchone()
        subjects = self._con.execute(
            "SELECT COUNT(DISTINCT subject_id) AS n FROM subject_alias "
            "WHERE is_active = 1").fetchone()
        return {
            "total": int(row["total"] or 0),
            "aktiv": int(row["aktiv"] or 0),
            "widerrufen": int(row["widerrufen"] or 0),
            "subjects": int(subjects["n"] or 0),
        }

    # --------------------------------------------------------------- Schreiben
    def add(self, *, subject_id: int, alias: str, kind_code: str,
            basis: str = "", note: Optional[str] = None,
            actor_id: Optional[int] = None,
            meta: Optional[Any] = None) -> Dict[str, Any]:
        """
        Legt einen Alias an. Duplikat (aktiv, gleiche Normform am selben Konto)
        -> CrossrefError. Auditiert. -> {'alias_id','subject_id','audit_seq'}.
        """
        writer = self._require_writer()
        sid = int(subject_id)
        alias_raw = (alias or "").strip()
        if not alias_raw:
            raise CrossrefError("Der Alias darf nicht leer sein.")
        norm = self.normalize(alias_raw)
        if not norm:
            raise CrossrefError(
                "Der Alias besteht nur aus Leerraum — kein verwertbarer Name.")
        self._require_kind(kind_code)
        basis = basis or ""
        note_norm = note if (note is None or note != "") else None

        now = int(time.time())
        state: Dict[str, Any] = {"row_id": None}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            # Kollisionspruefung INNERHALB der Transaktion (BEGIN IMMEDIATE).
            clash = self._active_collision(con, sid, norm)
            if clash is not None:
                raise CrossrefError(
                    "Alias %r ist am Konto %s bereits aktiv erfasst "
                    "(Eintrag #%d). Gross-/Kleinschreibung wird dabei nicht "
                    "unterschieden." % (alias_raw, sid, clash))
            cur = con.execute(
                "INSERT INTO subject_alias "
                "(subject_id, alias, alias_norm, kind_code, basis, note, "
                " is_active, retracted_reason, created_by, updated_by, "
                " created_at, updated_at, audit_seq, created_audit_seq) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, NULL, ?, ?, ?, ?, 0, 0)",
                (sid, alias_raw, norm, kind_code, basis, note_norm,
                 actor_id, actor_id, now, now),
            )
            state["row_id"] = int(cur.lastrowid or 0)
            # Payload: FAKTEN + Textlaengen, KEIN Freitext.
            return {
                "alias_id": state["row_id"],
                "subject_id": sid,
                "kind_code": kind_code,
                "alias_len": self._tlen(alias_raw),
                "basis_len": self._tlen(basis),
                "note_len": self._tlen(note_norm),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "UPDATE subject_alias SET audit_seq = ?, created_audit_seq = ? "
                "WHERE id = ?", (seq, seq, state["row_id"]))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.SUBJECT_ALIAS_ADDED,
            actor_id=actor_id, target_type="subject_alias",
            target_id=str(sid), meta=meta, after_audit=_after,
        )
        logger.info("subject_alias #%s angelegt (subject_id=%s, Beleg #%d).",
                    state["row_id"], sid, seq)
        return {"alias_id": state["row_id"], "subject_id": sid,
                "audit_seq": seq}

    def update(self, *, alias_id: int, kind_code: Optional[str] = None,
               basis: Optional[str] = None, note: Optional[str] = None,
               actor_id: Optional[int] = None,
               meta: Optional[Any] = None) -> Dict[str, Any]:
        """
        Aendert Art/Basis/Notiz eines Eintrags. Der ALIASTEXT ist bewusst NICHT
        aenderbar (siehe Kopfkommentar). Ein No-Op wirft CrossrefError und
        erzeugt KEINEN irrefuehrenden Beleg. Auditiert.
        """
        writer = self._require_writer()
        aid = int(alias_id)
        if kind_code is not None:
            self._require_kind(kind_code)
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._row_by_id(con, aid)
            if row is None:
                raise CrossrefError("Unbekannter Alias-Eintrag #%d." % aid)
            if int(row["is_active"]) != 1:
                raise CrossrefError(
                    "Eintrag #%d ist widerrufen — er wird erst durch "
                    "'Zuruecknehmen' wieder bearbeitbar." % aid)

            new_kind = kind_code if kind_code is not None else row["kind_code"]
            new_basis = basis if basis is not None else row["basis"]
            new_note = note if note is not None else row["note"]
            new_note = new_note if (new_note is None or new_note != "") else None

            changes: Dict[str, Any] = {}
            if row["kind_code"] != new_kind:
                changes["kind_code"] = {"alt": row["kind_code"],
                                        "neu": new_kind}
            # Freitext-Diffs NUR als Laengenaenderung (Sensibilitaetsregel).
            for field, old_val, new_val in (
                ("basis", row["basis"], new_basis),
                ("note", row["note"], new_note),
            ):
                if (old_val or "") != (new_val or ""):
                    changes["%s_len" % field] = {
                        "alt": self._tlen(old_val), "neu": self._tlen(new_val)}
            if not changes:
                raise CrossrefError(
                    "Keine Aenderung — die Werte entsprechen dem aktuellen "
                    "Stand (Eintrag #%d)." % aid)

            con.execute(
                "UPDATE subject_alias SET kind_code = ?, basis = ?, note = ?, "
                "updated_by = ?, updated_at = ? WHERE id = ?",
                (new_kind, new_basis or "", new_note, actor_id, now, aid))
            return {"alias_id": aid, "subject_id": int(row["subject_id"]),
                    "changes": changes}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE subject_alias SET audit_seq = ? WHERE id = ?",
                        (seq, aid))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.SUBJECT_ALIAS_UPDATED,
            actor_id=actor_id, target_type="subject_alias",
            target_id=str(aid), meta=meta, after_audit=_after,
        )
        logger.info("subject_alias #%d geaendert (Beleg #%d).", aid, seq)
        return {"alias_id": aid, "audit_seq": seq}

    def retract(self, *, alias_id: int, reason: str,
                actor_id: Optional[int] = None,
                meta: Optional[Any] = None) -> Dict[str, Any]:
        """
        WIDERRUF (soft): is_active=0 + Pflicht-Grund. Die Zeile BLEIBT — ein
        stilles Loeschen wuerde die Erkenntnis "wir hielten X einmal fuer einen
        Alias" vernichten (Grundregel 1). Danach darf derselbe Name am selben
        Konto neu erfasst werden (partieller UNIQUE-Index in M022).
        """
        writer = self._require_writer()
        aid = int(alias_id)
        reason_txt = (reason or "").strip()
        if not reason_txt:
            raise CrossrefError(
                "Grund ist Pflicht: ein Alias darf nicht ohne nachvollziehbaren "
                "Grund widerrufen werden.")
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._row_by_id(con, aid)
            if row is None:
                raise CrossrefError("Unbekannter Alias-Eintrag #%d." % aid)
            if int(row["is_active"]) != 1:
                raise CrossrefError(
                    "Eintrag #%d ist bereits widerrufen." % aid)
            con.execute(
                "UPDATE subject_alias SET is_active = 0, retracted_reason = ?, "
                "updated_by = ?, updated_at = ? WHERE id = ?",
                (reason_txt, actor_id, now, aid))
            return {"alias_id": aid, "subject_id": int(row["subject_id"]),
                    "is_active": 0, "reason_len": self._tlen(reason_txt)}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE subject_alias SET audit_seq = ? WHERE id = ?",
                        (seq, aid))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.SUBJECT_ALIAS_RETRACTED,
            actor_id=actor_id, target_type="subject_alias",
            target_id=str(aid), meta=meta, after_audit=_after,
        )
        logger.info("subject_alias #%d widerrufen (Beleg #%d).", aid, seq)
        return {"alias_id": aid, "audit_seq": seq}

    def reinstate(self, *, alias_id: int, actor_id: Optional[int] = None,
                  meta: Optional[Any] = None) -> Dict[str, Any]:
        """
        Nimmt einen Widerruf zurueck (der Widerruf war ein Irrtum). Kollidiert
        der Eintrag inzwischen mit einem AKTIVEN gleichen Alias am selben Konto,
        wird das sichtbar abgelehnt — sonst entstuenden zwei aktive Zeilen mit
        derselben Aussage. Der Kollisionstest laeuft in der Transaktion.
        """
        writer = self._require_writer()
        aid = int(alias_id)
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._row_by_id(con, aid)
            if row is None:
                raise CrossrefError("Unbekannter Alias-Eintrag #%d." % aid)
            if int(row["is_active"]) == 1:
                raise CrossrefError("Eintrag #%d ist bereits aktiv." % aid)
            clash = self._active_collision(
                con, int(row["subject_id"]), row["alias_norm"], except_id=aid)
            if clash is not None:
                raise CrossrefError(
                    "Zuruecknehmen nicht moeglich: am Konto %s ist derselbe "
                    "Alias inzwischen erneut aktiv erfasst (Eintrag #%d)."
                    % (int(row["subject_id"]), clash))
            con.execute(
                "UPDATE subject_alias SET is_active = 1, "
                "retracted_reason = NULL, updated_by = ?, updated_at = ? "
                "WHERE id = ?", (actor_id, now, aid))
            return {"alias_id": aid, "subject_id": int(row["subject_id"]),
                    "is_active": 1}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE subject_alias SET audit_seq = ? WHERE id = ?",
                        (seq, aid))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.SUBJECT_ALIAS_REINSTATED,
            actor_id=actor_id, target_type="subject_alias",
            target_id=str(aid), meta=meta, after_audit=_after,
        )
        logger.info("subject_alias #%d reaktiviert (Beleg #%d).", aid, seq)
        return {"alias_id": aid, "audit_seq": seq}

    # ------------------------------------------------------------------ intern
    @staticmethod
    def _as_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": int(row["id"]),
            "subject_id": int(row["subject_id"]),
            "alias": row["alias"],
            "alias_norm": row["alias_norm"],
            "kind_code": row["kind_code"],
            "kind_label": ALIAS_KINDS.get(row["kind_code"], row["kind_code"]),
            "basis": row["basis"],
            "note": row["note"],
            "is_active": int(row["is_active"]) == 1,
            "retracted_reason": row["retracted_reason"],
            "created_by": (int(row["created_by"])
                           if row["created_by"] is not None else None),
            "updated_by": (int(row["updated_by"])
                           if row["updated_by"] is not None else None),
            "created_at": int(row["created_at"]),
            "updated_at": int(row["updated_at"]),
            "audit_seq": int(row["audit_seq"]),
            "created_audit_seq": int(row["created_audit_seq"]),
        }
