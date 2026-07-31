# Regelwerk AIW — Oberfläche

**Stand:** Build 607 · 2026-07-31

Grundsatz (mc 2026-07-26): **„Einmal Erlerntes soll immer wieder verwendet werden."** Wer eine Listensicht bedienen kann, kann alle bedienen. Das lässt sich nicht durch guten Willen sichern — deshalb gibt es die Konformitätssuite `tests/unit/test_cockpit_tabellen_ux.test.js`. Jede Sicht wird dort eingetragen; wer eine umbaut und die Werkzeugleiste vergisst, bricht diese Datei, statt unbemerkt eine zwölfte Variante zu erzeugen.

## 1. Was jede Listensicht erfüllt

| Kennung | Zusicherung |
|---|---|
| UX01 / UX03 | Es gibt eine Werkzeugleiste mit der erwarteten Kennung und einer Trefferzahl, die die tatsächliche Zeilenzahl nennt. |
| UX02 | „Filter zurücksetzen" ist vorhanden **und wirkt**. |
| UX04 | Jede Spalte mit Feld trägt einen Kopffilter. Ausnahmen sind zulässig, müssen aber im Register benannt sein — eine Spalte, die *stillschweigend* keinen Filter bekommt, wäre ein Versehen. |
| UX05 | Die Hilfe-Anker sind gesetzt, eindeutig und in der zulässigen Form. |
| UX06 | Fällt die Tabellenmechanik aus, erscheint eine ausdrückliche Meldung **mit der Anzahl** — keine leere Fläche. Eine leere Fläche sieht aus wie „keine Daten vorhanden" (GR1). |
| UX08 / UX09 | Kein `rowClick` in den Konstruktoroptionen; wo ein Zeilenklick versprochen wird, hängt er auch. |
| UX10 | Keine handgebaute Tabelle entkommt unbemerkt. |
| UX11 | Jeder beim Rendern entstehende Hilfe-Anker hat einen Text im Register — sobald das Kapitel der Sicht verfasst ist. |

## 2. Leerbefund, Fehlerfall und Ausschnitt sind drei verschiedene Dinge

Das ist die am häufigsten verletzte und am teuersten zu übersehende Regel des Projekts.

- **Leerbefund:** „Es gibt nichts." Er wird ausformuliert und sagt, worauf er beruht.
- **Fehlerfall:** „Es ist unbekannt, ob es etwas gibt." Er bekommt eine **eigene** Anzeige und darf nie wie ein Leerbefund aussehen.
- **Ausschnitt:** „Es gibt mehr, aber Sie sehen es gerade nicht." Ein gesetzter Filter, eine Einschränkung, eine gekürzte Trefferliste — jedes davon wird benannt, und die Zahlen daneben werden ausdrücklich auf den Ausschnitt bezogen.

Beispiele aus dem Bestand: Die Fristenübersicht nennt beim Leerbefund, wie viele Fälle sich **nicht** prüfen ließen. Das Übergabeprotokoll sagt „die Zahlen unten beziehen sich allein auf diesen Fall". Die Namenssuche im Aliaskatalog nennt die Zahl der Treffer in der zweiten Quelle, die sie nicht listet — eine schweigende Kaskade sähe aus wie ein vollständiges Ergebnis.

## 3. Kein optimistisches Anzeigen

Nach jedem Schreibvorgang lädt die Sicht **neu** — auch im Fehlerfall. Dann zeigt die Liste den tatsächlichen Stand, und der ist: es wurde nichts geschrieben. Die Meldung sagt das ausdrücklich.

## 4. Sortierung ist eine Aussage

**Eine Spalte, die nach Beweisstärke oder Handlungsbedarf aussieht, darf nicht alphabetisch sortieren.** Alphabetisch stünde „gesichert" vor „Verdacht" vor „wahrscheinlich", und „fremdzuständig" vor „gesichtet" vor „offen" — also jeweils das Ende vor dem Anfang. In einem Beweismittelwerkzeug wäre das irreführend. Solche Spalten bekommen einen eigenen Sortierer über den Rang.

**Die Grundordnung des Werkzeugs bleibt.** Wo die Fachschicht bereits eine Ordnung liefert (stärkste Konfidenz zuerst, jüngster Beleg zuerst), bekommt die Tabelle bewusst **keine** Voreinstellung. Eine zweite Sortierung wäre eine zweite Auskunft über dieselbe Sache.

**Zeitspalten sortieren über den Rohwert.** Eine Textsortierung über „26.07.2026" ist keine Zeitsortierung.

## 5. Leere Zellen und unbekannte Werte

- Ein leerer Freitext wird zum Gedankenstrich. Das ist keine Kosmetik: eine leere Zelle sieht aus wie ein Anzeigefehler, ein Gedankenstrich sagt „nichts hinterlegt".
- Ein **unbekannter** Zustandscode verschwindet nicht. Er wird mit seinem Rohwert angezeigt und sortiert zuletzt. Angeboten wird dann keine Aktion — lieber gar keine als eine geratene.
- Ein fehlender Zeitstempel wird zum Gedankenstrich und nicht zu 1970.

## 6. Kennungen sind zugleich Zustandsschlüssel

Der Präfix einer Tabelle ist die Kennung für ihre Hilfe-Anker **und** für den gesicherten Bedienzustand (Sortierung, Filter, Spaltenwahl). Teilten sich zwei Tabellen eine Kennung, überschriebe die zuletzt gezeichnete die Einstellungen der anderen — und ein Hilfetext könnte nicht mehr sagen, welche gemeint ist. Deshalb hat jeder Abschnitt seine eigene.

## 7. Filter auf abgeleiteten Feldern

Kopffilter arbeiten auf dem, was in der Zelle steht. Ein Filter über einen Wahrheitswert erzeugt eine Auswahlliste „true"/„false", ein Filter über einen Rohcode eine unlesbare. Deshalb tragen die Zeilen zusätzlich abgeleitete Textfelder („ja"/„nein", die Beschriftung statt des Codes), nach denen gefiltert und sortiert wird, während der Formatter den Rohwert nimmt.

**Ein Filter, den man nicht lesen kann, wird nicht benutzt.**

## 8. Hilfemodus

- Umschalten über den festen Knopf in der Kopfzeile **oder** Shift+F1 (F1 allein kollidiert mit der Browserhilfe).
- Erklärte Elemente bleiben klar, alle übrigen werden abgedunkelt — über `opacity`, nicht über `blur()` (teuer und auf großen Tabellen flimmeranfällig).
- Das Popup öffnet auf **Klick**; Überfahren ändert nur den Mauszeiger.
- Im Hilfemodus löst kein Klick eine Funktion aus.
- `Esc`, ein erneuter Klick oder ein Sichtwechsel verlassen den Modus.
