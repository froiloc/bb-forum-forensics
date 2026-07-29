# Bauplan — Vereinheitlichung der Tabellen und Filter (UX)

**Anlass:** mc 2026-07-26 — „Ein Werkzeug wird erst gut, wenn es auch gut *in der
Hand liegt*. […] Es muss einfach zu erlernen sein, Fehler verzeihen und
unterstützen, und es muss eine schnelle Orientierung geben."
**Builds:** 548 ff. · **Baubasis:** 0.8.547
**Migration:** keine · **Neue Rechte:** keine
**Version:** 0.3 · 2026-07-26 (Build 556: Kriterium §2.2 samt Durchsetzung via UX10, `onboarding`-Entscheidung §2.3, geprüfte Zugehörigkeit §6.1)

---

## 1. Befund

Der Baum zerfällt in drei Gruppen (gemessen am 2026-07-26 gegen 0.8.547):

| Gruppe | Sichten | Zustand |
|---|---|---|
| **A — Referenz** | `assignment`, `cases` | Tabulator **+** `cockpit_tablekit.js` |
| **B — halbfertig** | `overview`, `mycases`, `myhistory`, `policy`, `reports`, `results`, `stats`, `support`, `mentoring`, `calendar`, `approval`, `lectorate` (12) | Tabulator da, **kein** Filterkopf, **keine** Werkzeugleiste |
| **C — Handtabelle** | `personnel`, `alias`, `crossfindings`, `crossref`, `merge`, `onboarding`, ~~`planung`~~, `promotion`, `releases` (**8**, s. §2.1) | `<table>` von Hand, kein Sortieren, kein Filtern |

**Es ist kein Neubau nötig.** `cockpit_tablekit.js` (Build 534) ist bereits das
gemeinsame Werkzeug — Kopffilter, Spaltenwahl, „Filter zurücksetzen",
Trefferzähler, Zustandssicherung. Es wurde für die Zuweisung gebaut und dann
nicht ausgerollt. Zu tun ist das Ausrollen auf 21 Sichten.

---

## 2. Zwei Sichten bleiben ausdrücklich draußen

**`audit` (Audit-Explorer) und `search` (Volltextsuche).** Beide filtern und
blättern **serverseitig**. Ein client-seitiger Kopffilter darüber würde nur die
geladene Seite durchsuchen und „3 Treffer" melden, während auf dem Server 300
liegen — eine **falsche Aussage in einem Beweismittelwerkzeug**.

Das steht hier und nicht nur im Gesprächsverlauf, weil es sonst später jemand
„repariert", indem er die fehlenden Filter nachrüstet. Wer diese Sichten
anfassen will, braucht zuerst einen serverseitigen Filterweg — nicht den
Kopffilter aus `tablekit`.

Entscheidung mc 2026-07-26: beide zunächst außen vor; die Volltextsuche wird
ohnehin erst erprobt.

### 2.1 `planung` bleibt draußen (entschieden Build 555)

Das war der **offene Punkt 1** dieses Bauplans. Gemessen statt vermutet:

Die Tabelle in `cockpit_planung.js` ist die **Szenarien-Tabelle der Prognose**,
nicht eine Listentabelle. `management/stats/forecast.py:98-105` erzeugt
**immer genau drei** Zeilen — optimistisch, erwartet, pessimistisch — und zwar
in dieser Reihenfolge.

Daraus folgt zweierlei:

* **Ein Kopffilter über drei feste Zeilen ist sinnlos.** Es gibt nichts
  einzugrenzen.
* **Eine Sortierung wäre schädlich.** Die Reihenfolge optimistisch → erwartet →
  pessimistisch *ist* die Aussage. Eine Spalte, die sich anklicken und
  umsortieren lässt, lädt dazu ein, sie zu zerstören — und eine nach „Restdauer"
  sortierte Szenarienliste liest sich wie eine Rangfolge, die niemand behauptet
  hat.

Die Tabelle bleibt daher eine schlichte `<table>`. Gruppe C umfasst damit
**acht** Sichten.

### 2.2 Die Regel dahinter (Build 556)

Zweimal derselbe Befund ergibt ein Kriterium. Es fehlte in v0.1 und steht
seither hier — **und in `cockpit_tablekit.js`, wo es gelesen wird**:

