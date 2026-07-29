# Bauplan Build 561 — Kapazitätspflege: Bedienbarkeit

**Version:** 0.1 · **Datum:** 2026-07-29 · **Baubasis:** `a92a6f8` (v0.8.560a)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc, 2026-07-29 (Entscheidungen 1–3, „Weiter geht's")

---

## 1. Der Fehler — und warum er schlimmer war, als er aussah

mc meldete: nach dem ersten erfolgreichen Eintrag wurden Korrekturen „nicht
übernommen", und danach ließ sich auch für **andere Personen** nichts mehr
eintragen.

**Gemessen, nicht geraten.** Serverseitig nachgestellt:

```
1) mit Datum:                 (200, ok, audit_seq 41)
2) ohne Datum:                (400, 'effective_from fehlt (ISO-Datum).')
3) andere Person, ohne Datum: (400, 'effective_from fehlt (ISO-Datum).')

Stichtagsfeld nach dem Neuzeichnen: ""
Montagsfeld  nach dem Neuzeichnen: "0"
Personenauswahl steht auf: 2        (= erster Eintrag, nicht die Wahl)
```

**Eine Ursache, drei Symptome:** Nach dem Speichern lud die Sicht neu und
zeichnete das Formular vollständig neu — dabei wurde auch das **Pflichtfeld**
„Gültig ab" geleert. Jede Folgeeingabe ging ohne Datum hinaus.

**Die leisere Falle** war die zurückspringende Personenauswahl: wer nach dem
Speichern eine andere Person wählt und das Datum übersieht, sieht nur den
Fehler — wer beides ausfüllt und die Auswahl übersieht, schreibt auf die
**falsche Person**.

---

## 2. Vier Netze

1. **Der Formularzustand überlebt das Neuladen.** Der Lader hält ihn **vor**
   dem Absenden fest — nach dem Neuladen ist das alte DOM weg.
2. **Die Personenauswahl behält die getroffene Wahl.**
3. **Der Stichtag ist mit heute vorbelegt.** Ein leeres Pflichtfeld, das erst
   der Server bemängelt, ist eine Falle.
4. **Die Rückmeldung schreibt aus, was übernommen wurde:** „Gespeichert:
   Müller, ab 2026-01-01 — Mo 478, Di 478, … (Woche 2390 min, Beleg #41)."

Im **Fehlerfall bleibt alles stehen** — es wurde nichts geschrieben, und
niemand soll neu tippen. CP11, CP12, CP16.

---

## 3. Feldmarkierung

`postJson` führt `feld` aus der Fehlerantwort mit (Build 560); die Maske setzt
`.aiw-feldfehler` genau auf dieses Feld und räumt eine vorherige Markierung weg.

**Nennt der Server kein Feld, wird auch keines markiert** — ein geratenes rotes
Feld wäre schlimmer als gar keines. CP13.

---

## 4. Entfernen und Bearbeiten

Aktionsspalte je Arbeitszeit-Zeile. **„Bearbeiten" schreibt nichts**: es füllt
das Formular und schaltet auf **Ersetzen** um. Der Modus ist sichtbar
(Warnhinweis, Knopfbeschriftung „Zeile ersetzen", Abbruchknopf), weil das
Speichern dort eine **andere Wirkung** hat als sonst — es legt nicht an, es
ersetzt. CP15, CP17.

---

## 5. Minutenrechner

Eigene Datei (Grundregel 10): er hängt an keiner Sicht und kennt das
Kapazitätsmodul nicht — sein Ziel bekommt er von außen gesagt.

| Eigenschaft | Begründung |
|---|---|
| `7,5` → 450 min | `parseFloat('7,5')` wäre **7** gewesen — jeden Tag ein halber Arbeitstag weniger. Ein **Datenfehler**, kein Schönheitsfehler. |
| Eingabefelder `type=text` | `type=number` verwirft das Komma je nach Browser still oder liefert `''`. Beides wäre ein stiller Verlust der Eingabe. |
| Rundung wird **benannt** | „439 Minuten, gerundet von 438,60" — die Datenbank kennt nur ganze Minuten; niemand soll später eine Minute suchen, die er selbst erzeugt hat. |
| Prozent auf die **gesamte** Dauer | `(h·60 + m) · p/100`. Alles andere wäre an dieser Stelle eine Überraschung. Vorgabe 100 %. |
| „Übernehmen" ohne Ziel **meldet** das | Wer drückt und nichts passiert, hält das Werkzeug für kaputt. |
| Kein Überlagerungsschirm, kein Escape, Schließen nur über X | Genau der Zweck (mc): bei offenem Rechner soll man ein Formularfeld anklicken können, um das Ergebnis dorthin zu übernehmen. |
| Ziehen nur an der Titelzeile | Sonst rutscht das Fenster beim Markieren von Text weg. |

MR01–MR10.

---

## 6. Tagesvorgaben

478 min (Angestellte) / 492 min (Beamte) als **Hinweis und als Griff**: je ein
Knopf setzt Mo–Fr auf den Wert und Sa/So auf 0 — genau der Schritt, den man nach
dem Lesen ohnehin macht. Ausdrücklich eine **Hilfe, keine Regel**; jeder andere
Wert bleibt eintragbar. CP14.

---

## 7. Issue-Tracker

Acht Einträge, gegen `issue-tracker.schema.json` validiert — **nicht** als
`issue-tracker/data/issues.json` ausgeliefert, sondern als
`issue-tracker/eintraege_claude_Build561.json` **außerhalb** von `data/`.

Grund: `.gitignore:15` nimmt `data*/` aus. Der Live-Stand liegt nicht im Klon;
lesbar war nur `backups/issues_backup_20260729_164658.json` (ein Eintrag). Eine
vollständige `issues.json` auszuliefern hieße, spätere Einträge beim Entpacken
zu **überschreiben** — Datenverlust, und der ist in diesem Projekt die eine
Sache, die nicht passieren darf. Zwei der Einträge melden genau diese
Zusammenarbeitslücke und dass das Schema kein Versionssuffix wie `0.8.560a`
zulässt.

---

## 8. Bewusst nicht enthalten

Die Umschaltung „auch entfernte anzeigen". `list_worktime` kann
`include_deleted` bereits, aber der Durchgriff in `GET
/api/capacity/stammdaten` wäre eine **Backend**-Änderung und hätte den
Frontend-Build vermischt (Festlegung 363). Als offener Trackereintrag
dokumentiert, Ziel 0.8.562.

---

## 9. Ankerdelta und Regression

Keine Migration, keine neuen Capabilities (46), keine neuen Ereignistypen,
`VIEW_CATALOG` unverändert (42), coordinator-Kette m001–m037.

| | 0.8.560a | 0.8.561 |
|---|---|---|
| vitest | 109 Dateien, 1503 passed | **110** Dateien, **1520** passed (+10 MR, +7 CP) |
| Python | 2327 / 50 skipped / 45 subtests | **unverändert** (kein Python berührt) |

---
*Dokument-Ende · Bauplan Build 561 · v0.1 · 2026-07-29*
