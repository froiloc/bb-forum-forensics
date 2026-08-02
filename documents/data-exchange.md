# Datenaustausch AIW — Übergabe von Arbeitsergebnissen

**Stand:** Build 661 · 2026-08-02 · **Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH

**Verbindlich ab 3. August 2026**, das heißt ab `aiw_webserver` **0.8.661** und
`aiw_sqlite_prepper` **0.1.129**. Festgelegt von Alex am 2026-08-02 nach der
Erörterung in derselben Sitzung. Diese Fassung ist die maßgebliche für beide
Bestände; im Prepper liegt unter demselben Pfad nur ein Verweis, damit nicht
zwei Fassungen derselben Regel entstehen.

---

## 1. Wozu diese Regel

Bis Build 660 wurden Arbeitsergebnisse als ZIP-Archiv übergeben: die im Build
bearbeiteten Dateien, Originalstruktur, MD5-Liste. Das Verfahren trägt, solange
nur an einer Stelle gearbeitet wird. Es versagt, sobald parallel gearbeitet wird
— und es versagt **still**.

**Der Befund** (gemessen am 2026-08-02 in einer nachgestellten Lage; das
Meßprotokoll steht in Abschnitt 10):

Wird ein ZIP über einen Bestand entpackt, in dem dieselbe Datei zwischenzeitlich
verändert wurde, ist die parallele Änderung danach **fort**. Git meldet
anschließend nur:

```
 M build.json
 M modul.py
```

Das ist von einer gewöhnlichen Bearbeitung nicht zu unterscheiden. Es gibt keine
Warnung, keine Markierung, keinen Konflikt. Ein Arbeitsergebnis verschwindet,
ohne daß irgendwo etwas darüber steht.

Das ist der Sache nach ein Verstoß gegen **GR1** — kein Beleg darf je still
übersprungen werden — auf der Ebene des Arbeitsweges statt der Beweisführung.
Für ein Projekt, dessen erste Regel das ist, war der Zustand nicht haltbar.

Derselbe Fall über ein Git-Bundle:

```
Auto-merging modul.py
CONFLICT (content): Merge conflict in modul.py
UU modul.py
```

Der Konflikt wird benannt, verortet und im Text markiert. Aus einem stillen
Verlust wird eine sichtbare Entscheidung. **Das, und nur das, ist der Grund für
die Umstellung.**

---

## 2. Was sich nicht ändert

Die Umstellung betrifft ausschließlich die **Form des Transports**. Unverändert
bleiben:

- **Kein Push.** Der GitHub-Token ist absichtlich auf `Read access` für
  `content` und `metadata` beschränkt. Das Einspielen besorgt Alex.
- **GR8 — MD5-Prüfsummen.** Sie bleiben, ausdrücklich beibehalten (Festlegung
  2026-08-02). Sie prüfen den Transport, der Commit-Hash prüft den Inhalt; die
  beiden ersetzen einander nicht (Abschnitt 7).
- **`build.json`** wird in jedem Build fortgeschrieben: Buildnummer, Version,
  Datum, Arbeitspaket, Baubasis, Auslieferungsform.
- **Nur die im Build bearbeiteten Dateien.** Ein Bundle liefert ohnehin nur die
  Unterschiede zur Baubasis — das ist keine Lockerung, sondern dieselbe Regel
  mit anderen Mitteln.
- **GR2, GR3, GR9.** Vor der Übergabe `py_compile` / `node --check`, danach in
  der VM die volle Regression.
- **Das ZIP als Transporthülle.** Die Bundle-Datei wird in einem ZIP übergeben,
  zusammen mit der MD5-Liste und dem Übergabedokument. Der Übertragungsweg
  bleibt damit derselbe wie bisher.

---

## 3. Ablauf — Erstellerseite

### 3.1 Zu Beginn der Sitzung

```
cd /home/claude
git clone -b master https://<token>@github.com/froiloc/bb-forum-forensics.git aiw_webserver
git -C aiw_webserver log --oneline -1          # Baubasis belegen, wie bisher
git -C aiw_webserver switch -c claude/build661 # Zweig nach dem ERSTEN Build der Sitzung
```

Der Zweigname lautet `claude/build<erste Buildnummer der Sitzung>`. Werden in
einer Sitzung mehrere Builds gebaut, bleibt der Zweigname unverändert; die
weiteren Builds sind Commits darauf.

### 3.2 Je Build ein Commit

Ein Build ist ein Commit. Nicht zwei, nicht ein halber. Damit bildet die
Git-Vorgeschichte die Builddisziplin des Projekts ab, statt sie einzuebnen.

```
git add -A
git add -f <Dateien, die unter .gitignore fallen>   # siehe 3.3
git commit -m "Build 661: <Kurzfassung>"
```

