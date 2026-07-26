# =============================================================================
# management/qs/qs_sampler.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3C (Build 540)
# =============================================================================
# Zweck:
#   Die ZIEHUNG der QS-Stichprobe. Reine Rechnung ohne Datenbank und ohne
#   Seiteneffekte — sie bekommt die Grundgesamtheit als Liste von dicts und
#   liefert die gezogenen Faelle samt Schichtung und Nachweis.
#
# ── DIE TRAGENDE ENTSCHEIDUNG: DER ZUFALLSKEIM WIRD MITGESCHRIEBEN ───────────
#
#   Eine Stichprobe, deren Ziehung man nicht nachvollziehen kann, ist kein
#   Beleg — sie waere gegen den Vorwurf der gezielten Auswahl nicht zu
#   verteidigen. Deshalb:
#
#     * random.Random(seed) und NICHT secrets. Das ist ABSICHT und keine
#       Nachlaessigkeit. Ein kryptografisch sicherer Zufall waere hier ein
#       FEHLER: er ist per Konstruktion nicht reproduzierbar, und genau die
#       Reproduzierbarkeit ist der Zweck.
#     * Der Keim, die Groesse der Grundgesamtheit und die Filterangaben werden
#       mit der Ziehung gespeichert (M034: seed, grundgesamtheit_n,
#       filter_json).
#     * ziehe() ist eine FUNKTION im mathematischen Sinn: gleiche Eingabe ->
#       gleiche Ausgabe, jederzeit. Ein Nachziehen mit demselben Keim ueber
#       dieselbe Grundgesamtheit MUSS dieselben subject_id in derselben
#       Reihenfolge liefern; QS-S02 prueft das.
#
#   DIE GRUNDGESAMTHEIT WIRD VOR DER ZIEHUNG SORTIERT (nach subject_id). Ohne
#   das haenge das Ergebnis an der Reihenfolge, in der die Datenbank die Zeilen
#   liefert — und die ist ohne ORDER BY nicht zugesichert. Eine Ziehung, die
#   sich nach einem VACUUM anders nachrechnet, waere wertlos.
#
# ── DIE SCHICHTUNG ───────────────────────────────────────────────────────────
#
#   Entscheidung mc: GESCHICHTET. Die blinden Flecken (nie bewertet, Abdeckung
#   unter der Schwelle) werden ueberproportional geprueft, weil dort der
#   Erkenntnisgewinn einer Pruefung liegt. Bei einer einfachen Zufallsstichprobe
#   ueber alle Faelle waeren sie fast nie dabei.
#
#   ES WIRD NACH GEWICHTETER MASSE AUFGETEILT UND DANN AUFGEFUELLT. Die
#   Aufteilung folgt NICHT dem Anteil einer Schicht an der Grundgesamtheit,
#   sondern dem Anteil ihrer GEWICHTETEN Masse (Faelle mal Gewicht aus
#   SCHICHT_GEWICHT). Das ist der Unterschied zwischen 'geschichtet' und
#   'ueberproportional': eine rein proportionale Schichtung zoege die blinden
#   Flecken genau so oft wie eine einfache Zufallsstichprobe, und der ganze
#   Aufwand waere Zierrat. Eine Schicht, die weniger Faelle hat als ihr Anteil,
#   gibt die Reste an die uebrigen zurueck; ohne dieses Auffuellen waere die
#   Stichprobe stillschweigend kleiner als angefordert — und niemand saehe,
#   warum.
#
#   LEERE SCHICHTEN WERDEN AUSGEWIESEN, nicht uebersprungen. 'schichten' nennt
#   je Schicht die Groesse der Grundgesamtheit UND die Zahl der Gezogenen.
#
# ── DIE GROESSE ──────────────────────────────────────────────────────────────
#
#   Entscheidung mc: RELATIVE MENGE MIT ABSOLUTER HOECHSTGRENZE, von der
#   Supervisorin gesetzt. Beides wird mitgeschrieben; die tatsaechliche Groesse
#   ist min(anteil * N, hoechstens) und mindestens 1, solange es ueberhaupt
#   einen Fall gibt. Eine Ziehung mit 0 Prueflingen ueber einer nicht leeren
#   Grundgesamtheit waere eine stillschweigende Nichtdurchfuehrung.
#
# ── DIE PRUEFLINGE SIND EIN VORSCHLAG ────────────────────────────────────────
#
#   Entscheidung mc: Abweichung ist erlaubt und wird PROTOKOLLIERT. Dieses
#   Modul zieht nur; die Abweichung ist ein Schreibvorgang und gehoert in den
#   Repository-Teil (Build 541). Hier steht sie als Vermerk, damit die Ziehung
#   nicht als bindend missverstanden wird.
#
# Version: v0.8.540 · Build: 540 · 2026-07-26
# =============================================================================

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from management.qs.qs_vokabular import (
    ABDECKUNG_SCHWELLE,
    SCHICHT_CODES,
    SCHICHT_GEWICHT,
    VERFAHREN_CODES,
    ZWECKBINDUNG,
    schicht_label,
)


