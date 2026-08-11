# =============================================================================
# management/help/inhalt/ueberblick.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H7)
# =============================================================================
# Zweck:
#   Die Hilfetexte der Nav-Gruppe "Ueberblick": dashboard, calendar,
#   escalation, nextactions.
#
#   DIE VIER SICHTEN BEANTWORTEN DIESELBE FRAGE AUF VIER ARTEN - "worauf muss
#   ich JETZT schauen?". Der Ueberblick antwortet mit Zustaenden, die
#   Eskalationen mit Schwellenverletzungen, die naechstbeste Aktion mit der
#   naechsten HANDLUNG, der Kalender mit Terminen. Diese Abgrenzung steht in
#   jedem der vier Kapitel im Abschnitt "Querverweise" - wer eine der Sichten
#   aufschlaegt, soll die anderen drei einordnen koennen, statt sie fuer
#   Wiederholungen zu halten.
#
# QUELLEN DER TEXTE (keine Behauptung ohne Beleg):
#   cockpit_dashboard.js, cockpit_calendar.js, cockpit_escalation.js,
#   cockpit_nextactions.js (jeweils Modulkopf mit den tragenden
#   Entscheidungen), management/viewprefs/viewpref_katalog.py (WIDGETS),
#   management/server/static/cockpit.js (VIEW_CATALOG, Rechte und Scope).
#
# REGEL H-0: kein Falldatum, keine echte Kennung, kein Beispiel aus dem
#   Betrieb.
#
# Version: v0.8.595 - Build: 595 - 2026-07-31
# =============================================================================

from __future__ import annotations

from typing import Tuple

from management.help.modell import Abschnitt, Kontexthilfe, Sichthilfe

_STAND = 595


# =============================================================================
# 1) dashboard - "Ueberblick"
# =============================================================================

