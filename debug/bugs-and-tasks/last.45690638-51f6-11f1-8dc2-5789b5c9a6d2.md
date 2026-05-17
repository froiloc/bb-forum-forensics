# Fehler im Frontend
(Cache-buster-pre-extension: 45690638-51f6-11f1-8dc2-5789b5c9a6d2)

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
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/bugs-and-tasks/last.45690638-51f6-11f1-8dc2-5789b5c9a6d2.md
* Die Ausgabe von DevTools-Console:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/devtools-console/last.45690638-51f6-11f1-8dc2-5789b5c9a6d2.log
* Die Ausgabe von DevTools-Network:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/devtools-network/last.45690638-51f6-11f1-8dc2-5789b5c9a6d2.har
* Das aktuelle DOM des gesamten Dokuments als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-html.45690638-51f6-11f1-8dc2-5789b5c9a6d2.html
* Das aktuelle DOM des gesamten Body als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-body.45690638-51f6-11f1-8dc2-5789b5c9a6d2.html
* Das aktuelle DOM des gesamten Sidebar als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-sidebar.45690638-51f6-11f1-8dc2-5789b5c9a6d2.html
* Das aktuelle DOM des gesamten Main als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-main.45690638-51f6-11f1-8dc2-5789b5c9a6d2.html
* Das aktuelle DOM des Akkordeon 1 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-1.45690638-51f6-11f1-8dc2-5789b5c9a6d2.html
* Das aktuelle DOM des Akkordeon 2 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-2.45690638-51f6-11f1-8dc2-5789b5c9a6d2.html
* Das aktuelle DOM des Akkordeon 3 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-3.45690638-51f6-11f1-8dc2-5789b5c9a6d2.html
* Das aktuelle DOM des Akkordeon 4 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-4.45690638-51f6-11f1-8dc2-5789b5c9a6d2.html
* Das aktuelle DOM des Search-Modal als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-searchmodal.45690638-51f6-11f1-8dc2-5789b5c9a6d2.html
* Die Ausgabe des aktuellen Webservers:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/webserver-log/last.45690638-51f6-11f1-8dc2-5789b5c9a6d2.log
* Die aktuellen Screenshots:
https://github.com/froiloc/bb-forum-forensics/tree/1b5017a2f62c5a8f1825de76fc6edabb25d6bf66/debug/screenshots
***

## 1. Style / Layout / CSS
Hier werden CSS‑Fehler aufgeführt. Das sind Themen, bei denen die Anzeige funktionale oder optische Probleme hervorruft

 1. erledigt
 2. erledigt
 3. erledigt
 4. erledigt
 5. erledigt
 6. (0) (BS6) Ein Dark-Theme wäre cool. Ich persönlich mag helles Layout nicht. Ich fände es toll, wenn wir hier auch ein Dark-Theme anbieten könnten.
 7. erledigt
 8. erledigt
 9. erledigt
 10. erledigt
 11. erledigt
 12. erledigt
 13. erledigt
 14. erledigt
 15. erledigt
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
---
## 2. Funktionalität Frontend / Daten / JS
Hier werden Funktionsprobleme aufgeführt, die verhindern, dass der Ermittler mit dem Webwerkzeug arbeiten kann oder ihn dabei nicht im vorgesehenen Maße unterstützen oder behindern.

 1. erledigt
 2. erledigt
 3. erledigt
 4. (2) (BS6) Die Funktionalität für die Schaltfläche `⬇ Export ▾` fehlt.
 5. erledigt
 6. erledigt
 7. erledigt
 8. erledigt
 9. erledigt
