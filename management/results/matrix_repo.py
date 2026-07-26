# =============================================================================
# management/results/matrix_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3B (Build 537)
# =============================================================================
# Zweck:
#   Der SAMMLER der Dringlichkeits-/Erkenntnislage-Matrix. Er holt die
#   Tatsachen aus den bestehenden Read-Models, fuegt sie je Fall zusammen und
#   uebergibt sie dem reinen Rechenkern (urgency_matrix.py).
#
# ── DIESES MODUL RECHNET NICHT UND LIEST KEINE EIGENEN TABELLEN ──────────────
#
#   Es gibt in diesem Werkzeug bereits sechs Fall-Aggregate. Ein siebtes mit
#   eigenen SQL-Abfragen waere eine siebte Wahrheit ueber denselben Bestand —
#   und die erste, die auseinanderlaeuft. Der Sammler benutzt deshalb
#   ausschliesslich vorhandene Repositories:
#
#     DashboardRepo.list_case_overview()   1 Abfrage  -> X-3, X-4, X-5
#     ExternalMattersRepo.list_matters()   1 Abfrage  -> X-2
#     v_investigation_current (roh)        1 Abfrage  -> Y-1, Y-2
#     AssessmentCatalogRepo.criteria()     1 Abfrage  -> Bezugsgroesse fuer Y-1
#     IdentifiedSubjectRepo.list()         1 Abfrage  -> Y-3
#
#   Y-1/Y-2 gehen ROH und nicht ueber CoverageRepo.coverage() — die Begruendung
#   steht im naechsten Absatz. Die SICHT 'v_investigation_current' ist dabei
#   dieselbe, auf der auch CoverageRepo arbeitet (coverage_repo.py:169); es
#   entsteht also keine zweite Wahrheit, nur eine andere Verdichtung.
#
#   Verbindungspunkt ist durchgaengig 'subject_id' (seit M019 einheitlich).
#
#   X-1 (die Verjaehrungsfrist) ist BEWUSST NICHT DABEI. Sie kostet zwei
#   Dateizugriffe JE FALL und kommt erst mit Build 538 dazu. Bis dahin ist die
#   Dringlichkeit jeder Zeile ausdruecklich NICHT BESTIMMBAR (Grund
#   'nicht_geladen') und der ausgewiesene Wert eine UNTERGRENZE. Das ist der
#   Unterschied zwischen 'noch nicht geholt' und 'nicht vorhanden', und er
#   steht in jeder Zeile.
#
# ── WARUM DIE BEWERTUNGEN ROH DURCHGEREICHT WERDEN ───────────────────────────
#
#   CoverageRepo rechnet die Abdeckung ueber ALLE zehn Kriterien. Die Matrix
#   braucht sie ueber NEUN — ohne 'identification', das ueber die
#   Identitaetstabelle eigens zaehlt (Entscheidung mc M-3). Statt CoverageRepo
#   umzubauen (es bedient /api/results/coverage, wo die Frage eine andere ist)
#   reicht der Sammler die ROHEN Bewertungszeilen durch und laesst den
#   Rechenkern ausschliessen. Damit gibt es weiterhin genau eine Stelle, an der
#   die Ausschlussregel steht.
#
# ── REIN LESEND ──────────────────────────────────────────────────────────────
#
#   coordinator.db wird vom Aufrufer mit mode=ro geoeffnet. Kein
#   CoordinatorWriter, kein Schreibpfad; der Migrationsvorbehalt ist nicht
#   beruehrt. Die Matrix schreibt insbesondere NICHT in cases.priority
#   (Entscheidung mc) — sie ist ein Vorschlag, den ein Mensch sieht.
#
# Version: v0.8.537 · Build: 537 · 2026-07-26
# =============================================================================

from __future__ import annotations

