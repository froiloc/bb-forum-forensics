# Regelkatalog `selection_json` 2.0 und Migration

**Version 1.0 — freigegeben durch Alex am 08.09.2026.**
Aenderungen gegenueber v0.4 in Abschnitt 9.

Dieses Dokument haelt fest, **was** entschieden ist und **warum**. Es ist die
Grundlage fuer den Bauplan; es ist selbst kein Bauplan. Gebaut ist davon noch
nichts — die Freigabe betrifft die Festlegungen, nicht deren Umsetzung.

---

## 0. Zweck

**Homogenisierung der Annotationen unter besonderer Beruecksichtigung des
Einsatzzwecks** — als Vorbedingung fuer aussagekraeftige und praezise Vermerke
fuer die Staatsanwaltschaft.

Anlass ist die Messung zu Build 764: von 455 Annotationen mit Anker sind 31
ihrer Lage nach `whole_post`, wurden aber als `text_range` abgelegt; 44 Anker
loesen im gespeicherten page BLOB nicht mehr auf. Beides verhindert, dass ein
Vermerk verlaesslich auf den Inhalt verweist.

---

## 1. Grundsatzentscheidungen

| Nr. | Entscheidung |
|---|---|
| G1 | Die neue Fassung entsteht als **neuer Datensatz** in `annotations`, nicht durch Aenderung eines bestehenden. |
| G2 | Der Vorgaenger bleibt unveraendert und wird ueber `deleted_at` als ersetzt markiert. Die Kette laeuft ueber `prev_id` und `version_nr`. |
| G3 | Das alte `selection_json` wird **nicht** eingebettet. Es steht als Vorgaengerdatensatz in der Datenbank; eine Kopie waere eine zweite Wahrheit. |
| G4 | Ein Datensatz umfasst **niemals** mehr als einen Beitrag. |
| G5 | Migration und Auswertung werden **atomar** ausgeliefert. |
| G6 | Der page BLOB bleibt die Quelle der Wahrheit. |
| G7 | Schema-Version **2.0**. |
| G8 | Alle keys sind **englisch**. |
| G9 | **Anker werden ausschliesslich mit html5lib erzeugt und ausgewertet.** libxml2 dient nur noch dem Vergleich in der Diagnose. |
| G10 | **Keine Sonderregeln je Beitragsart.** Alle Beitraege werden gleich behandelt: Inhaltsbereich gegen Rahmen entscheidet den Typ. |

### 1.1 Zu G9

Im Lauf zu Build 764 loesten 412 von 455 expressions unter libxml2 anders auf
als unter html5lib. Zwei Trees fuer denselben Abzug bedeuten zwei Wahrheiten
fuer denselben Anker. html5lib bildet die Rekonstruktion des Browsers nach —
gemessen am 31.08.2026 gegen Chromium: 17 von 17 Konstrukten gegen 7 von 17 bei
libxml2 roh.

### 1.2 Zu G10

In v0.3 war fuer den Systembeitrag (`posts.type = 4`) eine Ausnahme vorgesehen:
kein Inhaltsbereich, Typ fest auf `whole_post`. Diese Ausnahme ist
**fallengelassen** (Alex, 08.09.2026). Sie eroeffnete Komplexitaet ohne Gewinn:
der Systembeitrag hat sehr wohl einen Inhaltsbereich, er ist nur anders
benannt.

Damit gilt fuer jede Beitragsart dieselbe Regel, und `text_range` ist auch im
Systembeitrag zulaessig.

### 1.3 Die drei zulaessigen Formen

1. ein **ganzer Beitrag** — `whole_post`
2. ein **Teil des Inhaltsbereichs** eines Beitrags — `text_range` mit `post_id`
3. ein Bereich **ausserhalb jedes Beitrags** — `text_range` ohne `post_id`

### 1.4 Aufspaltung bei mehreren Beitraegen

Beruehrt eine Markierung mehrere Beitraege, entsteht **je betroffenem Beitrag
ein eigener Datensatz** vom Typ `whole_post`.

Gemessen: 28 der 31 `whole_post` betreffen einen Beitrag, zwei betreffen zwei,
einer betrifft acht. Keine der 418 `text_range` liegt ueber mehr als einem
Beitrag.

