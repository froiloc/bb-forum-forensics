# Bauplan AP-3E — Fallübergreifende Volltextsuche (Builds 560–563)

**Version:** 0.4 · **Datum:** 2026-07-26 · **Autor-Entwurf:** Claude (Instanz B), zur mc-Freigabe
**Fortschreibung:** §7 (Nachtrag zu 561) · §8 (Nachtrag zu 562/563 — AP-3E abgeschlossen)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Basis-Commit:** `39ec029` (v0.8.540) — vierter und letzter Aufsatzpunkt
**Grundlagen:** `management/Klaerung_AP3E_Freigabemodell_Volltextsuche_v0_2.md` ·
`management/Entscheidungen_2026-07-26_AP3B_AP3C_AP3E.md` §1 ·
`management/Parallelbetrieb_Welle_3_Aufgabenteilung_und_Vereinigung.md` §11

---

## 1. Was gebaut wird, und was ausdrücklich nicht

Die Suche beantwortet **eine** Frage: *„Ist dieser Begriff — meist ein Nickname —
schon irgendwo in der Dienststelle aufgefallen?"* Sie durchsucht dazu alle
`evidence_<uid>.db` und nennt Fall, Trefferzahl, Art und Zeitraum.

**Sie durchsucht keinen Forumsinhalt.** Der wichtigste Befund der Vorrecherche
(Klärung §2): In `evidence_<uid>.db` steht **kein** Forumstext. Die Originalseiten
liegen als HTML-BLOB in `forensic_<uid>.db` (`db/forensic_db.py:88-111`), der
gereinigte Beitragstext und die Übersetzungen in `translations.db`
(`db/translations_db.py:294-305`, `:246-253`). Durchsucht wird ausschließlich
**von Ermittler:innen geschriebener Text**.

Das verschiebt die Risikofrage: Es geht nicht um Missbrauchsmaterial, sondern um
die **Zweckbindung zwischen Ermittler:innen** — wer den Arbeitsstand *fremder*
Fälle im Volltext lesen darf. Eine Suche über Forumsinhalt wäre eine deutlich
schärfere Frage und ist **nicht Teil dieses Arbeitspakets** (Klärung §7,
Schlussabsatz).

---

## 2. Die Festlegungen, auf denen dieser Bauplan steht

| Nr. | Festlegung | Quelle |
| --- | ---------- | ------ |
| E-1 | **Modell B, zweistufig.** Stufe 1 = Trefferlage ohne Textausschnitt, frei für alle Berechtigten. Stufe 2 = Inhalt sofort bei **eigenen** Fällen, sonst gesperrt mit begründungspflichtiger Anfrage an die Chef-Ermittlerin. | Entscheidungen §1 E-1 |
| E-2 | **`evidence.fulltext_search` nicht scope-fähig**, default-deny, Grant zunächst nur `supervisor`. `searchagent` bleibt ohne Grant. | Entscheidungen §1 E-2 |
| E-3 | **Zweckangabe bei jeder Abfrage**, als Auswahlliste fester Codes; bei `sonstiges` Freitext-Pflicht. | Entscheidungen §1 E-3 |
| E-4 | **Eine Freigabe je Fall + Person**, nicht je Abfrage (`fulltext_release` in `coordinator.db`). | Entscheidungen §1 E-1 |
| E-5 | **Jede Abfrage ist ein Beleg** — `FULLTEXT_SEARCHED`, **auch der Leerbefund**. | Klärung §6 Nr. 1 |
| E-6 | **Rein lesend** (`mode=ro`), Migrationsvorbehalt nicht berührt. | Klärung §6 Nr. 2 |
| E-7 | **Index außerhalb der Beweismittel**, verwerfbar, **Hilfsmittel kein Beweismittel**; jeder Treffer wird vor der Anzeige gegen die Quelle verifiziert. | Klärung §6 Nr. 3 |
| E-8 | **Kein stiller Teiltreffer**; jede Antwort nennt den Indexzeitpunkt und die Zahl der seither veränderten Datenbanken. | Klärung §6 Nr. 4/5 |

