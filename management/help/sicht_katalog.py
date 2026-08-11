# =============================================================================
# management/help/sicht_katalog.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H1)
# =============================================================================
# Zweck:
#   Python-Spiegel des VIEW_CATALOG aus management/server/static/cockpit.js.
#   Die Hilfe braucht die Sichtenliste serverseitig - fuer das Inhalts-
#   verzeichnis der Vollhilfe, fuer die Capability-Sperre (E1) und fuer die
#   Vollstaendigkeitspruefung "keine Sicht ohne Hilfekapitel".
#
#   WARUM EIN SPIEGEL UND KEINE ZWEITE WAHRHEIT (gesicherte Erkenntnis):
#   Der VIEW_CATALOG ist und bleibt die Quelle - er steuert die Navigation im
#   Browser. Dieses Modul ist bewusst NUR eine Abschrift. Damit die Abschrift
#   nicht driftet (Konzept_Hilfesysteme §4.2, Hauptrisiko "Drift"), parst
#   tests/test_help_katalog_paritaet.py den VIEW_CATALOG und erzwingt
#   Deckungsgleichheit in ID, Recht, Gruppe, Label, Stichworten, Reihenfolge
#   und dem Merkmal 'immer'. Eine neue Sicht in cockpit.js ohne Nachzug hier
#   bricht ab diesem Build den Regressionslauf.
#
#   REINE DATEN, keine Funktionen mit Seiteneffekt: kein DB-, Netz- oder
#   Uhrzugriff -> vollstaendig testbar (Vorbild: management/stats/glossary.py).
#
# Beleg der Abschrift: management/server/static/cockpit.js, VIEW_CATALOG
#   (43 Eintraege, 11 Gruppen; Stand Build 587b / 232e314).
#
# Version: v0.8.588 - Build: 588 - 2026-07-31
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


class SichtKatalogError(Exception):
    """Der Sichtenkatalog ist in sich widerspruechlich."""


@dataclass(frozen=True)
class SichtEintrag:
    """
    Eine Sicht des Cockpits, wie der VIEW_CATALOG sie fuehrt.

    cap    - Leitfaehigkeit; traegt den Scope-Tag. None nur bei 'immer'.
    caps   - any-of-Liste, falls mehrere Rechte genuegen (z. B. Berichts-
             Abnahme: approve ODER review). Leer = es gilt allein 'cap'.
    immer  - Sicht ohne Rechtepruefung. GENAU EIN Eintrag traegt das Merkmal
             ('viewprefs', Beleg cockpit.js:337-348). Fuer die Hilfe folgt
             daraus: dieses eine Kapitel ist immer sichtbar (Konzept §3.3).
    """
    id: str
    cap: Optional[str]
    caps: Tuple[str, ...]
    gruppe: str
    label: str
    stichworte: str
    immer: bool = False

    def rechte(self) -> Tuple[str, ...]:
        """
        Die Rechte, von denen EINES genuegt (any-of) - dieselbe Auflegung wie
        viewCaps() in cockpit.js:380-392. Bei 'immer' ist die Menge leer.
        """
        if self.caps:
            return self.caps
        if self.cap is None:
            return ()
        return (self.cap,)


