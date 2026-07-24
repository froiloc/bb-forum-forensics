# Bauplan A3 — Identitäts-Merge/Split (AP-2A, Idee 11)

**Version:** 0.1 · **Datum:** 2026-07-24 · **Modul:** `aiw_webserver`
**Basis:** nach Build 508 · **Buildnummern:** 509 (Backend) + 510 (Frontend)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Auftrag:** mc 2026-07-24 · offener Punkt aus Bauplan Build 474 §5 / 478 §5

---

## 1. Fachlicher Kern

Idee 11 verlangt **umkehrbares, auditiertes Zusammenführen und Trennen von
Identitäten**. Der Ermittlungsfall dahinter ist der Kern des Projektziels:

> Konto 4711 und Konto 90210 werden von **derselben natürlichen Person**
> betrieben (Zweitkonto, Wiederanmeldung nach Sperre, Geist + Realkonto).

**Warum das umkehrbar sein muss:** Die Zusammenführung ist eine **Hypothese**,
keine Tatsache. Sie stützt sich auf Indizien (Schreibstil, IP, Zeitmuster,
Alias-Überschneidung). Erweist sie sich als falsch, muss die Trennung **so
belegt** sein wie die Zusammenführung — und beide Konten müssen danach wieder
für sich stehen, ohne dass eine Erkenntnis verloren geht.

---

## 2. Build 509 — Backend

### 2.1 Datenmodell — Entwurfsentscheidungen zur Abnahme

**(E1) Flache Zweiebenen-Struktur statt Baum/Graph.** Eine Zusammenführung
verbindet ein **Primär-Konto** mit einem **eingegliederten** Konto. Ketten
(A→B, B→C) sind **verboten**: Wer C zu B legen will, während B schon zu A gehört,
bekommt einen sprechenden Fehler und den Hinweis, C direkt zu A zu legen.