Betreffzeile: `Build <Nr>: <Kurzfassung>`. Im Rumpf die geänderten Dateien und
der Anlaß, in derselben Ausführlichkeit wie bisher im Feld `arbeitspaket` der
`build.json`.

### 3.3 Die Vorabprobe — Pflicht

**Der einzige Punkt, an dem das neue Verfahren schlechter ist als das alte, und
der einzige, der Aufmerksamkeit verlangt.**

Ein ZIP entsteht durch Kopieren: was kopiert wird, ist drin, `.gitignore` ist
belanglos. Ein Bundle entsteht aus Commits: was nicht committet ist, **fehlt
spurlos**. Beide Bestände haben `.gitignore`-Regeln, die genau die
projektwichtigen Dateien erfassen — im Webserver `*.md` und `*.html` mit
Ausnahmen für `documents/`, `management/` und den Issue-Tracker.

Vor jedem Bundle daher zwingend:

```
git status --porcelain --ignored
```

Was dort mit `!!` steht und geliefert werden soll, muß **vorher** mit
`git add -f` in einen Commit. Die Ausgabe dieser Probe gehört in das
Übergabedokument — auch dann, wenn sie leer ist. Eine Prüfung, deren Ergebnis
niemand sieht, ist keine Prüfung (GR1).

*Belegter Anlaß:* In der Erprobung am 2026-08-02 hat `git add -A` eine Datei
namens `cockpit.html` wegen der Regel `*.html` übergangen. Sie wäre nicht im
Bundle gewesen, und niemandem wäre es aufgefallen.

*Zur Handhabung* (Erfahrung aus dem ersten Lauf am 2026-08-02): Die Rohausgabe
ist im Webserver-Bestand rund sechzig Zeilen lang und besteht fast vollständig
aus `__pycache__`- und `.pytest_cache`-Verzeichnissen. Eine gefilterte Fassung
ist zulässig, **sofern der Filter im Übergabedokument mitgenannt wird** — ein
verschwiegener Filter wäre genau die stille Auslassung, die die Probe verhindern
soll:

```
git status --porcelain --ignored | grep '^!!' | grep -v '__pycache__\|\.pytest_cache'
```

*Durchsetzung:* **keine maschinelle.** Dies ist eine redaktionelle Regel. Eine
Prüfung im Auslieferungswerkzeug ist möglich und als offener Punkt vermerkt
(Abschnitt 11).

### 3.4 Bundle erzeugen und belegen

```
git bundle create ../aiw_webserver_661.bundle claude/build661 --not origin/master
git bundle verify ../aiw_webserver_661.bundle
git bundle list-heads ../aiw_webserver_661.bundle
git log --oneline origin/master..claude/build661
md5sum ../aiw_webserver_661.bundle
```

Die Form `<Zweig> --not origin/master` ist die maßgebliche: sie benennt die
enthaltene Ref ausdrücklich und trägt die Baubasis als Voraussetzung ein. Die
Kurzform mit `..` ist nicht zu verwenden — sie kann ein Bundle ohne benannte Ref
erzeugen, das sich nicht sauber fetchen läßt.

`git bundle create` verweigert ein leeres Bundle. Eine vergessene Lieferung
fällt damit auf, statt still durchzugehen.

### 3.5 Auslieferungspaket

Benennung: `<Modul>_Build<Nr>.zip`, also z. B. `aiw_webserver_Build661.zip`.
Inhalt:

| Datei | Zweck |
|---|---|
| `aiw_webserver_661.bundle` | die Arbeitsergebnisse |
| `MD5SUMS_Build661.txt` | Prüfsumme der Bundle-Datei **und** der einzelnen geänderten Dateien |
| `UEBERGABE_Build661.md` | Übergabedokument (Abschnitt 6) |

Die Prüfsummen werden zusätzlich im Antworttext genannt, damit sie unabhängig
vom Archiv nachlesbar sind.

---

## 4. Ablauf — Einspielseite

### 4.1 Prüfen, ohne etwas anzufassen

```
git bundle verify aiw_webserver_661.bundle
```

Die Ausgabe nennt die enthaltene Ref und die vorausgesetzte Baubasis
(`The bundle requires this ref: <SHA>`). Damit ist **maschinell** belegt, auf
welchem Stand gearbeitet wurde — bisher stand das nur als Satz in einem
Übergabedokument.

### 4.2 In eine eigene Ref holen

```
git fetch aiw_webserver_661.bundle 'refs/heads/claude/build661:refs/claude/build661'
git log --oneline master..refs/claude/build661
git diff master refs/claude/build661
```

Der Arbeitsbaum wird dabei **nicht** angefaßt. `refs/claude/*` liegt außerhalb
von `refs/heads/`, taucht also nicht in `git branch` auf und wird beim `git push`
nicht mitgeschickt.

