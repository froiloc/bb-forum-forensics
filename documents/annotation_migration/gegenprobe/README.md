# Gegenprobe an einem Einzelfall

**Wozu.** Bei einem Zweifelsfall muss man Seite und Wortlaut nebeneinander
legen koennen. Originaldaten duerfen die Umgebung des Auftraggebers nicht
verlassen — es sind laufende Ermittlungsverfahren.

**Das Verfahren** (Alex, 08.09.2026). Es liefert ein Paar aus Seite und
Wortlaut, das ZUEINANDER passt:

1. Die Seite mit `tools/anon_html.py` anonymisieren. Die XPath-Ausdruecke je
   Seitenart liegen daneben (`viewtopic_anon.xpath`).
2. Die anonymisierte Seite im Browser ueber DevTools an die Stelle der
   geladenen setzen.
3. Die Markierung **neu erzeugen** — an derselben Stelle.
4. Den entstandenen `selection_json` entnehmen.

**Warum der Umweg noetig ist.** Werden Seite und Wortlaut GETRENNT
anonymisiert, passen die Maskierungen nicht zueinander: Am 08.09.2026 standen
89 von 114 Bloecken in keinem Beitrag, und der erste stand nicht einmal
irgendwo im Abzug. Der Titel lautete im HTML `…XX XXXX XXXXXX #157477`, im
`textContent` dagegen `…XX XXXX (X+XX)#XXXXXX` — verschiedene Maskierung,
verschiedene Laengen. Eine Gegenprobe war damit unmoeglich.

Wird der Wortlaut dagegen AUS der anonymisierten Seite heraus erzeugt, stimmen
beide zwangslaeufig ueberein.

**Was dabei zu beachten ist.** Der Browser fuegt Dinge hinzu, die im Abzug
nicht stehen — etwa die Uebersetzungsschaltflaeche. Eine Markierung, die dort
endet, traegt einen Anker auf ein Element, das es im BLOB nie gab.

**Belegter Fall.** `583231/6`, Seite `/forum/viewtopic.php?id=157477`, 69
Beitraege. Anker: Start im Themenbetreff (ausserhalb jedes Beitrags), Ende in
`article[2]`. Ergebnis der Auswertung zu Build 770:

```
Bloecke   0-4    ausserhalb       71 Zeichen  ->  entfaellt
Bloecke   5-105  post 1550483   3670 Zeichen  ->  whole post
Bloecke 106-113  post 1550508    175 Zeichen  ->  whole post
```

Praefix, ein ganzer Beitrag, ein teilweise markierter — genau die Einordnung,
die Alex zuvor durch Sichtpruefung getroffen hatte.
