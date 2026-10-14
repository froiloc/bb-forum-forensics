# Arbeitsstand — Auftragsakte `annotation_migration`

## Was das hier ist, und fuer wen

**Adressat: ein unabhaengiger kuenftiger KI-Chat ohne jede Kenntnis der
bisherigen Sitzungen.**

Diese Datei und die Dateien neben ihr sind der Ersatz fuer das, was sonst
verloren geht. Ein Uebergabedokument, das am Ende einer Sitzung geschrieben
wird, ist *stille Post*: die Haelfte des Wissens faellt heraus, und was
bleibt, ist eine Zusammenfassung meiner Erinnerung statt der Sache selbst.
Ruestzeiten und Uebergabeverluste sind deshalb eines der Kernprobleme dieser
Zusammenarbeit.

**Der Auftrag an jede Sitzung lautet deshalb:** Diese Akte ist mit **jedem
ausgelieferten Build** fortzuschreiben. Nicht am Ende, nicht auf Zuruf — als
Teil des Builds, und der Waechter `AS01` erzwingt es.

**Was hineingehoert**, in dieser Reihenfolge je Build:

1. **Entscheidungen** — was festgelegt wurde, und von wem.
2. **Revidiertes** — welche Annahme fiel, und woran sie fiel. Eine Revision
   ohne das Revidierte ist nicht lesbar.
3. **Erkenntnisse ueber vorhandenen Code** — was schon da war und
   uebersehen wurde. Dieser Punkt hat in dieser Arbeit am meisten Zeit
   gekostet.
4. **Messwerte** — mit Datum und Lauf. Eine Zahl ohne Herkunft ist eine
   Behauptung.

**Datenbankfelder und JSON-Keys gehoeren NICHT hierher, sondern in
`Metadaten_Katalog.json`.** Erwartungen an Spalteninhalte haben wiederholt
Tage gekostet; sie brauchen eine maschinell durchsuchbare Ablage, nicht
Fliesstext.

**Die Reihenfolge ist chronologisch, aelteste zuerst.** Wer die Gedankengaenge
verfolgen will, liest vorwaerts; wer nur den Stand braucht, liest den
naechsten Abschnitt. Umsortieren kann eine Maschine, Kontext erfinden nicht.

---

## Aktueller Stand

**Build 775** — in dieser Akte unveraendert seit Build 770 (Builds 771 ff.
bauen den Bildschleier, Build 774 den Transaktionsschutz, Build 775 korrigiert
den Bildschleier, siehe Chronologie). Die Migration der Annotationen von `selection_json` 1.0.0 auf
2.0.0 ist **vorbereitet, aber nicht begonnen** — es ist noch kein Datensatz
migriert.

**Der naechste Schritt:** der Lauf von `tools/wortlaut_abgleich.py` in der
Fassung von Build 768 ueber alle Bestaende, und die Durchsicht der
Aufspaltungen.

## Die Dateien dieser Akte

| Datei | Inhalt |
|---|---|
| `Regelkatalog_selection_json_2_0.md` | **Version 1.0, freigegeben.** Alle Festlegungen zur Migration. Ohne dieses Dokument ist keine Entscheidung nachvollziehbar. |
| **`Metadaten_Katalog.json`** | **Was zu jedem Datenbankfeld und JSON-Key GEMESSEN wurde** — mit Zitat, Build, Zeitstempel, Beispielwerten und Haeufigkeiten. Dazu je Feld die Fehlannahmen, die hier bereits gemacht wurden. Maschinell auswertbar; Schema daneben. |
| `Post_Bereiche_Katalog.md` | Wo im Beitrag der Inhalt aufhoert und der Rahmen anfaengt, je Seitenart, mit Belegzeilen. |
| `Arbeitsstand.md` | diese Datei |

Ausserhalb der Akte: `build.json` (Feld `note`) und
`issue-tracker/data/issues.json`.

---

## Chronologie

### Build 763 — Prefix-Diagnose

**Entscheidungen.** Gemessen wird, **wo** ein Ausdruck bricht, nicht nur ob:
beide Endpunkte, der post container am letzten aufloesenden Node, die Spanne
dazwischen.

**Messwerte.** 4010 Tests; 470 aktive Annotationen, 455 mit Anker.

### Build 764 — Inhalt gegen Rahmen

**Entscheidungen (Alex, 07.09.2026).** *Liegt die Markierung vollstaendig im
Inhaltsbereich eines einzigen Beitrags, ist es eine `text range`. Greift sie
in den Rahmen oder einen zweiten Beitrag, ist es ein `whole post`.* Ob der
Inhaltsbereich vollstaendig ausgeschoepft wird, ist **nicht** Teil der Regel.

