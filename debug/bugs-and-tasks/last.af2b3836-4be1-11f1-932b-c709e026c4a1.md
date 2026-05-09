# Fehler auf der Berichtsseite
(Cache-buster-pre-extension: af2b3836-4be1-11f1-932b-c709e026c4a1)

Ich werde in dieser Liste fortlaufend die von mir beobachteten Fehler aufführen.
Falls diese abgeschlossen und verworfen wurden, werde ich sie durchstreichen. Alles, was nicht durchgestrichen ist, ist also noch offen und muss bearbeitet werden.
Am Anfang jedes Eintrages kann eine Zahl stehen. Je höher der Wert, desto dringender ist das Problem und sollte daher vorrangig behoben werden.
Themen gleicher Art sollten in einem gemeinsamen Build behoben werden.
Nach der Bearbeitung ist das behobene Problem anzugeben. Und zwar mit Kapitel (1 = CSS, 2 = JS, 3 = PY/SQL, 4 = Sonst) und der Nummer in der Liste.

Quellen zum Debuggen:
* Dieses Dokument mit den Arbeitsanweisungen und Problembeschreibungen:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/bugs-and-tasks/last.af2b3836-4be1-11f1-932b-c709e026c4a1.md
* Die Ausgabe von DevTools-Console:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/devtools-console/last.af2b3836-4be1-11f1-932b-c709e026c4a1.log
* Die Ausgabe von DevTools-Network:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/devtools-network/last.af2b3836-4be1-11f1-932b-c709e026c4a1.har
* Das aktuelle DOM als HTML:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/dom-dump/last.af2b3836-4be1-11f1-932b-c709e026c4a1.html
* Die Ausgabe des aktuellen Webservers:
https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/webserver-log/last.af2b3836-4be1-11f1-932b-c709e026c4a1.log
* Die aktuellen Screenshots:
https://github.com/froiloc/bb-forum-forensics/tree/1b5017a2f62c5a8f1825de76fc6edabb25d6bf66/debug/screenshots
***

## 1. Style / Layout / CSS
Hier werden CSS‑Fehler aufgeführt. Das sind Themen, bei denen die Anzeige funktionale oder optische Probleme hervorruft

 1. (10) Die Reiter in Annotationen nutzen bislang nicht die Symbole, welche auch in der Toolbar des Hauptfensters genutzt werden. Das Aussehen soll identisch sein! Der Anwender soll das wiedererkennen können.
 2. (20) Die Reihenfolge der Reiter in Annotationen entspricht noch immer nicht der Reihenfolge in der Toolbar des Hauptfensters. Die erwartete Reihenfolge lautet: PER, LOC, 176, 184, OPF, SON
 3. erledigt
 4. erledigt
 5. erledigt
 6. (0) Ein Dark-Theme wäre cool. Ich persönlich mag helles Layout nicht. Ich fände es toll, wenn wir hier auch ein Dark-Theme anbieten könnten.
 7. erledigt
 8. erledigt
 9. erledigt
 10. erledigt
 11. (1) Es wäre cool, wenn man die Breite von `<main>` und `<aside>` über einen Schiebebalken `⇹` oder `⇔`dynamisch könnte.
 12. erledigt
 13. erledigt
 14. erledigt
 15.  erledigt
 16.  erledigt
 17. erledigt
 18. erledigt
 19. erledigt
 20. erledigt
