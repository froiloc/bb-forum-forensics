# Bauplan Builds 771–773 — Bildschleier (optischer Selbstschutz)

**Version:** 0.2 · **Datum:** 2026-10-09 · **Baubasis:** `98035a5` (v0.8.770)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** ausstehend (`mc`)

---

## 1. Anlass

Ein Forschungsteam des LKA (zwei wissenschaftliche Mitarbeiter:innen, ein
IT-ler) begleitet das Projekt 35 Monate. Die wissenschaftlichen
Mitarbeiter:innen erhalten Zugriff auf den AiW-Webserver, sollen die Bilder des
Forums aber **nicht unverschleiert** sehen. Look-and-Feel des Forums bleibt
erhalten.

Für alle übrigen Ermittler:innen wird derselbe Schleier als **umschaltbare**
Ansicht angeboten (Vorführung vor Dritten, Blick Dritter, eigene Belastung).

**Schutzziel:** optischer Selbstschutz. **Kein** Zugriffsschutz — die Originale
liegen als BLOB in der Datenbank, eine bewusste Umgehung (DevTools, „Bild
speichern unter“) ist hingenommen (Alex, 09.10.2026).

---

## 2. Festlegungen (Alex, 09.10.2026)

| # | Festlegung |
|---|---|
| F1 | Der Schleier greift **vor** der ersten Darstellung. Kein Aufblitzen des Originals. |
| F2 | Steuerung über ein RBAC-Recht. Wer es **nicht** hat, sieht immer den Schleier, die Schaltfläche ist ausgegraut. |
| F3 | Rolle `researcher` für die wissenschaftlichen Mitarbeiter:innen. Der IT-ler erhält vorerst keinen Zugang. |
| F4 | Normale Ermittler:innen: Voreinstellung **klar**. Ihre Wahl wird dauerhaft je Person in der Datenbank gespeichert, nicht im Browser. |
| F5 | Unverschleiert bleiben nur: `/forum/img/…` außer `/forum/img/avatars/…` und `/forum/img/signatures/…`; `/forum/style/…` und `/forum/v4/style/…` mit Unterverzeichnissen; der exakte Pfad `/forum/1bg.png`. **Alles andere** wird verschleiert, egal von welcher Quelle — ausdrücklich auch `/pix/…`. |
| F6 | Ausnahmen gelten nur auf dem Forenhost, in relativer, wurzelrelativer und absoluter Schreibweise. Werte mit `..` sind nie ausgenommen. Im Zweifel: verschleiern. |
| F7 | Filterkette: `blur(48px) grayscale(100%) contrast(35%) brightness(115%)` mit `!important`, dazu `clip-path: inset(0)`. Konfigurierbar. |
| F8 | Direktaufruf eines Bildes (neuer Tab, Klick auf Bildlink) liefert bei aktivem Schleier eine HTML-Hülle mit verschleiertem Bild. |
| F9 | Umschalten wird auditiert. Nach dem Umschalten lädt die Seite neu (Scrollposition über `scroll_memory.js`). |
| F10 | Keine Wirkung auf DOCX-/PDF-Exporte, Berichtseditor, Userinfo-Fenster, Management. |
| F11 | Kein Messwerkzeug. Die Regel ist deterministisch und braucht keine Bestandsmessung. |
| F12 | Eigene neue Tabelle in `coordinator.db`, eigener Migrationslauf. |

---

## 3. Messbefunde (Baubasis `98035a5`)

### 3.1 Webserver

