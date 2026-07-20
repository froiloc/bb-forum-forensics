# Bauplan Build 409 — Frühwarnung Journal-Stempel, präziser Fehlertext, Test-Fix

**Baustelle:** 2 (Webserver) · **Version:** v0.7.409 · **Datum:** 2026-07-14
**Autoritativ:** `mc` vom 2026-07-14 · **Status:** umgesetzt, Regression grün

---

## 1. Was wir gelernt haben (belegt)

Build 408 hat den Journalmodus zentralisiert — der Start scheiterte trotzdem weiter. Die zweite Diagnose hat gezeigt, **warum**:

| Befund | Beleg |
|---|---|
| Das Share ist **in Ordnung** | Diagnose 2, Testmatrix auf einer **Kopie der echten** `evidence`-DB im selben Verzeichnis: **alle sieben** Fälle grün (lesen, schreiben, `journal_mode=delete`, `mmap_size=0`, `locking_mode=EXCLUSIVE`) |
| Die **mmap-Hypothese ist widerlegt** | `PRAGMA mmap_size` ist in SQLite 3.50.4 ohnehin `0` — memory-mapped I/O war nie aktiv |
| `locking_mode=EXCLUSIVE` wird **nicht gebraucht** | ergibt sich aus derselben Matrix |
| Ursache war **eine einzelne Datei** | `evidence_524888.db` war als einzige noch WAL-gestempelt. Um WAL zu verlassen, muss SQLite die WAL-Datei auschecken — und braucht dafür die `-shm`, die auf einem Netzlaufwerk nicht anzulegen ist. Daher `disk I/O error` **auch bei** `journal_mode=delete` |

**Zwei Messfehler auf meiner Seite, die diese Runde gekostet haben:** Diagnose 1 maß gegen synthetische Probe-DBs statt gegen die echten Dateien. Diagnose 2 griff sich stillschweigend die alphabetisch **erste** `evidence_*.db` — und damit die falsche. Beide Lehren sind in diesen Build eingebaut.

---

## 2. Umsetzung

### 2.1 Frühwarnung: `core/startup_checks.py::_check_journal_stamps()` (neu)

* Liest für **jede** DB die SQLite-Header-Bytes 18/19 — **ohne SQLite**, ein `open()` und 100 Bytes. Das ist zwingend: eine WAL-gestempelte Datei lässt sich auf dem Netzlaufwerk gar nicht erst öffnen.
* Bricht mit **Klartext und Handlungsanweisung** ab, wenn eine WAL-gestempelte DB auf einem Netzlaufwerk liegt — inklusive des exakten Konverteraufrufs.
* Läuft **vor** Schema- und Integritätsprüfung (die öffnen die `forensic_db` per SQLite und würden sonst mit rohem `disk I/O error` sterben). Die Reihenfolge ist per Test **am Quelltext von `run_all()`** abgesichert, nicht per Kommentar.
* **Kein Fehlalarm:** Auf lokaler Platte ist eine WAL-DB völlig in Ordnung; bei unbekannter Laufwerksart wird nichts behauptet.
* Zusätzlich: erzwungenes `db.journal_mode: "wal"` auf einem Netzlaufwerk bricht mit Klartext ab.

### 2.2 `db/journal_policy.py` — zwei neue Helfer, ein korrigierter Text

* `is_network_path()` — UNC-Präfix (plattformunabhängig) und Windows `GetDriveTypeW` (`DRIVE_REMOTE == 4`). Liefert `None`, wo keine Aussage möglich ist: **kein Raten**.
* `journal_stamp()` — Header-Byte 18 ohne SQLite.
* `NETWORK_HINT` korrigiert: Der alte Text riet zu `db.journal_mode: "delete"` — was beim Auftreten des Fehlers **bereits gesetzt war**. Er nennt jetzt die tatsächliche Ursache (WAL-gestempelte **Datei**) und den Konverteraufruf.

### 2.3 Test-Fix (das rote `run_tests.py` in der VM)

`tests/test_journal_policy.py` hing an `caplog`. Der Projekt-Logger hat `propagate=False`, deshalb blieb `caplog` in der VM leer — **obwohl die Meldung kam** (sie stand im `Captured stderr`). Die Tests geben der echten Funktion jetzt über den vorhandenen `log=`-Parameter eine Logger-Attrappe mit. Kein Verlass mehr auf pytest-Interna.

### 2.4 Diagnosewerkzeuge ins Repo

`tools/diag_sqlite_netdrive.py` und `tools/diag_sqlite_netdrive2.py` — versioniert, auffindbar. **diag2 verlangt bei mehreren `evidence`-DBs zwingend `--db`** und listet die Kandidaten mit ihrem Stempel auf, statt still eine auszuwählen (Grundregel 1 — genau der Fehler, der oben passiert ist).

---

## 3. Tests

* `tests/test_startup_journal_stamps.py` (**+6**): rollback-gestempelt läuft durch · WAL auf Netzlaufwerk bricht mit Klartext **und** Konverterbefehl ab · WAL auf lokaler Platte ist **kein** Fehler · unbekannte Laufwerksart löst keinen Fehlalarm aus · erzwungenes WAL auf Netzlaufwerk bricht ab · **Reihenfolge in `run_all()` am Quelltext geprüft**.
* `tests/test_journal_policy.py` (**+2**, 2 repariert): UNC-Erkennung · Header-Stempel ohne SQLite.
* Regression: `python run_tests.py` — pytest **1209 passed / 54 skipped**, vitest bestanden.

**Keine Schemaänderung, keine Datenänderung.** Migrationsrelevanz: keine.

---

## 4. Was der Ermittler künftig sieht, wenn der Fall wiederkehrt

```
[FEHLER] Diese Datenbanken sind WAL-gestempelt und liegen auf einem Netzlaufwerk:
  evidence_db      \\KK31Storage15\Volume 1\...\data\evidence\evidence_524888.db

SQLite kann sie dort NICHT öffnen — auch nicht lesend. WAL braucht die
'-shm'-Datei im Shared Memory, und Shared Memory ist maschinenlokal.
Abhilfe (einmalig, ändert nur den Header-Stempel, nicht den Inhalt):
  python tools/convert_journal_mode.py --data-dir ./data            (Trockenlauf)
  python tools/convert_journal_mode.py --data-dir ./data --apply
```

Statt eines halben Abends: eine Zeile.
