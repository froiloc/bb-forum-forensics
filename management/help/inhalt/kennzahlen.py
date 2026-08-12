# =============================================================================
# management/help/inhalt/kennzahlen.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H11)
# =============================================================================
# Zweck:
#   Die Hilfetexte der Nav-Gruppe "Kennzahlen": stats, planung, qs, workload,
#   capacity, support.
#
#   DIE DURCHGEHENDE ZUSICHERUNG DIESER GRUPPE ist die Zweckbindung: KEIN
#   MITARBEITER-BEWERTUNGSINSTRUMENT. Vier der sechs Sichten zeigen Zahlen JE
#   PERSON - Fallzahlen, Verfuegbarkeit, Pruefergebnisse, Support-Sitzungen.
#   Genau solche Zahlen werden erfahrungsgemaess als Leistungsvergleich
#   gelesen, wenn niemand widerspricht. Deshalb widerspricht die Hilfe in
#   jedem der vier Kapitel, und zwar im ERSTEN Absatz.
#
#   DIE ZAHLEN MESSEN MENGE UND ZEIT, NICHT GUETE. Wer viele Faelle traegt,
#   arbeitet nicht besser als jemand mit wenigen; wer wenig verfuegbar ist,
#   arbeitet nicht schlechter. Diese Unterscheidung ist der Kern der Gruppe -
#   sie steht deshalb in denselben Worten in allen betroffenen Kapiteln.
#
# REGEL H-1 (Anwendersprache), REGEL H-0 (fallinhaltsfrei).
#
# Build 702 (Vorgang ff7e80ab): Das Kapitel "stats" sichert unter "Grenzen und
#   Zusicherungen" zu, dass eine nicht ermittelbare Angabe des
#   Erzeugungsvermerks als solche dasteht. _STAND bleibt 602 - er gilt fuer
#   ALLE sechs Kapitel dieser Datei, und fuenf davon sind unberuehrt (dieselbe
#   Handhabung wie in Build 698 bei ueberblick.py).
#
# Version: v0.8.602 - Build: 602 - 2026-07-31 (Ergaenzung Build 702)
# =============================================================================

from __future__ import annotations

from typing import Tuple

from management.help.modell import Abschnitt, Kontexthilfe, Sichthilfe

_STAND = 602

#: Die Zweckbindung in einem Satz - woertlich gleich in allen betroffenen
#: Kapiteln. Sie steht dort im Abschnitt "Grenzen und Zusicherungen" UND im
#: ersten Absatz; wer nur den Anfang liest, muss sie gelesen haben.
_ZWECKBINDUNG = (
    "Diese Sicht ist KEIN MITARBEITER-BEWERTUNGSINSTRUMENT. Ihre Zahlen "
    "messen Menge und Zeit, nicht Güte: Wer viele Fälle trägt, arbeitet nicht "
    "besser als jemand mit wenigen, und wer wenig verfügbar ist, arbeitet "
    "nicht schlechter."
)


#: Die Support-Historie zeigt DREI Tabellen ("Meine Sitzungen", "An meinen
#: Faellen", "Weitere Sitzungen"). Jede fuehrt eine EIGENE Kennung, weil die
#: Kennung zugleich der Schluessel der Zustandssicherung ist (Sortierung und
#: Filter je Abschnitt, Build 550). Damit tragen dieselben sieben Spalten
#: DREI verschiedene Ankerpraefixe.
#:
#: BEFUND beim Verfassen (Build 602): Texte unter dem Praefix "support"
#: waeren an keiner dieser Tabellen je erschienen - im Browser steht dort
#: "support_mine.spalte.status", nicht "support.spalte.status". Die
#: Paritaetstests nehmen den Bereich "spalte" ausdruecklich aus (er entsteht
#: erst beim Rendern), haetten den toten Bestand also nicht gemeldet. Deshalb
#: werden die Spaltentexte hier fuer alle drei Kennungen erzeugt, aus EINER
#: Quelle - drei handgepflegte Kopien waeren die naechste Driftstelle.
_SUPPORT_PRAEFIXE: Tuple[str, ...] = (
    "support_mine", "support_oncase", "support_weitere",
)

