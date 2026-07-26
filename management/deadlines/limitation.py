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
# BUILD 530 — ZWEI ORTHOGONALE ACHSEN STATT EINER LAENGEREN AMPEL:
#
#   Die Entscheidung von mc war Option C: der Monitor rechnet mit einem nicht
#   festgestellten Datum, kennzeichnet das Ergebnis aber als VORLAEUFIG. Ich
#   hatte dafuer einen weiteren Ampelzustand vorgeschlagen. Das war der falsche
#   Schnitt, und zwar aus einem pruefbaren Grund: 'vorlaeufig' ist keine ART von
#   Ampel, sondern eine Eigenschaft der GRUNDLAGE. Presst man beides in ein
#   Enum, wird 'vorlaeufig ueberschritten' unaussprechbar — und genau das ist
#   die operativ wichtigste Kombination (eine Frist ist rechnerisch abgelaufen,
#   und niemand hat das Datum je geprueft).
#
#   Deshalb gibt es jetzt DREI voneinander unabhaengige Angaben je Fall:
#
#     ampel        — die Rechtsfolge (unveraendert; 'ohne_anker' kommt hinzu).
#     feststellung — 'festgestellt' | 'vorlaeufig' | 'ohne'. Woher stammt das
#                    Datum, auf dem die Rechtsfolge beruht?
#     anker_art    — 'aktivitaet' | 'registrierung' | 'anmeldung' | 'keine'.
#                    WELCHES Datum ist es?
#
#   HEUTE IST JEDE ZEILE 'vorlaeufig'. Das ist kein Versehen: eine von einer
#   Ermittlerin FESTGESTELLTE Tatzeit gibt es in den ausgewerteten Datenbanken
#   noch nicht (Recherche 2026-07-25: die Tabelle 'annotations' in
#   db/evidence_db.py:258-275 fuehrt keine Tatzeitspalte). Der Zustand
#   'festgestellt' ist trotzdem gebaut und getestet — sonst muesste die Regel
#   'der Bericht zitiert nur Festgestelltes' spaeter nachtraeglich eingezogen
#   werden, und nachtraegliche Regeln sind die, die man vergisst.
#
# DER ERSATZANKER IST TATBESTANDSABHAENGIG (Build 529/530): Beruht das Datum
#   NICHT auf einer belegten Tathandlung, sondern auf Registrierung oder erster
#   protokollierter Anmeldung, dann wird nur fuer diejenigen Tatbestaende
#   gerechnet, deren Parametersatz-Eintrag das ausdruecklich zulaesst
#   (Offence.ersatzanker_zulaessig). Die uebrigen bekommen den Zustand
#   'ohne_anker' — sie verschwinden NICHT, sie werden nur nicht gerechnet.
#
#   RICHTUNG DES FEHLERS BEIM ERSATZANKER: Registrierung und erste Anmeldung
#   liegen am ANFANG der Zugehoerigkeit, § 78a StGB knuepft aber an die
#   BEENDIGUNG an. Ein daraus gerechneter Fristablauf ist also ZU FRUEH — der
#   Fall erscheint DRINGENDER als er ist. Fuer ein Fruehwarngeraet ist das die
#   vertretbare Richtung (Fehlalarm statt versaeumter Frist).
#
# Version: v0.8.530 · Build: 530 · 2026-07-25
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

#: Die Herkunft des Datums, auf dem die Rechtsfolge beruht (Build 530).
#  'aktivitaet'    — spaeteste belegte Tathandlung aus den Aktivitaetstabellen.
#  'registrierung' — ERSATZANKER: Zeitpunkt der Registrierung im Forum.
#  'anmeldung'     — ERSATZANKER: erste ueber die 100a-Massnahme protokollierte
#                    erfolgreiche Anmeldung.
#  'keine'         — es gibt kein Datum.
#  Build 535: 'tatzeit' ist hinzugekommen — die von einer Ermittlerin
#  FESTGESTELLTE Tatzeit aus annotation_tatzeit. Sie als 'aktivitaet' zu
#  fuehren waere falsch: anker_art sagt, WOHER das Datum stammt, und eine
#  Feststellung stammt nicht aus einer Aktivitaetstabelle. Sie ist auch KEIN
#  Ersatzanker (s. ERSATZANKER_ARTEN) — im Gegenteil, sie ist der staerkste
#  Anker, den es gibt, und unterliegt deshalb keiner tatbestandsbezogenen
#  Zulassung. Der Anker ANKER_ARTEN=4 aus Build 530 steigt damit auf 5; das ist
#  eine bewusste Anpassung, keine Umgehung.
ANKER_ARTEN: Tuple[str, ...] = ("tatzeit", "aktivitaet", "registrierung",
                                "anmeldung", "keine")

