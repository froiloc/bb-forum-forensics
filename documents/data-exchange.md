# Datenaustausch AIW — Übergabe von Arbeitsergebnissen

**Stand:** Build 662 · 2026-08-02 · **Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH

**Verbindlich ab 3. August 2026**, das heißt ab `aiw_webserver` **0.8.661** und
`aiw_sqlite_prepper` **0.1.129**. Festgelegt von Alex am 2026-08-02 nach der
Erörterung in derselben Sitzung. Diese Fassung ist die maßgebliche für beide
Bestände; im Prepper liegt unter demselben Pfad nur ein Verweis, damit nicht
zwei Fassungen derselben Regel entstehen.

---

## 0. Wo dieses Verfahren gilt

**Nur zwischen Bauumgebung und Linux-Entwicklungsbestand.** In der Windows-VM
ist kein Git verfügbar; dorthin geht stets ein **vollständiger Rollout** des
fertigen Bestandes. Der Bundle-Weg regelt also den Weg vom Erzeuger zum
Entwicklungsrechner — nicht den Weg in die Anlage. Beide hier beschriebenen
Werkzeuge sind Bash-Skripte und laufen unter Linux.

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

*Durchsetzung:* **maschinell, seit Build 662.** `tools/bundle_bauen.sh` bricht
ab, sobald `git status --porcelain` etwas meldet — verfolgte Änderung oder
unverfolgte Datei, gleich was:

```
ABBRUCH: Es liegt Nicht-Committetes im Arbeitsbaum.
Ein Bundle enthaelt NUR Committetes -- das hier waere spurlos weg:
?? vergessene_datei.txt
```

Ignorierte Dateien führen nicht zum Abbruch, werden aber gelistet und ins
Protokoll geschrieben, samt des verwendeten Rauschfilters.

### 3.4 Bundle erzeugen und belegen — `tools/bundle_bauen.sh`

Seit Build 662 erledigt ein Skript die Schritte 3.3 bis 3.5 in einem Zug:

```
tools/bundle_bauen.sh <paket> <buildnummer> [testbefehl]
tools/bundle_bauen.sh aiw_webserver 662
```

Es prüft den Zweignamen, bricht bei Nicht-Committetem ab, erzeugt die
MD5-Liste über `tools/md5sums_build.sh` und zieht sie in den letzten Commit
nach, baut und verifiziert das Bundle, fährt die Regression (**und baut bei
rotem Ergebnis kein Archiv**, GR2/GR9), schreibt ein Protokoll nach Abschnitt 6
und packt das Auslieferungsarchiv.

Ohne Testbefehl wird `python run_tests.py` versucht und auf `python3` gewechselt,
falls `python` nicht vorhanden ist. `-` als Testbefehl überspringt die
Regression — dann steht im Protokoll ausdrücklich
`AUSDRUECKLICH UEBERSPRUNGEN` statt eines Ergebnisses (GR1).

*Von Hand gleichbedeutend:*

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

Benennung: `<Modul>_Build<Nr>.zip`, also z. B. `aiw_webserver_Build662.zip`.
Inhalt:

| Datei | Zweck |
|---|---|
| `aiw_webserver_662.bundle` | die Arbeitsergebnisse |
| `MD5SUMS_Build662.txt` | Einzelprüfsummen der geänderten Dateien |
| `PROTOKOLL_Build662.md` | maschinell erzeugt, die Punkte 1–7 aus Abschnitt 6 |
| `UEBERGABE_Build662.md` | von Hand verfasst: Befunde, Begründungen, offene Punkte |

Das Protokoll nimmt dem Übergabedokument die mechanischen Teile ab. Was ein
Skript nicht wissen kann — warum etwas so gebaut wurde, was aufgefallen und
nicht behoben ist — bleibt von Hand zu schreiben.

Die Prüfsummen werden zusätzlich im Antworttext genannt, damit sie unabhängig
vom Archiv nachlesbar sind.

---

## 4. Ablauf — Einspielseite

Seit Build 662 fasst `tools/bundle_einspielen.sh` die Schritte 4.1 bis 4.4
zusammen:

```
tools/bundle_einspielen.sh <paket> <buildnummer> [testbefehl]
tools/bundle_einspielen.sh aiw_webserver 662
```