# --- Der Spiegel -------------------------------------------------------------
# Reihenfolge = Nav- und Kapitelreihenfolge (wie im VIEW_CATALOG).
SICHT_KATALOG: Tuple[SichtEintrag, ...] = (
    SichtEintrag(
        "dashboard", "dashboard.view", (),
        "Ueberblick", "Dashboard",
        "ueberblick kacheln startseite lage zusammenfassung",
        False),
    SichtEintrag(
        "calendar", "external.view", (),
        "Ueberblick", "Kalender & Wiedervorlage",
        "termine wiedervorlage frist erinnerung monat woche kalender",
        False),
    SichtEintrag(
        "escalation", "escalation.view", (),
        "Ueberblick", "Eskalationen",
        "eskalation ueberfaellig alarm rot dringend liegengeblieben",
        False),
    SichtEintrag(
        "nextactions", "nextactions.view", (),
        "Ueberblick", "Nächstbeste Aktion",
        "vorschlag empfehlung naechster schritt todo aufgabe prioritaet",
        False),
    SichtEintrag(
        "assignment", "assignment.edit", (),
        "Fallsteuerung", "Zuweisung",
        "zuweisen verteilen sachbearbeiter zustaendigkeit uebertragen fall",
        False),
    SichtEintrag(
        "cases", "assignment.edit", (),
        "Fallsteuerung", "Fall-Erkennung",
        "fall anlegen erkennung neuaufnahme portal beschuldigter akte",
        False),
    # BUILD 698 (Vorgang 60fe72fb): Recht von 'dashboard.view' auf
    # 'caseoverview.view'. Muss dem VIEW_CATALOG in cockpit.js folgen — dieser
    # Katalog ist dessen Spiegel, und ein Spiegel, der etwas anderes zeigt,
    # macht die Hilfe an genau der Stelle falsch, an der jemand nachschlaegt,
    # warum er eine Sicht nicht sieht.
    SichtEintrag(
        "faelle", "caseoverview.view", (),
        "Fallsteuerung", "Fallübersicht",
        "fall uebersicht tabelle ampel liste alle faelle bestand prioritaet zuweisung",
        False),
    SichtEintrag(
        "mentoring", "mentoring.view", (),
        "Betreuung", "Ermittler-Betreuung",
        "betreuung mentor anleitung begleitung einarbeitung ermittler",
        False),
    SichtEintrag(
        "notes", "mentoring_notes.view", (),
        "Betreuung", "Betreuungs-Notizen",
        "notiz vermerk betreuungsnotiz gespraech protokoll",
        False),
    SichtEintrag(
        "reports", "reports.approve", ("reports.approve", "reports.review",),
        "Abnahme", "Berichts-Abnahme",
        "bericht abnahme pruefung freigeben entwurf vermerk akte",
        False),
    SichtEintrag(
        "lectorate", "reports.review", ("reports.review", "reports.approve",),
        "Abnahme", "Lektorat",
        "lektorat korrektur sprache rechtschreibung durchsicht text",
        False),
    SichtEintrag(
        "approval", "reports.approve", (),
        "Abnahme", "Chef-Freigabe",
        "freigabe chef leitung genehmigung siegel abschluss",
        False),
    SichtEintrag(
        "templates", "templates.edit", (),
        "Redaktion", "Platzhalter & Queries",
        "platzhalter query vorlage baustein variable feldnamen",
        False),
    SichtEintrag(
        "doctemplates", "templates.edit", (),
        "Redaktion", "Dokumentvorlagen",
        "dokumentvorlage vorlage bericht layout gliederung docx",
        False),
    SichtEintrag(
        "modules", "templates.edit", (),
        "Redaktion", "Baustein-Module",
        "baustein modul textbaustein module_key vorschau bibliothek",
        False),
    SichtEintrag(
        "results", "results.view", (),
        "Auswertung", "Ermittlungsergebnis",
        "ermittlungsergebnis erkenntnis befund ergebnis bewertung",
        False),
    SichtEintrag(
        "stats", "stats.export_sta", (),
        "Kennzahlen", "Statistiken (StA/Fuehrung)",
        "statistik kennzahl staatsanwaltschaft fuehrung zahlen diagramm",
        False),
    SichtEintrag(
        "planung", "stats.export_sta", (),
        "Kennzahlen", "Prognose & Gantt",
        "prognose gantt planung szenario termin dauer hochrechnung",
        False),
    SichtEintrag(
        "annostats", "stats.export_sta", (),
        "Auswertung", "Annotations-Statistik",
        "annotation markierung statistik tag schlagwort verteilung",
        False),
    SichtEintrag(
        "limitation", "limitation.view", (),
        "Auswertung", "Fristen (Verjaehrung)",
        "frist verjaehrung ablauf stichtag paragraph fristenkontrolle",
        False),
    SichtEintrag(
        "matrix", "matrix.view", (),
        "Auswertung", "Dringlichkeit & Erkenntnislage",
        "dringlichkeit erkenntnislage matrix gewichtung ampel prioritaet",
        False),
    SichtEintrag(
        "qs", "qs.view", (),
        "Kennzahlen", "QS & Metriken",
        "qualitaetssicherung stichprobe metrik pruefung vieraugen kontrolle",
        False),
    SichtEintrag(
        "workload", "workload.view", (),
        "Kennzahlen", "Lastverteilung",
        "last auslastung verteilung arbeitsmenge pensum ermittler",
        False),
    SichtEintrag(
        "capacity", "capacity.edit", (),
        "Kennzahlen", "Kapazitaet",
        "kapazitaet auswertung arbeitszeit verfuegbarkeit netto diagramm",
        False),
    SichtEintrag(
        "support", "support_history.view", (),
        "Kennzahlen", "Support-Historie",
        "support historie hilfe anfrage sitzung unterstuetzung",
        False),
    SichtEintrag(
        "mycases", "mycases.view", (),
        "Persoenlich", "Meine Auftraege",
        "meine auftraege eigene faelle zugewiesen persoenlich",
        False),
    SichtEintrag(
        "myhistory", "myhistory.view", (),
        "Persoenlich", "Meine Historie",
        "meine historie eigene taetigkeit verlauf chronik persoenlich",
        False),
    SichtEintrag(
        "policy", "policy.view", (),
        "Administration", "Rechte / Policy",
        "recht rolle policy berechtigung faehigkeit grant rbac",
        False),
    SichtEintrag(
        "integrity", "ops.view", (),
        "Administration", "Integritaet / Betrieb",
        "integritaet betrieb pruefsumme hashkette backup speicher system",
        False),
    SichtEintrag(
        "audit", "ops.view", (),
        "Administration", "Audit-Explorer",
        "audit beleg protokoll kette nachweis revision ereignis",
        False),
    SichtEintrag(
        "handover", "handover.view", (),
        "Administration", "Übergabe-Protokoll",
        "uebergabe protokoll schichtwechsel dienstuebergabe abgabe",
        False),
    SichtEintrag(
        "retention", "retention.view", (),
        "Administration", "Aufbewahrungsfristen",
        "aufbewahrung loeschfrist retention archivierung lebensdauer",
        False),
    SichtEintrag(
        "promotion", "ops.view", (),
        "Administration", "Fremdforum-Promotion",
        "fremdforum promotion externes forum uebernahme quelle",
        False),
    SichtEintrag(
        "releases", "release.view", (),
        "Administration", "Externe Fallfreigabe",
        "freigabe extern fallfreigabe lka verteilung weitergabe",
        False),
    SichtEintrag(
        "onboarding", "onboarding.view", (),
        "Betreuung", "Onboarding / Offboarding",
        "onboarding offboarding eintritt austritt checkliste zugang",
        False),
    SichtEintrag(
        "personnel", "personnel.view", (),
        "Personal", "Personalverwaltung",
        "personal person mitarbeiter rolle konto stammdaten ad",
        False),
    SichtEintrag(
        "crossref", "crossref.view", (),
        "Identitaeten", "Kreuzbezug",
        "kreuzbezug querverweis verbindung bezug verknuepfung",
        False),
    SichtEintrag(
        "crossfindings", "crossref.view", (),
        "Identitaeten", "Querfunde",
        "querfund fremder fall hinweis stpo rueckkanal meldung",
        False),
    SichtEintrag(
        "alias", "crossref.view", (),
        "Identitaeten", "Aliasse",
        "alias nickname zweitname benutzername schreibweise",
        False),
    SichtEintrag(
        "merge", "crossref.view", (),
        "Identitaeten", "Identitäts-Gruppen",
        "identitaet gruppe zusammenfuehren merge split person subjekt",
        False),
    SichtEintrag(
        "search", "evidence.fulltext_search", (),
        "Auswertung", "Volltextsuche",
        "volltextsuche suchen begriff fundstelle beweismittel text",
        False),
    SichtEintrag(
        "viewprefs", None, (),
        "Persoenlich", "Ansicht anpassen",
        "ansicht anpassen reihenfolge ausblenden navigation gruppen kacheln",
        True),
    SichtEintrag(
        "capacity_pflege", "capacity.edit", (),
        "Personal", "Kapazitaetspflege",
        "arbeitszeit urlaub krank schulung abwesenheit feiertag minuten pflege",
        False),
)

