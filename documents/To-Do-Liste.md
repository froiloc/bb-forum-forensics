# To-Do-Liste — IT-Forensisches Ermittlungswerkzeug (aiw_webserver)

Stand: 2026-04-15 · Build: 015

---

## Offene Punkte

### TODO-001 · BrokenPipeError im Request-Handler-Thread

**Kategorie:** Monitoring / Betrieb  
**Priorität:** Niedrig  
**Erstellt:** Build 015 · 2026-04-15  

**Beschreibung:**  
In `server/http_server.py`, Methode `ForensicRequestHandler._send_500()`,
wird ein `BrokenPipeError` beim Schreiben der 500-Fehlerantwort mit `pass`
still verschluckt:

```python
def _send_500(self) -> None:
    body = b"<html><body><p>Interner Serverfehler.</p></body></html>"
    try:
        self.send_response_body(500, body)
    except Exception:
        pass  # Verbindung bereits geschlossen
```

**Begründung für Zurückstellung:**  
Ein `BrokenPipeError` entsteht, wenn der Browser die Verbindung bereits
geschlossen hat, bevor die 500-Antwort vollständig gesendet werden konnte.
Der Ermittler hat in diesem Szenario keine Handlungsmöglichkeit — die
Verbindung ist clientseitig bereits beendet. Eine Fehlermeldung auf der
Konsole würde Verwirrung stiften ohne handlungsleitend zu sein.

**Empfehlung für Behandlung:**  
Aufdeckung und Analyse gehören in das Server-Monitoring bzw. das
Log-Auswertungswerkzeug (Baustelle 5 / Verwaltungswerkzeug). Dort sollte
eine Häufung von `BrokenPipeError`-Einträgen im Log als Indikator für
Verbindungsprobleme oder Browser-Inkompatibilität ausgewertet werden.

**Betroffene Datei:** `server/http_server.py`  
**Betroffene Methode:** `ForensicRequestHandler._send_500()`

---

*Weitere Einträge werden hier ergänzt.*
