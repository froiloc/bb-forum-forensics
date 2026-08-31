# `tools/` — Werkzeuge für die Befehlszeile

## Was hier hineingehört

Eigenständig aufrufbare Kommandozeilenwerkzeuge für Betrieb, Migration,
Diagnose und Prüfung. Ein Werkzeug in diesem Verzeichnis wird von Menschen
aufgerufen, nicht von der Anwendung importiert.

## Was hier **nicht** hineingehört

* **Fachlogik.** Nach Grundregel 10 gehört der Vorgang in ein eigenes Modul —
  in der Regel unter `management/maintenance/`. Die Datei hier ist die
  Befehlszeile davor: Argumente, Wartungsvorbehalt, Ausgabe, Protokoll,
  Rückgabewert. `tools/postid_nachtragen.py` gegen
  `management/maintenance/postid_nachtrag.py` ist das Muster.
* **Einmalige Wegwerfskripte.** Die gehören nach `debug/`.
* **Von der Anwendung importierte Module.** Die gehören in ihr Fachpaket.

## Pflichten für jede neue Datei

1. **Katalogeintrag in `management/help/cli_katalog.py`.** Ohne ihn ist
   `tests/test_help_cli_katalog.py::test_ck02_vollzaehligkeit_in_beide_richtungen`
   rot — und das ist Absicht: ein Werkzeug, von dem niemand weiß, ist im
   Betrieb dasselbe wie keines, nur gefährlicher, weil es trotzdem laufen kann.
2. **`--help` mit Epilog.** Drei Zeilen am `ArgumentParser`:
   `epilog=cli_epilog.epilog("<schluessel>")`,
   `formatter_class=cli_epilog.HilfeFormat` und der Import. Der Epilog wird
   **aus dem Katalog erzeugt** und nicht je Werkzeug abgeschrieben.
3. **Regressionstest unter `tests/`.** Jede Gegenprobe muss anschlagen können:
   zu jedem Test gehört die Angabe, was ihn rot macht.
4. **Rückgabewerte**, im Katalog benannt. 0 heißt „durchgelaufen und nichts
   offen", nicht „das Programm ist nicht abgestürzt".
5. **Schreibende Werkzeuge**: Wartungsstufe in
   `maintenance/wartungsstufen.py` eintragen, Sicherung vor dem ersten
   schreibfähigen Öffnen, Beleg in der Hash-Kette. Lesende Werkzeuge öffnen
   ihre Datenbanken über `file:…?mode=ro` — nicht „sie schreiben nicht",
   sondern sie können es nicht.