# Gruppenfolge, wie sie sich aus der Katalogreihenfolge ergibt (erstes
# Auftreten). Sie ist zugleich die Gliederung des Hilfe-Inhaltsverzeichnisses.
GRUPPEN_REIHENFOLGE: Tuple[str, ...] = (
    "Ueberblick",
    "Fallsteuerung",
    "Betreuung",
    "Abnahme",
    "Redaktion",
    "Auswertung",
    "Kennzahlen",
    "Persoenlich",
    "Administration",
    "Personal",
    "Identitaeten",
)

# Schnellzugriff. Bewusst als Modul-Konstante (reine Daten, kein Zustand).
SICHT_IDS: Tuple[str, ...] = tuple(s.id for s in SICHT_KATALOG)
_BY_ID: Dict[str, SichtEintrag] = {s.id: s for s in SICHT_KATALOG}


def sicht(sicht_id: str) -> Optional[SichtEintrag]:
    """Katalogeintrag zu einer Sicht-ID oder None."""
    return _BY_ID.get(sicht_id)


def sichten_der_gruppe(gruppe: str) -> List[SichtEintrag]:
    """Alle Sichten einer Nav-Gruppe in Katalogreihenfolge."""
    return [s for s in SICHT_KATALOG if s.gruppe == gruppe]