### 4.3 Über einen Integrationszweig einspielen — immer

```
git switch -c integration/661 master
git merge --no-ff refs/claude/build661
#   ... etwaige Konflikte auflösen ...
python run_tests.py
git switch master
git merge --ff-only integration/661
git branch -d integration/661
git push
```

**Warum der Umweg.** Wird direkt auf `master` gemergt und es kracht, steht
`master` im Konfliktzustand: halb aufgelöste Dateien, kein lauffähiges System.
Bricht die Arbeit dort ab, ist unklar, was der Zweig gerade ist. Das verstößt
gegen **GR2**. Über den Integrationszweig bewegt sich `master` erst, wenn der
Merge aufgelöst und die Regression grün ist.

**Der Umweg kostet nichts.** Gemessen am 2026-08-02: beide Wege ergeben bei
gleicher Konfliktauflösung **denselben Commit** (`953fa10…`, Abschnitt 10). Er
ändert nur, in welchem Zustand `master` währenddessen ist.

**Zum `--ff-only` im vorletzten Schritt.** Das ist nicht das Fast-Forward, das
für die Übernahme der Arbeitsergebnisse abgelehnt wurde. Der Merge-Commit ist zu
diesem Zeitpunkt bereits gebaut, die einzelnen Builds hängen sichtbar als eigener
Ast daran. Das `--ff-only` schiebt nur den `master`-Zeiger auf einen Commit, der
ohnehin sein Nachfahre ist — und scheitert laut, falls `master` sich
zwischenzeitlich doch bewegt hat.

### 4.4 Was bleibt, was verschwindet

- **`refs/claude/*` bleibt.** Der Zeiger kostet nichts und hält den
  Auslieferungsstand dauerhaft adressierbar — auch nachdem beim Einspielen
  Korrekturen vorgenommen wurden. Damit ist jederzeit belegbar, was geliefert
  wurde und was daran geändert worden ist. Für einen Bestand mit Beweislast ist
  das mehr wert als ein aufgeräumtes `git branch`.
- **`integration/<Nr>` wird gelöscht**, sobald `master` steht. Der Commit ist
  erhalten, der Zweigname hat seinen Zweck erfüllt.
- Sollen die `refs/claude/*` auch auf GitHub liegen, braucht es einen
  ausdrücklichen Refspec: `git push origin 'refs/claude/*:refs/claude/*'`. Von
  allein gehen sie nicht mit. Ob das gewollt ist, ist **noch nicht entschieden**
  (Abschnitt 11).

---

## 5. Merge, nicht Rebase

`git rebase` auf die gelieferten Commits ist **untersagt**.

Der Grund ist kein Geschmack: Rebase schreibt die Commits neu, die SHAs ändern
sich, und damit ist die Gleichheit zwischen dem ausgelieferten und dem
eingespielten Stand dahin. Genau diese Gleichheit ist der Nachweis, den das
Verfahren liefern soll (Abschnitt 7). Wer rebased, wirft ihn weg.

Korrekturen am gelieferten Stand sind zulässig — als **eigene Commits** auf dem
Integrationszweig. Dann bleibt im Bestand sichtbar, was geliefert und was
nachträglich geändert wurde. Das ist der Fall, den `refs/claude/*` aufbewahrt.

---

## 6. Übergabedokument

Jede Lieferung trägt ein Übergabedokument bei. Verpflichtender Inhalt:

1. **Baubasis:** `git log --oneline -1` des Klons zu Sitzungsbeginn.
2. **Enthaltene Commits:** `git log --oneline` des Bundle-Bereichs.
3. **Ausgabe von `git bundle verify`** — mit der geforderten Baubasis-SHA.
4. **Ausgabe der Vorabprobe** `git status --porcelain --ignored`, auch wenn leer.
5. **Geänderte Dateien** mit Einzel-MD5.
6. **MD5 der Bundle-Datei.**
7. **Regressionsstand** der Bauumgebung, mit Nennung der dort verfügbaren
   Python-Fassung, falls sie von der VM abweicht.
8. **Offene Punkte** und alles, was in der Sitzung aufgefallen, aber nicht
   behoben worden ist.

---

## 7. Was wodurch belegt wird

| Frage | Nachweis |
|---|---|
| Ist die Datei unverfälscht angekommen? | MD5 der Bundle-Datei (GR8) |
| Stimmt eine einzelne Datei mit der Lieferung überein? | Einzel-MD5 in `MD5SUMS_Build<N>.txt` (GR8) |
| Auf welchem Stand wurde gearbeitet? | `git bundle verify` → `requires this ref: <SHA>` |
| Ist der eingespielte Stand derselbe wie der ausgelieferte? | Gleichheit des Commit-SHA auf beiden Seiten |
| Was genau wurde geändert? | `git diff master refs/claude/<Zweig>` |
| Wer hat es verfaßt? | Autor- und Committer-Angabe des Commits |

