# =============================================================================
# management/deadlines/limitation.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Zweck (Idee 32, Build 523):
#   Die REINE Berechnung der Verfolgungsverjaehrung je Fall: aus einem
#   Tatzeitpunkt (§ 78a StGB: Beendigung der Tat), dem gepruefen Parametersatz
#   und einem Stichtag entsteht eine Einschaetzung mit Ampel.
#
#   KEINE Datei, KEINE Datenbank, KEINE Uhr — Tatzeit und Stichtag werden
#   INJIZIERT. Damit ist jede Aussage dieses Moduls deterministisch
#   reproduzierbar; das ist bei einer Frist nicht Komfort, sondern Voraussetzung
#   (eine Fristangabe, die man nicht nachrechnen kann, ist kein Beleg).
#
# WAS DIESES MODUL AUSDRUECKLICH NICHT SAGT:
#   Es sagt NIE "verjaehrt". Es sagt "Fristablauf nach der ununterbrochenen
#   Frist rechnerisch ueberschritten — juristische Pruefung erforderlich".
#   Der Unterschied ist der ganze Punkt: § 78c StGB (Unterbrechung) kann die
#   Frist neu in Gang gesetzt haben, und davon weiss dieses Werkzeug nichts.
#
# DIE FUENF ZUSTAENDE (ampel), bewusst getrennt statt in "rot/gelb/gruen"
# gequetscht:
#   'keine_aussage'  — Parametersatz nicht bestaetigt. KEINE Ampel, ein Grund.
#   'ohne_tatzeit'   — kein Tatzeitpunkt belegt. Der Fall ist damit NICHT
#                      unverdaechtig, sondern UNGEPRUEFT. Eigener Zustand, weil
#                      "gruen" hier eine Falschaussage waere.
#   'ruht'           — alle in Betracht kommenden Tatbestaende ruhen moeglicher-
#                      weise (§ 78b Abs. 1 Nr. 1 StGB). Keine Restlaufzeit,
#                      weil das Opferalter nicht in den Daten steht.
#   'ueberschritten' — die ununterbrochene Frist ist rechnerisch abgelaufen.
#   'knapp'          — Restlaufzeit unter der Vorwarnschwelle.
#   'offen'          — Restlaufzeit ueber der Vorwarnschwelle.
#
# MASSGEBLICH IST DIE KUERZESTE FRIST — und sie wird BENANNT. Welcher
#   Tatbestand im Einzelfall verwirklicht ist, ist eine rechtliche Bewertung und
#   steht in keiner Tabelle. Das Modul rechnet deshalb ALLE Tatbestaende des
#   Vorgabesatzes durch, weist die frueheste Fristgrenze als 'massgeblich' aus
#   UND liefert die vollstaendige Einzelaufstellung mit. So kann niemand die
#   Zahl lesen, ohne zu sehen, woher sie kommt.
#
# LUECKEN WERDEN GEMELDET, NICHT UEBERBRUECKT: liegt fuer den Tatzeitpunkt keine
#   Fassung vor (z. B. Tat vor dem 01.07.2021), wird der Tatbestand als
#   'ohne_fassung' gefuehrt — er faellt NICHT stillschweigend weg und wird NICHT
#   mit einer spaeteren Fassung gerechnet (§ 2 Abs. 1 StGB, Tatzeitrecht;
#   Grundregel 1).
#
# Version: v0.8.523 · Build: 523 · 2026-07-25
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from management.deadlines.limitation_params import LimitationParams

_DAY = 86400

#: Vorwarnschwelle in Tagen (Vorgabe: 12 Monate). Uebersteuerbar — die
#  angewandte Schwelle faehrt in jeder Antwort mit, damit jede Einstufung
#  nachrechenbar ist (Muster ops/retention.py).
DEFAULT_VORWARN_TAGE = 365

#: Der Satz, der anstelle von "verjaehrt" gesagt wird. Wortlaut ist Absicht.
BEFUND_UEBERSCHRITTEN = (
    "Fristablauf nach der UNUNTERBROCHENEN Frist rechnerisch ueberschritten — "
    "juristische Pruefung erforderlich. Unterbrechungen nach § 78c StGB sind "
    "diesem Werkzeug nicht bekannt und koennen die Frist neu in Gang gesetzt "
    "haben."
)

