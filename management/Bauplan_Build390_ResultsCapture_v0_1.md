# Bauplan Build 390 — Erfassungsmaske Ermittlungsergebnis (Nutzerinfo-Tab)

**Version:** 0.1 · **Datum:** 2026-07-12
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Basis:** 0.7.387 · **mc:** 2026-07-12 · **Migration:** keine.
**Enthält zusätzlich:** Bugfix `investigators` → `person` (§1).

---

## 1. Bugfix — ein stiller Fehlschlag in Produktion

Beim Messen von Baustelle 4 gefunden. `forensic_api/userinfo_data.py`:

```sql
LEFT JOIN cdb.investigators i ON i.id = c.assigned_to
```

**`investigators` gibt es seit Migration M005 (Build 342) nicht mehr** — die
Tabelle heißt `person`. Gegenprobe:

```
investigators vorhanden? False
JOIN auf investigators SCHLAEGT FEHL: no such table: investigators
```

**Wirkung — und warum sie schwer wiegt:** Der Fehler landete in einem breiten
`except Exception` → `logger.warning` → `return None`. Die Karte
**„Ermittlungskoordination"** zeigte dem Ermittler seither **immer „nicht
zugewiesen"** — unabhängig davon, wie der Fall tatsächlich zugewiesen war.
**Kein Absturz, keine Meldung in der Oberfläche.** Der Ermittler sah keine Lücke,
sondern eine **Falschaussage**.

**Zwei Änderungen:**
1. Join auf **`cdb.person`**.
2. Der Fehlerfall wird **nicht mehr zu `None` geschluckt**, sondern als
   `{"error": …}` an die Oberfläche gereicht. Die Karte zeigt jetzt
   *„Fallakte nicht lesbar: …"* — **eine Fehlermeldung statt einer Lüge.**
   Ein fehlender `cases`-Eintrag liefert weiterhin `None` — das ist eine
   **echte Aussage** (der Fall ist noch nicht aufgenommen), kein Fehlschlag.

Testbelege: **UE01** (Gegenprobe: Tabelle existiert nicht), **UE02** (Join
liefert die Zuweisung), **UE03** (Fehler wird gemeldet, nicht verschluckt).

---

## 2. Architektur — warum eigene Endpunkte

Der Ermittler arbeitet am **forensischen Webserver** (127.0.0.2), nicht am
Cockpit. `/api/results/assess` (Build 387) ist dort nicht erreichbar: anderer
Server, anderer Port, anderes Token.

**Nötig ist das auch nicht:** `DatabaseBundle` hängt `coordinator.db` bereits
**READ-WRITE** ein, und `ResolvedContext.investigator_id` trägt die **`person.id`
des angemeldeten Ermittlers** — genau den `actor_id`, den der Beleg braucht.

Der forensische Server bekommt daher **eigene Endpunkte**, die aber **dieselben
Klassen** benutzen (`ResultsRepo`, `AssessmentCatalogRepo`, `CoordinatorWriter`,
`AuditLog`, `RbacResolver`). **Es wird keine Logik dupliziert** — zwei
Implementierungen derselben Bewertungsregeln wären die sicherste Art, sie
auseinanderlaufen zu lassen.

```
GET  /_forensic/results         -> Katalog + Stand + Historie + Kennzahl
POST /_forensic/results/assess  -> eine Bewertung (APPEND-ONLY)
```

---

## 3. Die drei Festlegungen, die die Kapselung tragen

### 3.1 Die `user_id` kommt **nicht aus dem Body**

Sie kommt aus dem `ResolvedContext` — dem Fall, den dieser Server **überhaupt
geöffnet** hat. Ein Bewerten **fremder Fälle ist damit strukturell unmöglich**,
nicht bloß durch eine Prüfung verhindert. Ein `user_id` im Rumpf wird
**ausdrücklich ignoriert und protokolliert** (es könnte ein Versuch sein).

> Testbeleg **UE07**: POST mit `user_id: 19` bei geöffnetem Fall 18 → geschrieben
> wird auf **18**, auf 19 **nichts**.

### 3.2 Eigene Verbindung für den Schreibpfad

**Nicht** die ATTACH-Verbindung des Bundles. `CoordinatorWriter` braucht
`BEGIN IMMEDIATE` und volle Kontrolle über die Transaktion; auf einer geteilten
Verbindung wäre das der bekannte **Win32-Mutex-Deadlock** (Produktionsbefund).
Verbindung pro Anfrage, `mode=ro` beim Lesen.

### 3.3 Rechte werden **auch hier** geprüft

`RbacResolver` über `context.investigator_id`. Fehlt der Grant → **403 mit
Begründung**, die die Oberfläche **anzeigt**. Der Ermittler soll wissen, **warum**
er nichts sieht — eine leere Karte wäre wieder ein stiller Fehlschlag.
**Ohne auflösbaren Ermittler wird nicht geschrieben:** ein Beleg ohne Handelnden
ist kein Beleg (**UE09**).

