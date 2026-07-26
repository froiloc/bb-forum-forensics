# Vermerk — Stiller Migrationsverlust durch die getrennten Nummernkreise

**Version:** 0.1 · **Datum:** 2026-07-26 · **Verfasser:** Claude (Instanz B)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Anlass:** Bau von Build 561 (AP-3E, Migration `m040_fulltext_release`)
**Betrifft:** `management/Parallelbetrieb_Welle_3_Aufgabenteilung_und_Vereinigung.md` §5 ·
`management/migrations/runner.py` · **Instanz A unmittelbar** (m035–m039)
**Status:** **Bau von Build 561 angehalten**, bis mc entschieden hat.

---

## 1. Der Befund in einem Satz

Die getrennten Migrations-Nummernkreise aus §5 (A: m035–m039, B: m040–m049)
verhindern eine Nummernkollision — **erzeugen aber genau den stillen Datenfehler,
den sie verhindern sollen**, sobald die höhere Nummer zuerst eingespielt wird.

---

## 2. Warum

`MigrationRunner` führt **keine Menge** angewandter Versionen, sondern einen
**Höchststand**:

```python
def current_version(self) -> int:
    row = self._con.execute("SELECT MAX(version) AS v FROM schema_migrations")…

def run(self):
    current = self.current_version()
    for mod in self._migrations:
        if mod.VERSION <= current:
            self._check_checksum(mod)
            continue
        self._apply(mod)
```
`management/migrations/runner.py:97-123`

`_check_checksum` schweigt zudem, wenn es **gar keine** Registry-Zeile zu der
Version gibt (`:207-209`: `if row is None: return`). Eine übersprungene, nie
angewandte Migration erzeugt daher **keine einzige Meldung**.

§5 des Parallelbetriebs-Dokuments beschreibt den Mechanismus für den Fall
*gleicher* Nummern völlig richtig. Übersehen wurde, dass ein Höchststand-Runner
auch bei *ungleichen* Nummern zuschlägt — nämlich immer dann, wenn die kleinere
Nummer später kommt.

---

## 3. Der Beleg (reproduziert, nicht hergeleitet)

Reproduktion gegen den **echten** `MigrationRunner`, synthetische Migrationen,
`coordinator`-Kette:

```
Lauf 1 (Instanz B liefert zuerst, nur m040): [40]
   current_version: 40
Lauf 2 (Instanz A liefert m035-m039 nach):   []
   current_version: 40
   Tabellen:                ['fulltext_release', 'schema_migrations']
   registrierte Versionen:  [40]
```

**Sieben Migrationen von Instanz A wurden übersprungen.** `run()` liefert `[]` und
protokolliert „Keine ausstehenden Migrationen" — also die Aussage *„alles
aktuell"* für einen Zustand, in dem sieben Schemaänderungen fehlen. Kein Fehler,
keine Warnung, kein Eintrag.

Das Skript liegt bei: `tools/diag_migrationsluecke.py`.

---

## 4. Wie weit die Wirkung reicht

* **Fehlende Tabelle/Spalte** — fällt irgendwann als Folgefehler an ganz anderer
  Stelle auf; die Ursache ist dann schwer zu finden.
