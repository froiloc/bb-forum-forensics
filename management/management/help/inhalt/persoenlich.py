# =============================================================================
# management/help/inhalt/persoenlich.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H8)
# =============================================================================
# Zweck:
#   Die Hilfetexte der Nav-Gruppe "Persoenlich": mycases, myhistory,
#   viewprefs.
#
#   DIE DREI SICHTEN HABEN EINES GEMEINSAM: sie zeigen ausschliesslich das
#   EIGENE. "Meine Auftraege" die eigenen Zuweisungen, "Meine Historie" die
#   eigenen Belege, "Ansicht anpassen" die eigene Oberflaeche. Deshalb steht
#   in jedem der drei Kapitel ausdruecklich, was dort NICHT zu finden ist -
#   wer die Arbeit anderer sucht, soll nicht erst durch Ausprobieren merken,
#   dass er hier falsch ist.
#
#   'viewprefs' ist ausserdem die EINZIGE Sicht ohne Rechtepruefung
#   (cockpit.js:337-348) und damit das einzige Kapitel, das JEDE Person in der
#   Vollhilfe sieht - auch ohne jedes Recht. Das ist bei der Formulierung zu
#   beachten: dieses Kapitel darf nichts voraussetzen.
#
# QUELLEN: cockpit_mycases.js, cockpit_myhistory.js, cockpit_viewprefs.js,
#   management/viewprefs/viewpref_katalog.py, cockpit.js (VIEW_CATALOG).
#
# REGEL H-0: kein Falldatum, keine echte Kennung.
#
# Version: v0.8.596 - Build: 596 - 2026-07-31
# =============================================================================

from __future__ import annotations

from typing import Tuple

from management.help.modell import Abschnitt, Kontexthilfe, Sichthilfe

_STAND = 596


MYCASES = Sichthilfe(
    sicht="mycases",
    titel="Meine Aufträge",
    recht_klartext=(
        "Recht: mycases.view. Die Sicht zeigt ausschließlich Fälle, die IHNEM "
        "Konto zugewiesen sind — unabhängig vom Scope. Sie ist damit die "
        "einzige Fallliste, deren Umfang nicht von einer Rechteeinstellung "
        "abhängt, sondern von der Zuweisung."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "„Meine Aufträge“ ist die eigene Arbeitsliste: alle Fälle, für "
                "die Sie zuständig sind, mit Ampel, Priorität und Inaktivität. "
                "Sie beantwortet „was liegt bei mir?“ — nicht „was liegt an?“.",
                "Die Sicht ist bewusst kurz gehalten. Sie soll die eigene "
                "Zuständigkeit zeigen und nicht dazu verleiten, den "
                "Gesamtbestand zu überblicken; dafür gibt es die "
                "Fallübersicht.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "mycases.view. Der Umfang ergibt sich aus der Zuweisung, "
                "nicht aus einem Scope: Sie sehen hier Ihre Fälle, und nur "
                "die. Auch eine Leitung mit Scope „alle“ sieht in DIESER "
                "Sicht ausschließlich ihre eigenen Zuweisungen.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter die Tabelle mit Kopffiltern und der "
                "Werkzeugleiste. Die letzte Spalte trägt den Knopf, mit dem "
                "ein Fall gestartet wird.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Tagesbeginn: nach Ampel sortieren und von oben abarbeiten.",
                "Einen Fall aufnehmen: „Fall starten“ in der Aktionsspalte. "
                "Der Knopf deaktiviert sich beim Klick selbst — ein "
                "Doppelklick startet nicht zweimal.",
                "Liegengebliebenes erkennen: nach „Inaktiv (Tage)“ absteigend "
                "sortieren.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "Die Sicht zeigt NUR eigene Zuweisungen. Wer die Arbeit "
                "anderer sucht, ist hier falsch — dafür gibt es die "
                "Fallübersicht und die Lastverteilung.",
                "Die Sicht weist nicht zu. Sie können hier keinen Fall "
                "annehmen, der Ihnen nicht zugewiesen wurde.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Meine Historie — die eigenen Belege zu diesen Fällen.",
                "Fallübersicht — der Gesamtbestand.",
                "Nächstbeste Aktion — dieselben Fälle, nach Handlung "
                "geordnet.",
                "Zuweisung — wo Zuständigkeiten geändert werden.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "mycases.spalte.subject_id", "Spalte „Fall (subject_id)“",
            "Der Ermittlungsschlüssel der Fallakte. Dieselbe Spalte trägt in "
            "der letzten Position den Knopf „Fall starten“."),
        Kontexthilfe(
            "mycases.spalte.username", "Spalte „Benutzername“",
            "Der im Forum geführte Kontoname — der Name, den man eher "
            "wiedererkennt als die Nummer."),
        Kontexthilfe(
            "mycases.spalte.status", "Spalte „Status“",
            "Der Bearbeitungsstand der Fallakte: offen, in Bearbeitung, "
            "freigegeben oder abgeschlossen."),
        Kontexthilfe(
            "mycases.spalte.priority", "Spalte „Prio“",
            "Die Prioritätsstufe von 1 (höchste) bis 5 (niedrigste). Sie "
            "wird in der Sicht „Zuweisung“ gesetzt."),
        Kontexthilfe(
            "mycases.spalte.ampel", "Spalte „Ampel“",
            "Die Dringlichkeits-Ampel: ein Bearbeitungssignal aus "
            "Inaktivität und Zuweisungslage, keine Bewertung des Vorwurfs.",
            verweis="faelle#ampel"),
        Kontexthilfe(
            "mycases.spalte.event_count", "Spalte „Ereignisse“",
            "Anzahl der protokollierten Fallereignisse. Ein Aktivitäts-, "
            "kein Ergebnismaß."),
        Kontexthilfe(
            "mycases.spalte.has_note", "Spalte „Notiz“",
            "Zeigt an, ob zum Fall eine Betreuungsnotiz vorliegt. Den Inhalt "
            "führt die Sicht „Betreuungs-Notizen“."),
        Kontexthilfe(
            "mycases.spalte.since_days", "Spalte „Inaktiv (Tage)“",
            "Tage seit dem letzten Fallereignis. Aus diesem Wert speist sich "
            "die Ampel.",
            verweis="faelle#ampel"),
        Kontexthilfe(
            "mycases.werkzeug.filter_entfernen", "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Sicht auf einmal."),
        Kontexthilfe(
            "mycases.werkzeug.trefferzahl", "Trefferanzeige",
            "Nennt, wie viele Zeilen sichtbar sind; bei gesetztem Filter "
            "„sichtbar von gesamt“."),
    ),
)


