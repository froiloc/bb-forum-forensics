# Katalog der Post-Bereiche

Stand: Build 765, 08.09.2026. Verfahren: AIW, Forum auf FluxBB/PunBB-Basis.

Dieses Dokument beschreibt, wie ein Beitrag im Seitenabzug aufgebaut ist und
wo die Grenze zwischen **Inhalt** und **Rahmen** verlaeuft. Es ist als
**Vorlage fuer andere Foren** gedacht: die Struktur der Beschreibung bleibt,
die Klassennamen und Elemente sind je Forum zu ersetzen.

> **Diese Liste ist nicht abschliessend.** Sie nennt die Seitenarten, die im
> Bestand dieses Verfahrens vorkommen und am Forenquelltext geprueft sind. Ein
> anderes Forum bringt andere Seitenarten mit. Eine Seitenart, die hier fehlt,
> wird vom Werkzeug als `sonstige` gefuehrt und **nicht** stillschweigend wie
> eine bekannte behandelt.

Die Tabelle steht zusaetzlich im Code, in
`management/maintenance/post_bereiche.py`. Beide werden vom Waechter **AD45**
gegeneinander gehalten. Wird hier etwas geaendert, muss es dort ebenfalls
geaendert werden - sonst faellt der Waechter, und das ist so gewollt.

---

## 1. Warum die Unterscheidung gebraucht wird

Eine Markierung wird als `text range` gefuehrt, wenn sie **vollstaendig im
Inhaltsbereich eines einzigen Beitrags** liegt. Greift sie auch ausserhalb -
in die Metadatenspalte, den Beitragskopf, die Signatur, die Funktionsleiste
oder in einen zweiten Beitrag -, wird sie als `whole post` gefuehrt.

Begruendung: Wer den Rahmen mitfasst, hat nicht eine Textstelle zitiert,
sondern den Beitrag als Ganzes gegriffen.

Der Typ `whole post` ist **kein neuer Typ**. Die Toolbar legt ihn seit Build
430 an: `annotations.element_id` traegt dann die aeussere Beitragskennung und
`selection_json` bleibt leer (Beleg: `forensic_api/annotations.py` Z. 62-64,
`forensic_api/annotate.py` Z. 10-25).

## 2. Warum nicht ueber die innere Kennung

In Build 763 war erwogen worden, den Rahmen als *im container, aber nicht in
der inneren Kennung* zu bestimmen. Das ist **falsch**, aus drei am Quelltext
belegten Gruenden:

1. Die innere Kennung umschliesst den Rahmen mit. `viewtopic0.php` Z. 977
   oeffnet darin `div.postbody`, Z. 980 `div.postleft` mit Autor, Avatar und
   Rang, Z. 1161 `div.postfoot` mit den Funktionen.
2. Zwei der 24 durchgesehenen whole-post-Faelle beginnen in `div.postleft`
   (Muster `dl/dd/strong`) und waeren durchgerutscht.
3. Im Anfaengerforum gibt es die innere Kennung **ueberhaupt nicht**.
   `viewtopic1.php` Z. 576 schreibt die einfache Kennung. Die Regel haette
   dort jede Markierung als Rahmen gewertet.

Die innere Kennung wird deshalb **nicht ausgewertet**.

## 3. Der Kennungstest

```
starts-with(@id,'p') and number(substring-after(@id,'p')) = number(substring-after(@id,'p'))
```

Das ist keine Tautologie, sondern ein NaN-Test. `substring-after(@id,'p')`
liefert bei der doppelten Kennung einen Rest, der mit `p` beginnt;
`number()` darauf ergibt `NaN`, und `NaN = NaN` ist falsch. Damit faellt die
innere Kennung ohne eigene Regel heraus, ebenso `id="progressbar"`
(`viewtopic0.php` Z. 989).

## 4. Zustandsklassen

Klassen, die einen **Zustand** ausdruecken statt einer Struktur, sind fuer den
Rang `by_class` des XPath-Generators nicht zu verwenden:

```
hidden, censored, uncensored, shadow
```

