# Bauplan Build 333 — Markieren von Übersetzungen (Baustelle 3 + 6)

**Version:** v0.2 · **Entscheidungen eingearbeitet, `mc` erteilt (2026-07-07)**
**Ersetzt:** Bauplan_Build332_MarkierenUebersetzung_v0_1 (Umnummerierung: der
UX-Fix wurde Build 332, das Markieren wird Build 333).
**Basis:** `aiw_webserver` Build 332
**Betroffene Baustellen:** B3 (JS-Toolbar), B6 (Bericht) — **B5 unverändert**
**Migrationsstatus:** **KEINE** Änderung am `evidence_<uid>.db`-Schema (§3)

---

## 1. Zweck
Ermittler:innen markieren Textstellen **innerhalb einer eingeblendeten
Übersetzung** (`.aiw-translation-body`) und sichern sie als Annotation —
analog zum Markieren im Originaltext, aber offset-verankert auf den maschinell
übersetzten Text. Eine solche Markierung ist eine **Ermittlungshilfe**, kein
gerichtsfester Beleg (§6).

---

## 2. Anker: Zeichen-Offsets statt XPath (unverändert ggü. v0.1)
Der Panel-Text ist deterministisch aus `translations.db` reproduzierbar
(`post_id`+`source`); das Panel-DOM ist dynamisch injiziert. Anker daher über
**Zeichen-Offsets im `translated_text`** — robuster und einfacher als XPath.

Offset-Bildung (belegbar korrekt, auch bei bereits vorhandenen `<mark>`-Kindern):
`range.selectNodeContents(bodyEl); range.setEnd(node, offset);
range.toString().length` liefert den Zeichen-Offset. Restore per Text-Knoten-
Durchlauf (`TreeWalker`, SHOW_TEXT) und `Range` über [charStart, charEnd).

---

## 3. Speicherung — KEINE Evidence-Schemaänderung (belegt)
Wiederverwendung der bestehenden `annotations`-Tabelle:

- `post_id` = Forum-post_id (Spalte existiert, Build 158+).
- `text`    = markierte Teilzeichenkette (Bericht-Lesbarkeit).
- **`category` = `Übersetzungsfund`** — neue, dedizierte Kategorie
  (Entscheidung 2; klarer als Wiederverwendung, offen für spätere Fundarten).
  Erfordert **einen Konstanten-Eintrag** in `VALID_CATEGORIES`
  (`db/evidence_db.py` / `forensic_api/annotate.py`) — **kein** Schema-Change.
- **`selection_json`** = neue Variante (frei-formiges JSON, kein Schemazwang):
  ```json
  { "target": "translation", "source": "posts",
    "charStart": 42, "charEnd": 78,
    "textLen": 1203, "textHash": "<hash-hex>" }
  ```

**Belege Migrationssicherheit:** `annotate.py:147–153` serialisiert `selection`
generisch nach `selection_json`; `evidence_db.add_annotation(...)` nimmt
`selection_json` frei entgegen; nur `category` wird gegen `VALID_CATEGORIES`
geprüft. Bestehender `POST /_forensic/annotate` + Restore-Pfad
(`loadAnnotations`) werden wiederverwendet — **kein neuer Endpoint, kein
ALTER TABLE, kein Migrationsvorbehalt berührt.**

---

## 4. Re-Übersetzungs-Schutz (Entscheidung 3)
Gespeichert werden `post_id` (ID der Fundstelle), `textHash`, `textLen`,
`charStart`, `charEnd`. Beim Restore/Anzeigen:
- aktuellen `translated_text` laden, `textLen` **und** `textHash` vergleichen;
- bei Abweichung wird die Markierung **nicht still verschoben**, sondern sichtbar
  gewarnt: „Übersetzung wurde seit der Markierung geändert - Position ungeprüft"
  (kein stiller Fehlbeleg, GR1). Verifikation ist Pflicht, Warnung Minimum.

Hash-Verfahren: einfacher, schneller Textinhalts-Hash (Erkennung von
Inhaltsänderung genügt; keine kryptografische Manipulationssicherheit nötig).
Genaues Verfahren wird nach der Console-Verifikation festgelegt.

---

## 5. Entwicklung: console-first (verbindlich)
Browserbasiertes JS wird nach dem etablierten Ablauf entwickelt:
1. **Ausgabelastiger Console-Test/PoC** (Offset-Erfassung aus Live-Selektion +
   Hash/Len-Erfassung + Restore aus Offsets) — mit Anweisung wann/wo/wie
   auszuführen und was zu beobachten ist. Alex liefert die Console-Ausgabe.
2. Erst nach bestätigter Ausgabe der **Roll-out** (TranslationModule-Erweiterung
   + `Übersetzungsfund`-Kategorie + Bericht-Beisatz + Tests).

Trigger im Roll-out: Selektion in `.aiw-translation-body` → Aktion „als
Übersetzungsfund markieren" → `POST /_forensic/annotate`. Rendern als
`<mark class="aiw-uebersetzungsfund aux-part">` (verschwindet im Original-Modus).
Restore beim Öffnen eines Panels (Offsets, nach Text-Verifikation §4).

---

## 6. Bericht (Baustelle 6) — Warnbadge + Rechts-Beisatz (Entscheidung 1)
Findet der Bericht Annotationen der Kategorie `Übersetzungsfund` bzw.
`selection_json.target=="translation"`, wird ein Warnbadge samt folgendem
Beisatz ausgegeben (Wortlaut von Alex):

> Die beigefügte Übersetzung wurde maschinell erstellt und dient ausschließlich
> der ersten internen Erschließung des fremdsprachigen Dokuments. Sie stellt
> keine verbindliche Übersetzung im Sinne des § 187 GVG dar. Für eine spätere
> Verwertung als Beweismittel ist eine beglaubigte Übersetzung durch einen
> vereidigten Gerichtsdolmetscher einzuholen. Die maschinelle Übersetzung wird
> der Akte lediglich zu Informationszwecken beigefügt.

---

## 7. Tests
- **JS (vitest):** reine Offset-Berechnung (Selektion → charStart/charEnd),
  Serialisierung der `selection_json`-Variante, Hash/Len-Verifikation
  (match/mismatch → Warnung). Gegen echten Code, kein Stub.
- **Python (pytest):** `annotate` akzeptiert die Variante verlustfrei
  (Round-Trip evidence_db); `Übersetzungsfund` in `VALID_CATEGORIES`;
  Bericht-Renderer gibt den Beisatz genau bei Übersetzungsfunden aus.
- Volle Regression `run_tests.py` grün.

---

## 8. Entscheidungen (erledigt)
1. **Bericht:** Warnbadge + Rechts-Beisatz (§ 187 GVG) — Wortlaut §6. ✔
2. **Kategorie:** dedizierte Kategorie `Übersetzungsfund`. ✔
3. **Re-Übersetzungs-Schutz:** post_id + textHash + textLen + charStart +
   charEnd, Pflicht-Verifikation, Warnung bei Abweichung. ✔

---

## 9. Nicht enthalten
Markieren in PM-Übersetzungen (folgt mit der PM-Anzeige);
Re-Übersetzungs-Versionshistorie (nur Erkennung/Warnung).

Liefergegenstand nach Console-Verifikation (Build 333): `toolbar/toolbar.js`
(+ ggf. `toolbar.css`), `VALID_CATEGORIES`-Eintrag, Bericht-Renderer (B6),
Tests, `build.json`. Kein Endpoint, keine DB-Schemaänderung.
