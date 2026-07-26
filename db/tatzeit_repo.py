# =============================================================================
# db/tatzeit_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A, Build 533)
# =============================================================================
# Zweck:
#   Lese- und Schreibzugriff auf 'annotation_tatzeit' in evidence_<uid>.db.
#   Jeder Schreibvorgang laeuft ueber EvidenceWriter und traegt damit einen
#   Beleg in derselben Transaktion und derselben Datei.
#
# ── APPEND-ONLY, GENAU WIE 'annotations' ─────────────────────────────────────
#
#   Es gibt KEIN UPDATE des Inhalts. Eine Korrektur ist eine NEUE Zeile mit
#   version_nr+1 und prev_id auf die Vorgaengerzeile; die Vorgaengerin bekommt
#   deleted_at gesetzt. Das ist Zeile fuer Zeile dasselbe Verfahren wie in
#   db/evidence_db.py:884-919 (save_annotation, Zweig A) — bewusst, damit hier
#   niemand ein zweites Versionierungsmodell lernen muss.
#
#   DIE FALLE, DIE DORT SCHON DOKUMENTIERT IST (db/evidence_db.py:886-891) GILT
#   HIER GENAUSO: 'deleted_at' auf der Vorgaengerin bedeutet "geaendert am ts",
#   NICHT "geloescht". Unterschieden wird das allein daran, ob eine Zeile mit
#   prev_id = this.id existiert. Wer das verwechselt, zaehlt jede Korrektur als
#   Ruecknahme — und der Fristenmonitor saehe eine festgestellte Tatzeit, die
#   es gar nicht mehr gibt, oder umgekehrt.
#
# ── WAS DIESES MODUL NICHT TUT ───────────────────────────────────────────────
#
#   Es rechnet KEINE Frist. Es liest keine Verjaehrungsparameter und kennt
#   keine Tatbestaende. Die Auswertung im Fristenmonitor ist Build 535; bis
#   dahin steht 'festgestellt=False' in limitation_repo.compute() unveraendert.
#   Diese Trennung ist Absicht: die Tabelle soll in der VM einzeln befuellt und
#   geprueft werden koennen, bevor sich die Aussage des Monitors aendert.
#
# ── PLAUSIBILITAETSRAHMEN: IMPORTIERT, NICHT KOPIERT ─────────────────────────
#
#   m002 traegt den Rahmen als FROZEN COPY im CHECK (m002:215-218) — richtig,
#   denn eine angewandte Migration darf ihre Bedeutung nicht nachtraeglich
#   aendern. Der LAUFZEITCODE dagegen importiert die Konstanten aus
#   management/deadlines/limitation_repo.py:206-207. Der Unterschied ist
#   beabsichtigt: die Maske soll dieselbe Grenze melden, die der Monitor
#   benutzt. Laufen beide je auseinander, faellt es hier auf — als sauberer
#   400er statt als IntegrityError aus der Tiefe der Datenbank. Test TR09 haelt
#   die Gleichheit fest.
#
# Version: v0.8.533 · Build: 533 · 2026-07-26
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from db.tatzeit_vokabular import (
    ANGABE_SCHLUESSEL,
    ART_HART,
    ART_WEICH,
    ARTEN,
    GENAUIGKEITEN,
    VokabularError,
    quelle_bauen,
    quelle_zerlegen,
)
from management.audit.event_types import EventType
from management.deadlines.limitation_repo import PLAUSIBEL_BIS, PLAUSIBEL_VON
from management.gateway.evidence_writer import EvidenceWriter

logger = logging.getLogger(__name__)

#: Spalten, die gelesen werden. Als Konstante, damit Lesen und Testen sich auf
#  denselben Satz beziehen.
_SPALTEN = (
    "id", "annotation_id", "annotation_local_id", "art", "von_ts", "bis_ts",
    "genauigkeit", "angabe_schluessel", "angabe_wert", "wortlaut", "quelle",
    "erfasst_von", "erfasst_at", "version_nr", "prev_id", "deleted_at",
)


class TatzeitError(ValueError):
    """Fachlicher Fehler — es wurde NICHTS geschrieben."""


