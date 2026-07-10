# Detail-Bauplan Build 344 — RBAC Schnitt (b): Schreibpfad + policy-CLI

**Version:** 0.1 · **Datum:** 2026-07-10 · **Build:** 344 · **Version:** 0.7.344
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.1/§11.3/§11.7 (Schnitt b).
**mc:** 2026-07-10.

---

## 1. Ziel und Abgrenzung

Zweiter RBAC-Schnitt der Welle 0 (nach Schema+Seed, Build 343). Liefert den
**auditierten Schreibpfad** auf die RBAC-Matrix und die **`policy`-CLI**. Additiv
(nur neuer Code + vier additive `event_types`; **keine** Schemaänderung — das
M006-Schema aus 343 genügt).

**Werkzeug-only (mc):** faithful zu §11.7 (b) „Schreibpfad + `policy_admin`-CLI".
**Keine** Basis-Grants im Build gebacken — auditierte Betriebsdaten entstehen zur
Deploy-Zeit über die CLI (Grundsatz wie bei `person`: keine Migrations-Seeds für
auditierte Betriebsdaten). Eine **empfohlene** Basis-Matrix (§4) ist dokumentiert,
wird aber **nicht** automatisch ausgeführt.

**NICHT enthalten** (Schnitt c, Folge-Build): Resolver (Rollen→Grants→Scope,
`alle` > `eigene`), Start-Check „jede Code-Capability existiert in der DB",
Durchsetzung.

---

## 2. Lieferumfang

| Datei | Art | Inhalt |
|---|---|---|
| `management/rbac/rbac_repo.py` | NEU | `RbacRepo` + `RbacError` (auditierter Schreibpfad + Leser) |
| `management/rbac/rbac_admin.py` | NEU | CLI `python -m management.rbac.rbac_admin` |
| `management/audit/event_types.py` | GEÄNDERT | 4 additive Werte (`RBAC_GRANTED/REVOKED`, `ROLE_ASSIGNED/REVOKED`) |
| `tests/test_management_rbac_repo.py` | NEU | G01–G11 + A01 |
| `build.json` | GEÄNDERT | Build 344 (ASCII-only) |
| `management/Bauplan_Build344_RBAC_Writepath_v0_1.md` | NEU | dieses Dokument (git-ignored, `git add -f`) |

---

## 3. Schreibpfad — `RbacRepo`

Jeder Write läuft über `CoordinatorWriter.audited_write` mit `after_audit`-Hook:
die geschriebene Zeile trägt `audit_seq == seq` ihres Belegs (Kopplung wie
`case_events`, §8.3) — Write + Beleg committen atomar oder gar nicht.

- `grant(role, capability, scope, actor_id, note)` → `RBAC_GRANTED`; INSERT
  `rbac_grant`.
- `revoke_grant(grant_id, actor_id, note)` → `RBAC_REVOKED`; **Soft-Revoke**
  (`revoked_at/by` + `revoke_audit_seq`), **kein DELETE**.
- `assign_role(person_id, role, actor_id)` → `ROLE_ASSIGNED`; INSERT
  `person_role`.
- `revoke_role(person_role_id, actor_id)` → `ROLE_REVOKED`; Soft-Revoke.
- Leser: `list_grants(active_only)`, `list_person_roles(person_id, active_only)`,
  `get_grant(id)`.

**Katalog-Validierung** gegen `catalog.ROLE_CODES` / `CAPABILITY_CODES` + `scope ∈
{alle, eigene, None}` → `RbacError` bei Verstoß (kein Write/Audit). **Logische
Eindeutigkeit** je aktivem Schlüssel: zweiter aktiver Grant `(role, capability)`
bzw. zweite aktive Zuweisung `(person, role)` → `RbacError`; Scope-Änderung per
**revoke-then-grant** (append-only). Alle Guards **innerhalb** der Schreibsperre
(kein TOCTOU).

---

## 4. EMPFOHLENE Basis-Matrix (§11.3) — *nicht* im Build, für Deploy