Das Forum verwendet kein JavaScript, ein Wechsel von Klassennamen findet also
nicht statt. Der Ausschluss erfolgt trotzdem - eine Zustandsklasse sagt nichts
darueber aus, **wo** ein Element steht, und darum geht es beim Erzeugen eines
Weges. Die Liste ist nicht abschliessend.

---

## 5. Die Seitenarten

**Eine Seitenart kann mehrere Inhaltsbereiche fuehren** (Build 765). Der erste
passende gewinnt; deshalb stehen die spezielleren - mit eigener Bauform des
containers - vor den allgemeinen.


### `viewtopic` — Themenansicht des Hauptforums

Container-Element: `article` mit Kennung.

```
viewtopic0.php Z. 886  <article class="post" id="p<id>">
viewtopic0.php Z. 1212 </article>
```

#### Inhaltsbereich: Systembeitrag

| | |
|---|---|
| gilt fuer Bauform | `article` mit Klasse `systempost` |
| Anker | `div` mit `id="contentType4"` oder `name="contentType4"` |

**Belege im Forenquelltext**

```
viewtopic0.php Z. 330 Verzweigung bei posts.type == 4
viewtopic.php Z. 618 include('include/type4.php')
type4.php <div id="contentType4"> - INHALT
kuenftige Abzuege: name="contentType4" statt id
```

#### Inhaltsbereich: regulaerer Beitrag

| | |
|---|---|
| Anker | `div` mit Klasse `postmsg` |
| ausgeschlossen | `postsignature` |
| geforderter Vorfahre | `div` mit Klasse `postright` |

**Belege im Forenquelltext**

```
viewtopic0.php Z. 1004 <div class="postright">
viewtopic0.php Z. 1005 <h3> Themenbetreff - RAHMEN
viewtopic0.php Z. 1006 <div class="postmsg"> - INHALT
viewtopic0.php Z. 1142 <div class="postwarn"> - RAHMEN
viewtopic0.php Z. 1179 <div class="postsignature postmsg"> - RAHMEN
```

Der Systembeitrag ist seit Build 765 KEIN Sonderfall mehr: er hat einen Inhaltsbereich, er ist nur anders benannt. 'text range' ist dort zulaessig. Sein Anker ist ueber die Beitragsnummer verankert, weil 'contentType4' selbst NICHT eindeutig ist - sie wiederholt sich bei jedem Systembeitrag der Seite. Randnotiz: bei einem Teil dieser Beitraege traegt posts.message ein serialisiertes PHP-Array, das das Forum selbst nicht sinnvoll anzeigt; fuer die Bereichsfrage ohne Belang.

**Ausdruecke**

`general_post`

```
//article[starts-with(@id,'p') and number(substring-after(@id,'p')) = number(substring-after(@id,'p'))]/descendant-or-self::node()
```

`content` — Systembeitrag

```
//article[starts-with(@id,'p') and number(substring-after(@id,'p')) = number(substring-after(@id,'p'))][contains(concat(' ',normalize-space(@class),' '),' systempost ')]//div[(@id='contentType4' or @name='contentType4')]/descendant-or-self::node()
```

`content` — regulaerer Beitrag

```
//article[starts-with(@id,'p') and number(substring-after(@id,'p')) = number(substring-after(@id,'p'))]//div[contains(concat(' ',normalize-space(@class),' '),' postmsg ') and not(contains(concat(' ',normalize-space(@class),' '),' postsignature '))][ancestor::div[contains(concat(' ',normalize-space(@class),' '),' postright ')]]/descendant-or-self::node()
```

`frame` — Systembeitrag

```
//article[starts-with(@id,'p') and number(substring-after(@id,'p')) = number(substring-after(@id,'p'))][contains(concat(' ',normalize-space(@class),' '),' systempost ')]/descendant-or-self::node()[not(ancestor-or-self::div[(@id='contentType4' or @name='contentType4')])]
```

`frame` — regulaerer Beitrag

```
//article[starts-with(@id,'p') and number(substring-after(@id,'p')) = number(substring-after(@id,'p'))]/descendant-or-self::node()[not(ancestor-or-self::div[contains(concat(' ',normalize-space(@class),' '),' postmsg ') and not(contains(concat(' ',normalize-space(@class),' '),' postsignature '))][ancestor::div[contains(concat(' ',normalize-space(@class),' '),' postright ')]])]
```

