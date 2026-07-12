# Bauplan Build 391 — Hotfix: Query-Vertrag des Management-Servers

**Version:** 0.1 · **Datum:** 2026-07-12
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Basis:** 0.7.390 · **mc:** 2026-07-12 · **Migration:** keine.
**Art:** Fehlerbehebung. **Kein neues Verhalten.**

---

## 1. Der Fehler

`ManagementApp.dispatch()` bekommt die Query in der **`parse_qs`-Form**:

```python
query: Optional[Dict[str, List[str]]]     # die Werte sind LISTEN
```

Die Handler aus **385** und **387** lasen sie als **Skalare**:

```python
von = q.get("von")            # -> ['2026-07-01']   statt '2026-07-01'
user_id = int(q.get("user_id"))   # -> TypeError
```

**Gemessene Wirkung:**

```
--- ECHTE Query-Form (parse_qs), VOR dem Fix ---
/api/calendar    -> 400  Ungueltiges Datum '['2026-07-01']' (erwartet YYYY-MM-DD).
/api/external    -> 200      <-- NUR SCHEINBAR
/api/results     -> 400  user_id fehlt/ungueltig.
```

`/api/calendar` war **durchgängig tot** (das gemeldete Symptom).
`/api/results` ebenso.
**`/api/external` war latent kaputt:** Der als Liste verpackte Stichtag wurde nur
dann ausgewertet, wenn es überhaupt Vorgänge gab. Bei leerer Liste kam 200
heraus — **mit dem ersten echten Vorgang wäre auch dieser Endpunkt gekippt.**
Ein Fehler, der auf ein leeres System wartet, ist der gefährlichere.

---

## 2. Warum die Tests das nicht gefunden haben

**Die Tests riefen `dispatch()` mit Skalaren auf** — also mit einer Form, die der
echte Server **nie** liefert:

```python
app.dispatch(1, "/api/calendar", {"von": "2026-07-01", ...})   # FALSCH
```

Zwölf grüne Tests, und der Endpunkt war trotzdem tot. **Das ist die
„grün aber tot"-Falle — nur an der Schnittstelle statt in der Logik.**
Der Test prüfte echten Code, aber gegen einen erfundenen Aufrufvertrag.

Deshalb ist die Testkorrektur der **wichtigere Teil dieses Builds**, nicht der
Einzeiler im Handler.

---

## 3. Vollständigkeitsprüfung (gemessen, nicht gerechnet)

Alle Query-Lesestellen in `management_app.py`:

| Zeile | Handler | Stand |
|---|---|---|
| 618, 973 | `_capacity`, `_report_verify` | ✅ `vals = q.get(k); vals[0]` |
| 730 | `_myhistory` | ✅ `query["limit"][0]` |
| 832 | `_stats` | ✅ `(q.get("format") or ["json"])[0]` |
| 929 | `_reports` | ✅ `(q.get("force") or ["0"])[0]` |
| **1176–1193** | **`_external`** | ❌ **Skalar** → behoben |
| **1235–1246** | **`_calendar`** | ❌ **Skalar** → behoben |
| **1480** | **`_results`** | ❌ **Skalar** → behoben |

**Nur meine drei Handler waren betroffen.** Die vor 385 gebauten lesen korrekt.

**Forensischer Server (`/_forensic/results`, Build 390): nicht betroffen.**
`handle()` wertet die Query gar nicht aus — die `user_id` kommt aus dem
`ResolvedContext`, nicht aus der Query; der POST liest einen JSON-Rumpf.

**Es wurden keine falschen Daten geschrieben.** Der Fehler betraf ausschließlich
**Lesepfade**; die POST-Handler lesen JSON-Rümpfe.

---

## 4. Der Fix

Ein gemeinsamer Helfer `ManagementApp._q1(query, key, default=None)`:

- nimmt die **parse_qs-Liste** und liefert den ersten Wert;
- akzeptiert **auch** einen Skalar — **nicht**, um den Vertrag aufzuweichen,
  sondern damit ein Aufrufer, der ihn missversteht, ein **richtiges Ergebnis**
  bekommt statt eines stillen 400.

Alle Lesestellen in `_external` (`offen`, `status`, `user_id`, `stichtag`),
`_calendar` (`von`, `bis`, `stichtag`) und `_results` (`user_id`) laufen darüber.

---

## 5. Die Wachhunde (der eigentliche Ertrag)

**EX13** (`test_external_matters.py`) und **IR14** (`test_investigation_results.py`)
prüfen **ausschließlich die echte parse_qs-Form** — und zwar **mit Daten**, denn
ohne Vorgänge war der Fehler unsichtbar.

EX13 prüft zusätzlich, dass der Stichtag **wirklich als String ausgewertet**
wurde: Wiedervorlage am 19.07., Stichtag 12.07., Vorwarnfrist 7 Tage → die Ampel
**muss gelb** sein. Dieser Wert stimmt **nur**, wenn die Datumsrechnung
tatsächlich lief.

Sämtliche bestehenden Endpunkt-Tests in beiden Suiten wurden auf die echte
Listenform umgestellt.

---

## 6. Regression (run_tests.py)

```
pytest : 1054 passed (1052 + 2 Wachhunde), 59 skipped, 6 subtests
vitest : 617 passed, 53 Testdateien   (unverändert — Backend-only)
```

---

## 7. Abnahme

**Management-Server neu starten.**

1. Cockpit → **„Kalender & Wiedervorlage"** lädt (vorher: HTTP 400).
   *Voraussetzung: die Grants für `external.*` sind vergeben — sonst erscheint
   die Sicht gar nicht erst in der Navigation (default-deny).*
2. Einen externen Vorgang anlegen → er erscheint in Raster **und** Liste;
   die Ampel passt zum angezeigten Stichtag.
3. `GET /api/results?user_id=<Fall>` liefert 200 (vorher 400).
4. Monatsnavigation (Vor/Zurück/Heute) funktioniert.

---

## 8. Lehre für kommende Builds

> **Ein Test, der den Aufrufvertrag selbst erfindet, prüft nichts.**
> Endpunkt-Tests rufen `dispatch()` ab sofort **nur** in der Form auf, die der
> HTTP-Handler tatsächlich erzeugt (`parse_qs` → `Dict[str, List[str]]`).

---

*Dokument-Ende · Bauplan Build 391 · 2026-07-12*