Es prüft, dass HEAD auf `master` steht (seit dem Umstieg auf eigene
Arbeitszweige kein Formalismus mehr — sonst landet eine Lieferung versehentlich
in `alex/thema`), verifiziert das Bundle vor jedem Eingriff, legt liegende
Arbeit beiseite, holt die Lieferung in `refs/claude/*`, mergt über einen
Integrationszweig, ruft bei Konflikt `git mergetool`, fährt die Regression und
zieht `master` erst danach nach.

**Konfliktauflösung.** Eingerichtet ist `kdiff3`:

```
git config --global merge.tool kdiff3
git config --global mergetool.keepBackup false
```

`keepBackup false` verhindert liegenbleibende `.orig`-Dateien. Ohne
eingerichtetes `merge.tool` oder ohne Terminal überspringt das Skript den
Aufruf mit einem Hinweis, statt zu hängen.

**Der Rückgabewert von `git mergetool` taugt nicht als Nachweis** — er kann 0
sein, obwohl das Werkzeug ohne Auflösung verlassen wurde. Geprüft wird deshalb
`git ls-files -u`; solange dort etwas steht, ist nichts aufgelöst. Und:
`mergetool` tut, was das Werkzeug tut. Nach der Auflösung gehört ein Blick in
die Datei, nicht nur einer auf die Erfolgsmeldung.

Die folgenden Abschnitte beschreiben, was das Skript im Einzelnen tut.

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

### 4.4a Abnahmeprobe — Pflicht *(Festlegung 2026-08-04, Build 666)*

**Nach dem Nachziehen von `master` wird die Lieferung gegen die Prüfsummenliste
abgenommen.** `tools/bundle_einspielen.sh` tut das als Schritt 8 selbst;
nachträglich und jederzeit von Hand:

```
./tools/pruefe_lieferung.sh 666
```

**Wozu.** Bis Build 665 wurde bei jeder Lieferung eine `MD5SUMS_Build<N>.txt`
erzeugt, mitgeliefert und committet — und **von niemandem geprüft**. Gemessen am
2026-08-04: 173 solcher Listen im Bestand, null Vorkommen von `md5sum -c` im
gesamten Projekt. Grundregel 8 verlangt Prüfsummen genau dafür, dass nicht mit
unterschiedlichen Dateifassungen gearbeitet wird — die Belege lagen vor, die
Abnahme fehlte.

Am selben Tag hat dieses Fehlen mehrere Wortwechsel gekostet: ein Testlauf lief
auf dem falschen Zweig, drei Tests fielen, und die Frage „fehlt die Datei
wirklich, oder schauen wir an die falsche Stelle?" ließ sich nicht in einem Zug
beantworten. Die Probe beantwortet sie in fünf Sekunden.

**Was die Probe sagt — und was nicht.** Geprüft werden **nur** die Dateien, die
diese Lieferung angefasst hat. Über den übrigen Bestand sagt sie nichts, und sie
behauptet es auch nicht: die Ausgabe nennt die geprüfte Zahl ausdrücklich.

**Eine Abweichung ist kein Fehler.** Wurde bei einer Konfliktauflösung bewusst
die eigene Fassung behalten, **muss** die Datei hier erscheinen. Die Probe fällt
kein Urteil, sie legt den Unterschied offen:

```
git diff refs/claude/build<N> -- <datei>
```

Erster echter Lauf (Build 665, Bestand von Alex): 27 übereinstimmend, eine
Abweichung — `tools/bundle_einspielen.sh`, erklärt durch Commit `717fa12`.

**Fehlt die Liste oder das Prüfwerkzeug, wird das gesagt.** Eine ausgefallene
Prüfung darf nicht wie eine bestandene aussehen; das wäre die gefährlichste
Ausgabe dieses Schrittes.

#### Die Probe ordnet ihre Befunde ein *(Build 695, Vorgang 08c9c821-725e-4e9f-89cd-9b012ce18c28)*

**Anlass, gemessen am 2026-08-11.** Build 693 wurde eingespielt. Der Merge lief
sauber durch, die Regression aus Schritt 6 war grün, `master` war nachgezogen —
und dann meldete diese Probe eine Abweichung an `toolbar/toolbar.js`. Der
Rollout wurde gestoppt. Die Aufklärung dauerte mehrere Wortwechsel und endete
mit dem Ergebnis, daß **alles in Ordnung war**: zwischen der Baubasis der
Lieferung (0.8.689) und dem Einspielen war Build 691 auf `master` gelandet und
hatte dieselbe Datei angefaßt.

