# =============================================================================
# management/help/inhalt/betreuung.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H12)
# =============================================================================
# Zweck:
#   Die Hilfetexte der Nav-Gruppe "Betreuung": mentoring, notes, onboarding.
#
#   WAS DIESE DREI SICHTEN VERBINDET: sie handeln von MENSCHEN, nicht von
#   Faellen. Damit stellt sich in jedem der drei Kapitel dieselbe Frage - wozu
#   die Angaben da sind und wozu ausdruecklich nicht. Eine Pinnwand mit
#   Merkzetteln ueber Kolleginnen und Kollegen, eine Liste laufender
#   Unterstuetzungen und eine Checkliste zum Ein- und Austritt lassen sich
#   allesamt als Personalbeurteilung missverstehen. Sie sind keine, und das
#   steht in jedem Kapitel - im ersten Absatz, nicht erst unter "Grenzen".
#
#   DIE HEIKELSTE STELLE dieser Gruppe ist die Notiz-Pinnwand. Sie nimmt
#   FREITEXT ueber namentlich benannte Personen auf. Deshalb sagt ihr Kapitel
#   ausdruecklich, dass eine Notiz ein Merkzettel ist und keine Personalakte,
#   und dass alles, was dienstrechtliche Bedeutung hat, in das dafuer
#   vorgesehene Verfahren gehoert und nicht auf eine Pinnwand.
#
# QUELLEN: cockpit_mentoring.js, cockpit_notes.js, cockpit_onboarding.js,
#   management/server/management_app.py (Rechte, Umfaenge).
#
# REGEL H-0: kein Falldatum, keine echte Kennung.
# REGEL H-1: Anwendersprache.
#
# Version: v0.8.603 - Build: 603 - 2026-07-31
# =============================================================================

from __future__ import annotations

from typing import Tuple

from management.help.modell import Abschnitt, Kontexthilfe, Sichthilfe

_STAND = 603

#: Die Zweckbindung dieser Gruppe, wortgleich in allen drei Kapiteln. Sie ist
#: die Schwester der Zweckbindung aus der Gruppe "Kennzahlen" - dort ging es um
#: Zahlen je Person, hier um Aufzeichnungen ueber Personen.
_ZWECKBINDUNG = (
    "Diese Sicht dient der UNTERSTUETZUNG von Kolleginnen und Kollegen und "
    "ist KEINE PERSONALBEURTEILUNG. Was hier steht, sagt nichts über die Güte "
    "der Arbeit einer Person aus."
)


# =============================================================================
# 1) mentoring - "Ermittler-Betreuung"
# =============================================================================

