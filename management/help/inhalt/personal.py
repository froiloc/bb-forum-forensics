# =============================================================================
# management/help/inhalt/personal.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H12)
# =============================================================================
# Zweck:
#   Die Hilfetexte der Nav-Gruppe "Personal": personnel, capacity_pflege.
#
#   BEIDE SICHTEN SIND PFLEGEFLAECHEN - hier wird geschrieben, nicht gelesen.
#   Damit verschiebt sich der Schwerpunkt der Kapitel: nicht "was bedeutet
#   diese Zahl?", sondern "was passiert, wenn ich das jetzt anklicke?".
#
#   DIE ZWEI VERWECHSLUNGEN, DIE HIER TEUER SIND:
#     1) MERKMAL IST NICHT RECHT (Personalverwaltung). Die Kaestchen
#        "Ermittler:in", "Supervisor", "Support" steuern, WO eine Person zur
#        Auswahl angeboten wird. Rechte kommen ausschliesslich aus den Rollen.
#        Wer das verwechselt, setzt ein Haekchen und wundert sich, dass die
#        Person nichts darf - oder schlimmer: haelt jemanden fuer berechtigt.
#     2) RECHENART IST NICHT GRUND (Kapazitaetspflege). "Einschraenkung" und
#        "Garantie" sagen, WIE gerechnet wird; "Urlaub", "Krank", "Schulung"
#        sagen, WARUM. Es sind zwei Felder, und die Maske sagt das bereits -
#        die Hilfe wiederholt es, weil es die haeufigste Rueckfrage ist.
#
#   DAS ANDERE DURCHGEHENDE THEMA: NICHTS WIRD HIER WIRKLICH GELOESCHT. Ein
#   Rollenwiderruf, eine entfernte Arbeitszeitregel, ein stillgelegter
#   Abwesenheitsgrund - alle bleiben als Beleg erhalten und fallen nur aus der
#   Rechnung. Ohne diesen Hinweis sieht korrektes Verhalten wie ein Fehler aus,
#   und jemand sucht die "richtige" Loeschfunktion.
#
# QUELLEN: cockpit_personnel.js, cockpit_capacity_pflege.js,
#   management/server/management_app.py (Rechte, Umfaenge).
#
# REGEL H-0: kein Falldatum, keine echte Kennung.
# REGEL H-1: Anwendersprache.
#
# Version: v0.8.603 - Build: 603 - 2026-07-31
# =============================================================================

from __future__ import annotations

from typing import List, Tuple

from management.help.modell import Abschnitt, Kontexthilfe, Sichthilfe

_STAND = 603


# =============================================================================
# 1) personnel - "Personalverwaltung"
# =============================================================================

