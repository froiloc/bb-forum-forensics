# Parallelbetrieb Welle 3 — Aufgabenteilung und Vereinigung

**Version:** 0.1 · **Datum:** 2026-07-26 · **Autor-Entwurf:** Claude (Instanz A), zur mc-Freigabe **Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH **Basis-Commit:** `05262cd` (v0.8.534c) · zzgl. der ausgelieferten, noch nicht gepushten v0.8.535

> **Dieses Dokument ist von JEDER Instanz zu Sitzungsbeginn zu lesen**, bevor
> die erste Zeile Code entsteht. Es ist die einzige Stelle, an der steht, wer
> welche Datei anfassen darf. Wer es überspringt, überschreibt fremde Arbeit —
> und zwar lautlos, weil Grundregel 7 vollständige Dateien verlangt.

---

## 1. Warum es dieses Dokument gibt

Ab jetzt arbeiten **mehrere Chat-Instanzen gleichzeitig** an demselben
Repository. Jede sieht nur ihren eigenen Arbeitsstand; keine bemerkt, was eine
andere gerade tut. mc ist die einzige Stelle, an der die Ergebnisse
zusammenlaufen.

**Die Gefahr ist konkret und schon eingetreten.** Am 2026-07-26 hat Instanz A
Build 535 auf v0.8.534 aufgesetzt, während mc parallel `cockpit.css` (+116
Zeilen) und `management_app.py` (+222 Zeilen) erweitert hat. Wäre die
Auslieferung ungeprüft eingespielt worden, wären beide Erweiterungen
verschwunden — **ohne Fehlermeldung, ohne Merge-Konflikt, ohne dass ein Test
angeschlagen hätte.** Genau das verhindert dieses Dokument.

Die drei Mechanismen dagegen:

1. **Eigentumszonen** — die meisten Dateien gehören genau einer Instanz (§3).
2. **Regeln für gemeinsame Dateien** — dort, wo es nicht anders geht (§4).
3. **Rebase vor jeder Auslieferung** — verbindlich, mit Prüfliste (§7).

---

## 2. Rollen und Zuteilung

| Instanz | Arbeitspaket                                                                    | Umfang     | Buildnummern |
| ------- | ------------------------------------------------------------------------------- | ---------- | ------------ |
| **A**   | **AP-3B** Dringlichkeits-/Erkenntnislage-Matrix, danach **AP-3C** QS & Metriken | ~4 Builds  | **536–559**  |
| **B**   | **AP-3E** Fallübergreifende Volltextsuche                                       | 4 Builds   | **560–579**  |
| **R1**  | Testhärtung (Existenz- → Wirkungsprüfungen)                                     | laufend    | **580–589**  |
| **R2**  | Beleg-Kette für Annotationen (`save_annotation` an `evidence_audit_log`)        | 1–2 Builds | **590–594**  |
| **R3**  | Vermerke und Nachträge (keine Produktivänderung im Webserver)                   | laufend    | **595–599**  |

**Nicht vergeben:** AP-3I (Abfrageagent). mc hat am 2026-07-26 festgelegt, dass
es ein **eigenes Arbeitspaket** ist und nicht zwischen die Wellen geschoben
wird. Es bleibt geparkt.

### 2.1 Warum diese Aufteilung — und nicht umgekehrt

**A behält die Fristen-Seite, weil dort unübertragbares Wissen liegt.** AP-3B
rechnet die X-Achse „Dringlichkeit" wesentlich aus der Restlaufzeit der
Verjährung (Gewicht 40 von 100). Diese Restlaufzeit ist seit Build 535 **nicht
mehr einheitlich belastbar**: sie kann auf einer festgestellten Tatzeit beruhen
(`feststellung='festgestellt'`, zitierfähig), auf Aktivitätsdaten
(`vorlaeufig`) oder auf einem Ersatzanker (`vorlaeufig`, und der Fristablauf ist
dort strukturell **zu früh**). Eine Prioritätszahl, die diese drei
gleichbehandelt, wäre genau die unmarkierte Schlussfolgerung, die dieses Projekt
nicht zulässt. Dazu kommen die Zustände `ohne_tatzeit` und `ohne_anker`, die **nicht** als „geringe Dringlichkeit" durchgehen dürfen — sie sind ungeprüft,
nicht unverdächtig. Wer AP-3A nicht gebaut hat, findet das in keinem Dokument in
dieser Schärfe.