class QsSamplerError(Exception):
    """Unbrauchbare Ziehungsvorgabe. Es wird VERWEIGERT, nicht repariert."""


@dataclass(frozen=True)
class Ziehung:
    """Das Ergebnis einer Ziehung. Reines Lese-DTO."""

    verfahren: str
    seed: int
    grundgesamtheit_n: int
    stichprobe_n: int
    anteil: float
    hoechstens: int
    abdeckung_schwelle: float
    #: subject_id in ZIEHUNGSREIHENFOLGE. Die Reihenfolge ist Teil des Belegs.
    subject_ids: Tuple[int, ...]
    #: Die Uebergewichtung je Schicht, mit der gezogen wurde. Sie gehoert in
    #  den Beleg: ohne sie liesse sich die Aufteilung nicht nachrechnen.
    schicht_gewicht: Dict[str, float] = field(
        default_factory=lambda: dict(SCHICHT_GEWICHT))
    #: je Schicht: {code, label, grundgesamtheit_n, soll_n, gezogen_n}
    schichten: Tuple[Dict[str, Any], ...] = ()
    hinweise: Tuple[str, ...] = ()

    def filter_json(self) -> str:
        """
        Die Angaben, die eine Ziehung REPRODUZIERBAR machen, als JSON.

        Sie werden mit der Ziehung gespeichert (M034.filter_json). Wer
        nachzieht, braucht genau diese Werte — der Keim allein genuegt nicht,
        weil Verfahren und Schwelle die Schichtung bestimmen.
        """
        return json.dumps({
            "verfahren": self.verfahren,
            "anteil": self.anteil,
            "hoechstens": self.hoechstens,
            "abdeckung_schwelle": self.abdeckung_schwelle,
            "schicht_gewicht": dict(self.schicht_gewicht),
            "schichten": [
                {k: s[k] for k in ("code", "grundgesamtheit_n", "soll_n",
                                   "gezogen_n")}
                for s in self.schichten
            ],
        }, ensure_ascii=False, sort_keys=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verfahren": self.verfahren,
            "seed": self.seed,
            "grundgesamtheit_n": self.grundgesamtheit_n,
            "stichprobe_n": self.stichprobe_n,
            "anteil": self.anteil,
            "hoechstens": self.hoechstens,
            "abdeckung_schwelle": self.abdeckung_schwelle,
            "schicht_gewicht": dict(self.schicht_gewicht),
            "subject_ids": list(self.subject_ids),
            "schichten": [dict(s) for s in self.schichten],
            "hinweise": list(self.hinweise),
            "zweckbindung": ZWECKBINDUNG,
            "ist_kein_bewertungsinstrument": True,
            "prueflinge_sind_vorschlag": True,
        }


def schicht_von(fall: Mapping[str, Any],
                schwelle: float = ABDECKUNG_SCHWELLE) -> str:
    """
    Die Schicht EINES Falls. Rein.

    Erwartet 'nie_bewertet' (bool) und 'abdeckung' (0..1) — beides liefert
    CoverageRepo (coverage_repo.py:113-131) bereits fertig; hier wird NICHTS
    nachgerechnet.

    FEHLT die Abdeckung ganz (None), gilt der Fall als NIE BEWERTET und nicht
    als 'rest'. Begruendung: eine fehlende Angabe ist kein Beleg fuer eine gute
    Abdeckung, und die Schichtung soll im Zweifel MEHR pruefen, nicht weniger.
    """
    if fall.get("nie_bewertet"):
        return "nie_bewertet"
    a = fall.get("abdeckung")
    if a is None:
        return "nie_bewertet"
    return "abdeckung_niedrig" if float(a) < float(schwelle) else "rest"