Relative Fassung fuer `toolbar.js` — Kontextknoten ist der Endpunkt der Selection, auch wenn er ein Textknoten ist:

```
ancestor-or-self::*[starts-with(@id,'p') and number(substring-after(@id,'p')) = number(substring-after(@id,'p'))][1]
# Systembeitrag
boolean(ancestor-or-self::div[(@id='contentType4' or @name='contentType4')])
# regulaerer Beitrag
boolean(ancestor-or-self::div[contains(concat(' ',normalize-space(@class),' '),' postmsg ') and not(contains(concat(' ',normalize-space(@class),' '),' postsignature '))][ancestor::div[contains(concat(' ',normalize-space(@class),' '),' postright ')]])
```

### `beginner_viewtopic` — Themenansicht des Anfaengerforums

Container-Element: `div` mit Kennung.

```
viewtopic1.php Z. 576 <div class="box typeN" id="p<id>"> - EINFACHE Kennung, keine innere Kennung
```

#### Inhaltsbereich: regulaerer Beitrag

| | |
|---|---|
| Anker | `div` mit Klasse `regular`, `contents` |
| geforderter Vorfahre | `div` mit Klasse `topic-body` |

**Belege im Forenquelltext**

```
viewtopic1.php Z. 584 <div class="topic-body clearfix">
viewtopic1.php Z. 585 <div class="topic-meta-data"> - RAHMEN
viewtopic1.php Z. 604 <div class="regular contents"> - INHALT
viewtopic1.php Z. 629 <div class="postsignature postmsg"> - RAHMEN, liegt hier ausserhalb des Inhaltsankers
```

**Ausdruecke**

`general_post`

```
//div[starts-with(@id,'p') and number(substring-after(@id,'p')) = number(substring-after(@id,'p'))]/descendant-or-self::node()
```

`content` — regulaerer Beitrag

```
//div[starts-with(@id,'p') and number(substring-after(@id,'p')) = number(substring-after(@id,'p'))]//div[contains(concat(' ',normalize-space(@class),' '),' regular ') and contains(concat(' ',normalize-space(@class),' '),' contents ')][ancestor::div[contains(concat(' ',normalize-space(@class),' '),' topic-body ')]]/descendant-or-self::node()
```

`frame` — regulaerer Beitrag

```
//div[starts-with(@id,'p') and number(substring-after(@id,'p')) = number(substring-after(@id,'p'))]/descendant-or-self::node()[not(ancestor-or-self::div[contains(concat(' ',normalize-space(@class),' '),' regular ') and contains(concat(' ',normalize-space(@class),' '),' contents ')][ancestor::div[contains(concat(' ',normalize-space(@class),' '),' topic-body ')]])]
```

Relative Fassung fuer `toolbar.js` — Kontextknoten ist der Endpunkt der Selection, auch wenn er ein Textknoten ist:

```
ancestor-or-self::*[starts-with(@id,'p') and number(substring-after(@id,'p')) = number(substring-after(@id,'p'))][1]
# regulaerer Beitrag
boolean(ancestor-or-self::div[contains(concat(' ',normalize-space(@class),' '),' regular ') and contains(concat(' ',normalize-space(@class),' '),' contents ')][ancestor::div[contains(concat(' ',normalize-space(@class),' '),' topic-body ')]])
```

### `pmsnew` — Private Nachrichten

Container-Element: `div` mit Kennung.

```
pms_new/mdl/topic.php Z. 462 <div id="p<id>" class="blockpost">
```

#### Inhaltsbereich: regulaerer Beitrag

| | |
|---|---|
| Anker | `div` mit Klasse `postmsg` |
| ausgeschlossen | `postsignature` |
| geforderter Vorfahre | `div` mit Klasse `postright` |

**Belege im Forenquelltext**

```
pms_new/mdl/topic.php Z. 466 <div class="postbody">
pms_new/mdl/topic.php Z. 476 <div class="postright">
pms_new/mdl/topic.php Z. 477 <div class="postmsg"> - INHALT
pms_new/mdl/topic.php Z. 482 <div class="postsignature postmsg"> - RAHMEN
```

