# Fehler im Frontend
(Cache-buster-pre-extension: 6e5a093a-586c-11f1-93ad-5baa6b35f409)

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

Quellen zum Debuggen:
* Dieses Dokument mit den Arbeitsanweisungen und Problembeschreibungen:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/bugs-and-tasks/last.6e5a093a-586c-11f1-93ad-5baa6b35f409.md
* Die Ausgabe von DevTools-Console:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/devtools-console/last.6e5a093a-586c-11f1-93ad-5baa6b35f409.log
* Die Ausgabe von DevTools-Network:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/devtools-network/last.6e5a093a-586c-11f1-93ad-5baa6b35f409.har
* Das aktuelle DOM des gesamten Dokuments als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-html.6e5a093a-586c-11f1-93ad-5baa6b35f409.html
* Das aktuelle DOM des gesamten Body als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-body.6e5a093a-586c-11f1-93ad-5baa6b35f409.html
* Das aktuelle DOM des gesamten Sidebar als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-sidebar.6e5a093a-586c-11f1-93ad-5baa6b35f409.html
* Das aktuelle DOM des gesamten Main als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-main.6e5a093a-586c-11f1-93ad-5baa6b35f409.html
* Das aktuelle DOM des Akkordeon 1 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-1.6e5a093a-586c-11f1-93ad-5baa6b35f409.html
* Das aktuelle DOM des Akkordeon 2 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-2.6e5a093a-586c-11f1-93ad-5baa6b35f409.html
* Das aktuelle DOM des Akkordeon 3 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-3.6e5a093a-586c-11f1-93ad-5baa6b35f409.html
* Das aktuelle DOM des Akkordeon 4 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-4.6e5a093a-586c-11f1-93ad-5baa6b35f409.html
* Das aktuelle DOM des Search-Modal als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-searchmodal.6e5a093a-586c-11f1-93ad-5baa6b35f409.html
* Die Ausgabe des aktuellen Webservers:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/webserver-log/last.6e5a093a-586c-11f1-93ad-5baa6b35f409.log
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
 2. (10) (BS6) Die Bausteine werden nicht geladen
 3. (10) (BS6) Die Form zum Erstellen neuer und zur Auswahl bestehender Berichte fehlt.
 4. (10) (BS6) Alle Schaltflächen sind inaktiv.
 5. (10) (BS6) Die Elemente des Akkordeons reagiern nicht auf Anklicken.
---
## 3. Funktionalität Backend / Python / SQLite3-Datenbank
Hier werden Funktionsprobleme aufgeführt, die aufgrund von Problemen im Webserver oder der Datenbank auftreten.

 1. 
---
## 4. Sonstiges
Themen, die keinem der zuvor genannten Bereiche eindeutig zugeordnet werden können.

1. 