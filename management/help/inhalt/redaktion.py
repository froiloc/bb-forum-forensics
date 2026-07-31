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
    stand=_STAND,
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
    stand=_STAND,
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
    stand=_STAND,
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
                "Überschrift, Hinweis, Liste der vorhandenen Bausteine und "
                "die Bearbeitungsmaske mit dem Text.",
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
                "Vor dem Speichern zeigt die Vorschau, wie der Baustein im "
                "Berichtseditor aussehen wird, und zählt die enthaltenen "
                "Platzhalter. Sie SCHREIBT NICHTS.",
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
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "Eine Änderung wirkt NUR AUF KÜNFTIGE Vermerke. Bereits "
                "geschriebene bleiben, wie sie sind — sonst änderte sich "
                "rückwirkend, was jemand unterschrieben hat.",
                "Platzhalter werden hier NICHT aufgelöst und auch nicht "
                "geprüft, ob es sie gibt. Die Vorschau zählt sie; ob ein "
                "Name stimmt, entscheidet sich in „Platzhalter & Queries“.",
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
    ),
)


#: Der Teilbestand dieser Nav-Gruppe, in Katalogreihenfolge
#: (templates, doctemplates, modules - siehe VIEW_CATALOG).
REDAKTION: Tuple[Sichthilfe, ...] = (TEMPLATES, DOCTEMPLATES, MODULES)
