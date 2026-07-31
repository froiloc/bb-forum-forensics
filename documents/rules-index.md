# Regelwerk AIW — Übersicht

**Stand:** Build 607 · 2026-07-31 · **Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH

Dieses Verzeichnis führt die Regeln des Projekts an EINER Stelle zusammen. Bis Build 606 standen sie verteilt: in den Projektanweisungen, in Bauplänen, in Dateiköpfen und in den Kommentaren einzelner Tests. Sie galten deshalb nicht weniger — aber wer sie nachschlagen wollte, musste wissen, wo er suchen muss.

## Die Dateien

| Datei | Bereich | Für wen |
|---|---|---|
| `rules-projekt.md` | Die zehn Grundregeln, die Fallregeln, der Migrationsvorbehalt, die Diskursregel | alle |
| `rules-coding.md` | Python und JavaScript: Aufbau, Kapselung, Kommentare, Tests | Entwicklung |
| `rules-ux.md` | Listensichten, Tabellen, Leerbefund gegen Fehlerfall | Entwicklung |
| `rules-help.md` | Die drei Hilfesysteme: Adressaten, Sprache, Gliederung, Anker | Entwicklung, Redaktion |
| `rules-cli.md` | Kommandozeilen-Werkzeuge: Katalog, Trockenlauf, Exit-Codes, Wartungsvorbehalt | Entwicklung, Betrieb |

## Wie diese Sammlung zu lesen ist

**Eine Regel ohne Durchsetzung ist eine Bitte.** Deshalb nennt jede Regel, wo sie maschinell geprüft wird — mit dem Namen des Tests. Wo es keine Prüfung gibt, steht das ausdrücklich dabei; das ist dann eine bewusst redaktionelle Regel und keine vergessene.

**Diese Sammlung ist abgeleitet, nicht neu.** Sie schreibt auf, was gilt, und erfindet nichts hinzu. Wo eine Regel aus einer datierten Festlegung stammt, steht die Festlegung dabei. Wo sie sich aus dem Bestand ergibt, steht die Fundstelle dabei.

**Sie ist nicht vollständig, und das steht hier.** Die Regeln zu Datenmigration stehen weiterhin im `Datenmigrationsleitfaden AIW.md` und werden hier nur verwiesen, nicht kopiert — zwei Fassungen derselben Regel wären eine Fassung zu viel.

## Pflegepflicht

Wer eine Regel ändert, ändert sie hier — und zwar in demselben Build, in dem die Änderung wirksam wird. Wer eine neue Regel einführt, legt sie hier ab und nennt ihre Durchsetzung. Eine Regel, die nur in einem Dateikopf steht, gilt zwar, ist aber für die nächste Person unauffindbar.

## Offene Punkte

- Der Wartungsvorbehalt für schreibende Kommandozeilen-Werkzeuge ist noch nicht entschieden (Issue `da6c16d0-ef1e-4052-8eb1-526c647de613`). `rules-cli.md` beschreibt den vorgeschlagenen Aufbau und kennzeichnet ihn als Vorschlag.
- Die Regeln zur Berichtsredaktion (Vorlagen, Bausteine, Platzhalter) sind hier noch nicht erfasst.
