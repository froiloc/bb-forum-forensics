# Fehler auf der Berichtsseite
(Cache-buster-pre-extension: 50248a60-4cbb-11f1-ba72-2b6a701189ef)

Ich werde in dieser Liste fortlaufend die von mir beobachteten Fehler aufführen.
Falls diese abgeschlossen und verworfen wurden, werde ich sie durchstreichen. Alles, was nicht durchgestrichen ist, ist also noch offen und muss bearbeitet werden.
Am Anfang jedes Eintrages kann eine Zahl stehen. Je höher der Wert, desto dringender ist das Problem und sollte daher vorrangig behoben werden.
Themen gleicher Art sollten in einem gemeinsamen Build behoben werden.
Nach der Bearbeitung ist das behobene Problem anzugeben. Und zwar mit Kapitel (1 = CSS, 2 = JS, 3 = PY/SQL, 4 = Sonst) und der Nummer in der Liste.

Quellen zum Debuggen:
* Dieses Dokument mit den Arbeitsanweisungen und Problembeschreibungen:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/bugs-and-tasks/last.50248a60-4cbb-11f1-ba72-2b6a701189ef.md
* Die Ausgabe von DevTools-Console:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/devtools-console/last.50248a60-4cbb-11f1-ba72-2b6a701189ef.log
* Die Ausgabe von DevTools-Network:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/devtools-network/last.50248a60-4cbb-11f1-ba72-2b6a701189ef.har
* Das aktuelle DOM des gesamten Dokuments als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-html.50248a60-4cbb-11f1-ba72-2b6a701189ef.html
* Das aktuelle DOM des gesamten Body als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-body.50248a60-4cbb-11f1-ba72-2b6a701189ef.html
* Das aktuelle DOM des gesamten Sidebar als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-sidebar.50248a60-4cbb-11f1-ba72-2b6a701189ef.html
* Das aktuelle DOM des gesamten Main als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-main.50248a60-4cbb-11f1-ba72-2b6a701189ef.html
* Das aktuelle DOM des Akkordeon 1 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-1.50248a60-4cbb-11f1-ba72-2b6a701189ef.html
* Das aktuelle DOM des Akkordeon 2 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-2.50248a60-4cbb-11f1-ba72-2b6a701189ef.html
* Das aktuelle DOM des Akkordeon 3 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-3.50248a60-4cbb-11f1-ba72-2b6a701189ef.html
* Das aktuelle DOM des Akkordeon 4 als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last-accordion-4.50248a60-4cbb-11f1-ba72-2b6a701189ef.html
* Die Ausgabe des aktuellen Webservers:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/webserver-log/last.50248a60-4cbb-11f1-ba72-2b6a701189ef.log
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
 6. (0) Ein Dark-Theme wäre cool. Ich persönlich mag helles Layout nicht. Ich fände es toll, wenn wir hier auch ein Dark-Theme anbieten könnten.
 7. erledigt
 8. erledigt
 9. erledigt
 10. erledigt
 11. (1) Es wäre cool, wenn man die Breite von `<main>` und `<aside>` über einen Schiebebalken `⇹` oder `⇔`dynamisch könnte. `<div class="group w-2 relative h-full cursor-col-resize -mr-1 z-30 grid place-items-center max-md:hidden"><div class="absolute top-0 bottom-0 right-1 w-[0.5px] bg-border-300 transition-all group-hover:delay-75 group-hover:bg-accent-100 group-hover:w-px group-hover:translate-x-[0.5px]"></div><div class="h-6 w-2 relative rounded-full border-0.5 bg-bg-100 shadow border-border-300 transition duration-200 group-hover:delay-75 group-hover:border-accent-900 group-hover:bg-accent-900 cursor-col-resize"></div></div>`So regelt das die Oberfläche bei `claude.ai` mit dem Trenner.
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
---
## 2. Funktionalität Frontend / Daten / JS
Hier werden Funktionsprobleme aufgeführt, die verhindern, dass der Ermittler mit dem Webwerkzeug arbeiten kann oder ihn dabei nicht im vorgesehenen Maße unterstützen oder behindern.

 1. (3) Die Einträge für `.as-annotation` innerhalb von `#accordion-body-annotations` müssen mehr Substanz erhalten. Ausblenden kann man die Daten immer noch, aber da sein müssen sie! Es soll neben den bestehenden `<div>` und `<span>` noch Angaben zu Quelle mit Verweis, markierter Text (zumindest die ersten 200 Zeichen), Datum und Zeit der Annotation, Tags und Notiz abgelegt sein. Der Name des Investigators ist mit der Klasse `as-ann-investigator` zu kennzeichnen. Alle anderen neuen Punkte sind entsprechend ebenfalls mit einer eigenen passenden Klasse zu versehen.
 2. (8) Bei Annotationen soll das Konzept zum Ausblenden geändert werden. Statt der Checkbox `bereits verankerte ausblenden`, sollen dort Schalter sein. Ausblenden: `Verankerte`, `Tags`, `Ermittler`, `Zitate`, `Quelle`, `Notizen` Durch CSS sollen diese Checkboxen dann die betroffenen Teile ausblenden. `#accordion-body-annotations:has(#as-hide-anchored[checked]) .as-annotation.as-ann-anchored {display: none}` Warum löschen wir die Elemente hier, statt sie einfach nur auszublenden? Das leuchtet mir nicht ein.
 3. erledigt
 4. (2) Die Funktionalität für die Schaltfläche `⬇ Export ▾` fehlt.
 5. erledigt
 6. erledigt
 7. erledigt
 8. erledigt
 9. (10) Verankerte Annotationen werden im Report nicht angezeigt oder gerendert.