**Revidiert.** Die Fallzuordnung 1–6 ueber die Lage der Endpunkte zueinander
traegt nicht: alle 24 von Alex als `whole post` eingeordneten Faelle fielen
auf Fall 1. Ebenso verworfen: der Rahmen sei *im container, aber nicht in der
inneren Kennung* — sie umschliesst den Rahmen mit, zwei der 24 Faelle beginnen
in `postleft`, und im Anfaengerforum gibt es sie gar nicht.

**Erkenntnisse ueber vorhandenen Code.** Die Signatur traegt **dieselbe**
Klasse `postmsg` wie der Inhalt und muss ausdruecklich ausgeschlossen werden.

**Messwerte.** 31 `whole post`, 418 `text range`, 6 unbestimmt; alle 24
durchgesehenen Faelle getroffen, kein Fehltreffer.

### Build 765 — Katalogumbau

**Entscheidungen (Alex, 08.09.2026).** Keine Sonderregeln je Beitragsart. Der
Systembeitrag ist **kein** Sonderfall mehr.

**Revidiert.** Bis 764 galt der Systembeitrag als Beitrag *ohne*
Inhaltsbereich. Er hat einen, er ist nur anders benannt — der Text steht in
`<div id="contentType4">`.

**Erkenntnisse ueber vorhandenen Code.** Die Annahme *eine Seitenart, ein
Anker* war falsch; der Systembeitrag steht auf derselben Seite wie der
regulaere Beitrag.

### Build 766 — Anker-Generator

**Entscheidungen (Alex, 08.09.2026).** Rangfolge `by_id` vor `by_class` vor
`by_position`. Keine Pruefung, ob eine Klasse die Kandidatenmenge verkleinert
— verkleinert sie nicht, ist der Gewinn null, aber die Kosten auch.

**Revidiert.** Die Warnung, id-gebundene Ausdruecke seien so zerbrechlich wie
positionsgebundene, war falsch: die 44 Brueche waren **ausnahmslos**
positionsgebunden.

**Erkenntnisse ueber vorhandenen Code.** `lxml` unterscheidet `.text` und
`.tail`; bei einem `tail` liefert `getparent()` das **vorangehende** Element.
Und die Nummer eines Textknotens laesst sich weder ueber die Objektidentitaet
noch ueber den Inhalt bestimmen — nur strukturell.

**Messwerte.** 910 Endpunkte, alle mit tragfaehigem Ausdruck, alle mit `by_id`
als staerkstem Rang. 845 haengen danach an **genau einem** Zaehlschritt; die
alten Ausdruecke hatten median 16.

### Build 767 — Wortlautabgleich

**Entscheidungen (Alex, 08.09.2026).** Drei Stufen: benannter Beitrag, zehn
naechste, ganze Seite. Keine Schwelle im Code. JSON statt YAML fuer den
Metadaten-Katalog.

**Revidiert.** Die Metadatenliste im Regelkatalog war ein Entwurf fuer etwas,
das es gab.

**Erkenntnisse ueber vorhandenen Code.** `AbsatzFinder._ueber_xpath()` haelt
den Fund **nie** gegen `textContent` — 101 Annotationen liefern deshalb
stillschweigend falschen Text. `PostMetaModule` in `toolbar.js` erhebt
laengst Metadaten, jeder Wert mit dem Namen seines Verfahrens.
`rangeFromSelection()` vergleicht zwei **verschiedene** Stringifizierungen.

**Messwerte.** 426 von 456 Wortlauten nach Normalisierung zeichengleich im
Abzug; 403 eindeutig; zwoelfmal war der Ausschluss versteckter Elemente
wirksam. Die 30 nicht gefundenen waren **alle** bereits von Alex
durchgesehen — kein neuer Fall.

### Build 768 — Aufspaltung und Auftragsakte

**Entscheidungen (Alex, 08.09.2026).** Je Thema eine **Auftragsakte** unter
`documents/`, Kurzname 8–30 Zeichen aus Kleinbuchstaben, Unterstrichen und
Zahlen. Der Metadaten-Katalog wird mit jedem Build fortgeschrieben. Chronologie
aelteste zuerst.

**Revidiert.** Die Stufenmessung aus Build 767 war **wertlos**: der benannte
Beitrag wurde aus `annotations.post_id` gelesen, und die ist bei 455 von 456
leer. Die 425 Treffer auf Stufe 3 hiessen nicht *der Anker zeigt woandershin*,
sondern *es gab nichts zu vergleichen*.

