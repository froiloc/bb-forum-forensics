# Übergabe nach Build 773 — Bildschleier

**Datum:** 2026-10-10 · **Baubasis:** `98035a5` (v0.8.770) · **Zweig:** `claude/build771`
**Lieferung:** EIN Bundle `aiw_webserver_773` mit den Builds 771, 772, 773
**Bauplan:** `management/Bauplan_Builds771-773_Bildschleier_v0_5.md` (Abschnitt 0: Abweichungen nach Bau)

---

## 1. Was gebaut wurde

| Build | Inhalt |
|---|---|
| 771 | Migration M040 (coordinator.db, additiv): Rolle `researcher`, Recht `imageveil.lift`, Tabelle `person_image_veil`. Ereignis `IMAGE_VEIL_SET`. `BildschleierRepo` mit Entscheidungsfolge. Hilfe (Rechte/Policy, Personalverwaltung). |
| 772 | Schleier im Forenviewer: Klasse an `<html>` serverseitig, Grundregel als erstes Stylesheet, Ausnahmen je Seite mit exakten Attributwerten, Endpunkt `/_forensic/image-veil`, Schaltfläche 👁 in Sektion 5. |
| 773 | Lückenschluss: Bildquellen in CSS werden Platzhalter; Direktaufruf eines Bildes bekommt eine verschleiernde Hülle; `Vary` an jeder Bildantwort. |

## 2. Wartungsfenster — Reihenfolge

```
1. Backup coordinator.db (verifiziert)
2. python tools/pruefe_migrationskette.py --db <coordinator.db>     # Exit 0
3. Migration (M040)
4. python -m management.rbac.rbac_admin grant --role investigator \
       --capability imageveil.lift --actor <SYSUSER>
   (ebenso supervisor und jede weitere Rolle, die ohne Pflichtschleier arbeitet)
5. python -m management.rbac.rbac_admin assign-role --role researcher \
       --person <system_username> --actor <SYSUSER>       # je Forschende
```

Bis Schritt 4 sehen **alle** die Bilder verschleiert, die Schaltfläche ist
gesperrt („Recht … nicht zugeteilt“). Das Management startet erst nach M040
(`verify_catalog_present`, bekanntes Verhalten).

**Nummer 40:** war bis Build 543 an `m040_fulltext_release` vergeben, die in
keiner Datenbank lief (Kopf von `m036_fulltext_release.py`). Schritt 2 belegt
das am Bestand.

## 3. PoC in PROD (Bauplan §10) — offen

Mit einem unverfänglichen Testbild:

| Nr. | Wann/Wo/Wie | Beobachten |
|---|---|---|
| P1 | DevTools → Network: Throttling „Slow 3G“, „Disable cache“ aus. Seite mit Bildern laden. | Kein Frame zeigt ein Bild unverschleiert. Forensymbole (Icons, Abzeichen) bleiben scharf, Avatare verschleiert. |
| P2 | Als Ermittler mit Recht: 👁 klicken (ein, dann aus). | Seite lädt neu, Scrollposition bleibt, Zeichen zeigt den neuen Zustand. Protokollbuch: je Klick ein Eintrag `image_veil_set`. |
| P3 | Bild im Viewer anzeigen lassen, dann den Bildlink per Mittelklick in neuem Tab öffnen. | Hülle mit verschleiertem Bild und Hinweiszeile. Network: die Navigation darf NICHT „(disk cache)“ zeigen. |
| P4 | Als Person mit Rolle `researcher`. | 👁 ausgegraut, Kurzhinweis „Für Ihre Rolle …“, Klick wirkungslos. |

Ticket dazu in `issue-tracker/eintraege_claude_Build773.json`.

## 4. Entscheidungen dieser Sitzung (Alex, 09.10.2026)

- Steuerung über das Recht `imageveil.lift`; ohne Recht immer verschleiert und gesperrt.
- Rolle `researcher` für die wissenschaftlichen Mitarbeiter:innen; der IT-ler vorerst ohne Zugang.
- Voreinstellung für Ermittler mit Recht: **klar**; die Wahl gilt dauerhaft (Datenbank, nicht Browser).
- Unverschleiert nur `img/` (außer `img/avatars/`, `img/signatures/`), `style/`, `v4/style/`, `1bg.png` — unter `/forum/` UND `/` (gleiche Dokumentwurzel). `/pix/` verschleiert.
- Forenhost `alice4n4kd5…onion` in `config.yaml`; `alicefe3…onion` ist der Image-Hoster und nie ausgenommen.
- Filterkette `blur(48px) grayscale(100%) contrast(35%) brightness(115%)`.
- Umschalten wird auditiert; nach dem Umschalten wird neu geladen.
- Kein Pixelfilter auf dem Server; Hülle für Direktaufrufe ja.
- Keine Wirkung auf DOCX/PDF, Berichtseditor, Userinfo, Management.
- Zeichen 👁 (U+1F441) statt SVG.

## 5. Abweichungen vom Bauplan 0.4 (Details in Bauplan §0)

1. Rolle `researcher` hat **Vorrang** vor dem Recht (statt: zweite Rolle hebt auf).
2. Ausnahmen mit **exakten Werten** statt Präfix-Selektoren.
3. Zwei zusätzliche Gründe: `store_unavailable`, `internal_error`.
4. Repo unter `management/bildschleier/` statt `db/`.

## 6. Regression

Siehe Lieferprotokoll `PROTOKOLL_Build773.md`. Bekannt und unverändert: die
fünf `BundleEinspielenTests` lk04–lk08 (fehlende Fixture im Baucontainer).
