# `documents/` — Fachliche Unterlagen zum Verfahren

## Was hier hineingehört

Unterlagen, die den **Gegenstand** der Arbeit beschreiben oder festhalten:

* **Baupläne** (`Bauplan_*.md`) — was gebaut werden soll und warum.
* **Befunde** (`Befund_*.md`) — was gemessen wurde, mit den Messwerten und
  der Angabe, was daraus folgt und was ausdrücklich **nicht**.
* **Leitfäden und Modelle** — Datenmigrationsleitfaden, Statusmodelle,
  Übergaben zwischen Bauabschnitten.

## Was hier **nicht** hineingehört

* **Verwaltungsthemen** — Arbeitsvereinbarungen, Argumentationslinien für die
  Staatsanwaltschaft, Zuständigkeiten, Kommunikation. Die gehören nach
  `management/`.
* **Messvorrichtungen und Rohausgaben** — die gehören nach `debug/`; hier
  steht die Auswertung, nicht das Werkzeug.

## Was ein Befund enthalten muss

1. **Die Messwerte selbst**, nicht ihre Zusammenfassung. Wer den Befund liest,
   muss ihn nachrechnen können.
2. **Herkunft der Messung**: Werkzeug, Buildnummer, MD5, Datum, Umgebung.
3. **Was widerlegt wurde** — auch und gerade eigene frühere Annahmen.
4. **Was offen bleibt.** Eine Grenze der eigenen Messung zu verschweigen ist
   dieselbe Auslassung wie ein übergangener Beleg (Grundregel 1).
