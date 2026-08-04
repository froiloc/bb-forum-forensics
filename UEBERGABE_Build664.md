# Übergabe Builds 663 und 664

**Baubasis:** 0.8.662 (Commit `aedc249`) · **Lieferung:** 0.8.664 · 2026-08-04
**Zweig:** `claude/build663` · **Verfahren:** Git-Bundle nach `documents/data-exchange.md`

Zwei Builds in einer Lieferung, als getrennte Commits im Bundle.

---

## 1. Was zu tun war

| Ticket | Art | Stand nach diesem Build |
|---|---|---|
| `d3f933cd-40fd-44c0-938f-e8f84053d382` | improvement | **behoben** — mit einer benannten Abweichung (§3) |
| `65a230fd-e31a-40d1-ac61-0e5ae8b98277` | bug | **geschlossen — kein Fehler** (§4) |
| `7b2f4a19-6c3d-4e58-9a71-0d5c8e2f4b63` | feature_request | **umgesetzt in Build 664** (§5) |

---

## 2. Ticket d3f933cd — der Baustein

Neu: `management/server/static/cockpit_datumspaar.js`.

```js
AIWDatumspaar.koppeln(vonEl, bisEl, {
    min:         true,   // untere Schranke am Bis-Feld      (Vorgabe AN)
    uebernehmen: false,  // leeres Bis-Feld bekommt Von-Datum (Vorgabe AUS)
    onUebernahme: fn,    // optional: Meldung an die Sicht
    onWarnung:    fn     // optional: Widerspruch melden
});
// -> { abmelden() }
```

Vier Zusagen, jede mit eigenem Testfall:

1. **Ein gefülltes Bis-Feld wird nie überschrieben** (DP03, CP25). Eine Bequemlichkeitsfunktion, die Eingaben ersetzt, macht jede Eingabe prüfungsbedürftig — das wäre schlimmer als die Unbequemlichkeit, die sie behebt.
2. **Ein Widerspruch wird gezeigt, nicht berichtigt** (DP07). Liegt ein vorhandenes Bis-Datum vor dem neuen Von-Datum, bleibt der Wert stehen; das Feld wird rot markiert und die Ergebniszeile nennt **beide** Daten. Die Korrektur bleibt Entscheidung der Bedienerin.
3. **Beim Zeichnen wird nicht übernommen** (DP09) — nur bei einer Eingabe. Sonst bekäme jedes Neuladen der Sicht (Formularzustand, Build 561) ein Bis-Datum geschenkt, das niemand gesetzt hat.
4. **`change`, nicht `input`.** Ein `<input type="date">` feuert `input` auch bei halbfertigen Eingaben; im Tastaturweg entsteht kurzzeitig etwa der 01.01.0002. Auf `input` zu reagieren hieße, das Bis-Feld mit Zwischenständen zu füllen.

**Eine Quelle, zwei Server.** Die Datei liegt einmal im Management-Baum und wird vom Ermittler-Webserver über eine neue Route mitausgeliefert (`forensic_api/static.py`, `_MGMT_STATIC_DIR`). Zwei Abschriften desselben Verhaltens laufen unweigerlich auseinander, und dann verhält sich dieselbe Bedienung an zwei Stellen verschieden.

**Das Risiko dieser Kopplung ist benannt und abgesichert:** `static.py` antwortet auf eine fehlende `.js`-Datei mit einem *leeren Platzhalter und HTTP 200*, damit der Browser nicht blockiert. Für den Betrieb richtig — für die Auslieferung gefährlich: ein Umbenennen oder Verschieben fiele niemandem auf, denn es gäbe keinen Fehler zu sehen, nur eine Funktion, die stillschweigend nicht mehr da ist. Dagegen steht `tests/test_forensic_static_registry.py`: **FS01** prüft *jeden* Registry-Eintrag auf Vorhandensein, **FS02** die Wegidentität zur Cockpit-Einbindung.

---

## 3. Abweichung vom Auftrag — bitte bestätigen oder überstimmen

Der Auftrag lautete, die Kopplung auf alle drei Datumspaare zu legen. **Die Übernahme liegt nur auf einem davon.**

| Maske | `min` | `uebernehmen` |
|---|---|---|
| Kapazitätspflege · Abwesenheit von/bis | ja | **ja** |
| Kapazitätsansicht · Auswertungszeitraum | ja | **nein** |
| Annotationsrecherche · Zeitraum-Schiene | ja | **nein** |

