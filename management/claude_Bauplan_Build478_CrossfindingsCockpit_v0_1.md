# Bauplan Build 478 — AP-2A(3) Scheibe 2: Cockpit-Sicht „Querfunde" (Frontend)

**Version:** 0.1 · **Datum:** 2026-07-21 · **Modul:** `aiw_webserver`
**Basis:** HEAD `553b234` (v0.8.477) · **Buildnummer:** 478 (reserviert durch mc)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc 2026-07-21 · Backend/Frontend getrennt (Festlegung 363)

---

## 1. Einordnung
Frontend zum in **Build 474** gelieferten Endpunkt `GET /api/crossfindings`
(rein lesende Querfund-Meta-Übersicht). Spiegel des Musters 470→471. Macht die
Querfunde („Fund über B im Fall A") sichtbar. Rein lesend — Erfassung/Transport
laufen automatisch über die `forensic_api`-Pipeline.

## 2. Gelieferte Artefakte
**Neu**
- `management/server/static/cockpit_crossfindings.js` — Modul nach Vorlage
  `cockpit_crossref.js` (IIFE, DEV-Logging, reine Helfer, UMD-Export). counts-Kopf
  (offen/integriert/gesamt), Tabelle, Umschalter „nur offene", „Aktualisieren".
  XSS-sicher.
- `tests/unit/test_cockpit_crossfindings.test.js` (QF01–QF07, echter Code/UMD).

**Geändert**
- `management/server/static/cockpit.js` — `VIEW_CATALOG`-Eintrag
  `{ id: 'crossfindings', cap: 'crossref.view', group: 'Auswertung', label: 'Querfunde' }`;
  `loadCrossfindings()`; View-Dispatch. **Kein SSE-Refresh** (§3).
- `management/server/static/cockpit.html` — Skript eingebunden.
- `management/server/static/cockpit.css` — Status-Badge-Stile (offen/integriert).
- `tests/unit/test_cockpit_nav.test.js` — Länge 28 → 29 + CN-QUERFUND.
- `build.json` — Bump auf 478 (ASCII-only verifiziert).

## 3. Zwei bewusste Design-Entscheidungen (mc)
1. **Manuelles „Aktualisieren" statt SSE-Refresh.** Querfunde entstehen über die
   automatische `forensic_api`-Pipeline (`pending_cross_annotations`), nicht über
   den coordinator-`audit_log`; der SSE-Strom würde für sie nicht feuern — ein
   SSE-Refresh wäre irreführend.
2. **503 „nicht verfügbar" statt leerer Liste (Grundregel 1).** Fehlt das
   Substrat, zeigt die Sicht eine Fehlermeldung, keine leere Tabelle, die
   fälschlich „keine Querfunde" suggerierte. Ein echter Leerbefund (Substrat da,
   0 Funde) zeigt bewusst „Keine Querfunde".

Recht **`crossref.view`** wiederverwendet. Keine neue Fähigkeit/Migration.

## 4. Verifikation
- Gezielt: `test_cockpit_crossfindings.test.js` (7) + `test_cockpit_nav.test.js`
  (19) grün.
- Kanonischer Gate `run_tests.py`: Python UND JavaScript bestanden.
- Kein Python geändert.

## 5. Nächste Scheiben (Empfehlung)
- **Governance zuerst:** `pending_cross_annotations` in die Migrationskette
  überführen + `subject_id`-angleichen.
- **B444 — Querfund-Rückkanal** (Zustandsmaschine, erreicht den B-Ermittler),
  danach diese Sicht um die Rückkanal-Spalte erweitern.
- **B446 — Identitäts-Merge/Split** (umkehrbar, auditiert).

---
*Dokument-Ende · Bauplan Build 478 · v0.1 · 2026-07-21*
