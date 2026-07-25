# =============================================================================
# management/deadlines/limitation_params.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Zweck (Idee 32, Build 523):
#   Laedt und PRUEFT den Verjaehrungs-Parametersatz
#   (management/deadlines/limitation_params.json).
#
# WARUM DIE FRISTEN NICHT IM CODE STEHEN:
#   Die Frist ist eine rechtliche Bewertung mit unumkehrbarer Folge — eine
#   verjaehrte Tat ist nicht heilbar. Eine im Code versteckte Zahl waere nicht
#   ueberpruefbar. Im Parametersatz traegt JEDER Eintrag seine Fundstelle und
#   seine Gueltigkeitsspanne; aendert sich das Recht, aendert sich EINE
#   Datendatei und kein Programm.
#
# DIE SELBSTPRUEFUNG IST DER KERN DIESES MODULS:
#   Die Ladeschicht RECHNET DIE FRIST AUS DER HOECHSTSTRAFE NACH (§ 78 Abs. 3
#   StGB) und weist den Satz zurueck, wenn die hinterlegte Frist nicht dazu
#   passt. Damit kann ein Tippfehler in der Frist NICHT unbemerkt in eine
#   Fristaussage einfliessen — die Staffel des § 78 Abs. 3 ist der einzige Teil
#   des Rechts, der hier ALS REGEL codiert ist, und er ist so einfach, dass er
#   pruefbar bleibt.
#
#   Weitere Pruefungen (alle mit Verweigerung, nie mit Reparatur):
#     * unbekannte schema_version                     -> Fehler
#     * 'bestaetigt' true ohne Bestaetiger oder Datum -> Fehler
#     * Gueltigkeitsspannen desselben Codes ueberlappen sich -> Fehler
#     * ein Vorgabe-Tatbestand existiert nicht        -> Fehler
#     * fehlende Fundstelle oder fehlendes ruht_grundlage -> Fehler
#
#   WARUM VERWEIGERN UND NICHT REPARIEREN: eine automatisch "korrigierte" Frist
#   waere eine Behauptung des Werkzeugs anstelle einer belegten Rechtstatsache.
#   Lieber gar keine Aussage als eine, deren Herkunft niemand mehr kennt
#   (Grundregel 1).
#
# KEIN DATENBANKZUGRIFF, KEINE UHR. Der Pfad ist injizierbar -> testbar.
#
# Version: v0.8.523 · Build: 523 · 2026-07-25
# =============================================================================

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: Die einzige vom Code verstandene Schema-Fassung. Eine hoehere Nummer wird
#  ABGELEHNT (nicht "bestmoeglich" gelesen) — ein unbekanntes Feld koennte
#  genau die Einschraenkung sein, die die Aussage veraendert.
SCHEMA_VERSION = 1

#: Vorgabepfad des Parametersatzes (neben diesem Modul).
DEFAULT_PARAMS_PATH = Path(__file__).with_name("limitation_params.json")

#: Hoechstmass der zeitigen Freiheitsstrafe in Monaten (§ 38 Abs. 2 StGB).
#  Wird fuer 'nicht unter X Jahren'-Rahmen gebraucht, deren Hoechstmass sich
#  erst aus dem Allgemeinen Teil ergibt.
HOECHSTMASS_ZEITIG_MONATE = 180


class LimitationParamsError(ValueError):
    """Der Parametersatz ist unbrauchbar. Er wird NICHT teilweise verwendet."""


