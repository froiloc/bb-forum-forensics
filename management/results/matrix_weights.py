# =============================================================================
# management/results/matrix_weights.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3B (Build 536)
# =============================================================================
# Zweck:
#   Laedt und PRUEFT den Gewichtungssatz der Dringlichkeits-/Erkenntnislage-
#   Matrix (management/results/matrix_weights.json).
#
# WARUM DIE GEWICHTE NICHT IM CODE STEHEN:
#   Dieselbe Ueberlegung wie beim Verjaehrungs-Parametersatz (AP-3A): eine im
#   Code versteckte Zahl ist nicht ueberpruefbar. Hier kommt hinzu, dass die
#   Gewichte eine LEITUNGSENTSCHEIDUNG sind — sie sagen, welcher Fall zuerst
#   Arbeitskraft bekommt. Wer sie aendert, aendert die Arbeitsverteilung einer
#   Dienststelle. Das gehoert in eine Datendatei mit Begruendung je Eintrag,
#   nicht in eine Zuweisung im Quelltext.
#
# WAS DIESE SCHICHT PRUEFT — und warum sie verweigert statt zu reparieren:
#   * unbekannte schema_version                          -> Fehler
#   * fehlender oder negativer Gewichtswert               -> Fehler
#   * Tagesgrenzen nicht aufsteigend (knapp < mittel)      -> Fehler
#   * Schwellen ausserhalb 0..100                          -> Fehler
#   * fehlende Zweckbindung oder leere Vorbehalte          -> Fehler
#
#   Ein automatisch "korrigiertes" Gewicht waere eine Behauptung des Werkzeugs
#   anstelle einer Leitungsentscheidung. Lieber keine Matrix als eine, deren
#   Zahlen niemand beschlossen hat (Grundregel 1).
#
# WAS DIESE SCHICHT AUSDRUECKLICH NICHT PRUEFEN KANN:
#   Ob die Konfidenztabelle den AKTUELLEN Katalog vollstaendig abdeckt. Der
#   Katalog steht in coordinator.db (assessment_scale_item), und dieses Modul
#   hat keinen Datenbankzugriff — bewusst, denn dadurch bleibt es rein testbar.
#   Die Vollstaendigkeit prueft stattdessen der Test MW07 gegen den Seed, und
#   zur Laufzeit faengt UrgencyMatrix jeden unbekannten Code ab und BENENNT ihn
#   (er ergibt NIE stillschweigend 0). Das ist die Absicherung, die die
#   Entscheidung M-2 verlangt.
#
# KEIN DATENBANKZUGRIFF, KEINE UHR. Der Pfad ist injizierbar -> testbar.
# Version: v0.8.536 · Build: 536 · 2026-07-26
# =============================================================================

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

#: Die einzige Fassung, die diese Ladeschicht versteht.
SCHEMA_VERSION = 1

_VORGABE_PFAD = Path(__file__).resolve().parent / "matrix_weights.json"


class MatrixWeightsError(ValueError):
    """Der Gewichtungssatz ist unbrauchbar. Es wird KEINE Matrix gerechnet."""


