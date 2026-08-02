# =============================================================================
# management/help/anker_katalog.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H5)
# =============================================================================
# Zweck:
#   Die Zuordnung ANKERPRAEFIX -> SICHT-ID.
#
# WARUM ES DIESE DATEI GIBT (Befund waehrend H5, Build 592 - nicht geplant,
# sondern vorgefunden):
#   Beim Bau der Pilotsicht stellte sich heraus, dass die Oberflaeche BEREITS
#   Hilfe-Anker traegt: Build 548 hat im gemeinsamen Tabellen-Werkzeug
#   (cockpit_tablekit.js) die Funktionen hilfeAnker/titelMitHilfe eingefuehrt
#   und ueber tabelleAufbauen() auf fuenfzehn Sichten ausgerollt. Jeder
#   Spaltenkopf und jedes Bedienelement einer Listentabelle traegt seither ein
#   Attribut 'data-hilfe-id' der Form '<praefix>.<bereich>.<name>'. Der Kopf
#   von cockpit_capacity_pflege.js nennt sogar den Grund: "damit die spaetere
#   Hilfsdokumente-Bibliothek hier andocken kann, ohne dass jede Sicht noch
#   einmal angefasst werden muss."
#
#   DAS IST GENAU DIESE BIBLIOTHEK. Wir docken an - statt daneben ein zweites
#   Ankersystem aufzubauen. Das Konzept (§4.2) nennt Drift als Hauptrisiko;
#   zwei Attribute fuer dieselbe Sache waeren die Drift selbst.
#
#   EIN HAKEN: Die Praefixe sind die Namen, unter denen die TABELLE gefuehrt
#   wird, nicht immer die Sicht-ID des VIEW_CATALOG. Die Fall-Uebersicht
#   (Sicht 'faelle', Build 574) traegt Anker mit dem Praefix 'overview', weil
#   ihr Modul aelter ist als die Sicht. Die Rechte-Sicht 'policy' fuehrt ZWEI
#   Tabellen und damit zwei Praefixe. Diese Namen im Bestand umzubenennen
#   waere ein Eingriff in fuenfzehn laufende Sichten fuer einen rein
#   kosmetischen Gewinn - und jeder gespeicherte Bedienzustand (die Praefixe
#   dienen auch als Zustandsschluessel!) ginge dabei verloren. Deshalb: eine
#   ausdrueckliche Zuordnung an EINER Stelle, maschinell gegen den Bestand
#   geprueft.
#
# Version: v0.8.637 - Build: 637 - 2026-08-01
# =============================================================================

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from management.help.sicht_katalog import SICHT_IDS

#: Der reservierte Praefix der Shell-Kontexthilfe (gehoert zu keiner Sicht).
SHELL = "shell"