@dataclass(frozen=True)
class Offence:
    """
    Eine Fassung eines Tatbestands — die kleinste Einheit des Parametersatzes.

    code            — stabiler Bezeichner des Tatbestands (mehrere Fassungen
                      teilen ihn; sie unterscheiden sich in der Gueltigkeit).
    gueltig_von     — erster Tag der Geltung (ISO), einschliesslich.
    gueltig_bis     — letzter Tag der Geltung (ISO), einschliesslich; None =
                      bis heute.
    frist_jahre     — Verjaehrungsfrist in Jahren (§ 78 Abs. 3 StGB).
    ruht_bis_30     — True, wenn § 78b Abs. 1 Nr. 1 StGB greift. Dann weist der
                      Monitor KEINE Restlaufzeit aus (Opferalter unbekannt).
    """
    code: str
    norm: str
    bezeichnung: str
    gueltig_von: str
    gueltig_bis: Optional[str]
    strafrahmen: str
    hoechststrafe_monate: int
    hoechststrafe_grundlage: str
    frist_jahre: int
    frist_grundlage: str
    ruht_bis_30: bool
    ruht_grundlage: str
    fundstelle: str

    def gilt_am(self, tag: date) -> bool:
        """Gilt diese Fassung an einem bestimmten Tag (Tatzeitrecht, § 2 StGB)?"""
        if tag < date.fromisoformat(self.gueltig_von):
            return False
        if self.gueltig_bis is not None:
            if tag > date.fromisoformat(self.gueltig_bis):
                return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code, "norm": self.norm,
            "bezeichnung": self.bezeichnung,
            "gueltig_von": self.gueltig_von, "gueltig_bis": self.gueltig_bis,
            "strafrahmen": self.strafrahmen,
            "hoechststrafe_monate": self.hoechststrafe_monate,
            "hoechststrafe_grundlage": self.hoechststrafe_grundlage,
            "frist_jahre": self.frist_jahre,
            "frist_grundlage": self.frist_grundlage,
            "ruht_bis_30": self.ruht_bis_30,
            "ruht_grundlage": self.ruht_grundlage,
            "fundstelle": self.fundstelle,
        }


@dataclass(frozen=True)
class LimitationParams:
    """Der geladene, gepruefte Parametersatz."""
    schema_version: int
    stand: str
    bestaetigt: bool
    bestaetigt_von: Optional[str]
    bestaetigt_am: Optional[str]
    hinweis_unbestaetigt: str
    vorbehalte: Tuple[str, ...]
    vorgabe_tatbestaende: Tuple[str, ...]
    vorgabe_begruendung: str
    offences: Tuple[Offence, ...]
    fehlende_fassungen: Tuple[str, ...]

    # -- Zugriffe ------------------------------------------------------------

    def codes(self) -> Tuple[str, ...]:
        """Alle bekannten Tatbestands-Codes (ohne Doppelung, Reihenfolge stabil)."""
        out: List[str] = []
        for o in self.offences:
            if o.code not in out:
                out.append(o.code)
        return tuple(out)

    def fassung_am(self, code: str, tag: date) -> Optional[Offence]:
        """
        Die zur Tatzeit geltende Fassung — oder None.

        None ist ein BEFUND, kein Fehler: fehlt die Fassung, darf der Monitor
        NICHT auf eine spaetere ausweichen (§ 2 Abs. 1 StGB, Tatzeitrecht). Er
        meldet die Luecke stattdessen.
        """
        for o in self.offences:
            if o.code == code and o.gilt_am(tag):
                return o
        return None

    def verweigerungsgrund(self) -> Optional[str]:
        """
        Der Grund, aus dem keine Fristaussage gemacht werden darf — oder None.

        Heute genau ein Grund: der Satz ist nicht bestaetigt. Die Methode
        existiert trotzdem als eigene Stelle, damit spaetere Gruende (etwa ein
        abgelaufener Bestaetigungsstand) nicht in die Rechenschicht wandern.
        """
        if not self.bestaetigt:
            return self.hinweis_unbestaetigt
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "stand": self.stand,
            "bestaetigt": self.bestaetigt,
            "bestaetigt_von": self.bestaetigt_von,
            "bestaetigt_am": self.bestaetigt_am,
            "vorbehalte": list(self.vorbehalte),
            "vorgabe_tatbestaende": list(self.vorgabe_tatbestaende),
            "vorgabe_begruendung": self.vorgabe_begruendung,
            "tatbestaende": [o.to_dict() for o in self.offences],
            "fehlende_fassungen": list(self.fehlende_fassungen),
            "verweigerungsgrund": self.verweigerungsgrund(),
        }


