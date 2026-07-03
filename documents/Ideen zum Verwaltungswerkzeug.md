# Ideen zum Verwaltungswerkzeug

## Gesamtzusammenstellung aller Funktionen

Im Folgenden alle besprochenen Punkte in Kurzform + Prosa:

---

### 1. Echtzeit-Ampel-Dashboard (pro User-ID)

**Kurzform:** Visueller Status (rot/gelb/grün) jeder User-ID mit Fortschrittsbalken und bearbeitendem Ermittler.  
**Prosa:** Die Chefermittlerin benötigt auf einen Blick den Überblick über Dutzende parallel laufende Ermittlungen. Die Ampel zeigt: Rot (nicht begonnen), Gelb (in Arbeit mit Namen des Ermittlers und letzter Aktivität), Grün (abgeschlossen, Freigabe liegt vor). Der Fortschrittsbalken basiert auf dem Verhältnis ausgewerteter Posts/PMs zur Gesamtzahl – so ist sofort erkennbar, ob ein Fall stockt.

### 2. Automatische Statistik für die Staatsanwaltschaft (Export)

**Kurzform:** Anzahl laufender/abgeschlossener Fälle, durchschnittliche Bearbeitungsdauer, Heatmap der Aktivitätszeiten (pro Fall im Detail).  
**Prosa:** Die Staatsanwaltschaft muss Verjährungsfristen im Blick behalten und Anklagezeiträume planen. Das Modul liefert aggregierte Kennzahlen: Wie viele Fälle sind diese Woche abgeschlossen worden? Wie lange dauert ein Fall durchschnittlich von Zuweisung bis Freigabe? Zudem kann sie für jeden abgeschlossenen Fall eine Aktivitätsheatmap anfordern, die Lebensrhythmen des Beschuldigten sichtbar macht.

### 3. Risiko- & Dringlichkeits-Matrix

**Kurzform:** 3x3-Raster mit verbleibenden Tagen bis Verjährung (X) vs. Relevanz-Score (Y) – jeder User ist ein klickbarer Punkt.  
**Prosa:** Nicht alle Fälle sind gleich eilig. Die Matrix kombiniert zwei kritische Dimensionen: Wie knapp ist das Zeitfenster vor Verjährung? Wie hoch ist die inhaltliche Relevanz des Users (basierend auf Sprache, Aktivitätszeiten, Passwortauffälligkeiten)? Daraus ergeben sich klare Handlungsempfehlungen wie „Sofort priorisieren“ oder „Dokumentieren und zurückstellen“. Ein Klick auf einen Punkt führt direkt zum Fall.

### 4. Differenzierungsansicht für Berichtsfreigabe

**Kurzform:** Side-by-Side-Ansicht (Originalbericht vs. Überarbeitungsvorschlag) mit Prinzip der unveräußerbaren Autorschaft.  
**Prosa:** Mehrere Ermittler arbeiten kollaborativ an einem Fallbericht – jeder Absatz bleibt seinem Autor zugeordnet und kann von anderen nur kommentiert, nicht überschrieben werden. Die Chefermittlerin sieht links den kollaborativen Bericht (farbig markiert nach Autoren), rechts ihren Änderungsvorschlag. Jede ihrer Formulierungen wird als *Suggestion* gespeichert. Die finale Freigabe erzeugt einen kryptografisch signierten Vermerk in der `coordinator.db`.

### 5. Gantt-Chart mit Ressourcenplanung

**Kurzform:** Zeitliche Darstellung aller Ermittler, ihrer Verfügbarkeiten und zugewiesenen User-IDs mit Meilensteinen.  
**Prosa:** Die Chefermittlerin muss gegenüber der Staatsanwaltschaft belastbare Prognosen liefern können. Das Gantt-Chart zeigt auf einer Zeitachse, welcher Ermittler wann an welchem Fall arbeitet, basierend auf hinterlegten Verfügbarkeitskalendern. Meilensteine wie „Zwischenbericht an StA“ oder „Freigabe durch Chefermittlerin“ strukturieren den Prozess zusätzlich.

### 6. Lastverteilungs-Dashboard mit Überlastwarnung

**Kurzform:** Berechnung offener Stunden vs. verfügbarer Ermittlerstunden, Warnung bei Überlast, Vorschlag zur Umverteilung.  
**Prosa:** Wenn die Summe der geschätzten Restaufwände die verfügbaren Kapazitäten übersteigt, erscheint eine Warnung mit der genauen Differenz. Das Dashboard schlägt konkrete Umverteilungen vor: „Ermittlerin A hat eine Lücke in ihrem Kalender – ihr könnte User-ID 42 übernehmen.“ So wird die Chefermittlerin proaktiv unterstützt, bevor es zu Verzögerungen kommt.

### 7. Prognose-Modul für die Staatsanwaltschaft (drei Szenarien)

**Kurzform:** Optimistische, realistische und pessimistische Fertigstellungsprognose exportierbar als PDF mit Wasserzeichen.  
**Prosa:** Die Staatsanwaltschaft benötigt Planungssicherheit für Anklageerhebungen. Das Modul berechnet auf Basis historischer Bearbeitungszeiten und aktueller Verfügbarkeiten drei Szenarien: optimistisch (keine Störungen), realistisch (80 % Verfügbarkeit, 15 % Puffer) und pessimistisch (Ausfälle, Rückfragen). Das PDF erhält ein vorläufiges Wasserzeichen und wird regelmäßig aktualisiert.

### 8. Ermittler-Metriken & Ausreißer-Detektion (Qualitätssicherung)