#: Der Satz fuer ruhende Fristen.
BEFUND_RUHT = (
    "Ruht moeglicherweise nach § 78b Abs. 1 Nr. 1 StGB (bis zur Vollendung des "
    "30. Lebensjahres des Opfers). Eine Restlaufzeit ist NICHT berechenbar, "
    "weil das Geburtsdatum des Opfers nicht in den ausgewerteten Daten steht."
)

#: Der Satz fuer Faelle ohne belegten Tatzeitpunkt.
BEFUND_OHNE_TATZEIT = (
    "KEIN Tatzeitpunkt belegt — dieser Fall ist damit nicht unverdaechtig, "
    "sondern UNGEPRUEFT. Ohne Fristbeginn (§ 78a StGB) ist keine Frist "
    "berechenbar."
)


def add_years(d: date, years: int) -> date:
    """
    Kalendarische Fortschreibung um ganze Jahre.

    29. Februar -> 28. Februar des Zieljahres, wenn dieses kein Schaltjahr ist.
    Das ist eine ANNAEHERUNG an die Fristberechnung nach §§ 78a StGB, 187 f.
    BGB und kann um einen Tag abweichen; der Vorbehalt dazu steht im
    Parametersatz und faehrt in jeder Antwort mit. Fuer ein Fruehwarngeraet mit
    Monatsvorlauf ist die Abweichung ohne Bedeutung — sie darf aber nicht
    verschwiegen werden.
    """
    try:
        return d.replace(year=d.year + int(years))
    except ValueError:                     # 29.02. in einem Nicht-Schaltjahr
        return d.replace(year=d.year + int(years), day=28)


@dataclass(frozen=True)
class OffenceDeadline:
    """Die Fristrechnung fuer EINEN Tatbestand des Vorgabesatzes."""
    code: str
    norm: str
    zustand: str                    # 'berechnet' | 'ruht' | 'ohne_fassung'
    frist_jahre: Optional[int]
    frist_grundlage: Optional[str]
    ablauf_tag: Optional[str]       # ISO-Datum
    restlaufzeit_tage: Optional[int]
    fassung_von: Optional[str]
    fassung_bis: Optional[str]
    fundstelle: Optional[str]
    hinweis: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code, "norm": self.norm, "zustand": self.zustand,
            "frist_jahre": self.frist_jahre,
            "frist_grundlage": self.frist_grundlage,
            "ablauf_tag": self.ablauf_tag,
            "restlaufzeit_tage": self.restlaufzeit_tage,
            "fassung_von": self.fassung_von, "fassung_bis": self.fassung_bis,
            "fundstelle": self.fundstelle, "hinweis": self.hinweis,
        }


@dataclass(frozen=True)
class LimitationAssessment:
    """Die Einschaetzung fuer EINEN Fall."""
    aussage_moeglich: bool
    ampel: str                      # s. Modulkopf (fuenf Zustaende + 'keine_aussage')
    befund: str
    tatzeit_ts: Optional[int]
    tatzeit_tag: Optional[str]
    stichtag: str
    vorwarn_tage: int
    massgeblich_code: Optional[str]
    massgeblich_norm: Optional[str]
    massgeblich_ablauf_tag: Optional[str]
    restlaufzeit_tage: Optional[int]
    deadlines: Tuple[OffenceDeadline, ...]
    ohne_fassung: Tuple[str, ...]
    vorbehalte: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "aussage_moeglich": self.aussage_moeglich,
            "ampel": self.ampel,
            "befund": self.befund,
            "tatzeit_ts": self.tatzeit_ts,
            "tatzeit_tag": self.tatzeit_tag,
            "stichtag": self.stichtag,
            "vorwarn_tage": self.vorwarn_tage,
            "massgeblich_code": self.massgeblich_code,
            "massgeblich_norm": self.massgeblich_norm,
            "massgeblich_ablauf_tag": self.massgeblich_ablauf_tag,
            "restlaufzeit_tage": self.restlaufzeit_tage,
            "deadlines": [d.to_dict() for d in self.deadlines],
            "ohne_fassung": list(self.ohne_fassung),
            "vorbehalte": list(self.vorbehalte),
        }


def _tag(ts: int) -> date:
    """Unix-Sekunden -> UTC-Kalendertag (das Projekt rechnet durchgehend UTC)."""
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()


