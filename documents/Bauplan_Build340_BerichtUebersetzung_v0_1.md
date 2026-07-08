# Bauplan — Bericht-Übersetzungsbehandlung (Builds 340 & 341)

**Version:** v0.1
**Baustellen:** B3 (Toolbar-Erfassung) · B6 (Bericht/Editor) · templates.db
**Status:** Entwurf — wartet auf `mc`

---

## 1. Ziel

Erkenntnisse (Annotationen), die auf einer **KI-Übersetzung** beruhen (Tag
`#KI-Übersetzung`, bzw. `selection.target === "translation"`), sollen im Bericht
klar, leserfreundlich und rechtssicher behandelt werden — **ohne** die
Ermittelnden zu bevormunden:

- **ein** konsolidierter, **editierbarer** Rechts-Baustein (§ 187 GVG) je Bericht,
- ein **Badge als Fußnotenverweis** an jedem betroffenen Block, der auf diesen
  Baustein zeigt,
- **sanfte Ein-Klick-Automatik**: Wird ein `#KI-Übersetzung`-Fund eingefügt und
  der Baustein fehlt noch, wird sein Einfügen angeboten (nicht erzwungen),
- **Provenienz** (Modell + Datum der Übersetzung) und **Verweis auf den ganzen
  Original-Post** am Fund.

## 2. Festgelegte Entscheidungen

1. Provenienz wird **eingefroren** (robuste Methode, auf Wunsch): Modell + Datum
   werden **beim Markieren** in den Anker geschrieben. Grund: eine spätere
   Neu-Übersetzung darf die im Bericht dokumentierte Provenienz nicht rückwirkend
   verändern.
2. Badge/Fußnote analog zum bestehenden `block-comment-badge`-Muster.
3. Der Rechts-Baustein erhält eine **stabile Kennung** (`module_key`), damit er
   auch bei Reorganisation/neuen Einträgen der templates.db eindeutig auffindbar
   bleibt — **nicht** über die AUTOINCREMENT-`id`.

## 3. Belegte Datenquellen (per `post_id`)

`translations.db` (Alias **`trdb`**, seit Build 329 read-only angebunden):

| Feld | Tabelle.Spalte | Zweck |
|---|---|---|
| Original-Text (bereinigt) | `posts_cleaned.clean_text` | Zitat des ganzen Original-Posts |
| Ausgangssprache | `posts_cleaned.source_lang` | z. B. „englisch" |
| Übersetzungs-Modell | `translations.model_used` | Provenienz |
| Übersetzungs-Datum | `translations.created_at` | Provenienz |

`/translate` liefert `model_used` und `created_at` bereits mit (Beleg:
`forensic_api/translate.py`, Response-Objekt). Der Original-Text ist **stabil**
(ändert sich auch bei Neu-Übersetzung nicht) → **live** aus trdb.
Modell/Datum sind **veränderlich** → **eingefroren** im Anker.

Die Annotation trägt seit Build 336 die `post_id` (Spalte) — damit ist die
trdb-Anreicherung ohne Umweg möglich.

---

## 4. Build 340 — Provenienz einfrieren (Toolbar, klein)

**Zweck:** Neue Übersetzungs-Marken tragen Modell + Datum der zum
Markierungszeitpunkt angezeigten Übersetzung.

**Änderungen (`toolbar/toolbar.js`):**

1. `_renderPanel(container, postId, data, btn)`: Panel bekommt zwei Datenfelder
   aus der `/translate`-Antwort:
   `panel.dataset.model = data.model_used || ""`,
   `panel.dataset.created = data.created_at || ""`.
   (Die Disclaimer-Zeile zeigt Modell/Datum ohnehin schon — jetzt zusätzlich als
   maschinenlesbare Attribute.)
2. `selectionFromBrowser(sel)`: Im `target === "translation"`-Zweig zusätzlich
   ```
   model:   panel ? (panel.getAttribute("data-model")   || null) : null,
   created: panel ? (panel.getAttribute("data-created") || null) : null,
   ```
   in den Anker aufnehmen (Felder **optional**).

**Server:** `forensic_api/annotate.py` — die Pflichtfeldmenge
`translation_fields = {postId, charStart, charEnd, textLen, textHash}` bleibt
**unverändert**. `model`/`created` sind Zusatzfelder und werden durch
`json.dumps(selection_raw)` automatisch mitgespeichert. **Kein Server-Change.**

**Fallback (im Bericht, Build 341):** Fehlen `model`/`created` am Anker
(Alt-Marken), liest der Bericht sie live aus `trdb.translations` per `post_id`
und kennzeichnet sie als „aktueller Stand" statt „zum Markierungszeitpunkt".

**Tests:** vitest — `selectionFromBrowser` schreibt `model`/`created`, wenn das
Panel die Attribute trägt; fehlen sie, bleibt der Anker gültig (Felder optional).

**Regression + ZIP** wie üblich.

---

## 5. Build 341 — Bericht-Teil (B6 + templates.db)

### 5.1 templates.db — stabiler Rechts-Baustein

**Migration (kontrolliert; templates.db enthält keine Ermittler-Ergebnisse):**

