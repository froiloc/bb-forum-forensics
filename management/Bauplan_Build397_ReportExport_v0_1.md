# Bauplan Build 397 ff. — Berichts-Ausgabe (Report-Renderer)

**Version:** 0.1 · **Datum:** 2026-07-12
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Basis:** 0.7.395 · **Umfang:** mehrere Builds (397 – 400)
**Status:** Bauplan — **noch kein `mc`**

---

## 0. Zusammenfassung in drei Sätzen

Die Berichts-Ausgabe ist **tot**: `export.py` ruft eine Methode auf, die es seit
dem Editor.js-Umbau nicht mehr gibt, und der Endpunkt ist trotzdem live. Die
Tests verdecken es doppelt — fünf sind abgeschaltet, die übrigen prüfen einen
`MagicMock`. Die Reparatur ist kein Einzeiler, weil zwei tragende Bausteine
**fehlen** (serverseitige Platzhalter-Auflösung; ein gemeinsam nutzbares
Renderer-Modul), und sie hat Vorrang vor der PDF-Erweiterung: **die Ausgabe ist
der Zweck des Werkzeugs — die Akte muss zur Staatsanwaltschaft.**

---

## 1. Befunde (gemessen, nicht vermutet)

### B1 — Der Export ruft eine Methode auf, die es nicht gibt

```
EvidenceDb.get_paragraphs         ->  False
EvidenceDb.get_blocks_for_report  ->  True
```

`db/evidence_db.py` dokumentiert es selbst: *„report_paragraphs ersetzt durch
report_blocks (Editor.js-Blockmodell)"*. `report_paragraphs` kommt im aktuellen
`evidence_schema_db.sql` **null mal** vor.

`forensic_api/export.py:128`:
```python
paras = edb.get_paragraphs(report.id)      # -> AttributeError
```

Der Endpunkt ist **live verdrahtet** (`forensic_api/__init__.py:448`):
`GET /_forensic/export?format=html|docx|sqlite`.

> **Seit dem Editor.js-Umbau kann kein Ermittler seinen Bericht ausgeben.**
> Weder HTML noch DOCX noch SQLite. Der Produktivbetrieb läuft seit dem 01.07.

### B2 — Die Tests verdecken es doppelt

- **Fünf** Tests in `tests/test_export.py` tragen `@unittest.skip(_PHASE1_SKIP)`.
  Begründung im Code:
  > *„export.py noch auf v0.3-Interface … Umbau erfolgt in Phase 2 (Build 100)."*

  **Build 100 ist nie gekommen.** Wir stehen bei 395. Der Skip ist seit rund
  295 Builds ein stiller Platzhalter — und er versteckt sich in den 59
  „skipped", über die wir jedes Mal hinweggelesen haben.

- Die **verbliebenen** Tests laufen gegen einen **`MagicMock`**-Bundle. Auf einem
  MagicMock liefert `get_paragraphs()` klaglos ein MagicMock zurück — **kein
  `AttributeError`**. Deshalb sind sie grün.

> **Die „grün aber tot"-Falle in Reinform:** Der Test prüft nicht den echten
> Code, sondern eine Attrappe, die alles beantwortet, was man sie fragt.

### B3 — `report_blocks` hat **keinen** Status

```
Felder: block_id, report_id, author, created_at, updated_at,
        block_type, block_data, placeholder_values_json, module_id
```

Das alte `EXPORT_STATUSES = ('active','approved')` ist **gegenstandslos**. Den
Status trägt jetzt der **Bericht** (`reports.status ∈ draft|submitted|approved|final`).
**Was exportiert wird, muss also neu festgelegt werden** (§4.1).

### B4 — Die Platzhalter werden **nur im Client** aufgelöst

`userinfo/report.js:412` → `_renderContent(content, placeholder_values_json)`.

Der **Server kennt den fertigen Text nicht**. Er hat `block_data` mit
`{{a:…}}`/`{{m:…}}`/`{{o:…}}` und daneben `placeholder_values_json`.

> Für einen serverseitigen Export muss die Auflösung **serverseitig nachgebaut**
> werden — und sie muss **identisch** zum Client sein. Weicht sie ab, weicht das
> Dokument, das zur Staatsanwaltschaft geht, von dem ab, was der Ermittler auf
> dem Bildschirm gesehen und verantwortet hat. **Das wäre forensisch fatal.**