**B bekommt AP-3E, weil es das sauberste Greenfield ist.** Eigene `search_index.db` (FTS5), eigene Tabelle `fulltext_release`, eigene Sicht,
eigener Endpunkt. Es liest alle `evidence_*.db` **read-only** und berührt weder `limitation*` noch `results*`. Die Überschneidung mit A besteht praktisch nur
aus den gemeinsamen Dateien aus §4.

**Ein glücklicher Nebeneffekt:** AP-3B schreibt **nichts** — mc hat festgelegt,
dass die Matrix nicht in `cases.priority` schreibt. Es braucht daher **keine
Migration**. Damit kollidiert A's erstes Paket nicht einmal im Nummernkreis der
Migrationen.

---

## 3. Eigentumszonen

Eine Datei in der Spalte „Zone" darf **ausschließlich** von der genannten
Instanz angelegt oder geändert werden. Alle anderen lesen sie höchstens.

| Zone          | Pfade                                                                                                                                                                                                                                      |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **A / AP-3B** | `management/results/priority_scorer.py` · `management/results/urgency_*.py` (neu) · `management/deadlines/**` · `management/server/static/cockpit_matrix.js` (neu) · `tests/test_urgency_*.py` · `tests/unit/test_cockpit_matrix*.test.js` |
| **A / AP-3C** | `management/qs/**` (neu) · `management/metrics/**` (neu) · `management/server/static/cockpit_qs.js` (neu) · `tests/test_management_qs_*.py` · `tests/unit/test_cockpit_qs*.test.js`                                                        |
| **B / AP-3E** | `management/search/**` (neu) · `db/search_index_db.py` (neu) · `management/server/static/cockpit_search.js` (neu) · `tests/test_management_search_*.py` · `tests/unit/test_cockpit_search*.test.js`                                        |
| **R2**        | `db/evidence_db.py` · `forensic_api/annotate.py` · `tests/test_forensic_api.py`                                                                                                                                                            |
| **mc**        | `management/server/static/cockpit_tk*.js`, `cockpit_assign*.js` und alles Übrige aus dem Oberflächen-Branch                                                                                                                                |

**Wer eine Datei braucht, die einer fremden Zone gehört, baut sie nicht um,
sondern meldet es an mc** und wartet. Ein Umbau in fremder Zone ist auch dann
unzulässig, wenn er offensichtlich richtig ist — die andere Instanz sieht ihn
nicht und arbeitet auf dem alten Stand weiter.

---

## 4. Gemeinsame Dateien und ihre Regeln

Diese Dateien müssen von mehreren Instanzen angefasst werden. Für jede gilt eine
Regel, die den Konflikt klein und mechanisch auflösbar hält.

