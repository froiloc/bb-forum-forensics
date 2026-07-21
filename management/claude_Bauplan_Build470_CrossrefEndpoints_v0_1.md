# Bauplan Build 470 — AP-2A(2a): Backend-Endpunkte für `identified_subject`

**Version:** 0.1 · **Datum:** 2026-07-20 · **Modul:** `aiw_webserver`
**Basis:** HEAD `bdca3df` (v0.8.469, nach M019) · **Buildnummer:** 470 (reserviert durch mc)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc 2026-07-20 · Backend/Frontend getrennt (Festlegung 363)

---

## 1. Einordnung
Der in Build 468 gelieferte `IdentifiedSubjectRepo` (Katalog identifizierter Personen,
M018) bekommt seine HTTP-Oberfläche im Management-Server. `subject_id`-nativ, da die
globale Schlüsselumstellung (M019, Build 469) bereits gelandet ist. **Keine Migration,
keine neue Fähigkeit** (Seed `crossref.view`/`crossref.edit` lag in M018).

## 2. Gelieferte Artefakte

**Geändert**
- `management/server/management_app.py`
  - Fähigkeits-Konstanten `CAP_CROSSREF_VIEW`/`CAP_CROSSREF_EDIT`; Import
    `IdentifiedSubjectRepo`/`CrossrefError`.
  - **GET `/api/crossref`** (Recht `crossref.view`): `repo.list()` (stärkste Konfidenz
    zuerst); optional `?subject_id=N` → Einzeleintrag bzw. 404. Lesen über `_ro_con()`,
    Repo ohne Writer. Global, **nicht** scope-behaftet.
  - **POST `/api/crossref/set`** (Recht `crossref.edit`): `{subject_id, real_identity,
    confidence_code, basis?, note?}` → `repo.upsert(...)` über `CoordinatorWriter`
    (auditiert). Antwort `{ok, subject_id, confidence_code, audit_seq, created}`.
    `CrossrefError` → 400 (inkl. No-Op, leere `real_identity`, ungültige
    `confidence_code`), unbekannt → 500.
  - Verdrahtung in GET-Dispatch (`dispatch`) und POST-Dispatch (`dispatch_write`).
- `build.json` — Bump auf 470/0.8.470 (ASCII-only verifiziert).

**Neu**
- `tests/test_crossref_api.py` — CA01–CA07.

## 3. Sensibilität & Forensik
Die strenge Regel „Freitext (`real_identity`/`basis`/`note`) nie im Audit-Payload" bleibt
vollständig im Repo verankert; die Endpunkte reichen nur durch. CA07 prüft das auf
Endpunktebene stichprobenartig gegen den rohen `audit_log`-Beleg.

## 4. Tests (CA01–CA07)
RBAC-Deny für GET **und** POST (403 mit korrektem `capability`), `set`→`list`→`get`
(inkl. `confidence_ordinal`-Einfrieren), Revision erhöht `audit_seq`, Validierung (400),
unbekannter `subject_id` (404), Freitext-Freiheit des Belegs.

## 5. Verifikation
- `py_compile -W error::SyntaxWarning` über `management/ tests/` — RC 0.
- **Python (pytest, `test_editor_renderer.py` ausgeklammert):** 1585 passed / 49 skipped
  (Baseline 1578 + 7 neu).
- **JavaScript:** unverändert (Backend-only; kein JS berührt).

## 6. MD5-Handshake (HEAD 469)
| Datei | MD5 |
|---|---|
| `management/server/management_app.py` | `764fa6b2ddd7c855a8d07cbc0fe0c08a` |
| `build.json` | `880a413f1a6cda021a3b9bf80c2bd980` |

## 7. Bewusst NICHT in diesem Build
Cockpit-Sicht/Nav/JS „Kreuzbezug" (AP-2A(2b), Frontend-Build). Grants `crossref.*`
bleiben operative mc-Entscheidung (default-deny) — ohne Grant liefern die Endpunkte 403.

## 8. Nächster Schritt
AP-2A(2b): Cockpit-Sicht „Kreuzbezug" (Nav + HTML/CSS + IIFE-JS gegen `/api/crossref`
und `/api/crossref/set`), nach Console-First-Protokoll für das JS.

---
*Dokument-Ende · Bauplan Build 470 · v0.1 · 2026-07-20*