| Befund | Fundstelle | Folge für den Bau |
|---|---|---|
| Zweiphasiges Laden: Shell mit `toolbar.css` im `<head>`, BLOB-Body erst per AJAX | `server/shell_handler.py` Z. 184–189 | Die Verschleierungsregel steht im `<head>`, bevor ein `<img>`-Knoten existiert (F1). |
| Navigation **innerhalb** der Shell per `history.pushState` | `toolbar/toolbar.js` Z. 2117–2118 | Seitenabhängiges darf nicht in die Shell. Es reist mit dem Seitenumschlag (`_handleEnvelope`). |
| `<base href>` wird je Seite gesetzt | `toolbar/toolbar.js` Z. 2214–2228 | Relative Bild-URLs lösen gegen `<base>` auf, sonst gegen die Seiten-URL. |
| Volle Asset-URLs werden bei der Auslieferung umgeschrieben auf `/_forensic/fileasset?url=<quote(url, safe="")>` | `server/blob_handler.py` Z. 598–637 | Die kodierte Form ist deterministisch und muss mitgeprüft werden. |
| `url(http…)` in ausgelieferten CSS-Dateien wird bereits zerlegt | `server/asset_handler.py` Z. 96–136 | Ort für den CSS-Teil des Schleiers (Abschnitt 5.3). |
| `fileasset` liefert mit `Cache-Control: max-age=3600, immutable` | `forensic_api/fileasset.py` Z. 199 | Ein Direktaufruf könnte aus dem Browser-Cache bedient werden und die Hülle umgehen. Gegenmittel: `Vary`, siehe 5.4 und PoC P3. |
| Webserver prüft Rechte über `context.investigator_id` + `RbacResolver(con).resolve(pid).can(cap)` | `forensic_api/results_endpoint.py` Z. 108–112 | Muster für die Rechteprüfung. |
| Webserver schreibt bereits ins `audit_log` der `coordinator.db` | `forensic_api/support_presence.py` Z. 135–136 (`CoordinatorWriter` + `AuditLog`) | Muster für den auditierten Schreibpfad. |
| Projektregel: kein `localStorage` | `management/server/static/cockpit.js` Z. 998 | Zustand serverseitig (F4). |
| `person_view_pref.art` hat `CHECK(art IN ('sicht','widget'))` | `m037_view_pref.py` Z. 91 | Nicht additiv erweiterbar, daher eigene Tabelle (F12). |
| **Keine Migration vergibt Grants**, weil `rbac_grant.audit_seq NOT NULL` einen Akteur verlangt | `m038_caseoverview_rbac.py` Kopf, Abschnitt „Was diese Migration ausdrücklich nicht tut“ | Unmittelbar nach `m040` hat **niemand** das neue Recht. Alle sehen den Schleier, bis im Wartungsfenster vergeben wird (Abschnitt 6). Das ist die sichere Richtung. |
| Forenhostname steht in `hosts_management.forum_hostname`, Vorgabe leer | `core/hosts_manager.py` Z. 98, 160–162 | Eigene Liste der Forenhosts im Abschnitt `image_veil`. Ist sie leer, sind absolute Forenhost-URLs **nicht** ausgenommen (Überverschleierung, sicher). |

### 3.2 Forenquelltext (`aiw_sqlite_prepper/forum/html`)

| Bildquelle | Fundstelle | Ergebnis nach F5 |
|---|---|---|
| Avatar `img.avatar`, absolut `get_base_url(true)/img/avatars/…`, teils mit Inline-`filter:invert(100%)` | `include/functions.php` Z. 2107 | verschleiert. `!important` nötig, sonst gewinnt der Inline-Stil. |
| BB-Code-Bilder auf Hoster `alicefe3…onion/images/720/…`, Klasse `bb-image`, umschlossen von `<a href=…/images/0/… target="_blank">` | `include/parser.php` Z. 523–525 | verschleiert. Der Link ist der Fall F8. |
| Kopfbanner als Inline-`background-image` von Hoster | `include/functions.php` Z. 992 | verschleiert (Inline-Stil, 5.2). |
| Finder-Bilder als Inline-`background` von `/images/…` | `finder/finder.inc.php` Z. 377 | verschleiert. |
| Badges als Inline-`background` `/forum/img/badge/…` | `top.php` Z. 124–126 | klar. |
| Icons, Userbar, Badges, Logo `img/…` | `viewforum.php`, `user.php`, `header0.php` | klar. |
| `url(…)` in Stylesheets: 106× `./images/`, 21× `Air/img/`, 9× `./img/`, 4× `../img/icons/` | `style/*.css`, `v4/style/*.css` | klar (lösen in `/forum/style/…` bzw. `/forum/img/…` auf). |
| `url("/pix/banner/s9/1–4.jpg")` | `style/index.css` Z. 584–587 | verschleiert (F5: zeigen Kinder). |
| `url(/style/bg.webp)` — Wurzelverzeichnis `/style/`, **nicht** `/forum/style/` | `style/old.css` Z. 6 | **offen** (v0.2): nicht besprochen; nach F5 fiele es unter „alles andere“. Entscheidung Alex ausstehend. |
| `do_smilies()` ist ein No-op | `include/parser.php` Z. 246 | Smilies sind im Repo-Parser nicht belegbar. Liegen sie unter `/forum/img/smilies/`, bleiben sie klar, sonst verschleiert. |