PERSONNEL = Sichthilfe(
    sicht="personnel",
    titel="Personalverwaltung",
    recht_klartext=(
        "Rechte: personnel.view zum Lesen, personnel.edit zum Ändern, "
        "personnel.sync für den AD-Abgleich. Ohne Änderungsrecht ist die "
        "Liste vollständig sichtbar, aber ohne Bedienelemente."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Hier werden die Anwenderinnen und Anwender der Anlage "
                "verwaltet: wer aktiv ist, welche Merkmale eine Person trägt "
                "und welche Rollen ihr zugewiesen sind.",
                "MERKMAL UND RECHT SIND ZWEIERLEI. Die Kästchen "
                "„Ermittler:in“, „Supervisor“ und „Support“ sind Merkmale: "
                "sie steuern, wo eine Person zur Auswahl angeboten wird — "
                "etwa in der Zuweisung. RECHTE kommen ausschließlich aus den "
                "Rollen. Ein Merkmal allein erlaubt nichts, und eine Rolle "
                "wirkt auch ohne Merkmal.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "personnel.view zum Lesen. Zum Setzen eines Merkmals oder "
                "zum Zuweisen und Widerrufen einer Rolle ist personnel.edit "
                "nötig. Der AD-Abgleich hängt an personnel.sync und "
                "erscheint nur mit diesem Recht.",
                "DIE EIGENE ZEILE TRÄGT KEINE BEDIENELEMENTE. Das ist kein "
                "Versehen, sondern Absicht: niemand soll sich selbst "
                "versehentlich aussperren oder sich selbst Rechte erteilen. "
                "Die eigene Kennung ist mit „(ich)“ gekennzeichnet.",
                "WELCHE ROLLE WELCHES RECHT TRÄGT, WIRD HIER NICHT "
                "GEPFLEGT. Diese Zuordnung ist in der Rechte-Matrix "
                "einzusehen und wird über die Kommandozeile gepflegt.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter eine Hinweiszeile und die Zeile für "
                "Rückmeldungen. Dann die Liste aller Anwender mit "
                "Kopffiltern und Werkzeugleiste.",
                "Deaktivierte Personen bleiben in der Liste und sind "
                "gekennzeichnet; die Spalte „Status“ nennt beim Überfahren "
                "Zeitpunkt und Grund. Mit dem Recht für den AD-Abgleich "
                "folgt unten ein eigener Abschnitt.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Ein Merkmal setzen oder entfernen: das Kästchen in der "
                "jeweiligen Spalte anklicken. Es wird sofort gespeichert.",
                "Eine Rolle zuweisen: in der Spalte „Rollen“ die Auswahl "
                "„Rolle zuweisen …“ öffnen. Angeboten wird nur, was die "
                "Person noch nicht hat.",
                "Eine Rolle widerrufen: das × am Rollen-Schildchen.",
                "Jemanden suchen: der Kopffilter der Spalte „Rollen“ "
                "durchsucht die Rollenkürzel — so findet man alle, die eine "
                "bestimmte Rolle tragen.",
                "AD-Abgleich: „AD-Vorschau laden“ holt den Stand aus dem "
                "Verzeichnisdienst. Das geschieht erst auf Anforderung, weil "
                "die Abfrage dauern kann.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "EIN WIDERRUF IST KEINE LÖSCHUNG. Die widerrufene Zuweisung "
                "bleibt mit Zeitpunkt erhalten — sie ist der Beleg dafür, "
                "dass die Rolle in einem bestimmten Zeitraum bestand. In der "
                "Liste erscheint sie nicht mehr.",
                "MERKMALE VERGEBEN KEINE RECHTE. Wer einer Person etwas "
                "erlauben will, weist eine ROLLE zu.",
                "An der eigenen Person ist nichts änderbar — auch nicht mit "
                "allen Rechten.",
                "Die Sicht ändert nichts im Verzeichnisdienst. Der "
                "AD-Abgleich ist eine Vorschau und ein Übernahmeweg in diese "
                "Anlage, keine Pflege des Verzeichnisses.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Rechte-Matrix — welche Rolle welches Recht trägt.",
                "Onboarding / Offboarding — die Checkliste, die auf diese "
                "Sicht verweist.",
                "Kapazitätspflege — Arbeitszeit und Abwesenheiten derselben "
                "Personen.",
                "Lastverteilung — wie viele Fälle auf sie treffen.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "personnel.titel", "Personalverwaltung",
            "Verwaltet die Anwender der Anlage: Aktiv-Status, Merkmale und "
            "Rollen. Merkmale steuern die Auswahl, Rechte kommen aus den "
            "Rollen.",
            verweis="personnel#zweck"),
        Kontexthilfe(
            "personnel.kennzeile", "Was hier möglich ist",
            "Nennt den Umfang dieser Sicht und weist auf zweierlei hin: die "
            "eigene Person ist unantastbar, und die Zuordnung von Rollen zu "
            "Rechten wird anderswo gepflegt.",
            verweis="personnel#rechte"),
        Kontexthilfe(
            "personnel.spalte.kennung", "Spalte „Kennung“",
            "Der Anmeldename aus dem Verzeichnisdienst. Die eigene Zeile ist "
            "mit „(ich)“ gekennzeichnet und trägt keine Bedienelemente.",
            verweis="personnel#rechte"),
        Kontexthilfe(
            "personnel.spalte.anzeigename", "Spalte „Anzeigename“",
            "Der Name aus dem Verzeichnisdienst."),
        Kontexthilfe(
            "personnel.spalte.status", "Spalte „Status“",
            "Aktiv oder deaktiviert. Bei Deaktivierten nennt der Hinweis "
            "beim Überfahren Zeitpunkt und Grund; die Zeile bleibt stehen, "
            "weil sie zur Vorgeschichte gehört."),
        Kontexthilfe(
            "personnel.spalte.investigator", "Spalte „Ermittler:in“",
            "Merkmal: die Person wird dort zur Auswahl angeboten, wo "
            "ermittelnde Personen gebraucht werden. Es ist KEIN Recht.",
            verweis="personnel#zweck"),
        Kontexthilfe(
            "personnel.spalte.supervisor", "Spalte „Supervisor“",
            "Merkmal: die Person wird als aufsichtführend angeboten, etwa "
            "bei der Abnahme. Es ist KEIN Recht.",
            verweis="personnel#zweck"),
        Kontexthilfe(
            "personnel.spalte.support", "Spalte „Support“",
            "Merkmal: die Person wird als unterstützend angeboten. Es ist "
            "KEIN Recht.",
            verweis="personnel#zweck"),
        Kontexthilfe(
            "personnel.spalte.rollen", "Spalte „Rollen“",
            "Die aktiven Rollenzuweisungen — sie tragen die Rechte. Der "
            "Filter dieser Spalte durchsucht die Rollenkürzel.",
            verweis="personnel#ablaeufe"),
        Kontexthilfe(
            "personnel.bedienung.flag_investigator",
            "Merkmal „Ermittler:in“ setzen",
            "Schaltet das Merkmal sofort um. Es entscheidet über das "
            "Angebot zur Auswahl, nicht über Rechte.",
            verweis="personnel#zweck"),
        Kontexthilfe(
            "personnel.bedienung.flag_supervisor",
            "Merkmal „Supervisor“ setzen",
            "Schaltet das Merkmal sofort um. Es entscheidet über das "
            "Angebot zur Auswahl, nicht über Rechte.",
            verweis="personnel#zweck"),
        Kontexthilfe(
            "personnel.bedienung.flag_support", "Merkmal „Support“ setzen",
            "Schaltet das Merkmal sofort um. Es entscheidet über das "
            "Angebot zur Auswahl, nicht über Rechte.",
            verweis="personnel#zweck"),
        Kontexthilfe(
            "personnel.bedienung.rolle_zuweisen", "Rolle zuweisen",
            "Weist der Person eine Rolle zu — und damit deren Rechte. "
            "Angeboten wird nur, was sie noch nicht hat.",
            verweis="personnel#ablaeufe"),
        Kontexthilfe(
            "personnel.bedienung.rolle_widerrufen", "Rolle widerrufen",
            "Nimmt die Zuweisung zurück. Die Zuweisung bleibt mit Zeitpunkt "
            "als Beleg erhalten; sie wirkt nur nicht mehr.",
            verweis="personnel#grenzen"),
        Kontexthilfe(
            "personnel.abschnitt.adsync", "AD-Abgleich",
            "Vergleicht die hier geführten Anwender mit dem "
            "Verzeichnisdienst. Der Abschnitt erscheint nur mit dem Recht "
            "personnel.sync.",
            verweis="personnel#grenzen"),
        Kontexthilfe(
            "personnel.bedienung.adsync_laden", "AD-Vorschau laden",
            "Holt den Stand aus dem Verzeichnisdienst. Das geschieht erst "
            "auf Anforderung, weil die Abfrage je nach Lage dauern kann.",
            verweis="personnel#ablaeufe"),

        # Die sechs Bedienelemente des AD-Abschnitts (Build 636, Welle B4).
        # Er ist seit Build 512 Teil DIESER Sicht und keine eigene - deshalb
        # tragen seine Marken den Praefix 'personnel.'.
        Kontexthilfe(
            "personnel.bedienung.adsync_vollzug",
            "Automatische Schritte vollziehen",
            "Führt die unstrittigen Schritte in einem Zug aus: neue Anwender "
            "aufnehmen und geänderte Namen nachziehen. Was in der "
            "Beschriftung steht, wird auch getan — und nur das. Alles "
            "Weitere verlangt eine Einzelentscheidung darunter.",
            verweis="personnel#ablaeufe"),
        Kontexthilfe(
            "personnel.bedienung.adsync_wort", "Bestätigungswort",
            "Das Wort, das genau so eingetippt werden muss, wie es in der "
            "Überschrift steht. Es ist die Sicherung gegen den Fehlklick: "
            "Eine Deaktivierung nimmt einem Menschen den Zugang, und das soll "
            "nicht versehentlich geschehen.",
            verweis="personnel#grenzen"),
        Kontexthilfe(
            "personnel.bedienung.adsync_notiz", "Notiz / Grund",
            "Die Begründung für den Abbruch — sie geht in den Beleg ein. Ohne "
            "sie bliebe offen, warum ein vorgeschlagener Schritt nicht "
            "vollzogen wurde."),
        Kontexthilfe(
            "personnel.bedienung.adsync_deaktivieren", "Deaktivieren",
            "Setzt diesen Anwender inaktiv, weil er im Verzeichnisdienst "
            "nicht mehr geführt wird. Nur mit dem richtig eingetippten "
            "Bestätigungswort; die Rollen bleiben als Beleg erhalten.",
            verweis="personnel#grenzen"),
        Kontexthilfe(
            "personnel.bedienung.adsync_abbruch", "Abbruch protokollieren",
            "Hält fest, dass der vorgeschlagene Schritt bewusst NICHT "
            "vollzogen wird. Das ist keine Untätigkeit, sondern eine "
            "Entscheidung — und sie gehört belegt."),
        Kontexthilfe(
            "personnel.bedienung.adsync_reaktivieren", "Reaktivieren",
            "Nimmt einen zurückgekehrten Anwender wieder in Betrieb. Seine "
            "früheren Rollen werden dabei WIEDER WIRKSAM — prüfen Sie, ob das "
            "noch passt.",
            verweis="personnel#grenzen"),
        Kontexthilfe(
            "personnel.werkzeug.filter_entfernen", "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Sicht auf einmal."),
        Kontexthilfe(
            "personnel.werkzeug.trefferzahl", "Trefferanzeige",
            "Nennt, wie viele Zeilen sichtbar sind; bei gesetztem Filter "
            "„sichtbar von gesamt“."),
    ),
)