MENTORING = Sichthilfe(
    sicht="mentoring",
    titel="Ermittler-Betreuung",
    recht_klartext=(
        "Recht: mentoring.view. Die Sicht zeigt die gerade laufenden "
        "Unterstützungssitzungen — nicht die abgeschlossenen."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Sicht zeigt, wer im Augenblick bei der Fallbearbeitung "
                "unterstützt wird: an welchem Fall, durch wen, seit wann.",
                "Ihr eigentlicher Zweck ist die zweite Spalte der Anzeige: "
                "sie macht sichtbar, wo eine Unterstützung angefangen hat und "
                "dann liegengeblieben ist. Eine Sitzung, von der seit "
                "geraumer Zeit kein Lebenszeichen mehr eingegangen ist, wird "
                "hervorgehoben. Ohne diese Anzeige fiele so etwas erst auf, "
                "wenn jemand nachfragt.",
                _ZWECKBINDUNG,
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "mentoring.view. Wer das Recht hat, sieht alle laufenden "
                "Sitzungen der Dienststelle; ein eingeschränkter Umfang ist "
                "hier nicht vorgesehen, weil eine Betreuungslage, die nur zur "
                "Hälfte sichtbar ist, ihren Zweck verfehlt.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter eine Zeile mit der Zahl der laufenden "
                "Sitzungen und der Zahl der betreuungsbedürftigen. Darunter "
                "die Liste.",
                "Betreuungsbedürftige Zeilen sind farblich hinterlegt. Die "
                "Anzeige aktualisiert sich von selbst — Sie müssen die Seite "
                "nicht neu laden.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Rundgang: die hervorgehobenen Zeilen durchgehen und "
                "nachfragen, ob noch Unterstützung gebraucht wird.",
                "Dauer einschätzen: die Spalte „Laufzeit“ sagt, wie lange die "
                "Sitzung schon offen ist.",
                "Herrenlose Sitzungen finden: steht bei „Supporter“ das Wort "
                "„herrenlos“, ist keine unterstützende Person hinterlegt — "
                "dann ist zu klären, wer sich kümmert.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                _ZWECKBINDUNG,
                "„STALE“ HEISST NICHT „UNTÄTIG“. Der Hinweis bedeutet nur, "
                "dass seit einer festgelegten Zeit kein Lebenszeichen dieser "
                "Sitzung eingegangen ist. Das kann eine Besprechung sein, "
                "ein gesperrter Bildschirm oder eine Sitzung, die zu beenden "
                "jemand vergessen hat. Was zutrifft, sagt nur ein Gespräch.",
                "Die Sicht zeigt AUSSCHLIESSLICH laufende Sitzungen. Was "
                "abgeschlossen ist, steht in der Support-Historie; eine leere "
                "Liste hier heißt „gerade läuft nichts“ und nicht „es gab "
                "nichts“.",
                "Die Sicht ist REIN LESEND. Sie beendet keine Sitzung und "
                "benachrichtigt niemanden.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Support-Historie — die abgeschlossenen Sitzungen.",
                "Betreuungs-Notizen — was aus einem Gespräch festgehalten "
                "wird.",
                "Onboarding / Offboarding — die Einarbeitung.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "mentoring.titel", "Ermittler-Betreuung",
            "Zeigt die gerade laufenden Unterstützungssitzungen und hebt die "
            "hervor, von denen seit längerem kein Lebenszeichen kam.",
            verweis="mentoring#zweck"),
        Kontexthilfe(
            "mentoring.kennzeile", "Zahl der Sitzungen",
            "Nennt, wie viele Sitzungen laufen und wie viele davon "
            "betreuungsbedürftig sind. Die Anzeige aktualisiert sich von "
            "selbst.",
            verweis="mentoring#aufbau"),
        Kontexthilfe(
            "mentoring.spalte.id", "Spalte „Sitzung“",
            "Die laufende Nummer der Sitzung. Sie dient dem eindeutigen "
            "Bezug, etwa in einem Vermerk."),
        Kontexthilfe(
            "mentoring.spalte.subject_id", "Spalte „Fall“",
            "Der Fall, an dem gerade gearbeitet wird."),
        Kontexthilfe(
            "mentoring.spalte.username", "Spalte „Benutzername“",
            "Das Forenkonto, um das es in diesem Fall geht — nicht die "
            "Person, die unterstützt wird."),
        Kontexthilfe(
            "mentoring.spalte.supporter", "Spalte „Supporter“",
            "Wer unterstützt. Steht hier „herrenlos“, ist keine "
            "unterstützende Person hinterlegt.",
            verweis="mentoring#ablaeufe"),
        Kontexthilfe(
            "mentoring.spalte.laufzeit", "Spalte „Laufzeit“",
            "Wie lange die Sitzung schon offen ist. Eine lange Laufzeit ist "
            "kein Befund für sich — sie ist ein Anlass nachzufragen."),
        Kontexthilfe(
            "mentoring.spalte.heartbeat", "Spalte „Letzter Heartbeat“",
            "Wie lange das letzte Lebenszeichen dieser Sitzung her ist. "
            "Daraus ergibt sich der Status.",
            verweis="mentoring#grenzen"),
        Kontexthilfe(
            "mentoring.spalte.status", "Spalte „Status“",
            "„live“ heißt: es kommen Lebenszeichen. „stale (Betreuung!)“ "
            "heißt: seit einer festgelegten Zeit kam keines mehr — nicht, "
            "dass jemand untätig ist.",
            verweis="mentoring#grenzen"),
        Kontexthilfe(
            "mentoring.werkzeug.filter_entfernen", "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Sicht auf einmal."),
        Kontexthilfe(
            "mentoring.werkzeug.trefferzahl", "Trefferanzeige",
            "Nennt, wie viele Zeilen sichtbar sind; bei gesetztem Filter "
            "„sichtbar von gesamt“."),
    ),
)


# =============================================================================
# 2) notes - "Betreuungs-Notizen"
# =============================================================================