**Auch bei beidseitig `outside` ist auf umschlossene Beitraege zu pruefen.**
Eine Markierung, die vor dem ersten und hinter dem letzten Beitrag ansetzt,
umschliesst diese — sie ist kein `outside`-Fall, sondern spaltet sich auf. Nur
wenn zwischen den Endpunkten **kein** Beitrag liegt, greift Form 3.

**Was zwischen den Beitraegen markiert war, entfaellt bei der Aufspaltung
ersatzlos.** Ausdruecklich mitgetragen von Alex, 08.09.2026. Die Alternative —
je Fragment ein eigener `outside`-Datensatz — ist geprueft und verworfen.

---

## 2. Die Typen

### 2.1 `whole_post`

> Beruehrt mindestens ein Endpunkt der Markierung den **Rahmen** des Beitrags —
> Beitragskopf, Metadatenspalte, Betreff, Signatur, Funktionsleiste —, ist es
> ein `whole_post`. Liegt die Markierung vollstaendig im **Inhaltsbereich**, ist
> es eine `text_range`.

Bereichsdefinition je Seitenart: `documents/Post_Bereiche_Katalog.md`.

**Nicht Bestandteil der Regel:** ob die Markierung den Inhaltsbereich
vollstaendig ausschoepft. Eine Markierung vom ersten bis zum letzten Zeichen
bleibt `text_range`, solange sie den Rahmen nicht beruehrt.

**Unbestimmte Faelle werden `text_range`.**

### 2.2 `text_range`

Alles Uebrige. Traegt zusaetzlich Anker nach Abschnitt 3.

### 2.3 Was welcher Typ traegt

| Feld | `whole_post` | `text_range` |
|---|---|---|
| `element_id`, `post_id` | ja | ja bei Form 2; leer bei Form 3 |
| `xpathStart`, `xpathEnd` | der **Beitrag** (Abschnitt 4) | die markierte Stelle, smart (Abschnitt 3) |
| `offsetStart` | `0` | wie bisher |
| `offsetEnd` | `null` | wie bisher |
| `textContent` | der **zitierfaehige Inhalt**: Wortlaut des Inhaltsbereichs, reiner Text | der markierte Wortlaut |
| `metadata`, `extracted` | ja | ja |

### 2.4 Die Arbeitsteilung von Anker und Inhalt

**Die XPath expressions bestimmen den Bezugsrahmen der Annotation.
`textContent` beschreibt den Inhalt, der zitiert werden soll.** Zwei Felder,
zwei Zwecke.

Bei `whole_post` fallen sie auseinander, und das ist gewollt: der Ermittler hat
den **Beitrag als Ganzes** gegriffen, einschliesslich Verfasser, Rang und
Zeitstempel — die Metadaten gehoeren zum Bezugsrahmen. Zitierfaehig ist davon
aber nur der Inhalt.

> **Bei `whole_post` ist `textContent` massgeblich fuer das, was zitiert wird.
> Die XPath expressions bezeichnen den Bezugsrahmen und duerfen nicht
> verwendet werden, um den zu zitierenden Text abzuleiten.**

Dieser Satz steht hier, weil der naheliegende Fehler still waere: Ein
Berichtsgenerator, der aus `xpathStart`/`xpathEnd` und den Offsets den Text
bildet, gaebe den gesamten Rahmen mit aus — Verfassername, Rang,
Funktionsleiste.

---

## 3. Der Anker-Generator

Kern der Umstellung. Erzeugt die expressions fuer `text_range` und wird
spaeter auch von `toolbar.js` gebraucht — er gehoert deshalb in ein Modul, das
beide Seiten speist.

### 3.1 Rangfolge

| Rang | Verfahren | Bedingung |
|---|---|---|
| 1 | `by_id` | `id` vorhanden **und** dokumentweit eindeutig |
| 2 | `by_class` | eine Klasse vorhanden, die nicht in der Ausschlussliste steht |
| 3 | `by_position` | sonst |

### 3.2 Der Algorithmus

