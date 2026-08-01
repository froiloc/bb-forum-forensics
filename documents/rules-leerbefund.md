# Regelwerk AIW — Leerbefund ist kein Erfolg

**Stand:** Build 647 · 2026-08-01

## Die Regel

> **Wer nichts vorfindet, hat nichts geprüft.**
>
> Ein Werkzeug, das einen Bestand prüft, beantwortet **drei** Fragen — nicht zwei:
>
> 1. Ist alles in Ordnung?
> 2. Gibt es eine Abweichung?
> 3. **War überhaupt etwas da, woran man messen konnte?**
>
> Die dritte Frage ist die, die in allen bisher gefundenen Fällen gefehlt hat. Fehlt sie, wird aus *„es gibt nichts zu prüfen"* die Meldung *„alles geprüft und in Ordnung"*.

## Warum das in diesem Projekt schwerer wiegt als anderswo

Der Rückgabewert ist dafür da, **ohne die Ausgabe zu lesen** auswertbar zu sein. Genau darauf verlässt sich, wer ein Werkzeug in ein Skript oder in eine Überwachung hängt. Eine Erfolgsmeldung für ein Nichts ist deshalb kein Schönheitsfehler, sondern eine **falsche Zusage** — und sie beendet die Suche.

Die drei bislang gefundenen Fälle liegen alle an Stellen, an denen das teuer ist:

| Vorgang | Werkzeug | Was gemeldet wurde | Woran es lag |
| --- | --- | --- | --- |
| `d30b3d95` | `ausschleus_admin verify` | „OK — alle Artefakte stimmen mit dem Manifest überein", Rückgabewert 0 — auf einem **leeren Verzeichnis** | `load()` liefert bei fehlendem Manifest ein frisches Grundgerüst mit leerer Artefaktliste; danach waren alle drei Befundlisten leer |
| `0329896b` | `prepare_deployment` | Rückgabewert 0 trotz **gescheitertem Wheel-Download** | Der Fehlschlag wurde als „WARNUNG" gedruckt, dann kehrte die Funktion zurück |
| `e9522fe2` | `backup_admin list` | Rückgabewert 0, auch wenn **jede** Zeile `integrity=FEHLER` trug | Der Zählzweig fehlte; gedruckt wurde die Spalte, ausgewertet wurde sie nicht |

Die Ausschleusung ist der Weg, auf dem Material das Haus verlässt. Die Auslieferung ist der Weg, auf dem die Anlage auf die VM kommt. Die Sicherung ist das, worauf man sich verlässt, wenn alles andere weg ist.

## Was beim Bauen zu tun ist

**Den Leerbefund vom Befund unterscheiden — im Rückgabewert, nicht nur im Text.** Der Hausgebrauch dieses Bestands ist: `0` = in Ordnung, `1` = Befund, `2` = es war nichts da (bzw. der Ernstfall, wo das die schwerere Lage ist). Mehrere Werkzeuge halten es bereits so — `qs_admin nachziehen`, `results_admin coverage`, `external_admin list`, `index_cli --auffrischen`, `backup_admin pruefen`.

**Der Rückgabewert gehört in den Katalog.** Sonst hält ihn jemand für einen Absturz. `CliTiefe.exit_codes` ist der Ort.

**Ein „nichts gefunden" ist auszusprechen, nicht nur zurückzugeben.** Die 1 bei `hilfe.py suche` ohne Treffer ist eine *Auskunft*, kein Programmfehler — und sie wird als solche gedruckt.

**Was nicht geprüft wurde, steht im Schlussbericht.** Ein halber Lauf darf nicht aussehen wie ein ganzer. `prepare_deployment --skip-wheels` sagt seither ausdrücklich, dass es über die Vollzähligkeit **nichts** aussagt; `diag_backup_verdraengung` führt nicht gefahrene Proben namentlich unter „NICHT GEPRÜFT".

## Die Abgrenzung, ohne die die Regel zu grob wäre

**Ein leeres Ergebnis ist nicht automatisch ein Fehler.** Ein Ausschleusungspaket *mit* Manifest und *ohne* Artefakte ist eine gültige Aussage: Jemand hat ein Paket erzeugt, das nichts enthält. Es unterscheidet sich von „hier wurde nie etwas erzeugt", und genau diese Unterscheidung war bei `d30b3d95` verlorengegangen.

Die Frage lautet also nicht „ist die Liste leer?", sondern **„gab es eine Grundlage, gegen die gemessen wurde?"**

## Durchsetzung

`tests/test_leerbefund.py` — LB01–LB22.

Die Suite prüft in beide Richtungen: dass der Leerbefund auffällt (LB01, LB11), **und** dass die gültigen Fälle weiter durchgehen (LB02) und die bisherigen Befunde nicht verschluckt wurden (LB03). Eine Prüfung, die nur die eine Richtung kennt, lädt dazu ein, den Fehler durch einen anderen zu ersetzen.

LB12 ist die Gegenprobe gegen den *falschen Treffer*: `pytest_asyncio-…` darf nicht als Rad für `pytest` durchgehen. Eine Vollzähligkeitsprüfung, die sich täuschen lässt, ist schlimmer als keine — sie meldet Vollzähligkeit, wo ein Paket fehlt.
