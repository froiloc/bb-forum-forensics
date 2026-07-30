# Bauplan Build 570 — Diagramme der Überblick-Kacheln (Ticket `3fb9f16e`)

**Version:** 0.1 · **Datum:** 2026-07-29 · **Baubasis:** `e596d01` (v0.8.569)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc, 2026-07-29 („große Freiheit", ECharts erwünscht)

---

## 1. Vorbefund zum gemeldeten 404 — nicht nachstellbar

Statisch geprüft und **nicht bestätigt**:

- Alle acht `api_path` des Kachelkatalogs liegen im **Lese**-Dispatcher.
- Alle 51 in `cockpit.html` eingebundenen Skripte existieren auf der Platte.
- `cockpit_dashboard.js` ist eingebunden; Reduzierer und Render-Schleife sind
  seit Build 545/547 vollständig.

Der 404 ist damit **kein Routing- und kein Einbindungsfehler**. Zur Aufklärung
braucht es Konsolen- und Netzwerkausgabe vom lebenden System (Console-First).
Als eigener Trackereintrag mit `cannot_reproduce` geführt.

Die eigentliche Lücke des Tickets war eine andere und ist behoben: **die Kacheln
waren reiner Text.**

---

## 2. Wozu ein Dashboard da ist

Es soll in drei Sekunden und **ohne Lesen** die Frage beantworten: brennt etwas,
und wo? Daraus vier Regeln, die das neue Modul durchhält:

| # | Regel | Warum |
|---|---|---|
| a | **Eine Farbe bedeutet in jeder Kachel dasselbe** — rot überschritten, gelb Vorwarnung, grün in Ordnung, grau keine Aussage | Wären die Farben je Kachel anders belegt, müsste man jede einzeln lesen — dann ist der Überblick keiner |
| b | **Ein Diagramm muss mehr sagen als die Zahl daneben** | Ein Balken, der die Zahlen der Unterzeile wiederholt, ist Rauschen |
| c | **Kein Diagramm auf einer Ja/Nein-Aussage** | Dekoration auf einer forensischen Aussage ist schlechter als nichts |
| d | **Ein nicht besetzter Eimer verschwindet nicht** | Sonst verschöbe sich die Form von Abruf zu Abruf, und ein leerer Eimer sähe aus wie ein nicht erhobener |

---

## 3. Sechs Formen, zwei begründete Auslassungen

| Kachel | Form | Warum diese |
|---|---|---|
| `fallampel`, `meine_auftraege` | **Ampelring**, Gesamtzahl im Loch | Es geht um **Anteile eines Ganzen**; das Ganze steht als Zahl in der Mitte |
| `eskalationen` | Balken über **Liegezeit** | Die Schwere steht schon als Text in der Unterzeile. Wie lange etwas liegt, steht sonst **nirgends** (Regel b) |
| `fristen` | Balken über **Restlaufzeit** (≤7 / 8–30 / 31–90 / >90 Tage) | Rot→grün: die Dringlichkeit ist die Aussage |
| `wiedervorlage`, `naechste_aktion` | liegender **Anteilsbalken** | „7 von 42". Bewusst **kein Tacho** — der suggeriert eine Skala mit gut und schlecht, die es hier nicht gibt |
| `lastverteilung` | liegende **Balken je Person** + Grenzlinie | Die Linie ist der eigentliche Gewinn: ohne sie sieht man Balken, aber nicht, ob sie zu lang sind |
| `kettenzustand` | **kein Diagramm**, stattdessen Tönung der ganzen Kachel | Ja/Nein-Aussage (Regel c) |

Jede Auslassung ist in `DIAGRAMMLOS` **begründet**, damit niemand sie für eine
Lücke hält und „nachträgt". `DC10` prüft, dass **jede** der acht Kacheln
entschieden ist.

---

## 4. Keine Form ohne Aussage

Die Fristenkachel bekommt **kein** Diagramm, wenn `params_bestaetigt === false`
oder `aussage_moeglich === false` — ein Balken wäre eine unbelegte
Rechtsbehauptung. Dieselbe Regel, die `reduceFristen` seit Build 547 für die
**Zahl** durchhält, gilt jetzt auch für die **Form**. `DC08`.

Ebenso: ein Abrufausfall ergibt nie eine Option (`DC09`), und eine ausgefallene
Kachel bekommt keinen Diagramm-Behälter (`DB20`) — ein leerer Kasten sähe wie
ein nicht geladenes Diagramm aus.

**Fehlende Angaben werden nicht weggerundet:** eine fehlende Liegezeit landet
unter `unbekannt` und nicht unter „bis 3 Tage"; eine Frist ohne möglichen
Anker in **keinem** Restlaufzeit-Eimer; ein unbekannter Ampelwert unter
`sonst` und nicht unter grün. `DC01`–`DC03`.

---

## 5. Eigene Datei, prüfbar ohne Browser

Eine ECharts-Option ist ein **Datenobjekt**.
`cockpit_dashboard_charts.js` enthält nur reine Eimer- und Optionsfunktionen
plus zwei Einhänge-Helfer; die Tests schauen **in die Option** — Serientyp,
Farbreihenfolge, Achsendaten, Grenzlinie — und nicht auf Pixel. Dieselbe
Trennung wie `cockpit_capacity.echartsOption` seit Build 360 (Grundregel 10).

---

## 6. Betriebliches

- **Jede Diagramminstanz** wird in `state.charts` vermerkt, weil `cleanupView()`
  sie beim Sichtwechsel entsorgt. Sonst bleiben Leinwände und Resize-Horcher
  zurück, und der Überblick wird bei jedem Besuch etwas langsamer.
- **Fehlt die Bibliothek**, sagt die Kachel das statt leer zu bleiben. `DC12`.
- **Feste Höhe der Diagrammfläche** (132 px, breite Kachel 150 px) — kein
  Schönheitswert: ECharts braucht bei `init()` eine messbare Höhe, ein
  Behälter, der sich erst durch seinen Inhalt aufspannt, ist zu diesem
  Zeitpunkt 0 Pixel hoch und das Diagramm bliebe unsichtbar.
- **`animation: false`** überall. Ein Überblick soll sofort stehen, nicht
  wachsen; nebenbei sind animationsfreie Optionen im Test deterministisch.
- **Reihenfolge im Rumpf:** Titel → Zahl → Form → Einzelzeilen → Hinweise. Der
  Blick geht von der Größenordnung über die Verteilung zum Detail — und darf
  beim Detail aufhören, ohne etwas zu verpassen. `DB19`.

**Selbstaktualisierung: bewusst keine.** Das Ticket nennt sie selbst als meist
unnötig; ein Dashboard, das sich unter der Hand neu zeichnet, verliert den
Bildlauf und die Aufmerksamkeit. Der Überblick lädt beim Betreten der Sicht,
und der bestehende SSE-Zweig erneuert ihn, wenn serverseitig etwas passiert.

---

## 7. Ankerdelta und Regression

Keine Migration, keine neuen Capabilities (46), keine neuen Ereignistypen,
`VIEW_CATALOG` 42/11 unverändert, Kachelkatalog unverändert (8).

| | 0.8.569 | 0.8.570 |
|---|---|---|
| vitest | 113 Dateien, 1562 passed | **114** Dateien, **1578** passed (+12 DC, +4 DB) |
| Python | 2343 / 50 skipped / 45 subtests | **unverändert** — belegt: `git diff HEAD -- '*.py'` ist leer |

**Nicht automatisch prüfbar:** ob es gut aussieht. JSDOM rechnet kein Layout und
zeichnet keine Leinwand. Farben und Höhen sind einzeilige Änderungen.

---
*Dokument-Ende · Bauplan Build 570 · v0.1 · 2026-07-29*
