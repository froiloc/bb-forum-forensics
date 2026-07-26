# Bauplan — Vereinheitlichung der Tabellen und Filter (UX)

**Anlass:** mc 2026-07-26 — „Ein Werkzeug wird erst gut, wenn es auch gut *in der
Hand liegt*. […] Es muss einfach zu erlernen sein, Fehler verzeihen und
unterstützen, und es muss eine schnelle Orientierung geben."
**Builds:** 548 ff. · **Baubasis:** 0.8.547
**Migration:** keine · **Neue Rechte:** keine
**Version:** 0.1 · 2026-07-26

---

## 1. Befund

Der Baum zerfällt in drei Gruppen (gemessen am 2026-07-26 gegen 0.8.547):

| Gruppe | Sichten | Zustand |
|---|---|---|
| **A — Referenz** | `assignment`, `cases` | Tabulator **+** `cockpit_tablekit.js` |
| **B — halbfertig** | `overview`, `mycases`, `myhistory`, `policy`, `reports`, `results`, `stats`, `support`, `mentoring`, `calendar`, `approval`, `lectorate` (12) | Tabulator da, **kein** Filterkopf, **keine** Werkzeugleiste |
| **C — Handtabelle** | `personnel`, `alias`, `crossfindings`, `crossref`, `merge`, `onboarding`, `planung`, `promotion`, `releases` (9) | `<table>` von Hand, kein Sortieren, kein Filtern |

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
| **552–555** | Gruppe C, die restlichen acht Handtabellen. |
| **556** | Feinschliff: einheitliche Leer-, Lade- und Fehlerzustände + Abnahme-Checkliste. |

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

## 6. Offene Punkte (2)

1. **`planung`** enthält eine Handtabelle, ist aber überwiegend Gantt/Prognose.
   Ob die Tabelle dort überhaupt eine Listentabelle ist, prüfe ich bei Build 552
   — sie könnte auch ein Diagrammgerüst sein und dann außen vor bleiben.
2. **Die Abnahme-Checkliste (556)** soll „gleich aussehen" prüfbar machen. Ohne
   sie bleibt Einheitlichkeit Geschmackssache und driftet beim nächsten Umbau
   wieder auseinander.

---
*Dokument-Ende · Bauplan UX/Tabellen · v0.1 · 2026-07-26*
