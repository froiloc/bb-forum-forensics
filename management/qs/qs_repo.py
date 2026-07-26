# =============================================================================
# management/qs/qs_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3C (Build 541)
# =============================================================================
# Zweck:
#   Der SCHREIBPFAD der QS-Stichprobe: Ziehungen anlegen, Pruefergebnisse
#   erfassen, beides lesen — und die Selbstpruefungssperre durchsetzen.
#
# ── DIE SELBSTPRUEFUNGSSPERRE GEHOERT IN DEN SERVER ─────────────────────────
#
#   Entscheidung mc (C-1): "Wer einen Fall selbst bearbeitet hat, kann ihn
#   nicht pruefen. Die Sperre gehoert in den Server, nicht in die Oberflaeche —
#   dort waere sie umgehbar und im Zweifel nicht belegbar."
#
#   SIE IST HIER UND NICHT IM ENDPUNKT, aus demselben Grund: der Endpunkt ist
#   EIN Aufrufer. Ein CLI-Werkzeug, ein Import, ein spaeterer zweiter Endpunkt
#   wuerden die Pruefung sonst umgehen, ohne dass jemand es merkt. Die Regel
#   steht an genau einer Stelle: _mitwirkung().
#
#   WAS ALS 'BEARBEITET' GILT — drei Beruehrungsarten, jede fuer sich genuegt:
#     (a) cases.assigned_to zeigt auf die Person (aktuelle Zuweisung),
#     (b) sie hat mindestens ein INHALTLICHES case_events-Ereignis dieses Falls
#         erzeugt (case_events.created_by — das ist die HISTORIE, sie ueberlebt
#         eine Umzuweisung),
#     (c) sie hat mindestens eine Ergebnisbewertung dieses Falls geschrieben
#         (investigation_results.created_by).
#
#   NUR (a) ZU PRUEFEN WAERE DIE OFFENSICHTLICHE LUECKE: nach einer Umzuweisung
#   waere die frueher zustaendige Person ploetzlich pruefberechtigt fuer genau
#   den Fall, den sie selbst bearbeitet hat. (c) steht daneben, weil eine
#   Bewertung auch ohne Fallzuweisung geschrieben worden sein kann.
#
# ── WARUM 'INHALTLICH' UND NICHT 'JEDES EREIGNIS' ───────────────────────────
#
#   ERSTER ENTWURF ZAEHLTE JEDES case_events-EREIGNIS. Der Test hat gezeigt,
#   wohin das fuehrt: die Chef-Ermittlerin LEGT die Faelle an
#   (CasesRepo.create_case schreibt 'case_created' mit ihrer person_id) und
#   WEIST sie zu ('assigned'). Damit waere sie mit JEDEM Fall der Dienststelle
#   'beruehrt' und koennte KEINEN EINZIGEN pruefen — die Sperre haette das
#   Werkzeug abgeschaltet, das sie schuetzen soll.
#
#   Gezaehlt werden deshalb nur die Ereignisarten, die AUSWERTUNGSARBEIT sind:
#     'manual'          — manueller Ermittlereintrag am Fall,
#     'external_matter' — ein externer Vorgang wurde veranlasst/gefuehrt,
#     'assessment'      — eine Ergebnisbewertung wurde geschrieben.
#   NICHT gezaehlt: 'case_created', 'assigned', 'status_changed', 'approved'.
#   Das sind STEUERUNGSHANDLUNGEN der Leitung und keine Auswertung; die QS
#   prueft die Auswertung.
#
#   DAS IST EINE EINSCHRAENKUNG DER SPERRE UND DAMIT EINE ENTSCHEIDUNG.
#   Vorgelegt mit der Bitte um Widerspruch (mc): wer 'approved' mitzaehlen
#   will, macht die freigebende Person zur Nicht-Prueferin desselben Falls —
#   das ist vertretbar, fuehrt aber bei einer einzigen Supervisorin wieder in
#   dieselbe Sackgasse.
#
#   DIE SPERRE MELDET DEN GRUND. Ein blosses "nicht erlaubt" waere im Betrieb
#   nicht verwertbar; die Meldung nennt, WELCHE Beruehrung gefunden wurde,
#   damit die Supervisorin den Fall an jemand anderen geben kann.
#
# ── DIE PRUEFLINGE SIND EIN VORSCHLAG, ABWEICHUNG WIRD PROTOKOLLIERT ────────
#
#   Entscheidung mc. Ein Pruefergebnis zu einem Fall, der NICHT gezogen wurde,
#   ist deshalb ZULAESSIG — es traegt aber 'ausserhalb_der_ziehung = 1', geht
#   so in den Audit-Beleg ein und wird in der Sicht ausgewiesen. Ein
#   stillschweigend angenommenes Ergebnis ausserhalb der Ziehung waere die
#   gezielte Auswahl durch die Hintertuer.
#
# ── IM AUDIT-PROTOKOLL STEHT NIE DER WORTLAUT DER BEGRUENDUNG ───────────────
#
#   Nur Fakten: sample_id, subject_id, Ergebnis-CODE, LAENGE der Begruendung,
#   ausserhalb_der_ziehung. Die Begruendung kann Angaben zur Arbeitsweise einer
#   namentlich bekannten Person enthalten; im unveraenderlichen Protokoll hat
#   sie nichts zu suchen. Sensibilitaetsregel wie M018/M022/M002.
#
# ── DIE ZIEHUNG SCHREIBT ZWEI TABELLEN IN EINER TRANSAKTION ─────────────────
#
#   qs_sample und qs_sample_item entstehen ueber CoordinatorWriter.
#   audited_write mit after_audit: die Kopfzeile bekommt ihre audit_seq, die
#   Positionen haengen daran. Eine Ziehung ohne ihre Faelle waere ein halber
#   Beleg — sie committet vollstaendig oder gar nicht.
#
# Version: v0.8.541 · Build: 541 · 2026-07-26
# =============================================================================

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter
from management.qs.qs_sampler import Ziehung, nachziehen_stimmt, ziehe
from management.qs.qs_vokabular import (
    ERGEBNIS_CODES,
    ZWECKBINDUNG,
    ergebnis_gueltig,
    ergebnis_label,
)

