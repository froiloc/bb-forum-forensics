# Bauplan Build 564/565 — `module_key` nachtragbar machen

**Version:** 0.1 · **Datum:** 2026-07-29 · **Baubasis:** `7e7561d` (v0.8.563a)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc, 2026-07-29 (`mc`; Schlüssel endgültig, 8 Altzeilen)

---

## 1. Befund

| Ebene | Zustand | Fundstelle |
|---|---|---|
| Schema | `module_key TEXT` **NULL-fähig**, partieller Unique-Index `WHERE module_key IS NOT NULL` | `templates.db.schema.sql:15, 103-106` |
| Migration | legt nur Spalte, Index und **einen** Seed an — **kein Nachtragen** | `migrate_templates_module_key.py` |
| Validierung | `module_key` ist Pflicht — für Speichern **und** Vorschau | `module_validator.py:72-76` |
| Frontend | im Editiermodus `disabled = true` | `cockpit_modules.js:188` |

---

## 2. Die Falle, die man von außen nicht sieht

`ModuleAuthorRepo.upsert` adressiert die Zeile **ausschließlich über
`module_key`** (`UPDATE … WHERE module_key=?`). Hätte man nur das Eingabefeld
entsperrt, hätte der Upsert unter dem neu getippten Schlüssel **nichts**
gefunden und eine **zweite Zeile** angelegt — die Altzeile wäre unangetastet
daneben stehen geblieben. Aus einem gesperrten Baustein wären zwei geworden,
einer davon weiterhin unerreichbar.

**Der reine Frontend-Fix hätte den Schaden vergrößert.** `TM20` prüft
ausdrücklich, dass keine zweite Zeile entsteht.

---

## 3. Build 564 — Backend

1. **Nachtrag über die Zeilen-`id`**, und nur dafür: ist `id` im Payload und
   trägt die Zeile **keinen** Schlüssel, wird per `id` aktualisiert. Sonst gilt
   weiter der Weg über `module_key` — zwei Adresswege auf dieselbe Zeile wären
   einer zu viel.
2. **Der Schlüssel ist danach endgültig** (mc). Ein Umtragen wird abgewiesen:
   Berichtsvorlagen verweisen über ihn auf den Baustein. Wanderte er, bräche
   jede Vorlage — und zwar **still**, denn ein nicht gefundener Baustein fällt
   erst beim Erzeugen des Berichts auf. `TM22`.
3. **Kollision vor dem Schreiben.** Der Unique-Index würde einen
   `IntegrityError` werfen; der sagt dem Ausfüllenden nichts. Stattdessen eine
   Meldung, die **nennt**, wer den Schlüssel schon hat. `TM23`.
4. **Die Zuweisung ist eine eigene Tatsache im Beleg** (`old_value`:
   `module_key: null`, `new_value`: der Schlüssel). Ohne das stünde in der Akte
   nur „geändert". `TM21`.
5. **Die Vorschau prüft denselben Weg mit**, schreibfrei — sonst sähe der
   Dry-Run grün aus und das Speichern schlüge fehl. `TM26`.

Neue Fehlerklasse `ModuleKeyAssignError` mit Feldangabe (Muster
`CapacityError`, Build 560); der Endpunkt antwortet **400 mit `feld`** statt
500. `TM25`.

---

## 4. Build 565 — Frontend

6. **Feld entsperrt genau dann, wenn kein Schlüssel da ist.** Bei vorhandenem
   Schlüssel bleibt es fest wie bisher.
7. **Vorschlag aus dem Titel** (`Anhörung des Beschuldigten` →
   `legal.anhoerung.des.beschuldigten`). Umlaute werden **ausgeschrieben**,
   nicht gelöscht — sonst fielen „Anhörung" und „Anhrung" zusammen. Frei
   überschreibbar, nie automatisch gespeichert. `MK01`, `MK02`.
8. **Hinweiszeile direkt unter dem Feld.** Ein Feld, das mal gesperrt und mal
   offen ist, ohne dass jemand sagt warum, wirkt kaputt.
9. **Die Listenmarkierung** greift bei Altzeilen über die `id` statt über den
   Schlüssel — sonst beruhte sie auf dem Text `"null"`.
10. **`id` wird nur im Nachtragsfall gesendet.** `MK03`.

**Nebenbei, und es war mein Fehler:** die Zielanzeige des Minutenrechners
(Build 561) folgte dem Fokus nicht. Sie horcht jetzt auf `focusin` am Dokument
— bewusst nicht auf `click`, weil man mit der Tabulatortaste ebenso das Feld
wechselt; Ereignisse aus dem Rechner selbst werden übergangen, sonst
überschriebe ein Klick in „Stunden" die Anzeige. Der Horcher wird beim
Schließen abgemeldet. `MR11`, `MR12`.

---

## 5. Kein Sammelskript

Bei **8** Altzeilen (Auskunft mc) ist ein Nachtragsskript mehr Werkzeug als
Arbeit — und jede Kennung sollte einmal bewusst gelesen werden, sie ist danach
endgültig. Als Merkposten im Tracker geführt, damit der Nachtrag nicht auf
halbem Weg liegen bleibt.

---

## 6. Ankerdelta und Regression

Keine Migration, keine neuen Capabilities (46), keine neuen Ereignistypen,
`VIEW_CATALOG` unverändert (42).

| | 0.8.563a | 0.8.564 | 0.8.565 |
|---|---|---|---|
| Python | 2331 | **2338** (+7: TM20–TM26) | unverändert |
| vitest | 1524 | unverändert | **1529** (+5: MR11, MR12, MK01–MK03) |

---
*Dokument-Ende · Bauplan Build 564/565 · v0.1 · 2026-07-29*