import dataclasses
import logging
import sqlite3
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from management.cases.escalation import (
    EscalationThresholds,
    evaluate_escalations,
)
from management.crossref.identified_subject_repo import IdentifiedSubjectRepo
from management.dashboard.dashboard_repo import DashboardRepo
from management.external.external_matters_repo import ExternalMattersRepo
from management.results.assessment_catalog_repo import AssessmentCatalogRepo
from management.results.matrix_weights import MatrixGewichte
from management.results.urgency_matrix import MatrixZelle, UrgencyMatrix

logger = logging.getLogger(__name__)

#: Die Vorgangsstaende, die noch auf eine Antwort warten. 'erledigt' und
#: 'erfolglos' sind Endzustaende und koennen nicht ueberfaellig sein
#: (matter_status.py:181-182).
OFFENE_VORGANGSSTAENDE: tuple = ("offen", "beantwortet")

#: Die Ampelfarbe eines externen Vorgangs, die 'ueberfaellig' bedeutet.
#: 'gelb' ist die VORWARNUNG und zaehlt ausdruecklich NICHT — sonst waere die
#: Vorwarnfrist eine zweite Faelligkeit.
AMPEL_UEBERFAELLIG: str = "rot"


class MatrixRepo:
    """Sammelt die Tatsachen je Fall und laesst den Rechenkern rechnen."""

    def __init__(self, con: sqlite3.Connection,
                 gewichte: MatrixGewichte,
                 forensic_dir: Optional[str] = None,
                 evidence_dir: Optional[str] = None,
                 params_pfad: Optional[Any] = None) -> None:
        """
        forensic_dir/evidence_dir sind fuer die FRISTKOMPONENTE (X-1) noetig.

        BEIDE SIND OPTIONAL, UND DAS FEHLEN IST KEIN FEHLER, SONDERN EIN
        BEFUND. Ein Aufrufer ohne Verzeichnisse bekommt eine Matrix ohne
        Fristbeitraege — mit 'fristen_geladen': false und einem benannten
        Grund in 'fehlende_quellen'. Ein stillschweigend weggelassener
        Fristbeitrag saehe aus wie 'keine Frist' und damit wie 'nicht eilig'
        (Build 537, Punkt 3).

        params_pfad uebersteuert den Verjaehrungs-Parametersatz. Der Betrieb
        laesst ihn WEG (dann gilt management/deadlines/limitation_params.json);
        er existiert, weil der ausgelieferte Satz absichtlich UNBESTAETIGT ist
        und ein bestaetigter Satz im Repository eine Rechtsauskunft waere, die
        niemand gegeben hat (Muster: tests/test_management_limitation_api.py,
        _params_bestaetigt()).
        """
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._g = gewichte
        self._matrix = UrgencyMatrix(gewichte)
        self._forensic_dir = forensic_dir
        self._evidence_dir = evidence_dir
        self._params_pfad = params_pfad

    # ------------------------------------------------------------------ Sammeln
    def _tage(self, ov: Dict[str, Any], now: int) -> Optional[int]:
        """
        Liegezeit in Tagen. Massgeblich ist 'last_activity_at' —
        max(cases.updated_at, MAX(case_events.created_at)),
        dashboard_repo.py:348. Nur das letzte EREIGNIS zu nehmen waere falsch:
        ein Fall ohne jedes Ereignis haette dann gar keine Liegezeit.
        """
        la = ov.get("last_activity_at")
        if la is None:
            return None
        return max(0, (now - int(la)) // 86400)

    def _ueberfaellige_vorgaenge(self, stichtag: str) -> Dict[int, int]:
        """
        subject_id -> Zahl der UEBERFAELLIGEN externen Vorgaenge.

        'Ueberfaellig' ist nicht gespeichert, sondern eine Funktion des
        Stichtags (matter_status.py:194-199). Gefragt wird deshalb der fertige
        Ampelwert und nicht das Datum — sonst entstuende hier eine zweite
        Faelligkeitsregel. Der Sonderfall 'verwaist' (Fall abgeschlossen,
        Vorgang offen) ist damit automatisch mit erfasst: er ist IMMER rot,
        unabhaengig vom Datum.
        """
        repo = ExternalMattersRepo(self._con)
        try:
            rows = repo.list_matters(statuses=list(OFFENE_VORGANGSSTAENDE))
        except sqlite3.Error as exc:
            # M010 nicht angewandt o. Ae. Der Beitrag entfaellt, aber der
            # Aufrufer erfaehrt es (s. compute -> 'fehlende_quellen').
            logger.warning("Matrix: externe Vorgaenge nicht lesbar: %s", exc)
            raise
        out: Dict[int, int] = {}
        for r in repo.with_ampel(rows, stichtag):
            if r.get("ampel") == AMPEL_UEBERFAELLIG:
                sid = int(r["subject_id"])
                out[sid] = out.get(sid, 0) + 1
        return out

    def _eskalationen(self, overviews: List[Dict[str, Any]],
                      now: int) -> Dict[int, int]:
        """
        subject_id -> Zahl der aktiven Eskalationsmeldungen.

        Es wird die REINE Regelauswertung benutzt (escalation.py:71) und NICHT
        EscalationRepo.compute() — Letzteres wuerde die Fallübersicht ein
        zweites Mal aus der Datenbank holen (escalation_repo.py:37-38), die
        hier bereits vorliegt.

        QUITTIERTE MELDUNGEN ZAEHLEN MIT. m027_escalation_ack.py:15-22
        woertlich: 'Sie ist KEIN Erledigen. Die Eskalation VERSCHWINDET NICHT
        aus der Liste.' Der Vermerk wird deshalb hier gar nicht erst gelesen.

        Systemische Meldungen (subject_id=None, etwa 'rueckstau_hoch') gehoeren
        zu KEINEM Fall und werden uebersprungen — sie einem Fall zuzurechnen
        waere eine Erfindung.
        """
        bericht = evaluate_escalations(
            overviews, EscalationThresholds(), now)
        out: Dict[int, int] = {}
        for item in bericht.items:
            if item.subject_id is None:
                continue
            sid = int(item.subject_id)
            out[sid] = out.get(sid, 0) + 1
        return out

    def _bewertungen(self, subject_ids: Sequence[int]
                     ) -> Dict[int, List[Dict[str, Any]]]:
        """
        subject_id -> die aktuellen Bewertungszeilen (roh).

        ROH, nicht verdichtet: die Matrix schliesst 'identification' aus
        (Entscheidung M-3), CoverageRepo tut das nicht — und soll es auch
        nicht, weil /api/results/coverage eine andere Frage beantwortet. Die
        Ausschlussregel steht deshalb an genau EINER Stelle, im Rechenkern.
        """
        if not subject_ids:
            return {}
        marks = ",".join("?" for _ in subject_ids)
        rows = self._con.execute(
            "SELECT subject_id, criterion_code, extrem, confidence_code, "
            "       confidence_ordinal "
            "FROM v_investigation_current WHERE subject_id IN (%s)" % marks,
            [int(s) for s in subject_ids]).fetchall()
        out: Dict[int, List[Dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(int(r["subject_id"]), []).append(dict(r))
        return out

    # ---------------------------------------------------------- Fristen (X-1)
    def _fristen(self, ids: Sequence[int], now: int
                 ) -> Tuple[Dict[int, Dict[str, Any]], Dict[str, Any]]:
        """
        subject_id -> LimitationRow.to_dict(), plus die Kopfangaben des
        Fristenmonitors.

        DIE MATRIX RECHNET DIE FRIST NICHT SELBST NACH. Sie ruft
        LimitationRepo.compute() — dieselbe Rechnung, die /api/limitation
        ausliefert. Zwei Fristrechnungen ueber denselben Bestand waeren zwei
        Wahrheiten, und die Verjaehrung ist der letzte Ort, an dem man sich
        das leisten koennte.

        DER TEURE TEIL DER MATRIX STECKT HIER: LimitationRepo oeffnet JE FALL
        bis zu zwei Dateien (forensic_<uid>.db fuer die Aktivitaetsdaten,
        evidence_<uid>.db fuer die festgestellte Tatzeit) — alle uebrigen
        Beitraege zusammen kosten fuenf Abfragen auf EINER Verbindung. Deshalb
        ist dieser Teil abschaltbar, und deshalb wird seine Dauer gemessen und
        ausgewiesen.

        DER PARAMETERSATZ WIRD HIER GELADEN UND NICHT DURCHGEREICHT, damit ein
        Aufrufer ihn nicht versehentlich weglassen kann. Ist er UNBRAUCHBAR,
        wirft diese Methode — der Aufrufer entscheidet dann (compute faengt es
        und BENENNT es). Ist er nur NICHT BESTAETIGT, ist das kein Fehler:
        der Monitor liefert dann Zeilen mit Ampel 'keine_aussage', und genau
        das ist die richtige Antwort. Sie faellt im Rechenkern ins fuenfte Feld
        (AMPEL_MIT_FRIST ist eine Positivliste) — mit dem Grund
        'keine_aussage' und NICHT 'nicht_geladen'. Der Unterschied ist der
        zwischen "nicht nachgesehen" und "nachgesehen, keine Aussage moeglich".
        """
        # Spaeter Import: der Fristenmonitor zieht limitation_params nach, und
        # matrix_repo soll ohne Fristverzeichnisse importierbar bleiben.
        from management.deadlines.limitation_params import load_params
        from management.deadlines.limitation_repo import LimitationRepo

        params = (load_params(self._params_pfad) if self._params_pfad
                  else load_params())
        repo = LimitationRepo(self._con, self._forensic_dir,
                              self._evidence_dir)
        bericht = repo.compute(params=params, now_ts=now,
                               subject_ids=list(ids))

        zeilen: Dict[int, Dict[str, Any]] = {}
        for row in bericht.rows:
            zeilen[int(row.tatzeit.subject_id)] = row.to_dict()

        kopf = {
            "aussage_moeglich": bericht.aussage_moeglich,
            "verweigerungsgrund": bericht.verweigerungsgrund,
            "params_stand": bericht.params_stand,
            "params_bestaetigt": bericht.params_bestaetigt,
            "vorwarn_tage": bericht.vorwarn_tage,
            "vorbehalte": list(bericht.vorbehalte),
            "zaehler": dict(bericht.zaehler),
            "faelle_mit_quellenfehler": bericht.faelle_mit_quellenfehler,
            "faelle_mehrdeutig": bericht.faelle_mehrdeutig,
        }
        return zeilen, kopf

    # ------------------------------------------------------------------ Rechnen
    def compute(self, *, now_ts: Optional[int] = None,
                subject_ids: Optional[Sequence[int]] = None,
                mit_fristen: bool = True
                ) -> Dict[str, Any]:
        """
        Die Matrix ueber alle (oder die genannten) Faelle.

        subject_ids=None -> alle. subject_ids=[] -> KEINE. Eine leere Auswahl
        ist eine Auswahl und bedeutet ausdruecklich nicht 'alle' (Muster
        coverage_repo.py:64-67, limitation_repo.py:677-680).

        mit_fristen=False laesst X-1 WEG. Der Aufrufer bekommt dann exakt das
        Verhalten aus Build 537: jede Zelle traegt dringlichkeit_bestimmbar
        false mit dem Grund 'nicht_geladen', 'fristen_geladen' ist false, und
        der Wert in 'dringlichkeit_mindestens' ist eine UNTERGRENZE. Das ist
        die schnelle Sicht fuer den Ueberblick — sie luegt nicht, sie sagt
        weniger, und sie sagt WELCHES weniger.
        """
        now = int(time.time()) if now_ts is None else int(now_ts)
        stichtag = datetime.fromtimestamp(now, tz=timezone.utc).date().isoformat()
        fehlende_quellen: List[str] = []
        t_start = time.monotonic()

        # --- (1) Fallübersicht: eine Aggregatabfrage ------------------------
        overviews = [dataclasses.asdict(o)
                     for o in DashboardRepo(self._con).list_case_overview(now=now)]
        if subject_ids is not None:
            erlaubt = {int(s) for s in subject_ids}
            overviews = [o for o in overviews
                         if int(o["subject_id"]) in erlaubt]

        ids = [int(o["subject_id"]) for o in overviews]

        # --- (2) die drei uebrigen Quellen ---------------------------------
        #     Faellt eine aus, wird der Fall NICHT weggelassen — der Beitrag
        #     entfaellt, und die Quelle wird BENANNT. Ein stillschweigend
        #     fehlender Beitrag saehe aus wie 'trifft nicht zu'.
        try:
            vorgaenge = self._ueberfaellige_vorgaenge(stichtag)
        except sqlite3.Error as exc:
            vorgaenge = {}
            fehlende_quellen.append("externe Vorgaenge (%s)" % exc)

        try:
            eskalationen = self._eskalationen(overviews, now)
        except Exception as exc:                        # noqa: BLE001
            eskalationen = {}
            fehlende_quellen.append("Eskalationen (%s)" % exc)

        try:
            bewertungen = self._bewertungen(ids)
        except sqlite3.Error as exc:
            bewertungen = {}
            fehlende_quellen.append("Ergebnisbewertungen (%s)" % exc)

        try:
            alle_kriterien = [c["code"]
                              for c in AssessmentCatalogRepo(self._con).criteria()]
        except Exception as exc:                        # noqa: BLE001
            alle_kriterien = []
            fehlende_quellen.append("Bewertungskatalog (%s)" % exc)

        try:
            identitaeten = {int(d["subject_id"]): d.get("confidence_code")
                            for d in IdentifiedSubjectRepo(self._con).list()}
        except Exception as exc:                        # noqa: BLE001
            identitaeten = {}
            fehlende_quellen.append("Identitaetszuordnungen (%s)" % exc)

        # --- (2b) die Fristkomponente X-1 (Build 538) ----------------------
        #     Der teuerste Teil: bis zu zwei Dateizugriffe JE FALL. Er ist
        #     abschaltbar, er wird gemessen, und sein Ausbleiben wird in JEDER
        #     Zeile ausgewiesen — nie stillschweigend als 'keine Frist'.
        fristen: Dict[int, Dict[str, Any]] = {}
        fristen_kopf: Optional[Dict[str, Any]] = None
        fristen_geladen = False
        dauer_fristen_ms: Optional[int] = None

        if not mit_fristen:
            fehlende_quellen.append(
                "Fristen (nicht angefordert: mit_fristen=False)")
        elif not self._forensic_dir:
            fehlende_quellen.append(
                "Fristen (kein forensic-Verzeichnis uebergeben — es wurde "
                "NICHT nachgesehen)")
        else:
            t_frist = time.monotonic()
            try:
                fristen, fristen_kopf = self._fristen(ids, now)
                fristen_geladen = True
            except Exception as exc:                    # noqa: BLE001
                # Auch der unbrauchbare Parametersatz landet hier. Er ist ein
                # Grund, die FRIST wegzulassen — kein Grund, die ganze Matrix
                # zu verweigern: die uebrigen fuenf Beitraege sind davon
                # unberuehrt. Was fehlt, steht in 'fehlende_quellen'.
                logger.exception("Matrix: Fristkomponente nicht ladbar")
                fehlende_quellen.append("Fristen (%s)" % exc)
            finally:
                dauer_fristen_ms = int((time.monotonic() - t_frist) * 1000)

        # --- (3) je Fall zusammenfuegen und rechnen ------------------------
        faelle = []
        for ov in overviews:
            sid = int(ov["subject_id"])
            faelle.append({
                "subject_id": sid,
                "username": ov.get("username") or "?",
                # Build 538: der Fristbericht. Fehlt die Zeile zu EINEM Fall,
                # bleibt sie None — dieser eine Fall traegt dann 'nicht_
                # geladen', die uebrigen ihre echte Frist. Ein Vorgabewert
                # waere hier eine erfundene Frist.
                "limitation": fristen.get(sid),
                "wiedervorlage_ueberfaellig": vorgaenge.get(sid, 0) > 0,
                "eskalationen": eskalationen.get(sid, 0),
                "tage_ohne_ereignis": self._tage(ov, now),
                "unzugewiesen": ov.get("assigned_to") is None,
                "alle_kriterien": alle_kriterien,
                "bewertungen": bewertungen.get(sid, []),
                "identitaet_konfidenz": identitaeten.get(sid),
            })

        zellen: List[MatrixZelle] = self._matrix.bewerte_alle(faelle)

        quadranten: Dict[str, int] = {}
        belastbarkeit: Dict[str, int] = {}
        unbekannte: Dict[str, int] = {}
        for z in zellen:
            quadranten[z.quadrant] = quadranten.get(z.quadrant, 0) + 1
            belastbarkeit[z.dringlichkeit_belastbarkeit] = (
                belastbarkeit.get(z.dringlichkeit_belastbarkeit, 0) + 1)
            for c in z.unbekannte_codes:
                unbekannte[c] = unbekannte.get(c, 0) + 1

        # Build 538: fehlt einem EINZELNEN Fall die Fristzeile, obwohl die
        # Fristen geladen wurden, ist das ein Widerspruch (der Monitor liefert
        # zu jedem Fall aus 'cases' eine Zeile). Er wird gezaehlt und benannt,
        # nicht geglaettet.
        ohne_fristzeile = 0
        if fristen_geladen:
            ohne_fristzeile = sum(1 for i in ids if i not in fristen)

        hinweise = self._hinweise(
            zellen, fehlende_quellen, unbekannte,
            fristen_geladen=fristen_geladen, fristen_kopf=fristen_kopf,
            ohne_fristzeile=ohne_fristzeile)

        out: Dict[str, Any] = {
            "stichtag": stichtag,
            "faelle_gesamt": len(zellen),
            "fristen_geladen": fristen_geladen,
            "fristen_angefordert": bool(mit_fristen),
            "fristen_kopf": fristen_kopf,
            "faelle_ohne_fristzeile": ohne_fristzeile,
            "quadranten": quadranten,
            "belastbarkeit_verteilung": belastbarkeit,
            "unbekannte_codes": unbekannte,
            "fehlende_quellen": fehlende_quellen,
            "hinweise": hinweise,
            "zellen": [z.to_dict() for z in zellen],
            # LAUFZEIT: sie faehrt MIT, statt nur im Protokoll zu stehen.
            # Die Fristkomponente ist der einzige Teil, der mit der Zahl der
            # Faelle in DATEIZUGRIFFEN waechst; wer sie abschaltet, will
            # nachlesen koennen, was das gebracht hat.
            "dauer_gesamt_ms": int((time.monotonic() - t_start) * 1000),
            "dauer_fristen_ms": dauer_fristen_ms,
        }
        out.update(self._g.to_dict())
        return out

    # ------------------------------------------------------------------ Hinweise
    @staticmethod
    def _hinweise(zellen: Sequence[MatrixZelle],
                  fehlende_quellen: Sequence[str],
                  unbekannte: Dict[str, int],
                  *,
                  fristen_geladen: bool = False,
                  fristen_kopf: Optional[Dict[str, Any]] = None,
                  ohne_fristzeile: int = 0) -> List[str]:
        """
        Die Hinweise der Antwort. Reihenfolge: das Dringendste zuletzt
        eingefuegt, weil insert(0) nach vorn schiebt.
        """
        n = len(zellen)
        hinweise: List[str] = []

        if not fristen_geladen:
            hinweise.append(
                "Die Fristbeitraege sind in diesem Stand NICHT geladen. Jede "
                "Zeile traegt deshalb 'dringlichkeit_bestimmbar': false mit "
                "dem Grund 'nicht_geladen', und der Wert in "
                "'dringlichkeit_mindestens' ist eine UNTERGRENZE — kein Fall "
                "ist so wenig dringlich, wie er hier aussieht.")
        else:
            hinweise.append(
                "Die Fristbeitraege stammen aus DERSELBEN Rechnung wie "
                "/api/limitation (LimitationRepo.compute) — die Matrix rechnet "
                "die Verjaehrung nicht eigenstaendig nach. DIESE SICHT STELLT "
                "KEINE VERJAEHRUNG FEST: § 78c StGB (Unterbrechung) ist dem "
                "Werkzeug nicht bekannt, ein 'ueberschritten' heisst "
                "rechnerisch ueberschritten und verlangt juristische Pruefung.")
            kopf = fristen_kopf or {}
            if not kopf.get("aussage_moeglich", True):
                # DER WICHTIGSTE FALL IM AUSLIEFERUNGSZUSTAND: der
                # Parametersatz ist ein Entwurf (limitation_params.json:
                # 'bestaetigt': false). Der Monitor verweigert dann JEDE
                # Fristaussage, und die Matrix darf das nicht wie 'keine
                # Frist' aussehen lassen.
                hinweise.insert(0,
                    "DIE FRISTEN WURDEN GELADEN, ABER DER FRISTENMONITOR "
                    "VERWEIGERT JEDE AUSSAGE: %s. Alle Zeilen stehen deshalb "
                    "mit dem Grund 'keine_aussage' im fuenften Feld — das ist "
                    "NICHT 'nicht_geladen' und erst recht nicht 'keine "
                    "Frist'. Die Dringlichkeit dieser Matrix beruht bis zur "
                    "Bestaetigung des Parametersatzes allein auf den fuenf "
                    "uebrigen Beitraegen."
                    % (kopf.get("verweigerungsgrund")
                       or "kein Grund angegeben"))
            if ohne_fristzeile:
                hinweise.insert(0,
                    "WIDERSPRUCH: zu %d von %d Faellen kam KEINE Fristzeile "
                    "zurueck, obwohl die Fristen geladen wurden. Diese Faelle "
                    "tragen 'nicht_geladen' und sind damit erkennbar — "
                    "trotzdem gehoert die Ursache geklaert."
                    % (ohne_fristzeile, n))

        unbestimmbar = sum(1 for z in zellen
                           if z.quadrant == "nicht_bestimmbar")
        if unbestimmbar:
            hinweise.insert(0,
                "%d von %d Faellen stehen im Feld 'nicht bestimmbar'. Sie sind "
                "damit UNGEPRUEFT und nicht unverdaechtig — deshalb stehen sie "
                "in der Liste OBEN und nicht am Ende."
                % (unbestimmbar, n))

        if unbekannte:
            hinweise.insert(0,
                "Es kommen Konfidenz-Codes vor, die der Gewichtungssatz nicht "
                "kennt: %s. Die betroffenen Faelle werden NICHT mit 0 "
                "gerechnet, sondern als nicht bestimmbar gefuehrt. Vermutlich "
                "wurde der Bewertungskatalog erweitert und "
                "management/results/matrix_weights.json nicht nachgezogen — "
                "das ist eine fachliche Entscheidung, keine Codeanpassung."
                % ", ".join("%s (%dx)" % (k, v)
                            for k, v in sorted(unbekannte.items())))

        if fehlende_quellen:
            hinweise.insert(0,
                "MINDESTENS EINE QUELLE WAR NICHT LESBAR: %s. Die betroffenen "
                "Beitraege fehlen in JEDER Zeile — ein Fall kann deshalb "
                "harmloser aussehen, als er ist."
                % "; ".join(fehlende_quellen))

        return hinweise
