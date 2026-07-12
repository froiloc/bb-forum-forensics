# Bauplan Build 377 — Berichts-Versiegelung (Backend)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 · **Basis:** 0.7.376 · **mc:** 2026-07-10
**Migration:** keine (coordinator); **neue zentrale DB** `approved_reports.db`.

---

## 1. Das Siegel sitzt an zwei Orten — weil es zwei Aufgaben hat

| Ort | Aufgabe | Umsetzung |
|---|---|---|
| `evidence_<uid>.db` | **Durchsetzung** — dort wird geschrieben, dort muss gesperrt werden | `reports.status = approved/final` (**Spalte existiert bereits → keine Schemaänderung**, Migrationsvorbehalt gewahrt) |
| `approved_reports.db` (zentral) | **Beweis** — außerhalb der Reichweite des Ermittlers | vollständiges **Abbild** + kanonischer **Inhaltshash** |

Die evidence-seitige Sperre schützt gegen den **normalen Weg** (die Anwendung).
Sie schützt **nicht** gegen jemanden, der die evidence-DB direkt mit einem
SQLite-Werkzeug manipuliert. **Genau dagegen wirkt der zentrale Hash:** `verify()`
hasht neu und vergleicht — **Abweichung = Manipulation, nachweisbar** (Test SE06).

---

## 2. Hash-Konvention (kein neues Rad)

Übernommen aus `core/startup_checks.py`: **nicht** über Datei-Bytes (bei SQLite
instabil), sondern **kanonischer Inhaltsdump**
`"<tabelle>:<repr(col1)>|<repr(col2)>…\n"` als UTF-8 → SHA-256.

**Umfang (mc):** `reports` (Kopf) + `report_blocks` **in der Anzeige-Reihenfolge**
aus `report_block_order` + `report_anchors`. **Nicht** im Siegel:
`report_comments` (Arbeitsmaterial) sowie `report_approvals`/`report_opened`
(Metadaten der Abnahme).

**`status` ist aus dem Hash ausgenommen** — er ändert sich *durch* die Freigabe;
wäre er im Hash, würde das Siegel im Moment des Siegelns ungültig
(selbstreferenzieller Konflikt; dieselbe Begründung wie der Ausschluss des
`sha256`-Eintrags in `forensic_meta`).

---

## 3. Das Zwei-Datenbanken-Problem — offen benannt

Beleg (`coordinator.db`), Bericht (`evidence_<uid>.db`) und Siegel
(`approved_reports.db`) liegen in **drei** SQLite-Dateien. Eine gemeinsame
Transaktion gibt es **nicht**; ein „atomares" Versprechen wäre gelogen. Deshalb:

1. Bericht lesen + hashen (read-only)
2. **Beleg** `REPORT_APPROVED` via `CoordinatorWriter` → `audit_seq`
3. **Siegel** zentral ablegen (Abbild + Hash + `audit_seq`)
4. **Durchsetzung** in evidence (`report_approvals` + `reports.status`)

Scheitert 3 oder 4, **bleibt der Beleg stehen** (der Versuch *hat*
stattgefunden), und der Aufrufer bekommt einen **expliziten** Fehler mit der
Angabe, was gelungen ist. Ein stiller Teilerfolg ist ausgeschlossen (Grundregel 1).

---

## 4. Umfang (geliefert)

- **NEU** `report_sealer.py` (`ReportSealer`), `approved_reports_db.py`
  (`ApprovedReportsDb`), `approval_service.py` (`ApprovalService`).
- **GEÄNDERT** `event_types.py` (`REPORT_APPROVED`, `REPORT_SEAL_VERIFIED`),
  `config_loader.py` (`paths.approved_reports_db`), `management_app.py`
  (`POST /api/report/approve` — `reports.approve`, Scope `alle`; `GET
  /api/report/verify`).
- **Tests** `test_report_sealing.py` (SE01–SE07).

**Vom Test aufgedeckt:** Der `UNIQUE`-Schlüssel muss `is_final` enthalten — die
Aufwertung `approved → final` siegelt denselben Inhalt erneut (der Inhalt ändert
sich dabei ja gerade *nicht*); das ist ein legitimer zweiter Eintrag.

---

## 5. Regression (run_tests.py)

```
pytest : 994 passed, 59 skipped, 3 subtests   (987 + 7)
vitest : 565 passed, 1 skipped, 1 todo (567), 49 Testdateien   (unverändert)
```

---

## 6. Abnahme

**Server neu starten.** Einen Bericht auf `status='submitted'` setzen, dann:
`POST /api/report/approve {user_id, report_id}` (mit `Content-Type:
application/json` und `X-AIW-Token`) → 200 mit `content_sha256`, `audit_seq`,
`seal_id`. Prüfen: evidence-Status `approved`; `approved_reports.db` enthält
Abbild + Hash; `audit_log` enthält `report_approved`.
`GET /api/report/verify?user_id=..&report_id=..` → `match: true`.
**Gegenbeweis:** den Bericht direkt in der evidence-DB ändern → `verify` meldet
`match: false` und „ABWEICHUNG".

---

## 7. Nächste Schritte

**378 — Frontend der Freigabe** (Knopf in der Berichts-Abnahme, Siegel-/Verify-
Anzeige) · **379 — Schreibsperre im Ermittler-Webserver** bei `approved`/`final`
(Durchsetzung dort, wo geschrieben wird).

---

*Dokument-Ende · Bauplan Build 377 · 2026-07-10*
