# =============================================================================
# management/help/inhalt/redaktion.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H9)
# =============================================================================
# Zweck:
#   Die Hilfetexte der Nav-Gruppe "Redaktion": templates (Platzhalter &
#   Queries), doctemplates (Dokumentvorlagen), modules (Baustein-Module).
#
#   DREI AUTORENSICHTEN, DREI BAUTEILE EINES VERMERKS. Ein Vermerk entsteht
#   aus einer VORLAGE (das Geruest), enthaelt BAUSTEINE (wiederverwendbare
#   Textstuecke) und darin PLATZHALTER (Werte, die erst beim Schreiben des
#   konkreten Vermerks eingesetzt werden). Wer nicht weiss, welches der drei
#   er gerade pflegt, pflegt das falsche - deshalb steht die Abgrenzung in
#   allen drei Kapiteln.
#
#   DIE DREI PLATZHALTERARTEN sind das eigentlich Erklaerungsbeduerftige und
#   stehen deshalb in jedem der drei Kapitel gleichlautend.
#
# REGEL H-1 (Anwendersprache), REGEL H-0 (fallinhaltsfrei).
#
# Version: v0.8.598 - Build: 598 - 2026-07-31
# =============================================================================

from __future__ import annotations

from typing import Tuple

from management.help.modell import Abschnitt, Kontexthilfe, Sichthilfe

_STAND = 598

#: Redaktionsstand der in Welle B3 (Build 635) nachredigierten Kapitel.
_STAND_B3 = 635

#: Die drei Platzhalterarten - woertlich gleich in allen drei Kapiteln.
_ARTEN = (
    "{{a:name}} — AUTOMATISCH. Der Wert wird beim Schreiben des Vermerks aus "
    "der Fallakte geholt. Dahinter steht eine gespeicherte Abfrage.",
    "{{m:name}} — VERPFLICHTEND. Die schreibende Person muss den Wert "
    "eingeben; ohne ihn ist der Vermerk nicht vollständig.",
    "{{o:name}} — OPTIONAL. Die schreibende Person kann den Wert eingeben; "
    "bleibt er leer, entfällt die Stelle.",
)

_BAUTEILE = (
    "Dokumentvorlagen — das Gerüst: aus welchen Blöcken ein Vermerk besteht.",
    "Baustein-Module — die wiederverwendbaren Textstücke, die in ein Gerüst "
    "eingefügt werden.",
    "Platzhalter & Queries — die Werte, die in Bausteinen und Vorlagen offen "
    "bleiben und erst beim Schreiben eingesetzt werden.",
)


# =============================================================================
# 1) templates - "Platzhalter & Queries"
# =============================================================================

