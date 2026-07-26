# =============================================================================
# management/results/urgency_matrix.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3B (Build 536)
# =============================================================================
# Zweck:
#   Die REINE Berechnung der Dringlichkeits-/Erkenntnislage-Matrix je Fall.
#   Aus einem Satz Tatsachen (dict) und dem Gewichtungssatz entsteht eine
#   Zelle mit zwei Achsenwerten, einem Quadranten und der vollstaendigen
#   Aufstellung ihrer Beitraege.
#
#   KEINE Datei, KEINE Datenbank, KEINE Uhr. Alle Eingaben werden INJIZIERT —
#   dasselbe Muster wie management/cases/escalation.py:71 und
#   management/cases/next_actions.py:57, die beide dicts nehmen und nichts
#   lesen. Damit ist jede Aussage dieses Moduls ohne Vorrichtung nachrechenbar.
#
# ── WAS DIESES MODUL AUSDRUECKLICH NICHT SAGT (§ 261 StPO) ───────────────────
#
#   Es erzeugt KEINE Aussage ueber Tatschwere oder Belastungsgrad. Beide Achsen
#   sind verfahrensbezogen: 'Dringlichkeit' sagt, wie eilig die BEARBEITUNG
#   ist, 'Erkenntnislage' sagt, wie weit die ERMITTLUNG ist — nicht, wie schwer
#   die Tat wiegt. Eine 'Schwere'-Achse ist ausdruecklich abgelehnt
#   (Entscheidung mc 2026-07-26). Die Zweckbindung faehrt in jeder Antwort mit
#   und wird nicht hier formuliert, sondern aus dem Gewichtungssatz uebernommen
#   — eine zweite Formulierung waere eine zweite Wahrheitsquelle.
#
# ── DIE DREI FESTLEGUNGEN, DIE DAS INNENLEBEN BESTIMMEN ──────────────────────
#
# (M-1) DIE BELASTBARKEIT WIRD NICHT EINGERECHNET, SONDERN AUSGEWIESEN.
#   Die Fristpunkte werden ungekuerzt vergeben, gleich ob die Frist auf einer
#   FESTGESTELLTEN Tatzeit, auf Aktivitaetsdaten oder auf einem Ersatzanker
#   beruht. Daneben steht 'dringlichkeit_belastbarkeit'. Begruendung: eine
#   vorlaeufige Frist ist nicht WENIGER dringlich, sie ist gleich dringlich und
#   schlechter belegt. Beides in eine Zahl zu pressen hiesse, Beleglage in
#   Dringlichkeit umzurechnen — eine Umrechnung, die niemand beschlossen hat.
#
#   FAELLE OHNE BESTIMMBARE FRIST BEKOMMEN KEINE 0. Sie landen im FUENFTEN
#   Feld 'nicht_bestimmbar'. Eine 0 saehe aus wie eine Aussage ('niedrige
#   Dringlichkeit'), waere aber eine Nichtaussage — und der Fall saenke ans
#   Listenende, obwohl er UNGEPRUEFT ist und nicht unverdaechtig.
#
#   IHRE UEBRIGEN PUNKTE GEHEN TROTZDEM NICHT VERLOREN: sie stehen in
#   'dringlichkeit_mindestens'. Ein Fall mit 40 Punkten aus Wiedervorlage,
#   Eskalation und Liegezeit UND unbestimmter Frist ist erkennbar dringend.
#
# (M-2) DIE KONFIDENZTABELLE IST FEST — UND EIN UNBEKANNTER CODE ERGIBT NIE 0.
#   Die Skala hat sechs Stufen und ist im Betrieb aenderbar (catalog_admin).
#   Faellt ein Code aus der Tabelle, wird er BENANNT: der Fall traegt
#   erkenntnislage_bestimmbar=False und den Code in 'unbekannte_codes'. Ohne
#   diese Regel saenke ein Fall nach einer Katalogerweiterung stillschweigend
#   ab, und niemand wuesste warum.
#
# (M-3) 'identification' WIRD AUS DER Y-ACHSE HERAUSGENOMMEN.
#   Sonst ginge dieselbe Erkenntnis zweimal ein — einmal als Bewertungs-
#   kriterium, einmal ueber identified_subject. Die Abdeckung rechnet deshalb
#   ueber NEUN statt zehn Kriterien; die Zahl der gerechneten Kriterien steht
#   in der Antwort, damit sich niemand ueber die Prozentzahl wundert.
#
# Version: v0.8.536 · Build: 536 · 2026-07-26
# =============================================================================

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from management.results.matrix_weights import MatrixGewichte

