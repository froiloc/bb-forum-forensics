# =============================================================================
# management/help/inhalt/auswertung.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H10)
# =============================================================================
# Zweck:
#   Die Hilfetexte der Nav-Gruppe "Auswertung": results, annostats, limitation,
#   matrix, search.
#
#   HIER LIEGEN DIE HEIKELSTEN ZUSICHERUNGEN DES GANZEN WERKZEUGS. Drei
#   Sichten dieser Gruppe koennten missverstanden werden als etwas, das sie
#   ausdruecklich NICHT sind:
#     * "Fristen" koennte als Feststellung einer Verjaehrung gelesen werden.
#     * "Dringlichkeit & Erkenntnislage" koennte als Bewertung eines
#       Beschuldigten gelesen werden (§ 261 StPO).
#     * Die Volltextsuche koennte als Zugang zum Arbeitsstand eines fremden
#       Verfahrens gelesen werden.
#   In allen drei Kapiteln steht die Zusicherung deshalb NICHT nur unter
#   "Grenzen", sondern schon im ersten Absatz von "Zweck und Motivation". Wer
#   nur den Anfang liest - und das ist der Normalfall -, muss sie gelesen
#   haben.
#
#   DIE WORTLAUTE sind aus der Oberflaeche uebernommen und nicht umformuliert.
#   Eine Zusicherung, die in der Hilfe anders klingt als auf dem Bildschirm,
#   waere schlimmer als keine: sie liesse Raum fuer die Frage, welche der
#   beiden gilt.
#
# REGEL H-1 (Anwendersprache), REGEL H-0 (fallinhaltsfrei).
#
# Version: v0.8.599 - Build: 599 - 2026-07-31
# =============================================================================

from __future__ import annotations

from typing import Tuple

from management.help.modell import Abschnitt, Kontexthilfe, Sichthilfe

_STAND = 599


# =============================================================================
# 1) results - "Ermittlungsergebnis"
# =============================================================================