| Datei                                       | Regel                                                                                                                                                                                             |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `build.json`                                | Vollständig ersetzen, mit der **eigenen Nummer aus §2**. Ein ZIP je Commit — nie zwei Auslieferungen in einen Commit mischen. Die Notiz der Vorgängerversion lebt in der Git-Historie weiter.     |
| `management/rbac/catalog.py`                | **Nur anhängen**, am Ende von `CAPABILITIES`, in einem mit `# --- Build NNN ---` überschriebenen Block. Die Zahl der ergänzten Fähigkeiten **muss in `build.json` stehen** (§6).                  |
| `management/audit/event_types.py`           | **Nur anhängen**, eigener Block vor `# --- reserviert für spätere Builds ---`, und die Werte zusätzlich am Ende von `ALL` eintragen.                                                              |
| `management/migrations/coordinator/`        | Neue Datei, Nummer aus dem eigenen Kreis (§5). Bestehende Migrationen sind unantastbar.                                                                                                           |
| `management/migrations/evidence/`           | Ebenso. **Zusätzlich Migrationsvorbehalt** — Eintrag im Datenmigrationsleitfaden ist Teil des Builds.                                                                                             |
| `management/server/management_app.py`       | Fachlogik gehört in ein **eigenes Modul** der eigenen Zone. Hier steht nur die Route, in einem mit `# --- Build NNN: <Paket> ---` überschriebenen Block, **am Ende** der jeweiligen Routen-Liste. |
| `management/server/static/cockpit.js`       | Genau **ein** `VIEW_CATALOG`-Eintrag je Sicht, **ans Ende** der Liste. Delta in `build.json` ausweisen.                                                                                           |
| `management/server/static/cockpit.css`      | **Ausschließlich ans Dateiende anhängen**, mit Kommentarkopf. Niemals in eine bestehende Regelgruppe einfügen.                                                                                    |
| `documents/Datenmigrationsleitfaden_AIW.md` | Neuer Abschnitt **am Ende**, Versionszeile und Änderungshistorie oben nachziehen.                                                                                                                 |

**Der gemeinsame Nenner aller Regeln lautet: am Rand arbeiten, nie in der
Mitte.** Ein Anhang am Dateiende lässt sich zusammenführen; ein Einschub in eine
bestehende Gruppe erzeugt einen Konflikt, den jemand von Hand auflösen muss —
und Handauflösungen sind die Stelle, an der Belege verlorengehen.

---

## 5. Nummernkreise

**Buildnummern:** s. Tabelle in §2. Lücken sind ausdrücklich zulässig und kein
Fehler — die Historie ist ohnehin schon nicht lückenlos (`534`, `534c`).

**Migrationen — der gefährlichste Kreis.** Zwei Migrationen mit derselben `VERSION` sind kein Merge-Konflikt, sondern ein **stiller Datenfehler**: der
Runner wendet die erste an, registriert die Version, und überspringt die zweite
für immer.

| Instanz | coordinator     | evidence    | forensic / assets |
| ------- | --------------- | ----------- | ----------------- |
| **A**   | **m033 – m039** | m004 – m005 | nach Rücksprache  |
| **B**   | **m040 – m049** | m006 – m007 | nach Rücksprache  |
| **R2**  | m050 – m052     | m008        | —                 |

Stand `05262cd`: coordinator bis **m032**, evidence bis **m003** (durch das
gelieferte Build 535 unverändert).

---

## 6. Ankerarithmetik — die Stelle, an der Parallelbetrieb wehtut

Mehrere Tests halten **Zahlen** fest, damit eine Erweiterung nicht unbemerkt
mitläuft. Genau diese Tests brechen im Parallelbetrieb doppelt.

| Anker                       | Stand `05262cd` | Ort                                                               |
| --------------------------- | --------------- | ----------------------------------------------------------------- |
| Capabilities                | **40**          | `tests/test_management_rbac_schema.py`, `tests/test_demo_seed.py` |
| Rollen                      | 8               | ebenda                                                            |
| `VIEW_CATALOG`              | **37**          | `tests/unit/test_cockpit_nav.test.js`                             |
| coordinator-Migrationsliste | bis 32          | `tests/test_management_dashboard.py`                              |
| evidence-Kette              | `[1, 2, 3]`     | `tests/test_management_migration_executor.py`                     |

**Verbindliche Regel:**

1. Jede Instanz schreibt in ihre `build.json` einen Satz der Form:
   
   > `ANKERDELTA: +2 Capabilities (40 -> 42), +1 VIEW_CATALOG (37 -> 38), coordinator-Kette bis m034.`

2. Der Anker wird **auf den Stand angepasst, der beim Rebase tatsächlich
   vorgefunden wurde** — nicht auf den, der beim Baubeginn galt.

3. Wer beim Rebase feststellt, dass ein Anker sich **ohne eigenes Zutun** verschoben hat, korrigiert ihn und **vermerkt das**. Ein stillschweigend
   angepasster Anker ist ein aufgegebener Anker.