10. erledigt
11. erledigt
12. erledigt
13. erledigt
14. erledigt
15. erledigt
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
31. erledigt
32. erledigt
33. erledigt
34. erledigt
35. erledigt
36. erledigt
37. erledigt
38. erledigt
39. erledigt
40. erledigt
41. erledigt
42. erledigt
43. erledigt
44. zurückgezogen
45. (10) (BS6) Möglicherweise wird der Fokus verloren, nachdem ein Autosave durchgeführt wurde. Ich bin aber nicht sicher. Ich konnte es nicht genau beobachten und nachstellen.
46. erledigt
47. erledigt
48. erledigt
49. erledigt
50. erledigt
51. erledigt
52. erledigt
53. erledigt
54. erledigt
55. erledigt
56. (20) (BS6) Es kommt noch immer zu Situationen, in denen nicht inline eingefügt werden kann und bei denen dann der Platzhalter nach einem Block eingefügt wird. In diesem Fall wurde der Platzhalter am Ende des Dokuments eingefügt, obwohl zuvor der Fokus in einem der vorderen Blöcke war. Der Cursor wurde zuvor aktiv in einen Text in einem Block platziert. Erst dann wurde die Schaltfläche `+ Einfügen` für `user.aliases` angeklickt. Der Platzhalter wurde dann zunächst am Ende des Dokuments eingefügt. Nach erneutem Platzieren des Cursors im ursprünglichen Block und erneutem Klicken auf `+Einfügen` wurde `user.aliases` dann korrekt inline an der gewünschten Stelle gesetzt.
57. erledigt
58. erledigt
59. erledigt
60. erledigt
61. (20) (BS6) Es kommt vor, und das ist wieder so ein "Beim ersten Versuch klappt es nicht, bei den folgenden Versuchen aber schon"-Fehler, dass beim Einfügen eines Standard-Elements dieses nicht an der Position nach dem aktuellen Block, sondern am Anfang des Dokuments eingefügt wird. Das sollte nicht sein. Hier müssen wir wieder schauen, wie wir da herausfinden, woran das liegen kann. Ich wünsche daher, dass im Consolen-Output die Aktualisierung der Cursor-Position angezeigt wird, wenn sie durch Mousedown oder Keydown erfasst wird. Und es soll vor dem Setzen des neuen gespeicherten Wertes dessen derzeitiger Wert aufgeben werden. Und ich wünsche, dass beim Einfügen eines Elements in der Console die Position des Cursors angegeben wird und die Position, an der das neue Element eingefügt wird. Das wird uns hoffentlich rasch helfen, das Problem zu lösen.
62. (20) (BS6) Nach dem Laden der Seite wurde in `Bausteine` > `Module` > `Standard` das Element per Drag and Drop in den `Editor.js` an eine Stelle am Anfang gezogen und losgelassen. Es wurde aber nicht an dieser Stelle, sondern ganz am Ende des Dokuments eingefügt.
63. erledigt
64. erledigt
65. erledigt
66. erledigt
67. erledigt
68. erledigt
69. erledigt
70. erledigt
71. erledigt
72. erledigt
73. erledigt
74. erledigt
75. erledigt
76. erledigt
77. erledigt
78. erledigt
79. erledigt
80. erledigt
81. erledigt
82. erledigt
83. erledigt
84. erledigt
85. erledigt
86. erledigt
87. erledigt
88. erledigt
89. erledigt
90. erledigt
91. erledigt
92. erledigt
93. erledigt
94. erledigt
95. erledigt
96. (10) (BS6) Im Berichtseditor können Einzeldaten nicht per Drag-and-drop eingefügt werden. Nur das Einfügen über die `+Einfügen` Schaltfläche funktioniert.
97. erledigt
98. (25) (BS6) Wenn ich in Editor.js einen Block lösche, dauert es bis zu einer halben Minute, damit der Block auch im Formular-Bereich verschwindet. Das ist sehr irritierend. Das Löschen eines Blocks sollte ein Autosave auslösen.
99. (40) (BS6) Ab und zu, wenn ich Blöcke gelöscht habe und neue Blöcke erstelle, dann kann ich bei diesen neuen Blöcken nicht kommentieren. Nach einer Weile klappt es dann. :-/ Heisenbug? Delayed saving issue?
100. (10) (BS6) Leere Blöcke erscheinen nicht als Block im Formularbereich. Sie werden quasi ignoriert. Liegt das daran, dass leere Blöcke nicht gespeichert werden?
101. (30) (BS6) Wenn ich einen neuen Bericht erstelle und dann zu einem bestehenden Bericht wechsle, wird dieser nicht angezeigt.
102. erledigt
103. (40) (BS6) Wenn ein neuer Bericht erstellt wird, erzeugt der keinen leeren Bericht mehr.
104. (40) (BS6) Das Doppelklicken auf ein Modul erzeugt keinen neuen Block im Editor.js. Kann sein, dass das mit dem Löschen eines vorher existierenden Blocks zusammenhängt.
105. (40) (BS6) Das Doppelklicken auf ein Modul erzeugt zwei unterschiedliche Blocks. Kann auch sein, dass das ein Anzeigeproblem ist, dass nach dem Löschen eines Blocks dieser wieder angezeigt wird, weil er noch nicht durch einen Autosave final entfernt wurde.
106. erledigt
107. erledigt
108. (5) (BS6) Wenn das Modal für das Erstellen eines neuen Berichts angezeigt wird, dann soll auch das Betätigen der Entertaste den Bericht erzeugen und nicht nur ein Klick auf die Schaltfläche `Anlegen`. Gleichfalls soll das Drücken auf ESC das Feld schließen und gleichbedeutend sein mit einem Klick auf die Schaltfläche `Abbrechen`.
109. (5) (BS6) Es ist sicherzustellen, dass, wenn im Formular-Bereich ein Block ausgewählt und umrahmt ist, dieser Block auch im `Editor.js`-Bereich umrahmt ist.
110. (5) (BS6) Um das Verhalten der Bausteine gleich zu machen, sollen auch Standard-Blöcke und Einzeldaten per Doppelklick eingefügt werden können. Derzeit ist das nur für Module möglich.
111. (10) (BS6) Es kommt vor, dass ein Klick auf `+Einfügen` bei einem Einzeldaten-Platzhalter den Platzhalter nicht beim Cursor einfügt, sondern am Ende des `Editor.js` in einem neuen Block.
112. (20) (BS6) Wenn ein Block in `Editor.js` per Editor-Toolbar gelöscht wurde, und dann binnen 2 Sekunden ein neues Modul eingefügt wird (Doppelklick), dann erscheint der gelöschte Block wieder.
---
## 3. Funktionalität Backend / Python / SQLite3-Datenbank
Hier werden Funktionsprobleme aufgeführt, die aufgrund von Problemen im Webserver oder der Datenbank auftreten.

 1. erledigt
 2. erledigt
 3. erledigt
 4. erledigt
 5. erledigt
 6. erledigt
 7. erledigt
 8. erledigt
 9. erledigt
 10. erledigt
 11. erledigt
---
## 4. Sonstiges
Themen, die keinem der zuvor genannten Bereiche eindeutig zugeordnet werden können.

1. erledigt