#: Feldname (bereits normiert, wie cockpit_tablekit.hilfeIdNormieren ihn
#: bildet) -> (Spaltenueberschrift, Text, Verweis oder "").
_SUPPORT_SPALTEN: Tuple[Tuple[str, str, str, str], ...] = (
    ("session_id", "Sitzung",
     "Die laufende Nummer der Unterstützungssitzung. Sie dient dem "
     "Wiederfinden und dem eindeutigen Bezug in einem Vermerk.", ""),
    ("subject_id", "Fall",
     "Der Fall, an dem unterstützt wurde. Ein leeres Feld bedeutet: die "
     "Sitzung betraf keinen bestimmten Fall.", ""),
    ("username", "Benutzername",
     "Das Benutzerkonto des Falls, an dem gearbeitet wurde — nicht die "
     "Person, die unterstützt hat.", ""),
    ("supporter", "Supporter",
     "Wer unterstützt hat. Die Spalte dient dem Auffinden der Sitzung, "
     "nicht dem Vergleich von Personen.", "support#grenzen"),
    ("started", "Start",
     "Beginn der Sitzung.", ""),
    ("ended", "Ende",
     "Ende der Sitzung. Ein leeres Feld bedeutet: die Sitzung läuft noch "
     "oder wurde nicht ordentlich beendet — nicht „Dauer null“.", ""),
    ("status", "Status",
     "Der Stand der Sitzung: laufend, beendet oder abgebrochen. Ein "
     "Abbruch ist keine Wertung, sondern eine Feststellung.", ""),
)


def _support_kontext() -> Tuple[Kontexthilfe, ...]:
    """
    Die Spalten- und Werkzeugtexte der drei Support-Tabellen.

    Der Text ist je Spalte derselbe, weil die Spalte je Abschnitt dasselbe
    bedeutet; nur der Praefix wechselt. Die Abschnittszugehoerigkeit steht in
    der Ueberschrift der Tabelle und muss nicht im Popup wiederholt werden.
    """
    raus = []
    for praefix in _SUPPORT_PRAEFIXE:
        for feld, ueberschrift, text, verweis in _SUPPORT_SPALTEN:
            raus.append(Kontexthilfe(
                "%s.spalte.%s" % (praefix, feld),
                "Spalte „%s“" % ueberschrift,
                text,
                verweis=verweis or None))
        raus.append(Kontexthilfe(
            "%s.werkzeug.filter_entfernen" % praefix, "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Tabelle auf einmal."))
        raus.append(Kontexthilfe(
            "%s.werkzeug.trefferzahl" % praefix, "Trefferanzeige",
            "Nennt, wie viele Zeilen sichtbar sind; bei gesetztem Filter "
            "„sichtbar von gesamt“."))
    return tuple(raus)


# =============================================================================
# 1) stats - "Statistiken (StA/Fuehrung)"
# =============================================================================