```
0. Zielknoten bestimmen. Ist es ein Textknoten, merken und ab hier mit
   seinem Elternelement arbeiten.
1. Kette vom Zielelement zur Wurzel aufsammeln.
2. Von der Wurzel abwaerts je Element einen Schritt bilden:

   a) by_id:  id vorhanden UND count(//*[@id='<ID>']) = 1
              -> den GESAMTEN bisherigen Praefix ersetzen durch
                 //*[@id='<ID>']

   b) by_class: eine Klasse vorhanden, die nicht ausgeschlossen ist
              -> tag[contains(concat(' ',normalize-space(@class),' '),
                              ' KLASSE ')][i]
                 mit i NEU GEZAEHLT ueber die gefilterte Menge

   c) by_position: tag[i] ueber die gleichnamigen siblings

3. Rueckpruefung JE SCHRITT: den bis hierhin gebauten Ausdruck auswerten.
   Genau ein Treffer, und identisch mit dem erwarteten Element?
   Sonst diesen Schritt auf den naechstschwaecheren Rang zuruecksetzen
   und 3. wiederholen.

4. War das Ziel ein Textknoten: /text()[n] anhaengen (Abschnitt 3.6).
```

### 3.3 Zu `by_id` — die Eindeutigkeitsprüfung ist zwingend

Das Forum ist an dieser Stelle **nicht normkonform**. `viewtopic0.php` Z. 989
schreibt `<div id="progressbar">` innerhalb der `postleft` und damit **je
Beitrag einmal**; auf einer Seite mit 500 Beitraegen existiert die id
500-mal. `include/type4.php` schreibt `<div id="contentType4">` ohne
Beitragsnummer und wiederholt sie bei jedem Systembeitrag.

Ohne Pruefung entstuende `//*[@id='progressbar']/...` — ein Ausdruck, der
**aufloest** und den ersten von 500 Kandidaten liefert. Das ist schlimmer als
ein Bruch, weil es unbemerkt bleibt.

**Die Aenderung am Forum-Quelltext (Umstellung von `id` auf `name`,
08.09.2026) wirkt nicht ruekwirkend auf vorhandene Abzuege.** Die 144 page
BLOBs wurden vorher gesichert. Ein neuer Abzug ist vorgesehen; die Struktur
bleibt dabei unveraendert, geaendert wurde nur ein Attributname (Alex,
08.09.2026). Der Katalog fuehrt deshalb beide Formen (Abschnitt 4.2).

Ungeprueft: `include/poll.php` und `include/header0.php` enthalten
moeglicherweise weitere mehrfach vergebene ids. Der erste Lauf des Generators
weist alle aus.

### 3.4 Zu `by_class` — keine Pruefung auf Verkleinerung

Rang 2 wird verwendet, **sobald** eine brauchbare Klasse vorhanden ist. Eine
Pruefung, ob die Klasse die Kandidatenmenge verkleinert, entfaellt.

Begruendung: Verkleinert sie nicht, ist der Gewinn null — wir bauen einen
deterministischen Pfad, jeder Schritt engt auf genau einen Knoten ein, und ein
nicht verkleinerndes Praedikat waehlt denselben Knoten. Die Kosten sind dann
aber ebenfalls fast null. Einen Zweig in den Generator zu bauen, der je Schritt
Kandidatenmengen vergleicht, erhoeht die Komplexitaet ohne Nutzen.

**Der index ist in jedem Fall neu zu zaehlen.** `div[20]` bedeutet *das
zwanzigste div-Kind*; `div[contains(…)][20]` bedeutet *unter den div-Kindern
mit dieser Klasse das zwanzigste*. Das ist nicht dasselbe Element. Die
Klammerreihenfolge ist wesentlich: `div[contains(…)][3]` filtert erst und
zaehlt dann, `div[3][contains(…)]` wuerde umgekehrt pruefen.

### 3.5 Ausschlussliste fuer Zustandsklassen

Klassen, die einen Zustand statt einer Struktur ausdruecken, sind fuer Rang 2
nicht zu verwenden:

```
hidden, censored, uncensored, shadow
```

Die Liste gehoert in `documents/Post_Bereiche_Katalog.md`, nicht in den Code.

Das Forum verwendet kein JavaScript, ein Wechsel von Klassennamen findet also
nicht statt. Der Ausschluss erfolgt trotzdem — eine Zustandsklasse sagt nichts
darueber aus, **wo** ein Element steht.

### 3.6 Der letzte Schritt bleibt eine Zaehlung