> **Achtung:** Policy-Entscheidung der Chef-Ermittlerin. Konservativ gehalten
> (default-deny; Unter-Grant ist per Append heilbar, Über-Grant erzwingt einen
> Revoke-Beleg). §11.3-Anker sind fett gesetzt.

| Rolle | Fähigkeit (Scope) |
|---|---|
| **supervisor** | dashboard.view(alle), assignment.edit(alle), mentoring.view(alle), reports.review(alle), **reports.approve(alle)**, stats.export_sta(alle), workload.view(alle), support_history.view(alle), policy.view(alle), capacity.edit(alle), ops.view(alle), mycases.view(eigene), myhistory.view(eigene) |
| **investigator** | mycases.view(eigene), myhistory.view(eigene) |
| **support** | mentoring.view(eigene), support_history.view(eigene), myhistory.view(eigene) |
| **admin** | **feedback.moderate(alle)**, ops.view(alle), policy.view(alle) |
| **lector** | **reports.review(alle)**, myhistory.view(eigene) |
| **searchagent** | **evidence.fulltext_search(alle)**, myhistory.view(eigene) |

**Ausführung am Deploy (Beispiel, Akteur = erste supervisor-Person):**
```
python -m management.rbac.rbac_admin grant --role supervisor \
    --capability reports.approve --scope alle --actor h001
python -m management.rbac.rbac_admin grant --role lector \
    --capability reports.review --scope alle --actor h001
python -m management.rbac.rbac_admin grant --role searchagent \
    --capability evidence.fulltext_search --scope alle --actor h001
python -m management.rbac.rbac_admin grant --role admin \
    --capability feedback.moderate --scope alle --actor h001
# … übrige Zeilen der Tabelle analog
python -m management.rbac.rbac_admin assign-role --person h001 \
    --role supervisor --actor h001
```

**Kontrolle:** `list-grants`, `list-roles` zeigen den Ist-Stand; `catalog` die
gültigen Codes.

---

## 5. `event_types` (additiv)

`RBAC_GRANTED='rbac_granted'`, `RBAC_REVOKED='rbac_revoked'`,
`ROLE_ASSIGNED='role_assigned'`, `ROLE_REVOKED='role_revoked'` — in Klasse **und**
`ALL`-Frozenset. Das eingefrorene Vokabular wird nur **erweitert**, nie umbenannt
oder entfernt.

---

## 6. Tests (G01–G11 + A01, `tests/test_management_rbac_repo.py`)

grant atomar+gekoppelt (G01); ungültige Codes/Scope → Rollback (G02); Duplikat-
Guard (G03); `revoke_grant` Soft-Revoke+gekoppelt, Zeile bleibt (G04); revoke-
Fehler (G05); `assign_role` atomar (G06); assign-Fehler Person/Rolle/Duplikat
(G07); `revoke_role` Soft (G08); `verify_chain` grün nach allen Writes (G09);
`active_only`-Semantik (G10); default-deny-Ausgangszustand (G11); CLI
`grant`+`list-grants` Ende-zu-Ende (A01).

**Regression (`run_tests.py`):** Python **833** passed (821 + 12), 59 skipped,
3 subtests; JavaScript **467** passed, 1 skipped, 1 todo (kein JS geändert).

---

## 7. Deploy

**Keine Migration** in diesem Build. Die Basis-Matrix (§4) wird per
`rbac_admin`-CLI gesetzt (auditiert, `coordinator.db`, kein Migrationslock).

---

## 8. Anschluss (Schnitt c, Folge-Build 345)

`RbacResolver` (rein lesend): Rollen der Person aus `person_role` (aktiv) →
Vereinigung aktiver Grants → Fähigkeit bei ≥1 Grant, **Scope = weitester**
(`alle` > `eigene`). **Start-Check:** jede `catalog`-Capability existiert in der
DB (`rbac_capability`); fehlt eine → harter, handlungsleitender Fehler (GR1).

---

*Dokument-Ende · Detail-Bauplan Build 344 · v0.1 · 2026-07-10*
