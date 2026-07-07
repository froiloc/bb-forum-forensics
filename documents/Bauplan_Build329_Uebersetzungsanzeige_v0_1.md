# Bauplan Build 329 — Übersetzungsanzeige (Baustelle 3 + 5)

**Version:** v0.1 · Entwurf zur `mc`-Freigabe
**Basis-HEAD:** `aiw_webserver 6547955 / 0.7.328`, `aiw_sqlite_prepper babd907 / 0.1.104`
**Ziel-Build:** `aiw_webserver` Build 329
**Betroffene Baustellen:** B3 (JS-Toolbar), B5 (DB-Interfaces), B2 (Endpoints/Router)

---

## 1. Zweck und Abgrenzung

### 1.1 Zweck
Nicht-deutschsprachige Forenbeiträge werden extern (lokales `ollama`) ins Deutsche
übersetzt und in einer neuen, **global geteilten, ausschließlich lesbaren**
Datenbank `translations.db` abgelegt. Dieser Build gibt Ermittler:innen einen
unmittelbaren Zugriff auf diese Übersetzungen direkt am Post:

- pro Post mit vorliegender Übersetzung eine injizierte **Flaggen-Schaltfläche**
  neben dem (Original-)Translate-Link im `.postfoot`,
- Klick klappt ein **Inline-Panel unterhalb des Posts** aus, das die Übersetzung
  samt Provenienz-Hinweis zeigt.

### 1.2 Ausdrücklich NICHT in diesem Build (Abgrenzung)
- **Markierungen/Annotationen in Übersetzungen** — bewusst in einen separaten
  Build verschoben. Die Verankerung von Markierungen hängt von der hier erst
  festgelegten DOM-Struktur des Übersetzungs-Panels ab.
- **Schreibzugriff** auf `translations.db` (die DB wird extern befüllt).
- `confidence_markers` — die einpflegende Software trägt hier keine sinnvollen
  Daten ein; die Spalte wird ignoriert und **nicht** angezeigt.

### 1.3 Grundregel-Bezug
- **GR1 (kein Beleg still übersprungen):** Provenienz (Modell, Zeitstempel) und
  der Hinweis „maschinell übersetzt, nicht gerichtsverwertbar" laufen untrennbar
  mit der Anzeige mit.
- **GR2 (jede Version lauffähig/getestet):** Die Endpoints werden ausgeliefert,
  **bevor** die Daten vorliegen (~2 Wochen), und liefern bis dahin leere
  Ergebnisse — kein zweiter Deploy nötig.
- **GR10 (je Klasse eine Datei):** Neue DB-Klasse und je Endpoint ein Modul.

### 1.4 Migrationssicherheit
`translations.db` ist eine **neue** Datenbank und fällt **nicht** unter den
Migrationsvorbehalt (der gilt nur für `evidence_/forensic_/assets_<uid>.db`).
Global read-only, wie `templates.db`/`default.db` — Ermittler speichern dort
keine Ergebnisse, es kann kein Wissen verloren gehen. Die Änderung am
`ViewModeModule` ist reines JS (keine Daten). **Keine Schema-Änderung an
eingefrorenen DBs.**

---

## 2. Datenbank-Anbindung (Baustelle 5)

### 2.1 Muster (belegt)
Der ConnectionManager bindet globale Read-only-DBs optional per
`_attach_readonly(con, path, alias)` an — in Normal- und Support-Modus — mit
eigener `*Db`-Klasse im Bundle (Beleg: `db/connection_manager.py:13–34, 203–227`;
Vorbild `TemplatesDb`, `tdb`, NEU Build 117). `translations.db` folgt exakt diesem
Muster.

### 2.2 Neue Datei `db/translations_db.py` (GR10)
Klasse `TranslationsDb`, ausschließlich lesend, analog `db/templates_db.py`:

- Erwartet eine bereits geöffnete `sqlite3.Connection`, in der `translations.db`
  unter dem Alias **`trdb`** angebunden ist (*Alias-Name zur Bestätigung — siehe
  §7*).
- Ist `trdb` **nicht** angebunden (DB noch nicht vorhanden): alle Methoden liefern
  leere Ergebnisse und protokollieren **WARNING** — kein Absturz (GR1: kein
  stiller Fehler, aber auch kein Absturz). Exakt das `TemplatesDb`-Verhalten.
- **Spalten-Robustheit:** Vor der Topic-Abfrage prüft die Klasse per
  `PRAGMA table_info(translations)`, ob die Spalte `topic_id` existiert. Fehlt
  sie (falls die Produktionstabelle doch ohne `topic_id` geliefert wird),
  WARNING + leeres Ergebnis statt Exception.

Methoden:
```
list_translated_post_ids(topic_id: int) -> list[int]
    SELECT post_id FROM trdb.translations
    WHERE topic_id = ?
      AND status = 'completed'
      AND translated_text IS NOT NULL AND translated_text <> '';

get_translation(post_id: int) -> Optional[TranslationRecord]
    SELECT post_id, translated_text, model_used, status, created_at
    FROM trdb.translations
    WHERE post_id = ?
      AND status = 'completed'
      AND translated_text IS NOT NULL AND translated_text <> '';
```
`confidence_markers`, `processing_time_ms`, `error_message`, `batch_id`,
`worker_url` werden **nicht** gelesen.