def _groesse(n: int, anteil: float, hoechstens: int) -> int:
    """
    Die Zielgroesse: min(ceil(anteil * n), hoechstens), aber mindestens 1,
    solange n > 0 ist.

    AUFGERUNDET (ceil) und nicht abgerundet: bei 12 Faellen und 5 % waere
    abgerundet 0 — eine Ziehung, die nichts zieht, sieht aus wie 'nichts zu
    pruefen' und ist doch nur eine Rundung.
    """
    if n <= 0:
        return 0
    ziel = int(math.ceil(anteil * n))
    ziel = min(ziel, int(hoechstens), n)
    return max(1, ziel)


def ziehe(grundgesamtheit: Sequence[Mapping[str, Any]], *,
          seed: int,
          anteil: float = 0.1,
          hoechstens: int = 10,
          verfahren: str = "geschichtet",
          abdeckung_schwelle: float = ABDECKUNG_SCHWELLE) -> Ziehung:
    """
    Zieht die Stichprobe. REIN: gleiche Eingabe -> gleiche Ausgabe.

    grundgesamtheit — Liste von dicts mit mindestens 'subject_id'; fuer die
                      geschichtete Ziehung zusaetzlich 'nie_bewertet' und
                      'abdeckung' (Muster CoverageRepo).

    Es wird VERWEIGERT statt repariert: ein unbekanntes Verfahren, ein Anteil
    ausserhalb (0, 1], eine Hoechstgrenze unter 1 oder ein Eintrag ohne
    subject_id sind Fehler. Ein automatisch korrigierter Ziehungsparameter
    waere eine Behauptung des Werkzeugs anstelle einer Leitungsentscheidung —
    dieselbe Haltung wie beim Matrix-Gewichtungssatz (Build 536).
    """
    if verfahren not in VERFAHREN_CODES:
        raise QsSamplerError(
            "Unbekanntes Ziehungsverfahren '%s' (gueltig: %s)."
            % (verfahren, ", ".join(VERFAHREN_CODES)))
    if not (0.0 < float(anteil) <= 1.0):
        raise QsSamplerError(
            "Der Anteil muss groesser als 0 und hoechstens 1 sein (%r)."
            % (anteil,))
    if int(hoechstens) < 1:
        raise QsSamplerError(
            "Die Hoechstgrenze muss mindestens 1 betragen (%r)." % (hoechstens,))

    # SORTIEREN VOR DEM ZIEHEN — sonst haengt das Ergebnis an der Reihenfolge
    # der Datenbankzeilen, und die ist ohne ORDER BY nicht zugesichert.
    try:
        faelle = sorted(grundgesamtheit, key=lambda f: int(f["subject_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise QsSamplerError(
            "Jeder Eintrag der Grundgesamtheit braucht eine ganzzahlige "
            "'subject_id' (%s)." % exc) from exc

    n = len(faelle)
    ziel = _groesse(n, float(anteil), int(hoechstens))
    hinweise: List[str] = []

    if n == 0:
        hinweise.append(
            "Die Grundgesamtheit ist LEER. Das ist ein Leerbefund ueber die "
            "Fallauswahl und keine Aussage ueber die Auswertungsqualitaet.")
        return Ziehung(verfahren=verfahren, seed=int(seed), grundgesamtheit_n=0,
                       stichprobe_n=0, anteil=float(anteil),
                       hoechstens=int(hoechstens),
                       abdeckung_schwelle=float(abdeckung_schwelle),
                       subject_ids=(), schichten=(),
                       hinweise=tuple(hinweise))

    if ziel == n:
        hinweise.append(
            "Die Stichprobe umfasst die GESAMTE Grundgesamtheit (%d Faelle). "
            "Das ist eine Vollpruefung; die Schichtung hat dann keine Wirkung "
            "mehr." % n)

    rnd = random.Random(int(seed))

    # --- einfache Ziehung ------------------------------------------------
    if verfahren == "einfach":
        gezogen = rnd.sample([int(f["subject_id"]) for f in faelle], ziel)
        return Ziehung(
            verfahren=verfahren, seed=int(seed), grundgesamtheit_n=n,
            stichprobe_n=len(gezogen), anteil=float(anteil),
            hoechstens=int(hoechstens),
            abdeckung_schwelle=float(abdeckung_schwelle),
            subject_ids=tuple(gezogen),
            schichten=({"code": "rest", "label": schicht_label("rest"),
                        "grundgesamtheit_n": n, "soll_n": ziel,
                        "gezogen_n": len(gezogen)},),
            hinweise=tuple(hinweise))

    # --- geschichtete Ziehung --------------------------------------------
    eimer: Dict[str, List[int]] = {c: [] for c in SCHICHT_CODES}
    for f in faelle:
        eimer[schicht_von(f, abdeckung_schwelle)].append(int(f["subject_id"]))

    # Aufteilung nach GEWICHTETER Masse, dann AUFFUELLEN. Die Gewichtung ist
    # der Grund fuer die Schichtung ueberhaupt (s. Kopf): proportional
    # aufgeteilt wuerde 'geschichtet' dasselbe leisten wie 'einfach'.
    masse = {c: len(eimer[c]) * float(SCHICHT_GEWICHT.get(c, 1.0))
             for c in SCHICHT_CODES}
    masse_gesamt = sum(masse.values())
    soll: Dict[str, int] = {}
    rest = ziel
    for code in SCHICHT_CODES:
        anteil_schicht = (masse[code] / masse_gesamt) if masse_gesamt else 0.0
        s = min(len(eimer[code]), int(math.floor(anteil_schicht * ziel)))
        soll[code] = s
        rest -= s
    # Die Reste gehen in der Reihenfolge der PruefLAST: blinde Flecken zuerst.
    for code in SCHICHT_CODES:
        if rest <= 0:
            break
        frei = len(eimer[code]) - soll[code]
        nimm = min(frei, rest)
        soll[code] += nimm
        rest -= nimm

    gezogen: List[int] = []
    schichten: List[Dict[str, Any]] = []
    for code in SCHICHT_CODES:
        kandidaten = eimer[code]
        k = min(soll[code], len(kandidaten))
        teil = rnd.sample(kandidaten, k) if k else []
        gezogen.extend(teil)
        schichten.append({
            "code": code, "label": schicht_label(code),
            "grundgesamtheit_n": len(kandidaten),
            "soll_n": soll[code], "gezogen_n": len(teil),
        })
        if kandidaten and not teil:
            # LEERE ZIEHUNG AUS EINER NICHT LEEREN SCHICHT — das ist eine
            # Aussage und wird benannt, nicht verschwiegen.
            hinweise.append(
                "Aus der Schicht '%s' (%d Faelle) wurde NICHTS gezogen. Bei "
                "dieser Stichprobengroesse bleibt sie unbeobachtet."
                % (schicht_label(code), len(kandidaten)))

    if rest > 0:
        hinweise.append(
            "Es wurden %d Faelle WENIGER gezogen als angefordert (%d von %d): "
            "die Grundgesamtheit gibt nicht mehr her." % (rest, len(gezogen),
                                                          ziel))

    return Ziehung(
        verfahren=verfahren, seed=int(seed), grundgesamtheit_n=n,
        stichprobe_n=len(gezogen), anteil=float(anteil),
        hoechstens=int(hoechstens),
        abdeckung_schwelle=float(abdeckung_schwelle),
        subject_ids=tuple(gezogen), schichten=tuple(schichten),
        hinweise=tuple(hinweise))


def nachziehen_stimmt(ziehung: Ziehung,
                      grundgesamtheit: Sequence[Mapping[str, Any]]
                      ) -> Tuple[bool, List[str]]:
    """
    Rechnet eine gespeicherte Ziehung NACH und meldet jede Abweichung.

    Das ist der eigentliche Zweck des mitgeschriebenen Keims: gegen den Vorwurf
    der gezielten Auswahl hilft nur, dass es jemand nachrechnen KANN. Der
    CLI-Befehl aus Build 541 ruft genau diese Funktion.

    -> (stimmt, abweichungen[]). Die Abweichungen sind Klartext, weil sie in
       einen Vermerk gehoeren.
    """
    neu = ziehe(grundgesamtheit, seed=ziehung.seed, anteil=ziehung.anteil,
                hoechstens=ziehung.hoechstens, verfahren=ziehung.verfahren,
                abdeckung_schwelle=ziehung.abdeckung_schwelle)
    ab: List[str] = []
    if neu.grundgesamtheit_n != ziehung.grundgesamtheit_n:
        ab.append(
            "Die Grundgesamtheit hat sich geaendert: damals %d Faelle, heute "
            "%d. Eine Ziehung laesst sich nur ueber DEMSELBEN Bestand "
            "nachrechnen."
            % (ziehung.grundgesamtheit_n, neu.grundgesamtheit_n))
    if neu.subject_ids != ziehung.subject_ids:
        ab.append(
            "Die gezogenen Faelle weichen ab. Damals: %s. Heute: %s."
            % (list(ziehung.subject_ids), list(neu.subject_ids)))
    return (not ab), ab