logger = logging.getLogger(__name__)

#: Die Ampelzustaende, bei denen eine RESTLAUFZEIT vorliegt und die Frist
#  deshalb in die Dringlichkeit eingeht. Alle uebrigen fuehren ins fuenfte
#  Feld.
#
#  BEWUSST ALS POSITIVLISTE. Eine Negativliste ('alles ausser ohne_tatzeit und
#  ohne_anker') wuerde einen kuenftigen neunten Ampelzustand stillschweigend
#  als rechenbar behandeln — und die Ampel ist schon einmal von fuenf auf acht
#  Zustaende gewachsen (Build 530).
#
#  ZU DEN DREI ZUSTAENDEN, DIE mc NICHT AUSDRUECKLICH GENANNT HAT:
#    'ruht'          — es GIBT einen Tatzeitpunkt, aber keine Restlaufzeit: die
#                      Frist ruht moeglicherweise nach § 78b Abs. 1 Nr. 1 StGB,
#                      und ob sie das tut, haengt am Opferalter, das nicht in
#                      den Daten steht (limitation.py:114-118). 0 Fristpunkte
#                      hiessen 'nicht eilig' — das ist eine Behauptung ueber
#                      etwas Unbekanntes.
#    'ohne_fassung'  — fuer den Tatzeitpunkt ist keine Fassung hinterlegt
#                      (§ 2 Abs. 1 StGB). Es wird ausdruecklich NICHT mit einer
#                      anderen gerechnet.
#    'keine_aussage' — der Parametersatz ist nicht bestaetigt; dann ist der
#                      Fristenmonitor insgesamt stumm.
#  Alle drei sind Nichtaussagen und gehoeren aus demselben Grund ins fuenfte
#  Feld wie 'ohne_tatzeit' und 'ohne_anker'. Diese Ausweitung ist eine
#  Ableitung aus M-1, keine eigene Entscheidung — sie steht hier, damit mc
#  widersprechen kann.
AMPEL_MIT_FRIST: Tuple[str, ...] = ("ueberschritten", "knapp", "offen")

#: Die Quadranten. 'nicht_bestimmbar' ist das fuenfte Feld (M-1).
QUADRANTEN: Tuple[str, ...] = (
    "arbeitsreif",          # hohe Dringlichkeit, hohe Erkenntnislage
    "gefaehrlich",          # hohe Dringlichkeit, NIEDRIGE Erkenntnislage
    "belegt_nicht_eilig",   # niedrige Dringlichkeit, hohe Erkenntnislage
    "nachrangig",           # beides niedrig
    "nicht_bestimmbar",     # Dringlichkeit oder Erkenntnislage nicht bestimmbar
)

#: Klartext je Quadrant. Der gefaehrlichste steht bewusst nicht 'rot' da,
#  sondern mit seinem Grund — eine Farbe erklaert nichts.
QUADRANT_BEDEUTUNG: Dict[str, str] = {
    "arbeitsreif": "Hohe Dringlichkeit bei belastbarer Erkenntnislage — "
                   "arbeitsreif.",
    "gefaehrlich": "Hohe Dringlichkeit bei DUENNER Erkenntnislage. Hier droht "
                   "der Fristablauf, bevor ueberhaupt ermittelt wurde.",
    "belegt_nicht_eilig": "Belastbare Erkenntnislage ohne Zeitdruck.",
    "nachrangig": "Weder Zeitdruck noch belastbare Erkenntnislage.",
    "nicht_bestimmbar": "Mindestens eine Achse ist NICHT bestimmbar. Der Fall "
                        "ist damit UNGEPRUEFT, nicht unverdaechtig.",
}