#: Die Ersatzanker — also die Anker, die KEINE belegte Tathandlung sind und
#  deshalb der tatbestandsbezogenen Zulassung beduerfen (§ 78a StGB).
ERSATZANKER_ARTEN: Tuple[str, ...] = ("registrierung", "anmeldung")

#: Die Belastbarkeit des Datums (Build 530). Orthogonal zur Ampel — s. Modulkopf.
FESTSTELLUNGEN: Tuple[str, ...] = ("festgestellt", "vorlaeufig", "ohne")

#: Der Vermerk, der JEDER vorlaeufigen Zeile beiliegt. Wortlaut ist Absicht: er
#  sagt, was fehlt (die Feststellung) UND was daraus folgt (keine Zitierfaehig-
#  keit im Bericht). Ein Vermerk, der nur 'vorlaeufig' sagt, wird ueberlesen.
VERMERK_VORLAEUFIG = (
    "VORLAEUFIG — das zugrunde liegende Datum ist von KEINER Ermittlerin "
    "festgestellt worden. Es stammt aus den gesicherten Daten und ist ein "
    "Arbeitswert fuer die Priorisierung. Der Bericht darf nur FESTGESTELLTE "
    "Daten zitieren."
)

#: Der Vermerk fuer Ersatzanker — zusaetzlich zum Vorlaeufigkeitsvermerk.
VERMERK_ERSATZANKER = (
    "ERSATZANKER: Es liegt KEINE belegte Tathandlung mit Zeitstempel vor. "
    "Gerechnet wurde ab %s. Dieser Zeitpunkt liegt am ANFANG der Zugehoerigkeit "
    "zum Forum, waehrend § 78a StGB an die BEENDIGUNG der Tat anknuepft — der "
    "Fristablauf ist damit ZU FRUEH angesetzt und der Fall erscheint "
    "DRINGENDER, als er nach den bekannten Tatsachen ist."
)

#: Die Marken, die dem Befund VORANGESTELLT werden. Kurz, damit der Befund
#  lesbar bleibt; der volle Wortlaut steht in 'anker_vermerke'. Als Konstanten,
#  damit ein Test sie pruefen kann, ohne den Befundtext zu zerlegen.
BEFUND_MARKE_VORLAEUFIG = "VORLAEUFIG —"
BEFUND_MARKE_ERSATZANKER = "ERSATZANKER —"

#: Der Befund, wenn ein Ersatzanker vorliegt, aber fuer keinen der geprueften
#  Tatbestaende verwendet werden darf.
BEFUND_OHNE_ANKER = (
    "Ein Ersatzanker liegt vor (%s), darf aber fuer KEINEN der geprueften "
    "Tatbestaende (%s) verwendet werden — der Parametersatz laesst ihn dort "
    "nicht zu. Es wurde nichts gerechnet und nichts geschaetzt. Der Fall ist "
    "damit NICHT unverdaechtig, sondern UNGEPRUEFT."
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
    # 'berechnet' | 'ruht' | 'ohne_fassung' | 'ohne_anker' (Build 530)
    zustand: str
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
    ampel: str                      # s. Modulkopf
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
    # -- Build 530: die beiden zur Ampel ORTHOGONALEN Achsen (s. Modulkopf) ----
    #: 'festgestellt' | 'vorlaeufig' | 'ohne' — Belastbarkeit des Datums.
    feststellung: str = "ohne"
    #: 'aktivitaet' | 'registrierung' | 'anmeldung' | 'keine' — Herkunft.
    anker_art: str = "keine"
    #: Die Vermerke zu Vorlaeufigkeit und Ersatzanker. Sie stehen NEBEN den
    #  Vorbehalten des Parametersatzes, weil sie fallbezogen sind und nicht
    #  satzbezogen — und sie duerfen deshalb nicht mit ihnen vermischt werden.
    anker_vermerke: Tuple[str, ...] = ()
    #: Tatbestaende, die wegen eines unzulaessigen Ersatzankers NICHT gerechnet
    #  wurden. Sie verschwinden nicht, sie werden benannt (Grundregel 1).
    ohne_anker: Tuple[str, ...] = ()

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
            "feststellung": self.feststellung,
            "anker_art": self.anker_art,
            "anker_vermerke": list(self.anker_vermerke),
            "ohne_anker": list(self.ohne_anker),
            # Der Bericht darf nur Festgestelltes zitieren. Damit diese Regel
            # nicht in jedem Aufrufer neu formuliert werden muss (und dabei
            # abweicht), faehrt sie als EIN Feld mit.
            "zitierfaehig": self.feststellung == "festgestellt",
        }