MYHISTORY = Sichthilfe(
    sicht="myhistory",
    titel="Meine Historie",
    recht_klartext=(
        "Recht: myhistory.view. Die Sicht zeigt ausschließlich die Belege, "
        "die auf IHRE Kennung geschrieben wurden. Sie ist eine Lesart des "
        "Protokollbuchs, kein zweiter Bestand."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Jede schreibende Handlung im Werkzeug erzeugt einen Beleg im "
                "Protokollbuch. Diese Sicht zeigt die eigenen — in der "
                "Reihenfolge, in der sie entstanden sind.",
                "Der Zweck ist Nachvollziehbarkeit in beide Richtungen: Sie "
                "können belegen, was Sie getan haben, und Sie können "
                "nachsehen, was Sie getan haben. Beides ist in einem "
                "forensischen Verfahren regelmäßig gefragt.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "myhistory.view. Die Sicht ist auf die eigene Kennung "
                "festgelegt; es gibt keinen Weg, über sie fremde Belege zu "
                "lesen. Wer das darf, benutzt den Audit-Explorer.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter die Tabelle mit Kopffiltern. Jede "
                "Zeile ist ein Beleg mit laufender Nummer, Zeitpunkt, "
                "Ereignisart, Ziel und Herkunft.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Nachweisen, wann etwas geschah: nach Ereignisart filtern und "
                "die Belegnummer notieren.",
                "Eine eigene Änderung wiederfinden: nach dem Ziel filtern "
                "(etwa der Subject-ID) und die Zeitspalte lesen.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "Die Sicht ist REIN LESEND und zeigt nur EIGENE Belege. Sie "
                "kann nichts löschen und nichts ändern — das Protokollbuch "
                "ist eine Hash-Kette; ein nachträglich veränderter Eintrag "
                "würde die Kettenprüfung brechen.",
                "Eine leere Liste heißt: es liegt kein Beleg auf Ihre "
                "Kennung vor. Sie heißt nicht, dass das Protokollbuch leer "
                "ist.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Audit-Explorer — dieselbe Quelle, ohne die Beschränkung auf "
                "die eigene Kennung (Recht ops.view).",
                "Integrität / Betrieb — der Zustand der Hash-Kette.",
                "Übergabe-Protokoll — die Lesart derselben Kette entlang der "
                "Zuständigkeitswechsel.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "myhistory.spalte.seq", "Spalte „Beleg (seq)“",
            "Die laufende Nummer des Belegs im Protokollbuch. Sie ist "
            "lückenlos und aufsteigend — eine Lücke wäre ein Befund und "
            "würde die Kettenprüfung brechen."),
        Kontexthilfe(
            "myhistory.spalte.zeit", "Spalte „Zeit“",
            "Zeitpunkt der Handlung, wie er beim Schreiben festgehalten "
            "wurde. Er stammt aus dem Beleg, nicht aus der Anzeige."),
        Kontexthilfe(
            "myhistory.spalte.event_type", "Spalte „Ereignis“",
            "Die Art der Handlung, etwa eine Zuweisung oder eine Freigabe. "
            "Das Vokabular ist festgelegt; ein unbekannter Wert wäre ein "
            "Befund."),
        Kontexthilfe(
            "myhistory.spalte.ziel", "Spalte „Ziel“",
            "Worauf sich die Handlung bezog — meist eine Fallakte oder eine "
            "Person."),
        Kontexthilfe(
            "myhistory.spalte.herkunft", "Spalte „Herkunft“",
            "Über welchen Weg die Handlung erfolgte (Oberfläche oder "
            "Kommandozeile). Für die Nachvollziehbarkeit ist das ein "
            "Unterschied."),
        Kontexthilfe(
            "myhistory.werkzeug.filter_entfernen", "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Sicht auf einmal."),
        Kontexthilfe(
            "myhistory.werkzeug.trefferzahl", "Trefferanzeige",
            "Nennt, wie viele Belege sichtbar sind; bei gesetztem Filter "
            "„sichtbar von gesamt“."),
    ),
)


