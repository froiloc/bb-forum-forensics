# Regelwerk AIW — Hilfesysteme

**Stand:** Build 622 · 2026-08-01 · **Baustelle H**

Das Werkzeug hat **drei** Hilfesysteme mit **zwei verschiedenen Adressaten**. Das ist der Schlüssel zu allen Regeln dieses Blattes.

| System | Wo | Adressat |
|---|---|---|
| Kontexthilfe | Popup im Hilfemodus (Shift+F1) | Ermittelnde |
| Vollhilfe | eigenes Fenster, `/help` | Ermittelnde |
| CLI-Hilfe | Kommandozeile; seit Build 622 **auch** als Betriebskapitel in der Vollhilfe | Betriebsseite |

## Regel H-0 — Fallinhaltsfrei

**Kein Hilfetext enthält Falldaten.** Keine echte Kennung, kein echter Name, keine echte Fallnummer. Beispielwerte stammen aus einem festgelegten fiktiven Beispielraum; damit ist an jeder Zahl im Text erkennbar, dass sie erfunden ist.

*Warum:* Die Vollhilfe ist zugleich das druckbare Handbuch. Ein Handbuch mit Falldaten wäre nicht weitergebbar.

*Durchsetzung:* `verify_fallinhaltsfrei()` in `management/help/pruefung.py`. **Ehrliche Abgrenzung:** Die Prüfung ist ein Netz gegen die wahrscheinlichsten Versehen, keine Garantie — ein frei formulierter Satz mit einem echten Namen darin ist maschinell nicht von einem erfundenen zu unterscheiden. Die eigentliche Sicherung ist die Vier-Augen-Lesung.

## Regel H-1 — Anwendersprache (Kontexthilfe und Vollhilfe)

**Festlegung mc 2026-07-31, wörtlich:**

> „Die Texte richten sich im Regelfall an den Endanwender. Dieser hat keinen technischen Hintergrund, und für ihn ist das Werkzeug ein Anwendungsgegenstand und kein Softwareprojekt. Dem Endanwender ist es egal, wie die Historie der Entwicklung war. Ihn interessiert der Ist-Stand: ‚Was kann ich damit machen?' Technische Begriffe wie ‚Build', ‚Backend' oder ‚Wahrheitsquelle' haben hier nichts zu suchen."

Daraus folgt eine Liste verbotener Begriffe mit ihrer jeweiligen Entsprechung — u. a. Build (weglassen), Backend/Frontend („das Werkzeug"), Wahrheitsquelle („maßgeblich"), Endpunkt (die Sicht benennen), Scope („Umfang"), Hash und audit_log („Protokollbuch", „lückenlose Kette"), Migration, Tooltip („Kurzhinweis, wenn Sie mit der Maus darauf zeigen"), Server („das Werkzeug"), Fähigkeit („Recht"), Dateinamen mit `.db`.

*Durchsetzung:* `verify_anwendersprache()` in `management/help/pruefung.py`. Sie prüft alle Texte, die eine anwendende Person zu sehen bekommt: Kapiteltitel, Rechtelage, Abschnittsüberschriften, Absätze, Listenpunkte und Popup-Texte. Quelltext-Kommentare prüft sie nicht — dort ist Entwicklersprache richtig.

*Wirkung in der Praxis:* Beim Scharfschalten in Build 597 fand die Prüfung **38 Verstöße in meinen eigenen, bereits abgenommenen Texten**. Guter Wille allein hätte denselben Fehler in den restlichen 33 Kapiteln wiederholt.

### Die einzige Ausnahme: wörtliche Bildschirmzitate

Ein verbotener Begriff darf stehen, wenn er als **Zitat in deutschen Anführungszeichen** einen Text benennt, der genau so auf dem Bildschirm steht. Anlass: Die Rechte-Sicht führt Spalten, die „Faehigkeit" und „Scope" heißen. Eine Hilfe, die eine Spalte anders nennt als der Bildschirm, ist schlechter als eine mit Jargon — die suchende Person findet die Spalte dann gar nicht.

Der Fließtext daneben benutzt weiterhin die Anwendersprache („Recht", „Umfang").

*Durchsetzung:* `BILDSCHIRMZITATE` in `pruefung.py`; `test_help_schluessel_paritaet.py` SP08 prüft, dass **jedes** Zitat wirklich als sichtbarer Text im Bestand vorkommt. Ohne diese Gegenprobe wäre die Liste ein Schlupfloch.

## Regel H-2 — Betriebssprache (CLI-Hilfe)

**Regel H-1 gilt für die CLI-Hilfe ausdrücklich NICHT** — aus demselben Grund, aus dem sie für die Ermittelnden gilt: Man spricht die Sprache des Adressaten.