RESULTS = Sichthilfe(
    sicht="results",
    titel="Ermittlungsergebnis",
    recht_klartext=(
        "Recht: results.view. Der zugeteilte Umfang entscheidet, welche Fälle "
        "erscheinen."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Diese Sicht zeigt, WIE WEIT die Bewertung je Fall gediehen "
                "ist — nicht, wie sie ausgefallen ist. Sie beantwortet „wo "
                "haben wir noch nicht hingesehen?“.",
                "Der wichtigste Wert steht deshalb ganz oben und rot, sobald "
                "es ihn gibt: die Zahl der Fälle, die NOCH GAR NICHT bewertet "
                "sind. Eine Auswertung, die nur die bewerteten Fälle "
                "zusammenfasst, verschweigt genau die, auf die es ankommt.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "results.view. Der zugeteilte Umfang bestimmt, welche Fälle "
                "in die Abdeckung eingehen — bei „eigene“ ist die Abdeckung "
                "die Ihrer Fälle, nicht die der Dienststelle.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter die Hauptaussage in einem Satz, "
                "darunter der Katalogstand, darunter die Falltabelle und die "
                "Verteilung je Kriterium.",
            ),
        ),
        Abschnitt(
            "abdeckung", "Was „Abdeckung“ bedeutet",
            (
                "Abdeckung ist der Anteil der Kriterien, zu denen bei einem "
                "Fall überhaupt eine Bewertung vorliegt. Sie sagt nichts "
                "darüber, wie diese Bewertung ausgefallen ist.",
                "Ein Fall mit hoher Abdeckung ist gründlich bearbeitet — "
                "nicht belastet. Ein Fall mit niedriger Abdeckung ist "
                "unvollständig bearbeitet — nicht entlastet. Diese "
                "Unterscheidung ist der Kern der Sicht.",
            ),
        ),
        Abschnitt(
            "blinde_flecken", "Blinde Flecken",
            (
                "Fälle ohne jede Bewertung werden ausdrücklich gezählt und "
                "die Kopfzeile färbt sich. Ebenso werden die fehlenden "
                "Kriterien je Fall benannt statt nur gezählt.",
                "Der Grund: Ein blinder Fleck fällt sonst niemandem auf. Er "
                "sieht aus wie ein Fall ohne Befund — und ist doch das "
                "Gegenteil, nämlich ein Fall ohne Prüfung.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Lücken finden: nach „fehlende Kriterien“ sortieren und von "
                "oben abarbeiten.",
                "Unbearbeitetes finden: die Kopfzeile nennt die Zahl der gar "
                "nicht bewerteten Fälle; danach filtern.",
                "Vor einem Abschlussbericht: prüfen, ob der Fall vollständig "
                "bewertet ist — die Abdeckung sagt es in einer Zahl.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "ABDECKUNG IST KEINE BEWERTUNG. Sie misst, wie viel geprüft "
                "wurde, nicht was dabei herauskam. Aus einer hohen Abdeckung "
                "folgt kein Verdacht und aus einer niedrigen keine "
                "Entlastung.",
                "Die Sicht ist REIN LESEND. Bewertet wird in der Fallakte, "
                "nicht hier.",
                "Die Abdeckung bezieht sich auf einen bestimmten Stand des "
                "Kriterienkatalogs. Ändert sich der Katalog, ändern sich die "
                "Zahlen — deshalb steht der Katalogstand unter der "
                "Hauptaussage und nicht im Kleingedruckten.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Annotations-Statistik — womit gearbeitet wurde, nicht wie "
                "weit.",
                "Dringlichkeit & Erkenntnislage — die Rangfolge, in die diese "
                "Zahlen eingehen.",
                "Berichts-Abnahme — worauf sich ein Vermerk stützen sollte.",
                "Fallübersicht — der Bestand, über den hier gerechnet wird.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "results.titel", "Ermittlungsergebnis",
            "Zeigt, wie weit die Bewertung je Fall gediehen ist — nicht, wie "
            "sie ausgefallen ist. Abdeckung ist keine Bewertung.",
            verweis="results#abdeckung"),
        Kontexthilfe(
            "results.hauptaussage", "Die Hauptaussage",
            "Nennt in einem Satz, wie viele Fälle bewertet sind und wie viele "
            "NOCH GAR NICHT. Die Zeile färbt sich, sobald es unbewertete "
            "Fälle gibt — ein blinder Fleck sieht sonst aus wie ein Fall ohne "
            "Befund.",
            verweis="results#blinde_flecken"),
        Kontexthilfe(
            "results.katalogstand", "Katalogstand",
            "Nennt, auf welchen Stand des Kriterienkatalogs sich die "
            "Abdeckung bezieht. Ändert sich der Katalog, ändern sich die "
            "Zahlen — deshalb steht die Angabe hier und nicht im "
            "Kleingedruckten.",
            verweis="results#grenzen"),
        Kontexthilfe(
            "results.spalte.ampel", "Spalte „A“",
            "Eine Kurzanzeige zur Abdeckung des Falls. Sie bewertet den Fall "
            "nicht, sondern den Bearbeitungsstand.",
            verweis="results#abdeckung"),
        Kontexthilfe(
            "results.spalte.subject_id", "Spalte „Fall“",
            "Der Ermittlungsschlüssel der Fallakte."),
        Kontexthilfe(
            "results.spalte.username", "Spalte „Benutzername“",
            "Der im Forum geführte Kontoname des Falls."),
        Kontexthilfe(
            "results.spalte.status", "Spalte „Zustand“",
            "Der Bearbeitungsstand der Fallakte."),
        Kontexthilfe(
            "results.spalte.assigned_to", "Spalte „Ermittler“",
            "Die zuständige Person. Die Spalte dient dem Auffinden, nicht "
            "dem Vergleich von Personen."),
        Kontexthilfe(
            "results.spalte.abdeckung", "Spalte „Abdeckung“",
            "Der Anteil der Kriterien, zu denen eine Bewertung vorliegt. "
            "Hoch heißt gründlich bearbeitet, nicht belastet; niedrig heißt "
            "unvollständig bearbeitet, nicht entlastet.",
            verweis="results#abdeckung"),
        Kontexthilfe(
            "results.spalte.n_beste", "Spalte „beste“",
            "Wie oft bei diesem Fall die günstigste Einstufung vergeben "
            "wurde. Sie wird getrennt ausgewiesen und nicht mit der "
            "schwersten verrechnet.",
            verweis="results#grenzen"),
        Kontexthilfe(
            "results.spalte.hoechste", "Spalte „höchste Konfidenz“",
            "Die höchste Sicherheit, mit der bei diesem Fall eine Einstufung "
            "vergeben wurde. Eine Angabe über die Bewertung, nicht über den "
            "Fall."),
        Kontexthilfe(
            "results.spalte.score", "Spalte „Score“",
            "Ein rechnerischer Wert aus den vorliegenden Bewertungen. Er "
            "ordnet die Bearbeitung und ist keine Aussage über den "
            "Tatvorwurf.",
            verweis="results#grenzen"),
        Kontexthilfe(
            "results.spalte.fehlend", "Spalte „fehlende Kriterien“",
            "Welche Kriterien bei diesem Fall noch ohne Bewertung sind — "
            "benannt und nicht nur gezählt. Das ist die Arbeitsanweisung "
            "dieser Sicht.",
            verweis="results#blinde_flecken"),
        Kontexthilfe(
            "results.werkzeug.filter_entfernen", "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Sicht auf einmal."),
        Kontexthilfe(
            "results.werkzeug.trefferzahl", "Trefferanzeige",
            "Nennt, wie viele Zeilen sichtbar sind; bei gesetztem Filter "
            "„sichtbar von gesamt“."),
    ),
)


