# Bauplan AP-3G — Modul-Steuerung / konfigurierbares Dashboard

**Arbeitspaket:** AP-3G (Welle 3, Baustelle 7) · **Idee 37** (§15 des Ideenpapiers)
**Builds:** 545 (Backend) · 546 (Frontend Sichten-Steuerung) · 547 (Frontend Widget-Überblick)
**Baubasis:** `9f11b97` (v0.8.544)
**Migration:** **M037** (`person_view_pref`) · **Neue Rechte:** keine
**Version:** 0.1 · 2026-07-26

---

## 0. Abweichungen vom Wellenplan — und warum

Der Bauplan Welle 3 (`management_Bauplan_Welle3_Builds522ff_v0_1.md` §3) sieht für
AP-3G **zwei** Builds (538/539) und **M035** vor. Drei Angaben davon sind
überholt; das ist hier festgehalten, nicht stillschweigend korrigiert:

| Wellenplan | tatsächlich | Grund |
|---|---|---|
| Builds 538/539 | **545–547** | Der Parallelbetrieb hat die Nummern 538–544 verbraucht (Ende: Build 544). |
| M035 | **M037** | M035 ist der Metriken-Seed (Build 542), M036 die Volltext-Freigabe (Build 544). Nächste freie Nummer ist 37 (Leitfaden §17.4). |
| 2 Builds | **3 Builds** | Backend und Frontend gehören nach Festlegung 363 ohnehin getrennt. Der dritte Build trennt die Navigations-Steuerung von der Kachelfläche des Überblicks: das sind zwei verschiedene Gegenstände, und beide sollen einzeln lauffähig und einzeln zurücknehmbar sein (GR2). |

