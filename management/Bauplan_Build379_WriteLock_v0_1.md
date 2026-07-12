# Bauplan Build 379 — Berichts-Schreibsperre + Statusmodell + Siegel-Prüfbefehl

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Basis:** 0.7.378 · **mc:** 2026-07-10 · **Migration:** keine.
**Statusmodell:** `docs/Berichts_Statusmodell.md` · Code-Suchbegriff:
**`BERICHTS-STATUSMODELL`**

---

## 1. Die gefundenen Lücken (gemessen — das war der Anlass)

| Schreibpfad | Sperre bei `approved` | Sperre bei `final` |
|---|---|---|
| `update_block` | ja | **nein** |
| `delete_block` | ja | **nein** |
| `save_block` (neue Blöcke) | **nein** | **nein** |
| `set_block_order` (Reihenfolge) | **nein** | **nein** |
| `add_anchor` / `remove_anchor` | **nein** | **nein** |
| `update_report_status` | **nein** | **nein** |

**Konkret:** Ein freigegebener Bericht konnte **neue Blöcke** bekommen,
**umsortiert** und mit **Beweisankern** versehen werden — alles Bestandteile des
Siegel-Hashes (Build 377). Ein **`final`**-Bericht war **vollständig
ungeschützt**. Und der Status ließ sich beliebig zurückstufen, womit sich die
Sperre **selbst aushebeln** ließ.

Das Siegel hätte jede dieser Änderungen **nachträglich** aufgedeckt — verhindert
hat sie niemand.

---

## 2. Statusmodell (verbindlich festgelegt)

`draft` → `submitted` (Autor reicht ein, **Autor gesperrt**) → `approved`
(Abnahme + Versiegelung, **unwiderruflich**) → `final` (an StA versandt,
Endzustand). Rückgabe `submitted → draft` **nur** durch Lektor/Chef-Ermittlerin.

**Warnung:** `final` gibt es **zweimal** — als **Status** (versandt) und als
**report_type** (Abschlussbericht). Das war die Ursache der Begriffsverwirrung.

Dokumentiert **im Code** (an der Konstante) **und** als eigenständiges
Review-Dokument `docs/Berichts_Statusmodell.md`.

---

## 3. Umfang (geliefert)

- **`db/evidence_db.py`**: `ReportSealedError(EvidenceDbError)` — **erbt
  bewusst**, damit die bestehenden Fehlerpfade in `forensic_api/report.py`
  (`EvidenceDbError → 403/409`) **sofort greifen**, ohne jeden Endpunkt
  anzufassen. Zentrale Guards (`_assert_report_editable`,
  `_assert_block_editable`) — **eine Stelle statt sieben Endpunkten** — in allen
  sechs Inhalts-Schreibwegen. `update_report_status` **erzwingt** die Übergänge
  (`allow_reset=True` nur für den Management-Pfad).
  **Kommentare bleiben erlaubt** (`mc`).
- **NEU `management/reports/seal_check.py`**: `python -m
  management.reports.seal_check` — prüft **alle** Siegel gegen die evidence-DBs.
  Exit 0 = in Ordnung · **2 = Manipulationsverdacht** · 1 = Aufruffehler.
- **NEU `docs/Berichts_Statusmodell.md`** (Review-Dokument).
- **Tests** `test_report_write_lock.py` (WL01–WL08) · `test_evidence_db_b6.py`
  T06 (Setup an die Zustandsmaschine angepasst).

---

## 4. Regression (run_tests.py)

```
pytest : 1002 passed, 59 skipped, 6 subtests   (994 + 8)
vitest : 568 passed, 1 skipped, 1 todo (570), 49 Testdateien   (unverändert)
```

---

## 5. Abnahme

**Server neu starten.**
1. `python -m management.reports.seal_check` → prüft alle Siegel (bei noch keiner
   Freigabe: „Keine Siegel vorhanden").
2. Bericht über das Cockpit freigeben → im Ermittler-Editor eine Änderung
   versuchen → **wird mit klarer Meldung abgewiesen**.
3. **Kommentar** am freigegebenen Bericht → weiterhin möglich.

---

## 6. Offene Punkte (vermerkt)

1. **Ermittler-Editor:** Schaltfläche **„Zur Abnahme freigeben"**
   (`draft → submitted`) mit **Bestätigungsdialog** (Tragweite, weiterer Prozess,
   Rückholmöglichkeit über Lektor/Chefin). *Endpunkt existiert noch nicht.*
2. **Cockpit:** Rückgabe `submitted → draft` (auditierter Management-Pfad).
   *Endpunkt existiert noch nicht.*
3. **Cockpit-Beschriftung:** „Endgültig freigeben" → **„Als versandt/
   abgeschlossen kennzeichnen"**.

**Nächster Build 380:** Rückgabe-Pfad (Cockpit-Backend) + Beschriftungskorrektur.
**Danach 381:** Editor-Knopf mit Bestätigungsdialog.

---

*Dokument-Ende · Bauplan Build 379 · 2026-07-10*
