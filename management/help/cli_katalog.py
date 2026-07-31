# =============================================================================
# management/help/cli_katalog.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H15)
# =============================================================================
# Zweck:
#   Der Katalog der Kommandozeilen-Werkzeuge. EIN Grundeintrag je Werkzeug,
#   vollzaehlig: 64 Eintraege - 35 Verwaltungswerkzeuge unter management/,
#   14 Werkzeuge unter tools/, 9 Einzelskripte unmittelbar unter management/
#   und 6 Startskripte im Wurzelverzeichnis.
#
# WIE DIE ANGABEN ZUSTANDE KAMEN (Beleglage):
#   Jeder Eintrag ist am Quelltext geprueft, nicht aus dem Dateinamen
#   geschlossen. Geprueft wurden je Werkzeug: die argparse-'description', die
#   Unterbefehle, die tatsaechlichen Schreibpfade (CoordinatorWriter/AuditLog/
#   INSERT/UPDATE), die geoeffneten Datenbanken samt Oeffnungsart
#   ('mode=ro' oder schreibfaehig) und die Aussagen des Dateikopfes zum
#   Betrieb.
#
#   ZWEI BEFUNDE AUS DIESER PRUEFUNG, die eine oberflaechliche Aufnahme
#   falsch gemacht haette:
#     * workload_admin und support_overview_admin oeffnen coordinator.db
#       SCHREIBFAEHIG (ohne 'mode=ro'), fuehren aber keinen einzigen
#       Schreibvorgang aus. Sie sind LESEND. Wer nur die Verbindungsart
#       ansieht, traegt hier das Gegenteil ein.
#     * Mehrere Werkzeuge erzeugen eine AUSGABEDATEI (HTML, PDF, XLSX), ohne
#       eine Datenbank zu aendern. Sie sind LESEND; die erzeugte Datei steht
#       im Feld 'ausgabe'. Diese Unterscheidung entscheidet darueber, ob ein
#       Werkzeug unter den Migrationsvorbehalt faellt.
#
# WAS HIER NOCH FEHLT: die TIEFE (geprueft gefahrene Beispielaufrufe,
#   Exit-Codes, Warntexte). Sie kommt in H17/H18. Bis dahin fuehrt
#   fehlliste_cli_tiefe() jeden Eintrag ohne Tiefe namentlich - kein
#   stillschweigendes "kommt noch" (Grundregel 1).
#
# ADRESSAT: die Betriebsseite. Regel H-1 (Anwendersprache) gilt hier
#   ausdruecklich NICHT - die Begruendung steht im Kopf von cli_modell.py.
#
# Version: v0.8.606 - Build: 606 - 2026-07-31
# =============================================================================

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from management.help.cli_modell import (
    CliBefehl, CliBeispiel, CliEintrag, CliModellError, CliTiefe,
)

#: Arbeitsbereiche, in der Reihenfolge der Ausgabe.
GRUPPEN_REIHENFOLGE: Tuple[str, ...] = (
    "Fallsteuerung",
    "Personal und Rechte",
    "Kennzahlen und Berichte",
    "Identitaeten und Externe",
    "Betrieb und Sicherung",
    "Migration und Reparatur",
    "Diagnose",
    "Start und Einrichtung",
)


def _b(name: str, art: str, zweck: str) -> CliBefehl:
    """Kurzform fuer einen Unterbefehl."""
    return CliBefehl(name=name, art=art, zweck=zweck)


#: Wo die Beispiele dieses Builds gefahren wurden. EINE Stelle, damit der
#: Nachweis nicht in 60 Zeichenketten auseinanderlaeuft.
_GEPRUEFT = ("Build 609, 2026-07-31, gegen einen Wegwerf-Bestand "
             "(/tmp mit leeren Datenbanken), Python 3.13")

#: Der Nachweis fuer die Beispiele aus H18 (Build 613). Der Wegwerf-Bestand
#: ist diesmal VOLL EINGERICHTET und nicht bloss leer: erst
#: 'setup_coordinator_dev.py', dann 'python -m management.migrate' (alle 37
#: Migrationen angewandt, Belegkette 38 Eintraege). Auf einer nur angelegten,
#: nicht eingerichteten Datei brechen die Auswertungen mit 'no such table' ab -
#: ein Beispiel, das gegen einen solchen Bestand 'lief', haette nichts belegt.
_GEPRUEFT_613 = ("Build 613, 2026-07-31, gegen einen eingerichteten "
                 "Wegwerf-Bestand (/tmp, setup_coordinator_dev + alle 37 "
                 "Migrationen, keine Faelle), Python 3.13")

#: Der Nachweis fuer H18 Teil 2 (Build 614). Fuer die Diagnosewerkzeuge ist
#: derselbe eingerichtete Wegwerf-Bestand verwendet worden; die beiden
#: Netzlaufwerks-Diagnosen liefen zusaetzlich gegen ein eigenes Wegwerf-
#: Verzeichnis mit einer Attrappen-evidence-Datenbank.
_GEPRUEFT_614 = ("Build 614, 2026-07-31, gegen einen eingerichteten "
                 "Wegwerf-Bestand unter /tmp, Python 3.13, Linux - KEIN "
                 "Netzlaufwerk")


def _bsp(aufruf: str, wirkung: str, geprueft: str = _GEPRUEFT) -> CliBeispiel:
    """Kurzform fuer einen GEFAHRENEN Beispielaufruf."""
    return CliBeispiel(aufruf=aufruf, wirkung=wirkung, geprueft=geprueft)