# =============================================================================
# 2) annostats - "Annotations-Statistik"
# =============================================================================

ANNOSTATS = Sichthilfe(
    sicht="annostats",
    titel="Annotations-Statistik",
    recht_klartext=(
        "Recht: stats.export_sta — dasselbe wie für die Statistiken und die "
        "Prognose. Die Sicht ist rein auswertend."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Sicht zeigt, WOMIT gearbeitet wurde: wie sich die "
                "gesetzten Anmerkungen auf Kategorien und Schlagworte "
                "verteilen. Sie beantwortet „welche Art von Fundstellen "
                "beschäftigt uns?“.",
                "Der Nutzen liegt im Auffälligen: Eine Kategorie, die kaum "
                "vorkommt, ist entweder selten — oder sie wird übersehen. "
                "Beides ist wissenswert, und die Zahlen unterscheiden es "
                "nicht; das muss die lesende Person tun.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "stats.export_sta. Die Sicht wertet über Fälle hinweg aus und "
                "hängt deshalb am selben Recht wie die übrigen "
                "Auswertungen.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter die Zusammenfassung in einem Satz, "
                "darunter zwei Verteilungen nebeneinander: nach Kategorie und "
                "nach Schlagwort.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Schwerpunkte erkennen: die Verteilung nach Kategorie lesen.",
                "Blinde Flecken vermuten: nach Kategorien suchen, die "
                "auffällig selten vorkommen — und in der Betreuung "
                "nachfragen, ob sie wirklich selten sind.",
                "Schlagwortpflege: ein Schlagwort, das nur einmal vorkommt, "
                "ist meist ein Tippfehler eines anderen.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "DIE ZAHLEN MESSEN ARBEIT, NICHT SACHVERHALTE. Sie sagen, wie "
                "oft etwas angemerkt wurde — nicht, wie oft es vorkommt. Wer "
                "sie als Aussage über den Bestand liest, verwechselt beides.",
                "Die Sicht ist KEIN Bewertungsinstrument für Personen. Wer "
                "wie viele Anmerkungen gesetzt hat, sagt nichts über die "
                "Qualität der Arbeit — eine sorgfältig geprüfte Fundstelle "
                "kann eine einzige Anmerkung ergeben.",
                "Die Sicht ist rein lesend und ändert keine Anmerkung.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Ermittlungsergebnis — wie weit bewertet wurde.",
                "Statistiken — die Zahlen zum Fallbestand.",
                "QS & Metriken — die Prüfung der Bearbeitungsqualität.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "annostats.titel", "Annotations-Statistik",
            "Zeigt, wie sich die gesetzten Anmerkungen auf Kategorien und "
            "Schlagworte verteilen. Die Zahlen messen Arbeit, nicht "
            "Sachverhalte.",
            verweis="annostats#grenzen"),
        Kontexthilfe(
            "annostats.zusammenfassung", "Zusammenfassung",
            "Nennt in einem Satz, wie viele Anmerkungen in die Auswertung "
            "eingehen. Ohne diese Grundgesamtheit wäre jeder Anteil darunter "
            "nicht einzuordnen.",
            verweis="annostats#zweck"),
    ),
)


