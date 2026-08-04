# Übergabe Build 663 — Tickets d3f933cd und 65a230fd

**Baubasis:** 0.8.662 (Commit `aedc249`) · **Lieferung:** 0.8.663 · 2026-08-04
**Zweig:** `claude/build663` · **Verfahren:** Git-Bundle nach `documents/data-exchange.md`

---

## 1. Was zu tun war

| Ticket | Art | Stand nach diesem Build |
|---|---|---|
| `d3f933cd-40fd-44c0-938f-e8f84053d382` | improvement | **behoben** — mit einer benannten Abweichung (§3) |
| `65a230fd-e31a-40d1-ac61-0e5ae8b98277` | bug | **nicht behoben** — Ursache eingegrenzt, Symptom sichtbar gemacht (§4) |
| `7b2f4a19-6c3d-4e58-9a71-0d5c8e2f4b63` | feature_request | **neu angelegt** — abgetrennt aus 65a230fd (§5) |

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

## 4. Ticket 65a230fd — gemessen, nicht geraten

**Das Frontend ist als Ursache ausgeschlossen.**

Messung (`CP22`, jsdom, echter Quelltext): wird `renderCapacityPflege` mit zwei Gründen in `data.reasons` aufgerufen, enthält `#aiw-capp-av-grund` genau

```
['=(kein Grund)', 'urlaub=Urlaub', 'krank=Krankheit']
```

Gegenprobe im Repository: `git diff 7ca1211..aedc249` zeigt, dass Build 662 am Kapazitätscode **nichts** geändert hat — die Messung gilt also für die von dir gemeldete Version.

**Deshalb wurde kein Fix gebaut.** Ob `GET /api/capacity/stammdaten` die Gründe überhaupt liefert, entscheidet sich an der Produktions-`coordinator.db` und nicht am Quelltext. Der Lesepfad (`_capacity_stammdaten` → `ReasonRepo.list_reasons` → `_geteilt`) ist beim Lesen unauffällig; ein Eingriff ohne Beleg wäre Raten.

**Erforderliche Messung** — Cockpit öffnen, F12, Kapazitätspflege aufrufen:

```js
window.AIW_COCKPIT_DEBUG = true;
fetch('/api/capacity/stammdaten').then(r=>r.json())
  .then(d=>console.log('COUNTS:', d.counts,
                       '| SCOPE:', d.scope,
                       '| ENTFERNT:', d.entfernt,
                       '| REASONS:', JSON.stringify(d.reasons)));
```

Zu beobachten ist nur die eine Ausgabezeile:

* `REASONS: []` und `counts.reasons: 0` → der Server liefert nichts. Dann liegt es an der Datenbank oder am Lesepfad, und ich suche dort weiter. Bitte in dem Fall zusätzlich `entfernt.reasons` mitschicken: ist die Zahl > 0, sind die Gründe stillgelegt und nicht verschwunden.
* `REASONS: [...]` gefüllt → dann widerspricht die Produktionsinstanz meiner Messung, und der Fehler sitzt zwischen Antwort und Auswahlfeld. Bitte dann zusätzlich die Zeile `Kapazitaetspflege gerendert: …` aus der Konsole mitschicken.

**Was dieser Build stattdessen tut** — ein GR1-Befund, der unabhängig vom Ursprung gilt: Bisher zeigte die Auswahl bei leerem Katalog nur „(kein Grund)", und zwar wortlos. „Es ist noch kein Grund angelegt" war von „die Gründe sind nicht angekommen" nicht zu unterscheiden — eine stille Auslassung genau dort, wo eine Erklärung gebraucht wird. Die Maske benennt den leeren Katalog jetzt ausdrücklich und nennt die Gegenprobe (`CP23`).

---

## 5. Abgetrennt: neues Ticket

`7b2f4a19-6c3d-4e58-9a71-0d5c8e2f4b63` — *Verfügbarkeits-Einträge nachträglich ändern können* (feature_request, medium, offen).

Der Wunsch aus 65a230fd („Es wäre sehr gut, wenn man Einträge auch im Nachhinein ändern könnte") ist fachlich ein eigenes Vorhaben: `availability_entry` ist auditiert, ein echtes `UPDATE` schriebe forensische Historie um. Der Weg wäre derselbe wie bei den Arbeitszeiten seit Build 555 — Ersetzen-Modus, alte Zeile stillgelegt und als Beleg erhalten. Vorschlag steht im Ticket; **noch nicht freigegeben**.

---

## 6. Hilfe

Regelgemäß angepasst (`Keine Änderung ohne Anpassung in der Hilfe`):

* `capacity_pflege.bedienung.av_von` — Vorbelegung benannt, samt der Zusage, dass ein gefülltes Feld nie überschrieben wird
* `capacity_pflege.bedienung.av_bis` — Schranke und die Behandlung des Widerspruchs
* `capacity_pflege.bedienung.av_grund_leer` — **neu**, mit der Gegenprobe
* `capacity.bedienung.bis` — Schranke, und *warum hier absichtlich nicht vorbelegt wird*

**Eigener Fehler, hier festgehalten:** Im ersten Anlauf standen „Build 663" in drei Hilfetexten. Regel H-1 (Anwendersprache) verbietet das; `test_help_register.py` HR14/HR20 hat es gefangen. Berichtigt.

---

## 7. Regression

Bauumgebung (Container, **Python 3.12.3 — nicht die VM**):

```
Python (pytest):     3124 passed, 92 skipped, 51 subtests   (662: 3103)
JavaScript (vitest):  122 Dateien, 1741 passed              (662: 1722)
Zusammenfassung:     beide BESTANDEN
```

20 neue Fälle: `DP01–DP12` (neue Datei), `CP22–CP26`, `CA09/CA10`, `FS01/FS02`.

---

## 8. Nach dem Einspielen zu prüfen

1. `python run_tests.py` — die 20 neuen Fälle müssen grün sein.
2. **Browser-Zwischenspeicher leeren** — vier `.js`-Dateien und `cockpit.html` sind geändert.
3. Kapazitätspflege: Von-Datum setzen → das leere Bis-Feld folgt, und die Ergebniszeile sagt es.
4. Kapazitätsansicht **und** Annotationsrecherche: Von-Datum setzen → das Bis-Feld **muss leer bleiben**; nur der Kalender darf keinen früheren Tag mehr anbieten. (Das ist die Gegenprobe zu §3.)
5. Die Konsolenmessung aus §4.

---

## 9. Offene Punkte

* **Wartet auf dich:** die Messung zu 65a230fd (§4) und die Entscheidung zu §3.
* **Randbefund, nicht angefasst:** `tools/` enthält zwei Einspielskripte — `bundle-einspielen.sh` (Bindestrich, ältere Fassung: kein kdiff3, keine Stash-Gegenprobe) und `bundle_einspielen.sh` (Unterstrich, aktuell). Verwechslungsgefahr an einer Stelle, an der eine Verwechslung Arbeit kostet. Auf dein Wort entferne ich die alte.
* **Weiterhin offen aus Build 662:** erster echter kdiff3-Lauf unter Linux.
