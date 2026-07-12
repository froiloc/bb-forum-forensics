# Berichts-Statusmodell (AIW)

**Version:** 1.0 · **Verbindlich festgelegt:** 2026-07-10 (`mc`)
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Gilt für:** `evidence_<uid>.db`, Tabelle `reports`, Spalte `status`
**Im Code:** `db/evidence_db.py` — Suchbegriff **`BERICHTS-STATUSMODELL`**
**Durchsetzung:** Build 379 · **Versiegelung:** Build 377

---

## 1. Warum dieses Dokument existiert

Die vier Statuswerte standen seit Beginn im Schema
(`CHECK(status IN ('draft','submitted','approved','final'))`), waren aber **nie
definiert**: kein Beleg an der Konstante, keine Erwähnung in Bauplänen oder
Projektdokumenten, **keine erzwungene Übergangslogik**. Faktisch wurde außer
`draft` nie ein Status gesetzt. Das Modell konnte daher frei und sauber
festgelegt werden — und wird hier verbindlich dokumentiert.

---

## 2. Häufige Verwechslung: `final` gibt es zweimal

`final` ist **sowohl** ein **Berichts-Typ** (`report_type ∈ {interim, final,
addendum}` = „Abschlussbericht") **als auch** ein **Status** (siehe unten =
„versandt/abgeschlossen").

> Ein Abschlussbericht im Entwurf ist `report_type='final'` **mit**
> `status='draft'`.

---

## 3. Die vier Status

| Status | Bedeutung | Autor darf Inhalt ändern | Übergang gesetzt durch |
|---|---|---|---|
| **`draft`** | Autor arbeitet am Bericht. | **ja** | Anlage (automatisch) |
| **`submitted`** | Autor hat den Bericht **zur Abnahme eingereicht**. Der Bericht ist damit **für den Autor gesperrt**. | nein | **Autor** (`draft → submitted`) |
| **`approved`** | Chef-Ermittlerin hat **abgenommen und versiegelt** (zentrales Abbild + Inhaltshash in `approved_reports.db`). | nein | **Chef-Ermittlerin** (`reports.approve`) |
| **`final`** | Der abgenommene Bericht ist **an die StA versandt / abgeschlossen**. Endzustand. | nein | **Chef-Ermittlerin** |

---

## 4. Zulässige Übergänge (erzwungen ab Build 379)

```
   draft  ──(Autor: "Zur Abnahme freigeben")──►  submitted
     ▲                                              │
     │                                              │
     └──(Lektor / Chef-Ermittlerin: Nachbesserung)──┘
                                                    │
                          (Chef-Ermittlerin: Abnahme + Versiegelung)
                                                    ▼
                                                approved
                                                    │
                              (Chef-Ermittlerin: an StA versandt)
                                                    ▼
                                                  final
```

- **`submitted → draft`** (Rückgabe zur Nachbesserung): **nur** Lektor
  (`reports.review`) oder Chef-Ermittlerin (`reports.approve` — impliziert
  `reports.review`). Der Autor kann sich **nicht** selbst zurückholen.
- **`approved` und `final` sind unwiderruflich.** Es gibt **keine** Rückstufung.
  Inhaltliche Schwächen eines abgenommenen Berichts werden über einen
  **Nachtragsbericht** (`report_type='addendum'`) behandelt.
- Alle anderen Übergänge werden mit `ReportSealedError` abgewiesen.

---

## 5. Schreibsperre (Build 379)

Ab **`submitted`** ist der Berichts**inhalt** gesperrt. Betroffene Schreibpfade
in `db/evidence_db.py` (zentral, nicht je Endpunkt):

`save_block` · `update_block` · `delete_block` · `set_block_order` ·
`add_anchor` · `remove_anchor` → **`ReportSealedError`**

**Kommentare bleiben erlaubt** (`add_comment`, `update_comment`). Begründung:
Sie stecken **nicht** im Siegel-Hash und helfen, die Notwendigkeit eines
Nachtragsberichts zu dokumentieren.

### Was vor Build 379 falsch war

| Schreibpfad | Sperre bei `approved` | Sperre bei `final` |
|---|---|---|
| `update_block` | ja | **nein** |
| `delete_block` | ja | **nein** |
| `save_block` (neue Blöcke) | **nein** | **nein** |
| `set_block_order` (Reihenfolge) | **nein** | **nein** |
| `add_anchor` / `remove_anchor` | **nein** | **nein** |
| `update_report_status` | **nein** | **nein** |

Ein freigegebener Bericht konnte also **neue Blöcke** bekommen, **umsortiert**
und mit **Beweisankern** versehen werden — alles Bestandteile des Siegel-Hashes.
Ein `final`-Bericht war vollständig ungeschützt. Zudem ließ sich der Status
beliebig zurückstufen und die Sperre damit selbst aushebeln.

---

## 6. Zwei Schutzebenen — und was jede leistet

| Ebene | Ort | Leistet | Leistet **nicht** |
|---|---|---|---|
| **Verhinderung** | `evidence_<uid>.db` (Schreibsperre, Build 379) | verhindert Änderungen über die **Anwendung** | schützt **nicht** gegen direkte Manipulation der DB mit einem SQLite-Werkzeug |
| **Nachweis** | `approved_reports.db` (Siegel, Build 377) | **deckt jede** Inhaltsänderung nach der Freigabe auf (Hash-Vergleich) | verhindert nichts |

Beide zusammen ergeben den Schutz. **Prüfbefehl:**

```
python -m management.reports.seal_check
```

Er rechnet alle Siegel gegen die `evidence_*.db` nach. Exit 0 = in Ordnung,
Exit 2 = **Manipulationsverdacht** (oder Bericht nicht prüfbar).

---

## 7. Offene Punkte (Stand Build 379)

1. **Ermittler-Editor:** Schaltfläche **„Zur Abnahme freigeben"**
   (`draft → submitted`) — mit **Bestätigungsdialog**, der über die Tragweite
   aufklärt (Autor wird gesperrt), den weiteren Prozess skizziert und die
   Rückholmöglichkeit über Lektor/Chef-Ermittlerin nennt. **Bewusste
   Entscheidung, kein versehentlicher Klick.** *(Endpunkt existiert noch nicht.)*
2. **Cockpit:** Rückgabe **`submitted → draft`** durch Lektor/Chef-Ermittlerin
   (auditierter Management-Pfad). *(Endpunkt existiert noch nicht.)*
3. **Cockpit-Beschriftung:** „Endgültig freigeben" → **„Als versandt/
   abgeschlossen kennzeichnen"** (der Knopf setzt `approved → final`).

---

*Dokument-Ende · Berichts-Statusmodell v1.0 · 2026-07-10*