# =============================================================================
# 3) limitation - "Fristen (Verjaehrung)"
# =============================================================================

LIMITATION = Sichthilfe(
    sicht="limitation",
    titel="Fristen (Verjährung)",
    recht_klartext=(
        "Recht: limitation.view. Ohne bestätigten Parametersatz zeigt die "
        "Sicht bewusst KEINE rechtliche Einstufung — die Fallliste und die "
        "Datenlage bleiben dabei vollständig sichtbar."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "DIESE SICHT STELLT KEINE VERJÄHRUNG FEST. Sie rechnet die "
                "ununterbrochene Frist und zeigt, bei welchen Fällen sie in "
                "den Vorwarnbereich läuft. Jede Angabe ist die "
                "FRÜHESTMÖGLICHE Frist und ersetzt keine juristische Prüfung "
                "im Einzelfall.",
                "Der Zweck ist eine Erinnerung, keine Entscheidung: Ein Fall, "
                "der seit Jahren ruht, soll nicht deshalb verjähren, weil "
                "niemand hingesehen hat. Was daraus folgt, entscheidet die "
                "rechtliche Prüfung.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "limitation.view. Der zugeteilte Umfang entscheidet, welche "
                "Fälle erscheinen.",
            ),
        ),
        Abschnitt(
            "vorbehalt", "Der Verjährungsvorbehalt",
            (
                "Ganz oben in der Sicht steht der Vorbehalt, und er steht "
                "dort nicht als Höflichkeitsfloskel: Unterbrechungen nach "
                "§ 78c StGB — etwa die Bekanntgabe der Verfahrenseinleitung, "
                "eine Beschlagnahme- oder Durchsuchungsanordnung, die "
                "Anklageerhebung — sind diesem Werkzeug NICHT BEKANNT und "
                "können die Frist neu in Gang gesetzt haben.",
                "Deshalb ist jede Angabe die früheste denkbare Frist. Die "
                "tatsächliche kann später liegen, niemals früher. Wer die "
                "Angabe als Feststellung behandelt, behandelt sie falsch.",
                "Trägt die Antwort den Vorbehalt einmal NICHT mit, sagt die "
                "Sicht das ausdrücklich und ändert ihre Farbe. Dann ist keine "
                "Zeile dieser Liste als Feststellung zu behandeln, bevor die "
                "Herkunft der Angabe geklärt ist.",
            ),
        ),
        Abschnitt(
            "stumm", "Wenn die Sicht schweigt",
            (
                "Ohne bestätigten Parametersatz zeigt die Sicht KEINE "
                "rechtliche Einstufung und nennt den Grund. Die Fallliste und "
                "die Datenlage bleiben dabei vollständig sichtbar — nur die "
                "Einstufung fehlt.",
                "Das ist Absicht: Eine Sicht, die im Zweifel eine Ampel "
                "zeigte, wäre gefährlicher als eine, die schweigt. Und eine, "
                "die im Zweifel gar nichts zeigte, verschwiege die Datenlage, "
                "die unstrittig ist.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter der Vorbehalt, darunter — falls "
                "einschlägig — der Grund für das Schweigen, darunter die "
                "Fallliste mit Fristbeginn, gerechneter Frist und "
                "Vorwarnung.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Regelmäßiger Blick: die Fälle im Vorwarnbereich ansehen und "
                "die rechtliche Prüfung veranlassen.",
                "Bei einer Auffälligkeit: nicht die Angabe dieser Sicht "
                "weitergeben, sondern den Fall zur Prüfung geben. Die Sicht "
                "liefert den Anlass, nicht das Ergebnis.",
                "Meldet die Sicht einen Fehler: das ist KEIN Leerbefund. Es "
                "ist dann unbekannt, ob Fristen ablaufen — der Zustand gehört "
                "gemeldet.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "DIESE SICHT STELLT KEINE VERJÄHRUNG FEST. Sie rechnet die "
                "ununterbrochene Frist; Unterbrechungen nach § 78c StGB sind "
                "ihr nicht bekannt.",
                "Jede Angabe ist die FRÜHESTMÖGLICHE Frist und ersetzt keine "
                "juristische Prüfung im Einzelfall.",
                "Eine leere Liste im Fehlerfall wäre die gefährlichste "
                "Anzeige dieses Werkzeugs — sie läse sich als „keine Frist in "
                "Gefahr“. Die Sicht sagt deshalb bei einem Fehler "
                "ausdrücklich, dass es sich um keinen Leerbefund handelt.",
                "Die Sicht ist rein lesend. Sie ändert keine Frist und keinen "
                "Fallzustand.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Kalender & Wiedervorlage — die selbst gesetzten Termine; "
                "diese Sicht behandelt die gesetzlichen.",
                "Dringlichkeit & Erkenntnislage — wo die Fristnähe in eine "
                "Rangfolge eingeht.",
                "Überblick — die Kachel „Fristen mit Vorwarnung“, mit "
                "demselben Vorbehalt.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "limitation.titel", "Fristen (Verjährung)",
            "Rechnet die ununterbrochene Verjährungsfrist und zeigt, wo sie "
            "in den Vorwarnbereich läuft. Sie STELLT KEINE VERJÄHRUNG FEST.",
            verweis="limitation#vorbehalt"),
        Kontexthilfe(
            "limitation.vorbehalt", "Der Verjährungsvorbehalt",
            "Unterbrechungen nach § 78c StGB sind diesem Werkzeug nicht "
            "bekannt und können die Frist neu in Gang gesetzt haben. Jede "
            "Angabe ist die FRÜHESTMÖGLICHE Frist und ersetzt keine "
            "juristische Prüfung im Einzelfall.",
            verweis="limitation#vorbehalt"),
    ),
)