Das war kein Fehlalarm im Sinne von „zu empfindlich". Die Probe hat richtig
gemessen. Sie hat nur nicht gesagt, **was** sie gemessen hat — und ließ damit
genau die beiden Fälle ununterscheidbar, die entgegengesetzte Schritte
verlangen:

| Lage | Richtiger Schritt |
|---|---|
| (a) Die Lieferung ist beschädigt oder unvollständig angekommen | Anhalten, nachfassen |
| (b) Die Lieferung ist unversehrt angekommen und wurde mit einer zweiten Lieferung verschmolzen | In Ordnung, weitermachen |

**Der Nachweis lag bereits vor, er wurde nur nicht benutzt.** Abschnitt 4.4
verlangt, daß `refs/claude/build<N>` nach dem Einspielen stehenbleibt — sie
*ist* die Lieferung, unverändert, als Git-Objekt. Die Probe hält jede
abweichende Datei jetzt zusätzlich gegen diese Ref und schreibt eine Einordnung
dazu:

| Code | Bedeutung |
|---|---|
| `VERSCHMOLZEN` | Lieferung unversehrt in der Ref, Ref in `HEAD`, andere Commits erklären den Unterschied — sie werden **namentlich** genannt |
| `BEFUND` | Schon die Ref weicht von ihrer eigenen Liste ab. Liste und Bundle passen nicht zusammen — der Fehler liegt auf der **Erstellerseite** |
| `NICHT-EINGESPIELT` | Die Ref steckt nicht in `HEAD` |
| `LOKAL` | Unversehrt und eingespielt, der Unterschied ist aber **nicht committet** |
| `UNERKLAERT` | Unversehrt und eingespielt, kein Commit erklärt den Unterschied — vermutlich eine Konfliktauflösung im Merge |
| `OFFEN` | Ohne Lieferref nicht einzuordnen (Verhalten bis Build 693) |

**Neuer Rückgabewert 3**, wenn *jede* Abweichung als `VERSCHMOLZEN` erklärt ist.
Bewußt nicht `0` — es *ist* ein Unterschied zur Lieferung, und wer maschinell
auswertet, soll ihn sehen. Bewußt auch nicht `1` — das heißt „hier muß jemand
hinsehen", und das trifft dann nicht mehr zu. `bundle_einspielen.sh` Schritt 8
wertet `3` aus und bricht nicht mehr ab.

**Ein zweiter, systematischer Fall verschwindet damit gleich mit:**
`merge-new-tickets.sh` **löscht** `issue-tracker/eintraege_claude_Build<N>.json`,
nachdem sie eingemischt wurde — so steht es in der Anleitung nach dem
Einspielen. Diese Datei steht aber in jeder Prüfsummenliste. Bis Build 693
meldete die Probe sie deshalb bei *jeder* Lieferung als `FEHLEND`, ohne
Erklärung. Jetzt steht der löschende Commit daneben.

**Was die Erweiterung nicht tut:** Sie prüft nicht, ob die verschmolzene Fassung
*fachlich* richtig ist. Das kann keine Prüfsumme. Dafür ist die Regression
zuständig, die im Einspielvorgang **vor** dieser Probe läuft (Schritt 6) — sie
hatte am 2026-08-11 längst grün gemeldet, als die Probe anschlug.

---

### 4.4b Das Werkzeug liefert sich selbst aus *(Build 666)*

Ändert eine Lieferung `tools/bundle_einspielen.sh`, wird sie noch mit der
**alten** Fassung eingespielt. Verbesserungen am Einspielen wirken erst ab der
**nächsten** Lieferung. Das ist nicht zu beheben, aber es wird angesagt:
`bundle_bauen.sh` schreibt seit Build 666 eine Warnung ins Protokoll.

Am 2026-08-04 ist genau das zweimal passiert — einmal in den fehlerhaften
Fetch-Refspec, einmal in den Abbruch „Ref existiert bereits", dessen Behebung in
ebendieser Lieferung steckte.

Damit sich das Skript nicht **während** des Laufs selbst wegräumt (Bash liest
Skripte nach Dateiposition, nicht am Stück), kopiert es sich beim Start nach
`/tmp` und startet sich von dort neu. Danach kann ihm kein Merge, kein Checkout
und kein Stash mehr den Boden wegziehen.

---

### 4.5 Eigene Arbeitszweige statt Arbeit auf master

