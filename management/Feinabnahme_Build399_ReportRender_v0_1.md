# Feinabnahme Build 399 — Fundament + HTML (`report_render/`)

**Version:** 0.1 · **Datum:** 2026-07-13 · **Autor-Vorschlag zur Abnahme durch mc**
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Basis-Commit:** `deab0a5` (Version 0.7.397) · **Ziel-Build:** 399
**Bezug:** `Bauplan_Build397_ReportExport_v0_1.md` §2/§5; mc-Festlegungen 2026-07-13

> Zweck dieses Dokuments: **den Modulschnitt vor der Codeübergabe abnehmen.**
> Jede Aussage ist mit `Datei:Zeile` belegt. Erst nach `mc` entsteht Code.

---

## 0. Belegte Ausgangslage (gemessen)

| Befund | Beleg |
|---|---|
| `report_render/` existiert nicht | `find . -name report_render` → leer |
| `export.py` ist tot (v0.6.097) | `forensic_api/export.py:33,56,128` (`get_paragraphs`, altes `EXPORT_STATUSES`) |
| Endpunkt live verdrahtet | `forensic_api/__init__.py:448,805` (`GET /_forensic/export`) |
| Server-Resolver existiert bereits, aber nur `a:` | `forensic_api/placeholders.py:58` (`_PLACEHOLDER_RE`, nur `auto|a`, 2 Felder) |
| Client-Wahrheit kennt a/m/o + 3 Felder + b64regex | `userinfo/placeholder_chips.js:73` (`_CHIP_RE`), Doku Z. 8–29 |
| Blocklader ordnet bereits nach `sort_index`, Ordnungslose ans Ende | `db/evidence_db.py:1675` (`get_blocks_for_report`, `COALESCE(...,999999)`) |
| 5 Export-Tests `@unittest.skip`, Rest gegen `MagicMock` | `tests/test_export.py:51,106,124,138,195,208` |

**Zentrales Risiko (R-Parität):** Server- und Client-Auflösung stimmen **heute nicht
überein** (`a` vs. `a/m/o`, 2 vs. 3 Felder). Ein serverseitiger Export, der `{{m:}}`/`{{o:}}`
nicht auflöst, liefert eine Akte, die vom Bildschirm des Ermittlers abweicht — forensisch fatal
(Bauplan §6). Deshalb ist `placeholder_resolver.py` der Angelpunkt von Build 399.

---

## 1. Modul-Grenzen (`report_render/`) — je Klasse eine Datei (Grundregel 10)

```
report_render/
├── __init__.py               # nur Re-Exporte, keine Logik
├── report_document.py        # ReportDocument, ReportBlock, DocWarning  (neutrales Modell)
├── placeholder_resolver.py   # PlaceholderResolver                      (reiner Kern, kein HTTP)
├── report_source.py          # ReportSource                             (DB → ReportDocument)
└── html_renderer.py          # HtmlRenderer                             (ReportDocument → bytes)
```

**Serverunabhängig (Bauplan §2):** kein `import` von `http_server`, `ResolvedContext` oder
`DatabaseBundle` in `report_render/`. Eingänge sind **sqlite3-Verbindungen** und Skalare,
Ausgang sind **Bytes**. Damit von `forensic_api/export.py` **und** später
`management/report_export.py` nutzbar.

---

## 2. `ReportDocument` — das neutrale Zwischenmodell (`report_document.py`)

```python
@dataclass
class DocWarning:
    kind: str          # 'unresolved_placeholder' | 'unknown_placeholder'
                       # | 'unordered_block' | 'unknown_block_type' | 'missing_image'
    detail: str        # menschenlesbar, z.B. "{{a:user.username}}"
    block_id: str | None = None

@dataclass
class RenderedBlock:
    block_id: str
    block_type: str        # Editor.js-Toolname (B5)
    html_fragment: str     # bereits aufgelöst + escaped, aber ohne Dokumentrahmen
    anchors: list          # ReportAnchorRecord je Block (Fußnoten)

@dataclass
class ReportDocument:
    # Meta
    report_id: int
    report_type: str        # interim|final|addendum
    sequence_nr: int
    title: str
    status: str             # draft|submitted|approved|final  -> R1-Kopf
    uid: int
    username: str
    generated_at: int       # Unix-ts (KEIN datetime.now() im Modul; von außen gesetzt)
    # Inhalt
    blocks: list[RenderedBlock]
    warnings: list[DocWarning]
```

