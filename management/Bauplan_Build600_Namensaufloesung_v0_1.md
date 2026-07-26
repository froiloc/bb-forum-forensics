# Bauplan Build 600 — Namensauflösung in der Alias-Sicht

**Baustelle 7 (Management-Cockpit) · Zweig `feature/b7-alias-namensaufloesung`**
**Basis:** `209c86b` (v0.8.535) · Stand: 2026-07-26 · Version v0.1

> **Buildnummer:** 600 ist ein **Vorschlag**. mc vergibt die Nummer beim
> Einspielen (Festlegung 2026-07-26). Sie liegt oberhalb aller in
> Parallelbetrieb Welle 3 §2 vergebenen Kreise und kollidiert daher mit keiner
> Instanz. Begründung gegen einen Text-Platzhalter: §7 dieses Dokuments.

---

## 1. Auftrag

> „Unsere Ermittler sind mit den Namen der Forennutzer vertraut, aber nicht mit
> den `user_id` oder `subject_id`. […] In jedem Fall ist es den Anwendern nicht
> zuzumuten, die `subject_id` zu kennen. Obendrein wäre es großartig, wenn
> hinter oder unter dem Eingabefeld `subject_id` der aufgelöste Benutzername
> angezeigt werden würde." (mc, 2026-07-26)

---

## 2. Die Schlüsselfrage — geprüft, nicht angenommen

**Ist `known_users.user_id` dasselbe wie die `subject_id` der Fallakte?**
**Ja — für Realnutzer, und nur die stehen dort.**

Zwei Belege, die zusammen die Antwort tragen:

1. Entscheidung *„Ermittlungsschlüssel `subject_id` für Nutzer ohne
   `users.id`"* vom 2026-07-20, §3: „**Realnutzer** (`user_id` bekannt):
   `subject_id = users.id` — unverändert."
2. `default.db` wird aus genau dieser Tabelle befüllt:
   `aiw_sqlite_prepper/stage1/phase_b_exporter.py`, Schritt 1 — „Export aller
   Nutzer aus MariaDB `users` → `id`, `username`".

**Es wird also nicht umgerechnet, und es darf auch nicht umgerechnet werden.**
Test **NR02** hält das fest: läge hier irgendwo ein Offset, fände er nichts.

---

## 3. Was es *nicht* gibt — und warum die Oberfläche das sagt

mc hatte gefragt, ob es eine Datenbank **aller** Nutzernamen gibt, also auch
der nur über die 100a-Maßnahme belegten. **Geprüft: nein.**

Die **Geister** — Namen ohne Forenkonto, beim Erstlauf 2026-07-20 immerhin
**552.334 von 795.972** — tragen eine `subject_id` aus dem Band oberhalb
1.000.000.000 und stehen in **MariaDB** (`mat_usernames` / `mat_subject_map`).
In **keiner** SQLite-Datei dieses Servers: der Prepper exportiert nach
`default.db` ausschließlich `users`, und `known_aliases` wird dort sogar
ausdrücklich **leer** angelegt („keine MariaDB-Quelle",
`phase_b_exporter.py:1571`).

**Folge für die Oberfläche.** Jede Antwort trägt den Satz, dass ein Leerbefund

> „in den **abgefragten** Quellen nicht gefunden"

heißt und **nicht** „gibt es nicht". Und eine Kennung im Geisterband bekommt
die Erklärung dazu, statt als „unbekannt" durchzugehen (Test **NR03**). Ein
Export von `mat_subject_map` nach `default.db` wäre nachrüstbar — er gehört
aber in das **andere** Repository (`aiw_sqlite_prepper`) und damit in eine
fremde Zone.

---

## 4. Die Kaskade und ihr Preis

Festlegung mc 2026-07-26: **erst die Fallakte, dann die globale Namensliste.**
So umgesetzt.

**Ergänzt habe ich genau eine Zahl:** die nicht abgefragte Stufe wird
**gezählt** und die Zahl mitgeliefert (`weitere_treffer`) — **gelistet** wird
sie nicht. Grund: eine Kaskade, die schweigt, sieht aus wie ein vollständiges
Ergebnis, und der gesuchte Zweitaccount ist genau der Treffer, den sie
verschweigen würde. Kosten: eine `COUNT`-Abfrage.

