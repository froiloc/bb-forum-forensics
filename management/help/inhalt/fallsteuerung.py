# =============================================================================
# management/help/inhalt/fallsteuerung.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H5)
# =============================================================================
# Zweck:
#   Die Hilfetexte der Nav-Gruppe "Fallsteuerung" (Sichten: assignment, cases,
#   faelle).
#
#   STAND BUILD 592 (H5): NUR die Pilotsicht 'faelle' (Fallübersicht). Sie
#   durchlaeuft als erste die volle Kette - Attribut im Browser, Kontexttext,
#   Vollhilfe-Kapitel, Verweis - und ist damit der QUALITAETSMASSSTAB fuer
#   alle folgenden Inhaltswellen ("so sieht fertig aus", Bauplan H5).
#   'assignment' und 'cases' folgen in Welle H8.
#
# REDAKTIONSLEITFADEN, nach dem diese Texte verfasst sind (Konzept §2.2/§2.3):
#   Kontexthilfe: Was ist das? -> Was bewirkt es? -> Was ist die Folge?
#     Hoechstens vier Saetze, der erste allein tragfaehig. Das ELEMENT wird
#     beschrieben, nie sein Inhalt. Keine Rechte-Zusage ("hier koennen Sie"),
#     sondern die Nennung des Rechts.
#   Vollhilfe: feste Gliederung Zweck - Rechtelage - Aufbau - Ablaeufe -
#     Grenzen - Querverweise, jeder Abschnitt mit Anker.
#
# REGEL H-0: kein Falldatum, kein echter Kontoname, keine echte UID. Die
#   Beispiele stammen aus dem fiktiven Raum (pruefung.FIKTIVE_UIDS).
#
# Version: v0.8.592 - Build: 592 - 2026-07-31
# =============================================================================

from __future__ import annotations

from typing import Tuple

from management.help.modell import Abschnitt, Kontexthilfe, Sichthilfe

# Der Ankerpraefix der Fall-Uebersicht ist 'overview' und nicht 'faelle' -
# das Modul cockpit_overview.js ist aelter als die Sicht (Build 574) und
# setzt seine Anker seit Build 548 unter diesem Namen. Die Zuordnung steht in
# management/help/anker_katalog.py; hier wird sie nur benutzt.
_P = "overview"

