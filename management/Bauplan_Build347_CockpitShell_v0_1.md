# Bauplan Build 347 — Cockpit-Shell (Fundament)

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface), Welle 0 → Welle 1 (Cockpit-Sichten)
**Autoritativ:** `Bauplan_Baustelle7_Management_v1_1.md` §11.2 (Cockpit-Shell,
policy-getriebene Nav, `/static`), §11.7 (Welle 1); Referenzlayout
`AIW_Verwaltung_Mockup.html`; Übergabe `UEBERGABE_Build346_ff.md` §6.
**Basis:** HEAD `232c362` — Version 0.7.346 (Management-Server-Backend).

---

## 1. Ziel und Abgrenzung

Build 347 legt das **Fundament** der policy-getriebenen Verwaltungsoberfläche:
statische Auslieferung im Management-Server + Shell-Skelett (HTML/CSS) +
`cockpit.js` mit Navigation, die **allein aus `/api/whoami`** entsteht (Rechte
= `capabilities{cap: scope}`, nicht aus einem fest verdrahteten Rollenbild).

**Split (analog 314/315/346):** 347 = testbarer Kern (Static-Serving via pytest,
Nav-Modell via vitest) → **CI-grün ohne Live-Browser**. Die eigentlichen Sichten
(Overview-/Integritäts-**Tabellen** über `/api/overview` bzw. `/api/integrity`,
**SSE-Reload** über `/events`) folgen in **Build 348** — erster echter
Browser-Abnahme-Build, **console-first**.

**Migration:** keine (reiner Lesepfad + statische Assets).

---

## 2. Umfang (geliefert)

### 2.1 Backend (pytest-testbar)

- **NEU `management/server/static_assets.py`** — `StaticAssets` (Grundregel 10).
  Sichere Auslieferung aus festem Basisverzeichnis:
  - **MIME-Whitelist** (`.html/.js/.css/.map/.svg`) statt Blacklist.
  - **Doppelte Traversal-Abwehr:** (a) String-Prüfung (`..`, führendes `/`,
    Backslash, leer → **400**); (b) `realpath`-Containment gegen Ausbruch aus
    dem Basisverzeichnis (Symlink/Normalisierung → **400**).
  - Fehlend / nicht erlaubter Typ → **404**; einheitlicher JSON-Fehlerkörper
    (kein stiller Fehlpfad, Grundregel 1).
  - Rückgabe `(status, ctype, body)` — **kein** Import der `Response`
    (vermeidet Zirkularimport). Muster: `forensic_api/static.handle_vendor_asset`
    (Build 084).
- **GEÄNDERT `management/server/management_app.py`:**
  - `/` liefert jetzt die statische **`cockpit.html`** — der Platzhalter
    `_SHELL_HTML` **entfällt**; der Anzeigename wird im Browser per
    `fetch('/api/whoami')` gesetzt.
  - `/static/<f>` liefert echte Assets über `StaticAssets` (statt 404-Platzhalter).
  - `ManagementApp(db_path, static_dir=None)` — `static_dir` im Test injizierbar;
    PROD = `STATIC_DIR` neben dem Modul.
  - `whoami`/`overview`/`integrity`/SSE unverändert; read-only.

### 2.2 Frontend (vitest-testbar + Browser-Smoke als Abnahme)

- **NEU `management/server/static/cockpit.html`** — statische Shell (KEINE
  Inline-Daten) nach Referenzlayout: Kopf mit Anzeigename-Slot, Integritäts-
  Banner-Slot (neutral; Bindung folgt 348), Nav-Container `#aiw-nav`, `#aiw-main`.
  Bindet `cockpit.css`/`cockpit.js` + vendorte Tabulator (`defer`, in 347 noch
  ungenutzt — reduziert Churn für 348).
- **NEU `management/server/static/cockpit.css`** — Stile aus dem Mockup
  (Nav-Gruppen, Scope-Tags `alle`/`eigene`, Kacheln, Tabellen, Leerzustand);
  **ohne** Rollen-Umschalter (Identität server-fixiert).