DASHBOARD = Sichthilfe(
    sicht="dashboard",
    titel="Dashboard",
    recht_klartext=(
        "Recht: dashboard.view für die Sicht selbst. JEDE KACHEL trägt "
        "darüber hinaus ihr eigenes Recht — Sie sehen nur die Kacheln, deren "
        "Recht Sie besitzen. Eine Kachel, die hier fehlt, ist Ihnen nicht "
        "zugeteilt und nicht etwa ausgefallen; ausgefallene Kacheln sagen "
        "das ausdrücklich („Nicht abrufbar“)."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Der Überblick ist die Einstiegsseite: eine Kachelfläche, die "
                "in wenigen Zahlen zeigt, wie die Lage gerade ist. Er ist "
                "bewusst keine Arbeitsfläche — man liest ihn und springt dann "
                "in die Sicht, die zur Frage passt.",
                "Jede Kachel beantwortet genau eine Frage und nennt ihre "
                "Grundlage. Das ist der Unterschied zwischen einer Kennzahl "
                "und einer Behauptung: Wer eine Zahl weitergibt, muss sagen "
                "können, worauf sie beruht.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "Die Sicht selbst hängt an dashboard.view. Die Kacheln haben "
                "eigene Rechte: Fall-Übersicht an caseoverview.view, "
                "Eskalationen an escalation.view, Nächstbeste Aktion an "
                "nextactions.view, Fällige Wiedervorlagen an external.view, "
                "Fristen an limitation.view, Lastverteilung an "
                "workload.view, Meine Aufträge an mycases.view, Zustand der "
                "Audit-Kette an ops.view.",
                "Der Kachelwähler zeigt ausschließlich Kacheln, für die Sie "
                "berechtigt sind. Er kann also nichts einblenden, was Ihnen "
                "verwehrt ist — die Auswahl ordnet und blendet aus, sie "
                "erlaubt nichts.",
                "GEÄNDERT IM AUGUST 2026: Die Fall-Übersicht hing bis dahin "
                "am selben Recht wie der Überblick selbst (dashboard.view) "
                "und war damit die einzige Kachel ohne eigenes. Wer den "
                "Überblick öffnen durfte, bekam die vollständige Fallliste "
                "ungefragt dazu. Sie trägt jetzt caseoverview.view. "
                "dashboard.view öffnet seither nur noch den Rahmen: Sie sehen "
                "die Kachelfläche, aber jede Kachel darin nach ihrem eigenen "
                "Recht.",
                "Fehlt Ihnen die Fall-Übersicht seit der Umstellung, ist das "
                "kein Ausfall: Ihnen fehlt caseoverview.view. Die "
                "Chef-Ermittlerin kann es vergeben.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Oben die Überschrift, darunter die Kachelfläche, darunter "
                "der Kachelwähler.",
            ),
        ),
        Abschnitt(
            "kachel", "Aufbau einer Kachel",
            (
                "Jede Kachel liest sich von oben nach unten in der "
                "Reihenfolge, in der der Blick sie braucht: Titel, dann die "
                "Größenordnung als Zahl, dann die Form als Diagramm (wo eines "
                "sinnvoll ist), dann die Einzelzeilen. Beim Detail darf der "
                "Blick aufhören, ohne etwas zu verpassen.",
                "Die Fußzeile ist Pflichtbestandteil und kein Kleingedrucktes. "
                "Sie nennt bis zu drei Dinge: die Grundlage der Zahl, einen "
                "Reduktionshinweis (die Kachel zeigt nur die obersten "
                "Einträge) und einen Vorbehalt (etwa den Verjährungsvorbehalt "
                "der Fristen-Kachel). Den vollständigen Wortlaut zeigt ein "
                "Kurzhinweis, wenn Sie mit der Maus darauf zeigen.",
            ),
            liste=(
                "„Es liegt nichts an.“ — ein echter Leerbefund: es wurde "
                "gemessen, und es kam nichts heraus.",
                "„Nicht abrufbar: …“ — ein Ausfall. Ausgefallen ist NICHT "
                "leer; die Kachel färbt sich entsprechend und nennt den Grund.",
            ),
        ),
        Abschnitt(
            "waehler", "Kachelwähler",
            (
                "Unten stellen Sie ein, welche Kacheln erscheinen und in "
                "welcher Reihenfolge: Auswahl per Haken, Reihenfolge mit den "
                "Pfeilen. Die Einstellung gilt nur für Ihr Konto.",
                "Im Überblick sind Sie dabei frei — anders als bei der "
                "Navigation gibt es hier keine Warnungen und keine "
                "Mindestauswahl. Wer nichts einstellt, bekommt die "
                "Werkseinstellung und merkt von der Einstellmöglichkeit "
                "nichts.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Lagebild zu Dienstbeginn: Überblick öffnen, die Zahlen der "
                "Kacheln lesen, bei einer auffälligen Zahl in die zugehörige "
                "Sicht wechseln.",
                "Eine Kachel meldet „Nicht abrufbar“: das ist ein "
                "Betriebsvorfall, kein Leerbefund. Den genannten Grund "
                "notieren und den Betrieb verständigen.",
                "Die Fläche einrichten: unten die Kacheln abwählen, die Sie "
                "nicht brauchen, und die wichtigste nach oben schieben.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "Die Kacheln sind REDUZIERT. Sie zeigen die obersten "
                "Einträge, nicht den vollständigen Bestand — die Fußzeile "
                "sagt es, wo es zutrifft. Wer den ganzen Bestand braucht, "
                "geht in die Fachsicht.",
                "Der Überblick ist REIN LESEND. Er verteilt nicht, gibt nicht "
                "frei und quittiert nicht. Die einzige Einstellung, die er "
                "kennt, betrifft seine eigene Kachelfläche.",
                "Eine fehlende Kachel und eine ausgefallene Kachel sind zwei "
                "verschiedene Aussagen. Fehlt sie ganz, haben Sie das Recht "
                "nicht oder haben sie abgewählt; steht „Nicht abrufbar“, ist "
                "die Quelle nicht erreichbar.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (
                "Vier Sichten beantworten die Frage „worauf muss ich jetzt "
                "schauen?“ auf vier Arten — das ist Absicht und keine "
                "Doppelung:",
            ),
            liste=(
                "Überblick — mit Zuständen (wie steht es gerade?).",
                "Eskalationen — mit Schwellenverletzungen (was ist über eine "
                "Grenze gelaufen?).",
                "Nächstbeste Aktion — mit der nächsten Handlung (was tue ich "
                "als Nächstes?).",
                "Kalender & Wiedervorlage — mit Terminen (was wird wann "
                "fällig?).",
                "Fallübersicht — der vollständige Bestand hinter der "
                "Ampel-Kachel.",
                "Ansicht anpassen — dieselbe Einstelllogik für die "
                "Navigation.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "dashboard.titel", "Überblick",
            "Die Einstiegsseite: eine Kachelfläche, die in wenigen Zahlen "
            "zeigt, wie die Lage gerade ist. Rein lesend; jede Kachel nennt "
            "ihre Grundlage.",
            verweis="dashboard#zweck"),
        Kontexthilfe(
            "dashboard.kachel.fallampel", "Kachel „Fall-Übersicht (Ampel)“",
            "Die Verteilung der Fälle auf die Dringlichkeits-Ampel, dazu die "
            "dringendsten Fälle. Recht: caseoverview.view — seit August 2026 "
            "ein eigenes Recht, vorher dashboard.view. Der vollständige "
            "Bestand steht in der Sicht „Fallübersicht“.",
            verweis="dashboard#kachel"),
        Kontexthilfe(
            "dashboard.kachel.eskalationen", "Kachel „Eskalationen“",
            "Was über eine Schwelle gelaufen ist, beschränkt auf die obersten "
            "Einträge. Recht: escalation.view. Die vollständige Liste samt "
            "Maßstab und Quittierung steht in der Sicht „Eskalationen“.",
            verweis="dashboard#kachel"),
        Kontexthilfe(
            "dashboard.kachel.naechste_aktion", "Kachel „Nächstbeste Aktion“",
            "Die vordersten Einträge der Auftragsliste. Recht: "
            "nextactions.view. Die Begründung je Eintrag steht vollständig in "
            "der gleichnamigen Sicht.",
            verweis="dashboard#kachel"),
        Kontexthilfe(
            "dashboard.kachel.wiedervorlage", "Kachel „Fällige Wiedervorlagen“",
            "Externe Vorgänge, deren Frist erreicht oder überschritten ist. "
            "Recht: external.view. Der Kalender zeigt sie im Zusammenhang.",
            verweis="dashboard#kachel"),
        Kontexthilfe(
            "dashboard.kachel.fristen", "Kachel „Fristen mit Vorwarnung“",
            "Fälle, deren Verjährungsfrist in den Vorwarnbereich läuft. "
            "Recht: limitation.view. Der Verjährungsvorbehalt fährt mit — die "
            "Kachel stellt keine Verjährung fest.",
            verweis="dashboard#kachel"),
        Kontexthilfe(
            "dashboard.kachel.lastverteilung", "Kachel „Lastverteilung“",
            "Aktive Fälle je Ermittler:in samt Überlastwarnung. Recht: "
            "workload.view. Dient ausschließlich dem Mengenausgleich  "
            "bei der Aufgabenverteilung.",
            verweis="dashboard#kachel"),
        Kontexthilfe(
            "dashboard.kachel.meine_auftraege", "Kachel „Meine Aufträge“",
            "Die eigenen offenen Zuweisungen. Recht: mycases.view.",
            verweis="dashboard#kachel"),
        Kontexthilfe(
            "dashboard.kachel.kettenzustand", "Kachel „Zustand der Audit-Kette“",
            "Ergebnis der Kettenprüfung und die aktuelle Spitze des "
            "Protokollbuchs — der Betriebsblick. Recht: ops.view. Eine "
            "Meldung hier ist ein Betriebsvorfall.",
            verweis="dashboard#kachel"),

        # Build 637 (Welle B5).
        Kontexthilfe(
            "dashboard.bedienung.kachelwahl", "Kachel anzeigen",
            "Nimmt diese Kachel in Ihre Übersicht auf oder heraus. Die "
            "Auswahl gilt nur für Ihr Konto.",
            verweis="dashboard#waehler"),
    ),
)