def _tag(ts: int) -> date:
    """Unix-Sekunden -> UTC-Kalendertag (das Projekt rechnet durchgehend UTC)."""
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()


#: Klartext je Ankerart — fuer den Vermerk. Als Tabelle, damit die Bezeichnung
#  an EINER Stelle steht und in Antwort, Vermerk und Sicht nicht auseinanderlaeuft.
ANKER_BEZEICHNUNG: Dict[str, str] = {
    # Build 535: bewusst "FRUEHESTEN" — bei mehreren festgestellten
    # Tatzeitraeumen verankert die frueheste Beendigung (Entscheidung mc
    # 2026-07-26). Das ist die Gegenrichtung zu 'aktivitaet', und der Text sagt
    # es, damit niemand die beiden Zeilen fuer dasselbe haelt.
    "tatzeit": "der FRUEHESTEN von einer Ermittlerin festgestellten "
               "Tatzeit-Beendigung",
    "aktivitaet": "der spaetesten belegten Tathandlung",
    "registrierung": "dem Registrierungsdatum (uid_profile.registered)",
    "anmeldung": "der ersten ueber die 100a-Massnahme protokollierten "
                 "erfolgreichen Anmeldung (uid_surveillance.logged_at)",
    "keine": "keinem Zeitpunkt",
}