TEMPLATES = Sichthilfe(
    sicht="templates",
    titel="Platzhalter & Queries",
    recht_klartext=(
        "Recht: templates.edit. Dasselbe Recht trägt auch die Pflege der "
        "Dokumentvorlagen und der Baustein-Module — die drei gehören zur "
        "Redaktionsarbeit und werden nicht getrennt zugeteilt. Jede Änderung "
        "wird protokolliert."
    ),
    stand=_STAND_B3,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Ein Platzhalter ist eine Stelle im Text, die beim Schreiben "
                "eines konkreten Vermerks gefüllt wird — mit einem Wert aus "
                "der Fallakte oder mit einer Eingabe. Hier werden diese "
                "Platzhalter angelegt und gepflegt.",
                "Der Gewinn ist Einheitlichkeit: Wenn dieselbe Angabe in "
                "hundert Vermerken vorkommt, soll sie hundertmal gleich "
                "heißen und gleich zustande kommen.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "templates.edit. Das Anlegen und Ändern läuft über den "
                "protokollierten Schreibweg; die Probeauswertung schreibt "
                "nichts.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter der Hinweis auf die drei "
                "Platzhalterarten, darunter die Liste der vorhandenen "
                "Platzhalter und die Bearbeitungsmaske.",
            ),
        ),
        Abschnitt(
            "arten", "Die drei Platzhalterarten",
            (
                "Woran man sie im Text erkennt und was sie bedeuten:",
            ),
            liste=_ARTEN,
        ),
        Abschnitt(
            "probe", "Die Probeauswertung",
            (
                "Vor dem Speichern lässt sich ein automatischer Platzhalter "
                "gegen eine Beispiel-Fallakte ausprobieren. Die Probe "
                "SCHREIBT NICHTS — sie zeigt nur, was herauskäme.",
                "Das ist der Kern dieser Sicht: Ein Platzhalter, der erst "
                "beim fertigen Vermerk auffällt, hat dort bereits Schaden "
                "angerichtet. Lieber vorher einmal ausprobieren als nachher "
                "hundert Vermerke prüfen.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Einen automatischen Platzhalter anlegen: Namen vergeben, "
                "Abfrage eintragen, Probeauswertung fahren, erst dann "
                "speichern.",
                "Einen Eingabe-Platzhalter anlegen: entscheiden, ob "
                "verpflichtend oder optional — das ist die eigentliche "
                "Festlegung.",
                "Einen bestehenden ändern: bedenken, dass er in vorhandenen "
                "Bausteinen und Vorlagen bereits benutzt wird. Der Name ist "
                "die Verbindung; wer ihn ändert, trennt sie.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "Eine Abfrage darf ausschließlich LESEN. Es gibt hier keinen "
                "Weg, über einen Platzhalter etwas an einer Fallakte zu "
                "verändern.",
                "Eine Abfrage bezieht sich immer auf GENAU EINEN Fall. Sie "
                "kann nicht über Fälle hinweg zusammenfassen — das wäre eine "
                "Auswertung und gehört nicht in einen Platzhalter.",
                "Die Probeauswertung schreibt nichts. Sie verändert weder die "
                "Beispielakte noch den gespeicherten Platzhalter.",
                "Ein Platzhalter wird hier NICHT aufgelöst. Aufgelöst wird "
                "erst beim Schreiben des konkreten Vermerks.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (
                "Drei Sichten pflegen drei Bauteile eines Vermerks:",
            ),
            liste=_BAUTEILE + (
                "Berichts-Abnahme — wo die fertigen Vermerke landen.",),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "templates.titel", "Platzhalter & Queries",
            "Pflegt die Stellen, die in Bausteinen und Vorlagen offen bleiben "
            "und erst beim Schreiben eines Vermerks gefüllt werden.",
            verweis="templates#zweck"),
        Kontexthilfe(
            "templates.hinweis", "Die drei Arten auf einen Blick",
            "Nennt die drei Platzhalterarten und die Regeln für automatische "
            "Platzhalter: Die Abfrage darf nur lesen und bezieht sich auf "
            "genau einen Fall. Vor dem Speichern ausprobieren.",
            verweis="templates#arten"),

        # ------------------------------------------------------------------
        # Die Bedienelemente (Build 635, Welle B3). Die Eingabefelder
        # stammen alle aus der Fabrik '_labeledField'; ihre Marken sitzen an
        # den Abnahmestellen (Fabrikregel, Build 633).
        # ------------------------------------------------------------------
        Kontexthilfe(
            "templates.bedienung.neu", "Neuer Platzhalter",
            "Leert die Maske für eine Neuanlage. Ein bereits geladener "
            "Platzhalter wird dabei nicht verändert — geschrieben wird erst "
            "mit „Speichern“."),
        Kontexthilfe(
            "templates.bedienung.waehlen", "Platzhalter aus der Liste",
            "Lädt diesen Platzhalter in die Maske. Das ist ein Ladevorgang "
            "und kein Schreibvorgang."),
        Kontexthilfe(
            "templates.bedienung.kennung", "Name des Platzhalters",
            "Der Name, unter dem der Platzhalter in Bausteinen und Vorlagen "
            "steht. ER IST DIE VERBINDUNG: Wer ihn ändert, trennt sie — die "
            "Stellen, die ihn benutzen, finden ihn dann nicht mehr.",
            verweis="templates#ablaeufe"),
        Kontexthilfe(
            "templates.bedienung.titel", "Titel",
            "Die Bezeichnung für Menschen. Sie steht in der Liste links und "
            "hat auf die Auflösung keinen Einfluss."),
        Kontexthilfe(
            "templates.bedienung.beschreibung", "Beschreibung",
            "Wofür dieser Platzhalter gedacht ist. Ein Satz hier erspart der "
            "nächsten Person die Rückfrage, ob sie den richtigen erwischt "
            "hat."),
        Kontexthilfe(
            "templates.bedienung.typ", "Art des Platzhalters",
            "Automatisch, verpflichtend oder optional. Das ist die "
            "eigentliche Festlegung: Ein automatischer Platzhalter holt "
            "seinen Wert selbst, die anderen beiden verlangen ihn von der "
            "schreibenden Person.",
            verweis="templates#arten"),
        Kontexthilfe(
            "templates.bedienung.abfrage", "Abfrage",
            "Die Abfrage, aus der ein automatischer Platzhalter seinen Wert "
            "holt. Sie darf AUSSCHLIESSLICH LESEN und bezieht sich immer auf "
            "genau einen Fall — eine Zusammenfassung über Fälle hinweg wäre "
            "eine Auswertung und gehört nicht in einen Platzhalter.",
            verweis="templates#grenzen"),
        Kontexthilfe(
            "templates.bedienung.rueckgabetyp", "Art des Ergebnisses",
            "Was die Abfrage liefern soll — ein einzelner Wert oder eine "
            "Aufstellung. Die Angabe entscheidet darüber, wie das Ergebnis "
            "im Vermerk erscheint."),
        Kontexthilfe(
            "templates.bedienung.schlagworte", "Schlagworte",
            "Freiwillige Stichworte zum Wiederfinden. Sie wirken sich auf die "
            "Auflösung nicht aus."),
        Kontexthilfe(
            "templates.bedienung.vorgabewert", "Vorgabewert",
            "Der Wert, der voreingetragen erscheint, wenn die schreibende "
            "Person nichts angibt — freiwillig. Bei einem verpflichtenden "
            "Platzhalter ersetzt er die Eingabe NICHT."),
        Kontexthilfe(
            "templates.bedienung.pruefart", "Prüfart",
            "Wie die Eingabe geprüft wird: mit einem Suchmuster, gegen eine "
            "Liste erlaubter Werte oder mit einem einfachen Vergleichsmuster. "
            "Welche Schreibweise die gewählte Art erwartet, steht als "
            "Kurzhinweis unter dem Feld.",
            verweis="templates#grenzen"),
        Kontexthilfe(
            "templates.bedienung.pruefregel", "Prüfregel",
            "Die Regel selbst, in der Schreibweise der gewählten Prüfart. "
            "Unter dem Feld wird sofort gemeldet, ob die Regel überhaupt "
            "gültig ist — eine fehlerhafte Regel würde sonst erst beim "
            "Schreiben eines Vermerks auffallen."),
        Kontexthilfe(
            "templates.bedienung.schreibweise",
            "Groß- und Kleinschreibung ignorieren",
            "Lässt die Prüfung Groß- und Kleinschreibung außer Acht. Gilt für "
            "alle drei Prüfarten. Im Zweifel einschalten: Eine Eingabe, die "
            "nur wegen eines großen Anfangsbuchstabens abgewiesen wird, "
            "wirkt auf die schreibende Person wie ein Fehler des Werkzeugs."),
        Kontexthilfe(
            "templates.bedienung.testeingabe", "Testfeld",
            "Ein Beispielwert, der sofort gegen die Prüfregel gehalten wird. "
            "Er wird nirgends gespeichert — das Feld dient nur dazu, die "
            "Regel auszuprobieren, bevor sie gilt."),
        Kontexthilfe(
            "templates.bedienung.probe_konto", "Beispiel-Fall für die Probe",
            "Der Fall, gegen den die Probeauswertung läuft. Wählen Sie einen, "
            "bei dem Sie das erwartete Ergebnis kennen — sonst sagt die Probe "
            "wenig.",
            verweis="templates#probe"),
        Kontexthilfe(
            "templates.bedienung.probelauf", "Probeauswertung",
            "Führt die Abfrage gegen den angegebenen Beispiel-Fall aus und "
            "zeigt, was herauskäme. SIE SCHREIBT NICHTS — weder an der "
            "Beispielakte noch am Platzhalter.",
            verweis="templates#probe"),
        Kontexthilfe(
            "templates.bedienung.speichern", "Speichern",
            "Schreibt den Platzhalter fest; der Vorgang wird protokolliert. "
            "Bedenken Sie vorher, dass ein geänderter Platzhalter überall "
            "wirkt, wo er schon benutzt wird.",
            verweis="templates#ablaeufe"),
    ),
)