Gleicher Inhaltsanker wie 'viewtopic'. In Build 763 war fuer diese Seitenart ganz 'postright' als Inhalt vorgeschlagen; das haette die Signatur eingeschlossen und die Seitenarten ungleich behandelt, ohne dass ein Beleg das traegt.

**Ausdruecke**

`general_post`

```
//div[starts-with(@id,'p') and number(substring-after(@id,'p')) = number(substring-after(@id,'p'))]/descendant-or-self::node()
```

`content` — regulaerer Beitrag

```
//div[starts-with(@id,'p') and number(substring-after(@id,'p')) = number(substring-after(@id,'p'))]//div[contains(concat(' ',normalize-space(@class),' '),' postmsg ') and not(contains(concat(' ',normalize-space(@class),' '),' postsignature '))][ancestor::div[contains(concat(' ',normalize-space(@class),' '),' postright ')]]/descendant-or-self::node()
```

`frame` — regulaerer Beitrag

```
//div[starts-with(@id,'p') and number(substring-after(@id,'p')) = number(substring-after(@id,'p'))]/descendant-or-self::node()[not(ancestor-or-self::div[contains(concat(' ',normalize-space(@class),' '),' postmsg ') and not(contains(concat(' ',normalize-space(@class),' '),' postsignature '))][ancestor::div[contains(concat(' ',normalize-space(@class),' '),' postright ')]])]
```

Relative Fassung fuer `toolbar.js` — Kontextknoten ist der Endpunkt der Selection, auch wenn er ein Textknoten ist:

```
ancestor-or-self::*[starts-with(@id,'p') and number(substring-after(@id,'p')) = number(substring-after(@id,'p'))][1]
# regulaerer Beitrag
boolean(ancestor-or-self::div[contains(concat(' ',normalize-space(@class),' '),' postmsg ') and not(contains(concat(' ',normalize-space(@class),' '),' postsignature '))][ancestor::div[contains(concat(' ',normalize-space(@class),' '),' postright ')]])
```

### `search` — Suchergebnisse

Traegt **keine Beitraege**. Im Lauf zu Build 764 bestaetigt: 2 Markierungen, 0 container.

Das ist eine **Erwartung, kein Schalter**: die Erkennung laeuft auf diesen Seiten trotzdem, und ein Widerspruch zwischen Erwartung und Abzug wird gemeldet. Ein Ueberspringen anhand der Adresse waere ein stiller Sprung.

### `viewforum` — Themenliste eines Unterforums

Traegt **keine Beitraege**. Im Lauf zu Build 764 bestaetigt: 1 Markierung, 0 container.

Das ist eine **Erwartung, kein Schalter**: die Erkennung laeuft auf diesen Seiten trotzdem, und ein Widerspruch zwischen Erwartung und Abzug wird gemeldet. Ein Ueberspringen anhand der Adresse waere ein stiller Sprung.

### `profile` — Benutzerprofil

Traegt **keine Beitraege**. Festgestellt durch Alex, 08.09.2026.

Das ist eine **Erwartung, kein Schalter**: die Erkennung laeuft auf diesen Seiten trotzdem, und ein Widerspruch zwischen Erwartung und Abzug wird gemeldet. Ein Ueberspringen anhand der Adresse waere ein stiller Sprung.

### `notifications` — Benachrichtigungen

Traegt **keine Beitraege**. Festgestellt durch Alex, 08.09.2026.

Das ist eine **Erwartung, kein Schalter**: die Erkennung laeuft auf diesen Seiten trotzdem, und ein Widerspruch zwischen Erwartung und Abzug wird gemeldet. Ein Ueberspringen anhand der Adresse waere ein stiller Sprung.

---

## 6. Hinweise zur Fassung der Ausdruecke

**`descendant-or-self::node()` und nicht `//*`.** Der zweite waehlt nur
Elemente *unterhalb* des Ankers. Der Beitragstext steht aber direkt im Anker;
sein Textknoten hat den Anker als Elternelement. Unter `//*` laege der
haeufigste Fall ueberhaupt ausserhalb des Inhalts.