Die Ergänzung ist **in einer Zeile zu streichen** (`NameResolver.suchen`,
Aufruf von `_zaehle_forenkonten`) und im Modulkopf als *meine* Ergänzung
gekennzeichnet, nicht als Auftrag. Tests **NR05** und **AS21**.

Unterhalb der Mindestlänge wird auch nicht gezählt: `None` heißt dort
**„nicht abgefragt"** und nicht `0`.

---

## 5. Was die Sicht bekommt

| Ort | Was passiert |
|---|---|
| Unter dem Feld `subject_id` | Der aufgelöste Benutzername **mit seiner Herkunft**. Kontrollanzeige: sie sagt, ob die richtige Nummer erwischt wurde, **bevor** ein Beleg entsteht. Entprellt (350 ms). |
| Daneben | **Namenssuche**: Namen eintippen, Treffer wählen → Kennung wird gesetzt **und sofort rückwärts bestätigt**. Zwei Anzeigen, eine Wahrheit. Damit muß die Nummer nie bekannt sein — der eigentliche Auftrag. |
| Unter der Katalogsuche | Dieselbe Auflösung. Der Katalog kennt nur **erfaßte** Aliasse; die Suche meint aber meist den Namen als solchen. Ein Klick auf einen Treffer führt in den Katalog **dieses** Kontos. |

**Drei Zustände, die nicht verwechselt werden dürfen** (`aufloesungText`,
Test **AS20**):

* **gefunden** — grün, **mit Quelle**. Ein Name aus der Fallakte ist ein
  anderer Beleg als einer aus der globalen Namensliste.
* **nicht gefunden** — gelb, mit dem Zusatz „in den abgefragten Quellen".
* **nicht abfragbar** — gelb, fett, **mit Grund**.

Eine fehlende oder unlesbare `default.db` darf **nie** wie ein Leerbefund
aussehen; die Fallakte antwortet in diesem Fall weiter (Test **NR04**). Die
Prüfung steht **vor** jeder Nutzung — die Lehre aus Build 534/US05, daß
`sqlite3.connect()` die Datei gar nicht öffnet und `file is not a database`
erst bei der ersten Abfrage anfällt.

---

## 6. Nebenkorrektur an sieben Dateien aus Build 534

In `master` steht in den Modulköpfen von `uid_stats_repo.py`,
`cases_batch_repo.py`, `cases_repo.py`, `coordinator_writer.py`,
`management_app.py`, `test_assignment_batch.py`, `test_uid_stats_repo.py` und
`cockpit.js` weiterhin **„Build 533"** bzw. `v0.8.533`.

Diese Arbeit ist als **Build 534** eingespielt worden (`aff1d88`); upstream ist
533 aber `db/tatzeit_repo.py` aus AP-3A — **zwei verschiedene Dinge unter einer
Nummer**. Die Berichtigung war in Commit `e81aa69` vorbereitet, aber nicht
mitgepusht worden.

Es sind **ausschließlich** Kommentare und Versionszeilen. Kein
Verhaltensunterschied.

---

## 7. Zur Buildnummer — warum kein Text-Platzhalter

mc vergibt die Nummer beim Einspielen. Ein Platzhalter wie `"BUILD-TBD"` im
Feld `build` wäre naheliegend, aber gefährlich:
`management/export/context_builder.py:38-44` liest den Wert mit `int()` und
fällt bei einem Fehler **still auf 0** zurück. Aus dem Platzhalter würde in der
**Aktenfassung** die Buildnummer 0 — und eine falsche Nummer in einer Akte ist
schlimmer als eine vorläufige.

Deshalb: eine **numerische** Nummer als Vorschlag, plus das Feld
`build_nummer_vorbehalt` in `build.json`, das den Vorbehalt ausspricht. Wird
die Nummer beim Einspielen geändert, ist **nur** die MD5 von `build.json` neu
zu bilden — die Zahl steht sonst ausschließlich in Kommentaren.

---

## 8. Einhaltung des Parallelbetriebs (Welle 3)