> Eine Tabelle bekommt Filter und Sortierung nur, wenn ihre **Zeilenzahl
> variabel** ist und ihre **Reihenfolge keine Aussage trägt**. Feste, fachlich
> geordnete Zeilenmengen bleiben schlichte `<table>`.

Der Grund ist nicht Sparsamkeit, sondern **Schaden**: eine anklickbare
Sortierspalte lädt dazu ein, eine Ordnung aufzulösen, die etwas bedeutet. Und
ein Filter über fünf feste Zeilen grenzt ohnehin nichts ein.

**Die Regel ist erzwungen, nicht nur aufgeschrieben.** `UX10` der
Konformitätssuite verlangt, dass jede Datei mit einer handgebauten Tabelle
entweder umgebaut *oder* ausdrücklich mit Grund ausgenommen ist — und dass die
Ausnahmeliste nicht veraltet (ein Eintrag, dessen Tabelle längst umgebaut wurde,
würde später eine neue Lücke zudecken). Verfahren wie `_BEWUSST_OHNE_EXPORT`
beim Akten-Export. Die Gegenprobe ist gefahren: entfernt man einen Eintrag,
bricht der Test.

### 2.3 `onboarding` bleibt draußen (entschieden Build 556)

`management/onboarding/checklist_status.py:43-58` friert je Art **genau fünf**
Schritte ein:

| Onboarding | Offboarding |
|---|---|
| Person → AD-Gruppe → Rolle → Einweisung → Zugang | Rechte entziehen → Fälle umverteilen → Zugang sperren → AD-Gruppe → Notizen |

Beim Offboarding ist die Reihenfolge **fachlich zwingend**. Der Dateikopf der
Sicht sagt selbst, worum es geht: „Ein vergessener Schritt (z. B. nicht
entzogene Rechte) wäre ein Governance-Risiko". Eine Sortierspalte wäre hier ein
Eigentor. Außerdem zeigt die Sicht immer nur **eine** Checkliste für **eine**
Person — es gibt nichts zu durchsuchen.

---

## 3. Hilfe-Anker: jetzt legen, später nutzen

Die geplante **Schnellhilfe** (Overlay-Modus, in dem erklärte Elemente umrandet
werden und der Zeiger zum Fragezeichen wird) gibt es noch nicht. Ihre Anker
entstehen trotzdem **jetzt**, bei jedem Tabellenumbau:

* Muster `<sicht>.<bereich>.<name>`, erzwungen durch `HILFE_MUSTER`.
* `tablekit.werkzeugleiste()` vergibt sie **automatisch** — jede künftige Sicht
  erbt sie, ohne dass jemand daran denken muss.