**Festlegung 2026-08-02:** Auf `master` wird nicht mehr gearbeitet. Eigene
Arbeit läuft auf `alex/<thema>`.

Was das leistet — und was nicht. Es beseitigt **nicht** den Bedarf zu mergen:
die Arbeit muss weiterhin nach `master`, und wer dieselben Zeilen anfasst wie
eine Lieferung, bekommt weiterhin einen Konflikt. Der entsteht aus zwei
Bearbeitungen derselben Stelle, nicht aus der Zweigtopologie. Zweige verlegen
den Konflikt, sie beseitigen ihn nicht.

Was sie leisten:

- `master` steht immer auf einem geprüften Stand; Halbfertiges liegt woanders.
- Das Einspielskript stasht seit Build 666 **gar nicht mehr**: ein Arbeitsbaum
  mit verfolgten Änderungen führt zum Abbruch mit Anleitung. Der Stash war der
  einzige Zustand des Ablaufs, der sich nicht aus Git ableiten ließ — brach
  etwas zwischen Beiseitelegen und Zurückholen ab, blieb er liegen, und ein
  zweiter Lauf fand einen sauberen Baum und holte nichts zurück. Die Arbeit war
  nicht verloren, aber *still* verschwunden (GR1). Was nie beiseitegelegt wird,
  kann nicht liegenbleiben. Der Preis ist ein Handgriff, den man ohnehin haben
  will.
- Der Konflikt wandert an die bessere Stelle: auf den eigenen Zweig, mit echter
  Basis im Graphen, zu einem selbstgewählten Zeitpunkt.

```
git switch -c alex/thema          # anfangen
git switch alex/thema && git merge master     # aufschliessen
git switch master && git merge --no-ff alex/thema   # fertig
```

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
| Ist eine Abweichung ein Schaden oder eine Verschmelzung? | `tools/pruefe_lieferung.sh` hält die Datei gegen `refs/claude/build<N>` (Abschnitt 4.4a) |
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

**(f) `git bundle create` scheitert auf dem Ausgabe-Mount der Bauumgebung**

```
fatal: sha1 file '<stdout>' write error: Bad file descriptor
error: pack-objects died
```

`zip` und `cp` funktionieren dort dagegen. Die Ursache liegt im Mount, nicht in
git. `tools/bundle_bauen.sh` baut das Bundle deshalb in einem Stapelverzeichnis
unter `/tmp` und kopiert es erst danach.

**(g) `git status --porcelain` ist die falsche Probe für „muss ich stashen?"**

Eine einzige unverfolgte Datei genügte, damit das Einspielskript den
Stash-Zweig betrat. `git stash push` (ohne `-u`) meldete dann
`No local changes to save`, legte nichts an, und das folgende
`git rev-parse stash@{0}` brach ab. Die Probe muß genau das messen, was `stash`
auch mitnimmt: `git diff --quiet && git diff --cached --quiet`.

**(h) `git stash -u` räumt die Bundle-Datei mit beiseite**, wenn sie unverfolgt
im Arbeitsbaum liegt. Der Fetch scheiterte danach mit `does not appear to be a
git repository` — zwei Schritte später und ohne erkennbaren Bezug. Deshalb kein
`-u`, und deshalb wird der Bundle-Pfad vor dem Stash absolut aufgelöst.

**(i) Das Testprotokoll landete im Auslieferungsarchiv**, weil es im
Stapelverzeichnis lag. Es liegt jetzt außerhalb.

**Umgebung der Messung:** git 2.43.0, Linux-Bauumgebung. Die Bundle-Fassung ist
seit Git 1.5 unverändert lesbar; eine Fassungsabhängigkeit ist nicht zu erwarten,
aber beim ersten Einspielen in der VM zu bestätigen.

---

## 11. Offene Punkte

- **`refs/claude/*` auf GitHub?** Ob der Auslieferungsstand auch entfernt
  vorgehalten wird, ist nicht entschieden. Es hängt daran, ob GitHub hier Archiv
  oder nur Austauschpunkt ist.
- **Windows.** Erledigt sich: dort ist kein Git verfügbar, die Anlage bekommt
  einen vollständigen Rollout (Abschnitt 0). Der Bundle-Weg wird dort nie
  gefahren.

*Erledigt mit Build 662:* die maschinelle Vorabprobe (Abschnitt 3.3, jetzt
harter Abbruch in `tools/bundle_bauen.sh`).