# =============================================================================
# 2) calendar - "Kalender & Wiedervorlage"
# =============================================================================

CALENDAR = Sichthilfe(
    sicht="calendar",
    titel="Kalender & Wiedervorlage",
    recht_klartext=(
        "Recht: external.view. Die Sicht bedient BEIDE Rollen: mit dem "
        "Umfang „alle“ sehen Sie die Fälligkeiten der Dienststelle, mit "
        "„eigene“ die der eigenen Fälle. Das Anlegen, Verschieben und "
        "Abschließen "
        "eines Vorgangs setzt zusätzlich das Schreibrecht voraus; ohne dieses "
        "ist die Sicht rein lesend."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Der Kalender führt die Termine zusammen, die aus "
                "verschiedenen Quellen auf einen Fall zulaufen: externe "
                "Vorgänge mit Wiedervorlagefrist, Fälligkeiten, "
                "Erinnerungen. Er beantwortet die Frage „was wird wann "
                "fällig?“ — die einzige der vier Überblicksfragen, die von "
                "einem Datum und nicht von einem Zustand abhängt.",
                "Ohne diese Sicht müsste jede Frist einzeln im Kopf behalten "
                "werden. Genau das ist die Fehlerquelle, die eine "
                "Wiedervorlage verhindern soll.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "Die Sicht hängt an external.view. Der zugeteilte Umfang "
                "entscheidet, "
                "wessen Fälligkeiten Sie sehen: „alle“ die der Dienststelle, "
                "„eigene“ die der eigenen Fälle. Schreibende Vorgänge "
                "(anlegen, verschieben, abschließen) werden protokolliert und "
                "sind ohne das entsprechende Recht nicht erreichbar.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Unter der Überschrift steht der Stichtag — die "
                "Rechengrundlage, auf die sich alle Fristangaben beziehen. "
                "Darunter erscheinen Hinweise, wenn der Kalender etwas nicht "
                "beantworten kann. Es folgen das Monatsraster und die "
                "Fälligkeitsliste als Tabelle mit Kopffiltern.",
            ),
        ),
        Abschnitt(
            "stichtag", "Der Stichtag",
            (
                "Der Stichtag steht sichtbar über allem, damit eine falsch "
                "gestellte Uhr auffällt. Jede Angabe wie „überfällig“ oder "
                "„in 3 Tagen“ ist eine Aussage RELATIV zu diesem Datum — ohne "
                "ihn wäre sie nicht nachprüfbar.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Tagesrunde: Kalender öffnen, Stichtag prüfen, die "
                "überfälligen Einträge der Liste abarbeiten.",
                "Wiedervorlage verschieben: Der Grund ist Pflichtangabe. Das "
                "ist keine Schikane — eine verschobene Frist ohne Grund ist "
                "später von einer vergessenen nicht mehr zu unterscheiden.",
                "Vorgang abschließen: unwiderruflich. Vor dem Abschließen "
                "prüfen, ob wirklich alles vorliegt.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "Der Kalender rechnet gegen den angezeigten Stichtag und "
                "gegen nichts sonst. Er stellt KEINE Verjährung fest — dafür "
                "gibt es die Sicht „Fristen (Verjährung)“, und auch die "
                "stellt sie ausdrücklich nicht fest.",
                "Der Abschluss eines Vorgangs ist unwiderruflich. Es gibt in "
                "dieser Sicht keinen Weg zurück.",
                "Was der Kalender nicht beantworten kann, sagt er als Hinweis "
                "über der Liste, statt die Zeile wegzulassen.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Überblick — die Kachel „Fällige Wiedervorlagen“ zeigt "
                "denselben Bestand verdichtet.",
                "Fristen (Verjährung) — die andere Art von Frist: die "
                "gesetzliche, nicht die selbst gesetzte.",
                "Eskalationen — was über eine Schwelle gelaufen ist, "
                "unabhängig von einem Termin.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "calendar.titel", "Kalender & Wiedervorlage",
            "Führt die Termine zusammen, die auf einen Fall zulaufen: externe "
            "Vorgänge, Fristen, Erinnerungen. Beantwortet „was wird wann "
            "fällig?“.",
            verweis="calendar#zweck"),
        Kontexthilfe(
            "calendar.stichtag", "Stichtag",
            "Die Rechengrundlage aller Fristangaben dieser Sicht. Steht "
            "sichtbar, damit eine falsch gestellte Uhr auffällt: „überfällig“ "
            "ist immer eine Aussage relativ zu diesem Datum.",
            verweis="calendar#stichtag"),
        Kontexthilfe(
            "calendar.spalte.ampel", "Spalte „A“ (Ampel)",
            "Die Fälligkeitsampel des Vorgangs, gerechnet gegen den Stichtag. "
            "Die Begründung steht in der letzten Spalte.",
            verweis="calendar#stichtag"),
        Kontexthilfe(
            "calendar.spalte.id", "Spalte „Nr.“",
            "Die laufende Nummer des externen Vorgangs. Sie ist der "
            "Schlüssel, unter dem der Vorgang protokolliert wird."),
        Kontexthilfe(
            "calendar.spalte.subject_id", "Spalte „Fall“",
            "Die Subject-ID der Fallakte, zu der der Vorgang gehört."),
        Kontexthilfe(
            "calendar.spalte.fall_username", "Spalte „Benutzername“",
            "Der im Forum geführte Kontoname des Falls — der Name, den man "
            "eher wiedererkennt als die Nummer."),
        Kontexthilfe(
            "calendar.spalte.kind_label", "Spalte „Art“",
            "Die Art des externen Vorgangs (etwa Auskunftsersuchen oder "
            "Beschluss). Sie entscheidet mit darüber, welche Frist gilt."),
        Kontexthilfe(
            "calendar.spalte.betreff", "Spalte „Betreff“",
            "Die Kurzbezeichnung des Vorgangs, wie sie beim Anlegen "
            "vergeben wurde."),
        Kontexthilfe(
            "calendar.spalte.adressat", "Spalte „Adressat“",
            "Die Stelle, an die sich der Vorgang richtet."),
        Kontexthilfe(
            "calendar.spalte.wiedervorlage_am", "Spalte „Wiedervorlage“",
            "Das Datum, zu dem der Vorgang wieder vorgelegt werden soll. "
            "Verschieben ist möglich, verlangt aber eine Begründung.",
            verweis="calendar#ablaeufe"),
        Kontexthilfe(
            "calendar.spalte.status_label", "Spalte „Zustand“",
            "Der Bearbeitungsstand des Vorgangs. Ein abgeschlossener Vorgang "
            "lässt sich nicht wieder öffnen.",
            verweis="calendar#grenzen"),
        Kontexthilfe(
            "calendar.spalte.ampel_grund", "Spalte „Begründung“",
            "Warum die Ampel so steht, wie sie steht — im Klartext. Ohne "
            "diese Spalte wäre die Farbe eine unbelegte Behauptung."),
        # ------------------------------------------------------------------
        # Die Bedienelemente (Build 636, Welle B4). Die Erhebung zaehlte hier
        # nur VIER - die Sicht baut ihre Knoepfe und Felder in zwei Fabriken
        # ('_btn', '_field'), und eine Fabrik zaehlt einmal. Tatsaechlich
        # sind es zwanzig, und alle zwanzig bekommen hier ihren Text.
        # ------------------------------------------------------------------
        Kontexthilfe(
            "calendar.bedienung.vormonat", "Vormonat",
            "Blättert einen Monat zurück. Die Liste unter dem Kalender folgt "
            "der Monatsanzeige."),
        Kontexthilfe(
            "calendar.bedienung.folgemonat", "Folgemonat",
            "Blättert einen Monat vor. Fristen, die im Folgemonat fällig "
            "werden, sehen Sie so, bevor sie drücken."),
        Kontexthilfe(
            "calendar.bedienung.heute", "Heute",
            "Springt zum laufenden Monat zurück."),
        Kontexthilfe(
            "calendar.bedienung.ampelfilter", "Ampel",
            "Zeigt nur Vorgänge einer Ampelstufe; in Klammern steht die "
            "Anzahl. Der Filter verbirgt Zeilen — er ändert nichts an den "
            "Fristen.",
            verweis="calendar#stichtag"),
        Kontexthilfe(
            "calendar.bedienung.neuer_vorgang", "Neuer Vorgang",
            "Öffnet das Formular für einen externen Vorgang. Der Knopf "
            "erscheint nur mit dem Recht zum Ändern.",
            verweis="calendar#rechte"),
        Kontexthilfe(
            "calendar.bedienung.aktion", "Aktion am Vorgang",
            "Führt den nächsten Schritt aus — je nach Zustand verschieben, "
            "beantworten oder abschließen. Angeboten wird nur, was von hier "
            "aus zulässig ist. Vor der Ausführung kommt immer eine Rückfrage.",
            verweis="calendar#grenzen"),
        Kontexthilfe(
            "calendar.bedienung.bestaetigen", "Ja, ausführen",
            "Führt die gewählte Aktion aus und schreibt sie fest. Was bis "
            "dahin in den Feldern steht, wird mitgeschrieben."),
        Kontexthilfe(
            "calendar.bedienung.abbrechen", "Abbrechen",
            "Schließt die Rückfrage. Es wird nichts geschrieben."),
        Kontexthilfe(
            "calendar.bedienung.neues_datum", "Neues Wiedervorlagedatum",
            "Der Tag, an dem der Vorgang wieder auf den Tisch kommt. Das "
            "Verschieben ändert die Wiedervorlage, NICHT die Frist selbst.",
            verweis="calendar#grenzen"),
        Kontexthilfe(
            "calendar.bedienung.verschiebegrund", "Grund der Verschiebung",
            "PFLICHTANGABE. Eine verschobene Wiedervorlage ohne Grund ist "
            "später nicht von einem Versäumnis zu unterscheiden."),
        Kontexthilfe(
            "calendar.bedienung.antwortergebnis", "Ergebnis der Antwort",
            "Was die angeschriebene Stelle mitgeteilt hat — freiwillig, aber "
            "die einzige Stelle, an der es festgehalten wird."),
        Kontexthilfe(
            "calendar.bedienung.abschlussergebnis", "Ergebnis / Begründung",
            "Womit der Vorgang endet. Ein abgeschlossener Vorgang lässt sich "
            "NICHT wieder öffnen; ein Irrtum wird durch einen neuen Vorgang "
            "berichtigt.",
            verweis="calendar#grenzen"),
        Kontexthilfe(
            "calendar.bedienung.fall", "Fall (Pflicht)",
            "Der Ermittlungsschlüssel des Falls, zu dem der Vorgang gehört. "
            "Das Werkzeug prüft die Angabe: ein unbekannter Fall wird "
            "abgewiesen, ein nicht zugewiesener ebenfalls."),
        Kontexthilfe(
            "calendar.bedienung.vorgangsart", "Vorgangsart",
            "Um welche Art von externem Vorgang es sich handelt. Die Art "
            "bestimmt mit, wie der Vorgang später gelesen wird."),
        Kontexthilfe(
            "calendar.bedienung.betreff", "Betreff (Pflicht)",
            "Worum es geht, in einer Zeile. Er steht später in der Liste — "
            "schreiben Sie ihn so, dass er dort allein trägt."),
        Kontexthilfe(
            "calendar.bedienung.adressat", "Adressat",
            "An wen der Vorgang gerichtet ist. Freiwillig, aber ohne diese "
            "Angabe lässt sich später nicht nachvollziehen, wo nachzufassen "
            "wäre."),
        Kontexthilfe(
            "calendar.bedienung.aktenzeichen", "Aktenzeichen (extern)",
            "Das Zeichen der EMPFANGENDEN Stelle — nicht das eigene. Es ist "
            "der Faden, an dem eine Rückfrage hängt."),
        Kontexthilfe(
            "calendar.bedienung.wiedervorlage", "Wiedervorlage (Pflicht)",
            "Der Tag, an dem der Vorgang wieder vorgelegt wird. Aus ihm und "
            "der Vorwarnfrist ergibt sich die Ampel.",
            verweis="calendar#stichtag"),
        Kontexthilfe(
            "calendar.bedienung.vorwarnfrist", "Vorwarnfrist (Tage)",
            "Wie viele Tage vor der Wiedervorlage die Ampel auf Gelb "
            "springt. Bei einer Stelle, die erfahrungsgemäß lange braucht, "
            "lohnt eine längere Vorwarnung.",
            verweis="calendar#stichtag"),
        Kontexthilfe(
            "calendar.bedienung.anlegen", "Anlegen",
            "Legt den Vorgang an. Pflicht sind Fall, Betreff und "
            "Wiedervorlage; fehlt eines, wird nichts geschrieben."),
        Kontexthilfe(
            "calendar.bedienung.formular_abbrechen", "Abbrechen",
            "Schließt das Formular. Es wird nichts geschrieben."),
        Kontexthilfe(
            "calendar.werkzeug.filter_entfernen", "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Sicht auf einmal."),
        Kontexthilfe(
            "calendar.werkzeug.trefferzahl", "Trefferanzeige",
            "Nennt, wie viele Zeilen gerade sichtbar sind; sobald ein Filter "
            "greift, „sichtbar von gesamt“."),
    ),
)


