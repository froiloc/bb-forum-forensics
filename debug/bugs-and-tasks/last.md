# Fehler auf der Berichtsseite
Ich werde in dieser Liste fortlaufend die von mir beobachteten Fehler aufführen.
Falls diese abgeschlossen und verworfen wurden, werde ich sie durchstreichen. Alles, was nicht durchgestrichen ist, ist also noch offen und muss bearbeitet werden.
Am Anfang jedes Eintrages kann eine Zahl stehen. Je höher der Wert, desto dringender ist das Problem und sollte daher vorrangig behoben werden.
Themen gleicher Art sollten in einem gemeinsamen Build behoben werden.
Nach der Bearbeitung ist das behobene Problem anzugeben. Und zwar mit Kapitel (1 = CSS, 2 = JS, 3 = PY/SQL, 4 = Sonst) und der Nummer in der Liste.

***

## 1. Style / Layout / CSS
Hier werden CSS‑Fehler aufgeführt. Das sind Themen, bei denen die Anzeige funktionale oder optische Probleme hervorruft

 1. (10) Die Reiter in Annotationen nutzen bislang nicht die Symbole, welche auch in der Toolbar des Hauptfensters genutzt werden. Das Aussehen soll identisch sein! Der Anwender soll das wiedererkennen können.
 2. (20) Die Reihenfolge der Reiter in Annotationen entspricht noch immer nicht der Reihenfolge in der Toolbar des Hauptfensters. Die erwartete Reihenfolge lautet: PER, LOC, 176, 184, OPF, SON
 3. ~~(1) Der Rahmen von `.as-list` soll dieselbe Farbe haben wie der aktive Reiter. Also bei geöffnetem PER soll der Rahmen `#f5c842` (gelb) sein. Lösung: `#accordion-body-annotations:has(.as-tab[data-cat="CAT_PERSON"].as-tab--active) .as-list {border-color: #f5c842}`~~
 4. ~~(1) Die Höhe von `as-list` ist falsch. `#accordion-body-annotations .as-list {max-height: 380px;}` muss entfernt werden.~~
 5. ~~(1) `.as-annotation` soll `margin: 0px 5px;` erhalten, um die Ränder sich nicht berühren zu lassen.~~
 6. (0) Ein Dark-Theme wäre cool. Ich persönlich mag helles Layout nicht. Ich fände es toll, wenn wir hier auch ein Dark-Theme anbieten könnten.
 7. ~~(2) Die Überschrift für das Akkordeon sollte größer sein. `font-size: 17px` für `.support-accordion-toggle` fände ich besser.~~
 8. ~~(1) Beim Wechsel der Support-Akkordeon-Abschnitte wäre eine sanfte Animation schön. Das machte das Ganze geschmeidiger.~~
 9. ~~(8) Die Schaltfläche `✎ Drucken` verwendet das falsche Symbol. Es soll `🖶` verwendet werden.~~
 10. ~~(1) Das Element `#editor-report-title`drückt die oberste Leiste nach unten. `#editor-report-title` sollte verschoben werden, und zwar zwischen `#report-action-bar-title` und `#report-action-bar-buttons` und es sollte wahrscheinlich besser ein `<div>` Tag sein, statt des `<span>` das es bisher ist.~~
 11. (1) Es wäre cool, wenn man die Breite von `<main>` und `<aside>` über einen Schiebebalken `⇹` oder `⇔`dynamisch könnte.
 12. ~~(1) Die Breite des Bereichs von `Editor.js`~~ 
 13. ~~(1) Die Höhe von `.mp-list` ist durch `max-height: 340px` beschränkt. Dieser Eintrag muss entfernt werden.~~
 14. ~~(5) Beim Hover über ein `Editor.js` Element verschiebt die Zeile mit Autor, Datum, Uhrzeit und Kommentieren-Schaltfläche die Position des Blocks. Das stört den Lesefluss. Die Elemente sollten `fixed` eingeblendet werden.~~
 15.  ~~(7) Der Scrollbar im Bereich `Bausteine` ist nicht mehr da. Damit sind tiefer liegende Elemente aus der Liste nicht mehr erreichbar.~~
 16.  ~~(5) Der Blur im `Formular` Bereich ist etwas zu aggressiv. Und ich glaube, dass er zweimal verwendet wird. Also additiv. Das sollte nicht sein.~~
 17. ~~(20) Damit Flex auch überall funktioniert, muss `.support-accordion-body` noch um `display: flex` ergänzt werden. Sonst zeigt das keine Wirkung.~~
 18. ~~(20) Ebenso muss dann `.as-panel` um `flex: 1 1 0%` ergänzt werden.~~
 19. ~~(20) Die Blöcke in `Formular` sind nun senkrecht. Um das zu ändern, muss `#accordion-body-form` den Eintrag `flex-direction: column` erhalten.~~
 20. ~~(15) Die um das fokussierte Formular liegenden Blöcke sollen etwas schwächer geblurt werden. Daher bitte folgendes CSS einfügen: `.pf-block-group.pf-block-group--focused + .pf-block-group.pf-block-group--blurred, .pf-block-group.pf-block-group--blurred:has(+ .pf-block-group.pf-block-group--focused) {
    filter: blur(0.7px);
    opacity: 1;
    cursor: pointer;
}`~~
21. (20) Der Scrollbalken in `#mp-list` da, liegt aber am falschen Element. `#accordion-body-blocks {flex-direction: row;}` hilft, aber es sorgt dafür, dass dieses div nicht mehr die volle Breite einnimmt.
22. (20) Die Visualisierung des Speicherns gefällt mir nicht! Ich möchte: Keine Aktion (default) `.save-indicator--idle`: graue, leicht blury Diskette `🖫`; aktives Speichern `.save-indicator--saving`: grüner, pulsierender Rahmen um das Symbole. Diskette ist grün; Speichern erfolgreich `.save-indicator--saved`: Diskette ist für 5 Sekunden grün wird dann wieder default-grau. Speichern  `.save-indicator--failed`fehlgeschlagen: Diskette ist rot. Dauerhaft. Bis Speichern wieder erfolgreich ist.
---
## 2. Funktionalität Frontend / Daten / JS
Hier werden Funktionsprobleme aufgeführt, die verhindern, dass der Ermittler mit dem Webwerkzeug arbeiten kann oder ihn dabei nicht im vorgesehenen Maße unterstützen oder behindern.

 1. (3) Die Einträge für `.as-annotation` innerhalb von `#accordion-body-annotations` müssen mehr Substanz erhalten. Ausblenden kann man die Daten immer noch, aber da sein müssen sie! Es soll neben den bestehenden `<div>` und `<span>` noch Angaben zu Quelle mit Verweis, markierter Text (zumindest die ersten 200 Zeichen), Datum und Zeit der Annotation, Tags und Notiz abgelegt sein. Der Name des Investigators ist mit der Klasse `as-ann-investigator` zu kennzeichnen. Alle anderen neuen Punkte sind entsprechend ebenfalls mit einer eigenen passenden Klasse zu versehen.
 2. (8) Bei Annotationen soll das Konzept zum Ausblenden geändert werden. Statt der Checkbox `bereits verankerte ausblenden`, sollen dort Schalter sein. Ausblenden: `Verankerte`, `Tags`, `Ermittler`, `Zitate`, `Quelle`, `Notizen` Durch CSS sollen diese Checkboxen dann die betroffenen Teile ausblenden. `#accordion-body-annotations:has(#as-hide-anchored[checked]) .as-annotation.as-ann-anchored {display: none}` Warum löschen wir die Elemente hier, statt sie einfach nur auszublenden? Das leuchtet mir nicht ein.
 3. (10) Für `.mp-item mp-item--standard` fehlt das `<div>` für den Eintrag `mp-item-preview` also der beschreibende Text. Auch hier soll als CSS-Style dasselbe gelten wie im Bereich `Standard`.
 4. (2) Die Funktionalität für die Schaltfläche `⬇ Export ▾` fehlt.
 5. (8) Die Funktionalität für die Schaltfläche `✎ Drucken` fehlt.
 6. ~~(5) Beim Hover über das Schloss-Symbol `🔓` von `#report-lock-indicator` ist nicht klar, was es jetzt aussagen soll. Beim Hover steht da `Lock-Status`, aber nicht der Zustand. Das ist unzureichend. Hier muss eine Nachricht hin, die dem Ermittler eine Information vermittelt.  Gleiches gilt für `#report-lock-status`.~~
 7. (2) Die Funktionalität für die Schaltfläche `🔄 Aktualisieren` fehlt.
 8. ~~(6) Im Akkordeon-Abschnitt für `Formular` (Warum hat alles eine ID, aber das nicht?) steht, obwohl ein Bericht geöffnet ist, `Kein Bericht geöffnet`. Das ist irritierend, weil nicht wahr. Der Text, wenn der Editor verfügbar ist, muss anders lauten. Wir benötigen hier einen weiteren Platzhalter. Dieser kann/sollte per CSS geschaltet werden. Nachfolgendes ist die Idee:`#report-workspace:has(#report-selector-container select:checked) .pf-empty-state {display: none;}` Ich bin mir nicht sicher, ob `select:checked` hier korrekt ist.~~
 9. (10) Verankerte Annotationen werden im Report nicht angezeigt oder gerendert.
 10. (10)  Das `Editor.js`-Modul `Beweismittelgruppe` ist nicht mehr funktional. Es erlaubt kein Hinzufügen von Belegen. Weder per Drag-and-Drop noch durch Klicken auf `+ Beleg hinzufügen`.
 11. (8) Das Einfügen von `Standard`-Elementen per Drag-and-Drop funktioniert nicht. Weder mit den Elementen bei der Anzeige in `Alle` noch bei `Standard`.
 12. ~~(4) Kommentare können noch nicht gemacht werden. Es gibt keine entsprechende Funktion, die beim Hovern über einem Block im `Editor.js`-Bereich angezeigt wird.~~
 13. ~~(8) Beim Wechseln in den Akkordeon-Bereich "Bausteine" werden die falschen Daten in `#mp-list` angezeigt. Aktiv ist die Schaltfläche `Module` und auch die Kategorien von `Alle` bis `Standard` werden als Schaltflächen angezeigt, aber der Inhalt von `#mp-list` entspricht den zuvor angezeigten Daten von `Einzeldaten`. Das passiert nur, wenn beim letzten Öffnen von `Bausteine` der Bereich `Einzeldaten` angezeigt wurde, da der Bereich scheinbar immer mit einem aktiven `Module` geöffnet wird, ohne allerdings den Inhalt in `#mp-list` anzupassen. Die Schaltflächen `Alle` bis `Standard` sind aber ohne Funktion. Damit sie wieder funktionieren, muss erneut auf `Module` geklickt werden.~~
 14. ~~(10) Nachdem in `Formular` das Formular gewechselt wurde, wird im Editor zwar der pulsierende, blaue Rahmen angezeigt, aber nach einem Wechsel des Formulars nicht mehr gelöscht. Er bleibt dauerhaft angezeigt.~~
 15. ~~(5) Das Hovern über einem Block in `Editor.js` erzeugt nun zwar die Schaltflächen für `Kommentieren` und in der Support-Sidebar wird auch in den Bereich `Kommentare` gewechselt, aber es erscheint noch immer `Kein Block ausgewählt.` und eine Möglichkeit zum Kommentieren gibt es nicht.~~
 16. ~~(20) Schwerer Typenfehler: `editorjs.mjs:7747 Uncaught TypeError: Cannot read properties of undefined (reading 'updateCurrentInput')
    at Qo.setCurrentBlockByChildNode (editorjs.mjs:7747:88)
    at n.setToBlock (editorjs.mjs:8193:23)
    at n.setToTheLastBlock (editorjs.mjs:8235:14)
    at fn.documentTouched (editorjs.mjs:10898:77)
    at HTMLDivElement.documentTouchedListener (editorjs.mjs:10603:12)` verhindert, dass im Block geschrieben werden kann.~~