Ebenso revidiert: die Verteilung der Aehnlichkeiten aus 767 sah nach einer
Schwelle aus, war aber eine **falsche Suchmenge**. Bei `whole post` umfasst
der Wortlaut Rahmen und Inhalt in der Reihenfolge, in der der Browser sie
sichtbar aneinanderreiht.

**Erkenntnisse ueber vorhandenen Code.** Eine beitragsweise Verteilung kommt
nicht in Gang, wenn der erste Block ausserhalb jedes Beitrags liegt. Verteilt
wird deshalb **je Block der naechste Beitrag, der ihn traegt**.

**Was neu moeglich ist.** Eine Markierung ueber mehrere Beitraege wird
aufgespalten, und je Beitrag steht, **was daraus wuerde** — `text range` oder
`whole post`. Was zwischen den Beitraegen lag, wird als `entfaellt`
ausgewiesen statt stillschweigend getilgt.

### Build 769 — die Schranke

**Entscheidungen (Alex, 08.09.2026).** Die Aufspaltung wird auf die Beitraege
zwischen den beiden Ankerpunkten begrenzt. Eine Mindestlaenge je Block waere
der falsche Weg: sie daempft die Drift, beseitigt sie nicht, und sie waere
eine statistische Grenze fuer ein strukturell bestimmtes Problem. Ohne beide
Ankerpunkte gibt es keine Aufspaltung, sondern eine Vorlage.

**Revidiert.** Die Verteilung aus Build 768 driftete: sie suchte jeden Block
auf der ganzen Seite, und kurze Bloecke trafen in spaeteren Beitraegen
zufaellig. Aus zwei Beitraegen wurden neun.

Ebenso revidiert: die Vermutung, ein gebrochener Anker in der anonymisierten
Fassung belege einen unvollstaendigen Abzug. Er belegte nur, dass ich gegen
die falsche Wurzel gemessen habe.

**Erkenntnisse ueber vorhandenen Code.** Die XPath-Ausdruecke der Toolbar sind
relativ zu `div#forensic-viewport` gebildet, nicht zur Dokumentwurzel. Dass
`anker_diagnose` trotzdem richtig misst, liegt daran, dass es gegen den page
BLOB auswertet, dessen Wurzel der Viewport entspricht — eine Uebereinstimmung,
die bis hierhin ungeprueft war.

`<donate>`, `<my_leftbar>` und `<my_warning>` sind Platzhalter der
Forensoftware, die `header0.php` Z. 435 ff. zur Laufzeit ersetzt.

**Messwerte.** Build 768: 449 benannte Beitraege aus dem Anker, 340 auf Stufe
1, 78 auf Stufe 2, 32 auf Stufe 3, 6 nicht gefunden; 24 blockweise, 3
aufgespalten. Die 78 Stufe-2-Faelle liegen ausschliesslich auf `pmsnew` und
dort auf neun Seiten; auf sechs davon stehen gleichzeitig Stufe-1-Faelle.

### Build 770 — Zusammenhang und Endpunkte

**Entscheidungen (Alex, 08.09.2026).** Das Gegenprobe-Verfahren: anonymisierte
Seite im Browser ueber DevTools einsetzen, Markierung neu erzeugen,
`selection_json` entnehmen. Nur so passen Seite und Wortlaut zueinander.

**Revidiert.** Die Ankuendigung, die Verankerung des ersten Blocks wuerde die
Fehlzuordnung der Seitenzahl beheben, war falsch — der betroffene Block war
nicht der erste. Die Loesung ist die Zusammenhangsregel.

**Erkenntnisse ueber vorhandenen Code.** `Ankerbefund` traegt das Feld
`position_vorhanden`; ein Zugriff auf `bricht_bei` erzeugt einen
AttributeError, der in Build 769 von einem pauschalen `except Exception`
verschluckt wurde. Der Lauf sah gesund aus, obwohl die Aufspaltung nie
stattfand.

**Was neu moeglich ist.** Eine Markierung ist ein zusammenhaengender Bereich;
daraus folgt, dass ein Beitrag in der Zuordnung nur einen Lauf haben kann.
Zusammen mit der Verankerung der Endpunkte loest `583231/6` sauber auf: 71
Zeichen Praefix, Beitrag 1550483 vollstaendig, Beitrag 1550508 teilweise.

**Messwerte.** Build 769: 449 benannte Beitraege aus dem Anker, 340/78/32 auf
den drei Stufen, 6 nicht gefunden, 24 blockweise — aber 0 aufgespalten, was
den Feldnamen-Fehler sichtbar gemacht hat.