STATS = Sichthilfe(
    sicht="stats",
    titel="Statistiken (StA/Führung)",
    recht_klartext=(
        "Recht: stats.export_sta. Der zugeteilte Umfang entscheidet, ob die "
        "Zahlen die eigenen Fälle oder alle betreffen — er steht als Klartext "
        "in der Zeile unter der Überschrift."
    ),
    anker_praefixe=("stats", "stats_assign"),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Sicht fasst den Fallbestand in Zahlen zusammen — für "
                "Berichte an die Staatsanwaltschaft und für die eigene "
                "Führung. Sie beantwortet „wie viel liegt vor, und wie "
                "verteilt es sich?“.",
                _ZWECKBINDUNG,
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "stats.export_sta — dasselbe Recht trägt auch die Prognose "
                "und die Annotations-Statistik. Der Umfang „eigene“ macht aus "
                "der Dienststellenstatistik eine Selbstauskunft; welcher gilt, "
                "steht über den Zahlen.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter die Gesamtzahlen mit dem geltenden "
                "Umfang, darunter die Ausgabemöglichkeiten, darunter die "
                "Verteilungen nach Zustand, Priorität, Ampel und "
                "Zuständigkeit.",
            ),
        ),
        Abschnitt(
            "definitionen", "Woher die Zahlen kommen",
            (
                "Jede Kennzahl hat eine festgelegte Definition — was genau "
                "gezählt wird und worauf sich der Wert bezieht. Zwei Berichte "
                "mit derselben Kennzahl meinen dasselbe.",
                "Das ist der eigentliche Zweck einer festen Definition: Eine "
                "Zahl, die in zwei Berichten unterschiedlich zustande kommt, "
                "ist vor Gericht wertlos.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Zahlen für einen Bericht holen: Umfang prüfen, Zahlen "
                "ablesen, Ausgabe erzeugen. Die Ausgabe trägt Kopfzeile, "
                "Erzeugungsvermerk und Prüfsumme.",
                "Eine Zahl hinterfragen: die Definition der Kennzahl "
                "nachlesen, bevor sie weitergegeben wird.",
                "Eine Verteilung deuten: immer zusammen mit der Gesamtzahl. "
                "Ein Anteil ohne Grundgesamtheit ist keine Aussage.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                _ZWECKBINDUNG,
                "Die Zahlen je Zuständigkeit dienen der Verteilung von "
                "Arbeit, nicht dem Vergleich von Personen.",
                "Die Sicht ist REIN LESEND und ändert keinen Fall.",
                "Alle Zahlen gelten für den angezeigten Umfang. Wer sie "
                "weitergibt, gibt den Umfang mit weiter — sonst behauptet die "
                "Zahl mehr, als sie deckt.",
                # Build 702 (Vorgang ff7e80ab). Der Satz gehoert in die
                # ZUSICHERUNGEN und nicht in die Ablaeufe: er sagt nicht, was
                # zu tun ist, sondern worauf man sich verlassen kann - naemlich
                # darauf, dass eine fehlende Angabe im Vermerk als fehlend
                # dasteht und nicht als Wert. Vorher trug ein Bericht in dieser
                # Lage Buildnummer 0 und den Ersteller "unbekannt", und beides
                # sah aus wie eine regulaere Angabe.
                "Kann eine Angabe des Erzeugungsvermerks nicht ermittelt "
                "werden, steht in der betreffenden Zeile „nicht ermittelbar“ "
                "und darunter der Grund. Der Bericht entsteht trotzdem, und "
                "das Werkzeug sagt es beim Erzeugen. Ein Vermerk ohne solche "
                "Zeile ist vollständig.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Prognose & Gantt — dieselben Zahlen in die Zukunft gerechnet.",
                "Lastverteilung — die Verteilung auf Personen, mit "
                "Überlastwarnung.",
                "QS & Metriken — die Prüfung der Bearbeitung.",
                "Annotations-Statistik — womit gearbeitet wurde.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "stats.titel", "Statistiken (StA/Führung)",
            "Fasst den Fallbestand in Zahlen zusammen — für Berichte und für "
            "die Führung. KEIN Mitarbeiter-Bewertungsinstrument.",
            verweis="stats#grenzen"),
        Kontexthilfe(
            "stats.kennzeile", "Gesamtzahlen und Umfang",
            "Nennt die Gesamtzahlen und dahinter den geltenden Umfang — alle "
            "Fälle oder nur die eigenen. Wer eine Zahl weitergibt, gibt den "
            "Umfang mit weiter.",
            verweis="stats#grenzen"),
        Kontexthilfe(
            "stats_assign.spalte.ermittler", "Spalte „Ermittler“",
            "Die Person, der die Fälle zugewiesen sind. Die Spalte dient der "
            "Verteilung von Arbeit, nicht dem Vergleich von Personen.",
            verweis="stats#grenzen"),
        Kontexthilfe(
            "stats_assign.spalte.anzahl", "Spalte „Fälle“",
            "Wie viele Fälle dieser Person zugewiesen sind. Eine Menge, keine "
            "Bewertung: Fälle sind unterschiedlich aufwendig.",
            verweis="stats#grenzen"),
        Kontexthilfe(
            "stats_assign.werkzeug.filter_entfernen", "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Tabelle auf einmal."),
        Kontexthilfe(
            "stats_assign.werkzeug.trefferzahl", "Trefferanzeige",
            "Nennt, wie viele Zeilen sichtbar sind; bei gesetztem Filter "
            "„sichtbar von gesamt“."),

        # Build 637 (Welle B5).
        Kontexthilfe(
            "stats.bedienung.tabelle_laden", "Tabelle herunterladen",
            "Speichert die Zahlen als Tabelle zum Weiterrechnen. Der "
            "Zeitpunkt und der Zuschnitt stehen mit in der Datei — eine Zahl "
            "ohne Stichtag ist später nicht einzuordnen."),
        Kontexthilfe(
            "stats.bedienung.daten_laden", "Daten herunterladen",
            "Speichert dieselben Zahlen in maschinenlesbarer Form — für die "
            "Weitergabe an ein anderes Werkzeug."),
        Kontexthilfe(
            "stats.bedienung.reiter_verteilungen", "Reiter „Verteilungen“",
            "Wie sich der Bestand auf Zustände und Prioritäten verteilt."),
        Kontexthilfe(
            "stats.bedienung.reiter_durchsatz", "Reiter „Durchsatz“",
            "Wie viel im Zeitverlauf hinzugekommen und abgeschlossen wurde."),
        Kontexthilfe(
            "stats.bedienung.reiter_ermittler", "Reiter „Ermittler“",
            "Wie viele Fälle bei wem liegen. DAS IST EINE LASTVERTEILUNG UND "
            "KEINE LEISTUNGSMESSUNG: Fälle sind verschieden schwer, und die "
            "Zahl sagt darüber nichts.",
            verweis="stats#grenzen"),
    ),
)