FAELLE = Sichthilfe(
    sicht="faelle",
    titel="Fallübersicht",
    recht_klartext=(
        "Recht: dashboard.view. Mit dem Umfang „alle“ zeigt die Tabelle den "
        "gesamten Fallbestand, mit „eigene“ ausschließlich die Fälle, "
        "die Ihnen zugewiesen sind. Welcher Umfang gilt, steht als Klartext "
        "in der Zeile unter der Überschrift."
    ),
    anker_praefixe=("faelle", _P),
    stand=592,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Fallübersicht ist die vollständige Liste aller Fallakten "
                "im zulässigen Umfang — eine Zeile je Beschuldigtenkonto, "
                "sortiert nach Dringlichkeit. Sie beantwortet die Frage "
                "„Welche Fälle gibt es, und welcher braucht als nächstes "
                "Aufmerksamkeit?“",
                "Die Kachel „Fall-Übersicht“ im Überblick zeigt nur die "
                "dringendsten Fälle; diese Sicht ist der Ort, an dem der "
                "Bestand vollständig steht. Sie ist deshalb kein zweiter "
                "Weg zu denselben Daten, sondern der einzige, der alle "
                "zeigt.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "Die Sicht hängt am Recht dashboard.view — demselben, das "
                "auch die Kachel „Fall-Übersicht“ im Überblick verlangt. Es "
                "entsteht also kein zusätzlicher "
                "Zugang, nur ein zweiter Weg zu einem Bestand, den Sie "
                "ohnehin sehen dürfen.",
                "Der zugeteilte Umfang entscheidet: „alle“ zeigt den "
                "Gesamtbestand (Leitungssicht), „eigene“ nur die Ihnen "
                "zugewiesenen Fälle. Fremde Fälle sind bei „eigene“ nicht "
                "etwa ausgeblendet, sondern werden Ihnen gar nicht "
                "erst geliefert.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Oben steht die Überschrift, darunter eine Zeile mit dem "
                "geltenden Umfang und der Anzahl der Fälle. Es folgt die "
                "Werkzeugleiste, darunter die Tabelle.",
                "Die Tabelle ist nach Dringlichkeit vorsortiert: zuerst die "
                "Ampelstufe, dann die Priorität aufsteigend, dann die letzte "
                "Aktivität absteigend, zuletzt die Subject-ID. Diese "
                "Reihenfolge ist eine Aussage — wer umsortiert, verlässt sie "
                "bewusst.",
            ),
        ),
        Abschnitt(
            "ampel", "Die Dringlichkeits-Ampel",
            (
                "Die Ampel ist kein Ergebnis der Ermittlung, sondern ein "
                "Bearbeitungssignal. Sie misst, wie lange am Fall nichts "
                "geschehen ist, und ob er überhaupt jemandem zugewiesen "
                "wurde.",
                "Neben dem Farbpunkt steht der Grund im Klartext. Die "
                "Schwellen sind einstellbar (Vorgabe: ab 7 Tagen ohne "
                "Aktivität gelb, ab 21 Tagen rot); abgeschlossene und "
                "freigegebene Fälle sind grün.",
            ),
            liste=(
                "rot — offen und nicht zugewiesen, oder lange ohne Aktivität",
                "gelb — mittlere Inaktivität oberhalb der gelben Schwelle",
                "grün — aktiv, freigegeben oder abgeschlossen",
            ),
        ),
        Abschnitt(
            "spalten", "Die Spalten",
            (
                "Jeder Spaltenkopf trägt eine eigene Kurzhilfe: schalten Sie "
                "den Hilfemodus ein (Knopf „Hilfe“ oder Shift+F1) und klicken "
                "Sie den Kopf an.",
            ),
            liste=(
                "Ampel — Dringlichkeitsstufe mit Grund im Klartext.",
                "Prio — Prioritätsstufe 1 (höchste) bis 5 (niedrigste).",
                "Subject-ID — der Ermittlungsschlüssel der Fallakte.",
                "Benutzer — der im Forum geführte Kontoname.",
                "Status — offen, in Bearbeitung, freigegeben, abgeschlossen.",
                "Zugewiesen — die zuständige Person, sonst ein Gedankenstrich.",
                "Letzte Aktivität — Tage seit dem letzten Fallereignis.",
                "Ereignisse — Anzahl der protokollierten Fallereignisse.",
                "Notiz — ob zum Fall eine Betreuungsnotiz vorliegt.",
                "Support — laufende Support-Sitzungen (Anwesenheit, kein "
                "Fallzustand).",
            ),
        ),
        Abschnitt(
            "filter", "Filtern, Sortieren und Spaltenwahl",
            (
                "Jede Spalte hat einen Kopffilter. Wo eine Spalte weniger als "
                "zehn verschiedene Werte führt, ist es eine Auswahlliste mit "
                "Mehrfachauswahl, sonst ein Freitextfeld. Eine leere Auswahl "
                "filtert nicht — sie lässt also alles stehen, statt alles "
                "auszublenden.",
                "Die Trefferanzeige rechts in der Werkzeugleiste nennt "
                "„sichtbar von gesamt“, sobald ein Filter greift. "
                "„Filter zurücksetzen“ entfernt alle Filter dieser Sicht auf "
                "einmal. Sortierung, Filter und Spaltenwahl werden im Browser "
                "gesichert und stehen beim nächsten Aufruf wieder so da.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (
                "Zwei Wege führen in die Sicht: der Navigationseintrag "
                "„Fallübersicht“ und die Kommandopalette (Strg+K), deren "
                "Fallsuche unmittelbar auf die betreffende Zeile springt und "
                "sie kurz hervorhebt.",
            ),
            liste=(
                "Rückstau finden: nach Ampel „rot“ filtern und die Spalte "
                "„Zugewiesen“ auf leer prüfen — das sind die Fälle, die noch "
                "niemandem gehören.",
                "Liegengebliebenes finden: nach „Letzte Aktivität“ absteigend "
                "sortieren; oben stehen die Fälle mit der längsten Ruhe.",
                "Einen bestimmten Fall aufschlagen: Strg+K, den Kontonamen "
                "oder die Subject-ID eingeben, den Treffer wählen. Die Zeile "
                "wird angesprungen und hervorgehoben.",
                "Zur Zuweisung wechseln: die Sicht „Zuweisung“ öffnen; sie "
                "trägt den Schreibweg. Die Fallübersicht selbst verändert "
                "nichts.",
            ),
            geordnet=False,
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "Diese Sicht ist REIN LESEND. Sie weist nicht zu, ändert "
                "keinen Status und setzt keine Priorität; es gibt dafür in "
                "ihr keinen Weg. Wer etwas ändern will, benutzt die Sicht "
                "„Zuweisung“ — dort wird jede Änderung protokolliert.",
                "Die Ampel ist ein Bearbeitungs-, kein Bewertungssignal. Sie "
                "sagt nichts über die Schwere eines Tatvorwurfs und nichts "
                "über die Erkenntnislage aus; sie misst allein Inaktivität "
                "und Zuweisungslage. Eine rote Ampel ist eine Aufforderung, "
                "hinzusehen — keine Feststellung.",
                "Die Anzahl der Ereignisse ist ein Aktivitäts- und kein "
                "Ergebnismaß. Ein Fall mit vielen Ereignissen ist nicht "
                "weiter fortgeschritten als einer mit wenigen.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Zuweisung — der Schreibweg: Fälle verteilen, Priorität und "
                "Status setzen.",
                "Dashboard — dieselbe Ampel als Kompaktkachel mit den drei "
                "dringendsten Fällen.",
                "Eskalationen — die Fälle, die eine Schwelle überschritten "
                "haben, mit Quittierung.",
                "Meine Aufträge — derselbe Bestand, auf die eigene Zuweisung "
                "verengt.",
            ),
        ),
    ),
    kontext=(
        # --- Kopfbereich (literale Marken in cockpit_overview.js) ----------
        Kontexthilfe(
            "faelle.titel", "Fallübersicht",
            "Die vollständige Liste der Fallakten im zulässigen Umfang, "
            "vorsortiert nach Dringlichkeit. Rein lesend.",
            verweis="faelle#zweck"),
        Kontexthilfe(
            "faelle.umfang", "Geltender Umfang",
            "Nennt im Klartext, welcher Ausschnitt des Bestands Ihnen "
            "angezeigt wird: alle Fälle oder nur die Ihnen zugewiesenen. Der "
            "Umfang folgt dem, was Ihnen zum Recht dashboard.view zugeteilt "
            "ist, und lässt sich hier nicht erweitern.",
            verweis="faelle#rechte"),
        # --- Spaltenkoepfe (Anker aus dem Tabellen-Werkzeug, Build 548) ----
        Kontexthilfe(
            "%s.spalte.rank" % _P, "Spalte „Ampel“",
            "Zeigt die Dringlichkeitsstufe des Falls und den Grund dafür im "
            "Klartext. Die Ampel misst Inaktivität und Zuweisungslage, nicht "
            "die Schwere des Vorwurfs.",
            verweis="faelle#ampel"),
        Kontexthilfe(
            "%s.spalte.priority" % _P, "Spalte „Prio“",
            "Die vergebene Prioritätsstufe von 1 (höchste) bis 5 "
            "(niedrigste). Sie wird in der Sicht „Zuweisung“ gesetzt und ist "
            "hier nur ablesbar."),
        Kontexthilfe(
            "%s.spalte.subject_id" % _P, "Spalte „Subject-ID“",
            "Der Ermittlungsschlüssel der Fallakte. Unter dieser Nummer "
            "sind alle Falldaten des Beschuldigtenkontos abgelegt."),
            
        Kontexthilfe(
            "%s.spalte.username" % _P, "Spalte „Benutzer“",
            "Der im Forum geführte Kontoname des Beschuldigtenkontos. Er ist "
            "der Name, unter dem das Konto im Forum aufgetreten ist — keine "
            "Aussage über eine natürliche Person."),
        Kontexthilfe(
            "%s.spalte.status" % _P, "Spalte „Status“",
            "Der Bearbeitungsstand der Fallakte: offen, in Bearbeitung, "
            "freigegeben oder abgeschlossen. Gesetzt wird er über die "
            "Zuweisung und die Freigabe."),
        Kontexthilfe(
            "%s.spalte.assignee" % _P, "Spalte „Zugewiesen“",
            "Die Person, der der Fall zugewiesen ist. Ein Gedankenstrich "
            "bedeutet: noch niemandem — solche Fälle laufen in der Ampel "
            "sofort auf rot.",
            verweis="faelle#ampel"),
        Kontexthilfe(
            "%s.spalte.sincedays" % _P, "Spalte „Letzte Aktivität“",
            "Tage seit dem letzten protokollierten Fallereignis. Ein "
            "Gedankenstrich bedeutet: es liegt kein Ereignis vor. Aus diesem "
            "Wert speist sich die Ampel.",
            verweis="faelle#ampel"),
        Kontexthilfe(
            "%s.spalte.event_count" % _P, "Spalte „Ereignisse“",
            "Die Anzahl der zum Fall protokollierten Ereignisse. Ein "
            "Aktivitätsmaß, kein Ergebnismaß: viele Ereignisse bedeuten "
            "nicht, dass der Fall weiter fortgeschritten ist.",
            verweis="faelle#grenzen"),
        Kontexthilfe(
            "%s.spalte.has_note" % _P, "Spalte „Notiz“",
            "Zeigt an, ob zum Fall eine Betreuungsnotiz vorliegt. Den Inhalt "
            "der Notiz führt die Sicht „Betreuungs-Notizen“; hier steht nur, "
            "dass es eine gibt."),
        Kontexthilfe(
            "%s.spalte.support" % _P, "Spalte „Support“",
            "Weist auf laufende Support-Sitzungen zum Fall hin. Das ist eine "
            "Anwesenheitsangabe und kein Fallzustand — sie sagt nichts über "
            "den Bearbeitungsstand."),
        # --- Werkzeugleiste (Anker aus dem Tabellen-Werkzeug) --------------
        Kontexthilfe(
            "%s.werkzeug.filter_entfernen" % _P, "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Sicht auf einmal. Sortierung "
            "und Spaltenwahl bleiben dabei stehen.",
            verweis="faelle#filter"),
        Kontexthilfe(
            "%s.werkzeug.trefferzahl" % _P, "Trefferanzeige",
            "Nennt, wie viele Zeilen gerade sichtbar sind. Sobald ein Filter "
            "greift, steht hier „sichtbar von gesamt“ — damit nach einem "
            "Filterwechsel niemand über den Umfang im Zweifel ist.",
            verweis="faelle#filter"),
    ),
)