logger = logging.getLogger(__name__)


class QsError(Exception):
    """Fachlicher Verstoss. Der Aufrufer macht daraus einen 400/403."""


class QsSelbstpruefungError(QsError):
    """
    Die Selbstpruefungssperre hat gegriffen.

    EIGENE Klasse, damit der Endpunkt sie von einem gewoehnlichen Eingabefehler
    unterscheiden kann: das eine ist ein 400 (falsch ausgefuellt), das andere
    ein 403 (nicht zulaessig — und zwar unabhaengig davon, wie sorgfaeltig
    ausgefuellt wurde).
    """


#: Die case_events-Arten, die als AUSWERTUNGSARBEIT gelten (s. Kopf).
#  Spiegel von management/case_events/case_events_repo.py:43 — dort stehen
#  sieben Arten; diese drei sind Auswertung, die uebrigen vier
#  ('case_created', 'assigned', 'status_changed', 'approved') sind Steuerung.
#
#  POSITIVLISTE UND KEINE NEGATIVLISTE, und das ist Absicht: eine kuenftige
#  achte Ereignisart wuerde bei einer Negativliste STILLSCHWEIGEND als
#  Auswertung gelten und die Sperre unbemerkt ausweiten. So faellt sie
#  heraus, bis jemand sie bewusst aufnimmt — und ein Test haelt beide Listen
#  gegeneinander.
MITWIRKUNGS_EVENT_KINDS: Tuple[str, ...] = (
    "manual", "external_matter", "assessment",
)

#: Die Gegenprobe: Steuerungshandlungen der Leitung. Sie stehen hier
#  AUSDRUECKLICH, damit die Aufteilung vollstaendig sichtbar ist und ein Test
#  pruefen kann, dass beide Listen zusammen das ganze Vokabular ergeben.
STEUERUNGS_EVENT_KINDS: Tuple[str, ...] = (
    "case_created", "assigned", "status_changed", "approved",
)