# =============================================================================
# 2) planung - "Prognose & Gantt"
# =============================================================================

PLANUNG = Sichthilfe(
    sicht="planung",
    titel="Prognose & Gantt",
    recht_klartext=(
        "Recht: stats.export_sta — dasselbe wie für die Statistiken. Die "
        "Sicht ist rein auswertend."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Sicht rechnet den vorhandenen Rückstand mit der zuletzt "
                "beobachteten Abarbeitungsgeschwindigkeit in die Zukunft: "
                "„Wie lange brauchen wir bei diesem Tempo?“ Dazu ein "
                "Zeitplan, der die Vorhaben nebeneinanderstellt.",
                "Die Prognose ist ausdrücklich eine FORTSCHREIBUNG DER "
                "VERGANGENHEIT, keine Zusage. Sie hilft bei der Frage, ob "
                "eine Frist realistisch ist — sie beantwortet sie nicht.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "stats.export_sta. Die Prognose lässt sich zusätzlich als "
                "Bericht ausgeben; dafür gilt dasselbe Recht, denn der "
                "Bericht enthält keine Angabe, die die Sicht nicht ohnehin "
                "zeigt.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter Rückstand und beobachtete Rate, "
                "darunter die drei Szenarien und der Zeitplan.",
            ),
        ),
        Abschnitt(
            "szenarien", "Die drei Szenarien",
            (
                "Die Prognose wird immer in drei Szenarien gezeigt — "
                "günstig, erwartet, ungünstig — und diese Reihenfolge ist "
                "fachlich, keine Rangfolge. Sie lässt sich deshalb nicht "
                "umsortieren.",
                "Ein einzelner Wert wäre eine Scheingenauigkeit. Drei Werte "
                "zeigen die Spannweite, und die Spannweite ist die "
                "eigentliche Aussage.",
            ),
        ),
        Abschnitt(
            "belastbarkeit", "Wann keine Prognose möglich ist",
            (
                "Reichen die beobachteten Abschlüsse nicht aus, sagt die "
                "Sicht ausdrücklich „keine belastbare Prognose“ und rechnet "
                "trotzdem — sichtbar unter Vorbehalt.",
                "Der Grund: Eine Prognose aus drei Datenpunkten sieht genauso "
                "aus wie eine aus dreihundert. Der Hinweis ist der einzige "
                "Unterschied, den man sehen kann.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Machbarkeit prüfen: Rückstand und Rate lesen, dann die drei "
                "Szenarien — und zuerst nachsehen, ob die Prognose als "
                "belastbar gilt.",
                "Für eine Besprechung: den Bericht erzeugen; er enthält "
                "dieselben Zahlen samt Annahmen.",
                "Bei einer unerwarteten Zahl: die Annahmen lesen. Dort steht, "
                "was als Rückstand gilt und woraus die Rate stammt.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "EINE PROGNOSE IST KEINE ZUSAGE. Sie schreibt die "
                "Vergangenheit fort und weiß nichts von künftigen Zu- oder "
                "Abgängen, Krankheit oder neuen Fällen.",
                "Die Sicht ist KEIN Mitarbeiter-Bewertungsinstrument. Die "
                "Rate ist eine Eigenschaft der Dienststelle, nicht einer "
                "Person.",
                "Ist die Datenlage zu dünn, wird das benannt. Eine Prognose "
                "ohne diesen Hinweis zu zitieren, wäre eine Falschauskunft.",
                "Die Reihenfolge der Szenarien ist fachlich und keine "
                "Rangfolge.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Statistiken — die Zahlen, aus denen die Prognose entsteht.",
                "Kapazität — was an Arbeitszeit tatsächlich zur Verfügung "
                "steht.",
                "Lastverteilung — wie sich der Rückstand gerade verteilt.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "planung.titel", "Prognose & Gantt",
            "Rechnet den Rückstand mit der zuletzt beobachteten "
            "Geschwindigkeit in die Zukunft. Eine Fortschreibung der "
            "Vergangenheit, keine Zusage.",
            verweis="planung#grenzen"),
        Kontexthilfe(
            "planung.kennzeile", "Rückstand und Rate",
            "Nennt die Zahl der offenen Fälle und die beobachtete "
            "Abarbeitungsgeschwindigkeit. Steht hier „keine belastbare "
            "Prognose“, reichen die beobachteten Abschlüsse nicht aus — die "
            "Zahlen darunter stehen dann unter Vorbehalt.",
            verweis="planung#belastbarkeit"),
    ),
)