# =============================================================================
# 3) escalation - "Eskalationen"
# =============================================================================

ESCALATION = Sichthilfe(
    sicht="escalation",
    titel="Eskalationen",
    recht_klartext=(
        "Recht: escalation.view — BEWUSST OHNE Einschränkung des Umfangs. "
        "Die Sicht ist nicht auf "
        "„eigene“ verengbar, weil die wichtigste Meldung (der Rückstau) zu "
        "keinem Fall und damit zu keiner Person gehört; auf „eigene“ verengt "
        "hätte die Sicht genau die Fälle ausgeblendet, um derentwillen es sie "
        "gibt. Das Quittieren verlangt zusätzlich escalation.ack."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Sicht zeigt, was über eine Schwelle gelaufen ist: Fälle, "
                "die zu lange ruhen, Rückstau bei der Verteilung, "
                "überschrittene Fristen. Sie beantwortet „was ist über eine "
                "Grenze gelaufen?“ — nicht „wie steht es allgemein?“.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "Ansehen: escalation.view, ohne Einschränkung des Umfangs. "
                "Quittieren: "
                "zusätzlich escalation.ack. Fehlt das Quittierrecht, sagt die "
                "Sicht das ausdrücklich — sie zeigt nicht wortlos keinen "
                "Knopf. Ebenso unterscheidet sie „die Struktur fehlt“ "
                "(die Vorbereitung dafür ist auf dieser Anlage noch nicht "
                "erfolgt) von „Sie haben dieses Recht "
                "nicht“. Das sind zwei verschiedene Aussagen.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter die Zählzeile, darunter die Liste der "
                "Meldungen und unter der Liste die angewandten Schwellen.",
            ),
        ),
        Abschnitt(
            "massstab", "Der Maßstab steht dabei",
            (
                "Unter der Liste stehen die tatsächlich angewandten "
                "Schwellenwerte. Das ist Absicht: „30 Tage inaktiv“ ist erst "
                "zusammen mit „ab 30“ eine nachprüfbare Aussage. Ohne den "
                "Maßstab wäre jede Zeile eine unbelegte Behauptung.",
            ),
        ),
        Abschnitt(
            "systemisch", "Meldungen ohne Fallbezug",
            (
                "Eine Meldung ohne Fallbezug ist eine Aussage, keine Lücke. "
                "Die Regel zum Rückstau gehört zu keinem einzelnen Fall — sie "
                "meldet, dass Fälle unverteilt liegen bleiben. Sie wird "
                "deshalb ausdrücklich als „systemisch (kein Einzelfall)“ "
                "ausgewiesen und nicht als leere Zelle. Sie ist ebenfalls "
                "quittierbar; sie ist die wichtigste Meldung der Sicht.",
            ),
        ),
        Abschnitt(
            "quittung", "Quittieren",
            (
                "Quittieren heißt: festhalten, dass die Meldung gesehen wurde "
                "und was veranlasst ist. Es ist protokolliert, verlangt eine "
                "Pflichtbegründung und ist widerrufbar — widerrufen, nicht "
                "gelöscht.",
                "Ein überholter Vermerk wird als solcher gezeigt: Wenn der "
                "Fall heute länger ruht als zum Zeitpunkt der Quittierung, "
                "hat sich die Lage seither VERSCHLECHTERT. Das darf nicht "
                "aussehen wie ein frischer Vermerk.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Durchsicht: nach Schwere von oben nach unten lesen; die "
                "systemische Rückstaumeldung zuerst behandeln.",
                "Quittieren: Meldung auswählen, Begründung eingeben "
                "(Pflicht), bestätigen. Die Meldung bleibt anschließend "
                "stehen.",
                "Widerrufen: einen irrtümlich gesetzten Vermerk mit "
                "Begründung widerrufen. Der ursprüngliche Vermerk bleibt "
                "protokolliert.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "QUITTIEREN IST KEIN ERLEDIGEN. Eine quittierte Meldung "
                "bleibt in der Liste und behält ihre Schwere und ihre Farbe; "
                "sie bekommt lediglich einen Vermerk. Würde die Sicht sie "
                "ausblenden oder abstufen, ließe sich ein liegengebliebener "
                "Fall per Klick unauffällig machen, ohne dass sich an ihm "
                "etwas ändert.",
                "Die Sicht filtert und sortiert NICHTS um. Die Reihenfolge "
                "ist fix; eine Sortierung hier wäre eine "
                "Verzerrung der Wahrheit.",
                "Drei Zustände sind unterscheidbar: Fehler („derzeit nicht "
                "verfügbar“), echter Leerbefund („keine Eskalation — bewertet "
                "wurden N Fälle“) und Befund. Eine leere Liste im Fehlerfall "
                "hätte fälschlich „alles in Ordnung“ behauptet.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Überblick — die Kachel „Eskalationen“ zeigt die obersten "
                "Einträge.",
                "Nächstbeste Aktion — was tun, wenn etwas eskaliert ist.",
                "Fallübersicht — der Bestand, aus dem die Meldungen stammen.",
                "Zuweisung — der Weg, den Rückstau aufzulösen.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "escalation.titel", "Eskalationen",
            "Zeigt, was über eine Schwelle gelaufen ist: zu lange ruhende "
            "Fälle, Rückstau, überschrittene Fristen. Die angewandten "
            "Schwellen stehen unter der Liste.",
            verweis="escalation#massstab"),
        Kontexthilfe(
            "escalation.zahlen", "Zählzeile",
            "Nennt, wie viele Meldungen je Schwere vorliegen und wie viele "
            "Fälle bewertet wurden. Die Grundgesamtheit steht dabei, damit "
            "eine kurze Liste nicht wie ein Datenfehler aussieht.",
            verweis="escalation#grenzen"),
        Kontexthilfe(
            "escalation.spalte.schwere", "Spalte „Schwere“",
            "Die Schwere der Meldung: hoch, mittel oder niedrig. Ein "
            "unbekannter Wert wird wörtlich durchgereicht und als unbekannt "
            "markiert, statt still auf „niedrig“ zu fallen."),
        Kontexthilfe(
            "escalation.spalte.regel", "Spalte „Regel“",
            "Die Regel, die angeschlagen hat. Ihr Maßstab steht unter der "
            "Liste.",
            verweis="escalation#massstab"),
        Kontexthilfe(
            "escalation.spalte.bezug", "Spalte „Bezug“",
            "Der Fall, auf den sich die Meldung bezieht — oder „systemisch "
            "(kein Einzelfall)“. Letzteres ist eine Aussage und keine Lücke.",
            verweis="escalation#systemisch"),
        Kontexthilfe(
            "escalation.spalte.inaktiv", "Spalte „Inaktiv“",
            "Tage ohne Aktivität am Fall. Erst zusammen mit der Schwelle "
            "unter der Liste ist die Zahl eine nachprüfbare Aussage.",
            verweis="escalation#massstab"),
        Kontexthilfe(
            "escalation.spalte.begruendung", "Spalte „Begründung“",
            "Der Text der Meldung — wörtlich aus der Regel, die angeschlagen "
            "hat. Er ist der Beleg, nicht die Zusammenfassung."),
        Kontexthilfe(
            "escalation.spalte.vermerk", "Spalte „Vermerk“",
            "Der Quittierungsvermerk, sofern einer vorliegt: wer, wann, mit "
            "welcher Begründung. Ein überholter Vermerk ist als solcher "
            "gekennzeichnet — dann ruht der Fall heute länger als bei der "
            "Quittierung.",
            verweis="escalation#quittung"),

        # Build 637 (Welle B5).
        Kontexthilfe(
            "escalation.bedienung.pflichttext", "Pflichttext",
            "PFLICHTANGABE — und je nach Lage zweierlei: Bei einer offenen "
            "Meldung „was wurde veranlasst?“, bei einer bereits quittierten "
            "der Grund des Widerrufs. Die Beschriftung sagt, was gerade "
            "gemeint ist. Ohne Text wird nichts geschrieben.",
            verweis="escalation#quittung"),
    ),
)