**Kurzform:** Automatische Erkennung von Ermittlern mit Abweichungen vom Median bei Aktivität, Annotationstiefe oder Rückweisungsquote.  
**Prosa:** Um die Beweisqualität über das gesamte Projekt zu gewährleisten, müssen Auffälligkeiten früh erkannt werden. Das Dashboard zeigt pro Ermittler Kennzahlen wie bearbeitete Einheiten pro Stunde, durchschnittliche Länge von Anmerkungen und das Verhältnis freigegebener zu zurückgewiesener Berichte. Wer signifikant unter oder über dem Median liegt, wird automatisch markiert.

### 9. Internes Nachrichtensystem (nur standardisierte Templates)

**Kurzform:** Einbahnstraße von der Chefermittlerin zu Ermittlern mit vordefinierten Textbausteinen, keine personenbezogenen Daten.  
**Prosa:** Im abgeschotteten Netzwerk stehen keine E-Mail- oder Chat-Systeme zur Verfügung. Das interne Nachrichtensystem erlaubt der Chefermittlerin dennoch, standardisierte Hinweise zu versenden – z. B. „Bitte erhöhen Sie die Annotationstiefe“ oder „Ihre Geschwindigkeit liegt unter dem Median“. Die Nachricht erscheint als Banner im Arbeitsplatz des Ermittlers. Freitext ist nicht erlaubt, um Datenschutzprobleme zu vermeiden.

### 10. Backup & Point-in-Time-Recovery-Maske

**Kurzform:** Nächtliche automatische Snapshots aller Datenbanken, Wiederherstellung mit Dry-Run und Bestätigung.  
**Prosa:** Backups sind automatisiert, aber die Wiederherstellung muss auch von der Chefermittlerin selbst angestoßen werden können. Die Maske listet alle verfügbaren Backups mit Datum und Größe. Ein Dry-Run zeigt vor der eigentlichen Wiederherstellung, welche Änderungen rückgängig gemacht würden. Erst nach einer zweiten Bestätigung („Ich bin sicher“) werden die aktiven Datenbanken überschrieben.

### 11. Fall-bezogener Ereigniszeitstrahl

**Kurzform:** Vertikale Timeline pro User-ID mit automatischen und manuellen Ereignissen (Zuweisungen, Statuswechsel, Rückstellungen).  
**Prosa:** Die Kommunikation mit der Staatsanwaltschaft erfordert nachvollziehbare Entscheidungen. Der Zeitstrahl protokolliert automatisch jede Zuweisung und Statusänderung. Die Chefermittlerin kann manuell Einträge hinzufügen wie „Rückstellung bis 15.07.2026 – Grund: weitere Beschlüsse erforderlich“ oder „Priorität erhöht auf Anordnung der StA“. Das schafft Transparenz und dokumentiert die Ermittlungsführung.

### 12. StA-Export-Modul mit Ausschleus-Verzeichnis

**Kurzform:** Export von Berichten, Zeitstrahl und Beweismittelverzeichnissen in ein verschlüsseltes Transferverzeichnis.  
**Prosa:** Das ermittlungsinterne Netzwerk ist vom Internet getrennt. Für die Übergabe an die Staatsanwaltschaft werden Exporte in ein spezielles Ausschleus-Verzeichnis geschrieben, verschlüsselt mit einem einmaligen Schlüssel. Ein sicherer Transferagent holt die Dateien ab. Nach erfolgreichem Abholen können die Quelldateien aus dem Arbeitsverzeichnis gelöscht werden – so bleibt das Arbeitsnetzwerk sauber.

### 13. Audit-Log mit Nachweis der Nichtmanipulierbarkeit

**Kurzform:** Kryptographisch verkettete Log-Tabelle (Hash der vorherigen Zeile) für alle kritischen Aktionen.  
**Prosa:** Für die spätere Gerichtsverwertbarkeit reicht ein einfacher SQLite-Timestamp nicht aus – ein Administrator könnte theoretisch Einträge nachträglich ändern. Das Audit-Log arbeitet wie eine Mini-Blockchain: Jeder neue Eintrag enthält den Hash des vorherigen Eintrags plus einen geheimen Salt. Die Chefermittlerin kann jederzeit die Integrität prüfen lassen. Weicht ein Hash ab, ist eine Manipulation nachweisbar.

### 14. Volltextsuche über alle User-IDs hinweg

**Kurzform:** Zentrale Suchmaschine über alle entschlüsselten Nachrichten und Posts, Treffer werden pro Fall gruppiert.  
**Prosa:** Zusammenhänge zwischen verschiedenen Usern (gleiche Redewendungen, gleiche Orte, gleiche Fehler in der Verschlüsselung) entgehen sonst leicht. Die Volltextsuche erlaubt Queries wie „Nordbahnhof“ oder „treffen um 15 Uhr“ über alle `evidence_*.db` hinweg. Das Ergebnis zeigt sofort, welche User-IDs die Begriffe enthalten – und kann Prioritäten verschieben oder neue Ermittlungsansätze liefern.

### 15. Modul-Steuerung mit Rollen-basierten Widgets (Chefermittlerin & Admin)

**Kurzform:** Konfigurierbares Dashboard mit Drag & Drop – Chefermittlerin wählt sichtbare Module, Admin sieht zusätzlich technische Metriken.  
**Prosa:** Nicht jeder braucht alles. Die Chefermittlerin kann aus einer Modulbibliothek (Ampel, Gantt, Risikomatrix, Ausreißer-Monitor, Prognose-Export) die für ihre aktuelle Sitzung relevanten Widgets auswählen und per Drag & Drop anordnen. Der Administrator hat einen eigenen, nur für ihn sichtbaren Bereich mit SQLite-Connection-Status, ATTACH-Fehlern und aktiven Sessions.

---

Das ist das vollständige Brainstorming-Ergebnis.