# -- Die codierte Regel: § 78 Abs. 3 StGB -------------------------------------

def frist_aus_hoechststrafe(hoechststrafe_monate: int) -> int:
    """
    Die Verjaehrungsfrist in Jahren aus der Hoechststrafe (§ 78 Abs. 3 StGB).

    Nr. 1 (30 Jahre, lebenslange Freiheitsstrafe) ist hier bewusst NICHT
    abgebildet: keiner der verfahrensgegenstaendlichen Tatbestaende droht
    lebenslange Freiheitsstrafe, und ein Platzhalter fuer einen Fall, der nicht
    vorkommt, waere nur eine ungetestete Abzweigung. Kommt ein solcher
    Tatbestand hinzu, muss diese Funktion (und ihr Test) ERWEITERT werden — die
    Selbstpruefung erzwingt das, weil sonst 20 statt 30 Jahre herauskaeme und
    der Satz zurueckgewiesen wuerde.

    § 78 Abs. 4 StGB: es zaehlt der Rahmen des Tatbestands OHNE Schaerfungen
    oder Milderungen des Allgemeinen Teils und ohne minder schwere Faelle. Diese
    Auswahl trifft der Parametersatz (Feld 'hoechststrafe_grundlage'), nicht
    diese Funktion.
    """
    m = int(hoechststrafe_monate)
    if m <= 0:
        raise LimitationParamsError(
            "hoechststrafe_monate muss > 0 sein (war %r)" % hoechststrafe_monate)
    if m > 120:
        return 20      # § 78 Abs. 3 Nr. 2 — mehr als zehn Jahre
    if m > 60:
        return 10      # Nr. 3 — mehr als fuenf bis zehn Jahre
    if m > 12:
        return 5       # Nr. 4 — mehr als ein Jahr bis fuenf Jahre
    return 3           # Nr. 5 — uebrige Taten


# -- Laden + Pruefen ----------------------------------------------------------

def _need(node: Dict[str, Any], key: str, kontext: str) -> Any:
    if key not in node:
        raise LimitationParamsError("%s: Feld '%s' fehlt." % (kontext, key))
    return node[key]


def _iso(value: Any, kontext: str, feld: str) -> str:
    try:
        date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise LimitationParamsError(
            "%s: '%s' ist kein ISO-Datum (%r)." % (kontext, feld, value)) from exc
    return str(value)