# =============================================================================
# 3) qs - "QS & Metriken"
# =============================================================================

QS = Sichthilfe(
    sicht="qs",
    titel="QS & Metriken",
    recht_klartext=(
        "Recht: qs.view. Wer eine Prüfung einträgt, kann damit NICHT die "
        "eigene Arbeit prüfen — der Versuch wird abgewiesen und die "
        "Abweisung angezeigt."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Sicht zieht eine Stichprobe von Fällen zur Gegenprüfung "
                "und hält fest, was die Prüfung ergeben hat. Daneben stehen "
                "Bearbeitungsmetriken — wie lange etwas dauert und woran.",
                _ZWECKBINDUNG,
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "qs.view. Das Eintragen eines Prüfergebnisses ist ein "
                "protokollierter Schreibvorgang. Die Selbstprüfung ist "
                "gesperrt: Wer den Fall bearbeitet hat, kann ihn nicht selbst "
                "als geprüft eintragen.",
            ),
        ),
        Abschnitt(
            "zweckbindung", "Die Zweckbindung",
            (
                "Ganz oben steht die Zweckbindung, wortgleich aus der "
                "Auswertung übernommen. Sie ist der Grund, aus dem eine Sicht "
                "mit Zahlen je Person überhaupt verantwortbar ist.",
                "Trägt die Antwort die Zweckbindung einmal NICHT mit, sagt "
                "die Sicht das ausdrücklich und ändert ihre Farbe. Dann ist "
                "keine Angabe dieser Sicht als Aussage über eine Person zu "
                "behandeln, bevor die Herkunft geklärt ist.",
            ),
        ),
        Abschnitt(
            "vorschlag", "Die Ziehung ist ein Vorschlag",
            (
                "Die gezogenen Fälle sind ein VORSCHLAG. Eine Abweichung ist "
                "zulässig und wird protokolliert; ein Ergebnis zu einem nicht "
                "gezogenen Fall erscheint eigens ausgewiesen.",
                "Ohne diesen Satz läse sich eine Ziehung wie eine Anweisung. "
                "Wer einen anderen Fall für prüfenswerter hält, soll ihn "
                "prüfen — nachvollziehbar, nicht heimlich.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter die Zweckbindung, darunter der "
                "Hinweis auf den Vorschlagscharakter, darunter die Ziehung "
                "mit dem Prüffortschritt und die Metriken.",
                "Der Fortschritt nennt die noch OFFENEN Prüfungen mit. Eine "
                "Ziehung, an der niemand gearbeitet hat, sähe sonst aus wie "
                "eine ohne Beanstandung.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Prüfen: einen gezogenen Fall öffnen, gegenlesen, Ergebnis "
                "eintragen.",
                "Abweichen: einen anderen Fall prüfen und das Ergebnis dazu "
                "eintragen — es wird als nicht gezogen ausgewiesen.",
                "Metriken deuten: immer zusammen mit der Fallzahl. Eine "
                "Bearbeitungsdauer über zwei Fälle ist keine Kennzahl.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                _ZWECKBINDUNG,
                "SELBSTPRÜFUNG IST GESPERRT. Wer den Fall bearbeitet hat, "
                "kann ihn nicht selbst als geprüft eintragen; der Versuch "
                "wird abgewiesen und die Abweisung angezeigt — nicht "
                "verschwiegen.",
                "Die gezogenen Fälle sind ein Vorschlag und keine Anweisung.",
                "Eine leere Liste im Fehlerfall wäre eine Falschauskunft: Sie "
                "läse sich als „nichts zu beanstanden“. Die Sicht sagt "
                "deshalb bei einem Fehler ausdrücklich, dass unbekannt ist, "
                "ob geprüft wurde.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Ermittlungsergebnis — wie weit bewertet wurde.",
                "Statistiken — die Zahlen zum Bestand.",
                "Ermittler-Betreuung — der Ort für das Gespräch über "
                "Bearbeitungsqualität.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "qs.titel", "QS & Metriken",
            "Zieht eine Stichprobe zur Gegenprüfung und hält die Ergebnisse "
            "fest. KEIN Mitarbeiter-Bewertungsinstrument.",
            verweis="qs#zweckbindung"),
        Kontexthilfe(
            "qs.zweckbindung", "Die Zweckbindung",
            "Nennt wortgleich, wozu die Zahlen dieser Sicht dienen — und "
            "wozu nicht. Trägt die Antwort die Zweckbindung nicht mit, ändert "
            "die Zeile ihre Farbe; dann ist keine Angabe als Aussage über "
            "eine Person zu behandeln.",
            verweis="qs#zweckbindung"),
        Kontexthilfe(
            "qs.vorschlag", "Vorschlagscharakter der Ziehung",
            "Die gezogenen Fälle sind ein Vorschlag. Eine Abweichung ist "
            "zulässig und wird protokolliert; ein Ergebnis zu einem nicht "
            "gezogenen Fall erscheint eigens ausgewiesen.",
            verweis="qs#vorschlag"),

        # Build 637 (Welle B5).
        Kontexthilfe(
            "qs.bedienung.ergebnis", "Prüfergebnis",
            "Wie die Prüfung dieser Fallakte ausgegangen ist. Die Auswahl "
            "erscheint nur mit dem Prüfrecht und nur an Fällen, die nicht "
            "gesperrt sind — ein Bedienelement ohne Wirkung wäre schlimmer "
            "als keines.",
            verweis="qs#rechte"),
        Kontexthilfe(
            "qs.bedienung.begruendung", "Begründung",
            "PFLICHTANGABE: was trägt und was fehlt. Ein Prüfergebnis ohne "
            "Begründung ist für die geprüfte Person keine Rückmeldung und für "
            "die Akte kein Beleg.",
            verweis="qs#zweckbindung"),
    ),
)