21. (20) Der Scrollbalken in `#mp-list` da, liegt aber am falschen Element. `#accordion-body-blocks {flex-direction: row;}` hilft, aber es sorgt dafür, dass dieses div nicht mehr die volle Breite einnimmt.
22. (20) Die Visualisierung des Speicherns gefällt mir nicht! Ich möchte: Keine Aktion (default) `.save-indicator--idle`: graue, leicht blury Diskette `🖫`; aktives Speichern `.save-indicator--saving`: grüner, pulsierender Rahmen um das Symbole. Diskette ist grün; Speichern erfolgreich `.save-indicator--saved`: Diskette ist für 5 Sekunden grün wird dann wieder default-grau. Speichern  `.save-indicator--failed`fehlgeschlagen: Diskette ist rot. Dauerhaft. Bis Speichern wieder erfolgreich ist.
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
11. (8) Das Einfügen von `Standard`-Elementen per Drag-and-Drop funktioniert nicht. Weder mit den Elementen bei der Anzeige in `Alle` noch bei `Standard`.
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
30. (12) Wenn die Blöcke umsortiert werden, wird dem im Formular-Bereich nicht Rechnung getragen. Dort muss die Sortierung ebenfalls angepasst werden. Gleiches gilt, wenn Blöcke hinzugefügt oder entfernt werden.
31. erledigt
32. erledigt
33. erledigt
34. erledigt
35. erledigt
36. erledigt
37. erledigt
38. erledigt
39. (40) Das Löschen eines Blocks im Editor ist nicht mehr möglich. Sie werden optisch im Editor gelöscht. Aber nach einem Reload der Seite sind alle gelöschten Elemente wieder da.
40. (50) Das Speichern wird noch immer nicht in Echtzeit angezeigt oder bleibt aus. Ich habe mit build 132 einen Eintrag hinter dem Wort "Stadt" gemacht. Aber der wurde nicht gespeichert.
41. erledigt
42. erledigt
43. (30) Das automatische Speichern nach dem Einfügen von Platzhaltern funktioniert nicht.
44. (10) Wenn der `Kommentare` Akkordeon-Bereich aktiv ist, sollte ein Klick in einen Block die zugehörigen Kommentare dieses Bereichs anzeigen. ABER es darf nicht der Fokus auf die Kommentareingabe für einen neuen Kommentar gesetzt werden! Das zusätzliche Setzen des Fokus darf und muss grundsätzlich nur passieren, wenn die Schaltfläche `Kommentieren` geklickt wird.
45. (10) Möglicherweise wird der Fokus verloren, nachdem ein Autosave durchgeführt wurde. Ich bin aber nicht sicher. Ich konnte es nicht genau beobachten und nachstellen.
46. (15) Es muss eine Möglichkeit geben, nach einem Platzhalter den Cursor zu setzen, um dahinter Text zu ergänzen. Gleiches gilt für davor. Vielleicht kann man ein Space um das Tag ergänzen oder einen längeren Space oder ein Zeichen mit null Breite. In jedem Fall muss es möglich sein, um einen einzelnen Cursor herum Text zu schreiben!
47. (20) Wir sind kurz vor dem totalen Erfolg. NUR BEIM ERSTEN MAL klappt das mit dem Einfügen inline noch nicht (zuverlässig immer). Ab dem zweiten Klick auf die Schaltfläche funktioniert es. Wir müssen also nur noch herausfinden, warum es beim ersten Mal nicht klappt, dann können wir das Thema endlich zumachen. :-)
48. (20) Beim Einfügen eines Platzhalters muss zuvor geprüft werden, dass der Cursor nicht bereits in einem Platzhalter steht. Dann muss entweder die Aktion abgelehnt werden oder das Element wird ans Ende des Platzhalters, in dem der Cursor steckt, eingefügt.
49. (10) Wenn die Platzhalter im Formular ausgefüllt sind, sollten die Platzhalter im Editor diese Eingabe auch rendern.
50. (20) Wir müssen verhindern, dass der Benutzer in Platzhaltern im Editor schreibt. Ideen?
---
## 3. Funktionalität Backend / Python / SQLite3-Datenbank
Hier werden Funktionsprobleme aufgeführt, die aufgrund von Problemen im Webserver oder der Datenbank auftreten.

 1. erledigt
 2. erledigt
 3. erledigt
 4. erledigt
 5. erledigt
 6. erledigt
 7. (30) Das Speichern von eingetragenen Werten für Inline-Platzhalter wird vom Backend nicht akzeptiert. Es erscheint `report_editor.js:1179 report_editor.js: Platzhalter-Save fehlgeschlagen: realname {error: "'block_data' fehlt oder ist kein Objekt", code: 'MISSING_FIELD'}
_onPlaceholderFieldSave @ report_editor.js:1179
await in _onPlaceholderFieldSave
_saveField @ placeholder_wizard.js:484
(anonymous) @ placeholder_wizard.js:473
setTimeout
_scheduleFieldSave @ placeholder_wizard.js:472
(anonymous) @ placeholder_wizard.js:401Understand this warning`
---
## 4. Sonstiges
Themen, die keinem der zuvor genannten Bereiche eindeutig zugeordnet werden können.

1. erledigt