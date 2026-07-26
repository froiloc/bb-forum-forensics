# Übergabe AP-3G — Modul-Steuerung / konfigurierbares Dashboard

**Arbeitspaket:** AP-3G (Welle 3, Baustelle 7) · Idee 37 (§15 des Ideenpapiers)
**Builds:** 545 (Backend) · 546 (Frontend Sichten) · 547 (Frontend Kacheln)
**Baubasis:** `9f11b97` (v0.8.544), frisch geklont
**Migration:** M037 · **Neue Rechte:** keine
**Stand:** 2026-07-26 · abgeschlossen

---

## 1. Was jetzt da ist

Eine Person richtet ihre eigene Oberfläche ein:

1. **Navigation** — Reihenfolge und Sichtbarkeit der Cockpit-Sichten
   (Sicht *Ansicht anpassen*, Gruppe *Persönlich*).
2. **Überblick** — Auswahl und Reihenfolge von acht Kacheln.

Gespeichert wird in `coordinator.db` (`person_view_pref`, M037), auditiert über
`CoordinatorWriter`.

**Kein neuer Datenweg.** Jede Kachel speist sich aus einem Endpunkt, den es
bereits gibt, und erbt dessen Rechteprüfung, Scope und Fehlerbild.

---

## 2. Die vier Entscheidungen, die den Ausschlag geben

### 2.1 Der Rechtefilter läuft zuletzt

```
VIEW_CATALOG  →  applyViewPrefs  →  visibleViews(capabilities)
Katalog       →  Vorliebe        →  Recht
```

`applyViewPrefs` **ordnet und markiert nur** — es kann konstruktiv nichts
hinzufügen. Eine Vorliebe kann deshalb keine Sicht einblenden, für die das Recht
fehlt; wird ein Recht später entzogen, verschwindet die Sicht trotz
gespeicherter Vorliebe. Bei den Kacheln trifft die Rechteauskunft der **Server**
(`erlaubt` je Kachel), weil die Zuordnung Kachel → Recht an genau einer Stelle
geführt wird.

### 2.2 Ausblenden ist erlaubt, aber nie still — bei der Navigation

Eine ausgeblendete Eskalationssicht könnte eine übersehene Eskalation bedeuten.
Das Verbot wäre die schlechtere Antwort: dann richtet sich niemand die
Oberfläche ein, und die Sicht bleibt trotzdem ungelesen — nur ohne Vermerk.
Stattdessen:

* Zähler „N Sichten ausgeblendet", dauerhaft am Fuß der Navigation, ein Klick
  führt zum Zurücknehmen.
* Gezählt werden **nur Sichten, die die Person sehen dürfte**. Sichten ohne
  Recht sind nicht ausgeblendet, sondern nicht vorhanden — sie mitzuzählen wäre
  eine Auskunft über fremde Rechte.
* Ausgeblendetes bleibt über die Kommandopalette (Strg-K) erreichbar; sie
  bekommt unverändert die **nur rechte-gefilterte** Liste.
* In der Einstellsicht verschwindet Ausgeblendetes nicht, sondern steht
  durchgestrichen an seinem Platz.
* Jede Speicherung ist ein Audit-Beleg mit dem **vollständigen** Zustand.

**Im Dashboard gilt das nicht.** Dort ist die Person frei (Entscheidung mc
2026-07-26): keine Zähler, keine Hinweise. Der Unterschied ist gewollt — eine
abgewählte Kachel verbirgt eine Übersicht, ein ausgeblendeter Nav-Eintrag den
Zugang zu einem ganzen Bereich.

### 2.3 Jede Reduktion wird benannt

Eine Kachel zeigt weniger als der Endpunkt liefert. Das ist ihr Zweck — und ihre
Gefahr: ein Ausschnitt, der nicht als Ausschnitt kenntlich ist, sieht aus wie
ein vollständiges Bild und behauptet damit „mehr liegt nicht an". Zwei Arten,
beide stehen in der Kachel:

| Art | Beispiel | Feld |
|---|---|---|
| Abschneiden | „5 von 23 angezeigt" | `hinweis` |
| Filtern | „nur fällige und überfällige Vorgänge (von 12)" | `grundlage` |

**DB14** hält das über alle Reduzierer fest. Und **leer ist nicht ausgefallen**:
ein Leerbefund sagt „nichts liegt an", ein Fehlschlag, dass die Erhebung nicht
gelaufen ist — anderer Text, andere Einfärbung, eigener Test (DB13).

### 2.4 Die Fristen-Kachel zeigt keine Zahl ohne Aussage

