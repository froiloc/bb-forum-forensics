# `tests/` — Regressionstests

`python run_tests.py` fährt beide Suiten: pytest für Python, vitest für
JavaScript. **Nur ein grüner Gesamtlauf darf ausgeliefert werden**
(Grundregel 9).

## Was hier hineingehört

Ein Test je Bauteil, benannt nach dem Bauteil (`test_<modul>.py`). Innerhalb
der Datei tragen die Fälle **Kennungen** (`PN62`, `CK02`, `XV04` …), damit ein
roter Fall in einem Protokoll benannt werden kann, ohne die Datei zu öffnen.

## Die Regel, die dieses Projekt teuer bezahlt hat

> **Jede Gegenprobe muss anschlagen.**

Zweimal in der Buildreihe 750–752 wurde ein Schutz stillgelegt und **kein Test
rot**; zweimal war ein Testwortlaut so gewählt, dass der Fall nie prüfte, was
sein Name behauptete. Beides fiel nur auf, weil eine **neue** Prüfung dazukam.

Deshalb gilt für jeden Test hier:

1. Im Docstring steht, **was ihn rot macht** — nicht, was er tut.
2. Wo ein Satz oder ein Befund erwartet wird, gehört die **Gegenrichtung**
   dazu: ein Werkzeug, das den Satz immer druckt, muss durchfallen.
3. Eine Vorrichtung (Fixture) bildet den **gemessenen** Aufbau nach, nicht
   einen gedachten. Steht im Bestand `Elementindex = 2·Platz + 3`, dann steht
   das auch in der Vorrichtung — sonst prüft der Test einen Aufbau, den es
   nicht gibt.

## Was hier nicht hineingehört

Prüfungen, die ein laufendes System, ein Netz oder echte Fallakten brauchen.
Tests laufen gegen Wegwerf-Bestände unter `tmp_path`; **niemals** gegen
`data/evidence/` oder `data/forensic/`.