CLI_KATALOG: Tuple[CliEintrag, ...] = (
    # -------------------------------------------------------------- Fallsteuerung
    CliEintrag(
        schluessel="cases_admin",
        pfad="management/cases/cases_admin.py",
        aufruf="python -m management.cases.cases_admin --subject-id N [...]",
        titel="Fallakten pflegen",
        gruppe="Fallsteuerung",
        zweck="Auditierte Verwaltung der Fallakten: anlegen, zuweisen, "
              "Status, Prioritaet und Vermerk setzen.",
        art="schreibend",
        datenbanken=("coordinator.db (schreibend)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        beleg=True,
        befehle=(
            _b("", "schreibend",
               "Ohne Aenderungsoption liest der Aufruf nur; jede gesetzte "
               "Option (--assign/--status/--priority/--note) schreibt."),
        ),
        hinweis="Der Normalweg ist die Cockpit-Sicht; dies ist der "
                "Betriebsweg fuer Skripte und Nachpflege.",
    ),
    CliEintrag(
        schluessel="case_events_admin",
        pfad="management/case_events/case_events_admin.py",
        aufruf="python -m management.case_events.case_events_admin "
               "list|add --subject-id N",
        titel="Ereigniszeitstrahl je Fall",
        gruppe="Fallsteuerung",
        zweck="Den Ereigniszeitstrahl eines Falls anzeigen und um einen "
              "eigenen Eintrag ergaenzen.",
        art="gemischt",
        datenbanken=("coordinator.db (list lesend, add schreibend)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        beleg=True,
        befehle=(
            _b("list", "lesend", "Die Ereignisse eines Falls ausgeben."),
            _b("add", "schreibend",
               "Einen Eintrag von Hand ergaenzen. Die automatisch "
               "gespiegelten Ereignisse entstehen nicht hier."),
        ),
    ),
    CliEintrag(
        schluessel="escalation_admin",
        pfad="management/cases/escalation_admin.py",
        aufruf="python -m management.cases.escalation_admin [--json]",
        titel="Eskalationsregeln auswerten",
        gruppe="Fallsteuerung",
        zweck="Die Eskalationsregel-Auswertung ausgeben - dieselbe Rechnung "
              "wie in der Cockpit-Sicht.",
        art="lesend",
        datenbanken=("coordinator.db (lesend, mode=ro)",),
        betrieb="Der Betrieb darf weiterlaufen; die Verbindung nimmt keine "
                "Schreibsperre.",
    ),
    CliEintrag(
        schluessel="handover_admin",
        pfad="management/cases/handover_admin.py",
        aufruf="python -m management.cases.handover_admin "
               "[--subject-id N] [--json]",
        titel="Uebergabeprotokoll",
        gruppe="Fallsteuerung",
        zweck="Das Uebergabe- und Umverteilungsprotokoll ausgeben, wahlweise "
              "auf einen Fall eingeschraenkt.",
        art="lesend",
        datenbanken=("coordinator.db (lesend, mode=ro)",),
        betrieb="Der Betrieb darf weiterlaufen.",
    ),
    CliEintrag(
        schluessel="next_actions_admin",
        pfad="management/cases/next_actions_admin.py",
        aufruf="python -m management.cases.next_actions_admin "
               "[--scope alle|eigene] [--json]",
        titel="Naechstbeste Aktion",
        gruppe="Fallsteuerung",
        zweck="Die Auftragsliste 'naechstbeste Aktion' ausgeben.",
        art="lesend",
        datenbanken=("coordinator.db (lesend, mode=ro)",),
        betrieb="Der Betrieb darf weiterlaufen.",
    ),
    CliEintrag(
        schluessel="dashboard_admin",
        pfad="management/dashboard/dashboard_admin.py",
        aufruf="python -m management.dashboard.dashboard_admin "
               "list|export-html",
        titel="Ampel-Uebersicht",
        gruppe="Fallsteuerung",
        zweck="Die Ampel-Uebersicht der Faelle ausgeben oder als "
              "eigenstaendiges HTML erzeugen.",
        art="lesend",
        datenbanken=("coordinator.db (lesend)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        befehle=(
            _b("list", "lesend", "Uebersicht auf der Konsole."),
            _b("export-html", "lesend",
               "Eigenstaendiges HTML mit Erzeugungsvermerk (--out)."),
        ),
        ausgabe="HTML-Datei bei export-html (--out).",
    ),
    CliEintrag(
        schluessel="limitation_admin",
        pfad="management/deadlines/limitation_admin.py",
        aufruf="python -m management.deadlines.limitation_admin "
               "pruefen|zeigen|rechnen",
        titel="Verjaehrungsparameter",
        gruppe="Fallsteuerung",
        zweck="Den Verjaehrungs-Parametersatz pruefen, anzeigen und eine "
              "Fristeinschaetzung nachrechnen.",
        art="lesend",
        datenbanken=(),
        betrieb="Beruehrt keine Datenbank und braucht keinen laufenden "
                "Betrieb; gelesen wird nur die Parameterdatei.",
        befehle=(
            _b("pruefen", "lesend", "Parametersatz laden und pruefen."),
            _b("zeigen", "lesend", "Hinterlegte Fassungen listen."),
            _b("rechnen", "lesend", "Eine Fristeinschaetzung nachrechnen."),
        ),
    ),
    CliEintrag(
        schluessel="qs_admin",
        pfad="management/qs/qs_admin.py",
        aufruf="python -m management.qs.qs_admin liste|zeigen|nachziehen "
               "--db data/coordinator.db",
        titel="QS-Stichprobe",
        gruppe="Fallsteuerung",
        zweck="QS-Stichproben ansehen und nachrechnen. Rein lesend - ein "
              "Schreibweg auf der Kommandozeile waere ein unauditierter "
              "Nebeneingang.",
        art="lesend",
        datenbanken=("coordinator.db (lesend, mode=ro)",),
        betrieb="Braucht KEINEN laufenden Betrieb und laeuft auch gegen eine "
                "gesicherte Kopie der coordinator.db.",
        befehle=(
            _b("liste", "lesend", "Stichproben auflisten."),
            _b("zeigen", "lesend", "Eine Stichprobe im Einzelnen."),
            _b("nachziehen", "lesend",
               "Die Stichprobe nachrechnen. Exit 1 bedeutet Abweichung - "
               "das ist ein Befund, kein Programmfehler."),
        ),
    ),
    CliEintrag(
        schluessel="results_admin",
        pfad="management/results/results_admin.py",
        aufruf="python -m management.results.results_admin <befehl>",
        titel="Ermittlungsergebnis bewerten",
        gruppe="Fallsteuerung",
        zweck="Die Bewertung des Ermittlungsergebnisses erfassen und "
              "auswerten; erfasst wird ausschliesslich ergaenzend.",
        art="gemischt",
        datenbanken=("coordinator.db (assess schreibend, sonst lesend)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        beleg=True,
        befehle=(
            _b("catalog", "lesend", "Bewertungskatalog anzeigen."),
            _b("assess", "schreibend",
               "Bewertung erfassen - immer als NEUE Zeile."),
            _b("current", "lesend", "Aktueller Stand."),
            _b("history", "lesend", "Volle Historie."),
            _b("score", "lesend", "Vorlaeufige Kennzahl."),
            _b("stats", "lesend", "Auswertung ueber alle Faelle."),
            _b("coverage", "lesend",
               "Abdeckung je Fall, samt der nie bewerteten. Exit 2 meldet "
               "solche blinden Flecken, damit ein Skript sie sieht."),
        ),
    ),
    CliEintrag(
        schluessel="catalog_admin",
        pfad="management/results/catalog_admin.py",
        aufruf="python -m management.results.catalog_admin <befehl> --actor X",
        titel="Bewertungskatalog pflegen",
        gruppe="Fallsteuerung",
        zweck="Den Bewertungskatalog pflegen: Skalen, Merkmale und Kriterien "
              "anlegen und ausser Dienst stellen.",
        art="schreibend",
        datenbanken=("coordinator.db (schreibend)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        beleg=True,
        befehle=(
            _b("add-scale", "schreibend", "Eine Skala anlegen."),
            _b("add-item", "schreibend", "Ein Merkmal anlegen."),
            _b("add-criterion", "schreibend", "Ein Kriterium anlegen."),
            _b("set-quality", "schreibend",
               "Einem Kriterium nachtraeglich eine Skala geben."),
            _b("deprecate", "schreibend",
               "Ausser Dienst stellen. KEIN Loeschen - ein hartes Loeschen "
               "wuerde bestehende Ergebnisse unlesbar machen."),
        ),
        hinweis="Jeder Aufruf verlangt --actor. Es gibt keinen lesenden "
                "Unterbefehl; zum Ansehen dient results_admin catalog.",
    ),

    # --------------------------------------------------------- Personal, Rechte
    CliEintrag(
        schluessel="person_admin",
        pfad="management/person/person_admin.py",
        aufruf="python -m management.person.person_admin list|create|update",
        titel="Ermittlerstammdaten",
        gruppe="Personal und Rechte",
        zweck="Auditierte Verwaltung der Ermittlerstammdaten.",
        art="gemischt",
        datenbanken=("coordinator.db (create/update schreibend, "
                     "list lesend)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        beleg=True,
        befehle=(
            _b("list", "lesend", "Personen auflisten."),
            _b("create", "schreibend", "Person anlegen."),
            _b("update", "schreibend", "Stammdaten aendern."),
        ),
    ),
    CliEintrag(
        schluessel="rbac_admin",
        pfad="management/rbac/rbac_admin.py",
        aufruf="python -m management.rbac.rbac_admin <befehl>",
        titel="Rechte-Matrix pflegen",
        gruppe="Personal und Rechte",
        zweck="Auditierte Verwaltung der Rechte-Matrix: Rechte an Rollen "
              "vergeben und Rollen an Personen zuweisen.",
        art="gemischt",
        datenbanken=("coordinator.db (Vergabe/Zuweisung schreibend, "
                     "Listen lesend; 'catalog' oeffnet gar keine Datenbank)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        beleg=True,
        befehle=(
            _b("catalog", "lesend",
               "Den im Code hinterlegten Katalog der Rollen und Rechte "
               "ausgeben - ohne Datenbank."),
            _b("grant", "schreibend", "Einer Rolle ein Recht geben."),
            _b("revoke-grant", "schreibend",
               "Ein Recht zuruecknehmen. Kein Loeschen, sondern Widerruf."),
            _b("assign-role", "schreibend",
               "Einer Person eine Rolle zuweisen."),
            _b("revoke-role", "schreibend",
               "Eine Rollenzuweisung widerrufen."),
            _b("list-grants", "lesend", "Vergebene Rechte auflisten."),
            _b("list-roles", "lesend", "Rollenzuweisungen auflisten."),
        ),
        hinweis="Dies ist die einzige Stelle, an der die Zuordnung Rolle -> "
                "Recht gepflegt wird; die Cockpit-Sicht 'Rechte / Policy' "
                "zeigt sie nur an.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.rbac.rbac_admin catalog",
                     "Gibt Rollen und Rechte aus, ohne eine Datenbank zu "
                     "oeffnen. Im Versuch: 8 Rollen, danach die Rechte, "
                     "Rueckgabewert 0."),
            ),
            exit_codes=((0, "erledigt"), (1, "Fehler")),
            warnungen=(
                "'revoke-grant' und 'revoke-role' loeschen nicht, sie "
                "widerrufen. Die Zeile bleibt als Beleg erhalten.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="ad_sync_admin",
        pfad="management/ad_sync/ad_sync_admin.py",
        aufruf="python -m management.ad_sync.ad_sync_admin preview|apply",
        titel="AD-Abgleich",
        gruppe="Personal und Rechte",
        zweck="Die Ermittlerstammdaten gegen das Active Directory abgleichen "
              "- erst als Vorschau, dann als Vollzug.",
        art="gemischt",
        datenbanken=("coordinator.db (preview lesend, apply schreibend)",),
        betrieb="Der Betrieb darf weiterlaufen. 'apply' ist INTERAKTIV und "
                "verlangt eine aktive aufsichtfuehrende Person.",
        beleg=True,
        befehle=(
            _b("preview", "lesend", "Vorschau - rein lesend."),
            _b("apply", "schreibend",
               "Vollzug. Fragt bei Deaktivierungen nach."),
        ),
        hinweis="Braucht Zugriff auf das Verzeichnis (LDAP); die Abfrage "
                "kann dauern.",
    ),
    CliEintrag(
        schluessel="capacity_admin",
        pfad="management/capacity/capacity_admin.py",
        aufruf="python -m management.capacity.capacity_admin <aktion>",
        titel="Kapazitaetsdaten pflegen",
        gruppe="Personal und Rechte",
        zweck="Arbeitszeiten, Feiertage, Abwesenheitsgruende und "
              "Abwesenheiten pflegen - die Grundlage der Kapazitaetsrechnung.",
        art="gemischt",
        datenbanken=("coordinator.db (list-* lesend, alles Uebrige "
                     "schreibend)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        beleg=True,
        befehle=(
            _b("set-worktime", "schreibend",
               "Arbeitszeit ab einem Stichtag setzen (neue Zeile)."),
            _b("remove-worktime", "schreibend",
               "Arbeitszeitregel stilllegen - die Zeile bleibt erhalten."),
            _b("replace-worktime", "schreibend",
               "Regel ersetzen: stilllegen und neu schreiben in EINEM "
               "Vorgang, mit zwei Belegen."),
            _b("list-worktime", "lesend", "Arbeitszeitregeln auflisten."),
            _b("add-holiday", "schreibend", "Feiertag anlegen."),
            _b("remove-holiday", "schreibend", "Feiertag stilllegen."),
            _b("list-holidays", "lesend", "Feiertage auflisten."),
            _b("add-reason", "schreibend", "Abwesenheitsgrund anlegen."),
            _b("list-reasons", "lesend", "Abwesenheitsgruende auflisten."),
            _b("set-availability", "schreibend", "Abwesenheit erfassen."),
            _b("remove-availability", "schreibend",
               "Abwesenheit stilllegen."),
            _b("list-availability", "lesend", "Abwesenheiten auflisten."),
        ),
    ),
    CliEintrag(
        schluessel="onboarding_admin",
        pfad="management/onboarding/onboarding_admin.py",
        aufruf="python -m management.onboarding.onboarding_admin "
               "steps|show|set",
        titel="Onboarding-Checkliste",
        gruppe="Personal und Rechte",
        zweck="Den Stand der Onboarding-/Offboarding-Checkliste ansehen und "
              "einzelne Schritte setzen.",
        art="gemischt",
        datenbanken=("coordinator.db (set schreibend, show lesend; "
                     "'steps' oeffnet keine Datenbank)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        beleg=True,
        befehle=(
            _b("steps", "lesend", "Den Schritt-Katalog ausgeben."),
            _b("show", "lesend", "Stand der Checkliste einer Person."),
            _b("set", "schreibend",
               "Einen Schritt setzen. 'offen' setzt ihn zurueck und "
               "entfernt die Zeile."),
        ),
    ),
    CliEintrag(
        schluessel="support_overview_admin",
        pfad="management/support_overview/support_overview_admin.py",
        aufruf="python -m management.support_overview.support_overview_admin "
               "list|export-html",
        titel="Support-Historie",
        gruppe="Personal und Rechte",
        zweck="Die Historie der Unterstuetzungssitzungen ausgeben oder als "
              "HTML erzeugen; die Angaben stammen aus dem Protokollbuch.",
        art="lesend",
        datenbanken=("coordinator.db (nur gelesen; die Verbindung ist "
                     "technisch schreibfaehig, es wird aber nichts "
                     "geschrieben)",),
        betrieb="Der Betrieb darf weiterlaufen. 'export-html' rechnet die "
                "gesamte Belegkette nach; bei grossen Bestaenden dauert das.",
        befehle=(
            _b("list", "lesend", "Sitzungen auf der Konsole."),
            _b("export-html", "lesend",
               "Eigenstaendiges HTML mit Erzeugungsvermerk (--out)."),
        ),
        ausgabe="HTML-Datei bei export-html (--out).",
    ),
    CliEintrag(
        schluessel="workload_admin",
        pfad="management/workload/workload_admin.py",
        aufruf="python -m management.workload.workload_admin list|export-html",
        titel="Lastverteilung",
        gruppe="Personal und Rechte",
        zweck="Die Fallverteilung je ermittelnder Person ausgeben oder als "
              "HTML erzeugen.",
        art="lesend",
        datenbanken=("coordinator.db (nur gelesen; Verbindung technisch "
                     "schreibfaehig, ohne Schreibvorgang)",),
        betrieb="Der Betrieb darf weiterlaufen. 'export-html' rechnet die "
                "gesamte Belegkette nach.",
        befehle=(
            _b("list", "lesend", "Verteilung auf der Konsole."),
            _b("export-html", "lesend",
               "Eigenstaendiges HTML mit Erzeugungsvermerk (--out)."),
        ),
        ausgabe="HTML-Datei bei export-html (--out).",
    ),
    CliEintrag(
        schluessel="overload_admin",
        pfad="management/workload/overload_admin.py",
        aufruf="python -m management.workload.overload_admin [--json]",
        titel="Ueberlastwarnung",
        gruppe="Personal und Rechte",
        zweck="Die aktiven Ueberlastwarnungen je ermittelnder Person "
              "ausgeben; die Schwellen stehen in der Konfiguration.",
        art="lesend",
        datenbanken=("coordinator.db (lesend, mode=ro)",),
        betrieb="Der Betrieb darf weiterlaufen.",
    ),

    # ------------------------------------------------- Kennzahlen und Berichte
    CliEintrag(
        schluessel="annotation_stats_admin",
        pfad="management/stats/annotation_stats_admin.py",
        aufruf="python -m management.stats.annotation_stats_admin [--json]",
        titel="Annotations-Statistik",
        gruppe="Kennzahlen und Berichte",
        zweck="Die Verteilung der Annotationen nach Kategorie und Schlagwort "
              "ausgeben.",
        art="lesend",
        datenbanken=("coordinator.db (lesend, mode=ro)",
                     "evidence_<uid>.db (lesend, mode=ro)"),
        betrieb="Der Betrieb darf weiterlaufen; die Fall-Datenbanken werden "
                "ausschliesslich lesend geoeffnet.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.stats.annotation_stats_admin "
                     "--coordinator-db ./data/coordinator.db --evidence-dir "
                     "./data/evidence --json",
                     "Gab die Verteilung als JSON aus. Auf dem eingerichteten "
                     "Wegwerf-Bestand: cases_total 0, cases_with_evidence 0, "
                     "cases_without_evidence 0. Rueckgabewert 0.",
                     _GEPRUEFT_613),
            ),
            exit_codes=((0, "ausgegeben"),
                        (1, "kein coordinator.db-Pfad - weder ueber "
                            "--coordinator-db noch aus der config.yaml")),
            warnungen=(
                "OHNE --coordinator-db UND --evidence-dir greift das Werkzeug "
                "auf ./data/... zu, und zwar relativ zum aktuellen "
                "Verzeichnis. Wer es aus der Bestandswurzel aufruft, wertet "
                "damit den PRODUKTIVEN Bestand aus - lesend zwar, aber "
                "unbeabsichtigt.",
                "Eine fehlende evidence_<uid>.db ist KEIN Fehler: der Fall "
                "wird als 'ohne Beweismittel-Datenbank' gezaehlt und im Kopf "
                "der Ausgabe ausgewiesen. Er verschwindet nicht still.",
                "'--scope eigene' ohne --person-id liefert null Faelle. Das "
                "ist kein Fehler und sieht wie ein Ergebnis aus - es ist "
                "keines.",
                "Die Laufzeit waechst mit der Fallzahl: je Fall wird eine "
                "eigene Datei geoeffnet. Auf einem Netzlaufwerk ist das "
                "spuerbar.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="forecast_admin",
        pfad="management/stats/forecast_admin.py",
        aufruf="python -m management.stats.forecast_admin [--json]",
        titel="Abbau-Prognose",
        gruppe="Kennzahlen und Berichte",
        zweck="Die Prognose zum Abbau des Rueckstands in drei Szenarien "
              "ausgeben.",
        art="lesend",
        datenbanken=("coordinator.db (lesend, mode=ro)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.stats.forecast_admin "
                     "--coordinator-db ./data/coordinator.db --no-capacity "
                     "--json",
                     "Gab die drei Szenarien als JSON aus. Auf dem leeren "
                     "Bestand: Rueckstand 0, beobachtete Rate 0,0, "
                     "Beobachtungsfenster 30 Tage. Rueckgabewert 0.",
                     _GEPRUEFT_613),
            ),
            exit_codes=((0, "ausgegeben"),
                        (1, "kein coordinator.db-Pfad, oder "
                            "--lookback-days 0 bzw. negativ")),
            warnungen=(
                "KEIN RUECKGABEWERT MELDET 'keine belastbare Prognose'. Das "
                "steht nur im Text bzw. als data_sufficient=false im JSON. "
                "Wer allein den Rueckgabewert auswertet, haelt ein "
                "Nullergebnis fuer einen Erfolg.",
                "Der Kapazitaetsteil ist ausdruecklich 'nach bestem "
                "Vermoegen': fehlende Kapazitaetsdaten lassen den Lauf "
                "durchgehen und werden nur als Annahme vermerkt. "
                "--no-capacity schaltet ihn ganz ab und macht den Lauf "
                "schneller.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="forecast_report_admin",
        pfad="management/stats/forecast_report_admin.py",
        aufruf="python -m management.stats.forecast_report_admin "
               "--out prognose.pdf --format pdf",
        titel="Prognosebericht",
        gruppe="Kennzahlen und Berichte",
        zweck="Den Prognosebericht als HTML oder PDF erzeugen.",
        art="lesend",
        datenbanken=("coordinator.db (lesend, mode=ro)",),
        betrieb="Fuer den Stapelbetrieb gedacht und ohne Browsersitzung "
                "lauffaehig; der Betrieb darf weiterlaufen.",
        ausgabe="HTML- oder PDF-Datei (--out).",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.stats.forecast_report_admin "
                     "--coordinator-db ./data/coordinator.db --out "
                     "./prognose.html --format html",
                     "Schrieb den Bericht. Die Schlusszeile nannte "
                     "ausdruecklich die Datenlage: 'Backlog 0, KEINE "
                     "belastbare Prognose (keine Abschluesse im Fenster)'. "
                     "Rueckgabewert 0.",
                     _GEPRUEFT_613),
            ),
            exit_codes=((0, "Bericht geschrieben - AUCH DANN, wenn die "
                            "Datenlage keine Prognose traegt"),
                        (1, "kein coordinator.db-Pfad, --lookback-days 0 "
                            "bzw. negativ, oder reportlab fehlt (nur bei "
                            "--format pdf)")),
            warnungen=(
                "DAS VORGABEFORMAT IST PDF und setzt reportlab voraus. Fuer "
                "einen Lauf ohne diese Abhaengigkeit '--format html' "
                "angeben.",
                "FAELLT DER ERZEUGUNGSRAHMEN AUS, ENTSTEHT DER BERICHT "
                "TROTZDEM - mit Buildnummer 0 und Ersteller 'unbekannt', und "
                "zwar ohne Meldung. Bei einem Bericht, der aus dem Haus geht, "
                "ist der Erzeugungsvermerk deshalb vor der Weitergabe "
                "anzusehen.",
                "--out ueberschreibt eine vorhandene Datei wortlos.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="gantt_admin",
        pfad="management/stats/gantt_admin.py",
        aufruf="python -m management.stats.gantt_admin [--json]",
        titel="Balkenplan",
        gruppe="Kennzahlen und Berichte",
        zweck="Die Fall-Balken je ermittelnder Person ausgeben - die "
              "Datengrundlage der Gantt-Ansicht.",
        art="lesend",
        datenbanken=("coordinator.db (lesend, mode=ro)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.stats.gantt_admin "
                     "--coordinator-db ./data/coordinator.db --json",
                     "Gab die Balken als JSON aus. Auf dem leeren Bestand: "
                     "total_bars 0, lanes leer, range_start und range_end "
                     "beide null. Rueckgabewert 0.",
                     _GEPRUEFT_613),
            ),
            exit_codes=((0, "ausgegeben"),
                        (1, "kein coordinator.db-Pfad")),
            warnungen=(
                "Die Konsolenausgabe ist EINE ZEILE JE FALL. Bei realer "
                "Fallzahl ist das nichts zum Ueberfliegen - fuer die "
                "Weiterverarbeitung '--json' verwenden.",
                "Faelle ohne Zuweisung erscheinen in einer eigenen Spur. Sie "
                "fehlen nicht, sie stehen nur nicht bei einer Person.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="glossary_admin",
        pfad="management/stats/glossary_admin.py",
        aufruf="python -m management.stats.glossary_admin "
               "list|check|export-html",
        titel="Kennzahlen-Glossar",
        gruppe="Kennzahlen und Berichte",
        zweck="Das Glossar der Kennzahlen ausgeben, auf Vollstaendigkeit "
              "pruefen oder als HTML erzeugen.",
        art="lesend",
        datenbanken=("coordinator.db (nur bei export-html und nur, wenn "
                     "--coordinator-db gesetzt ist; lesend, mode=ro)",),
        betrieb="Der Betrieb darf weiterlaufen. 'list' und 'check' oeffnen "
                "gar keine Datenbank.",
        befehle=(
            _b("list", "lesend", "Definitionen ausgeben."),
            _b("check", "lesend",
               "Vollstaendigkeit pruefen. Exit 1 meldet eine Luecke - ein "
               "Befund, kein Programmfehler."),
            _b("export-html", "lesend",
               "Eigenstaendiges Glossar-HTML erzeugen (--out)."),
        ),
        ausgabe="HTML-Datei bei export-html (--out).",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.stats.glossary_admin check",
                     "Meldete 'OK - jede erzeugte Kennzahl ist definiert' und "
                     "nannte die Zahl der Eintraege. Rueckgabewert 0.",
                     _GEPRUEFT_613),
                _bsp("python -m management.stats.glossary_admin export-html "
                     "--out ./glossar.html --coordinator-db "
                     "./data/coordinator.db",
                     "Schrieb die Definitionen als eigenstaendige HTML-Datei "
                     "(ohne aeussere Verweise) und nannte ihre Zahl. "
                     "Rueckgabewert 0.",
                     _GEPRUEFT_613),
            ),
            exit_codes=((0, "ausgegeben bzw. geschrieben"),
                        (1, "BEFUND: mindestens eine erzeugte Kennzahl hat "
                            "keine Definition. Das ist kein Programmfehler, "
                            "sondern die Luecke, die dieses Werkzeug suchen "
                            "soll")),
            warnungen=(
                "'list' und 'check' oeffnen GAR KEINE Datenbank - sie pruefen "
                "den Bestand statisch. Sie sind damit in jedem "
                "Betriebszustand aufrufbar.",
                "'export-html' liest die coordinator.db nur, wenn "
                "--coordinator-db gesetzt ist. Ohne die Angabe entsteht die "
                "Datei OHNE Kettenspitze; das steht dann auf der "
                "Fehlerausgabe, aendert den Rueckgabewert aber nicht.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="status_report_admin",
        pfad="management/stats/status_report_admin.py",
        aufruf="python -m management.stats.status_report_admin "
               "--out bericht.pdf --format pdf",
        titel="Statusbericht",
        gruppe="Kennzahlen und Berichte",
        zweck="Den Statusbericht fuer die Staatsanwaltschaft als HTML oder "
              "PDF erzeugen.",
        art="lesend",
        datenbanken=("coordinator.db (lesend, mode=ro)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        ausgabe="HTML- oder PDF-Datei (--out).",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.stats.status_report_admin "
                     "--coordinator-db ./data/coordinator.db --out "
                     "./bericht.html --format html",
                     "Schrieb den Bericht; die Schlusszeile nannte die Zahl "
                     "der beruecksichtigten Faelle (hier '0 Faelle'). "
                     "Rueckgabewert 0.",
                     _GEPRUEFT_613),
            ),
            exit_codes=((0, "Bericht geschrieben"),
                        (1, "kein coordinator.db-Pfad, oder reportlab fehlt "
                            "(nur bei --format pdf)")),
            warnungen=(
                "DAS VORGABEFORMAT IST PDF und setzt reportlab voraus.",
                "Wie beim Prognosebericht: FAELLT DER ERZEUGUNGSRAHMEN AUS, "
                "entsteht der Bericht trotzdem - mit Buildnummer 0 und "
                "Ersteller 'unbekannt', ohne Meldung.",
                "FEHLT EINE TABELLE, gibt es hier einen rohen Programmabbruch "
                "und nicht die handlungsleitende Meldung, die "
                "'export_admin' in derselben Lage ausgibt. Der Bestand ist "
                "dann zuerst zu migrieren.",
                "--person-id schaltet den Umfang auf die Faelle EINER Person.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="export_admin",
        pfad="management/export/export_admin.py",
        aufruf="python -m management.export.export_admin "
               "case-status-xlsx --out fall.xlsx",
        titel="Management-Exporte",
        gruppe="Kennzahlen und Berichte",
        zweck="Auswertungen ueber das einheitliche Export-Verfahren "
              "ausgeben; derzeit die Fallstatus-Uebersicht als Tabelle.",
        art="lesend",
        datenbanken=("coordinator.db (lesend, mode=ro)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        befehle=(
            _b("case-status-xlsx", "lesend",
               "Fallstatus-Uebersicht als Tabellendatei."),
        ),
        ausgabe="XLSX-Datei (--out).",
        hinweis="Der Erzeugungsvermerk nennt den Stand der Belegkette; vor "
                "einem produktiven Lauf sind die Pruefsummen der "
                "eingesetzten Dateien zu bestaetigen.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.export.export_admin "
                     "case-status-xlsx --coordinator-db "
                     "./data/coordinator.db --out ./faelle.xlsx --actor "
                     "KENNUNG",
                     "Schrieb die Mappe (im Versuch 5774 Bytes, mit "
                     "Datendigest im Blatt) und nannte die Zahl der Faelle. "
                     "Rueckgabewert 0. Auf der FEHLERAUSGABE stand "
                     "zusaetzlich, dass die angegebene Kennung keinem "
                     "Personendatensatz zugeordnet ist - der Lauf ging "
                     "trotzdem durch.",
                     _GEPRUEFT_613),
            ),
            exit_codes=((0, "Mappe geschrieben"),
                        (1, "kein coordinator.db-Pfad, eine benoetigte "
                            "Tabelle fehlt (mit Hinweis auf die Migration), "
                            "oder openpyxl fehlt"),
                        (2, "Aufruffehler - der Unterbefehl fehlt")),
            warnungen=(
                "EINE GEBROCHENE BELEGKETTE AENDERT DEN RUECKGABEWERT NICHT. "
                "Sie erscheint auf der Fehlerausgabe, der Export laeuft und "
                "endet mit 0. Wer den Export weitergibt, muss die "
                "Fehlerausgabe gelesen haben - der Rueckgabewert allein sagt "
                "es nicht.",
                "OHNE --actor und ohne passenden Personendatensatz steht "
                "'unbekannt' im Erzeugungsvermerk der Mappe. Der Export "
                "laeuft trotzdem.",
                "openpyxl ist Voraussetzung. Fehlt es, bricht der Lauf mit 1 "
                "ab - die Mappe entsteht dann gar nicht.",
                "Die Buildnummer im Vermerk kommt aus der build.json der "
                "Bestandswurzel. Wird das Werkzeug ausserhalb der Struktur "
                "aufgerufen, steht dort 0.",
                "--out ueberschreibt eine vorhandene Datei wortlos.",
            ),
        ),
    ),

    # -------------------------------------------------- Identitaeten, Externe
    CliEintrag(
        schluessel="case_release_admin",
        pfad="management/external/case_release_admin.py",
        aufruf="python -m management.external.case_release_admin <befehl>",
        titel="Externe Fallfreigabe",
        gruppe="Identitaeten und Externe",
        zweck="Faelle an bestaetigte Empfaenger ausserhalb der Dienststelle "
              "freigeben und Freigaben widerrufen.",
        art="gemischt",
        datenbanken=("coordinator.db (grant/revoke schreibend, "
                     "list lesend)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        beleg=True,
        befehle=(
            _b("recipients", "lesend",
               "Die berechtigten Empfaenger aus der Konfiguration."),
            _b("umfang", "lesend", "Katalog der Umfangsarten."),
            _b("list", "lesend", "Freigaben auflisten."),
            _b("grant", "schreibend",
               "Fall freigeben. Die Unbedenklichkeits-Grundlage ist Pflicht."),
            _b("revoke", "schreibend",
               "Freigabe widerrufen. Der Grund ist Pflicht."),
        ),
        hinweis="Eine Freigabe endet NICHT von selbst - es gibt keine Frist. "
                "Sie besteht, bis sie widerrufen wird.",
    ),
    CliEintrag(
        schluessel="external_admin",
        pfad="management/external/external_admin.py",
        aufruf="python -m management.external.external_admin <befehl>",
        titel="Wiedervorlage externer Vorgaenge",
        gruppe="Identitaeten und Externe",
        zweck="Externe Vorgaenge und ihre Wiedervorlage fuehren: anlegen, "
              "verschieben, beantworten, abschliessen.",
        art="gemischt",
        datenbanken=("coordinator.db (add/defer/answer/close schreibend, "
                     "list lesend)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        beleg=True,
        befehle=(
            _b("list", "lesend",
               "Vorgaenge auflisten. Exit 2 meldet rote Ampeln."),
            _b("add", "schreibend", "Vorgang anlegen."),
            _b("defer", "schreibend",
               "Wiedervorlage verschieben. Der Grund ist Pflicht."),
            _b("answer", "schreibend", "Antwort eingegangen."),
            _b("close", "schreibend", "Endgueltig abschliessen."),
            _b("kinds", "lesend", "Katalog der Vorgangsarten."),
        ),
    ),
    CliEintrag(
        schluessel="ausschleus_admin",
        pfad="management/export/ausschleus_admin.py",
        aufruf="python -m management.export.ausschleus_admin "
               "add|finalize|verify",
        titel="Ausschleus-Verzeichnis",
        gruppe="Identitaeten und Externe",
        zweck="Das Ausschleus-Verzeichnis fuer die Staatsanwaltschaft "
              "fuehren: gepruefte Dateien aufnehmen, abschliessen, "
              "nachrechnen.",
        art="lesend",
        datenbanken=("coordinator.db (nur lesend, mode=ro, fuer die "
                     "Kettenspitze; optional)",),
        betrieb="Der Betrieb darf weiterlaufen. Geschrieben wird nur im "
                "Ausschleus-Verzeichnis, nicht in einer Datenbank.",
        befehle=(
            _b("add", "lesend",
               "Eine geprueft unbedenkliche Datei aufnehmen. Ohne den "
               "ausdruecklichen Unbedenklichkeitsschalter wird abgewiesen."),
            _b("finalize", "lesend",
               "Kopfdaten stempeln und die Uebergabedatei schreiben."),
            _b("verify", "lesend",
               "Das Paket gegen sein Verzeichnis nachrechnen."),
        ),
        ausgabe="Dateien im Ausschleus-Verzeichnis (Kopien, Manifest, "
                "UEBERGABE.txt).",
    ),
    CliEintrag(
        schluessel="lkae_admin",
        pfad="management/distribution/lkae_admin.py",
        aufruf="python -m management.distribution.lkae_admin "
               "build --target D --freigabe",
        titel="Demo-Paket bauen",
        gruppe="Identitaeten und Externe",
        zweck="Ein Vorfuehrpaket bauen und gegen sein Verzeichnis pruefen.",
        art="gemischt",
        datenbanken=("erzeugt im Zielverzeichnis eine SYNTHETISCHE "
                     "coordinator.db; die Datenbanken der Anlage werden "
                     "nicht angefasst",),
        betrieb="Laeuft ausserhalb der laufenden Anlage. Das Zielverzeichnis "
                "muss leer sein; eine Ueberschneidung mit den Pfaden der "
                "Anlage wird abgewiesen.",
        befehle=(
            _b("build", "schreibend",
               "Paket bauen. Ohne den Freigabeschalter wird nichts getan."),
            _b("verify", "lesend", "Paket gegen sein Verzeichnis pruefen."),
        ),
        hinweis="NICHT fuer den Produktivbetrieb. Die Daten des Pakets sind "
                "erfunden.",
    ),
    CliEintrag(
        schluessel="promotion_admin",
        pfad="management/ops/promotion_admin.py",
        aufruf="python -m management.ops.promotion_admin "
               "candidates|list|decide",
        titel="Fremdforum-Promotion",
        gruppe="Identitaeten und Externe",
        zweck="Kandidaten aus einem Fremdforum sichten und entscheiden, ob "
              "sie in die eigene Ermittlung uebernommen werden.",
        art="gemischt",
        datenbanken=("coordinator.db (decide schreibend, sonst lesend)",
                     "Verzeichnisse der Fall-Datenbanken werden nur "
                     "abgezaehlt, nicht geoeffnet"),
        betrieb="Der Betrieb darf weiterlaufen.",
        beleg=True,
        befehle=(
            _b("candidates", "lesend", "Kandidaten samt Zustand."),
            _b("list", "lesend", "Alle erfassten Entscheidungen."),
            _b("decide", "schreibend",
               "Entscheidung erfassen. 'uebernommen' und 'fremdzustaendig' "
               "sind ENDGUELTIG."),
        ),
    ),

    # ------------------------------------------------- Betrieb und Sicherung
    CliEintrag(
        schluessel="backup_admin",
        pfad="management/backup/backup_admin.py",
        aufruf="python -m management.backup.backup_admin plan|run|list",
        titel="Datensicherung",
        gruppe="Betrieb und Sicherung",
        zweck="Die auditierte Datensicherung planen, ausfuehren und die "
              "vergangenen Laeufe auflisten.",
        art="gemischt",
        datenbanken=("coordinator.db (run schreibend, plan/list lesend)",
                     "alle uebrigen Datenbanken werden zur Sicherung "
                     "AUSSCHLIESSLICH gelesen und dabei nicht veraendert"),
        betrieb="TEILWEISE betriebsvertraeglich - die Einstufung ist am "
                "2026-07-31 nachgeprueft und RICHTIGGESTELLT worden (Build "
                "616). 'plan' ist rein lesend und jederzeit unbedenklich. "
                "'run' veraendert die Quellen NICHT (es kopiert mit 'VACUUM "
                "INTO'), aber die frueher hier stehende Zusage 'blockiert "
                "den Zugriff nicht' traegt so nicht: unter dem Rollback-"
                "Journal, das seit dem WAL-Verbot ueberall gilt, schliessen "
                "Leser und Schreiber einander aus. Vor allem aber ist der "
                "Sicherungs-SATZ nicht punktgleich - die Datenbanken werden "
                "nacheinander gesichert, jede fuer sich stimmig, der Satz "
                "als Ganzes nicht. Fuer eine wiederherstellbare Sicherung "
                "sollte kein Schreiber offen sein. Einzelheiten und "
                "Vorgaenge: siehe Warnungen.",
        beleg=True,
        befehle=(
            _b("plan", "lesend",
               "Was gesichert wuerde, samt Platzbedarf. Schreibt nichts."),
            _b("run", "schreibend",
               "Sicherung ausfuehren und den Lauf belegen."),
            _b("list", "lesend", "Vergangene Laeufe auflisten. ACHTUNG - "
               "es oeffnet die coordinator.db trotz dieser Einstufung "
               "SCHREIBFAEHIG und setzt dabei ein Journalmodus-PRAGMA; "
               "geschrieben werden keine Nutzdaten. Vorgang eroeffnet."),
        ),
        ausgabe="Sicherungsdateien und ein Manifest im Sicherungsverzeichnis "
                "(bei 'run').",
        tiefe=CliTiefe(
            exit_codes=((0, "'plan': Vorabpruefung bestanden. 'run': ALLE "
                            "Datenbanken gesichert UND integer. 'list': "
                            "ausgegeben - IMMER, siehe Warnung"),
                        (1, "'run': mindestens eine Sicherung ist "
                            "fehlgeschlagen oder nicht integer"),
                        (2, "'plan'/'run': die Vorabpruefung ist "
                            "fehlgeschlagen (etwa zu wenig Platz); bei "
                            "'run' wurde dann NICHTS gesichert")),
            warnungen=(
                "DIE AUFBEWAHRUNG SIEHT NICHT AUF DIE INTEGRITAET. Die "
                "Aufraeumung behaelt je Datenbank die neuesten Generationen "
                "allein nach dem Zeitstempel im Dateinamen; ob eine Kopie "
                "die Integritaetspruefung bestanden hat, geht NICHT ein. "
                "Eine als defekt erkannte Sicherung zaehlt damit als "
                "juengste Generation und verdraengt die aelteste gute. Das "
                "ist der schwerste der bei der Nachpruefung gefundenen "
                "Punkte - Vorgang eroeffnet.",
                "DER SICHERUNGSSATZ IST NICHT PUNKTGLEICH. Die Datenbanken "
                "werden NACHEINANDER gesichert. Jede Kopie ist fuer sich "
                "transaktional stimmig; zwischen zweien kann der Betrieb "
                "einen Fall anlegen oder eine Zuweisung aendern. FUER EINE "
                "WIEDERHERSTELLUNG DES GESAMTEN BESTANDES ist deshalb ein "
                "ruhiger Zustand noetig - keine offenen Schreiber -, sonst "
                "kann ein Zustand entstehen, den es nie gegeben hat. SEIT "
                "BUILD 617 IST DAS GEKENNZEICHNET (Entscheidung mc "
                "2026-07-31: Kennzeichnung statt Wartungsfenster, damit eine "
                "taegliche Sicherung nebenher laufen kann): das Manifest "
                "traegt 'punktgleich: false' samt Klartext, je Datenbank "
                "stehen Beginn und Ende der Kopie darin, und der Vermerk "
                "erscheint bei JEDEM Lauf auch auf der Konsole. Behoben ist "
                "die Ungleichzeitigkeit damit nicht - sie ist sichtbar.",
                "WAS WAEHREND DES LAUFS ENTSTEHT, WIRD NICHT GESICHERT - "
                "aber seit Build 617 GENANNT: eine Fall-Datenbank, die es "
                "beim Planen noch nicht gab, steht danach im Manifest unter "
                "'nicht_gesichert_weil_neu' und auf der Konsole. Sie fehlt "
                "im Satz und ist beim naechsten Lauf dabei.",
                "'list' LIEFERT IMMER 0 - auch dann, wenn jede aufgefuehrte "
                "Sicherung 'integrity=FEHLER' traegt. Eine Ueberwachung, die "
                "nur den Rueckgabewert auswertet, sieht dauerhaft gruen. Die "
                "Spalte 'integrity' ist zu LESEN.",
                "FUER DIE HIER ERZEUGTEN SICHERUNGEN GIBT ES KEINEN "
                "RUECKWEG. Das Werkzeug kennt kein 'restore', und im Bestand "
                "ist keiner vorgesehen und keiner erprobt. Eine Sicherung, "
                "deren Rueckweg nie gefahren wurde, ist eine Vermutung.",
                "Die Pruefsumme jeder Kopie wird ERHOBEN und im Register "
                "abgelegt, aber nie wieder GEPRUEFT. Die vorhandene "
                "Pruefroutine hat keinen produktiven Aufrufer. Eine "
                "Sicherung altert damit unbeobachtet.",
                "Eine Fall-Datenbank, die WAEHREND des Laufs neu entsteht, "
                "wird nicht gesichert und erscheint auch nicht unter den "
                "fehlenden - das Verzeichnis wird einmal vor dem Lauf "
                "gelesen.",
                "Es ist keine Wartezeit auf belegte Datenbanken gesetzt. Es "
                "gilt der Vorgabewert der Python-Anbindung von fuenf "
                "Sekunden; danach meldet die betroffene Datenbank "
                "'database is locked' und hat in diesem Lauf KEINE "
                "Sicherung. Der Lauf endet dann mit 1.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="storage_admin",
        pfad="management/ops/storage_admin.py",
        aufruf="python -m management.ops.storage_admin [--json]",
        titel="Speicheruebersicht",
        gruppe="Betrieb und Sicherung",
        zweck="Den Speicherbedarf der Anlage und den freien Platz ausgeben; "
              "warnt bei knappem Speicher.",
        art="lesend",
        datenbanken=("keine - die Dateien werden nur gezaehlt und gemessen, "
                     "nicht geoeffnet",),
        betrieb="Der Betrieb darf weiterlaufen.",
    ),
    CliEintrag(
        schluessel="retention_admin",
        pfad="management/ops/retention_admin.py",
        aufruf="python -m management.ops.retention_admin [--json]",
        titel="Aufbewahrungsfristen",
        gruppe="Betrieb und Sicherung",
        zweck="Uebersicht, welche abgeschlossenen Faelle die "
              "Aufbewahrungsfrist ueberschritten haben.",
        art="lesend",
        datenbanken=("coordinator.db (lesend, mode=ro)",),
        betrieb="Der Betrieb darf weiterlaufen.",
        hinweis="LOESCHT NICHTS und kann nichts loeschen. Die Ausgabe ist "
                "ein Pruefvorschlag; das Loeschen von Beweismitteln ist eine "
                "Entscheidung ausserhalb dieser Anlage.",
    ),
    CliEintrag(
        schluessel="index_cli",
        pfad="management/search/index_cli.py",
        aufruf="python -m management.search.index_cli "
               "--status | --auffrischen [--voll]",
        titel="Suchindex",
        gruppe="Betrieb und Sicherung",
        zweck="Den Suchindex aufbauen, auffrischen und seinen Stand pruefen.",
        art="gemischt",
        datenbanken=("search_index.db (schreibend) - ein Hilfsmittel, kein "
                     "Beweismittel",
                     "evidence_<uid>.db (lesend, mode=ro - technisch "
                     "gesperrt, nicht nur zugesagt)"),
        betrieb="STUFE B - betriebsvertraeglich (Analyse Build 609). Der "
                "Lauf schreibt ausschliesslich in search_index.db, die kein "
                "anderer Dienst offen haelt; die evidence-Datenbanken werden "
                "nur mit 'mode=ro' gelesen. Je Fall eine kurze Transaktion, "
                "kein Zwischenzustand. ABER: der Lauf ist ein betrieblicher "
                "Vorgang mit messbaren Kosten auf dem Netzlaufwerk (Faktor "
                "rund 24 gegenueber der Entwicklung), und eine gerade "
                "beschriebene evidence-Datei kann er nicht lesen - dann "
                "bleibt dieser Fall unvollstaendig und der Lauf endet mit 2.",
        befehle=(
            _b("--status", "lesend", "Stand des Index ausgeben."),
            _b("--auffrischen", "schreibend",
               "Index auffrischen. Exit 2 heisst: gelaufen, aber mindestens "
               "ein Fall ist unvollstaendig."),
        ),
        hinweis="'--voll' baut neu auf und ist teuer - aber der einzige Weg, "
                "einen Fehltreffer der Kurzpruefung aufzuloesen. Der Lauf "
                "erzeugt bewusst KEINEN Beleg: er ist keine "
                "Ermittlungshandlung; die Handlung ist die Abfrage.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.search.index_cli --status",
                     "Zeigt den Stand des Index je Fall. Im Versuch gegen "
                     "ein leeres Verzeichnis: alle Zaehler 0, Gesamtbefund "
                     "'NICHT belegt aktuell', Rueckgabewert 0."),
            ),
            exit_codes=((0, "gelaufen bzw. Stand ausgegeben"),
                        (1, "Fehler"),
                        (2, "gelaufen, ABER mindestens ein Fall ist "
                            "unvollstaendig")),
            warnungen=(
                "Eine gerade beschriebene evidence-Datei laesst sich nicht "
                "lesen. Der Fall bleibt dann unvollstaendig, und der Lauf "
                "endet mit 2 - das ist ein Befund und kein Absturz.",
                "'--voll' baut den Index neu auf und ist teuer.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="maintenance",
        pfad="tools/maintenance.py",
        aufruf="python tools/maintenance.py enter|exit|status",
        titel="Wartungsfenster",
        gruppe="Betrieb und Sicherung",
        zweck="Ein Wartungsfenster setzen, beenden und seinen Stand "
              "abfragen - der Weg, die Anlage ruhigzustellen.",
        art="gemischt",
        datenbanken=("coordinator.db (lesend, fuer die Rechtepruefung)",
                     "die benannten Ziel-Datenbanken werden zum Nachweis "
                     "kurz exklusiv gesperrt und sofort wieder freigegeben"),
        betrieb="DIES IST DAS WERKZEUG ZUR RUHIGSTELLUNG. 'enter' wartet, "
                "bis alle laufenden Dienste bestaetigt haben UND die "
                "Ziel-Datenbanken exklusiv sperrbar sind. Die Bestaetigung "
                "allein ist nicht der Nachweis - die Sperre ist es.",
        befehle=(
            _b("enter", "schreibend",
               "Fenster setzen. Der Grund ist Pflicht. Exit 2 heisst: "
               "gesetzt, aber NICHT vollstaendig bestaetigt - das ist kein "
               "freigegebenes Fenster."),
            _b("exit", "schreibend", "Fenster beenden."),
            _b("status", "lesend", "Stand des Fensters."),
        ),
        hinweis="Geschrieben werden nur Steuerdateien im Wartungsverzeichnis "
                "- an den Fachdaten aendert dieses Werkzeug nichts.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/maintenance.py status --data-dir ./data",
                     "Zeigt das Fenster und die angemeldeten Dienste. Im "
                     "Versuch: 'Wartungsfenster: KEINES gesetzt.' mit 0."),
                _bsp("python tools/maintenance.py enter --reason \"Migration "
                     "templates.db\" --ziel coordinator --wait-timeout 60",
                     "Setzt das Fenster und wartet auf Ruhe. Im Versuch "
                     "gegen einen Bestand ohne Personentabelle brach der "
                     "Aufruf mit 1 ab: die Rechtepruefung war nicht "
                     "moeglich, und ohne Recht wird kein Fenster gesetzt."),
                _bsp("python tools/maintenance.py exit --data-dir ./data",
                     "Beendet das Fenster. Im Versuch: 'Kein Wartungsfenster "
                     "gesetzt - nichts zu tun.' mit 0."),
            ),
            exit_codes=((0, "erledigt"),
                        (1, "Berechtigung fehlt oder Aufruffehler"),
                        (2, "Fenster gesetzt, aber NICHT vollstaendig "
                            "bestaetigt - das ist KEIN freigegebenes "
                            "Fenster")),
            warnungen=(
                "'--ziel all' erfasst NUR die Datenbanken der obersten "
                "Ebene. Die Fall-Datenbanken in den Unterverzeichnissen "
                "evidence/, forensic/ und assets/ sind NICHT dabei - fuer "
                "sie ist das Ziel einzeln zu nennen (z. B. "
                "'evidence:900001'). Ein mit 'all' gesetztes Fenster ist "
                "also KEIN Nachweis fuer die Ruhe einer Fall-Datenbank.",
                "Eine schreibgeschuetzte (versiegelte) Datei gilt als ruhig "
                "- richtig, weil es dort keinen Schreiber geben kann.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="maintenance_kill",
        pfad="tools/maintenance_kill.py",
        aufruf="python tools/maintenance_kill.py --list|--uuid X|--all",
        titel="Haengende Wartungsdienste beenden",
        gruppe="Betrieb und Sicherung",
        zweck="Wartungs-Testdienste beenden, die nach dem Ende eines "
              "Fensters weiterlaufen.",
        art="gemischt",
        datenbanken=("keine",),
        betrieb="Wirkt auf laufende Dienste. Der Weg fuehrt ueber "
                "Steuerdateien, nicht ueber einen Prozessabbruch.",
        befehle=(
            _b("--list", "lesend", "Angemeldete Dienste auflisten."),
            _b("--uuid", "schreibend", "Einen bestimmten Dienst beenden."),
            _b("--all", "schreibend", "Alle angemeldeten Dienste beenden."),
        ),
        hinweis="GEKLAERT (Analyse Build 609): Ein REGULAERER Dienst ist "
                "ueber diesen Weg NICHT erreichbar. Nur ein mit "
                "--maintenance gestarteter Dienst legt eine Anmeldedatei an, "
                "und nur er wertet die Kill-Anforderung aus; ein regulaerer "
                "Dienst schreibt lediglich ein Lebenszeichen in ein anderes "
                "Verzeichnis. ABER: '--all' nimmt ALLE Anmeldungen ohne "
                "Filter nach Rechner oder Fenster - auf einem geteilten "
                "Laufwerk trifft es auch die Wartungsdienste anderer.",
        tiefe=CliTiefe(
            exit_codes=((0, "erledigt"),
                        (1, "Aufruffehler"),
                        (2, "Nachzuegler - mindestens ein Dienst hat sich "
                            "nicht abgemeldet")),
            warnungen=(
                "'--all' nimmt ALLE Anmeldungen ohne Filter nach Rechner "
                "oder Fenster. Auf einem geteilten Laufwerk trifft es auch "
                "die Wartungsdienste anderer.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="hilfe",
        pfad="tools/hilfe.py",
        aufruf="python tools/hilfe.py liste|zeige <kennung>|suche <begriff>"
               "|stand",
        titel="Werkzeugverzeichnis",
        gruppe="Betrieb und Sicherung",
        zweck="Das Dach ueber alle Kommandozeilen-Werkzeuge: auflisten, ein "
              "Werkzeug im Einzelnen zeigen, suchen, Ausarbeitungsstand.",
        art="lesend",
        datenbanken=("keine",),
        betrieb="Zu jeder Zeit und in jedem Betriebszustand gefahrlos: es "
                "gibt nur Text aus, fuehrt nichts aus, oeffnet nichts und "
                "nimmt keine Sperre - auch mitten in einer Migration "
                "aufrufbar.",
        befehle=(
            _b("liste", "lesend",
               "Alle Werkzeuge, nach Arbeitsbereich gruppiert; "
               "'--nur-schreibend' zeigt nur die aendernden."),
            _b("zeige", "lesend",
               "Ein Werkzeug im Einzelnen. Endet mit dem '--help'-Aufruf des "
               "Zielwerkzeugs."),
            _b("suche", "lesend",
               "Volltextsuche ueber den Katalog. Rueckgabewert 1 bedeutet "
               "'kein Treffer' - eine Auskunft, kein Fehler."),
            _b("stand", "lesend",
               "Wie weit der Katalog ausgearbeitet ist."),
        ),
        hinweis="Der Katalog sagt, WOZU ein Werkzeug da ist. Die "
                "vollstaendige Liste der Optionen sagt das Werkzeug selbst - "
                "ein hier abgeschriebener Optionsblock wuerde veralten.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/hilfe.py suche sicherung",
                     "Fuehrte die Werkzeuge auf, deren Katalogtext den "
                     "Begriff enthaelt - hier unter anderem 'backup_admin'. "
                     "Rueckgabewert 0.",
                     _GEPRUEFT_613),
                _bsp("python tools/hilfe.py suche zzzgibtsnicht",
                     "LEERBEFUND: 'Kein Treffer' samt der Angabe, WORIN "
                     "gesucht wurde (Kennung, Titel, Zweck, Aufrufform). "
                     "Rueckgabewert 1 - damit ein Skript den Leerbefund "
                     "erkennt, ohne die Ausgabe zu lesen.",
                     _GEPRUEFT_613),
                _bsp("python tools/hilfe.py stand",
                     "Nannte die Gesamtzahl der Werkzeuge und wie viele davon "
                     "ueber den Grundeintrag hinaus ausgearbeitet sind. "
                     "Rueckgabewert 0.",
                     _GEPRUEFT_613),
            ),
            exit_codes=((0, "ausgegeben"),
                        (1, "unbekanntes Werkzeug (mit Vorschlaegen auf der "
                            "Fehlerausgabe) bzw. Suche ohne Treffer - beides "
                            "eine Auskunft und kein Fehler"),
                        (2, "Aufruffehler bzw. kein Unterbefehl angegeben")),
            warnungen=(
                "Das Werkzeug FUEHRT NICHTS AUS, oeffnet keine Datenbank und "
                "nimmt keine Sperre. Es ist damit in jedem Betriebszustand "
                "aufrufbar, auch mitten in einer Migration.",
                "Bei einem unbekannten Werkzeug geht die Meldung auf die "
                "FEHLERAUSGABE - wer die Ausgabe in eine Datei umleitet, hat "
                "dort keinen Fehlertext stehen.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="hilfe_lektorat",
        pfad="tools/hilfe_lektorat.py",
        aufruf="python tools/hilfe_lektorat.py [--nur sicht1,sicht2] "
               "[--ziel datei.html]",
        titel="Lektoratsfassung der Hilfe",
        gruppe="Betrieb und Sicherung",
        zweck="Alle Hilfetexte in EIN lesbares HTML schreiben, damit sie "
              "gegengelesen werden koennen, ohne jedes Element einzeln "
              "anzuklicken.",
        art="lesend",
        datenbanken=("keine",),
        betrieb="Der Betrieb darf weiterlaufen; gelesen wird nur der "
                "Hilfebestand im Paket.",
        ausgabe="HTML-Datei (--ziel).",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/hilfe_lektorat.py --ziel ./lektorat.html",
                     "Schrieb die Lektoratsfassung der gesamten Hilfe in eine "
                     "Datei und nannte die Zahl der Kapitel und der "
                     "Einblendtexte. Rueckgabewert 0.",
                     _GEPRUEFT_613),
                _bsp("python tools/hilfe_lektorat.py --nur gibtsnicht",
                     "Brach ab und nannte auf der Fehlerausgabe ALLE "
                     "verfassten Kapitelkennungen. Rueckgabewert 1.",
                     _GEPRUEFT_613),
            ),
            exit_codes=((0, "Datei geschrieben"),
                        (1, "in --nur steht eine Kennung, zu der es kein "
                            "verfasstes Kapitel gibt")),
            warnungen=(
                "EIN TIPPFEHLER IN --nur BRICHT AB, statt eine leere Fassung "
                "zu schreiben. Das ist Absicht: eine stillschweigend leere "
                "Lektoratsfassung saehe aus wie 'nichts zu tun'.",
                "--ziel ueberschreibt eine vorhandene Datei wortlos.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="pruefe_auslieferung",
        pfad="tools/pruefe_auslieferung.py",
        aufruf="python tools/pruefe_auslieferung.py [--alle]",
        titel="Auslieferung pruefen",
        gruppe="Betrieb und Sicherung",
        zweck="Die Pruefsummenliste des Builds gegen den Bestand pruefen - "
              "von der WURZEL aus, damit ein zu tief entpacktes Archiv "
              "auffaellt.",
        art="lesend",
        datenbanken=("keine",),
        betrieb="Nach jedem Einspielen aufzurufen. Der Betrieb darf "
                "weiterlaufen.",
        hinweis="Bei relativen Pfaden ist ein gleichmaessig verschobener "
                "Baum in sich stimmig - dieser Fehler ist ausschliesslich "
                "von der Wurzel aus sichtbar.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/pruefe_auslieferung.py",
                     "Prueft die Liste zum Build aus der build.json. Im "
                     "Versuch: 'Alle 11 Dateien in Ordnung', Rueckgabewert 0.",
                     _GEPRUEFT_613),
                _bsp("python tools/pruefe_auslieferung.py "
                     "MD5SUMS_Build609.txt",
                     "Prueft eine AELTERE Liste gegen den heutigen Bestand. "
                     "Im Versuch: '5 von 7 Dateien in Ordnung' samt "
                     "Nennung der abweichenden Datei mit erwarteter und "
                     "gefundener Pruefsumme, Rueckgabewert 1. Die Abweichung "
                     "ist hier RICHTIG - die Dateien wurden seither "
                     "geaendert.",
                     _GEPRUEFT_613),
            ),
            exit_codes=((0, "alle geprueften Dateien stimmen"),
                        (1, "mindestens eine Datei fehlt oder weicht ab"),
                        (2, "falsches Arbeitsverzeichnis oder Aufrufproblem")),
            warnungen=(
                "OHNE ARGUMENT wird NUR die Liste zum Build aus der "
                "build.json geprueft. Eine Liste beschreibt den Stand ZUM "
                "ZEITPUNKT IHRES BUILDS; alle Listen gegen den heutigen "
                "Bestand zu pruefen erzeugte lauter richtige Abweichungen - "
                "und in diesem Rauschen ginge der eine echte Befund unter.",
                "Das Werkzeug WEIGERT SICH, wenn es nicht in der Wurzel des "
                "Bestands laeuft. Der Grund ist ein Befund vom 2026-07-31: "
                "zwei Archive wurden eine Ebene zu tief entpackt, und weil "
                "die Pfade in der Liste relativ sind, war der verschobene "
                "Baum in sich stimmig - sichtbar wird der Fehler nur von der "
                "Wurzel aus.",
            ),
        ),
    ),

    # ---------------------------------------------- Migration und Reparatur
    CliEintrag(
        schluessel="migrate",
        pfad="management/migrate.py",
        aufruf="python -m management.migrate [--deployed-by KENNUNG]",
        titel="coordinator.db migrieren",
        gruppe="Migration und Reparatur",
        zweck="Ausstehende Migrationen der coordinator.db anwenden.",
        art="schreibend",
        datenbanken=("coordinator.db (schreibend)",),
        betrieb="STUFE A - WARTUNGSFENSTER ERFORDERLICH (Analyse Build "
                "609). Die Migrationen bauen Tabellen der coordinator.db um "
                "(neu anlegen, kopieren, alte loeschen, umbenennen) und "
                "setzen Journalmodus und Kontrollpunkt. Genau diese Datei "
                "haelt der Auswertungsdienst im Regelbetrieb SCHREIBEND "
                "offen. Ein Backup legt das Werkzeug NICHT an."
                "SEIT BUILD 612 SETZT DAS WERKZEUG DAS SELBST DURCH: es prueft vor "
                "dem scharfen Lauf, ob die betroffenen Dateien ruhig sind, bricht "
                "bei einer belegten Datei ohne Rueckfrage ab und faehrt ohne "
                "aktives Wartungsfenster nur nach Eingabe des Wortes 'OHNE "
                "WARTUNGSFENSTER' fort.",
        beleg=True,
        hinweis="DER EINZIGE Weg fuer die coordinator.db. tools/migrate-dbs.py "
                "verweist ausdruecklich hierher: zwei Wege, die dasselbe "
                "schreiben, waeren zwei Wahrheiten ueber den Beleg.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.migrate --coordinator-db "
                     "./data/coordinator.db --deployed-by KENNUNG",
                     "Wendet die ausstehenden Migrationen an und prueft "
                     "danach die Belegkette nach."),
            ),
            exit_codes=((0, "angewandt oder nichts zu tun"),
                        (1, "Fehler - die betroffene Migration wurde "
                            "zurueckgerollt"),
                        (3, "Wartungsvorbehalt - der Lauf wurde nicht ausgefuehrt; es wurde NICHTS geschrieben")),
            warnungen=(
                "Es wird KEIN Backup angelegt. Eines ist vorher von Hand zu "
                "erstellen (Datenmigrationsleitfaden).",
                "Auf einer noch nicht eingerichteten coordinator.db bricht "
                "der Lauf bei der zweiten Migration mit einer unbehandelten "
                "Ausnahme ab (geprueft Build 609). Der vorgesehene "
                "Ausgangspunkt ist eine bereits eingerichtete Datei.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="migrate-dbs",
        pfad="tools/migrate-dbs.py",
        aufruf="python tools/migrate-dbs.py [--db templates] "
               "[--subject-id N] [--apply]",
        titel="Migrationsstand aller Datenbanken",
        gruppe="Migration und Reparatur",
        zweck="Den Migrationsstand aller Datenbanken pruefen und - nur mit "
              "ausdruecklicher Scharfschaltung - anwenden.",
        art="gemischt",
        datenbanken=("templates.db, evidence_<uid>.db, assets_<uid>.db "
                     "(mit --apply schreibend)",
                     "forensic_<uid>.db (NIE geschrieben - auch mit --apply "
                     "nicht)",
                     "coordinator.db (nur gelesen; angewandt wird sie ueber "
                     "management.migrate)"),
        betrieb="STUFE A - WARTUNGSFENSTER ERFORDERLICH (Analyse Build "
                "609), sobald --apply gesetzt ist. Geschrieben werden "
                "templates.db sowie evidence_<uid>.db und assets_<uid>.db; "
                "die evidence-Datei haelt der Auswertungsdienst des "
                "jeweiligen Falls schreibend offen. Es werden Tabellen "
                "umgebaut. Eine Sicherungskopie legt das Werkzeug vorher an "
                "(ausser mit --no-backup) - sie wird aber NICHT automatisch "
                "zurueckgespielt. Ohne --apply ist der Lauf reine Anzeige "
                "und jederzeit unbedenklich."
                "SEIT BUILD 612 SETZT DAS WERKZEUG DAS SELBST DURCH: es prueft vor "
                "dem scharfen Lauf, ob die betroffenen Dateien ruhig sind, bricht "
                "bei einer belegten Datei ohne Rueckfrage ab und faehrt ohne "
                "aktives Wartungsfenster nur nach Eingabe des Wortes 'OHNE "
                "WARTUNGSFENSTER' fort.",
        befehle=(
            _b("(ohne --apply)", "lesend",
               "Trockenuebung. Die Vorgabe - es wird nichts geschrieben."),
            _b("--apply", "schreibend",
               "Anwenden. Sichert vorher, ausser mit --no-backup."),
        ),
        hinweis="Die versiegelte forensic-Datenbank bleibt unberuehrt. Das "
                "ist keine Vorsichtsmassnahme, sondern eine Grenze.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/migrate-dbs.py --data-dir ./data",
                     "Trockenuebung ueber alle Datenbanken. Meldete im "
                     "Versuch 'OFFEN in 2 Datenbank(en): coordinator, "
                     "templates' und endete mit 1 - es wurde nichts "
                     "geschrieben."),
                _bsp("python tools/migrate-dbs.py --db templates --apply",
                     "Wendet die templates-Schritte an; legt vorher eine "
                     "Sicherungskopie neben der Datei an.",
                     "Build 609: die Trockenuebung ist gefahren, das "
                     "Scharfschalten NICHT - es haette den Wegwerf-Bestand "
                     "veraendert und damit den naechsten Versuch entwertet."),
            ),
            exit_codes=((0, "alles auf Stand"),
                        (1, "Migrationen offen bzw. Fehler beim Anwenden"),
                        (2, "Abbruch waehrend des Anwendens"),
                        (3, "Wartungsvorbehalt - der Lauf wurde nicht ausgefuehrt; es wurde NICHTS geschrieben")),
            warnungen=(
                "forensic_<uid>.db wird NIE geschrieben - auch mit --apply "
                "nicht. Das ist eine Grenze und keine Vorsichtsmassnahme.",
                "Die coordinator.db wendet dieses Werkzeug nicht selbst an; "
                "dafuer gibt es 'python -m management.migrate'. Zwei Wege, "
                "die dasselbe schreiben, waeren zwei Wahrheiten ueber den "
                "Beleg.",
                "Die Sicherungskopie wird NICHT automatisch zurueckgespielt.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="migration_fleet_admin",
        pfad="management/migration_fleet/migration_fleet_admin.py",
        aufruf="python -m management.migration_fleet.migration_fleet_admin "
               "<befehl>",
        titel="Flottenmigration",
        gruppe="Migration und Reparatur",
        zweck="Die Migration ueber viele Fall-Datenbanken hinweg fuehren: "
              "Katalog abgleichen, Stand erheben, Plan erstellen, ausfuehren.",
        art="gemischt",
        datenbanken=("migration.db (Katalog und Laufbuch; schreibend bei "
                     "catalog-sync und beim scharfen Lauf)",
                     "die benannten Fall-Datenbanken (nur beim scharfen "
                     "Lauf schreibend)"),
        betrieb="STUFE A - WARTUNGSFENSTER ERFORDERLICH (Analyse Build "
                "609), sobald 'companion --confirm' gesetzt ist. Der "
                "Rueckweg im Fehlerfall KOPIERT die Sicherung UEBER die "
                "Originaldatei und setzt dabei voraus, dass keine andere "
                "Verbindung offen ist - er prueft es aber nicht. Genau das "
                "ist der Fall, in dem ein laufender Auswertungsdienst "
                "Schaden nimmt. Vor dem scharfen Lauf sind vier Tore zu "
                "passieren; eine Sicherung ist Pflicht. Ohne --confirm wird "
                "nur vorgeprueft und geplant."
                "SEIT BUILD 612 SETZT DAS WERKZEUG DAS SELBST DURCH: es prueft vor "
                "dem scharfen Lauf, ob die betroffenen Dateien ruhig sind, bricht "
                "bei einer belegten Datei ohne Rueckfrage ab und faehrt ohne "
                "aktives Wartungsfenster nur nach Eingabe des Wortes 'OHNE "
                "WARTUNGSFENSTER' fort.",
        befehle=(
            _b("catalog-sync", "schreibend",
               "Den Migrationskatalog in das Laufbuch uebernehmen."),
            _b("reconcile", "lesend", "Stand gegen den Katalog abgleichen."),
            _b("plan", "lesend", "Plan fuer ein Ziel erstellen."),
            _b("ledger-verify", "lesend", "Das Laufbuch nachrechnen."),
            _b("ledger-list", "lesend", "Eintraege des Laufbuchs auflisten."),
            _b("companion", "schreibend",
               "Ausfuehren - aber NUR mit --confirm. Ohne --confirm wird "
               "ausschliesslich vorgeprueft und geplant."),
        ),
        hinweis="Der Beleg laeuft hier NICHT ueber das Protokollbuch: "
                "Beweis-Datenbanken fuehren keines. Der forensische Beleg "
                "ist das verkettete Laufbuch.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.migration_fleet."
                     "migration_fleet_admin ledger-list",
                     "Listet die Eintraege des Laufbuchs. Achtung: dieses "
                     "Werkzeug kennt KEIN --data-dir; ein unbekanntes "
                     "Argument endet mit 2 (im Versuch bestaetigt)."),
            ),
            exit_codes=((0, "erledigt"),
                        (1, "Vorpruefung nicht bestanden oder Lauf "
                            "gescheitert"),
                        (2, "Aufruffehler"),
                        (3, "Wartungsvorbehalt - der Lauf wurde nicht ausgefuehrt; es wurde NICHTS geschrieben")),
            warnungen=(
                "Der Rueckweg im Fehlerfall kopiert die Sicherung UEBER die "
                "Originaldatei und setzt voraus, dass keine andere "
                "Verbindung offen ist - er prueft es nicht.",
                "Der Beleg laeuft nicht ueber das Protokollbuch: "
                "Beweis-Datenbanken fuehren keines. Der Nachweis ist das "
                "verkettete Laufbuch.",
                "Ein unterbrochener Lauf blockiert den naechsten, bis er "
                "geklaert ist.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="templates_db_status",
        pfad="management/templates_db_status.py",
        aufruf="python management/templates_db_status.py",
        titel="Migrationsstand der templates.db",
        gruppe="Migration und Reparatur",
        zweck="In einem Aufruf sagen, welche Migrationen der templates.db "
              "angewandt sind, welche fehlen - und mit welchem Befehl die "
              "Luecke zu schliessen ist.",
        art="lesend",
        datenbanken=("templates.db (lesend)",),
        betrieb="Der Betrieb darf weiterlaufen. Die von diesem Werkzeug "
                "empfohlenen Migrationen sind laut seiner eigenen Ausgabe "
                "bei angehaltenem Dienst auszufuehren.",
        hinweis="Anlass war ein Fall, in dem zwei Migrationen nie gelaufen "
                "waren: die Folge war kein Fehler, sondern Stille. "
                "Exit 1 heisst 'Migration fehlt', Exit 2 'Datei unbrauchbar'.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python management/templates_db_status.py "
                     "--templates-db ./data/templates.db",
                     "Nennt angewandte und fehlende Migrationen samt dem "
                     "Befehl, der die Luecke schliesst. Im Versuch gegen "
                     "eine leere Datei: alle fuenf fehlen, Rueckgabewert 1."),
            ),
            exit_codes=((0, "vollstaendig"),
                        (1, "Migration(en) fehlen"),
                        (2, "Datei unbrauchbar")),
            warnungen=(
                "Die von diesem Werkzeug vorgeschlagenen Migrationen sind "
                "laut seiner eigenen Ausgabe bei angehaltenem Dienst "
                "auszufuehren.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="migrate_templates_module_key",
        pfad="management/migrate_templates_module_key.py",
        aufruf="python -m management.migrate_templates_module_key",
        titel="templates.db: stabile Bausteinkennung",
        gruppe="Migration und Reparatur",
        zweck="Eine stabile Kennung fuer die Berichtsbausteine einfuehren "
              "(statt der laufenden Nummer).",
        art="schreibend",
        datenbanken=("templates.db (schreibend)",),
        betrieb="Vor dem Ausfuehren ist ein geprueftes Backup anzulegen. "
                "Die templates.db hat kein eigenes Migrationsverfahren; "
                "dieses Skript laeuft eigenstaendig.",
        hinweis="EINMALIGE Altmigration. Mehrfaches Ausfuehren ist "
                "unschaedlich - ist die Kennung vorhanden, geschieht nichts.",
    ),
    CliEintrag(
        schluessel="migrate_templates_full_templates",
        pfad="management/migrate_templates_full_templates.py",
        aufruf="python -m management.migrate_templates_full_templates "
               "[--dry-run]",
        titel="templates.db: vollstaendige Vorlagen",
        gruppe="Migration und Reparatur",
        zweck="Die Tabelle der vollstaendigen Berichtsvorlagen anlegen und "
              "die fehlenden Abfragen sowie eine Vorlage einsetzen.",
        art="gemischt",
        datenbanken=("templates.db (schreibend; mit --dry-run lesend)",),
        betrieb="Vor dem Ausfuehren ist ein geprueftes Backup anzulegen.",
        befehle=(
            _b("--dry-run", "lesend", "Zeigt nur, was geschehen wuerde."),
            _b("(ohne --dry-run)", "schreibend", "Fuehrt die Migration aus."),
        ),
        hinweis="EINMALIGE Altmigration. Mehrfaches Ausfuehren ist "
                "unschaedlich.",
    ),
    CliEintrag(
        schluessel="migrate_templates_audit_check",
        pfad="management/migrate_templates_audit_check.py",
        aufruf="python -m management.migrate_templates_audit_check",
        titel="templates.db: Pruefregel des Protokolls erweitern",
        gruppe="Migration und Reparatur",
        zweck="Die Pruefregel des templates-Protokolls um eine weitere "
              "Zielart erweitern; die Tabelle wird dafuer verlustfrei neu "
              "aufgebaut.",
        art="schreibend",
        datenbanken=("templates.db (schreibend)",),
        betrieb="Eigenstaendig auszufuehren; ein geprueftes Backup ist "
                "anzulegen. Das Skript legt selbst keines an.",
        hinweis="EINMALIGE Altmigration. Ist die Regel bereits erweitert, "
                "geschieht nichts.",
    ),
    CliEintrag(
        schluessel="migrate_templates_placeholders",
        pfad="management/migrate_templates_placeholders.py",
        aufruf="python -m management.migrate_templates_placeholders "
               "[--no-backup]",
        titel="templates.db: Platzhalter vereinheitlichen",
        gruppe="Migration und Reparatur",
        zweck="Die drei Platzhalterarten in EINER Tabelle zusammenfuehren.",
        art="schreibend",
        datenbanken=("templates.db (schreibend)",),
        betrieb="Legt selbst eine Sicherungskopie an, sofern man sie nicht "
                "abschaltet. Eigenstaendig auszufuehren.",
        hinweis="EINMALIGE Altmigration - und die einzige mit einem "
                "loeschenden Schritt: die alte Tabelle wird entfernt. Das "
                "geschieht in EINER Transaktion und verlustfrei.",
    ),
    CliEintrag(
        schluessel="migrate_templates_ci",
        pfad="management/migrate_templates_ci.py",
        aufruf="python management/migrate_templates_ci.py [--no-backup]",
        titel="templates.db: Gross-/Kleinschreibung bei der Pruefung",
        gruppe="Migration und Reparatur",
        zweck="Den Platzhaltern ein Merkmal geben, mit dem die Pruefung "
              "Gross- und Kleinschreibung unterscheiden kann.",
        art="schreibend",
        datenbanken=("templates.db (schreibend)",),
        betrieb="Legt selbst eine Sicherungskopie an, sofern man sie nicht "
                "abschaltet, und prueft die Datei danach nach.",
        hinweis="EINMALIGE Altmigration. Ist die Spalte vorhanden, geschieht "
                "nichts.",
    ),
    CliEintrag(
        schluessel="repair_block_types",
        pfad="management/repair_block_types.py",
        aufruf="python -m management.repair_block_types "
               "[--apply --ja-backup-vorhanden]",
        titel="Bausteinarten reparieren",
        gruppe="Migration und Reparatur",
        zweck="Bausteinarten wiederherstellen, die durch einen inzwischen "
              "behobenen Fehler still zurueckgesetzt wurden.",
        art="gemischt",
        datenbanken=("evidence_<uid>.db (mit --apply schreibend)",),
        betrieb="Aendert Ermittlerdaten. Vor dem scharfen Lauf MUSS ein "
                "geprueftes Backup bestehen; das Skript verlangt dafuer eine "
                "ausdrueckliche Bestaetigung und bricht sonst ab.",
        befehle=(
            _b("(ohne --apply)", "lesend",
               "Trockenlauf. Die Vorgabe - es wird nichts geschrieben."),
            _b("--apply", "schreibend",
               "Aenderungen schreiben. Verlangt zusaetzlich die "
               "Backup-Bestaetigung."),
        ),
        hinweis="Zweifelsfaelle werden NICHT angefasst, sondern als unklar "
                "gemeldet.",
    ),
    CliEintrag(
        schluessel="consolidate_default_db",
        pfad="management/consolidate_default_db.py",
        aufruf="python -m management.consolidate_default_db --target D "
               "--source Q [...]",
        titel="default.db zusammenfuehren",
        gruppe="Migration und Reparatur",
        zweck="Mehrere versehentlich je Beschuldigtem angelegte default.db "
              "verlustfrei in eine zentrale zusammenfuehren.",
        art="schreibend",
        datenbanken=("default.db am Ziel (schreibend)",
                     "die Quell-Dateien (strikt lesend, mode=ro)"),
        betrieb="STUFE A - WARTUNGSFENSTER ERFORDERLICH (Analyse Build "
                "609). Zwei Gruende: (1) mit --overwrite wird die vorhandene "
                "Ziel-default.db GELOESCHT, und zwar VOR der Transaktion - "
                "ein Abbruch danach laesst gar keine default.db zurueck, das "
                "Zuruckrollen holt sie nicht wieder. (2) Der ganze Lauf "
                "haengt an EINER Transaktion ueber alle Quellen. Die "
                "default.db haelt der Auswertungsdienst lesend offen. Ein "
                "Backup legt das Werkzeug nicht an."
                "SEIT BUILD 612 SETZT DAS WERKZEUG DAS SELBST DURCH: es prueft vor "
                "dem scharfen Lauf, ob die betroffenen Dateien ruhig sind, bricht "
                "bei einer belegten Datei ohne Rueckfrage ab und faehrt ohne "
                "aktives Wartungsfenster nur nach Eingabe des Wortes 'OHNE "
                "WARTUNGSFENSTER' fort.",
        hinweis="Die Herkunft jeder uebernommenen Zeile wird im Ziel "
                "vermerkt.",
        tiefe=CliTiefe(
            exit_codes=((0, "erledigt, auch mit aufgeloesten Konflikten"),
                        (1, "harter Fehler - der ganze Lauf wurde "
                            "zurueckgerollt"),
                        (3, "Wartungsvorbehalt - der Lauf wurde nicht ausgefuehrt; es wurde NICHTS geschrieben")),
            warnungen=(
                "Mit --overwrite wird die vorhandene Ziel-default.db "
                "GELOESCHT, und zwar VOR der Transaktion. Ein Abbruch danach "
                "laesst gar keine default.db zurueck; das Zurueckrollen holt "
                "sie nicht wieder.",
                "Der ganze Lauf haengt an EINER Transaktion. Es gibt keinen "
                "Wiederaufsetzpunkt - ein Abbruch bedeutet: von vorn.",
                "Ein Backup legt das Werkzeug nicht an.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="convert_journal_mode",
        pfad="tools/convert_journal_mode.py",
        aufruf="python tools/convert_journal_mode.py --data-dir ./data "
               "[--apply]",
        titel="Journalmodus umstempeln",
        gruppe="Migration und Reparatur",
        zweck="Datenbanken zwischen den Journalverfahren umstempeln - der "
              "Weg weg von WAL auf Netzlaufwerken.",
        art="gemischt",
        datenbanken=("ALLE Datenbanken im Datenverzeichnis, einschliesslich "
                     "der versiegelten forensic_<uid>.db (mit --apply "
                     "schreibend)",),
        betrieb="STUFE A - WARTUNGSFENSTER ERFORDERLICH (Nachtrag Build "
                "615). Das Werkzeug nimmt 'locking_mode=EXCLUSIVE', aendert "
                "den DATEIKOPF - die Bytes 18 und 19 sind der Journalstempel "
                "- und hebt dafuer den Schreibschutz voruebergehend auf. Es "
                "fasst dabei auch die versiegelten forensic_<uid>.db an. SEIT "
                "BUILD 615 SETZT ES DAS SELBST DURCH: '--apply' prueft vor "
                "dem Lauf, ob die betroffenen Dateien ruhig sind, bricht bei "
                "einer belegten Datei ohne Rueckfrage ab und faehrt ohne "
                "aktives Wartungsfenster nur nach Eingabe des Wortes 'OHNE "
                "WARTUNGSFENSTER' fort. Der Trockenlauf bleibt frei.",
        befehle=(
            _b("(ohne --apply)", "lesend",
               "Trockenlauf. Die Vorgabe - es wird nichts geschrieben."),
            _b("--apply", "schreibend", "Umstempeln."),
        ),
        hinweis="Bei den versiegelten Datenbanken wird der INHALT vor und "
                "nach dem Vorgang verglichen. Weicht er ab, ist das ein "
                "Siegelbruch und der Lauf bricht hart ab - er wird NICHT "
                "uebersprungen.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/convert_journal_mode.py --data-dir ./data",
                     "Trockenlauf ueber alle Datenbanken. Meldete im Versuch "
                     "'0 von 5 Datenbanken WUERDEN umgestempelt' und endete "
                     "mit 0."),
            ),
            exit_codes=((0, "nichts zu tun oder erfolgreich umgestempelt"),
                        (1, "HARTER ABBRUCH - Siegelbruch, oder ein Fehler "
                            "ohne '--skip-on-error'. Es wurden KEINE "
                            "weiteren Dateien angefasst"),
                        (2, "der Lauf ist durchgelaufen, aber mindestens "
                            "eine Datenbank wurde wegen eines Fehlers "
                            "UEBERSPRUNGEN ('--skip-on-error'). Sie ist "
                            "NICHT konvertiert"),
                        (3, "Wartungsvorbehalt - der Lauf wurde nicht "
                            "ausgefuehrt; es wurde NICHTS geschrieben")),
            warnungen=(
                "Ein SIEGELBRUCH - eine Abweichung des Inhalts-Hashes einer "
                "forensic-Datei - wird NICHT uebersprungen. Der Lauf bricht "
                "hart ab.",
                "DIE RUECKGABEWERTE 1 UND 2 STANDEN BIS BUILD 614 IN "
                "DIESEM KATALOG VERTAUSCHT. Massgeblich ist: 1 heisst "
                "harter Abbruch, es wurde nichts weiter angefasst; 2 heisst, "
                "der Lauf ist durchgelaufen und hat dabei Dateien "
                "uebersprungen. Wer die 2 fuer einen Aufruffehler haelt, "
                "haelt einen unvollstaendigen Lauf fuer einen fehlgeschlagenen "
                "- und zieht die uebersprungenen Dateien nie nach.",
                "'--skip-on-error' ueberspringt operative Fehler WAEHREND des "
                "Laufs. Es hebt den Wartungsvorbehalt nicht auf: der prueft "
                "VOR dem Lauf und nennt in einem Durchgang alle belegten "
                "Dateien. Das ist die Antwort auf den Anlass von Build 433 - "
                "damals brach ein Lauf an der ersten gesperrten Datenbank ab, "
                "und die eigentlich zu konvertierenden Dateien wurden nie "
                "erreicht.",
                "Bei versiegelten Dateien meldet der Vorbehalt 'nicht "
                "pruefbar' und fragt nach - auch bei gesetztem "
                "Wartungsfenster. Das ist hier der Regelfall und kein "
                "Fehler: auf einer schreibgeschuetzten Datei kann die "
                "Sperrprobe nicht messen.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="forensic_index_upgrade",
        pfad="tools/forensic_index_upgrade.py",
        aufruf="python tools/forensic_index_upgrade.py --forensic-dir D "
               "[--ausfuehren]",
        titel="Zeitindizes nachruesten",
        gruppe="Migration und Reparatur",
        zweck="Fehlende Zeitindizes auf den versiegelten forensic-Datenbanken "
              "anlegen, damit die Fristenrechnung in vertretbarer Zeit "
              "laeuft.",
        art="gemischt",
        datenbanken=("forensic_<uid>.db (mit --ausfuehren schreibend)",),
        betrieb="STUFE A - WARTUNGSFENSTER ERFORDERLICH (Analyse Build "
                "609), sobald --ausfuehren gesetzt ist. Geschrieben wird in "
                "die VERSIEGELTE forensic_<uid>.db, die der "
                "Auswertungsdienst lesend offen haelt; ein Leser blockiert "
                "den noetigen Schreibzugriff. Das Werkzeug setzt keine "
                "Wartezeit und legt kein Backup an - scheitert der Zugriff, "
                "bekommt die Datei den Zustand 'fehler' und der Lauf macht "
                "mit der naechsten weiter. Ohne --ausfuehren ist der Lauf "
                "reine Anzeige."
                "SEIT BUILD 612 SETZT DAS WERKZEUG DAS SELBST DURCH: es prueft vor "
                "dem scharfen Lauf, ob die betroffenen Dateien ruhig sind, bricht "
                "bei einer belegten Datei ohne Rueckfrage ab und faehrt ohne "
                "aktives Wartungsfenster nur nach Eingabe des Wortes 'OHNE "
                "WARTUNGSFENSTER' fort.",
        befehle=(
            _b("(ohne --ausfuehren)", "lesend",
               "Trockenlauf. Die Vorgabe."),
            _b("--ausfuehren", "schreibend", "Indizes anlegen."),
        ),
        hinweis="DIE DATEI-PRUEFSUMME AENDERT SICH, DER INHALT NICHT - das "
                "wird vorher und nachher geprueft. Das Werkzeug nimmt nichts "
                "zurueck: ein Entfernen waere eine zweite Aenderung an einer "
                "bereits auffaelligen Datei. Auf WAL-gestempelte Dateien "
                "wird nicht geschrieben; die brauchen zuerst "
                "tools/convert_journal_mode.py.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/forensic_index_upgrade.py --forensic-dir "
                     "./data/forensic",
                     "Trockenlauf. Meldete im Versuch 'Dateien gefunden: 1 / "
                     "aktuell: 1' und endete mit 0 - es wurde nichts "
                     "geschrieben."),
            ),
            exit_codes=((0, "nichts zu tun oder alles erledigt"),
                        (1, "mindestens eine Datei mit Zustand 'fehler'"),
                        (2, "Aufruffehler"),
                        (3, "Wartungsvorbehalt - der Lauf wurde nicht ausgefuehrt; es wurde NICHTS geschrieben")),
            warnungen=(
                "Die DATEI-Pruefsumme aendert sich, der INHALT nicht - das "
                "wird vor und nach dem Lauf geprueft. Wer Pruefsummen "
                "fuehrt, muss sie danach neu erheben.",
                "Auf WAL-gestempelte Dateien wird nicht geschrieben; die "
                "brauchen zuerst tools/convert_journal_mode.py.",
                "Das Werkzeug nimmt nichts zurueck. Weicht die Nachpruefung "
                "ab, wird das benannt - mehr nicht.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="pruefe_migrationskette",
        pfad="tools/pruefe_migrationskette.py",
        aufruf="python tools/pruefe_migrationskette.py --db data/"
               "coordinator.db [--art evidence]",
        titel="Migrationskette pruefen",
        gruppe="Migration und Reparatur",
        zweck="Sichtbar machen, ob eine im Paket vorhandene Migration still "
              "uebersprungen wurde.",
        art="lesend",
        datenbanken=("die benannte Datenbank (lesend, mode=ro)",),
        betrieb="Vor jedem Einspielen aufzurufen; auch auf einer "
                "Produktivdatenbank unbedenklich.",
        hinweis="Exit 2 meldet eine Luecke, Exit 3 eine Version, die das "
                "Paket nicht kennt. Beides ist ein Befund, kein "
                "Programmfehler.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/pruefe_migrationskette.py --db "
                     "./data/coordinator.db --art coordinator",
                     "Vergleicht die im Paket vorhandenen Migrationen mit "
                     "den angewandten. Im Versuch: 37 im Paket, 1 angewandt, "
                     "36 ausstehend - Rueckgabewert 0, weil Ausstehendes "
                     "beim naechsten Start nachlaeuft."),
            ),
            exit_codes=((0, "schluessig"),
                        (1, "Aufruffehler"),
                        (2, "Luecke - eine vorhandene Migration wurde "
                            "uebersprungen"),
                        (3, "die Registrierung kennt eine Version, die das "
                            "Paket nicht hat")),
        ),
    ),
    CliEintrag(
        schluessel="poc_m019_weg_a",
        pfad="tools/poc_m019_weg_a.py",
        aufruf="python tools/poc_m019_weg_a.py kopie.db",
        titel="Nachweislauf zur Schluesselumstellung",
        gruppe="Migration und Reparatur",
        zweck="Auf einer KOPIE nachweisen, dass die Umbenennung des "
              "Fallschluessels durchlaeuft.",
        art="schreibend",
        datenbanken=("ausschliesslich die als Argument uebergebene Datei",),
        betrieb="Ausserhalb des Betriebs, auf einer Kopie.",
        hinweis="ES GIBT KEINE EINGEBAUTE PRUEFUNG, dass die uebergebene "
                "Datei wirklich eine Kopie ist - der Schutz ist "
                "organisatorisch. '--seed' fuellt Testzeilen ein und gehoert "
                "NICHT auf eine Kopie mit echten Daten.",
    ),

    # ---------------------------------------------------------------- Diagnose
    CliEintrag(
        schluessel="diag_limitation_laufzeit",
        pfad="tools/diag_limitation_laufzeit.py",
        aufruf="python tools/diag_limitation_laufzeit.py [--runs 5] [--url U]",
        titel="Laufzeit der Fristenrechnung messen",
        gruppe="Diagnose",
        zweck="Messen, wie lange die Fristenrechnung braucht.",
        art="lesend",
        datenbanken=("coordinator.db, forensic_<uid>.db, evidence_<uid>.db "
                     "(alle lesend, mode=ro)",),
        betrieb="Im laufenden Betrieb gefahrlos. Mit --url muss der Dienst "
                "laufen und die aufrufende Person das Leserecht haben.",
        hinweis="Diagnose, nicht Teil des Produktivsystems.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/diag_limitation_laufzeit.py "
                     "--coordinator-db ./data/coordinator.db --forensic-dir "
                     "./data/forensic --evidence-dir ./data/evidence --runs 1",
                     "Mass den Fristenmonitor und gab am Ende den Block "
                     "'ERGEBNIS ZUM ZURUECKMELDEN' aus, der KEINE Fallinhalte "
                     "enthaelt. Auf dem leeren Wegwerf-Bestand: Faelle 0, "
                     "erster Lauf 948 us. Rueckgabewert 0.",
                     _GEPRUEFT_614),
            ),
            exit_codes=((0, "gemessen"),
                        (2, "coordinator.db nicht gefunden")),
            warnungen=(
                "KEIN RUECKGABEWERT MELDET EINEN BEFUND. Auch 'keine "
                "Zeitkandidaten gefunden' - laut dem Werkzeug selbst ein "
                "wichtiger Befund - und Lesefehler enden mit 0. Die Aussage "
                "steht ausschliesslich im Text.",
                "DER TEUERSTE TEIL IST DIE SCHEMA-SONDE: sie rechnet je "
                "Spalte je Tabelle ueber die Stichprobe, und die Stichprobe "
                "enthaelt ausdruecklich die GROESSTEN Dateien. Auf einem "
                "Netzlaufwerk sind das vollstaendige Tabellendurchlaeufe auf "
                "Dateien im Gigabyte-Bereich.",
                "Der Docstring der Stichprobe sagt an einer Stelle noch, es "
                "wuerden die KLEINSTEN Dateien genommen; das trifft seit der "
                "vierten Fassung nicht mehr zu. Massgeblich ist die "
                "Groessenspanne einschliesslich der groessten Dateien.",
                "'--schema-dateien' ist eine MINDESTZAHL, keine Obergrenze - "
                "wer 1 angibt, bekommt trotzdem bis zu 15 Dateien.",
                "Die Zahl 'Faelle ohne Datei' ist eine Differenz aus Fallzahl "
                "und Dateizahl, keine Pruefung je Fall. Ueberzaehlige "
                "forensic-Dateien ohne Fall druecken sie nach unten.",
                "'--url' sendet KEINE Anmeldung. Ein 403 heisst hier "
                "regelmaessig: das Recht 'limitation.view' fehlt.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="diag_matrix_laufzeit",
        pfad="tools/diag_matrix_laufzeit.py",
        aufruf="python tools/diag_matrix_laufzeit.py [--runs 5] [--url U]",
        titel="Laufzeit der Matrix messen",
        gruppe="Diagnose",
        zweck="Messen, was die Fristenkomponente der Dringlichkeitsmatrix "
              "kostet.",
        art="lesend",
        datenbanken=("coordinator.db, forensic_<uid>.db, evidence_<uid>.db "
                     "(alle lesend, mode=ro)",),
        betrieb="Im laufenden Betrieb gefahrlos.",
        hinweis="Diagnose, nicht Teil des Produktivsystems.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/diag_matrix_laufzeit.py --coordinator-db "
                     "./data/coordinator.db --forensic-dir ./data/forensic "
                     "--evidence-dir ./data/evidence --runs 1",
                     "Mass die Matrix zweimal - mit und ohne Fristkomponente - "
                     "und nannte den Faktor zwischen beiden. Auf dem leeren "
                     "Wegwerf-Bestand: ohne Frist 1,7 ms, mit Frist 9,3 ms, "
                     "Faktor 5,6x. Rueckgabewert 0.",
                     _GEPRUEFT_614),
            ),
            exit_codes=((0, "gemessen"),
                        (2, "coordinator.db nicht gefunden")),
            warnungen=(
                "EIN GESCHEITERTER LAUF AENDERT DEN RUECKGABEWERT NICHT. "
                "Messfehler werden gedruckt, das Werkzeug endet trotzdem "
                "mit 0.",
                "MIT '--url' BLOCKIERT DER AUFRUF BIS ZU 600 SEKUNDEN JE "
                "ABRUF, ohne dass zwischendurch etwas ausgegeben wird. Bei "
                "'--runs 3' koennen daraus eine halbe Stunde werden.",
                "Die Selbstmessung der Antwort steht NEBEN der Stoppuhr und "
                "ersetzt sie nicht. Eine Abweichung zwischen beiden ist eine "
                "eigene Aussage und kein Widerspruch.",
                "Die Zeile mit dem Faktor fehlt kommentarlos, wenn die "
                "Vergleichsmessung 0 ergibt - bei sehr kleinem Bestand ist "
                "das der Regelfall.",
                "Gebraucht wird mehr als die Tabelle 'cases': die Matrix "
                "liest eine Sicht, die erst eine Migration anlegt. Eine von "
                "Hand gebaute Datei genuegt hier nicht.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="diag_sqlite_netdrive",
        pfad="tools/diag_sqlite_netdrive.py",
        aufruf="python tools/diag_sqlite_netdrive.py --data-dir ./data",
        titel="Journalverfahren auf dem Netzlaufwerk pruefen",
        gruppe="Diagnose",
        zweck="Pruefen, welche Journalverfahren auf dem Netzlaufwerk "
              "tragen - nicht zerstoerend.",
        art="lesend",
        datenbanken=("die vorhandenen Datenbanken (nur lesend); die "
                     "Schreibversuche laufen gegen eigens angelegte "
                     "Probedateien",),
        betrieb="Legt Probedateien und eine Protokolldatei im "
                "Datenverzeichnis an und raeumt die Probedateien wieder weg.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/diag_sqlite_netdrive.py --data-dir "
                     "./data --skip-local",
                     "Nahm den Bestand auf und fuhr die fuenf Journalmodi "
                     "gegen eigene Probedateien. Auf einem LOKALEN "
                     "Dateisystem waren alle fuenf gruen (WAL, WAL+exklusiv, "
                     "DELETE, TRUNCATE, PERSIST), je mit Schreiben und "
                     "Ruecklesen belegt. Rueckgabewert 0. Die Protokolldatei "
                     "diag_sqlite_netdrive.log blieb im aufrufenden "
                     "Verzeichnis liegen.",
                     _GEPRUEFT_614),
            ),
            exit_codes=((0, "durchgelaufen - AUCH DANN, wenn kein einziger "
                            "Modus getragen hat, wenn das Datenverzeichnis "
                            "fehlt oder wenn gar keine Datenbank gefunden "
                            "wurde"),),
            warnungen=(
                "ES GIBT NUR DEN RUECKGABEWERT 0. Der Befund steht "
                "ausschliesslich im Text bzw. in der Protokolldatei. Fuer "
                "eine automatische Auswertung taugt das Werkzeug nicht.",
                "EXISTIERT DAS DATENVERZEICHNIS NICHT, wird BEIDES "
                "uebersprungen - Bestandsaufnahme und Messung. Das Werkzeug "
                "laeuft dann 'erfolgreich' durch und hat nichts gemessen.",
                "AUSSERHALB VON WINDOWS entfaellt die Kernaussage: der Beleg "
                "'dies ist ein Netzlaufwerk' laesst sich dort nicht "
                "erheben, und alle Modi sind trivialerweise gruen. Der Lauf "
                "erzeugt dann nur die Vergleichsgruppe 'lokal'.",
                "ES SCHREIBT - auch wenn es als lesend gefuehrt ist: fuenf "
                "Probedatenbanken im Datenverzeichnis (aufgeraeumt, auch im "
                "Fehlerfall) und eine Protokolldatei im AUFRUFENDEN "
                "Verzeichnis, die liegen bleibt. Die echten Datenbanken "
                "bleiben unberuehrt.",
                "Bei einem harten Abbruch bleiben Probedateien mit dem "
                "Praefix '_probe_' im Datenverzeichnis liegen.",
                "Ein gruenes PRAGMA gilt bewusst NICHT als Beleg. Erst "
                "Schreiben und Ruecklesen zaehlen - das ist der Grund, aus "
                "dem dieses Werkzeug ueberhaupt gebaut wurde.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="diag_sqlite_netdrive2",
        pfad="tools/diag_sqlite_netdrive2.py",
        aufruf="python tools/diag_sqlite_netdrive2.py --data-dir ./data "
               "--db <datei>",
        titel="Zugriffsarten auf dem Netzlaufwerk vergleichen",
        gruppe="Diagnose",
        zweck="Zwei Zugriffsarten auf dem Netzlaufwerk gegeneinander "
              "messen - nicht zerstoerend.",
        art="lesend",
        datenbanken=("die gewaehlte Datenbank wird KOPIERT, nicht "
                     "veraendert; die grosse default.db wird nur gelesen",),
        betrieb="Braucht Platz in Groesse der gewaehlten Datenbank fuer die "
                "Kopie; die Kopie wird danach entfernt.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/diag_sqlite_netdrive2.py --data-dir ./data "
                     "--db ./data/evidence/evidence_1000001.db",
                     "Fuhr die sieben Kandidaten gegen eine Vollkopie der "
                     "angegebenen Datei. Auf einem LOKALEN Dateisystem waren "
                     "alle sieben gruen. Rueckgabewert 0; nach dem Lauf lagen "
                     "keine Kopien mehr im Verzeichnis, die Protokolldatei "
                     "blieb liegen.",
                     _GEPRUEFT_614),
                _bsp("python tools/diag_sqlite_netdrive2.py --data-dir ./data",
                     "VERWEIGERUNG bei mehreren evidence-Dateien: das "
                     "Werkzeug fuehrte alle gefundenen samt Journalstempel "
                     "auf und verlangte '--db'. Rueckgabewert 1. Das ist kein "
                     "Fehler, sondern die Lehre aus der ersten Fassung, die "
                     "sich still die alphabetisch erste Datei genommen und "
                     "damit die falsche vermessen hatte.",
                     _GEPRUEFT_614),
            ),
            exit_codes=((0, "durchgelaufen - AUCH DANN, wenn jeder Kandidat "
                            "gescheitert ist"),
                        (1, "'--db' fehlt bei mehreren evidence-Dateien "
                            "(bewusste Verweigerung), die angegebene Datei "
                            "fehlt, es wurde gar keine gefunden, oder die "
                            "Kopie liess sich nicht anlegen")),
            warnungen=(
                "ES LEGT SIEBEN VOLLKOPIEN DER GEWAEHLTEN "
                "BEWEISMITTEL-DATENBANK AN - eine je Testfall, nacheinander, "
                "im selben Verzeichnis - und setzt auf jede Kopie Lese- UND "
                "SCHREIBRECHT FUER ALLE. Auf einem geteilten Laufwerk ist das "
                "nicht auf die aufrufende Person beschraenkt. Vorgang: siehe "
                "Issue-Tracker.",
                "Platzbedarf und I/O-Last betragen das SIEBENFACHE der "
                "gewaehlten Datei (immer nur eine Kopie gleichzeitig, aber "
                "siebenmal nacheinander). Der Kopiervorgang blockiert ohne "
                "Fortschrittsanzeige.",
                "Bei einem harten Abbruch bleibt eine Kopie mit dem Praefix "
                "'_probe2_' liegen - und das Schwesterwerkzeug "
                "diag_sqlite_netdrive schliesst beim Bestandsdurchgang nur "
                "'_probe_' aus, nicht '_probe2_'. Es wuerde die "
                "liegengebliebene Kopie also wie eine regulaere Datenbank "
                "mitvermessen.",
                "AUF EINEM LOKALEN DATEISYSTEM SIND ALLE SIEBEN KANDIDATEN "
                "TRIVIALERWEISE GRUEN. Die Frage, fuer die das Werkzeug "
                "gebaut wurde, laesst sich nur auf dem echten Share "
                "beantworten.",
                "Die Zeile 'Schreibgeschuetzt' bezieht sich auf das ORIGINAL; "
                "die Tests laufen auf der Kopie. Nicht verwechseln.",
                "default.db wird ausdruecklich NICHT kopiert - sie ist dafuer "
                "zu gross. Sie wird nur lesend abgefragt.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="diag_migrationsluecke",
        pfad="tools/diag_migrationsluecke.py",
        aufruf="python tools/diag_migrationsluecke.py",
        titel="Nachstellung der Migrationsluecke",
        gruppe="Diagnose",
        zweck="Den Befund nachstellen, dass beim Migrieren ein Hoechststand "
              "statt einer Menge angewandter Versionen gefuehrt wird.",
        art="lesend",
        datenbanken=("keine - der Nachweis laeuft vollstaendig im "
                     "Arbeitsspeicher",),
        betrieb="Ueberall gefahrlos; es wird keine Datei angefasst.",
        hinweis="Ein BELEG, kein Produktivcode. Ohne Argumente aufzurufen.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/diag_migrationsluecke.py",
                     "Fuehrte den Nachweis im Arbeitsspeicher: 'Lauf 1: [40]', "
                     "'Lauf 2: []', 'registrierte Versionen: [40]'. Die "
                     "nachgelieferten niedrigeren Migrationen wurden also "
                     "uebersprungen - ohne Fehler und ohne Registereintrag. "
                     "Rueckgabewert 0.",
                     _GEPRUEFT_614),
            ),
            exit_codes=((0, "durchgelaufen - AUCH DANN, wenn die Luecke "
                            "reproduziert wurde"),),
            warnungen=(
                "DER NACHGEWIESENE MANGEL SCHLAEGT SICH NICHT IM "
                "RUECKGABEWERT NIEDER. Das Werkzeug ist ein Beleg zum Lesen "
                "und keine Pruefung fuer eine Kette; wer es in einen "
                "Regressionslauf haengt, bekommt immer 'gruen'.",
                "DIE VERSIONSNUMMERN 33 BIS 40 SIND ATTRAPPEN und haengen an "
                "keiner echten Migrationsdatei. Sie werden bewusst nicht "
                "nachgezogen - ein Beleg, der rueckwirkend umgeschrieben "
                "wird, ist kein Beleg mehr. Wer daraus den aktuellen "
                "Nummernstand ablesen will, liest falsch.",
                "Die Umnummerierung hat die KONKRETE Luecke beseitigt, nicht "
                "die Ursache im Migrations-Ausfuehrer. Der Befund gilt "
                "weiter; der Lauf zu Build 614 hat das bestaetigt.",
            ),
        ),
    ),

    # ------------------------------------------------- Start und Einrichtung
    CliEintrag(
        schluessel="management",
        pfad="management.py",
        aufruf="python management.py [--auto-port] [--open-browser]",
        titel="Verwaltungsdienst starten",
        gruppe="Start und Einrichtung",
        zweck="Den Verwaltungsdienst starten, der die Cockpit-Sichten "
              "ausliefert.",
        art="lesend",
        datenbanken=("coordinator.db (lesend)",),
        betrieb="Der Normalbetrieb. Mit --maintenance ist der Start NUR bei "
                "aktivem Wartungsfenster erlaubt.",
        hinweis="Keine Schreibpfade: der Dienst liest.",
        tiefe=CliTiefe(
            exit_codes=((0, "sauber beendet"),
                        (1, "kein coordinator.db-Pfad, Datei nicht gefunden, "
                            "kein freier Port, '--maintenance' ohne aktives "
                            "Wartungsfenster, unvollstaendiger "
                            "Rechtekatalog, Identitaet nicht aufloesbar, "
                            "oder die Adresse liess sich nicht belegen")),
            warnungen=(
                "ES LAEUFT DAUERHAFT und kehrt erst nach dem Beenden "
                "zurueck. Vorgabe ist 127.0.0.1:8090.",
                "DER OS-BENUTZERNAME MUSS IN DER PERSONENTABELLE STEHEN, "
                "sonst startet es nicht. Fuer eine Erprobung gibt es "
                "'--as-user'.",
                "OHNE VOLLSTAENDIGEN RECHTEKATALOG IN DER DATENBANK bricht "
                "der Start ab. Ein blosser Entwicklungs-Bootstrap genuegt "
                "dafuer nicht.",
                "ES MIGRIERT BEWUSST NICHT SELBST. Es meldet den "
                "Migrationsstand und nennt den zustaendigen Aufruf - zwei "
                "Wege, die dasselbe schreiben, waeren zwei Wahrheiten ueber "
                "den Beleg.",
                "Eine Adresse ausserhalb von localhost erzeugt nur eine "
                "Warnung und keinen Abbruch.",
                "'--config' wird RELATIV ZUM AKTUELLEN VERZEICHNIS gesucht - "
                "anders als beim Auswertungsdienst, der neben seiner eigenen "
                "Datei nachsieht.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="main",
        pfad="main.py",
        aufruf="python main.py [--mode job|cli|support] [--subject-id N]",
        titel="Auswertungsdienst starten",
        gruppe="Start und Einrichtung",
        zweck="Den forensischen Auswertungsdienst zu einem Fall starten.",
        art="gemischt",
        datenbanken=("evidence_<uid>.db und coordinator.db (schreibend)",
                     "forensic_<uid>.db, default.db und assets_<uid>.db "
                     "(strikt lesend, mode=ro)"),
        betrieb="Der Normalbetrieb je Fall.",
        befehle=(
            _b("--mode job", "schreibend", "Regelbetrieb."),
            _b("--mode cli", "schreibend", "Betrieb ohne Browserfenster."),
            _b("--mode support", "lesend",
               "Wie cli, aber die Aenderungen gehen in eine "
               "Zwischendatenbank."),
        ),
        hinweis="Die versiegelte forensic-Datenbank wird IMMER nur lesend "
                "geoeffnet. Jeder Fehler beim Start fuehrt zum harten "
                "Abbruch - kein stiller Betrieb unter unklaren Bedingungen.",
        tiefe=CliTiefe(
            exit_codes=((0, "sauber beendet"),
                        (1, "Konfiguration, Protokollierung, Systembenutzer, "
                            "Startmodus, Wartungsfenster, Startpruefung, "
                            "hosts-Eintrag, Datenbankverbindungen, freier "
                            "Port oder Adressbelegung - jeder dieser "
                            "Startschritte kann abbrechen, jeweils mit "
                            "eigener Meldung")),
            warnungen=(
                "ES LAEUFT DAUERHAFT und kehrt erst nach dem Beenden "
                "zurueck. Vorgabe ist 127.0.0.2:8080.",
                "IN DEN MODI 'cli' UND 'support' IST '--subject-id' ODER "
                "'--username' PFLICHT, obwohl beide formal Wahloptionen "
                "sind. Fehlt beides, bricht die Modusaufloesung ab.",
                "DIE VORGABE DES MODUS STEHT NICHT IM CODE, SONDERN IN DER "
                "config.yaml. Der im Code hinterlegte Rueckfall lautet "
                "'job', die ausgelieferte Konfiguration setzt aber 'cli' - "
                "und die Konfiguration hat Vorrang.",
                "forensic_<uid>.db und default.db MUESSEN VORHANDEN SEIN. "
                "evidence_<uid>.db dagegen wird angelegt, wenn sie fehlt.",
                "Der Journalmodus wird beim Start auf evidence_<uid>.db und "
                "coordinator.db gesetzt - das ist ein Schreibvorgang auf "
                "bestehende Dateien.",
                "Protokolldatei und Einfrier-Abzug gehen dorthin, wo die "
                "Konfiguration es sagt (Vorgabe './logs/'), RELATIV ZUM "
                "AUFRUFENDEN VERZEICHNIS. Eine Kommandozeilenoption dafuer "
                "gibt es nicht.",
                "Der hosts-Eintrag wird nur angefasst, wenn die "
                "Konfiguration das ausdruecklich erlaubt; in der "
                "ausgelieferten Fassung ist das abgeschaltet.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="run_tests",
        pfad="run_tests.py",
        aufruf="python run_tests.py [--python-only|--js-only]",
        titel="Regressionslauf",
        gruppe="Start und Einrichtung",
        zweck="Beide Testsuiten fahren - die Python-Seite und die "
              "JavaScript-Seite - und eine gemeinsame Zusammenfassung geben.",
        art="lesend",
        datenbanken=("keine der Produktivdatenbanken; die Tests arbeiten mit "
                     "eigenen Wegwerfdaten",),
        betrieb="Vor jeder Uebergabe zu fahren.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python run_tests.py",
                     "Fuhr beide Suiten und fasste sie zusammen. Im "
                     "Bau-Container zu diesem Build: pytest bestanden, vitest "
                     "bestanden, 'Alle Testsuites bestanden'. Rueckgabewert "
                     "0. Laufzeit rund acht Minuten.",
                     _GEPRUEFT_614),
            ),
            exit_codes=((0, "alle gefahrenen Suiten bestanden"),
                        (1, "mindestens eine Suite ist gescheitert oder war "
                            "nicht ausfuehrbar")),
            warnungen=(
                "DER TESTPFAD IST FEST VERDRAHTET ('tests/' bzw. "
                "'tests/unit/'). Es gibt keine Option, einzelne Dateien oder "
                "Muster zu waehlen - dafuer ist pytest unmittelbar "
                "aufzurufen.",
                "FEHLT 'node_modules', WIRD 'npm install' VON SELBST "
                "AUSGEFUEHRT. Auf einer Maschine ohne Internetzugang "
                "scheitert der Lauf dann an dieser Stelle und nicht an einem "
                "Test.",
                "Ein UEBERSPRUNGENES Testmodul sagt das nicht von selbst. "
                "Fehlt eine Zusatzbibliothek, zaehlt die Zusammenfassung ein "
                "einziges 'skipped' - dahinter koennen zehn Tests stehen. Wer "
                "eine Zahl mit einem frueheren Lauf vergleicht, sollte "
                "zusaetzlich 'pytest -rs' fahren.",
                "Die Suite setzt Python 3.12 oder neuer voraus.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="install",
        pfad="install.py",
        aufruf="python install.py [--target dev|prod] [--os win|linux]",
        titel="Installieren",
        gruppe="Start und Einrichtung",
        zweck="Die Anlage auf dem Zielsystem installieren.",
        art="schreibend",
        datenbanken=("keine",),
        betrieb="Vor der Inbetriebnahme. Schreibt ins Dateisystem, nicht in "
                "Datenbanken.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python install.py --target dev --os linux",
                     "Gefahren in einem WEGWERF-VENV, damit die Systemumgebung "
                     "unberuehrt bleibt. Der Lauf brach ab: 'Could not find a "
                     "version that satisfies the requirement pyyaml (from "
                     "versions: none)', Rueckgabewert 1 - das "
                     "Offline-Verzeichnis setup/linux64/wheels enthaelt zum "
                     "Zeitpunkt dieses Builds nur ein einziges Rad. Das "
                     "Werkzeug hat richtig gemeldet; der Mangel liegt beim "
                     "Erzeugen des Pakets (siehe Issue-Tracker).",
                     _GEPRUEFT_614),
            ),
            exit_codes=((0, "installiert und nachgeprueft"),
                        (1, "Python zu alt, 'pip install' gescheitert, oder "
                            "ein Paket war nach der Installation nicht "
                            "einlesbar")),
            warnungen=(
                "ES INSTALLIERT IN DEN GERADE LAUFENDEN INTERPRETER - kein "
                "venv, kein '--user', kein Zielverzeichnis. Wer es "
                "ausprobieren will, aktiviert vorher eine Wegwerf-Umgebung.",
                "'--upgrade' KANN VORHANDENE PAKETVERSIONEN ANHEBEN. Das ist "
                "nicht von selbst rueckholbar, und ein zweiter Lauf ist "
                "nicht versionsstabil.",
                "DIE OFFLINE-RAEDER SIND AN EINE PYTHON-NEBENVERSION "
                "GEBUNDEN (gebaut fuer 3.14). Unter einer anderen "
                "Nebenversion meldet pip 'No matching distribution found' - "
                "auch dann, wenn die Datei im Verzeichnis liegt. Die Meldung "
                "weist dabei auf das erste fehlende Paket und nicht auf die "
                "Versionsbindung.",
                "Fehlt das Rad-Verzeichnis ganz, wird STILL auf eine "
                "Online-Installation umgeschaltet. Auf einer Maschine ohne "
                "Internetzugang scheitert die dann.",
                "Node wird nur GEPRUEFT, nicht installiert.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="prepare_deployment",
        pfad="prepare_deployment.py",
        aufruf="python prepare_deployment.py [--skip-bundle] [--skip-wheels]",
        titel="Auslieferung vorbereiten",
        gruppe="Start und Einrichtung",
        zweck="Die Verzeichnisse fuer den Installationslauf vorbereiten.",
        art="schreibend",
        datenbanken=("keine",),
        betrieb="Laeuft auf einem Rechner MIT Internetzugang - nicht auf der "
                "Anlage.",
        tiefe=CliTiefe(
            exit_codes=((0, "durchgelaufen - AUCH DANN, wenn der "
                            "Rad-Download vollstaendig gescheitert ist"),
                        (1, "das Bundle-Skript fehlt oder der Bundle-Bau ist "
                            "gescheitert")),
            warnungen=(
                "EIN GESCHEITERTER RAD-DOWNLOAD AENDERT DEN RUECKGABEWERT "
                "NICHT. Er erscheint als 'WARNUNG', und der Lauf endet mit 0. "
                "Das Ergebnis liegt im Bestand: setup/win64/wheels ist "
                "vollstaendig, setup/linux64/wheels enthaelt ein einziges "
                "Rad. Vorgang: siehe Issue-Tracker.",
                "ES UEBERSCHREIBT IM ARBEITSBESTAND, und es gibt KEINE Option, "
                "das Ziel zu verlegen: die Editor-Buendel unter "
                "static/editor/, beide setup/README.txt und das "
                "deployment_manifest.json. Ein gefahrloser Probelauf ist "
                "damit nicht moeglich - auch nicht mit '--skip-bundle "
                "--skip-wheels'.",
                "Das Rad-Verzeichnis wird NICHT geleert. Ueber mehrere "
                "Versionen sammeln sich dort verschiedene Staende derselben "
                "Pakete an.",
                "Es braucht Node und einen Internetzugang. Schlaegt der "
                "versionsgenaue Download fehl, greift ein Rueckfall ohne "
                "Plattformbindung - der kann Raeder der FALSCHEN Plattform "
                "ablegen.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="setup_coordinator_dev",
        pfad="setup_coordinator_dev.py",
        aufruf="python setup_coordinator_dev.py [--db ./data/coordinator.db]",
        titel="Entwicklungsbestand anlegen",
        gruppe="Start und Einrichtung",
        zweck="Einen minimalen Entwicklungsbestand in der coordinator.db "
              "anlegen.",
        art="schreibend",
        datenbanken=("coordinator.db (schreibend)",),
        betrieb="Nur in der Entwicklung.",
        hinweis="ABGEKUENDIGT: hat keine regulaere Verwendung mehr und wird "
                "mittelfristig entfernt. Der Eintrag steht hier, damit das "
                "Werkzeug nicht unbemerkt liegen bleibt.",
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python setup_coordinator_dev.py --db "
                     "/tmp/wegwerf/coordinator.db",
                     "Legte die Datei samt Verzeichnis an, erzeugte die "
                     "Minimaltabellen, drei Dummy-Ermittler und einen "
                     "DEV-Job und schloss mit 'Abgeschlossen - keine Fehler'. "
                     "Rueckgabewert 0. Erst danach laeuft 'python -m "
                     "management.migrate' durch - auf einer nur angelegten "
                     "Datei bricht es bei der zweiten Migration ab.",
                     _GEPRUEFT_614),
            ),
            exit_codes=((0, "angelegt bzw. bereits vorhanden"),
                        (1, "unbehandelte Ausnahme - etwa wenn eine "
                            "erwartete Spalte nach dem Anlegen fehlt")),
            warnungen=(
                "ES IST ABGEKUENDIGT und baut ABSICHTLICH einen alten "
                "Schemastand (Tabelle 'investigators' statt 'person', Spalte "
                "'user_id' statt 'subject_id'). Das ist kein Versehen: die "
                "nachfolgenden Migrationen finden so ihren Anker und "
                "benennen verlustfrei um. Wer daraus den aktuellen "
                "Schemastand ablesen will, liest falsch.",
                "OHNE '--db' TRIFFT ES './data/coordinator.db' RELATIV ZUM "
                "AKTUELLEN VERZEICHNIS. Auf einer echten coordinator.db "
                "spielt es drei erfundene Personen und einen Schein-Job ein, "
                "die nur von Hand wieder herauszubekommen sind.",
                "Es ist wiederholbar aufrufbar; die Eintraege entstehen nur "
                "einmal. Ein 'ALTER TABLE' laesst sich aber nicht "
                "zuruecknehmen.",
                "Es muss aus der Wurzel des Bestands aufgerufen werden - es "
                "biegt den Suchpfad nicht selbst zurecht.",
            ),
        ),
    ),
)