@dataclass(frozen=True)
class MatrixGewichte:
    """Der gepruefte Gewichtungssatz."""

    stand: str
    zweckbindung: str
    vorbehalte: Tuple[str, ...]

    # --- Schwellen (Prozent des jeweils erreichbaren Hoechstwerts) ----------
    schwelle_dringlichkeit_prozent: int
    schwelle_erkenntnislage_prozent: int

    # --- Dringlichkeit -------------------------------------------------------
    frist_knapp: int
    frist_knapp_tage_bis: int
    frist_mittel: int
    frist_mittel_tage_bis: int
    wiedervorlage_ueberfaellig: int
    eskalation_aktiv: int
    liegezeit: int
    liegezeit_tage_ab: int
    unzugewiesen: int

    # --- Erkenntnislage ------------------------------------------------------
    abdeckung_max: int
    konfidenz: Mapping[str, int]
    identitaet: Mapping[str, int]
    ausgeschlossene_kriterien: Tuple[str, ...]

    # ------------------------------------------------------------ Hoechstwerte
    @property
    def dringlichkeit_max(self) -> int:
        """
        Der ERREICHBARE Hoechstwert der X-Achse.

        'frist_knapp' und 'frist_mittel' schliessen einander aus — es zaehlt
        nur der groessere. Ihn zu addieren waere ein Rechenfehler, der die
        Quadrantengrenze verschoebe, ohne dass es jemandem auffiele.
        """
        return (max(self.frist_knapp, self.frist_mittel)
                + self.wiedervorlage_ueberfaellig
                + self.eskalation_aktiv
                + self.liegezeit
                + self.unzugewiesen)

    @property
    def erkenntnislage_max(self) -> int:
        """Der erreichbare Hoechstwert der Y-Achse."""
        return (self.abdeckung_max
                + (max(self.konfidenz.values()) if self.konfidenz else 0)
                + (max(self.identitaet.values()) if self.identitaet else 0))

    @property
    def frist_max(self) -> int:
        """
        Der groesste FRISTBEITRAG allein (Build 539).

        Er faehrt in der Antwort mit, weil die Sicht ohne ihn nicht sagen kann,
        WIEVIEL fehlt, solange die Fristen nicht geladen sind. Sie soll das
        nicht aus 'dringlichkeit_max' zurueckrechnen muessen — eine solche
        Rechnung im Frontend waere eine zweite Stelle, an der die Gewichtung
        steht, und sie waere still falsch, sobald ein Beitrag hinzukommt.
        Dieselbe Ausschlussregel wie in dringlichkeit_max: 'frist_knapp' und
        'frist_mittel' schliessen einander aus.
        """
        return max(self.frist_knapp, self.frist_mittel)

    @property
    def schwelle_dringlichkeit(self) -> float:
        return self.dringlichkeit_max * self.schwelle_dringlichkeit_prozent / 100.0

    @property
    def schwelle_erkenntnislage(self) -> float:
        return self.erkenntnislage_max * self.schwelle_erkenntnislage_prozent / 100.0

    def to_dict(self) -> Dict[str, Any]:
        """Die Angaben, die in JEDER Antwort mitfahren muessen."""
        return {
            "gewichte_stand": self.stand,
            "zweckbindung": self.zweckbindung,
            "vorbehalte": list(self.vorbehalte),
            "dringlichkeit_max": self.dringlichkeit_max,
            # Build 539: der Fristanteil einzeln — die Sicht sagt damit, WIEVIEL
            # fehlt, solange die Fristen nicht geladen sind.
            "frist_max": self.frist_max,
            "erkenntnislage_max": self.erkenntnislage_max,
            "schwelle_dringlichkeit": round(self.schwelle_dringlichkeit, 2),
            "schwelle_erkenntnislage": round(self.schwelle_erkenntnislage, 2),
            "ausgeschlossene_kriterien": list(self.ausgeschlossene_kriterien),
            "konfidenz_punkte": dict(self.konfidenz),
            "identitaet_punkte": dict(self.identitaet),
        }


def _int_ab_null(quelle: Mapping[str, Any], schluessel: str, wo: str) -> int:
    if schluessel not in quelle:
        raise MatrixWeightsError("%s: '%s' fehlt." % (wo, schluessel))
    wert = quelle[schluessel]
    if isinstance(wert, bool) or not isinstance(wert, (int, float)):
        raise MatrixWeightsError(
            "%s: '%s' ist keine Zahl (%r)." % (wo, schluessel, wert))
    if wert < 0:
        raise MatrixWeightsError(
            "%s: '%s' ist negativ (%r). Ein negatives Gewicht wuerde "
            "Dringlichkeit ABZIEHEN — das ist in diesem Modell nicht "
            "vorgesehen und waere vermutlich ein Vorzeichenfehler."
            % (wo, schluessel, wert))
    return int(wert)


def _punktetabelle(quelle: Mapping[str, Any], schluessel: str,
                   wo: str) -> Dict[str, int]:
    tabelle = quelle.get(schluessel)
    if not isinstance(tabelle, dict) or not tabelle:
        raise MatrixWeightsError(
            "%s: '%s' fehlt oder ist leer." % (wo, schluessel))
    out: Dict[str, int] = {}
    for code, punkte in tabelle.items():
        if isinstance(punkte, bool) or not isinstance(punkte, (int, float)):
            raise MatrixWeightsError(
                "%s.%s: Punktwert von '%s' ist keine Zahl (%r)."
                % (wo, schluessel, code, punkte))
        if punkte < 0:
            raise MatrixWeightsError(
                "%s.%s: Punktwert von '%s' ist negativ." % (wo, schluessel, code))
        out[str(code)] = int(punkte)
    return out