# =============================================================================
# 2) doctemplates - "Dokumentvorlagen"
# =============================================================================

DOCTEMPLATES = Sichthilfe(
    sicht="doctemplates",
    titel="Dokumentvorlagen",
    recht_klartext=(
        "Recht: templates.edit — dasselbe wie für Platzhalter und Bausteine. "
        "Jede Änderung wird protokolliert."
    ),
    stand=_STAND_B3,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Eine Dokumentvorlage ist das Gerüst eines Vermerks: die "
                "Abfolge der Blöcke, aus denen er besteht. Wer einen neuen "
                "Vermerk beginnt, bekommt dieses Gerüst und muss nicht mit "
                "einem leeren Blatt anfangen.",
                "Der Gewinn ist Vergleichbarkeit: Vermerke derselben Art "
                "sollen denselben Aufbau haben. Das erleichtert nicht nur das "
                "Schreiben, sondern vor allem das Lesen — bei der Abnahme und "
                "später bei Gericht.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "templates.edit. Das Speichern läuft über den protokollierten "
                "Schreibweg; die Strukturvorschau schreibt nichts.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, Hinweis, Liste der vorhandenen Vorlagen und der "
                "Blocklisten-Editor: je Block eine Art und der zugehörige "
                "Inhalt.",
                "Jede Vorlage hat eine feste Kennung, unter der sie geladen "
                "wird. Diese Kennung ist die Verbindung zum Berichtseditor — "
                "sie zu ändern trennt sie.",
            ),
        ),
        Abschnitt(
            "arten", "Die drei Platzhalterarten",
            (
                "Platzhalter in einer Vorlage bleiben stehen und werden erst "
                "beim Schreiben des konkreten Vermerks eingesetzt:",
            ),
            liste=_ARTEN,
        ),
        Abschnitt(
            "vorschau", "Die Strukturvorschau",
            (
                "Vor dem Speichern lässt sich die Struktur prüfen: Sie zeigt, "
                "welche Blockarten in welcher Zahl vorkommen, und meldet "
                "Fehler in der Zusammenstellung. Sie SCHREIBT NICHTS.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Eine Vorlage anlegen: Kennung und Namen vergeben, Blöcke in "
                "der gewünschten Reihenfolge zusammenstellen, "
                "Strukturvorschau fahren, speichern.",
                "Eine Vorlage ändern: bedenken, dass bereits geschriebene "
                "Vermerke davon unberührt bleiben — die Änderung wirkt nur "
                "auf künftige.",
                "Eine Vorlage außer Gebrauch nehmen: nicht die Kennung "
                "ändern, sondern eine neue Vorlage anlegen. Eine geänderte "
                "Kennung findet der Berichtseditor nicht mehr.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "Eine Änderung an einer Vorlage wirkt NUR AUF KÜNFTIGE "
                "Vermerke. Bereits geschriebene bleiben, wie sie sind — sonst "
                "änderte sich rückwirkend, was jemand unterschrieben hat.",
                "Platzhalter werden hier NICHT aufgelöst. Sie stehen in der "
                "Vorlage als Platzhalter und werden erst beim Schreiben "
                "eingesetzt.",
                "Die Strukturvorschau schreibt nichts und legt nichts an.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (
                "Drei Sichten pflegen drei Bauteile eines Vermerks:",
            ),
            liste=_BAUTEILE + (
                "Berichts-Abnahme — wo die fertigen Vermerke landen.",),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "doctemplates.titel", "Dokumentvorlagen",
            "Pflegt die Gerüste, aus denen neue Vermerke entstehen: welche "
            "Blöcke in welcher Reihenfolge.",
            verweis="doctemplates#zweck"),
        Kontexthilfe(
            "doctemplates.hinweis", "Was eine Vorlage enthält",
            "Eine Vorlage besteht aus Blöcken. Platzhalter darin bleiben "
            "stehen und werden erst beim Schreiben des konkreten Vermerks "
            "eingesetzt. Vor dem Speichern die Strukturvorschau fahren.",
            verweis="doctemplates#vorschau"),

        # Die elf Bedienelemente (Build 635, Welle B3).
        Kontexthilfe(
            "doctemplates.bedienung.neue_vorlage", "Neue Vorlage",
            "Leert die Maske für eine Neuanlage. Eine bereits geladene "
            "Vorlage wird dabei nicht verändert."),
        Kontexthilfe(
            "doctemplates.bedienung.vorlage_waehlen", "Vorlage aus der Liste",
            "Lädt diese Vorlage in die Maske. Ein Ladevorgang, kein "
            "Schreibvorgang."),
        Kontexthilfe(
            "doctemplates.bedienung.schluessel", "Kennung der Vorlage",
            "Die feste Kennung, unter der die Vorlage geladen wird. SIE IST "
            "DIE VERBINDUNG zum Berichtseditor: Wer sie ändert, trennt sie. "
            "Eine Vorlage außer Gebrauch nehmen heißt deshalb NICHT, die "
            "Kennung zu ändern, sondern eine neue anzulegen.",
            verweis="doctemplates#ablaeufe"),
        Kontexthilfe(
            "doctemplates.bedienung.vorlagentitel", "Titel der Vorlage",
            "Die Bezeichnung für Menschen. Sie steht in der Liste links."),
        Kontexthilfe(
            "doctemplates.bedienung.beschreibung", "Beschreibung",
            "Wofür diese Vorlage gedacht ist — freiwillig, aber die "
            "einfachste Art, ein Verwechseln zweier ähnlicher Vorlagen zu "
            "verhindern."),
        Kontexthilfe(
            "doctemplates.bedienung.vermerkstyp", "Vermerkstyp",
            "Für welche Art von Schriftstück die Vorlage gedacht ist: "
            "Vermerk, Ergänzungsvermerk oder Abschlussbericht."),
        Kontexthilfe(
            "doctemplates.bedienung.sortierung", "Sortierung",
            "Bestimmt die Reihenfolge in der Auswahl beim Anlegen eines "
            "Vermerks. Ein kleinerer Wert steht weiter oben."),
        Kontexthilfe(
            "doctemplates.bedienung.blockart", "Art des Blocks",
            "Was für ein Baustein an dieser Stelle steht — Absatz, "
            "Überschrift, Aufzählung und so fort. Beim Wechsel wird ein noch "
            "leerer Inhalt durch ein passendes Gerüst ersetzt; ein "
            "ausgefüllter bleibt unangetastet."),
        Kontexthilfe(
            "doctemplates.bedienung.blockdaten", "Inhalt des Blocks",
            "Die Angaben dieses Blocks in strukturierter Schreibweise. "
            "Platzhalter darin bleiben stehen und werden erst beim Schreiben "
            "des konkreten Vermerks eingesetzt. Ob die Zusammenstellung "
            "stimmt, sagt die Strukturvorschau.",
            verweis="doctemplates#vorschau"),
        Kontexthilfe(
            "doctemplates.bedienung.block_hoch", "Block nach oben",
            "Tauscht diesen Block mit dem darüber. Die Reihenfolge der Blöcke "
            "ist die Reihenfolge im späteren Vermerk."),
        Kontexthilfe(
            "doctemplates.bedienung.block_runter", "Block nach unten",
            "Tauscht diesen Block mit dem darunter."),
        Kontexthilfe(
            "doctemplates.bedienung.block_entfernen", "Block entfernen",
            "Nimmt diesen Block aus der Vorlage. Das wirkt nur auf die "
            "Vorlage in der Maske; geschrieben wird erst mit „Speichern“, und "
            "bereits verfasste Vermerke bleiben unberührt.",
            verweis="doctemplates#grenzen"),
        Kontexthilfe(
            "doctemplates.bedienung.block_hinzufuegen", "Block hinzufügen",
            "Hängt einen weiteren Block an das Ende der Vorlage. Verschieben "
            "lässt er sich anschließend mit den Pfeilen in seiner Zeile."),
        Kontexthilfe(
            "doctemplates.bedienung.strukturvorschau", "Strukturvorschau",
            "Prüft die Zusammenstellung: welche Blockarten in welcher Zahl "
            "vorkommen und ob etwas nicht zusammenpasst. SIE SCHREIBT NICHTS "
            "und legt nichts an.",
            verweis="doctemplates#vorschau"),
        Kontexthilfe(
            "doctemplates.bedienung.speichern", "Speichern",
            "Schreibt die Vorlage fest; der Vorgang wird protokolliert. Die "
            "Änderung wirkt NUR AUF KÜNFTIGE Vermerke — bereits geschriebene "
            "bleiben, wie sie sind.",
            verweis="doctemplates#grenzen"),
    ),
)


