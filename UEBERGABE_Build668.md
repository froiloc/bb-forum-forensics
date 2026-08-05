# Übergabe Build 668 — Der Tracker sagte die Unwahrheit, seit Build 661

**Baubasis:** `d8a2399` (Build 667) · **Lieferung:** 0.8.668 · 2026-08-05
**Zweig:** `claude/build668` · **Verfahren:** Git-Bundle nach `documents/data-exchange.md`

---

## 1. `merge-new-tickets.sh` konnte nicht funktionieren

```bash
python merge.py eintraege_claude_Build*.json --auto-resolve source && rm ...
```

`merge.py` nimmt **genau eine** Quelldatei. Das Muster expandierte zu sieben, argparse brach ab:

```
merge.py: error: unrecognized arguments: eintraege_claude_Build662.json …
```

Es scheiterte **sicher** — durch das `&&` wurde nichts gelöscht. Aber es lief nie. Deshalb lagen die Eintragsdateien seit Build 661 unbearbeitet da, und der Tracker führte erledigte Arbeit als offen.

**Neu geschrieben**, mit drei Zusagen: Abbruch beim ersten Fehler (sonst liefe der Rest weiter, während eine Datei stillschweigend liegenbliebe) · Löschen nur bei Erfolg genau dieser Datei · Zählung und Abschlussmeldung, weil ein stiller Erfolg von einem stillen Ausfall nicht zu unterscheiden ist. Dazu ein `--trocken`-Lauf: bei Daten, die nur in einer Datei liegen, sollte man vorher sehen können, was passiert.

---

## 2. Der wichtigere Teil: die Strategie hätte Historie gekostet

Ich habe nachgelesen, was `merge.py` bei einem Konflikt **tatsächlich** tut — und keine der beiden Strategien ist für sich richtig:

| Strategie | Status | Historie |
|---|---|---|
| `--auto-resolve source` (so stand es im Skript) | ✔ richtig | ✘ „Issue erstellt" (Alex, 2026-08-03) **verschwindet** |
| `--auto-resolve merge` | ✘ bliebe `open` | ✔ bliebe erhalten |

`source` ersetzt den Vorgang vollständig, `merge` behält den Ziel-Vorgang und hängt nur neue Updates an. Betroffen wären `65a230fd` und `d3f933cd` — die beiden Tickets vom Sitzungsbeginn.

**Deshalb wurde nicht die Strategie gewechselt, sondern die Quelle vollständig gemacht.** Die gelieferte Fassung trägt den ursprünglichen Eintrag jetzt mit, chronologisch einsortiert. Damit ist `--auto-resolve source` verlustfrei: Historie bleibt, Status stimmt.

**Warum das ein GR1-Fall ist:** `merge.py` meldet einen erfolgreichen Merge, auch wenn dabei eine Zeile Historie verschwindet. Der Verlust wäre lautlos. Der Tracker ist Teil der Projektdokumentation — verlorene Historie ist dort dasselbe wie eine stille Auslassung im Befund.

**`IT03` ist der Wächter** und prüft das auf der *Erstellerseite*, bevor irgendetwas eingemischt wird: liegt ein Vorgang bereits in `data/issues.json`, muss die gelieferte Fassung alle dort vorhandenen Update-Zeitstempel enthalten. Gegenprobe gefahren — Eintrag testweise entfernt, `IT03` fällt und nennt Vorgang und Zeitstempel.

---

## 3. Echter Lauf, auf einer Wegwerfkopie

Nicht auf dem Bestand — auf einer Kopie in `/tmp`:

```
6 Dateien eingemischt und entfernt
167 Vorgaenge im Ergebnis

65a230fd | closed   | 3 Updates | ['Alex', 'Claude', 'Alex']
d3f933cd | resolved | 2 Updates | ['Alex', 'Claude']
```

Der erste Eintrag stammt in beiden Fällen von dir. Nichts verloren.

---

## 4. `data/issues.json` liegt nicht im Bundle — mit Absicht

Du legst dort laufend Vorgänge an. Eine parallel geänderte Fassung ergäbe einen Konflikt in einer großen JSON-Datei — genau die Sorte, die man nicht von Hand auflösen will. Das Einmischen gehört auf die Einspielseite und dauert Sekunden.

`eintraege_claude_Build661.json` ist **entfernt**: der Trockenlauf ergab 0 neue Vorgänge und 0 Konflikte, der Inhalt steckt bereits im Bestand.

---

## 5. Nach dem Einspielen

```bash
cd issue-tracker
./merge-new-tickets.sh --trocken      # erwartet: 7 Dateien, 12 neu, 2 Konflikte
./merge-new-tickets.sh                # wirklich einmischen
```

**Die Gegenprobe, auf die es ankommt:** `65a230fd` muss danach auf `closed` stehen **und drei Update-Einträge haben, deren erster von dir stammt** („Issue erstellt"). Fehlt dieser Eintrag, ist Historie verloren gegangen — dann bitte melden und `data/issues.json` **nicht** committen; die Sicherung liegt in `issue-tracker/backups/`.

Danach `data/issues.json` committen.

---

## 6. Offene Punkte

* **Weiterhin offen:** die Entscheidung zu Build 663 §3 — die Von→Bis-Übernahme liegt nur auf der Eingabemaske, nicht auf den beiden Filtern.
* **Zwei kritische Vorgänge warten auf Abnahme, nicht auf Entwicklung:** `651e6d84` (Sicherung verdrängt gute Generationen — behoben in 625–627, Status `testing`) und `317481d3` (Lektorat-Anker — geliefert in 659/661). Nach dem Einmischen stehen sie wieder korrekt in der Liste.
* **Auf dein Wort:** 173 `MD5SUMS_Build*.txt` im Wurzelverzeichnis — Belege, gehören nicht gelöscht, aber ein Unterverzeichnis wäre übersichtlicher.
* **Befund aus Build 666, unverändert:** der CLI-Katalog führt ausschließlich Python-Werkzeuge; die Shell-Werkzeuge des Datenaustauschs stehen dort nicht. Maßgeblich ist `documents/data-exchange.md`.