*Begründung:* Ketten machen die Umkehrung mehrdeutig — löst man B→A auf, wohin
gehört dann C? Ein Werkzeug, das diese Frage nicht eindeutig beantworten kann,
erzeugt in einem Strafverfahren angreifbare Aussagen. Die flache Struktur ist
eindeutig, in einem Blick prüfbar und deckt den realen Bedarf („n Konten, eine
Person") vollständig ab.

**(E2) Trennung ist ein Soft-Widerruf, kein DELETE.** Die Zeile bleibt, mit
`is_active=0`, Trennungsgrund, Zeitpunkt und eigenem Beleg. Die Historie
„wir hielten das mal für dieselbe Person, und hier steht warum wir es nicht mehr
tun" ist selbst ein Ermittlungsergebnis.

**(E3) Kein Zusammenführen mit sich selbst**, und ein Konto ist **zu einer Zeit
höchstens einmal** eingegliedert (partieller UNIQUE-Index). Beide Regeln werden
**in der Transaktion** geprüft.

### 2.2 Migration M025 `m025_subject_merge.py`

```sql
CREATE TABLE IF NOT EXISTS subject_merge (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    primary_subject_id INTEGER NOT NULL,   -- führendes Konto
    merged_subject_id  INTEGER NOT NULL,   -- eingegliedertes Konto
    basis              TEXT    NOT NULL,   -- Indizien der Zusammenführung (SENSIBEL)
    confidence_code    TEXT    NOT NULL
                       CHECK(confidence_code IN
                             ('verdacht','wahrscheinlich','gesichert')),
    confidence_ordinal INTEGER NOT NULL,   -- eingefroren 10/20/30
    is_active          INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
    split_reason       TEXT,               -- Grund der Trennung (SENSIBEL)
    merged_by          INTEGER REFERENCES person(id),
    split_by           INTEGER REFERENCES person(id),
    created_at         INTEGER NOT NULL,
    updated_at         INTEGER NOT NULL,
    split_at           INTEGER,
    audit_seq          INTEGER NOT NULL REFERENCES audit_log(seq),
    created_audit_seq  INTEGER NOT NULL REFERENCES audit_log(seq),
    CHECK(primary_subject_id <> merged_subject_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_subject_merge_active
    ON subject_merge (merged_subject_id) WHERE is_active = 1;
CREATE INDEX IF NOT EXISTS ix_subject_merge_primary
    ON subject_merge (primary_subject_id);
```

- **Konfidenz-Achse wiederverwendet** (`verdacht`/`wahrscheinlich`/`gesichert`,
  Ordinal 10/20/30, eingefroren) — dieselbe Skala wie `identified_subject`
  (M018). Eine Zusammenführung ist genauso eine Erkenntnis mit Reifegrad wie eine
  Identifizierung; zwei verschiedene Skalen wären eine Fehlerquelle.
- **`CHECK(primary <> merged)`** auf DDL-Ebene: Selbstverschmelzung ist auch bei
  einem Programmierfehler unmöglich.
- **Keine neue Fähigkeit** — `crossref.view` / `crossref.edit`.

### 2.3 `management/crossref/subject_merge_repo.py`

`SubjectMergeRepo`:

| Methode | Art | Verhalten |
|---|---|---|
| `list(include_split=False)` | lesend | aktive Zusammenführungen, stärkste Konfidenz zuerst |
| `group_of(subject_id)` | lesend | **alle** Konten derselben Person (Primär + eingegliederte), unabhängig davon, welches Konto gefragt wurde |
| `counts()` | lesend | `aktiv` / `getrennt` / `betroffene_konten` |
| `merge(primary, merged, basis, confidence, actor)` | **auditiert** | Regeln E1/E3 prüfen → anlegen |
| `revise(merge_id, …)` | **auditiert** | Konfidenz/Basis reifen lassen; No-Op wirft |
| `split(merge_id, reason, actor)` | **auditiert** | Soft-Trennung, **Grund Pflicht** |
| `remerge(merge_id, basis, actor)` | **auditiert** | Trennung war ein Irrtum; Kollisionsprüfung in der Transaktion |

**Kettenprüfung (E1)** in `merge`, innerhalb der Transaktion:
1. `merged_subject_id` bereits aktiv eingegliedert? → Fehler mit Nennung des
   bestehenden Primärkontos.
2. `merged_subject_id` ist selbst Primär einer aktiven Zusammenführung? → Fehler
   mit dem Hinweis, die Kette aufzulösen bzw. direkt anzuhängen.
3. `primary_subject_id` ist selbst aktiv eingegliedert? → Fehler mit dem Hinweis
   auf das tatsächlich führende Konto.

Jeder dieser drei Fälle liefert eine **sprechende** Meldung samt der beteiligten
`subject_id`s — die Ermittlerin soll sofort sehen, was der Konflikt ist, statt
ein generisches „geht nicht".

**Sensibilität:** `basis` und `split_reason` sind Freitext und bleiben aus dem
Audit-Payload; dort stehen `primary_subject_id`, `merged_subject_id`,
`confidence_code`, `confidence_ordinal`, `basis_len`, `reason_len`.

**Ereignistypen (neu):** `SUBJECT_MERGED`, `SUBJECT_MERGE_REVISED`,
`SUBJECT_SPLIT`, `SUBJECT_REMERGED`.

### 2.4 Endpunkte

| Route | Recht |
|---|---|
| `GET /api/merge` (`?subject_id=N` → `group_of`, `?include_split=1`) | `crossref.view` |
| `POST /api/merge/set` — anlegen **oder** revidieren | `crossref.edit` |
| `POST /api/merge/split` — trennen (Grund Pflicht) | `crossref.edit` |
| `POST /api/merge/remerge` — Trennung zurücknehmen | `crossref.edit` |

### 2.5 Tests Build 509

`tests/test_subject_merge_repo.py` (**MG01–MG12**): anlegen + lesen; Selbstmerge
→ Fehler (Repo **und** DDL-CHECK); Doppelmerge desselben Kontos → Fehler mit
Nennung des Primärkontos; **Kette verboten** in beiden Richtungen (E1, Fälle 2
und 3); `group_of` liefert von **jedem** beteiligten Konto aus dieselbe Gruppe;
Revision lässt Konfidenz reifen und erhöht `audit_seq`; No-Op wirft; Trennung ist
soft (Zeile bleibt, Grund gespeichert); Trennung ohne Grund → Fehler; nach
Trennung ist ein neuer Merge desselben Kontos erlaubt; `remerge` kollidiert mit
aktivem Merge → Fehler; **Sensibilität** (Basis/Grund nicht im `audit_log`).

`tests/test_merge_api.py` (**MA01–MA07**): RBAC-Deny GET/POST; set→list;
`?subject_id=` → Gruppe; split→`include_split`; Validierung → 400;
Sensibilität auf Endpunktebene.

**Anker:** `tests/test_management_dashboard.py` D01 `…24` → `…25`.

---

## 3. Build 510 — Frontend

### 3.1 `management/server/static/cockpit_merge.js` (Sicht „Identitäts-Gruppen")

Eigene Sicht (Gruppe „Auswertung", Recht `crossref.view`) — begründet wie bei A1:
Zusammenführungen bestehen unabhängig davon, ob eines der Konten identifiziert
oder mit Aliassen versehen ist.

Aufbau: `counts`-Kopf · Suchfeld `subject_id` → zeigt die **ganze Gruppe** ·
Anlageformular (Primär, Eingliederung, Konfidenz, Basis) · Tabelle der aktiven
Zusammenführungen mit Konfidenz-Badge und Aktionen „Revidieren" / „Trennen"
(Grund-Pflichtfeld) · Umschalter „getrennte zeigen" mit Trennungsgrund und
„Trennung zurücknehmen".

**Konfliktmeldungen des Servers werden wörtlich angezeigt** (inkl. der genannten
`subject_id`s) — die Ermittlerin braucht den konkreten Konflikt, nicht dessen
Zusammenfassung.

Projekt-Gebote wie gehabt: IIFE + `'use strict'`, DEV-Logging, ausführliche
Kommentare, reine Helfer ohne DOM, UMD-Ausgang `window.AIWCockpitMerge`,
`textContent` (XSS), kein optimistisches UI.

### 3.2 Geändert

`cockpit.js` (Nav-Eintrag `merge`, `loadMerge()`, Dispatch, SSE-Reload — hier
korrekt, da coordinator-`audit_log`), `cockpit.html` (**`git add -f`**),
`cockpit.css` (scoped `.aiw-merge-*`).
`tests/unit/test_cockpit_nav.test.js`: **31 → 32** + `CN-MERGE`.

### 3.3 Tests Build 510

`tests/unit/test_cockpit_merge.test.js` (**MS01–MS08**): Payload-Bau; Rendern
mit/ohne `canEdit`; Gruppen-Darstellung; Trennen verlangt Grund im UI;
Konfidenz-Badges; getrennte Zeilen gedimmt inkl. Grund; Server-Konfliktmeldung
wird unverändert angezeigt; XSS-Probe.

---

## 4. Abschluss AP-2A

Mit Build 510 sind die Ideen **6, 7, 8, 9, 10, 11** vollständig umgesetzt und
AP-2A ist abgeschlossen. Ich lege dazu eine Übergabe
`claude/UEBERGABE_AP2A_Abschluss.md` in den Projektspeicher, mit der
Reconciliation Idee → Build → Beleg, den offenen Grants und dem Nachtrag der
Migrationen M022–M025 in den Datenmigrationsleitfaden.

## 5. Migrationsklasse

M025 **additiv**, neue Tabelle, nur `coordinator.db`. Ermittler-Ergebnisdaten
unberührt.

---
*Dokument-Ende · Bauplan A3 · v0.1 · 2026-07-24*