Der Wellenplan zitiert außerdem `cockpit.js:413` als Beleg dafür, dass
`localStorage` für Sichtzustand ausgeschlossen ist. Die Stelle steht inzwischen
auf **Zeile 447** — Wortlaut unverändert („Zustand lebt nur im Speicher (kein
localStorage — Projekt-/Artefakt-Regel)"), nachgesehen am 2026-07-26 gegen
0.8.544. Der Beleg trägt, nur die Zeilennummer nicht.

---

## 1. Was gebaut wird

Eine Person kann ihre eigene Oberfläche einrichten:

1. **Navigation** — Reihenfolge und Sichtbarkeit der Cockpit-Sichten.
2. **Überblick** — Auswahl und Reihenfolge von Kacheln.

Beides wird **serverseitig** je Person gespeichert (`person_view_pref`), weil
der Browser als Ablageort projektweit ausgeschlossen ist.

**Was ausdrücklich NICHT gebaut wird:** kein neuer Datenweg. Jede Kachel speist
sich aus einem Endpunkt, den es bereits gibt (`api_path` im Kachel-Katalog).
Eine Kachel ist eine zweite, gedrängte Darstellung dessen, was die zugehörige
Sicht ohnehin zeigt — und erbt damit deren Rechteprüfung, Scope und Fehlerbild.

---

## 2. Die heikle Stelle: Ausblenden und Grundregel 1

Eine ausgeblendete Sicht könnte eine übersehene Eskalation bedeuten. Das ist die
einzige Stelle, an der eine Bedienvorliebe an Grundregel 1 rührt.

**Die Antwort ist nicht, das Ausblenden zu verbieten.** Dann richtete sich
niemand seine Oberfläche ein, und die Sicht bliebe trotzdem ungelesen — nur
ohne dass irgendwo stünde, dass sie abgestellt wurde. Die Antwort ist, dass
nichts **still** verschwindet:

| Maßnahme | Build |
|---|---|
| (a) Die Navigation trägt dauerhaft einen Zähler „N Sichten ausgeblendet". | 546 |
| (b) Ausgeblendete Sichten bleiben über die Kommandopalette (Strg-K) erreichbar — sie bekommt bewusst die **nur rechte-gefilterte** Liste. | 546 |
| (c) Rücksetzen auf Werkseinstellung mit einem Klick. | 545/546 |
| (d) Die Sicht „Ansicht anpassen" selbst ist nicht ausblendbar. | 546 |
| (e) Jede Speicherung ist ein Audit-Beleg mit dem **vollständigen** Zustand. | 545 |

Zu (e): Wer eine Eskalationssicht ausgeblendet hatte, hat sie nicht übersehen,
sondern abgestellt. Das ist ein Unterschied, den sich später niemand aus dem
Gedächtnis rekonstruiert. Der Payload trägt deshalb `reihenfolge` und
`ausgeblendet` vollständig und kein Delta — aus **einem** Beleg ist ablesbar,
wie eine Oberfläche zu einem Zeitpunkt eingerichtet war.

Und die Zeilen sind auswertbar: „Wer hat die Eskalationssicht ausgeblendet?" ist
ein `SELECT` und keine JSON-Zerlegung. Deshalb normalisiert und nicht als
JSON-Klumpen.

---

## 3. Rechte filtern zuletzt

Nicht verhandelbar (Wellenplan §3): **eine Vorliebe darf nie eine Sicht
einblenden, für die das Recht fehlt.** Die Reihenfolge im Frontend lautet
deshalb:

```
VIEW_CATALOG  ->  Vorliebe (Reihenfolge/Sichtbarkeit)  ->  visibleViews(capabilities)
```

Der Rechtefilter steht **hinten**. Eine gespeicherte Vorliebe zu einer Sicht,
für die das Recht später entzogen wird, verschwindet damit konstruktiv — sie
kann sie nicht wiederbeleben.

Bei den **Kacheln** trifft die Rechteauskunft der **Server** (`erlaubt` je
Kachel in `GET /api/viewprefs`). Grund: die Zuordnung Kachel → Recht wird an
genau einer Stelle geführt (`viewpref_katalog.py`), und das ist die Stelle, die
der Server kennt. Der Browser leitet hier nichts selbst ab.

---

## 4. Build-Schnitt

### B545 — Backend

* `management/migrations/coordinator/m037_view_pref.py` — `person_view_pref`,
  rein additiv, nur `coordinator.db`, kein Rechte-Seed.
* `management/viewprefs/viewpref_katalog.py` — steuerbare Sichten (Kopie von
  `VIEW_CATALOG`, per Test gegen `cockpit.js` gehalten) + Kachel-Katalog
  (einzige Wahrheitsquelle).
* `management/viewprefs/viewpref_repo.py` — Lesen ohne Schreiber, Schreiben nur
  über `CoordinatorWriter`; **ein Audit-Beleg je Art**, vollständiges Ersetzen.
* `management/audit/event_types.py` — `view_pref_set`, `view_pref_reset`.
* `management/server/management_app.py` — `GET /api/viewprefs`,
  `POST /api/viewprefs`, `POST /api/viewprefs/reset`.
* Tests: `tests/test_management_viewprefs.py` (VP01–VP23).

**Keine Fähigkeit an diesen Endpunkten.** Eine Vorliebe kann keine Sicht
öffnen, für die das Recht fehlt; ein eigenes Recht hätte nur die Frage
aufgeworfen, wer es wem entzieht.

**Keine Vertretung.** `actor_id` muss `person_id` sein — auch für die Leitung.
Wer die Oberfläche einer anderen Person umbauen könnte, könnte ihr die
Eskalationssicht wegnehmen.

### B546 — Frontend: Sichten-Steuerung

* Neue Sicht `viewprefs` („Ansicht anpassen", Gruppe *Persönlich*), Eintrag in
  `NICHT_STEUERBAR` (d).
* `cockpit_viewprefs.js` — Sortable-Liste, Sichtbarkeitsschalter, Speichern,
  Zurücksetzen.
* `cockpit.js` — reine Funktion `applyViewPrefs(views, prefs)`; Rechtefilter
  bleibt hinten. Zähler ausgeblendeter Sichten in der Navigation.
* Tests: vitest.

### B547 — Frontend: Widget-Überblick

* `cockpit_dashboard.js` — Kachelfläche; die Fall-Übersicht wird die erste
  Kachel. **Ohne gespeicherte Vorliebe sieht der Überblick aus wie bisher** —
  eine Änderung, die allen im Produktivbetrieb die gewohnte Oberfläche umbaut,
  wäre der falsche Weg.
* Auswahl/Reihenfolge der Kacheln, jede an ihrem eigenen Recht.
* Tests: vitest. Kumulative Auslieferung + Übergabe.

---

## 5. Offene Punkte (3)

1. **Ausblendbarkeit von `escalation`/`nextactions`** — gebaut nach Abschnitt 2
   (erlaubt, aber nie still). Zur Bestätigung vorgelegt.
2. **Kachel-Umfang** — acht Kacheln, alle aus bestehenden Endpunkten. Weitere
   sind je eine Zeile im Katalog; die Auswahl ist ein Vorschlag.
3. **`unbekannt`-Aufräumen** — verwaiste Einträge werden benannt, aber nicht
   automatisch gelöscht. Ob die Oberfläche einen Aufräum-Knopf bekommt, ist
   noch nicht entschieden (B546).

---
*Dokument-Ende · Bauplan AP-3G · v0.1 · 2026-07-26*
