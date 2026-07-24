# Bauplan B1 — Druck-/Akten-Export je Sicht (AP-2B, Idee 5)

**Version:** 0.1 · **Datum:** 2026-07-24 · **Modul:** `aiw_webserver`
**Basis:** HEAD `b145427` (v0.8.510) · **Buildnummern:** 511 (Backend) + 512 (Frontend)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Auftrag:** mc 2026-07-24 („Daher kannst du schon mit AP-2B (B1) weitermachen.")

---

## 1. Belegter Ist-Stand

Der Arbeitspaket-Plan §3 (AP-2B, B449) verlangt „Druck-/Akten-Export je Sicht
nachrüsten (restliche Sichten)". Stand heute:

| Sicht | Export | Art |
|---|---|---|
| `dashboard` | ✅ | `management/dashboard/html_export.py` — self-contained HTML **mit JS/ECharts**, per CLI (`dashboard_admin export-html`) |
| `workload` | ✅ | `management/workload/html_export.py` — dito |
| `support` | ✅ | `management/support_overview/html_export.py` — dito |
| `audit` | ✅ | `management/audit/audit_export.py` + `GET /api/audit/export` — **gerichtsfeste Tabelle** über `ExportEnvelope` |
| **die übrigen 28** | ❌ | — |

Build 442 hat die drei erstgenannten auf `ExportEnvelope` retrofittet
(`git show --stat` 442); der Rest ist offen.

## 2. Der Entwurf — und warum nicht 28 weitere `html_export.py`

Die naheliegende Lösung wäre, das Muster 28-mal zu kopieren. Das lehne ich ab:

1. **28 fast identische Dateien** wären 28 Stellen, an denen der Aktenkopf, die
   Prüfsummenbildung und die Escaping-Regel auseinanderlaufen können. Genau das
   sollte AP-2B (Idee 1, „einheitlicher Rahmen") beenden.
2. Jede neue Sicht müsste ihren Export **daran denken** mitzubringen. Vergisst
   sie es, fehlt er still — und stille Lücken sind das, was Grundregel 1
   verbietet.

**Stattdessen ein GENERISCHER Sichten-Export.** Die tragende Beobachtung: jede
Cockpit-Sicht wird aus genau einem (oder zwei) lesenden JSON-Endpunkt(en)
gespeist. Der Export kann deshalb:

1. denselben Endpunkt über den **bestehenden** `dispatch()` aufrufen,
2. das zurückgegebene JSON als gerichtsfeste Tabelle rendern,
3. in den `ExportEnvelope` aus AP-2B einwickeln.

**Der entscheidende Nebeneffekt:** Weil der Export durch `dispatch()` geht,
erbt er die **RBAC-Prüfung, den Scope und die Fehlerbilder der Sicht
automatisch**. Es entsteht kein zweiter Lesepfad, der abdriften oder ein Recht
übersehen könnte. Wer die Sicht nicht sehen darf, kann sie auch nicht
exportieren — ohne dass das irgendwo doppelt gepflegt werden müsste.

### 2.1 Warum die vier bestehenden Exporte bleiben

Sie sind etwas anderes: interaktive, JS-getriebene Analysedateien (ECharts,
Tabulator) bzw. — beim Audit-Explorer — ein bereits gerichtsfester Spezialexport
mit eigenem Filterbegriff. Der neue Export ist der **Akten-Export**: statisch,
druckbar, tabellarisch, ohne JavaScript. Beides steht nebeneinander; der Katalog
vermerkt bei diesen vier ausdrücklich, dass ein Spezialexport existiert.

## 3. Build 511 — Backend

### 3.1 Neue Dateien (je eine Klasse/Belang, Grundregel 10)

- **`management/export/view_export_spec.py`** — `SectionSpec` + `ViewExportSpec`
  (eingefrorene Dataclasses): welche Sicht, welcher Endpunkt, welche
  JSON-Abschnitte, optionale Spaltenbeschriftungen.
- **`management/export/view_export_catalog.py`** — der Katalog aller
  exportierbaren Sichten (`VIEW_EXPORTS`) + `spec_for(view_id)`.
- **`management/export/view_renderer.py`** — `ViewExportRenderer`: **reine**
  Render-Klasse (keine DB, keine Uhr, kein Netz) — JSON → gerichtsfestes,
  self-contained HTML ohne JavaScript.

### 3.2 Die vier Regeln des Renderers (jede gegen einen konkreten Fehler)

1. **Spalten werden aus den DATEN abgeleitet**, nicht im Katalog hart
   verdrahtet (Vereinigung aller Schlüssel, Reihenfolge des ersten Auftretens).
   *Grund:* Hätte ich 28 Spaltenlisten von Hand abgeschrieben, wäre jeder
   Tippfehler und jede spätere Feldergänzung eine **still fehlende Spalte** —
   also ein stillschweigend ausgelassener Beleg. Optionale `labels` verschönern
   nur die Überschrift, sie **filtern nie**.
2. **Nicht abgedeckte Top-Level-Schlüssel landen in „Weitere Daten"**. Was der
   Endpunkt liefert, steht im Export — auch wenn der Katalog es nicht kennt.
3. **Ein fehlender Abschnitt wird BENANNT** („im Datensatz nicht enthalten"),
   nicht weggelassen.
4. **Kappung ist sichtbar.** Über `_MAX_ROWS` (Vorgabe 5000) hinausgehende
   Zeilen werden abgeschnitten — mit einem **roten Vermerk im Dokument**, der
   die Gesamtzahl nennt. Ein stilles Abschneiden wäre der schlimmste Fall:
   der Export sähe vollständig aus.

Weiter: alle Werte `html.escape()` (UTF-8 bleibt), `None` → „—",
`True/False` → „ja/nein", verschachtelte Werte → kompaktes JSON.
Prüfsumme über `json_payload_sha256(data)` — der Empfänger kann sie aus
derselben Endpunkt-Antwort unabhängig nachrechnen.

### 3.3 Endpunkt

`GET /api/view/export?view=<id>` (weitere Query-Parameter werden **unverändert
durchgereicht**, damit z. B. `capacity` seinen `start` und `onboarding` seine
`person_id` bekommt).

Ablauf: Spec suchen → `dispatch(person_id, spec.api_path, query)` →
Status ≠ 200 wird **unverändert weitergereicht** (403 bleibt 403, 503 bleibt
503) → sonst rendern. Unbekannte `view` → 404 mit der Liste der bekannten IDs.

### 3.4 Tests Build 511

`tests/test_view_export_renderer.py` (**VR01–VR09**) und
`tests/test_view_export_api.py` (**VE01–VE08**), u. a.:
Spaltenableitung inkl. Feld, das nur in einer späteren Zeile auftaucht;
undeklarierte Schlüssel erscheinen; fehlender Abschnitt wird benannt; Kappung
ist sichtbar; XSS; leere Sicht ist ein Leerbefund, kein Fehler; **RBAC-Erbe**
(ohne Recht der Sicht → 403 aus `dispatch`, ohne dass der Export es selbst
prüft); Fehlerdurchreichung; Katalog-Konsistenz (jede exportierbare ID existiert
im Cockpit-`VIEW_CATALOG` — geprüft gegen `cockpit.js`).

## 4. Build 512 — Frontend

Ein **„Akten-Export"**-Knopf in der Cockpit-Kopfzeile, sichtbar genau dann, wenn
die aktive Sicht im Katalog steht. Er öffnet
`/api/view/export?view=<aktive Sicht>` in einem neuen Tab (samt der aktuell
gesetzten Sicht-Parameter). Dazu Druck-CSS (`@media print`), damit die erzeugte
Seite ohne Nacharbeit in die Akte kann.

## 5. Migrationsklasse

**Keine Migration, keine neue Fähigkeit.** Der Export liest ausschließlich über
den bestehenden, rechtegeprüften Lesepfad. Ermittler-Ergebnisdaten sind nicht
berührt.

---
*Dokument-Ende · Bauplan B1 · v0.1 · 2026-07-24*