---

## 4. Architektur

Eine einzige Python-Klasse trifft die Entscheidung „ausgenommen oder nicht“.
Alle übrigen Bausteine fragen sie. Es gibt also genau eine Quelle der Wahrheit.

```
                      ┌────────────────────────────┐
  config.yaml ───────►│  core/bildschleier_regel   │  ist_ausgenommen(url, basis)
  image_veil:         │  BildschleierRegel         │  relative_praefixe(basis)
                      └──────┬──────────┬──────────┘
                             │          │
             ┌───────────────┘          └──────────────────┐
             ▼                                             ▼
  core/bildschleier_css                         server/bildschleier_huelle
  BildschleierCss                               BildschleierHuelle
   · Grundregel (alles verschleiern)             · Direktaufruf → HTML-Hülle
   · seitenunabhängige Ausnahmen                 · Sec-Fetch-Dest / Accept
   · seitenabhängige Ausnahmen (je Umschlag)
   · url()-Ersetzung in CSS-Text

  db/bildschleier_repo        BildschleierRepo      Lesen/Schreiben + Audit
  forensic_api/bildschleier   BildschleierEndpoint  GET/POST /_forensic/image-veil
  toolbar/bildschleier.js     BildschleierSchalter  Icon, 3 Zustände, Umschalten
```

Jede Klasse in einer eigenen Datei (Grundregel 10).

### 4.1 Zustand je Anfrage

`BildschleierRepo.zustand(person_id)` liefert:

| Feld | Bedeutung |
|---|---|
| `veiled` | Schleier wirkt (bool) |
| `locked` | Schaltfläche gesperrt (bool) |
| `reason` | Grund, maschinenlesbar |

Die Gründe:

| `reason` | Bedeutung | `veiled` | `locked` |
|---|---|---|---|
| `required_by_role` | Person trägt Rolle `researcher` (Vorschlag v0.2) | true | true |
| `no_capability` | Recht `imageveil.lift` fehlt, keine Rolle `researcher` | true | true |
| `no_investigator` | `investigator_id` nicht auflösbar | true | true |
| `rbac_unavailable` | `coordinator.db` / RBAC nicht lesbar | true | true |
| `chosen` | Recht vorhanden, eigene Wahl gespeichert | gespeichert | false |
| `default` | Recht vorhanden, keine Zeile | false (F4) | false |

Jeder Fehlerfall endet **verschleiert und gesperrt**. Der Grund wird im Log
benannt und im Tooltip angezeigt (Grundregel 1).

---

## 5. Wirkweise

### 5.1 Reihenfolge-Garantie (F1)

1. `ShellHandler` liest den Zustand und schreibt `<html class="aiw-image-veil">`,
   wenn `veiled`. Zusätzlich gibt er `data-image-veil-locked` und
   `data-image-veil-reason` aus.
2. Im `<head>` steht `/_forensic/image-veil.css?v=<build>` als blockierendes
   `<link>`, **vor** `toolbar.css`. Der Inhalt:
   - die **Grundregel**: alles verschleiern,
   - die **seitenunabhängigen** Ausnahmen (wurzelrelativ, absolut auf
     Forenhost, kodierte `fileasset`-Form).
3. Der BLOB-Body kommt per AJAX. Der Seitenumschlag trägt zusätzlich die
   **seitenabhängigen** Ausnahmen (relative Präfixe, gegen `<base>` bzw.
   Seiten-URL berechnet). `_handleEnvelope` setzt sie in
   `<style id="aiw-image-veil-page">` **bevor** der Viewport befüllt wird.