# =============================================================================
# 4) workload - "Lastverteilung"
# =============================================================================

WORKLOAD = Sichthilfe(
    sicht="workload",
    titel="Lastverteilung",
    recht_klartext=(
        "Recht: workload.view. Der zugeteilte Umfang entscheidet, ob Sie die "
        "Verteilung der Dienststelle oder nur die eigene Last sehen."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Sicht zeigt, wie viele aktive Fälle bei wem liegen, und "
                "warnt, wenn eine Schwelle überschritten ist. Sie beantwortet "
                "„ist die Arbeit gleichmäßig verteilt?“.",
                _ZWECKBINDUNG,
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "workload.view. Mit dem Umfang „alle“ ist es die "
                "Verteilsicht der Leitung, mit „eigene“ die Selbstauskunft.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter Umfang und Zeilenzahl, darunter die "
                "Überlastwarnung, darunter die Verteilung.",
                "Die Warnung steht VOR der Verteilung: Man soll sie lesen, "
                "bevor man die Balken deutet.",
            ),
        ),
        Abschnitt(
            "warnung", "Die Überlastwarnung",
            (
                "Die Warnung erscheint IMMER — auch wenn nichts zu warnen "
                "ist. Eine Warnung, die nur im Alarmfall existiert, lässt "
                "offen, ob gerade nichts los ist oder ob die Prüfung "
                "ausgefallen ist.",
                "Sie meldet eine Schwellenüberschreitung, keine "
                "Leistungsschwäche. Wer über der Schwelle liegt, hat zu viele "
                "Fälle — nicht zu wenig Fleiß.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Vor dem Verteilen: hier nachsehen, bevor in der Zuweisung "
                "weitere Fälle vergeben werden.",
                "Bei einer Warnung: umverteilen oder die Ursache klären — die "
                "Zahl allein sagt nicht, woran es liegt.",
                "Für ein Gespräch: die Zahlen mitnehmen, aber als Frage, "
                "nicht als Befund.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                _ZWECKBINDUNG,
                "DIE ZAHL DER FÄLLE IST KEIN AUFWANDSMASS. Ein Fall mit "
                "hunderttausend Beiträgen und einer mit zwanzig zählen hier "
                "beide als ein Fall.",
                "Die Sicht verteilt nicht. Sie zeigt die Verteilung; geändert "
                "wird sie in der Zuweisung.",
                "Die Überlastwarnung erscheint immer, auch ohne Anlass — "
                "damit ihr Fehlen nie mit ihrem Ausfall verwechselt wird.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Kapazität — was an Arbeitszeit zur Verfügung steht.",
                "Zuweisung — wo umverteilt wird.",
                "Statistiken — die Verteilung im Zusammenhang des Bestands.",
                "Eskalationen — was bereits über eine Schwelle gelaufen ist.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "workload.titel", "Lastverteilung",
            "Zeigt, wie viele aktive Fälle bei wem liegen, und warnt bei "
            "Überschreitung einer Schwelle. KEIN "
            "Mitarbeiter-Bewertungsinstrument.",
            verweis="workload#grenzen"),
        Kontexthilfe(
            "workload.kennzeile", "Umfang und Zeilenzahl",
            "Nennt den geltenden Umfang und die Zahl der Zeilen. Bei "
            "„eigene“ ist die Sicht eine Selbstauskunft und keine Verteilsicht "
            "— eine kurze Liste ist dann kein Befund.",
            verweis="workload#rechte"),
    ),
)