Ein Textknoten traegt weder `id` noch `class`. Der letzte Schritt ist
zwangslaeufig `text()[n]`, also `by_position`.

**Der Generator macht das Element robust, nicht die Position im Text.**

Gemessen: 38 der 44 Brueche entstanden genau an diesem Schritt. Die Ursache ist
nicht das Forum, sondern der parser — wie ein Tree die Zeichendaten in
Textknoten aufteilt, haengt von ihm ab. G9 verkleinert das Problem, indem nur
noch ein parser verwendet wird; es verschwindet nicht.

**Arbeitsteilung:** Der Ausdruck findet das Element, `textContent` findet die
Stelle darin. Beim Lesen wird der Zeichen-Offset ueber `textContent` bestimmt,
nicht ueber `n`.

**Bei der Migration** wird der bestehende `text()`-Teilausdruck uebernommen. Bei
geheilten Ankern (6.2) wird er aus der Fundstelle des Wortlauts neu gebildet.

### 3.7 Keine Verkuerzung ueber `//`

`//` ist die `descendant-or-self`-Achse und kann in mehreren Tiefen zutreffen.
Ein kuerzerer Ausdruck, der zwei Kandidaten trifft, ist schlechter als ein
laengerer, der einen trifft. Zudem laesst sich der Tree dann nicht mehr linear
durchlaufen. Einvernehmlich verworfen.

---

## 4. Anker bei `whole_post` und Inhaltsbereiche

### 4.1 Anker bei `whole_post`

```
xpathStart:  (//*[@id='p<post_id>']//text())[1]
xpathEnd:    (//*[@id='p<post_id>']//text())[last()]
offsetStart: 0
offsetEnd:   null
```

Die Anker liegen auf dem **Beitrag**, nicht auf dem Inhaltsbereich — sie
bezeichnen den Bezugsrahmen (2.4). Die Achse `//text()` laeuft ueber den
gesamten Teilbaum **einschliesslich Rahmen**: Beitragskopf, Metadatenspalte und
Funktionsleiste. `[last()]` ist damit der letzte Textknoten, der zum Beitrag
gehoert.

**Warum Textknoten und nicht das container-Element:** Zeichen-Offsets sind nur
in Textknoten definiert. Zeigte `xpathEnd` auf ein Element, waere `offsetEnd:
null` — *bis zum Ende des Nodes* (4.3) — bedeutungslos, und `offsetStart: 0`
ebenso. In v0.4 stand hier die Elementform; sie widersprach 4.3. Korrigiert auf
Nachfrage von Alex, 08.09.2026.

**Einschraenkung:** Der letzte Textknoten kann reiner Leerraum zwischen zwei
schliessenden Tags sein. Fuer einen Bezugsrahmen ist das unerheblich — er
markiert weiterhin das Ende des Beitrags. Fuer die Textgewinnung waere es
relevant, aber die ist nach 2.4 ausdruecklich untersagt.

**`//*` und nicht `//div`:** Das container-Element unterscheidet sich je
Seitenart — `viewtopic0.php` Z. 886 `<article>`, `viewtopic1.php` Z. 576 und
`pms_new/mdl/topic.php` Z. 462 `<div>`. Unterscheidend ist die id, nicht der
Tag-Name.

### 4.2 Inhaltsbereich je Seitenart

Der Inhaltsbereich entscheidet den Typ (2.1) und liefert `textContent` (2.3).

| Seitenart | Inhaltsbereich |
|---|---|
| `viewtopic`, `pmsnew` | `div.postmsg` unterhalb `div.postright`, ohne `postsignature` |
| `beginner_viewtopic` | `div.regular.contents` unterhalb `div.topic-body` |
| Systembeitrag (`posts.type = 4`) | `//*[@id='p<post_id>']//div[@id='contentType4' or @name='contentType4']` |

**Zum Systembeitrag:** Der Ausdruck wird ueber die Beitragsnummer verankert,
weil `contentType4` selbst **nicht eindeutig** ist — sie wiederholt sich bei
jedem Systembeitrag der Seite. Beide Attributformen sind aufgenommen: die
vorhandenen 144 BLOBs tragen `@id`, kuenftige Abzuege `@name`. Damit ist keine
Nachbesserung noetig, wenn der neue Abzug vorliegt.

### 4.3 Zeichen-Offsets