**Fehlerrichtung:** Ausnahmen können nur *ent*schleiern. Kommen sie zu spät
oder fehlen sie, ist die Folge Überverschleierung, nie Unterverschleierung. Die
Grundregel selbst kennt keine Seitenabhängigkeit und steht immer zuerst.

### 5.2 Selektoren

**Grundregel** (Spezifität 1 Klasse + 1 ID + Element, dazu `!important`):

```css
html.aiw-image-veil #forensic-viewport :is(img, input[type=image], video,
    object, embed, picture, svg image),
html.aiw-image-veil #forensic-viewport [style*="url("] {
    filter: blur(48px) grayscale(100%) contrast(35%) brightness(115%) !important;
    clip-path: inset(0) !important;
}
```

**Ausnahme** für ein ausgenommenes Präfix `P` (je Verzeichnis aus F5):

```css
html.aiw-image-veil #forensic-viewport img[src^="P"]:not([src*=".."])
    :not([src^="P/avatars/"]):not([src^="P/signatures/"]) { filter: none !important; clip-path: none !important; }
```

Die `avatars`- und `signatures`-Ausschlüsse gelten nur für das `img`-Verzeichnis.
`[src^=…]` vergleicht den Attributwert **wörtlich**. Deshalb erzeugt
`BildschleierCss` jede Schreibweise einzeln:

| Form | Beispiel | Woher |
|---|---|---|
| wurzelrelativ | `/forum/img/` | statisch |
| absolut je Forenhost, `http` und `https` | `http://<host>/forum/img/` | statisch aus `image_veil.forum_hosts` |
| kodierte `fileasset`-Form | `/_forensic/fileasset?url=http%3A%2F%2F<host>%2Fforum%2Fimg%2F` | statisch, mit derselben `quote()`-Funktion wie `blob_handler` |
| relativ zur Seite | `img/`, `../img/`, `./img/` | je Seite, `posixpath.relpath(D, basisverzeichnis)` |

**Inline-Stile:** Ein Element mit `style="…url(P…)"` wird nur ausgenommen, wenn
`P` ein ausgenommenes Präfix ist (Varianten `url(P`, `url('P`, `url("P`).

**Bekannte Grenze:** Stehen in **einem** Inline-Stil zwei `url()`, eine
ausgenommene und eine nicht ausgenommene, nimmt der Selektor das Element aus.
CSS kann `url(` nicht zählen. Gemessen im Forenquelltext: kein solcher Fall,
jeder Inline-Stil mit `url()` trägt genau eine (Abschnitt 3.2). Wächter BS14
hält diese Annahme am Quelltext fest.

### 5.3 Bilder aus Stylesheets

Kein CSS-Selektor erreicht ein Bild, das eine CSS-*Regel* einem Element
zuweist. Deshalb wirkt dieser Teil serverseitig, nur bei aktivem Schleier:

- `AssetHandler` (CSS-Dateien) und `BlobHandler` (`<style>`-Blöcke im
  Seitenkopf und im Body) lösen jede `url(…)` mit `urljoin` gegen die Adresse
  der CSS-Datei bzw. gegen `<base>`/Seiten-URL auf.
- Nicht ausgenommene Ziele werden durch `/_forensic/image-veil-placeholder.svg`
  ersetzt (neutrales Grau).
- CSS-Antworten erhalten `Cache-Control: no-store`, damit ein Umschalten nach
  dem Neuladen (F9) sicher wirkt.

Der gespeicherte BLOB bleibt unberührt. Umgeschrieben wird nur bei der
Auslieferung, wie bisher bei `_rewrite_asset_urls()`.

### 5.4 HTML-Hülle für Direktaufrufe (F8)

`BildschleierHuelle.ist_dokumentanfrage(headers)`:
- `Sec-Fetch-Dest: document` → ja
- `Sec-Fetch-Dest` fehlt → `Accept` enthält `text/html` → ja
- sonst → nein

