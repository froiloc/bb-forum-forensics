# Bauplan A2 — Querfund-Rückkanal (AP-2A, Idee 7)

**Version:** 0.1 · **Datum:** 2026-07-24 · **Modul:** `aiw_webserver`
**Basis:** nach Build 506 · **Buildnummern:** 507 (Backend) + 508 (Frontend)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Auftrag:** mc 2026-07-24 · offener Punkt aus Bauplan Build 474 §5 / 478 §5

---

## 1. Das Problem, das dieser Build löst

Ein **Querfund** ist die Lage: Ermittlerin A stößt im Fall A auf eine Erkenntnis
über Konto **B**, das Ermittler B bearbeitet. Der **Transport** dieser Annotation
läuft heute vollautomatisch (`forensic_api/cross_annotation_integrator.py` →
`pending_cross_annotations` → Ziel-`evidence_<uid>.db`), und Build 474/478 machen
das **sichtbar**.

**Was fehlt (Idee 7):** Der Fund erreicht die Ziel-Datenbank — aber **niemand
weiß, ob ein Mensch ihn je gesehen hat.** `integrated_at` belegt nur, dass die
*Technik* die Annotation kopiert hat. Ob Ermittler B sie zur Kenntnis genommen,
verwertet oder als irrelevant bewertet hat, ist **unbelegt**. Genau das ist ein
stilles Übergehen eines Belegs — Grundregel 1.

Dieser Build schließt die Lücke: Er legt eine **auditierte Zustandsmaschine über
den menschlichen Umgang** mit jedem Querfund. Er ändert **nichts** am Transport.

---

## 2. Build 507 — Backend

### 2.1 Zustandsmodell (`management/crossref/crossfinding_channel_status.py`)

Reine Logik, **ohne Datenbank und ohne Uhr** — vollständig in pytest prüfbar
(Muster `promotion_status.py`, `matter_status.py`, `checklist_status.py`).

```
(kein Eintrag = implizit 'offen' — der Fund liegt vor, niemand hat quittiert)
     │
     ├──(zustellen)──────────► zugestellt
     │                              │
     │   ┌──────────────────────────┘
     │   ▼
     ├──(quittieren)─────────► quittiert     (B hat den Fund GESEHEN)
     │                              │
     ├──(verwerten + BASIS)──► verwertet          ✔ endgültig
     │
     └──(nicht relevant + GRUND)──► nicht_relevant ✔ endgültig
```

| Festlegung | Begründung |
|---|---|
| `'offen'` ist ein **Pseudo-Zustand**, nie gespeichert | Die Abwesenheit einer Zeile *ist* „unbearbeitet". Deckt sich mit dem CHECK in M024 und mit `promotion_status.py`. |
| `verwertet` / `nicht_relevant` sind **endgültig** | Gleiche Linie wie MatterStatus (385), Berichts-Statusmodell (377), PromotionStatus (460). Ein Irrtum wird durch eine **neue, belegte** Erkenntnis korrigiert, nicht durch Zurückdrehen. |
| **Grund ist Pflicht** bei `nicht_relevant` | Ein stilles Wegwischen eines Querfundes ist exakt die Lücke, die dieses System schließt. |
| **Basis ist Pflicht** bei `verwertet` | „Verwertet" ist eine Tatsachenbehauptung über die Ermittlung — sie braucht ihren Beleg (wo ist die Erkenntnis eingeflossen?). |
| `zugestellt` ist **überspringbar** | Ein Ermittler, der den Fund im Cockpit direkt sieht und quittiert, soll nicht erst „zustellen" müssen. `offen → quittiert` ist erlaubt. |

### 2.2 Migration M024 `m024_crossfinding_feedback.py`

