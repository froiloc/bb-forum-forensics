# Regelwerk AIW — Code

**Stand:** Build 607 · 2026-07-31

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
