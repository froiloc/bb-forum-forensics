# Regelwerk AIW — Übersicht

**Stand:** Build 661 · 2026-08-02 · **Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH

Dieses Verzeichnis führt die Regeln des Projekts an EINER Stelle zusammen. Bis Build 606 standen sie verteilt: in den Projektanweisungen, in Bauplänen, in Dateiköpfen und in den Kommentaren einzelner Tests. Sie galten deshalb nicht weniger — aber wer sie nachschlagen wollte, musste wissen, wo er suchen muss.

## Die Dateien

| Datei | Bereich | Für wen |
|---|---|---|
| `rules-projekt.md` | Die zehn Grundregeln, die Fallregeln, der Migrationsvorbehalt, die Diskursregel | alle |
| `rules-coding.md` | Python und JavaScript: Aufbau, Kapselung, Kommentare, Tests | Entwicklung |
| `rules-ux.md` | Listensichten, Tabellen, Leerbefund gegen Fehlerfall | Entwicklung |
| `rules-help.md` | Die drei Hilfesysteme: Adressaten, Sprache, Gliederung, Anker | Entwicklung, Redaktion |
| `rules-cli.md` | Kommandozeilen-Werkzeuge: Katalog, Trockenlauf, Exit-Codes, Wartungsvorbehalt | Entwicklung, Betrieb |
| `rules-leerbefund.md` | Leerbefund ist kein Erfolg: die dritte Frage, Rückgabewerte, was nicht geprüft wurde | Entwicklung, Betrieb |
| `rules-nachstellung.md` | Die Nachstellung muß der Wirklichkeit standhalten: unwirkliche Testvorrichtungen, fremde Rechte, der ganze Weg einer Meldung | Entwicklung |
| `data-exchange.md` | Übergabe von Arbeitsergebnissen: Git-Bundle statt ZIP, Integrationszweig, Vorabprobe, Urheberschaft | Entwicklung, Betrieb |

## Wie diese Sammlung zu lesen ist

**Eine Regel ohne Durchsetzung ist eine Bitte.** Deshalb nennt jede Regel, wo sie maschinell geprüft wird — mit dem Namen des Tests. Wo es keine Prüfung gibt, steht das ausdrücklich dabei; das ist dann eine bewusst redaktionelle Regel und keine vergessene.

**Diese Sammlung ist abgeleitet, nicht neu.** Sie schreibt auf, was gilt, und erfindet nichts hinzu. Wo eine Regel aus einer datierten Festlegung stammt, steht die Festlegung dabei. Wo sie sich aus dem Bestand ergibt, steht die Fundstelle dabei.

**Sie ist nicht vollständig, und das steht hier.** Die Regeln zu Datenmigration stehen weiterhin im `Datenmigrationsleitfaden AIW.md` und werden hier nur verwiesen, nicht kopiert — zwei Fassungen derselben Regel wären eine Fassung zu viel.

## Pflegepflicht

Wer eine Regel ändert, ändert sie hier — und zwar in demselben Build, in dem die Änderung wirksam wird. Wer eine neue Regel einführt, legt sie hier ab und nennt ihre Durchsetzung. Eine Regel, die nur in einem Dateikopf steht, gilt zwar, ist aber für die nächste Person unauffindbar.

## Offene Punkte

- Der Wartungsvorbehalt für schreibende Kommandozeilen-Werkzeuge ist noch nicht entschieden (Issue `da6c16d0-ef1e-4052-8eb1-526c647de613`). `rules-cli.md` beschreibt den vorgeschlagenen Aufbau und kennzeichnet ihn als Vorschlag.
- Die Regeln zur Berichtsredaktion (Vorlagen, Bausteine, Platzhalter) sind hier noch nicht erfasst.

## Nachtrag Build 649

Zwei Blätter sind hinzugekommen, die es bei Abfassung dieser Übersicht (Build 607) noch nicht gab: `rules-leerbefund.md` (Build 647, aus den Vorgängen `d30b3d95`, `0329896b`, `e9522fe2`) und `rules-nachstellung.md` (Build 649, aus den Vorgängen `c3f80e54` und `2f8a61d0`). Beide waren bis dahin nur in Testköpfen und Buildvermerken niedergelegt — sie galten also, waren aber nicht auffindbar. Genau das ist der Fall, den die Pflegepflicht oben verhindern soll; er ist hier vermerkt und nicht stillschweigend nachgetragen.

## Nachtrag Build 661

`data-exchange.md` ist hinzugekommen und regelt ab dem 3. August 2026 die Form,
in der Arbeitsergebnisse übergeben werden: Git-Bundle statt ZIP-Archiv. Anlaß war
ein am 2026-08-02 gemessener Befund — ein über einen Bestand entpacktes ZIP
löscht eine parallel entstandene Änderung **still**, während dieselbe Lage über
ein Bundle einen benannten Konflikt erzeugt. Das Blatt gehört sachlich nicht zu
den `rules-`Dateien (es regelt den Arbeitsweg, nicht das Erzeugnis) und trägt
deshalb einen eigenen Namen; es steht hier, weil die Pflegepflicht oben keine
Regel außerhalb dieser Übersicht duldet.

Die Regel aus Abschnitt 3.3 jenes Blattes — die Vorabprobe
`git status --porcelain --ignored` — hat **keine maschinelle Durchsetzung**. Das
ist dort ausdrücklich vermerkt und als offener Punkt geführt.
