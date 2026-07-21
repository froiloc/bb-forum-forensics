# Bauplan Build 471 — AP-2A(2b): Cockpit-Sicht „Kreuzbezug" (Frontend)

**Version:** 0.1 · **Datum:** 2026-07-20 · **Modul:** `aiw_webserver`
**Basis:** HEAD `551dfa9` (v0.8.470) · **Buildnummer:** 471 (reserviert durch mc)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc 2026-07-20 · Backend/Frontend getrennt (Festlegung 363)

---

## 1. Einordnung
Die in Build 470 gelieferten Endpunkte (`GET /api/crossref`, `POST /api/crossref/set`)
bekommen ihre Cockpit-Oberfläche: die Sicht „Kreuzbezug" zeigt den Katalog
identifizierter Personen (Konto `subject_id` → reale Person) mit Konfidenzstufe und
erlaubt — mit Recht `crossref.edit` — Anlage/Revision. `subject_id`-nativ (Basis M019).
Keine neue Migration, keine neue Fähigkeit.

## 2. Gelieferte Artefakte

**Neu**
- `management/server/static/cockpit_crossref.js` — Modul nach Vorlage
  `cockpit_onboarding.js`: IIFE + `use strict`, DEV-Logging (`AIW_COCKPIT_DEBUG`),
  ausführliche Kommentare, reine Helfer ohne DOM, **UMD-Export**
  (`window.AIWCockpitCrossref` / `module.exports`). Rendert Katalog-Tabelle mit
  Konfidenz-Badge (verdacht/wahrscheinlich/gesichert) und — mit `crossref.edit` —
  ein Anlage-/Revisions-Formular samt Zeilen-Aktion „Revidieren" (befüllt das
  Formular vor; Konfidenz reift). Kein optimistisches UI. XSS-sicher (`textContent`).
- `tests/unit/test_cockpit_crossref.test.js` — CX01–CX07 gegen den **echten** Code
  (JSDOM/UMD), keine Logik-Duplikation (B4-S12).

**Geändert**
- `management/server/static/cockpit.js` — `VIEW_CATALOG`-Eintrag
  `{ id: 'crossref', cap: 'crossref.view', group: 'Auswertung', label: 'Kreuzbezug' }`;
  `loadCrossref()` (`fetchJson /api/crossref`, `postJson /api/crossref/set`,
  `canEdit` via `hasCap`); View-Dispatch + SSE-Refresh-Dispatch.
- `management/server/static/cockpit.html` — Skript `cockpit_crossref.js` eingebunden.
- `management/server/static/cockpit.css` — Konfidenz-Badge-Stile (drei Stufen) +
  Kreuzbezug-Tabellen-/Formular-Stile (Basis-Variablen wiederverwendet).
- `tests/unit/test_cockpit_nav.test.js` — Katalog-Länge 27 → 28 + CN-XREF.
- `build.json` — Bump auf 471 (ASCII-only verifiziert).

## 3. Sensibilität & Sicherheit
Die PII-Freitexte (`real_identity`/`basis`/`note`) bleiben serverseitig aus dem
Audit-Payload (Repo/Endpunkt aus 468/470); das Frontend reicht nur durch und zeigt
sie nur der berechtigten Ermittlerin. Alle variablen Texte via `textContent` (XSS).

## 4. Verifikation
- Gezielte Suiten: `test_cockpit_crossref.test.js` (7) + `test_cockpit_nav.test.js` (18)
  grün.
- Kanonischer Gate `run_tests.py`: Python UND JavaScript bestanden.
- `py_compile` unverändert relevant (kein Python geändert).

## 5. Zurückgestellt & Grants
- Grants für `crossref.*` bleiben operative mc-Entscheidung (default-deny) — ohne
  Grant erscheint die Sicht nicht in der Nav.
- **Verwertbarkeits-Achse (StA)** weiterhin zurückgestellt bis juristische
  Rückkopplung; additiv nachrüstbar. Fragenkatalog liegt der StA vor. **Kopierfertiger
  Wiedervorlage-Eintrag** (für `claude_Wiedervorlage_offene_Punkte.md` im
  Projektspeicher — die Datei ist nicht Teil des Repos):

  > **Offen — Verwertbarkeits-Achse (Achse 2) im Kreuzbezugs-Katalog.**
  > Status: zurückgestellt bis juristische Rückkopplung mit der StA (Termin
  > 2026-07-22, Fragenkatalog `claude_Fragenkatalog_StAin_Verwertbarkeit_Konfidenz_v0_1.md`).
  > Inhalt: zweite, von der Identitäts-Konfidenz getrennte Dimension
  > (`verwertbar`/`teilverwertbar`/`Verwertungsverbot`/`Quellenschutz`; Zufalls-/
  > Querfunde § 108 StPO). Umsetzung additiv (Spalte/Tabelle an `identified_subject`),
  > verlustfrei nachrüstbar. Blockiert nichts an AP-2A; vor Umsetzung mc + StA.

## 6. Nächster Schritt (Vorschlag)
Auf Wunsch eine Tabulator.js-Variante der Liste (du prüfst den DOM-Ansatz; ggf.
separater Auftrag). Sonst AP-2A(3): Alias-Katalog / Querfunde — dort auf die
bestehende `forensic_api`-Klempnerei (`aliases.py`, `cross_annotation_integrator.py`)
aufsetzen statt duplizieren (belegte Reconciliation).

---
*Dokument-Ende · Bauplan Build 471 · v0.1 · 2026-07-20*
