# Arbeitsstand

**Diese Datei ist der EINSTIEG.** Wer eine neue Sitzung beginnt, liest sie
zuerst und danach die hier genannten Dokumente — in dieser Reihenfolge.

Sie wird von Waechter **AS01** gegen `build.json` gehalten: nennt sie eine
andere Buildnummer als die ausgelieferte, faellt der Test. Sie kann damit
nicht veralten, ohne dass es auffaellt.

> **Warum es diese Datei gibt.** Uebergabedokumente, die am Ende einer Sitzung
> geschrieben werden, verlieren die Haelfte des Wissens — es ist *stille Post*.
> Was traegt, steht im Repository: die Regelkataloge, die Kommentare im Code,
> die `note` in `build.json`, der Issue-Tracker. Was fehlte, war der Hinweis,
> **welche** davon in welcher Reihenfolge zu lesen sind. Das ist diese Datei.

---

## Aktueller Stand

**Build 767** — Wortlautabgleich, Messwerkzeug.

## Was gerade gearbeitet wird

Die **Migration der Annotationen** von `selection_json` Version 1.0.0 auf
2.0.0. Es ist noch nichts migriert; die Builds 763 bis 767 sind die Vorarbeit,
die belegt, was migriert werden muss und was dabei zu beachten ist.

**Der naechste Schritt** ist der Lauf von `tools/wortlaut_abgleich.py` ueber
alle Bestaende. Erst danach wird der Bauplan der Migration geschnitten.

## Was zuerst zu lesen ist

| Reihenfolge | Dokument | Warum |
|---|---|---|
| 1 | `documents/Regelkatalog_selection_json_2_0.md` | **Version 1.0, freigegeben.** Alle Festlegungen zur Migration: Typen, Anker, Offsets, Aufbau, Ablauf, Erwartungswerte. Ohne dieses Dokument ist keine Entscheidung nachvollziehbar. |
| 2 | `documents/Post_Bereiche_Katalog.md` | Wo im Beitrag der Inhalt aufhoert und der Rahmen anfaengt — je Seitenart, mit Belegzeilen aus dem Forenquelltext. |
| 3 | `build.json`, Feld `note` | Der Befund des jeweils letzten Builds, einschliesslich der Fehler, die dabei gefunden wurden. |
| 4 | `issue-tracker/data/issues.json` | Die Vorgaenge. Die Eintraege der letzten Builds tragen die Begruendungen. |

## Die Builds dieser Arbeit, in Kuerze

| Build | Was daraus gilt |
|---|---|
| 763 | Prefix-Diagnose: misst, **wo** ein XPath expression bricht — beide Endpunkte, post container am letzten aufloesenden Node, Spanne dazwischen. |
| 764 | **Inhalt gegen Rahmen** entscheidet `text range` gegen `whole post`. Nicht die Lage der Endpunkte zueinander — das war widerlegt. |
| 765 | Katalogumbau: `Elementprobe` mit `has_attribute`, mehrere Inhaltsbereiche je Seitenart, Systembeitrag kein Sonderfall mehr. |
| 766 | Anker-Generator: `by_id` vor `by_class` vor `by_position`, mit Eindeutigkeitspruefung und Rueckpruefung je Schritt. |
| 767 | Wortlautabgleich: dreistufige Suche, Normalisierung, Ausschluss nicht gerenderter Elemente. |

## Die fuenf Befunde, die alles Weitere bestimmen

1. **107 von 455 Annotationen tragen einen Ausdruck, der aufloest, aber an die
   falsche Stelle zeigt.** Nur 6 brechen strukturell. Bei den uebrigen 101
   liefert der Berichtsgenerator heute stillschweigend den falschen Text, weil
   `AbsatzFinder._ueber_xpath()` den Fund nie gegen `textContent` haelt.

2. **Ein zeichengenauer Vergleich ist unmoeglich.** `textContent` entsteht aus
   `Selection.toString()` — dem sichtbar ausgewaehlten Text mit
   browserabhaengigen Leerraumregeln, nicht der Verkettung der Textknoten.
   Normalisierung und Aehnlichkeit sind der einzige Weg, kein Notbehelf.

3. **Der Browser ueberspringt nicht gerenderte Elemente, eine Textentnahme aus
   dem Baum nicht.** Gemessener Fall: die unzensierte Fassung eines zensierten
   Wortes steht im Abzug, ist aber `display: none`.

4. **Das Forum ist nicht normkonform.** `id="progressbar"` steht je Beitrag
   einmal — auf einer Seite bis zu 269-mal; dazu `contentType4` und
   `page-footer`. Jede Verankerung ueber `id` muss die Eindeutigkeit pruefen.

5. **Die Toolbar erhebt bereits Metadaten.** `PostMetaModule` in `toolbar.js`
   fuellt einen `meta`-Zweig mit Zeit, Betreff, Verfasser, Eroeffner, Konto und
   Kennungen — jeder Wert mit dem Namen seines Verfahrens. Die Migration
   uebernimmt ihn, sie entwirft ihn nicht neu.

## Arbeitsregeln, die aus Fehlern entstanden sind

- **Vor dem Bauen im Baum suchen.** In dieser Arbeit sind vier Werkzeuge und
  eine Metadatenliste neu entworfen worden, die es bereits gab.
- **Eine Regel wird am Quelltext hergeleitet, nicht an einer Korrelation.** Die
  in Build 763 erwogene Regel ueber die innere Beitragskennung passte zu den
  Messwerten und war trotzdem falsch.
- **Mutationsgegenproben mit Dateikopien, nicht mit `git checkout`.** Neue
  Dateien sind unversioniert; `git checkout` stellt sie nicht wieder her und
  bricht bei gemischten Pfaden ganz ab.
- **Ein Waechter, der ueber eine Menge laeuft, prueft die leere Menge nicht.**
  Zweimal blieb eine Mutation gruen, weil die Liste leer gesetzt wurde.
- **Wird eine Buildnummer ein zweites Mal ausgeliefert**, traegt die
  Eintragsdatei des Issue-Trackers nur, was seit der ersten Auslieferung
  hinzugekommen ist.

## Sprache

Deutsche Prosa, **englische Fachbegriffe**. Keine deutschen Wortschoepfungen
fuer informatische Begriffe. Keys, Variablen und Argumente englisch;
Endnutzerausgaben deutsch. Bereits eingefuehrte deutsche Bezeichner bleiben bis
zu einem beauftragten Refactoring stehen — eine Mischung in derselben Datei
waere schlimmer.