Jeder Renderer sieht **nur** dieses Modell. Neues Format = neue Datei, kein Umbau (Bauplan §2).

---

## 3. `PlaceholderResolver` (`placeholder_resolver.py`) — Paritäts-Angelpunkt

**Regex identisch zu `_CHIP_RE`** (`placeholder_chips.js:73`), portiert nach Python:

```python
_CHIP_RE = re.compile(
    r"\{\{(a|auto|m|mandatory|o|optional):([A-Za-z0-9._-]+)"
    r"(?:\|([^|}\n]*))?(?:\|([^|}\n]*))?(?:\|([^|}\n]*))?\}\}"
)   # Gruppen: typ, name, default, description, b64regex
```

Auflösungsregeln (deckungsgleich mit Client-Semantik `placeholder_chips.js:25–29`):

| Typ | Quelle | Fehlerfall → Verhalten (R2) |
|---|---|---|
| `a`/`auto` | Cache → `templates.get_query` → SQL gegen `fdb` (Logik aus `placeholders.py:298–325`) | nicht auflösbar → **default** einsetzen **+** `DocWarning('unresolved_placeholder')` |
| `m`/`mandatory` | Wert aus `placeholder_values_json[name]` des Blocks | leer → default; leer **und** kein default → `DocWarning('unresolved_placeholder')` |
| `o`/`optional` | Wert aus `placeholder_values_json[name]` | leer → default (ohne Warnung; optional ist zulässig leer) |
| unbekannter Typ | — | Text-Markierung `⚠ UNBEKANNT: …` **+** `DocWarning('unknown_placeholder')` |

**Reiner Kern:** `resolve(text, values, resolve_auto_fn) -> (resolved_text, list[DocWarning])`.
`resolve_auto_fn(name, default) -> str|None` wird injiziert — so bleibt das Modul HTTP-frei;
`export.py` reicht eine Funktion herein, die den bestehenden Cache/Query-Pfad kapselt.

**Refactor statt dritte Kopie:** Der `a:`-Pfad aus `placeholders.py:_resolve_body` (Z. 279–328)
wird als `resolve_auto_fn`-Implementierung wiederverwendet; die HTTP-Klasse `PlaceholderEndpoint`
ruft künftig denselben Kern. Keine Duplikation (Bauplan §6, Analogie `ResultsRepo`/Build 390).

---

## 4. `ReportSource` (`report_source.py`) — DB → `ReportDocument`

Eingänge: `evidence_con`, `forensic_con`, `templates_con`, `assets_con`, `uid`, `username`,
`generated_at`, optional `report_id`.

Ablauf:
1. **Berichtswahl (§4.1, mc):**
   - `report_id` gegeben → `EvidenceDb.get_report(report_id)` (`evidence_db.py:1316`).
   - sonst → aus `get_reports()` (`:1308`) der Bericht mit **höchster `sequence_nr`**;
     Gleichstand → jüngstes `created_at`. `report_type` filtert **nicht** (nur Kopf-Info).
     *(Offen: Typ-Priorität — derzeit nein, siehe §9.)*
2. **Blöcke:** `get_blocks_for_report(report_id)` (`:1675`) — bereits `sort_index`-sortiert.
3. **Ordnungslose Blöcke → Warnliste:** Gegen `get_block_order_for_report` (`:1796`) prüfen;
   Blöcke ohne Eintrag ans Ende **und** `DocWarning('unordered_block')` (R2/Grundregel 1).
4. **Platzhalter je Block** via `PlaceholderResolver` (§3), Werte aus
   `ReportBlockRecord.placeholder_values_json` (`evidence_db.py:526`).
5. **Anker je Block:** `get_anchors_for_block(block_id)` (`:1970`) → `RenderedBlock.anchors`.
6. **Bilder (§4.2, mc — nur Verweis):** siehe §6.

**Nur-Lesen:** kein Schreibpfad in `evidence_<uid>.db` → **kein Migrationsvorbehalt** berührt.

---

## 5. `HtmlRenderer` (`html_renderer.py`) — `ReportDocument` → `bytes`

Selbstenthaltendes HTML (UTF-8), Stil aus dem Altcode übernommen
(`export.py:183–194`, damit optisch keine Regression). Pflichtelemente:

- **R1 Statuskopf:** `draft`→„ENTWURF — nicht freigegeben"; `submitted`→„ZUR ABNAHME VORGELEGT";
  `approved`/`final`→Freigabevermerk mit Datum/Person.