**Neu entschieden am 2026-07-26 (mc, auf drei Fragen von Instanz B):**

| Nr. | Festlegung | Begründung in Kurzform |
| --- | ---------- | ---------------------- |
| E-9 | **Indexpflege: nur ausdrücklich, inkrementell.** Die Abfrage indiziert nie. Aufgefrischt wird über CLI bzw. Knopf; gelesen werden nur Datenbanken mit verändertem Fingerabdruck. | Vorhersehbare Abfragelatenz auf dem Netzlaufwerk (Faktor ~24), und die Antwort behält einen **benennbaren** Indexzeitpunkt. |
| E-10 | **Zwei Indizes, Modus wählbar:** `unicode61 remove_diacritics 2` (Wort, Standard) und `trigram` (Teilstring). | Eine reine Wortsuche fände `birnenmus` nicht in `xXbirnenmusXx` und schwiege darüber (Grundregel 1). Der Preis ist Plattenplatz in einem Hilfsmittel. |
| E-11 | **Überholte und zurückgenommene Fassungen werden mitindiziert**, in Stufe 1 getrennt ausgewiesen. | Der verworfene Befund ist für den Kreuzbezug wertvoll; ihn wegzulassen wäre eine unmarkierte Auslassung. |

---

## 3. Build-Schnitt

Der Schnitt aus dem Parallelbetriebs-Dokument §11 wird **unverändert
übernommen**. Er beginnt bewusst mit dem Teil, der **keine einzige gemeinsame
Datei** berührt — im Parallelbetrieb ist das die kleinstmögliche Angriffsfläche
für eine lautlose Überschreibung.

| Build | Inhalt | Berührt aus §4 (gemeinsame Dateien) |
| ----- | ------ | ----------------------------------- |
| **560** | Indexaufbau: `search_index.db`, Quellenleser, Indexbauer, Status, CLI | nur `build.json` |
| **561** | Migration `fulltext_release` + Zweckcode-Katalog + Recht `fulltext.release` + `EventType FULLTEXT_SEARCHED` | `build.json`, `rbac/catalog.py` (anhängen), `audit/event_types.py` (anhängen), `migrations/coordinator/m040*` (neu), Datenmigrationsleitfaden |
| **562** | Endpunkte Stufe 1 / Stufe 2, Freigabe-Schreibpfad, Trefferverifikation gegen die Quelle | `build.json`, `management_app.py` (nur Routen, am Ende) |
| **563** | Sicht `cockpit_search.js` | `build.json`, `cockpit.js` (ein `VIEW_CATALOG`-Eintrag ans Ende), `cockpit.css` (nur ans Dateiende) |

**Nummernkreise (Parallelbetrieb §5):** Builds **560–579**, coordinator-Migrationen
**m040–m049**, evidence-Migrationen **m006–m007**. Evidence-Migrationen sind für
AP-3E **nicht vorgesehen** — die Beweismitteldatenbanken werden ausschließlich
gelesen.

---

## 4. Build 560 — der Suchindex (gebaut)

### 4.1 Neue Dateien

```
db/search_index_db.py                        SearchIndexDb (Schema + Schreibpfad)
management/search/__init__.py
management/search/index_vokabular.py         was indiziert wird, Fassungen, Befunde, Tokenizer
management/search/satz.py                    Satz (ein Textfund samt Rückweg zur Quelle)
management/search/block_text.py              Klartext aus Editor.js-/JSON-Spalten
management/search/evidence_source_reader.py  liest EINE evidence_<uid>.db (read-only)
management/search/index_status.py            SearchIndexStatus (rein lesend)
management/search/index_builder.py           SearchIndexBuilder (Lauf + Bericht)
management/search/index_cli.py               Befehlszeile
tests/test_management_search_index.py        SI01–SI23 (25 Tests)
```

### 4.2 Schema von `search_index.db`