Dataclass `TranslationRecord(post_id, translated_text, model_used, created_at)`.

### 2.3 ConnectionManager-Erweiterung
- Import `from db.translations_db import TranslationsDb`.
- Bundle-Attribut `translations: TranslationsDb`.
- Optionale Read-only-Anbindung `_attach_readonly(con, translations_path, "trdb")`
  in Normal- **und** Support-Modus, existenzgeschützt (wie `adb`/`tdb`).
- Pfad aus dem bestehenden Kontext-Objekt (`self._ctx.translations_db`, analog
  `default_db`/`assets_db`).

### 2.4 Abhängigkeit an die Produktionstabelle
Der Topic-Endpoint setzt voraus, dass die Produktions-`translations`-Tabelle die
Spalte `topic_id` trägt (von dir angekündigte Ergänzung). Die Schema-Datei
`translations_db.sql` führt `topic_id` bislang nur in `posts_cleaned` (Beleg:
`translations_db.sql:5, 31–44`). Bis zur Lieferung greift §2.2 (leer + WARNING).

---

## 3. Endpoints (Baustelle 2)

Beide unter `/_forensic/` (Router-Zwang, sonst BLOB-Fehlleitung — Beleg
`Bauplan_Baustelle2_Webserver_v0_3.md`, Router-Dispatch), je eigenes Modul (GR10),
Muster `forensic_api/status.py`/`resolve_posts.py`.

### 3.1 `forensic_api/translations.py` — `GET /_forensic/translations?topic_id=<id>`
Liefert die `post_id`s eines Topics mit vorliegender Übersetzung.

Response (200):
```json
{ "topic_id": 69192, "post_ids": [706037, 706040], "count": 2, "status": "ok" }
```
- fehlender/ungültiger `topic_id` → 400 `{ "error": "...", "status": "error" }`
- `trdb` nicht angebunden → 200 `{ "post_ids": [], "count": 0, "status": "ok" }` + WARNING

### 3.2 `forensic_api/translate.py` — `GET /_forensic/translate?post_id=<id>`
Liefert die Übersetzung eines einzelnen Posts.

Response (200, gefunden):
```json
{ "post_id": 706037, "found": true, "translated_text": "...",
  "model_used": "...", "created_at": "2026-06-..." }
```
- gefunden, aber keine Übersetzung (kein `completed`) → 200 `{ "post_id": ..., "found": false }`
- fehlender/ungültiger `post_id` → 400
- `trdb` nicht angebunden → 200 `{ "found": false }` + WARNING

„Nicht gefunden" ist **kein** Fehler (kein 404) — es ist eine normale Antwort.

### 3.3 Router-Registrierung
`forensic_api/__init__.py` dispatch() um beide Pfade erweitern (Muster der
bestehenden Registrierungen). Config-Konstanten `API_TRANSLATIONS`,
`API_TRANSLATE` analog `API_VIEWPORT`.

---

## 4. Toolbar (Baustelle 3)

Neues `TranslationModule` in `toolbar/toolbar.js`, IIFE-gekapselt, exzessives
`_dbg()`-Logging, ausführlich kommentiert (JS-Gebote 1–4).

### 4.1 Seiten-Scope
Initialisierung **nur auf `viewtopic.php`** (dort existieren Posts + `.postfoot`).
Erkennung über die aktuelle Seiten-URL (Muster: `PMSTableOrganizerModule` ist auf
`pmsnew.php` beschränkt).

### 4.2 Ablauf
1. `topic_id` aus der Seiten-URL lesen (`viewtopic.php?id=<topic_id>`; Beleg
   `forensic_api/annotate.py:13`, `viewport.py:12`). **Parallel** zum
   Seiten-Fetch — nicht auf das Post-DOM warten.
2. `GET /_forensic/translations?topic_id=` → Ergebnis als `Set<post_id>` cachen.
3. Für jeden Post-Container `#p<post_id>` (Beleg `toolbar.js:720`), dessen id im
   `Set` liegt: in `.postfootright` **eine eigene Flaggen-Schaltfläche einfügen**
   (`class="aux-part"`), direkt neben dem Original-Translate-Link. `post_id` wird
   aus dem `#p<id>`-Container gelesen; der Original-Link (`...&action=translate`,
   Original-Scrape, Beleg: kein Generator in beiden Repos) bleibt **unangetastet**.
4. Klick auf die Flagge → `GET /_forensic/translate?post_id=` → **Inline-Panel**
   unterhalb von `.postfoot` einfügen/umschalten (`class="aux-part"`). Zweiter
   Klick klappt ein (Toggle). Ergebnis wird pro Post gecacht (kein Doppel-Fetch).

### 4.3 Panel-Aufbau
- **Kopfzeile (Pflicht, GR1):** „⚠ Maschinell übersetzt · Modell `{model_used}` ·
  `{created_at}` · nicht gerichtsverwertbar" — Text aus der Endpoint-Antwort.