### Build 771 — kein Fortschritt in dieser Akte (Bildschleier)

**Entscheidungen.** Keine zur Annotationsmigration. Builds 771 bis 773 bauen
den Bildschleier im Forenviewer (Auftrag Alex, 09.10.2026; Bauplan
`management/Bauplan_Builds771-773_Bildschleier_v0_5.md`). Der naechste
Schritt dieser Akte ist unveraendert der aus Build 770.

**Erkenntnisse, die diese Akte beruehren.** Der Bildschleier wirkt
ausschliesslich ueber CSS und veraendert den DOM unter
`div#forensic-viewport` nicht: kein Attribut, keine Klasse, kein Knoten an
den Bildern. Das ist eine Bauvorgabe GERADE wegen dieser Akte — die
XPath-Ausdruecke der Annotationen haengen am Viewport-DOM (Metadaten-Katalog:
Bezugsebene `div#forensic-viewport`), und der Rang `by_class` des
XPath-Generators liest Klassen. Build 771 selbst beruehrt den Viewer noch gar
nicht (nur `coordinator.db`, Migration M040).

**Messwerte.** Keine.

### Build 772 — kein Fortschritt in dieser Akte (Bildschleier im Viewer)

**Entscheidungen.** Keine zur Annotationsmigration.

**Erkenntnisse, die diese Akte beruehren.** Der Bildschleier wirkt jetzt im
Viewer. Er schreibt die Klasse `aiw-image-veil` an `<html>`, ein
`<style id="aiw-image-veil-page">` in den `<head>` und eine Schaltflaeche in
die Toolbar — alles AUSSERHALB von `div#forensic-viewport`. Der Seiteninhalt
wird unveraendert eingefuegt; die Ausnahmen nennen die Bilder ueber ihre
exakten Attributwerte, ohne ein Attribut hinzuzufuegen. Waechter BS17c haelt
fest, dass `seiteAnwenden()` vor `viewport.innerHTML` steht und es genau eine
Einfuegestelle gibt.

**Messwerte.** Keine.

### Build 773 — kein Fortschritt in dieser Akte (Bildschleier, Lueckenschluss)

**Entscheidungen.** Keine zur Annotationsmigration.

**Erkenntnisse, die diese Akte beruehren.** Bei aktivem Schleier ersetzt der
Server `url(…)` in `<style>`-Bloecken des Seiteninhalts durch einen
Platzhalter (`server/blob_handler.py`, `_bildschleier_umschlag`). Das aendert
TEXT innerhalb von `<style>`, kein Element und kein Attribut; die Zahl der
Knoten bleibt gleich. Die gespeicherten BLOBs bleiben unberuehrt — alle
Werkzeuge dieser Akte lesen die BLOBs, nicht den ausgelieferten Inhalt.
Waechter BS30 haelt fest, dass ausserhalb von `<style>` kein Zeichen
veraendert wird.

**Messwerte.** Keine.

### Build 774 — kein Fortschritt in dieser Akte (Transaktionsschutz)

**Entscheidungen.** Keine zur Annotationsmigration.

**Erkenntnisse, die diese Akte beruehren.** Jede Schreibfunktion in
`db/evidence_db.py` laeuft jetzt in `with Schreibvorgang(...)`
(`db/schreibvorgang.py`): Lock der geteilten Verbindung fuer die ganze Dauer,
`rollback()` bei jeder Ausnahme. Betroffen sind auch `save_annotation`,
`delete_annotation` und `restore_annotation`. Ihr Verhalten im Erfolgsfall ist
unveraendert — nachgewiesen per AST-Vergleich (alt gegen neu, nach Entfernen
der Huelle gleich). Ein Migrationslauf, der ueber diese Funktionen schreibt,
bekommt bei einem Fehler kuenftig ein sauberes `rollback()` statt einer offen
gelassenen Transaktion.

**Messwerte.** Keine.

### Build 775 — kein Fortschritt in dieser Akte (Bildschleier, Korrekturen)

**Entscheidungen.** Keine zur Annotationsmigration.

**Erkenntnisse, die diese Akte beruehren.** Der Seitenumschlag traegt
`exempt_css` jetzt auch im klaren Zustand. Das ist ein `<style>`-Element im
Kopf (`#aiw-image-veil-page`), nicht im Viewport — am Seiteninhalt und an den
XPath-Ausdruecken der Annotationen aendert sich nichts.

**Messwerte.** Keine.