```sql
CREATE TABLE IF NOT EXISTS crossfinding_feedback (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id        INTEGER NOT NULL,   -- pending_cross_annotations.id
    subject_id        INTEGER NOT NULL,   -- Ziel-Subjekt (Redundanz mit Zweck, s.u.)
    status_code       TEXT    NOT NULL
                      CHECK(status_code IN
                            ('zugestellt','quittiert','verwertet','nicht_relevant')),
    reason            TEXT    NOT NULL DEFAULT '',  -- Grund/Basis (SENSIBEL)
    decided_by        INTEGER REFERENCES person(id),
    created_at        INTEGER NOT NULL,
    updated_at        INTEGER NOT NULL,
    audit_seq         INTEGER NOT NULL REFERENCES audit_log(seq),
    created_audit_seq INTEGER NOT NULL REFERENCES audit_log(seq),
    UNIQUE(finding_id)
);
CREATE INDEX IF NOT EXISTS ix_cff_status  ON crossfinding_feedback (status_code);
CREATE INDEX IF NOT EXISTS ix_cff_subject ON crossfinding_feedback (subject_id);
```

**Festlegungen:**

1. **Eine Zeile je Querfund** (`UNIQUE(finding_id)`) trägt den **Ist-Stand**; die
   Historie der Übergänge liegt im hash-verketteten `audit_log`. Gleiche Bauform
   wie `identified_subject` (M018) und `promotion_decision` (M015).
2. **Kein FK auf `pending_cross_annotations`** — bewusst. Begründung: die
   Zieltabelle wird zur Laufzeit von `db/coordinator_db.py` mitverwaltet (siehe
   A4); ein FK würde die Reihenfolge von Migration und Laufzeit-DDL hart koppeln
   und im Fehlerfall die produktive Querfund-Pipeline blockieren. Stattdessen
   prüft das **Repo** die Existenz des Fundes in der Transaktion und wirft
   sichtbar, wenn er fehlt — das ist die belegte, nicht die stille Variante.
3. **`subject_id` wird mitgeführt**, obwohl aus dem Fund ableitbar: die
   Rückkanal-Sicht filtert „meine Subjekte" ohne Join auf eine Tabelle, deren
   Zeilen die Pipeline parallel schreibt. Es ist eine **Kopie zum Zeitpunkt der
   Entscheidung** — forensisch der Beleg, auf welches Subjekt sich die
   Entscheidung bezog.
4. **Keine neue Fähigkeit**: `crossref.view` (sehen) / `crossref.edit`
   (entscheiden). Entscheidungslinie Build 474 §3 — keine Rechte-Inflation.

### 2.3 `management/crossref/crossfinding_channel_repo.py`

`CrossfindingChannelRepo`:

| Methode | Art | Verhalten |
|---|---|---|
| `status_of(finding_id)` | lesend | Ist-Zustand oder `'offen'` |
| `list_with_status(only_open=False)` | lesend | Querfunde **inklusive** Rückkanal-Zustand (LEFT JOIN), Handlungsbedürftiges zuerst |
| `counts()` | lesend | je Zustand inkl. `'offen'` |
| `decide(finding_id, target_status, reason, actor_id)` | **auditiert** | Übergang prüfen → schreiben → `audit_log` |

- `decide` prüft **in** der Transaktion: existiert der Fund? ist der Übergang
  erlaubt? ist Grund/Basis vorhanden? Erst dann Upsert.
- Ereignistyp `CROSSFINDING_FEEDBACK_SET` mit Payload **Fakten + Textlänge**
  (`finding_id`, `subject_id`, `von`, `nach`, `reason_len`) — der Freitext-Grund
  bleibt draußen (Sensibilitätsregel wie M018/A1).
- `audit_seq`-Backfill über den `after_audit`-Hook.

### 2.4 Sortierung „Handlungsbedürftiges zuerst"

`offen (0) → zugestellt (1) → quittiert (2) → verwertet (3) → nicht_relevant (4)`,
danach neueste zuerst. Muster `PromotionStatus.rank`.

### 2.5 Endpunkte

| Route | Recht | Zweck |
|---|---|---|
| `GET /api/crossfindings` **erweitert** um `feedback` je Zeile + `feedback_counts` | `crossref.view` | rückwärtsverträglich: alle bisherigen Felder bleiben |
| `POST /api/crossfindings/decide` `{finding_id, status_code, reason?}` | `crossref.edit` | auditierte Entscheidung |

