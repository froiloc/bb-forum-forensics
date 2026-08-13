# =============================================================================
# management/help/cli_katalog.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H15)
# =============================================================================
# Zweck:
#   Der Katalog der Kommandozeilen-Werkzeuge. EIN Grundeintrag je Werkzeug,
#   vollzaehlig: 66 Eintraege (Stand Build 630) - 35 Verwaltungswerkzeuge
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
# AENDERUNG BUILD 696 (Ticket 9e1ba63e): EINE Textstelle - die Beschreibung
#   des Unterbefehls 'zeige' beim Eintrag 'hilfe'. Sie sagte bisher, die
#   Ausgabe ende mit dem '--help'-Aufruf "des Zielwerkzeugs"; genau das traf
#   bei vier Werkzeugen nicht zu. Mit der Berichtigung in cli_text.py trifft
#   es zu, und die Beschreibung sagt jetzt ausdruecklich, dass NIE ein
#   Unterbefehl gemeint ist. Das ist die Hilfe-Anpassung zu dieser Aenderung
#   (Gebot 'keine Aenderung ohne Anpassung in der Hilfe').
#
#
# BUILD 702/706 (Vorgaenge ff7e80ab und 70641ff9) - DER ERZEUGUNGSVERMERK.
#   Die Warnungen zu 'forecast_report_admin' und 'status_report_admin' standen
#   seit Build 613 als NOTLOESUNG hier ("eine Hilfe ersetzt keine Meldung zur
#   Laufzeit"); sie beschreiben seit Build 702 das Verfahren.
#   Bei 'glossary_admin' kam in Build 706 ein eigener Befund dazu: der Text
#   sicherte eine Meldung auf der Fehlerausgabe zu, die es NICHT gab. Eine
#   Hilfe, die eine Meldung verspricht, ist schlimmer als gar keine - sie
#   laesst den Leser darauf vertrauen, dass er es merken wuerde.
#
#   Bei 'export_admin' kam in Build 708 der letzte dieser Faelle dazu: der
#   Eintrag fuehrte seit Build 640 den Merkposten "Wird das Werkzeug
#   ausserhalb der Struktur aufgerufen, steht dort 0." - richtig beschrieben,
#   nie behoben. Jetzt berichtigt.
#
# Version: v0.8.708 - Build: 708 - 2026-08-12
# =============================================================================

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from management.help.cli_modell import (
    KONFIG_KEINE, CliBefehl, CliBeispiel, CliEintrag, CliKonfig,
    CliModellError, CliTiefe,
)


def _k(schluessel: str, bedeutung: str, vorgabe: str, beleg: str,
       argument: str = "") -> CliKonfig:
    """Kurzform fuer einen ausgewerteten Eintrag aus config.yaml (Build 639)."""
    return CliKonfig(schluessel=schluessel, bedeutung=bedeutung,
                     vorgabe=vorgabe, beleg=beleg, argument=argument)

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

#: H18 Teil 3 (Build 618). Derselbe eingerichtete Wegwerf-Bestand.
_GEPRUEFT_618 = ("Build 618, 2026-07-31, gegen einen eingerichteten "
                 "Wegwerf-Bestand unter /tmp (setup_coordinator_dev + alle "
                 "37 Migrationen, keine Faelle), Python 3.13")

#: H18 Teil 4 (Build 619). Derselbe Wegwerf-Bestand - eingerichtet, aber OHNE
#: Faelle. Das ist fuer diese Gruppe die aussagekraeftige Lage: die meisten
#: dieser Werkzeuge zeigen damit ihren LEERBEFUND, und genau der ist der
#: Zustand, in dem man am ehesten unsicher ist, ob das Werkzeug gelaufen ist.
_GEPRUEFT_619 = ("Build 619, 2026-08-01, gegen einen eingerichteten "
                 "Wegwerf-Bestand unter /tmp (setup_coordinator_dev + alle "
                 "37 Migrationen, KEINE Faelle), Python 3.13")

#: H18 Teil 5 (Build 620) - der Abschluss. Fuer die Vorlagen-Migrationen ist
#: eine eigene Wegwerf-templates.db aus tests/fixtures_templates_schema.sql
#: gebaut worden; sie bildet den Zustand NACH allen fuenf Migrationen ab.
#: Damit belegen die Beispiele die IDEMPOTENZ - jedes der fuenf Skripte
#: erkennt seinen eigenen Endzustand und tut nichts. Das ist die Eigenschaft,
#: auf die es beim zweiten Lauf ankommt.
_GEPRUEFT_620 = ("Build 620, 2026-08-01, gegen Wegwerf-Bestaende unter /tmp "
                 "(templates.db aus tests/fixtures_templates_schema.sql = "
                 "Zustand nach allen Migrationen), Python 3.13")


#: Build 655 (Ticket 5d81a0c7). Der Lauf ist gegen eine Wegwerf-templates.db
#: unter /tmp gefahren, gebaut aus tests/fixtures_templates_schema.sql - also
#: gegen genau die Gestalt, die der Bestand nach allen Migrationen hat. Beide
#: Laeufe sind gemessen: der erste ergaenzt, der zweite meldet No-op. Die
#: Zeile mit module_key 'intro.start' ist danach unveraendert (updated_at
#: gleich, block_type 'paragraph', block_data NULL), PRAGMA integrity_check
#: meldet 'ok'.
_GEPRUEFT_655 = ("Build 655, 2026-08-02, gegen einen Wegwerf-Bestand unter "
                 "/tmp (templates.db aus tests/fixtures_templates_schema.sql), "
                 "Python 3.14")


#: Build 623 (H19 Nachtrag). Diese Laeufe brauchten KEINEN Wegwerf-Bestand,
#: und das ist keine Nachlaessigkeit, sondern die Eigenschaft des Werkzeugs:
#: tools/hilfe_lektorat.py oeffnet keine Datenbank. Es liest das Hilferegister
#: und diesen Katalog aus dem Paket und schreibt eine HTML-Datei nach --ziel.
#: Gefahren wurde deshalb im Bestand selbst, mit einem Ziel unter /tmp.
_GEPRUEFT_623 = ("Build 623, 2026-08-01, im Bestand selbst - das Werkzeug "
                 "oeffnet keine Datenbank; Ziel unter /tmp, Python 3.13")


#: Build 626. Gefahren gegen einen Wegwerf-Sicherungsordner unter /tmp, in
#: dem ein ECHTER Abbruchrest liegt: eine 'VACUUM INTO'-Kopie einer 68-MB-
#: Quelle, nach 0,30 s mit SIGKILL abgebrochen. Genau die Lage also, um deren
#: Erkennung es geht - nicht eine nachgebaute.
_GEPRUEFT_626 = ("Build 626, 2026-08-01, gegen einen Wegwerf-Bestand unter "
                 "/tmp mit einem echten Abbruchrest (VACUUM INTO nach 0,30 s "
                 "mit SIGKILL beendet), Python 3.13")


#: Build 630. Gefahren gegen eigens gebaute Wegwerf-HTML-Dateien unter
#: /tmp - das Werkzeug beruehrt keine Datenbank und keinen Bestand; es
#: liest eine HTML-Datei und schreibt eine neue daneben.
_GEPRUEFT_630 = ("Build 630, 2026-08-01, gegen Wegwerf-HTML-Dateien unter "
                 "/tmp, Python 3.13, lxml")


#: Build 642. Gefahren im Container gegen Wegwerf-Verzeichnisse unter /tmp -
#: das Werkzeug legt sich seinen Bestand selbst an und beruehrt keinen
#: vorhandenen. Der Lauf mit '--mit-abbruch' erzeugte eine 253-MB-Quelle und
#: schoss das 'VACUUM INTO' nach 5.718.016 geschriebenen Byte ab.
_GEPRUEFT_642 = ("Build 642, 2026-08-01, gegen Wegwerf-Verzeichnisse unter "
                 "/tmp, Python 3.13")


#: Build 647. Gefahren im Container (Python 3.13) gegen Wegwerf-Verzeichnisse
#: unter /tmp; bei prepare_deployment gegen den Bestand selbst mit
#: '--skip-bundle --skip-wheels' - also OHNE Netzzugriff und ohne etwas an den
#: Auslieferungsverzeichnissen zu aendern.
_GEPRUEFT_647 = ("Build 647, 2026-08-01, im Container (Python 3.13), "
                 "Wegwerf-Verzeichnisse unter /tmp")


#: Build 671. Gefahren im Container (Python 3.11) gegen einen SELBST GEBAUTEN
#: Wegwerf-Bestand unter /tmp, der die Form von forensic_<uid>.db nachstellt.
#: AUSDRUECKLICH NICHT gegen einen echten Fall - der liegt nur in der VM. Die
#: Zahlen in den Beispielen sind daher die des Wegwerf-Bestandes und nicht die
#: eines Bestandes aus der Ermittlung.
_GEPRUEFT_671 = ("Build 671, 2026-08-05, im Container (Python 3.11) gegen "
                 "einen gebauten Wegwerf-Bestand unter /tmp - NICHT gegen "
                 "einen echten Fall")


#: Build 672. Wie 671, aber gegen die BERICHTIGTE Fassung: sie zaehlt nach
#: page_id statt nach URL. Der erste Lauf gegen einen echten Bestand
#: (forensic_1488.db, 05.08.2026) hatte gezeigt, dass die URL-Zaehlung die
#: Luecke um mehr als das Dreissigfache aufblaeht - Sprungmarken und zweite
#: Pfade sind dieselbe Seite. Die Zahlen aus jenem Lauf sind hier bewusst
#: NICHT aufgefuehrt: sie stammen von der falschen Fassung.
_GEPRUEFT_672 = ("Build 672, 2026-08-05, im Container (Python 3.11) gegen "
                 "einen gebauten Wegwerf-Bestand unter /tmp - NICHT gegen "
                 "einen echten Fall")

_GEPRUEFT_677 = ("Build 677, 2026-08-05, im Container (Python 3.11) gegen "
                 "einen gebauten Wegwerf-Bestand unter /tmp - NICHT gegen "
                 "einen echten Fall")


#: Build 675. Wie zuvor im Container gegen einen gebauten Wegwerf-Bestand, der
#: die am 05.08.2026 in der VM gemessene Lage nachstellt (Profilseiten nur fuer
#: den Beschuldigten selbst, Ziele fuer viele weitere Benutzer).
_GEPRUEFT_675 = ("Build 675, 2026-08-05, im Container (Python 3.11) gegen "
                 "einen gebauten Wegwerf-Bestand unter /tmp - NICHT gegen "
                 "einen echten Fall")


#: Build 680. Der Rueckweg (Vorgang 2785556a). Gefahren wurde der GANZE Weg
#: gegen einen gebauten Wegwerf-Bestand unter /tmp/wh_final: sichern, das Ziel
#: mit 4096 Null-Bytes zerstoeren, zurueckspielen, VON HAND tauschen und
#: gegenlesen. Danach standen die 200 Zeilen und die user_version wieder da.
#: KEIN Lauf gegen einen echten Fall - das waere ein Lauf in der VM.
_GEPRUEFT_680 = ("Build 680, 2026-08-05, im Container (Python 3.13) gegen "
                 "einen gebauten Wegwerf-Bestand unter /tmp - NICHT gegen "
                 "einen echten Fall")


#: Build 687. Gefahren gegen Wegwerf-HTML unter /tmp im Container. Es wurde
#: KEIN Bestand beruehrt - das Werkzeug oeffnet keine Datenbank. Gemessen
#: wurden neben den Beispielen auch die drei zurueckgebauten Altdefekte
#: (Gegenprobe zu den Waechtern AH01-AH18).
_GEPRUEFT_687 = ("Build 687, 2026-08-11, gegen Wegwerf-HTML unter /tmp, "
                 "Python 3.12.3, lxml 6.0.2")


#: Build 690. Die Nachbesserung aus dem Vergleich mit einer zweiten,
#: unabhaengig gebauten Fassung desselben Vorgangs (technische Panne, beide
#: Bearbeitungen liefen parallel). Gefahren gegen Wegwerf-HTML unter /tmp:
#: Fragment mit mehreren Knoten der obersten Ebene, Fragment mit einem
#: Knoten, verschachtelte Treffer, Volldokument mit und ohne DOCTYPE,
#: gemischte Ausdrucksliste, unbekannter Kodierungsname. Der Vergleich steht
#: im Vermerk 'Vergleich_anon_html_Build687_gegen_Build690_v1_0.md'.
_GEPRUEFT_690 = ("Build 690, 2026-08-11, gegen Wegwerf-HTML unter /tmp, "
                 "Python 3.13, lxml 6.1.1")


#: Build 694. Vorgang 1400b31f - "erst bauen, dann tauschen" fuer
#: consolidate_default_db. Gefahren gegen WEGWERF-default.db unter /tmp, mit
#: einem herbeigefuehrten Abbruch in der zweiten Quelle. Es wurde KEIN
#: Bestand beruehrt. Gemessen wurde der Zustand AUF DER PLATTE vor, waehrend
#: und nach dem Lauf - nicht der Ablauf im Speicher.
_GEPRUEFT_694 = ("Build 694, 2026-08-11, gegen Wegwerf-default.db unter "
                 "/tmp, Python 3.13")


