# Detail-Bauplan Build 346 — Management-Server (Backend, read-only)

**Version:** 0.1 · **Datum:** 2026-07-10 · **Build:** 346 · **Version:** 0.7.346
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.2 (+§11.6, §10.6).
**mc:** 2026-07-10 (fahre fort).

---

## 1. Ziel und Abgrenzung

Welle-0-Schritt 3: der **eigenständige Management-Server** (`management.py`),
getrennt vom Forensik-Webserver (`server/`, B2). **Erster Build mit Browser-
Anteil** — daher **Split analog 314/315**: das vollständig **pytest-testbare
Backend** jetzt; die **gerenderte Cockpit-Oberfläche** (policy-getriebene
Navigation) folgt in einem **browser-verifizierbaren** Build (Live-Abnahme hier
nicht möglich).

**READ-ONLY im ersten Build** (§11.1.4): nur GET, kein `CoordinatorWriter`, keine
Migration.

---

## 2. Lieferumfang

| Datei | Art | Inhalt |
|---|---|---|
| `management.py` | NEU | Entry-Point (Start-Check → Identität → localhost-Server) |
| `management/server/__init__.py` | NEU | Paket-Kopf |
| `management/server/identity.py` | NEU | `IdentityResolver`/`IdentityError` (OS→person, mockbar) |
| `management/server/management_app.py` | NEU | `ManagementApp`, `Response`, `format_sse_event` (testbarer Kern) |
| `management/server/management_handler.py` | NEU | `ManagementRequestHandler`, `ManagementHTTPServer` |
| `tests/test_management_server.py` | NEU | M01–M11 |
| `build.json` | GEÄNDERT | Build 346 (ASCII-only) |
| `management/Bauplan_Build346_ManagementServer_v0_1.md` | NEU | dieses Dokument (git-ignored, `git add -f`) |

---

## 3. Architektur

**Nebenläufigkeit (Build-325-Lehre, §11.2):** ThreadingHTTPServer, aber **keine
geteilte Connection** — jeder Request/Tick öffnet eine kurzlebige read-only
Verbindung (`file:…?mode=ro`) und schließt sie. Kein Win32-Mutex-Deadlock, kein
Schreibpfad.

**Testbarkeit (§10.6):** `ManagementApp.dispatch(person_id, path, query) →
Response` ist der reine Kern **ohne Socket** → pytest. Der HTTP-Handler ist eine
dünne Hülle; der SSE-Stream nutzt `format_sse_event`.

**Identität (§11.6):** OS-Benutzer (SAMAccountName) → `person.system_username`
(stabile forensische Identität); AD-Anzeigename = `display_name`. Gekapselt,
**mockbar** (`os_user_source` injizierbar; `--as-user` Override). Unbekannt →
`IdentityError` (kein stiller Fallback).

**Start-Check:** `startup_selfcheck()` ruft `verify_catalog_present` (Schnitt c)
— kein Start mit unvollständiger RBAC-Basis (Grundregel 1).

---

## 4. Endpunkte

| Pfad | Gate | Inhalt |
|---|---|---|
| `GET /` | — | Platzhalter-Shell (HTML); Anzeigename + Backend-Status |
| `GET /api/whoami` | — (eigene Identität) | `person_id`, `system_username`, `display_name`, `roles`, `capabilities{cap:scope}` |
| `GET /api/overview` | `dashboard.view` | Fallübersicht (DashboardRepo). Scope `alle` = alle Fälle; sonst nur eigene Zuweisungen (`assigned_to==person_id`) |
| `GET /api/integrity` | `ops.view` | `verify_chain` (ok, first_bad_seq, detail) + `tip_seq` |
| `GET /events` | — | SSE-Tick: sofort `hello{tip_seq}`, dann Poll → `changed{tip_seq}` / `keepalive` |
| `GET /static/*` | — | 404 (Cockpit-Assets folgen) |
| sonst | — | 404 |
| POST/PUT/DELETE/PATCH | — | 405 (read-only) |

Fehlende Fähigkeit → **403** (kein stiller Teilinhalt). SSE-Rahmen nach RFC 8895
(`event:`/`data:`/Leerzeile), eigene Maschinerie (nicht B3/4 wiederverwendet).

---

## 5. Tests (M01–M11, `tests/test_management_server.py`)

whoami (M01); overview Gating + Scope: `eigene` filtert auf eigene Zuweisungen,
`alle`=alle, kein Grant→403 (M02); integrity Gating (M03); Shell (M04);
404/static (M05); SSE-Format (M06); `startup_selfcheck` grün + Lücke→
`RbacCatalogError` (M07); `IdentityResolver` Mock + unbekannt→`IdentityError`
(M08); **Live-Server** GET + POST→405 (M09); **Live-SSE** `hello` (M10);
Read-Only-Nachweis: `audit_log` unverändert (M11).

**Regression (`run_tests.py`):** Python **855** passed (844 + 11), 59 skipped,
3 subtests; JavaScript **467** passed, 1 skipped, 1 todo (kein JS geändert).

---

## 6. Deploy / Start

Keine Migration; reiner Lesepfad. Start:
```
python management.py --coordinator-db ./data/coordinator.db [--auto-port --open-browser]
```
Identität aus dem OS-Konto (oder `--as-user h0XXXXX` im Dev-Betrieb). Bindet nur
localhost.

---

## 7. Anschluss (browser-verifizierbarer Folge-Build)

**Cockpit-Frontend:** policy-getriebene Navigation/Tabs (aus `/api/whoami`),
`/static/<f>` (cockpit.* + Wiederverwendung `dashboard.js`/`support_overview.js`/
`workload.js`), Live-Aktualisierung über den `/events`-SSE-Client (kein F5),
ECharts/Tabulator sobald die erste Sicht sie braucht. Vorgehen **console-first**
(Console-Output → PoC → Roll-out), sobald Browser-Abnahme möglich ist.

---

*Dokument-Ende · Detail-Bauplan Build 346 · v0.1 · 2026-07-10*