# =============================================================================
# Build 596 (H8): die uebrigen Sichten der Gruppe "Fallsteuerung".
# =============================================================================

ASSIGNMENT = Sichthilfe(
    sicht="assignment",
    titel="Zuweisung",
    recht_klartext=(
        "Recht: assignment.edit. Dies ist eine SCHREIBSICHT: jede Änderung "
        "geht sofort an den auditierten Schreibpfad und erzeugt einen Beleg "
        "im Protokollbuch."
    ),
    stand=596,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Hier werden Fälle verteilt: Ermittler zuordnen, Priorität "
                "setzen, Status ändern. Es ist die Gegenstelle zur "
                "Fallübersicht — jene zeigt den Bestand, hiesige Sicht "
                "verändert ihn.",
                "Der Sammelmodus ermögicht es, die Zuweisung von Fällen an "
                "einen einzelnen Ermittler zu beschleunigen. Mit einer "
                "komfortablen Mehrfachauswahl können alle gewünschten "
                "Fälle mit einer Aktion zugewiesen werden.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "assignment.edit mit dem Umfang „alle“. Dasselbe Recht trägt "
                "auch die Fall-Erkennung — dafür wurde bewusst kein "
                "zweites Recht eingeführt.",
                "Das Werkzeug prüft jede Änderung noch einmal, bevor es sie "
                "übernimmt. Was die "
                "Oberfläche anbietet, ist nie schon die Erlaubnis.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter der Hinweis auf die Belegpflicht und "
                "die Fallzahl, darunter ein Rückmeldebereich für Erfolg und "
                "Fehler, darunter die Tabelle mit Kopffiltern je Spalte.",
                "Wo eine Spalte weniger als zehn verschiedene Werte führt "
                "(Priorität, Status, Ermittler), ist der Filter eine "
                "Auswahlliste mit Mehrfachauswahl, sonst ein Freitextfeld.",
            ),
        ),
        Abschnitt(
            "sammelmodus", "Sammelmodus",
            (
                "Im Sammelmodus wählen Sie mehrere Zeilen aus und ändern sie "
                "in einem Vorgang. Er ist die Antwort auf die Massenzuweisung "
                "— und er verhindert zugleich die Fehlbedienung, weil zwischen "
                "Auswahl und Ausführung nichts neu aufgebaut wird.",
                "Nach einer bestätigten Einzeländerung wird nur "
                "die betroffene Zeile aufgefrischt. Sortierung, Filter, "
                "Bildlauf und Auswahl bleiben stehen.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Einen Fall zuweisen: Zelle „Ermittler“ öffnen, Person "
                "wählen. Die Änderung ist sofort geschrieben und belegt.",
                "Viele Fälle zuweisen: Sammelmodus einschalten, Zeilen "
                "auswählen, Ziel wählen, ausführen.",
                "Rückstau auflösen: nach leerer Zuweisung filtern und die "
                "Fälle verteilen.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "KEIN OPTIMISTISCHES BILD. Die Oberfläche zeigt nie einen "
                "Zustand, der nicht bestätigt geschrieben ist. Was Sie sehen, "
                "ist auch so gespeichert.",
                "Jede Änderung ist protokolliert — mit Person, Zeitpunkt und "
                "altem wie neuem Wert. Es gibt in dieser Sicht keinen Weg, "
                "eine Änderung unprotokolliert vorzunehmen.",
                "Die Sicht löscht nichts. Fälle werden verteilt und "
                "eingestuft, nicht entfernt.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Fallübersicht — derselbe Bestand, rein lesend.",
                "Fall-Erkennung — wie ein Fall überhaupt in die Fallakte "
                "kommt.",
                "Lastverteilung — wie viel bei wem liegt, bevor Sie weiter "
                "verteilen.",
                "Nächstbeste Aktion — welche Fälle unverteilt liegen.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "assignment.titel", "Zuweisung",
            "Die Schreibsicht der Fallverteilung: Ermittler zuordnen, "
            "Priorität und Status setzen. Jede Änderung wird sofort "
            "geschrieben und belegt.",
            verweis="assignment#zweck"),
        Kontexthilfe(
            "assignment.hinweis", "Belegpflicht und Fallzahl",
            "Nennt die Zahl der Fälle im Umfang und erinnert daran, dass "
            "jede Änderung in dieser Sicht sofort geschrieben und im "
            "Protokollbuch belegt wird. Es gibt keinen Entwurfsmodus.",
            verweis="assignment#grenzen"),
    ),
)


