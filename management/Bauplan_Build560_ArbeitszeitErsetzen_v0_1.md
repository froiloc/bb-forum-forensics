# Bauplan Build 560 — Arbeitszeit: Dublettensperre, Entfernen, Ersetzen

**Version:** 0.1 · **Datum:** 2026-07-29 · **Baubasis:** `b86b59a` (v0.8.559)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc, 2026-07-29 (Entscheidungen 1–3 beantwortet, „Weiter geht's")

---

## 1. Anlass und Vorbefund

mc meldete beim Test von 0.8.559: eine Korrektur zum **selben** Stichtag legte
eine zweite Zeile an, statt die alte zu ersetzen.

**Die Rechnung war dabei nie falsch.** `capacity_calculator._load_worktime`
sortiert `ORDER BY effective_from ASC, id ASC` und nimmt die letzte passende
Regel — bei gleichem Stichtag also die **jüngere**. Falsch war die
**Darstellung**: die Tabelle sammelte Karteileichen, und niemand konnte sehen,
welche der beiden Zeilen gilt.

Vorhandene Bausteine (gemessen): `person_worktime.deleted_at` existiert seit
`m008:57`, der Rechner filtert bereits `deleted_at IS NULL`, und
`CoordinatorWriter.audited_write_many` (Build 534) kann mehrere Einheiten in
**einer** Transaktion mit **je eigenem** Beleg schreiben. Es fehlten nur die
Methode, der Ereignistyp und die Route.

---

## 2. Dublettensperre

`set_worktime` weist eine zweite **aktive** Regel je `(person_id,
effective_from)` zurück (mc, Entscheidung 1).

Die Prüfung läuft **innerhalb der Schreibtransaktion** — sie wird aus `do_write`
gerufen, nicht davor. So kann zwischen Prüfung und Einfügen nichts
dazwischenkommen, und ein Verstoß rollt den ganzen Vorgang zurück: es bleibt
weder Zeile noch Beleg. **KP15** prüft beides.

---

## 3. Entfernen ist Soft-Delete

**„Löschen" entfernt hier nichts.** Die Zeile bleibt stehen und trägt
`deleted_at`; sie fällt aus Rechnung und Liste, nicht aus dem Bestand.

**Der Beleg trägt die entfernten Werte** — `person_id`, `effective_from` und
alle sieben Minutenwerte. Sonst stünde in der Akte nur „Zeile 7 entfernt", und
was darin stand, müsste aus der Datenbank rekonstruiert werden.

Ein **zweites** Entfernen wird zurückgewiesen, statt einen Beleg ohne Wirkung zu
erzeugen. **KP16**, **KP17**.

---

## 4. Ersetzen ist eine eigene Handlung

`replace_worktime` führt Entfernen und Setzen in **einer** Transaktion aus
(`audited_write_many`): **zwei eigene Belege**, kein Sammelbeleg.

Zwischen zwei getrennten Aufrufen läge ein Zustand, in dem die Person zum
Stichtag **gar keine** Regel hat — und bricht der zweite ab, bleibt sie darin
stehen. **KP19** prüft genau das: nach einem Fehlschlag ist weder die alte Zeile
entfernt noch ein Beleg zurückgeblieben (`MAX(seq)` unverändert).

**Die Reihenfolge ist zwingend: erst entfernen, dann setzen.** Andersherum
schlüge die eigene Dublettensperre an, weil die alte Zeile zum Zeitpunkt des
Setzens noch aktiv wäre. `audited_write_many` arbeitet die Einheiten vollständig
nacheinander ab (`do_write` → Beleg → `after_audit` je Einheit) — die Sperre in
der zweiten Einheit sieht die erste also bereits.

**Die Scope-Prüfung läuft zweimal:** gegen die Person der **alten** Zeile *und*
gegen die Zielperson der neuen. Sonst könnte eine selbstpflegende Person eine
fremde Zeile entfernen, indem sie als Zielperson sich selbst angibt. **KP21**
geht genau diesen Umweg.

---

## 5. Fehler nennen das Feld

`CapacityError` trägt ein optionales `feld`; die 400-Antwort gibt es weiter (mc,
Entscheidung 2 — Feldmarkierung in der Oberfläche).

Der Parameter ist **nachgestellt und hat einen Vorgabewert**; alle bestehenden
Aufrufe `CapacityError("text")` bleiben gültig. Kennt eine Ausnahme kein Feld,
steht `feld` **nicht** in der Antwort — die Oberfläche zeigt dann die Meldung
ohne Markierung, statt irgendein Feld zu raten. Bei sieben Minutenfeldern
nebeneinander ist „mon_min muss eine Minutenzahl >= 0 sein" sonst eine
Suchaufgabe. **KP20**.

---

## 6. Endpunkte und Kommandozeile

| Methode | Pfad | Nutzlast |
|---|---|---|
| POST | `/api/capacity/worktime/remove` | `worktime_id` |
| POST | `/api/capacity/worktime/replace` | `worktime_id, person_id, effective_from, mon_min…sun_min, effective_to?` |

Die Kommandozeile wurde nachgezogen (`remove-worktime`, `replace-worktime`) —
kein Selbstzweck: seit der Dublettensperre läuft eine Korrektur zum selben
Stichtag über `replace`. Ohne diese Kommandos bekäme jemand an der
Kommandozeile einen Fehler, wo bisher etwas durchlief, **ohne zu erfahren, wie es
richtig geht**.

---

## 7. Zwei eigene Fehler beim Bau

1. Beim Herausziehen der `INSERT`-Parameter in `_set_unit` fiel `person_id` aus
   der Liste (12 statt 13 Bindungen). **22 bestehende Tests schlugen sofort an** —
   genau wofür die Regression da ist.
2. Im Test: die Nutzlast eines Belegs steht in `audit_log.content`, nicht in
   `.payload`.

Beides korrigiert.

---

## 8. Ankerdelta und Regression

**+1 Ereignistyp** (`WORKTIME_REMOVED`). Keine Migration, keine neuen
Capabilities (46), `VIEW_CATALOG` unverändert (42), coordinator-Kette m001–m037,
evidence `[1,2,3]`.

| | 0.8.559 | 0.8.560 |
|---|---|---|
| Python | 2320 / 50 skipped / 45 subtests | **2327** (+7: KP15–KP21) |
| vitest | 109 Dateien, 1503 passed | **unverändert** (kein JS berührt) |

---

## 9. Offen — Build 561 (Frontend)

Formularzustand überlebt das Neuladen · Personenauswahl bleibt stehen ·
Stichtag vorbelegt · Erfolgsmeldung mit den übernommenen Werten ·
Feldmarkierung im Fehlerfall anhand `feld` · Hinweis 478/492 Minuten ·
Minutenrechner als bewegliches Modal · Aktionsspalte „Entfernen"/„Bearbeiten" ·
Umschaltung „auch entfernte anzeigen" · Anhang an `cockpit.css`.

---
*Dokument-Ende · Bauplan Build 560 · v0.1 · 2026-07-29*
