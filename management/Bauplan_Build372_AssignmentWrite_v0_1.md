# Bauplan Build 372 — Zuweisung Teil 1: Erster auditierter Schreibpfad (Backend)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), **Welle 1**
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §2.6 (`CoordinatorWriter`
= „der einzige zulässige Schreibpfad"). **Basis:** 0.7.371. **mc:** 2026-07-10.

---

## 1. Architektur-Änderung (bewusst, mit `mc`)

Der Management-Server war bisher **strukturell schreibunfähig**:
`do_POST/PUT/DELETE/PATCH → 405` und **alle** DB-Verbindungen `mode=ro`.
Management ist jedoch keine rein passive Tätigkeit — daher jetzt eine **eng
regulierte Schreibschicht** über POST. Der forensische Kern bleibt unangetastet:
**jede** Änderung geht durch `CoordinatorWriter` (BEGIN IMMEDIATE → Write →
Audit → COMMIT) und erzeugt zwingend ihren `audit_log`-Beleg. Kein Direkt-SQL.

---

## 2. Umfang (geliefert)

### `management/server/management_app.py`
- **Schreib-Token** pro Serverlauf (`secrets.token_urlsafe(32)`), ausgeliefert
  **nur** über `GET /api/whoami` (`write_token`); Vergleich konstantzeitlich
  (`hmac.compare_digest`).
- **`_rw_con()`** — Schreibverbindung, ausschließlich in den Schreibhandlern;
  alle Lesepfade bleiben `_ro_con()` (`mode=ro`).
- **`GET /api/assignable`** — Fälle + wählbare Ermittler (mit aktueller Last) +
  Status-/Prioritäts-Vokabular.
- **`dispatch_write()`** mit genau **drei** Schreibrouten:
  `/api/case/assign` `{user_id, person_id|null}` ·
  `/api/case/priority` `{user_id, priority 1..5}` ·
  `/api/case/status` `{user_id, status}`.
  Schreiben **nur** via `CasesRepo` + `CoordinatorWriter` → Belege
  `case_assigned` / `case_priority_set` / `case_status_changed`.
- **RBAC:** `assignment.edit` **und** Scope `alle` erforderlich (Scope `eigene` →
  403). **Selbstzuweisung ist ausdrücklich erlaubt** — wer `alle` hat, darf auch
  sich selbst zuweisen; es gibt keine Regel „Ziel ≠ Handelnder".
- **Validierung:** unbekannter Fall/Person → 400; Nicht-Ermittler als Ziel → 400;
  ungültige Priorität/Status → 400; unbekannte Route → 404; Schreibfehler → 500
  **mit Log** (Grundregel 1). Antwort enthält `audit_seq`.

### `management/server/management_handler.py`
`do_POST` mit **Härtung**: Content-Type muss `application/json` sein (→ 415;
blockt einfache Cross-Origin-Formular-POSTs) · Origin (falls gesetzt) muss
localhost sein (→ 403) · `X-AIW-Token` muss stimmen (→ 403; schützt gegen
Bridges/Tunnel und CSRF — wer die GET-Antwort nicht lesen kann, kennt das Token
nicht) · Body-Limit 64 KiB (→ 413) · JSON-Parsefehler → 400.
**PUT/DELETE/PATCH bleiben 405.**

### Tests
`tests/test_assignment_write.py` (AS01–AS08, inkl. **echtem HTTP-Server** für die
Härtung und **Audit-Beleg-Prüfung**) · `tests/test_management_server.py` m09 auf
die neue Härtung aktualisiert (**strenger**: 415 / 403 / 405 / 404).

---

## 3. Regression (run_tests.py)

```
pytest : 973 passed, 59 skipped, 3 subtests   (965 + 8)
vitest : 551 passed, 1 skipped, 1 todo (553), 47 Testdateien   (unverändert)
```

---

## 4. Abnahme

**Server neu starten** (neue Routen + Token). `GET /api/whoami` → enthält
`write_token`. `GET /api/assignable` → Fälle + Ermittler. `POST /api/case/assign`
mit `Content-Type: application/json` und `X-AIW-Token: <token>` → 200 +
`audit_seq`; der Beleg steht im `audit_log`.

---

## 5. Nächster Build (373, Frontend, console-first)

`cockpit_assignment.js` — Fall-Tabelle mit Zuweisung/Priorität/Status, Token aus
`whoami`, POST + Fehleranzeige, SSE-Reload.

---

## 6. VERMERKT — offener Punkt (eigener Baustein, **Ermittler-Webserver**)

**Fallauswahl-GUI für Ermittler.** Ermittler brauchen beim Start eine Oberfläche,
die ihre zugewiesenen Fälle zeigt und es erlaubt, **abweichend von der
automatischen Auswahl des höchstpriorisierten Falls** gezielt einen anderen
zugewiesenen Fall zu öffnen — **ohne Konsole**. Begründung: Ermittler müssen
selbst entscheiden können, welchen ihrer Fälle sie bearbeiten. Aktueller Behelf:
CLI-Modus in `main.py` mit `--user-id`. Umsetzung in naher Zukunft erwünscht.

---

*Dokument-Ende · Bauplan Build 372 · 2026-07-10*
