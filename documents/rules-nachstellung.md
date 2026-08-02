# Regelwerk AIW — Die Nachstellung muß der Wirklichkeit standhalten

**Stand:** Build 649 · 2026-08-01 · **Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH

Dieses Blatt faßt zwei Vorgänge zusammen, die dasselbe Grundmuster von zwei Seiten zeigen: `c3f80e54` (schwache Prüfungen erzeugen unwirkliche Testvorrichtungen) und `2f8a61d0` (Lehre aus der Kette 578–583: den ganzen Weg einer Fehlermeldung prüfen). Beide handeln davon, daß eine Messung **grün** sein kann, ohne über den Betrieb etwas auszusagen.

## Die Regel

> **Eine Prüfung sagt nur so viel, wie ihre Nachstellung wert ist.**
>
> Drei Fragen sind vor jedem grünen Ergebnis zu beantworten:
>
> 1. **Kann es den nachgestellten Zustand im Betrieb überhaupt geben?**
> 2. **Sind die Bedingungen dieselben** — derselbe Benutzer, dieselben Rechte, dieselbe Schichtenfolge?
> 3. **Reicht die Prüfung bis dorthin, wo die Wirkung ankommen soll** — oder endet sie an der Schicht, in der ich gerade arbeite?

Wird eine dieser Fragen nicht beantwortet, ist das Ergebnis kein Beleg, sondern eine Vermutung mit grüner Farbe.

---

## NS1 — Eine Testvorrichtung bildet einen Zustand ab, den es geben kann

**Vorgang `c3f80e54`.** Zweimal in Folge mußte eine Testvorrichtung angepaßt werden, weil sie einen Zustand abbildete, den es real nicht geben kann:

| Fundstelle | Was die Vorrichtung baute | Warum es das nicht gibt |
| --- | --- | --- |
| `test_placeholders::T10` | die Tabellen in der **Hauptdatenbank** | im Betrieb liegen sie als angehängte `tdb` |
| `_con_mit_tdb()` | `placeholders` **nur mit `id`-Spalte** | die echte Tabelle hat mehr, und die Prüfung liest mehr |

**Beide fielen erst auf, als die Produktionsprüfung strenger wurde** — und das ist der eigentliche Befund. Solange die Prüfung schwach war, paßte die unwirkliche Vorrichtung zu ihr. Die Vorrichtung war nicht *zufällig* falsch: sie war **genau so schwach wie die Prüfung, für die sie gebaut wurde**. Eine schwache Prüfung erzeugt die Attrappe, die zu ihr paßt, und beide bestätigen einander.

**Was daraus folgt:**

- **Die Vorrichtung wird aus derselben Quelle gebaut wie der Betrieb**, wo immer das geht — aus dem Schema, aus dem Katalog, aus der Anlegefunktion des Bestandes. Eine von Hand abgeschriebene Tabelle weicht binnen zweier Builds ab, und zwar unbemerkt.
- **Wer eine Prüfung verschärft, sieht ihre Vorrichtungen durch.** Die Verschärfung ist der Anlaß, an dem die Attrappe auffällt — nicht die Gelegenheit, sie schnell anzupassen, damit es wieder grün wird.
- **Eine Anpassung der Vorrichtung ist ein Befund und wird als solcher vermerkt** (GR1). Sonst steht am Ende im Protokoll „Test angepaßt", wo „die Nachstellung war unwirklich" stehen müßte.

### NS1 in freier Wildbahn, Build 648

`96f2b18f` meldete, die Sperrprobe sei auf versiegelten Beweismitteln blind. **Mein erster Nachstellversuch lief als `root` und zeigte durchgehend das gute Verhalten** — er hätte den Vorgang als unbegründet erscheinen lassen. `root` schreibt auch auf eine Datei mit `0444`; den fraglichen Zustand **gibt es unter `root` gar nicht**. Erst der Wechsel auf einen fremden Benutzer (`nobody`, im Unterprozeß) hat ihn sichtbar gemacht — und dann war der Befund sogar **breiter** als gemeldet: betroffen ist nicht die Versiegelung, sondern das Schreibrecht des messenden Prozesses, also auch eine ganz gewöhnliche `0644`-Datei auf einem geteilten Laufwerk.

**Die Lehre ist unbequem:** Eine mißlungene Nachstellung sieht genauso aus wie ein widerlegter Vorgang. Wer unter falschen Bedingungen mißt, bekommt kein „unklar", sondern ein überzeugendes **Gegenteil**.

*Durchsetzung:* `tests/test_sperrprobe_dreiwertig.py` fährt die heiklen Fälle im Unterprozeß als `nobody` und **überspringt sichtbar und namentlich**, wo das nicht geht (kein `root`, kein `nobody`, Windows). Ein übersprungener Fall steht im Lauf; ein stillschweigend weggelassener nicht.

### NS1 und die Nachbarschaft: eine Vorrichtung, die stehenbleibt

Ebenfalls Build 648, ebenfalls meiner: Die erste Fassung von MK01–MK05 ersetzte `ServerRegistration.alle_laden` durch **Zuweisung** statt über `monkeypatch`. Die Ersetzung blieb bis zum Ende des Laufs stehen und hat **drei fremde Tests umgebracht** — aufgefallen erst im Vollauf, im Einzellauf nie.

> **Eine Vorrichtung, die den eigenen Fall überlebt, ist keine Vorrichtung mehr, sondern eine Änderung am Bestand.** Klassenattribute werden mit `monkeypatch` gesetzt, nie mit `=`. Und ein Einzellauf ist kein Nachweis: der Vollauf ist es.

---