#: Schluessel -> Eintrag.
_NACH_SCHLUESSEL: Dict[str, CliEintrag] = {e.schluessel: e
                                           for e in CLI_KATALOG}

#: Pfad -> Eintrag. Der Pfad ist der Schluessel des Abgleichs gegen den
#: Bestand: was auf der Platte liegt, muss hier stehen - und umgekehrt.
_NACH_PFAD: Dict[str, CliEintrag] = {e.pfad: e for e in CLI_KATALOG}

#: Alle Schluessel in Katalogreihenfolge.
CLI_SCHLUESSEL: Tuple[str, ...] = tuple(e.schluessel for e in CLI_KATALOG)

#: Alle Pfade in Katalogreihenfolge.
CLI_PFADE: Tuple[str, ...] = tuple(e.pfad for e in CLI_KATALOG)


class CliKatalogError(Exception):
    """Der Katalog ist in sich unstimmig."""


def eintrag(schluessel: str) -> Optional[CliEintrag]:
    """Der Eintrag zu einer Kurzkennung, oder None."""
    return _NACH_SCHLUESSEL.get(schluessel)


def eintrag_zu_pfad(pfad: str) -> Optional[CliEintrag]:
    """Der Eintrag zu einem Dateipfad, oder None."""
    return _NACH_PFAD.get(pfad.replace("\\", "/"))


