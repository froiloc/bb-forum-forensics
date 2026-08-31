# `management/` — Verwaltung, Steuerung und Hilfesystem

## Zwei verschiedene Dinge unter einem Dach

### 1. Code (Unterverzeichnisse)

Die Fachmodule des Verwaltungswerkzeugs: `cases/`, `help/`, `maintenance/`,
`dashboard/` und weitere. Hier liegt die **Fachlogik** zu den Werkzeugen in
`tools/` (Grundregel 10: der Vorgang gehört in ein eigenes Modul, die
Befehlszeile davor nach `tools/`).

Besonders zu beachten: **`management/help/cli_katalog.py` ist die einzige
Quelle** für die Werkzeughilfe. Konsolenübersicht, Vollhilfe und der Epilog
von `--help` lesen alle daraus. Kein vierter Bestand, kein abgeschriebener
Epilog.

### 2. Verwaltungsunterlagen (Markdown im Wurzelverzeichnis)

Alles, was die **Zusammenarbeit** und die **Außendarstellung** betrifft:

* Arbeitsvereinbarungen und Kommunikationsregeln
* Argumentationslinien für die Staatsanwaltschaft
* Referenz- und Zuordnungsunterlagen für die Hauptermittler

## Was hier **nicht** hineingehört

Fachliche Befunde, Baupläne und Leitfäden zum Untersuchungsgegenstand. Die
gehören nach `documents/`. Faustregel: geht es um **Verwaltung**, gehört es
hierher; geht es um den **Fall oder das Werkzeug**, gehört es nach
`documents/`.

## Pflicht seit Einführung der Hilfe im Management

> Keine Änderung oder Neuerung an einer Funktion, einem Bedienelement oder
> einer Komponente des Managements ohne die zugehörige Änderung oder Ergänzung
> im Hilfesystem.