# =============================================================================
# 4) matrix - "Dringlichkeit & Erkenntnislage"
# =============================================================================

MATRIX = Sichthilfe(
    sicht="matrix",
    titel="Dringlichkeit & Erkenntnislage",
    recht_klartext=(
        "Recht: matrix.view. Die Sicht ist rein auswertend und schreibt "
        "keine Priorität."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "DIESE SICHT IST KEINE BEWEISWÜRDIGUNG (§ 261 StPO). Sie "
                "ordnet Fälle nach Bearbeitungsdringlichkeit — also danach, "
                "worauf die Dienststelle als Nächstes ihre Kraft richten "
                "sollte. Sie sagt nichts über Schuld, Unschuld oder das "
                "Gewicht eines Tatvorwurfs.",
                "Der Zweck ist die Verteilung knapper Arbeitszeit auf viele "
                "Fälle. Ohne eine solche Ordnung entscheidet darüber der "
                "Zufall — und der ist die schlechteste aller Reihenfolgen.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "matrix.view. Der zugeteilte Umfang entscheidet, welche Fälle "
                "eingehen.",
            ),
        ),
        Abschnitt(
            "zweckbindung", "Die Zweckbindung",
            (
                "Ganz oben steht die Zweckbindung, wortgleich mit dem "
                "Gewichtungssatz, auf dem die Rangfolge beruht. Sie ist der "
                "Grund, aus dem diese Sicht überhaupt verantwortbar ist.",
                "Trägt die Antwort die Zweckbindung einmal NICHT mit, sagt "
                "die Sicht das ausdrücklich und ändert ihre Farbe. Dann ist "
                "keine Zahl dieser Sicht als Bewertung eines Beschuldigten zu "
                "behandeln, bevor die Herkunft der Angabe geklärt ist.",
            ),
        ),
        Abschnitt(
            "keine_prioritaet", "Die Sicht schreibt keine Priorität",
            (
                "Die Reihenfolge ist ein VORSCHLAG. Die Priorität eines Falls "
                "bleibt unberührt und wird weiterhin von Menschen gesetzt — "
                "in der Zuweisung.",
                "Diese Trennung ist die zweite tragende Zusicherung: Eine "
                "Rangfolge, die sich selbst in die Fallsteuerung schreibt, "
                "wäre keine Empfehlung mehr, sondern eine Entscheidung ohne "
                "Entscheider.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter die Zweckbindung, darunter die "
                "Zusicherung zur Priorität, darunter die Rangfolge mit den "
                "Merkmalen, aus denen sie sich zusammensetzt.",
                "Die Merkmale werden einzeln ausgewiesen und nicht nur "
                "summiert: Wer eine Rangfolge übernehmen soll, muss sehen "
                "können, woraus sie entstanden ist.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Arbeitsplanung: die Rangfolge lesen und die oberen Fälle "
                "zuerst einplanen.",
                "Eine Einstufung nachvollziehen: die Einzelmerkmale der Zeile "
                "ansehen. Wer den Weg nicht nachvollziehen kann, sollte die "
                "Reihenfolge nicht übernehmen.",
                "Eine Priorität ändern: in der Zuweisung — hier geht es "
                "nicht, und das ist Absicht.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "KEINE BEWEISWÜRDIGUNG (§ 261 StPO). Die Zahlen ordnen die "
                "Bearbeitung und bewerten keinen Beschuldigten.",
                "DIE SICHT SCHREIBT KEINE PRIORITÄT. Die Reihenfolge ist ein "
                "Vorschlag; gesetzt wird die Priorität weiterhin von Menschen.",
                "Eine leere Liste im Fehlerfall läse sich als „nichts ist "
                "dringend“. Die Sicht sagt deshalb bei einem Fehler "
                "ausdrücklich, dass es sich um keinen Leerbefund handelt.",
                "Die Rangfolge beruht auf einem festgelegten Gewichtungssatz. "
                "Ändert er sich, ändert sich die Reihenfolge — sie ist keine "
                "Eigenschaft der Fälle, sondern eine Aussage über die "
                "gewählte Gewichtung.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Nächstbeste Aktion — die Empfehlung je Fall statt der "
                "Rangfolge über alle.",
                "Ermittlungsergebnis — die Erkenntnislage, die hier eingeht.",
                "Fristen (Verjährung) — die Fristnähe, die hier eingeht.",
                "Zuweisung — wo Prioritäten tatsächlich gesetzt werden.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "matrix.titel", "Dringlichkeit & Erkenntnislage",
            "Ordnet Fälle nach Bearbeitungsdringlichkeit. KEINE "
            "Beweiswürdigung (§ 261 StPO) und keine Aussage über Schuld oder "
            "das Gewicht eines Tatvorwurfs.",
            verweis="matrix#zweckbindung"),
        Kontexthilfe(
            "matrix.zweckbindung", "Die Zweckbindung",
            "Nennt wortgleich den Gewichtungssatz, auf dem die Rangfolge "
            "beruht. Trägt die Antwort die Zweckbindung nicht mit, ändert "
            "die Zeile ihre Farbe — dann ist keine Zahl dieser Sicht als "
            "Bewertung eines Beschuldigten zu behandeln.",
            verweis="matrix#zweckbindung"),
    ),
)