MD5 und Commit-Hash beantworten verschiedene Fragen. Der MD5 sichert den
Transport einer Datei, der Commit-Hash sichert einen ganzen Baum samt
Vorgeschichte. Beides wird geführt.

---

## 8. Urheberschaft

Die gelieferten Commits tragen die Urheberangabe der erstellenden Instanz
(`noreply@anthropic.com`). Das ist **so gewollt** (Festlegung Alex, 2026-08-02)
und folgt der Projektregel „Ehre, wem Ehre gebührt" aus `rules-projekt.md` § 4:
Was maschinell verfaßt wurde, ist im Bestand als maschinell verfaßt erkennbar,
und was nachträglich von Hand geändert wurde, hebt sich davon ab.

Bis Build 660 erschien alles unter dem Namen des Einspielenden. Die neue Lage
ist die genauere.

---

## 9. Rückfall auf ZIP

Der alte Weg bleibt zulässig, aber nur in diesen Fällen und nur mit Angabe des
Grundes im Übergabedokument:

- Es liegt **kein Klon** vor (Einzeldatei ohne Bestandsbezug, Entwurf, Auszug).
- Das Repositorium war in der Sitzung **nicht erreichbar**.
- Die Lieferung enthält **ausschließlich** Dateien, die nicht in den Bestand
  gehören (Auswertungen, Meßprotokolle, Schriftstücke zur Vorlage).

Für alles, was in den Bestand eingespielt werden soll, gilt der Bundle-Weg.

---

## 10. Meßprotokoll (2026-08-02)

Nachgestellte Lage: Basis-Commit `b352b00` mit `modul.py`, `build.json`,
`.gitignore` (`*.html`) und `cockpit.html`. Zwei Klone. Die eine Seite ändert
`modul.py` Zeile 2 und legt Build 659/660 an; die andere ändert parallel
dieselbe Zeile.

**(a) ZIP-Weg — stiller Verlust**

```
-- Stand vor dem Entpacken --
zeile2 GEAENDERT-VON-ALEX
-- nach dem Entpacken --
zeile2 GEAENDERT-VON-CLAUDE
-- was git dazu sagt --
 M build.json
 M modul.py
```

**(b) Bundle-Weg — sichtbarer Konflikt**

```
$ git bundle verify aiw_659-660.bundle
The bundle contains this ref:
21dd0c0acd28ff208190fc0612d8e062b58f5609 refs/heads/claude/build659
The bundle requires this ref:
b352b00ab8c87262c4a70e60fbb10dc5a351b505
aiw_659-660.bundle is okay

$ git merge --no-ff refs/claude/build659
Auto-merging modul.py
CONFLICT (content): Merge conflict in modul.py
Automatic merge failed; fix conflicts and then commit the result.

$ git status --short
M  build.json
UU modul.py
```

**(c) Die `.gitignore`-Falle**

```
$ git status --porcelain --ignored
!! cockpit.html
```

`git add -A` hatte die Datei übergangen; sie wäre nicht im Bundle gewesen.

**(d) Integrationszweig ändert das Ergebnis nicht**

```
A (direkt auf master) = 953fa10bffeb74205573c44e33b8437ac186096c
B (über Zweig)        = 953fa10bffeb74205573c44e33b8437ac186096c
>>> IDENTISCH
```

Während der Konfliktauflösung in Weg B stand `master` unverrückt auf `794da2f`.

**(e) Größe** — 857 Byte Bundle gegen 525 Byte ZIP im Versuch. Der Aufschlag ist
die mitgeführte Vorgeschichte und fällt nicht ins Gewicht.

**Umgebung der Messung:** git 2.43.0, Linux-Bauumgebung. Die Bundle-Fassung ist
seit Git 1.5 unverändert lesbar; eine Fassungsabhängigkeit ist nicht zu erwarten,
aber beim ersten Einspielen in der VM zu bestätigen.

---

## 11. Offene Punkte

- **Maschinelle Vorabprobe.** Die Prüfung aus 3.3 ließe sich in ein
  Auslieferungswerkzeug fassen (`tools/pruefe_auslieferung.py` prüft bereits die
  MD5-Liste von der Wurzel aus). Bis dahin ist 3.3 eine redaktionelle Regel ohne
  Durchsetzung.
- **`refs/claude/*` auf GitHub?** Ob der Auslieferungsstand auch entfernt
  vorgehalten wird, ist nicht entschieden. Es hängt daran, ob GitHub hier Archiv
  oder nur Austauschpunkt ist.
- **Erste Erprobung in der VM.** Der Weg aus Abschnitt 4 ist bislang in der
  Bauumgebung gemessen, nicht unter Windows mit UNC-Pfaden gefahren.