> **Nie einen roten Anker „reparieren", ohne zu wissen, warum er rot ist.** Er
> kann durch die eigene Erweiterung ausgelöst sein — dann ist die Anpassung
> richtig. Er kann aber auch anzeigen, dass eine fremde Änderung eingespielt
> wurde, die man gerade zu überschreiben im Begriff ist. Der Unterschied ist mit `git diff origin/master -- <datei>` in zehn Sekunden geklärt.

---

## 7. Ablauf je Auslieferung (verbindlich)

Diese Prozedur hat sich beim Neuaufsetzen von Build 535 bewährt und ist ab jetzt
Pflicht — **unmittelbar vor dem Packen**, nicht zu Sitzungsbeginn.

```
1.  git fetch
2.  git log --oneline -1 origin/master          # Stand notieren
3.  Für JEDE Datei des Builds:
       git diff --stat <Baubasis> origin/master -- <datei>
    -> leer  : Datei ist unberührt, eigene Fassung kann übernommen werden
    -> nicht leer: Datei ist gewandert. NICHT kopieren.
                   Eigene Änderung gezielt NEU anbringen.
4.  git diff origin/master        # ansehen: enthält er GENAU die eigenen Änderungen?
5.  Anker gegen den NEUEN Stand prüfen und anpassen (§6)
6.  Regression NEU messen — und den Basiswert ebenfalls, in einem Worktree:
       git worktree add --detach /tmp/basis origin/master
       (cd /tmp/basis && python -m pytest tests/ -q)
       git worktree remove --force /tmp/basis
7.  build.json mit ANKERDELTA-Satz schreiben, MD5SUMS erzeugen
8.  ZIP packen, Archivinhalt gegen MD5SUMS gegenprüfen
```

**Schritt 3 ist der eigentliche Schutz.** Er kostet pro Datei Sekunden und ist
der Unterschied zwischen „Build eingespielt" und „fremde Arbeit gelöscht".

---

## 8. Der Vereinigungsprozess bei mc

**mc ist die einzige Stelle, die committet und pusht** (Festlegung 2026-07-26).
Damit ist die Vereinigung serialisiert, und das ist gut so — ein verteiltes
Merge-Modell würde hier nichts beschleunigen und alles gefährden.

```
        Instanz A  ──ZIP──┐
                          ├──►  mc: einspielen ► Regression ► commit ► push
        Instanz B  ──ZIP──┘                                              │
                          ◄──── "neuer Stand ist <commit>" ──────────────┘
```

**Je Auslieferung, in dieser Reihenfolge:**

1. **Ein ZIP auspacken** — nie zwei gleichzeitig.
2. **MD5 gegenprüfen** (`md5sum -c MD5SUMS_BuildNNN.txt`). Weicht eine Datei ab,
   wurde parallel gearbeitet: **abbrechen und zurückmelden**.
3. **`ANKERDELTA` aus `build.json` gegen die Ist-Zahlen halten.** Stimmt die
   Arithmetik nicht, ist der Build auf einem veralteten Stand gebaut worden.
4. **Volle Regression in der VM**, einschließlich `tests/test_editor_renderer.py` (die im Container ausgeklammert bleibt).
5. **Committen und pushen.**
6. **Beiden Instanzen den neuen Commit nennen.** Das ist der Taktgeber: erst
   danach darf die jeweils andere Instanz ihre nächste Auslieferung packen.

**Bei einem Konflikt entscheidet der Zeitpunkt der Meldung, nicht die Größe der
Änderung.** Wer zuerst geliefert hat, wird eingespielt; die andere Instanz
rebased. So gibt es keine Verhandlung darüber, wessen Arbeit „wichtiger" ist.

---

## 9. Prüfliste zum Sitzungsbeginn (jede Instanz)

- [ ] Dieses Dokument gelesen; die eigene Zone (§3) und den eigenen
  Nummernkreis (§5) notiert.