NOTES = Sichthilfe(
    sicht="notes",
    titel="Betreuungs-Notizen",
    recht_klartext=(
        "Rechte: mentoring_notes.view zum Lesen, mentoring_notes.edit zum "
        "Pflegen. Mit dem Umfang „alle“ sehen und pflegen Sie auch die "
        "Pinnwand anderer — etwa in Vertretung; sonst nur die eigene."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Sicht ist eine Pinnwand für Merkzettel: „daran denken“, "
                "„nachfragen“, „beim nächsten Gespräch ansprechen“. Sie "
                "ersetzt den Zettel am Bildschirmrand, der verloren geht.",
                "Jede Karte ist aufgebaut wie eine kurze Mitteilung: die "
                "ERSTE ZEILE ist die Überschrift und immer sichtbar, alles "
                "Weitere erscheint erst beim Aufklappen. So bleibt die "
                "Pinnwand lesbar, auch wenn auf einer Karte viel steht.",
                _ZWECKBINDUNG,
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "mentoring_notes.view zum Lesen, mentoring_notes.edit zum "
                "Anlegen und Ändern. Der Umfang „alle“ erlaubt den Blick auf "
                "fremde Pinnwände und das Pflegen in Vertretung; ohne ihn "
                "sehen Sie ausschließlich die eigene.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Oben der Titel, die Rückmeldung des letzten Vorgangs sowie "
                "die Knöpfe „Archiv ansehen“ und „+ Neue Notiz“. Darunter die "
                "Leiste zum Suchen und Filtern (Farbe, Status, Schlagwort), "
                "dann die Karten.",
                "Unter den Karten stehen zwei Zeilen: wie viele Karten der "
                "Filter gerade durchlässt, und ob sich die Karten ordnen "
                "lassen.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Anlegen: „+ Neue Notiz“. In die erste Zeile die "
                "Überschrift, darunter die Einzelheiten. Farbe und "
                "Schlagworte sind frei wählbar.",
                "Abhaken: der Haken links auf der Karte schaltet zwischen "
                "„offen“ und „erledigt“.",
                "Wichtiges oben halten: „Anheften“. Angeheftete Karten "
                "stehen immer zuerst.",
                "Ordnen: Karten am Griff ziehen oder die Pfeile ▲▼ benutzen. "
                "Das geht nur, wenn keine Suche und kein Filter gesetzt ist "
                "und genau eine Pinnwand angezeigt wird.",
                "Aus dem Weg räumen: „Archivieren“. Über „Archiv ansehen“ "
                "kommt die Karte zurück.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "EINE NOTIZ IST EIN MERKZETTEL UND KEINE PERSONALAKTE. Was "
                "dienstrechtliche Bedeutung hat, gehört in das dafür "
                "vorgesehene Verfahren und nicht auf eine Pinnwand. Bitte "
                "formulieren Sie jede Karte so, dass die betroffene Person "
                "sie lesen könnte.",
                "SUCHE UND FILTER ARBEITEN NUR AUF DEM, WAS GERADE ANGEZEIGT "
                "WIRD. Wer im aktiven Bereich sucht, durchsucht das Archiv "
                "nicht mit — dafür ist zuerst auf „Archiv ansehen“ zu "
                "wechseln.",
                "ORDNEN IST GESPERRT, SOLANGE EIN AUSSCHNITT ANGEZEIGT WIRD. "
                "Das ist Absicht: eine Reihenfolge, die nur die sichtbaren "
                "Karten kennt, würde die ausgeblendeten stillschweigend "
                "verschieben. Die Zeile unter den Karten sagt jeweils, "
                "warum es gerade nicht geht.",
                "ARCHIVIEREN LÖSCHT NICHT. Die Karte bleibt erhalten und "
                "lässt sich wiederherstellen.",
                _ZWECKBINDUNG,
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Ermittler-Betreuung — wer gerade unterstützt wird.",
                "Support-Historie — was schon unterstützt wurde.",
                "Onboarding / Offboarding — die Schritte bei Ein- und "
                "Austritt.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "notes.titel", "Betreuungs-Notizen",
            "Die Pinnwand für Merkzettel zur Betreuung. Erste Zeile einer "
            "Karte ist die Überschrift, alles Weitere klappt auf.",
            verweis="notes#zweck"),
        Kontexthilfe(
            "notes.kennzeile", "Wie viele Karten angezeigt werden",
            "Nennt, wie viele der vorhandenen Karten Suche und Filter gerade "
            "durchlassen — damit ein Ausschnitt nicht wie der ganze Bestand "
            "aussieht.",
            verweis="notes#grenzen"),
        Kontexthilfe(
            "notes.ordnungshinweis", "Hinweis zum Ordnen",
            "Sagt, ob sich die Karten gerade ziehen lassen — und wenn nicht, "
            "warum: bei gesetztem Filter oder bei mehreren Pinnwänden "
            "zugleich wäre die neue Reihenfolge unvollständig.",
            verweis="notes#grenzen"),
    ),
)


# =============================================================================
# 3) onboarding - "Onboarding / Offboarding"
# =============================================================================