CASES = Sichthilfe(
    sicht="cases",
    titel="Fall-Erkennung",
    recht_klartext=(
        "Recht: assignment.edit — dasselbe Recht wie die Zuweisung. Es "
        "wurde bewusst kein zweites eingeführt: wer Fälle verteilen darf, darf "
        "auch feststellen, welche es gibt. Die Aufnahme neu erkannter Fälle "
        "ist ein Schreibvorgang und wird protokolliert."
    ),
    stand=596,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Sicht gleicht ab, was auf der Platte liegt, mit dem, was "
                "in der Fallakte geführt wird — und nennt jede Abweichung. Sie "
                "beantwortet die Frage „stimmt unser Bestand noch mit der "
                "Wirklichkeit überein?“",
                "Ohne diesen Abgleich fiele eine verschwundene Falldatenbank "
                "erst auf, wenn jemand sie öffnen will.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "Ansehen und Aufnehmen: assignment.edit. Der Abgleich selbst "
                "ist rein lesend; nur die Aufnahme neu erkannter Fälle "
                "schreibt.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, Zählzeile, die Angabe der geprüften "
                "Verzeichnisse, darunter der Warnbereich und die Tabelle.",
            ),
        ),
        Abschnitt(
            "zustaende", "Die vier Zustände",
            (
                "Jede Zeile trägt genau einen von vier Zuständen. Zwei davon "
                "sind Befunde, die gemeldet gehören:",
            ),
            liste=(
                "ok — der Fall steht in der Fallakte UND die Falldatenbank "
                "ist vorhanden.",
                "neu — die Falldatenbank ist da, der Fall aber nicht in der "
                "Fallakte. Diese Fälle sind aufnehmbar.",
                "vermisst — der Fall steht in der Fallakte, die Falldatenbank "
                "fehlt. MELDEN.",
                "unlesbar — die Datenbank ist da, aber nicht lesbar oder ohne "
                "Profil. MELDEN.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Regelmäßiger Abgleich: Sicht öffnen, Warnbereich lesen, dann "
                "die Zustände „neu“ prüfen.",
                "Neue Fälle aufnehmen: Kästchen setzen, Knopf drücken, im "
                "Bestätigungsblock die Auflistung prüfen, ausführen. Zwei "
                "Stufen — ein Fehlklick darf keine Fallakte verändern.",
                "„vermisst“ oder „unlesbar“: nicht selbst reparieren, sondern "
                "melden. Der Grund steht in der Hinweisspalte.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "Der Warnbereich über der Tabelle lässt sich NICHT wegfiltern. "
                "„vermisst“ und „unlesbar“ stehen dort zusätzlich zur Zeile, "
                "damit ein Statusfilter sie nicht unsichtbar machen kann.",
                "Es gibt KEIN „alles auswählen“. Die Aufnahme ist ein "
                "bewusster, belegpflichtiger Vorgang; der Stapelbetrieb bleibt "
                "der Kommandozeile vorbehalten.",
                "Auswählbar sind nur Fälle im Zustand „neu“ mit Benutzernamen "
                "— genau die Menge, die auch angenommen würde. Die "
                "Oberfläche bietet nichts an, was zwingend zurückgewiesen "
                "würde.",
                "Die Rückmeldung nennt aufgenommene UND übersprungene Fälle, "
                "jeden übersprungenen mit Grund.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Zuweisung — der nächste Schritt nach der Aufnahme.",
                "Fallübersicht — der Bestand, in den ein aufgenommener Fall "
                "eingeht.",
                "Integrität / Betrieb — wenn Datenbanken fehlen oder unlesbar "
                "sind.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "cases.titel", "Fall-Erkennung",
            "Gleicht ab, was auf der Platte liegt, mit dem, was in der "
            "Fallakte geführt wird, und nennt jede Abweichung.",
            verweis="cases#zweck"),
        Kontexthilfe(
            "cases.zahlen", "Zählzeile",
            "Nennt, wie viele Fälle je Zustand gefunden wurden. Die Zahlen "
            "sind das Ergebnis des Abgleichs, nicht der Fallakte allein.",
            verweis="cases#zustaende"),
        Kontexthilfe(
            "cases.verzeichnisse", "Geprüfte Verzeichnisse",
            "Nennt, ÜBER WELCHE Verzeichnisse gemessen wurde. Ohne diese "
            "Angabe bliebe unklar, worauf sich eine Aussage wie „kein Fall "
            "gefunden“ überhaupt bezieht.",
            verweis="cases#grenzen"),
    ),
)


#: Der Teilbestand dieser Nav-Gruppe, in Katalogreihenfolge
#: (assignment, cases, faelle - siehe VIEW_CATALOG).
FALLSTEUERUNG = (ASSIGNMENT, CASES, FAELLE)