**Der Inhaltsanker ist ein Schrittausdruck mit Praedikat, kein Pfad.** Ein
Pfad beschreibt, *wo* der Anker steht. Gebraucht wird aber eine Aussage
*ueber einen Knoten*. Der Ausdruck
`not(ancestor-or-self::div[postright]//div[postmsg])` fragt, ob irgendein
Vorfahre mit Klasse `postright` irgendwo ein `postmsg` enthaelt - und das ist
fuer das `<h3>` mit dem Themenbetreff wahr, obwohl es nicht im Inhalt steht.

**Klassen werden tokenweise verglichen.** `contains(@class,'contents')` waere
auch bei `class="table-of-contents"` wahr.

**Die Signatur traegt die Klasse des Inhaltsankers.** In `viewtopic` und
`pmsnew` steht sie als Geschwister des Inhalts unter `postright` und muss
ausdruecklich ausgeschlossen werden. In `beginner_viewtopic` liegt sie schon
durch die Struktur ausserhalb des Ankers.

**Attribute werden mit ODER verknuepft.** Der Systembeitrag traegt seinen
Inhaltsbereich in den vorhandenen 144 page BLOBs als `id="contentType4"`, in
kuenftigen Abzuegen als `name="contentType4"`. Beide Formen treffen, eine
Nachbesserung nach dem naechsten Abzug entfaellt.

**Determinismus gilt je Baum, nicht zwischen den Baeumen.** Gemessen im Lauf
zu Build 764: 412 von 455 Ausdruecken loesen unter libxml2 anders auf als
unter html5lib. Seit Build 765 gilt html5lib als alleinige Grundlage
(Regelkatalog G9).

## 7. Zum Systembeitrag

Er haengt an `posts.type = 4`. `viewtopic0.php` Z. 330 leitet den Zweig ein
und verlaesst die Beitragsausgabe danach mit `return`. Es gibt zwei Bauformen:
die Tabelle in `viewtopic0.php` Z. 351 ff. und die aufklappbare aus
`include/type4.php`, eingebunden ueber `viewtopic.php` Z. 618. Die zweite ist
die im Bestand angetroffene.

**Bis Build 764 galt er als Beitrag ohne Inhaltsbereich, jede Markierung darin
wurde `whole post`. Seit Build 765 gilt das nicht mehr:** er hat einen
Inhaltsbereich, er ist nur anders benannt. Damit gilt fuer jede Beitragsart
dieselbe Regel, und `text range` ist auch dort zulaessig.

Sein Anker ist ueber die Beitragsnummer verankert, weil `contentType4` selbst
**nicht eindeutig** ist - sie wiederholt sich bei jedem Systembeitrag der
Seite. Dasselbe gilt fuer `id="progressbar"` (`viewtopic0.php` Z. 989), das je
Beitrag einmal geschrieben wird.

Randnotiz: bei einem Teil dieser Beitraege traegt `posts.message` ein
serialisiertes PHP-Array, das das Forum selbst nicht sinnvoll anzeigt. Fuer
die Bereichsfrage ohne Belang.

## 8. Was beim Uebertragen auf ein anderes Forum zu tun ist

1. Kennungsmuster der post container bestimmen und den Kennungstest anpassen.
2. Je Seitenart Container-Element und Inhaltsbereiche am Quelltext belegen -
   nicht aus dem gerenderten HTML raten.
3. Pruefen, ob ein Element die Klasse des Inhaltsankers ausserhalb des
   Inhalts traegt (hier: die Signatur). Solche Faelle ausdruecklich
   ausschliessen.
4. Pruefen, ob eine Seitenart mehrere Bauformen des containers kennt (hier:
   der Systembeitrag). Jede Bauform bekommt einen eigenen Inhaltsbereich.
5. Seitenarten ohne Beitraege ebenfalls aufnehmen - die Aussage 'hier stehen
   keine Beitraege' ist selbst eine Katalogaussage und wird gegen den Abzug
   geprueft.
6. Zustandsklassen sammeln und in Abschnitt 4 eintragen.