Ist der Schleier aktiv, die Antwort ein Bild (`image/*`), die URL nicht
ausgenommen und die Anfrage eine Dokumentanfrage, dann liefert der Server statt
der Bytes eine kleine HTML-Seite: `<img src="dieselbe URL">` plus
`image-veil.css` mit `<html class="aiw-image-veil">`. Die Hülle trägt
`Cache-Control: no-store`.

Betroffen: `AssetHandler` und `FileassetEndpoint`. **Alle** Bildantworten
erhalten zusätzlich `Vary: Sec-Fetch-Dest, Accept`, damit der Browser eine
`<img>`-Antwort aus dem Cache nicht für eine Navigation wiederverwendet
(Befund `fileasset.py` Z. 199). Ob Chromium das einhält, prüft PoC P3.

### 5.5 Schaltfläche

In Sektion 5 der Toolbar direkt vor `#forensic-session-user`
(`toolbar.js` Z. 1822). Eigene Datei `toolbar/bildschleier.js` (IIFE,
`'use strict'`, Debug-Logging mit PROD-Schalter).

| Zustand | Darstellung | Klick |
|---|---|---|
| gesperrt | Icon verschleiert, ausgegraut, `aria-disabled="true"`, Tooltip nennt den Grund | keine Wirkung |
| verschleiert | Icon verschleiert, farbig | ausschalten |
| klar | Icon klar, farbig | einschalten |

**Einschalten:** zuerst Klasse setzen (sofortiger Schutz), dann `POST`, dann
Neuladen. **Ausschalten:** zuerst `POST`, dann Neuladen. Schlägt der `POST`
fehl, bleibt der Schleier aktiv und die Sync-Anzeige meldet den Fehler. Ein
fehlgeschlagenes **Aus**schalten entschleiert also nie.

### 5.6 Endpunkt

- `GET  /_forensic/image-veil` → `{veiled, locked, reason}`
- `POST /_forensic/image-veil` mit `{"veiled": true|false}`
  → `403 {"error":"forbidden","capability":"imageveil.lift"}` ohne Recht
  → sonst Schreiben + Audit, Antwort wie `GET`

---

## 6. Migration `m040` (coordinator.db)

**Name:** `m040_image_veil.py`, `KIND = "additive"`.

1. Rolle `researcher` („Forschung — Bildschleier verpflichtend“), wörtlich
   geseedet (m005-Prinzip).
2. Recht `imageveil.lift` („Bildschleier aufheben“; Beschreibung: „Die
   Bildverschleierung im Forenviewer selbst ein- und ausschalten. Ohne dieses
   Recht ist der Schleier immer aktiv.“), wörtlich geseedet.
3. Tabelle:

```sql
CREATE TABLE IF NOT EXISTS person_image_veil (
    person_id   INTEGER PRIMARY KEY REFERENCES person(id),
    veiled      INTEGER NOT NULL CHECK("veiled" IN (0,1)),
    changed_at  INTEGER NOT NULL,
    audit_seq   INTEGER NOT NULL REFERENCES audit_log(seq)
)
```

Eine Zeile je Person, die laufende Wahl. Die Historie steht im `audit_log`
(Ereignis `IMAGE_VEIL_SET`, Nutzlast `{"veiled": …}`).

**Keine Grants** (Muster `m038`). Delta-Wächter wie `m038` seit Build 711:
Grants vor und nach dem Seed zählen, nur ein **Zuwachs** bricht ab.

**Migrationsvorbehalt:** nur `coordinator.db`. `evidence_`, `forensic_` und
`assets_<uid>.db` bleiben unberührt. Rein additiv, kein Tabellenumbau, kein
`executescript()`.

### 6.1 Wartungsfenster — Reihenfolge

```
1. Backup coordinator.db (verifiziert)
2. python -m management.migrate …            # m040 (Aufruf wie gewohnt)
3. python -m management.rbac.rbac_admin grant --role investigator \
       --capability imageveil.lift --actor <SYSUSER>
   (ohne --scope: das Recht wirkt nur auf die eigene Oberfläche;
    dasselbe für supervisor und jede weitere Rolle, die den Viewer
    ohne Pflichtschleier nutzt)
4. python -m management.rbac.rbac_admin assign-role --role researcher \
       --person <system_username> --actor <SYSUSER>   # je wissenschaftl. Mitarbeiter:in
```

