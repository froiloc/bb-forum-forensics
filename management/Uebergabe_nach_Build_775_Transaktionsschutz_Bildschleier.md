# Uebergabe nach Build 775 — Transaktionsschutz (774) und Bildschleier-Korrekturen (775)

Stand: 14.10.2026 · Basis: Build 773 (`origin/master` = `2e9ad16`) · Zweig `claude/build774`

## 1. Anlass (Befund 13./14.10.2026, PROD)

Nach dem Einspielen der Builds 771–773 und der Migration 37→40 meldete das
Umschalten des Bildschleiers in PROD
„Umschalten fehlgeschlagen: database is locked“; zusaetzlich waren Abzeichen
und Smileys verschleiert.

Gemessene Ursachenkette:

1. `evidence_2948078.db` war beschaedigt (Integritaetssonde; Schaden in
   `viewport_events`, `page_visits`, `lock_queue`, `lock_takeover_requests`).
2. `EvidenceDb.save_viewport_batch` scheiterte mit
   „database disk image is malformed“ und rief kein `rollback()` auf. Im
   Legacy-Transaktionsmodus ist das implizite BEGIN dann gelaufen; die
   Transaktion der geteilten Verbindung blieb offen.
3. Die naechste Lesung auf `cdb` (coordinator.db) hielt in dieser offenen
   Transaktion eine SHARED-Sperre.
4. Der Bildschleier-Schreiber (eigene Verbindung, `CoordinatorWriter`,
   BEGIN IMMEDIATE) bekam nach 5 s „database is locked“.
5. Dazu zwei Fehler im Bildschleier selbst: D1 (Ausnahmen fehlten beim
   Einschalten auf klarer Seite) und D2 (nach gescheitertem Einschalten kein
   Rueckweg ausser F5).

Die Datei wurde am 14.10.2026 mit `evidence_reparatur.py` 1.2 (ausserhalb der
Buildkette, MD5 `5c8d1106291c6cd7b91daa43642363ad`) neu aufgebaut: freigegeben,
alle Tabellen mit Ermittlungsergebnissen fehlerfrei und unveraendert
uebernommen. Seitdem schaltet der Schleier in PROD in beide Richtungen
(Rueckmeldung Alex, 14.10.2026).

## 2. Build 774 — Transaktionsschutz

- `db/schreibvorgang.py` (neu, Klasse `Schreibvorgang`): Lock der
  LockingConnection fuer die ganze Dauer, `rollback()` bei jeder Ausnahme.
  Vorbild `EvidenceWriter.transaction()`.
- Eingewickelt: `evidence_db` 42, `coordinator_db` 3, `forensic_db` 1,
  `cross_annotation_integrator` 1, `events._send_lock_status` (nur die
  Bereinigung — `send_fn` schreibt auf den SSE-Socket).
  Nachweis „nur die Huelle“: AST alt/neu nach Entfernen der Huellen gleich.
- `rollback()` in den verschluckenden Behandlern von `save_alias`,
  `acquire_lock` (Normalfall bei Konkurrenz um den Berichtseditor!) und
  `_migrate_schema`.
- `LockingConnection`: Transaktions-Besitzer; `sicherheitsnetz()` am Ende
  jedes Requests (`server/http_server.py`). Zurueckgerollt wird nur im
  eroeffnenden Thread (Festlegung Alex, 14.10.2026).
- Waechter `tests/test_transaktionsschutz_waechter.py`: R1 jede
  Schreibfunktion im Schreibvorgang (7 begruendete Ausnahmen, alle eigene
  Verbindungen bzw. der Wrapper selbst), R2 wer in einem schreibenden
  try-Block einen DB-Fehler verschluckt, rollt zurueck.
- Nebenbefund: `test_wrapper_prevents_overlap` war „gruen aber tot“
  (Ausnahmen in Worker-Threads gingen verloren) — korrigiert.

## 3. Build 775 — Bildschleier-Korrekturen

- D1: `exempt_css` kommt in beiden Zustaenden (Server und
  `seiteAnwenden()`). Test BSU01 hatte den Fehler als Sollverhalten
  festgeschrieben und ist bewusst umgeschrieben.
- D2: Zustand „lokal“ in `toolbar/bildschleier.js` (Klasse steht, gespeichert
  ist klar), Darstellung `.is-local` (gestrichelter roter Rahmen), Klick hebt
  ohne Request auf. Server-500 traegt den gespeicherten Zustand, auch bei
  unerwarteten Fehlern.
- Integrationstest BSE03 (Durchlauf des Befunds) mit Gegenprobe BSE04
  (ohne Schutz: 500 „locked“ nach ~5 s).
- Hilfe: Kapitel Rechte/Policy, Abschnitt „Bildschleier im Forenviewer“,
  Stand 775.

## 3a. Unabhaengige Durchsicht (14.10.2026) — in 775 behoben

Ein eigener Pruefer, der an der Entstehung nicht beteiligt war, hat den Diff
774/775 durchgesehen. Befunde und Behebung:

1. **Regression aus 774 (bestaetigt):** `get_sort_index_after` verschob
   Bloecke ohne `commit()`; das kam erst aus `save_block`. Die mit 774
   eingefuehrten `rollback()` anderer Threads (z. B. `acquire_lock` bei
   Konkurrenz um den Editor) nahmen die Verschiebung mit -> doppelter
   `sort_index`. Behoben (eigener Schreibvorgang mit commit), neue
   Waechterregel R3 (jede DML im Schreibvorgang, auch ohne eigenes commit).
   **Build 774 darf deshalb nicht allein eingespielt werden.**
2. Leck aus einem Thread, der kein Request ist, blieb stumm -> Meldung
   „verwaist“ (ohne Rollback).
3. `sicherheitsnetz()` nahm nach jedem Request den Lock -> Schnellpfad.
4. Bildschleier: Blaettern waehrend des Einschaltens entschleierte (seit 772);
   gescheitertes Ausschalten mit gespeichert „klar“ -> beides behoben.

Ohne Befund: Verklemmungen durch den gehaltenen Lock, Besitzer-Verfolgung im
Uebrigen, Erfolgspfad (AST-Gleichheit bestaetigt).

## 4. Einspielen

Einzuspielen ist `aiw_webserver_775` (enthaelt 774 und 775; gleicher Zweig,
die Lieferung folgt der letzten Nummer). Das zuvor gelieferte
`aiw_webserver_774` NICHT allein einspielen (Befund 1 in 3a). Keine Migration, keine Schemaaenderung. PROD-Einspielung geplant
am 15.10.2026; vorher DEV-Test durch Alex.

## 5. Offen

1. Build 776: Integritaetspruefung beim Start des Webservers
   (Issue `280ce9c4-506d-41bb-8406-f8beb3f1e20a`). Vorschlag: evidence immer;
   forensic/assets erst nach Messung der Dauer; bei Befund Start verweigern
   und in `<backup.dest_dir>/defekt` sichern, nicht automatisch austauschen.
2. Sonden und Reparaturskript als Werkzeuge aufnehmen
   (Issue `f61df99c-2757-4ffd-90f4-63ce004844c0`).
3. `management/migration_fleet/executor.py`: Flotten-Companion uebergibt
   `expected_deltas={}` (Issue `c90c9977-bbfc-48d8-a38a-6f6953fb5c7d`).
4. Bildschleier PoC P1–P4 in PROD (Issue
   `2db913eb-310c-429f-980b-ad5f3e4e4b64`).