Der Adressat der CLI-Hilfe ist eine technisch versierte Person, die Systeme aufsetzt, betreut und in einem einsatztauglichen Zustand hält, die mit dem Betriebssystem und mit Python vertraut ist und komplexe Systemanbindungen und Datenmigrationen durchführt (Festlegung mc 2026-07-31). Für sie ist `coordinator.db` der Name der Sache. Ein Katalog, der die Datei „die Falldateien des Kontos" nennt, wäre in dem Moment unbrauchbar, in dem jemand sie sichern will.

**Die Trennung ist strukturell, nicht nur redaktionell:** Der CLI-Katalog (`management/help/cli_katalog.py`) ist ein eigener Bestand. Er wird von `verify_anwendersprache()` nicht erfasst, weil er nicht Teil des Sicht-Registers ist — und er fließt auch nirgends dort hinein.

### Die Betriebskapitel in der Vollhilfe (seit Build 622)

Seit Build 622 steht der CLI-Katalog **zusätzlich** als Betriebsteil in der Vollhilfe: ein Kapitel je Werkzeug, 65 Stück, hinter den Sichtkapiteln, gerendert von `management/help/cli_html.py` aus **demselben** Katalog wie die Konsolenausgabe. Ein dritter Autorenbestand entsteht nicht; `test_help_cli_html.py` CH18 geht den Katalog Feld für Feld durch und verlangt jede Angabe im erzeugten HTML wieder.

Damit stehen **zwei Adressaten in einem Dokument**. Das ist nur unter drei Bedingungen zulässig, und alle drei sind maschinell nachgehalten:

1. **Kennzeichnung.** Jedes Betriebskapitel trägt im Kopf die Marke „Betriebskapitel", die Klasse `aiw-h-betrieb` und seine Rechtelage; davor steht ein Vorspann, der den Adressatenwechsel ausspricht. *Durchsetzung:* CH06 — für **jedes** Betriebskapitel, nicht stichprobenhaft.
2. **Eigenes Recht.** Der gesamte Betriebsteil hängt an `ops.view` (Entscheidung mc 2026-08-01). Begründung: Ein Betriebskapitel gehört zu keiner Sicht und kann darum kein Recht erben — die vorhandene Sperre hätte hier nichts, woran sie greift. Gewählt ist das Recht der Sichten mit demselben Adressaten (Integrität/Betrieb, Audit-Explorer, Fremdforum-Promotion). Ohne dieses Recht ist der Teil **leer**: kein Verzeichniseintrag, kein Kapitel, kein Suchindex-Eintrag. *Durchsetzung:* CH01, CH15e, HD20, HA14.
3. **Keine Rückwirkung nach oben.** Die Betriebssprache darf nicht in die Sichtkapitel durchschlagen. *Durchsetzung:* HD19 misst den Seitenteil oberhalb des Betriebsvorspanns gegen „Build", „coordinator.db", „python -m" und „.py".

**Regel H-1 gilt für die Betriebskapitel nicht, Regel H-0 sehr wohl.** Der Katalog beschreibt Werkzeuge, keine Fälle; Beispielaufrufe laufen gegen Wegwerf-Bestände.

## Gliederung eines Vollhilfe-Kapitels

Jedes Kapitel hat dieselben sechs Abschnitte, in dieser Reihenfolge:

`zweck` · `rechte` · `aufbau` · `ablaeufe` · `grenzen` · `verweise`

*Durchsetzung:* `PFLICHT_ANKER` in `management/help/modell.py`, geprüft von `verify_gliederung()`.

**Die Zusicherung steht im ersten Absatz, nicht erst unter „Grenzen".** Wer nur den Anfang eines Kapitels liest — und das ist der Normalfall —, muss die Zusicherung gelesen haben. Wo eine Sicht als etwas gelesen werden könnte, das sie ausdrücklich nicht ist, steht der Satz zweimal: im ersten Absatz **und** unter „Grenzen".

**Wortlaute aus der Oberfläche werden übernommen, nicht umformuliert.** Eine Zusicherung, die in der Hilfe anders klingt als auf dem Bildschirm, wäre schlimmer als keine: sie ließe Raum für die Frage, welche der beiden gilt.

## Anker und Marken

**Eine Hilfe-Marke wird LITERAL gesetzt, nie zusammengesetzt.**

```js
h.setAttribute('data-hilfe-id', 'faelle.titel');   // richtig
tk.hilfeAnker(h, praefix + '.titel');              // NICHT so
```

*Warum:* Eine zusammengesetzte Kennung steht nirgends wörtlich im Quelltext. Die Paritätsprüfung kann dann nicht sehen, dass es zu einem Hilfetext auch eine Marke gibt — und ein Text, den niemand je zu sehen bekommt, bleibt unbemerkt. Wird die Kennung an einen Helfer übergeben, gehört sie **an die Aufrufstelle**, wörtlich neben den Attributnamen.