def load_weights(pfad: Optional[Path] = None) -> MatrixGewichte:
    """
    Laedt den Gewichtungssatz und prueft ihn. Wirft MatrixWeightsError, wenn
    er unbrauchbar ist — es wird dann KEINE Matrix gerechnet.
    """
    p = Path(pfad) if pfad else _VORGABE_PFAD
    try:
        roh = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise MatrixWeightsError("Gewichtungssatz nicht gefunden: %s" % p)
    except (ValueError, OSError) as exc:
        raise MatrixWeightsError("Gewichtungssatz nicht lesbar (%s): %s"
                                 % (p, exc))

    if roh.get("schema_version") != SCHEMA_VERSION:
        raise MatrixWeightsError(
            "Unbekannte schema_version %r (erwartet %d). Ein neuerer "
            "Gewichtungssatz wird NICHT mit alten Regeln gelesen."
            % (roh.get("schema_version"), SCHEMA_VERSION))

    zweck = str(roh.get("zweckbindung") or "").strip()
    if not zweck:
        raise MatrixWeightsError(
            "Die Zweckbindung fehlt. Sie faehrt in JEDER Antwort mit; ohne sie "
            "waere die Matrix eine Zahl ohne Aussage darueber, was sie NICHT "
            "sagt (§ 261 StPO).")
    vorbehalte = tuple(str(v) for v in (roh.get("vorbehalte") or []))
    if not vorbehalte:
        raise MatrixWeightsError("Die Vorbehalte fehlen (mindestens einer).")

    schwellen = roh.get("schwellen") or {}
    sd = _int_ab_null(schwellen, "dringlichkeit_prozent", "schwellen")
    se = _int_ab_null(schwellen, "erkenntnislage_prozent", "schwellen")
    for name, wert in (("dringlichkeit_prozent", sd),
                       ("erkenntnislage_prozent", se)):
        if wert > 100:
            raise MatrixWeightsError(
                "schwellen.%s liegt ueber 100 (%d) — dann waere kein Fall je "
                "im oberen Quadranten." % (name, wert))

    d = roh.get("dringlichkeit") or {}
    e = roh.get("erkenntnislage") or {}

    frist_knapp_tage = _int_ab_null(d, "frist_knapp_tage_bis", "dringlichkeit")
    frist_mittel_tage = _int_ab_null(d, "frist_mittel_tage_bis", "dringlichkeit")
    if frist_mittel_tage <= frist_knapp_tage:
        raise MatrixWeightsError(
            "dringlichkeit: frist_mittel_tage_bis (%d) muss GROESSER sein als "
            "frist_knapp_tage_bis (%d). Sonst waere die mittlere Stufe nie "
            "erreichbar und die 20 Punkte toter Code."
            % (frist_mittel_tage, frist_knapp_tage))

    gewichte = MatrixGewichte(
        stand=str(roh.get("stand") or "?"),
        zweckbindung=zweck,
        vorbehalte=vorbehalte,
        schwelle_dringlichkeit_prozent=sd,
        schwelle_erkenntnislage_prozent=se,
        frist_knapp=_int_ab_null(d, "frist_knapp", "dringlichkeit"),
        frist_knapp_tage_bis=frist_knapp_tage,
        frist_mittel=_int_ab_null(d, "frist_mittel", "dringlichkeit"),
        frist_mittel_tage_bis=frist_mittel_tage,
        wiedervorlage_ueberfaellig=_int_ab_null(
            d, "wiedervorlage_ueberfaellig", "dringlichkeit"),
        eskalation_aktiv=_int_ab_null(d, "eskalation_aktiv", "dringlichkeit"),
        liegezeit=_int_ab_null(d, "liegezeit", "dringlichkeit"),
        liegezeit_tage_ab=_int_ab_null(d, "liegezeit_tage_ab", "dringlichkeit"),
        unzugewiesen=_int_ab_null(d, "unzugewiesen", "dringlichkeit"),
        abdeckung_max=_int_ab_null(e, "abdeckung_max", "erkenntnislage"),
        konfidenz=_punktetabelle(e, "konfidenz", "erkenntnislage"),
        identitaet=_punktetabelle(e, "identitaet", "erkenntnislage"),
        ausgeschlossene_kriterien=tuple(
            str(k) for k in (e.get("ausgeschlossene_kriterien") or ())),
    )

    if gewichte.dringlichkeit_max <= 0 or gewichte.erkenntnislage_max <= 0:
        raise MatrixWeightsError(
            "Mindestens eine Achse hat den Hoechstwert 0 — dann gibt es keine "
            "Quadranten, sondern nur eine Zeile.")

    logger.debug("Matrix-Gewichte geladen: Stand %s, X_max=%d, Y_max=%d",
                 gewichte.stand, gewichte.dringlichkeit_max,
                 gewichte.erkenntnislage_max)
    return gewichte
