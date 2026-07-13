# Bauplan Build 393 — Abdeckung & blinde Flecken (Backend)

**Version:** 0.1 · **Datum:** 2026-07-12
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Basis:** 0.7.392 · **mc:** 2026-07-12 · **Migration:** keine.
**Cockpit-Sicht folgt als Build 394** (Festlegung 363).

---

## 1. Der Mangel (gemessen)

`ResultsRepo.stats()` (Build 387) liest aus **`v_investigation_current`**. Dort
steht ein Fall **nur, wenn er mindestens eine Bewertung hat**.

**Folge:** Ein Fall, den **niemand** bewertet hat, taucht in der Statistik
**überhaupt nicht auf**. Er wird nicht als Lücke gezeigt — er ist schlicht
**unsichtbar**. Und die Statistik sieht dabei **vollständig** aus.

Testbeleg **CV01**:

```python
st = repo.stats()
st["faelle"]  ->  1        # Fall 20 (nie bewertet) fehlt komplett
```

Genau diese Fälle sind aber das, wonach die Chef-Ermittlerin sucht: **die
blinden Flecken.** Eine Auswertung, die nur über die Fälle spricht, die schon
jemand angefasst hat, **beantwortet die falsche Frage** — und verschweigt dabei,
dass sie es tut (Grundregel 1).

**Das Frontend kann das nicht heilen.** Es müsste `/api/results?user_id=` für
jeden Fall einzeln abrufen. Es ist ein Backend-Mangel.

---

## 2. Die Lösung

`CoverageRepo` geht **von `cases` aus** und joint die Bewertungen **links** an —
nicht umgekehrt. **Jeder Fall steht in der Liste**, auch der mit `abdeckung = 0`.

```
GET /api/results/coverage
{
  faelle_gesamt, nie_bewertet, kriterien[], n_kriterien,
  catalog_version, vermerk, scope, summary{},
  faelle: [{
    user_id, username, status, priority, assigned_to,
    n_bewertet / n_kriterien, abdeckung,
    n_beste,                      # 'beste' SEPARAT ausgewiesen
    unbewertet[],                 # welche Kriterien fehlen — BENANNT
    score,                        # provisorisch, mit Vermerk
    hoechste_konfidenz, hoechstes_kriterium,
    zuletzt_bewertet,
    nie_bewertet                  # <-- der blinde Fleck
  }]
}
```

**Sortierung: die blinden Flecken zuerst.** Wer die Liste öffnet, soll sehen,
**wo nicht ermittelt wurde** — nicht danach suchen müssen.

**Abdeckung bezieht sich auf `schwerste`** (`mc`) — die Priorisierungsachse (die
**gravierendste**, nicht die bestbelegte Erkenntnis). `beste` wird **separat**
ausgewiesen (`n_beste`), damit sichtbar wird, ob ein Fall nur **einseitig**
bewertet ist. Testbeleg **CV02**.

**Leistung:** Der aktuelle Stand aller Fälle wird in **einem** Zug gelesen
(`_current_map`), nicht je Fall eine Abfrage — bei 477.178 Nutzern wäre das
nicht tragbar.

---

## 3. `/api/results/stats` weist die Differenz jetzt aus

Neu: `faelle_gesamt` und `faelle_unbewertet` neben `faelle` (= die bewerteten).

> Ohne die Gesamtzahl daneben liest sich *„Bewertete Fälle: 19"* wie eine
> **Vollerhebung**. **Die Differenz *ist* der Befund.**

Auch die CLI sagt es jetzt: *„Bewertete Faelle: 1 von 3 (2 noch gar nicht
bewertet — siehe 'coverage')"*.

---

## 4. Scope

`results.view`. Scope `alle` → alle Fälle; `eigene` → die zugewiesenen.

**Anders als `/stats` gibt es hier kein 403 für `eigene`:** *„Wie vollständig
habe **ich** meine Fälle bewertet?"* ist eine legitime **Eigenfrage**. Die
fallübergreifende **Statistik** bleibt `alle` vorbehalten (Testbeleg **CV08**).

---

## 5. Dateien

| | |
|---|---|
| **NEU** | `management/results/coverage_repo.py` (`CoverageRepo`) |
| geändert | `management/server/management_app.py` — `GET /api/results/coverage`; `/stats` + `faelle_gesamt`/`faelle_unbewertet` |
| geändert | `management/results/results_admin.py` — Befehl `coverage` (`--nur-luecken`), **Exit 2** bei blinden Flecken mit umrahmter Warnung auf stderr |
| **NEU** | `tests/test_results_coverage.py` (CV01–CV09) |
| **NEU** | `management/Bauplan_Build393_ResultsCoverage_v0_1.md` (**`git add -f`**) |

Die Endpunkt-Tests verwenden die **`parse_qs`-Listenform** (Regel aus Build 391).

---

## 6. Regression (run_tests.py)

```
pytest : 1121 passed (1112 + 9), 59 skipped, 6 subtests
vitest : 653 passed, 54 Testdateien   (unverändert — Backend-only)
```

---

## 7. Abnahme

**Management-Server neu starten.** Keine Migration, keine neuen Grants
(`results.view` genügt).

1. `python -m management.results.results_admin coverage`
   → **jeder** Fall steht in der Liste; nie bewertete zeigen
   **„ALLE (nie bewertet)"**; **Exit 2** + umrahmte Warnung auf stderr.
2. `… coverage --nur-luecken` → nur die unvollständigen.
3. `… stats` → *„Bewertete Faelle: N von M (K noch gar nicht bewertet)"*.
4. **Gegenprobe:** einen Fall anlegen und **nicht** bewerten → er erscheint in
   `coverage` mit `nie_bewertet`, in `stats` **gar nicht**. Genau das ist der
   Unterschied, um den es geht.
5. `GET /api/results/coverage` als Ermittler (`eigene`) → **200**, nur die
   eigenen Fälle; `GET /api/results/stats` → **403**.

---

## 8. Nächster Build

**394 — Cockpit-Sicht „Ermittlungsergebnis":**
Abdeckungstabelle (Tabulator, blinde Flecken **rot**, Zähler nennt sie
ausdrücklich) + Verteilung **je Kriterium** (ECharts, **nie über Kriterien
hinweg** — `ordinal` misst bei `abuser` **Schwere**, bei `location`
**Präzision**, M011 §D). Der Vermerk zur Kennzahl bleibt nicht wegklickbar.

---

*Dokument-Ende · Bauplan Build 393 · 2026-07-12*