*Befund, der zu dieser Regel führte:* Build 603 (Kapazitätspflege, vier stumme Abschnittsüberschriften) und Build 604 (dreimal beinahe wiederholt).

**Form einer Kennung:** `<präfix>.<name>` oder `<präfix>.<bereich>.<name>`, je Abschnitt Kleinbuchstaben, Ziffern und Unterstrich, beginnend mit einem Buchstaben. Dieselbe Form wie `HILFE_MUSTER` in `cockpit_tablekit.js` — zeichengleich, damit beide Seiten dasselbe meinen.

**Der Präfix ist der Name der TABELLE, nicht immer der der Sicht.** Eine Sicht kann mehrere führen (Support-Historie: drei; Kapazitätspflege: vier; Rechte-Sicht: zwei). Die Zuordnung Präfix → Sicht steht an einer Stelle: `management/help/anker_katalog.py`.

*Befund, der zu dieser Regel führte:* In Build 602 waren Spaltentexte für die Support-Historie unter dem Präfix `support` verfasst worden — die drei Tabellen heißen aber `support_mine`, `support_oncase` und `support_weitere`. Die Texte wären an keiner Tabelle je erschienen.

## Sichtbarkeit

Die Vollhilfe ist **serverseitig nach Rechten gefiltert** (Entscheidung E1). Wer eine Sicht nicht sehen darf, sieht auch ihr Kapitel nicht; ein Direktaufruf liefert 403. Ausnahme: das Kapitel zur Ansichtseinstellung ist immer sichtbar, weil die Sicht selbst kein Recht verlangt.

*Durchsetzung:* `management/help/sichtbarkeit.py`, geprüft in `tests/test_help_sichtbarkeit.py` mit einer Rechte-Matrix.

## Vollständigkeit

**Keine Sicht ohne Kapitel.** Seit Build 605 ist die Fehlliste leer und die Prüfung scharf: von da an ist jeder neue Eintrag ein Befund — entweder ist eine Sicht ohne Hilfe hinzugekommen oder ein Kapitel verlorengegangen.

*Durchsetzung:* `verify_sichten_abgedeckt()` und `verify_fehlliste_monoton()`; der Stand liegt in `tests/hilfe_fehlliste_stand.json`.

**Keine Marke ohne Text, kein Text ohne Marke.** Zwei Prüfungen, die einander ergänzen und einzeln nur ein halbes Netz wären:

- `tests/test_help_schluessel_paritaet.py` findet die **literalen** Marken per Textsuche (SP01–SP08).
- `tests/unit/test_cockpit_tabellen_ux.test.js` UX11 rendert jede Listensicht und liest die **berechneten** Anker aus dem Baum. Nur diese Messung trifft, was am Ende wirklich am Element steht.

Damit UX11 messen kann, liest die JavaScript-Seite das Hilferegister vom Register selbst (`tests/unit/_hilfe_schluessel.js`) — ein regulärer Ausdruck über die Quelltexte sähe berechnete Schlüssel grundsätzlich nicht.

## Pflicht bei jeder Änderung

**Keine Änderung und keine Neuerung ohne Anpassung oder Ergänzung in der Hilfe.** Wer ein Feature, eine Funktion oder eine Komponente der Verwaltung ändert, ändert im selben Build den zugehörigen Hilfetext.

**Kein Bedienelement ohne Text.** Seit Build 631 wird nicht mehr nur geprüft, ob eine *vorhandene* Marke einen Text hat, sondern ob ein Bedienelement überhaupt eine Marke bekommen hat. Das war die Lücke, in der Vorgang 17200856 saß: Die Paritätsprüfungen waren grün, während vier von fünf Schaltflächen stumm blieben — ein Knopf ohne Marke kam in ihrer Welt schlicht nicht vor.

Wer ein `button`, `input`, `select` oder `textarea` baut, setzt im selben Build die Marke `<sicht>.bedienung.<name>` und schreibt den Text nach `management/help/inhalt/`.

*Durchsetzung:* `tests/test_help_bedienelemente.py` (BD01–BD08) gegen `tests/hilfe_bedienung_stand.json`; die Zahlen dürfen nur sinken, und eine neue Datei mit Lücke ist ein Befund.

Zwei Fallstricke, beide in Build 632 aufgetreten und beide leicht zu vermeiden:

- Die Marke muss **innerhalb desselben Funktionsrumpfs** stehen wie das `createElement` — die Erhebung sucht nur bis zum Beginn der nächsten Funktion. Steht direkt hinter dem Element eine Hilfsfunktion, gehört die Marke davor.
- Die Kennung steht **literal** im Quelltext, nie zusammengesetzt. Ein Umbruch nach dem Komma ist erlaubt (Gegenprobe BD05c), eine berechnete Kennung nicht: SP01/SP02 sähen sie nicht.