| Regel (§) | Umsetzung |
|---|---|
| §4 `management_app.py` | Route **am Ende** der GET-Liste, in einem `# --- Build 600: … ---`-Block. Fachlogik in einem **eigenen** Modul. |
| §4 `cockpit.css` | Ausschließlich **ans Dateiende** angehängt, mit Kommentarkopf. |
| §4 `build.json` | Vollständig ersetzt, mit `ANKERDELTA`-Satz. |
| §6 Ankerarithmetik | **ANKERDELTA: keine.** +0 Capabilities (40 → 40), +0 `VIEW_CATALOG` (37 → 37), coordinator-Kette bis m032, evidence-Kette `[1, 2, 3]`. Der Endpunkt hängt am **bestehenden** Recht `crossref.view`. |
| §7 Ablauf | `git fetch` unmittelbar vor dem Packen; jede Datei gegen `origin/master` geprüft (alle unberührt); Basis-Regression im Worktree gemessen. |
| §10 Nicht-parallel | RBAC-Kern, Audit-Kette, Migrationen, `run_tests.py` **unangetastet**. Keine Umbenennung, keine Verschiebung. |

---

## 9. Prüfstand

| Suite | Basis `209c86b` | Build 600 | Δ |
|---|---|---|---|
| pytest | 2078 / 65 skip / 33 subtests | **2090** / 65 / 33 | +12 (`NR01`–`NR12`) |
| vitest | 1242, 102 Dateien | **1248**, 102 Dateien | +6 (`AS20`–`AS25`) |

Basiswerte in einem `git worktree` auf `origin/master` gemessen (§7 Schritt 6).

**Umgebungsvorbehalt:** Container mit Python 3.13.
`tests/test_editor_renderer.py` verlangt ≥ 3.12 (PEP 701) und lief hier mit.
Maßgeblich bleibt `python run_tests.py` in der VM.

---

## 10. Befund zur Protokollierung — nicht von mir behoben

`db/default_db.py:284` behauptet im Kommentar einen Index

```
known_users_username_idx ON known_users(username COLLATE NOCASE)
```

Das DDL des Preppers legt ihn **ohne** `NOCASE` an
(`phase_b_exporter.py:220`: `ON known_users (username)`). Zwei Aussagen über
dieselbe Tatsache; die falsche steht im Kommentar.

**Wirkung:** die case-insensitive Suche kann den Index auch bei einer
Präfixsuche nicht nutzen — ein **Leistungs-**, kein Richtigkeitsproblem. Bei
477.000 Zeilen ist das der Grund für die Mindestlänge von 4 Zeichen.

**Gemeldet statt behoben:** `db/` ist eine fremde Zone (Parallelbetrieb §3).

---

## 11. Bewußt **nicht** gebaut (kein stiller Verzicht)

1. **Die Namensauflösung steht nur in der Alias-Sicht.** Zuweisung,
   Kreuzbezug und Identitäts-Gruppen zeigen weiterhin bloße Kennungen. Der
   Endpunkt ist da; das Anklemmen je Sicht ist ein eigener Schritt — und in
   der Zuweisung wäre es eine Spalte, in den Identitäts-Gruppen eine Zeile,
   also je eine eigene Entscheidung.
2. **Keine Namensspalte im Aktenexport.**
3. **Keine Auflösung für Geister außerhalb der Fallakte** (§3).
4. **Keine Vervollständigung während des Tippens** in der Namenssuche. Bei
   477.000 Zeilen ohne nutzbaren Index wäre jede Tastenanschlag-Abfrage ein
   Volldurchlauf. Die Suche läuft auf Knopfdruck bzw. Eingabetaste.

---

## 12. Dateien

**Neu**

* `management/crossref/name_resolver.py`
* `tests/test_name_resolver.py`
* `management/Bauplan_Build600_Namensaufloesung_v0_1.md` (dieses Dokument)

**Geändert**

* `management/server/management_app.py` — `GET /api/names` + Import
* `management/server/static/cockpit_alias.js` — beide Richtungen + Namensblock
* `management/server/static/cockpit.js` — `loadAlias`-Verdrahtung, `state`
* `management/server/static/cockpit.css` — Abschnitt „Build 600" (am Ende)
* `tests/unit/test_cockpit_alias.test.js` — `AS20`–`AS25`
* `build.json`

**Nebenkorrektur (nur Kommentare/Versionszeilen, §6)**

* `management/stats/uid_stats_repo.py`, `management/cases/cases_batch_repo.py`,
  `management/cases/cases_repo.py`, `management/gateway/coordinator_writer.py`,
  `tests/test_assignment_batch.py`, `tests/test_uid_stats_repo.py`
  (sowie `management_app.py` und `cockpit.js`, die ohnehin geändert sind)