* `titelMitHilfe()` hängt sie an **Spaltenköpfe**; die sind das Erste, was eine
  Hilfe erklären muss („was steht in dieser Spalte?").
* Eine ungültige Kennung wird **verworfen und gemeldet**, nicht gesetzt: die
  Schnellhilfe umrandete das Element später, fände aber keinen Text. Lieber kein
  Rahmen als ein Rahmen ohne Inhalt.

Grund für „jetzt": ohne die Anker wären später **21 Sichten ein zweites Mal**
anzufassen.

---

## 4. Build-Schnitt

| Build | Inhalt |
|---|---|
| **548** | `tablekit`: Hilfe-Anker (`hilfeAnker`, `hilfeIds`, `titelMitHilfe`, automatische Vergabe in der Werkzeugleiste). **`personnel`** auf Tabulator + tablekit. Dazu die drei Kommentar-Nachträge aus AP-3G. |
| **549–551** | Gruppe B, je vier Sichten. Billig, weil Tabulator schon steht. |
| **552–554** | Gruppe B, Rest: `stats`, `lectorate`, `approval`. **Gruppe B abgeschlossen.** |
| **555 ff.** | Gruppe C, eine Sicht je Build: `crossref` (555), dann `alias`, `crossfindings`, `merge`, `onboarding`, `promotion`, `releases`. |
| **zuletzt** | Feinschliff: einheitliche Leer- und Fehlerzustände. |

**Zur Abnahme-Checkliste (ursprünglich Build 556):** sie ist **vorgezogen und
maschinell** — `tests/unit/test_cockpit_tabellen_ux.test.js` prüft je
eingetragener Sicht dieselben Zusicherungen (UX01–UX09). Eine Checkliste, die
niemand abhakt, ist eine Bitte; diese bricht. Neue Sichten kosten dort **einen
Registereintrag**.

**Warum `personnel` zuerst:** sie ist der schwerste Fall der Gruppe C (drei
Flag-Kästchen, Rollen-Chips mit Widerruf und eine Zuweisen-Auswahl **je Zeile**)
und wird damit zur Vorlage für die übrigen acht. Was hier trägt, trägt überall.

---

## 5. Die Regeln, nach denen umgebaut wird

1. **Abgeleitete Filterfelder statt Rohwerte.** Wahrheitswerte werden zu
   `'ja'/'nein'`, Listen zu einem Textfeld. Ein Filter mit `true`/`false` in der
   Auswahlliste wird nicht benutzt.
2. **Die Filterart folgt den Daten, nicht der Spalte.** `tablekit` entscheidet
   ab `SCHWELLE_AUSWAHL` (10) zwischen Auswahlliste und Eingabefeld. Eine
   Dienststelle mit 6 Kennungen braucht eine Liste, eine mit 60 ein Suchfeld —
   handverdrahtet wäre das still falsch.
3. **Kein stiller Ausfall.** Fehlt die Tabellenbibliothek, sagt die Sicht das
   **mit Anzahl** („es sind 3 Anwender hinterlegt"). Eine leere Fläche sähe aus
   wie „keine Daten vorhanden" (Grundregel 1).
4. **Schreibwege bleiben unangetastet.** Selbstschutz, kein optimistisches UI,
   Neuladen nach jedem Schreibvorgang — der Umbau ist eine Darstellungsfrage.
5. **Bestehende Klassennamen bleiben.** `aiw-pers-row`, `.self`, `.inactive`
   hängen künftig an Tabulator-Zeilen statt an `<tr>`; Stil und Tests laufen so
   nicht auseinander.

---

## 6. Offene Punkte

**Beide Punkte der Fassung v0.1 sind erledigt:**

1. ~~`planung`~~ — entschieden in Build 555, bleibt draußen (§2.1).
2. ~~Abnahme-Checkliste~~ — vorgezogen als maschinelle Konformitätssuite
   (Build 549, seither je Build erweitert).

**Neu hinzugekommen ist nichts** — wohl aber ein Befund, der über dieses
Arbeitspaket hinausweist: siehe §7.

---

## 6.1 Geprüfte Zugehörigkeit (Stand Build 556)

Nach dem Kriterium aus §2.2 geprüft — gemessen an den Server-Katalogen, nicht
vermutet:

| Sicht | Zeilenquelle | Ergebnis |
|---|---|---|
| `promotion` | Fremdforum-Kandidaten aus dem Dateibestand (forensic ohne evidence) | **variabel → Umbau** |
| `releases` | erfasste externe Fallfreigaben, wachsend | **variabel → Umbau** |
| `alias`, `crossfindings`, `merge` | Ermittlungsdaten, wachsend | **variabel → Umbau** |
| `planung` | `forecast.py:98-105` — immer 3 Szenarien | **draußen** (§2.1) |
| `onboarding` | `checklist_status.py:43-58` — immer 5 Schritte | **draußen** (§2.3) |
| `audit`, `search` | serverseitig gefiltert/geblättert | **draußen** (§2) |

---

## 7. Was der Umbau nebenbei gefunden hat

Diese Punkte waren nicht Gegenstand des Auftrags. Sie sind aufgefallen, weil ein
gemeinsames Werkzeug erzwingt, dass eine Sache nur an *einer* Stelle falsch sein
kann.

| Befund | Umfang | behoben in |
|---|---|---|
| Ersatzpfad ohne Zahlangabe — ein Ausfall sah aus wie ein Leerbefund | 7 Sichten | 549–554 |
| `rowClick` als Konstruktoroption: von Tabulator v6.4.0 **still ignoriert** | 3 Sichten (seit Build 367/378/386) | 551 |
| Ein Test, der genau diesen Fehler mitverdeckte (prüfte die nie benutzte Mechanik) | `test_cockpit_reports.test.js` | 551 |

Der `rowClick`-Fehler war in Build 486 für zwei Sichten erkannt und behoben
worden — der Vermerk stand im Kopf von `cockpit_lectorate.js`. Er hat die drei
übrigen Sichten nie erreicht. **Das ist das Argument für dieses Arbeitspaket in
einem Satz.**

---
*Dokument-Ende · Bauplan UX/Tabellen · v0.1 · 2026-07-26*