- **Neun Blocktypen (B5):** `paragraph, header, list, table, quote, image, delimiter, marker,
  evidence`. Jeder Typ ein eigener kleiner Renderer (dict-Dispatch). Escaping über eine zentrale
  Funktion (Portierung von `export.py:_html_esc`, Z. 574).
- **R3 unbekannter Typ:** `⚠ Unbekannter Blocktyp 'xyz' — Inhalt nicht dargestellt` **+**
  `DocWarning('unknown_block_type')`. Kein stilles Überspringen.
- **Anker als Fußnoten** je Block (Muster `export.py:162–167`).
- **Abschnitt „Hinweise zur Erzeugung"** am Dokumentende (R2): Zeitpunkt, Status, Blockzahl,
  **vollständige Warnliste**, Zahl der Beweisanker.

---

## 6. Bilder (§4.2, mc: **Verweis statt Einbettung**)

`image`-Block ist Editor.js-`SimpleImage` (`report_editor.js:907`); `block_data.url` trägt die
Quelle. **Keine Bild-Bytes im Export** (Grund: §§184b/184c — die Akte darf nicht selbst Träger
inkriminierender Inhalte werden).

Stattdessen forensisch harter Verweis, aufgelöst gegen `assets_<uid>.db`:
`AssetsDb.get_asset(url)` (`db/assets_db.py:228`) liefert das Asset; der Renderer setzt
einen sichtbaren Kasten mit **Quell-`url` + `content_hash`** (und `share_id`, wo ableitbar) —
eindeutig re-lokalisierbar, ohne Reproduktion. Fehlt das Asset →
`DocWarning('missing_image')` + Platzhalter (R2).

*(Restpunkt: exakter Ort von `content_hash`/`share_id` in `assets`/`asset_urls` wird beim Bau
gegen das Schema verifiziert — Bauplan §4.2 „muss ich noch messen".)*

---

## 7. `export.py`-Umstellung (dünn)

Endpunkt-Vertrag **unverändert**: `GET /_forensic/export?format=html|docx|sqlite`
(`__init__.py:448`). `format` optional → **Default `html`** (mc). `handle_get` baut die vier
Verbindungen aus `self._bundle`, ruft `ReportSource` + `HtmlRenderer`, sendet Bytes.
DOCX/SQLite bleiben in 399 zunächst am Altpfad **oder** liefern sauber `501` bis Build 398 —
**abzunehmen** (§9). PDF: Build 400.

---

## 8. Testplan (kein `MagicMock` an der Schnittstelle — Bauplan §5)

- **Echte `EvidenceDb` auf `tempfile`** mit Fixture-Bericht (alle 9 Blocktypen, 1 ordnungsloser
  Block, 1 `image`, je 1 `{{a:}}/{{m:}}/{{o:}}`).
- **Reaktivierung** von T03/T04/T05/T07 (`tests/test_export.py`) gegen echten Pfad; T08
  („nur active/approved") **entfällt** — Status liegt jetzt am Bericht (B3), das ist zu vermerken,
  nicht still zu löschen (Grundregel 1).
- **Paritätstest (neu):** dieselben Eingaben durch `PlaceholderResolver` (Py) und eine
  Node-Ausführung von `placeholder_chips.js` (vitest) → identische Ausgabe. Abweichung = Fehler.
- **Warnlisten-Test:** ordnungsloser Block, fehlendes Bild, unbekannter Blocktyp, unauflösbares
  `{{a:}}` erscheinen **je** in der Warnliste.
- **Regression:** `python run_tests.py` grün in der VM vor Übergabe (Grundregel 9).

---

## 9. Punkte, die diese Feinabnahme **offen** an mc zurückgibt

1. **DOCX/SQLite in 399:** sauberer `501`-Zwischenstand bis 398 — **oder** Altpfad vorerst
   weiterlaufen lassen? (Empfehlung: `501` + Hinweis, damit nichts „grün aber tot" bleibt.)
2. **§4.1 Typ-Priorität:** bleibt es bei reiner `sequence_nr`-Maximierung (Empfehlung: ja)?
3. **Bild-Verweisfelder:** `content_hash` allein, oder zusätzlich `share_id`, wenn ableitbar?

## 10. Was Build 399 **nicht** tut
Kein PDF (400), kein neuer DOCX/SQLite-Renderer (398), **keine Schemaänderung**, keine
Änderung am Client/Editor. Der Server wird an den Client **angeglichen**, nicht umgekehrt.

---
*Dokument-Ende · Feinabnahme Build 399 v0.1 · 2026-07-13*
