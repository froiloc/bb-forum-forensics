# Regelwerk AIW — Code

**Stand:** Build 628 · 2026-08-01

## 1. JavaScript

Die fünf Gebote stammen aus den Projektanweisungen (mc).

**JS1 — IIFE-Wrapper für jede Datei.**

```js
(function () {
    'use strict';
    // ...
})();
```

**JS2 — Exzessives Debug-Logging für die Entwicklungsphase, zur Laufzeit abschaltbar.**
Hausmuster: ein Schalter `window.AIW_COCKPIT_DEBUG`, eine `log()`-Funktion mit Modulpräfix.

```js
function debugOn() {
    return (typeof window !== 'undefined') && window.AIW_COCKPIT_DEBUG === true;
}
```

**JS3 — Ausführlich kommentieren.** Was bezweckt wird und welche Überlegung zum gewählten Verfahren geführt hat.

**JS4 — Klassen kapseln, wo es nur geht.**

**JS5 — Reine Funktionen fassen NIE das DOM an.** Nur die `render*`-Funktionen berühren `document`. Ein UMD-artiger Ausgang (`module.exports` und `window.*`) sorgt dafür, dass vitest den **echten** Code prüft und nicht eine grüne, aber tote Kopie.

### Sicherheit

**Variabler Text ausschließlich über `textContent`, niemals über `innerHTML`.** Die Freitexte stammen aus der rechtegekapselten Fachschicht, sind aber grundsätzlich als fremdbestimmt zu behandeln — Forennamen sind Fremdtext.

### Ladereihenfolge

Zugriffe auf gemeinsame Werkzeuge (`window.AIWTableKit`) erfolgen **lazy**, in der Funktion und nicht beim Laden. Ein späterer Umbau der Reihenfolge soll eine Sicht nicht lautlos brechen.

### Debugging im Browser

Oberstes Gebot bei der Fehlersuche (Festlegung mc): **erst** Konsolenausgabe für sehr ausgabelastigen Testcode anfordern, **dann** einen Machbarkeitsnachweis für die Konsole liefern, und **erst wenn das klappt** einen Fix zum Ausrollen schreiben. Zu jedem Debugging-Code gehört die Anweisung, wann, wo und wie er auszuführen ist und was dabei zu beobachten ist.

## 2. Python

**PY1 — Jede Klasse in eine eigene Datei** (GR10).

**PY2 — Reine Funktionen von der Ein-/Ausgabe trennen.** Was gerechnet wird, wird ohne Datenbank und ohne Dateisystem gerechnet und ist damit direkt prüfbar.

**PY3 — Eingefrorene Datenklassen für Register und Kataloge.**
`@dataclass(frozen=True)` mit einer `__post_init__`, die den Eintrag gegen sich selbst prüft. Ein unstimmiger Eintrag scheitert beim Laden und nicht im Betrieb. Vorbild: `management/stats/glossary.py`.

**PY4 — Lesend heißt technisch lesend.**
Wer nur liest, öffnet mit `sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)`. Eine Zusicherung im Kommentar ist keine Sperre.
*Befund 2026-07-31:* `workload_admin` und `support_overview_admin` sichern im Kopf zu, ausschließlich zu lesen, öffnen aber schreibfähig. Sie schreiben nichts — aber die Zusicherung ist nicht durchgesetzt (Issue `906ede75-a898-405c-8d80-1548e8b5b553`).

### PY4 im Einzelnen — bei SQLite ist Lesen nicht folgenlos

**Das ist der Grund, warum PY4 strenger ist als bei anderen Dateien.** Bei einer gewöhnlichen Datei ist Öffnen ohne Wirkung. Bei SQLite kann das bloße `connect()` **schreiben**. Gemessen am 2026-08-01 (Python 3.13):

| Lage | gewöhnliches `connect()` | mit `mode=ro` |
|---|---|---|
| Datei mit heißem `-journal` | SQLite **spielt das Journal zurück** — aus 34 MB Teildatei werden 0 Byte | `attempt to write a readonly database`, **Datei bleibt unberührt** |
| Pfad existiert nicht | **legt die Datei an** (0 Byte) | `unable to open database file` |
| `apply_journal_mode` auf der Verbindung | setzt ein PRAGMA — ein Schreibvorgang an der Datei | entfällt |
| `VACUUM INTO` | gelingt | **gelingt ebenfalls** — die Zusage kostet nichts |
| `wal_checkpoint(PASSIVE)` | führt aus | liefert still `(0,0,0)` — **tut nichts** |