`offsetEnd` bleibt **exklusiv** und **nicht-negativ**.

> **`offsetEnd: null` bedeutet: bis zum Ende des Nodes, auf den `xpathEnd`
> zeigt.**

Begruendung gegen `-1`:

- Der W3C Web Annotation Data Model beschreibt mit dem `TextPositionSelector`
  genau diesen Sachverhalt: Position 0 liegt unmittelbar vor dem ersten
  Zeichen, das Anfangszeichen ist eingeschlossen, das Endzeichen nicht. Die
  Konformitaetspruefung fordert fuer `start` und `end` je einen einzelnen
  **nicht-negativen** ganzzahligen Wert.
- `toolbar.js` Z. 1133 uebernimmt `range.endOffset` unveraendert aus dem DOM
  Range; dort ist der Offset ebenfalls exklusiv.
- In Python und JavaScript schliesst ein Index `-1` beim Slicing das letzte
  Zeichen gerade **aus**.
- `null` ist in JSON eindeutig und nicht mit `0` zu verwechseln.

---

## 5. Aufbau von `selection_json` 2.0

```
{
  "schema_version": "2.0",
  "annotation_kind": "whole_post" | "text_range",

  "xpathStart":  "...",
  "xpathEnd":    "...",
  "offsetStart": 0,
  "offsetEnd":   null,
  "textContent": "...",

  "metadata":  { ... },
  "extracted": { ... },
  "migrated":  { ... }        // nur bei migrierten Datensaetzen
}
```

Drei Zweige. Die Trennung ist Absicht: `extracted` kann als Ganzes neu erzeugt
werden, wenn ein Extraktionsverfahren verbessert wird, ohne `metadata` oder die
Anker anzufassen.

### 5.1 `metadata`

**Zweck: direkter Zugriff durch einmalige Extraktion.** Die Daten werden einmal
aus dem page BLOB geholt und stehen danach unmittelbar zur Verfuegung — ohne
Zugriff auf weitere Datenbanken und ohne Abhaengigkeit von
Extraktionsalgorithmen.

| key | Anmerkung |
|---|---|
| `ts_post` | Zeitstempel des Beitrags |
| `ts_last_edited`, `edited_by` | sofern vorhanden |
| `author`, `rank` | |
| `likes` | |
| `subject` | Betreff |
| `signature` | gehoert zum Rahmen, nicht zum Inhalt — als Metadatum gefuehrt |
| `topic_id` | |
| `forum_id` | **entfaellt bei `/forum/pmsnew.php`** — ein Befund, kein fehlender Wert |
| `fetched_at` | wann der Seitenabzug entstand |
| `parser` | `{ "name": ..., "version": ..., "build": ... }` |

`page_url` wird nicht aufgenommen — eigene Spalte in `annotations`. `method`
wird nicht aufgenommen — der page BLOB wird immer ueber denselben Weg
abgerufen.

### 5.2 `extracted`

Was aus dem Beitrag isoliert wurde und zur Zuordnung eines Benutzerkontos zu
einer natuerlichen Person beitragen kann.

Aufzunehmen: zitierte Beitraege mit `post_id` und Verfasser, URLs mit Typ,
Zugangsdaten, erwaehnte Benutzernamen und Aliase, Dateireferenzen und
`share_id`.

**Jeder Zweig traegt Name und Version des Verfahrens, das ihn erzeugt hat.**
Nicht weil sich die Daten aendern — das Forum ist abgeschaltet und statisch —,
sondern weil sich die **Verfahren** aendern. Mit der Kennung ist die Frage
*welche Datensaetze tragen noch das Ergebnis der aelteren Zitaterkennung* eine
Abfrage; ohne sie eine Vermutung.

### 5.3 `migrated`

| key | Wert |
|---|---|
| `version_prior` | `"1.0"` |
| `ts` | Zeitpunkt der Migration |
| `build` | Buildnummer des Migrationslaufs |
| `rule` | Bezeichnung und Version der angewandten Regel |

`schema_version` steht auf **jedem** Datensatz.

---

## 6. Die Migration

### 6.1 Ablauf je Datensatz

