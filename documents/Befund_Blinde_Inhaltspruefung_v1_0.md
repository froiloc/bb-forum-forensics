# Befund: Die Prüfung war blind für den Inhalt

**Fassung 1.0 · 31.08.2026 · Build 754 · Basis `origin/master 090154e`**

---

## 1. Die Frage

> „Sind in der `anker_diagnose.py` die Anker mit dem Text verglichen worden?
> Oder war das Skript zufrieden, wenn es die Position gefunden hat, und hat
> nicht mehr geprüft, ob der Text passt?" — Alex, 31.08.2026

## 2. Die Antwort: es war zufrieden

`management/maintenance/anker_diagnose.py`, `_anker_pruefen()` — die ganze
Prüfung bestand aus zwei Fragen:

```python
if marke == "text()":
    da = sicht.textknoten(knoten)
    trifft = 1 <= wunsch <= da          # gibt es den n-ten Textknoten?
…
naechster = sicht.schritt(knoten, marke, wunsch)
if naechster is None:                   # gibt es das n-te <div>?
    b.traegt = False
```

Gegenprobe über die ganze Datei:

```
$ grep -c "wortlaut\|textContent" management/maintenance/anker_diagnose.py
0
```

**Null Vorkommen.** `selection_json` wurde an zwei Stellen angefasst, beide
holten nur `xpathStart` heraus. Der markierte Wortlaut wurde nie gelesen.

## 3. Dieselbe Lücke an fünf Stellen — eine prüfte, und warf das Ergebnis weg

| Stelle | prüft den Inhalt? |
|---|---|
| `anker_diagnose._anker_pruefen()` | **nein** — nur Positionen |
| `postid_nachtrag`, Zweig `Weg=anker` | **nein** — Nummer ungeprüft übernommen |
| `postid_nachtrag`, Zweig Teilanker | ja — Kreuzprobe seit Build 751 |
| `toolbar.js` `rangeFromSelection()` | ja — `stale = (actual !== stored)` |
| `toolbar.js` `renderHighlight()` | zeichnet trotzdem, setzt nur `ann.stale` |

Die Kreuzprobe aus Build 751 lief **ausgerechnet nur dort, wo der Ausdruck
schon gestolpert war**. Wo er glatt durchlief, wurde er geglaubt.

## 4. Was das gekostet hat

Auf einer Seite mit 500 Beiträgen existiert fast jeder Index — er ist dann
nur der falsche. Die Zahlen aus der Browsermessung M1b (Chrome 151,
31.08.2026):

| Seite | Annotationen | Bereich mit passendem Text | alte Prüfung hätte gemeldet |
|---|---|---|---|
| `pmsnew.php?…tid=64200` | 46 | **7** | ~31 „trägt" |
| `pmsnew.php?…tid=57358` | 43 | **5** | ~27 „trägt" |
| `pmsnew.php?…tid=19368` | 10 | **9** | 10 „trägt" |

Im Trockenlauf 5 über alle Bestände entstanden **408 von 445** vorgesehenen
Eintragungen auf dem ungeprüften Weg `Weg=anker`.

## 5. Was Build 754 daran ändert

1. **Die Prüfung gibt es jetzt genau einmal** —
   `management/maintenance/annotation_pruefung.py`. `anker_diagnose` und das
   neue `tools/annotationen_verifizieren.py` benutzen dieselbe. Zwei
   Prüfungen derselben Frage wären binnen zweier Builds auseinandergelaufen.
2. **`Ankerbefund.traegt` heißt jetzt `position_vorhanden`**, und die Ausgabe
   schreibt `POSITION` statt `traegt`. Ein Feld, das „trägt" heißt, wird als
   „stimmt" gelesen — das hat diese Woche gekostet.
3. **Die Diagnose gibt zu jedem Beleg eine Zeile `INHALT`** mit Urteil,
   benanntem Beitrag, Wortlautträgern und Ergebnis der Textprobe.
4. **Sechs benannte Lagen statt einer Note:** `BESTAETIGT`,
   `BEITRAG_BELEGT`, `NUR_WORTLAUT`, `UNKLAR`, `WIDERLEGT`, `UNPRUEFBAR`.
   Sie werden nicht verrechnet — eine Gesamtnote nähme dem Leser die
   Unterscheidung ab, auf die es vor Gericht ankommt.

## 6. Grenzen

* Das lxml-Baummodell kennt **keine benachbarten Textknoten**. Wo der Browser
  welche hat, zählt `text()[n]` dort anders. **Ein Fehlschlag der Textprobe
  führt deshalb nicht auf `WIDERLEGT`, sondern auf die Wortlautprobe.**
* Die Textprobe ist nur anwendbar, wenn Start- und Endausdruck derselbe sind
  und auf einen Textknoten zeigen. Sonst steht `nicht_anwendbar` — eine
  Auskunft, kein Mangel.
* `WIDERLEGT` heißt **nicht**, dass der Ermittler sich geirrt hat, sondern
  dass die Angabe des Ausdrucks vom Inhalt nicht getragen wird.
* Neu benannt: `versatz_ende_vor_anfang`. Eine gültige Browser-Auswahl kann
  kein `offsetEnd < offsetStart` erzeugt haben. Im Bestand kommt es vor
  (Belege 14 und 50 in `evidence_1488`) — ein Befund über die **Speicherung**.