# =============================================================================
# 5) search - "Volltextsuche"
# =============================================================================

SEARCH = Sichthilfe(
    sicht="search",
    titel="Volltextsuche",
    recht_klartext=(
        "Recht: evidence.fulltext_search — BEWUSST OHNE Einschränkung des "
        "Umfangs. Auf „eigene“ verengt beantwortete die Sicht genau die Frage "
        "nicht, für die es sie gibt. Der INHALT eines fremden Falls verlangt "
        "darüber hinaus eine belegte Freigabe."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Suche beantwortet EINE Frage: „Ist dieser Begriff — "
                "meist ein Kontoname — schon irgendwo in der Dienststelle "
                "aufgefallen?“ Sie zeigt dabei die TREFFERLAGE, nicht den "
                "Inhalt.",
                "Der Gewinn ist der Kreuzbezug: Wenn eine Kollegin denselben "
                "Namen bereits geprüft hat — auch wenn sie ihn verworfen hat "
                "—, ist das für den eigenen Fall wertvoll und wäre sonst nicht "
                "auffindbar.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "evidence.fulltext_search für die Trefferlage. Der Inhalt "
                "eines fremden Falls verlangt zusätzlich eine belegte "
                "Freigabe — sie wird über die Sicht selbst beantragt.",
                "Die Suche ist nicht auf eigene Fälle verengbar. Eine Suche, "
                "die nur die eigenen Fälle durchsieht, beantwortet die Frage "
                "nach dem Kreuzbezug nicht.",
            ),
        ),
        Abschnitt(
            "zwei_stufen", "Zwei Stufen — und warum",
            (
                "STUFE 1 ZEIGT KEINEN TEXT. Sie nennt Fall, Trefferzahl, Art, "
                "Zeitraum und Urheber — mehr nicht.",
                "Das ist kein Sparen an der Anzeige, sondern der Kern des "
                "Freigabemodells: Der Arbeitsstand eines FREMDEN Verfahrens "
                "enthält Klarnamen, Opferangaben und Bewertungen von "
                "Kolleginnen. Er wird erst nach einer belegten Entscheidung "
                "sichtbar.",
                "Stufe 2 zeigt den Inhalt — nach der Freigabe. Bei einem "
                "fremden Fall steht deshalb „Inhalt gesperrt“ zusammen mit "
                "dem Weg zur begründungspflichtigen Anfrage. Eine Sperre ist "
                "hier kein Fehler, sondern ein Weg.",
            ),
        ),
        Abschnitt(
            "indexstand", "Der Suchstand",
            (
                "Ganz oben steht, wie aktuell der durchsuchte Bestand ist. "
                "Ein drei Tage alter Stand liefert eine Trefferlage von vor "
                "drei Tagen — stünde das klein am Ende, läse es niemand, und "
                "ein Leerbefund sähe aus wie „es gibt nichts“.",
                "Ist der Stand nicht belastbar, wird die Zeile hervorgehoben. "
                "Dann ist ein Leerbefund keine Auskunft.",
            ),
        ),
        Abschnitt(
            "fassungen", "Die drei Fassungen",
            (
                "Treffer werden nach Fassung getrennt gezählt — aktuell, "
                "überholt, zurückgenommen — und NIE addiert. Eine Summe "
                "behauptete eine Trefferlage, die es nicht gibt.",
                "Gerade der ZURÜCKGENOMMENE Befund ist wertvoll: Er sagt, "
                "dass eine Kollegin die Sache bereits geprüft und verworfen "
                "hat. Das ist eine Auskunft und kein Nichts.",
            ),
        ),
        Abschnitt(
            "zweck_pflicht", "Die Zweckangabe",
            (
                "Vor jeder Suche ist der Zweck aus einer Liste zu wählen. "
                "Ohne ihn wird nicht gesucht. Jede Abfrage wird protokolliert "
                "— auch die, die nichts findet.",
                "Fehlt für Ihr Anliegen ein passender Zweck, wählen Sie nicht "
                "ersatzweise den Sammeleintrag, sondern melden Sie den "
                "fehlenden. Der Anteil des Sammeleintrags wird ausgewiesen: "
                "Steigt er, fehlt ein Zweck — dann wird die Liste ergänzt und "
                "nicht der Sammeleintrag ausgeweitet.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter der Suchstand, darunter die "
                "Suchmaske mit Begriff und Zweck. Nach der Suche folgt die "
                "Trefferlage je Fall; ein Treffer im eigenen Fall lässt sich "
                "öffnen, ein fremder zeigt den Weg zur Anfrage.",
                "Die Sicht sucht beim Öffnen NICHT von selbst — die Maske "
                "erscheint leer. Ein Suchlauf ohne menschliche Handlung "
                "erzeugte einen Beleg, den niemand veranlasst hat.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Kreuzbezug prüfen: Kontonamen eingeben, Zweck wählen, "
                "suchen. Die Trefferlage lesen, ohne Inhalt zu erwarten.",
                "Einen fremden Treffer verfolgen: die Anfrage aus der Zeile "
                "heraus stellen und begründen. Die Entscheidung trifft die "
                "zuständige Stelle.",
                "Einen Leerbefund einordnen: zuerst den Suchstand oben "
                "ansehen. Bei einem nicht belastbaren Stand ist „nichts "
                "gefunden“ keine Auskunft.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "STUFE 1 ZEIGT KEINEN TEXT. Der Arbeitsstand eines fremden "
                "Verfahrens wird erst nach einer belegten Entscheidung "
                "sichtbar.",
                "Die Suche findet nur, was im durchsuchten Bestand steht. Ist "
                "dessen Stand alt, ist die Trefferlage alt — die Sicht sagt "
                "es oben.",
                "Die drei Fassungen werden NIE addiert. Eine Summe wäre eine "
                "Trefferlage, die es nicht gibt.",
                "Jede Abfrage wird protokolliert, auch der Leerbefund. Das "
                "ist keine Überwachung der Suchenden, sondern die "
                "Nachvollziehbarkeit des Zugriffs auf fremde Verfahren.",
                "Ein Treffer ist kein Beweis und keine Identität. Er ist ein "
                "Hinweis darauf, dass eine Zeichenfolge zweimal vorkommt.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Kreuzbezug — der ausgearbeitete Zusammenhang zwischen "
                "Fällen.",
                "Querfunde — der Rückkanal für das, was dabei gefunden wird.",
                "Aliasse — die gepflegten Namensgleichheiten.",
                "Externe Fallfreigabe — wo über Freigaben entschieden wird.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "search.titel", "Fallübergreifende Volltextsuche",
            "Beantwortet, ob ein Begriff — meist ein Kontoname — schon "
            "irgendwo in der Dienststelle aufgefallen ist. Stufe 1 zeigt die "
            "Trefferlage, KEINEN Text.",
            verweis="search#zwei_stufen"),
        Kontexthilfe(
            "search.indexstand", "Suchstand",
            "Nennt, wie aktuell der durchsuchte Bestand ist. Ein alter Stand "
            "liefert eine alte Trefferlage; ist er nicht belastbar, wird die "
            "Zeile hervorgehoben — dann ist ein Leerbefund keine Auskunft.",
            verweis="search#indexstand"),

        # Die vier Bedienelemente der Suchmaske (Build 636, Welle B4).
        Kontexthilfe(
            "search.bedienung.begriff", "Suchbegriff",
            "Wonach gesucht wird — meist ein Kontoname. Ein Leerbefund heißt "
            "„im durchsuchten Bestand nicht gefunden“ und nicht „kommt nicht "
            "vor“; wie aktuell dieser Bestand ist, sagt die Zeile darüber.",
            verweis="search#indexstand"),
        Kontexthilfe(
            "search.bedienung.suchart", "Suchart",
            "Wortsuche findet den Begriff als eigenes Wort. Die Teilstring-"
            "Suche findet ihn auch inmitten längerer Zeichenfolgen — sie "
            "findet also auch Verklebtes, liefert dafür aber mehr "
            "Zufallstreffer. Bei einem kurzen Namen lohnt beides "
            "nacheinander.",
            verweis="search#zwei_stufen"),
        Kontexthilfe(
            "search.bedienung.zweck", "Zweck der Abfrage",
            "PFLICHTANGABE. Jede Suche wird mit ihrem Zweck protokolliert — "
            "auch der Leerbefund. Das ist keine Überwachung der Suchenden, "
            "sondern die Nachvollziehbarkeit eines Zugriffs auf fremde "
            "Verfahren.",
            verweis="search#grenzen"),
        Kontexthilfe(
            "search.bedienung.begruendung", "Begründung",
            "Freitext zum Zweck. Das Feld ist gesperrt, solange der gewählte "
            "Zweck keine Begründung verlangt, und wird bei „Sonstiges“ zur "
            "Pflicht — ein Zweck, der alles abdeckt, deckt sonst nichts ab.",
            verweis="search#grenzen"),
    ),
)


#: Der Teilbestand dieser Nav-Gruppe, in Katalogreihenfolge
#: (results, annostats, limitation, matrix, search - siehe VIEW_CATALOG).
AUSWERTUNG: Tuple[Sichthilfe, ...] = (
    RESULTS, ANNOSTATS, LIMITATION, MATRIX, SEARCH,
)