def verify_katalog_konsistent() -> None:
    """
    Innere Konsistenz des Spiegels (kein Vergleich mit cockpit.js - das tut
    der Paritaetstest):
      * keine doppelte Sicht-ID,
      * jede Gruppe steht in GRUPPEN_REIHENFOLGE und umgekehrt,
      * genau ein Eintrag mit immer=True, und der hat cap=None,
      * jeder Eintrag ohne 'immer' hat mindestens ein Recht,
      * Stichworte sind gesetzt (Grundstock des Suchindex, Konzept §3.3).
    Verstoss -> SichtKatalogError mit benannter Luecke (Grundregel 1).
    """
    ids = [s.id for s in SICHT_KATALOG]
    doppelt = sorted({i for i in ids if ids.count(i) > 1})
    if doppelt:
        raise SichtKatalogError("Doppelte Sicht-IDs: %s" % ", ".join(doppelt))

    im_katalog = []
    for s in SICHT_KATALOG:
        if s.gruppe not in im_katalog:
            im_katalog.append(s.gruppe)
    if tuple(im_katalog) != GRUPPEN_REIHENFOLGE:
        raise SichtKatalogError(
            "Gruppenfolge weicht ab: Katalog %s, Konstante %s"
            % (im_katalog, list(GRUPPEN_REIHENFOLGE)))

    immer = [s.id for s in SICHT_KATALOG if s.immer]
    if len(immer) != 1:
        raise SichtKatalogError(
            "Genau eine Sicht darf 'immer' sein, gefunden: %s"
            % (", ".join(immer) or "keine"))
    if _BY_ID[immer[0]].cap is not None:
        raise SichtKatalogError(
            "Die Sicht ohne Rechtepruefung (%s) darf keine Leitfaehigkeit "
            "tragen." % immer[0])

    ohne_recht = sorted(s.id for s in SICHT_KATALOG
                        if not s.immer and not s.rechte())
    if ohne_recht:
        raise SichtKatalogError(
            "Sichten ohne Recht und ohne 'immer': %s" % ", ".join(ohne_recht))

    ohne_stichworte = sorted(s.id for s in SICHT_KATALOG
                             if not (s.stichworte or "").strip())
    if ohne_stichworte:
        raise SichtKatalogError(
            "Sichten ohne Stichworte: %s" % ", ".join(ohne_stichworte))