**Grund.** Es gibt zwei Arten von Datumspaaren. In einer **Eingabemaske** heißt ein leeres Bis-Feld „habe ich noch nicht gesagt" — dort ist die Übernahme genau die gewünschte Abkürzung. In einer **Filter- oder Zeitraumwahl** heißt es „ohne obere Grenze"; `annotation_recherche.js` setzt dafür ausdrücklich `to = null`. Spränge das Feld dort auf das Von-Datum, schrumpfte die Auswertung stillschweigend auf 24 Stunden, und wer es übersieht, hält das Ergebnis für den ganzen Zeitraum. Das wäre eine still herbeigeführte Auslassung (GR1) — erzeugt ausgerechnet von einer Bequemlichkeitsfunktion.

Die **Schranke** dagegen liegt auf allen drei Paaren: ein Ende vor dem Anfang ist in jedem Fall unsinnig.

Willst du die Übernahme dennoch überall, sind es zwei Zeichen je Aufrufstelle (`uebernehmen: true`) plus die Umkehrung von CA09. Sag Bescheid.

---

## 4. Ticket 65a230fd -- kein Fehler

**Aufgeklaert (Alex, 2026-08-04): der Gruendekatalog war leer.** Dass dann nur „(kein Grund)“ zur Wahl steht, ist das richtige Verhalten. Am Auswahlfeld wurde nichts geaendert.

Die Messung passte dazu. `CP22` (jsdom, echter Quelltext) hatte gezeigt: bekommt `renderCapacityPflege` zwei Gruende in `data.reasons`, enthaelt `#aiw-capp-av-grund` genau

```
['=(kein Grund)', 'urlaub=Urlaub', 'krank=Krankheit']
```

Deshalb wurde kein Fix gebaut -- und rueckblickend war genau das der Punkt: haette dieser Build auf Verdacht am Auswahlfeld gearbeitet, waere in einer Produktivumgebung funktionierender Code angefasst worden, ohne dass es dort etwas zu beheben gab. `CP22` bleibt als Gegenprobe stehen; faellt sie je um, sitzt der Fehler dann wirklich hier.

**Was bleibt und warum.** Die Maske zeigte den leeren Katalog *wortlos*. „Es ist noch kein Grund angelegt“ war von „die Gruende sind nicht angekommen“ nicht zu unterscheiden -- eine stille Auslassung (GR1) genau dort, wo eine Erklaerung gebraucht wird. Dieser Vorgang ist selbst der Beleg dafuer, dass die Luecke bedienungsrelevant ist: sie hat eine Fehlermeldung ausgeloest, wo keine Stoerung vorlag. Der Hinweis aus Build 663 (`CP23`) benennt den leeren Katalog jetzt und nennt die Gegenprobe. Er bleibt.

---

## 5. Build 664 -- Abwesenheiten berichtigen (Ticket `7b2f4a19`)

Abgetrennt aus 65a230fd, freigegeben mit `mc`, unveraendert nach Bauplan gebaut.

**Repo.** `AvailabilityRepo.replace_availability(entry_id, person_id, ...)` -> `{"entfernt_seq", "gesetzt_seq"}`. Dafuer sind `set`/`remove` in `WriteUnit`s zerlegt und die Validierung in `_pruefe` herausgezogen -- eine zweite Kopie der Regeln liefe eines Tages von der ersten weg. Die bestehenden Einzelwege verhalten sich unveraendert.

**Kein `UPDATE`.** Die alte Zeile wird stillgelegt und bleibt mit ihren urspruenglichen Werten stehen (`AV06`). Ein Update schriebe forensische Historie um -- danach waere nicht mehr feststellbar, was vor der Korrektur in der Akte stand.

**Alles oder nichts.** Beide Schreibungen laufen in einer Transaktion mit **zwei** Belegen. `AV07` provoziert einen Wertfehler und haelt fest: keine stillgelegte Zeile ohne Nachfolger (das waere ein Verlust), kein Beleg ohne Wirkung (das waere eine Luege in der Akte) -- und die hoechste `audit_log`-seq ist danach unveraendert.

**Die Scope-Falle.** Die Zielperson steht in der Nutzlast, die Person der *alten* Zeile nicht. Wer nur die Zielperson prueft, laesst eine selbstpflegende Person fremde Zeilen entfernen, indem sie sich selbst als Ziel angibt -- der Eintrag der anderen waere weg, und an seiner Stelle stuende einer fuer die Aufrufende. Die Pruefung laeuft deshalb zweimal (`KP11c`).

**Rohwerte statt Beschriftungen.** Die Tabelle zeigt `Urlaub` und `50 %`; daraus laesst sich weder `urlaub` noch die Einheit zurueckrechnen. `availabilityRows` fuehrt deshalb ein unsichtbares `_roh` mit den Codes (`CP28`). Fehlt es, **meldet** der Lader das, statt ein halbes Formular zu fuellen -- eine Bearbeitung mit stillschweigend leeren Feldern wuerde beim Speichern Angaben loeschen, die niemand angefasst hat.

