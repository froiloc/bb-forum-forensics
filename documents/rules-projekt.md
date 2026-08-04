# Regelwerk AIW — Projekt

**Stand:** Build 662 · 2026-08-02 (Abschnitt 4 ergänzt; alles Übrige unverändert seit Build 607)

## 1. Die zehn Grundregeln

Sie stammen aus den Projektanweisungen und gelten für alles, was in diesem Projekt entsteht.

**GR1 — Kein Beleg darf ausgelassen werden. Kein Beleg darf je still übersprungen werden.**
Das ist die wichtigste Regel und zugleich die am häufigsten angewandte. Sie wirkt weit über die Beweisführung hinaus: Ein Leerbefund muss von einem Fehlerfall unterscheidbar sein. Eine Ausnahme muss benannt sein. Eine gekürzte Liste muss sagen, dass sie gekürzt ist. Ein Filter muss sagen, dass er greift.
*Durchsetzung:* an vielen Stellen einzeln — u. a. `test_cockpit_tabellen_ux.test.js` UX06 (Ausfall nennt die Anzahl), `test_help_cli_katalog.py` CK09 (jede Ausnahme trägt eine Begründung), die Fehllisten der Baustelle H.

**GR2 — Jede Versionsnummer muss ein lauffähiges, getestetes System sein.**
*Durchsetzung:* `python run_tests.py` vor jeder Übergabe.

**GR3 — Regressionstests sind Pflicht.**
*Durchsetzung:* `run_tests.py` fährt beide Suiten (pytest und vitest) und liefert eine gemeinsame Zusammenfassung.

**GR4 — Versionierung und Buildnummern sind Pflicht.**
Jede Datei trägt im Kopf ihre Version und Buildnummer.

**GR5 — Buildnummern sind mit jedem Durchgang zu iterieren.**
Übersprungene Nummern werden ausdrücklich vermerkt (Beispiel: 600 und 601, Festlegung mc 2026-07-31).

**GR6 — Gesicherte Erkenntnisse und Intentionen von Code sind zu kommentieren.**
Nicht *was* der Code tut, sondern *warum er so aussieht* — und was passiert ist, das zu dieser Form geführt hat. Ein Kommentar, der einen Befund festhält, verhindert, dass derselbe Fehler ein zweites Mal gemacht wird.

**GR7 — Änderungen sind als vollständige Datei zu übergeben.**

**GR8 — MD5-Prüfsummen für im Einsatz befindliche Dateien sind anzufordern.**
*Durchsetzung:* `tools/md5sums_build.sh` erzeugt die Liste, `tools/pruefe_auslieferung.py` prüft sie **von der Wurzel aus** — bei relativen Pfaden ist ein gleichmäßig verschobener Baum in sich stimmig, der Fehler ist nur von der Wurzel aus sichtbar (Befund 2026-07-31).

**GR9 — Nur fehlerfrei kompilierbarer Code darf übergeben werden.**
Jede geänderte `.py` mit `python -m py_compile`, jede geänderte `.js` mit `node --check`, und die vorhandenen Tests müssen in der VM laufen.
*Sinngemäß auf Dokumentation angewandt:* ein Beispielaufruf im CLI-Katalog wird vor der Aufnahme tatsächlich gefahren (siehe `rules-cli.md`).

**GR10 — Der Code soll so modular wie möglich sein. Jede Klasse gehört in eine eigene Datei.**

## 2. Die Fallregeln

**FR1 — Die Webseite ist UTF-8 kodiert.**

**FR2 — Das Forum ist multilingual.** Es sind unterschiedlichste Sprachen und Zeichensätze zu erwarten. Jede Textverarbeitung muss damit rechnen.

**FR3 — Inhalte und reale Bundles können nur nach Prüfung auf Unverfänglichkeit geteilt werden.**
*Durchsetzung:* `management/export/ausschleus_admin.py` weist ohne den ausdrücklichen Unbedenklichkeitsschalter ab (Default-Deny); `management/external/case_release_admin.py` verlangt die Unbedenklichkeits-Grundlage als Pflichtangabe.

## 3. Migrationsvorbehalt (seit 01.07.2026)

Seit dem Produktivbetrieb erzeugen Ermittelnde Daten. Daraus folgt:

- `evidence_<uid>.db`, `forensic_<uid>.db` und `assets_<uid>.db` sind **nicht ohne Migrationsvorbehalt** zu ändern. Jede Änderung muss bestehende Daten verlustfrei überführen.
- `coordinator.db`, `default.db` und `templates.db` werden von den Ermittelnden nur gelesen. Umsicht gilt auch hier, aber eine Änderung kann kein Wissen vernichten.
- Das genaue Vorgehen steht im `Datenmigrationsleitfaden AIW.md`. Er ist die maßgebliche Fassung; dieses Regelwerk verweist nur darauf.

**Praktische Folge für Werkzeuge:** Ein Werkzeug, das eine Beweismitteldatenbank schreibend anfasst, trägt im CLI-Katalog einen ausdrücklichen Hinweis.
*Durchsetzung:* `test_help_cli_katalog.py` CK05.

## 4. Zusammenarbeit

**Drei je Wortwechsel.** Fragen, Vorschläge und Anmerkungen sind auf drei je Wortwechsel beschränkt. Bestehen weitere, ist das anzumerken.

**Ehre, wem Ehre gebührt.** Niemand übernimmt Verantwortung für Fehler, die er nicht zu verantworten hat — und niemand nimmt Lorbeeren für Erfolge, die überwiegend ein anderer verantwortet.

**Vier Augen bei Texten.** Was Anwender zu lesen bekommen, verfasst der eine und nimmt der andere ab. Maschinelle Prüfungen fangen Muster; sie ersetzen die Lesung nicht (siehe `rules-help.md`).

**Übergabe von Arbeitsergebnissen.** Seit dem 3. August 2026 (`aiw_webserver` 0.8.661, `aiw_sqlite_prepper` 0.1.129) wird als Git-Bundle übergeben, nicht mehr als ZIP-Archiv mit Dateien. Anlass war ein gemessener Befund: ein über den Bestand entpacktes ZIP löscht eine parallel entstandene Änderung still — ein GR1-Verstoß auf der Ebene des Arbeitsweges. Das Verfahren steht in `data-exchange.md`; dieses Regelwerk verweist nur darauf. Werkzeuge dazu: `tools/bundle_bauen.sh` und `tools/bundle_einspielen.sh` (Build 662). Auf `master` wird seither nicht mehr gearbeitet — eigene Arbeit läuft auf `alex/<thema>`.

## 5. Belegpflicht in der Argumentation

Keine Behauptung ohne Beleg. Wo eine Aussage aus dem Bestand stammt, gehört die Fundstelle dazu (Datei und Zeile). Wo sie eine Schlussfolgerung ist, gehört das Wort „Schlussfolgerung" dazu. Wo etwas unklar ist, gehört das Wort „unklar" dazu — und nicht die plausibelste Vermutung im Ton einer Feststellung.
