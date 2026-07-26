# Vermerk — `/api/names` ist mit v0.8.537 aus `management_app.py` verschwunden

**Version:** 0.1 · **Datum:** 2026-07-26 · **Verfasser:** Claude (Instanz B)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Betrifft:** `management/server/management_app.py` · Route `GET /api/names`
und Methode `_names()` · **Instanz A** und **mc**
**Status:** **ERLEDIGT.** Der Verlust ist mit v0.8.540 behoben — `/api/names`
und `_names()` stehen wieder in `management_app.py`, und
`tests/test_name_resolver.py` ist grün (nachgemessen auf `39ec029`).
**Dieses Dokument bleibt als Beleg und wegen §5 bestehen** — der dort
vorgeschlagene Prüfschritt ist unabhängig vom Einzelfall und wird von mir
seit dieser Auslieferung vor jedem Packen ausgeführt.

---

## 1. Der Befund

`origin/master` ist zum Zeitpunkt dieses Vermerks **rot**:

```
tests/test_name_resolver.py::NameResolverTests::test_nr10_endpunkt
    AssertionError: 404 != 200
```

Gemessen in einem eigenen Worktree auf `3cc774c` (v0.8.537), **ohne jede
Änderung von mir**. Der Fehlschlag besteht also unabhängig von meiner
Auslieferung.

## 2. Die Ursache — belegt, nicht vermutet

```
$ git show 364b5aa:management/server/management_app.py | grep -c '_names'
2
$ git show 3cc774c:management/server/management_app.py | grep -c '_names'
0
```

`364b5aa` ist v0.8.536b (mc, Oberflächen-Zweig), `3cc774c` ist v0.8.537
(Instanz A, AP-3B Teil 2). Der Diff zwischen beiden zeigt die Entfernung
ausdrücklich:

```
$ git diff 364b5aa 3cc774c -- management/server/management_app.py | grep '^-.*names'
-        if path == "/api/names":
-            return self._names(person_id, query)
-    def _names(self, actor_person_id: int, query) -> Response:
-        GET /api/names — NAMENSAUFLOESUNG (Oberflaechen-Zweig, Build 600).
-            return Response.json(500, {"error": "names_failed",
```

Es sind **die Route und die vollständige Methode `_names()` (55 Zeilen)**.
`management/crossref/name_resolver.py` und `tests/test_name_resolver.py` sind
unverändert vorhanden — es fehlt genau die Anbindung.

## 3. Warum das hier steht und nicht nur im Testprotokoll

**Das ist exakt der Vorfall, den das Parallelbetriebs-Dokument in §1
beschreibt** — nur mit vertauschten Rollen:

> „Am 2026-07-26 hat Instanz A Build 535 auf v0.8.534 aufgesetzt, während mc
> parallel `cockpit.css` und `management_app.py` erweitert hat. Wäre die
> Auslieferung ungeprüft eingespielt worden, wären beide Erweiterungen
> verschwunden — **ohne Fehlermeldung, ohne Merge-Konflikt, ohne dass ein Test
> angeschlagen hätte.**"

Diesmal **hat** ein Test angeschlagen — `test_nr10_endpunkt` ist mit mcs
Build 536b entstanden und hat den Verlust aufgedeckt. Das ist der Beleg dafür,
dass die Testhärtung wirkt. Der Verlust selbst ist trotzdem eingetreten und
liegt aktuell auf `master`.

**Kein Vorwurf an Instanz A.** Grundregel 7 (vollständige Dateien) macht genau
das unvermeidlich, sobald zwei Beteiligte dieselbe Datei anfassen; §7 der
Prüfliste ist die einzige Abwehr, und sie kostet Disziplin bei jeder einzelnen
Auslieferung. Ich bin bei meinen Builds 561/562/563 dreimal in dieselbe Lage
gekommen und habe `management_app.py` jedes Mal neu aufsetzen müssen.

## 4. Wiederherstellung (eine Minute)

Die beiden Stücke stehen unverändert in `364b5aa`. Route — **ans Ende der
`dispatch()`-Liste, vor dem `/static/`-Zweig**:

```python
        if path == "/api/names":
            return self._names(person_id, query)
```

Methode — vollständig übernehmen aus:

```
git show 364b5aa:management/server/management_app.py
```

(Methode `_names`, 55 Zeilen; sie beginnt mit dem Docstring
„GET /api/names — NAMENSAUFLOESUNG (Oberflaechen-Zweig, Build 600).")

Danach muss `tests/test_name_resolver.py` wieder grün sein.

**Meine Auslieferung 562/563 ist davon unabhängig**: sie setzt auf `3cc774c`
auf und fügt ihre Routen am Ende derselben Listen an. Wird `_names`
wiederhergestellt, stehen beide Blöcke nebeneinander — die Anker meiner
Auslieferung (`if path.startswith("/static/"):` bzw.
`if path == "/api/mentoring/note/reorder":`) sind davon nicht berührt.

## 5. Ein Vorschlag, damit es nicht wieder passiert

`management/server/management_app.py` steht in §4 bereits mit der Regel „nur
die Route, am Ende der jeweiligen Routen-Liste". Die Regel war richtig und hat
hier nicht gereicht, weil die **Methode** am Dateiende steht und beim
Neuaufsetzen mit übernommen werden muss.

Vorschlag zur Ergänzung von §4 für diese Datei:

> Wer `management_app.py` neu aufsetzt, prüft **vor dem Packen**:
> ```
> git diff origin/master -- management/server/management_app.py | grep '^-'
> ```
> Der Diff darf **keine gelöschten Zeilen** enthalten, die nicht zur eigenen
> Änderung gehören. Eine einzelne `-`-Zeile aus fremder Hand ist ein Abbruch.

Das ist ein Befehl und dauert Sekunden — und er hätte diesen Vorfall gefunden.

---

*Dokument-Ende · Vermerk `/api/names` · v0.1 · 2026-07-26 · Instanz B*
