# Bauplan A1 — Globaler Alias-Katalog (AP-2A, Idee 8)

**Version:** 0.1 · **Datum:** 2026-07-24 · **Modul:** `aiw_webserver`
**Basis:** HEAD `5541fa0` (v0.8.503) · **Buildnummern:** 504 (Backend) + 505 (Frontend)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Auftrag:** mc 2026-07-24 („Arbeiten wir also AP-2A bitte zunächst vollständig ab")

---

## 1. Einordnung und belegte Reconciliation

Idee 8 verlangt einen **globalen Alias-Editor/-Katalog**: „Alias für andere
Forennutzer" — also die Erkenntnis *„Konto X tritt außerdem unter dem Namen Y
auf"*, fallübergreifend gepflegt.

**Belegter Ist-Stand (kein Duplizieren, Grundregel 1):**

| Fundstelle | Was es ist | Warum es Idee 8 NICHT erfüllt |
|---|---|---|
| `forensic_api/aliases.py` | Endpunkt `/_forensic/aliases` — **Ermittler-Suchbegriffe** („Panther") je Fall, in der `evidence_<uid>.db` | Fallbezogen, kein Katalog über Forennutzer, keine Herkunft, kein Audit im coordinator-Sinn |
| `management_app.py` Z. 628, 1732 | Legacy-**Routen**aliase (`/api/templates/queries`) | Namensgleichheit, fachlich unbeteiligt |
| `management/crossref/__init__.py` Z. 11 | Ausblick-Kommentar „Alias-Katalog … spätere Builds" | Bestätigt die Lücke ausdrücklich |
| `user_resolver.py` (Prepper) | löst Aliasnamen zu `user_id` auf | Ableitung aus den Forendaten, **keine Ermittlererkenntnis** |

→ Der globale Alias-Katalog fehlt. Er wird **neu** gebaut, setzt aber
schlüsselseitig auf `subject_id` (Prepper-Schema, M019) auf — genau wie
`identified_subject`.

**Abgrenzung zu `identified_subject` (M018):** dort steht *„Konto → **reale
Person**"* (eine Zeile je Konto, PII). Hier steht *„Konto → **weiterer
Forenname/Handle**"* (n Zeilen je Konto, Forenwelt). Zwei getrennte Erkenntnis-
arten; eine Vermischung hätte die Konfidenz-Achse verwässert.

---

## 2. Build 504 — Backend

### 2.1 Migration M022 `m022_subject_alias.py`

```sql
CREATE TABLE IF NOT EXISTS subject_alias (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id        INTEGER NOT NULL,          -- Forenkonto (Prepper-Schema)
    alias             TEXT    NOT NULL,          -- der weitere Name/Handle
    alias_norm        TEXT    NOT NULL,          -- casefold(alias), Dedup-Schlüssel
    kind_code         TEXT    NOT NULL
                      CHECK(kind_code IN
                            ('forenname','handle','signatur','kontakt','sonstiges')),
    basis             TEXT    NOT NULL DEFAULT '',   -- Fundgrundlage (SENSIBEL)
    note              TEXT,                          -- freie Notiz (SENSIBEL)
    is_active         INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
    retracted_reason  TEXT,
    created_by        INTEGER REFERENCES person(id),
    updated_by        INTEGER REFERENCES person(id),
    created_at        INTEGER NOT NULL,
    updated_at        INTEGER NOT NULL,
    audit_seq         INTEGER NOT NULL REFERENCES audit_log(seq),
    created_audit_seq INTEGER NOT NULL REFERENCES audit_log(seq)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_subject_alias_active
    ON subject_alias (subject_id, alias_norm) WHERE is_active = 1;
CREATE INDEX IF NOT EXISTS ix_subject_alias_norm ON subject_alias (alias_norm);
CREATE INDEX IF NOT EXISTS ix_subject_alias_subject ON subject_alias (subject_id);
```

**Forensische Festlegungen:**

1. **`alias_norm` = `str.casefold()`** — die Kollations-Leitlinie des Falls
   („alles an `users.username`, utf8mb4_unicode_**ci**, ausrichten"; Beleg:
   `Wiedervorlage_offene_Punkte.md`, Entscheidung mc 2026-07-20). SQLite kennt
   kein Unicode-`NOCASE`; deshalb wird die Normalform **im Repo in Python**
   gebildet und **gespeichert**, statt sich auf eine Collation zu verlassen, die
   bei Nicht-ASCII stillschweigend versagte. Das Forum ist multilingual
   (Fall-Erkenntnis 2) — bei ASCII-`NOCASE` wären „Ярослав"/„ЯРОСЛАВ" zwei
   Einträge geworden. **`alias` bleibt im Original erhalten** (Beweismittel).
2. **Partieller UNIQUE-Index** statt harter UNIQUE-Spalte: derselbe Alias darf
   nach einem Widerruf erneut vergeben werden — die widerrufene Zeile bleibt als
   Beleg stehen. **Es wird nie gelöscht.**
3. **`kind_code` mit CHECK** (geschlossene Menge, Linie M010/M015/M016/M018):
   ein Tippfehler ließe eine Zeile aus jedem Filter fallen (stiller Verlust).
4. **Kein FK auf `cases`** — identisch begründet wie M018: der Katalog ist global
   und erfasst auch Geisternutzer ohne Fallpaket (> 550k Namen).
5. **Keine neue Fähigkeit.** `crossref.view`/`crossref.edit` werden
   wiederverwendet (gleiche F5-Familie; Entscheidungslinie Build 474 §3). Damit
   ist M022 eine **reine Tabellen-Migration ohne RBAC-Seed** — der Fähigkeits-
   katalog bleibt bei 33.

### 2.2 `management/crossref/subject_alias_repo.py`

`SubjectAliasRepo` (eine Klasse, eigene Datei — Grundregel 10):

| Methode | Art | Verhalten |
|---|---|---|
| `list(subject_id=None, include_retracted=False)` | lesend | Aliasse, aktive zuerst, dann `alias_norm` |
| `search(term)` | lesend | Rückwärtssuche „welche Konten führen diesen Namen?" über `alias_norm` |
| `counts()` | lesend | `total` / `aktiv` / `widerrufen` / `subjects` |
| `add(...)` | **auditiert** | legt an; Duplikat (aktiv, gleiche Normform) → `CrossrefError` |
| `update(...)` | **auditiert** | `kind_code`/`basis`/`note`; No-Op → `CrossrefError` |
| `retract(alias_id, reason)` | **auditiert** | Soft-Widerruf, **Grund Pflicht**; nie DELETE |
| `reinstate(alias_id)` | **auditiert** | Widerruf zurücknehmen (Irrtum), Kollisionsprüfung in der Transaktion |

- Schreiben ausschließlich über `CoordinatorWriter.audited_write` mit
  `after_audit`-Hook für den `audit_seq`-Backfill (Muster
  `IdentifiedSubjectRepo`).
- **Sensibilitätsregel:** `alias`, `basis`, `note` gehen **nie** als Klartext ins
  Audit-Payload — dort stehen `subject_id`, `kind_code`, `alias_len`,
  `basis_len`, `note_len`. Begründung wie M018: der Beleg bleibt prüfbar, ohne
  den sensiblen Inhalt zu spiegeln.
  *Anmerkung zur Abnahme:* ein Forenname ist schwächere PII als ein Klarname —
  ich behandle ihn trotzdem gleich streng, weil ein Alias eine reale Person
  identifizierbar machen **kann**. Wenn du den Alias im Klartext im Beleg
  wünschst, ist das eine Ein-Zeilen-Änderung.
- Alle Kollisionsprüfungen laufen **innerhalb** der Transaktion
  (`BEGIN IMMEDIATE`) — kein TOCTOU-Fenster.

### 2.3 Neue Ereignistypen (`audit/event_types.py`)

`SUBJECT_ALIAS_ADDED`, `SUBJECT_ALIAS_UPDATED`, `SUBJECT_ALIAS_RETRACTED`,
`SUBJECT_ALIAS_REINSTATED` — additiv, inkl. Aufnahme in die Registrierungsliste.

### 2.4 Endpunkte (`server/management_app.py`)

| Route | Recht | Zweck |
|---|---|---|
| `GET /api/alias` (`?subject_id=N`, `?q=Suchbegriff`, `?include_retracted=1`) | `crossref.view` | Katalog / Rückwärtssuche |
| `POST /api/alias/add` | `crossref.edit` | anlegen |
| `POST /api/alias/update` | `crossref.edit` | Art/Basis/Notiz ändern |
| `POST /api/alias/retract` | `crossref.edit` | widerrufen (Grund Pflicht) |
| `POST /api/alias/reinstate` | `crossref.edit` | Widerruf zurücknehmen |

Fehlerbilder: `CrossrefError` → 400, unbekannt → 500, fehlendes Recht → 403.

### 2.5 Tests Build 504

`tests/test_subject_alias_repo.py` (**AL01–AL10**) und
`tests/test_alias_api.py` (**AA01–AA07**):

- AL01 anlegen + lesen; AL02 `alias_norm` case-insensitiv **mit Nicht-ASCII**
  (kyrillisch/griechisch/Umlaut) — der Kern der ci-Leitlinie;
  AL03 Duplikat aktiv → Fehler; AL04 Widerruf ist soft (Zeile bleibt, Grund
  gespeichert); AL05 Widerruf ohne Grund → Fehler; AL06 nach Widerruf ist die
  Neuvergabe erlaubt; AL07 `reinstate` kollidiert mit aktivem Duplikat → Fehler;
  AL08 `search` findet über Normform; AL09 `counts`; AL10 **Sensibilität**:
  Klartext-Alias/Basis/Notiz nicht im rohen `audit_log`.
- AA01/AA02 RBAC-Deny GET/POST; AA03 add→list; AA04 retract→`include_retracted`;
  AA05 Validierung → 400; AA06 Rückwärtssuche `?q=`; AA07 Sensibilität auf
  Endpunktebene.

### 2.6 Anker, die additiv nachzuziehen sind

- `tests/test_management_dashboard.py` D01: Migrationsliste `…21` → `…22`.
- Fähigkeitszahl **33 bleibt** (kein Seed) → `test_management_rbac_schema.py`
  und `test_demo_seed.py` **unverändert**.

---

## 3. Build 505 — Frontend

### 3.1 Entwurfsentscheidung (zur Abnahme): eigene Sicht statt Anbau

Der Arbeitspaket-Plan nennt „Alias- + Personen-Katalog Cockpit-Sicht". Die
Personen-Sicht (`crossref`) existiert seit Build 471. Ich baue den Alias-Katalog
als **eigene Sicht `alias`** (Gruppe „Auswertung", Label „Aliasse"), weil:

1. Aliasse existieren **unabhängig** vom Identitätskatalog — ein Konto kann fünf
   Aliasse und **keine** Identifizierung haben. Ein Anbau an die Kreuzbezug-
   Tabelle hätte diese Fälle unsichtbar gemacht (Grundregel 1).
2. Grundregel 10 (Modularität): eine Klasse/ein Belang je Datei.
3. Die Rückwärtssuche („welches Konto führt diesen Namen?") ist eine eigene
   Arbeitsweise mit eigener Eingabemaske.

Beide Sichten teilen sich das Recht `crossref.view`/`crossref.edit`, stehen
nebeneinander in derselben Nav-Gruppe und verlinken sich gegenseitig über die
`subject_id`.

### 3.2 `management/server/static/cockpit_alias.js`

Muster `cockpit_crossref.js`: IIFE + `'use strict'`, DEV-Logging über
`AIW_COCKPIT_DEBUG`, ausführliche Kommentare, **reine Helfer ohne DOM**
(vitest-prüfbar), UMD-Ausgang `window.AIWCockpitAlias`, alle variablen Texte via
`textContent` (XSS).

Aufbau der Sicht: Kopfzeile mit `counts` · Suchfeld (Konto **oder** Name) ·
Anlage-Formular (nur `crossref.edit`) · Tabelle mit Art-Badge, Basis, Status,
Aktionen „Widerrufen" (Grund-Eingabe) / „Zurücknehmen" · Umschalter „Widerrufene
zeigen". **Kein optimistisches UI** — nach jedem Schreiben lädt `cockpit.js` neu.

### 3.3 Geändert

- `cockpit.js`: `VIEW_CATALOG`-Eintrag `alias`, `loadAlias()`, View-Dispatch,
  SSE-Reload (Alias-Änderungen laufen über den coordinator-`audit_log`, der
  SSE-Strom feuert also korrekt — anders als bei `crossfindings`, Build 478 §3).
- `cockpit.html` (Skript-Tag; **`git add -f`** wegen `*.html`-gitignore),
  `cockpit.css` (scoped `.aiw-alias-*`).
- `tests/unit/test_cockpit_nav.test.js`: Katalog-Länge **30 → 31** + `CN-ALIAS`.

### 3.4 Tests Build 505

`tests/unit/test_cockpit_alias.test.js` (**AS01–AS08**) gegen den **echten**
Code (JSDOM/UMD, keine Logik-Duplikation): Normalisierungs-Helfer, Payload-Bau,
Rendern mit/ohne `canEdit`, Widerruf verlangt Grund im UI, Badge-Klassen,
XSS-Probe mit `<script>`-haltigem Alias, Leerbefund-Text, Rückwärtssuche.

---

## 4. Migrationsklasse und Produktivbetrieb

M022 ist **additiv**, betrifft **ausschließlich `coordinator.db`** und legt eine
**neue** Tabelle an. Ermittler-Ergebnisdaten (`evidence_/forensic_/assets_<uid>.db`)
sind **nicht** berührt — der Migrationsvorbehalt seit 01.07.2026 greift nicht.
Rückbau wäre ein reines `DROP TABLE`; da nichts Bestehendes verändert wird, ist
kein Datenverlust möglich.

## 5. Verifikation je Build

`ast.parse` (bzw. `node --check`) über alle geänderten Dateien · volle Python-
und vitest-Regression grün · `build.json`-Bump · ZIP mit `aiw_webserver/`-Präfix
+ `MD5SUMS_BuildNNN.txt`.

## 6. MD5-Handshake (Stand HEAD `5541fa0`)

Die Prüfsummen der zu ändernden Bestandsdateien liegen der Lieferung als
`MD5SUMS_Build504.txt` bei; bei Abweichung gegen deine VM bitte melden, **bevor**
du einspielst.

---
*Dokument-Ende · Bauplan A1 · v0.1 · 2026-07-24*
