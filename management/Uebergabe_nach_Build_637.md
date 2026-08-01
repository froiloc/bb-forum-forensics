# Übergabe: Builds 632–637 — Vorgang 17200856 abgeschlossen

**Stand:** 2026-08-01 · letzter Build **0.8.637** · getestet, committet, gepusht (mc)

## 1. Wo wir stehen

Vorgang **17200856** („Alle Schaltflächen und Inputs beschreiben") ist abgeschlossen. Die Fehlliste der Bedienelemente ist leer: **170 von 170 erklärt** (Build 631: 34 von 170). Über sechs Builds sind rund **250 Texte** entstanden — die gezählten 170 sind eine Untergrenze, weil eine Fabrik, die mehrere Bedienelemente baut, einmal zählt.

Die Einzelheiten stehen im Vermerk `management/Vermerk_Bedienelemente_Abschluss_v1_0.md`: die fünf Wellen, die vier Befunde neben den Texten, die vier Messkorrekturen an der Erhebung selbst.

**Beim Einstieg zu prüfen:** Ob die Eingangsdatei `issue-tracker/eingang_claude_Build637.json` eingepflegt ist. Sie setzt `17200856` auf `resolved` und trägt den Abschlussbericht ein.

## 2. Was am Hilfesystem noch offen ist

Strukturell ist die Hilfe vollständig; inhaltlich fehlen drei benannte Punkte.

| Ticket     | Priorität      | Sache                                                                                                                                                                                                                                                                                                     |
| ---------- | -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `60e4236e` | high / trivial | Die CLI-Hilfe erklärt die Einträge in `config.yaml` nicht. **Echte Inhaltslücke.**                                                                                                                                                                                                                        |
| `9e1ba63e` | low / minor    | `hilfe_aufruf()` verweist teils auf die Hilfe eines *Unterbefehls* statt auf das Werkzeug (Befund aus CE11).                                                                                                                                                                                              |
| —          | —              | `cli_ohne_beispiele` in `tests/hilfe_fehlliste_stand.json`: fünf Werkzeuge ohne **gefahrene** Beispielaufrufe — `maintenance_kill`, `consolidate_default_db`, `management`, `main`, `prepare_deployment`. Bei `maintenance_kill` ist das kein Versehen: ein Beispiel zu fahren heißt, etwas abzuschießen. |

`3eff6110` (Online-Hilfe insgesamt) bleibt **offen, bis die Vier-Augen-Lesung durch ist** — dafür ist das Ticket da. Die Lektoratsfassung (`tools/hilfe_lektorat.py`) enthält jeden der rund 250 Texte; LK03/LK04 erzwingen das.

## 3. Nächstes Arbeitspaket (Festlegung mc)

**`15429c75` (critical/blocker) zusammen mit `60e4236e` (high/trivial)** — beide drehen sich um `config.yaml`. Wer die Vorrangregel baut, weiß danach genau, welche Einträge zu erklären sind.

### Was `15429c75` verlangt

> Das Argument wird übernommen. Und im Allgemeinen sollten die Werte aus `config.yaml` verwendet werden, falls das Argument nicht verwendet wird. Aber **Argument schlägt `config.yaml` schlägt hardcoded default**.

### Vorgefundene Anhaltspunkte (nicht geprüft, nur gesichtet)

- `tools/maintenance.py`, 267 Zeilen. Die Vorgabewerte stehen **hart im argparse-Aufbau** und fragen `config.yaml` nirgends: `--data-dir default="./data"` (Z. 220), `--coordinator-db default=None` (Z. 222), `--stale type=int default=30` (Z. 224). Weitere Vorgaben im Unterbefehl `enter`: `--on-active default="pause"`, `--min-build default=0`, `--ablauf-min default=0`, `--wait-timeout default=60`, `--poll default=1.0`.
- `_paths(args)` (Z. 50 f.): `args.coordinator_db` schlägt `args.data_dir` — die einzige Stelle, an der überhaupt eine Vorrangregel existiert.
- `config.yaml` hat 167 Zeilen und ist stark kommentiert; die Kommentare sind bereits Betriebssprache und taugen als Vorlage für die Hilfetexte. Abschnitte: `server`, `browser`, `paths`, `db` (mit dem WAL-Verbot aus Build 499) und weitere.
- **Offene Frage an mc, gleich eingangs zu stellen:** Der Ticket-Text sagt „Das Argument wird ignoriert. Der Modus ist daher nicht zu wechseln." **Welcher Modus** ist gemeint — `--on-active pause|beenden`, `server.mode` aus `config.yaml`, oder etwas Drittes? Ohne diese Auskunft ist der Kern des Tickets nicht sicher zu treffen. Der Rest (Vorrangregel) ist eindeutig.

### Vorschlag für den Zuschnitt

1. Vorrangregel **an einer Stelle** bauen, nicht in jedem Werkzeug einzeln — sonst gibt es dreißig Auflösungen derselben Frage. Prüfen, ob es dafür schon einen gemeinsamen Ort gibt (rund fünfzehn Module lesen `config.yaml`).
2. Gegenproben: Argument gesetzt → Argument gewinnt; Argument fehlt, `config.yaml` gesetzt → `config.yaml` gewinnt; beides fehlt → Vorgabewert. Eine Prüfung, die nie anschlägt, belegt nichts (TE5).
3. Erst danach `60e4236e`: die so belegten Einträge in der CLI-Hilfe erklären — **Regel H-2**, Betriebssprache, nicht H-1.

## 4. Zwei Tickets, die vermutlich schon erledigt sind

- **`651e6d84`** (critical) „Sicherungs-Aufbewahrung verdrängt gute Generationen durch defekte" — beschreibt genau das, was die Builds **625–627** behoben haben (`.defekt`-Endung, `_prune` nur über verifizierte Labels, BE18). **Nachprüfen und schließen**, nicht neu bearbeiten.
- **`17200856`** — siehe Abschnitt 1.

Danach bleiben von den 51 offenen Punkten **ein** unbearbeiteter critical: `15429c75`.

## 5. Was jetzt maschinell greift (nicht mehr anfassen, nur bedienen)

- `tests/test_help_bedienelemente.py`: **BD10** verlangt „kein Bedienelement ohne Text" ohne Einschränkung. BD01, BD02, BD09 als zweites Netz, BD04–BD05h als Gegenproben.
- `documents/rules-help.md` hat drei neue Regeln: „Kein Bedienelement ohne Text", „Kein Text ohne Bedienelement", „Eine Fabrik, mehrere Bedienelemente" — letztere mit der Folgeregel, das Ergebnis einer Fabrik nie direkt in `appendChild` weiterzureichen.
- **Wer künftig ein `button`/`input`/`select`/`textarea` baut, schreibt im selben Build den Hilfetext.** Sonst fällt der Regressionslauf am selben Tag auf.

## 6. Regressionsstand

Container, Python 3.13: **pytest 2883 passed, 65 skipped, 46 subtests**. **vitest 118 Dateien, 1670 passed, 1 skipped, 1 todo** — über alle sechs Builds unverändert; kein bestehender Test wurde geändert.

Achtung beim Einstieg: Der Container bringt Python 3.11 mit, der Code braucht ≥ 3.12. **Alle Aufrufe mit `python3.13`.**