#: Build 717. Vorgang 77757536 - 'backup_admin versatz'. Gefahren gegen
#: HANDGEBAUTE Manifeste unter /tmp und nicht gegen einen produktiven
#: Sicherungssatz. Das ist eine Einschraenkung und keine Nachlaessigkeit: ein
#: Versatz von Minuten laesst sich mit Wegwerf-Datenbanken nicht herstellen,
#: die sind in Sekundenbruchteilen kopiert. Die FORM der Manifeste ist
#: trotzdem belegt - der Testfall VZ18 wertet ein von BackupExecutor
#: WIRKLICH geschriebenes Manifest aus. Die Zahlen der Beispiele sind damit
#: nachgebaut, die Lesart ist gemessen.
_GEPRUEFT_717 = ("Build 717, 2026-08-13, gegen handgebaute "
                       "Manifeste unter /tmp, Python 3.14 - NICHT gegen "
                       "einen produktiven Sicherungssatz")


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
        # Build 640 (Welle 1): geprueft am Quelltext.
        # Aufloesung: Argument --coordinator-db > paths.coordinator_db > Abbruch.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Fall-Datenbank, mit der das Werkzeug arbeitet.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad waere schlimmer als ein Abbruch.",
               "management/cases/cases_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--coordinator-db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.cases.cases_admin --subject-id 1 --coordinator-db ./data/coordinator.db",
                     "Ohne weitere Optionen ein reiner Blick auf den Fall. Auf dem leeren Bestand: 'Fall subject_id=1 fehlt und kein --username zum Anlegen angegeben.' auf der Fehlerausgabe, Rueckgabewert 1.",
                     _GEPRUEFT_619),
            ),
            exit_codes=((0, "gelesen bzw. geaendert"), (1, "coordinator.db fehlt, der Fall fehlt und es wurde kein '--username' angegeben, oder ein Fachfehler"),),
            warnungen=(
                "MIT '--username' WIRD DER FALL ANGELEGT, wenn es ihn noch nicht gibt - ohne eigenen Schalter und ohne Rueckfrage. Das ist der ueberraschendste Punkt an diesem Werkzeug: wer sich beim '--subject-id' vertippt und '--username' mitgibt, legt einen Fall an, statt einen Fehler zu bekommen.",
                "ES GIBT KEINEN REIN LESENDEN UNTERBEFEHL. Auch der Blick auf einen Fall laeuft ueber eine schreibfaehige Verbindung und setzt den Journalmodus - die Datei wird also angefasst, auch wenn nichts geaendert wird.",
                "Ohne '--actor' wird als Urheber NULL gebucht und der Systembenutzer nur im Beleg vermerkt. Im laufenden Betrieb gehoert '--actor' dazu.",
                "Alle Aenderungen sind protokolliert und NICHT zurueckzunehmen.",
            ),
        ),
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
        # Build 640 (Welle 1): geprueft am Quelltext.
        # Aufloesung: Argument --coordinator-db > paths.coordinator_db > Abbruch.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Fall-Datenbank, mit der das Werkzeug arbeitet.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad waere schlimmer als ein Abbruch.",
               "management/case_events/case_events_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--coordinator-db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.case_events.case_events_admin list --subject-id 1 --coordinator-db ./data/coordinator.db",
                     "Zeigt den Zeitstrahl eines Falls. Auf dem leeren Bestand: 'Kein Zeitstrahl-Eintrag fuer subject_id=1.' Rueckgabewert 0 - der Leerbefund ist kein Fehler.",
                     _GEPRUEFT_619),
            ),
            exit_codes=((0, "ausgegeben, auch beim Leerbefund; bzw. Eintrag geschrieben"), (1, "coordinator.db fehlt oder Fachfehler"),),
            warnungen=(
                "'add' ERZEUGT EINEN UNWIDERRUFLICHEN EINTRAG samt Beleg. Der Zeitstrahl ist eine Chronik und kein Arbeitsblatt.",
                "DIE AUTOMATISCH GESPIEGELTEN EREIGNISSE ENTSTEHEN NICHT HIER. Dieses Werkzeug traegt nur von Hand nach, was sonst nirgends steht.",
                "Auch 'list' oeffnet die Datenbank schreibfaehig und setzt den Journalmodus.",
                "Es wird nicht geprueft, ob die angegebene Fallnummer ueberhaupt zu einem Fall gehoert - ein Zahlendreher legt den Eintrag am falschen Zeitstrahl ab.",
            ),
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
        # Build 640 (Welle 1): geprueft an escalation_admin.py Z. 35-62 und
        # escalation.py Z. 141-155. Die drei Schwellen stehen seit Build 640
        # AUSKOMMENTIERT in config.yaml - vorher waren sie nur im Quelltext zu
        # finden, obwohl der Code sie liest (Befund der Erhebung).
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Fall-Datenbank, aus der der Fallzustand gelesen wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab.",
               "management/cases/escalation_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py (Build 644)",
               "--coordinator-db"),
            _k("escalation.red_overdue_days",
               "Offener Fall, Ampel rot UND so viele Tage ohne Aktivitaet: "
               "Regel R1 'ueberfaellig', Schwere hoch.",
               "30 Tage",
               "management/cases/escalation.py, escalation_thresholds_from_config() Z. 141-153"),
            _k("escalation.stale_open_days",
               "Zugewiesener Fall im Status 'open' und so viele Tage ohne "
               "Aktivitaet: Regel R2 'unbearbeitet', Schwere mittel. Greift "
               "NICHT, wenn R1 fuer denselben Fall schon angeschlagen hat - "
               "keine Doppelmeldung.",
               "14 Tage",
               "management/cases/escalation.py, escalation_thresholds_from_config() Z. 141-153"),
            _k("escalation.backlog_high",
               "Unzugewiesener Rueckstau ab dieser Zahl: Regel R3, eine "
               "systemische Meldung ohne Fallbezug.",
               "10 Faelle",
               "management/cases/escalation.py, escalation_thresholds_from_config() Z. 141-153"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.cases.escalation_admin --coordinator-db ./data/coordinator.db",
                     "Gibt die Eskalationsstufen aus. Auf dem leeren Bestand: 'Eskalationen: hoch=0 mittel=0 niedrig=0 (von 0 Faellen)' und '(keine Eskalation)'. Rueckgabewert 0.",
                     _GEPRUEFT_619),
            ),
            exit_codes=((0, "ausgegeben - AUCH wenn nichts eskaliert ist"),),
            warnungen=(
                "ES GIBT NUR DEN RUECKGABEWERT 0. Eine hohe Eskalation steht ausschliesslich in der Ausgabe; eine Ueberwachung muss den Text oder die JSON-Ausgabe auswerten.",
                "FEHLT EINE BENOETIGTE TABELLE, gibt es einen rohen Programmabbruch statt einer handlungsleitenden Meldung - der Bestand ist dann zuerst zu migrieren.",
                "IST DIE KONFIGURATION NICHT LESBAR, wird das STILL uebergangen und es gelten die Vorgabeschwellen. Dieselbe Datenbank kann damit eine andere Eskalationslage ergeben.",
                "Es oeffnet die coordinator.db ausdruecklich nur lesend und nimmt keine Sperre - der Betrieb darf weiterlaufen.",
            ),
        ),
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
        # Build 640 (Welle 1): geprueft am Quelltext.
        # Aufloesung: Argument --coordinator-db > paths.coordinator_db > Abbruch.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Fall-Datenbank, mit der das Werkzeug arbeitet.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad waere schlimmer als ein Abbruch.",
               "management/cases/handover_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py (Build 644)", "--coordinator-db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.cases.handover_admin --coordinator-db ./data/coordinator.db",
                     "Gibt das Uebergabeprotokoll aus. Auf dem leeren Bestand: 'Uebergabe-Protokoll: 0 Umverteilung(en) ueber 0 Fall/Faelle.' Rueckgabewert 0.",
                     _GEPRUEFT_619),
            ),
            exit_codes=((0, "ausgegeben"),),
            warnungen=(
                "DIE QUELLE IST DAS PROTOKOLLBUCH, NICHT DIE FALLTABELLE. Das ist der Vorzug dieses Werkzeugs: die Uebergaben bleiben lesbar, auch wenn die Faelle spaeter veraendert wurden. Umgekehrt gilt: was nicht protokolliert wurde, steht hier nicht.",
                "'--reassignments-only' FILTERT NUR DIE TEXTAUSGABE. Die Kopfzahlen und die JSON-Ausgabe bleiben ungefiltert - die Zaehlung passt dann nicht zur angezeigten Liste.",
                "Nur lesend, mit ausdruecklichem Nur-Lese-Zugriff.",
            ),
        ),
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
        # Build 640 (Welle 1): geprueft am Quelltext.
        # Aufloesung: Argument --coordinator-db > paths.coordinator_db > Abbruch.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Fall-Datenbank, mit der das Werkzeug arbeitet.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad waere schlimmer als ein Abbruch.",
               "management/cases/next_actions_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py (Build 644)", "--coordinator-db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.cases.next_actions_admin --coordinator-db ./data/coordinator.db",
                     "Gibt die naechstbesten Aktionen aus. Auf dem leeren Bestand: 'Naechstbeste Aktionen (scope alle): 0 von 0 Faellen offen, 0 abgeschlossen.' Rueckgabewert 0.",
                     _GEPRUEFT_619),
            ),
            exit_codes=((0, "ausgegeben"),),
            warnungen=(
                "ES GIBT NUR DEN RUECKGABEWERT 0.",
                "'--scope eigene' OHNE '--person-id' WIRD HIER NICHT ABGEFANGEN. Was dabei herauskommt, entscheidet die darunterliegende Auswertung; verlassen sollte man sich darauf nicht.",
                "FEHLT EINE BENOETIGTE TABELLE, gibt es einen rohen Programmabbruch - wie bei escalation_admin.",
                "Nur lesend, mit ausdruecklichem Nur-Lese-Zugriff.",
            ),
        ),
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
        # Build 640 (Welle 1): geprueft an dashboard_admin.py Z. 40-70/147-150
        # und dashboard_repo.py Z. 103-150. BEMERKENSWERT: Die Ampel-Schwellen
        # sind der einzige bisher gefundene Fall, in dem ein unsinniger Wert
        # NICHT still auf die Vorgabe zurueckfaellt, sondern zum Abbruch fuehrt.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Fall-Datenbank, aus der die Uebersicht gebildet wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab.",
               "management/dashboard/dashboard_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py (Build 644)",
               "--coordinator-db"),
            _k("dashboard.ampel.amber_idle_days",
               "Ab so vielen Tagen ohne Fall-Aktivitaet wird die Ampel GELB.",
               "7 Tage - die Verwendung des Vorgabewerts wird protokolliert",
               "management/dashboard/dashboard_repo.py, ampel_thresholds_from_config() Z. 103-150"),
            _k("dashboard.ampel.red_idle_days",
               "Ab so vielen Tagen ohne Fall-Aktivitaet wird die Ampel ROT. "
               "ACHTUNG: Ein nicht ganzzahliger Wert oder eine unsinnige "
               "Staffelung (gelb >= rot, gelb < 1) fuehrt zum ABBRUCH mit "
               "Klartext - hier faellt anders als bei den uebrigen Schwellen "
               "NICHTS still auf die Vorgabe zurueck.",
               "21 Tage - die Verwendung des Vorgabewerts wird protokolliert",
               "management/dashboard/dashboard_repo.py, ampel_thresholds_from_config() Z. 103-150"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.dashboard.dashboard_admin list --coordinator-db ./data/coordinator.db",
                     "Gibt die Fallliste mit Ampel aus. Auf dem leeren Bestand: '[dashboard_admin] Keine Faelle vorhanden.' Rueckgabewert 0 - der Leerbefund ist kein Fehler.",
                     _GEPRUEFT_619),
            ),
            exit_codes=((0, "ausgegeben bzw. geschrieben; auch beim Leerbefund"), (1, "coordinator.db fehlt, die Ampelschwellen in der Konfiguration sind unbrauchbar, oder eine benoetigte Tabelle fehlt - Letzteres wird hier sauber gemeldet und nicht als Programmabbruch"),),
            warnungen=(
                "DIE AMPEL-BEDEUTUNG IST LAUT DATEIKOPF VORLAEUFIG. Wer sie in einen Bericht uebernimmt, sollte das wissen.",
                "'--out' UEBERSCHREIBT die Zieldatei ohne Rueckfrage.",
                "'export-html' liest zusaetzlich zwei Dateien aus dem Oberflaechenverzeichnis. Fehlen sie, bricht der Aufruf mit einem rohen Programmabbruch ab.",
                "Die Schwellen kommen aus der Konfiguration (Vorgabe 7 und 21 Tage) - dieselbe Datenbank ergibt mit einer anderen Konfiguration eine andere Ampelverteilung.",
                "Der Dateikopf nennt das Werkzeug nur-lesend; die Verbindung ist trotzdem schreibfaehig. Geschrieben wird nichts.",
                # Build 706 (Vorgang 70641ff9): die Kennzeichnung im
                # Dokument gibt es seit Build 702, die Meldung zur
                # Laufzeit erst seit 706.
                "KANN EINE ANGABE DES ERZEUGUNGSVERMERKS NICHT ERMITTELT WERDEN, steht sie seit Build 702 als 'nicht ermittelbar' im Dokument und wird seit Build 706 zusaetzlich auf der Fehlerausgabe benannt. Der Rueckgabewert bleibt 0.",
                "OHNE '--actor' WIRD DER ANGEMELDETE OS-BENUTZER GENOMMEN. Ist der keinem person-Datensatz zugeordnet, traegt die Ausgabe einen ungeprueften Erstellernamen; das Werkzeug meldet es. Im Stapelbetrieb ist '--actor' anzugeben.",
            ),
        ),
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
        # Build 640 (Welle 1): geprueft am ganzen Quelltext von
        # limitation_admin.py - kein ConfigLoader, kein '--config', kein
        # Zugriff auf config.yaml. Die Verjaehrungsparameter kommen aus einer
        # EIGENEN Datei (management/deadlines/limitation_params.json, ueber
        # '--params' austauschbar); sie sind Rechtsstoff und gehoeren
        # ausdruecklich nicht in die Betriebskonfiguration.
        konfiguration=KONFIG_KEINE,
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/../management/deadlines/limitation_admin.py pruefen  (bzw. python -m management.deadlines.limitation_admin pruefen)",
                     "Prueft den Verjaehrungs-Parametersatz. Im Versuch: 'Parametersatz in Ordnung', Stand 2026-07-25, 19 Fassungen - und trotzdem Rueckgabewert 3, weil der Satz NICHT juristisch bestaetigt ist. Das ist der Sollzustand und kein Defekt.",
                     _GEPRUEFT_619),
            ),
            exit_codes=((0, "der Parametersatz ist in Ordnung UND bestaetigt"), (2, "der Parametersatz ist unbrauchbar"), (3, "BEFUND: keine Fristaussage moeglich - insbesondere, weil der Satz noch nicht juristisch bestaetigt ist. KEIN Fehler"),),
            warnungen=(
                "DER AUSGELIEFERTE PARAMETERSATZ IST EIN ENTWURF UND NICHT JURISTISCH BESTAETIGT. 'pruefen' endet deshalb heute regelmaessig mit 3, nicht mit 0. Wer die 3 fuer einen Fehler haelt, sucht an der falschen Stelle - sie ist die Auskunft, dass auf dieser Grundlage keine Frist berechnet werden darf.",
                "Der Satz benennt seine eigenen Luecken und Vorbehalte ausdruecklich, unter anderem den unberuecksichtigten Paragrafen 78c StGB (Unterbrechung).",
                "ES WIRD KEINE DATENBANK GEOEFFNET. Das Werkzeug rechnet allein aus dem Parametersatz und ist damit in jedem Betriebszustand aufrufbar.",
            ),
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
        # Build 640 (Welle 1): geprueft am ganzen Quelltext von qs_admin.py -
        # kein ConfigLoader, kein '--config'.
        #
        # BEFUND, der zur Auskunft gehoert: Der Rueckfallwert fuer '--db' ist
        # die fest verdrahtete Zeichenkette _VORGABE_DB = "data/coordinator.db"
        # (Z. 54), NICHT 'paths.coordinator_db' aus config.yaml. Wer die
        # coordinator.db anderswo liegen hat, MUSS hier '--db' angeben - eine
        # Standortfestlegung in config.yaml hilft ihm bei diesem einen Werkzeug
        # nicht. Das ist kein Fehler dieses Katalogs, aber es gehoert gesagt.
        konfiguration=KONFIG_KEINE,
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.qs.qs_admin liste --db ./data/coordinator.db",
                     "Fuehrt die Stichprobenziehungen auf. Auf dem leeren Bestand ein ausdruecklicher Leerbefund unter der Ueberschrift 'REIN LESEND'. Rueckgabewert 0.",
                     _GEPRUEFT_619),
            ),
            exit_codes=((0, "ausgegeben, auch beim Leerbefund; bei 'nachziehen': die Ziehung stimmt"), (1, "BEFUND von 'nachziehen': ABWEICHUNG zwischen Ziehung und heutigem Stand. KEIN Programmfehler, sondern etwas, das ein Mensch bewerten muss"), (2, "coordinator.db oder die angegebene Ziehung nicht gefunden, oder Fachfehler"),),
            warnungen=(
                "DER RUECKGABEWERT 1 IST EIN BEFUND UND KEIN FEHLER. Eine Abweichung heisst: der Bestand hat sich seit der Ziehung geaendert. Ob das in Ordnung ist, entscheidet ein Mensch.",
                "OHNE '--db' WIRD STILL './data/coordinator.db' ANGENOMMEN - relativ zum aktuellen Verzeichnis. Aus dem falschen Verzeichnis aufgerufen prueft man eine andere Datenbank, ohne es zu merken.",
                "'--db' darf vor ODER hinter dem Unterbefehl stehen.",
                "Es oeffnet ausdruecklich nur lesend und setzt kein PRAGMA - eines der wenigen Werkzeuge, bei denen die Nur-Lese-Zusage technisch durchgesetzt ist.",
            ),
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
        # Build 640 (Welle 1): geprueft am Quelltext.
        # Aufloesung: Argument --db > paths.coordinator_db > Abbruch.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Fall-Datenbank, mit der das Werkzeug arbeitet.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad waere schlimmer als ein Abbruch.",
               "management/results/results_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.results.results_admin --db ./data/coordinator.db catalog",
                     "Gibt den Bewertungskatalog samt Skalen aus. Im Versuch: 'Katalogversion: 1' und die Konfidenzskala. Rueckgabewert 0; es werden keine Faelle gebraucht.",
                     _GEPRUEFT_619),
                _bsp("python -m management.results.results_admin --db ./data/coordinator.db coverage",
                     "Zeigt die blinden Flecken der Bewertung. Auf dem leeren Bestand: 'Faelle gesamt: 0 | vollstaendig bewertet: 0 | mittlere Abdeckung: None'. Rueckgabewert 0.",
                     _GEPRUEFT_619),
            ),
            exit_codes=((0, "ausgegeben bzw. bewertet; bei 'coverage': keine nie bewerteten Faelle"), (1, "Fachfehler - etwa eine unbekannte Kennung bei '--actor'"), (2, "BEFUND von 'coverage': es gibt Faelle, die NIE bewertet wurden. KEIN Fehler, sondern Handlungsbedarf - der Wert ist da, damit ein Skript ihn sieht"),),
            warnungen=(
                "'--db' MUSS VOR DEN UNTERBEFEHL. Steht es dahinter, meldet die Auswertung der Kommandozeile einen Aufruffehler (Rueckgabewert 2) - gemessen am 2026-08-01. Das ist leicht zu verwechseln, weil andere Werkzeuge beides erlauben.",
                "'assess' UEBERSCHREIBT NICHTS. Jede Bewertung ist eine neue Zeile mit eingefrorener Katalogversion; zurueckgenommen wird nichts.",
                "Die Kennzahl aus 'score' ist ausdruecklich vorlaeufig - der Vorbehalt wird bei jedem Aufruf mitgedruckt.",
                "Alle Unterbefehle, auch die rein lesenden, laufen ueber eine schreibfaehige Verbindung.",
            ),
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
        # Build 640 (Welle 1): geprueft am Quelltext.
        # Aufloesung: Argument --db > paths.coordinator_db > Abbruch.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Fall-Datenbank, mit der das Werkzeug arbeitet.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad waere schlimmer als ein Abbruch.",
               "management/results/catalog_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.results.catalog_admin --db ./data/coordinator.db add-scale --code x --label X --actor KENNUNG",
                     "Auf einem Bestand ohne die angegebene Kennung: 'FEHLER: Unbekannte Kennung' auf der Fehlerausgabe, Rueckgabewert 1 - und zwar BEVOR irgendetwas geschrieben wurde. Ein gefahrloser Beispiellauf ist bei diesem Werkzeug nicht moeglich: es hat keinen einzigen lesenden Unterbefehl.",
                     _GEPRUEFT_619),
            ),
            exit_codes=((0, "die Aenderung ist durchgefuehrt"), (1, "Fachfehler - darunter eine unbekannte Kennung bei '--actor'"),),
            warnungen=(
                "ES GIBT KEINEN LESENDEN UNTERBEFEHL. Jeder Aufruf ist ein Schreibversuch. Zum ANSEHEN des Katalogs dient 'results_admin catalog'.",
                "JEDE AENDERUNG ERHOEHT DIE KATALOGVERSION. Bereits erfasste Bewertungen behalten ihren damaligen Wert und aendern ihre Bedeutung nicht rueckwirkend - eine Auswertung ueber mehrere Katalogversionen hinweg ist aber mit Bedacht zu lesen.",
                "ES WIRD NICHTS GELOESCHT. 'deprecate' stellt nur ausser Dienst; der Eintrag bleibt lesbar. Ein Rueckbau geht nur ueber eine weitere Aenderung - die ihrerseits die Version erhoeht.",
                "'--actor' ist in JEDEM Unterbefehl Pflicht und wird VOR der Aktion aufgeloest. Auf einem Bestand ohne Personal scheitert deshalb jeder Aufruf, bevor etwas geschrieben wird.",
                "'--db' gehoert vor den Unterbefehl.",
            ),
        ),
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
        # Build 640 (Welle 2): geprueft am Quelltext. Aufloesung:
        # Argument --coordinator-db > paths.coordinator_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank mit den Personen und ihren Rollen.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad "
               "waere schlimmer als ein Abbruch.",
               "management/person/person_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--coordinator-db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.person.person_admin list --coordinator-db ./data/coordinator.db",
                     "Fuehrte die hinterlegten Personen mit Rollen auf. Im Versuch drei Eintraege aus dem Entwicklungs-Bootstrap. Rueckgabewert 0.",
                     _GEPRUEFT_618),
            ),
            exit_codes=((0, "ausgegeben bzw. angelegt/geaendert"), (1, "coordinator.db nicht gefunden, Fachfehler oder unbekannte Aktion"),),
            warnungen=(
                "ES GIBT KEIN LOESCHEN, und die Anmeldekennung wird nie geaendert. Wer ausscheidet, wird stillgelegt ('--set-investigator 0'). Das ist Absicht: eine geloeschte Person hinterliesse Belegzeilen ohne Urheber.",
                "OHNE '--actor' wird als Urheber NULL protokolliert und der Systembenutzer im Beleg vermerkt. Das ist fuer den ersten Eintrag gedacht, mit dem ueberhaupt jemand angelegt wird - im laufenden Betrieb gehoert '--actor' dazu.",
                "Auch 'list' oeffnet die Datenbank schreibfaehig UND setzt den Journalmodus. Das ist ein Schreibzugriff auf die Datei, obwohl nur gelesen wird.",
            ),
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
            _b("migrate-grants", "schreibend",
               "Die aktiven Rechte eines Rechts auf ein anderes uebernehmen "
               "(--from/--to, Umfang unveraendert). Gebraucht, wenn ein Recht "
               "geteilt wird: ohne diesen Lauf verliert jede Rolle die Sicht, "
               "die an das neue Recht wandert. ERST DIE MIGRATION, DANN DIESER "
               "LAUF - das neue Recht muss in der Datenbank stehen, sonst "
               "bricht der Lauf ab (Build 711). Erst mit '--probe' fahren."),
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
        # Build 640 (Welle 2): geprueft am Quelltext. Aufloesung:
        # Argument --coordinator-db > paths.coordinator_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, in der Rollen und Rechte gefuehrt werden.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad "
               "waere schlimmer als ein Abbruch.",
               "management/rbac/rbac_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--coordinator-db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.rbac.rbac_admin catalog",
                     "Gibt Rollen und Rechte aus, ohne eine Datenbank zu "
                     "oeffnen. Im Versuch: 8 Rollen, danach die Rechte, "
                     "Rueckgabewert 0."),
                _bsp("python -m management.rbac.rbac_admin migrate-grants "
                     "--from dashboard.view --to caseoverview.view --probe",
                     "Zeigt Rolle fuer Rolle, wer das neue Recht bekaeme und "
                     "mit welchem Umfang, und was bereits vorhanden ist. "
                     "Schreibt nichts. Ohne '--probe' derselbe Lauf scharf, "
                     "mit einem eigenen Beleg je vergebenem Recht."),
            ),
            exit_codes=((0, "erledigt"), (1, "Fehler")),
            warnungen=(
                "'revoke-grant' und 'revoke-role' loeschen nicht, sie "
                "widerrufen. Die Zeile bleibt als Beleg erhalten.",
                "'migrate-grants' nimmt das Quellrecht NICHT zurueck. Nach "
                "dem Lauf hat jede Rolle beide Rechte; ob das alte bleiben "
                "soll, ist eine Entscheidung je Rolle und gehoert einzeln mit "
                "'revoke-grant' getroffen.",
                "REIHENFOLGE: Ein neues Recht entsteht in ZWEI Schritten - "
                "die Migration traegt es in den Katalog der Datenbank ein "
                "('python -m management.migrate'), erst danach verteilt es "
                "'migrate-grants'. Wer tauscht, erzeugte bis Build 710 einen "
                "Grant auf ein Recht, das die Datenbank nicht kannte: die "
                "Pruefung in rbac_admin sieht den Katalog im CODE, und die "
                "Fremdschluessel der coordinator.db greifen bei "
                "foreign_keys=OFF nicht. Die Migration liess sich danach nicht "
                "mehr anwenden, und das Management verweigerte den Start. "
                "SEIT BUILD 711 wird die Reihenfolge geprueft: fehlt das Recht "
                "in der Datenbank, bricht der Lauf ab, nennt den fehlenden "
                "Schritt und schreibt nichts.",
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
        # Build 640 (Welle 2): geprueft am Quelltext. Aufloesung:
        # Argument --db > paths.coordinator_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, in die der Abgleich mit dem Verzeichnisdienst schreibt.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad "
               "waere schlimmer als ein Abbruch.",
               "management/ad_sync/ad_sync_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.ad_sync.ad_sync_admin --db ./data/coordinator.db preview",
                     "OHNE ERREICHBARES VERZEICHNIS: 'FEHLER: AD-Abgleich nicht konfiguriert' mit Nennung aller vier fehlenden Pflichtwerte, Rueckgabewert 1. Das ist der Regelfall auf einem Rechner ohne Verzeichnisanbindung - die Vorschau braucht die Quelle genauso wie die Ausfuehrung.",
                     _GEPRUEFT_618),
            ),
            exit_codes=((0, "Vorschau ausgegeben bzw. Abgleich ausgefuehrt"), (1, "Verzeichnis nicht erreichbar oder nicht konfiguriert, Planungs- oder Fachfehler"),),
            warnungen=(
                "AUCH DIE VORSCHAU BRAUCHT DAS VERZEICHNIS. 'preview' ist lesend, aber nicht 'ohne Netz' - es holt die Gruppenmitglieder genauso wie 'apply'.",
                "'--actor' MUSS EIN AKTIVER SUPERVISOR SEIN, sonst bricht der Aufruf ab.",
                "'apply' IST INTERAKTIV: je Person ist wortwoertlich 'Entfernen' bzw. 'Reaktivieren' einzugeben. Jede andere Eingabe ist ein protokollierter Abbruch. Aus einem Skript heraus laesst sich das nicht fahren - und das ist Absicht.",
                "Es wird niemand geloescht, nur stillgelegt.",
            ),
        ),
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
        # Build 640 (Welle 2): geprueft am Quelltext. Aufloesung:
        # Argument --coordinator-db > paths.coordinator_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank mit den Kapazitaetsangaben je Person.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad "
               "waere schlimmer als ein Abbruch.",
               "management/capacity/capacity_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--coordinator-db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.capacity.capacity_admin list-reasons --coordinator-db ./data/coordinator.db",
                     "Fuehrte die hinterlegten Abwesenheitsgruende auf. Auf dem leeren Bestand: 'Keine Gruende.' Rueckgabewert 0.",
                     _GEPRUEFT_618),
            ),
            exit_codes=((0, "ausgegeben bzw. eingetragen"), (2, "FACHLICHE ABLEHNUNG - etwa eine Dublette zum selben Stichtag. KEIN Absturz"),),
            warnungen=(
                "ES GIBT KEINEN RUECKGABEWERT 1. Eine fachliche Ablehnung meldet 2. Wer nur auf 1 prueft, haelt eine Ablehnung fuer einen Erfolg.",
                "EINE KORREKTUR ZUM SELBEN STICHTAG MUSS UEBER 'replace-worktime' LAUFEN - 'set-worktime' scheitert dann an der Dublettensperre. Das ist gewollt: eine stillschweigend ueberschriebene Arbeitszeit waere im Nachhinein nicht mehr nachvollziehbar.",
                "Loeschungen sind keine: die Zeile bleibt mit Loeschzeitpunkt erhalten und ist mit '--all' wieder sichtbar.",
                "Kein Pfad wird auf Vorhandensein geprueft - ein Tippfehler legt eine leere Datenbank an.",
            ),
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
        # Build 640 (Welle 2): geprueft am Quelltext. Aufloesung:
        # Argument --db > paths.coordinator_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, in der die Einarbeitung gefuehrt wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad "
               "waere schlimmer als ein Abbruch.",
               "management/onboarding/onboarding_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.onboarding.onboarding_admin steps --kind onboarding",
                     "Fuehrte die Schritte des Einarbeitungswegs mit Kennung und Klartext auf. Rueckgabewert 0. Dieser Unterbefehl oeffnet GAR KEINE Datenbank und ist damit jederzeit aufrufbar.",
                     _GEPRUEFT_618),
            ),
            exit_codes=((0, "ausgegeben bzw. gesetzt"), (1, "Fach- oder Aufruffehler"),),
            warnungen=(
                "'--status offen' LOESCHT DIE ZEILE und setzt den Schritt zurueck. Das ist die einzige Stelle, an der hier etwas verschwindet - die Ausgabe sagt 'zurueckgesetzt'.",
                "Bei '--kind offboarding' zeigt 'show' zusaetzlich, wie viele Faelle der Person noch zugewiesen sind. Diese Zahl ist vor dem Abschluss zu lesen.",
                "'steps' braucht keine Datenbank; 'show' und 'set' oeffnen sie schreibfaehig.",
            ),
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
        datenbanken=("coordinator.db (lesend - seit Build 629 mit 'mode=ro' "
                     "erzwungen; bis Build 628 war die Verbindung "
                     "technisch schreibfaehig, Vorgang 906ede75)",),
        betrieb="Der Betrieb darf weiterlaufen. 'export-html' rechnet die "
                "gesamte Belegkette nach; bei grossen Bestaenden dauert das.",
        befehle=(
            _b("list", "lesend", "Sitzungen auf der Konsole."),
            _b("export-html", "lesend",
               "Eigenstaendiges HTML mit Erzeugungsvermerk (--out)."),
        ),
        ausgabe="HTML-Datei bei export-html (--out).",
        # Build 640 (Welle 2): geprueft am Quelltext. Aufloesung:
        # Argument --coordinator-db > paths.coordinator_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, aus der die Betreuungsuebersicht gebildet wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad "
               "waere schlimmer als ein Abbruch.",
               "management/support_overview/support_overview_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py (Build 644)", "--coordinator-db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.support_overview.support_overview_admin list --coordinator-db ./data/coordinator.db",
                     "Fuehrte die Support-Sitzungen aus dem Protokollbuch auf. Auf dem leeren Bestand: 'Keine Support-Sitzungen im audit_log.' Rueckgabewert 0.",
                     _GEPRUEFT_618),
            ),
            exit_codes=((0, "ausgegeben bzw. geschrieben - AUCH bei gebrochener Belegkette"), (1, "coordinator.db nicht gefunden oder eine benoetigte Tabelle fehlt"),),
            warnungen=(
                "EINE GEBROCHENE BELEGKETTE AENDERT DEN RUECKGABEWERT NICHT. Sie erscheint als Warnung auf der Fehlerausgabe und als Banner in der Ausgabe; der Lauf endet mit 0. Wer den Bericht weitergibt, muss die Fehlerausgabe gelesen haben.",
                "Die Datenquelle ist das PROTOKOLLBUCH - die Historie wird daraus rekonstruiert. Was dort nicht steht, gibt es hier nicht.",
                "'--out' ueberschreibt eine vorhandene Datei wortlos.",
                "Der Dateikopf sichert zu, die coordinator.db werde AUSSCHLIESSLICH gelesen - die Verbindung wird trotzdem schreibfaehig geoeffnet. Vorgang eroeffnet (Issue 906ede75).",
                # Build 706 (Vorgang 70641ff9): die Kennzeichnung im
                # Dokument gibt es seit Build 702, die Meldung zur
                # Laufzeit erst seit 706.
                "KANN EINE ANGABE DES ERZEUGUNGSVERMERKS NICHT ERMITTELT WERDEN, steht sie seit Build 702 als 'nicht ermittelbar' im Dokument und wird seit Build 706 zusaetzlich auf der Fehlerausgabe benannt. Der Rueckgabewert bleibt 0.",
                "OHNE '--actor' WIRD DER ANGEMELDETE OS-BENUTZER GENOMMEN. Ist der keinem person-Datensatz zugeordnet, traegt die Ausgabe einen ungeprueften Erstellernamen; das Werkzeug meldet es. Im Stapelbetrieb ist '--actor' anzugeben.",
            ),
        ),
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
        datenbanken=("coordinator.db (lesend - seit Build 629 mit 'mode=ro' "
                     "erzwungen; bis Build 628 war die Verbindung "
                     "technisch schreibfaehig, Vorgang 906ede75)",),
        betrieb="Der Betrieb darf weiterlaufen. 'export-html' rechnet die "
                "gesamte Belegkette nach.",
        befehle=(
            _b("list", "lesend", "Verteilung auf der Konsole."),
            _b("export-html", "lesend",
               "Eigenstaendiges HTML mit Erzeugungsvermerk (--out)."),
        ),
        ausgabe="HTML-Datei bei export-html (--out).",
        # Build 640 (Welle 2): geprueft an workload_admin.py Z. 44-62/176 und
        # dashboard_repo.py Z. 103-150. Die Ampel-Schwellen sind BEWUSST
        # dieselben wie in der Fallsteuerung - "so ist die Farbsemantik
        # konsistent" (Dateikopf Z. 19). Zwei Werkzeuge, EIN Eintrag: haette
        # jedes seinen eigenen, wuerde dieselbe Farbe zwei Dinge bedeuten.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, aus der die Auslastung je Person gebildet wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab.",
               "management/workload/workload_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py (Build 644)",
               "--coordinator-db"),
            _k("dashboard.ampel.amber_idle_days",
               "Ab so vielen Tagen ohne Fall-Aktivitaet gilt ein Fall als GELB "
               "- dieselbe Schwelle wie in der Fallsteuerung, damit dieselbe "
               "Farbe ueberall dasselbe heisst.",
               "7 Tage",
               "management/workload/workload_admin.py Z. 176; Auswertung in "
               "management/dashboard/dashboard_repo.py Z. 103-150"),
            _k("dashboard.ampel.red_idle_days",
               "Ab so vielen Tagen ohne Fall-Aktivitaet gilt ein Fall als ROT. "
               "Ein unsinniger Wert fuehrt hier wie in der Fallsteuerung zum "
               "ABBRUCH und nicht zum stillen Rueckfall.",
               "21 Tage",
               "management/workload/workload_admin.py Z. 176; Auswertung in "
               "management/dashboard/dashboard_repo.py Z. 103-150"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.workload.workload_admin list --coordinator-db ./data/coordinator.db",
                     "Gab die Auslastung je ermittelnder Person als Tabelle aus - Faelle, Ampelverteilung, letzte Aktion. Rueckgabewert 0.",
                     _GEPRUEFT_618),
            ),
            exit_codes=((0, "ausgegeben bzw. geschrieben - AUCH bei gebrochener Belegkette"), (1, "coordinator.db nicht gefunden, Konfigurationsfehler oder eine benoetigte Tabelle fehlt"),),
            warnungen=(
                "EINE GEBROCHENE BELEGKETTE AENDERT DEN RUECKGABEWERT NICHT - wie beim Support-Ueberblick nur eine Warnung auf der Fehlerausgabe.",
                "DIE AMPELSCHWELLEN KOMMEN AUS DER KONFIGURATION (Vorgabe 7 und 21 Tage). DIESELBE DATENBANK LIEFERT MIT EINER ANDEREN KONFIGURATION ANDERE AMPELZAHLEN. Wer zwei Ausgaben vergleicht, muss dieselbe Konfiguration benutzt haben.",
                "Die Zeile fuer den Rueckstau (Faelle ohne Zuweisung) ist eine Sammelzeile ohne Rollen und ohne Aktionen - sie steht fuer niemanden.",
                "Der Dateikopf sichert nur-lesenden Zugriff zu; die Verbindung ist trotzdem schreibfaehig. Vorgang eroeffnet (Issue 906ede75).",
                # Build 706 (Vorgang 70641ff9): die Kennzeichnung im
                # Dokument gibt es seit Build 702, die Meldung zur
                # Laufzeit erst seit 706.
                "KANN EINE ANGABE DES ERZEUGUNGSVERMERKS NICHT ERMITTELT WERDEN, steht sie seit Build 702 als 'nicht ermittelbar' im Dokument und wird seit Build 706 zusaetzlich auf der Fehlerausgabe benannt. Der Rueckgabewert bleibt 0.",
                "OHNE '--actor' WIRD DER ANGEMELDETE OS-BENUTZER GENOMMEN. Ist der keinem person-Datensatz zugeordnet, traegt die Ausgabe einen ungeprueften Erstellernamen; das Werkzeug meldet es. Im Stapelbetrieb ist '--actor' anzugeben.",
            ),
        ),
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
        # Build 640 (Welle 2): geprueft an overload_admin.py Z. 26-63 und
        # overload.py Z. 33-38/152-168. Die drei Grenzwerte stehen seit Build
        # 640 AUSKOMMENTIERT in config.yaml - vorher waren sie nur im
        # Quelltext zu finden, obwohl der Code sie liest (Befund der Erhebung).
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, aus der Fallbestand und Rueckstau gelesen werden.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab.",
               "management/workload/overload_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py (Build 644)",
               "--coordinator-db"),
            _k("workload.overload.max_active_cases",
               "Aktive Faelle (Status offen oder in Arbeit) je Ermittler:in, "
               "ab denen die Ueberlastwarnung anschlaegt.",
               "10 Faelle",
               "management/workload/overload.py, overload_thresholds_from_config() Z. 152-168"),
            _k("workload.overload.max_red_cases",
               "Rote Faelle je Ermittler:in, ab denen gewarnt wird.",
               "3 Faelle",
               "management/workload/overload.py, overload_thresholds_from_config() Z. 152-168"),
            _k("workload.overload.backlog_alert",
               "Unzugewiesener Rueckstau ab dieser Groesse - eine systemische "
               "Meldung, die keiner einzelnen Person zuzurechnen ist.",
               "5 Faelle",
               "management/workload/overload.py, overload_thresholds_from_config() Z. 152-168"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.workload.overload_admin --coordinator-db ./data/coordinator.db",
                     "Gab die Ueberlastwarnung samt der geltenden Grenzen aus. Im Versuch: 'Grenzen: aktive<=10, rote<=3, Rueckstau-Alarm>=5', overload 0, warn 0, Rueckstau 0. Rueckgabewert 0.",
                     _GEPRUEFT_618),
            ),
            exit_codes=((0, "ausgegeben - AUCH bei ausgeloestem Alarm"),),
            warnungen=(
                "ES GIBT NUR DEN RUECKGABEWERT 0. Der Ueberlast- und Rueckstau-Alarm steht ausschliesslich in der Ausgabe. Eine Ueberwachung muss den Text oder die JSON-Ausgabe auswerten; auf den Rueckgabewert kann sie sich nicht stuetzen.",
                "DIE GRENZEN STEHEN IN JEDER AUSGABE und sind mitzulesen: ist die Konfiguration nicht lesbar, gelten die Vorgabewerte, und dieselbe Datenbank ergibt dann eine andere Bewertung.",
                "Es ist das einzige Werkzeug dieser beiden Gruppen, das die coordinator.db ausdruecklich NUR LESEND oeffnet. Deshalb muss die Datei vorhanden sein - ein falscher Pfad meldet einen Datenbankfehler, statt eine leere Datei anzulegen.",
            ),
        ),
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
        # Build 640 (Welle 3): geprueft an annotation_stats_admin.py Z. 26-60.
        # ZWEI Pfade, und sie verhalten sich VERSCHIEDEN - deshalb stehen sie
        # einzeln und nicht als ein Eintrag "die Pfade".
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, aus der die Faelle und ihre Zuordnung gelesen "
               "werden.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab.",
               "management/stats/annotation_stats_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py (Build 644)",
               "--coordinator-db"),
            _k("paths.evidence_db_dir",
               "Das Verzeichnis der evidence_<uid>.db, aus denen die "
               "Annotationen je Fall gezaehlt werden.",
               "./data/evidence/ - hier gibt es einen Rueckfallwert, anders "
               "als beim Pfad darueber.",
               "management/stats/annotation_stats_admin.py, _resolve_evidence_dir(); die Aufloesung selbst in core/werkzeug_konfig.py (Build 644)",
               "--evidence-dir"),
        ),
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
        # Build 640 (Welle 3): geprueft am Quelltext. Aufloesung:
        # Argument --coordinator-db > paths.coordinator_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, aus der die Vorausschau gerechnet wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad "
               "waere schlimmer als ein Abbruch.",
               "management/stats/forecast_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py (Build 644)", "--coordinator-db"),
        ),
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
        # Build 640 (Welle 3): geprueft am Quelltext. Aufloesung:
        # Argument --coordinator-db > paths.coordinator_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, aus der der Vorausschau-Bericht gebildet wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad "
               "waere schlimmer als ein Abbruch.",
               "management/stats/forecast_report_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py (Build 644)", "--coordinator-db"),
        ),
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
                # Build 702 (Vorgang ff7e80ab): Diese Warnung stand seit Build
                # 613 als NOTLOESUNG hier - eine Hilfe kann darauf hinweisen,
                # dass man etwas nachsehen muss, aber sie ersetzt keine
                # Meldung zur Laufzeit. Die Meldung gibt es jetzt; der Text
                # beschreibt daher nicht mehr eine Luecke, sondern das
                # Verfahren.
                "FAELLT DER ERZEUGUNGSRAHMEN AUS, ENTSTEHT DER BERICHT "
                "TROTZDEM - und das ist Absicht: ein geschriebenes Dokument "
                "nachtraeglich zu verwerfen, wuerde die Auskunft mit "
                "vernichten. Seit Build 702 wird der Ausfall ZWEIFACH "
                "benannt: auf der Fehlerausgabe mit dem Grund und einem "
                "Nachsatz zur Folge, und im Bericht selbst - die betroffene "
                "Zeile des Erzeugungsvermerks lautet dann 'nicht "
                "ermittelbar' statt Buildnummer 0 bzw. traegt hinter dem "
                "Kontonamen den Zusatz '[nicht aufgeloest]'. Der "
                "Rueckgabewert bleibt 0.",
                "OHNE '--actor' NIMMT DAS WERKZEUG DEN ANGEMELDETEN "
                "OS-BENUTZER. Ist der keinem person-Datensatz zugeordnet, "
                "laesst sich die Identitaet nicht aufloesen; der Bericht "
                "entsteht dann mit einem ungeprueften Erstellernamen und "
                "meldet das seit Build 702. Im Stapelbetrieb ist '--actor' "
                "deshalb anzugeben.",
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
        # Build 640 (Welle 3): geprueft am Quelltext. Aufloesung:
        # Argument --coordinator-db > paths.coordinator_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, aus der der Terminplan gebildet wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad "
               "waere schlimmer als ein Abbruch.",
               "management/stats/gantt_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py (Build 644)", "--coordinator-db"),
        ),
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
        # Build 640 (Welle 3): geprueft am ganzen Quelltext - kein
        # ConfigLoader, kein '--config'. '--coordinator-db' ist OPTIONAL und
        # dient nur dem Beleg im Protokollbuch; ohne die Angabe laeuft das
        # Werkzeug und schreibt keinen Beleg. Ein Rueckfall auf
        # 'paths.coordinator_db' findet NICHT statt.
        konfiguration=KONFIG_KEINE,
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
                # BUILD 706 (Vorgang 70641ff9) - DIESER TEXT WAR FALSCH, UND
                # ZWAR IN DER ENTSCHEIDENDEN HAELFTE. Er sagte, der Ausfall
                # stehe "auf der Fehlerausgabe". Gemessen am 12.08.2026 stand
                # dort NICHTS; ausserdem fehlte nicht nur die Kettenspitze,
                # sondern auch die Buildnummer (0) und der Ersteller
                # ('unbekannt'). Eine Hilfe, die eine Meldung zusichert, die es
                # nicht gibt, ist schlimmer als gar keine: sie laesst den
                # Leser darauf vertrauen, dass er es merken wuerde.
                "'export-html' liest die coordinator.db nur, wenn "
                "--coordinator-db gesetzt ist. OHNE die Angabe fehlen dem "
                "Erzeugungsvermerk die Kettenspitze UND die Identitaet der "
                "erzeugenden Person; beides steht seit Build 706 als Befund "
                "im Dokument und auf der Fehlerausgabe. Der Rueckgabewert "
                "bleibt 0.",
                "DIE BUILDNUMMER IST DAVON NICHT MEHR BETROFFEN. Bis Build "
                "702 trug die Datei ohne --coordinator-db 'Werkzeug-Build: "
                "0', obwohl die Nummer in build.json steht und keine "
                "Datenbank braucht. Seit Build 706 ist sie in jedem Fall "
                "richtig.",
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
        # Build 640 (Welle 3): geprueft am Quelltext. Aufloesung:
        # Argument --coordinator-db > paths.coordinator_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, aus der der Sachstandsbericht gebildet wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad "
               "waere schlimmer als ein Abbruch.",
               "management/stats/status_report_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py (Build 644)", "--coordinator-db"),
        ),
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
                # Build 702 (Vorgang ff7e80ab): siehe Kommentar beim
                # Prognosebericht - beide Werkzeuge trugen denselben Fehler.
                "Wie beim Prognosebericht: FAELLT DER ERZEUGUNGSRAHMEN AUS, "
                "entsteht der Bericht trotzdem. Seit Build 702 wird der "
                "Ausfall auf der Fehlerausgabe benannt und im "
                "Erzeugungsvermerk des Berichts als 'nicht ermittelbar' "
                "gekennzeichnet; der Rueckgabewert bleibt 0.",
                "OHNE '--actor' NIMMT DAS WERKZEUG DEN ANGEMELDETEN "
                "OS-BENUTZER. Ist der keinem person-Datensatz zugeordnet, "
                "meldet das Werkzeug seit Build 702 einen ungeprueften "
                "Erstellernamen. Im Stapelbetrieb ist '--actor' anzugeben.",
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
        # Build 640 (Welle 3): geprueft am Quelltext. Aufloesung:
        # Argument --coordinator-db > paths.coordinator_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, aus der die Ausgabedatei gebildet wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad "
               "waere schlimmer als ein Abbruch.",
               "management/export/export_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py (Build 644)", "--coordinator-db"),
        ),
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
                "'unbekannt [nicht aufgeloest]' im Erzeugungsvermerk der "
                "Mappe, darunter der Grund; das Werkzeug meldet es. Der "
                "Export laeuft trotzdem.",
                "openpyxl ist Voraussetzung. Fehlt es, bricht der Lauf mit 1 "
                "ab - die Mappe entsteht dann gar nicht.",
                # BUILD 708 (Vorgang 5001d293) - DIESER SATZ WAR RICHTIG UND
                # BESCHRIEB EINEN MANGEL. Er stand seit Build 640 als
                # Merkposten hier: die Mappe konnte 'Werkzeug-Build: 0'
                # tragen, und niemand erfuhr es. Genau derselbe Zustand wie
                # bei den Berichtswerkzeugen (ff7e80ab), nur ist export_admin
                # zusaetzlich am context_builder vorbeigelaufen.
                "DIE BUILDNUMMER IM VERMERK KOMMT AUS DER build.json DER "
                "BESTANDSWURZEL. Ist sie nicht lesbar - etwa weil das "
                "Werkzeug ausserhalb der Struktur aufgerufen wird - stand "
                "dort bis Build 706 eine '0', ohne jede Meldung. Seit Build "
                "708 lautet die Zeile 'Werkzeug-Build: nicht ermittelbar', "
                "der Grund steht darunter, und das Werkzeug sagt es auf der "
                "Fehlerausgabe. Der Rueckgabewert bleibt 0.",
                "ZU UNTERSCHEIDEN: eine GEBROCHENE Belegkette ist eine "
                "Aussage ueber den Bestand und erscheint als eigene Warnung "
                "mit der Fundstelle; ein unvollstaendiger Erzeugungsvermerk "
                "ist eine Aussage ueber die Mappe. Beides kann zugleich "
                "auftreten und wird getrennt gemeldet.",
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
        # Build 640 (Welle 3): geprueft am Quelltext. Aufloesung:
        # Argument --db > paths.coordinator_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, in der die Fallfreigabe belegt wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad "
               "waere schlimmer als ein Abbruch.",
               "management/external/case_release_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.external.case_release_admin --db ./data/coordinator.db list",
                     "Fuehrte die erteilten Freigaben auf. Auf dem leeren Bestand: 'Keine Freigaben.' Rueckgabewert 0.",
                     _GEPRUEFT_618),
            ),
            exit_codes=((0, "ausgegeben bzw. erteilt/entzogen"), (1, "Fach- oder Aufruffehler"),),
            warnungen=(
                "Der Empfaenger wird gegen die Verzeichnis-Freigabeliste geprueft. IST DIE KONFIGURATION NICHT LESBAR, wird eine LEERE Liste benutzt - dann wird alles abgelehnt. Das ist die sichere Richtung, sieht aber aus wie 'der Empfaenger ist unzulaessig' und nicht wie 'die Konfiguration fehlt'.",
                "Die Kennung hinter '--actor' muss als Person hinterlegt sein, sonst bricht der Aufruf ab.",
                "EIN TIPPFEHLER IM DATENBANKPFAD LEGT EINE LEERE DATEI AN, statt abzubrechen: die Verbindung wird schreibfaehig geoeffnet und die Datei nicht vorher auf Vorhandensein geprueft. Wer dann 'Keine Freigaben' liest, hat eine frische leere Datenbank vor sich und nicht den Bestand.",
                "'recipients' und 'umfang' oeffnen gar keine Datenbank - sie geben die zulaessigen Werte aus.",
            ),
        ),
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
        # Build 640 (Welle 3): geprueft am Quelltext. Aufloesung:
        # Argument --db > paths.coordinator_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, in der die externen Stellen gefuehrt werden.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab. Das ist Absicht: ein erratener Pfad "
               "waere schlimmer als ein Abbruch.",
               "management/external/external_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.external.external_admin --db ./data/coordinator.db list",
                     "Fuehrte die externen Vorgaenge auf. Auf dem leeren Bestand: 'Keine externen Vorgaenge.' Rueckgabewert 0.",
                     _GEPRUEFT_618),
            ),
            exit_codes=((0, "ausgegeben, keine rote Ampel"), (1, "Fach- oder Aufruffehler"), (2, "BEFUND: mindestens ein Vorgang steht auf rot - ueberfaellig oder verwaist. KEIN Fehler"),),
            warnungen=(
                "DER RUECKGABEWERT 2 IST NORMALBETRIEB und kein Absturz. Ein Skript, das ihn als Fehler behandelt, meldet einen Programmfehler, wo eine Wiedervorlage faellig ist.",
                "'close' ist ENDGUELTIG - das sagt das Werkzeug auch so.",
                "'--offen' UEBERSCHREIBT ein gleichzeitig angegebenes '--status'. Wer beides setzt, bekommt nicht, was er meint.",
                "'list' oeffnet die coordinator.db schreibfaehig, obwohl es nur liest. Vorgang eroeffnet (Muster wie Issue 906ede75).",
            ),
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
        # Build 640 (Welle 3): geprueft am ganzen Quelltext - kein
        # ConfigLoader, kein '--config'. Wie bei glossary_admin ist
        # '--coordinator-db' optional und dient nur dem Beleg; ein Rueckfall
        # auf 'paths.coordinator_db' findet NICHT statt.
        konfiguration=KONFIG_KEINE,
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.export.ausschleus_admin verify --dir ./ausschleusung",
                     "Rechnet jede Datei gegen das Manifest nach. Im Versuch auf einem LEEREN Verzeichnis: '[ausschleus] OK - alle Artefakte stimmen mit dem Manifest ueberein', Rueckgabewert 0 - siehe die erste Warnung, das ist ein Befund und keine Zusicherung.",
                     _GEPRUEFT_618),
            ),
            exit_codes=((0, "'add' aufgenommen, 'finalize' geschrieben, 'verify' Paket stimmt - AUCH bei einem LEEREN Paket MIT Manifest; das ist eine gueltige, wenn auch ungewoehnliche Lage"), (1, "'verify' BEFUND: das Paket weicht vom Manifest ab (veraendert, fehlend oder zusaetzlich) - kein Programmfehler; sonst Staging-Fehler"), (2, "'add' BEFUND: die Unbedenklichkeit ist nicht bestaetigt, das Artefakt wurde NICHT aufgenommen; 'verify' KEIN PAKET: in diesem Verzeichnis liegt kein manifest.json - hier ist nichts ausgeschleust worden, es gibt nichts zu pruefen (NEU Build 647, Vorgang d30b3d95)"),),
            warnungen=(
                "BEHOBEN IN BUILD 647 (Vorgang d30b3d95), hier festgehalten, weil aeltere Staende im Umlauf sind: Bis Build 646 meldete 'verify' auf einem Verzeichnis OHNE Manifest 'OK' mit Rueckgabewert 0 - ein Leerbefund wurde als Erfolgsmeldung ausgegeben. Seit Build 647 liefert dieser Fall den Rueckgabewert 2 und die Meldung 'KEIN PAKET'. WER EINEN AELTEREN STAND BEDIENT, sieht vor einer Ausschleusung zusaetzlich nach, ob ueberhaupt ein manifest.json da ist.",
                "'--unbedenklich' ist ein ausdruecklicher Freigabeschalter. Ohne ihn wird nichts aufgenommen, und eine leere Angabe bei '--cleared-by' wird ebenfalls abgewiesen - die Unbedenklichkeit braucht einen Namen.",
                "KEIN STILLES UEBERSCHREIBEN: ein bereits vorhandener Dateiname fuehrt zum Abbruch.",
                # BUILD 706 (Vorgang 70641ff9): Der Satz nannte nur die
                # Kettenspitze. Tatsaechlich trug die UEBERGABE.txt ohne
                # --coordinator-db auch Buildnummer 0 und Ersteller
                # 'unbekannt', und der Lauf sagte dazu nichts (gemessen am
                # 12.08.2026). Bei dem Dokument, das mit dem Paket an die
                # Staatsanwaltschaft geht, ist das keine Kleinigkeit.
                "Nur 'finalize' liest die coordinator.db, und zwar ausdruecklich nur lesend. Ist sie nicht angegeben oder nicht erreichbar, entsteht das Paket trotzdem - dem Erzeugungsvermerk der UEBERGABE.txt fehlen dann die Kettenspitze und die Identitaet der erzeugenden Person. Seit Build 706 steht beides als Befund im Dokument UND auf der Fehlerausgabe, mit dem Grund; der Rueckgabewert bleibt 0.",
                "DIE UEBERGABE.TXT GEHT AUS DEM HAUS. Wer sie ohne '--coordinator-db' und ohne '--actor' erzeugt, uebergibt ein Abgabedokument, dessen Erzeugungsvermerk niemanden benennt. Die Angaben sind nicht verpflichtend (Entscheidung Alex, 12.08.2026) - der Lauf sagt seit Build 706 aber, was fehlt.",
            ),
        ),
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
        # Build 640 (Welle 3): geprueft an lkae_admin.py, _prod_paths() Z. 34-52.
        #
        # DIESER EINTRAG IST EIN SONDERFALL und deshalb ausfuehrlich erklaert:
        # Das Werkzeug liest diese sechs Pfade NICHT, um sie zu benutzen,
        # sondern um sie zu MEIDEN. Sie bilden die Sperrliste, gegen die das
        # Zielverzeichnis des Demo-Pakets geprueft wird - ein Demo-Paket darf
        # niemals in einen Produktivpfad gebaut werden.
        #
        # FOLGE FUER DEN BETRIEB, die man kennen muss: Ist die config.yaml
        # nicht lesbar, faellt der Schutz auf './data/coordinator.db' und
        # './data/' zurueck (Z. 48-51) - er ist dann SCHWAECHER als sonst,
        # nicht abgeschaltet. Wer die Produktivdaten anderswo liegen hat und
        # eine unlesbare config.yaml, hat hier keinen wirksamen Schutz mehr.
        # Das Werkzeug sagt es auf der Fehlerausgabe; es bricht aber nicht ab.
        konfiguration=(
            _k("paths.coordinator_db",
               "Teil der Sperrliste: Das Zielverzeichnis des Demo-Pakets darf "
               "nicht auf diesen Pfad zeigen.",
               "bei unlesbarer config.yaml faellt die Sperrliste auf "
               "'./data/coordinator.db' und './data/' zurueck",
               "management/distribution/lkae_admin.py, _prod_paths() Z. 34-52"),
            _k("paths.evidence_db_dir",
               "Teil der Sperrliste (Beweismittel).",
               "siehe oben - gemeinsamer Rueckfall der ganzen Liste",
               "management/distribution/lkae_admin.py, _prod_paths() Z. 34-52"),
            _k("paths.forensic_db_dir",
               "Teil der Sperrliste (forensische Daten).",
               "siehe oben - gemeinsamer Rueckfall der ganzen Liste",
               "management/distribution/lkae_admin.py, _prod_paths() Z. 34-52"),
            _k("paths.assets_db_dir",
               "Teil der Sperrliste (Anlagen).",
               "siehe oben - gemeinsamer Rueckfall der ganzen Liste",
               "management/distribution/lkae_admin.py, _prod_paths() Z. 34-52"),
            _k("paths.templates_db",
               "Teil der Sperrliste (Vorlagen).",
               "siehe oben - gemeinsamer Rueckfall der ganzen Liste",
               "management/distribution/lkae_admin.py, _prod_paths() Z. 34-52"),
            _k("paths.default_db",
               "Teil der Sperrliste (gemeinsame Vorgaben).",
               "siehe oben - gemeinsamer Rueckfall der ganzen Liste",
               "management/distribution/lkae_admin.py, _prod_paths() Z. 34-52"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.distribution.lkae_admin verify --target ./lkae-paket",
                     "Prueft ein gebautes Paket gegen sein Manifest. Im Versuch gegen ein leeres Verzeichnis: 'FEHLER: Kein manifest.json in ...' auf der Fehlerausgabe, Rueckgabewert 1. Anders als bei ausschleus_admin wird das fehlende Manifest hier also erkannt.",
                     _GEPRUEFT_618),
            ),
            exit_codes=((0, "gebaut bzw. Paket stimmt"), (1, "Verteilungsfehler - etwa ein fehlendes Manifest"), (2, "BEFUND: 'verify' fand eine Abweichung zum Manifest - kein Programmfehler"),),
            warnungen=(
                "NICHT FUER DEN PRODUKTIVBETRIEB. Das sagt der Dateikopf ausdruecklich.",
                "'--freigabe' ist Pflicht-Freigabeschalter fuer 'build'. Ohne ihn wird nicht gebaut.",
                "'build' VERWEIGERT, wenn das Ziel eine produktive Datenablage ueberlappt oder wenn es nicht leer ist. IST DIE KONFIGURATION NICHT LESBAR, greift nur noch der Schutz ueber die Standardpfade - der Ueberlappungsschutz ist dann schwaecher.",
                "Es oeffnet keine Datenbank; die Konfiguration wird nur gelesen, um die produktiven Pfade zu kennen.",
            ),
        ),
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
        # Build 640 (Welle 4): geprueft an promotion_admin.py Z. 46-80.
        # ZWEIERLEI VERHALTEN in EINEM Werkzeug, deshalb einzeln aufgefuehrt:
        # der coordinator.db-Pfad bricht ohne Angabe ab, die drei
        # Datenverzeichnisse haben Rueckfallwerte.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, in der die Uebernahme belegt wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab.",
               "management/ops/promotion_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)", "--db"),
            _k("paths.forensic_db_dir",
               "Verzeichnis der forensic_<uid>.db.", "./data/forensic/",
               "management/ops/promotion_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)"),
            _k("paths.evidence_db_dir",
               "Verzeichnis der evidence_<uid>.db.", "./data/evidence/",
               "management/ops/promotion_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)"),
            _k("paths.assets_db_dir",
               "Verzeichnis der assets_<uid>.db.", "./data/assets/",
               "management/ops/promotion_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.ops.promotion_admin --db ./data/coordinator.db list",
                     "Fuehrte die Uebernahmeentscheidungen auf. Auf dem leeren Bestand: 'Keine Eintraege.' Rueckgabewert 0.",
                     _GEPRUEFT_618),
            ),
            exit_codes=((0, "ausgegeben bzw. entschieden"), (1, "Fach- oder Aufruffehler"),),
            warnungen=(
                "'--force' UEBERGEHT DIE KANDIDATENPRUEFUNG. Danach schuetzt nur noch die Zustandsmaschine. Der Schalter ist fuer den Ausnahmefall gedacht und nicht fuer den Regelbetrieb.",
                "'candidates' braucht die Pfade zu den Fall-Verzeichnissen. IST DIE KONFIGURATION NICHT LESBAR, werden stillschweigend die Standardpfade unter './data/' benutzt - das Ergebnis kann dann leer sein, OHNE dass ein Fehler erscheint. Eine leere Kandidatenliste ist deshalb erst dann eine Aussage, wenn die Pfade stimmen.",
                "'candidates' und 'list' oeffnen die coordinator.db schreibfaehig, obwohl sie nur lesen.",
            ),
        ),
    ),

    CliEintrag(
        schluessel="anon_html",
        pfad="tools/anon_html.py",
        aufruf="python tools/anon_html.py <datei.html> -x <xpath> [-o ziel.html] "
               "[--overwrite] [--encoding utf-8] [-d] [-v]",
        titel="HTML unverfaenglich machen",
        gruppe="Identitaeten und Externe",
        zweck="In einer HTML-Datei den GESAMTEN Textinhalt der ueber XPath "
              "ausgewaehlten Teilbaeume durch gleich langen Blindtext ('X') "
              "ersetzen, das Ergebnis nachpruefen und als NEUE Datei "
              "schreiben.",
        art="lesend",
        datenbanken=(),
        betrieb="Der Betrieb darf weiterlaufen. Das Werkzeug oeffnet keine "
                "Datenbank und beruehrt den Bestand nicht - es liest eine "
                "HTML-Datei und schreibt eine zweite daneben.",
        ausgabe="HTML-Datei (--output; ohne Angabe '<original>.new.html'). "
                "Sie entsteht NUR, wenn ersetzt wurde UND die Gegenprobe "
                "bestanden ist.",
        hinweis="SEIT BUILD 687 PRUEFT ES SICH SELBST NACH (Vorgang "
                "ad88708d): es blendet den GANZEN Teilbaum, liest die "
                "GESCHRIEBENE Datei neu ein und misst nach, dass darin kein "
                "Textknoten der getroffenen Auswahl mehr etwas anderes "
                "enthaelt als 'X' und Leerraum. Erst dann entsteht die "
                "Zieldatei. WAS DIESE PROBE NICHT ABDECKT, sagt die "
                "Schlussmeldung woertlich: den Rest der Datei und alle "
                "Attributwerte. BUILD 690 hat drei Nachbesserungen "
                "eingearbeitet, die erst der Vergleich mit einer zweiten, "
                "unabhaengig gebauten Fassung sichtbar gemacht hat - ein "
                "Fragment mit mehreren Knoten der obersten Ebene lief bis "
                "dahin GAR NICHT durch (die Gegenprobe scheiterte immer), "
                "verschachtelte Treffer wurden doppelt gezaehlt, und der von "
                "lxml erfundene Rahmen wurde nicht gemeldet. ES BLEIBT EIN "
                "HANDWERKZEUG: wer damit Material fuer die Weitergabe "
                "vorbereitet, liest das Ergebnis MIT DEN AUGEN gegen.",
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config', kein Zugriff auf config.yaml.
        # Build 687 erneut geprueft: unveraendert, die beiden neuen Optionen
        # '--overwrite' und '--encoding' kommen ausschliesslich von der
        # Kommandozeile.
        konfiguration=KONFIG_KEINE,
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/anon_html.py probe.html "
                     "-x \"//div[@class='postmsg']\" --dry-run",
                     "Zeigt je Treffer Original und Blindtext und schreibt "
                     "NICHTS. Im Versuch: 'Matched 2 element(s), replaced 4 "
                     "text node(s).', dann '[DRY RUN] No file written.' "
                     "Rueckgabewert 0.",
                     _GEPRUEFT_687),
                _bsp("python tools/anon_html.py probe.html "
                     "-x \"//div[@class='postmsg']\" -o anonym.html",
                     "Schrieb anonym.html. Aus '<div>Vorname <b>Nachname</b> "
                     "wohnt in Musterstadt.</div>' wurde '<div>XXXXXXX "
                     "<b>XXXXXXXX</b> XXXXX XX XXXXXXXXXXXX</div>' - Wortlaenge "
                     "und Wortgrenze erhalten, das <b> steht noch. Danach "
                     "'VERIFIED: ... no text node contains any character "
                     "other than X and whitespace.' Rueckgabewert 0.",
                     _GEPRUEFT_687),
                _bsp("python tools/anon_html.py probe.html "
                     "-x \"//div[@class='gibtesnicht']\" -o anonym.html",
                     "Bricht ab: 'FINDING: No elements matched the given "
                     "XPath(s).' KEINE Datei geschrieben. Rueckgabewert 2.",
                     _GEPRUEFT_687),
                _bsp("python tools/anon_html.py probe.html "
                     "-x \"//div[@class='postmsg']\" -o anonym.html "
                     "(bei bereits vorhandener anonym.html)",
                     "Bricht ab: 'ERROR: Output file already exists' und "
                     "'Refusing to overwrite it.' Die vorhandene Datei bleibt "
                     "unangetastet. Rueckgabewert 4.",
                     _GEPRUEFT_687),
                _bsp("python tools/anon_html.py probe.html "
                     "-x \"//div\" --encoding ascii",
                     "Bricht VOR jeder Verarbeitung ab: 'ERROR: File is not "
                     "valid ascii: ... byte 0xc3 in position 29'. Keine "
                     "Datei. Rueckgabewert 1.",
                     _GEPRUEFT_687),
                _bsp("python tools/anon_html.py schnipsel.html "
                     "-x \"//div[@class='postmsg']\" -o anonym.html",
                     "Auf einem von Hand herausgeschnittenen Stueck OHNE "
                     "'<html>' und mit mehreren Knoten der obersten Ebene: "
                     "laeuft durch, Rueckgabewert 0, mit dem Hinweis "
                     "'NOTE: ... processed as a FRAGMENT'. BIS BUILD 687 "
                     "endete genau dieser Fall mit Rueckgabewert 3 und "
                     "'position path ... resolved to 0 element(s)' - es "
                     "entstand GAR KEINE Datei.",
                     _GEPRUEFT_690),
                _bsp("python tools/anon_html.py probe.html",
                     "Bricht ab: 'ERROR: Either --xpath-file or --xpath must "
                     "be provided.' Rueckgabewert 1.",
                     _GEPRUEFT_687),
            ),
            exit_codes=((0, "ersetzt, Gegenprobe bestanden, Datei "
                            "geschrieben (bzw. Trockenlauf durchgelaufen)"),
                        (1, "Aufruffehler (kein XPath, beide XPath-Optionen "
                            "zugleich, leere Ausdrucksdatei), Eingabedatei "
                            "fehlt, XPath ungueltig, Kodierung passt nicht "
                            "zur Datei, HTML nicht lesbar oder Ausgabe nicht "
                            "schreibbar"),
                        (2, "BEFUND - kein Element getroffen ODER getroffen, "
                            "aber nichts zu ersetzen. KEINE Datei "
                            "geschrieben"),
                        (3, "BEFUND - die Gegenprobe an der geschriebenen "
                            "Datei ist gescheitert. KEINE Datei geschrieben, "
                            "eine vorhandene Vorgaengerdatei blieb "
                            "unangetastet"),
                        (4, "die Zieldatei existiert und '--overwrite' wurde "
                            "nicht angegeben - es wurde nichts getan")),
            warnungen=(
                "DIE GEGENPROBE BELEGT NUR DIE GETROFFENE AUSWAHL. Sie sagt "
                "NICHTS ueber den Rest der Datei und NICHTS ueber "
                "Attributwerte. Wer den falschen XPath waehlt, bekommt eine "
                "Datei, die 'VERIFIED' meldet und daneben Klartext enthaelt. "
                "Die Schlussmeldung sagt diese Grenze woertlich - sie ist zu "
                "LESEN und nicht zu ueberblaettern.",
                "ATTRIBUTWERTE WERDEN NICHT ERSETZT. GEMESSEN am 2026-08-11: "
                "'title=\"Klarname im Attribut\"' und "
                "'href=\"mailto:klar@example.com\"' innerhalb eines "
                "getroffenen Elements ueberleben unveraendert. Das ist eine "
                "ENTSCHEIDUNG und kein Versehen - 'class' und 'href' blind zu "
                "ueberschreiben zerstoert genau die Gestalt, um derentwillen "
                "die Datei weitergegeben wird. Ihre ZAHL wird immer gemeldet, "
                "mit '-v' die Liste. Sie sind von Hand zu pruefen.",
                "DER BLINDTEXT ERHAELT WORTLAENGEN UND WORTGRENZEN. Das ist "
                "gewollt (die Gestalt der Seite bleibt beurteilbar), heisst "
                "aber auch: die Laenge jedes Wortes bleibt ablesbar. Fuer "
                "eine Weitergabe, bei der auch das nicht stehen bleiben soll, "
                "taugt das Ergebnis nicht.",
                "DIE KODIERUNG WIRD ANGESAGT, NICHT GERATEN ('--encoding', "
                "Vorgabe utf-8). Passt sie nicht zur Datei, BRICHT der Lauf "
                "ab (Rueckgabewert 1), statt beschaedigten Text zu schreiben. "
                "GRUND, gemessen: ohne '<meta charset>' riet lxml bis Build "
                "686 und landete bei Latin-1; nicht getroffener Text kam dann "
                "DOPPELT KODIERT aus dem Lauf. Ein von Hand "
                "herausgeschnittenes Fragment hat regelmaessig keine "
                "Deklaration.",
                "EIN FRAGMENT OHNE '<html>' BEKOMMT VON lxml EINEN RAHMEN. "
                "GEMESSEN: um mehrere Knoten der obersten Ebene ein <div>, um "
                "blossen Text ein <span>; offene Tags werden geschlossen. "
                "Dieser Rahmen steht dann in der Weitergabe, ohne je in der "
                "Vorlage gestanden zu haben, und ein weiter Ausdruck "
                "('//div') trifft ihn MIT. Seit Build 690 meldet das Werkzeug "
                "die Lage ('NOTE: ... processed as a FRAGMENT'); aufloesen "
                "kann es sie nicht - ein hinzugefuegter Rahmen ist von einem "
                "gleichnamigen echten Element nicht sicher zu unterscheiden. "
                "HIER IST DER VERGLEICH MIT DER VORLAGE PFLICHT.",
                "DER INHALT VON <script> UND <style> WIRD MITGEBLENDET, wenn "
                "er im getroffenen Teilbaum liegt. Ein ausgenommener Knoten "
                "waere ein Versteck. Wer eine Seite samt Skript vorfuehren "
                "will, waehlt den XPath entsprechend enger.",
                "'lxml' ist eine zusaetzliche Abhaengigkeit "
                "(requirements.txt Zeile 7). Ohne sie bricht das Werkzeug "
                "beim Import ab.",
            ),
        ),
    ),

    # ------------------------------------------------- Betrieb und Sicherung
    CliEintrag(
        schluessel="backup_admin",
        pfad="management/backup/backup_admin.py",
        aufruf="python -m management.backup.backup_admin "
               "plan|run|list|pruefen|versatz|restore",
        titel="Datensicherung",
        gruppe="Betrieb und Sicherung",
        zweck="Die auditierte Datensicherung planen, ausfuehren, die "
              "vergangenen Laeufe auflisten, den Versatz im Sicherungssatz "
              "nachrechnen (Build 717) - und eine Sicherung geprueft "
              "zurueckspielen (Build 680).",
        art="gemischt",
        datenbanken=("coordinator.db (run schreibend; plan/list/pruefen "
                     "lesend, seit Build 627 mit 'mode=ro' erzwungen)",
                     "alle uebrigen Datenbanken werden zur Sicherung "
                     "AUSSCHLIESSLICH gelesen - seit Build 627 auch technisch "
                     "erzwungen ('mode=ro'). EINE AUSNAHME: der optionale "
                     "'wal_checkpoint(PASSIVE)' schreibt naturgemaess in die "
                     "Quelle; wer das nicht will, setzt backup.checkpoint auf "
                     "etwas anderes als 'passive' - die Sicherung braucht ihn "
                     "nicht, 'VACUUM INTO' liest ohnehin konsistent ueber das "
                     "WAL hinweg"),
        betrieb="TEILWEISE betriebsvertraeglich - die Einstufung ist am "
                "2026-07-31 nachgeprueft und RICHTIGGESTELLT worden (Build "
                "616). 'plan' und 'versatz' sind rein lesend und jederzeit "
                "unbedenklich; 'versatz' oeffnet nicht einmal eine Datenbank, "
                "es liest allein die Manifest-Dateien. "
                "'run' veraendert die Quellen NICHT (es kopiert mit 'VACUUM "
                "INTO'), aber die frueher hier stehende Zusage 'blockiert "
                "den Zugriff nicht' traegt so nicht: unter dem Rollback-"
                "Journal, das seit dem WAL-Verbot ueberall gilt, schliessen "
                "Leser und Schreiber einander aus. Vor allem aber ist der "
                "Sicherungs-SATZ nicht punktgleich - die Datenbanken werden "
                "nacheinander gesichert, jede fuer sich stimmig, der Satz "
                "als Ganzes nicht. Fuer eine wiederherstellbare Sicherung "
                "sollte kein Schreiber offen sein. Einzelheiten und "
                "Vorgaenge: siehe Warnungen.\n\n"
                "STUFE B (Einstufung Build 686): kein Wartungsvorbehalt, "
                "und das mit Absicht - die Ungleichzeitigkeit des Satzes ist "
                "gekennzeichnet statt verboten (Entscheidung mc 2026-07-31).\n\n"
                "'restore' (Build 680) LEGT NUR EINE DATEI NEBEN DAS "
                "ORIGINAL und ueberschreibt keine Datenbank; der Tausch bleibt "
                "Handarbeit nach der ausgegebenen Anleitung. Gegenueber der "
                "coordinator.db ist es rein lesend - im Ernstfall kann sie "
                "selbst das Ersetzungsziel sein.",
        beleg=True,
        befehle=(
            _b("plan", "lesend",
               "Was gesichert wuerde, samt Platzbedarf. Schreibt nichts."),
            _b("run", "schreibend",
               "Sicherung ausfuehren und den Lauf belegen."),
            _b("list", "lesend", "Die REGISTRIERTEN Laeufe auflisten - was "
               "geschehen ist, nicht was heute im Ordner liegt. Seit Build "
               "626 Rueckgabewert 1, wenn mindestens eine Sicherung als "
               "nicht integer vermerkt ist. Seit Build 627 oeffnet es die "
               "coordinator.db wirklich nur lesend ('mode=ro', kein "
               "Journalmodus-PRAGMA) - bis Build 626 war die Einstufung "
               "'lesend' eine Zusage, die nichts durchsetzte."),
            _b("pruefen", "lesend", "Den SICHERUNGSORDNER ansehen und je "
               "Datenbank sagen, wie viele BRAUCHBARE Generationen uebrig "
               "sind (Build 626). Rein lesend - eine Datei mit heissem "
               "Journal wird nicht einmal geoeffnet, weil SQLite sie dabei "
               "auf 0 Byte verkuerzen wuerde. Rueckgabewert 2 heisst: "
               "mindestens eine Datenbank hat KEINE brauchbare Sicherung. "
               "Mit '--pruefsummen' werden die beim Sichern erhobenen "
               "SHA512 gegengerechnet; dass es NICHT geschehen ist, steht "
               "im Befund."),
            _b("versatz", "lesend", "DIE NACHRECHNUNG (Build 717, "
               "Vorgang 77757536). Sie beantwortet aus den Manifesten die "
               "Frage, die seit Build 617 ablesbar, aber nie gemessen war: "
               "wie weit liegen erste und letzte Kopie eines Laufs "
               "auseinander? Ausgegeben werden kleinste/mittlere/groesste "
               "Spanne, welche Datenbank die Spanne bestimmt und in welchen "
               "Laeufen eine Fall-Datenbank waehrend des Laufs entstand. "
               "REIN LESEND - es wird keine Datenbank geoeffnet, nur die "
               "Manifeste gelesen. ES BEURTEILT DIE SPANNE NICHT VON SELBST: "
               "eine Grenze, ab der der Versatz zu gross ist, ist nicht "
               "entschieden, und eine fest verdrahtete waere eine "
               "Entscheidung im Gewand einer Messung. Wer eine pruefen will, "
               "nennt sie mit '--schwelle-minuten'; dass NICHT beurteilt "
               "wurde, steht sonst im Bericht."),
            _b("restore", "schreibend", "DER RUECKWEG (Build 680, Vorgang "
               "2785556a). Er prueft die Sicherung gegen die beim Sichern "
               "erhobene Pruefsumme, sieht sie innen an, probt die "
               "Zieldatenbank auf Ruhe - und legt die gegengelesene Kopie "
               "NEBEN das Original, als '<name>.wiederhergestellt'. "
               "ER UEBERSCHREIBT NIEMALS EINE DATENBANK: der Tausch bleibt "
               "Handarbeit nach der ausgegebenen Anleitung (Entscheidung "
               "Alex, 2026-08-05). 'schreibend' bezieht sich allein auf "
               "die neue Datei neben dem Original und auf den Beleg "
               "daneben; an der Zieldatenbank und an der coordinator.db "
               "aendert dieser Unterbefehl nichts. Mit '--trocken' prueft "
               "er alles und schreibt gar nichts."),
        ),
        ausgabe="Sicherungsdateien und ein Manifest im Sicherungsverzeichnis "
                "(bei 'run'). Bei 'restore': die Datei "
                "'<ziel>.wiederhergestellt' neben der Zieldatenbank und "
                "daneben der vollstaendige Befund als "
                "'<ziel>.wiederhergestellt.befund.json'.",
        # Build 639 (Ticket 60e4236e, das dieses Werkzeug ausdruecklich
        # nennt): geprueft am Quelltext von management/backup/backup_config.py
        # (from_config, Z. 51-83) und management/backup/backup_admin.py
        # (_paths_from_cfg Z. 60, _coordinator_db Z. 63-70).
        #
        # AUSDRUECKLICH NICHT AUFGENOMMEN: 'db.journal_mode'. Es liegt nahe,
        # dass ein Sicherungswerkzeug diesen Eintrag auswertet - es tut es
        # NICHT. backup_admin ruft apply_journal_mode(con, db_path) ohne
        # 'mode' auf (Z. 84) und bekommt damit den fest verdrahteten
        # Vorgabewert aus db/journal_policy.py, nicht den Eintrag aus
        # config.yaml. Eine plausible Angabe ohne Fundstelle waere hier eine
        # Vermutung gewesen.
        konfiguration=(
            _k("backup.dest_dir",
               "Wohin gesichert wird. In der Produktivumgebung der UNC-Pfad "
               "auf dem Sicherungsziel. Das Verzeichnis oder sein "
               "Elternverzeichnis muss erreichbar sein - sonst bricht die "
               "Vorabpruefung ab, BEVOR etwas geschrieben wird.",
               "./backups/", "management/backup/backup_config.py, Z. 51-56"),
            _k("backup.retention_count",
               "Wie viele Generationen je Datenbank behalten werden. Aeltere "
               "werden nach dem Lauf entfernt. Muss mindestens 1 sein.",
               "7", "management/backup/backup_config.py, Z. 58-65"),
            _k("backup.min_free_factor",
               "Wie viel Platz am Ziel frei sein muss, als Vielfaches der "
               "Gesamtgroesse aller Quellen. Der Aufschlag deckt den "
               "voruebergehenden Mehrbedarf der Kopie ab. Vorfallgetrieben: "
               "volle Platte am 2026-07-01.",
               "1,3", "management/backup/backup_config.py, Z. 68-74"),
            _k("backup.checkpoint",
               "Behandlung eines vorgefundenen WAL vor der Kopie: 'passive' "
               "oder 'none'. 'truncate' ist unzulaessig. 'passive' schreibt "
               "als einzige Stelle des Laufs in die QUELLE; wer das nicht "
               "will, setzt 'none' - die Sicherung braucht den Schritt "
               "nicht.",
               "passive", "management/backup/backup_config.py, Z. 76-81"),
            _k("backup.include_shared_dbs",
               "Ob default.db, templates.db und translations.db mitgesichert "
               "werden. Die fallbezogenen Datenbanken werden IMMER gesichert, "
               "unabhaengig von diesem Eintrag.",
               "true (mitsichern)",
               "management/backup/backup_config.py, Z. 83"),
            _k("paths.coordinator_db",
               "Die Datenbank, in der der Lauf registriert und belegt wird - "
               "und zugleich eine der gesicherten Quellen.",
               "./data/coordinator.db",
               "management/backup/backup_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 646)",
               "--coordinator-db"),
            _k("paths.forensic_db_dir",
               "Verzeichnis der forensic_<uid>.db - Quellen der Sicherung.",
               "./data/forensic/",
               "management/backup/backup_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 646)"),
            _k("paths.evidence_db_dir",
               "Verzeichnis der evidence_<uid>.db - Quellen der Sicherung.",
               "./data/evidence/",
               "management/backup/backup_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 646)"),
            _k("paths.assets_db_dir",
               "Verzeichnis der assets_<uid>.db - Quellen der Sicherung.",
               "./data/assets/",
               "management/backup/backup_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 646)"),
            _k("paths.default_db",
               "Die default.db - Quelle der Sicherung, sofern "
               "backup.include_shared_dbs gesetzt ist.",
               "./data/default.db",
               "management/backup/backup_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 646)"),
            _k("paths.templates_db",
               "Die templates.db - Quelle der Sicherung, sofern "
               "backup.include_shared_dbs gesetzt ist.",
               "./data/templates.db",
               "management/backup/backup_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 646)"),
            _k("paths.translations_db",
               "Die translations.db - Quelle der Sicherung, sofern "
               "backup.include_shared_dbs gesetzt ist.",
               "./data/translations.db",
               "management/backup/backup_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 646)"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.backup.backup_admin pruefen "
                     "--config ./cfg.yaml",
                     "Sah den Sicherungsordner durch. Im Versuch: "
                     "'coordinator 2 brauchbar, 1 unbrauchbar' - der "
                     "Abbruchrest wurde am heissen Journal erkannt und NICHT "
                     "geoeffnet; er lag danach unveraendert da (37.158.912 "
                     "Byte). Rueckgabewert 1.",
                     _GEPRUEFT_626),
                _bsp("python -m management.backup.backup_admin pruefen "
                     "--config ./cfg.yaml",
                     "Derselbe Ordner, nachdem die beiden brauchbaren "
                     "Generationen entfernt worden waren: 'OHNE BRAUCHBARE "
                     "SICHERUNG (1): coordinator', zusaetzlich auf der "
                     "Fehlerausgabe. Rueckgabewert 2 - der Ernstfall.",
                     _GEPRUEFT_626),
                # --- Der Rueckweg, in der Reihenfolge, in der man ihn faehrt.
                _bsp("python -m management.backup.backup_admin restore "
                     "--config ./config.yaml --db-label evidence_18 "
                     "--trocken",
                     "Am gesunden Bestand: elf Pruefschritte, davon neun "
                     "'OK' und zwei 'OFFEN' (geschrieben/gegengelesen - es "
                     "war ja Trockenlauf). Die Zeile, auf die es ankommt, "
                     "lautete 'SHA512 stimmt mit der beim Sichern erhobenen "
                     "ueberein'. Abschluss: 'TROCKENLAUF BESTANDEN'. "
                     "Rueckgabewert 0.",
                     _GEPRUEFT_680),
                _bsp("python -m management.backup.backup_admin restore "
                     "--config ./config.yaml --db-label evidence_18",
                     "DER ERNSTFALL. Zuvor waren die ersten 4096 Byte der "
                     "evidence_18.db mit Nullen ueberschrieben worden. Der "
                     "Lauf legte die Kopie ab ('Kopie nachgelesen: SHA512 "
                     "gleich der Sicherung, integrity_check ok'), schrieb "
                     "den Beleg daneben und gab die Tauschanleitung aus - "
                     "mit dem Vorbehalt 'DIE ZIELDATENBANK IST SELBST "
                     "BESCHAEDIGT' VOR Schritt 1. Rueckgabewert 1: die "
                     "Kopie ist in Ordnung, das ZIEL ist es nicht.",
                     _GEPRUEFT_680),
                _bsp("python -m management.backup.backup_admin restore "
                     "--config ./config.yaml --db-label evidence_18 "
                     "--trocken",
                     "SCHRITT 4 DER ANLEITUNG, nach dem Tausch von Hand "
                     "(Original nach '.vor_wiederherstellung' verschoben, "
                     "Kopie an seine Stelle). Jetzt meldete auch "
                     "'ziel_in_ruhe' ein 'Zieldatei in Ruhe (exklusiv "
                     "erhalten)', und die Pruefsummenzeile stimmte - die "
                     "zertifizierte Sicherung lag an ihrem Platz. "
                     "Gegengelesen: 200 Zeilen, user_version 7, "
                     "integrity_check ok. Rueckgabewert 0.",
                     _GEPRUEFT_680),
                # --- Die Nachrechnung (Vorgang 77757536).
                _bsp("python -m management.backup.backup_admin versatz "
                     "--verzeichnis /tmp/vzdemo --ortszeit-versatz 120 "
                     "--arbeitszeit 07:00-18:00",
                     "Sechs handgebaute Laeufe und ein Manifest aus der Zeit "
                     "vor Build 617. Ausgegeben: Spanne kleinste 1:55 min / "
                     "Median 2:17 min / groesste 11:59 min; 'default' war in "
                     "allen sechs Laeufen die laengste Kopie und machte im "
                     "Median 78 % der Spanne aus; ein Lauf hatte eine "
                     "waehrend der Sicherung entstandene evidence_4711.db. "
                     "Das alte Manifest stand namentlich unter 'NICHT "
                     "AUSGEWERTET' und ging in keine Zahl ein. "
                     "Rueckgabewert 1. DIE ZAHLEN SIND NACHGEBAUT - sie "
                     "belegen die Lesart, nicht den Betrieb.",
                     _GEPRUEFT_717),
                _bsp("python -m management.backup.backup_admin versatz "
                     "--verzeichnis /tmp/vzdemo --arbeitszeit 07:00-18:00",
                     "ABBRUCH ohne Auswertung: '--arbeitszeit verlangt "
                     "zusaetzlich --ortszeit-versatz', mit der Begruendung "
                     "auf der Fehlerausgabe. Rueckgabewert 3. Es wurde "
                     "NICHTS ausgegeben, was wie ein Ergebnis aussieht.",
                     _GEPRUEFT_717),
            ),
            exit_codes=((0, "'plan': Vorabpruefung bestanden. 'run': ALLE "
                            "Datenbanken gesichert UND integer. 'list': "
                            "ausgegeben, keine als defekt vermerkt. "
                            "'pruefen': nichts zu beanstanden. 'versatz': "
                            "ausgewertet, nichts zu beanstanden. 'restore': "
                            "die gegengelesene Kopie liegt bereit und am "
                            "Ziel steht nichts entgegen"),
                        (1, "'run': mindestens eine Sicherung ist "
                            "fehlgeschlagen oder nicht integer. 'list': "
                            "mindestens eine registrierte Sicherung ist als "
                            "nicht integer vermerkt. 'pruefen': Befunde im "
                            "Ordner, aber jede Datenbank hat noch mindestens "
                            "eine brauchbare Generation. 'versatz': BEFUND - "
                            "zu wenige auswertbare Laeufe fuer die vom "
                            "Vorgang verlangte Grundlage, oder waehrend "
                            "eines Laufs ist eine Fall-Datenbank entstanden, "
                            "oder eine mit '--schwelle-minuten' GENANNTE "
                            "Grenze ist ueberschritten, oder ein Manifest "
                            "konnte nicht ausgewertet werden. 'restore': DIE "
                            "KOPIE LIEGT BEREIT, ABER AM ZIEL STEHT ETWAS "
                            "ENTGEGEN - im haeufigsten Fall ist das genau "
                            "die Nachricht 'deine Zieldatenbank ist "
                            "beschaedigt, die Ersatzdatei steht daneben'"),
                        (2, "'plan'/'run': die Vorabpruefung ist "
                            "fehlgeschlagen (etwa zu wenig Platz); bei "
                            "'run' wurde dann NICHTS gesichert. 'pruefen': "
                            "DER ERNSTFALL - mindestens eine Datenbank hat "
                            "KEINE brauchbare Sicherung. 'versatz': OHNE "
                            "GRUNDLAGE - es liegt kein einziges Manifest aus "
                            "Build 617 oder neuer vor, der Versatz ist also "
                            "nicht einmal ablesbar. Das wiegt SCHWERER als "
                            "der Befund 1: ein Befund ist Wissen, dies ist "
                            "die Abwesenheit von Wissen. 'restore': es "
                            "liegt KEINE Kopie bereit, obwohl die Sicherung "
                            "taugt (Platz, Schreibfehler, Gegenprobe "
                            "gescheitert)"),
                        (3, "'pruefen': das Sicherungsverzeichnis ist nicht "
                            "lesbar - es ist gar nichts festgestellt. "
                            "'versatz': dasselbe - oder die Angaben zur "
                            "Uhrzeit sind unvollstaendig ('--arbeitszeit' "
                            "ohne '--ortszeit-versatz'); auch dann ist "
                            "nichts festgestellt, und das ist gewollt: eine "
                            "Arbeitszeit in Ortszeit gegen UTC-Stempel zu "
                            "halten waere im Sommer um zwei Stunden daneben, "
                            "ohne dass man es der Ausgabe ansieht. "
                            "'restore': DIE SICHERUNG SELBST TAUGT NICHT - "
                            "falsche oder fehlende Pruefsumme, nicht "
                            "integer, leer, gar nicht gefunden. Der "
                            "schwerste Fall: hier ist nicht der Rueckweg "
                            "gescheitert, sondern das, worauf man sich "
                            "verlassen wollte")),
            warnungen=(
                "'restore' TAUSCHT NICHT. Es legt die gepruefte Kopie NEBEN "
                "das Original und ueberschreibt keine Datenbank - der Tausch "
                "bleibt Handarbeit nach der ausgegebenen Anleitung "
                "(Entscheidung Alex, 2026-08-05). Das ist Absicht: ab dem "
                "01.07.2026 stehen echte Ermittlerdaten in den Datenbanken, "
                "und ein Werkzeug, das ein Beweismittel ueberschreiben KANN, "
                "ist dauerhaft eine Angriffsflaeche - nicht nur im "
                "Ernstfall. Wer die Anleitung faehrt, LOESCHT DAS ORIGINAL "
                "NICHT, sondern legt es auf '.vor_wiederherstellung' "
                "beiseite: es ist das einzige Stueck, das noch Daten aus der "
                "Zeit NACH dem Sicherungszeitpunkt tragen koennte.",
                "'restore' SCHREIBT KEINEN AUDITBELEG in die coordinator.db, "
                "und das ist bewusst und nicht vergessen: im Ernstfall kann "
                "ausgerechnet die coordinator.db die Datenbank sein, die zu "
                "ersetzen ist - ein Rueckweg, der einen Schreibzugriff auf "
                "sie voraussetzt, waere dann nicht zu fahren. "
                "EventType.RESTORE_PERFORMED bleibt deshalb reserviert und "
                "gehoert zum TAUSCH, den ein Mensch verantwortet. Belegt ist "
                "der Lauf trotzdem: der vollstaendige Befund liegt als "
                "'<ziel>.wiederhergestellt.befund.json' neben der Kopie und "
                "gehoert zur Akte.",
                "EINE SICHERUNG OHNE ERHOBENE PRUEFSUMME WIRD VON 'restore' "
                "NICHT DURCHGEWUNKEN. Liegt zu einer Datei keine "
                "registrierte SHA512 vor - etwa weil sie von Hand vom "
                "Sicherungsmedium geholt wurde oder die Registrierung "
                "unlesbar ist -, ist das ein BEFUND mit Rueckgabewert 3 und "
                "kein Durchmarsch. Genau dieser Zustand ist der Anlass des "
                "Vorgangs 2785556a gewesen: die Summe wurde seit Build 354 "
                "erhoben und bis Build 626 nie wieder ausgewertet.",
                "DIE AUFBEWAHRUNG ZAEHLT SEIT BUILD 625 NUR BRAUCHBARE "
                "GENERATIONEN. Bis Build 624 behielt die Aufraeumung je "
                "Datenbank die neuesten Kopien allein nach dem Zeitstempel im "
                "Dateinamen; ob eine Kopie die Pruefung bestanden hatte, ging "
                "NICHT ein - eine defekte Sicherung zaehlte als juengste "
                "Generation und verdraengte die aelteste gute (Vorgang "
                "651e6d84, kritisch). BEHOBEN, dreifach: eine nicht belegte "
                "Kopie wird auf '.defekt' umbenannt und traegt den zaehlenden "
                "Namen nicht mehr; beschnitten wird nur ein Label, fuer das "
                "DIESER Lauf eine belegte Kopie erzeugt hat; und jede Datei "
                "wird vor dem Zaehlen billig nachgesehen, damit auch eine "
                "Altlast aus einem abgebrochenen Lauf auffaellt. Geloescht "
                "wird das Beiseitegelegte nicht - an einer Teildatei sieht "
                "man, woran es gescheitert ist.",
                "PRAGMA integrity_check ALLEIN ZERTIFIZIERT KEINE SICHERUNG - "
                "gemessen am 2026-08-01: eine mitten im 'VACUUM INTO' "
                "abgebrochene Sicherung hinterlaesst eine Teildatei samt "
                "Journal; beim ERSTEN Oeffnen rollt SQLite zurueck, die Datei "
                "ist danach 0 Byte gross - und integrity_check meldet darauf "
                "'ok'. Eine leere SQLite-Datei ist formal fehlerfrei. SEIT "
                "BUILD 625 wird die Kopie deshalb gegen die QUELLE gemessen: "
                "integrity_check UND user_version UND Zahl der Schemaobjekte "
                "UND nicht leer, wenn die Quelle es nicht war.",
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
                "die Ungleichzeitigkeit damit nicht - sie ist sichtbar. SEIT "
                "BUILD 717 IST SIE AUCH AUSRECHENBAR: 'backup_admin "
                "versatz' bildet aus den Manifesten die Zahl, auf der die "
                "Entscheidung von mc bisher nur als Annahme ruht (Vorgang "
                "77757536). SOLANGE DIESE ZAHL NICHT AUS PRODUKTIVEN "
                "LAEUFEN GEBILDET IST, bleibt die Entscheidung gegen ein "
                "Wartungsfenster unbelegt - sie ist damit nicht falsch, aber "
                "sie ist ungeprueft.",
                "WAS WAEHREND DES LAUFS ENTSTEHT, WIRD NICHT GESICHERT - "
                "aber seit Build 617 GENANNT: eine Fall-Datenbank, die es "
                "beim Planen noch nicht gab, steht danach im Manifest unter "
                "'nicht_gesichert_weil_neu' und auf der Konsole. Sie fehlt "
                "im Satz und ist beim naechsten Lauf dabei.",
                # BUILD 717 - VIER UEBERHOLTE WARNUNGEN BERICHTIGT
                # (Vorgang siehe eintraege_claude_Build717.json, Weisung
                # Alex 13.08.2026). Sie standen unveraendert hier, waehrend
                # derselbe Eintrag weiter oben bereits das Gegenteil
                # beschrieb. EINE HILFE, DIE SICH SELBST WIDERSPRICHT, IST
                # SCHLIMMER ALS EINE LUECKE: der Leser kann nicht wissen,
                # welche Haelfte gilt, und wird im Zweifel der Warnung
                # glauben - hier also dem aelteren, falschen Stand.
                #
                # (1) "'list' LIEFERT IMMER 0" - falsch seit Build 626.
                #     cmd_list gibt 1 zurueck, sobald eine registrierte
                #     Sicherung als nicht integer vermerkt ist
                #     (backup_admin.py, cmd_list, Zaehler 'defekt'). Der
                #     Unterbefehlstext sagt das seit Build 626; die Warnung
                #     sagte weiter das Gegenteil. GESTRICHEN - der noch
                #     gueltige Teil (list liest die Registrierung, nicht die
                #     Platte) steht beim Unterbefehl.
                # (2) "KEIN RUECKWEG" - falsch seit Build 680. Ersetzt durch
                #     die Einschraenkung, die WIRKLICH noch gilt.
                # (3) "Pruefsumme nie wieder GEPRUEFT" - falsch seit Build
                #     626/680 (backup_pruefer.py Z. 359 und
                #     backup_wiederhersteller.py). Ersetzt durch das, was
                #     davon uebrig ist: sie wird nur auf VERLANGEN geprueft.
                # (4) "erscheint auch nicht unter den fehlenden" - falsch
                #     seit Build 617 (backup_executor._nachzuegler, Z. 682,
                #     aufgerufen Z. 278). GESTRICHEN, weil die Warnung zwei
                #     Zeilen darueber denselben Sachverhalt richtig darstellt.
                "DER RUECKWEG IST ERPROBT, ABER NICHT AM ERNSTFALL. "
                "'restore' ist seit Build 680 da und gefahren - gegen einen "
                "gebauten Wegwerf-Bestand unter /tmp, nicht gegen eine "
                "Fall-Datenbank aus dem Verfahren und nicht von einem "
                "Sicherungsmedium. UND ER TAUSCHT NICHT: die letzte Strecke, "
                "das Ersetzen der Datenbank, ist Handarbeit nach der "
                "ausgegebenen Anleitung und war damit noch nie Gegenstand "
                "eines Laufs. Wer sich auf den Rueckweg verlaesst, verlaesst "
                "sich auf einen Weg, dessen letztes Stueck ein Mensch geht.",
                "DIE PRUEFSUMME WIRD NUR AUF VERLANGEN GEGENGERECHNET. Sie "
                "wird bei jeder Sicherung erhoben (Build 354) und seit Build "
                "626 von 'pruefen --pruefsummen' und seit Build 680 von "
                "'restore' geprueft - aber in keinem der beiden Faelle von "
                "selbst: 'pruefen' ohne die Option liest die Dateien nicht "
                "ganz, und 'restore' faehrt nur, wenn jemand ihn faehrt. "
                "OHNE EINEN REGELMAESSIGEN LAUF MIT '--pruefsummen' altert "
                "eine Sicherung weiterhin unbeobachtet; ein Bitfehler auf "
                "dem Sicherungsmedium faellt dann erst im Ernstfall auf.",
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
        # Build 640 (Welle 4): geprueft an storage_admin.py Z. 25-33/60-75.
        # Dieses Werkzeug liest die MEISTEN Pfade von allen - es will ja
        # wissen, was der Bestand insgesamt belegt. JEDER hat einen
        # Rueckfallwert; das Werkzeug bricht nie ab, weil ein Pfad fehlt.
        konfiguration=(
            _k("paths.forensic_db_dir", "Verzeichnis der forensic_<uid>.db.",
               "./data/forensic/", "management/ops/storage_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)",
               "--forensic-dir"),
            _k("paths.evidence_db_dir", "Verzeichnis der evidence_<uid>.db.",
               "./data/evidence/", "management/ops/storage_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)",
               "--evidence-dir"),
            _k("paths.assets_db_dir", "Verzeichnis der assets_<uid>.db.",
               "./data/assets/", "management/ops/storage_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)",
               "--assets-dir"),
            _k("paths.coordinator_db", "Wird in der Groessenaufstellung "
               "mitgezaehlt.", "./data/coordinator.db",
               "management/ops/storage_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)"),
            _k("paths.default_db", "Wird in der Groessenaufstellung "
               "mitgezaehlt.", "./data/default.db",
               "management/ops/storage_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)"),
            _k("paths.templates_db", "Wird in der Groessenaufstellung "
               "mitgezaehlt.", "./data/templates.db",
               "management/ops/storage_admin.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.ops.storage_admin --forensic-dir ./data/forensic --evidence-dir ./data/evidence --assets-dir ./data/assets",
                     "Gibt die Speicheruebersicht je Verzeichnis aus und kennzeichnet fehlende ausdruecklich mit '[fehlt]'. Auf dem Wegwerf-Bestand: 'Speicheruebersicht (gesamt 0.0 B)'. Rueckgabewert 0.",
                     _GEPRUEFT_620),
            ),
            exit_codes=((0, "ausgegeben - AUCH bei ausgeloestem Platzalarm"),),
            warnungen=(
                "ES GIBT NUR DEN RUECKGABEWERT 0. Der Platzalarm und die Fremdforum-Kandidaten stehen ausschliesslich in der Ausgabe.",
                "ES OEFFNET KEINE EINZIGE DATENBANK. Die genannten Dateien werden nur VERMESSEN - die Zahlen sagen nichts ueber ihren Inhalt und nichts darueber, ob sie lesbar sind.",
                "Ein fehlendes Verzeichnis wird mit '[fehlt]' gekennzeichnet und nicht stillschweigend als 'leer' gefuehrt.",
                "Die Grenze fuer den Platzalarm laesst sich mit '--low-disk-pct' verschieben (Vorgabe 10 Prozent).",
            ),
        ),
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
        # Build 640 (Welle 4): geprueft an retention_admin.py Z. 28-47/71 und
        # retention.py Z. 41-42/113-125. Die Frist steht seit Build 640
        # AUSKOMMENTIERT in config.yaml - vorher war sie nur im Quelltext zu
        # finden, obwohl der Code sie liest (Befund der Erhebung).
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, aus der die Aufbewahrungskandidaten gelesen "
               "werden.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab.",
               "management/ops/retention_admin.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py (Build 644)",
               "--coordinator-db"),
            _k("retention.retention_days",
               "Aufbewahrungsfrist in Tagen. Was aelter ist, erscheint als "
               "KANDIDAT - geloescht wird nichts.",
               "730 Tage (zwei Jahre)",
               "management/ops/retention.py, retention_thresholds_from_config() Z. 113-125"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.ops.retention_admin --coordinator-db ./data/coordinator.db",
                     "Auf dem leeren Bestand: 'Aufbewahrung (Frist 730 Tage): 0 abgeschlossene Faelle, 0 Kandidat(en) zur Loeschpruefung' samt dem Hinweis, dass dies nur ein Pruefvorschlag ist. Rueckgabewert 0.",
                     _GEPRUEFT_620),
            ),
            exit_codes=((0, "ausgegeben - AUCH wenn Kandidaten gefunden wurden"),),
            warnungen=(
                "ES LOESCHT NICHTS UND KANN NICHTS LOESCHEN. Die Ausgabe ist ein Pruefvorschlag; das Loeschen ist eine auditierte Entscheidung und geht einen anderen Weg. Der Hinweis steht bei jedem Lauf dabei.",
                "ES GIBT NUR DEN RUECKGABEWERT 0. Gefundene Kandidaten stehen nur im Text bzw. in der JSON-Ausgabe.",
                "'--retention-days' UEBERSCHREIBT die Frist aus der Konfiguration vollstaendig - die ausgegebene Fristangabe ist deshalb mitzulesen.",
                "Es oeffnet die coordinator.db ausdruecklich nur lesend.",
            ),
        ),
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
        # Build 640 (Welle 4): geprueft an index_cli.py Z. 68-88/185-190.
        #
        # BEFUND, der in die Auskunft gehoert: Die beiden Pfade dieses
        # Werkzeugs werden UNTERSCHIEDLICH aufgeloest. Das Beweismittel-
        # Verzeichnis kommt aus config.yaml; der Ort des Suchindex NICHT - er
        # ist der fest verdrahtete Vorgabewert von '--index-db'
        # (STANDARD_INDEX_PFAD, Z. 69). Der SERVER dagegen liest fuer denselben
        # Index 'paths.search_index_db' (management_app.py, _search_index_pfad).
        # Wer den Index also per config.yaml verlegt, verlegt ihn NUR fuer den
        # Server - dieses Werkzeug arbeitet dann weiter am alten Ort, ohne dass
        # es das meldet.
        konfiguration=(
            _k("paths.evidence_db_dir",
               "Das Verzeichnis der evidence_<uid>.db, aus denen der Index "
               "gebaut wird.",
               "./data/evidence/ - und der Rueckfall wird protokolliert, nicht "
               "still genommen",
               "management/search/index_cli.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 646)", "--evidence-dir"),
        ),
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
        # Build 639: geprueft am Quelltext von maintenance/cli_config.py
        # (VORGABEN/SCHLUESSEL) und tools/maintenance.py (_add_common). Der
        # Abschnitt 'maintenance' in config.yaml ist AUSKOMMENTIERT
        # ausgeliefert; ohne Eintrag gilt jeweils der Vorgabewert.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, gegen die die Rechtepruefung laeuft. Der "
               "DATEINAME zaehlt mit - eine abweichend benannte Datei "
               "(etwa beim Parallelbetrieb zweier Bestaende) wird "
               "verwendet, wie sie hier steht.",
               "./data/coordinator.db", "maintenance/cli_config.py, "
               "SCHLUESSEL['coordinator_db']; aufgeloest in pfade_aufloesen()",
               "--coordinator-db"),
            _k("maintenance.data_dir",
               "Verzeichnis mit dem Wartungsverzeichnis und den "
               "Datenbanken.",
               "das Elternverzeichnis der oben aufgeloesten coordinator.db, "
               "sonst ./data",
               "maintenance/cli_config.py, pfade_aufloesen()", "--data-dir"),
            _k("maintenance.stale_seconds",
               "Ab wann ein Lebenszeichen als veraltet gilt. Ein Dienst "
               "mit aelterem Lebenszeichen wird als 'vermutlich tot, "
               "unbestaetigt' gefuehrt - NIE als in Ordnung. Auf einem "
               "traegen Netzlaufwerk eher erhoehen: ein zu knapper Wert "
               "erklaert lebende Dienste fuer tot.",
               "30 Sekunden", "maintenance/cli_config.py, VORGABEN['stale']",
               "--stale"),
            _k("maintenance.on_active",
               "Was mit laufenden Diensten geschieht, wenn das Fenster "
               "gesetzt wird: 'pause' oder 'beenden'. Ein anderer Wert wird "
               "beim Aufruf mit Klartext abgewiesen und NICHT ins Fenster "
               "geschrieben.",
               "pause", "tools/maintenance.py, cmd_enter (Pruefung des "
               "aufgeloesten Werts)", "--on-active"),
            _k("maintenance.min_build",
               "Versions-Waechter: Dienste mit kleinerer Buildnummer "
               "beenden sich beim Wiederaufnehmen selbst.",
               "0 (keine Anforderung)",
               "maintenance/cli_config.py, VORGABEN['min_build']",
               "--min-build"),
            _k("maintenance.ablauf_min",
               "Selbsttaetiger Ablauf des Fensters in Minuten. Als "
               "Standortvorgabe sinnvoll: ein vergessenes Fenster haelt "
               "den Betrieb sonst an, bis es jemand bemerkt.",
               "0 (laeuft nie von selbst ab)",
               "maintenance/cli_config.py, VORGABEN['ablauf_min']",
               "--ablauf-min"),
            _k("maintenance.wait_timeout_seconds",
               "Wie lange 'enter' auf die Bestaetigungen und den "
               "Sperrnachweis wartet.",
               "60 Sekunden",
               "maintenance/cli_config.py, VORGABEN['wait_timeout']",
               "--wait-timeout"),
            _k("maintenance.poll_seconds",
               "Abstand zweier Pruefungen in der Warteschleife. Das "
               "Werkzeug begrenzt den wirksamen Wert selbst auf 0,2 bis "
               "2,0 Sekunden.",
               "1,0 Sekunden", "maintenance/cli_config.py, VORGABEN['poll']; "
               "Begrenzung in tools/maintenance.py, cmd_enter", "--poll"),
        ),
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
        # Build 639: geprueft am Quelltext von tools/maintenance_kill.py
        # (main) und maintenance/cli_config.py. Dieses Werkzeug oeffnet keine
        # Datenbank fuer die Fachdaten, braucht aber dieselbe Rechtepruefung -
        # daher derselbe coordinator.db-Pfad.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, gegen die die Rechtepruefung laeuft. Ist sie "
               "gerade gesperrt, wird das Beenden NICHT blockiert - dies ist "
               "eine Wiederherstellung.",
               "./data/coordinator.db",
               "maintenance/cli_config.py, pfade_aufloesen(); Auswertung in "
               "maintenance/cli_support.pruefe_wartungsberechtigung()",
               "--coordinator-db"),
            _k("maintenance.data_dir",
               "Verzeichnis mit dem Wartungsverzeichnis, in dem die "
               "Anmeldungen der Dienste liegen.",
               "das Elternverzeichnis der oben aufgeloesten coordinator.db, "
               "sonst ./data",
               "maintenance/cli_config.py, pfade_aufloesen()", "--data-dir"),
            _k("maintenance.kill_wait_timeout_seconds",
               "Wie lange auf das Selbstbeenden der angesprochenen Dienste "
               "gewartet wird. Danach werden Nachzuegler NAMENTLICH gemeldet "
               "und der Aufruf endet mit 2.",
               "30 Sekunden",
               "maintenance/cli_config.py, VORGABEN['kill_wait_timeout']",
               "--wait-timeout"),
        ),
        tiefe=CliTiefe(
            exit_codes=((0, "erledigt"),
                        (1, "Aufruffehler"),
                        (2, "Nachzuegler - mindestens ein Dienst hat sich "
                            "nicht abgemeldet")),
            warnungen=(
                "'--all' nimmt ALLE Anmeldungen ohne Filter nach Rechner "
                "oder Fenster. Auf einem geteilten Laufwerk trifft es auch "
                "die Wartungsdienste anderer. ENTSCHAERFT IN BUILD 648 "
                "(Vorgang 1155da11), aber NICHT aufgehoben: Das Werkzeug "
                "listet die betroffenen Anmeldungen jetzt VOR der Wirkung "
                "auf - mit Rechnername und Fenster-Kennung - und fragt "
                "zurueck, sobald ein FREMDER Rechner dabei ist. Zu "
                "bestaetigen ist mit dem Wort 'FREMDE BEENDEN'; ein blosses "
                "'j' tippt man versehentlich, dieses Wort nicht. Einen "
                "Filter nach Rechner oder Fenster gibt es weiterhin nicht.",
                "'--ja' uebergeht die Rueckfrage - fuer Skripte. Die "
                "AUFLISTUNG bleibt dabei stehen: sie ist der Beleg im "
                "Sitzungsprotokoll darueber, wessen Lauf abgebrochen wurde.",
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
               "Zielwerkzeugs SELBST - nie mit dem eines Unterbefehls, auch "
               "dann nicht, wenn die Aufrufform oben einen nennt."),
            _b("suche", "lesend",
               "Volltextsuche ueber den Katalog. Rueckgabewert 1 bedeutet "
               "'kein Treffer' - eine Auskunft, kein Fehler."),
            _b("stand", "lesend",
               "Wie weit der Katalog ausgearbeitet ist."),
        ),
        hinweis="Der Katalog sagt, WOZU ein Werkzeug da ist. Die "
                "vollstaendige Liste der Optionen sagt das Werkzeug selbst - "
                "ein hier abgeschriebener Optionsblock wuerde veralten.",
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config'. Das ist hier eine
        # EIGENSCHAFT und kein Versaeumnis: Das Werkzeug liest nichts ausser dem
        # Katalog aus dem Paket und ist damit in jedem Betriebszustand gefahrlos
        # aufrufbar, auch mitten in einer Migration (Dateikopf tools/hilfe.py).
        konfiguration=KONFIG_KEINE,
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
               "[--nur-betrieb|--ohne-betrieb] [--ziel datei.html]",
        titel="Lektoratsfassung der Hilfe",
        gruppe="Betrieb und Sicherung",
        zweck="Alle Hilfetexte in EIN lesbares HTML schreiben - die "
              "Sichtkapitel, ihre Einblendtexte UND die Betriebskapitel zu "
              "den Werkzeugen -, damit sie gegengelesen werden koennen, ohne "
              "jedes Element einzeln anzuklicken.",
        art="lesend",
        datenbanken=("keine",),
        betrieb="Der Betrieb darf weiterlaufen; gelesen wird nur der "
                "Hilfebestand im Paket.",
        ausgabe="HTML-Datei (--ziel).",
        hinweis="Seit Build 623 stehen auch die Betriebskapitel in der "
                "Fassung - OHNE Rechtefilter, wie der ganze Rest. Die Sperre "
                "gilt fuer die ausgelieferte Hilfe unter /help, nicht fuer "
                "die Redaktion des Bestands.",
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config'. Wie 'hilfe':
        # es liest das Hilferegister aus dem Paket und schreibt eine HTML-Datei
        # nach '--ziel'. Keine Datenbank, kein Bestand.
        konfiguration=KONFIG_KEINE,
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/hilfe_lektorat.py --ziel ./lektorat.html",
                     "Schrieb die Lektoratsfassung der gesamten Hilfe in eine "
                     "Datei. Im Versuch: '43 Kapitel, 366 Popup-Texte, 65 "
                     "Betriebskapitel'. Rueckgabewert 0.",
                     _GEPRUEFT_623),
                _bsp("python tools/hilfe_lektorat.py --nur-betrieb "
                     "--ziel ./nur_werkzeuge.html",
                     "Nur die Werkzeugkapitel, ohne die Sichtkapitel. Im "
                     "Versuch: '0 Kapitel, 0 Popup-Texte, 65 "
                     "Betriebskapitel'. Rueckgabewert 0.",
                     _GEPRUEFT_623),
                _bsp("python tools/hilfe_lektorat.py --nur-betrieb "
                     "--ohne-betrieb",
                     "Wies die einander widersprechenden Schalter zurueck, "
                     "ohne eine Datei zu schreiben. Rueckgabewert 2.",
                     _GEPRUEFT_623),
                _bsp("python tools/hilfe_lektorat.py --nur gibtsnicht",
                     "Brach ab und nannte auf der Fehlerausgabe ALLE "
                     "verfassten Kapitelkennungen. Rueckgabewert 1.",
                     _GEPRUEFT_613),
            ),
            exit_codes=((0, "Datei geschrieben"),
                        (1, "in --nur steht eine Kennung, zu der es kein "
                            "verfasstes Kapitel gibt"),
                        (2, "einander ausschliessende Schalter "
                            "(--nur-betrieb zusammen mit --ohne-betrieb oder "
                            "mit --nur)")),
            warnungen=(
                "EIN TIPPFEHLER IN --nur BRICHT AB, statt eine leere Fassung "
                "zu schreiben. Das ist Absicht: eine stillschweigend leere "
                "Lektoratsfassung saehe aus wie 'nichts zu tun'.",
                "--nur GRENZT AUF SICHTEN EIN und laesst den Betriebsteil "
                "weg - so wie es auch die Shell-Texte weglaesst. Wer die "
                "Werkzeuge gegenlesen will, nimmt --nur-betrieb.",
                "WIDERSPRUECHLICHE SCHALTER WERDEN ZURUECKGEWIESEN und nicht "
                "ausgelegt. Eine Vorrangregel muesste man sich merken, und "
                "wer sich vertut, bekaeme wortlos eine Fassung, die er nicht "
                "wollte.",
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
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config'. Es
        # vergleicht Pruefsummen gegen MD5SUMS_Build<N>.txt und braucht dafuer
        # nur die build.json und den Bestand selbst.
        konfiguration=KONFIG_KEINE,
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
                "offen. Ein Backup legt das Werkzeug NICHT an. "
                "SEIT BUILD 612 SETZT DAS WERKZEUG DAS SELBST DURCH: es prueft vor "
                "dem scharfen Lauf, ob die betroffenen Dateien ruhig sind, bricht "
                "bei einer belegten Datei ohne Rueckfrage ab und faehrt ohne "
                "aktives Wartungsfenster nur nach Eingabe des Wortes 'OHNE "
                "WARTUNGSFENSTER' fort.",
        beleg=True,
        hinweis="DER EINZIGE Weg fuer die coordinator.db. tools/migrate-dbs.py "
                "verweist ausdruecklich hierher: zwei Wege, die dasselbe "
                "schreiben, waeren zwei Wahrheiten ueber den Beleg.",
        # Build 640 (Welle 4): geprueft an migrate.py Z. 49-62/72-75.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, auf die die Migrationen angewandt werden.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab. Bei einem Werkzeug, das das Schema "
               "aendert, waere ein erratener Pfad besonders teuer.",
               "management/migrate.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--coordinator-db"),
        ),
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
                "DIESER LAUF KOMMT ZUERST, wenn eine Umstellung ein neues "
                "Recht mitbringt: die Migration legt es an, erst danach "
                "verteilt 'rbac_admin migrate-grants' es an die Rollen. Die "
                "umgekehrte Reihenfolge hat am 12.08.2026 einen Bestand "
                "verriegelt (Vorgang 9c4e17b2); seit Build 711 weist "
                "'migrate-grants' sie ab.",
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
                "und jederzeit unbedenklich. "
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
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config'.
        # BEFUND MIT VORGESCHICHTE, der hierher gehoert: Der Dateikopf (Z. 278-295)
        # haelt fest, dass in Build 586 auf 'paths.migration_db' verwiesen wurde,
        # obwohl dieser Eintrag in der config.yaml nicht steht und die migration.db
        # auf dieser Anlage nie in Betrieb war - der Befehl brach ab. Massgeblich
        # ist das Register IN der jeweiligen Datenbank (schema_migrations), nicht
        # eine Steuerdatei daneben. Dieses Werkzeug liest deshalb bewusst nichts
        # aus der config.yaml.
        konfiguration=KONFIG_KEINE,
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
                "nur vorgeprueft und geplant. "
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
                "ist das verkettete Laufbuch. "
                "GEAENDERTES VERHALTEN SEIT BUILD 649 (Vorgang f51fd838): "
                "Eine benannte Datenbank, die es NICHT GIBT, ist jetzt ein "
                "Befund und kein Erfolg. Bis Build 648 haben die "
                "Pruefbausteine der Flotte eine fehlende Datei beim Oeffnen "
                "ANGELEGT und der Unversehrtheitspruefung anschliessend ein "
                "'ok' bescheinigt - die Flotte bestaetigte damit eine "
                "Datenbank, die sie selbst erzeugt hatte. Wer sich auf ein "
                "frueheres 'ok' zu einem Tippfehler im Pfad verlassen hat, "
                "hat es zu Recht nicht mehr: die Meldung lautet nun "
                "'unable to open database file'.",
        # Build 640 (Welle 4): geprueft an migration_fleet_admin.py Z. 59-94.
        # BEIDE Eintraege standen bis Build 640 in KEINER ausgelieferten
        # config.yaml, obwohl das Werkzeug sie liest - wer sie setzen wollte,
        # musste sie im Quelltext finden (Befund der Erhebung). Sie sind
        # seither dort auskommentiert aufgenommen.
        konfiguration=(
            _k("paths.migration_db",
               "Die Steuerdatenbank der Migrationsflotte.",
               "KEIN Vorgabewert - ohne Eintrag und ohne '--migration-db' "
               "bricht das Werkzeug ab. Absicht: eine Migration soll nicht "
               "gegen eine erfundene Steuerdatei laufen.",
               "management/migration_fleet/migration_fleet_admin.py, "
               "_resolve_migration_db_path() Z. 59-75", "--migration-db"),
            _k("paths.backup_dir",
               "Das Sicherungsziel VOR einer Migration. Nicht zu verwechseln "
               "mit 'backup.dest_dir' - das ist die laufende Datensicherung.",
               "KEIN Vorgabewert. Ohne Eintrag und ohne '--backup-dir' "
               "verweigert der Companion die Ausfuehrung ueber das Tor "
               "'KEIN_BACKUP_DIR': eine Migration ohne Sicherung findet nicht "
               "statt.",
               "management/migration_fleet/migration_fleet_admin.py, "
               "_resolve_backup_dir() Z. 78-94", "--backup-dir"),
        ),
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
        # Build 640 (Welle 5): geprueft an templates_db_status.py Z. 135-162.
        #
        # BESONDERHEIT, die man kennen muss: Dieses Werkzeug liest die
        # config.yaml WEDER ueber den ConfigLoader NOCH ueber einen
        # YAML-Parser. Es sucht zeilenweise nach der Zeichenfolge
        # 'templates_db:' und nimmt, was dahinter steht (Z. 135-147) - der
        # Kommentar nennt als Grund, ohne YAML-Abhaengigkeit auszukommen.
        #
        # WAS DARAUS FOLGT: Die Suche kennt keine Abschnitte. Stuende
        # 'templates_db:' irgendwo anders in der Datei, naehme das Werkzeug
        # diesen Wert. Auskommentierte Zeilen werden uebersprungen, die
        # Einrueckung wird nicht geprueft. Fuer eine reine Statusanzeige ist
        # das tragbar; ein Werkzeug, das schreibt, duerfte so nicht bauen.
        konfiguration=(
            _k("paths.templates_db",
               "Die Vorlagen-Datenbank, deren Migrationsstand angezeigt wird.",
               "./data/templates.db - dieses Werkzeug hat als einziges der "
               "Vorlagen-Werkzeuge einen Rueckfallwert und bricht nicht ab.",
               "management/templates_db_status.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 646)",
               "--templates-db"),
        ),
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
        # Build 640 (Welle 5): geprueft am Quelltext. Aufloesung:
        # Argument --templates-db > paths.templates_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.templates_db",
               "Die Vorlagen-Datenbank, auf die die Migration angewandt wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab.",
               "management/migrate_templates_module_key.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--templates-db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.migrate_templates_module_key --templates-db ./data/templates.db",
                     "Auf einem bereits migrierten Bestand: 'fertig: Spalte module_key bereits vorhanden; Index ok; Baustein legal.ki_uebersetzung geseedet.' Rueckgabewert 0 - der zweite Lauf ist unschaedlich.",
                     _GEPRUEFT_620),
            ),
            exit_codes=((0, "fertig ODER bereits vorhanden - beides meldet 0, der Unterschied steht nur im Text"), (2, "templates.db nicht gefunden"),),
            warnungen=(
                "ES LEGT KEINE SICHERUNG AN. Eine Kopie der templates.db ist VOR dem Lauf von Hand zu erstellen.",
                "DER RUECKGABEWERT UNTERSCHEIDET NICHT, ob etwas geaendert wurde oder ob alles schon so war. Wer wissen will, was geschehen ist, muss die Zeile lesen.",
                "Es ist wiederholbar aufrufbar: Spalte, Index und Baustein werden je einzeln geprueft, bevor sie angelegt werden.",
            ),
        ),
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
        # Build 640 (Welle 5): geprueft an migrate_templates_full_templates.py
        # Z. 414-425. BESONDERHEIT: Dieses Skript liest die config.yaml mit
        # 'yaml.safe_load' UNMITTELBAR und nicht ueber den ConfigLoader - der
        # Kommentar im Quelltext nennt als Grund, das Skript ohne den
        # Paket-Import lauffaehig zu halten. Folge fuer den Betrieb: Die Coded
        # Defaults des ConfigLoaders greifen hier NICHT. Fehlt der Eintrag in
        # der Datei, bricht es ab - auch wenn der ConfigLoader einen Wert
        # geliefert haette.
        konfiguration=(
            _k("paths.templates_db",
               "Die Vorlagen-Datenbank, auf die die Migration angewandt wird.",
               "KEIN Vorgabewert. Der Eintrag muss in der DATEI stehen; die "
               "Coded Defaults des ConfigLoaders greifen hier nicht.",
               "management/migrate_templates_full_templates.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 646)",
               "--templates-db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.migrate_templates_full_templates --templates-db ./data/templates.db --dry-run",
                     "TROCKENLAUF - das einzige der fuenf Skripte, das einen hat. Auf einem migrierten Bestand meldete er, welche Abfragen und Vorlagen er aufnehmen WUERDE, und schrieb nichts. Rueckgabewert 0.",
                     _GEPRUEFT_620),
            ),
            exit_codes=((0, "Lauf beendet - der Ergebnisbericht darunter beeinflusst den Wert NICHT"), (1, "die Tabelle 'placeholders' fehlt - dann ist zuerst migrate_templates_placeholders zu fahren"), (2, "templates.db nicht gefunden"),),
            warnungen=(
                "ES LEGT KEINE SICHERUNG AN. Eine Kopie der templates.db ist VOR dem Lauf von Hand zu erstellen. Der Trockenlauf ist der Ersatz - und er ist zu benutzen.",
                "ACHTUNG BEI DER REIHENFOLGE: Dieses Skript traegt die niedrigere Buildnummer (388), verlangt aber die Tabelle 'placeholders', die erst Build 489 anlegt. Auf einem Bestand, der noch vor 489 steht, bricht es ab. Die Reihenfolge nach Buildnummer ist hier also NICHT die Reihenfolge der Ausfuehrung.",
                "Vorhandene Abfragen und Vorlagen werden NICHT ueberschrieben - das Skript laesst sie stehen und nimmt nur Fehlendes auf.",
                "Der Ergebnisbericht am Ende ist zu lesen: er nennt, was aufgenommen wurde und was bereits bestand.",
            ),
        ),
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
        # Build 640 (Welle 5): geprueft am Quelltext. Aufloesung:
        # Argument --templates-db > paths.templates_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.templates_db",
               "Die Vorlagen-Datenbank, auf die die Migration angewandt wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab.",
               "management/migrate_templates_audit_check.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--templates-db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.migrate_templates_audit_check --templates-db ./data/templates.db",
                     "Auf einem bereits migrierten Bestand: 'CHECK bereits erweitert (template) - No-op.' Rueckgabewert 0.",
                     _GEPRUEFT_620),
            ),
            exit_codes=((0, "erweitert ODER bereits erweitert"), (1, "die Tabelle templates_audit_log fehlt - dann ist es vermutlich die falsche Datei"), (2, "templates.db nicht gefunden"), (3, "Wartungsvorbehalt - der Lauf wurde nicht ausgefuehrt; es wurde NICHTS geschrieben"),),
            warnungen=(
                "ES LEGT KEINE SICHERUNG AN. Eine Kopie der templates.db ist VOR dem Lauf von Hand zu erstellen. Bei diesem Skript wiegt das schwerer als bei den uebrigen: es BAUT DIE TABELLE NEU auf (anlegen, umkopieren, alte loeschen, umbenennen), weil eine CHECK-Bedingung in SQLite nicht nachtraeglich zu aendern ist.",
                "Fremdschluessel werden fuer den Umbau abgeschaltet und nicht nachgezogen. Verweise auf die Protokolltabelle waeren davon betroffen.",
                "Eine bereits vorhandene Tabelle mit dem Arbeitsnamen wird ungefragt entfernt.",
                "Ist die CHECK-Bedingung nach dem Umbau nicht wirksam, bricht das Skript mit einem Programmabbruch ab, statt einen halben Zustand zu hinterlassen.",
            ),
        ),
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
        # Build 640 (Welle 5): geprueft am Quelltext. Aufloesung:
        # Argument --templates-db > paths.templates_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.templates_db",
               "Die Vorlagen-Datenbank, auf die die Migration angewandt wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab.",
               "management/migrate_templates_placeholders.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--templates-db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.migrate_templates_placeholders --templates-db ./data/templates.db",
                     "Auf einem bereits migrierten Bestand: 'bereits migriert - No-op.' Rueckgabewert 0, und es wird keine Sicherung angelegt - die entsteht nur, wenn wirklich etwas zu tun ist.",
                     _GEPRUEFT_620),
            ),
            exit_codes=((0, "migriert ODER bereits migriert"), (1, "weder die alte noch die neue Tabelle vorhanden; ODER BEIDE vorhanden - dann ist der Zustand von Hand zu pruefen; ODER die Protokolltabelle fehlt"), (2, "templates.db nicht gefunden"), (3, "Wartungsvorbehalt - der Lauf wurde nicht ausgefuehrt; es wurde NICHTS geschrieben"),),
            warnungen=(
                "DAS EINZIGE DER FUENF SKRIPTE, DAS ETWAS LOESCHT: die alte Tabelle wird nach dem Umkopieren entfernt. Deshalb legt es als einziges VON SELBST eine Sicherung an ('.pre489.bak'), sofern nicht '--no-backup' gesetzt ist.",
                "SIND BEIDE TABELLEN VORHANDEN, bricht es ab und verlangt eine Pruefung von Hand. Das ist der Zustand nach einem Abbruch mitten im Lauf - und die richtige Antwort darauf ist nicht, es noch einmal zu versuchen.",
                "Die Zeilenzahl wird vor und nach dem Umkopieren verglichen; weicht sie ab, bricht der Lauf ab und rollt zurueck.",
                "'--no-backup' nimmt die einzige Sicherung heraus, die dieses Skript hat.",
            ),
        ),
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
        # Build 640 (Welle 5): geprueft am Quelltext. Aufloesung:
        # Argument --templates-db > paths.templates_db > Abbruch mit Klartext.
        konfiguration=(
            _k("paths.templates_db",
               "Die Vorlagen-Datenbank, auf die die Migration angewandt wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab.",
               "management/migrate_templates_ci.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--templates-db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python management/migrate_templates_ci.py --templates-db ./data/templates.db",
                     "Auf einem bereits migrierten Bestand: 'Spalte validation_ci vorhanden - No-op.' Rueckgabewert 0.",
                     _GEPRUEFT_620),
            ),
            exit_codes=((0, "ergaenzt ODER bereits vorhanden"), (2, "templates.db nicht gefunden"),),
            warnungen=(
                "Es legt VON SELBST eine Sicherung an ('.pre497.bak'), sofern nicht '--no-backup' gesetzt ist - und nur dann, wenn wirklich etwas zu tun ist.",
                "ES BAUT BEWUSST KEINE TABELLE NEU, sondern haengt nur eine Spalte an. Das ist der risikoaermste der fuenf Schritte.",
                "ES SETZT DEN STAND VON BUILD 489 VORAUS. Fehlt die Tabelle 'placeholders', bricht es mit einem Programmabbruch ab und nennt das zustaendige Skript.",
                "Nach dem Lauf wird die Datei mit einer Vollpruefung nachgeprueft.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="migrate_templates_blocktyp",
        pfad="management/migrate_templates_blocktyp.py",
        aufruf="python management/migrate_templates_blocktyp.py [--no-backup]",
        titel="templates.db: Blockart und Blockdaten an den Bausteinen",
        gruppe="Migration und Reparatur",
        zweck="Einem Baustein die Moeglichkeit geben, etwas anderes zu sein "
              "als ein Absatz - etwa eine Tabelle.",
        art="schreibend",
        datenbanken=("templates.db (schreibend)",),
        betrieb="Legt selbst eine Sicherungskopie an, sofern man sie nicht "
                "abschaltet, und prueft die Datei danach nach. Es wird KEINE "
                "vorhandene Zeile veraendert - nur zwei Spalten angehaengt.",
        hinweis="EINMALIGE Altmigration. Sind beide Spalten vorhanden, "
                "geschieht nichts.",
        konfiguration=(
            _k("paths.templates_db",
               "Die Vorlagen-Datenbank, auf die die Migration angewandt wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht das "
               "Werkzeug mit Klartext ab.",
               "management/migrate_templates_blocktyp.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--templates-db"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python management/migrate_templates_blocktyp.py --templates-db /tmp/mig655/templates.db",
                     "Erster Lauf: 'Backup: ...pre655.bak' und 'fertig: block_type und block_data hinzugefuegt (block_type Default \'paragraph\', block_data NULL = Inhalt steht in body), Audit-Zeile geschrieben.' Rueckgabewert 0.",
                     _GEPRUEFT_655),
                _bsp("python management/migrate_templates_blocktyp.py --templates-db /tmp/mig655/templates.db",
                     "Zweiter Lauf auf demselben Bestand: 'block_type und block_data vorhanden - No-op.' Kein Backup, keine Audit-Zeile. Rueckgabewert 0.",
                     _GEPRUEFT_655),
            ),
            exit_codes=((0, "ergaenzt ODER bereits vorhanden"), (2, "templates.db nicht gefunden"),),
            warnungen=(
                "ES VERAENDERT KEINE EINZIGE BESTANDSZEILE. Die neue Spalte 'block_data' bleibt leer, und leer bedeutet ausdruecklich 'der Inhalt steht wie bisher im Bausteintext'. Deshalb aendert sich auch kein Aenderungsdatum.",
                "Es legt VON SELBST eine Sicherung an ('.pre655.bak'), sofern nicht '--no-backup' gesetzt ist - und nur dann, wenn wirklich etwas zu tun ist.",
                "DIE ZULAESSIGEN BLOCKARTEN SIND FESTGESCHRIEBEN. Eine SIEBTE Blockart laesst sich nachtraeglich NICHT einfach ergaenzen: die Datenbank kann diese Festschreibung nicht aendern, es braucht dafuer einen Tabellen-Neubau und damit eine eigene Migration. Das war beim Bau bekannt und ist so entschieden worden.",
                "Nach dem Lauf wird die Datei mit einer Vollpruefung nachgeprueft.",
            ),
        ),
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
        # Build 640 (Welle 5): geprueft an repair_block_types.py Z. 183-192.
        # Liest die config.yaml unmittelbar mit 'yaml.safe_load', nicht ueber
        # den ConfigLoader - die Coded Defaults greifen hier also nicht.
        konfiguration=(
            _k("paths.evidence_db_dir",
               "Das Verzeichnis der evidence_<uid>.db, in denen die verlorenen "
               "Bausteinarten wiederhergestellt werden.",
               "KEIN Vorgabewert. Der Eintrag muss in der DATEI stehen; sonst "
               "bricht das Werkzeug mit 'paths.evidence_db_dir fehlt' ab.",
               "management/repair_block_types.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 646)",
               "--evidence-dir"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.repair_block_types --evidence-dir ./data/evidence",
                     "TROCKENLAUF - er ist die Vorgabe. Auf einem leeren Verzeichnis: 'Keine evidence_*.db in ... gefunden.' Rueckgabewert 0.",
                     _GEPRUEFT_620),
            ),
            exit_codes=((0, "Lauf beendet - AUCH wenn defekte Bloecke gefunden wurden"), (2, "das Verzeichnis wurde nicht gefunden"), (3, "'--apply' wurde ohne die Bestaetigung '--ja-backup-vorhanden' angegeben, ODER der Wartungsvorbehalt hat den Lauf abgewiesen (Stufe A seit Build 686) - in beiden Faellen wurde NICHTS geaendert"),),
            warnungen=(
                "DIE FUNDE AENDERN DEN RUECKGABEWERT NICHT. 'eindeutig defekt' und 'unklar' stehen nur im Text. Wer das Werkzeug in eine Ueberwachung haengt, muss die Ausgabe auswerten.",
                "ES FASST ERMITTLERDATEN AN. Deshalb verlangt '--apply' zusaetzlich die ausdrueckliche Bestaetigung, dass eine gepruefte Sicherung vorliegt - eine Sicherung legt es NICHT selbst an.",
                "ZWEIFELSFAELLE WERDEN GEMELDET UND NICHT ANGEFASST. Sie sind von Hand zu pruefen; das Werkzeug raet nicht.",
                "Ein zweiter Lauf findet die bereits reparierten Bloecke nicht mehr - er ist unschaedlich.",
            ),
        ),
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
        datenbanken=("default.db am Ziel (schreibend - seit Build 694 erst "
                     "am Ende, siehe Hinweis)",
                     "die Quell-Dateien (strikt lesend, mode=ro)"),
        betrieb="STUFE A - WARTUNGSFENSTER ERFORDERLICH (Analyse Build 609; "
                "die Gruende sind mit Build 694 fortgeschrieben). (1) Der "
                "letzte Handgriff ist ein os.replace() auf die default.db. "
                "Unter Windows scheitert der, solange eine andere Anwendung "
                "sie offen haelt - und der Auswertungsdienst haelt sie lesend "
                "offen. (2) Der ganze Lauf haengt an EINER Transaktion ueber "
                "alle Quellen; eine Quelle, die waehrend des Lesens "
                "beschrieben wird, ergibt ein Ergebnis, das niemandem "
                "auffaellt und trotzdem falsch ist. Ein Backup legt das "
                "Werkzeug nicht an. "
                "DER URSPRUENGLICHE ERSTE GRUND IST ENTFALLEN: bis Build 690 "
                "loeschte '--overwrite' die vorhandene Ziel-Datei VOR der "
                "Transaktion. Das tut es seit Build 694 nicht mehr. "
                "SEIT BUILD 612 SETZT DAS WERKZEUG DEN VORBEHALT SELBST "
                "DURCH: es prueft vor dem scharfen Lauf, ob die betroffenen "
                "Dateien ruhig sind, bricht bei einer belegten Datei ohne "
                "Rueckfrage ab und faehrt ohne aktives Wartungsfenster nur "
                "nach Eingabe des Wortes 'OHNE WARTUNGSFENSTER' fort.",
        hinweis="ERST BAUEN, DANN TAUSCHEN (seit Build 694, Vorgang "
                "1400b31f). Die Zusammenfuehrung entsteht unter einem "
                "Nebennamen '<ziel>.merge-tmp-<pid>' im Zielverzeichnis und "
                "kommt erst nach dem COMMIT per os.replace() an ihren Platz. "
                "EIN ABBRUCH LAESST DIE VORHANDENE default.db DAMIT "
                "UNBERUEHRT - und beim Erstlauf entsteht gar keine. "
                "Die Herkunft jeder uebernommenen Zeile wird im Ziel "
                "vermerkt.",
        # Build 640 (Welle 5): geprueft an consolidate_default_db.py Z. 56-70.
        # Build 694: am umgebauten Quelltext erneut geprueft - die Aufloesung
        # des Ziels ist unveraendert.
        konfiguration=(
            _k("paths.default_db",
               "Die gemeinsame Vorgaben-Datenbank, in die zusammengefuehrt "
               "wird.",
               "KEIN Vorgabewert - ohne Eintrag und ohne '--target' bricht das "
               "Werkzeug mit Klartext ab.",
               "management/consolidate_default_db.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 646)", "--target"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python -m management.consolidate_default_db "
                     "--target ./data/default.db --source ./a/default.db "
                     "--source ./b/default.db --overwrite",
                     "Bei einem HERBEIGEFUEHRTEN Abbruch in der zweiten "
                     "Quelle: die vorhandene default.db stand danach Zeile "
                     "fuer Zeile unveraendert an ihrem Platz, und es lag "
                     "keine Arbeitsdatei daneben. BIS BUILD 690 stand dort "
                     "eine LEERE, syntaktisch einwandfreie default.db - "
                     "gemessen 'assets=0 urls=0' statt vorher "
                     "'assets=1 urls=1'.",
                     _GEPRUEFT_694),
                _bsp("python -m management.consolidate_default_db "
                     "--target ./data/default.db --source ./a/default.db "
                     "--source ./b/default.db",
                     "Erstlauf ohne '--overwrite', ebenfalls mit "
                     "herbeigefuehrtem Abbruch: danach existierte GAR KEINE "
                     "Ziel-Datei. Bis Build 690 blieb auch hier eine leere "
                     "zurueck, und der naechste Versuch scheiterte dann an "
                     "'Ziel existiert bereits' - einer Meldung, die auf eine "
                     "ganz andere Ursache zeigt.",
                     _GEPRUEFT_694),
            ),
            exit_codes=((0, "erledigt, auch mit aufgeloesten Konflikten"),
                        (1, "harter Fehler - der ganze Lauf wurde "
                            "zurueckgerollt; die vorhandene default.db ist "
                            "unberuehrt geblieben"),
                        (3, "Wartungsvorbehalt - der Lauf wurde nicht ausgefuehrt; es wurde NICHTS geschrieben")),
            warnungen=(
                "SCHEITERT DER LETZTE HANDGRIFF, LIEGT DAS ERGEBNIS NEBENAN "
                "UND MUSS VON HAND EINGESAMMELT WERDEN. os.replace() kann "
                "fehlschlagen - unter Windows regelmaessig dann, wenn eine "
                "andere Anwendung die Ziel-Datei offen haelt. Die "
                "Zusammenfuehrung ist in dem Fall FERTIG und wird NICHT "
                "weggeworfen: sie bleibt unter '<ziel>.merge-tmp-<pid>' "
                "liegen, und die Meldung nennt Pfad und Handgriff. Die "
                "vorhandene default.db bleibt unberuehrt. WER DIE MELDUNG "
                "UEBERLIEST, haelt einen fehlgeschlagenen Lauf fuer einen "
                "verlorenen und faengt von vorn an.",
                "WAEHREND DES LAUFS LIEGEN BEIDE DATEIEN NEBENEINANDER - die "
                "alte default.db und die im Aufbau befindliche. Der "
                "Platzbedarf ist dadurch voruebergehend doppelt so hoch. Das "
                "ist der Preis dafuer, dass ein Abbruch nichts kostet.",
                "Der ganze Lauf haengt an EINER Transaktion. Es gibt keinen "
                "Wiederaufsetzpunkt - ein Abbruch bedeutet: von vorn.",
                "Ein Backup legt das Werkzeug nicht an. Es braucht seit "
                "Build 694 auch keines mehr, um einen Abbruch zu ueberstehen "
                "- wohl aber, um einen ERFOLGREICHEN Lauf zurueckzunehmen, "
                "der sich hinterher als falsch herausstellt.",
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
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config'.
        # BEMERKENSWERT, weil es ueberrascht: Dieses Werkzeug stempelt den
        # Journalmodus um, wertet aber 'db.journal_mode' aus der config.yaml NICHT
        # aus. Der Zielmodus kommt ausschliesslich aus '--to', das Verzeichnis aus
        # '--data-dir'. Das ist folgerichtig - es ist das Werkzeug fuer den
        # EINMALIGEN Umstempelvorgang, und der soll genau das tun, was auf der
        # Kommandozeile steht, und nicht das, was in einer Datei steht.
        konfiguration=KONFIG_KEINE,
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
                "reine Anzeige. "
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
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config'.
        # Die zu behandelnde Datenbank wird als Pfad uebergeben.
        konfiguration=KONFIG_KEINE,
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
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config'.
        # Es liest die Migrationsdateien aus dem Paket.
        konfiguration=KONFIG_KEINE,
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
        schluessel="pruefe_sort_index",
        pfad="tools/pruefe_sort_index.py",
        aufruf="python tools/pruefe_sort_index.py [--dir data/evidence] [--json]",
        titel="Voruntersuchung zu M004 (Bausteinreihenfolge)",
        gruppe="Migration und Reparatur",
        zweck="Vor dem Scharfschalten von M004 feststellen, welche "
              "Falldatenbanken den falschen Spaltentyp tragen, ob ihre Werte "
              "sauber wandelbar sind und ob sich die Reihenfolge der "
              "Bausteine ueberhaupt aendert.",
        art="lesend",
        datenbanken=("alle evidence_<uid>.db des Verzeichnisses "
                     "(lesend, mode=ro)",),
        betrieb="Vor jedem 'migrate-dbs.py --apply' aufzurufen; auch im "
                "Produktivbetrieb unbedenklich, da es keinen Schreibpfad hat.",
        hinweis="Rueckgabewert 3 heisst NICHT 'Fehler', sondern 'zu "
                "migrieren, aber jemand muss hinsehen': ein Wert ist keine "
                "kanonische Ganzzahl und wuerde von M004 per CAST "
                "uebernommen. Eine Datei, deren Reihenfolge sich aendert, "
                "hatte bereits gefertigte Vermerke moeglicherweise in "
                "falscher Ordnung - diese sind nachzusehen.",
        konfiguration=KONFIG_KEINE,
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/pruefe_sort_index.py --dir ./data/evidence",
                     "Nennt je Falldatenbank Spaltentyp, Zeilenzahl, ob die "
                     "Reihenfolge sich aendert und jeden Zweifelsfall mit "
                     "block_id und Rohwert. Dateien, die nicht die Form "
                     "evidence_<uid>.db tragen, werden gezaehlt und genannt, "
                     "nicht stillschweigend uebergangen."),
                _bsp("python tools/pruefe_sort_index.py --json "
                     "> phase0_befund.json",
                     "Maschinenlesbar fuer die Ablage als Phase-0-Artefakt "
                     "nach dem Datenmigrationsleitfaden."),
            ),
            exit_codes=((0, "nichts zu tun - keine Datei traegt TEXT"),
                        (1, "Aufruffehler (Verzeichnis fehlt)"),
                        (2, "Migration noetig, alle Werte kanonisch"),
                        (3, "Migration noetig, aber mindestens ein Wert ist "
                            "keine kanonische Ganzzahl"),
                        (4, "mindestens eine Datei war nicht lesbar - der "
                            "Befund ist unvollstaendig")),
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
        betrieb="Ausserhalb des Betriebs, auf einer Kopie. WARTUNGSSTUFE B "
                "mit SPERRLISTE (Build 686): Zeigt der uebergebene Pfad auf "
                "die in config.yaml eingetragene coordinator.db, bricht das "
                "Werkzeug mit 3 ab und oeffnet die Datei nicht einmal. Ein "
                "Wartungsfenster verlangt es NICHT - fuer eine Wegwerfkopie "
                "waere das Reibung ohne Schutzgewinn.",
        hinweis="ES GIBT KEINE EINGEBAUTE PRUEFUNG, dass die uebergebene "
                "Datei wirklich eine Kopie ist - der Schutz ist "
                "organisatorisch. '--seed' fuellt Testzeilen ein und gehoert "
                "NICHT auf eine Kopie mit echten Daten.",
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config'.
        # Ein Machbarkeitsnachweis gegen einen uebergebenen Wegwerf-Bestand.
        konfiguration=(
            _k("paths.coordinator_db",
               "NUR fuer die Sperrliste (Build 686): der Eintrag sagt, "
               "welche Datei dieses Werkzeug NIEMALS anfassen darf. Es "
               "liest ihn nicht, um irgendetwas zu oeffnen. Fehlt die "
               "config.yaml oder ist sie unlesbar, greift die Sperre "
               "nicht - das ist Absicht: das Werkzeug laeuft oft "
               "ausserhalb der Anlage auf einer Wegwerfkopie.",
               "(kein Vorgabewert - ohne Eintrag keine Sperre)",
               "tools/poc_m019_weg_a.py, _produktivpfad()"),
        ),
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/poc_m019_weg_a.py /tmp/kopie.db",
                     "Auf einer Kopie, die M019 BEREITS hinter sich hat: 'FEHLER: no such column: user_id -> ROLLBACK. Weg A NICHT gangbar.' Rueckgabewert 1. Das ist kein Programmfehler, sondern die zutreffende Auskunft - und es belegt zugleich, dass ein zweiter Lauf auf derselben Datei nicht funktioniert.",
                     _GEPRUEFT_620),
            ),
            exit_codes=((0, "BEFUND: Weg A ist gangbar"), (1, "BEFUND: Weg A ist nicht gangbar, es braucht den Rebuild - ODER ein Programmabbruch. Beides meldet 1"), (2, "Aufruf ohne Pfadangabe"),),
            warnungen=(
                "ES SCHREIBT IMMER. Es gibt keinen Trockenlauf, und es prueft NICHT nach, ob die angegebene Datei wirklich eine Kopie ist. Der Schutz davor ist rein organisatorisch - der Pfad ist vor der Eingabetaste zu lesen.",
                "ES IST NICHT WIEDERHOLBAR. Nach einem gelungenen Lauf gibt es die alte Spalte nicht mehr; ein zweiter Lauf schlaegt fehl. Fuer eine weitere Probe braucht es eine frische Kopie.",
                "'--seed' schreibt Testzeilen und gehoert NIE auf eine Kopie mit echten Daten.",
                "Der Rueckgabewert 1 hat zwei Bedeutungen - Befund oder Abbruch. Welche zutrifft, steht im Text darueber.",
            ),
        ),
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
        # Build 640 (Welle 6): geprueft an tools/diag_limitation_laufzeit.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645).
        # Alle drei Pfade sind ausfallsicher: ist die config.yaml nicht
        # lesbar, gilt still der Vorgabewert ('except Exception: return
        # vorgabe'). Bei einer MESSUNG ist das vertretbar - sie veraendert
        # nichts und meldet ohnehin, welchen Bestand sie angesehen hat.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, aus der die Faelle fuer die Messung stammen.",
               "./data/coordinator.db", "tools/diag_limitation_laufzeit.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)", "--coordinator-db"),
            _k("paths.forensic_db_dir",
               "Verzeichnis der forensic_<uid>.db.", "./data/forensic/",
               "tools/diag_limitation_laufzeit.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)", "--forensic-dir"),
            _k("paths.evidence_db_dir",
               "Verzeichnis der evidence_<uid>.db.", "./data/evidence/",
               "tools/diag_limitation_laufzeit.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)", "--evidence-dir"),
        ),
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
        schluessel="diag_backup_verdraengung",
        pfad="tools/diag_backup_verdraengung.py",
        aufruf="python tools/diag_backup_verdraengung.py "
               "--arbeitsverzeichnis VERZ [--mit-abbruch] [--behalten]",
        titel="Nachpruefung: verdraengt eine defekte Sicherung eine gute?",
        gruppe="Diagnose",
        zweck="Prueft nachvollziehbar nach, ob eine defekte Sicherungskopie "
              "eine brauchbare Generation aus der Aufbewahrung verdraengen "
              "kann (Vorgang 651e6d84).",
        art="lesend",
        datenbanken=("keine - das Werkzeug legt sich seinen eigenen "
                     "Wegwerf-Bestand an und ruehrt den Bestand nicht an",),
        betrieb="Im laufenden Betrieb gefahrlos. Es arbeitet ausschliesslich "
                "in einem Verzeichnis, das es selbst anlegt; ein vorhandenes, "
                "nicht leeres Zielverzeichnis wird abgelehnt.",
        hinweis="DIE SELBSTPROBE IST DER GRUND, DEM ERGEBNIS ZU TRAUEN. Vor "
                "den eigentlichen Proben faehrt das Werkzeug denselben Fall "
                "gegen den Stand VOR Build 625 und verlangt, dass der Fehler "
                "sich dort ZEIGT. Tut er es nicht, ist die Nachpruefung blind "
                "und meldet das, statt Entwarnung zu geben. Ein 'BESTANDEN' "
                "von einer Probe, die nichts messen kann, ist schlimmer als "
                "kein Ergebnis - es beendet die Suche.",
        konfiguration=KONFIG_KEINE,
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/diag_backup_verdraengung.py "
                     "--arbeitsverzeichnis /tmp/p651",
                     "Faehrt die Selbstprobe und die beiden schnellen Proben. "
                     "Im Versuch: Selbstprobe 'gute ueberlebt 2 von 3, defekte "
                     "zaehlt JA' (der alte Stand faellt also auf), Probe A "
                     "'3 von 3, defekte zaehlt NEIN, 1 beiseitegelegt', Probe "
                     "B 'verbleibend 3, aelteste geloescht'. Probe C wurde "
                     "NICHT gefahren und steht namentlich im Schlussbericht. "
                     "Rueckgabewert 0.",
                     _GEPRUEFT_642),
                _bsp("python tools/diag_backup_verdraengung.py "
                     "--arbeitsverzeichnis /tmp/p651b --mit-abbruch",
                     "Zusaetzlich der echte Abbruchrest. Im Versuch: 253 MB "
                     "Wegwerf-Quelle, das 'VACUUM INTO' nach 5.718.016 "
                     "geschriebenen Byte abgeschossen; daneben lag ein "
                     "'-journal'. Die Teildatei zaehlte danach NICHT als "
                     "Generation, alle drei guten ueberlebten. Rueckgabewert 0.",
                     _GEPRUEFT_642),
            ),
            exit_codes=((0, "alle GEFAHRENEN Proben bestanden - der Vorgang "
                            "ist behoben"),
                        (1, "DER ERNSTFALL: mindestens eine Probe hat den "
                            "Vorgang nachgewiesen, oder die Selbstprobe hat "
                            "gezeigt, dass die Nachpruefung blind ist"),
                        (2, "Aufruffehler oder die Vorbereitung ist "
                            "gescheitert - dann ist NICHTS geprueft")),
            warnungen=(
                "'--mit-abbruch' legt eine Wegwerf-Datenbank von rund 250 MB "
                "an und kopiert sie teilweise. Auf einem knappen Laufwerk "
                "vorher den Platz ansehen.",
                "Ist die Platte sehr schnell, kann das 'VACUUM INTO' fertig "
                "sein, bevor der Abbruch greift. Das Werkzeug meldet das "
                "dann als NICHT GEFAHREN - nicht als bestanden. Abhilfe: "
                "ABBRUCH_QUELLE_MB im Kopf des Werkzeugs erhoehen.",
                "Das Werkzeug prueft die AUFBEWAHRUNG. Es sagt nichts "
                "darueber, ob die Sicherungen des Bestandes brauchbar sind - "
                "dafuer ist 'backup_admin pruefen' da.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="pruefe_profilerfassung",
        pfad="tools/pruefe_profilerfassung.py",
        aufruf="python tools/pruefe_profilerfassung.py "
               "(--verzeichnis VERZ | --forensic-db DATEI) [--fehlende N] "
               "[--csv DATEI]",
        titel="Fehlende Profilseiten je Fall auszaehlen",
        gruppe="Diagnose",
        zweck="Prueft fallweise, ob zu den erfassten Benutzern auch die "
              "Profilseiten im Bestand liegen, und nennt die Faelle, die neu "
              "erfasst werden muessen (Vorgang 90e7c214).",
        art="lesend",
        datenbanken=("forensic_<uid>.db (lesend, mode=ro)",),
        betrieb="Im laufenden Betrieb gefahrlos. Ausschliesslich lesend ueber "
                "'mode=ro'; kein PRAGMA, keine TEMP-Sicht, keine Kopie. Die "
                "evidence_<uid>.db wird nicht geoeffnet.",
        ausgabe="pruefe_profilerfassung.log im aktuellen Verzeichnis; mit "
                "'--csv' zusaetzlich eine Liste der betroffenen Faelle "
                "(subject_id, Benutzername, Fehlmenge).",
        hinweis="WAS DAS WERKZEUG NICHT SAGT: ob eine Nacherfassung noch "
                "moeglich ist. Das Forum ist beschlagnahmt und nicht "
                "erreichbar; die Auskunft lautet allein, WO etwas fehlt. Der "
                "Anlass: am 05.08.2026 standen in forensic_1488.db 1.000 "
                "Profil-Erfassungsziele 12 Profilseiten gegenueber - und alle "
                "zwoelf gehoerten dem Beschuldigten selbst. Die Profilseite "
                "ist die Seitenart, die fuer die Zuordnung eines Kontos zu "
                "einer natuerlichen Person am meisten hergibt.",
        konfiguration=KONFIG_KEINE,
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/pruefe_profilerfassung.py "
                     "--verzeichnis ./data/forensic",
                     "Geht alle 'forensic_*.db' des Verzeichnisses durch und "
                     "stellt je Fall Ziele, vorhandene und fehlende "
                     "Profilseiten gegenueber. Im Versuch gegen einen "
                     "gebauten Bestand: 41 Ziele, 1 vorhanden, 40 fehlend, "
                     "Befund BETROFFEN, am Ende subject_id und Benutzername "
                     "zum Uebernehmen. Rueckgabewert 1.",
                     _GEPRUEFT_675),
                _bsp("python tools/pruefe_profilerfassung.py "
                     "--forensic-db ./data/forensic/forensic_1488.db "
                     "--fehlende 20 --csv betroffen.csv",
                     "Nur ein Fall, dazu die ersten 20 fehlenden "
                     "Benutzerkennungen und eine CSV-Liste der betroffenen "
                     "Faelle mit Semikolon als Trenner.",
                     _GEPRUEFT_675),
            ),
            exit_codes=((0, "kein Fall betroffen"),
                        (1, "mindestens ein Fall betroffen - das ist ein "
                            "BEFUND und kein Fehler"),
                        (2, "Aufruf- oder Zugriffsfehler: Verzeichnis oder "
                            "Datei fehlt, oder es liegt keine "
                            "'forensic_*.db' darin")),
            warnungen=(
                "DIE KENNUNG STEHT NICHT IMMER DIREKT HINTER "
                "'profile.php?'. Im Bestand kommen beide Formen vor: "
                "'profile.php?id=1488' und "
                "'profile.php?section=essentials&edit&id=1488'. Das Werkzeug "
                "sucht deshalb 'id=' irgendwo in der Abfragezeichenkette. Wer "
                "eine eigene Auswertung schreibt und nur die erste Form "
                "sucht, meldet eine Fehlmenge, die es nicht gibt (Testfall "
                "PP03).",
                "Ein Erfassungsziel ohne Benutzerkennung (actor_user_id NULL) "
                "wird NICHT mitgezaehlt - ihm laesst sich keine Profilseite "
                "zuordnen. Im Bestand gab es am 05.08.2026 genau eines "
                "davon, ein 'pgp_probe'-Ziel.",
                "Fehlt die Tabelle 'page_aliases', wird ohne sie gezaehlt und "
                "das im Protokoll benannt. Die Fehlmenge faellt dann "
                "moeglicherweise zu gross aus.",
            ),
        ),
    ),
    CliEintrag(
        schluessel="diag_spurensequenz_luecken",
        pfad="tools/diag_spurensequenz_luecken.py",
        aufruf="python tools/diag_spurensequenz_luecken.py "
               "--forensic-db PFAD [--json DATEI] [--ohne-selbstprobe] "
               "[--nachweis]",
        titel="Luecken der Spurensequenz auszaehlen",
        gruppe="Diagnose",
        zweck="Zaehlt aus, wie viele erfasste Seiten die Spurensequenz "
              "uebergeht (Vorgang 2f1044b9). Mit '--nachweis' stellt es der "
              "Fassung bis Build 676 die Fassung ab Build 677 gegenueber und "
              "weist aus, wie viele Seiten die Behebung zurueckgewinnt.",
        art="lesend",
        datenbanken=("forensic_<uid>.db (lesend, mode=ro)",),
        betrieb="Im laufenden Betrieb gefahrlos. Die Datei wird ausschliesslich "
                "ueber 'mode=ro' geoeffnet; es wird kein PRAGMA gesetzt und "
                "keine TEMP-VIEW angelegt. Die evidence_<uid>.db wird gar "
                "nicht erst geoeffnet - 'blob_lookup' ist eine Sicht allein "
                "ueber fdb.pages und fdb.page_aliases.",
        ausgabe="diag_spurensequenz_luecken.log im aktuellen Verzeichnis; "
                "mit '--json' zusaetzlich ein maschinenlesbarer Befund.",
        hinweis="DIE SELBSTPROBE IST DER GRUND, DEM ERGEBNIS ZU TRAUEN. Vor "
                "der Messung baut das Werkzeug einen Bestand mit BEKANNTER "
                "Luecke und verlangt, dass die Messung sie findet. Faellt "
                "die Probe, wird KEIN Ergebnis ausgewiesen (Rueckgabewert 3) "
                "- ein 'keine Luecken' von einer blinden Messung beendet die "
                "Suche, statt sie zu fuehren. Beim Bauen hat genau diese "
                "Probe eine falsche Erwartung des Verfassers widerlegt.",
        konfiguration=KONFIG_KEINE,
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python tools/diag_spurensequenz_luecken.py "
                     "--forensic-db /tmp/probe_forensic.db",
                     "Selbstprobe bestanden, danach die Messung. Im Versuch "
                     "gegen einen gebauten Bestand mit 10 Seiten und 7 "
                     "Erfassungszielen: 5 Eintraege in der Sequenz, 10 "
                     "erreichbare SEITEN, 5 uebergangene Seiten - alle fuenf "
                     "mit Seitenteil. Zusaetzlich ausgewiesen: Gruppe "
                     "'profile' leer und ein Erfassungsziel ohne jede "
                     "passende Seite. Rueckgabewert 1.",
                     _GEPRUEFT_672),
                _bsp("python tools/diag_spurensequenz_luecken.py "
                     "--forensic-db /tmp/probe_forensic.db --json befund.json",
                     "Wie oben, zusaetzlich wird der vollstaendige Befund "
                     "als JSON abgelegt - noetig, weil die Konsole nur die "
                     "ersten 15 uebergangenen Seiten nennt. Der Befund traegt "
                     "je Eintrag die page_id, sodass sich Zweitadressen "
                     "derselben Seite nachtraeglich zusammenlegen lassen.",
                     _GEPRUEFT_672),
                _bsp("python tools/diag_spurensequenz_luecken.py "
                     "--forensic-db /tmp/probe_forensic.db --nachweis",
                     "Wie oben, zusaetzlich der Abschnitt NACHWEIS DER "
                     "BEHEBUNG: Seiten in der Sequenz vorher und nachher, "
                     "die Zahl der zurueckgewonnenen Seiten und - namentlich "
                     "- die Seiten, die die neue Fassung BEWUSST nicht mehr "
                     "fuehrt, weil sie nur ueber eine fremde Kennung oder "
                     "ueber ein Ziel ohne Kennung erreichbar waren. Der "
                     "Rueckgabewert richtet sich weiterhin nach der Messung "
                     "der alten Fassung; '--nachweis' aendert ihn nicht.",
                     _GEPRUEFT_677),
            ),
            exit_codes=((0, "gelaufen, KEINE Luecke gefunden"),
                        (1, "gelaufen, LUECKE gefunden - das ist ein BEFUND "
                            "und kein Fehler"),
                        (2, "Aufruf- oder Zugriffsfehler: Datei fehlt, ist "
                            "nicht lesbar, oder eine erwartete Tabelle fehlt"),
                        (3, "die Selbstprobe ist gefallen - die Messung ist "
                            "blind, es wird KEIN Ergebnis ausgewiesen")),
            warnungen=(
                "DIE ZAHL IST EINE OBERGRENZE, KEIN ENDSTAND. Die "
                "Trefferpruefung ist eine Teilzeichenkette - 'sid=2' passt "
                "auch auf 'sid=202313'. Solche Fremdtreffer stehen im Bericht "
                "unter MEHRDEUTIGE MUSTER und koennen die Zahl der "
                "erreichbaren Seiten nach oben verfaelschen. In Build 671 "
                "stand hier noch, die Zahl stehe fest; der erste Lauf gegen "
                "einen echten Bestand hat das widerlegt.",
                "'LIMIT 1 ohne ORDER BY' hat keine zugesicherte Reihenfolge. "
                "WELCHE einzelne Seite je Erfassungsziel in der Sequenz "
                "landet, kann daher von diesem Nachbau abweichen. Gemessen am "
                "05.08.2026: 6346 Sequenzeintraege hier gegen 6347 im "
                "laufenden Server - eine Abweichung von genau einem Eintrag.",
                "GEZAEHLT WIRD NACH SEITEN (page_id), NICHT NACH URLs. Eine "
                "Seite traegt oft mehrere Adressen: eine Sprungmarke "
                "('...#p4711') und einen zweiten Pfad ('/forum/beginner/...'), "
                "beide in page_aliases. Build 671 zaehlte URLs und meldete "
                "dadurch 73.796 statt rund 2.000 uebergangener Seiten. Wer "
                "eine alte Ausgabe vor sich hat, erkennt sie an der Zeile "
                "'Verschiedene erreichbare URLs'.",
                "Die TYPE_MAP im Werkzeug ist eine Abschrift aus "
                "db/forensic_db.py. Wird sie dort geaendert, misst das "
                "Werkzeug etwas anderes als das, was laeuft. Der Testfall "
                "SL05 in tests/test_diag_spurensequenz_luecken.py schlaegt "
                "dann an.",
                "'--ohne-selbstprobe' schaltet die einzige Absicherung ab. "
                "Der Lauf sagt das dann auch - aber sein Ergebnis ist ohne "
                "Gewaehr.",
                "Fehlt die Tabelle 'page_aliases', wird ohne sie gemessen "
                "und das im Protokoll benannt. Die Zahlen sind dann "
                "unvollstaendig, nicht falsch.",
                "'--nachweis' rechnet mit einer ZWEITEN Abschrift des "
                "Produktivcodes (messe_neu). Sie waehlt je Seite die "
                "kuerzeste Adresse, waehrend get_trace_sequence() ab Build "
                "677 die KANONISCHE waehlt - dieses Werkzeug liest pages und "
                "page_aliases zusammengeschuettet und kennt die Herkunft "
                "einer Adresse nicht mehr. Fuer die Zaehlung nach page_id ist "
                "das ohne Belang; EINZELNE Adressen aus diesem Abschnitt "
                "duerfen aber nicht zeichengenau mit der Ausgabe des "
                "laufenden Servers verglichen werden.",
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
        # Build 640 (Welle 6): geprueft an tools/diag_matrix_laufzeit.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645).
        # Alle drei Pfade sind ausfallsicher: ist die config.yaml nicht
        # lesbar, gilt still der Vorgabewert ('except Exception: return
        # vorgabe'). Bei einer MESSUNG ist das vertretbar - sie veraendert
        # nichts und meldet ohnehin, welchen Bestand sie angesehen hat.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, aus der die Faelle fuer die Messung stammen.",
               "./data/coordinator.db", "tools/diag_matrix_laufzeit.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)", "--coordinator-db"),
            _k("paths.forensic_db_dir",
               "Verzeichnis der forensic_<uid>.db.", "./data/forensic/",
               "tools/diag_matrix_laufzeit.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)", "--forensic-dir"),
            _k("paths.evidence_db_dir",
               "Verzeichnis der evidence_<uid>.db.", "./data/evidence/",
               "tools/diag_matrix_laufzeit.py; die Aufloesung selbst in core/werkzeug_konfig.py (Build 645)", "--evidence-dir"),
        ),
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
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config'.
        # Die Diagnose misst ein VERZEICHNIS, das uebergeben wird - sie soll
        # gerade nicht dorthin sehen, wo der Bestand liegt.
        konfiguration=KONFIG_KEINE,
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
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config'.
        # Wie die erste Fassung: das zu messende Verzeichnis wird uebergeben.
        konfiguration=KONFIG_KEINE,
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
                "BEWEISMITTEL-DATENBANK AN - eine je Testfall, nacheinander. "
                "Seit Build 682 liegen sie in einem eigenen Unterverzeichnis "
                "'_probe2_<pid>' neben der Datei und tragen Rechte NUR FUER "
                "DIE AUFRUFENDE PERSON (0600 statt 0666). Bis Build 681 lagen "
                "sie zwischen den echten Datenbanken und waren fuer JEDEN "
                "Benutzer les- und beschreibbar (Vorgang 33b859f9).",
                "ZUR WIRKUNG UNTER WINDOWS, weil sie oft falsch erwartet "
                "wird: os.chmod setzt dort ausschliesslich das "
                "Schreibschutz-Merkmal, alle uebrigen Bits werden ignoriert. "
                "Auf NTFS bewirkten 0666 und 0600 also DASSELBE; die Rechte "
                "der Kopie ergeben sich aus der Vererbung des "
                "Zielverzeichnisses. Der behobene Befund wog auf der "
                "Produktions-VM damit leichter als auf einem POSIX-System - "
                "was bleibt, ist der Rest bei hartem Abbruch.",
                "Platzbedarf und I/O-Last betragen das SIEBENFACHE der "
                "gewaehlten Datei (immer nur eine Kopie gleichzeitig, aber "
                "siebenmal nacheinander). Der Kopiervorgang blockiert ohne "
                "Fortschrittsanzeige.",
                "BEI EINEM HARTEN ABBRUCH BLEIBT DIE KOPIE LIEGEN - daran "
                "aendert Build 682 nichts, wohl aber daran, was man damit "
                "tut: sie liegt in '_probe2_<pid>' und ist damit als Rest "
                "ERKENNBAR, der naechste Lauf BENENNT sie beim Start, und das "
                "Schwesterwerkzeug diag_sqlite_netdrive uebergeht sie jetzt "
                "(Ausschluss ueber jeden Pfadteil, der mit '_probe' beginnt) "
                "und sagt, dass es sie uebergeht. Geloescht wird ein Rest "
                "NICHT selbsttaetig: eine vollstaendige Kopie eines "
                "Beweismittels raeumt man nicht nebenbei weg, ohne dass "
                "jemand davon weiss.",
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
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config'.
        # Die zu untersuchenden Datenbanken werden als Pfade uebergeben.
        konfiguration=KONFIG_KEINE,
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
        # Build 657: der Start prueft seit diesem Build den Schemastand ALLER
        # Datenbanken des Katalogs, nicht mehr nur den der coordinator.db.
        # Geoeffnet wird dabei ausschliesslich nur-lesend.
        datenbanken=("coordinator.db (lesend)",
                     "templates.db (nur-lesend, Schemastand)",
                     "evidence_<uid>.db, assets_<uid>.db (nur-lesend, "
                     "Schemastand, zusammengefasst)"),
        betrieb="Der Normalbetrieb. Mit --maintenance ist der Start NUR bei "
                "aktivem Wartungsfenster erlaubt. Beim Start wird gemeldet, "
                "ob alle Datenbanken auf dem erwarteten Stand sind; ein "
                "Rueckstand haelt den Start NICHT an, wird aber deutlich "
                "benannt.",
        hinweis="Keine Schreibpfade: der Dienst liest. Er migriert auch "
                "nicht - er sagt nur, welcher Befehl es taete.",
        # Build 640 (Welle 6): geprueft an management.py Z. 48-86.
        konfiguration=(
            _k("paths.coordinator_db",
               "Die Datenbank, mit der der Verwaltungsserver arbeitet.",
               "KEIN Vorgabewert - ohne Eintrag und ohne Argument bricht der "
               "Start mit Klartext ab.",
               "management.py, _resolve_db_path(); die Aufloesung selbst in core/werkzeug_konfig.py, db_pfad() (Build 643)", "--coordinator-db"),
        ),
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
                "BEIM START WIRD DER SCHEMASTAND ALLER DATENBANKEN GEMELDET "
                "(Build 657). Ein Rueckstand haelt den Start nicht an - "
                "betroffen waeren einzelne Sichten, nicht der Betrieb. Die "
                "Meldung nennt den Pfad und den Befehl, der ihn behebt. "
                "ANLASS war der Vorfall vom 2026-08-02: eine nicht "
                "angewandte Migration der templates.db liess eine Sicht mit "
                "HTTP 500 ausfallen, und niemand sagte etwas.",
                "DER DIENST MIGRIERT NICHT SELBST. Das Anwenden bleibt eine "
                "bewusste, protokollierte Handlung - bitte den in der "
                "Meldung genannten Befehl benutzen und KEINEN Pfad von Hand "
                "eintippen: der Befehl holt ihn aus config.yaml.",
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
        # Build 640 (Welle 6): geprueft an main.py Z. 330-380/570-590/750-870
        # sowie an den Bauteilen, die main.py mit der geladenen Konfiguration
        # versorgt (core/mode_resolver.py, core/logger.py, core/hosts_manager.py,
        # core/browser_launcher.py, db/journal_policy.py, core/validation_rules.py).
        #
        # DIES IST DER GROESSTE EINTRAG DES KATALOGS, und das ist richtig so:
        # main.py ist das einzige Werkzeug, das die Konfiguration als GANZES
        # auswertet. Jedes andere liest ein oder zwei Eintraege.
        #
        # NICHT AUFGEFUEHRT sind Eintraege, die erst der Verwaltungsserver
        # (management/server/management_app.py) liest - etwa
        # 'paths.search_index_db' oder 'ad.ldap.*'. Sie gehoeren zu dessen
        # Betrieb und nicht zum Start dieses Servers.
        konfiguration=(
            _k("server.mode",
               "Der Startmodus: 'job' (Auftrag aus der Fall-Datenbank), 'cli' "
               "(Beschuldigter per Argument) oder 'support' (nur lesend, alle "
               "Schreibvorgaenge in eine fluechtige Datenbank). Ein anderer "
               "Wert bricht den Start ab.",
               "job", "core/config_loader.py, _DEFAULTS und _validate(); "
               "Auswertung in core/mode_resolver.py", "--mode"),
            _k("server.host",
               "Adresse, auf der der Server lauscht. In der Zielumgebung die "
               "Adresse, auf die der Hostname des Originalforums zeigt.",
               "127.0.0.2", "main.py, Z. 577", "--host"),
            _k("server.port",
               "Port des Servers. Muss zwischen 1 und 65535 liegen; sonst "
               "bricht der Start ab.",
               "8080 (Coded Default des ConfigLoaders: 80)",
               "main.py, Z. 581; Pruefung in core/config_loader.py, _validate()",
               "--port"),
            _k("paths.coordinator_db",
               "Die Fall-Datenbank: Auftragslage, Personen, Rechte.",
               "./data/coordinator.db",
               "main.py, _build_config_overrides(); Auswertung in "
               "core/mode_resolver.py", "--coordinator-db"),
            _k("paths.forensic_db_dir",
               "Verzeichnis der forensic_<uid>.db. Der DATEINAME wird aus der "
               "subject_id gebildet und ist NICHT einstellbar.",
               "./data/forensic/",
               "main.py, _build_config_overrides(); core/mode_resolver.py",
               "--forensic-db-dir"),
            _k("paths.evidence_db_dir",
               "Verzeichnis der evidence_<uid>.db - der Beweismittel.",
               "./data/evidence/",
               "main.py, _build_config_overrides(); core/mode_resolver.py",
               "--evidence-db-dir"),
            _k("paths.assets_db_dir",
               "Verzeichnis der assets_<uid>.db.", "./data/assets/",
               "core/mode_resolver.py"),
            _k("paths.default_db",
               "Die gemeinsame Vorgaben-Datenbank.", "./data/default.db",
               "main.py, _build_config_overrides(); core/mode_resolver.py",
               "--default-db"),
            _k("paths.templates_db",
               "Die Vorlagen-Datenbank fuer die Berichte.",
               "./data/templates.db", "core/config_loader.py, _DEFAULTS"),
            _k("paths.translations_db",
               "Die Uebersetzungen - nur lesend angebunden.",
               "./data/translations.db", "core/config_loader.py, _DEFAULTS"),
            _k("db.journal_mode",
               "Journalmodus, den der Server auf neuen Datenbanken setzt. "
               "'wal' ist VERBOTEN und fuehrt zum harten Startabbruch mit "
               "Klartext (Build 499, PROD-Vorfall Citrix). 'auto' setzt seit "
               "Build 499 unmittelbar den Rueckfallwert - es wird kein WAL "
               "mehr versucht.",
               "auto (in der ausgelieferten config.yaml hart 'delete')",
               "db/journal_policy.py, resolve_mode() Z. 228-247"),
            _k("db.journal_mode_fallback",
               "Der Modus, auf den 'auto' faellt. Zulaessig sind delete, "
               "truncate und persist.",
               "delete", "db/journal_policy.py, resolve_fallback() Z. 249-262"),
            _k("logging.level",
               "Umfang der Protokollierung: 'info' oder 'debug'. Ein anderer "
               "Wert bricht den Start ab.",
               "info", "main.py, Z. 365; Pruefung in core/config_loader.py, "
               "_validate()", "--debug"),
            _k("logging.logfile",
               "Datei, in die protokolliert wird.",
               "./logs/forensic_server.log", "main.py, Z. 366 und Z. 689"),
            _k("logging.max_bytes",
               "Groesse, ab der die Protokolldatei umgebrochen wird. Stand "
               "bis Build 640 nur in den Coded Defaults und in keiner "
               "ausgelieferten config.yaml.",
               "10485760 (10 MiB)", "main.py, Z. 367; core/logger.py Z. 111"),
            _k("logging.backup_count",
               "Wie viele umgebrochene Protokolldateien aufgehoben werden. "
               "Stand bis Build 640 nur in den Coded Defaults.",
               "5", "main.py, Z. 368; core/logger.py Z. 112"),
            _k("maintenance.drain_timeout_sec",
               "Wie lange der Server beim Ruhigstellen auf das Auslaufen "
               "offener Anfragen wartet, bevor er das Wartungsfenster "
               "bestaetigt.",
               "30 Sekunden", "main.py, Z. 758"),
            _k("maintenance.poll_interval_sec",
               "In welchem Abstand der laufende Server nachsieht, ob ein "
               "Wartungsfenster gesetzt oder aufgehoben wurde.",
               "3 Sekunden", "main.py, Z. 867"),
            _k("browser.path",
               "Programmpfad des zu startenden Browsers. Wird NUR ausgewertet, "
               "wenn der Server mit '--open-browser' gestartet wird. Leer "
               "heisst: selbst erkennen, sonst der Systemstandard.",
               "leer (Auto-Erkennung)", "core/browser_launcher.py"),
            _k("hosts_management.enabled",
               "Ob der Server den Hostnamen des Originalforums in die "
               "hosts-Datei eintraegt.",
               "false", "core/hosts_manager.py"),
            _k("hosts_management.forum_hostname",
               "Der einzutragende Hostname. Stand bis Build 640 nur in den "
               "Coded Defaults.",
               "leer", "core/hosts_manager.py, Z. 98"),
            _k("hosts_management.target_ip",
               "Die Adresse, auf die der Hostname zeigen soll. Stand bis "
               "Build 640 nur in den Coded Defaults.",
               "127.0.0.2", "core/hosts_manager.py, Z. 99"),
            _k("support.temp_db",
               "Wohin die Schreibvorgaenge im Nur-Lese-Betrieb gehen: "
               "'memory' oder 'file'. Steht in keiner ausgelieferten "
               "config.yaml, wird aber ausgewertet und geprueft.",
               "memory", "core/config_loader.py, _validate(); "
               "db/connection_manager.py Z. 380"),
            _k("validation.rules",
               "Formatregeln fuer die Eingabefelder der Berichte (Muster, "
               "Normalisierung, Klartext-Hinweis). Eine NEUE Spurennummern-"
               "Form wird hier aufgenommen, ohne Code-Aenderung und ohne "
               "Aenderung an der Vorlagen-Datenbank - danach Server neu "
               "starten.",
               "keine Regeln", "core/validation_rules.py"),
            _k("url_patterns.asset_prefixes",
               "Pfad-Vorsilben, unter denen der Server Beiwerk (Stil, Bilder) "
               "ausliefert statt Forenseiten. Steht in keiner ausgelieferten "
               "config.yaml.",
               "/forum/style/, /forum/img/, /forum/extensions/",
               "server/router.py, Z. 68; core/config_loader.py, _DEFAULTS"),
        ),
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
        aufruf="python run_tests.py [--python-only|--js-only] "
               "[--jobs N] [--leise] [--log-dir VERZEICHNIS]",
        titel="Regressionslauf",
        gruppe="Start und Einrichtung",
        zweck="Beide Testsuiten fahren - die Python-Seite und die "
              "JavaScript-Seite - und eine gemeinsame Zusammenfassung geben.",
        art="lesend",
        datenbanken=("keine der Produktivdatenbanken; die Tests arbeiten mit "
                     "eigenen Wegwerfdaten",),
        betrieb="Vor jeder Uebergabe zu fahren.",
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config'.
        # Der Testlauf ist von der Betriebskonfiguration unabhaengig - das ist
        # Absicht: eine Pruefung, die sich aus der Konfiguration bedient, prueft
        # nicht mehr denselben Gegenstand auf jeder Anlage.
        konfiguration=KONFIG_KEINE,
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python run_tests.py",
                     "Fuhr beide Suiten und fasste sie zusammen. Im "
                     "Bau-Container zu diesem Build: pytest bestanden, vitest "
                     "bestanden, 'Alle Testsuites bestanden'. Rueckgabewert "
                     "0. Laufzeit rund acht Minuten.",
                     _GEPRUEFT_614),
            ),
            # Build 665: getrennte Codes. Es sind Bitmasken (1 = Python,
            # 2 = JavaScript); jeder Aufrufer der Form 'if ! run_tests.py'
            # verhaelt sich unveraendert.
            exit_codes=((0, "alle gefahrenen Suiten bestanden"),
                        (1, "die Python-Suite ist gescheitert oder war nicht "
                            "ausfuehrbar"),
                        (2, "die JavaScript-Suite ist gescheitert oder war "
                            "nicht ausfuehrbar"),
                        (3, "beide Suiten sind gescheitert")),
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
                "JEDER LAUF SCHREIBT EIN PROTOKOLL nach 'logs/' - je Suite "
                "eine Datei mit Zeitstempel. Der Bildschirm kann abschneiden, "
                "die Datei nicht. Bei einem roten Lauf steht der Fehlerauszug "
                "zusaetzlich GANZ AM ENDE der Bildschirmausgabe; die "
                "vollstaendige Fassung nennt der Pfad darunter.",
                "Der Auszug am Ende ist auf 120 Zeilen begrenzt. Wird "
                "gekuerzt, steht das in der ersten Zeile des Auszugs - "
                "vollstaendig ist er nur in der Protokolldatei.",
                "Die Protokolle enthalten Farb-Steuerzeichen. 'less -R' zeigt "
                "sie richtig an, ein einfaches 'less' zeigt Zeichensalat.",
                "'--leise' unterdrueckt NUR die laufende Ausgabe. Protokoll, "
                "Zusammenfassung und Fehlerauszug bleiben.",
                "Die Kopfzeile nennt den verwendeten Interpreter und die "
                "pytest-Fassung. Das ist kein Beiwerk: dass 'pytest "
                "--version' auf der Kommandozeile funktioniert, beweist "
                "NICHT, dass derselbe Interpreter pytest hat - liegt eines "
                "im Benutzerverzeichnis und keines in der aktiven Umgebung, "
                "scheitert der Lauf mit 'No module named pytest'.",
                "Fehlt pytest, wird das als FEHLENDE VORAUSSETZUNG gemeldet "
                "und nicht als Testfehler. Es wurde dann NICHTS geprueft.",
                "'--jobs N' faehrt die Python-Tests parallel (pytest-xdist); "
                "'--jobs auto' nimmt die Zahl der Kerne. Es wird dabei KEINE "
                "Abdeckung aufgegeben - es laufen dieselben Tests. Gemessen "
                "am 04.08.2026: rund 16 Minuten sequenziell gegen 5 Minuten "
                "39 Sekunden mit acht Prozessen.",
                "FEHLT pytest-xdist, wird SEQUENZIELL gefahren und das "
                "gemeldet - der Lauf bricht nicht ab. Auf der offline "
                "betriebenen Produktionsumgebung laesst sich das Modul "
                "nicht nachinstallieren; die Regression muss dort trotzdem "
                "laufen.",
                "Mehr Prozesse sind nicht automatisch schneller: jeder legt "
                "eigene Wegwerf-Datenbanken an, und ab einem gewissen Punkt "
                "ist die Platte der Engpass. Im Zweifel messen.",
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
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config'. Die Einrichtung
        # legt die config.yaml erst an bzw. setzt sie voraus; sie kann sie noch
        # nicht auswerten.
        konfiguration=KONFIG_KEINE,
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
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config'.
        # Es packt den Auslieferungsstand; die Zielkonfiguration entsteht erst
        # auf der Zielanlage.
        konfiguration=KONFIG_KEINE,
        tiefe=CliTiefe(
            beispiele=(
                _bsp("python prepare_deployment.py --skip-bundle --skip-wheels",
                     "Schreibt die beiden README.txt und das "
                     "deployment_manifest.json neu, ohne etwas "
                     "herunterzuladen. Im Versuch: Rueckgabewert 0 mit dem "
                     "ausdruecklichen Satz, dass dieser Lauf ueber die "
                     "Vollzaehligkeit der Offline-Pakete NICHTS aussagt - "
                     "'--skip-wheels' war gesetzt. VORSICHT: Auch dieser "
                     "Aufruf ueberschreibt im Arbeitsbestand (siehe unten).",
                     _GEPRUEFT_647),
            ),
            exit_codes=((0, "durchgelaufen UND die Raeder sind vollzaehlig - "
                            "oder '--skip-wheels' war gesetzt, dann sagt der "
                            "Lauf ueber die Vollzaehligkeit ausdruecklich "
                            "nichts"),
                        (1, "das Bundle-Skript fehlt bzw. der Bundle-Bau ist "
                            "gescheitert; ODER (NEU Build 647) ein Download "
                            "ist fehlgeschlagen bzw. es fehlt fuer mindestens "
                            "ein Paket ein Rad - die Pakete stehen namentlich "
                            "in der Schlussbilanz")),
            warnungen=(
                "BEHOBEN IN BUILD 647 (Vorgang 0329896b): Bis Build 646 "
                "aenderte ein gescheiterter Rad-Download den Rueckgabewert "
                "NICHT - er erschien als 'WARNUNG', und der Lauf endete mit 0. "
                "Genau so ist ein unvollstaendiges Offline-Paket in den "
                "Bestand gekommen und dort liegengeblieben. Seit Build 647 "
                "prueft der Lauf je Zielverzeichnis, ob fuer JEDES verlangte "
                "Paket ein Rad vorliegt, nennt die fehlenden beim Namen und "
                "endet mit 1.",
                "DER BESTAND IST STAND BUILD 647 NICHT VOLLZAEHLIG: In "
                "setup/win64/wheels und setup/linux64/wheels fehlen "
                "'pyeditorjs', 'python-docx' und 'reportlab' - also der "
                "DOCX-Export, der PDF-Export und der serverseitige "
                "Editor.js-Export. Gemessen am 2026-08-01 mit der neuen "
                "Pruefung. Ein Lauf OHNE '--skip-wheels' auf einem Rechner "
                "mit Internetzugang holt sie nach; der Download der drei "
                "Pakete fuer cp314 ist am selben Tag erprobt worden.",
                "DIE RAEDER SIND FUER EINE BESTIMMTE PYTHON-NEBENVERSION "
                "GEBAUT (cp314, also Python 3.14). Unter einer anderen "
                "Nebenversion findet pip sie NICHT - auch dann nicht, wenn "
                "die Datei im Verzeichnis liegt; die Meldung lautet dann 'No "
                "matching distribution found' und nennt das PAKET, nicht die "
                "Version. Seit Build 647 steht die geforderte Version in "
                "beiden README.txt und im deployment_manifest.json.",
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
        # Build 640 (Welle 6): geprueft am ganzen Quelltext -
        # kein ConfigLoader, kein '--config'.
        # Der Vorgabepfad ist die fest verdrahtete Zeichenkette DEFAULT_DB_PATH =
        # './data/coordinator.db' (Z. 67). Der Kommentar daneben nennt sie
        # 'passend zu config.yaml' - GELESEN wird die Datei aber nicht. Wer die
        # coordinator.db anderswo liegen hat, muss den Pfad hier uebergeben.
        konfiguration=KONFIG_KEINE,
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


def fehlliste_cli_konfiguration() -> Tuple[str, ...]:
    """
    Die ABGELEITETE Fehlliste der Werkzeuge, bei denen NOCH NICHT GEPRUEFT
    ist, welche Eintraege aus config.yaml sie auswerten (NEU Build 639,
    Ticket 60e4236e).

    WAS HIER NICHT STEHT UND WARUM: Ein Werkzeug, bei dem die Pruefung
    ergeben hat, dass es KEINEN Eintrag liest, steht NICHT in dieser Liste.
    Es traegt KONFIG_KEINE, und das ist eine Antwort. Nur 'konfiguration=None'
    - also "nicht nachgesehen" - landet hier.

    Ohne diese Unterscheidung waere die Liste wertlos: sie wuerde entweder
    geprueft-leere Werkzeuge ewig mitfuehren oder ungepruefte als erledigt
    ausweisen. Beides waere ein stilles Uebergehen einer Luecke
    (Grundregel 1).

    Sie wird nicht gepflegt, sondern gerechnet - eine gepflegte Liste koennte
    luegen.
    """
    return tuple(e.schluessel for e in CLI_KATALOG
                 if not e.konfiguration_geprueft())


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

    BUILD 630: BEIDE RICHTUNGEN WERDEN IN EINER MELDUNG GENANNT. Bis Build
    629 kehrte die Funktion nach der ersten Richtung um; wer eine Datei
    zuviel UND eine zuwenig hatte, sah nur die eine und nach dem Beheben die
    andere.

    AUFGEFALLEN AN MCS REGRESSIONSLAUF ZU BUILD 629: 'tools/anon_html.py'
    war neu im Bestand und hatte keinen Katalogeintrag. Das meldete CK02 -
    und CK02b fiel gleich mit um, weil es denselben Aufruf benutzt und die
    ZWEITE Richtung erwartete, die nie erreicht wurde. Zwei Fehlermeldungen,
    ein Grund, und die zweite war irrefuehrend: sie sah aus wie ein zweiter
    Befund.
    """
    gefunden = {p.replace("\\", "/") for p in gefundene_pfade}
    im_katalog = set(CLI_PFADE)

    befunde = []
    ohne_eintrag = sorted(gefunden - im_katalog)
    if ohne_eintrag:
        befunde.append(
            "Werkzeuge im Bestand OHNE Katalogeintrag: %s. Jedes Werkzeug "
            "braucht einen Eintrag - sonst weiss niemand, dass es es gibt."
            % ", ".join(ohne_eintrag))

    ohne_datei = sorted(im_katalog - gefunden)
    if ohne_datei:
        befunde.append(
            "Katalogeintraege OHNE Datei im Bestand: %s. Entweder ist die "
            "Datei entfallen (dann gehoert der Eintrag weg) oder sie wurde "
            "verschoben (dann gehoert der Pfad nachgezogen)."
            % ", ".join(ohne_datei))

    if befunde:
        raise CliKatalogError(" | ".join(befunde))
