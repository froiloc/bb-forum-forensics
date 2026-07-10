# Detail-Bauplan Build 345 — RBAC Schnitt (c): Auflösung & Durchsetzung

**Version:** 0.1 · **Datum:** 2026-07-10 · **Build:** 345 · **Version:** 0.7.345
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.3; `Bauplan_Build344…` §8.
**mc:** 2026-07-10 (fahre fort).

---

## 1. Ziel und Abgrenzung

Dritter und letzter RBAC-Schnitt der Welle 0. Liefert die **rein lesende**
Auflösungsschicht (Rollen → aktive Grants → Fähigkeit + weitester Scope) und den
**Start-Check** (Code-Katalog ⊆ DB). **Keine** Schemaänderung, **kein**
`CoordinatorWriter`, **kein** Schreibpfad → kein Datenverlust-Risiko;
`coordinator.db` ist im Produktivbetrieb ohnehin nur lesend.

Damit ist die **RBAC-Trias komplett**: Schema+Seed (343) · Schreibpfad (344) ·
Auflösung (345).

**NICHT enthalten** (Folge-Build, Welle-0-Schritt 3): Verdrahtung in
`management.py` (Management-Server + SSE), Durchsetzung an konkreten Endpunkten,
policy-getriebene Navigation.

---

## 2. Lieferumfang

| Datei | Art | Inhalt |
|---|---|---|
| `management/rbac/rbac_resolver.py` | NEU | `PersonPolicy`, `RbacResolver`, `RbacResolverError`/`RbacCatalogError`, `verify_catalog_present()` |
| `tests/test_management_rbac_resolver.py` | NEU | S01–S11 |
| `build.json` | GEÄNDERT | Build 345 (ASCII-only) |
| `management/Bauplan_Build345_RBAC_Resolver_v0_1.md` | NEU | dieses Dokument (git-ignored, `git add -f`) |

Kolokation von DTO/Fehlern/Resolver in **einer** Datei folgt der Präzedenz
`dashboard_repo.py` (`CaseOverview` + `DashboardSchemaError` + `DashboardRepo`).

---

## 3. Auflösung — `RbacResolver` (§11.3)

`resolve(person_id) -> PersonPolicy`:
1. aktive Rollen der Person aus `person_role` (`revoked_at IS NULL`),
2. Vereinigung der aktiven Grants dieser Rollen aus `rbac_grant`
   (`revoked_at IS NULL`),
3. Fähigkeit gilt bei ≥1 Grant; Scope = **weitester**.

**default-deny:** keine Rolle / kein Grant ⇒ keine Fähigkeit; unbekannte Person ⇒
leere Policy (**kein** Fehler). Bequemlichkeit: `can(person, cap)`,
`scope_for(person, cap)`.

**`PersonPolicy`** (frozen DTO): `person_id`, `roles` (frozenset),
`capabilities` (dict cap→scope). `can(cap)` = Präsenz; `scope(cap)` = weitester
Scope (None = nicht vorhanden **oder** vorhanden ohne Scope → zur Unterscheidung
`can()` nutzen).

**Scope-Ordnung:** `alle` (2) > `eigene` (1) > `None` (0). Bei mehreren Grants für
dieselbe Fähigkeit gewinnt der höchste Rang. `None` = „kein Scope ausgewiesen"
(Fähigkeiten ohne Scope-Semantik, z. B. `reports.approve`) und ist der niedrigste
Rang, damit ein ausgewiesenes `eigene`/`alle` immer gewinnt.

---

## 4. Start-Check — `verify_catalog_present(con)` (§11.3)

„Jede Code-Capability existiert in der DB": Richtung **Code ⊆ DB** — jede Rolle/
Fähigkeit aus `catalog.py` **muss** in `rbac_role`/`rbac_capability` geseedet
sein. Die **DB darf voraus sein** (eine neue Migration hat Codes ergänzt, die der
Code noch nicht kennt) — das ist zulässig. Fehlt etwas → harter, handlungsleitender
`RbacCatalogError` (Hinweis auf `python -m management.migrate`), **niemals** ein
stiller Durchgang (Grundregel 1). Fehlende RBAC-Tabellen (`OperationalError`) →
ebenfalls `RbacCatalogError`.

**Verortung:** im rbac-Modul, jetzt eigenständig testbar; die Verdrahtung erfolgt
in `management.py` beim Start des Management-Servers (Welle-0-Schritt 3). Bewusst
**nicht** an `core/startup_checks.py` (Baustelle-2-Forensik-Webserver) gehängt —
getrennte Belange.

---

## 5. Tests (S01–S11, `tests/test_management_rbac_resolver.py`)

default-deny ohne Rolle (S01); Einzelrolle mit Grants inkl. Scope `None` (S02);
Scope-Widening `eigene`+`alle`→`alle` und `None`<`eigene` (S03); zurückgenommener
Grant/zurückgenommene Rolle fällt aus (S04); Mehrfachrollen-Vereinigung (S05);
ungegrantete Fähigkeit (S06); Katalog-Check grün (S07); fehlende Fähigkeit/Rolle →
`RbacCatalogError` handlungsleitend (S08/S09); DB voraus → ok (S10); Read-Only-
Nachweis: `resolve` ändert keine Zeilenzahlen und kein `audit_log` (S11).

**Regression (`run_tests.py`):** Python **844** passed (833 + 11), 59 skipped,
3 subtests; JavaScript **467** passed, 1 skipped, 1 todo (kein JS geändert).

---

## 6. Deploy

Keine Migration; kein Schema-/Datenpfad berührt. Reiner Code-Zuwachs (Lesepfad).

---

## 7. Anschluss (Welle-0-Schritt 3)

**Management-Server** `management.py` (read-only-first, §11.2): löst OS-Identität
(`SAMAccountName` → `person`) auf, ruft `verify_catalog_present` beim Start, leitet
über `RbacResolver` die Policy ab (policy-getriebene Cockpit-Navigation), bindet
**nur localhost**, SSE über die `audit_log`-Spitze. Read-Models der gebauten
Module (dashboard/support_overview/workload) werden dort erstmals hinter der
Durchsetzung zusammengeführt.

---

*Dokument-Ende · Detail-Bauplan Build 345 · v0.1 · 2026-07-10*