def assess_limitation(*, tatzeit_ts: Optional[int], params: LimitationParams,
                      now_ts: int,
                      offence_codes: Optional[Sequence[str]] = None,
                      vorwarn_tage: int = DEFAULT_VORWARN_TAGE
                      ) -> LimitationAssessment:
    """
    Die Fristeinschaetzung fuer einen Fall.

    tatzeit_ts     — Zeitpunkt der LETZTEN belegten Tathandlung (Unix-s) oder
                     None. Warum die letzte und nicht die erste: § 78a StGB
                     knuepft an die BEENDIGUNG der Tat an; die spaeteste belegte
                     Handlung ist die fristrechtlich guenstigste BELEGTE
                     Tatsache. (Ob mehrere Handlungen eine Tat im Rechtssinne
                     bilden, ist eine juristische Bewertung — das Werkzeug
                     trifft sie nicht und sagt das im Vorbehalt.)
    offence_codes  — die in Betracht kommenden Tatbestaende; None = der
                     Vorgabesatz aus dem Parametersatz.
    vorwarn_tage   — Schwelle fuer 'knapp'; faehrt in der Antwort mit.

    Die Funktion wirft NICHT. Jeder Zweifelsfall wird zu einem BENANNTEN
    Zustand — eine Ausnahme haette an dieser Stelle nur bedeutet, dass ein Fall
    aus der Liste verschwindet, und ein verschwundener Fall ist der
    gefaehrlichste (Grundregel 1).
    """
    now_ts = int(now_ts)
    stichtag = _tag(now_ts).isoformat()
    vorwarn = max(0, int(vorwarn_tage))
    vorbehalte = params.vorbehalte

    # (1) Kein bestaetigter Parametersatz -> KEINE Aussage, sondern der Grund.
    grund = params.verweigerungsgrund()
    if grund is not None:
        return LimitationAssessment(
            aussage_moeglich=False, ampel="keine_aussage", befund=grund,
            tatzeit_ts=(int(tatzeit_ts) if tatzeit_ts is not None else None),
            tatzeit_tag=(_tag(tatzeit_ts).isoformat()
                         if tatzeit_ts is not None else None),
            stichtag=stichtag, vorwarn_tage=vorwarn,
            massgeblich_code=None, massgeblich_norm=None,
            massgeblich_ablauf_tag=None, restlaufzeit_tage=None,
            deadlines=(), ohne_fassung=(), vorbehalte=vorbehalte)

    codes = tuple(offence_codes if offence_codes is not None
                  else params.vorgabe_tatbestaende)

    # (2) Kein Tatzeitpunkt -> UNGEPRUEFT (eigener Zustand, nicht 'gruen').
    if tatzeit_ts is None:
        return LimitationAssessment(
            aussage_moeglich=False, ampel="ohne_tatzeit",
            befund=BEFUND_OHNE_TATZEIT,
            tatzeit_ts=None, tatzeit_tag=None, stichtag=stichtag,
            vorwarn_tage=vorwarn, massgeblich_code=None,
            massgeblich_norm=None, massgeblich_ablauf_tag=None,
            restlaufzeit_tage=None, deadlines=(), ohne_fassung=(),
            vorbehalte=vorbehalte)

    tatzeit_tag = _tag(tatzeit_ts)
    deadlines: List[OffenceDeadline] = []
    ohne_fassung: List[str] = []

    for code in codes:
        fassung = params.fassung_am(code, tatzeit_tag)
        if fassung is None:
            # LUECKE WIRD GEMELDET, nicht ueberbrueckt (§ 2 Abs. 1 StGB).
            ohne_fassung.append(code)
            deadlines.append(OffenceDeadline(
                code=code, norm=code, zustand="ohne_fassung",
                frist_jahre=None, frist_grundlage=None, ablauf_tag=None,
                restlaufzeit_tage=None, fassung_von=None, fassung_bis=None,
                fundstelle=None,
                hinweis="Fuer den Tatzeitpunkt %s ist keine Fassung dieses "
                        "Tatbestands hinterlegt. Es wird NICHT mit einer "
                        "anderen Fassung gerechnet (Tatzeitrecht, § 2 Abs. 1 "
                        "StGB)." % tatzeit_tag.isoformat()))
            continue

        if fassung.ruht_bis_30:
            deadlines.append(OffenceDeadline(
                code=code, norm=fassung.norm, zustand="ruht",
                frist_jahre=fassung.frist_jahre,
                frist_grundlage=fassung.frist_grundlage,
                ablauf_tag=None, restlaufzeit_tage=None,
                fassung_von=fassung.gueltig_von,
                fassung_bis=fassung.gueltig_bis,
                fundstelle=fassung.fundstelle,
                hinweis="%s %s" % (BEFUND_RUHT, fassung.ruht_grundlage)))
            continue

        ablauf = add_years(tatzeit_tag, fassung.frist_jahre)
        rest = (ablauf - _tag(now_ts)).days
        deadlines.append(OffenceDeadline(
            code=code, norm=fassung.norm, zustand="berechnet",
            frist_jahre=fassung.frist_jahre,
            frist_grundlage=fassung.frist_grundlage,
            ablauf_tag=ablauf.isoformat(), restlaufzeit_tage=rest,
            fassung_von=fassung.gueltig_von, fassung_bis=fassung.gueltig_bis,
            fundstelle=fassung.fundstelle,
            hinweis="Frist %d Jahre ab %s (%s)."
                    % (fassung.frist_jahre, tatzeit_tag.isoformat(),
                       fassung.frist_grundlage)))

    # (3) Die MASSGEBLICHE Frist ist die frueheste berechnete.
    berechnet = [d for d in deadlines if d.zustand == "berechnet"]
    if berechnet:
        massgeblich = min(berechnet, key=lambda d: (d.ablauf_tag or "", d.code))
        rest = massgeblich.restlaufzeit_tage
        if rest is not None and rest <= 0:
            ampel, befund = "ueberschritten", BEFUND_UEBERSCHRITTEN
        elif rest is not None and rest < vorwarn:
            ampel = "knapp"
            befund = ("Restlaufzeit %d Tage (Vorwarnschwelle %d Tage). "
                      "Massgeblich: %s, Fristablauf %s."
                      % (rest, vorwarn, massgeblich.norm,
                         massgeblich.ablauf_tag))
        else:
            ampel = "offen"
            befund = ("Restlaufzeit %s Tage. Massgeblich: %s, Fristablauf %s."
                      % (rest, massgeblich.norm, massgeblich.ablauf_tag))
        return LimitationAssessment(
            aussage_moeglich=True, ampel=ampel, befund=befund,
            tatzeit_ts=int(tatzeit_ts), tatzeit_tag=tatzeit_tag.isoformat(),
            stichtag=stichtag, vorwarn_tage=vorwarn,
            massgeblich_code=massgeblich.code,
            massgeblich_norm=massgeblich.norm,
            massgeblich_ablauf_tag=massgeblich.ablauf_tag,
            restlaufzeit_tage=rest, deadlines=tuple(deadlines),
            ohne_fassung=tuple(ohne_fassung), vorbehalte=vorbehalte)

    # (4) Nichts berechenbar: entweder alles ruht, oder es fehlen die Fassungen.
    #     BEIDE Faelle bekommen ihren eigenen Befund — sie bedeuten Verschiedenes.
    if any(d.zustand == "ruht" for d in deadlines):
        return LimitationAssessment(
            aussage_moeglich=True, ampel="ruht", befund=BEFUND_RUHT,
            tatzeit_ts=int(tatzeit_ts), tatzeit_tag=tatzeit_tag.isoformat(),
            stichtag=stichtag, vorwarn_tage=vorwarn,
            massgeblich_code=None, massgeblich_norm=None,
            massgeblich_ablauf_tag=None, restlaufzeit_tage=None,
            deadlines=tuple(deadlines), ohne_fassung=tuple(ohne_fassung),
            vorbehalte=vorbehalte)

    return LimitationAssessment(
        aussage_moeglich=False, ampel="ohne_fassung",
        befund="Fuer den Tatzeitpunkt %s ist zu KEINEM der geprueften "
               "Tatbestaende (%s) eine Fassung hinterlegt. Es wurde nichts "
               "gerechnet und nichts geschaetzt."
               % (tatzeit_tag.isoformat(), ", ".join(codes) or "keine"),
        tatzeit_ts=int(tatzeit_ts), tatzeit_tag=tatzeit_tag.isoformat(),
        stichtag=stichtag, vorwarn_tage=vorwarn,
        massgeblich_code=None, massgeblich_norm=None,
        massgeblich_ablauf_tag=None, restlaufzeit_tage=None,
        deadlines=tuple(deadlines), ohne_fassung=tuple(ohne_fassung),
        vorbehalte=vorbehalte)


#: Die Zustaende, die eine Sicht darstellen muss. Als Konstante, damit ein
#  Frontend-Test sie gegen die Farbtabelle halten kann — ein neuer Zustand ohne
#  Farbe waere sonst unsichtbar.
AMPEL_ZUSTAENDE: Tuple[str, ...] = (
    "keine_aussage", "ohne_tatzeit", "ohne_fassung", "ruht",
    "ueberschritten", "knapp", "offen",
)