class TatzeitRepo:
    """Append-only Zugriff auf 'annotation_tatzeit' in evidence_<uid>.db."""

    def __init__(self, con: sqlite3.Connection,
                 writer: Optional[EvidenceWriter] = None) -> None:
        """
        con    — die evidence-Verbindung. Im Serverbetrieb ist das die GETEILTE
                 LockingConnection des Bundles (db/connection_manager.py:337);
                 EvidenceWriter haelt fuer seine Transaktionen deren Lock.
        writer — nur fuer Schreibzugriffe noetig. Fehlt er, sind die
                 Schreibmethoden gesperrt (statt still nichts zu tun).
        """
        self._con = con
        self._writer = writer

    # ------------------------------------------------------------------ Lesen
    def liste(self, *, annotation_id: Optional[int] = None,
              annotation_local_id: Optional[str] = None,
              mit_historie: bool = False) -> List[Dict[str, Any]]:
        """
        Liefert die Tatzeitangaben zu einer Annotation.

        Aufloesung wie in der Uebergabe festgelegt: ueber 'annotation_local_id'
        (die LOGISCHE Annotation, damit die Tatzeit einer bearbeiteten
        Annotation FOLGT), mit Rueckfall auf 'annotation_id' — denn local_id
        ist optional ("anonyme Einmal-Annotation", db/evidence_db.py:871).

        mit_historie=False liefert nur die aktiven Zeilen (deleted_at IS NULL).
        mit_historie=True liefert alles, aelteste zuerst — fuer die Akte.
        """
        if annotation_id is None and not annotation_local_id:
            raise TatzeitError(
                "Weder annotation_id noch annotation_local_id angegeben — "
                "eine Tatzeit ohne Bezug waere nicht zuzuordnen.")

        felder = ", ".join('"%s"' % s for s in _SPALTEN)
        if annotation_local_id:
            wo = '"annotation_local_id" = ?'
            args: tuple = (str(annotation_local_id),)
        else:
            wo = '"annotation_id" = ?'
            args = (int(annotation_id),)

        if not mit_historie:
            wo += ' AND "deleted_at" IS NULL'

        rows = self._con.execute(
            'SELECT %s FROM "annotation_tatzeit" WHERE %s ORDER BY "id" ASC'
            % (felder, wo), args
        ).fetchall()
        return [self._zeile(r) for r in rows]

    def eine(self, tatzeit_id: int) -> Optional[Dict[str, Any]]:
        """Eine einzelne Zeile, unabhaengig von deleted_at (oder None)."""
        felder = ", ".join('"%s"' % s for s in _SPALTEN)
        row = self._con.execute(
            'SELECT %s FROM "annotation_tatzeit" WHERE "id" = ?' % felder,
            (int(tatzeit_id),)
        ).fetchone()
        return self._zeile(row) if row is not None else None

    def hat_nachfolger(self, tatzeit_id: int) -> bool:
        """
        True, wenn eine Zeile mit prev_id = tatzeit_id existiert.

        Das ist die EINZIGE Art, eine Korrektur von einer Ruecknahme zu
        unterscheiden (s. Kopf). Deshalb steht sie als eigene, benannte
        Methode hier und nicht als Bedingung mitten in einer Abfrage.
        """
        return self._con.execute(
            'SELECT 1 FROM "annotation_tatzeit" WHERE "prev_id" = ? LIMIT 1',
            (int(tatzeit_id),)
        ).fetchone() is not None

    @staticmethod
    def _zeile(row: sqlite3.Row) -> Dict[str, Any]:
        d = {s: row[s] for s in _SPALTEN}
        code, freitext = quelle_zerlegen(d.get("quelle") or "")
        d["quelle_code"] = code
        d["quelle_freitext"] = freitext
        return d

    # -------------------------------------------------------------- Pruefungen
    @staticmethod
    def _ts(wert: Any, feld: str) -> Optional[int]:
        """Wandelt einen Zeitwert und prueft den Plausibilitaetsrahmen."""
        if wert is None or wert == "":
            return None
        try:
            ts = int(wert)
        except (TypeError, ValueError):
            raise TatzeitError(
                "%s ist keine Ganzzahl (Unix-Zeit in Sekunden): %r" % (feld, wert))
        if ts < PLAUSIBEL_VON or ts > PLAUSIBEL_BIS:
            # Der CHECK in der Datenbank faengt das ebenfalls ab (m002:215-218).
            # Hier faellt es als lesbare Meldung auf, statt als IntegrityError.
            raise TatzeitError(
                "%s liegt ausserhalb des Plausibilitaetsrahmens "
                "(%d..%d, entspricht 2018-01-01 bis 2027-01-01): %d"
                % (feld, PLAUSIBEL_VON, PLAUSIBEL_BIS, ts))
        return ts

    def _pruefe(self, *, art: str, von_ts: Optional[int], bis_ts: Optional[int],
                genauigkeit: Optional[str], angabe_schluessel: Optional[str],
                angabe_wert: Optional[str]) -> None:
        """
        Spiegelt die CHECK-Bedingungen aus m002 im Anwendungscode.

        WARUM DOPPELT GEPRUEFT WIRD: Der CHECK ist die letzte Verteidigung und
        wirkt auch gegen einen kuenftigen Schreibpfad, den es heute noch nicht
        gibt — er bleibt. Aber ein IntegrityError sagt der Ermittlerin nicht,
        WAS sie falsch gemacht hat. Diese Pruefung liefert den Satz dazu.
        Beide Ebenen pruefen dasselbe; TR08 stellt sicher, dass sie sich einig
        sind, indem es jede hier abgelehnte Eingabe auch gegen die Datenbank
        laufen laesst.
        """
        if art not in ARTEN:
            raise TatzeitError(
                "Unbekannte Art %r. Zulaessig: %s"
                % (art, ", ".join(sorted(ARTEN))))

        if genauigkeit is not None and genauigkeit not in GENAUIGKEITEN:
            raise TatzeitError(
                "Unbekannte Genauigkeit %r. Zulaessig: %s"
                % (genauigkeit, ", ".join(sorted(GENAUIGKEITEN))))

        if art == ART_HART:
            if von_ts is None and bis_ts is None:
                raise TatzeitError(
                    "Eine harte Tatzeitangabe braucht mindestens einen "
                    "Zeitwert (Beginn oder Ende). Sonst wuerde sie als "
                    "festgestellt gezaehlt, ohne etwas festzustellen.")
            if angabe_schluessel is not None or angabe_wert is not None:
                raise TatzeitError(
                    "Eine harte Angabe fuehrt keine weichen Felder mit — "
                    "sonst waere unklar, was gilt.")
            if von_ts is not None and bis_ts is not None and bis_ts < von_ts:
                raise TatzeitError(
                    "Das Ende liegt vor dem Beginn (%d < %d)." % (bis_ts, von_ts))
        else:  # ART_WEICH
            if not angabe_schluessel:
                raise TatzeitError(
                    "Eine unscharfe Angabe braucht ihren Schluessel, sonst ist "
                    "sie weder auswertbar noch wiederfindbar.")
            if angabe_schluessel not in ANGABE_SCHLUESSEL:
                raise TatzeitError(
                    "Unbekannter Angabe-Schluessel %r. Zulaessig: %s"
                    % (angabe_schluessel, ", ".join(sorted(ANGABE_SCHLUESSEL))))
            if von_ts is not None or bis_ts is not None:
                raise TatzeitError(
                    "Eine unscharfe Angabe fuehrt keine Zeitwerte mit. Wenn "
                    "ein Datum bekannt ist, ist die Angabe nicht unscharf.")

    # --------------------------------------------------------------- Schreiben
    def setzen(
        self,
        *,
        annotation_id: int,
        annotation_local_id: Optional[str],
        art: str,
        quelle_code: str,
        actor_id: int,
        von_ts: Any = None,
        bis_ts: Any = None,
        genauigkeit: Optional[str] = None,
        angabe_schluessel: Optional[str] = None,
        angabe_wert: Optional[str] = None,
        wortlaut: Optional[str] = None,
        quelle_freitext: Optional[str] = None,
        ersetzt_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Erfasst eine Tatzeitangabe oder ersetzt eine bestehende durch eine neue
        Version (append-only). Schreibt Fachzeile UND Beleg in EINER
        Transaktion.

        ersetzt_id — die zu ersetzende Zeile. None = Ersterfassung.

        Gibt {"tatzeit_id", "version_nr", "prev_id", "audit_seq"} zurueck.
        """
        if self._writer is None:
            raise TatzeitError(
                "Dieses Repository ist ohne Schreibpfad geoeffnet (kein "
                "EvidenceWriter). Es wurde NICHTS geschrieben.")
        if actor_id is None:
            raise TatzeitError(
                "Kein Handelnder — ein Beleg ohne Handelnden ist kein Beleg.")

        art = (art or "").strip()
        genauigkeit = (genauigkeit or None)
        angabe_schluessel = (angabe_schluessel or None)
        angabe_wert = (angabe_wert or None)
        wortlaut = (wortlaut or None)

        von = self._ts(von_ts, "von_ts")
        bis = self._ts(bis_ts, "bis_ts")
        self._pruefe(art=art, von_ts=von, bis_ts=bis, genauigkeit=genauigkeit,
                     angabe_schluessel=angabe_schluessel,
                     angabe_wert=angabe_wert)

        try:
            quelle = quelle_bauen(quelle_code, quelle_freitext)
        except VokabularError as exc:
            raise TatzeitError(str(exc))

        # --- Vorgaengerin pruefen (VOR der Transaktion, damit ein Fehlgriff
        #     gar nicht erst eine Schreibsperre nimmt) ------------------------
        vorgaenger = None
        if ersetzt_id is not None:
            vorgaenger = self.eine(int(ersetzt_id))
            if vorgaenger is None:
                raise TatzeitError(
                    "Die zu ersetzende Tatzeitangabe #%s gibt es nicht."
                    % ersetzt_id)
            if vorgaenger["deleted_at"] is not None:
                # Eine bereits ersetzte oder zurueckgenommene Zeile darf nicht
                # noch einmal ersetzt werden — sonst entstuenden zwei Aeste an
                # derselben Stelle, und keiner waere mehr "der aktuelle".
                raise TatzeitError(
                    "Die Tatzeitangabe #%s ist nicht mehr aktiv (bereits "
                    "ersetzt oder zurueckgenommen). Es wurde NICHTS "
                    "geschrieben." % ersetzt_id)
            if int(vorgaenger["annotation_id"]) != int(annotation_id):
                raise TatzeitError(
                    "Die zu ersetzende Angabe gehoert zu Annotation #%s, nicht "
                    "zu #%s." % (vorgaenger["annotation_id"], annotation_id))

        jetzt = int(time.time())
        neue_version = 1 if vorgaenger is None else int(vorgaenger["version_nr"]) + 1
        prev_id = None if vorgaenger is None else int(vorgaenger["id"])
        ergebnis: Dict[str, Any] = {}

        def _write(con: sqlite3.Connection) -> Dict[str, Any]:
            # (1) Vorgaengerin markieren. 'deleted_at' heisst hier "geaendert
            #     am" — unterschieden wird das ueber den Nachfolger (s. Kopf).
            if prev_id is not None:
                con.execute(
                    'UPDATE "annotation_tatzeit" SET "deleted_at" = ? '
                    'WHERE "id" = ? AND "deleted_at" IS NULL',
                    (jetzt, prev_id),
                )
            # (2) Neue Zeile.
            cur = con.execute(
                'INSERT INTO "annotation_tatzeit" '
                '("annotation_id", "annotation_local_id", "art", "von_ts", '
                ' "bis_ts", "genauigkeit", "angabe_schluessel", "angabe_wert", '
                ' "wortlaut", "quelle", "erfasst_von", "erfasst_at", '
                ' "version_nr", "prev_id") '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (int(annotation_id),
                 str(annotation_local_id) if annotation_local_id else None,
                 art, von, bis, genauigkeit, angabe_schluessel, angabe_wert,
                 wortlaut, quelle, int(actor_id), jetzt, neue_version, prev_id),
            )
            neue_id = int(cur.lastrowid)
            ergebnis["tatzeit_id"] = neue_id
            ergebnis["version_nr"] = neue_version
            ergebnis["prev_id"] = prev_id

            # (3) Payload des Belegs — NUR FAKTEN. Kein Wortlaut, kein
            #     Freitext (Sensibilitaetsregel wie M018/M022, s.
            #     event_types.py bei TATZEIT_SET). Vom Freitext nur die Laenge:
            #     sie belegt, DASS eine Begruendung da war, ohne sie in eine
            #     zweite Datei zu tragen.
            code, freitext = quelle_zerlegen(quelle)
            return {
                "tatzeit_id": neue_id,
                "annotation_id": int(annotation_id),
                "annotation_local_id": annotation_local_id or None,
                "art": art,
                "von_ts": von,
                "bis_ts": bis,
                "genauigkeit": genauigkeit,
                "angabe_schluessel": angabe_schluessel,
                "quelle_code": code,
                "quelle_freitext_len": len(freitext) if freitext else 0,
                "wortlaut_len": len(wortlaut) if wortlaut else 0,
                "angabe_wert_len": len(angabe_wert) if angabe_wert else 0,
                "version_nr": neue_version,
                "prev_id": prev_id,
            }

        seq = self._writer.audited_write(
            do_write=_write,
            event_type=EventType.TATZEIT_SET,
            actor_id=int(actor_id),
            target_type="annotation",
            target_id=str(annotation_id),
        )
        ergebnis["audit_seq"] = seq
        logger.info(
            "Tatzeit gesetzt: #%s (Annotation %s, Version %s, Beleg seq=%s)",
            ergebnis["tatzeit_id"], annotation_id, neue_version, seq)
        return ergebnis

    def zuruecknehmen(self, *, tatzeit_id: int, actor_id: int,
                      grund: Optional[str] = None) -> Dict[str, Any]:
        """
        Nimmt eine Tatzeitangabe zurueck (deleted_at, KEINE Nachfolgeversion).

        Bewusst getrennt von setzen(): eine Ruecknahme ist die Aussage, dass
        eine frueher festgestellte Zeit nicht mehr traegt — nicht dieselbe
        Handlung wie eine Korrektur. Deshalb ein eigener Ereignistyp
        (TATZEIT_CLEARED), dieselbe Begruendung wie bei
        ESCALATION_ACK_REVOKED.
        """
        if self._writer is None:
            raise TatzeitError(
                "Dieses Repository ist ohne Schreibpfad geoeffnet (kein "
                "EvidenceWriter). Es wurde NICHTS geschrieben.")
        if actor_id is None:
            raise TatzeitError(
                "Kein Handelnder — ein Beleg ohne Handelnden ist kein Beleg.")

        zeile = self.eine(int(tatzeit_id))
        if zeile is None:
            raise TatzeitError(
                "Die Tatzeitangabe #%s gibt es nicht." % tatzeit_id)
        if zeile["deleted_at"] is not None:
            raise TatzeitError(
                "Die Tatzeitangabe #%s ist bereits nicht mehr aktiv. Es wurde "
                "NICHTS geschrieben." % tatzeit_id)

        jetzt = int(time.time())
        grund_text = (grund or "").strip()

        def _write(con: sqlite3.Connection) -> Dict[str, Any]:
            con.execute(
                'UPDATE "annotation_tatzeit" SET "deleted_at" = ? '
                'WHERE "id" = ? AND "deleted_at" IS NULL',
                (jetzt, int(tatzeit_id)),
            )
            return {
                "tatzeit_id": int(tatzeit_id),
                "annotation_id": int(zeile["annotation_id"]),
                "art": zeile["art"],
                "von_ts": zeile["von_ts"],
                "bis_ts": zeile["bis_ts"],
                "version_nr": int(zeile["version_nr"]),
                "grund_len": len(grund_text),
                "deleted_at": jetzt,
            }

        seq = self._writer.audited_write(
            do_write=_write,
            event_type=EventType.TATZEIT_CLEARED,
            actor_id=int(actor_id),
            target_type="annotation",
            target_id=str(zeile["annotation_id"]),
        )
        logger.info("Tatzeit zurueckgenommen: #%s (Beleg seq=%s)",
                    tatzeit_id, seq)
        return {"tatzeit_id": int(tatzeit_id), "audit_seq": seq,
                "deleted_at": jetzt}