```
index_meta    (schluessel, wert)                     Schemaversion, Tokenizer, Laufzeitpunkte
index_quelle  (subject_id, db_pfad, fingerprint,     je Quelldatenbank: Stand + Befund
               indiziert_at, satz_zahl,
               gekuerzt_zahl, befund, befund_detail)
index_satz    (satz_id, subject_id, satz_art,        ein Textfund samt Rückweg zur Quelle
               quell_tabelle, quell_spalte,
               quell_schluessel, fassung, ts,
               urheber, text)
index_wort    FTS5 external content, unicode61 remove_diacritics 2
index_teil    FTS5 external content, trigram
```

Drei Trigger halten die beiden FTS-Tabellen synchron (`INSERT`, `DELETE`) und
**verbieten `UPDATE`** auf `index_satz` — der Bauer ersetzt einen Fall immer
vollständig. Ein UPDATE-Trigger wäre ein Mechanismus, den niemand benutzt und den
deshalb auch kein Test abdeckt; die Sperre macht daraus einen harten Fehler
statt eines stillen Indexdrifts.

### 4.3 Was indiziert wird

Die acht Fundstellen aus Klärung §2, zuzüglich `annotations.category` als
**eigene** Satzart (es ist ein Code, kein Freitext, und muss in der Sicht
getrennt behandelbar bleiben):

`annotation_text` · `annotation_kategorie` · `annotation_schlagworte` ·
`bericht_titel` · `berichtsbaustein` · `platzhalterwert` · `berichtsanker` ·
`gegenlesen_kommentar` · `gegenlesen_vorschlag` · `freigabevermerk` ·
`ermittler_alias`

**SI02 hält diese Liste gegen das echte `evidence`-Schema.** Ein Tippfehler in
einem Spaltennamen indizierte sonst nichts und sähe aus wie „nichts erfasst".

### 4.4 Fassungen

`annotations` ist append-only: eine Bearbeitung legt einen neuen Datensatz an
(`version_nr+1`, `prev_id = alte.id`) und stempelt die alte mit `deleted_at`
(`db/evidence_db.py:868-874`). **`deleted_at` heißt dort „geändert", nicht
„gelöscht".**

| Zustand | Bestimmung |
| ------- | ---------- |
| `aktuell` | `deleted_at IS NULL` |
| `ueberholt` | `deleted_at` gesetzt **und** ein anderer Datensatz zeigt mit `prev_id` hierher |
| `zurueckgenommen` | `deleted_at` gesetzt, **kein** Nachfolger |

Über `local_id` ginge es nicht: sie ist optional („anonyme Einmal-Annotation",
`db/evidence_db.py:871`), eine gelöschte anonyme Annotation wäre nicht
einzuordnen. Für `report_comments` gilt `status='revoked'` → `zurueckgenommen`;
`dismissed` ausdrücklich **nicht** — ein abgelehnter Kommentar ist geäußert
worden und bleibt Arbeitsstand.

### 4.5 Fünf Befunde je Quelldatenbank

`gelesen` · `nicht_oeffenbar` · `nicht_lesbar` · `ohne_tabelle` · `fehlt`

`ohne_tabelle` trägt den Klartext **„Es ist NICHT gesagt, dass nichts erfasst
wurde"** — dieselbe Trennschärfe wie `nicht_geprueft`/`ohne_feststellung` im
Fristenmonitor (Build 535, TA16). Ein Fehler bei **einem** Fall beendet den Lauf
nicht; ein fehlendes `evidence`-Verzeichnis leert den Index nicht; ein einmal
unvollständiger Fall wird beim nächsten Lauf erneut versucht.

### 4.6 Bedienung

```
python -m management.search.index_cli --status
python -m management.search.index_cli --auffrischen
python -m management.search.index_cli --auffrischen --voll
python -m management.search.index_cli --auffrischen --nur 4711,5023
python -m management.search.index_cli --status --json
```

Exit-Codes: `0` sauber · `1` Aufruf-/Konfigurationsfehler · `2` gelaufen, **aber
unvollständig**. Der eigene Code 2 ist Absicht: „gelaufen, aber nicht
vollständig" darf im Betriebsskript nicht wie „gelaufen" aussehen.