def gruppen() -> Tuple[Tuple[str, Tuple[CliEintrag, ...]], ...]:
    """
    Die Eintraege nach Arbeitsbereich, in der Reihenfolge von
    GRUPPEN_REIHENFOLGE. Leere Gruppen entfallen.
    """
    raus: List[Tuple[str, Tuple[CliEintrag, ...]]] = []
    for g in GRUPPEN_REIHENFOLGE:
        treffer = tuple(e for e in CLI_KATALOG if e.gruppe == g)
        if treffer:
            raus.append((g, treffer))
    return tuple(raus)


def suche(begriff: str) -> Tuple[CliEintrag, ...]:
    """
    Volltextsuche ueber Kennung, Titel, Zweck, Aufruf und die Unterbefehle.
    Gross- und Kleinschreibung spielt keine Rolle.
    """
    b = (begriff or "").strip().lower()
    if not b:
        return ()
    raus: List[CliEintrag] = []
    for e in CLI_KATALOG:
        heuhaufen = " ".join([
            e.schluessel, e.titel, e.zweck, e.aufruf, e.gruppe, e.hinweis,
            " ".join(b2.name + " " + b2.zweck for b2 in e.befehle),
        ]).lower()
        if b in heuhaufen:
            raus.append(e)
    return tuple(raus)


