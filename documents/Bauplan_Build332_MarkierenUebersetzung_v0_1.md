# Bauplan Build 332 — Markieren von Übersetzungen (Baustelle 3 + 6)

**Version:** v0.1 · Entwurf zur `mc`-Freigabe
**Basis:** `aiw_webserver` Build 331 (Übersetzungsanzeige + Schema-Korrektur)
**Betroffene Baustellen:** B3 (JS-Toolbar), B6 (Bericht) — **B5 unverändert**
**Migrationsstatus:** **KEINE** Änderung an `evidence_<uid>.db`-Schema (s. §3)

---

## 1. Zweck und Abgrenzung

### 1.1 Zweck
Ermittler:innen sollen Textstellen **innerhalb einer eingeblendeten Übersetzung**
(`.aiw-translation-body`, Build 329/331) markieren und als Annotation sichern
können — analog zum bestehenden Markieren im Originaltext, aber auf den
maschinell übersetzten Text bezogen.

### 1.2 Abgrenzung / Forensische Einordnung
Eine Übersetzung ist **maschinell erzeugt und nicht gerichtsverwertbar**
(Pflicht-Hinweis Build 329 §4.3). Eine Markierung darauf ist daher eine
**Ermittlungshilfe**, kein gerichtsfester Beleg. Der Bericht muss solche
Markierungen sichtbar als „auf maschineller Übersetzung beruhend" kennzeichnen
(§6, offene Frage 1).

### 1.3 Grundregeln
- **GR1:** Herkunft (post_id, source, Modell/Datum der Übersetzung) und die
  Nicht-Verwertbarkeit reisen mit der Markierung mit.
- **Migrationssicherheit:** additive Datenform, keine Schema-Änderung an einer
  vorbehaltsgebundenen DB (§3) — der zentrale Entwurfstreiber.

---

## 2. Kernentscheidung: Anker über Zeichen-Offsets statt XPath

Der Originaltext wird per XPath+Offset in `#forensic-viewport` verankert
(`toolbar.js` `_xpathOf`/`_nodeFromXpath`, `selection_json={xpathStart,
offsetStart,xpathEnd,offsetEnd}`). Für Übersetzungen ist das **ungeeignet**:

- Das Panel wird **dynamisch beim Klick** injiziert; sein XPath hängt von
  Injektionsreihenfolge/-zeitpunkt ab (nicht stabil).
- Der Übersetzungstext ist **deterministisch** aus `translations.db`
  (Schlüssel `post_id`+`source`) reproduzierbar.

**Daher:** Anker = **Zeichen-Offsets in `translated_text`**:
`{ target:"translation", source, charStart, charEnd }`. Gegeben post_id+source
liefert der Server denselben Text; die Markierung ist exakt reproduzierbar —
robuster und einfacher als XPath.

---

## 3. Speicherung — KEINE Evidence-Schemaänderung (belegt)

Wiederverwendung der bestehenden `annotations`-Tabelle (evidence_<uid>.db):

- `post_id` = Forum-post_id (Spalte existiert, Build 158+).
- `text`    = markierte Teilzeichenkette der Übersetzung (Bericht-Lesbarkeit).
- `selection_json` = **neue Variante** (frei-formiges JSON, kein Schemazwang):
  ```json
  { "target": "translation", "source": "posts",
    "charStart": 42, "charEnd": 78,
    "textLen": 1203, "textHash": "<sha256-hex-16>" }
  ```
- `category` = eine der bestehenden Highlight-Kategorien (Vorschlag: keine neue
  Kategorie nötig; Diskriminator ist `selection_json.target`) — siehe Frage 2.

**Belege für Migrationssicherheit:**
- `forensic_api/annotate.py:147–153` serialisiert `selection` generisch nach
  `selection_json` (beliebige JSON-Form) — die neue Variante passt ohne
  Code-/Schemazwang durch.
- `db/evidence_db.py` `add_annotation(..., selection_json, ..., post_id, ...)`
  nimmt `selection_json` frei entgegen; nur `category` wird gegen
  `VALID_CATEGORIES` geprüft (evidence_db.py:803).
- **Keine** neue Spalte, **kein** ALTER TABLE, **kein** Migrationsvorbehalt
  berührt. Bestehende Daten bleiben unverändert gültig.

Der bestehende `POST /_forensic/annotate` und der Restore-Pfad
(`loadAnnotations`) werden wiederverwendet — **kein neuer Endpoint**.

---

## 4. Re-Übersetzungs-Schutz (GR1)