17. ~~(15) Nach dem Neuladen erscheint die Fehlermeldung `Netzwerkfehler: TypeError: Cannot set properties of null (setting 'disabled')` über dem `Editor.js`-Bereich.~~
18. ~~(12) DevTools Console zeigt:~~
```
Blocked aria-hidden on an element because its descendant retained focus. The focus must not be hidden from assistive technology users. Avoid using aria-hidden on a focused element or its ancestor. Consider using the inert attribute instead, which will also prevent focus. For more details, see the aria-hidden section of the WAI-ARIA specification at https://w3c.github.io/aria/#aria-hidden.
Element with focus: <button.block-meta-comment-btn>
Ancestor with aria-hidden: <div.block-meta-bar> <div class=​"block-meta-bar" aria-hidden=​"true">​flex<span class=​"block-meta-author">​paul​</span>​<span class=​"block-meta-date">​07.05.2026, 23:15​</span>​<button class=​"block-meta-comment-btn" type=​"button" aria-label=​"Kommentar zu Block von paul verfassen" data-empty=​"false">​💬 Kommentieren​</button>​</div>​Understand this warning
6editorjs.mjs:136 Block «paragraph» skipped because saved data is invalid
```
19. (20) Das Einfügen von `Einzeldaten` wird nicht in Echtzeit angezeigt. Nur durch Neuladen wird das Element im `Editor.js`-Bereich sichtbar.
20. ~~(20) Das Anlegen eines neuen `Editor.js`-Blocks nach dem Neuladen funktioniert, aber gespeichert wird der nicht.~~
21. (30) Das Einfügen von Platzhaltern ist nicht inline möglich.
22. (10) In `Bausteine`>`Module`>`Alle` wird unter den `Standard-Blöcken` der Text `Keine Einträge gefunden.` angezeigt.
23. ~~(20) Nachfolgefehler von 2.18, Fehler in DevTools Console:~~
```
report_editor.js:639 Uncaught (in promise) ReferenceError: metaBar is not defined at _wrapBlock (report_editor.js:639:5) at tryWrap (report_editor.js:817:9) at NodeList.forEach (<anonymous>) at initBlockWrappers (report_editor.js:821:42) at onReady (report_editor.js:522:13) at editorjs.mjs:11173:26
```
24. ~~(12) In `Editor.js` wird nun beim Wechseln des Blocks in `Formular` kein blauer Rahmen mehr angezeigt. Im Akkordeon-Bereich `Formular` wird der Rahmen angezeigt, aber im Bereich `Editor.js` nicht.~~
25. ~~(18) Bestehende, geladene Blöcke in `Editor.js` werden angezeigt, aber können nicht bearbeitet werden.~~
26. (6) Bestehende, geladene Blöcke in `Editor.js` anderer Ermittler können umgewandelt werden, beispielsweise von `Text` zu `Quote` und können dann bearbeitet werden. Allerdings werden diese Änderungen nicht gespeichert. Sie sollten nicht änderbar sein.
27. (100) Es scheint keinen Indikator zum Speichern zu geben ~~, oder das Speichern funktioniert generell nicht mehr~~.
28. ~~(18) Fehler in der DevTools-Console:~~
```
editorjs.mjs:7747 Uncaught TypeError: Cannot read properties of undefined (reading 'updateCurrentInput') at Qo.setCurrentBlockByChildNode (editorjs.mjs:7747:88) at fn.selectionChanged (editorjs.mjs:10955:274) at editorjs.mjs:10601:12 at s (editorjs.mjs:209:24)
setCurrentBlockByChildNode @ editorjs.mjs:7747
selectionChanged @ editorjs.mjs:10955
(anonymous) @ editorjs.mjs:10601
(anonymous) @ editorjs.mjs:209
setTimeout
(anonymous) @ editorjs.mjs:211
selectionchange
setCursor @ editorjs.mjs:1390
set @ editorjs.mjs:8224
setToBlock @ editorjs.mjs:8193
setToTheLastBlock @ editorjs.mjs:8238
documentTouched @ editorjs.mjs:10898
(anonymous) @ editorjs.mjs:10603
```
29. ~~(10) Identisch zu (2.14) Der Fehler ist zurück. Nachdem in `Formular` das Formular gewechselt wurde, wird im Editor zwar der pulsierende, blaue Rahmen angezeigt, aber nach einem Wechsel des Formulars nicht mehr gelöscht. Er bleibt dauerhaft angezeigt.~~
30. (12) Wenn die Blöcke umsortiert werden, wird dem im Formular-Bereich nicht Rechnung getragen. Dort muss die Sortierung ebenfalls angepasst werden. Gleiches gilt, wenn Blöcke hinzugefügt oder entfernt werden.
31. ~~(10) Der Status von Kommentaren kann nicht geändert werden.~~
32. ~~(14) Beim Wechseln in den Akkordeon-Bereich Bausteine und vorher aktiven Einzeldaten, werden die Schaltflächen `Alle` bis `Standard` angezeigt, die nicht zu `Einzeldaten` sondern zu `Module` gehören.~~
33. ~~(15) Kommentare werden in `Kommentare` nur angezeigt, wenn in dem Block auf `Kommentieren` geklickt wird. Ein Klicken auf den Block reicht nicht aus.~~
34. ~~(10) Es soll einen Indikator geben, der bei Blöcken eingeblendet wird, zu denen es Kommentare gibt. Dieser Indikator soll grau sein, wenn die Kommentare alle erledigt wurden und rot wenn es Kommentare mit pending gibt. Evtl. sollte vermerkt werden, ob ein Kommentar gelesen wurde.~~
35. ~~(16) Wenn bei einem Block auf "Kommentieren" geklickt wird, öffnet sich der Akkordeonbereich Kommentare. Das löst aus, dass der Block im `Editor.js` blau umrahmt wird. Wenn dann der Bereich des Akkordeons gewechselt wird, dann wird der Rahmen noch immer angezeigt und geht nicht weg. Wir benötigen ein CSS Query für die Blöcke, das den Rahmen nur anzeigt, wenn der Akkordeon-Bereich geöffnet ist. Dann wird das automatisch wieder ausgeblendet: `#report-workspace:has(#support-sidebar .support-accordion-section:nth-of-type(4).support-accordion-section--open) .ce-block.block-wrapper--own.block-wrapper--comment-focus {box-shadow: 0  0  0  2px  var(--color-focus,  #1a73e8);border-radius: var(--radius,  4px);}`~~
36. ~~(30) Nach der letzten Änderung werden die Einträge in `Bausteine`nicht mehr angezeigt. Sowohl bei `Module` als auch bei `Einzeldaten` erscheint keine Liste mehr.~~
37. (20) Nachdem ein Platzhalter (Einzeldaten) eingefügt worden ist, erscheint er nicht im Abschnitt `Editor.js`. Wenn ich dann einen Text im Abschnitt `Editor.js` erstelle, wo der Platzhalter eingefügt werden sollte, so wird dieser nicht gespeichert. Bei einem Reload der Seite wird im Editor der Platzhalter angezeigt, der vorher nicht angezeigt worden war, aber der Text, der danach hinzugefügt worden war, nicht.
38. ~~(50) Sobald ich in einen Block im Editor klicke, um den Text zu bearbeiten, öffnet sich das Akkordeon `Kommentare` und der Fokus springt in das Textarea-Element `.ct-textarea.comment-input-textarea`. Dadurch kann kein Text mehr bearbeitet werden.~~
39. (40) Das Löschen eines Blocks im Editor ist nicht mehr möglich. Sie werden optisch im Editor gelöscht. Aber nach einem Reload der Seite sind alle gelöschten Elemente wieder da.
40. (50) Das Speichern wird noch immer nicht in Echtzeit angezeigt oder bleibt aus.
---
## 3. Funktionalität Backend / Python / SQLite3-Datenbank
Hier werden Funktionsprobleme aufgeführt, die aufgrund von Problemen im Webserver oder der Datenbank auftreten.

 1. ~~(10) Im `CLI-Modus` muss der Name des Ermittlers, wie in anderen Modi auch, dem Namen des Benutzers im Betriebssystem entsprechen. Windows: `SAMAccountName`, Linux: `ENV:USER`.~~
 2.  (12) Ich benötige ein paar plausible Dummy-Module und Einzeldaten zum Testen. Bitte entwirf von jedem mindestens drei Stück. Erstelle ein Python-Skript `add-dummy-data.py` oder erweitere das Skript `setup_templates.py` (im Paket "SQLite-Prepper") um die Datenbank damit `templates.db` zu befüllen.
 3.  ~~(11) Die `templates.db` im Verzeichnis `./data` wird durch den Webserver noch ignoriert und nicht zum Laden der Bausteine verwendet.~~
4.   ~~(20) Das Speichern des Berichts funktioniert nicht: `report_editor.js:1134 report_editor.js: Block-Save fehlgeschlagen: 4rZcgdVuan {error: 'Interner Datenbankfehler', code: 'ERROR'}`~~
5.  ~~(18) Das Setzen des Kommentar-Status funktioniert  nicht im Backend oder das Frontend reagiert nicht korrekt.~~
---
## 4. Sonstiges
Themen, die keinem der zuvor genannten Bereiche eindeutig zugeordnet werden können.

1. ~~(100) Bitte lies dir vom Projekt nochmals die `Instructions` durch.~~