- [ ] `claude/UEBERGABE_Builds533-535_AP3A_Abgeschlossen.md` gelesen —
  insbesondere §3 (Ankerstände) und §5 (betriebliche Voraussetzungen).
- [ ] `management/Entscheidungen_2026-07-26_AP3B_AP3C_AP3E.md` gelesen — dort
  stehen die sechs Festlegungen, die die Wellen-3-Pakete entsperrt haben.
- [ ] Repository frisch geklont, `git log --oneline -1` **als Baubasis
  notiert** und im ersten `build.json` genannt.
- [ ] `pip install pytest --break-system-packages`, `npm install`.
- [ ] Beide Regressionen **einmal zu Beginn** gemessen — sonst weiß man später
  nicht, welche Fehlschläge man selbst verursacht hat.

---

## 10. Was ausdrücklich NICHT parallel läuft

- **Migrationen in derselben DB-Art zur selben Zeit.** Die Nummernkreise
  verhindern die Kollision, nicht aber die inhaltliche Überschneidung. Wer eine
  evidence-Migration plant, meldet es vorher an — die Beweismitteldatenbanken
  stehen unter Migrationsvorbehalt.
- **Änderungen am RBAC-Kern** (`rbac_resolver.py`, `rbac_repo.py`, `rbac_admin.py`). Der Katalog wird angehängt, der Mechanismus nicht angefasst.
- **Änderungen an der Audit-Kette** (`audit_log.py`, `hashing.py`, `evidence_audit_log.py`, `coordinator_writer.py`, `evidence_writer.py`). Die
  Hash-Formel ist ab Zeile 1 der Kette eingefroren; eine Änderung dort zerstört
  den Manipulationsnachweis rückwirkend.
- **Umbenennungen und Verschiebungen** irgendeiner Datei. Sie erzeugen bei jeder
  anderen Instanz einen Konflikt, den nur mc sehen kann.
- **`run_tests.py` und die Testinfrastruktur.**

---

## 11. Auftrag Instanz B — AP-3E, Volltextsuche

**Damit B kalt starten kann, steht hier alles Nötige.**

**Grundlage:** `management/Klaerung_AP3E_Freigabemodell_Volltextsuche_v0_2.md` —
vollständig lesen, insbesondere §2 (was die Funktion tut) und §6 (was in jedem
Modell gilt). Die Modellwahl ist **entschieden**; §4 dient nur noch dem
Verständnis der Begründung.

**Die Festlegungen (mc, 2026-07-26 — nicht mehr verhandelbar):**

1. **Modell B, zweistufig.** Stufe 1 = Trefferlage (Fall, Trefferzahl, Art,
   Zeitraum) **ohne Textausschnitt**, für alle Berechtigten frei. Stufe 2 =
   Inhalt sofort bei **eigenen** Fällen, sonst gesperrt mit
   begründungspflichtiger Anfrage an die Chef-Ermittlerin.
2. **Neue Tabelle `fulltext_release`** in `coordinator.db`: wer, welcher Fall,
   Zweck, erteilt von, wann, Widerruf. **Eine Freigabe je Fall + Person**, nicht
   je Abfrage — sonst wird die Chef-Ermittlerin zum Nadelöhr.
3. **`evidence.fulltext_search` ist NICHT scope-fähig**, default-deny. Grant
   zunächst **nur `supervisor`**. Die Rolle `searchagent` existiert im Katalog
   (`management/rbac/catalog.py:62`), bleibt aber **ohne Grant**.
4. **Zweckangabe bei JEDER Abfrage** — Stufe 1 und Stufe 2 —, und zwar als **Auswahlliste fester Codes**, nicht als Freitext. Vorschlag zur Bestätigung: `kreuzbezug_nickname`, `alias_pruefung`, `wiedervorlage`, `sonstiges`; bei `sonstiges` ist ein Freitext Pflicht. Der Anteil `sonstiges` ist die Kennzahl
   dafür, ob die Liste vollständig ist.