1. Anker neu erzeugen (3), heilen wo noetig (6.2)
2. Typ bestimmen (2.1)
3. Bei mehreren betroffenen Beitraegen aufspalten (1.4)
4. `metadata` und `extracted` aus dem page BLOB erheben
5. Je Ergebnis einen neuen Datensatz ueber den vorhandenen Versionierungsweg
   schreiben (`EvidenceDb` Z. 885 ff.): Vorgaenger erhaelt `deleted_at`, neuer
   Datensatz `version_nr + 1` und `prev_id`

Bei einer Aufspaltung tragen alle entstehenden Datensaetze dasselbe `prev_id`.

### 6.2 Ankerheilung — Teil dieser Migration, kein eigener Schritt

Weil ohnehin jeder Anker neu erzeugt wird, heilt die Migration die gebrochenen
als Nebenwirkung. Gemessen: 38 Datensaetze brechen ausschliesslich am
abschliessenden `text()`-Schritt, 6 strukturell.

1. Bestehende expression im page BLOB aufloesen
2. Bruch am `text()`-Schritt: das tragende Element ist aufgeloest; neuer Anker
   darauf, Offset ueber den gespeicherten Wortlaut
3. Struktureller Bruch: Suche ueber den gespeicherten Wortlaut, zuerst im
   benannten post container, dann in wachsender Nachbarschaft
   (`fundstellen_nach_naehe()`, Build 762)

**Gelingt die Verortung nicht oder ist der Wortlaut mehrdeutig, wird der
Datensatz benannt und zur Sichtung vorgelegt.** Es wird nicht geraten und
nichts stillschweigend uebersprungen (Grundregel 1). Solche Datensaetze
behalten Typ und Anker der Version 1.0 und tragen den Befund in `migrated`.

### 6.3 `local_id`

**Jeder neue Datensatz erhaelt eine neue UUID.**

`local_id` ist eine client-seitig erzeugte UUID (`toolbar.js` Z. 1214,
`crypto.randomUUID`), die im Browser als key der Map `_state.annotations` dient
und ueber die der Server den aktiven Vorgaenger sucht. Ihr Zweck liegt in der
laufenden Sitzung; die Migration laeuft ohne eine solche.

Die in v0.1 erwogene Ableitung `<local_id>#<post_id>` ist verworfen. Die
Zusammengehoerigkeit aufgespaltener Datensaetze ist ueber `prev_id` gegeben.

### 6.4 `created_by`

**Vom Vorgaenger uebernommen, normalisiert.**

> Normalisiert heisst: Buchstaben werden als Grossbuchstaben geschrieben,
> **wenn und nur wenn** der Eintrag mit `h0` beginnt.

Die Migration erfindet keine System-Kennung. Der Datensatz bleibt dem
Ermittler zugeordnet, der die Annotation angelegt hat; die Migration ist eine
Formatumstellung, keine neue Ermittlerhandlung.

`investigator_id` ist **deprecated**, wird global nicht mehr verwendet und von
der Migration nicht geschrieben.

### 6.5 Rahmen

Schreibend auf `evidence_<uid>.db`, also **Migrationsvorbehalt**.
Vier-Phasen-Workflow nach `Datenmigrationsleitfaden_AIW.md`:

| Phase | Inhalt |
|---|---|
| 0 | Referenzbestand und Trockenlauf, getesteter Rueckweg |
| 1 | Sicherung mit `VACUUM INTO`, Versionierung, Siegel |
| 2 | Migration auf einer **Kopie** mit Pruefprotokoll |
| 3 | Verifikation im Vieraugenprinzip — durch die **Chef-Ermittlerin**, die die Migration weder geschrieben noch ausgefuehrt hat |
| 4 | Produktivuebernahme und Archivierung |

Kein manuelles SQL. Alles ueber ein versioniertes Migrationsmodul.

### 6.6 Erwartungswerte fuer den Trockenlauf

| Groesse | Erwartung |
|---|---|
| aktive Datensaetze vor der Migration | 470 |
| davon mit XPath expression | 455 |
| davon Beitragsmarkierungen ohne expression | 15 |
| neu als `whole_post` | 31 Markierungen |
| davon mit Aufspaltung | 3 (2 + 2 + 8 Beitraege) |
| Zeilenzuwachs durch Aufspaltung | +9 |
| als `text_range` | 418 |
| Anker mit Bruch am `text()`-Schritt, zu heilen | 38 |
| Anker mit strukturellem Bruch, zu heilen | 6 |