# =============================================================================
# 4) nextactions - "Naechstbeste Aktion"
# =============================================================================

NEXTACTIONS = Sichthilfe(
    sicht="nextactions",
    titel="Nächstbeste Aktion",
    recht_klartext=(
        "Recht: nextactions.view. DER ZUGETEILTE UMFANG ENTSCHEIDET: mit "
        "„eigene“ ist es "
        "Ihre eigene Auftragsliste, mit „alle“ die Verteilsicht der "
        "Leitung. Welcher Umfang gerade gilt, steht über der Liste — sonst "
        "läse sich eine kurze eigene Liste wie eine leere Dienststelle."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Sicht nennt je offenem Fall die nächste sinnvolle "
                "Handlung — und dazu die Begründung, warum gerade diese. Sie "
                "beantwortet „was tue ich als Nächstes?“.",
                "Die Begründung ist die Hauptsache, nicht die Handlung. Eine "
                "Auftragsliste, die nur sagt „Fall bearbeiten“, ist ein "
                "Befehl. Eine, die sagt „rote Ampel, seit 34 Tagen keine "
                "Aktivität“, ist ein Beleg. Deshalb steht die Begründung als "
                "eigene, breite Spalte und nicht als Kurzhinweis, den niemand "
                "aufklappt.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "nextactions.view, mit zugeteiltem Umfang. „eigene“ und „alle“ "
                "beantworten "
                "verschiedene Fragen: Selbstorganisation gegenüber "
                "Verteilung. Der geltende Umfang wird deshalb immer benannt.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter Umfang und Zählzeile, darunter die "
                "Tabelle. Die Reihenfolge ist fest vorgegeben: "
                "Dringlichkeit, dann Priorität, dann letzte Aktivität, dann "
                "Subject-ID.",
            ),
        ),
        Abschnitt(
            "zahlen", "Die drei Zahlen",
            (
                "Über der Liste stehen immer alle drei Zahlen: wie viele "
                "Fälle handlungsbedürftig sind, wie viele es insgesamt gibt, "
                "und wie viele abgeschlossen und deshalb nicht aufgeführt "
                "sind.",
                "Die Zahl der handlungsbedürftigen Fälle allein wäre "
                "irreführend — eine kurze Liste bei vielen Fällen sähe wie "
                "ein Datenfehler aus. Erst zu dritt sind die Zahlen eine "
                "Aussage.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Eigene Arbeitsrunde: von oben nach unten abarbeiten. Die "
                "Reihenfolge ist bereits die Empfehlung.",
                "Verteilen (Umfang „alle“): die Einträge mit „NICHT "
                "zugewiesen“ heraussuchen und in der Sicht „Zuweisung“ "
                "verteilen.",
                "Eine Empfehlung prüfen: die Spalte „Begründung“ lesen. Sie "
                "nennt die Signale, auf denen die Empfehlung beruht.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "Die Sicht ist REIN LESEND. Sie weist nicht zu und ändert "
                "nichts; sie schlägt vor und belegt den Vorschlag.",
                "Die Liste wird hier NICHT neu sortiert. Die Ordnung ist "
                "fest vorgegeben; eine Sortierung hier wäre eine Verzerrung der "
                "Wahrheit.",
                "Drei Zustände sind unterscheidbar: Fehler („derzeit nicht "
                "verfügbar — dies ist KEIN Leerbefund“), echter Leerbefund "
                "(„nichts zu tun“, mit der geprüften Grundgesamtheit) und "
                "Befund.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Eskalationen — was über eine Schwelle gelaufen ist.",
                "Zuweisung — der Schreibweg für die Verteilung.",
                "Meine Aufträge — dieselben Fälle aus der Sicht der "
                "Zuständigkeit.",
                "Überblick — die Kachel „Nächstbeste Aktion“ mit den "
                "vordersten Einträgen.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "nextactions.titel", "Nächstbeste Aktion",
            "Nennt je offenem Fall die nächste sinnvolle Handlung samt "
            "Begründung. Rein lesend: die Sicht schlägt vor und belegt den "
            "Vorschlag.",
            verweis="nextactions#zweck"),
        Kontexthilfe(
            "nextactions.zahlen", "Umfang und Zählzeile",
            "Nennt zuerst, wessen Aufträge hier stehen (eigene oder alle), "
            "dann alle drei Zahlen: handlungsbedürftig, Fälle insgesamt und "
            "abgeschlossen-und-deshalb-nicht-aufgeführt.",
            verweis="nextactions#zahlen"),
        Kontexthilfe(
            "nextactions.spalte.dringlichkeit", "Spalte „Dringlichkeit“",
            "Die Einstufung, nach der die Auftragsliste geordnet ist. Sie ist "
            "fest vorgegeben und wird hier nicht verändert.",
            verweis="nextactions#grenzen"),
        Kontexthilfe(
            "nextactions.spalte.fall", "Spalte „Fall“",
            "Subject-ID und Kontoname zusammen: die Nummer ist der "
            "Schlüssel, der Name das, was man wiedererkennt."),
        Kontexthilfe(
            "nextactions.spalte.handlung", "Spalte „Nächste Handlung“",
            "Der Vorschlag, was als Nächstes zu tun ist. Ein Vorschlag, keine "
            "Anweisung — die Begründung daneben macht ihn nachprüfbar.",
            verweis="nextactions#zweck"),
        Kontexthilfe(
            "nextactions.spalte.begruendung", "Spalte „Begründung“",
            "Die Signale, auf denen der Vorschlag beruht — wörtlich aus dem "
            "der Auswertung. Das ist die wichtigste Spalte dieser Sicht.",
            verweis="nextactions#zweck"),
        Kontexthilfe(
            "nextactions.spalte.ampel", "Spalte „Ampel“",
            "Die Dringlichkeits-Ampel des Falls, dieselbe wie in der "
            "Fallübersicht: ein Bearbeitungssignal, keine Bewertung des "
            "Vorwurfs.",
            verweis="faelle#ampel"),
        Kontexthilfe(
            "nextactions.spalte.status", "Spalte „Status“",
            "Der Bearbeitungsstand der Fallakte. Abgeschlossene Fälle "
            "erscheinen in dieser Liste nicht; ihre Zahl steht in der "
            "Zählzeile.",
            verweis="nextactions#zahlen"),
        Kontexthilfe(
            "nextactions.spalte.zuweisung", "Spalte „Zuweisung“",
            "WEr kümmert sich um diesen Fall? „Zugewiesen“ oder " 
            "„NICHT zugewiesen“. "
            "Letzteres ist die Aussage, auf die es in dieser Sicht ankommt."),
        Kontexthilfe(
            "nextactions.spalte.aktivitaet", "Spalte „Letzte Aktivität“",
            "Zeitpunkt des letzten Fallereignisses. Ein Gedankenstrich "
            "bedeutet: es liegt keines vor."),
    ),
)


#: Der Teilbestand dieser Nav-Gruppe, in Katalogreihenfolge
#: (dashboard, calendar, escalation, nextactions - siehe VIEW_CATALOG).
UEBERBLICK: Tuple[Sichthilfe, ...] = (
    DASHBOARD, CALENDAR, ESCALATION, NEXTACTIONS,
)