Daraus folgen drei Anwendungsregeln:

1. **Der Journalmodus gehört nicht auf eine lesende Verbindung.** Er ist eine Eigenschaft der *Datei*, nicht der Verbindung, und ihn zu setzen ist ein Schreibvorgang.
2. **Ein Checkpoint gehört ausdrücklich auf eine schreibfähige Verbindung.** Er schreibt naturgemäß; read-only fällt er *still* aus, und ein stiller Nichtlauf ist das schlechteste Ergebnis. Das ist die einzige begründete Ausnahme im Sicherungspfad — sie steht bei `BackupExecutor._checkpoint_passive`.
3. **Wer eine Datei nur beurteilen will, sieht erst nach, ob ein `-journal` oder `-wal` daneben liegt** — und öffnet sie dann gar nicht. Das Journal *ist* in dem Fall schon die Antwort.

**Durchgesetzt wird PY4 je Modul über den Syntaxbaum**, nicht über eine Textsuche. Muster: `tests/test_backup_executor.py` BR02 — es sammelt alle `sqlite3.connect`-Aufrufe ohne `mode=ro` und verlangt für den Sicherungspfad: in `harness/backup.py` und `backup_pruefer.py` **keinen**, in `backup_executor.py` **genau einen**, und der muss in `_checkpoint_passive` stehen.
*Warum nicht per Textsuche:* Die erste Fassung von BR02 suchte die Zeichenfolge `sqlite3.connect(` — und fand dabei den **Kommentar**, der die Änderung erklärt. Eine Prüfung, die ihre eigene Begründung für einen Befund hält, ist unbrauchbar.

**Der Befund, der zu dieser Verschärfung führte — und er ist meiner.** Build 625 führte `_traegt_inhalt` ein, um eine unbrauchbare Sicherung zu erkennen, **ohne sie zu löschen** — ausdrücklich, damit die Teildatei als Beleg erhalten bleibt. Die Funktion öffnete gewöhnlich. Bei einem heißen Journal hat also genau die Funktion, die den Beleg erhalten sollte, ihn beim Ansehen vernichtet. Behoben in Build 626.