def fehlliste_cli_beispiele() -> Tuple[str, ...]:
    """
    Die ABGELEITETE Fehlliste der Werkzeuge ohne GEPRUEFTE Beispielaufrufe.

    WARUM NEBEN fehlliste_cli_tiefe() EINE ZWEITE LISTE: Exit-Codes und
    Warnungen lassen sich am Quelltext belegen; ein Beispiel muss GEFAHREN
    werden, und genau das ist der teure Teil. Ohne diese zweite Liste saehe
    ein Eintrag mit Exit-Codes fertig aus, obwohl der Nachweis fehlt.
    """
    return tuple(e.schluessel for e in CLI_KATALOG if not e.hat_beispiele())


def fehlliste_cli_tiefe() -> Tuple[str, ...]:
    """
    Die ABGELEITETE Fehlliste der Werkzeuge ohne Tiefeninhalt.

    Sie wird nicht gepflegt, sondern gerechnet - eine gepflegte Liste koennte
    luegen. Bis H17/H18 stehen hier alle Werkzeuge; das ist der ehrliche
    Stand und kein Versaeumnis, das man verschweigen duerfte.
    """
    return tuple(e.schluessel for e in CLI_KATALOG if not e.hat_tiefe())


def verify_katalog_konsistent() -> None:
    """
    Der Katalog ist in sich stimmig:
      * Kurzkennungen sind eindeutig,
      * Pfade sind eindeutig,
      * jede Gruppe ist eine bekannte Gruppe,
      * jeder Eintrag mit Unterbefehlen nennt sie eindeutig.
    """
    doppelt_k = sorted({e.schluessel for e in CLI_KATALOG
                        if CLI_SCHLUESSEL.count(e.schluessel) > 1})
    if doppelt_k:
        raise CliKatalogError(
            "Doppelte Kurzkennungen: %s" % ", ".join(doppelt_k))

    doppelt_p = sorted({e.pfad for e in CLI_KATALOG
                        if CLI_PFADE.count(e.pfad) > 1})
    if doppelt_p:
        raise CliKatalogError("Doppelte Pfade: %s" % ", ".join(doppelt_p))

    fremd = sorted({e.gruppe for e in CLI_KATALOG
                    if e.gruppe not in GRUPPEN_REIHENFOLGE})
    if fremd:
        raise CliKatalogError(
            "Eintraege mit unbekanntem Arbeitsbereich: %s" % ", ".join(fremd))

    for e in CLI_KATALOG:
        namen = [b.name for b in e.befehle]
        doppelt_b = sorted({n for n in namen if namen.count(n) > 1})
        if doppelt_b:
            raise CliKatalogError(
                "%s: doppelte Unterbefehle %s"
                % (e.schluessel, ", ".join(doppelt_b)))