- **Körper:** `translated_text`, als Text gerendert (BB-Codes wurden beim
  Übersetzen entfernt → keine Formatierung zu übernehmen).
- Kein `confidence_markers`.

### 4.4 Original/Angepasst-Integration
Flaggen-Button und Panel tragen `aux-part` und verschwinden im Original-Modus
automatisch (siehe §5). Da beide AIW-eigen sind, entfällt jedes bedingte
An-/Abklemmen am Original-Link.

---

## 5. ViewModeModule + CSS (Baustelle 3)

### 5.1 `aux-part`-Konvention (neu, von dir freigegeben)
Bislang schaltet `_setOriginal()`/`_setEnhanced()` je Modul per
`clearAll()`/`restoreAll()` + `visibility:hidden` (Beleg `toolbar.js:5701–5764`).
Ergänzung:

- in `_setOriginal()`: `document.body.classList.add("aiw-view-original")`
- in `_setEnhanced()`: `document.body.classList.remove("aiw-view-original")`

### 5.2 `toolbar/toolbar.css`
```css
body.aiw-view-original .aux-part { display: none !important; }
```
Bewusst `display:none` (nicht `visibility:hidden` wie Banner/Minimap, §21.1):
injizierte Übersetzungs-Elemente sind **kein** Teil des Original-Layouts und
dürfen im Original-Modus keinen Platz belegen.

Zusätzlich: Styling für die **Flaggen-Schaltfläche** (Deutschland: drei
horizontale Bänder Schwarz-Rot-Gold, rein per CSS — **keine externe
Bilddatei** wegen Offline-VM) und für das **Panel** (dezenter Rahmen,
Warn-Kopfzeile hervorgehoben).

### 5.3 Vorbereitung späterer Nutzung (notiert)
Dieselbe `aux-part`-Konvention trägt später die rot-gelb-grünen
Bearbeitungsrahmen um Posts/Topics — sie verschwinden im Original-Modus dann
automatisch mit. (Kein Bestandteil dieses Builds.)

---

## 6. Tests (GR2, GR3)

### 6.1 Python (pytest)
- `TranslationsDb`: (a) `trdb` nicht angebunden → leer + WARNING; (b) gegen eine
  **synthetische Referenz-`translations.db`** mit `topic_id`: korrekte Liste /
  korrekter Einzeldatensatz; (c) `status != 'completed'` und leerer
  `translated_text` werden ausgeschlossen; (d) fehlende Spalte `topic_id` →
  leer + WARNING (Spalten-Robustheit §2.2).
- `translations`-Endpoint: gültige `topic_id` → Liste; fehlend/ungültig → 400;
  DB fehlt → leere Liste 200.
- `translate`-Endpoint: vorhandene `post_id` → Datensatz; ohne Übersetzung →
  `found:false`; fehlend/ungültig → 400.

### 6.2 JavaScript (vitest, jsdom)
Nach Projektkonvention wird die reine Logik im Testfile dupliziert (Toolbar ist
IIFE-gekapselt): `Set`-Membership (welche Posts bekommen einen Button),
`post_id`-Ableitung aus `#p<id>`, Panel-Toggle-Zustand. **Kein „green but dead"**
— die Tests müssen den tatsächlichen Pfad ausüben (B4-S12-Muster beachten).

### 6.3 Gate
`python run_tests.py` grün (pytest + vitest). Baseline vor Build: Python
747 passed / 59 skipped, JavaScript 423 passed (Beleg `build.json` Build 328).

---

## 7. Offene Punkte / Bestätigung nötig

1. **Alias-Name `trdb`** — Vorschlag (TRanslations DB), optisch nah an `tdb`
   (templates). Bestätigen oder Gegenvorschlag (z.B. `xdb`).

**Geparkt** (kein Entscheidungsbedarf jetzt): Re-Übersetzungs-Versionierung;
toter `action=translate`-Navigationsklick bei Posts *ohne* Übersetzung (Original-
Link bleibt, führt ins Leere); rot-gelb-grüne Rahmen via `aux-part`.

---

## 8. Liefergegenstand Build 329

Geänderte/neue Dateien (nur diese im ZIP, repo-relativ, mit MD5):

- `db/translations_db.py` (neu)
- `db/connection_manager.py` (Anbindung `trdb`)
- `forensic_api/translations.py` (neu)
- `forensic_api/translate.py` (neu)
- `forensic_api/__init__.py` (Router-Registrierung)
- `toolbar/toolbar.js` (TranslationModule + ViewModeModule-Body-Klasse)
- `toolbar/toolbar.css` (`aux-part`-Regel, Flaggen-/Panel-Styling)
- `core/*` bzw. Config (Endpoint-Konstanten)
- Tests: `tests/unit/…` (Python + vitest)
- `build.json` (Build 329 + Änderungsnotiz)

Workflow: `mc` → Implementierung → `py_compile` → `python run_tests.py` → ZIP
(`aiw_webserver_329`) + MD5 → `present_files` → du committest selbst.