5. **Jede Abfrage ist ein Beleg** — neuer `EventType` `FULLTEXT_SEARCHED`, **auch der Leerbefund**, sonst ließe sich spurenfrei sondieren.
6. **Rein lesend.** Alle `evidence_*.db` mit `mode=ro` öffnen (Muster `management/reports/reports_repo.py:122`). Der Migrationsvorbehalt ist nicht
   berührt.
7. **Der FTS5-Index liegt außerhalb der Beweismitteldatenbanken** — eigene,
   jederzeit verwerfbare `search_index.db`. **Hilfsmittel, kein Beweismittel**;
   jeder Treffer wird vor der Anzeige gegen die Quelle verifiziert.
8. **Kein stiller Teiltreffer.** Nicht lesbare oder fehlende `evidence_*.db` werden gezählt und benannt. Und: jede Antwort nennt den **Indexzeitpunkt** und die Zahl der seit dem Index veränderten Datenbanken.

**Was B sich sparen kann, weil es schon dasteht:**

- Ein **auditierter Schreibpfad im Forensik-Server** ist gebaut und getestet — `forensic_api/results_endpoint.py` ist die Blaupause für RBAC-Gating
  außerhalb des Cockpits (403 **mit Begründung**, „ohne Handelnden wird NICHTS
  geschrieben").
- Für Schreibvorgänge in `coordinator.db` ist `CoordinatorWriter.audited_write` der einzige zulässige Weg (Write + Beleg in **einer** Transaktion).
- Für Aggregate über alle `evidence_*.db` gibt es ein erprobtes Muster mit
  Fehlerzählung: `management/stats/annotation_stats_repo.py:112-154`.
- **Es gibt im ganzen Repository noch keine FTS5-Nutzung** (Recherche
  2026-07-25). B ist der erste — Aufbau und Pflege des Index sind zu entwerfen,
  nicht abzuschreiben.

**Vorgeschlagener Build-Schnitt** (B darf ihn ändern, soll die Änderung aber
begründen): 560 Indexaufbau + `search_index.db`; 561 Migration `fulltext_release` + Recht + EventType; 562 Endpunkte Stufe 1/Stufe 2 +
Freigabe-Schreibpfad; 563 Sicht `cockpit_search.js`.

---

## 12. Auftrag Instanz A — AP-3B, danach AP-3C

**AP-3B (Buildnummern ab 536).** Grundlage `management/Klaerung_AP3B_Gewichtungsmodell_261_v0_1.md`. Entschieden sind:
Achsen **Dringlichkeit** (X) und **Erkenntnislage** (Y), **keine „Schwere"-Achse** (§ 261 StPO); Gewichte unverändert aus §4; Darstellung als **Quadrant**, Zahlen
im Aufklappbereich; **kein Schreiben** in `cases.priority`.

**Der Punkt, an dem AP-3B mit AP-3A verzahnt ist und den A nicht übersehen darf:** Seit Build 535 kann die Restlaufzeit auf drei verschieden belastbaren Grundlagen
beruhen — festgestellte Tatzeit (zitierfähig), Aktivitätsdaten (vorläufig) und
Ersatzanker (vorläufig, Fristablauf strukturell **zu früh**). Ein
Dringlichkeitswert, der alle drei gleich gewichtet, behauptet eine Sicherheit,
die es nicht gibt. Ebenso dürfen `ohne_tatzeit` und `ohne_anker` **nicht** als
geringe Dringlichkeit erscheinen: diese Fälle sind ungeprüft, nicht
unverdächtig. Wie das gelöst wird, ist zu entwerfen und mc vorzulegen — dass es
gelöst werden muss, steht fest.

**AP-3C (danach).** Bauplan `management/Bauplan_AP3C_Builds527-529_QS_Metriken_v0_1.md` — **die
Buildnummern darin sind veraltet**, der Inhalt gilt. Zu ergänzen: geschichtete
Ziehung, supervisor-gesetzte relative Menge mit absoluter Höchstgrenze, Ziehung
als **Vorschlag** mit protokollierter Abweichung, Ausgleichshinweis mit **ECharts Nested Pies**, `qs.edit` an `supervisor` **und** `lector` mit
serverseitiger Selbstprüfungssperre.

---

## 13. Aufträge der R-Instanzen

**R1 — Testhärtung.** Sucht Tests, die die *Existenz* einer Struktur prüfen, und
macht daraus Prüfungen ihrer *Wirkung*. Vorbilder aus Build 532/533: TZ10 prüft
nicht, dass ein Index existiert, sondern dass SQLite ihn **benutzt** (`EXPLAIN QUERY PLAN`); EA08 prüft nicht, dass eine Hash-Kette da ist, sondern
dass `verify_chain()` eine **Manipulation aufdeckt**. **Nur Testdateien**, **keine Produktivänderung**, **keine Datei aus einer fremden Zone**. Findet R1
dabei einen echten Fehler, wird er **gemeldet, nicht behoben** — die Behebung
gehört der Zone, in der er liegt.

**R2 — Beleg-Kette für Annotationen.** Der größte offene Befund dieser Sitzung: `save_annotation` (`db/evidence_db.py:847-949`) schreibt und committet direkt
(`:947`), **ohne Gateway und ohne Beleg**. Die zentrale Ermittlerhandlung des
ganzen Werkzeugs hinterlässt keinen Datenbankbeleg. Seit Build 533 gibt es das
Fundament dafür: `evidence_audit_log` (Migration m003) und `management/gateway/evidence_writer.py`. R2 schließt `save_annotation`, `delete_annotation` und `restore_annotation` daran an. **Vor dem Bau zu
klären:** ob die Umstellung rückwirkend gelten soll (sie kann es nicht — die
Kette beginnt mit ihrer Genesis) und wie das in der Akte benannt wird.
Der Modulkopf von `evidence_writer.py` beschreibt die beiden Fallen
(geteilte Verbindung, `isolation_level`) vollständig.

**R3 — Vermerke und Nachträge.** Ohne Produktivcode im Webserver:

- `Klaerung_AP3A_Verjaehrungsparameter_v0_1.md` §4 → v0.2 korrigieren (die
  Aussage, es gebe keinen Zeitstempel zu geteilten Dateien, ist falsch; `uid_shares.posted_ts` existiert samt Index).
- Prepper-DDL: zwei Zeitindizes ergänzen
  (`management/Vermerk_Prepper_DDL_Zeitindizes_v0_1.md`) — **anderes
  Repository** (`aiw_sqlite_prepper`), eigener Nummernkreis dort.
- Platzhalter `user.activity_range` in bestehenden `templates.db`.
- Migrations-Workflow für die Beweismitteldatenbanken weiter ausarbeiten.

---

## 14. Offene Punkte dieses Dokuments

1. **Die Nummernkreise sind ein Vorschlag.** Wenn mc lieber durchgehend
   fortlaufende Buildnummern hätte, müsste die Nummer stattdessen **beim
   Einspielen** vergeben werden — dann ändert sich `build.json` nach der
   Auslieferung und die MD5-Prüfung dieser einen Datei entfällt. Ich halte die
   Kreise für den kleineren Preis, aber es ist mcs Entscheidung.
2. **R2 ist ein Vorschlag mit Tragweite.** Die Annotationen an die Beleg-Kette
   anzuschließen berührt den meistgenutzten Schreibpfad des Werkzeugs im
   Produktivbetrieb. Wenn das zu viel auf einmal ist, gehört R2 hinter Welle 3.
3. **Nicht abgedeckt: was passiert, wenn zwei Instanzen dieselbe Erkenntnis
   gewinnen** und beide dieselbe Datei anlegen wollen. Bisher fängt das die
   Zoneneinteilung ab; sollte es doch vorkommen, entscheidet mc nach §8 (wer
   zuerst geliefert hat).

---

*Dokument-Ende · Parallelbetrieb Welle 3 · v0.1 · 2026-07-26 · zur mc-Freigabe*