### B5 — Neun Block-Typen

`paragraph`, `header`, `list`, `table`, `quote`, `image`, `delimiter`, `marker`,
`evidence` (Editor.js-Tool-Namen).

---

## 2. Architektur: **ein** Modul, **zwei** Server

Anforderung (Alex, 2026-07-12): Das Modul muss **vom forensischen Webserver und
vom Management-Server** aus nutzbar sein.

Deshalb wird der Renderer **serverunabhängig**: kein HTTP, kein
`ResolvedContext`, kein `DatabaseBundle`. Er bekommt **Verbindungen** und
liefert **Bytes**.

```
                 report_render/            (NEU — kennt keinen Server)
                 ─────────────────────────────────────────────────────
   evidence_<uid>.db ──► ReportSource ──┐
   forensic_<uid>.db ──► PlaceholderResolver ──► ReportDocument
   templates.db     ──►                 │        (neutrales Zwischenmodell)
                                        │
                                        ├──► HtmlRenderer    (397)
                                        ├──► DocxRenderer    (398)
                                        ├──► SqliteRenderer  (398)
                                        └──► PdfRenderer     (400)
                 ─────────────────────────────────────────────────────
                          ▲                              ▲
        forensic_api/export.py                management/report_export.py
        (Ermittler: eigener Fall)             (Chefin/StA: jeder Fall, RBAC)
```

**Beide Server bauen nur die Verbindungen und rufen dasselbe Modul.** Es wird
**keine Renderlogik dupliziert** — zwei Implementierungen desselben Berichts
wären die sicherste Art, sie auseinanderlaufen zu lassen (dieselbe Begründung
wie bei `ResultsRepo` in Build 390).

**`ReportDocument` ist der Angelpunkt:** ein neutrales Zwischenmodell (Meta,
Blöcke, Anker, Warnungen). Jeder Renderer sieht **nur** dieses Modell, nie die
Datenbank. Ein neues Format ist damit eine neue Datei, kein Umbau.

---

## 3. Die drei Regeln, die im Renderer nicht verhandelbar sind

### R1 — Ein Entwurf darf nicht wie eine freigegebene Akte aussehen

Jedes erzeugte Dokument trägt den **Berichtsstatus sichtbar im Kopf**:

| `reports.status` | Vermerk im Dokument |
|---|---|
| `draft` | **ENTWURF — nicht freigegeben. Nicht zur Vorlage bestimmt.** |
| `submitted` | **ZUR ABNAHME VORGELEGT — noch nicht freigegeben.** |
| `approved` / `final` | Freigabevermerk mit Datum und Person |

Ein Entwurf, der aussieht wie eine fertige Akte, ist gefährlicher als gar kein
Export.

### R2 — Kein Platzhalter verschwindet still

Beim Auflösen kann dreierlei passieren. **Alle drei werden sichtbar**, keines
still:

| Fall | Verhalten |
|---|---|
| aufgelöst | Wert wird eingesetzt |
| **nicht auflösbar** (Query liefert nichts, DB fehlt) | Der **Default** wird eingesetzt **und** der Platzhalter in die **Warnliste** am Dokumentende aufgenommen |
| **unbekannter Platzhalter** | **Sichtbare Markierung** im Text (`⚠ UNBEKANNT: …`) **und** Warnliste |

**Ein `{{a:user.username}}`, das unaufgelöst in einer Akte an die
Staatsanwaltschaft geht, ist ein Fehlbeleg. Ein stillschweigend gelöschter
Platzhalter ist schlimmer** — dann fehlt eine Aussage, ohne dass es jemand
merkt (Grundregel 1).

Jedes Dokument endet mit einem Abschnitt **„Hinweise zur Erzeugung"**:
Erzeugungszeitpunkt, Berichtsstatus, Zahl der Blöcke, **Liste aller nicht
auflösbaren Platzhalter**, Zahl der Beweisanker.

### R3 — Ein unbekannter Block-Typ wird gemeldet, nicht übersprungen

Neun Typen sind bekannt (B5). Taucht ein zehnter auf (neues Editor.js-Tool),
**wird er im Dokument sichtbar gemeldet** (`⚠ Unbekannter Blocktyp 'xyz' — Inhalt
nicht dargestellt`) **und** in die Warnliste aufgenommen.

