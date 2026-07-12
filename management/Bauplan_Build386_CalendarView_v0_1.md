# Bauplan Build 386 — Cockpit-Sicht „Kalender & Wiedervorlage" (Frontend)

**Version:** 0.1 · **Datum:** 2026-07-12
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Basis:** 0.7.385 · **mc:** 2026-07-12 · **Migration:** keine.

---

## 1. Abgrenzung

Reiner **Frontend**-Build zum Backend aus 385 (Festlegung 363). Das Backend
bleibt **unverändert**.

**Recht:** `external.view` (Sicht) · Schreiben nur mit `external.edit`.
Nav-Gruppe **„Überblick"**, weil die Sicht **beide Rollen** bedient: die Chefin
sieht alle Fälligkeiten, der Ermittler (Scope `eigene`) die seines Falls.
Die Kapselung passiert im **Backend** (Scope), nicht in der Navigation.

---

## 2. Zwei Abrufe, eine Sicht

```
GET /api/calendar?von=&bis=   -> Monatsraster (externe Vorgänge + Abwesenheiten
                                 + Feiertage)
GET /api/external?stichtag=   -> Fälligkeitsliste + Arbeitsvorrat
```

Beide verwenden **denselben Stichtag**. Der Server bestimmt ihn
(`Europe/Berlin`); die Sicht übernimmt ihn aus der Kalender-Antwort und gibt ihn
der Vorgangsliste **ausdrücklich** mit. Andernfalls könnten Raster und Liste
**unterschiedliche Ampeln** zeigen — ein Widerspruch, den niemand auflösen könnte.

---

## 3. Die drei Dinge, die diese Sicht leisten muss

1. **Nichts darf durchrutschen.** Ein **überfälliger** Vorgang aus einem früheren
   Monat steht nicht nur im Raster (dort wäre er beim Blättern unsichtbar),
   sondern zusätzlich in einem eigenen **roten Block** *„Überfällig — außerhalb
   dieses Monats"*. **Genau dieses Versäumnis soll das System verhindern.**