# =============================================================================
# 3) modules - "Baustein-Module"
# =============================================================================

MODULES = Sichthilfe(
    sicht="modules",
    titel="Baustein-Module",
    recht_klartext=(
        "Recht: templates.edit — dasselbe wie für Platzhalter und "
        "Dokumentvorlagen. Jede Änderung wird protokolliert."
    ),
    stand=_STAND_B3,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Ein Baustein ist ein wiederverwendbares Textstück, das sich "
                "beim Schreiben eines Vermerks einfügen lässt — eine "
                "Rechtsbelehrung, ein wiederkehrender Befund, eine "
                "Standardformulierung.",
                "Der Gewinn ist doppelt: Die Formulierung ist einmal "
                "sorgfältig geschrieben statt fünfzigmal frei erfunden, und "
                "sie lässt sich an einer Stelle nachbessern.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "templates.edit. Das Speichern läuft über den protokollierten "
                "Schreibweg; die Vorschau schreibt nichts.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Oben die Tabelle aller vorhandenen Bausteine, darunter "
                "links die Bearbeitungsmaske und rechts die Vorschau.",
                "Die Tabelle lässt sich in jeder Spalte filtern und "
                "sortieren und blättert in Seiten zu 15 Zeilen. Ein Klick "
                "auf eine Zeile lädt den Baustein in die Maske; die "
                "geladene Zeile bleibt markiert.",
                "Reicht die Breite nicht für zwei Spalten, rückt die "
                "Vorschau unter die Maske.",
                "Jeder Baustein hat eine feste Kennung, unter der ihn der "
                "Berichtseditor einfügt. Sie ist die Verbindung — wer sie "
                "ändert, trennt sie.",
            ),
        ),
        Abschnitt(
            "arten", "Die drei Platzhalterarten",
            (
                "Der Text eines Bausteins darf Platzhalter enthalten. Sie "
                "bleiben stehen und werden erst beim Schreiben des konkreten "
                "Vermerks eingesetzt:",
            ),
            liste=_ARTEN,
        ),
        Abschnitt(
            "vorschau", "Die Vorschau",
            (
                "Die Vorschau zeigt, wie der Baustein im Berichtseditor "
                "aussehen wird, und zählt die enthaltenen Platzhalter. Sie "
                "SCHREIBT NICHTS.",
                "Sie steht rechts neben der Maske und ist dauerhaft "
                "eingeblendet — es muss nichts angeklickt werden, damit sie "
                "erscheint. Sie läuft beim Tippen mit, kurz verzögert, damit "
                "sie sich nicht bei jedem Tastendruck neu aufbaut.",
                "Ist das Fenster zu schmal für drei Spalten, rückt die "
                "Vorschau unter die Maske. Das ist kein Fehler, sondern die "
                "Platzregel: Die Maske behält Vorrang vor der Ansicht.",
                "Die Platzhalterzählung ist der eigentliche Prüfwert: Ein "
                "vertippter Platzhaltername fällt hier auf — im fertigen "
                "Vermerk fiele er als leere Stelle auf.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Einen Baustein anlegen: Kennung und Namen vergeben, Text "
                "schreiben, Vorschau fahren, Platzhalterzahl prüfen, "
                "speichern.",
                "Einen Baustein nachbessern: Der neue Wortlaut gilt für "
                "künftige Vermerke; bereits geschriebene bleiben unberührt.",
                "Einen Baustein außer Gebrauch nehmen: nicht die Kennung "
                "ändern, sondern einen neuen anlegen.",
                "Einen Platzhalter prüfen: In der Tabelle unter dem Text "
                "eine Beispieleingabe in die Spalte „Testeingabe“ schreiben. "
                "Passt sie nicht, passt sie auch beim Ausfüllen nicht.",
                "Eine fehlende Kennung nachtragen: „Nur ohne Kennung“ "
                "einschalten, Zeile anklicken, den Vorschlag prüfen oder "
                "ersetzen, speichern. Danach ist die Kennung endgültig.",
            ),
        ),
        Abschnitt(
            "platzhaltertabelle", "Die Platzhalter-Tabelle",
            (
                "Unter dem Bausteintext stehen alle Platzhalter, die er "
                "enthält — mit Typ, Name, Vorgabe, Beschreibung, Prüfmuster "
                "und der Zahl der Vorkommen. Die Tabelle läuft beim Tippen "
                "mit und SCHREIBT NICHTS.",
                "Das Prüfmuster steht im Klartext da, auch wenn es im "
                "Bausteintext verschlüsselt hinterlegt ist oder nur als "
                "Verweis auf eine benannte Formatregel.",
                "Die Spalte „Verifikation“ nennt jeden Befund im Klartext "
                "und nicht nur als Farbe. Sechs Dinge werden geprüft:",
            ),
            liste=(
                "V1 — Etwas sieht aus wie ein Platzhalter, ist aber keiner: "
                "ein Leerzeichen im Namen, ein unbekanntes Kürzel, ein Feld "
                "zu viel. DAS IST DER WICHTIGSTE BEFUND. Solcher Text löst "
                "keinen Fehler aus, er steht am Ende wörtlich im Vermerk.",
                "V2 — Ein automatischer Platzhalter, den es nicht gibt, der "
                "abgeschaltet ist oder der anderswo anders geführt wird.",
                "V3 — Ein Eingabefeld, dessen Art von der hinterlegten "
                "abweicht — etwa freiwillig hier, verpflichtend dort.",
                "V4 — Ein Prüfmuster, das ins Leere zeigt oder sich nicht "
                "übersetzen lässt.",
                "V5 — Das Prüfmuster am Platzhalter weicht von dem "
                "hinterlegten ab. Kein Fehler, aber beim Ausfüllen gilt das "
                "hinterlegte.",
                "V6 — Derselbe Name steht mehrfach im Text, aber mit "
                "verschiedenen Angaben. Beim Ausfüllen gewinnt eine Fassung, "
                "und welche, sieht man dem Text nicht an.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "Eine Änderung wirkt NUR AUF KÜNFTIGE Vermerke. Bereits "
                "geschriebene bleiben, wie sie sind — sonst änderte sich "
                "rückwirkend, was jemand unterschrieben hat.",
                "Platzhalter werden hier NICHT aufgelöst. Ob es einen Namen "
                "gibt und ob eine Eingabe zum Muster passt, prüft die "
                "Tabelle unter dem Text; gepflegt werden die Platzhalter "
                "selbst in „Platzhalter & Queries“.",
                "Die Testeingabe in der Tabelle ist ein Probelauf und sonst "
                "nichts: Sie wird nirgends gespeichert und landet in keinem "
                "Vermerk.",
                "Die Vorschau schreibt nichts.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (
                "Drei Sichten pflegen drei Bauteile eines Vermerks:",
            ),
            liste=_BAUTEILE + (
                "Berichts-Abnahme — wo die fertigen Vermerke landen.",),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "modules.titel", "Baustein-Module",
            "Pflegt wiederverwendbare Textstücke, die sich beim Schreiben "
            "eines Vermerks einfügen lassen.",
            verweis="modules#zweck"),
        Kontexthilfe(
            "modules.hinweis", "Was ein Baustein enthält",
            "Der Text ist Freitext und darf Platzhalter enthalten; diese "
            "bleiben stehen und werden erst beim Schreiben des konkreten "
            "Vermerks eingesetzt. Vor dem Speichern die Vorschau fahren.",
            verweis="modules#vorschau"),

        # Die acht Bedienelemente (Build 635, Welle B3). Der Umschalter
        # 'Rohansicht / Vorschau' steht woertlich im Vorgang 17200856.
        # Build 652 (Ticket 3508ad71): die Vorschau steht jetzt dauerhaft in
        # einer eigenen Spalte. Der Schalter wechselt nicht mehr zwischen
        # zwei Ansichten, sondern klappt die Spalte zu - und merkt sich das.
        # Der ALTE Text hat das Gegenteil zugesichert ("er wird auch nicht
        # gemerkt"); er waere ab diesem Build falsch gewesen.
        Kontexthilfe(
            "modules.bedienung.ansicht", "Vorschau ein-/ausblenden",
            "Klappt die Vorschau-Spalte rechts neben der Maske zu und wieder "
            "auf. AM BAUSTEIN ÄNDERT DAS NICHTS — es ist eine Ansichtssache. "
            "Der Stand wird gemerkt: Wer die Vorschau zuklappt, findet sie "
            "beim nächsten Öffnen zugeklappt vor. Auf schmalen Bildschirmen "
            "steht die Vorschau unter der Maske statt daneben; der Schalter "
            "wirkt dort genauso.",
            verweis="modules#vorschau"),
        Kontexthilfe(
            "modules.bedienung.neu", "Neuer Baustein",
            "Leert die Maske für eine Neuanlage. Ein bereits geladener "
            "Baustein wird dabei nicht verändert."),
        # Build 653 (Ticket d60e893a): aus der Liste wurde eine Tabelle.
        # Der alte Text sprach von "der Liste links" — sie steht jetzt oben.
        Kontexthilfe(
            "modules.bedienung.waehlen", "Baustein aus der Tabelle",
            "Lädt diesen Baustein in die Maske darunter. Ein Ladevorgang, "
            "kein Schreibvorgang — solange nicht gespeichert wird, ändert "
            "sich am Bestand nichts. Die geladene Zeile bleibt markiert, "
            "damit auch nach einem Seitenwechsel erkennbar ist, was gerade "
            "bearbeitet wird."),
        Kontexthilfe(
            "modules.bedienung.nurohne", "Nur ohne Kennung",
            "Zeigt ausschließlich die Bausteine, denen die Kennung noch "
            "fehlt. Sie stammen aus der Zeit vor der Kennungspflicht und "
            "müssen EINZELN nachgetragen werden; eine Sammelvergabe gibt es "
            "bewusst nicht, weil eine Kennung nach der Vergabe endgültig "
            "ist. Erneutes Anklicken hebt den Filter auf; die übrigen "
            "Spaltenfilter bleiben dabei stehen.",
            verweis="modules#ablaeufe"),

        # --- Die Spalten der Tabelle (Build 653). Die Anker vergibt das
        # gemeinsame Tabellenwerkzeug aus den Feldnamen; der führende
        # Unterstrich abgeleiteter Felder fällt dabei weg
        # (cockpit_tablekit.js hilfeIdNormieren, Build 592).
        Kontexthilfe(
            "modules.spalte.kennungtext", "Spalte „Kennung“",
            "Die feste Kennung, über die Berichtsvorlagen auf den Baustein "
            "verweisen. Steht hier „ohne Kennung“, ist der Baustein älter "
            "als die Kennungspflicht und noch nachzutragen.",
            verweis="modules#aufbau"),
        Kontexthilfe(
            "modules.spalte.title", "Spalte „Titel“",
            "Die Bezeichnung für Menschen — sie steht auch in der Auswahl "
            "des Berichtseditors."),
        Kontexthilfe(
            "modules.spalte.rolletext", "Spalte „Rolle“",
            "Für welche Aufgabe der Baustein gedacht ist. Die Tabelle ist "
            "nach dieser Spalte vorsortiert."),
        Kontexthilfe(
            "modules.spalte.topic", "Spalte „Thema“",
            "Das Stichwort, unter dem verwandte Bausteine zusammenstehen."),
        Kontexthilfe(
            "modules.spalte.sort_order", "Spalte „Sortierung“",
            "Die Reihenfolge innerhalb einer Rolle. Ein kleinerer Wert steht "
            "weiter oben."),
        Kontexthilfe(
            "modules.spalte.aktivtext", "Spalte „Aktiv“",
            "Ob der Baustein im Berichtseditor angeboten wird. Ein "
            "abgeschalteter Baustein bleibt erhalten und wirkt weiter in "
            "bereits geschriebenen Vermerken.",
            verweis="modules#grenzen"),
        Kontexthilfe(
            "modules.werkzeug.filter_entfernen", "Filter zurücksetzen",
            "Entfernt ALLE Spaltenfilter dieser Tabelle auf einmal — auch "
            "den Filter „Nur ohne Kennung“."),
        Kontexthilfe(
            "modules.werkzeug.trefferzahl", "Trefferanzeige",
            "Wie viele Bausteine gerade sichtbar sind und wie viele es "
            "insgesamt gibt. Weichen die Zahlen voneinander ab, ist ein "
            "Filter gesetzt — das ist die erste Frage nach jedem "
            "Filterwechsel."),
        Kontexthilfe(
            "modules.bedienung.schluessel", "Kennung des Bausteins",
            "Die feste Kennung, unter der der Baustein gefunden wird. Ob das "
            "Feld gerade offen oder gesperrt ist, sagt die Zeile direkt "
            "darunter — ein Feld, das mal geht und mal nicht, ohne dass "
            "jemand sagt warum, wirkt kaputt."),
        Kontexthilfe(
            "modules.bedienung.titel", "Titel",
            "Die Bezeichnung für Menschen. Sie steht in der Liste links und "
            "in der Auswahl des Berichtseditors."),
        Kontexthilfe(
            "modules.bedienung.rolle", "Rolle",
            "Für welche Aufgabe der Baustein gedacht ist. Die Angabe ordnet "
            "ihn ein und schränkt nicht ein, wer ihn benutzen darf."),
        Kontexthilfe(
            "modules.bedienung.thema", "Thema",
            "Ein Stichwort zum Gruppieren verwandter Bausteine — freiwillig, "
            "aber bei wachsendem Bestand der Unterschied zwischen Finden und "
            "Suchen."),
        Kontexthilfe(
            "modules.bedienung.beschreibung", "Beschreibung",
            "Wofür dieser Baustein gedacht ist. Ein Satz hier erspart der "
            "nächsten Person die Rückfrage."),
        Kontexthilfe(
            "modules.bedienung.bausteintext", "Bausteintext",
            "Der Text selbst. Er ist Freitext und darf Platzhalter enthalten; "
            "diese bleiben stehen und werden erst beim Schreiben des "
            "konkreten Vermerks eingesetzt. Wie er wirkt, zeigt die Vorschau "
            "darüber.",
            verweis="modules#vorschau"),
        # Build 654 (Ticket 4b032177): die Platzhalter-Tabelle.
        Kontexthilfe(
            "modules.bedienung.phtabelle", "Platzhalter im Bausteintext",
            "Führt jeden Platzhalter des Textes mit allen Angaben auf und "
            "prüft ihn. Die Tabelle läuft beim Tippen mit und schreibt "
            "nichts. Jeder Befund steht im Klartext dabei — die Farbe allein "
            "wäre keine Auskunft.",
            verweis="modules#platzhaltertabelle"),
        Kontexthilfe(
            "modules.bedienung.phtest", "Testeingabe",
            "Eine Beispieleingabe, um zu sehen, ob sie zum Prüfmuster passt. "
            "SIE WIRD NIRGENDS GESPEICHERT und landet in keinem Vermerk. "
            "Gibt es zwei Regeln — eine am Platzhalter und eine hinterlegte "
            "— stehen BEIDE Urteile da. Weichen sie voneinander ab, wird das "
            "ausdrücklich gesagt: beim Ausfüllen gilt die hinterlegte.",
            verweis="modules#platzhaltertabelle"),
        Kontexthilfe(
            "modules.bedienung.sortierung", "Sortierung",
            "Bestimmt die Reihenfolge in der Auswahl des Berichtseditors. Ein "
            "kleinerer Wert steht weiter oben."),
        Kontexthilfe(
            "modules.bedienung.probelauf", "Vorschau (schreibfrei)",
            "Prüft den Baustein und zeigt das Ergebnis, ohne etwas zu "
            "speichern. Der Unterschied zur Vorschau darüber: Diese hier "
            "prüft auch, ob die Platzhalter auflösbar sind.",
            verweis="modules#vorschau"),
        Kontexthilfe(
            "modules.bedienung.speichern", "Speichern",
            "Schreibt den Baustein fest; der Vorgang wird protokolliert. Ein "
            "geänderter Baustein wirkt dort, wo er künftig eingefügt wird — "
            "bereits geschriebene Vermerke bleiben unberührt.",
            verweis="modules#grenzen"),
    ),
)


#: Der Teilbestand dieser Nav-Gruppe, in Katalogreihenfolge
#: (templates, doctemplates, modules - siehe VIEW_CATALOG).
REDAKTION: Tuple[Sichthilfe, ...] = (TEMPLATES, DOCTEMPLATES, MODULES)