`translated_text` kann sich später ändern (`updated_at`). Gespeicherte Offsets
zeigten dann evtl. auf verschobenen Text. Schutz:

- Beim Anlegen `textLen` + `textHash` (gekürzter SHA-256) des vollständigen
  `translated_text` mitspeichern (in `selection_json`).
- Beim Restore/Anzeigen: aktuellen Text laden, `textLen`/`textHash` vergleichen.
  Bei Abweichung wird die Markierung **nicht still verschoben**, sondern sichtbar
  als „Übersetzung wurde seit der Markierung geändert — Position ungeprüft"
  gekennzeichnet (kein stiller Fehlbeleg). Verankert dies mit der geparkten
  Re-Übersetzungs-Versionierung.

---

## 5. Toolbar (Baustelle 3)

Neues Teilverhalten im `TranslationModule` (oder Schwestermodul), IIFE,
`_dbg`-Logging, ausführlich kommentiert:

1. **Selektion** in `.aiw-translation-body` erkennen → `charStart/charEnd`
   relativ zum reinen Textinhalt des Panels berechnen (der Panel-Body ist reiner
   Text ohne Kind-Elemente → Offset-Berechnung trivial und stabil).
2. Kontext-Aktion („markieren") → `POST /_forensic/annotate` mit
   `selection={target,source,charStart,charEnd,textLen,textHash}`, `post_id`,
   `category`, `text`=Teilzeichenkette.
3. **Rendern:** markierten Bereich in `<mark class="aiw-tr-highlight aux-part">`
   hüllen → verschwindet im Original-Modus automatisch (aux-part, Build 329 §5).
4. **Restore:** beim Öffnen eines Panels die für `post_id` gespeicherten
   Annotationen mit `selection_json.target==="translation"` re-anwenden
   (Offsets), nach Text-Verifikation (§4).

**Debug-Protokoll (verbindlich):** browserbasiertes JS wird nach dem
etablierten Ablauf entwickelt — erst Console-Ausgabe für ausgabelastigen
Test-Code anfordern, dann Console-PoC (Offset-Berechnung + Restore), erst dann
der Roll-out-Fix. Zu jedem Debug-Schnipsel: wann/wo/wie auszuführen und was zu
beobachten ist.

---

## 6. Bericht (Baustelle 6)

Übersetzungsbasierte Annotationen (`selection_json.target=="translation"`)
werden im Bericht **gekennzeichnet** als „Fundstelle auf maschineller
Übersetzung (Modell/Datum) — nicht gerichtsverwertbar". Genaue Platzierung:
**offene Frage 1**.

---

## 7. Tests

- **JS (vitest):** reine Offset-Berechnung (Selektion → charStart/charEnd),
  Serialisierung der `selection_json`-Variante, Text-Verifikation (Hash/Len
  match/mismatch). Gegen echten Code (JSDOM-eval), kein Stub.
- **Python (pytest):** `annotate`-Endpoint akzeptiert die neue
  `selection_json`-Variante verlustfrei (Round-Trip in/aus evidence_db);
  Bericht-Renderer kennzeichnet target=="translation".
- Volle Regression `run_tests.py` grün.

---

## 8. Offene Fragen (Bestätigung nötig)

1. **Bericht-Darstellung:** Eigener Abschnitt „Hinweise aus Übersetzungen",
   Inline mit Warnbadge, oder Ausschluss aus der „verwertbar"-Beleg-Liste?
2. **Kategorie:** bestehende Highlight-Kategorien wiederverwenden (Diskriminator
   nur `selection_json.target`), oder eine dedizierte Kategorie
   „Übersetzungs-Fund" in `VALID_CATEGORIES` ergänzen?
3. **Re-Übersetzungs-Schutz (§4):** `textLen`+`textHash` mitspeichern und beim
   Restore verifizieren (Warnung bei Abweichung) — einverstanden?

---

## 9. Nicht in diesem Bauplan / Liefergegenstand

Nicht enthalten: Markieren in PM-Übersetzungen (folgt mit der PM-Anzeige);
Re-Übersetzungs-Versionshistorie (nur Erkennung/Warnung, keine Historie).

Liefergegenstand nach `mc`: `toolbar/toolbar.js` (+ ggf. `toolbar.css`),
Bericht-Renderer (B6), ggf. `VALID_CATEGORIES` (nur bei Frage 2 = dediziert),
Tests, `build.json`. Kein Endpoint, keine DB-Schemaänderung.