#: Die Belastbarkeit der Dringlichkeitszahl (M-1). Orthogonal zum Wert.
BELASTBARKEITEN: Tuple[str, ...] = ("festgestellt", "vorlaeufig", "ohne_frist")


@dataclass(frozen=True)
class MatrixZelle:
    """Ein Fall in der Matrix."""

    subject_id: int
    username: str

    # --- X ------------------------------------------------------------------
    #: Der Dringlichkeitswert — None, wenn die Frist nicht bestimmbar ist.
    dringlichkeit: Optional[int]
    #: Was OHNE die Fristkomponente schon zusammenkommt. Immer gesetzt.
    dringlichkeit_mindestens: int
    dringlichkeit_bestimmbar: bool
    #: 'festgestellt' | 'vorlaeufig' | 'ohne_frist' (M-1)
    dringlichkeit_belastbarkeit: str
    #: Warum nicht bestimmbar (Ampelzustand oder 'nicht_geladen').
    dringlichkeit_grund: Optional[str]

    # --- Y ------------------------------------------------------------------
    erkenntnislage: Optional[int]
    erkenntnislage_bestimmbar: bool
    #: Kriterien, ueber die die Abdeckung gerechnet wurde (ohne die
    #  ausgeschlossenen). Steht in der Antwort, damit die Prozentzahl erklaerbar
    #  bleibt (M-3).
    n_kriterien_matrix: int

    quadrant: str
    beitraege: Tuple[Dict[str, Any], ...] = ()
    vermerke: Tuple[str, ...] = ()
    #: Codes, die keine Punktetabelle kennt. NIE stillschweigend 0 (M-2).
    unbekannte_codes: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "username": self.username,
            "dringlichkeit": self.dringlichkeit,
            "dringlichkeit_mindestens": self.dringlichkeit_mindestens,
            "dringlichkeit_bestimmbar": self.dringlichkeit_bestimmbar,
            "dringlichkeit_belastbarkeit": self.dringlichkeit_belastbarkeit,
            "dringlichkeit_grund": self.dringlichkeit_grund,
            "erkenntnislage": self.erkenntnislage,
            "erkenntnislage_bestimmbar": self.erkenntnislage_bestimmbar,
            "n_kriterien_matrix": self.n_kriterien_matrix,
            "quadrant": self.quadrant,
            "quadrant_bedeutung": QUADRANT_BEDEUTUNG.get(self.quadrant, ""),
            "beitraege": [dict(b) for b in self.beitraege],
            "vermerke": list(self.vermerke),
            "unbekannte_codes": list(self.unbekannte_codes),
        }