VIEWPREFS = Sichthilfe(
    sicht="viewprefs",
    titel="Ansicht anpassen",
    recht_klartext=(
        "KEIN Recht nötig. Dies ist die einzige Sicht des Werkzeugs ohne "
        "Rechteprüfung, und das ist Absicht: Sie zeigt keine Fall- und keine "
        "Personendaten, sondern nur Ihre eigene Einrichtung. Hinge sie an "
        "einem Recht, müsste dieses erst jemand erteilen — und bis dahin käme "
        "niemand an seine eigenen Einstellungen. Ein Recht, das man niemandem "
        "sinnvoll vorenthalten kann, ist keines."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Hier stellen Sie ein, welche Bereiche in der linken "
                "Navigation erscheinen und in welcher Reihenfolge — Gruppen "
                "untereinander, Bereiche innerhalb ihrer Gruppe. Die "
                "Einstellung gilt nur für Ihr Konto.",
                "Ein Werkzeug mit 43 Bereichen ist für niemanden in voller "
                "Breite Alltag. Wer täglich mit fünf davon arbeitet, soll die "
                "fünf oben haben.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "Diese Sicht braucht kein Recht. Sie kann aber auch keines "
                "verschaffen: Die Einstellung ORDNET und BLENDET AUS — sie "
                "kann nichts einblenden, wofür Ihnen das Recht fehlt. Der "
                "Rechtefilter läuft ZULETZT, nach Ihrer Vorliebe. Wird ein "
                "Recht später entzogen, verschwindet der Bereich trotz "
                "gespeicherter Vorliebe.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, Hinweis, darunter die Liste der Gruppen und "
                "Bereiche zum Ziehen und Abwählen.",
                "„Ansicht anpassen“ selbst lässt sich nicht ausblenden — wer "
                "sie wegstellen könnte, mauerte sich den Rückweg zu.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Ordnen: die häufig gebrauchten Bereiche nach oben ziehen.",
                "Ausblenden: den Haken bei Bereichen entfernen, die Sie nicht "
                "brauchen. Sie sind damit nicht gesperrt, nur nicht im Weg.",
                "Zurücksetzen: die Vorliebe verwerfen und zur "
                "Werkseinstellung zurückkehren.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "Die Einstellung gilt NUR FÜR SIE. Sie ändert nichts an dem, "
                "was andere sehen, und nichts an Rechten.",
                "Ausblenden ist kein Entziehen. Ein ausgeblendeter Bereich "
                "bleibt erreichbar — etwa über die Kommandopalette (Strg+K).",
                "Ungespeicherte Änderungen: Wenn Sie die Sicht mit offenen "
                "Änderungen verlassen, fragt das Werkzeug nach. Der "
                "Zwischenstand bleibt zusätzlich im Browser erhalten und wird "
                "beim nächsten Aufruf wiederhergestellt.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Dashboard — dieselbe Einstelllogik für die Kachelfläche.",
                "Rechte / Policy — was Ihnen tatsächlich zugeteilt ist.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "viewprefs.titel", "Ansicht anpassen",
            "Stellt Reihenfolge und Sichtbarkeit der Bereiche in der linken "
            "Navigation ein. Gilt nur für Ihr Konto und ändert keine Rechte.",
            verweis="viewprefs#zweck"),
        Kontexthilfe(
            "viewprefs.hinweis", "Was hier eingestellt wird",
            "Gruppen werden untereinander geordnet, Bereiche innerhalb ihrer "
            "Gruppe. Ausblenden heißt nicht sperren: ein ausgeblendeter "
            "Bereich bleibt über die Kommandopalette erreichbar.",
            verweis="viewprefs#grenzen"),
    ),
)


#: Der Teilbestand dieser Nav-Gruppe, in Katalogreihenfolge
#: (mycases, myhistory, viewprefs - siehe VIEW_CATALOG).
PERSOENLICH: Tuple[Sichthilfe, ...] = (MYCASES, MYHISTORY, VIEWPREFS)