# =============================================================================
# 5) capacity - "Kapazitaet"
# =============================================================================

CAPACITY = Sichthilfe(
    sicht="capacity",
    titel="Kapazität",
    recht_klartext=(
        "Recht: capacity.edit. Dasselbe Recht trägt die Kapazitätspflege; "
        "den Unterschied macht der zugeteilte Umfang — „alle“ für alle "
        "Personen, „eigene“ für die Selbstpflege."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Sicht zeigt, wie viel Arbeitszeit im gewählten Zeitraum "
                "tatsächlich zur Verfügung steht — nach Abzug von Urlaub, "
                "Krankheit, Schulung und Feiertagen. Sie beantwortet „womit "
                "können wir rechnen?“.",
                _ZWECKBINDUNG,
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "capacity.edit. Diese Sicht ist die AUSWERTUNG; die "
                "Eingangsdaten werden in der Kapazitätspflege gepflegt.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter Umfang, Personenzahl und Zeitraum, "
                "darunter die Zeitraumwahl und die Verteilung je Person.",
            ),
        ),
        Abschnitt(
            "basis_netto", "Regelarbeitszeit und verfügbare Zeit",
            (
                "Zwei Werte je Person: die Regelarbeitszeit im Zeitraum und "
                "die davon tatsächlich verfügbare Zeit. Die Einfärbung folgt "
                "dem Verhältnis der beiden.",
                "Fehlt die Regelarbeitszeit, wird das ausgewiesen und nicht "
                "als Null gerechnet. Eine Null sähe aus wie eine Feststellung "
                "und wäre das Gegenteil davon.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Planen: Zeitraum wählen, verfügbare Zeit ablesen, mit dem "
                "Rückstand aus der Prognose vergleichen.",
                "Eine Auffälligkeit klären: eine stark verringerte "
                "Verfügbarkeit hat einen Grund — er steht in der "
                "Kapazitätspflege, nicht hier.",
                "Fehlt eine Regelarbeitszeit: in der Kapazitätspflege "
                "nachtragen. Bis dahin ist für diese Person keine Aussage "
                "möglich.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                _ZWECKBINDUNG,
                "VERFÜGBARKEIT IST KEINE LEISTUNG. Wer wenig verfügbar ist, "
                "arbeitet nicht schlechter — er ist im Urlaub, krank oder auf "
                "Schulung.",
                "Die Sicht rechnet ZEIT, nicht Arbeitsergebnisse. Sie sagt "
                "nichts darüber, was in dieser Zeit geschafft wurde.",
                "Eine fehlende Regelarbeitszeit wird ausgewiesen und nicht "
                "als Null gerechnet.",
                "Die Sicht ist REIN LESEND; gepflegt wird in der "
                "Kapazitätspflege.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Kapazitätspflege — wo Arbeitszeit und Abwesenheiten "
                "eingetragen werden.",
                "Lastverteilung — wie viele Fälle auf diese Zeit treffen.",
                "Prognose & Gantt — was daraus für die Termine folgt.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "capacity.titel", "Kapazität",
            "Zeigt, wie viel Arbeitszeit im gewählten Zeitraum zur Verfügung "
            "steht. Verfügbarkeit ist keine Leistung.",
            verweis="capacity#grenzen"),
        Kontexthilfe(
            "capacity.kennzeile", "Umfang, Personenzahl und Zeitraum",
            "Nennt den geltenden Umfang, wie viele Personen eingehen und für "
            "welchen Zeitraum gerechnet wurde. Ohne den Zeitraum ist jede "
            "Stundenzahl darunter nicht einzuordnen.",
            verweis="capacity#basis_netto"),

        # Build 637 (Welle B5).
        Kontexthilfe(
            "capacity.bedienung.von", "Zeitraum von",
            "Der erste Tag des ausgewerteten Zeitraums. Er wirkt erst mit "
            "„Aktualisieren“."),
        Kontexthilfe(
            "capacity.bedienung.bis", "Zeitraum bis",
            "Der letzte Tag des ausgewerteten Zeitraums. Ein sehr kurzer "
            "Zeitraum trifft leicht eine einzelne Abwesenheit und verzerrt "
            "das Bild. Der Kalender lässt hier kein Datum VOR dem Von-Datum "
            "zu. Vorbelegt wird das Feld ABSICHTLICH "
            "nicht: bliebe es leer und spränge auf das Von-Datum, schrumpfte "
            "die Auswertung unbemerkt auf einen einzigen Tag.",
            verweis="capacity#grenzen"),
        Kontexthilfe(
            "capacity.bedienung.aktualisieren", "Aktualisieren",
            "Berechnet die Kapazität für den eingestellten Zeitraum neu. Bis "
            "dahin gilt der Zeitraum, der oben genannt ist."),
    ),
)


