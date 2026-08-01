# =============================================================================
# core/setting_origin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Das Ergebnis EINER Wert-Aufloesung nach der projektweiten Vorrangregel
#
#       CLI-Argument  >  config.yaml  >  fester Vorgabewert
#
#   samt der Angabe, WOHER der Wert stammt. Der Wert allein genuegt nicht:
#   Genau die fehlende Herkunftsangabe hat den Vorfall aus Ticket 15429c75
#   so schwer auffindbar gemacht — das Werkzeug meldete einen Pfad, den
#   niemand uebergeben hatte, und nannte nicht, woher er kam.
#
# Forensische Relevanz:
#   Welche Datenbank ein Werkzeug oeffnet, entscheidet darueber, ueber
#   WELCHEN Bestand es Aussagen trifft. Ein Werkzeug, das nicht sagen kann,
#   woher sein Pfad stammt, liefert keinen ueberpruefbaren Befund
#   (Grundregel 1: kein Beleg darf still uebersprungen werden).
#
# Diese Datei enthaelt bewusst NUR die Datenklasse (Grundregel 10). Die
# Aufloesung selbst steht in core/setting_resolver.py.
#
# Abhaengigkeiten: dataclasses, typing — ausschliesslich Stdlib
# Version: v0.8.638 · Build: 638 · 2026-08-01
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple

#: Die zulaessigen Herkuenfte, in absteigendem Vorrang.
#:
#: 'argument'   — unmittelbar auf der Kommandozeile uebergeben.
#: 'abgeleitet' — aus einem ANDEREN Kommandozeilen-Argument gebildet (etwa das
#:                Datenverzeichnis aus dem Elternverzeichnis von
#:                --coordinator-db). Rangiert unter dem unmittelbaren
#:                Argument, aber UEBER config.yaml: die Grundlage ist eine
#:                Angabe des Aufrufers, keine Einstellung der Anlage.
#: 'config.yaml' — in der Konfigurationsdatei TATSAECHLICH EINGETRAGEN. Ein
#:                Wert, den nur der Coded Default des ConfigLoaders liefert,
#:                zaehlt hier NICHT — sonst waere die Herkunftsangabe falsch.
#: 'default'    — fester Vorgabewert des Werkzeugs.
HERKUENFTE: Tuple[str, ...] = ("argument", "abgeleitet", "config.yaml", "default")


class SettingOriginError(Exception):
    """Eine Herkunftsangabe ist in sich unstimmig."""


@dataclass(frozen=True)
class SettingOrigin:
    """
    Ein aufgeloester Einstellwert samt Herkunft.

    name     — die Benennung des Werts im Werkzeug (z. B. 'coordinator_db').
               Sie erscheint so in der Herkunftszeile und ist der Schluessel,
               unter dem eine Pruefung den Eintrag wiederfindet.
    wert     — der aufgeloeste Wert. Darf None sein, wenn ein Werkzeug einen
               Wert ausdruecklich als 'nicht gesetzt' fuehrt.
    herkunft — einer der Werte aus HERKUENFTE.
    quelle   — die konkrete Fundstelle im Klartext, also '--coordinator-db',
               'paths.coordinator_db aus config.yaml' oder 'Vorgabewert des
               Werkzeugs'. WARUM ZUSAETZLICH ZUR HERKUNFT: 'config.yaml'
               allein sagt nicht, WELCHER Eintrag gegriffen hat; bei zwei in
               Frage kommenden Eintraegen ist genau das die Frage.
    """
    name: str
    wert: Any
    herkunft: str
    quelle: str

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise SettingOriginError("Herkunftsangabe ohne Namen.")
        if self.herkunft not in HERKUENFTE:
            raise SettingOriginError(
                "%s: herkunft '%s' ist keine der zulaessigen (%s)."
                % (self.name, self.herkunft, ", ".join(HERKUENFTE)))
        if not str(self.quelle).strip():
            # Eine Herkunft ohne benannte Fundstelle waere kein Beleg,
            # sondern eine Behauptung.
            raise SettingOriginError(
                "%s: Fundstelle ('quelle') ist leer." % self.name)

    def zeile(self) -> str:
        """
        Eine Zeile fuer die Konsolenausgabe des Werkzeugs.

        Beispiel:
            coordinator_db = /srv/data/coordinator_2.db  [Argument --coordinator-db]
        """
        return "%s = %s  [%s]" % (self.name, self.wert, self.quelle)