Fehlerbilder: unzulässiger Übergang / fehlender Grund → **400**; unbekannter Fund
→ **404**; fehlendes Substrat → **503** (Linie Build 474); fehlendes Recht → 403.

### 2.6 Tests Build 507

`tests/test_crossfinding_channel_status.py` (**CS01–CS07**): Übergangsmatrix,
Endzustände unumkehrbar, Grund-/Basis-Pflicht, `'offen'` als Ziel verboten,
unbekannter Zustand wirft, `rank`-Reihenfolge, `allowed_next`.

`tests/test_crossfinding_channel_repo.py` (**CF01–CF08**): erste Entscheidung
legt an; Folgeentscheidung aktualisiert (`audit_seq` steigt); unzulässiger
Übergang wirft und schreibt **nichts** (Rollback-Beleg); Grund-Pflicht;
unbekannter `finding_id` wirft; `list_with_status` inkl. `'offen'`;
`counts`; **Sensibilität** (Grund-Klartext nicht im `audit_log`).

`tests/test_crossfindings_api.py` **erweitert** (**CX-API05–CX-API09**):
RBAC-Deny POST; decide→GET zeigt den Zustand; unzulässiger Übergang → 400;
unbekannter Fund → 404; Altfelder unverändert vorhanden (Rückwärtsverträglichkeit).

**Anker:** `tests/test_management_dashboard.py` D01 `…23` → `…24`.

---

## 3. Build 508 — Frontend

### 3.1 `cockpit_crossfindings.js` erweitern (keine neue Sicht)

Hier ist der Anbau richtig — anders als bei A1 —, weil der Rückkanal **genau
dieselbe Zeile** betrifft, die die Sicht schon zeigt. Eine zweite Sicht hätte den
Fund und seinen Bearbeitungsstand auseinandergerissen.

- Neue Spalte **„Rückkanal"** mit Zustands-Badge (`offen` deutlich hervorgehoben —
  das ist der handlungsbedürftige Fall).
- Aktionsspalte (nur `crossref.edit`): Auswahl des Zielzustands **nur aus den
  laut Zustandsmaschine erlaubten Folgezuständen** (die der Server mitliefert —
  das Frontend erfindet keine Übergänge), Grund-/Basis-Feld erscheint, sobald der
  gewählte Zustand es verlangt.
- Kopfzeile um `feedback_counts` erweitert („5 offen · 2 quittiert · …").
- Filter „nur offene" wirkt weiterhin auf den **Transport**status; **neu**
  „nur unquittierte" auf den **Rückkanal**status. Beide Filter sind beschriftet,
  damit niemand sie verwechselt.
- **Kein SSE-Auto-Reload** für die Transportdaten (Begründung Build 478 §3 gilt
  unverändert); nach einer **eigenen** Entscheidung lädt die Sicht neu.

### 3.2 Geändert

`cockpit.js` (`loadCrossfindings` um `onDecide` erweitert), `cockpit.css`
(Badge-Stile `.aiw-cff-*`). **Kein** neuer Nav-Eintrag → `test_cockpit_nav.test.js`
bleibt bei 31 (nach A1) **unverändert**.

### 3.3 Tests Build 508

`tests/unit/test_cockpit_crossfindings.test.js` **erweitert** (**QF08–QF14**):
Badge-Klassen je Zustand; nur erlaubte Folgezustände im Auswahlfeld; Grundfeld
erscheint/verschwindet zustandsabhängig; Entscheidung ohne Pflichtgrund wird im
UI abgefangen; `feedback_counts` im Kopf; Altverhalten (QF01–QF07) unverändert
grün; XSS-Probe auf dem Grundtext.

---

## 4. Migrationsklasse

M024 **additiv**, neue Tabelle, nur `coordinator.db`. Ermittler-Ergebnisdaten
unberührt; der Migrationsvorbehalt greift nicht.

---
*Dokument-Ende · Bauplan A2 · v0.1 · 2026-07-24*
