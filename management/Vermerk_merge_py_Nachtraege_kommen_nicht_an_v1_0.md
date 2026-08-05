# Vermerk: Warum `merge.py` reine Historien-Nachträge verwirft

**Vorgang:** `7d3c1a95` · **Stand:** 2026-08-05 · **Build:** 672 · **Verfasser:** Claude

Alex' Frage war: *„Was ist das Problem mit `merge.py`? Ich dachte, das wäre
alles bereits okay damit."* Dieser Vermerk beantwortet sie vollständig.

---

## 1. Die kurze Antwort

**Was du in den Builds 668 und 669 gebaut hast, ist in Ordnung und wirkt.**
Der neue Fehler liegt nicht darin — er liegt in einer Lücke, die *daneben*
offengeblieben ist und die niemand angesehen hat, weil sie in die
Gegenrichtung zeigt.

| Build | Was abgesichert wurde | Richtung |
|---|---|---|
| 668 | `merge-new-tickets.sh` konnte nie laufen; Historie ging beim Ersetzen verloren | Verlust beim **Ersetzen** |
| 669 | Wächter prüfte nur Anwesenheit, nicht Zulässigkeit der Felder | Abweisung durch die **Einspielseite** |
| **offen** | **Ein reiner Nachtrag kommt gar nicht erst an** | **Verlust beim Nicht-Ersetzen** |

Alle drei sind dieselbe Fehlerfamilie: *etwas verschwindet, und die Meldung
sagt „erfolgreich".* Die ersten beiden sind erledigt. Der dritte war nie
Gegenstand.

---

## 2. Was genau passiert ist

Am 05.08.2026 habe ich eine Eintragsdatei gebaut, die zu **zwei bereits
vorhandenen** Vorgängen (`2f1044b9`, `aa0d9033`) je einen Update-Eintrag
nachtrug. Sonst nichts — kein Statuswechsel, keine Textänderung.

Auf einer Wegwerfkopie des Bestandes gefahren:

```
   • 0 neue Issues hinzugefügt
   • 0 Issues aktualisiert
   • 0 Issues übersprungen
   • 0 Konflikte gelöst

  eingemischt und entfernt: eintraege_claude_Build671.json
Fertig: 1 Datei(en) eingemischt.
```

Danach im Bestand nachgesehen: **unverändert zwei statt drei Update-Zeilen je
Vorgang.** Der Nachtrag war nicht angekommen. Die Quelldatei war gelöscht.

Drei Dinge fallen zusammen, und erst zusammen sind sie gefährlich:

1. Der Inhalt kam nicht an.
2. Das Skript meldete Erfolg.
3. Die Quelldatei wurde gelöscht — der Nachtrag ist damit **nirgends** mehr.

---

## 3. Warum das passiert — die Stelle im Code

`merge.py`, `detect_conflicts()` (Z. 431/432):

```python
comparable_fields = ["title", "description", "status", "priority", "severity",
                     "assigned_to", "target_version", "affected_version"]
```

`updates` steht bewusst **nicht** darin — und das ist auch richtig so: sonst
wäre jede Historienerweiterung ein „Konflikt", und der Lauf würde bei jedem
zweiten Vorgang nachfragen.

Die Folge ist trotzdem fatal, weil `merge.py` für einen gelieferten Vorgang nur
**zwei** Wege kennt:

```
Kennung unbekannt?  ──ja──>  neuer Vorgang, wird angehängt
        │ nein
        v
Eines der acht Felder abweichend?  ──ja──>  Konflikt, --auto-resolve source
        │ nein                              ersetzt den Vorgang vollständig
        v
      (nichts)          <── HIER fällt der reine Nachtrag hindurch
```

Ein Vorgang, dessen Kennung bekannt ist und dessen acht Vergleichsfelder
gleich sind, ist **weder neu noch konfliktbehaftet**. Er nimmt keinen der
beiden Zweige. Es gibt keinen dritten.

**Die Ironie:** `merge.py` hat die passende Strategie längst — die
`ResolutionStrategy.MERGE_UPDATES` (Z. 628 ff.) tut genau das Richtige: Ziel
behalten, fehlende Updates aus der Quelle nachtragen, nach Zeitstempel
abgeglichen. Sie wird auf diesem Weg nur **nie erreicht**, weil der Vorgang
gar nicht erst als behandlungsbedürftig erkannt wird.