---

## 4. Die Maske (`mc`: Tabelle)

**Eine Zeile je Kriterium**, Spalten `schwerste` / `beste`. 10 × 2 wären als
offenes Formular **20 Eingabeblöcke auf einmal** — unbedienbar. Stattdessen:
Überblick in der Tabelle, die Bearbeitung öffnet **ein Feld unter der Zeile**.
Es ist **immer nur eine** Bewertung offen.

| Detail | Grund |
|---|---|
| Knopf heißt **„Erfassen (neuer Stand)"**, nicht „Speichern" | Jede Erfassung ist eine **neue Zeile**. Wer glaubt, er korrigiere einen Wert, versteht das System falsch — er **ergänzt** einen Stand. |
| **„nicht bewertet"** statt leerer Zelle | Die Lücke ist ein **Befund**, kein Nichts. |
| **Historie** aufklappbar je Zelle | Der Erkenntnisgewinn ist **selbst ein Ermittlungsergebnis**. Mit Katalogversion und Beleg-Nr. |
| **Semantik-Warnung** am Qualitätsfeld | `ordinal` misst bei `abuser` **Schwere**, bei `location` **Präzision**. Ohne den Hinweis vermischt jemand die Zahlen. |
| **Kein** Qualitätsfeld ohne Skala | Statt eines leeren Feldes, das nichts täte und das der Server mit 400 abwiese. |
| **Vermerk** zur Kennzahl **nicht wegklickbar** | Die Zahl ist provisorisch und unabgestimmt. Ohne den Satz wäre sie eine unbelegte Behauptung. |
| **Zweistufig** + Neuladen | Kein optimistisches UI. |

**Beim Bauen gefunden (Test UR09):** `openEditor()` bekam die Ankerzeile
übergeben. Nach `closeEditor()` konnte das gemerkte Element bereits **aus dem DOM
entfernt** sein (es war die alte Editor-Zeile) — der neue Editor hätte an einem
elternlosen Knoten gehangen und wäre **still nicht erschienen**. `openEditor()`
löst die Zeile jetzt **selbst** auf.

---

## 5. Umfang (geliefert)

| | |
|---|---|
| **NEU** | `forensic_api/results_endpoint.py` |
| **NEU** | `userinfo/userinfo_results.js` (IIFE + UMD, `window.AIWUserinfoResults`) |
| geändert | `forensic_api/userinfo_data.py` — **Bugfix §1** |
| geändert | `forensic_api/__init__.py` (Dispatch), `forensic_api/static.py` (Auslieferung), `forensic_api/userinfo.py` (Karte, **`git add -f`**) |
| geändert | `userinfo/userinfo.js` (Laden + Fehleranzeige), `userinfo/userinfo.css` (scoped `.uir-*`) |
| **NEU** | `tests/test_userinfo_results.py` (UE01–UE09) · `tests/unit/test_userinfo_results.test.js` (UR01–UR12) |

---

## 6. Regression (run_tests.py)

```
pytest : 1052 passed (1043 + 9), 59 skipped, 6 subtests
vitest : 617 passed (605 + 12), 53 Testdateien
```

---

## 7. Abnahme

**Forensischen Server neu starten.** Grants aus 387 müssen vergeben sein.

1. Nutzerinfo-Tab öffnen → Karte **„Ermittlungsergebnis · Bewertung"**:
   10 Zeilen, zwei Spalten, Katalogversion sichtbar.
2. **Bugfix-Probe:** Karte „Ermittlungskoordination" zeigt jetzt den **echten
   Zuweisungswert** (vorher immer „nicht zugewiesen").
3. Ein Kriterium bewerten → Bestätigung → Rückmeldung **mit Beleg-Nr.**
4. **Dasselbe Kriterium erneut** bewerten → der Wert ändert sich, und der
   **Verlauf** zeigt **beide** Stände.
5. `abuser` bearbeiten → **Semantik-Warnung** unter dem Qualitätsfeld;
   `cp_possession` → **kein** Qualitätsfeld.
6. **Kapselungsprobe:** in DevTools
   `fetch('/_forensic/results/assess',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:<FREMDER FALL>,criterion_code:'abuser',extrem:'beste',confidence_code:'verdacht'})})`
   → geschrieben wird auf den **eigenen** Fall; im Log steht die Warnung.
7. Grant `results.edit` entziehen → keine Knöpfe, **mit Begründung**.
8. DEV-Log: `window.AIW_UI_DEBUG = true`.

---

## 8. Nächster Build

**391** — Cockpit-Auswertung (`/api/results/stats`): Verteilungen je Kriterium,
Filter, Abdeckung, blinde Flecken. **Mittelwerte je Kriterium, nie darüber
hinweg** (M011 §D).

---

*Dokument-Ende · Bauplan Build 390 · 2026-07-12*