def verify_cli_abgedeckt(gefundene_pfade: Iterable[str]) -> None:
    """
    Der Abgleich Katalog <-> Bestand, in BEIDE Richtungen:
      * jedes gefundene Werkzeug hat einen Katalogeintrag,
      * jeder Katalogeintrag zeigt auf eine vorhandene Datei.

    Warum beide Richtungen: Ein neues Werkzeug ohne Eintrag bliebe sonst
    unsichtbar - und ein Eintrag zu einer geloeschten Datei liesse die
    Uebersicht laenger aussehen, als sie ist. Beides faellt hier auf, und
    zwar beim Bauen und nicht im Betrieb.
    """
    gefunden = {p.replace("\\", "/") for p in gefundene_pfade}
    im_katalog = set(CLI_PFADE)

    ohne_eintrag = sorted(gefunden - im_katalog)
    if ohne_eintrag:
        raise CliKatalogError(
            "Werkzeuge im Bestand OHNE Katalogeintrag: %s. Jedes Werkzeug "
            "braucht einen Eintrag - sonst weiss niemand, dass es es gibt."
            % ", ".join(ohne_eintrag))

    ohne_datei = sorted(im_katalog - gefunden)
    if ohne_datei:
        raise CliKatalogError(
            "Katalogeintraege OHNE Datei im Bestand: %s. Entweder ist die "
            "Datei entfallen (dann gehoert der Eintrag weg) oder sie wurde "
            "verschoben (dann gehoert der Pfad nachgezogen)."
            % ", ".join(ohne_datei))
