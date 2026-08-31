# Befund: Der Beitragsindex der gespeicherten XPath-Ausdrücke

**Fassung 1.0 · 31.08.2026 · Build 753 · Basis `origin/master 090154e`**

---

## 0. Herkunft der Messwerte

| | |
|---|---|
| Werkzeug | `debug/messung_xpath_blink_M1.js`, MD5 `7ce6e991d39184a4aa94dad868ea04cc` |
| Umgebung | Ermittlungsfenster, Chrome 151.0.0.0, X11/Linux x86_64 |
| Gefahren von | Alex, 31.08.2026, 17:05–17:09 UTC |
| Messstellen | drei Seiten aus zwei Beweismittelbeständen und einem Kontrollbestand |
| Vergleichswerte | Trockenlauf `tools/postid_nachtragen.py` Build 752 über 462 Annotationen |

Das Skript ist rein lesend (`document.evaluate`, `textContent`). Es hat den
DOM nicht verändert.

---

## 1. Zwei Hypothesen sind widerlegt

### 1.1 Die `<mark>`-Injektion ist es nicht

```
CSS.highlights     : object
Highlight-Konstr.  : function
<mark> im Viewport : 0
```

Die CSS Custom Highlights API ist verfügbar und wird benutzt. Der
`<mark>`-Rückfallpfad (`toolbar.js` Z. 1453 ff.) läuft nicht. **Der DOM wird
beim Markieren nicht verändert.**

Die in der Übergabe nach Build 752 als „drängend" bezeichnete Erklärung zu
Vorgang `8d3b62f5` ist damit **falsch**. Sie stammte von Claude und war nicht
gemessen; Alex hat sie vor der Messung bestritten und behält recht.

### 1.2 Der Zerleger ist es auch nicht

Blink und der gesicherte Seitenabzug sehen **denselben Baum**:

| gemessen an `/forum/pmsnew.php?mdl=topic&tid=64200` | Blink (M1) | Abzug (Build 752) |
|---|---|---|
| Textknoten im Trägerabsatz `div[52]/…/p[1]` | 23 | 23 |
| `div[52]` führt auf | #291411 | #291411 |
| Elementkinder am Beitragsbehälter | 53 | 53 |
| `div[54]` | bricht | bricht |

Der Umbau auf `html5lib` (Build 747) bildet Blink ab. Beide scheiden als
Ursache aus. **Sechs Builds Ankersuche haben damit ein Ergebnis: diese
Fehlerquelle ist geschlossen.**

---

## 2. Der Befund

> **Die gespeicherten XPath-Ausdrücke lösen auch in Blink nicht auf — auf
> derselben Seite, auf der sie erzeugt worden sind.**

`text()[24]` gegen 23 Textknoten. `div[54]` gegen 53 Kinder. `div[1010]` gegen
1005. Das ist kein Auswertungs- und kein Engine-Problem.

### 2.1 Der Fehler sitzt in genau einem Schritt

Auf `tid=64200` gilt über die ganze Seite ausnahmslos
**Elementindex = 2 · Platz + 3**:

| Beitrag | Platz | Elementindex | 2·P+3 |
|---|---|---|---|
| #273069 | 2 | 7 | 7 ✓ |
| #275600 | 4 | 11 | 11 ✓ |
| #275610 | 7 | 17 | 17 ✓ |
| #276369 | 9 | 21 | 21 ✓ |
| #276428 | 10 | 23 | 23 ✓ |
| #277474 | 11 | 25 | 25 ✓ |
| #284996 | 16 | 35 | 35 ✓ |
| #285261 | 17 | 37 | 37 ✓ |
| #285268 | 18 | 39 | 39 ✓ |
| #291411 | 25 | 53 | 53 ✓ |

**Kein Ausreißer.** Der Seitenbau ist vollkommen regelmäßig — nichts fehlt im
Baum, nichts ist eingeschoben.

Die Ausdrücke gegen den Beitrag, in dem der markierte Wortlaut **eindeutig**
steht:

| Belege | Ausdruck | landet auf Platz | Wortlaut auf Platz | Δ |
|---|---|---|---|---|
| 29, 31, 32, 33, 64 | `div[6]` | 2 | 2 | **0** |
| 81, 83 | `div[10]` | 4 | 4 | **0** |
| 34 | `div[16]` | 7 | 6 | **+1** |
| 35, 36 | `div[20]` | 9 | 8 | +1 |
| 37, 38, 39 | `div[22]` | 10 | 9 | +1 |
| 40, 41 | `div[24]` | 11 | 10 | +1 |
| 42 | `div[34]` | 16 | 15 | +1 |
| 43 | `div[36]` | 17 | 16 | +1 |
| 44 | `div[38]` | 18 | 17 | +1 |
| 45–73, 49 | `div[52]` | 25 | 24 | +1 |

**Δ = 0 bis Platz 4, danach Δ = +1 Beitrag, konstant.** Eine einzige Stufe.

Alles **unterhalb** dieses Schrittes ist heil: die 27 Ausdrücke auf `div[52]`
verlangen `text()[2]` bis `text()[38]`. Im richtigen Beitrag (#291084) gibt es
offenbar genug Textknoten, im falschen (#291411) nur 23 — deshalb brechen
genau die ab `[24]`, und die darunter lösen scheinbar sauber auf. **Der
Textknotenindex ist nicht kaputt; er wird im falschen Absatz nachgezählt.**

### 2.2 Auf einer langen Seite wächst der Fehler stufenweise

`tid=57358`, 500 Beiträge. `Elementindex = 2 · Platz + 3` hält auch hier exakt
(#252553 P31→65, #263323 P108→219, #315333 P472→947, #317186 P485→973).

| Position (div) | 218 | 526 | 548 | 588 | 598 | 636 | 728 | 790 | 888 | 906 | 918 | 946 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Δ (Beiträge) | +2 | +7 | +7 | +9 | +9 | +10 | +11 | +13 | +18 | +18 | +18 | +18 |

Monoton nicht fallend. Und: die Ausdrücke der Belege 45 und 46 verlangen
`div[1010]` bzw. `div[1016]` — **Platz 504 und 507 auf einer Seite mit 500
Beiträgen.**

### 2.3 Die Kontrollgruppe trägt

`tid=19368` (Bestand 155955), 6 Beiträge: **10 von 10 Ausdrücke richtig, kein
Bruch, alle eindeutig.** Dort gilt `Elementindex = Platz + 3` — ein Element je
Beitrag statt zwei. Das Verfahren ist also nicht grundsätzlich kaputt; es
versagt an bestimmten Seiten.

---

## 3. Was daraus folgt

Der Ausdruck zeigt **zu weit unten** ⇒ heute fehlen vor der Fundstelle
Elemente ⇒ **die damals ausgelieferte Seite trug an dieser Stelle mehr
Beiträge als der Abzug, der heute verglichen wird.** Die Fehlmenge wächst nach
unten; die fehlenden Beiträge liegen über die Seite verteilt, nicht am Rand.

Damit ist die Sache im Kern **keine Frage der XPath-Erzeugung, sondern der
Sicherung** — Vorgang `b41f7a08`. Unabhängig davon bleibt richtig, dass ein
rein positionaler Ausdruck aus einer solchen Differenz einen **lautlosen**
Fehler macht statt eines sichtbaren.

### 3.1 Beitrag aus dem Forenquelltext

`forum/html/include/pms_new/mdl/topic.php` (Prepper `97b072e`), Z. 122–166:

```php
$num_pages  = ceil(($cur_topic['replies'] + 1) / $self['disp_posts']);
$p          = (!isset($_GET['p']) || $_GET['p'] <= 1 || $_GET['p'] > $num_pages) ? 1 : intval($_GET['p']);
$start_from = $self['disp_posts'] * ($p - 1);
…
ORDER BY id LIMIT '.$start_from.','.$self['disp_posts'];
```

**Die PN-Themenseite ist paginiert, und wie viele Beiträge sie zeigt, hängt an
`$self['disp_posts']` — einer Einstellung des abrufenden Kontos.** Zwei Abzüge
derselben Adresse, mit verschiedenen Konten oder Einstellungen gezogen,
enthalten verschieden viele Beiträge. Das erklärt unmittelbar, warum ein
Ausdruck Platz 504 auf einer 500er-Seite verlangt.

**Was es nicht erklärt:** eine geänderte `disp_posts` schneidet am *Ende* ab;
sie erzeugt keine Lücken in der Mitte. Der stufenweise wachsende Versatz
braucht Beiträge, die *mitten aus der Reihe* fehlen. `ORDER BY id` heißt:
gelöschte Nachrichten schieben alles Nachfolgende nach oben — genau dieses
Muster. **Das ist Hypothese, nicht Messung.**

---

## 4. Die Folge für den scharfen Lauf

Der Nachtrag prüft die Kreuzprobe **nur beim teilweise aufgelösten Ausdruck**.
Löst der Ausdruck ganz auf, wird die Beitragsnummer ungeprüft übernommen
(`postid_nachtrag._nummer_bestimmen`, Zweig `fundstelle.weg == WEG_XPATH`).
Von den 410 vorgesehenen Eintragungen entstehen **373 auf diesem Weg**.

Gemessen:

| Seite | Ausdrücke lösen ganz auf | davon nachweislich falsch |
|---|---|---|
| `tid=64200` | 31 | **24** |
| `tid=57358` | 27 | ≥ 13 |
| `tid=19368` (Kontrolle) | 10 | 0 |

> **Der scharfe Lauf darf in dieser Form nicht gefahren werden.**

Zusätzlich prüft `AbsatzFinder._ueber_xpath()` an keiner Stelle, ob an der
gefundenen Stelle der markierte Wortlaut steht; reicht der Endausdruck nicht,
nimmt sie „ab hier so viele Zeichen, wie der Wortlaut lang ist". Das betrifft
damit auch den Textausschnitt, den das Vollzitat abdruckt.

---

## 5. Was offen ist

1. **Warum sieht im Ermittlungsfenster alles richtig aus?** Einwand Alex,
   31.08.2026. `renderHighlight()` bricht ab, wenn `rangeFromSelection()`
   `null` liefert (Z. 1487–1490) — und `null` entsteht unter anderem, wenn
   `range.setStart()` mit einem Versatz jenseits der Knotenlänge wirft. Dann
   würde die falsche Markierung **gar nicht gezeichnet**, und der Eindruck der
   Richtigkeit entstünde dadurch, dass die falschen fehlen. **Nicht gemessen.**
   Messvorrichtung: `debug/messung_wiederherstellung_M1b.js`, Gegenprobe
   `window.forensicTestHighlight()`.
2. **Hängt der Versatz an der Zeit oder an der Position?** Messvorrichtung:
   `tools/xpath_versatz_messen.py` (`pages.fetched_at` gegen
   `annotations.ts`).
3. **Wie lang war die Seite wirklich?** Messvorrichtung:
   `debug/messung_seitenumfang_M1c.js` (laufende Nummern aus
   `<span class="conr">`, Blätterleiste).
4. **HTML5-Konformität der Abzüge** ist nie geprüft worden. `M4` der
   Ankerdiagnose gibt das Fehlerprotokoll von **libxml2** aus — das ist keine
   HTML5-Prüfung: libxml2 beanstandet Zulässiges und schweigt zu Unzulässigem.
   Die Prüfung gehört in den Prepper.

## 6. Grenzen dieser Messung

* Die Wortlautprobe in `messung_xpath_blink_M1.js` normalisiert **schwächer**
  als `_klartext()` serverseitig. Auf `tid=57358` meldet sie bei neun Belegen
  „nein", wo der Trockenlauf genau einen Beitrag fand. **„nein" ist kein
  Beleg — „NEIN! steht in #…" ist einer.**
* Gemessen wurde an drei Seiten aus zwei Beständen plus einer Kontrollseite.
  Die übrigen zwölf Bestände sind **nicht** gemessen.
* Der Δ-Wert entsteht nur dort, wo der Wortlaut in **genau einem** Beitrag der
  Seite steht. Wo er in mehreren steht, gibt es keinen Messwert — und keinen
  Messwert zu haben ist etwas anderes, als einen von null zu haben.