---

## 4. Warum die Wächter grün waren

`IT01` bis `IT05` waren **alle grün**, während der Nachtrag ins Leere lief.
Das ist kein Versagen der Wächter, sondern eine Grenze ihres Zuschnitts:

> **Sie prüfen die Datei. Sie prüfen nicht ihre Wirkung.**

`IT03` insbesondere fragt: *„Bringt die gelieferte Fassung die vorhandene
Historie mit?"* — Ja, tat sie. Vollständig. Niemand fragte die Gegenrichtung:
*„Kommt das Neue auch an?"*

Das ist dieselbe Lehre wie bei `IT02` in Build 669, nur an anderer Stelle: ein
Wächter, der die halbe Frage stellt, gibt eine Sicherheit vor, die er nicht
hat.

---

## 5. Was ich bereits geliefert habe (Build 671)

**`IT06`** in `tests/test_issue_tracker_eintraege.py`. Er läuft auf der
**Erstellerseite**, also bevor geliefert wird, und fragt:

> Trägt eine gelieferte Fassung neue Update-Zeitstempel, unterscheidet sie sich
> dann auch in mindestens einem der acht Vergleichsfelder?

Wenn nein, schlägt er an, nennt Vorgang und Datei und nennt die Abhilfe.

**`IT06` ist ausdrücklich keine Behebung.** Er verhindert nur, dass eine
Lieferung lautlos ins Leere geht. Der Fehler sitzt in `merge.py`, und
`merge.py` ist dein Werkzeug — ich fasse es nicht ohne deine Entscheidung an.

---

## 6. Was zu tun wäre — drei Bausteine

### (a) Der dritte Zweig in `merge.py` — die eigentliche Behebung

In `detect_conflicts()` zusätzlich prüfen, ob die Quelle Update-Zeitstempel
trägt, die das Ziel nicht hat. Wenn ja: Vorgang zur Behandlung vormerken, aber
**nicht** als Konflikt im engeren Sinne, sondern mit fest gesetzter
`ResolutionStrategy.MERGE_UPDATES`. Kein Nachfragen, keine Ersetzung, nur
Anhängen — die Funktion dafür ist da und wird schon getestet.

*Aufwand:* klein. *Risiko:* gering — der neue Zweig greift nur in einem Fall,
der heute gar nicht behandelt wird. *Wirkung:* der Nachtrag kommt an.

### (b) Löschen erst nach Gegenprobe — in `merge-new-tickets.sh`

Heute löscht das Skript die Quelldatei, wenn `merge.py` Erfolg meldet. Besser:
nach dem Lauf nachsehen, ob **jede** Kennung aus der Quelldatei im Bestand
steht und **jeder** gelieferte Update-Zeitstempel dort vorkommt. Erst dann
löschen.

*Begründung:* Das ist dieselbe Sorgfalt, die `pruefe_lieferung.sh` beim
Einspielen leistet — die Meldung des Werkzeugs ist nicht der Beleg, der
Bestand ist es. Ohne (b) bleibt jede künftige Lücke in `merge.py` eine Lücke
**mit** Datenverlust; mit (b) ist sie nur noch eine Lücke.

### (c) `IT06` bleibt

Auch nach (a) und (b) sinnvoll: er meldet den Fall, bevor überhaupt geliefert
wird, und kostet nichts.

**Empfehlung:** alle drei. (b) ist mir dabei fast wichtiger als (a) — (a)
schließt *diese* Lücke, (b) sorgt dafür, dass die *nächste* nicht wieder Daten
kostet.

---

## 7. Was ich nicht getan habe, und warum

Ich habe `merge.py` und `merge-new-tickets.sh` **nicht** angefasst. Beide sind
in den Builds 668 und 669 von dir gebaut und begründet worden, und die
Begründungen stehen ausführlich in den Dateiköpfen. Ein Eingriff von mir ohne
Absprache würde genau die Sorgfalt untergraben, die dort investiert wurde.

Sag mir, ob ich (a) und (b) bauen soll — dann liefere ich sie mit
Regressionsfällen, die den Verlustfall vorher nachstellen und nachher
ausschließen.