# =============================================================================
# 2) capacity_pflege - "Kapazitaetspflege"
# =============================================================================
#
# VIER ABSCHNITTE, VIER TABELLEN, VIER KENNUNGEN: 'capacity_worktime',
# 'capacity_availability', 'capacity_holiday', 'capacity_reason'. Die
# Ueberschrift jedes Abschnitts und die Werkzeugleiste jeder Tabelle tragen
# Anker mit DIESEN Kennungen - nicht mit der Sicht-Kennung 'capacity_pflege'.
# Texte unter der Sicht-Kennung waeren an keiner der vier Tabellen je
# erschienen (derselbe Fall wie bei der Support-Historie, Build 602). Deshalb
# entstehen sie hier aus EINER Quelle je Abschnitt.

#: Abschnittskennung -> (Ueberschrift, Kurztext der Ueberschrift).
_ABSCHNITTE: Tuple[Tuple[str, str, str], ...] = (
    ("capacity_worktime", "Regel-Arbeitszeiten",
     "Minuten je Wochentag, gültig ab einem Stichtag. Eine Korrektur legt "
     "eine NEUE Zeile an; die bisherige bleibt als Beleg stehen."),
    ("capacity_availability", "Abwesenheiten und Garantien",
     "Zeiträume, die die verfügbare Zeit mindern oder einen Mindestboden "
     "sichern. Rechenart und Grund sind zwei verschiedene Felder."),
    ("capacity_holiday", "Feiertage",
     "Tage, die aus der Grundrechnung ALLER Personen herausfallen. Sie "
     "wirken anlagenweit."),
    ("capacity_reason", "Abwesenheitsgründe",
     "Der frei erweiterbare Katalog der Gründe. Welche Abwesenheitsarten "
     "vorkommen, entscheidet die Leitung."),
)