ONBOARDING = Sichthilfe(
    sicht="onboarding",
    titel="Onboarding / Offboarding",
    recht_klartext=(
        "Rechte: onboarding.view zum Lesen, onboarding.edit zum Pflegen. "
        "Ohne das Pflegerecht sehen Sie den Stand, können ihn aber nicht "
        "ändern; die Sicht sagt das ausdrücklich."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Sicht führt durch die Schritte, die beim Eintritt und "
                "beim Ausscheiden einer Mitarbeiterin oder eines "
                "Mitarbeiters zu erledigen sind: Konto anlegen oder sperren, "
                "Rollen erteilen oder entziehen, Fälle übergeben.",
                "Ein vergessener Schritt fällt sonst erst später auf — im "
                "schlimmsten Fall, wenn jemand nach dem Ausscheiden noch "
                "Zugriff hat. Die Checkliste macht den Stand sichtbar und "
                "hält fest, wer wann was erledigt hat.",
                _ZWECKBINDUNG,
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "onboarding.view zum Lesen. Zum Setzen eines Schritts ist "
                "zusätzlich onboarding.edit nötig; fehlt es, steht das als "
                "Hinweis über der Liste, und die Aktionsspalte bleibt leer.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Ganz oben die Auswahl: Person und Checkliste (Aufnahme oder "
                "Ausscheiden), dann „Anzeigen“. Erst danach erscheint die "
                "Checkliste — vorher steht dort ein Hinweis und keine leere "
                "Tabelle.",
                "Danach der Name der Person, drei Zähler (offen, erledigt, "
                "nicht zutreffend), die Zahl der noch zugewiesenen Fälle und "
                "die Liste der Schritte mit Zustand, Notiz und Aktionen.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Person wählen, Checkliste wählen, „Anzeigen“.",
                "Einen Schritt abhaken: „Erledigt“.",
                "Einen Schritt überspringen: „Nicht zutreffend“ — dafür ist "
                "ein Grund PFLICHT. Ohne Grund wird nichts gespeichert.",
                "Eine Angabe zurücknehmen: „Zurücksetzen“ stellt den Schritt "
                "wieder auf offen.",
                "Vor dem Ausscheiden: die Zeile „Noch offen zugewiesene "
                "Fälle“ lesen und die Fälle über die Zuweisung verteilen.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "DIE CHECKLISTE FÜHRT DIE SCHRITTE, SIE FÜHRT SIE NICHT AUS. "
                "Ein Haken bei „Rechte entzogen“ entzieht keine Rechte — er "
                "hält fest, dass es jemand getan hat. Das Entziehen selbst "
                "geschieht in der Personalverwaltung.",
                "DER GRUND BEI „NICHT ZUTREFFEND“ IST PFLICHT. Ein "
                "übersprungener Schritt ohne nachvollziehbaren Grund wäre "
                "später nicht von einem vergessenen zu unterscheiden.",
                "Die Zahl der noch zugewiesenen Fälle ist eine Auskunft, "
                "keine Sperre: die Sicht hindert niemanden am Abschließen. "
                "Sie stellt nur sicher, dass die Zahl niemandem entgeht.",
                _ZWECKBINDUNG,
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Personalverwaltung — wo Konten, Merkmale und Rollen "
                "wirklich geändert werden.",
                "Zuweisung — wo die Fälle verteilt werden.",
                "Kapazitätspflege — Arbeitszeit und Abwesenheiten der neuen "
                "oder ausscheidenden Person.",
                "Betreuungs-Notizen — was während der Einarbeitung anfällt.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "onboarding.titel", "Onboarding / Offboarding",
            "Die Checkliste der Schritte bei Aufnahme und Ausscheiden. Sie "
            "hält den Stand fest; ausgeführt werden die Schritte an anderer "
            "Stelle.",
            verweis="onboarding#grenzen"),
        Kontexthilfe(
            "onboarding.kennzeile", "Was die Checkliste festhält",
            "Weist darauf hin, dass jede Angabe mit Person und Zeitpunkt "
            "festgehalten wird — sie ist der Beleg dafür, dass ein Schritt "
            "erledigt wurde.",
            verweis="onboarding#zweck"),
        Kontexthilfe(
            "onboarding.fallast", "Noch offen zugewiesene Fälle",
            "Wie viele Fälle dieser Person noch zugewiesen sind. Vor dem "
            "Ausscheiden sind sie zu verteilen — sonst hat am Ende niemand "
            "die Zuständigkeit.",
            verweis="onboarding#ablaeufe"),
    ),
)


#: Der Teilbestand dieser Nav-Gruppe, in Katalogreihenfolge
#: (mentoring, notes, onboarding - siehe VIEW_CATALOG).
BETREUUNG: Tuple[Sichthilfe, ...] = (MENTORING, NOTES, ONBOARDING)
