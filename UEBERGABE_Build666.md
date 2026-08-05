# Übergabe Build 666 — Stabiler Bundle-Weg

**Baubasis:** `717fa12` (master nach Build 665) · **Lieferung:** 0.8.666 · 2026-08-04
**Zweig:** `claude/build666` · **Verfahren:** Git-Bundle nach `documents/data-exchange.md`

---

## 0. Zwei Dinge vorweg

> **Diese Lieferung ändert das Einspielwerkzeug selbst.** Sie wird noch mit der *alten* Fassung eingespielt — Abnahmeprobe, Selbst-Verlagerung und Stash-Wegfall wirken erst ab der **nächsten** Lieferung. Für diese hier bitte nach dem Einspielen von Hand: `./tools/pruefe_lieferung.sh 666`

> **Ein Konflikt an `tools/bundle_einspielen.sh` ist zu erwarten.** Dieser Build **ersetzt** deine Lösung aus `717fa12` (`rootpath` aus `$0`) durch `cd "$(git rev-parse --show-toplevel)"`. Begründung in §3 — sie ist inhaltlich, nicht kosmetisch. Beim Merge die Fassung **aus der Lieferung** nehmen.

---

## 1. Die Abnahme hat gefehlt

Grundregel 8 verlangt Prüfsummen, damit nicht mit unterschiedlichen Dateifassungen gearbeitet wird. Gemessen:

```
MD5SUMS-Dateien im Bestand:                     173
Vorkommen von "md5sum -c" im ganzen Projekt:      0
```

Wir haben bei jeder Lieferung Belege erzeugt, mitgeliefert und committet — und nie hineingesehen.

Was das gekostet hat, weißt du: heute fielen drei Tests, weil ein Lauf auf dem falschen Zweig lief. Die Frage „fehlt die Datei wirklich, oder schauen wir an die falsche Stelle?" hat uns mehrere Wortwechsel gekostet.

**Neu:** `tools/pruefe_lieferung.sh <build>`, dazu als Schritt 8 im Einspielskript.

**Erster echter Lauf**, gegen deinen Bestand nach Build 665:

```
uebereinstimmend: 27
abweichend:       1   -> tools/bundle_einspielen.sh
fehlend:          0
```

Genau richtig: die eine Abweichung ist dein Commit `717fa12`. Die Probe fällt kein Urteil, sie legt den Unterschied offen.

**Drei Zusagen:**

* **Fehlend und abweichend werden getrennt.** Deshalb *nicht* `md5sum -c` — dessen Ausgabe unterscheidet beides nicht, und die Unterscheidung ist die interessante: fehlend deutet auf einen unvollständigen Merge, abweichend auf eine Konfliktauflösung. Zwei Ursachen, zwei Wege.
* **Die Probe verspricht nicht mehr, als sie belegt.** Geprüft werden nur die Dateien *dieser* Lieferung; die Ausgabe sagt das ausdrücklich.
* **Eine ausgefallene Prüfung sieht nicht aus wie eine bestandene.** Fehlt die Liste, ist der Rückgabewert 2 — nicht 0 und nicht 1.

---

## 2. Kein Stash mehr

Der Stash war der einzige Zustand des Ablaufs, der sich **nicht aus Git ableiten ließ**. Brach etwas zwischen Beiseitelegen und Zurückholen ab, blieb er liegen — und ein zweiter Lauf fand einen sauberen Baum, legte keinen an und holte folglich nichts zurück. Die Arbeit war nicht verloren, aber *still* verschwunden.

Statt ihn kunstvoll zu verwalten, fällt er weg: **was nie beiseitegelegt wird, kann nicht liegenbleiben.** Ein Arbeitsbaum mit verfolgten Änderungen führt zum Abbruch mit Anleitung (Zweigname, drei Befehle, `git status --short`). Angetastet wird nichts — erprobt und nachgemessen.

---

## 3. Warum `717fa12` ersetzt wird

Deine Lösung war richtig gedacht: das Skript braucht die Wurzel. Sie ist aber mit der **Selbst-Verlagerung** nicht verträglich.

Das Skript räumte sich während des Laufs selbst weg — Schritt 5 mergt eine Lieferung, die `tools/bundle_einspielen.sh` ändern kann, und Bash liest ein Skript nicht am Stück, sondern nach Dateiposition. Beim Erproben ist mir genau das passiert: ein `git stash` nahm die frisch kopierte Fassung mit, und es lief die alte. Deshalb kopiert sich das Skript beim Start nach `/tmp` und startet sich von dort neu.

Danach liegt `$0` in `/tmp`. Ein aus dem Skriptpfad abgeleiteter Wurzelpfad zeigte damit ins Leere. `git rev-parse --show-toplevel` fragt die Wurzel bei git und ist außerdem unabhängig davon, ob relativ oder absolut aufgerufen wurde. Das Ziel ist dasselbe.

---

## 4. Womit wurde gemessen