Bis Schritt 3 sehen **alle** den Schleier, gesperrt mit Grund
`no_capability`. Das ist sichtbar, nicht still, und die sichere Richtung.

**Wichtig:** `researcher` darf **keine** Rolle zusätzlich tragen, die
`imageveil.lift` besitzt. RBAC ist additiv; eine zweite Rolle mit dem Recht hebt
den Pflichtschleier auf. Wächter BS22 prüft nur den Katalog; die Zuweisung im
Bestand ist Verantwortung der Personalverwaltung. Die Hilfe sagt das
ausdrücklich.

---

## 7. Konfiguration (`config.yaml`)

```yaml
image_veil:
  # Forenhosts, auf denen F5-Ausnahmen in absoluter Schreibweise gelten.
  # Leer = absolute Forenhost-URLs werden verschleiert (sichere Richtung).
  # Der Host allein nimmt NIE aus: derselbe Host liefert unter /images/
  # die BB-Code-Bilder (include/parser.php Z. 523-525). Ausgenommen wird
  # immer nur Host + Pfad aus exempt_dirs/exempt_files.
  forum_hosts:
    - "alicefe3b2dqil3mk3ipwtyoqjol23kdai7cjpgzrtvemfvtzz2s67ad.onion"   # Alex, 09.10.2026
  filter: "blur(48px) grayscale(100%) contrast(35%) brightness(115%)"
  exempt_dirs:
    - "/forum/img/"
    - "/forum/style/"
    - "/forum/v4/style/"
  exempt_files:
    - "/forum/1bg.png"
  excluded_dirs:
    - "/forum/img/avatars/"
    - "/forum/img/signatures/"
```

Die Vorgaben stehen zusätzlich in `core.config_loader.coded_default()`
(Wächter PH04).

---

## 8. Build-Schnitt

Jeder Build ist für sich lauffähig und getestet (Grundregel 2).

### Build 771 — Fundament (kein sichtbarer Effekt)

- `m040_image_veil.py`
- `management/rbac/catalog.py`: Rolle + Recht
- `management/audit/event_types.py`: `IMAGE_VEIL_SET`
- `db/bildschleier_repo.py`: Zustand lesen (5 Gründe), Wahl schreiben + Audit
- Hilfe: `management/help/inhalt/administration.py` (Recht, Rolle,
  Warnhinweis Mehrfachrolle), `personal.py` (Rolle `researcher`)
- Wächter BS01–BS08

### Build 772 — Schleier im Viewer

- `core/bildschleier_regel.py`, `core/bildschleier_css.py`
- `forensic_api/bildschleier.py` (Endpunkt), Routing
- `server/shell_handler.py`: Klasse und `data-*` auf `<html>`, CSS-Link
- `server/blob_handler.py`: seitenabhängige Ausnahmen im Umschlag
- `toolbar/bildschleier.js`, `toolbar/toolbar.js` (Einsatzpunkt in Sektion 5
  und in `_handleEnvelope`), `toolbar.css` (Icon)
- `config.yaml`, `core/config_loader.py`
- Wächter BS09–BS18 (pytest), BS19–BS21 (vitest)

### Build 773 — Lückenschluss

- `server/asset_handler.py` und `server/blob_handler.py`: `url()`-Ersetzung,
  `no-store`
- `server/bildschleier_huelle.py`; Einbindung in `asset_handler` und
  `forensic_api/fileasset.py`; `Vary`
- `/_forensic/image-veil-placeholder.svg`
- Wächter BS22–BS30

---

## 9. Wächter (Auswahl, je mit Mutationsgegenprobe)