def _offence_from(node: Dict[str, Any], idx: int) -> Offence:
    kontext = "tatbestaende[%d]" % idx
    code = str(_need(node, "code", kontext)).strip()
    if not code:
        raise LimitationParamsError("%s: 'code' ist leer." % kontext)

    gueltig_von = _iso(_need(node, "gueltig_von", kontext), kontext,
                       "gueltig_von")
    gueltig_bis = node.get("gueltig_bis")
    if gueltig_bis is not None:
        gueltig_bis = _iso(gueltig_bis, kontext, "gueltig_bis")
        if date.fromisoformat(gueltig_bis) < date.fromisoformat(gueltig_von):
            raise LimitationParamsError(
                "%s (%s): 'gueltig_bis' liegt vor 'gueltig_von'."
                % (kontext, code))

    try:
        hoechst = int(_need(node, "hoechststrafe_monate", kontext))
        frist = int(_need(node, "frist_jahre", kontext))
    except (TypeError, ValueError) as exc:
        raise LimitationParamsError(
            "%s (%s): hoechststrafe_monate/frist_jahre muessen ganze Zahlen "
            "sein." % (kontext, code)) from exc

    # DIE SELBSTPRUEFUNG: die Frist wird nachgerechnet.
    erwartet = frist_aus_hoechststrafe(hoechst)
    if frist != erwartet:
        raise LimitationParamsError(
            "%s (%s): hinterlegte Frist %d Jahre passt NICHT zur Hoechststrafe "
            "von %d Monaten — § 78 Abs. 3 StGB ergibt %d Jahre. Der "
            "Parametersatz wird nicht verwendet (kein automatisches Korrigieren "
            "einer Rechtstatsache)." % (kontext, code, frist, hoechst, erwartet))

    for pflicht in ("norm", "bezeichnung", "strafrahmen",
                    "hoechststrafe_grundlage", "frist_grundlage",
                    "ruht_grundlage", "fundstelle"):
        wert = _need(node, pflicht, "%s (%s)" % (kontext, code))
        if not str(wert).strip():
            raise LimitationParamsError(
                "%s (%s): '%s' ist leer — ohne Begruendung/Fundstelle ist der "
                "Eintrag kein Beleg." % (kontext, code, pflicht))

    ruht = _need(node, "ruht_bis_30", "%s (%s)" % (kontext, code))
    if not isinstance(ruht, bool):
        raise LimitationParamsError(
            "%s (%s): 'ruht_bis_30' muss true oder false sein (war %r) — ein "
            "unklarer Wert wuerde hier ueber eine Fristaussage entscheiden."
            % (kontext, code, ruht))

    return Offence(
        code=code, norm=str(node["norm"]),
        bezeichnung=str(node["bezeichnung"]),
        gueltig_von=gueltig_von, gueltig_bis=gueltig_bis,
        strafrahmen=str(node["strafrahmen"]),
        hoechststrafe_monate=hoechst,
        hoechststrafe_grundlage=str(node["hoechststrafe_grundlage"]),
        frist_jahre=frist, frist_grundlage=str(node["frist_grundlage"]),
        ruht_bis_30=bool(ruht), ruht_grundlage=str(node["ruht_grundlage"]),
        fundstelle=str(node["fundstelle"]))


def _pruefe_ueberlappungen(offences: Tuple[Offence, ...]) -> None:
    """
    Zwei Fassungen desselben Codes duerfen sich nicht ueberlappen.

    Warum das ein harter Fehler ist: bei Ueberlappung entschiede die
    REIHENFOLGE in der Datei darueber, welche Frist gilt. Eine Fristaussage,
    die von einer Dateireihenfolge abhaengt, ist nicht nachvollziehbar.
    """
    OFFEN = date(9999, 12, 31)
    nach_code: Dict[str, List[Offence]] = {}
    for o in offences:
        nach_code.setdefault(o.code, []).append(o)
    for code, gruppe in nach_code.items():
        spannen = sorted(
            ((date.fromisoformat(o.gueltig_von),
              OFFEN if o.gueltig_bis is None
              else date.fromisoformat(o.gueltig_bis), o) for o in gruppe),
            key=lambda t: t[0])
        for (a_von, a_bis, _a), (b_von, _b_bis, _b) in zip(spannen,
                                                           spannen[1:]):
            if b_von <= a_bis:
                raise LimitationParamsError(
                    "Tatbestand '%s': die Gueltigkeitsspannen %s..%s und ab %s "
                    "ueberlappen sich. Dann entschiede die Reihenfolge in der "
                    "Datei ueber die Frist — das ist nicht nachvollziehbar."
                    % (code, a_von.isoformat(),
                       "offen" if a_bis == OFFEN else a_bis.isoformat(),
                       b_von.isoformat()))