---

## 5. Builds 561–563 — der Entwurf (noch nicht gebaut)

### 5.1 Build 561 — Datenmodell der Freigabe

* **Migration `m040_fulltext_release.py`** (coordinator, additiv):
  `fulltext_release (id, subject_id, person_id, zweck_code, zweck_freitext,
  erteilt_von, erteilt_at, widerrufen_von, widerrufen_at, begruendung)`.
  **Eine Freigabe je Fall + Person** (E-4) — Eindeutigkeit über
  `(subject_id, person_id)` unter den nicht widerrufenen Zeilen.
* **Zweckcode-Katalog** als Vokabularmodul, Grundmenge zur Bestätigung:
  `kreuzbezug_nickname`, `alias_pruefung`, `wiedervorlage`, `sonstiges`
  (Freitext-Pflicht). Ablageform `sonstiges:<Freitext>` — dieselbe Konvention wie
  `db/tatzeit_vokabular.py`, weil kein Code einen Doppelpunkt enthält.
* **Neues Recht `fulltext.release`** (erteilen/widerrufen), an `supervisor`.
  *Nicht* `release.grant` mitbenutzen: das ist die **externe** Fallfreigabe
  (Build 462) und damit eine andere Zweckbindung — eine Wiederverwendung wäre
  kein Sparen, sondern ein Zweckbindungsverstoß (dieselbe Abgrenzung wie bei
  `tatzeit.edit` gegenüber `results.edit`).
* **EventTypes** `FULLTEXT_SEARCHED`, `FULLTEXT_RELEASE_GRANTED`,
  `FULLTEXT_RELEASE_REVOKED` — angehängt, zusätzlich am Ende von `ALL`.
* **ANKERDELTA** dann: +1 Capability (40 → 41), coordinator-Kette bis m040.

### 5.2 Build 562 — Endpunkte

* **Stufe 1** `GET /api/fulltext/lage` — Fall, Trefferzahl **je Fassung**, Arten,
  Zeitraum, **ohne Textausschnitt**. Zweckcode ist Pflichtparameter.
* **Stufe 2** `GET /api/fulltext/inhalt` — Textausschnitt. Zulässig, wenn der
  Fall dem Suchenden **zugewiesen** ist oder eine gültige `fulltext_release`
  vorliegt; sonst **403 mit Begründung** (Blaupause
  `forensic_api/results_endpoint.py`).
* **Trefferverifikation gegen die Quelle vor jeder Anzeige** (E-7). Weicht die
  Quelle ab, wird der Treffer als *„Index veraltet — Quelle abweichend"*
  ausgewiesen und **nicht** aus dem Index zitiert.
* **Jede Antwort nennt**: Indexzeitpunkt, Zahl der seither veränderten
  Datenbanken, Zahl und Namen der unvollständigen Fälle (E-8).
* **Jede Abfrage schreibt `FULLTEXT_SEARCHED`, auch der Leerbefund** (E-5), über
  `CoordinatorWriter.audited_write`.
* **Teilstring-Mindestlänge 3** wird im Klartext gemeldet, statt still leer zu
  antworten.

### 5.3 Build 563 — Sicht `cockpit_search.js`

Suchfeld, Moduswahl (Wort/Teilstring), Zweckcode-Auswahlliste, Trefferlage nach
Fall mit getrennter Zählung `aktuell` / `überholt` / `zurückgenommen`,
Aufklappbereich für Stufe 2 bzw. den Freigabeantrag, Kopfzeile mit
Indexzeitpunkt und Auffrischknopf, **Kennzahl „Anteil `sonstiges`"** (E-3: steigt
sie, fehlt ein Code).

---

## 6. Offene Punkte (3)

1. **SQLite-Fassung der VM ist noch nicht bekannt.** Der `trigram`-Tokenizer
   braucht mindestens 3.34 (Container: 3.45.1). Fehlt er, bricht `SearchIndexDb`
   **hart** ab — ein Rückfall auf `LIKE` ist ausgeschlossen, weil er nur einen
   Teil fände und darüber schwiege. Die Fassung ist vor dem Rollout von 560 zu
   melden.