def _abschnitt_kontext() -> Tuple[Kontexthilfe, ...]:
    """
    Je Abschnitt: der Text der Überschrift und die beiden Bedienelemente der
    zugehörigen Werkzeugleiste. Die Werkzeugtexte sind wortgleich, weil die
    Bedienelemente dasselbe tun; der Abschnitt steht in der Überschrift
    darüber und muss im Popup nicht wiederholt werden.
    """
    raus: List[Kontexthilfe] = []
    for kennung, titel, text in _ABSCHNITTE:
        raus.append(Kontexthilfe(
            "%s.titel" % kennung, titel, text,
            verweis="capacity_pflege#aufbau"))
        raus.append(Kontexthilfe(
            "%s.werkzeug.filter_entfernen" % kennung, "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Tabelle auf einmal."))
        raus.append(Kontexthilfe(
            "%s.werkzeug.trefferzahl" % kennung, "Trefferanzeige",
            "Nennt, wie viele Zeilen sichtbar sind; bei gesetztem Filter "
            "„sichtbar von gesamt“."))
    return tuple(raus)


CAPACITY_PFLEGE = Sichthilfe(
    sicht="capacity_pflege",
    titel="Kapazitätspflege",
    recht_klartext=(
        "Recht: capacity.edit. Mit dem Umfang „alle“ pflegen Sie alle "
        "Personen sowie Feiertage und Gründe; mit dem Umfang „eigene“ nur "
        "die eigene Arbeitszeit und die eigenen Abwesenheiten — Feiertage "
        "und Gründe stehen dann nur zur Ansicht."
    ),
    anker_praefixe=("capacity_pflege",) + tuple(k for k, _t, _x in _ABSCHNITTE),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Hier werden die Angaben eingetragen, aus denen die Sicht "
                "„Kapazität“ ihre Zahlen rechnet: die regelmäßige "
                "Arbeitszeit, Abwesenheiten, Feiertage und der Katalog der "
                "Abwesenheitsgründe.",
                "Die Sicht ist bewusst von der Anzeige getrennt. Wer Zahlen "
                "ansehen will, geht auf „Kapazität“; wer sie pflegt, "
                "kommt hierher. So wird beim Speichern nicht jedes Mal die "
                "ganze Auswertung neu gezeichnet.",
                "ZAHLEN ÜBER VERFÜGBARKEIT SIND KEINE LEISTUNGSZAHLEN. Wer "
                "wenig verfügbar ist, arbeitet nicht schlechter.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "capacity.edit. Der zugeteilte Umfang steht als Klartext "
                "unter der Überschrift.",
                "Mit dem Umfang „eigene“ entfällt die Personenauswahl — es "
                "gibt genau eine Person. Feiertage und Gründe erscheinen "
                "trotzdem, aber nur zur Ansicht: sie wirken auf alle und "
                "sind deshalb der Leitung vorbehalten. Ganz ausblenden wäre "
                "schlechter — ohne den Gründekatalog stünde in den eigenen "
                "Abwesenheitszeilen ein nackter Code.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift mit der Umfangszeile, darunter die Zeile für "
                "Rückmeldungen und die Umschaltung „Auch entfernte Zeilen "
                "anzeigen“. Dann vier Abschnitte, jeder mit einem "
                "Erfassungsformular und einer Liste: Regel-Arbeitszeiten, "
                "Abwesenheiten und Garantien, Feiertage, Abwesenheitsgründe.",
                "Neben der Überschrift sitzt der Minutenrechner. Er trägt "
                "sein Ergebnis in das Minutenfeld ein, das zuletzt "
                "angeklickt wurde.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Arbeitszeit erfassen: Person wählen, Stichtag setzen, "
                "Minuten je Wochentag eintragen, speichern. Die beiden "
                "Knöpfe mit den üblichen Tagessätzen füllen Montag bis "
                "Freitag auf einmal — sie sind eine Hilfe, keine Vorschrift.",
                "Arbeitszeit korrigieren: „Bearbeiten“ in der Zeile. Das "
                "Formular füllt sich, und das Speichern ERSETZT die alte "
                "Zeile in einem Zug. Ohne diesen Weg ließe sich zum selben "
                "Stichtag keine zweite Regel anlegen.",
                "Abwesenheit eintragen: Zeitraum, Rechenart, Grund und "
                "GENAU EINES von Prozent oder Minuten. Beides zugleich wird "
                "zurückgewiesen.",
                "Etwas herausnehmen: „Entfernen“. Die Zeile fällt aus "
                "Rechnung und Liste, bleibt aber erhalten.",
                "Entferntes ansehen: die Umschaltung oben. Auch wenn sie aus "
                "ist, steht daneben, wie viele Zeilen ausgeblendet sind.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "ARBEITSZEIT WIRD NICHT ÜBERSCHRIEBEN. Jede Regel gilt ab "
                "einem Stichtag; eine Korrektur legt eine neue datierte "
                "Zeile an, und die alte bleibt stehen, weil sie der Beleg "
                "für den Zeitraum ist, in dem sie galt. Es gilt jeweils die "
                "Zeile mit dem jüngsten Stichtag vor dem Tag der Berechnung. "
                "Wer die alte Zeile für eine Doppelbuchung hält und sie "
                "loswerden will, sucht etwas, das es nicht geben darf.",
                "RECHENART IST NICHT GRUND. Die Rechenart entscheidet, WIE "
                "gerechnet wird: „Einschränkung“ zieht ab, „Garantie“ setzt "
                "einen Mindestboden. Der Grund sagt, WARUM — Urlaub, Krank, "
                "Schulung. Beides sind getrennte Felder.",
                "NICHTS WIRD HART GELÖSCHT. Entfernte Zeilen und "
                "stillgelegte Gründe bleiben erhalten; bestehende Einträge "
                "behalten ihren Bezug. Eingeblendete entfernte Zeilen sind "
                "gekennzeichnet und tragen keine Aktionsknöpfe.",
                "FEIERTAGE UND GRÜNDE WIRKEN AUF ALLE PERSONEN. Deshalb "
                "sind sie nur mit dem vollen Pflegeumfang änderbar.",
                "Nach jedem Speichern lädt die Sicht neu — auch im "
                "Fehlerfall. Dann zeigt die Liste den tatsächlichen Stand, "
                "und der ist: es wurde nichts geschrieben.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Kapazität — die Auswertung dieser Angaben.",
                "Lastverteilung — wie viele Fälle auf diese Zeit treffen.",
                "Prognose & Gantt — was daraus für die Termine folgt.",
                "Personalverwaltung — welche Personen es überhaupt gibt.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "capacity_pflege.titel", "Kapazitätspflege",
            "Die Pflegefläche für Arbeitszeiten, Abwesenheiten, Feiertage "
            "und Abwesenheitsgründe. Angesehen werden die Zahlen in der "
            "Sicht „Kapazität“.",
            verweis="capacity_pflege#zweck"),
        Kontexthilfe(
            "capacity_pflege.kennzeile", "Umfang der Pflege",
            "Nennt, was Sie hier pflegen dürfen: alle Personen samt "
            "Feiertagen und Gründen — oder nur die eigene Kapazität.",
            verweis="capacity_pflege#rechte"),
        Kontexthilfe(
            "capacity_pflege.bedienung.entfernte",
            "Auch entfernte Zeilen anzeigen",
            "Blendet die stillgelegten Zeilen aller vier Abschnitte ein. Sie "
            "sind gekennzeichnet und tragen keine Aktionsknöpfe. Auch bei "
            "ausgeschalteter Umschaltung steht daneben, wie viele Zeilen "
            "ausgeblendet sind.",
            verweis="capacity_pflege#grenzen"),
        Kontexthilfe(
            "capacity_pflege.bedienung.rechner", "Minutenrechner",
            "Öffnet eine kleine Rechenhilfe für Minutenangaben. Ihr Ergebnis "
            "geht in das Minutenfeld, das zuletzt angeklickt wurde.",
            verweis="capacity_pflege#aufbau"),
        # ------------------------------------------------------------------
        # Die Bedienelemente (Build 637, Welle B5 - die letzte). Die Erhebung
        # zaehlte hier DREI: Die Sicht baut Felder, Auswahllisten und Knoepfe
        # in drei Fabriken, und eine Fabrik zaehlt einmal. Tatsaechlich sind
        # es siebenundzwanzig, und alle bekommen hier ihren Text.
        # ------------------------------------------------------------------
        Kontexthilfe(
            "capacity_pflege.bedienung.entfernen", "Entfernen",
            "Legt diesen Eintrag still. GELÖSCHT WIRD NICHTS: Die Zeile "
            "bleibt als Beleg erhalten und lässt sich über „Auch entfernte "
            "Zeilen anzeigen“ wieder ansehen.",
            verweis="capacity_pflege#grenzen"),
        Kontexthilfe(
            "capacity_pflege.bedienung.wt_person", "Person",
            "Wessen Arbeitszeit eingetragen wird. Das Feld erscheint nur bei "
            "vollem Pflegeumfang; wer nur die eigene pflegt, sieht es nicht.",
            verweis="capacity_pflege#rechte"),
        Kontexthilfe(
            "capacity_pflege.bedienung.wt_ab", "Gültig ab",
            "Der Stichtag, ab dem diese Arbeitszeit gilt. Je Person und "
            "Stichtag gibt es GENAU EINE Zeile; eine zweite zum selben "
            "Stichtag wird abgewiesen. Für eine Korrektur ist „Bearbeiten“ "
            "der richtige Weg.",
            verweis="capacity_pflege#grenzen"),
        Kontexthilfe(
            "capacity_pflege.bedienung.wt_minuten", "Minuten je Wochentag",
            "Die Arbeitszeit dieses Wochentags in Minuten — sieben Felder, "
            "eines je Tag. 0 heißt „kein Arbeitstag“. Wer lieber in Stunden "
            "denkt, benutzt den Minutenrechner."),
        Kontexthilfe(
            "capacity_pflege.bedienung.wt_vorgabe",
            "Übliche Wochenarbeitszeit",
            "Trägt eine gebräuchliche Arbeitszeit in einem Griff ein: Montag "
            "bis Freitag auf den genannten Wert, Samstag und Sonntag auf 0. "
            "Abweichungen sind zulässig — die Felder lassen sich danach "
            "einzeln ändern."),
        Kontexthilfe(
            "capacity_pflege.bedienung.wt_bearbeiten", "Bearbeiten",
            "Füllt das Formular mit dieser Zeile und schaltet auf Ersetzen "
            "um. ES WIRD DABEI NICHTS GESCHRIEBEN. Das ist der einzige Weg, "
            "eine Arbeitszeit zum selben Stichtag zu berichtigen.",
            verweis="capacity_pflege#ablaeufe"),
        Kontexthilfe(
            "capacity_pflege.bedienung.wt_entfernen", "Entfernen",
            "Legt diese Arbeitszeit still. Sie bleibt als Beleg erhalten; an "
            "einer bereits stillgelegten Zeile erscheint der Knopf nicht "
            "mehr.",
            verweis="capacity_pflege#grenzen"),
        Kontexthilfe(
            "capacity_pflege.bedienung.wt_abbrechen", "Bearbeitung abbrechen",
            "Verlässt den Ersetzen-Modus. Die vorhandene Zeile bleibt, wie "
            "sie ist; geschrieben wurde nichts."),
        Kontexthilfe(
            "capacity_pflege.bedienung.wt_speichern", "Arbeitszeit speichern",
            "Schreibt die Arbeitszeit fest. Im Ersetzen-Modus heißt der Knopf "
            "„Zeile ersetzen“ und tut auch das: Die alte Zeile wird "
            "stillgelegt und bleibt als Beleg erhalten.",
            verweis="capacity_pflege#ablaeufe"),
        Kontexthilfe(
            "capacity_pflege.bedienung.av_person", "Person",
            "Wessen Abwesenheit eingetragen wird — nur bei vollem "
            "Pflegeumfang.",
            verweis="capacity_pflege#rechte"),
        Kontexthilfe(
            "capacity_pflege.bedienung.av_von", "Von",
            "Erster Tag der Abwesenheit. Ist das Bis-Feld noch LEER, wird es "
            "beim Setzen dieses Datums damit vorbelegt — für eine "
            "eintägige Abwesenheit genügt deshalb eine einzige Eingabe. Ein "
            "bereits gefülltes Bis-Feld wird dabei NIE überschrieben."),
        Kontexthilfe(
            "capacity_pflege.bedienung.av_bis", "Bis",
            "Letzter Tag der Abwesenheit, einschließlich. Der Kalender lässt "
            "kein Datum vor dem Von-Datum zu. Steht hier bereits ein früheres "
            "Datum, wird es nicht stillschweigend berichtigt, sondern rot "
            "markiert und in der Ergebniszeile benannt — die Korrektur "
            "bleibt Ihre Entscheidung.",
            verweis="capacity_pflege#grenzen"),
        Kontexthilfe(
            "capacity_pflege.bedienung.av_rechenart", "Rechenart",
            "WIE die Abwesenheit auf die Kapazität wirkt: abziehen oder "
            "einen Mindestboden setzen. Das ist etwas anderes als der "
            "Grund — der sagt, WARUM.",
            verweis="capacity_pflege#grenzen"),
        Kontexthilfe(
            "capacity_pflege.bedienung.av_grund", "Grund",
            "Warum die Person abwesend ist — freiwillig. Die Gründe werden "
            "weiter unten auf derselben Seite gepflegt."),
        Kontexthilfe(
            "capacity_pflege.bedienung.av_grund_leer",
            "Hinweis: Gründekatalog leer",
            "Erscheint nur, wenn die Auswahl außer „(kein Grund)“ nichts "
            "anzubieten hat. Ohne diesen Hinweis wäre der Zustand nicht von "
            "einem Übertragungsfehler zu unterscheiden. PRÜFEN SIE die "
            "Tabelle „Abwesenheitsgründe“ weiter unten: Ist sie ebenfalls "
            "leer, ist der Katalog schlicht noch nicht gepflegt. Stehen dort "
            "Einträge, während die Auswahl leer bleibt, ist das ein Fehler "
            "und zu melden.",
            verweis="capacity_pflege#grenzen"),
        Kontexthilfe(
            "capacity_pflege.bedienung.av_prozent", "Prozent",
            "Der Anteil, um den die Kapazität sinkt. GENAU EINES von Prozent "
            "oder Minuten ausfüllen — beides zugleich wird abgewiesen, und "
            "das ist eine Regel der Sache und kein Formularfehler.",
            verweis="capacity_pflege#grenzen"),
        Kontexthilfe(
            "capacity_pflege.bedienung.av_minuten", "Minuten",
            "Die Kürzung in Minuten je Tag. Auch hier: entweder Prozent oder "
            "Minuten, nie beides. Ein LEERES Feld ist keine Angabe — eine 0 "
            "wäre eine.",
            verweis="capacity_pflege#grenzen"),
        Kontexthilfe(
            "capacity_pflege.bedienung.av_notiz", "Notiz",
            "Eine Bemerkung zur Abwesenheit — freiwillig."),
        Kontexthilfe(
            "capacity_pflege.bedienung.av_speichern", "Abwesenheit speichern",
            "Schreibt die Abwesenheit fest. Fehlt eine Pflichtangabe oder "
            "sind Prozent und Minuten beide gesetzt, wird nichts "
            "geschrieben.",
            verweis="capacity_pflege#grenzen"),
        Kontexthilfe(
            "capacity_pflege.bedienung.ho_tag", "Tag",
            "Das Datum des Feiertags. Feiertage gelten für alle und werden "
            "deshalb nur bei vollem Pflegeumfang angelegt.",
            verweis="capacity_pflege#grenzen"),
        Kontexthilfe(
            "capacity_pflege.bedienung.ho_bezeichnung", "Bezeichnung",
            "Der Name des Feiertags. Er erscheint später in der Liste — ohne "
            "ihn steht dort nur ein Datum."),
        Kontexthilfe(
            "capacity_pflege.bedienung.ho_region", "Region",
            "Für welchen Landesteil der Tag gilt — freiwillig. Leer heißt: "
            "für alle."),
        Kontexthilfe(
            "capacity_pflege.bedienung.ho_anlegen", "Feiertag anlegen",
            "Trägt den Feiertag ein. Er wirkt ab sofort auf die Berechnung "
            "der Kapazität aller Personen.",
            verweis="capacity_pflege#grenzen"),
        Kontexthilfe(
            "capacity_pflege.bedienung.re_code", "Code",
            "Das Kürzel, unter dem der Grund geführt wird. Es ist die "
            "Verbindung zu den bereits eingetragenen Abwesenheiten."),
        Kontexthilfe(
            "capacity_pflege.bedienung.re_bezeichnung", "Bezeichnung",
            "Wie der Grund in der Auswahlliste heißt."),
        Kontexthilfe(
            "capacity_pflege.bedienung.re_reihung", "Reihung",
            "Bestimmt die Reihenfolge in der Auswahlliste. Ein kleinerer "
            "Wert steht weiter oben."),
        Kontexthilfe(
            "capacity_pflege.bedienung.re_anlegen", "Grund anlegen",
            "Trägt den Abwesenheitsgrund ein. Er steht danach in der Auswahl "
            "des Abwesenheits-Formulars zur Verfügung."),
        Kontexthilfe(
            "capacity_pflege.bedienung.rechner_zeitangabe", "Zeitangabe",
            "Eine Zeit in der Schreibweise, die Ihnen liegt — auch mit "
            "Komma. Das Feld nimmt ausdrücklich Text entgegen und nicht nur "
            "Zahlen: Ein Zahlenfeld verwirft ein Komma je nach Browser "
            "stillschweigend, und ein still verworfener Wert ist schlimmer "
            "als eine Fehlermeldung.",
            verweis="capacity_pflege#aufbau"),
    ) + _abschnitt_kontext(),
)


#: Der Teilbestand dieser Nav-Gruppe, in Katalogreihenfolge
#: (personnel, capacity_pflege - siehe VIEW_CATALOG).
PERSONAL: Tuple[Sichthilfe, ...] = (PERSONNEL, CAPACITY_PFLEGE)