2. **Der Kalender sagt, wenn er schweigt.** `hinweise` aus der Serverantwort
   werden **angezeigt** („Diese Sicht ist NICHT vollständig — n Quelle(n) liefern
   nichts: …"). Ein leerer Kalender ohne Erklärung wäre gefährlicher als gar
   keiner.
3. **Die Rechengrundlage steht dabei.** `stichtag_text` wird sichtbar ausgegeben.
   Eine falsche VM-Uhr fällt so **einem Menschen** auf.

---

## 4. Warum ein Zeitraum an **jedem** Tag erscheint

`entriesByDay()` bildet eine Abwesenheit (15.–17.) auf **alle drei Tage** ab.
Sonst sähe man am Tag der Wiedervorlage nicht, dass der zuständige Ermittler
**im Urlaub** ist. **Das ist der eigentliche Nutzen der gemeinsamen Sicht** — und
die praktische Einlösung der Entscheidung aus 385.

---

## 5. Schreiben

- **Zweistufig:** Knopf → Bestätigung → Ausführen. **Kein optimistisches UI**:
  nach dem POST werden **beide** Abrufe neu geladen.
- **Verschieben verlangt einen Grund.** Fehlt er, wird **kein POST gestellt** —
  die Oberfläche bietet keine Anfrage an, die der Server zwingend mit 400
  abweisen würde. Die Meldung nennt den Grund im Klartext.
- **Abschließen ist unwiderruflich** — der Bestätigungstext sagt das **wörtlich**
  („Das lässt sich NICHT zurückdrehen — ein Irrtum wird durch einen NEUEN Vorgang
  korrigiert").
- **`availableActions()` spiegelt `MatterStatus`:** `offen` → verschieben ·
  Antwort · ohne Ergebnis abschließen; `beantwortet` → verschieben · erledigt ·
  ohne Ergebnis; **abgeschlossen → keine Aktion** (mit Begründung statt stiller
  Leere).

### Fall-Eingabe im Formular „Neuer Vorgang" — bewusst ein **Eingabefeld**

`/api/external` liefert nur Fälle, zu denen **schon ein Vorgang existiert**. Eine
daraus gebaute **Auswahlliste** könnte für einen Fall **ohne** Vorgang **nie einen
ersten** Vorgang anlegen — genau den Normalfall. Sie hätte diesen Mangel **still
versteckt** (die Liste sieht ja gefüllt aus). Der Server prüft die Eingabe ohnehin
doppelt: unbekannter Fall → 400, nicht zugewiesener Fall → 403.

> **Offen (vermerkt):** eine komfortable Fallauswahl braucht einen eigenen
> Endpunkt („welche Fälle darf ich?"). Backend → eigener Build.

---

## 6. Umfang (geliefert)

- **NEU** `management/server/static/cockpit_calendar.js`
  (IIFE + UMD, `window.AIWCockpitCalendar`)
- `cockpit.js` — Katalogeintrag `{id:'calendar', cap:'external.view',
  group:'Ueberblick'}`, `loadCalendar()`, Dispatch, SSE-Reload (ein
  `audit_log`-Ereignis kann ein Verschieben durch eine **andere** Person sein →
  Fälligkeiten neu messen)
- `cockpit.html` — Script-Tag (**`git add -f`**)
- `cockpit.css` — additiver Block, eng auf `.aiw-cal-*` gefasst
- **NEU** `tests/unit/test_cockpit_calendar.test.js` (KA01–KA13, 13 Fälle)
- `tests/unit/test_cockpit_nav.test.js` — Katalog 13 → 14, neu CN03c
- **NEU** `management/Bauplan_Build384_*.md`, `Bauplan_Build385_*.md` (nachgereicht)

**Datumsrechnung** läuft durchgehend über `Date.UTC`. Mit lokaler Zeit läge in
der Sommerzeit ein Tagessprung um eine Stunde daneben, und ein Monatserster
könnte auf den Vormonat fallen. **Der Server bleibt die Quelle der Wahrheit für
den Stichtag** — hier wird nur das Raster gezeichnet.

---

## 7. Regression (run_tests.py)

```
pytest : 1030 passed, 59 skipped, 6 subtests   (unverändert — Frontend-only)
vitest : 605 passed (591 + 13 + 1), 52 Testdateien
```

---

## 8. Abnahme

**Server neu starten.** **Grants aus 385 müssen vergeben sein**, sonst wirkt die
Sicht wie kaputt, obwohl sie korrekt default-deny arbeitet.

1. Nav „Überblick" → **Kalender & Wiedervorlage**. Stichtagsvermerk sichtbar.
2. Vorgang mit Datum in der **Vergangenheit** anlegen → **roter Block
   „Überfällig — außerhalb dieses Monats"**, auch wenn man einen anderen Monat
   ansieht.
3. Eine **Abwesenheit** (Kapazität) über den Tag einer Wiedervorlage legen → im
   Raster stehen **beide** am selben Tag.
4. **Verschieben ohne Grund** → Meldung „Grund ist Pflicht", **kein** POST
   (Netzwerk-Tab prüfen).
5. **Abschließen** → Bestätigung nennt „ENDGÜLTIG"; danach bietet der Vorgang
   **keine Aktion** mehr an.
6. Als Ermittler **ohne** `external.edit`: kein „Neuer Vorgang", keine
   Aktionsknöpfe — aber Raster und Warnungen stehen.
7. DEV-Log: `window.AIW_COCKPIT_DEBUG = true`.

---

## 9. Nächster Build

**`investigation_results`** (Ermittlungsergebnis-Bewertung, mehrkriteriell:
Konfidenz **und** Qualität) — braucht einen eigenen Bauplan. Danach sind aus
Welle 1 noch offen: **Textbaustein-Bibliothek** und die **ungeprüfte
PDF-Ausgabe**.

---

*Dokument-Ende · Bauplan Build 386 · 2026-07-12*