Ein stilles Überspringen hieße: **ein Absatz der Ermittlungsakte fehlt, und
niemand erfährt davon.**

---

## 4. Offene Festlegungen (brauchen `mc`)

### 4.1 Welcher Bericht wird exportiert, und was davon?

Der alte Code nahm *„den ersten Bericht mit Status draft/submitted"* und filterte
Blöcke nach einem Feld, das es nicht mehr gibt.

**Vorschlag:**
- Parameter **`report_id`** (optional). Fehlt er → der Bericht mit der
  **höchsten `sequence_nr`** je `report_type`, sonst der jüngste.
- **Alle** Blöcke dieses Berichts, in `report_block_order.sort_index`-Reihenfolge.
- Blöcke **ohne** Sortierungseintrag kommen ans Ende **und** in die Warnliste
  (sie sind ein Datenfehler, kein Normalfall).

### 4.2 Bilder (`image`-Blöcke)

Woher kommt das Bild — `assets_<uid>.db`? Für HTML wäre **Base64-Einbettung** der
richtige Weg (selbstenthaltendes Dokument, wie bisher). Das muss ich noch messen.
**Klärung in 398**, HTML ohne Bilder wäre unvollständig.

### 4.3 PDF-Bibliothek

`reportlab` ist rein Python und pip-installierbar (**keine Systembibliotheken**);
`weasyprint` bräuchte Cairo/Pango und ist in der Windows-Offline-VM keine
realistische Wahl. **`reportlab` steht nicht in `requirements.txt`** — es muss in
der VM bereitgestellt werden.

**Ohne `reportlab`:** Ausweg wäre HTML mit Druck-Stylesheet → Browser-Druckdialog.
Kein serverseitiges PDF, aber keine neue Abhängigkeit.
**Entscheidung nötig vor Build 400.**

---

## 5. Bauschnitt

| Build | Inhalt | Ergebnis |
|---|---|---|
| **397** | **Fundament + HTML.** `report_render/`-Paket: `ReportSource`, `PlaceholderResolver`, `ReportDocument`, `HtmlRenderer`. `forensic_api/export.py` auf das Modul umgestellt. **Die fünf Skips fallen.** Tests gegen eine **echte `EvidenceDb`** auf einer temporären Datei — **kein MagicMock** dort, wo es auf das Interface ankommt. | HTML-Export **lebt wieder** |
| **398** | **DOCX + SQLite** auf demselben Fundament. Bilder (§4.2). | Alle drei Altformate lebendig |
| **399** | **Management-Anbindung:** `GET /api/report/export?user_id=&format=` (RBAC: `reports.review`/`reports.approve`). Damit kann die Chefin die Akte **ohne** den forensischen Server ausgeben. | „von beiden Servern nutzbar" eingelöst |
| **400** | **PDF** (`PdfRenderer`), abhängig von §4.3. | Welle 1 abgeschlossen |

**Nicht verhandelbar in jedem dieser Builds:** kein Test gegen einen `MagicMock`
an der Stelle, an der das Interface geprüft wird. Genau dort ist der Fehler
entstanden.

---

## 6. Risiken

| Risiko | Umgang |
|---|---|
| **Server-Renderer ≠ Client-Renderer** (B4) | Die Regex und die Auflösungsregeln werden **einmal** festgelegt (`placeholder_resolver.py`) und der Client-Code (`report.js:_renderContent`) daran **gemessen**. Ein Test vergleicht beide an denselben Eingaben. Weichen sie ab, ist das ein **Fehler**, kein Detail. |
| **Migrationsvorbehalt** | Der Renderer **liest nur**. Keine Migration, kein Schreibpfad in `evidence_<uid>.db`. |
| **Umfang** | Deshalb vier Builds statt einem. |

---

## 7. Was 397 **nicht** tut

- Kein PDF (400).
- Kein DOCX/SQLite (398).
- **Keine Schemaänderung.**
- Keine Änderung am Editor oder am Client-Rendering — der Client bleibt, wie er
  ist; der Server wird **an ihn angeglichen**, nicht umgekehrt.

---

*Dokument-Ende · Bauplan Build 397 ff. · 2026-07-12*