`run_tests.py` nennt jetzt in Kopfzeile **und** Protokoll den Interpreter und die pytest-Fassung. Anlass war dein heutiger Fall: `pytest --version` funktionierte, während derselbe Lauf über `run_tests.py` an „No module named pytest" scheiterte.

Zwei Interpreter mit womöglich verschiedenen Paketständen fahren dieselbe Suite. Dann kann derselbe Bestand zweimal verschieden ausfallen, ohne dass es am Code liegt. Für ein forensisches Werkzeug ist „womit wurde gemessen" kein Beiwerk, sondern Teil des Befundes.

Und: eine **fehlende Voraussetzung ist kein Testfehler**. Die JavaScript-Seite prüft ihre Voraussetzungen seit jeher, die Python-Seite tat es nicht. Jetzt steht dort:

```
VORAUSSETZUNG FEHLT -- ES WURDE NICHT GETESTET.
Der Interpreter /pfad/python kennt kein Modul 'pytest'.
ACHTUNG: dass 'pytest --version' auf der Kommandozeile funktioniert,
beweist das Gegenteil NICHT ...
```

---

## 5. Was die Erprobung selbst gefunden hat

Drei Fehler, die erst im Lauf sichtbar wurden — und die ich ohne die Erprobung ausgeliefert hätte:

1. **Der Zustandsbericht schlug den `/tmp`-Pfad zum erneuten Aufruf vor** — einen Pfad, den es beim nächsten Mal nicht mehr gibt. Der Ursprungsaufruf wird jetzt über die Umgebung mitgenommen.
2. **Ein erster Entwurf riet bei gescheitertem Merge auf „häufig: keine git-Identität"** — und lag beim ersten Lauf prompt daneben. Es war eine unverfolgte Datei, die der Merge hätte überschreiben müssen. Eine falsche Ursachenangabe lenkt die Suche in die falsche Richtung; die Meldung verweist jetzt auf die git-Ausgabe und rät nicht.
3. **Genau diese Kollision fällt erst in Schritt 5 auf** — spät, und an einer Stelle, an der man den Zusammenhang nicht mehr vermutet. Sie wird jetzt schon in Schritt 2 gemeldet, sofern die Ref vorliegt. Liegt sie noch nicht vor, steht das da, statt zu schweigen.

**Erprobt in drei Läufen:** schmutziger Baum → Abbruch, Änderung unangetastet · voller Durchlauf → Abnahme bestanden (8/8) · Henne-Ei-Warnung beim Bauen → erscheint.

---

## 6. Befund, nicht behoben

Der CLI-Katalog führt ausschließlich Python-Werkzeuge — die drei Bundle-Skripte stehen dort **gar nicht** (null Treffer auf `.sh`). Ich habe den Umfang nicht eigenmächtig erweitert; maßgeblich für das Verfahren ist `documents/data-exchange.md`, und die ist fortgeschrieben (**4.4a** Abnahmeprobe als Pflicht, **4.4b** Henne-Ei). Ob die Shell-Werkzeuge in den Katalog gehören, entscheidest du.

---

## 7. Regression

Baucontainer, Python 3.12.3:

```
Python (pytest):     3147 passed, 92 skipped, 51 subtests   (665: 3140)
JavaScript (vitest):  122 Dateien, 1747 passed              (unveraendert)
```

Sieben neue Fälle: `PL01`–`PL07`. Geprüft wird vor allem der **Negativfall** — ein Prüfwerkzeug, das fälschlich „bestanden" meldet, ist schlimmer als gar keines: es beendet die Suche.

---

## 8. Nach dem Einspielen zu prüfen

1. `./tools/pruefe_lieferung.sh 666` — erwartet: **BESTANDEN**.
2. `python run_tests.py --python-only` — die Kopfzeile muss Interpreter und pytest-Fassung nennen.
3. Probe des Stash-Wegfalls: eine Datei ändern, **nicht** committen, Einspielskript starten. Es muss abbrechen, und die Änderung muss danach unverändert dastehen.

---

## 9. Offene Punkte

* **Weiterhin offen:** die Entscheidung zu Build 663 §3 — die Von→Bis-Übernahme liegt nur auf der Eingabemaske, nicht auf den beiden Filtern.
* **Vorgeschlagen, nicht gebaut:** Build 667 — Testlauf beschleunigen (`--jobs`, `--schnell`, `--auswahl`, `essenziell.txt`). Die Vorfrage dazu ist deine `-n auto`-Messung: `time python -m pytest tests/ -q -n auto` gegen deinen Referenzwert. Wenn daraus aus 16 Minuten vier werden, brauchen wir gar kein Subset.
* **Aufräumen:** 173 `MD5SUMS_Build*.txt` im Wurzelverzeichnis. Sie sind Belege und gehören nicht gelöscht — aber ein Unterverzeichnis wäre übersichtlicher. Auf dein Wort.
* **Erledigt:** erster echter kdiff3-Lauf (Build 665, du hast die Lieferungsseite genommen — korrekt).
