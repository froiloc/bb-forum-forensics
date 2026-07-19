# Fehler im Frontend
(Cache-buster-pre-extension: 81314f76-83b1-11f1-98d7-1f66383f4f84)

Ich werde in dieser Liste fortlaufend die von mir beobachteten Fehler aufführen.
Falls diese abgeschlossen und verworfen wurden, werde ich sie durchstreichen. Alles, was nicht durchgestrichen ist, ist also noch offen und muss bearbeitet werden.
Am Anfang jedes Eintrages kann eine Zahl stehen. Je höher der Wert, desto dringender ist das Problem und sollte daher vorrangig behoben werden.
Themen gleicher Art sollten in einem gemeinsamen Build behoben werden.
Nach der Bearbeitung ist das behobene Problem anzugeben. Und zwar mit Kapitel (1 = CSS, 2 = JS, 3 = PY/SQL, 4 = Sonst) und der Nummer in der Liste.
Hier noch einmal die Liste der Baustellen und wofür sie stehen:
| Baustelle | Abkürzung | Thema | base64-Zip-Archiv |
|--|--|--|--|
| 0 | BS0 | Datenextraktion aus MariaDB, Bereitstellung SQLite3-DBs, Vorberechnen von statischen Seiten | aiw_sqlite_prepper |
| 1 | BS1 | Laufzeitumgebung und Deployment | teilweise aiw_webserver |
| 2 | BS2 | Python-Webserver für Ermittler | aiw_webserver |
| 3 | BS3 | Toolbar, Werkzeugleiste der Hauptseite, Modals für Hauptseite | aiw_webserver |
| 4 | BS4 | userinfo-tab, Nutzerinformationsseite, statische, extrahierte Daten, ohne Darstellung in Foren-Webseiten, Sammlung und Darstellung der Ermittlungsergebnisse | aiw_webserver |
| 5 | BS5 | Datenbank-Interfaces, Schnittstellen und Zugriffsrechte zwischen Datenbanken | aiw_webserver, aiw_sqlite_prepper, aiw_administration (noch ausstehend) |
| 6 | BS6 | Berichtseditor, Export, Datenbereitstellung für die Akte und die Staatsanwaltschaft | aiw_webserver |
| 7 | BS7 | Management-Interface, Vorlagenverwaltung, Auftragsvergabe, Priorisierung | aiw_webserver, aiw_administration (noch ausstehend) |

Als optionale dritte Nummer in Klammern steht die Buildnummer, bei der das (erstmalig) festgestellt wurde.
	Beispiel: 4. (15) (BS6) (160) Die Schaltfläche Test ist funktionslos.
Die 4. Meldung im Kapitel hat eine Dringlichkeit von 15, gehört zur Baustelle 6, dem Berichtseditor, und wurde das erste Mal in Build 160 festgestellt.

Abgeschlossene Aufgaben werden durch das Wort `erledigt` ersetzt.

Quellen zum Debuggen:
* Dieses Dokument mit den Arbeitsanweisungen und Problembeschreibungen:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/bugs-and-tasks/last.81314f76-83b1-11f1-98d7-1f66383f4f84.md
* Die Ausgabe von DevTools-Console:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/devtools-console/last.81314f76-83b1-11f1-98d7-1f66383f4f84.log
* Die Ausgabe von DevTools-Network:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/devtools-network/last.81314f76-83b1-11f1-98d7-1f66383f4f84.har
* Das aktuelle DOM des gesamten Dokuments als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-html.81314f76-83b1-11f1-98d7-1f66383f4f84.html
* Das aktuelle DOM des gesamten Body als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-body.81314f76-83b1-11f1-98d7-1f66383f4f84.html
* Das aktuelle DOM des gesamten Sidebar als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-sidebar.81314f76-83b1-11f1-98d7-1f66383f4f84.html
* Das aktuelle DOM des gesamten Main als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-main.81314f76-83b1-11f1-98d7-1f66383f4f84.html
* Das aktuelle DOM des Akkordeon 1 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-1.81314f76-83b1-11f1-98d7-1f66383f4f84.html
* Das aktuelle DOM des Akkordeon 2 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-2.81314f76-83b1-11f1-98d7-1f66383f4f84.html
* Das aktuelle DOM des Akkordeon 3 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-3.81314f76-83b1-11f1-98d7-1f66383f4f84.html
* Das aktuelle DOM des Akkordeon 4 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-4.81314f76-83b1-11f1-98d7-1f66383f4f84.html
* Das aktuelle DOM des Search-Modal als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-searchmodal.81314f76-83b1-11f1-98d7-1f66383f4f84.html
* Die Ausgabe des aktuellen Webservers:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/webserver-log/last.81314f76-83b1-11f1-98d7-1f66383f4f84.log
* Die aktuellen Screenshots:
https://github.com/froiloc/bb-forum-forensics/tree/1b5017a2f62c5a8f1825de76fc6edabb25d6bf66/debug/screenshots
***