10. (10)  Das `Editor.js`-Modul `Beweismittelgruppe` ist nicht mehr funktional. Es erlaubt kein Hinzufügen von Belegen. Weder per Drag-and-Drop noch durch Klicken auf `+ Beleg hinzufügen`.
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
45. (10) Möglicherweise wird der Fokus verloren, nachdem ein Autosave durchgeführt wurde. Ich bin aber nicht sicher. Ich konnte es nicht genau beobachten und nachstellen.
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
56. (20) Es kommt noch immer zu Situationen, in denen nicht inline eingefügt werden kann und bei denen dann der Platzhalter nach einem Block eingefügt wird. In diesem Fall wurde der Platzhalter am Ende des Dokuments eingefügt, obwohl zuvor der Fokus in einem der vorderen Blöcke war. Der Cursor wurde zuvor aktiv in einen Text in einem Block platziert. Erst dann wurde die Schaltfläche `+ Einfügen` für `user.aliases` angeklickt. Der Platzhalter wurde dann zunächst am Ende des Dokuments eingefügt. Nach erneutem Platzieren des Cursors im ursprünglichen Block und erneutem Klicken auf `+Einfügen` wurde `user.aliases` dann korrekt inline an der gewünschten Stelle gesetzt.
57. erledigt
58. (30) Vorschlag für das 2.47 Problem mit dem ersten Klick. Können wir einen `mousedown` und `keydown`-Listener implementieren, der die _savedCursorRange setzt? Das müsste vor dem Click feuern und dann wäre der Wert gesetzt. Akzeptabel ist der "Restzustand" nur mit Bauchschmerzen. Aber ich würde das vorerst zurückstellen. Auch wenn ich mich freuen würde, wenn wir durch ein aggressiveres Debug-Logging hier mehr Gewissheit erlangen könnten. Speziell wenn der Wert für den Cursor nicht da ist, möchte ich einen vollumfänglichen Zustand des Systems kennen, um Schlussfolgerungen ziehen zu können.
59. erledigt
60. erledigt
61. (20) Es kommt vor, und das ist wieder so ein "Beim ersten Versuch klappt es nicht, bei den folgenden Versuchen aber schon"-Fehler, dass beim Einfügen eines Standard-Elements dieses nicht an der Position nach dem aktuellen Block, sondern am Anfang des Dokuments eingefügt wird. Das sollte nicht sein. Hier müssen wir wieder schauen, wie wir da herausfinden, woran das liegen kann. Ich wünsche daher, dass im Consolen-Output die Aktualisierung der Cursor-Position angezeigt wird, wenn sie durch Mousedown oder Keydown erfasst wird. Und es soll vor dem Setzen des neuen gespeicherten Wertes dessen derzeitiger Wert aufgeben werden. Und ich wünsche, dass beim Einfügen eines Elements in der Console die Position des Cursors angegeben wird und die Position, an der das neue Element eingefügt wird. Das wird uns hoffentlich rasch helfen, das Problem zu lösen.
62. (20) Nach dem Laden der Seite, wurde in `Bausteine` > `Module` > `Standard` das Element per Drag and Drop in den `Editor.js` an eine Stelle am Anfang gezogen und losgelassen. Es wurde aber nicht an dieser Stelle, sondern ganz am Ende des Dokuments eingefügt.
63. erledigt
64. (20) Das Drag-and-Drop von Modulen klappt noch nicht. Einfügen per Klick auf `+Einfügen` klappt. Aber per Drag-and-Drop nicht. Es wird dann nur ein leerer Paragraph als Block eingefügt.
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
---
## 4. Sonstiges
Themen, die keinem der zuvor genannten Bereiche eindeutig zugeordnet werden können.

1. erledigt