Sie ist die einzige mit einer Rechtsfolge. Ist der Parametersatz nicht bestätigt
oder verweigert der Endpunkt die Aussage, steht dort der **Grund** und keine
Zahl — eine Zahl wäre eine unbelegte Rechtsbehauptung. Die Vorbehalte des
Endpunkts fahren **immer** mit, auch wenn eine Zahl da steht (DB08/DB09).

---

## 3. Zwei Stellen, an denen es leicht gebrochen wäre

**Der Fall-Sprung der Kommandopalette.** `/api/overview` speist die
Tabulator-Tabelle, und die Palette springt über `focusCase()` in genau diese
Instanz (Build 459). Hätte die Kachel `fallampel` die Tabelle durch eine eigene,
gedrängte Darstellung ersetzt, wäre der Sprung **still** ausgefallen — die
Palette hätte weiter zur Übersicht gewechselt und dort nichts mehr hervorheben
können. Deshalb das **Steckplatz-Verfahren**: die Kachel bekommt einen leeren
Rumpf, in den die Shell die echte Tabelle zeichnet.

**Der falsche Reduktionshinweis.** Beim ersten Probelauf meldete `fallampel`
„0 von 3 angezeigt", obwohl sie über den Steckplatz alle Fälle zeigt — `gesamt`
war mit der Fallzahl belegt worden. `gesamt` ist die Grundgesamtheit der
**Zeilenliste**; eine Kachel ohne Zeilenliste hat keine. Korrigiert, mit
Begründung im Quelltext und Testabdeckung (DB04).

---

## 4. Was Bestätigung braucht

1. **`viewprefs` trägt `immer: true`** — die einzige Sicht ohne Rechteprüfung.
   An ihr gibt es nichts zu schützen, und bei default-deny käme niemand an seine
   eigenen Einstellungen, bis jemand ein Recht erteilt, das man niemandem
   sinnvoll vorenthalten kann. **CN02b** riegelt ab, dass sie die einzige
   bleibt. Zehn bestehende JS-Tests mussten dafür angepasst werden — sie nennen
   die Ausnahme jetzt ausdrücklich, statt sie zu verschweigen.
2. **Der Zähler in der Navigation** (Abschnitt 2.2). Ihre Freigabe betraf das
   Dashboard; für die Navigation steht die konservative Fassung. Soll sie
   fallen, ist es ein Einzeiler.
3. **Der Kachel-Umfang** — acht Kacheln, alle aus bestehenden Endpunkten.
   Weitere sind je ein Eintrag in `viewpref_katalog.WIDGETS` plus ein
   Reduzierer; **VP24** erzwingt, dass beides zusammen kommt.

---

## 5. Prüfungen, die künftige Builds festhalten

| Test | Hält fest |
|---|---|
| **VP01** | Der Sichten-Katalog des Servers deckt sich mit `VIEW_CATALOG` in `cockpit.js`. |
| **VP02** | Die Arten in M037 sind zeichengleich mit dem Katalog (eingefrorene Kopie). |
| **VP03** | Jede Kachel nennt ein echtes Recht und einen Endpunkt, den `dispatch()` kennt. |
| **VP24** | Zu jeder Kachel gibt es einen Reduzierer — und umgekehrt. Keine Endpunkt-Zeichenkette im Browser. |
| **CN02b** | `viewprefs` ist der einzige Eintrag ohne Rechteprüfung. |
| **DB13/DB14** | Ausfall ≠ Leerbefund; wer abschneidet oder filtert, sagt es. |
| **VE08/EX01** | Jede Sicht ist exportierbar oder ausdrücklich ausgenommen. |

---

## 6. Betrieblich

Reihenfolge: M035 (540) → M036 (544) → **M037 (545)**.
Vor dem Einspielen verbindlich:

```
python tools/pruefe_migrationskette.py --db data/coordinator.db
```

Nach dem Lauf erwartet: `schema_migrations` enthält **37**, `rbac_capability`
zählt **45**, `person_view_pref` existiert und ist **leer**. Es ist **nichts zu
löschen**.

**Regression (Container, gegen 0.8.544):**
Python 2281 → **2306** passed / 50 skipped / 45 subtests ·
vitest 1308 → **1347** passed / 1 skipped / 1 todo, 105 → **107** Dateien.
`tests/test_editor_renderer.py` bleibt im Container ausgeklammert (PEP-701,
Python 3.11) — **in der VM muss sie mitlaufen**.

---
*Dokument-Ende · Übergabe AP-3G · 2026-07-26*