* **Fehlender RBAC-Seed** — der Start-Check („jede Code-Capability existiert in
  der DB") schlägt an. Das ist der **einzige** Pfad, der heute überhaupt Alarm
  gibt, und er deckt nur Fähigkeiten ab.
* **Fehlende Datenmigration** — **fällt gar nicht auf.** Ab dem 01.07.2026 sind
  das Ermittlerdaten. Genau hier liegt der Schaden, den der Migrationsvorbehalt
  ausschließen soll.

Der Fehler ist **nicht auf den Parallelbetrieb beschränkt**: er trifft jede
Reihenfolge, in der eine kleinere Nummer nach einer größeren eingespielt wird.
Der Parallelbetrieb macht ihn nur zum Regelfall statt zum Ausnahmefall.

---

## 5. Was noch nicht passiert ist

**Stand jetzt ist nichts verloren.** `m040` ist gebaut, aber **nicht
ausgeliefert** und in keiner Datenbank angewandt. Solange `m040` in der VM nicht
läuft, ist der Zustand unauffällig herstellbar.

**Bitte `m040` nicht einspielen, bevor Punkt 6 entschieden ist.**

---

## 6. Vorschläge zur Entscheidung

### A · Den Runner reparieren *(mein Vorschlag)*

`run()` überspringt künftig, was **registriert** ist, statt was unterhalb des
Höchststands liegt:

```python
angewandt = {r[0] for r in con.execute("SELECT version FROM schema_migrations")}
…
if mod.VERSION in angewandt:
    self._check_checksum(mod); continue
```

Die Information liegt bereits vor — die Registry führt jede Version einzeln;
sie wird heute nur nicht benutzt. Zusätzlich: eine ausstehende Migration mit
`VERSION < MAX` wird beim Lauf **ausdrücklich gemeldet**. Sie ist ein
Betriebsbefund und kein Normalfall, auch wenn sie künftig sauber läuft.

*Dafür:* behebt die Ursache statt sie zu umgehen; wirkt auch außerhalb des
Parallelbetriebs; die Nummernkreise aus §5 können unverändert bleiben.
*Dagegen:* berührt geteilte Infrastruktur, die **keiner Zone** zugeordnet ist,
und wirkt auf alle drei Datenbankarten. Braucht eigene Regressionstests
(Reihenfolge, Idempotenz, Checksummenprüfung) und **eine ausdrückliche
Zuweisung durch mc** — ich fasse `runner.py` nicht ohne Auftrag an.

### B · Nummern erst beim Einspielen vergeben

Die Instanzen liefern Migrationen ohne feste Nummer; mc vergibt sie fortlaufend
beim Einspielen.
*Dafür:* kein Eingriff in Code.
*Dagegen:* `build.json` und die MD5-Summe der Migrationsdatei ändern sich **nach**
der Auslieferung — genau der Preis, den §14 Nr. 1 für Buildnummern vermeiden
wollte. Und das Grundproblem bleibt: läuft irgendwann doch etwas außer der
Reihe, schweigt der Runner weiterhin.

### C · Migrationen strikt serialisieren

Zu jedem Zeitpunkt hat höchstens **eine** Instanz offene Migrationen. Instanz A
liefert m035–m039 zuerst, danach bekommt B seine Nummer.
*Dafür:* kein Eingriff, sofort wirksam.
*Dagegen:* langsamste Variante, und sie verlässt sich auf Disziplin statt auf
einen Mechanismus. Die Falle bleibt scharf gestellt.

---

## 7. Wie Build 561 weitergeht

Der Rest von Build 561 hängt **nicht** an der Nummernfrage: Zweckcode-Vokabular,
Fähigkeit `fulltext.release`, die neuen EventTypes und der auditierte
Schreibpfad zur Freigabe sind davon unberührt. Nur die Migrationsdatei selbst
trägt die Nummer.

Ich kann daher entweder (i) 561 vollständig bauen und die Migration als
`m040` beilegen, **mit dem ausdrücklichen Vermerk, sie erst nach der
Entscheidung einzuspielen**, oder (ii) 561 ohne Migration bauen und sie als
eigene, kleine Auslieferung nachreichen, sobald die Nummer feststeht.

---

## 8. Ein zweiter, kleinerer Punkt aus demselben Anlass

Drei Testdateien halten Anker, die **beide** Instanzen anfassen müssen, und sie
stehen **nicht** in der Tabelle der gemeinsamen Dateien (§4):

| Datei | Anker |
| ----- | ----- |
| `tests/test_management_rbac_schema.py:182` | `assertEqual(len(cat_caps), 40)` |
| `tests/test_demo_seed.py:76` | `assertEqual(self._count("rbac_capability"), 40)` |
| `tests/test_management_dashboard.py:228-232` | die **vollständige Liste** `[1 … 32]` |

Die Fähigkeitszahlen sind einzelne Zeilen und mechanisch auflösbar. Die
**Migrationsliste** ist es nicht: A trägt `33…39` ein, B trägt `40` ein, beide an
derselben Stelle. Vorschlag für §4: eine Zeile je Instanz in einem mit
`# --- Build NNN ---` überschriebenen Block, und die Liste wird aus diesen
Blöcken zusammengesetzt statt als ein Literal geschrieben.

---

*Dokument-Ende · Vermerk Migrationslücke · v0.1 · 2026-07-26 · Instanz B*