| Nr. | Prüft |
|---|---|
| BS01 | `m040` additiv, idempotent, zweiter Lauf ohne Änderung |
| BS02 | `m040` schreibt **keinen** Grant (Delta) |
| BS03 | Katalog-Seed in `m040` == `catalog.py` (wörtliche Kopie) |
| BS04–BS06 | Zustand: alle drei Fehlergründe → verschleiert **und** gesperrt |
| BS07 | Ohne Zeile mit Recht → klar (F4) |
| BS08 | Schreiben erzeugt genau eine `audit_log`-Zeile, `audit_seq` gekoppelt |
| BS09 | `/forum/img/avatars/x.jpg`, `/forum/img/signatures/x.png` → verschleiert |
| BS10 | `http://fremd.onion/img/x.jpg` → verschleiert (fremder Host mit `/img/`) |
| BS11 | `/forum/img/../uploads/x.jpg` → verschleiert |
| BS12 | `/pix/…`, `/forum/uploads/…` → verschleiert; `/forum/style/x.png` und `/forum/v4/style/a/b.png` → klar |
| BS13 | `/forum/1bg.png` klar, `/forum/1bg.png.jpg` und `/forum/x/1bg.png` verschleiert |
| BS14 | Forenquelltext: kein Inline-Stil mit zwei `url()` (Annahme aus 5.2) |
| BS15 | Relative Präfixe: Seite `/forum/beginner/…` → `../img/` klar, `img/` verschleiert |
| BS16 | Kodierte `fileasset`-Form entsteht mit derselben Funktion wie in `blob_handler` |
| BS17 | Shell enthält `image-veil.css` **vor** jedem Body-Inhalt und vor `toolbar.css` |
| BS18 | `POST` ohne Recht → 403, keine Zeile, kein Audit |
| BS19 | Schalter: gesperrt → Klick ohne Wirkung, kein Request |
| BS20 | Einschalten setzt die Klasse **vor** dem Request |
| BS21 | Fehlgeschlagenes Ausschalten lässt die Klasse stehen |
| BS22 | `researcher` hat im Katalog kein Recht `imageveil.lift` |
| BS23 | CSS-Datei: `../img/icons/x.png` aus `/forum/style/Air.css` klar, `/pix/banner/s9/1.jpg` → Platzhalter |
| BS24 | Ohne Schleier wird CSS **nicht** verändert |
| BS25–BS27 | Hülle: `Sec-Fetch-Dest: document` → HTML; `image` → Bytes; Rückgriff `Accept` |
| BS28 | Hülle nicht bei ausgenommener URL und nicht ohne Schleier |
| BS29 | Bildantworten tragen `Vary: Sec-Fetch-Dest, Accept` |
| BS30 | `<style>`-Blöcke im Body: `url()` ersetzt, BLOB unverändert |

---

## 10. PoC in PROD (Alex, nach Build 772/773, mit unverfänglichem Testbild)

| Nr. | Wann/Wo | Beobachten |
|---|---|---|
| P1 | DevTools → Network → „Disable cache“ **aus**; Throttling „Slow 3G“; Seite mit Bild laden | Kein Frame zeigt das Bild unverschleiert. |
| P2 | Schaltfläche umschalten | Seite lädt neu, Scrollposition bleibt, Icon zeigt den neuen Zustand. |
| P3 | Bild einmal im Viewer laden, dann Bildlink per Mittelklick in neuem Tab öffnen | Hülle mit Schleier, **nicht** Rohbild aus dem Cache. Network-Spalte „Size“ darf nicht „(disk cache)“ für die Navigation zeigen. |
| P4 | Als `researcher` anmelden | Icon ausgegraut, Tooltip „Recht fehlt“, Klick wirkungslos. |

---

## 11. Offene Punkte

- **Entschieden (Alex, 09.10.2026):** Benennungen wie vorgeschlagen;
  Forenhost `alicefe3…onion`; Cache-Verhalten (5.4) wird im PoC P3 getestet.
- **`/style/` (Wurzel):** siehe 3.2 — Entscheidung ausstehend.
- **Grund `required_by_role`:** Vorschlag v0.2, damit Forschende einen
  eigenen Tooltip-Text erhalten. Entscheidung ausstehend.
- **Weiterer Host `6hvtnsvqo5jpq…onion`** (`bbcode.php` Z. 52): Forenhost
  oder nicht? Entscheidung ausstehend; bis dahin nicht ausgenommen.
- **Icon:** Inline-SVG statt Unicode-Zeichen. Entscheidung ausstehend.