def assess_limitation(*, tatzeit_ts: Optional[int], params: LimitationParams,
                      now_ts: int,
                      offence_codes: Optional[Sequence[str]] = None,
                      vorwarn_tage: int = DEFAULT_VORWARN_TAGE,
                      anker_art: str = "aktivitaet",
                      festgestellt: bool = False
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
    anker_art      — WOHER das Datum stammt (s. ANKER_ARTEN). Ein ERSATZANKER
                     ('registrierung'/'anmeldung') darf nur fuer diejenigen
                     Tatbestaende verwendet werden, deren Parametersatz-Eintrag
                     ihn zulaesst; die uebrigen bekommen 'ohne_anker'.
    festgestellt   — True, wenn eine Ermittlerin den Tatzeitpunkt FESTGESTELLT
                     hat. Heute nie: die Aktivitaetstabellen liefern belegte,
                     aber nicht festgestellte Zeitpunkte (s. Modulkopf).

    Die Funktion wirft NICHT. Jeder Zweifelsfall wird zu einem BENANNTEN
    Zustand — eine Ausnahme haette an dieser Stelle nur bedeutet, dass ein Fall
    aus der Liste verschwindet, und ein verschwundener Fall ist der
    gefaehrlichste (Grundregel 1).
    """
    now_ts = int(now_ts)
    stichtag = _tag(now_ts).isoformat()
    vorwarn = max(0, int(vorwarn_tage))
    vorbehalte = params.vorbehalte

    # Eine unbekannte Ankerart wird NICHT auf 'aktivitaet' zurechtgebogen — das
    # waere die staerkste Aussage aus dem schwaechsten Wissen. Sie wird zu
    # 'keine', und damit rechnet niemand.
    art = anker_art if anker_art in ANKER_ARTEN else "keine"
    if tatzeit_ts is None:
        art = "keine"
    ist_ersatz = art in ERSATZANKER_ARTEN

    # Ein Ersatzanker kann NIE 'festgestellt' sein — er ist per Definition kein
    # von einem Menschen bestimmter Tatzeitpunkt, sondern ein Hilfswert.
    if tatzeit_ts is None:
        feststellung = "ohne"
    elif festgestellt and not ist_ersatz:
        feststellung = "festgestellt"
    else:
        feststellung = "vorlaeufig"

    vermerke: List[str] = []
    if feststellung == "vorlaeufig":
        vermerke.append(VERMERK_VORLAEUFIG)
    if ist_ersatz:
        vermerke.append(VERMERK_ERSATZANKER % ANKER_BEZEICHNUNG[art])

    def _fertig(**kw: Any) -> LimitationAssessment:
        """Baut die Antwort und haengt die drei neuen Achsen IMMER an."""
        kw.setdefault("feststellung", feststellung)
        kw.setdefault("anker_art", art)
        kw.setdefault("anker_vermerke", tuple(vermerke))
        return LimitationAssessment(**kw)

    # (1) Kein bestaetigter Parametersatz -> KEINE Aussage, sondern der Grund.
    grund = params.verweigerungsgrund()
    if grund is not None:
        return _fertig(
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
        return _fertig(
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
    ohne_anker: List[str] = []

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

        if ist_ersatz and not fassung.ersatzanker_zulaessig:
            # DER ERSATZANKER TRAEGT DIESEN TATBESTAND NICHT. Er wird deshalb
            # NICHT gerechnet — aber auch nicht weggelassen. Die Begruendung
            # aus dem Parametersatz faehrt mit, damit die Entscheidung am Fall
            # nachlesbar ist und nicht in einer Datei gesucht werden muss.
            ohne_anker.append(code)
            deadlines.append(OffenceDeadline(
                code=code, norm=fassung.norm, zustand="ohne_anker",
                frist_jahre=fassung.frist_jahre,
                frist_grundlage=fassung.frist_grundlage,
                ablauf_tag=None, restlaufzeit_tage=None,
                fassung_von=fassung.gueltig_von,
                fassung_bis=fassung.gueltig_bis,
                fundstelle=fassung.fundstelle,
                hinweis="NICHT GERECHNET: der Parametersatz laesst einen "
                        "Ersatzanker fuer diesen Tatbestand nicht zu. "
                        "Begruendung: %s" % fassung.anker_grundlage))
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
        # Der Vorlaeufigkeitshinweis gehoert VOR den Befund, nicht dahinter:
        # wer die Zeile ueberfliegt, liest den Anfang. Der volle Wortlaut steht
        # in 'anker_vermerke' — hier steht nur die Marke, damit der Befund
        # lesbar bleibt.
        if feststellung == "vorlaeufig":
            befund = "%s %s" % (BEFUND_MARKE_VORLAEUFIG, befund)
        if ist_ersatz:
            befund = "%s %s" % (BEFUND_MARKE_ERSATZANKER, befund)
        return _fertig(
            aussage_moeglich=True, ampel=ampel, befund=befund,
            tatzeit_ts=int(tatzeit_ts), tatzeit_tag=tatzeit_tag.isoformat(),
            stichtag=stichtag, vorwarn_tage=vorwarn,
            massgeblich_code=massgeblich.code,
            massgeblich_norm=massgeblich.norm,
            massgeblich_ablauf_tag=massgeblich.ablauf_tag,
            restlaufzeit_tage=rest, deadlines=tuple(deadlines),
            ohne_fassung=tuple(ohne_fassung), vorbehalte=vorbehalte,
            ohne_anker=tuple(ohne_anker))

    # (4) Nichts berechenbar. DREI Lagen, die Verschiedenes bedeuten und
    #     deshalb NICHT zu einem Sammelbefund verschmolzen werden:
    #     ruht -> es gibt eine Fassung, sie ruht moeglicherweise.
    #     ohne_anker -> es gibt eine Fassung, aber der Anker traegt sie nicht.
    #     ohne_fassung -> es gibt gar keine Fassung.
    if any(d.zustand == "ruht" for d in deadlines):
        return _fertig(
            aussage_moeglich=True, ampel="ruht", befund=BEFUND_RUHT,
            tatzeit_ts=int(tatzeit_ts), tatzeit_tag=tatzeit_tag.isoformat(),
            stichtag=stichtag, vorwarn_tage=vorwarn,
            massgeblich_code=None, massgeblich_norm=None,
            massgeblich_ablauf_tag=None, restlaufzeit_tage=None,
            deadlines=tuple(deadlines), ohne_fassung=tuple(ohne_fassung),
            vorbehalte=vorbehalte, ohne_anker=tuple(ohne_anker))

    if ohne_anker:
        return _fertig(
            aussage_moeglich=False, ampel="ohne_anker",
            befund=BEFUND_OHNE_ANKER % (ANKER_BEZEICHNUNG[art],
                                        ", ".join(ohne_anker)),
            tatzeit_ts=int(tatzeit_ts), tatzeit_tag=tatzeit_tag.isoformat(),
            stichtag=stichtag, vorwarn_tage=vorwarn,
            massgeblich_code=None, massgeblich_norm=None,
            massgeblich_ablauf_tag=None, restlaufzeit_tage=None,
            deadlines=tuple(deadlines), ohne_fassung=tuple(ohne_fassung),
            vorbehalte=vorbehalte, ohne_anker=tuple(ohne_anker))

    return _fertig(
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
        vorbehalte=vorbehalte, ohne_anker=tuple(ohne_anker))


#: Die Zustaende, die eine Sicht darstellen muss. Als Konstante, damit ein
#  Frontend-Test sie gegen die Farbtabelle halten kann — ein neuer Zustand ohne
#  Farbe waere sonst unsichtbar. 'ohne_anker' seit Build 530.
AMPEL_ZUSTAENDE: Tuple[str, ...] = (
    "keine_aussage", "ohne_tatzeit", "ohne_fassung", "ohne_anker", "ruht",
    "ueberschritten", "knapp", "offen",
)