Weicht der Trockenlauf ab, ist die **Regel** zu pruefen, nicht die Messung.

---

## 7. Seitenarten ohne Beitraege

`/forum/search.php`, `/forum/viewforum.php`, `/forum/profile.php` und
`/forum/notifications.php` tragen keine Beitraege. Fuer `search` und
`viewforum` im Lauf zu Build 764 bestaetigt; fuer `profile` und
`notifications` festgestellt durch Alex, 08.09.2026.

Markierungen auf diesen Seiten sind `text_range` nach Form 3.

---

## 8. Offene Punkte

| Punkt | Stand |
|---|---|
| **Waechter AD41 kehrt sich um** | Er haelt die in v0.3 verworfene Ausnahme fest: Knoten im Systembeitrag ist `frame`, Ergebnis `whole post`. Sein Testabzug legt den Text in `contentType4` — also kuenftig in den Inhaltsbereich. Mit G10 wird daraus `content` und je nach zweitem Endpunkt `text_range`. **Das ist der beabsichtigte Verhaltenswechsel, keine Regression.** AD41 ist neu zu fassen. Da im Bestand kein Systembeitrag annotiert ist, aendert sich dabei **kein Messwert** — die Wachposten sind anzupassen, der Lauf nicht zu wiederholen. |
| mehrfach vergebene ids | `progressbar` und `contentType4` sind belegt. `include/poll.php` und `include/header0.php` **ungeprueft**. |
| neuer Seitenabzug | vorgesehen; Struktur unveraendert, nur `id` → `name` beim Systembeitrag. Beide Formen sind in 4.2 aufgenommen, Nachbesserung entfaellt. |
| Erkennung beim Anlegen in `toolbar.js` | eigener Bauplan; der Anker-Generator muss beide Seiten speisen |
| `_GETRAGEN_VON` in `tools/anker_diagnose.py` | `post_bereiche.py` fehlt in der Liste, deren MD5 im Kopf des Laufprotokolls ausgegeben wird — eine Aenderung der Bereichsdefinition waere dort nicht erkennbar. Eine Zeile. Umbenennung nach `_SOURCE_FILES` als eigener Auftrag. |
| `investigator_id` | deprecated, Entfernung als eigener Vorgang |
| Umstellung auf die W3C-keys `start`/`end` | moeglich, da 2.0 ohnehin bricht — eigene Entscheidung |
| Schulung der Ermittler | organisatorisch; 31 von 455 (rund 7 %) sind durch eine Bedienung entstanden, die das Werkzeug nicht vorgesehen hat |

---

## 9. Aenderungen gegenueber v0.4

| Abschnitt | Aenderung |
|---|---|
| Kopf | Entwurfsvermerk entfernt; freigegeben durch Alex am 08.09.2026 |
| 4.1 | **Korrektur** — die Anker bei `whole_post` zeigen wieder auf **Textknoten**, nicht auf das container-Element. Die Elementform aus v0.4 widersprach 4.3: Zeichen-Offsets sind nur in Textknoten definiert. Aufgefallen durch Nachfrage von Alex. |
| 6.6, 8 | Vorbehalt zum Erwartungswert 31 aufgeloest — im Bestand sind keine Systembeitraege annotiert (Alex, 08.09.2026). 31 steht. |
| 8 | AD41: ergaenzt, dass die Neufassung keinen Messwert aendert |

## 10. Aenderungshistorie

| Version | Datum | Wesentliche Aenderung |
|---|---|---|
| v0.1 | 08.09. | Erstfassung nach der Diskussion zu Schema und Migration |
| v0.2 | 08.09. | Smarte expressions, `offsetEnd: null`, Ankerheilung Teil der Migration, `created_by` normalisiert, neue UUID |
| v0.3 | 08.09. | Anker-Generator ausgearbeitet, Eindeutigkeitsprüfung fuer `by_id`, Ausschlussliste, html5lib als Grundsatz |
| v0.4 | 08.09. | Sonderregel fuer den Systembeitrag fallengelassen, Arbeitsteilung Anker/Inhalt, Inhaltsbereich je Seitenart |
| **v1.0** | 08.09. | Korrektur der `whole_post`-Anker auf Textknoten; freigegeben |