## NS2 — Der ganze Weg wird geprüft, nicht die Schicht, in der man steht

**Vorgang `2f8a61d0`, die Kette 578–583.** Vier Anläufe für **eine** Fehlermeldung:

| Build | Was getan wurde | Warum es nicht reichte |
| --- | --- | --- |
| 578 | eine Hülle auf einer ungeprüften Annahme gebaut | die Ausnahme kam dort nie an |
| 579 | die echte Stelle gefunden — der Fehler wurde eine Ebene tiefer geschluckt | die Meldung war nicht handhabbar formuliert |
| 582 | die Meldung handhabbar gemacht | — |
| 583 | festgestellt: sie erreichte den Browser gar nicht | der Abrufer verschluckte sie |

**Jede Stufe war eine Schicht, die etwas verschluckt hat:** Datenschicht, Endpunkt, Abrufer. Jeder einzelne Build war für sich richtig und hat den Betrieb nicht verbessert, weil die nächste Schicht das Ergebnis wieder kassierte.

**Was daraus folgt:**

- **Der Nachweis für eine Fehlermeldung ist ihre Ankunft**, nicht ihre Entstehung. Geprüft wird dort, wo sie gelesen wird — beim Ermittler auf dem Schirm oder im Rückgabewert des Werkzeugs.
- **Vor dem Bauen wird der Weg abgeschritten:** Wer wirft? Wer fängt? Wer reicht weiter? Wer gibt aus? An jeder Übergabe ist zu fragen, was dort mit einem Fehler geschieht — ein `except Exception: pass` ist die häufigste Antwort und die schlechteste.
- **Eine Schicht, die einen Fehler schluckt, ist selbst der Befund** — nicht der Text der Meldung, den man gerade verbessert.
- **Für den Browser gilt zusätzlich die Reihenfolge aus den Projektanweisungen:** erst Konsolenausgabe anfordern, dann einen Machbarkeitsnachweis für die Konsole liefern, und erst wenn das trägt, einen Fix für die Auslieferung.

### NS2 auf der Kommandozeile

Derselbe Weg, andere Schichten: Prüffunktion → Werkzeug → **Rückgabewert** → Skript, das ihn auswertet. Die drei Fälle aus `rules-leerbefund.md` sind allesamt NS2-Fälle: Die Prüfung *lief*, ihr Ergebnis *stand* sogar in der Ausgabe — und wurde eine Schicht weiter nicht mehr ausgewertet. `backup_admin list` druckte die Spalte `integrity=FEHLER` und gab trotzdem `0` zurück.

---

## NS3 — Wer die Grenzen der Messung nicht nennt, behauptet mehr, als er weiß

Aus beiden Vorgängen zusammen, und deckungsgleich mit TE4 (`rules-coding.md`):

- **Was nicht nachgestellt werden konnte, wird benannt.** Build 648 hat Windows und den WAL-Journalmodus ausdrücklich *nicht* geprüft (WAL ist projektweit verboten, Build 499; Windows steht aus) — das steht im Buildvermerk, nicht im Verschwiegenen.
- **Was die Suche nicht sehen kann, steht im Kopf der Suche.** `tests/_lesende_verbindungen.py` sagt selbst, daß es Verbindungen aus anderen Modulen nicht sieht und Zugriffe an `sqlite3` vorbei erst recht nicht. Aus dieser Selbstauskunft ist Vorgang `88dc129b` entstanden — und aus dem Vorgang die Erhebung in Build 649.
- **Eine Prüfung, die nie anschlägt, belegt nichts** (TE5). Das gilt auch für eine Auslassungsliste: In Build 649 wurde nachgemessen, welche der acht Auslassungen der Modul-Erhebung überhaupt etwas herausnimmt. Es ist **eine** (`tests`, 162 Dateien); die anderen sieben sind Vorsorge und stehen als solche gekennzeichnet. Wer sie ungeprüft aufzählte, erweckte den Eindruck, acht Fundgruben abgeräumt zu haben.

---

## Die Kurzfassung für den Alltag

| Frage vor dem grünen Haken | Wo es schiefging |
| --- | --- |
| Kann es diesen Zustand im Betrieb geben? | `T10`, `_con_mit_tdb()` — Vorgang `c3f80e54` |
| Messe ich unter denselben Rechten wie der Betrieb? | Sperrprobe als `root` — Build 648 |
| Überlebt meine Vorrichtung den Fall? | `ServerRegistration.alle_laden` per Zuweisung — Build 648 |
| Kommt die Wirkung dort an, wo sie gelesen wird? | Kette 578–583 — Vorgang `2f8a61d0` |
| Schlägt meine Prüfung bei einem echten Verstoß an? | TE5, durchgehend |
| Was habe ich **nicht** geprüft, und steht das da? | TE4, `rules-leerbefund.md` |

## Durchsetzung

Diese Regeln sind **überwiegend redaktionell** — das steht hier ausdrücklich, damit niemand sie für maschinell gesichert hält. Maschinell greifbar sind heute:

| Regel | Durchsetzung |
| --- | --- |
| NS1 (fremde Rechte) | `tests/test_sperrprobe_dreiwertig.py` SP01–SP08, sichtbares Überspringen mit Grund |
| NS1 (Vorrichtung bleibt stehen) | keine automatische — der **Vollauf** ist der Nachweis, nie der Einzellauf |
| NS2 (Rückgabewert) | `tests/test_leerbefund.py` LB01–LB22 |
| NS3 (Grenzen genannt) | TE4 als Redaktionsregel; für Auslassungslisten `tests/test_py4_lesend.py` PY10b/PY10c |
