# Bauplan Build 474 — AP-2A(3) Scheibe 1: Querfund-Meta-Übersicht (Backend)

**Version:** 0.1 · **Datum:** 2026-07-20 · **Modul:** `aiw_webserver`
**Basis:** HEAD `a0c4623` (v0.8.471) · **Buildnummer:** 474 (reserviert durch mc)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc 2026-07-20 (Scope + Klärungen 1–3 angenommen)

---

## 1. Einordnung
Erste Scheibe des Querfund-/Merge-Split-Blocks (AP-2A(3), Ideen 6/7/11). AP-2A(3)
umfasst insgesamt: **Querfund-Meta-Übersicht** (Idee 6, *dieser Build*),
**Querfund-Rückkanal** (Idee 7, Zustandsmaschine, neu), **Cockpit-Sicht** (6/7),
**Identitäts-Merge/Split** (Idee 11, neu).

**Belegter Kernbefund (kein Duplizieren):** Die automatische Querfund-Erfassung
und der Transport laufen bereits über `forensic_api/cross_annotation_integrator.py`
und die coordinator-Tabelle `pending_cross_annotations`. Die Ideen-Doku hält fest:
im Cockpit ist das „nur eine zusammenführende Meta-Übersicht". Dieser Build baut
also **nichts nach**, sondern **liest** den vorhandenen Bestand.

## 2. Gelieferte Artefakte
**Neu**
- `management/crossref/crossfindings_repo.py` — `CrossfindingsRepo(con)`, **rein
  lesend**: `list(only_open=False)` + `counts()` über `pending_cross_annotations`.
  `target_uid` → `subject_id` normalisiert; Best-effort-Joins auf `person`
  (Quell-Ermittler) und `cases` (Fall-Kontext).
- `tests/test_crossfindings_repo.py` (CR01–CR05),
  `tests/test_crossfindings_api.py` (CX-API01–CX-API04).

**Geändert**
- `management/server/management_app.py` — Import `CrossfindingsRepo`; GET
  `/api/crossfindings` (Recht `crossref.view`, optional `?only_open=1`); Handler
  `_crossfindings` (503 bei fehlendem Substrat, 500 sonst; nur `_ro_con()`).
- `build.json` — Bump auf 474 (ASCII-only verifiziert).

## 3. Entscheidungen (mc 2026-07-20)
- **`pending_cross_annotations` wie-es-ist gelesen** (schnell, nicht-invasiv). Die
  Tabelle liegt außerhalb der Migrationskette (`db/coordinator_db.py`, auf
  `target_uid` statt `subject_id`) — Überführung ist ein **eigener späterer
  Governance-Punkt**, nicht Teil von 474.
- **Fähigkeit `crossref.view` wiederverwendet** (gleiche F5-Familie, keine
  Rechte-Inflation). Keine neue Migration/Fähigkeit.
- **Grundregel 1:** nicht zuordenbare Zeilen bleiben sichtbar (`source_name`
  null, `has_case` false); fehlendes Substrat wirft (503), statt still eine leere
  Übersicht vorzutäuschen.

## 4. Verifikation
- `py_compile -W error::SyntaxWarning` OK.
- Gezielt: `test_crossfindings_repo.py` (5) + `test_crossfindings_api.py` (4) grün.
- Kanonischer Gate `run_tests.py`: Python UND JavaScript bestanden.

## 5. Nächste Scheiben (Vorschlag)
- **B444 — Querfund-Rückkanal** (Idee 7): Zustandsmaschine, die den B-Ermittler
  aktiv erreicht (Schreibpfad + Migration + Audit).
- **B445 — Cockpit-Sicht** „Querfunde" (Erfassung + Rückkanal-Status).
- **B446 — Identitäts-Merge/Split** (umkehrbar, auditiert).
- **Governance:** `pending_cross_annotations` in die Migrationskette überführen
  und `subject_id`-angleichen.

---
*Dokument-Ende · Bauplan Build 474 · v0.1 · 2026-07-20*
