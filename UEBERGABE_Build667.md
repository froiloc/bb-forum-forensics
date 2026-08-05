# Übergabe Build 667 — Paralleler Testlauf, und ein Befund, den erst er sichtbar machte

**Baubasis:** `5208bb9` (Build 666) · **Lieferung:** 0.8.667 · 2026-08-05
**Zweig:** `claude/build667` · **Verfahren:** Git-Bundle nach `documents/data-exchange.md`

> **Erste Lieferung, die das neue Einspielwerkzeug wirklich nutzt.** Abnahmeprobe (Schritt 8), Selbst-Verlagerung und Stash-Abbruch wirken ab jetzt.

---

## 0. Ein Befund vorweg

`origin/master` stand beim Bauen noch auf `717fa12`. **Build 666 ist auf GitHub nicht sichtbar.** Ich habe deshalb auf `5208bb9` aufgesetzt — dem Commit, den du gemergt hast; er liegt in deinem Bestand als Elternteil des Übernahme-Merges, das Bundle findet ihn also. Bitte `git push` nachholen; sonst arbeite ich beim nächsten Mal wieder auf einem Stand, den ich nur aus meinem eigenen Zweig kenne.

---

## 1. Die Messung hat das Vorhaben verändert

Deine Zahlen: **16 min sequenziell → 5 min 39 s mit `-n 8`**, bei 3147 Tests, **ohne jeden Verzicht auf Abdeckung**.

Damit **entfällt das geplante Subset ersatzlos.** `essenziell.txt` und `--schnell` waren vorgeschlagen, um lange Wartezeiten erträglich zu machen. Der Grund ist weg. Maschinerie, deren einziger Zweck es wäre, einen Teillauf zu erzeugen, den man später mit einer Regression verwechseln kann, baue ich nicht.

Vorher geprüft, ob es einen Ausreißer zum Wegoptimieren gibt: nein. Die 25 langsamsten Tests ergeben zusammen 32 von 175 Sekunden — es sind 3147 Tests à ~56 ms, verteilt auf den Aufbau der Wegwerf-Datenbanken.

---

## 2. Der eigentliche Fund

Unter xdist fiel `CE08` mit `assert 135 <= 80`. Sequenziell grün.

**Ursache, nachgemessen.** argparse holt seine Zeilenbreite über `shutil.get_terminal_size()`, und das beachtet `COLUMNS`.

* Sequenziell greift pytests Ausgabeumleitung, die Größenermittlung scheitert und fällt auf 80 zurück. **Der Test bestand aus Versehen.**
* xdist reicht die Breite des Steuerprozesses per `COLUMNS` an die Arbeitsprozesse weiter. Bei deinem ~140 Zeichen breiten Fenster kommt dort 140 an.

Gegenprobe im Baucontainer: `COLUMNS=140 pytest …` lässt `CE08` auch **sequenziell** fallen — mit exakt derselben Zahl (135). Bei `COLUMNS=200` fällt er schon an einer früheren Zusicherung.

**xdist hat also nichts kaputt gemacht, sondern etwas sichtbar.** Das Ergebnis eines Regressionstests hing an der Fensterbreite des Terminals, in dem er zufällig lief. Derselbe Bestand konnte zweimal verschieden ausfallen, ohne dass es am Code lag — und der sequenzielle Lauf hätte es nie gezeigt. Für einen Bestand mit Beweislast ist das keine Kleinigkeit.

**Deshalb wurde nicht der Test geflickt, sondern die Ursache entfernt.** `tests/conftest.py` legt `COLUMNS` für jeden Lauf fest — beim Import (argparse-Objekte können schon beim Einsammeln entstehen) und zusätzlich vor jedem Test. Unter xdist wird `conftest.py` in jedem Arbeitsprozess eingelesen, die Festlegung gilt also auch dort. `RT09` ist der Wächter.

Umfang geprüft: ein voller Lauf mit `COLUMNS=200` zeigte, dass **nur dieser eine Test** betroffen war.

Nebenwirkung, die dir Arbeit spart: du brauchst `COLUMNS=80` nicht mehr vor den Aufruf zu setzen — und musst dir nicht merken, in welcher Schale die Variable überlebt.

---

## 3. `--jobs` — und warum es nie Voraussetzung wird

```
python run_tests.py --jobs auto
python run_tests.py --python-only --jobs 8
```

Die Produktions-VM unter Windows ist offline; pytest-xdist lässt sich dort nicht nachinstallieren. Fehlt es bei angefordertem `--jobs`, wird **sequenziell gefahren und das gesagt**:

```
Parallel:     ANGEFORDERT (-n auto), ABER NICHT MOEGLICH - pytest-xdist fehlt
              in dieser Umgebung.
              Es wird SEQUENZIELL gefahren. Abhilfe: python -m pip install pytest-xdist
```

Kein Abbruch — dann liefe gar nichts. Kein Schweigen — dann glaubte man, parallel gemessen zu haben. Dieselbe Haltung wie bei der pytest-Prüfung aus Build 666. Erprobt in einer Umgebung ohne xdist.

**Mehr Prozesse sind nicht automatisch schneller.** Jeder legt eigene Wegwerf-Datenbanken an; ab einem Punkt ist die Platte der Engpass. Im Baucontainer (ein Kern) war `-n 2` sogar minimal schneller als `-n 4`. Steht als Warnung in der Hilfe.

---

## 4. Regression

Baucontainer, Python 3.12.3, `-n 2`:

```
Python (pytest):     3151 passed, 92 skipped, 51 subtests   (666: 3147)
JavaScript (vitest):  122 Dateien, 1747 passed              (unveraendert)
```

Neue Fälle: `RT09` (Wächter Terminalbreite), `RT10` (xdist-Erkennung), `RT11`/`RT11b` (Rückfall und Nutzung).

---

## 5. Nach dem Einspielen zu prüfen

1. `python run_tests.py --python-only --jobs auto` — **ohne** `COLUMNS=` davor. Muss grün sein, und die Kopfzeile muss `Parallel: -n auto` nennen.
2. Gegenprobe der Festlegung: `COLUMNS=200 python -m pytest tests/test_help_cli_epilog.py -q` muss **ebenfalls grün** sein. Vor diesem Build fiel `CE08` dabei.
3. Die Abnahmeprobe läuft diesmal automatisch als Schritt 8 mit — erwartet: **BESTANDEN**.

---

## 6. Offene Punkte

* **`git push` für Build 666** (siehe §0).
* **Weiterhin offen:** die Entscheidung zu Build 663 §3 — die Von→Bis-Übernahme liegt nur auf der Eingabemaske, nicht auf den beiden Filtern der Kapazitätsansicht und der Annotationsrecherche.
* **Der Tracker sagt weiterhin die Unwahrheit:** die Einträge aus den Builds 663–667 liegen in `issue-tracker/eintraege_claude_Build*.json` und sind noch nicht in `data/issues.json` eingemischt. `merge-new-tickets.sh` steht dafür bereit. Solange das nicht läuft, zeigt die Liste erledigte Arbeit als offen.
* **Zwei kritische Vorgänge warten auf Abnahme, nicht auf Entwicklung:** `651e6d84` (Sicherung verdrängt gute Generationen — behoben in 625–627, Status `testing`) und `317481d3` (Lektorat-Anker — geliefert in 659/661).
* **Aufräumen, auf dein Wort:** 173 `MD5SUMS_Build*.txt` im Wurzelverzeichnis. Belege, gehören nicht gelöscht — ein Unterverzeichnis wäre übersichtlicher.