**Leer ist keine 0** (`CP30`). Die Vorbelegung uebernimmt `value_pct`/`value_minutes` nur, wenn der Wert wirklich gesetzt ist -- sonst stuende in beiden Feldern eine 0, und der Server wiese *jeden* Bearbeitungsversuch ab.

**Zwei Bestandsfaelle angepasst, nicht abgeschwaecht.** `CP17` und `CP20` suchten Aktionsknoepfe ueber `.aiw-aktionen`. Seit die Abwesenheiten eine eigene Aktionsspalte haben, trifft der Selektor zwei Tabellen. Beide Faelle sind ueber die Hilfe-Marken auf die Arbeitszeiten eingegrenzt und pruefen dieselbe Zusage wie zuvor.

---

## 6. Hilfe

Regelgemäß angepasst (`Keine Änderung ohne Anpassung in der Hilfe`):

* `capacity_pflege.bedienung.av_von` — Vorbelegung benannt, samt der Zusage, dass ein gefülltes Feld nie überschrieben wird
* `capacity_pflege.bedienung.av_bis` — Schranke und die Behandlung des Widerspruchs
* `capacity_pflege.bedienung.av_grund_leer` — **neu**, mit der Gegenprobe
* `capacity.bedienung.bis` — Schranke, und *warum hier absichtlich nicht vorbelegt wird*
* `capacity_pflege.bedienung.av_bearbeiten`, `av_abbrechen` — **neu** (Build 664)
* `capacity_pflege.bedienung.av_speichern` — Umschaltung auf „Zeile ersetzen“
* Kapitel `capacity_pflege#ablaeufe` — dass nach einer Korrektur **zwei** Zeilen im Bestand stehen. Ohne diesen Satz haelt die naechste Bedienerin das für einen Doppeleintrag.

**Eigener Fehler, hier festgehalten:** Im ersten Anlauf standen „Build 663" in drei Hilfetexten. Regel H-1 (Anwendersprache) verbietet das; `test_help_register.py` HR14/HR20 hat es gefangen. Berichtigt.

---

## 7. Regression

Bauumgebung (Container, **Python 3.12.3 — nicht die VM**):

```
Python (pytest):     3131 passed, 92 skipped, 51 subtests   (662: 3103)
JavaScript (vitest):  122 Dateien, 1747 passed              (662: 1722)
Zusammenfassung:     beide BESTANDEN
```

33 neue Fälle. Build 663: `DP01–DP12` (neue Datei), `CP22–CP26`, `CA09/CA10`, `FS01/FS02`.
Build 664: `AV06–AV09`, `KP11b–KP11d`, `CP27/CP27b`, `CP28–CP31`.

---

## 8. Nach dem Einspielen zu prüfen

1. `python run_tests.py` — die 20 neuen Fälle müssen grün sein.
2. **Browser-Zwischenspeicher leeren** — vier `.js`-Dateien und `cockpit.html` sind geändert.
3. Kapazitätspflege: Von-Datum setzen → das leere Bis-Feld folgt, und die Ergebniszeile sagt es.
4. Kapazitätsansicht **und** Annotationsrecherche: Von-Datum setzen → das Bis-Feld **muss leer bleiben**; nur der Kalender darf keinen früheren Tag mehr anbieten. (Das ist die Gegenprobe zu §3.)
5. Kapazitätspflege bei **leerem** Gründekatalog: unter dem Grund-Feld muss „Der Gründekatalog ist LEER“ stehen. Nach dem Anlegen eines Grundes muss der Hinweis verschwinden und der Grund wählbar sein.
6. Eine Abwesenheit über „Bearbeiten“ berichtigen: die Meldung **muss zwei Belegnummern nennen**, und mit eingeblendeten entfernten Zeilen müssen danach **zwei** Zeilen dastehen — die stillgelegte alte und die neue.

---

## 9. Offene Punkte

* **Wartet auf dich:** die Entscheidung zu §3 (Übernahme nur in Eingabemasken). Sie ist die einzige Stelle, an der ich vom Auftrag abgewichen bin.
* **Erledigt durch dich:** das doppelte `bundle-einspielen.sh` ist entfernt. Dieses Bundle fässt die Datei nicht an; deine Löschung bleibt beim Zusammenführen bestehen.
* **Weiterhin offen aus Build 662:** erster echter kdiff3-Lauf unter Linux.