#: ANKERPRAEFIX -> SICHT-ID des VIEW_CATALOG.
#:
#: Belegt am Bestand (Build 592): die Werte stammen aus den Aufrufen
#: tabelleAufbauen({ sicht: '...' }) bzw. den SICHT-Konstanten der Module.
#: Wo Praefix und Sicht-ID uebereinstimmen, steht der Eintrag trotzdem hier -
#: damit die Liste VOLLZAEHLIG ist und nicht "die Ausnahmen" heisst.
ANKER_PRAEFIXE: Dict[str, str] = {
    # --- abweichend benannt (die interessanten Faelle) --------------------
    # Sicht 'faelle' (Build 574); das Modul cockpit_overview.js ist aelter
    # als die Sicht und heisst weiterhin 'overview'.
    "overview": "faelle",
    # Sicht 'policy' fuehrt ZWEI Tabellen: die Rechtevergabe und die
    # Rollenzuweisung. Beide Praefixe zeigen auf dasselbe Kapitel.
    "policy_grants": "policy",
    "policy_assign": "policy",
    # Sicht 'stats' fuehrt eine Zuweisungstabelle mit eigenem Praefix.
    "stats_assign": "stats",
    # Build 637 (Vorgang 17200856): Vier Sichten hatten bisher NUR Anker der
    # Form '<sicht>.<name>' (Titel, Kennzeile) und deshalb keinen Eintrag im
    # Verzeichnis der TABELLEN-Praefixe. Mit den Bedienungs-Marken tragen sie
    # jetzt auch '<sicht>.bedienung.<name>' - und SP04 verlangt zu Recht,
    # dass jeder benutzte Praefix hier zugeordnet ist. Praefix und Sicht-ID
    # stimmen bei allen vier ueberein; 'stats' kommt hinzu, weil die Sicht
    # neben ihrer Tabelle ('stats_assign') jetzt auch eigene Bedienelemente
    # hat.
    "capacity": "capacity",
    "qs": "qs",
    "stats": "stats",
    "viewprefs": "viewprefs",
    # Sicht 'support' fuehrt DREI Tabellen (Build 550): "Meine Sitzungen",
    # "An meinen Faellen", "Weitere Sitzungen". Jede hat eine eigene Kennung,
    # weil die Kennung zugleich der Schluessel der Zustandssicherung ist -
    # teilten sich die drei eine, ueberschriebe die zuletzt gezeichnete
    # Sortierung und Filter der beiden anderen. Alle drei zeigen auf dasselbe
    # Kapitel. (Nachgetragen Build 602 beim Verfassen der Kapitel; die
    # Kennungen werden in cockpit_support.js nicht als 'sicht: ...' gesetzt,
    # sondern als Feld einer Abschnittsliste - SP04 konnte sie deshalb nicht
    # von selbst finden.)
    "support_mine": "support",
    "support_oncase": "support",
    "support_weitere": "support",
    # Sicht 'capacity_pflege' fuehrt VIER Tabellen mit vier Kennungen
    # (Build 559): Arbeitszeiten, Abwesenheiten, Feiertage, Gruende. Die
    # Ueberschrift jedes Abschnitts und die Werkzeugleiste jeder Tabelle
    # tragen diese Kennungen. Nachgetragen Build 603 beim Verfassen der
    # Kapitel; die Kennungen werden in cockpit_capacity_pflege.js als
    # ARGUMENT uebergeben (bauen('capacity_worktime', ...)) und nicht als
    # 'sicht: ...' geschrieben - SP04 konnte sie deshalb nicht finden.
    "capacity_worktime": "capacity_pflege",
    "capacity_availability": "capacity_pflege",
    "capacity_holiday": "capacity_pflege",
    "capacity_reason": "capacity_pflege",

    # --- namensgleich (Praefix = Sicht-ID) --------------------------------
    "approval": "approval",
    # Build 595 (H7): die Sichten der Gruppe 'Ueberblick' setzen ihre Marken
    # selbst (handgebaute Tabellen bzw. Kacheln) und benutzen dafuer ihre
    # eigene Sicht-Kennung.
    "dashboard": "dashboard",
    "escalation": "escalation",
    "nextactions": "nextactions",
    "faelle": "faelle",
    "calendar": "calendar",
    "capacity_pflege": "capacity_pflege",
    "crossref": "crossref",
    "lectorate": "lectorate",
    "mentoring": "mentoring",
    # Build 653 (Ticket d60e893a): die Baustein-Module haben ihre
    # Schaltflaechenliste gegen eine Tabelle des gemeinsamen Werkzeugs
    # getauscht. Damit vergibt tabelleAufbauen() dort Anker der Form
    # 'modules.spalte.*' und 'modules.werkzeug.*'. Vorher trug die Sicht nur
    # handgesetzte Marken ('modules.titel', 'modules.bedienung.*'), und der
    # Praefix stand deshalb noch nicht in dieser Zuordnung.
    "modules": "modules",
    "mycases": "mycases",
    "myhistory": "myhistory",
    "personnel": "personnel",
    "promotion": "promotion",
    "reports": "reports",
    "results": "results",
    "support": "support",
}


class AnkerKatalogError(Exception):
    """Ein Ankerpraefix ist unbekannt oder zeigt auf keine Sicht."""


def sicht_zu_praefix(praefix: str) -> Optional[str]:
    """Die Sicht-ID zu einem Ankerpraefix, oder None (auch fuer 'shell')."""
    if praefix == SHELL:
        return None
    return ANKER_PRAEFIXE.get(praefix)


def praefixe_der_sicht(sicht_id: str) -> Tuple[str, ...]:
    """
    Alle Ankerpraefixe, die zu einer Sicht gehoeren - in stabiler Ordnung.
    Eine Sicht kann mehrere haben (siehe 'policy').
    """
    treffer = [p for p, s in ANKER_PRAEFIXE.items() if s == sicht_id]
    return tuple(sorted(treffer))


def sicht_zu_schluessel(schluessel: str) -> Optional[str]:
    """Die Sicht zu einem vollen Kontextschluessel ('overview.spalte.x')."""
    return sicht_zu_praefix(schluessel.split(".", 1)[0])


def verify_praefixe(sicht_ids: Iterable[str] = SICHT_IDS) -> None:
    """
    Jeder Praefix zeigt auf eine Sicht, die es im Katalog gibt, und der
    Shell-Praefix taucht hier NICHT auf (er gehoert bewusst zu keiner Sicht).
    """
    bekannt = set(sicht_ids)
    fehlend: List[str] = sorted(
        "%s -> %s" % (p, s) for p, s in ANKER_PRAEFIXE.items()
        if s not in bekannt)
    if fehlend:
        raise AnkerKatalogError(
            "Ankerpraefixe zeigen auf unbekannte Sichten: %s"
            % ", ".join(fehlend))
    if SHELL in ANKER_PRAEFIXE:
        raise AnkerKatalogError(
            "'%s' ist der Praefix der Shell-Kontexthilfe und darf keiner "
            "Sicht zugeordnet sein." % SHELL)