def load_params(path: Optional[Any] = None) -> LimitationParams:
    """
    Laedt den Parametersatz und PRUEFT ihn vollstaendig.

    Jeder Verstoss ist ein LimitationParamsError — der Satz wird NIE teilweise
    verwendet. Der Aufrufer (Endpunkt/CLI) meldet den Fehler im Klartext; die
    Sicht zeigt dann den Grund und keine Ampel.
    """
    p = Path(path) if path is not None else DEFAULT_PARAMS_PATH
    try:
        raw = json.loads(Path(p).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LimitationParamsError(
            "Parametersatz nicht gefunden: %s" % p) from exc
    except (ValueError, OSError) as exc:
        raise LimitationParamsError(
            "Parametersatz nicht lesbar (%s): %s" % (p, exc)) from exc

    if not isinstance(raw, dict):
        raise LimitationParamsError("Parametersatz ist kein JSON-Objekt.")

    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        raise LimitationParamsError(
            "Unbekannte schema_version %r (dieser Code versteht %d). Der Satz "
            "wird NICHT bestmoeglich gelesen — ein unbekanntes Feld koennte "
            "genau die Einschraenkung sein, die die Aussage aendert."
            % (version, SCHEMA_VERSION))

    bestaetigt = raw.get("bestaetigt")
    if not isinstance(bestaetigt, bool):
        raise LimitationParamsError(
            "'bestaetigt' muss true oder false sein (war %r)." % (bestaetigt,))
    bestaetigt_von = raw.get("bestaetigt_von")
    bestaetigt_am = raw.get("bestaetigt_am")
    if bestaetigt:
        if not str(bestaetigt_von or "").strip():
            raise LimitationParamsError(
                "'bestaetigt' ist true, aber 'bestaetigt_von' fehlt. Eine "
                "Bestaetigung ohne Bestaetiger ist kein Beleg.")
        _iso(bestaetigt_am, "bestaetigt_am", "bestaetigt_am")

    node_offences = raw.get("tatbestaende")
    if not isinstance(node_offences, list) or not node_offences:
        raise LimitationParamsError(
            "'tatbestaende' fehlt oder ist leer — ohne Tatbestaende gibt es "
            "keine Frist.")
    offences = tuple(_offence_from(n, i) for i, n in enumerate(node_offences))
    _pruefe_ueberlappungen(offences)

    vorgabe = raw.get("vorgabe_tatbestaende")
    if not isinstance(vorgabe, list) or not vorgabe:
        raise LimitationParamsError(
            "'vorgabe_tatbestaende' fehlt oder ist leer — der Monitor wuesste "
            "nicht, mit welchen Tatbestaenden er rechnen soll.")
    bekannt = {o.code for o in offences}
    unbekannt = [c for c in vorgabe if c not in bekannt]
    if unbekannt:
        raise LimitationParamsError(
            "vorgabe_tatbestaende nennt unbekannte Codes: %s"
            % ", ".join(map(str, unbekannt)))

    vorbehalte = raw.get("vorbehalte") or []
    if not isinstance(vorbehalte, list) or not vorbehalte:
        raise LimitationParamsError(
            "'vorbehalte' fehlt oder ist leer. Die Vorbehalte (Unterbrechung, "
            "Ruhen, Tatbestandswahl, Tagesgenauigkeit) sind PFLICHTBESTANDTEIL "
            "jeder Fristaussage — ohne sie waere die Zahl eine unbelegte "
            "Behauptung.")

    return LimitationParams(
        schema_version=SCHEMA_VERSION,
        stand=str(raw.get("stand") or "unbekannt"),
        bestaetigt=bestaetigt,
        bestaetigt_von=(str(bestaetigt_von) if bestaetigt_von else None),
        bestaetigt_am=(str(bestaetigt_am) if bestaetigt_am else None),
        hinweis_unbestaetigt=str(
            raw.get("hinweis_unbestaetigt")
            or "Der Parametersatz ist nicht als bestaetigt gekennzeichnet."),
        vorbehalte=tuple(str(v) for v in vorbehalte),
        vorgabe_tatbestaende=tuple(str(c) for c in vorgabe),
        vorgabe_begruendung=str(raw.get("vorgabe_begruendung") or ""),
        offences=offences,
        fehlende_fassungen=tuple(
            str(v) for v in (raw.get("fehlende_fassungen") or ())),
    )