## 1. Style / Layout / CSS
Hier werden CSS‑Fehler aufgeführt. Das sind Themen, bei denen die Anzeige funktionale oder optische Probleme hervorruft

 1. (0) (BS6) Ein Dark-Theme wäre cool. Ich persönlich mag helles Layout nicht. Ich fände es toll, wenn wir hier auch ein Dark-Theme anbieten könnten.
---
## 2. Funktionalität Frontend / Daten / JS
Hier werden Funktionsprobleme aufgeführt, die verhindern, dass der Ermittler mit dem Webwerkzeug arbeiten kann oder ihn dabei nicht im vorgesehenen Maße unterstützen oder behindern.

 1. (2) (BS6) Die Funktionalität für die Schaltfläche `⬇ Export ▾` fehlt.
2. (10) (BS6) Möglicherweise wird der Fokus verloren, nachdem ein Autosave durchgeführt wurde. Ich bin aber nicht sicher. Ich konnte es nicht genau beobachten und nachstellen.
3. (20) (BS6) Es kommt noch immer zu Situationen, in denen nicht inline eingefügt werden kann und bei denen dann der Platzhalter nach einem Block eingefügt wird. In diesem Fall wurde der Platzhalter am Ende des Dokuments eingefügt, obwohl zuvor der Fokus in einem der vorderen Blöcke war. Der Cursor wurde zuvor aktiv in einen Text in einem Block platziert. Erst dann wurde die Schaltfläche `+ Einfügen` für `user.aliases` angeklickt. Der Platzhalter wurde dann zunächst am Ende des Dokuments eingefügt. Nach erneutem Platzieren des Cursors im ursprünglichen Block und erneutem Klicken auf `+Einfügen` wurde `user.aliases` dann korrekt inline an der gewünschten Stelle gesetzt.
4. (20) (BS6) Es kommt vor, und das ist wieder so ein "Beim ersten Versuch klappt es nicht, bei den folgenden Versuchen aber schon"-Fehler, dass beim Einfügen eines Standard-Elements dieses nicht an der Position nach dem aktuellen Block, sondern am Anfang des Dokuments eingefügt wird. Das sollte nicht sein. Hier müssen wir wieder schauen, wie wir da herausfinden, woran das liegen kann. Ich wünsche daher, dass im Consolen-Output die Aktualisierung der Cursor-Position angezeigt wird, wenn sie durch Mousedown oder Keydown erfasst wird. Und es soll vor dem Setzen des neuen gespeicherten Wertes dessen derzeitiger Wert aufgeben werden. Und ich wünsche, dass beim Einfügen eines Elements in der Console die Position des Cursors angegeben wird und die Position, an der das neue Element eingefügt wird. Das wird uns hoffentlich rasch helfen, das Problem zu lösen.
5. (20) (BS6) Nach dem Laden der Seite wurde in `Bausteine` > `Module` > `Standard` das Element per Drag and Drop in den `Editor.js` an eine Stelle am Anfang gezogen und losgelassen. Es wurde aber nicht an dieser Stelle, sondern ganz am Ende des Dokuments eingefügt.
6. (10) (BS6) Im Berichtseditor können Einzeldaten nicht per Drag-and-drop eingefügt werden. Nur das Einfügen über die `+Einfügen` Schaltfläche funktioniert.
7. (10) (BS6) Wenn ein neuer Block erstellt wird, dann kann man bei diesem Block erst kommentieren, wenn der Block gespeichert wurde. Im Regelfall ist das nach einem Autosave oder wenn manuell `Speichern` angeklickt wird. Der Klick auf `Kommentieren` sollte daher prüfen, ob der Block bereits gespeichert wurde, und notfalls speichern, damit der Block kommentiert werden kann.
8. (30) (BS6) Wenn ich einen neuen Bericht erstelle und dann zu einem bestehenden Bericht wechsle, wird dieser nicht angezeigt.
9. (40) (BS6) Wenn ein neuer Bericht erstellt wird, erzeugt der keinen leeren Bericht mehr.
10. (5) (BS6) Es ist sicherzustellen, dass, wenn im `Formular`-Bereich ein Block ausgewählt und umrahmt ist, dieser Block auch im `Editor.js`-Bereich umrahmt ist. Das muss immer beim Wechsel in den `Formular`-Bereich sichergestellt werden.
11. (5) (BS6) Um das Verhalten der Bausteine gleich zu machen, sollen auch Standard-Blöcke und Einzeldaten per Doppelklick eingefügt werden können. Derzeit ist das nur für Module möglich.
12. (10) (BS6) Es kommt vor, dass ein Klick auf `+Einfügen` bei einem Einzeldaten-Platzhalter den Platzhalter nicht beim Cursor einfügt, sondern am Ende des `Editor.js` in einem neuen Block. Dies passiert meist beim ersten Versuch. Nachfolgende Versuche klappen.
13. (5) (BS6) Das Löschen eines Blocks per Backspace funktioniert nicht. (Wo muss der Cursor denn stehen, damit das klappt?) Beobachtet wird, dass lediglich das links vom Cursor stehende Element/Zeichen entfernt wird. 
14. (10) (BS6) Der Doppelklick auf ein Modul erstellt das Modul am Ende des `Editor.js` und nicht als neuen Block nach dem Block, der gerade den Cursor hat.
15. (30) (BS6) Wenn man beispielsweise eine Überschrift eingefügt hat und bearbeitet und dann unmittelbar hiernach ein Modul durch Doppelklick einfügt, so verschwindet die Überschrift. Sie wurde zuvor offensichtlich nicht gespeichert und aufgrund des Reload-Prozesses ohne vorheriges Speichern, ist diese Eingabe verloren.
16. erledigt
17. erledigt
18. erledigt
19. erledigt
20. erledigt
21. erledigt
22. erledigt
23. erledigt
24. erledigt
25. erledigt
26. erledigt
27. erledigt
28. erledigt
29. erledigt
30. erledigt
31. (15) (BS6) (298) beim Wechsel von Formular-Blöcken geht der Fokus (Scroll) im Editor nicht mit.
---
## 3. Funktionalität Backend / Python / SQLite3-Datenbank
Hier werden Funktionsprobleme aufgeführt, die aufgrund von Problemen im Webserver oder der Datenbank auftreten.

 1. (10) (BS0, BS4) (72) Für die Passwörter zu einem Benutzer soll über Ähnlichkeit (Levenshtein-Distanz) eine Liste mit absteigender Wahrscheinlichkeit für andere, möglicherweise von derselben natürlichen Person geführte Benutzerkonten erstellt werden. Diese sollen dann ebenfalls im UserInfo-Tab tabellarisch angezeigt werden.
---
## 4. Sonstiges
Themen, die keinem der zuvor genannten Bereiche eindeutig zugeordnet werden können.

1. 