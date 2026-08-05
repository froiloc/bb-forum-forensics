# Übergabe Build 669 — Nachbesserung zu 668

**Baubasis:** `659506d` (Build 668) · **Lieferung:** 0.8.669 · 2026-08-05
**Zweig:** `claude/build669` · **Verfahren:** Git-Bundle nach `documents/data-exchange.md`

---

## 1. Mein Fehler, zuerst

Der Titel des Vorgangs `f39ad572` war **85 Zeichen** lang, das Schema erlaubt 80. `merge.py` hat die Datei abgewiesen — **bevor etwas geschrieben wurde**. Der Bestand blieb unverändert, die Datei blieb liegen. Die Sperre auf deiner Seite hat genau das getan, wofür sie da ist.

Titel gekürzt auf 78 Zeichen, mit einem Vermerk in der Historie des Vorgangs.

---

## 2. Die eigentliche Lücke war mein Wächter

`IT02` prüft, **ob** die Pflichtfelder vorhanden sind — nicht, ob ihr Inhalt zulässig ist. Er war grün, während die Einspielseite die Datei abwies.

Ein Wächter, der nur die Anwesenheit prüft, gibt eine Sicherheit vor, die er nicht hat. Das ist schlechter als gar keiner, weil man sich auf ihn verlässt.

**`IT02b`** prüft jetzt die Grenzen des Schemas: `maxLength`, `minLength`, `enum`, `pattern`, `minimum`, `maximum`. Gegenprobe gefahren — Titel künstlich verlängert, der Test fällt und nennt Vorgang, Feld und beide Zahlen.

**Bewusst ohne `jsonschema`:** die Bibliothek ist keine Abhängigkeit dieses Projekts, und die Produktionsumgebung ist offline. Ein Wächter, der nur dort läuft, wo man Pakete nachinstallieren kann, hilft genau dann nicht, wenn man ihn braucht.

---

## 3. `--force` ist aus dem Skript entfernt

Ich habe nachgelesen, was der Schalter wirklich tut — und er hebt genau die Sperre auf, die uns gerade geschützt hat:

* **ohne `--force`:** merge.py bricht ab, *bevor* etwas geschrieben wird. „Es wurde NICHTS geschrieben."
* **mit `--force`:** die gültigen Vorgänge werden eingepflegt, die ungültigen mit einer Warnung übergangen. In einer Datei mit mehreren Einträgen fände sich der übergangene nur noch in einer Zeile weiter oben — und mein `rm` löscht die Datei danach.

Das wäre die Sorte Verlust, gegen die Build 668 gebaut wurde. Ich hatte den Schalter mit „keine Rückfragen" begründet, ohne nachzusehen, was er sonst noch aufhebt.

---

## 4. Der Abbruch erklärt sich jetzt

Bei deinem Lauf beendete `set -e` das Skript wortlos; auf dem Bildschirm stand nur die Ausgabe von merge.py. Ein EXIT-Trap nennt jetzt die betroffene Datei, dass sie **nicht** gelöscht wurde, dass der Bestand unverändert ist, und dass die bereits eingemischten Dateien erledigt sind. Dieselbe Lehre wie bei `bundle_einspielen.sh` in Build 665 — offenbar musste ich sie zweimal lernen.

---

## 5. Und eine Beobachtung aus deinen beiden Ausgaben

Der Trockenlauf meldete für `Build664` **„1 neu, 0 Konflikte"**, der echte Lauf **„0 neu, 1 Konflikt"**. Das ist kein Fehler: der Trockenlauf prüft jede Datei gegen den *jetzigen* Bestand, im echten Lauf wirken sie nacheinander — `Build663` hatte den Vorgang `7b2f4a19` kurz zuvor angelegt. Beides ist richtig, es sind verschiedene Fragen. Der Trockenlauf sagt das jetzt selbst dazu, damit die Abweichung nicht für einen Fehler gehalten wird.

---

## 6. Erprobt

Zwei Läufe auf einer Wegwerfkopie:

```
ungueltiger Vorgang -> Abbruch mit Erklaerung, Datei bleibt, Bestand unveraendert
nach dem Beheben    -> eingemischt, 168 Vorgaenge,
                       f39ad572 mit 78 Zeichen und drei Update-Eintraegen
```

---

## 7. Nach dem Einspielen

```bash
cd issue-tracker
./merge-new-tickets.sh --trocken      # erwartet: 2 Dateien, 2 neu, 0 Konflikte
./merge-new-tickets.sh
```

`f39ad572` muss danach im Bestand stehen. Dann `data/issues.json` committen.

---

## 8. Offene Punkte

* **Weiterhin offen:** die Entscheidung zu Build 663 §3 — die Von→Bis-Übernahme liegt nur auf der Eingabemaske, nicht auf den beiden Filtern.
* **Warten auf Abnahme, nicht auf Entwicklung:** `651e6d84` (Sicherung verdrängt gute Generationen) und `317481d3` (Lektorat-Anker). Beide stehen jetzt korrekt im Tracker.
* **Auf dein Wort:** 173 `MD5SUMS_Build*.txt` im Wurzelverzeichnis — Belege, ein Unterverzeichnis wäre übersichtlicher.