**Damit ist das Muster im Bestand viermal aufgetreten:** `906ede75`, der Wartungsvorbehalt bei `convert_journal_mode` („eine Zusage im Kommentar ist keine technische Sperre"), `e9522fe2` zweiter Teil (Build 627) — und der Fall aus Build 625. Der letzte zeigt: **das Wissen um das Muster schützt nicht davor, solange es keine Prüfung gibt.** PY4 stand seit Build 607 in diesem Blatt.

**PY5 — Jeder Schreibweg läuft über das Gateway.**
`CoordinatorWriter(con, AuditLog(con))`. Damit entsteht zu jeder Änderung ein Beleg in der lückenlosen Kette. Ein Schreibweg daran vorbei wäre ein unauditierter Nebeneingang.

## 3. Kommentare

**KO1 — Der Kommentar erklärt das WARUM, nicht das WAS.**

**KO2 — Ein Befund gehört in den Kommentar, samt Datum und Anlass.**
Der wertvollste Kommentar im Bestand ist der, der sagt: „Das sah hier einmal anders aus, und deshalb ist es jetzt so." Er verhindert, dass jemand die Verbesserung für Umständlichkeit hält und zurückbaut.

**KO3 — Eine überholte Begründung ist nicht falsch, sondern überholt.**
Wer sie ersetzt, sagt das — Beispiel im Kopf von `cockpit_personnel.js`: „DIE ALTE BEGRÜNDUNG WAR ÜBERHOLT, NICHT FALSCH."

**KO4 — Eine Ausnahme wird benannt und begründet, nie stillschweigend genommen** (GR1).

## 4. Tests

**TE1 — Ein Test, der von der Umgebung abhängt, ist kein Test.**
*Befund 2026-07-31 (Build 606):* Eine Gegenprobe ließ „das erste Element der sortierten Liste" weg und setzte damit voraus, dass die gefundene Menge genau dem Katalog entspricht. In der Anlage lag eine zusätzliche Datei — weggelassen wurde die überzählige, und der Test meldete „DID NOT RAISE". Jetzt wird ein namentlich bekannter Eintrag weggelassen.

**TE2 — Ein Test, der Falsches meldet, wird abgeschaltet.**
Deshalb ist eine Fehlmeldung ein Fehler erster Ordnung. Wird eine gefunden, gehört die Korrektur samt Anlass in den Test.
*Befund 2026-07-31:* Eine Prüfung fasste alle Datenbankangaben eines Katalogeintrags zu einem Text zusammen und hielt deshalb ein harmloses Werkzeug für gefährlich. Jetzt wird je Zeile geprüft.

**TE3 — Jeder Test trägt eine Kennung** (`UX05`, `SP08`, `CK02`) und im Dateikopf eine Liste, was er prüft.

**TE4 — Der Dateikopf sagt auch, was der Test NICHT kann.**
Ein halbes Netz, das sich für ein ganzes ausgibt, ist gefährlicher als gar keines.

**TE5 — Eine Gegenprobe gehört dazu.**
Zu jeder Prüfung, die etwas verbietet, gehört ein Test, der zeigt, dass sie bei einem echten Verstoß auch anschlägt.

**TE6 — Eine Ausnahmeliste wird gegen die Wirklichkeit geprüft.**
Jede genannte Ausnahme muss es geben (oder ihre Nichtprüfbarkeit muss begründet sein). Sonst bleibt eine Ausnahme stehen, deren Gegenstand längst umbenannt wurde — und die nächste Lücke fällt durch.

## 5. Abgabe

Vor jeder Übergabe:

1. `python -m py_compile` je geänderter `.py`, `node --check` je geänderter `.js` (GR9)
2. `python run_tests.py` — beide Suiten grün (GR2, GR3)
3. `build.json` mit iterierter Buildnummer und Änderungsvermerk (GR4, GR5)
4. `MD5SUMS_Build<N>.txt` erzeugen (GR8) und mit `tools/pruefe_auslieferung.py` prüfen
5. Auslieferung als `.zip` mit Originalstruktur, nur die berührten Dateien (GR7)
6. Ankerdelta vermerken (Katalog, Gruppen, Rechte)
7. **Liegt eine Eingangsdatei für den Vorgangstracker bei:**
   `cd issue-tracker && python merge.py --validate-only eingang_<name>.json`

### AB1 — Eine Eingangsdatei wird geprüft, bevor sie jemand einspielt

`merge.py --validate-only` ist der maßgebliche Weg (Hinweis mc, 2026-08-01). Er wertet das Schema aus — **einschließlich `maxLength: 80` für den Titel**.

*Befund 2026-08-01:* Drei von mir gelieferte Vorgänge hatten Titel von 107, 109 und 90 Zeichen. mc mußte sie vor dem Einpflegen von Hand kürzen. Die Grenze stand die ganze Zeit im Schema; meine Prüfung war auf „nur die Pflichtfelder" zurückgefallen, weil das Paket `jsonschema` im Container fehlte — und ich habe diesen Rückfall hingenommen, statt ihn zu beheben.

**Ein Rückfall auf die halbe Prüfung ist ein Befund, keine Umgehung.** Wer eine Prüfung abschwächt, weil ein Werkzeug fehlt, hat die Prüfung abgeschafft und merkt es nur später.

*Durchsetzung im Regressionslauf:* `tests/test_issue_eingang_schema.py`. IE02 hält die Titellänge **ohne** `jsonschema` — die Grenze wird dabei aus dem Schema gelesen und nicht abgeschrieben (IE05), sonst gäbe es zwei Wahrheiten. IE01 prüft vollständig gegen das Schema und wird sichtbar übersprungen, wenn das Paket fehlt; ein übersprungener Test steht im Lauf, ein stillschweigend weggelassener nicht.

**Der Titel ist eine Überschrift, kein Satz.** Was nicht in 80 Zeichen paßt, gehört in `description` — und beim Kürzen geht nichts verloren: der ursprüngliche Wortlaut wandert dorthin.
