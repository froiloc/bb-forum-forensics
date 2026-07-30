# Bauplan Build 576 + 577 — Vorschau eines Textbausteins (Ticket `64edd18a`)

**Version:** 0.1 · **Datum:** 2026-07-30 · **Baubasis:** v0.8.575
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc, 2026-07-30 (Weg (c) für die Stile; Erweiterung von `StaticAssets` genehmigt)

---

## 1. Was gezeigt werden soll — und was nicht

Die Vorschau zeigt **die Ansicht des Berichtseditors**, nicht die Exportfassung.

Ich hatte die Exportfassung empfohlen; mc hat widersprochen, und der Code gibt
ihm recht: `editor/html_renderer.py` löst Platzhalter **nicht** auf, es maskiert
nur Text. In der Exportfassung stünde wörtlich `{{a:username}}` — genau das
„sehr technisch", von dem das Ticket wegwill. Die Editor-Ansicht zeigt
stattdessen den farbigen Chip mit `username`.

**Es gibt drei Darstellungen, und sie unterscheiden sich:**

| | wo | Platzhalter |
|---|---|---|
| Bearbeitungsansicht | Editor.js mit Schreibrechten | Chip, plus Werkzeugleisten |
| **Nur-Lese-Ansicht** | Editor.js ohne Schreibrechte | **Chip** ← das ist die Vorschau |
| Exportfassung | `html_renderer.py` | roher Text `{{a:username}}` |

---

## 2. Abgestimmte Reihenfolge

| Schritt | Inhalt | Risiko an Daten |
|---|---|---|
| **576** | Geteilte Dateien bereitstellen und ausliefern | keins |
| **577** | Vorschau in der Bausteinverwaltung | keins |
| 578 | `block_type` + `block_data` an `report_modules` (**Migration**), Drop-Fehler `: {}` mit behoben | hier, und nur hier |
| 579 | Editor.js als Eingabe + Rohmodus mit JSON-Prüfung und Wechselvergleich | keins |

Grund für diese Folge: die Migration ist der einzige Schritt, der Daten anfassen
kann — er kommt, wenn alles andere bewiesen läuft.

---

## 3. Build 576 — was tatsächlich gebaut wurde

**Chip-Stile herausgelöst** (Weg (c)). Abschnitt 10 von `userinfo/report.css`
(96 Zeilen) und die zugehörige Druckregel wandern nach
`userinfo/placeholder_chips.css`. Modul und Stil sind ab jetzt ein **teilbares
Paar**.

Die **Druckregel kam mit ihrem `@media print`-Rahmen mit**. Sie stand in
`report.css` innerhalb eines solchen Blocks; ohne den Rahmen wäre sie im neuen
Dateikontext wirkungslos geworden — der Ausdruck hätte wieder farbige Chips
gezeigt statt nur den Wert.

**Nachweis statt Zusicherung:** alle **sieben** Chip-Selektoren sind in der
neuen Datei, **keiner** blieb in `report.css` zurück, Klammerbilanz beider
Dateien stimmt (19/19 und 490/490). `GA09` hält das dauerhaft fest.

**Geteilte Auslieferung über eine exakte Positivliste** — bewusst **kein**
zweites durchsuchbares Wurzelverzeichnis:

```python
GETEILTE_ASSETS = {
    "shared/editor.bundle.js":     <repo>/static/editor/editor.bundle.js,
    "shared/placeholder_chips.js": <repo>/userinfo/placeholder_chips.js,
    "shared/placeholder_chips.css":<repo>/userinfo/placeholder_chips.css,
}
```

Eine URL kann nur ein **wortgleicher Schlüssel** sein. Damit ist Traversal
ausgeschlossen, ohne die bestehende Abwehr anzufassen — sie bleibt für alle
anderen Pfade unverändert. Geprüft: Präfixe, Unterverzeichnisse, andere
Groß-/Kleinschreibung und angehängte Endungen werden **nicht** ausgeliefert
(`GA03`); Traversal bleibt abgewiesen (`GA04`); die Endungsprüfung gilt auch
für geteilte Dateien (`GA05`); ohne Positivliste verhält sich alles unverändert
(`GA07`).

**Ein fehlender Eintrag wird beim Start gemeldet** (`fehlende_geteilte()`, Log
auf ERROR) und beim Abruf mit einem eigenen 404 — nicht still. Das ist die Lehre
aus Build 570/571.

---

## 4. Der Test aus Build 493 hat mich sofort erwischt

Ich hatte `placeholder_chips.css` nur in der Liste in `forensic_api/__init__.py`
registriert. Es gibt aber **zwei** Stellen: jene Liste sagt, welche Adressen es
geben soll — die Tabelle in `forensic_api/static.py` sagt, welche **Datei**
dahinter liegt. `tests/test_report_assets_routing.py` meldete
`/_forensic/placeholder_chips.css: HTTP 404` und nannte die Adresse.

Genau diese Falle hatte Build 493 dokumentiert („in `_RESOURCES`, aber nie
dispatcht") und dafür diesen Test angelegt. Er hat sich bezahlt.

---

## 5. Build 577 — was folgt

Vorschaufeld unter dem Bausteinformular:

```js
{ blocks: [ { type: 'paragraph',
              data: { text: PlaceholderChips.hydrateChips(body, {}, {}) } } ] }
```

Editor.js im Nur-Lese-Modus, Aktualisierung beim Tippen (entprellt), Umschaltung
„Vorschau / Rohansicht" ohne Gedächtnis (ein Moment, keine Vorliebe).

**Was ich nicht vorhersagen kann:** wie viel vom übrigen `report.css` die Blöcke
brauchen — ob ein Absatz in der Management-Oberfläche auf Anhieb richtig aussieht
oder Editor.js dort nackt wirkt. Das sieht man erst am lebenden System, und die
Nachbesserung wird ein eigener kleiner Build. Ich behaupte hier nicht, dass es
sofort sitzt.

---

## 6. Regression

| | 0.8.575 | 0.8.576 |
|---|---|---|
| Python | 2344 / 50 skipped / 45 subtests | **2353** (+9: GA01–GA09) |
| vitest | 114 Dateien, 1587 passed | **unverändert** (kein JS berührt) |

**Vor Build 577 bitte im Berichtseditor nachsehen**, ob die Chips unverändert
aussehen — Bearbeitungsansicht **und** Probedruck. Automatisch prüfbar ist nur,
dass keine Regel verlorenging, nicht wie sie wirkt.

---
*Dokument-Ende · Bauplan Build 576/577 · v0.1 · 2026-07-30*