# =============================================================================
# 6) support - "Support-Historie"
# =============================================================================

SUPPORT = Sichthilfe(
    sicht="support",
    titel="Support-Historie",
    recht_klartext=(
        "Recht: support_history.view. Mit dem Umfang „alle“ sehen Sie alle "
        "Sitzungen, sonst die eigenen und die an eigenen Fällen."
    ),
    anker_praefixe=("support",) + _SUPPORT_PRAEFIXE,
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Sicht führt Buch darüber, wann jemand bei der "
                "Bearbeitung eines Falls unterstützt wurde: wer, wann, wie "
                "lange und woran.",
                _ZWECKBINDUNG,
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "support_history.view. Der Umfang „alle“ zeigt die Sitzungen "
                "der Dienststelle; ohne ihn sehen Sie die eigenen und die an "
                "Ihren Fällen — beides ist Ihre eigene Arbeitslage.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter der geltende Umfang, darunter die "
                "Sitzungen. Ein Klick auf eine Zeile öffnet die Einzelheiten.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Nachvollziehen: eine Zeile anklicken und die Einzelheiten "
                "der Sitzung lesen.",
                "Bedarf erkennen: häufen sich Sitzungen zu einem Thema, "
                "fehlt vermutlich eine Erklärung — nicht Können.",
                "Für die Betreuung: die Historie als Gesprächsgrundlage "
                "nehmen, nicht als Bewertung.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                _ZWECKBINDUNG,
                "UM HILFE ZU BITTEN IST KEIN MANGEL. Viele Sitzungen können "
                "bedeuten, dass jemand sorgfältig arbeitet und im Zweifel "
                "nachfragt — und sie können bedeuten, dass eine Erklärung "
                "fehlt. Was von beidem zutrifft, sagt keine Zahl.",
                "Die Sicht ist REIN LESEND.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Ermittler-Betreuung — der Ort für das Gespräch.",
                "Betreuungs-Notizen — was dabei festgehalten wird.",
                "Onboarding / Offboarding — die Einarbeitung.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "support.titel", "Support-Historie",
            "Führt Buch über die Unterstützung bei der Fallbearbeitung: wer, "
            "wann, wie lange, woran. KEIN Mitarbeiter-Bewertungsinstrument.",
            verweis="support#grenzen"),
        Kontexthilfe(
            "support.kennzeile", "Umfang und Bedienhinweis",
            "Nennt, welche Sitzungen Ihnen angezeigt werden, und weist "
            "darauf hin, dass eine Zeile die Einzelheiten öffnet.",
            verweis="support#rechte"),
        # Build 637 (Welle B5).
        Kontexthilfe(
            "support.bedienung.dialog_zu", "Schließen",
            "Schließt die Sitzungs-Details. Es wird nichts geändert; die "
            "Sitzung bleibt davon unberührt."),
    ) + _support_kontext(),
)


#: Der Teilbestand dieser Nav-Gruppe, in Katalogreihenfolge
#: (stats, planung, qs, workload, capacity, support - siehe VIEW_CATALOG).
KENNZAHLEN: Tuple[Sichthilfe, ...] = (
    STATS, PLANUNG, QS, WORKLOAD, CAPACITY, SUPPORT,
)