#: Der Fallzustand, aus dem die Grundgesamtheit gebildet wird. Geprueft wird,
#  was ABGESCHLOSSEN ist — an einem laufenden Fall waere eine Luecke kein
#  Befund, sondern ein Zwischenstand.
GRUNDGESAMTHEIT_STAENDE: Tuple[str, ...] = ("closed", "approved")


class QsRepo:
    """Ziehungen und Pruefergebnisse. Schreibt NUR ueber CoordinatorWriter."""

    def __init__(self, con: sqlite3.Connection,
                 writer: Optional[CoordinatorWriter] = None) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        # writer=None ist zulaessig fuer REIN LESENDE Nutzung (mode=ro).
        # Jeder Schreibweg prueft das ausdruecklich und scheitert laut, statt
        # still zu wirken (Muster ExternalMattersRepo).
        self._writer = writer

    # ------------------------------------------------------------------ Hilfen
    def _require_writer(self) -> CoordinatorWriter:
        if self._writer is None:
            raise QsError(
                "Schreibzugriff ohne CoordinatorWriter — kein unauditierter "
                "Schreibweg in die QS-Stichprobe.")
        return self._writer

    @staticmethod
    def _tlen(text: Optional[str]) -> int:
        return len(text or "")

    def _fall_existiert(self, subject_id: int) -> bool:
        return self._con.execute(
            "SELECT 1 FROM cases WHERE subject_id = ?",
            (int(subject_id),)).fetchone() is not None

    # ------------------------------------------------------ Grundgesamtheit
    def grundgesamtheit(self, *, staende: Sequence[str] = GRUNDGESAMTHEIT_STAENDE
                        ) -> List[Dict[str, Any]]:
        """
        Die Faelle, aus denen gezogen wird — MIT ihrer Abdeckung.

        Sie kommt aus CoverageRepo (coverage_repo.py:59) und wird hier NICHT
        nachgerechnet: die Abdeckung ist bereits ein Read-Model, und eine
        zweite Rechnung waere eine zweite Wahrheit ueber denselben Bestand.

        GEZOGEN WIRD AUS ABGESCHLOSSENEN FAELLEN. An einem laufenden Fall waere
        eine Luecke in der Bewertung kein Befund, sondern ein Zwischenstand —
        eine QS-Ruege dafuer waere sachlich falsch und im Verhaeltnis zur
        bearbeitenden Person unfair.
        """
        from management.results.coverage_repo import CoverageRepo

        marks = ",".join("?" for _ in staende)
        ids = [int(r[0]) for r in self._con.execute(
            "SELECT subject_id FROM cases WHERE status IN (%s) "
            "ORDER BY subject_id" % marks, tuple(staende)).fetchall()]
        if not ids:
            return []
        cov = CoverageRepo(self._con).coverage(subject_ids=ids)
        return list(cov.get("faelle") or [])

    # ------------------------------------------------ Selbstpruefungssperre
    def _mitwirkung(self, subject_id: int, person_id: int) -> List[str]:
        """
        Die BERUEHRUNGEN einer Person mit einem Fall — im Klartext.

        Leere Liste = keine Beruehrung = pruefberechtigt. Jeder Eintrag ist ein
        Grund, aus dem NICHT geprueft werden darf; sie werden ALLE gesammelt
        und nicht beim ersten Treffer abgebrochen, damit die Meldung
        vollstaendig ist.

        DIE HISTORIE ZAEHLT, NICHT NUR DER AKTUELLE STAND. Wer nur
        cases.assigned_to prueft, macht die frueher zustaendige Person nach
        einer Umzuweisung zur Prueferin ihrer eigenen Arbeit.
        """
        gruende: List[str] = []
        sid, pid = int(subject_id), int(person_id)

        row = self._con.execute(
            "SELECT assigned_to FROM cases WHERE subject_id = ?",
            (sid,)).fetchone()
        if row is not None and row[0] is not None and int(row[0]) == pid:
            gruende.append("Der Fall ist dieser Person aktuell zugewiesen.")

        marks = ",".join("?" for _ in MITWIRKUNGS_EVENT_KINDS)
        n_ev = self._con.execute(
            "SELECT COUNT(*) FROM case_events "
            "WHERE subject_id = ? AND created_by = ? "
            "AND event_kind IN (%s)" % marks,
            (sid, pid) + MITWIRKUNGS_EVENT_KINDS).fetchone()[0]
        if int(n_ev or 0) > 0:
            gruende.append(
                "Diese Person hat %d inhaltliche(s) Ereignis(se) dieses Falls "
                "erzeugt (Fallhistorie)." % int(n_ev))

        n_bew = self._con.execute(
            "SELECT COUNT(*) FROM investigation_results "
            "WHERE subject_id = ? AND created_by = ?", (sid, pid)).fetchone()[0]
        if int(n_bew or 0) > 0:
            gruende.append(
                "Diese Person hat %d Ergebnisbewertung(en) dieses Falls "
                "geschrieben." % int(n_bew))

        return gruende

    def darf_pruefen(self, subject_id: int, person_id: int
                     ) -> Tuple[bool, List[str]]:
        """
        -> (darf, gruende). Oeffentlich, damit die SICHT einen Fall schon vor
        dem Absenden als gesperrt kennzeichnen kann — die Sperre selbst wirkt
        aber IM SERVER und nicht in der Oberflaeche.
        """
        gruende = self._mitwirkung(subject_id, person_id)
        return (not gruende), gruende

    # ---------------------------------------------------------------- Ziehen
    def ziehen(self, *, seed: int, anteil: float = 0.1, hoechstens: int = 10,
               verfahren: str = "geschichtet", bemerkung: str = "",
               actor_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Zieht eine Stichprobe und schreibt sie auditiert. -> dict mit
        'sample_id', 'audit_seq' und der Ziehung.

        DIE ZIEHUNG WIRD HIER GERECHNET UND NICHT UEBERGEBEN. Ein Aufrufer, der
        die gezogenen subject_id selbst mitbringt, koennte die Auswahl
        bestimmen und trotzdem einen Keim mitschreiben — der Beleg waere dann
        eine Behauptung. Die Trennung ist der Punkt: qs_sampler.ziehe() ist
        rein, dieses Modul schreibt nur, was dabei herauskam.
        """
        writer = self._require_writer()
        if actor_id is None:
            raise QsError(
                "Eine Ziehung ohne handelnde Person ist kein Beleg "
                "(actor_id fehlt).")

        g = self.grundgesamtheit()
        z: Ziehung = ziehe(g, seed=int(seed), anteil=float(anteil),
                           hoechstens=int(hoechstens), verfahren=verfahren)
        now = int(time.time())
        # schicht je gezogenem Fall — fuer die Sicht und fuer den Nachweis,
        # aus WELCHER Schicht ein Fall kam.
        from management.qs.qs_sampler import schicht_von
        schicht_je_fall = {int(f["subject_id"]): schicht_von(
            f, z.abdeckung_schwelle) for f in g}
        ctx: Dict[str, Any] = {}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            cur = con.execute(
                "INSERT INTO qs_sample (gezogen_von, gezogen_at, verfahren, "
                "grundgesamtheit_n, stichprobe_n, seed, filter_json, "
                "bemerkung, audit_seq) VALUES (?,?,?,?,?,?,?,?,0)",
                (int(actor_id), now, z.verfahren, z.grundgesamtheit_n,
                 z.stichprobe_n, z.seed, z.filter_json(), bemerkung or None))
            ctx["sample_id"] = int(cur.lastrowid)
            for pos, sid in enumerate(z.subject_ids):
                con.execute(
                    "INSERT INTO qs_sample_item (sample_id, subject_id, "
                    "position, schicht) VALUES (?,?,?,?)",
                    (ctx["sample_id"], int(sid), pos,
                     schicht_je_fall.get(int(sid))))
            # DER PAYLOAD TRAEGT ALLES, WAS DIE ZIEHUNG NACHRECHENBAR MACHT.
            # Ohne den Keim im BELEG waere die Reproduzierbarkeit eine
            # Eigenschaft der Datenbank und keine des Protokolls.
            return {
                "sample_id": ctx["sample_id"], "verfahren": z.verfahren,
                "seed": z.seed, "grundgesamtheit_n": z.grundgesamtheit_n,
                "stichprobe_n": z.stichprobe_n,
                "subject_ids": list(z.subject_ids),
                "schichten": [dict(s) for s in z.schichten],
                "filter": json.loads(z.filter_json()),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE qs_sample SET audit_seq = ? WHERE id = ?",
                        (seq, ctx["sample_id"]))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.QS_SAMPLE_DRAWN,
            actor_id=actor_id, target_type="qs_sample",
            target_id=None, after_audit=_after)
        # target_id kann erst nach dem Insert bekannt sein; er steht im
        # Payload. Ihn nachtraeglich in den Audit-Eintrag zu schreiben waere
        # eine Aenderung an einer gehashten Zeile und damit ein Kettenbruch.

        out = z.to_dict()
        out.update({"sample_id": ctx["sample_id"], "audit_seq": seq,
                    "gezogen_at": now, "gezogen_von": int(actor_id),
                    "bemerkung": bemerkung or ""})
        logger.info("QS: Ziehung %d — %d von %d Faellen, Keim %d.",
                    ctx["sample_id"], z.stichprobe_n, z.grundgesamtheit_n,
                    z.seed)
        return out

    # --------------------------------------------------------------- Pruefen
    def pruefen(self, *, sample_id: int, subject_id: int, ergebnis: str,
                begruendung: str, actor_id: Optional[int] = None
                ) -> Dict[str, Any]:
        """
        Erfasst EIN Pruefergebnis. -> dict mit 'review_id' und 'audit_seq'.

        Reihenfolge der Pruefungen ist Absicht: erst die Zulaessigkeit der
        HANDLUNG (Selbstpruefung), dann die der EINGABE. Wer nicht pruefen
        darf, soll das erfahren, ohne vorher ein Formular korrekt ausfuellen zu
        muessen.
        """
        writer = self._require_writer()
        if actor_id is None:
            raise QsError(
                "Ein Pruefergebnis ohne handelnde Person ist kein Beleg "
                "(actor_id fehlt).")

        sid = int(subject_id)
        if not self._fall_existiert(sid):
            raise QsError("Fall %d existiert nicht." % sid)

        kopf = self._con.execute(
            "SELECT id FROM qs_sample WHERE id = ?", (int(sample_id),)
        ).fetchone()
        if kopf is None:
            raise QsError("Ziehung %d existiert nicht." % int(sample_id))

        # --- (1) DIE SELBSTPRUEFUNGSSPERRE, vor allem anderen --------------
        darf, gruende = self.darf_pruefen(sid, int(actor_id))
        if not darf:
            raise QsSelbstpruefungError(
                "SELBSTPRUEFUNG IST GESPERRT. Fall %d wurde von dieser Person "
                "bearbeitet: %s Die Pruefung ist an eine andere Person zu "
                "geben." % (sid, " ".join(gruende)))

        # --- (2) die Eingabe -----------------------------------------------
        if not ergebnis_gueltig(ergebnis):
            raise QsError(
                "Unbekanntes Ergebnis '%s' (gueltig: %s)."
                % (ergebnis, ", ".join(ERGEBNIS_CODES)))
        if not (begruendung or "").strip():
            raise QsError(
                "Die Begruendung ist Pflicht. Ein Pruefergebnis ohne "
                "Begruendung ist ein Daumen und kein Befund.")

        # --- (3) war der Fall ueberhaupt gezogen? --------------------------
        gezogen = self._con.execute(
            "SELECT 1 FROM qs_sample_item WHERE sample_id = ? AND "
            "subject_id = ?", (int(sample_id), sid)).fetchone() is not None
        ausserhalb = 0 if gezogen else 1

        now = int(time.time())
        ctx: Dict[str, Any] = {}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            try:
                cur = con.execute(
                    "INSERT INTO qs_review (sample_id, subject_id, "
                    "geprueft_von, geprueft_at, ergebnis, begruendung, "
                    "ausserhalb_der_ziehung, audit_seq) "
                    "VALUES (?,?,?,?,?,?,?,0)",
                    (int(sample_id), sid, int(actor_id), now, ergebnis,
                     begruendung, ausserhalb))
            except sqlite3.IntegrityError as exc:
                # Der UNIQUE-Schutz aus M034: EIN Ergebnis je Fall und Ziehung.
                raise QsError(
                    "Zu Fall %d gibt es in Ziehung %d bereits ein "
                    "Pruefergebnis. Eine zweite Meinung ist eine neue Ziehung "
                    "und kein zweiter Eintrag unter derselben Nummer (%s)."
                    % (sid, int(sample_id), exc)) from exc
            ctx["review_id"] = int(cur.lastrowid)
            # NUR FAKTEN. Der WORTLAUT der Begruendung geht NICHT ins Protokoll
            # (s. Kopf) — nur ihre Laenge, damit belegbar bleibt, dass sie
            # nicht leer war.
            return {
                "review_id": ctx["review_id"], "sample_id": int(sample_id),
                "subject_id": sid, "ergebnis": ergebnis,
                "begruendung_len": self._tlen(begruendung),
                "ausserhalb_der_ziehung": bool(ausserhalb),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE qs_review SET audit_seq = ? WHERE id = ?",
                        (seq, ctx["review_id"]))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.QS_REVIEW_RECORDED,
            actor_id=actor_id, target_type="qs_review",
            target_id=str(sid), after_audit=_after)

        return {"review_id": ctx["review_id"], "audit_seq": seq,
                "sample_id": int(sample_id), "subject_id": sid,
                "ergebnis": ergebnis, "ergebnis_label": ergebnis_label(ergebnis),
                "ausserhalb_der_ziehung": bool(ausserhalb),
                "geprueft_at": now, "geprueft_von": int(actor_id)}

    # ----------------------------------------------------------------- Lesen
    def liste(self, *, hoechstens: int = 50) -> Dict[str, Any]:
        """
        Die Ziehungen mit ihren Faellen und Ergebnissen, neueste zuerst.

        DER FORTSCHRITT WIRD AUSGEWIESEN, NICHT ERRECHNET-VERSCHWIEGEN: je
        Ziehung steht da, wie viele Prueflinge es gibt und wie viele davon
        geprueft sind. Eine Ziehung, an der niemand gearbeitet hat, sieht sonst
        aus wie eine ohne Beanstandung.
        """
        sample_rows = [dict(r) for r in self._con.execute(
            "SELECT s.*, p.system_username AS gezogen_von_name "
            "FROM qs_sample s LEFT JOIN person p ON p.id = s.gezogen_von "
            "ORDER BY s.gezogen_at DESC, s.id DESC LIMIT ?",
            (int(hoechstens),)).fetchall()]

        ziehungen: List[Dict[str, Any]] = []
        for s in sample_rows:
            sid = int(s["id"])
            items = [dict(r) for r in self._con.execute(
                "SELECT i.subject_id, i.position, i.schicht, c.username "
                "FROM qs_sample_item i "
                "LEFT JOIN cases c ON c.subject_id = i.subject_id "
                "WHERE i.sample_id = ? ORDER BY i.position", (sid,)).fetchall()]
            reviews = {int(r["subject_id"]): dict(r) for r in self._con.execute(
                "SELECT r.*, p.system_username AS geprueft_von_name "
                "FROM qs_review r LEFT JOIN person p ON p.id = r.geprueft_von "
                "WHERE r.sample_id = ?", (sid,)).fetchall()}

            for it in items:
                rv = reviews.get(int(it["subject_id"]))
                it["ergebnis"] = rv["ergebnis"] if rv else None
                it["ergebnis_label"] = (ergebnis_label(rv["ergebnis"])
                                        if rv else None)
                it["begruendung"] = rv["begruendung"] if rv else None
                it["geprueft_von_name"] = (rv["geprueft_von_name"] if rv
                                           else None)
                it["geprueft_at"] = rv["geprueft_at"] if rv else None

            # Ergebnisse zu NICHT gezogenen Faellen — die zulaessige Abweichung.
            gezogene = {int(i["subject_id"]) for i in items}
            ausserhalb = [dict(r) for sidx, r in reviews.items()
                          if sidx not in gezogene]

            zaehler: Dict[str, int] = {}
            for r in reviews.values():
                zaehler[r["ergebnis"]] = zaehler.get(r["ergebnis"], 0) + 1

            try:
                filt = json.loads(s.get("filter_json") or "{}")
            except (TypeError, ValueError):
                filt = {}

            s.update({
                "faelle": items,
                "ausserhalb_der_ziehung": ausserhalb,
                "geprueft_n": len(reviews),
                "offen_n": max(0, len(items) - len(
                    [i for i in items if i["ergebnis"]])),
                "zaehler": zaehler,
                "filter": filt,
            })
            ziehungen.append(s)

        return {
            "ziehungen": ziehungen,
            "ziehungen_gesamt": int(self._con.execute(
                "SELECT COUNT(*) FROM qs_sample").fetchone()[0]),
            "ergebnis_codes": list(ERGEBNIS_CODES),
            "zweckbindung": ZWECKBINDUNG,
            "ist_kein_bewertungsinstrument": True,
            "prueflinge_sind_vorschlag": True,
        }

    # ------------------------------------------------------------ Nachziehen
    def nachziehen(self, sample_id: int) -> Dict[str, Any]:
        """
        Rechnet eine GESPEICHERTE Ziehung nach. REIN LESEND.

        Das ist der eigentliche Zweck des mitgeschriebenen Keims: gegen den
        Vorwurf der gezielten Auswahl hilft nur, dass es jemand nachrechnen
        KANN. Eine Abweichung wird BENANNT und nicht als Fehler behandelt — die
        Grundgesamtheit aendert sich im laufenden Betrieb, und dann ist 'stimmt
        nicht mehr' die richtige und nicht die alarmierende Antwort.
        """
        row = self._con.execute(
            "SELECT * FROM qs_sample WHERE id = ?", (int(sample_id),)
        ).fetchone()
        if row is None:
            raise QsError("Ziehung %d existiert nicht." % int(sample_id))
        s = dict(row)
        ids = tuple(int(r[0]) for r in self._con.execute(
            "SELECT subject_id FROM qs_sample_item WHERE sample_id = ? "
            "ORDER BY position", (int(sample_id),)).fetchall())

        try:
            filt = json.loads(s.get("filter_json") or "{}")
        except (TypeError, ValueError) as exc:
            raise QsError(
                "Die Ziehungsparameter (filter_json) der Ziehung %d sind "
                "nicht lesbar: %s. Ohne sie laesst sich nicht nachrechnen."
                % (int(sample_id), exc)) from exc

        gespeichert = Ziehung(
            verfahren=s["verfahren"], seed=int(s["seed"]),
            grundgesamtheit_n=int(s["grundgesamtheit_n"]),
            stichprobe_n=int(s["stichprobe_n"]),
            anteil=float(filt.get("anteil", 0.1)),
            hoechstens=int(filt.get("hoechstens", 10)),
            abdeckung_schwelle=float(filt.get("abdeckung_schwelle", 0.5)),
            subject_ids=ids)

        stimmt, abweichungen = nachziehen_stimmt(
            gespeichert, self.grundgesamtheit())
        return {
            "sample_id": int(sample_id), "stimmt": stimmt,
            "abweichungen": abweichungen,
            "seed": int(s["seed"]),
            "verfahren": s["verfahren"],
            "damals_n": int(s["grundgesamtheit_n"]),
            "damals_subject_ids": list(ids),
            "hinweis": (
                "Die Ziehung ist nachgerechnet worden und stimmt."
                if stimmt else
                "Die Ziehung laesst sich mit dem heutigen Bestand NICHT "
                "nachrechnen. Das ist nicht ohne Weiteres ein Verstoss: die "
                "Grundgesamtheit aendert sich im laufenden Betrieb. "
                "Massgeblich ist, ob die Abweichung erklaerbar ist."),
            "zweckbindung": ZWECKBINDUNG,
        }