2. **Die Zweckcode-Grundmenge ist ein Vorschlag** (E-3 nennt sie „zur
   Bestätigung"). Sie wird mit Build 561 verbindlich; danach ist eine Ergänzung
   billig, eine Umbenennung nicht.
3. **Der erste Indexlauf ist ungemessen.** Dauer und Größe der entstehenden
   `search_index.db` auf dem Netzlaufwerk sind die Eingangsgröße für die
   Lastabschätzung von Build 562. Ohne diese Zahl ist jede Aussage über die
   Antwortzeit der Suche eine Schätzung — und Schätzungen gehören in diesem
   Projekt nicht in eine Akte.

---

---

## 7. Nachtrag nach dem Bau von Build 561

Zwei Punkte aus §5.1 haben sich beim Bauen als überholt erwiesen. Sie werden hier
benannt statt oben stillschweigend überschrieben — der Entwurf soll nachlesbar
bleiben, auch wo er falsch lag.

### 7.1 Der Zweck steht in ZWEI Spalten, nicht in einer

§5.1 sah die Ablageform `sonstiges:<Freitext>` in einem Feld vor, nach dem
Vorbild von `db/tatzeit_vokabular.py`. **Das war für diesen Fall falsch.**

Bei der Tatzeit lag die Spalte in einer Beweismitteldatenbank **unter
Migrationsvorbehalt**; eine zweite Spalte wäre dort ein Umbau an einer Datei mit
Ermittlerdaten gewesen — für eine reine Formatfrage. Hier entsteht eine **neue**
Tabelle in `coordinator.db`, ohne Vorbehalt und ohne Bestand. Damit fällt der
Grund weg, auf referentielle Integrität zu verzichten:

```
zweck_code      TEXT NOT NULL REFERENCES fulltext_zweck(code)
zweck_freitext  TEXT            -- NULL, außer bei 'sonstiges'
```

Der Fremdschlüssel ist der eigentliche Gewinn — ein Tippfehler im Code wird von
der **Datenbank** abgelehnt, nicht erst von der Anwendung. Genau dafür gibt es
die Katalogtabelle. Ein `CHECK` erzwingt zusätzlich: Freitext **genau dann**,
wenn der Code ihn verlangt. Beides ist wirkungsgeprüft (FR04, FR05 — je gegen
einen Schreibvorgang, der bewusst am Repository vorbeigeht).

### 7.2 Der Schreibpfad ist Teil von 561, nicht von 562

§3 wies den „Freigabe-Schreibpfad" Build 562 zu. Er ist stattdessen in 561
gebaut (`management/search/release_repo.py`), damit 561 ein **lauffähiges,
getestetes System** ist (Grundregel 2) und nicht eine Tabelle, die niemand
beschreibt. 562 behält die Endpunkte, die Trefferverifikation gegen die Quelle
und den Beleg `FULLTEXT_SEARCHED`.

### 7.3 Neu hinzugekommen: die Migrationsreihenfolge

Beim Bau von M040 ist ein Befund aufgefallen, der in v0.1 nicht vorkommen
konnte: der `MigrationRunner` führt einen **Höchststand** statt einer Menge, und
die getrennten Nummernkreise aus Parallelbetrieb §5 erzeugen damit genau den
stillen Datenfehler, den sie verhindern sollten. Vollständig in
`management/Vermerk_Migrationsluecke_Parallelbetrieb_v0_1.md`; mc hat am
2026-07-26 die **strikte Serialisierung** der Migrationen entschieden.

Folgen für diesen Bauplan:

* **M040 trägt einen Sperrvermerk** und darf erst nach den Migrationen von
  Instanz A eingespielt werden. Die Nummer ist bis dahin **vorläufig**.
* Neues Betriebswerkzeug `tools/pruefe_migrationskette.py` — es macht eine
  Lücke sichtbar, statt sich darauf zu verlassen, dass keine entsteht.
* Der Datenmigrationsleitfaden hat dazu **Abschnitt 15** bekommen (v0.5).

---

---

## 8. Nachtrag nach den Builds 562 und 563 — AP-3E ist vollständig

### 8.1 Was gebaut wurde

| Build | Inhalt | Neue Dateien |
| ----- | ------ | ------------ |
| **562** | Endpunkte beider Stufen, Verifikation gegen die Quelle, Beleg | `management/search/quellen_verifikation.py`, `search_repo.py`, `search_service.py` |
| **563** | Sicht | `management/server/static/cockpit_search.js` |

### 8.2 Die Suche ist ein POST, kein GET — Abweichung von §5.2

§5.2 sah `GET /api/fulltext/lage` vor. Umgesetzt ist ein **POST**. Zwei Gründe:

* **Jede Abfrage ist ein Beleg**, auch der Leerbefund (E-5). Ein GET, der
  belegt, erzeugte bei jedem Seitenwechsel und jedem Neuladen einen weiteren
  Eintrag — die Protokollspalte wäre binnen Tagen unbrauchbar und der einzelne
  Beleg wertlos.
* Die **Pflicht-Zweckangabe** (E-3) gehört in einen Rumpf, nicht in eine URL.

Konsequent dazu sucht die Sicht **beim Öffnen nicht** und beim SSE-Reload
**nicht**: ein automatischer Lauf erzeugte einen Beleg ohne menschliche
Handlung.

### 8.3 Eine Abweisung in Stufe 2 ist ein 200, kein 403

Wer das Suchrecht nicht hat, bekommt 403. Wer es hat, aber den Fall nicht
sehen darf, bekommt **200 mit `erlaubt: false`** samt Grund und dem Weg zur
Freigabe. Die Abweisung ist ein **Ermittlungsergebnis** („zu diesem Fall gibt
es etwas, Sie dürfen es nur nicht sehen"), kein Berechtigungsfehler. Ein 403
sagte „Sie haben hier nichts verloren" — sachlich falsch, und es hielte die
Ermittlerin von dem Schritt ab, den das Modell gerade vorsieht.

### 8.4 Der Suchbegriff steht im Beleg — bewusste Ausnahme

Klärung §6 Nr. 1 zählt ihn ausdrücklich auf. Er ist damit die einzige
Ausnahme von der Sensibilitätsregel (sonst nur Fakten und Textlängen). Ohne
ihn belegte der Eintrag nichts: „jemand hat nach etwas gesucht" beantwortet
keine Aufsichtsfrage. **Der Preis ist benannt**, nicht verschwiegen — ein
Suchbegriff kann ein Klarname sein, und damit steht ein Klarname im
`audit_log`. Der **Freitext** einer `sonstiges`-Zweckangabe ist von der
Ausnahme **nicht** gedeckt und geht nur als Länge ein.

### 8.5 Die Suche ist vom Akten-Export ausgenommen

Zwei bestehende Anker (`tests/test_view_export_api.py` VE08 und
`tests/unit/test_cockpit_export_button.test.js` EX01) haben die neue Sicht
gefunden und einen Export verlangt. Sie ist stattdessen **ausdrücklich
ausgenommen** worden, mit drei Gründen (ausführlich in
`view_export_catalog.py`) — der dritte allein wäre zwingend: **ein generischer
Export umginge die Stufe-2-Sperre** und stellte fremden Arbeitsstand in ein
Dokument, das anschließend in einer Akte liegt.

### 8.6 Offen bleibt

* Die **SQLite-Fassung der VM** (trigram ≥ 3.34) — Build 560 startet sonst nicht.
* Die **Laufzeit des ersten Indexlaufs** auf dem Netzlaufwerk.
* Die **Bestätigung der Zweckcode-Grundmenge**.
* Der **Sperrvermerk auf M040** (Migrationsreihenfolge, §7.3).

---

*Dokument-Ende · Bauplan AP-3E · v0.4 · 2026-07-26 · Instanz B · zur mc-Freigabe*