- **NEU `management/server/static/cockpit.js`** — IIFE, DEV-Debug-Log
  abschaltbar, ausführlich kommentiert, gekapselt; **reine Funktionen
  UMD-exportiert** (vitest testet ECHTEN Code):
  - `VIEW_CATALOG`: 10 Sichten aus dem Mockup + `integrity` (cap `ops.view`,
    Backend `/api/integrity` vorhanden).
  - Rein: `hasCap`, `visibleViews`, `scopeTag`, `firstViewId`, `groupSequence`,
    `viewById` (kein DOM).
  - DOM: `setWho` (display_name via **textContent** — AD-Herkunft, XSS-sicher),
    `buildNav` (Gruppenköpfe + Nav-Buttons + Scope-Tags + aktive Klasse +
    Klick-Callback), `renderPlaceholder` (Leerzustand; Sichten-Verdrahtung 348).
  - `boot()`: `fetch('/api/whoami')` → Nav bauen → erste sichtbare Sicht.
    **Auto-Boot nur im echten Browser** (`window`+`document`+`fetch`); unter
    Node/Vitest kein Boot (sonst sprengt fehlendes `fetch` den Modul-Eval).
- **NEU `management/server/static/vendor/tabulator/{tabulator.min.js,
  tabulator.min.css}`** — management-lokale Kopie (Selbstgenügsamkeit; **ohne**
  die großen `.map`-Dateien). ECharts zurückgestellt bis zur ersten
  Diagramm-Sicht (§11.7 Welle 0, Punkt 6).

### 2.3 Tests

- **NEU `tests/test_management_static.py`** (S01–S10): MIME-Whitelist,
  Traversal-Abwehr, 404 (fehlend/kein Typ), Unterverzeichnis, realpath-
  Containment, `/` → echte `cockpit.html`, `/static/<f>` echt/fehlend/Traversal,
  vendorte Tabulator ausgeliefert.
- **NEU `tests/unit/test_cockpit_nav.test.js`** (CN01–CN10, JSDOM,
  `window.AIWCockpit`): `visibleViews`/`scopeTag`/`firstViewId`/`groupSequence`,
  `buildNav` (DOM + Klick-Callback), `setWho` (XSS-sicher), `renderPlaceholder`.
- **GEÄNDERT `tests/test_management_server.py`:** M04 (jetzt statische
  `cockpit.html`) und M05 (jetzt `/static/cockpit.js` → 200; fehlend → 404) auf
  den neuen 347-Vertrag angepasst — das **Platzhalter-Verhalten von 346 ist
  bewusst ersetzt** (dokumentierte Vertragsänderung).

---

## 3. Regression (run_tests.py)

```
pytest : 865 passed, 59 skipped, 3 subtests   (855 + 10 = test_management_static)
vitest : 477 passed, 1 skipped, 1 todo (479), 35 Testdateien   (467 + 10; 34 + 1)
```

Umgebung dev: Python 3.12.3, SQLite 3.45.1, node v22. Prod: Python 3.14, Win11.

---

## 4. Abnahme (Browser-Smoke, console-first-Vorstufe)

`python management.py --coordinator-db PATH --as-user hXXXXX --auto-port
--open-browser`. Erwartet: Shell lädt; `#aiw-who` zeigt den Anzeigenamen; die
**Navigation entsteht aus den whoami-Fähigkeiten** (nur berechtigte Tabs), mit
korrekten Scope-Tags `alle`/`eigene`; Klick auf einen Tab zeigt den
Leerzustand-Platzhalter. Ohne Grants (default-deny) bleibt die Nav leer und der
Hauptbereich zeigt den default-deny-Hinweis.

---

## 5. Nächster Build (348) — Sichten-Verdrahtung (browser-verifizierbar)

- Overview-Sicht an `/api/overview` (Tabulator.js-Tabelle, Ampel, Scope-Anzeige).
- Integritäts-/Ops-Sicht an `/api/integrity` (+ Banner-Bindung).
- **SSE-Client** an `/events`: bei `changed` betroffene Sicht neu laden (kein F5).
- **console-first-Protokoll:** Console-Output anfordern → PoC für die Console →
  erst dann Roll-out-Fix.

---

*Dokument-Ende · Bauplan Build 347 · 2026-07-10*