```sql
ALTER TABLE report_modules ADD COLUMN module_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ux_report_modules_key
  ON report_modules(module_key) WHERE module_key IS NOT NULL;
```
(SQLite erlaubt kein `ADD COLUMN ... UNIQUE`; daher partieller UNIQUE-Index, der
mehrere `NULL` bei Bestandszeilen zulässt.)

**Seed (fixe Kennung):**
- `module_key = 'legal.ki_uebersetzung'`
- `role = 'legal'`, `topic = 'KI-Übersetzung'`, `is_active = 1`
- `title = 'Rechtshinweis maschinelle Übersetzung (§ 187 GVG)'`
- `body =` (Wortlaut Alex):
  > Die beigefügte Übersetzung wurde maschinell erstellt und dient ausschließlich
  > der ersten internen Erschließung des fremdsprachigen Dokuments. Sie stellt
  > keine verbindliche Übersetzung im Sinne des § 187 GVG dar. Für eine spätere
  > Verwertung als Beweismittel ist eine beglaubigte Übersetzung durch einen
  > vereidigten Gerichtsdolmetscher einzuholen. Die maschinelle Übersetzung wird
  > der Akte lediglich zu Informationszwecken beigefügt.

Auslieferung als **idempotentes** Seed-Skript (`INSERT ... WHERE NOT EXISTS`
gegen `module_key`), damit erneutes Ausführen keine Dublette erzeugt.

**Backend:** Modul-Lookup zusätzlich per `module_key` (nicht nur `id`) —
die Auto-Automatik referenziert `legal.ki_uebersetzung` stabil.

### 5.2 EvidenceBlock-Anreicherung für `#KI-Übersetzung`-Funde

Beim Rendern eines EvidenceBlocks, dessen Annotation den Tag `#KI-Übersetzung`
trägt (bzw. `selection.target === "translation"`):

- **Provenienz-Zeile:** „Maschinelle Übersetzung · Modell {model} · {created}".
  Quelle: eingefrorene Ankerfelder; Fallback live aus `trdb.translations`.
- **Original-Zitat:** ganzer Original-Post aus `trdb.posts_cleaned.clean_text`
  (per `post_id`), mit Sprachangabe aus `source_lang`. Als eigener, klar
  abgesetzter Zitatblock („Original ({source_lang})").
- **Badge/Fußnote:** `block-translation-badge` (analog `block-comment-badge`,
  als erstes Kind der `.ce-block`), Klick springt zum Rechts-Baustein.

Datenweg: neuer Platzhalter/Endpunkt-Zweig, der per `post_id` die
trdb-Felder liefert (read-only). Wiederverwendung der bestehenden
`/_forensic/placeholders/*`-Mechanik, sofern sie `post_id`-Parameter erlaubt;
sonst kleiner dedizierter GET-Endpunkt `/_forensic/translation_meta?post_id=`
(read-only, nur trdb).

### 5.3 Sanfte Ein-Klick-Automatik

Wird ein `#KI-Übersetzung`-Fund in den Bericht eingefügt und der Baustein
`legal.ki_uebersetzung` ist noch **nicht** enthalten:
- unaufdringlicher Hinweis mit **einem** Button „Rechtshinweis einfügen",
- Klick fügt den `legal`-Baustein **einmal** ein (danach editier-/löschbar),
- kein erneuter Hinweis, solange der Baustein vorhanden ist,
- **keine** Blockade, **kein** Pflichtfeld.

### 5.4 Export

DOCX/PDF-Export muss Badge-Verweis, Provenienz-Zeile, Original-Zitat und den
`legal`-Baustein mittragen. Prüfen, dass der Export die neuen Block-/Badge-
Strukturen nicht verschluckt.

### 5.5 Tests

- Python: Migration idempotent; Seed setzt `module_key`; Lookup per `module_key`;
  trdb-Meta-Lieferung per `post_id` (Original-Text + source_lang + Provenienz).
- vitest: Badge wird bei `#KI-Übersetzung`-Block gesetzt/nicht gesetzt;
  Auto-Automatik schlägt nur vor, wenn Baustein fehlt (reine Vorbedingungs-Logik).

---

## 6. Offene Annahmen (vor Umsetzung zu bestätigen)

1. **Original-Zitat = `clean_text`** (bereinigter Original-Text) ist als
   Zitatquelle akzeptabel. Alternative wäre der rohe Seiten-BLOB (aufwändiger);
   `clean_text` ist genau der Text, der übersetzt wurde.
2. Der `/_forensic/placeholders/*`-Mechanismus erlaubt einen `post_id`-Parameter;
   falls nicht, kommt der kleine read-only Zusatzendpunkt (5.2).

## 7. Reihenfolge & Workflow

1. **Build 340** (Toolbar-Provenienz) → `mc` → implementieren → Regression → ZIP.
2. **Build 341** (templates.db-Migration + B6) → `mc` → implementieren →
   Regression → ZIP. Migration mit verifiziertem Backup der templates.db vor
   Ausbringung (Vier-Augen: Seed einmalig geprüft, maschinell idempotent).

**Grundregeln:** kein Beleg still übersprungen; jede Version lauffähig/getestet;
`build.json` je Build; MD5 je Datei; nur syntaxgeprüfter Code.