class UrgencyMatrix:
    """Rechnet einen Fall in eine Matrixzelle. Rein, ohne Seiteneffekte."""

    def __init__(self, gewichte: MatrixGewichte) -> None:
        self._g = gewichte

    # ------------------------------------------------------------------ Achse X
    def _dringlichkeit(self, fall: Mapping[str, Any]
                       ) -> Tuple[Optional[int], int, bool, str, Optional[str],
                                  List[Dict[str, Any]], List[str]]:
        g = self._g
        beitraege: List[Dict[str, Any]] = []
        vermerke: List[str] = []

        def _add(code: str, punkte: int, text: str) -> None:
            if punkte:
                beitraege.append({"achse": "dringlichkeit", "code": code,
                                  "punkte": punkte, "grund": text})

        # --- die Beitraege OHNE Frist. Sie gelten immer, auch wenn die Frist
        #     nicht bestimmbar ist — sonst ginge Information verloren (M-1).
        rest_punkte = 0
        if fall.get("wiedervorlage_ueberfaellig"):
            rest_punkte += g.wiedervorlage_ueberfaellig
            _add("wiedervorlage", g.wiedervorlage_ueberfaellig,
                 "Mindestens ein externer Vorgang ist ueberfaellig.")

        n_esk = int(fall.get("eskalationen") or 0)
        if n_esk > 0:
            rest_punkte += g.eskalation_aktiv
            # Der Punktwert ist derselbe bei einer wie bei fuenf Meldungen; die
            # ZAHL steht im Beitrag. Sie zu addieren wuerde einen Fall mit
            # mehreren Regelverstoessen ueber die Frist heben, und das ist
            # nicht beschlossen.
            _add("eskalation", g.eskalation_aktiv,
                 "%d aktive Eskalationsmeldung(en). Quittierte zaehlen MIT — "
                 "eine Quittierung ist kein Erledigen (M027)." % n_esk)

        tage = fall.get("tage_ohne_ereignis")
        if tage is not None and int(tage) >= g.liegezeit_tage_ab:
            rest_punkte += g.liegezeit
            _add("liegezeit", g.liegezeit,
                 "Seit %d Tagen kein Ereignis (Schwelle %d)."
                 % (int(tage), g.liegezeit_tage_ab))

        if fall.get("unzugewiesen"):
            rest_punkte += g.unzugewiesen
            _add("unzugewiesen", g.unzugewiesen,
                 "Der Fall ist niemandem zugewiesen.")

        # --- die Fristkomponente -------------------------------------------
        lim = fall.get("limitation")
        if lim is None:
            # Build 538: die Fristbeitraege werden nachgeladen. Bis dahin ist
            # der Wert NICHT null, sondern UNBEKANNT — der Unterschied ist der
            # ganze Punkt.
            return (None, rest_punkte, False, "ohne_frist", "nicht_geladen",
                    beitraege,
                    vermerke + ["Die Fristkomponente wurde nicht geladen. Der "
                                "ausgewiesene Wert ist eine UNTERGRENZE."])

        ampel = str(lim.get("ampel") or "")
        feststellung = str(lim.get("feststellung") or "")
        anker_art = str(lim.get("anker_art") or "")

        if ampel not in AMPEL_MIT_FRIST:
            return (None, rest_punkte, False, "ohne_frist", ampel, beitraege,
                    vermerke + [
                        "Keine Restlaufzeit bestimmbar (Zustand '%s'). Der "
                        "Fall ist damit UNGEPRUEFT, nicht unverdaechtig — er "
                        "steht deshalb im Feld 'nicht bestimmbar' und nicht "
                        "mit 0 Punkten am Listenende." % ampel])

        rest_tage = lim.get("restlaufzeit_tage")
        if rest_tage is None:
            # Ampel sagt 'rechenbar', aber es kommt keine Zahl. Das ist ein
            # Widerspruch im Datensatz und wird BENANNT, nicht geglaettet.
            return (None, rest_punkte, False, "ohne_frist",
                    "restlaufzeit_fehlt", beitraege,
                    vermerke + ["WIDERSPRUCH: Ampel '%s' verspricht eine "
                                "Restlaufzeit, es kommt aber keine. Der Fall "
                                "wird nicht gerechnet." % ampel])

        rest_tage = int(rest_tage)
        frist_punkte = 0
        if rest_tage <= g.frist_knapp_tage_bis:
            frist_punkte = g.frist_knapp
            _add("frist", frist_punkte,
                 "Restlaufzeit %d Tage (Schwelle %d)."
                 % (rest_tage, g.frist_knapp_tage_bis))
        elif rest_tage <= g.frist_mittel_tage_bis:
            frist_punkte = g.frist_mittel
            _add("frist", frist_punkte,
                 "Restlaufzeit %d Tage (Schwelle %d)."
                 % (rest_tage, g.frist_mittel_tage_bis))

        if ampel == "ueberschritten":
            vermerke.append(
                "Der Fristablauf ist nach der UNUNTERBROCHENEN Frist "
                "rechnerisch ueberschritten — juristische Pruefung "
                "erforderlich (§ 78c StGB ist diesem Werkzeug nicht bekannt).")

        # --- Belastbarkeit: ausgewiesen, NICHT eingerechnet (M-1) -----------
        if feststellung == "festgestellt":
            belastbarkeit = "festgestellt"
        else:
            belastbarkeit = "vorlaeufig"
            vermerke.append(
                "Die Fristkomponente beruht auf einem NICHT festgestellten "
                "Datum. Sie ist ungekuerzt eingerechnet — die Belastbarkeit "
                "steht daneben, nicht in der Zahl.")
        if anker_art in ("registrierung", "anmeldung"):
            vermerke.append(
                "ERSATZANKER (%s): der Zeitpunkt liegt am ANFANG der "
                "Zugehoerigkeit, § 78a StGB knuepft an die BEENDIGUNG an. Der "
                "Fristablauf ist damit zu frueh gerechnet und der Fall "
                "erscheint dringender, als er nach den bekannten Tatsachen "
                "ist." % anker_art)

        return (rest_punkte + frist_punkte, rest_punkte, True, belastbarkeit,
                None, beitraege, vermerke)

    # ------------------------------------------------------------------ Achse Y
    def _erkenntnislage(self, fall: Mapping[str, Any]
                        ) -> Tuple[Optional[int], bool, int,
                                   List[Dict[str, Any]], List[str], List[str]]:
        g = self._g
        beitraege: List[Dict[str, Any]] = []
        vermerke: List[str] = []
        unbekannt: List[str] = []
        ausgeschlossen = set(g.ausgeschlossene_kriterien)

        def _add(code: str, punkte: int, text: str) -> None:
            if punkte:
                beitraege.append({"achse": "erkenntnislage", "code": code,
                                  "punkte": punkte, "grund": text})

        # --- (1) Abdeckung, OHNE die ausgeschlossenen Kriterien (M-3) -------
        alle = [k for k in (fall.get("alle_kriterien") or ())
                if k not in ausgeschlossen]
        n_krit = len(alle)
        bewertungen = [b for b in (fall.get("bewertungen") or ())
                       if b.get("extrem") == "schwerste"
                       and b.get("criterion_code") not in ausgeschlossen]
        bewertet = {b.get("criterion_code") for b in bewertungen}

        punkte = 0
        if n_krit:
            abdeckung = len(bewertet) / n_krit
            punkte = int(round(abdeckung * g.abdeckung_max))
            _add("abdeckung", punkte,
                 "%d von %d gerechneten Kriterien bewertet (%.0f %%). "
                 "'%s' ist ausgenommen, weil die Identitaet eigens zaehlt."
                 % (len(bewertet), n_krit, abdeckung * 100,
                    "', '".join(sorted(ausgeschlossen)) or "—"))
        else:
            vermerke.append(
                "Es sind keine Bewertungskriterien vorhanden — die Abdeckung "
                "ist nicht berechenbar.")

        # --- (2) hoechste Konfidenz ----------------------------------------
        konf_punkte = 0
        if bewertungen:
            # Hoechste nach dem ORDINAL der Skala, nicht nach unserer
            # Punktetabelle: welche Bewertung 'die hoechste' ist, entscheidet
            # der Katalog und nicht unsere Gewichtung.
            hoechste = max(
                bewertungen,
                key=lambda b: int(b.get("confidence_ordinal") or 0))
            code = str(hoechste.get("confidence_code") or "")
            if code in g.konfidenz:
                konf_punkte = g.konfidenz[code]
                punkte += konf_punkte
                _add("konfidenz", konf_punkte,
                     "Hoechste Konfidenz '%s' bei Kriterium '%s'."
                     % (code, hoechste.get("criterion_code")))
            else:
                # M-2: NIEMALS stillschweigend 0.
                unbekannt.append(code)
                vermerke.append(
                    "Die Konfidenzstufe '%s' steht in keiner Punktetabelle. "
                    "Der Fall wird NICHT mit 0 gerechnet, sondern als nicht "
                    "bestimmbar gefuehrt — vermutlich wurde der Katalog "
                    "erweitert und der Gewichtungssatz nicht nachgezogen."
                    % code)

        # --- (3) Identitaet, abgestuft (M-3) --------------------------------
        ident = fall.get("identitaet_konfidenz")
        if ident:
            code = str(ident)
            if code in g.identitaet:
                p = g.identitaet[code]
                punkte += p
                _add("identitaet", p,
                     "Identitaet zugeordnet, Konfidenz '%s'." % code)
            else:
                unbekannt.append(code)
                vermerke.append(
                    "Die Identitaets-Konfidenz '%s' steht in keiner "
                    "Punktetabelle. Der Fall wird NICHT mit 0 gerechnet."
                    % code)

        bestimmbar = not unbekannt
        return ((punkte if bestimmbar else None), bestimmbar, n_krit,
                beitraege, vermerke, unbekannt)

    # ------------------------------------------------------------------ Zelle
    def bewerte(self, fall: Mapping[str, Any]) -> MatrixZelle:
        """
        Rechnet EINEN Fall. 'fall' ist ein dict mit:

          subject_id, username
          limitation                — LimitationRow.to_dict() oder None
          wiedervorlage_ueberfaellig (bool)
          eskalationen              (int: Zahl der aktiven Meldungen)
          tage_ohne_ereignis        (int oder None)
          unzugewiesen              (bool)
          alle_kriterien            (Sequence[str])
          bewertungen               (Sequence[dict] aus v_investigation_current)
          identitaet_konfidenz      (str oder None)
        """
        (x, x_min, x_ok, belastbarkeit, x_grund,
         x_beitraege, x_vermerke) = self._dringlichkeit(fall)
        (y, y_ok, n_krit, y_beitraege, y_vermerke,
         unbekannt) = self._erkenntnislage(fall)

        if not x_ok or not y_ok:
            quadrant = "nicht_bestimmbar"
        else:
            hoch_x = x >= self._g.schwelle_dringlichkeit
            hoch_y = y >= self._g.schwelle_erkenntnislage
            if hoch_x and hoch_y:
                quadrant = "arbeitsreif"
            elif hoch_x:
                quadrant = "gefaehrlich"
            elif hoch_y:
                quadrant = "belegt_nicht_eilig"
            else:
                quadrant = "nachrangig"

        beitraege = sorted(x_beitraege + y_beitraege,
                           key=lambda b: (-b["punkte"], b["code"]))

        return MatrixZelle(
            subject_id=int(fall.get("subject_id") or 0),
            username=str(fall.get("username") or "?"),
            dringlichkeit=x,
            dringlichkeit_mindestens=x_min,
            dringlichkeit_bestimmbar=x_ok,
            dringlichkeit_belastbarkeit=belastbarkeit,
            dringlichkeit_grund=x_grund,
            erkenntnislage=y,
            erkenntnislage_bestimmbar=y_ok,
            n_kriterien_matrix=n_krit,
            quadrant=quadrant,
            beitraege=tuple(beitraege),
            vermerke=tuple(x_vermerke + y_vermerke),
            unbekannte_codes=tuple(unbekannt),
        )

    # ------------------------------------------------------------------ Menge
    def bewerte_alle(self, faelle: Sequence[Mapping[str, Any]]
                     ) -> List[MatrixZelle]:
        """
        Rechnet viele Faelle und sortiert sie so, wie die Leitung sie lesen
        soll:

          1. 'nicht_bestimmbar' ZUERST. Ungeprueftes darf nicht unter
             Unverdaechtiges rutschen — dieselbe Regel wie im Fristenmonitor
             (limitation_repo.compute(), Sortierung).
          2. dann 'gefaehrlich' (Frist laeuft, Erkenntnislage duenn),
          3. dann 'arbeitsreif',
          4. dann der Rest, jeweils nach Dringlichkeit absteigend.
        """
        rang = {"nicht_bestimmbar": 0, "gefaehrlich": 1, "arbeitsreif": 2,
                "belegt_nicht_eilig": 3, "nachrangig": 4}
        zellen = [self.bewerte(f) for f in faelle]
        zellen.sort(key=lambda z: (
            rang.get(z.quadrant, 9),
            # Innerhalb der nicht bestimmbaren zaehlt die UNTERGRENZE: ein
            # ungeprueter Fall mit vielen anderen Beitraegen ist dringender
            # als einer ohne.
            -(z.dringlichkeit if z.dringlichkeit is not None
              else z.dringlichkeit_mindestens),
            z.subject_id))
        return zellen
