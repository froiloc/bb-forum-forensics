/**
 * userinfo/userinfo.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Nutzerinfo-Tab
 *
 * Zweck:
 *   JavaScript für Fenster 2 (Nutzerinfo-Tab) und Fenster 3 (Bericht-Editor).
 *   Eine Datei für beide Fenster — Erkennung via body-id.
 *
 * Fenster 2 (#userinfo-static vorhanden):
 *   - Dynamische Blöcke via AJAX (/_forensic/userinfo/data) laden
 *   - SSE-Stream (/_forensic/events) abonnieren
 *   - Read-Only-Berichtsreiter befüllen
 *   - Kopier-Buttons initialisieren
 *   - Heatmap-Offset-Schieberegler
 *
 * Fenster 3 (#report-editor-body vorhanden):
 *   - Editor-UI aufbauen
 *   - BroadcastChannel 'forensic_editor_lock' (Schicht 1, §8.6 Bauplan B4)
 *   - Lock erwerben via /_forensic/report (acquire_lock)
 *   - Paragraphen laden und anzeigen
 *   - Neuen Paragraph anlegen
 *   - Beweisanker-Chips rendern und Navigation via window.postMessage
 *   - Lock freigeben bei beforeunload
 *
 * Kommunikation Fenster 3 → Fenster 1 (§9.3 Bauplan B4):
 *   window.opener?.postMessage({ type: 'navigate_to_annotation',
 *                                annotation_id: N }, origin)
 *
 * Version: v0.6.277 · Build: 277 · 2026-06-07
 *
 * Änderungen Build 089 (Bugfix: SSE-Deadlock-Kaskade):
 *   Ursache: Drei zusammenwirkende Probleme führten dazu, dass alle Server-Threads
 *   dauerhaft durch SSE-Verbindungen blockiert wurden und der Server keine weiteren
 *   Requests (insb. POST /_forensic/report) mehr beantworten konnte.
 *   Beleg: freeze_dump_003.txt, Projektgespräch 2026-05-07.
 *
 *   Fix 1 — acquireLock Re-Entry-Guard (_acquireLockRunning):
 *     acquireLock() kann durch mehrere Pfade gleichzeitig aufgerufen werden
 *     (editor_lock_released-SSE-Event, client_id-Reconnect-Pfad, DEV_LOCK_UI=false).
 *     Parallele Aufrufe erzeugten mehrere gleichzeitige POSTs, die den Thread-Pool
 *     erschöpften. Guard verhindert parallele Ausführung.
 *
 *   Fix 2 — editor_lock_released: acquireLock nur bei DEV_LOCK_UI=false:
 *     Der handler rief setTimeout(acquireLock, 500) bedingungslos auf — auch im
 *     DEV-Modus (DEV_LOCK_UI=true), wo der Benutzer den Lock manuell erwirbt.
 *     Im DEV-Modus darf kein automatisches Re-Acquire stattfinden.
 *
 *   Fix 3 — initSSEWindow3: 3s-Timeout verlängert auf 10s, mit Warnung:
 *     Der 3s-Timeout löste die Promise auf bevor der Server client_id liefern
 *     konnte — initEditor() fuhr dann ohne sseClientId fort. Im Normalfall
 *     antwortet der Server in <100ms; 3s war zu knapp für den Startmoment
 *     wenn mehrere SSE-Verbindungen gleichzeitig aufgebaut werden.
 *     10s gibt dem Server ausreichend Puffer. Bei Ablauf wird eine Warnung
 *     im Log ausgegeben statt stumm fortzufahren.
 */

(function() {
'use strict';
console.log('[userinfo.js] IIFE gestartet, readyState=', document.readyState);

// ---------------------------------------------------------------------------
// DEV-Logging (Build 110)
// Beleg: Projektgespraech 2026-05-07
// ---------------------------------------------------------------------------
/** @param {...*} args */
function _dbg(...args) {
    if (window.FORENSIC_DEBUG !== false) {
        console.debug('[forensic]', ...args);
    }
}


// ---------------------------------------------------------------------------
// Konstanten
// ---------------------------------------------------------------------------

const FORENSIC_API = {
    USERINFO_DATA:   '/_forensic/userinfo/data',
    USERINFO_STATIC: '/_forensic/userinfo/static',
    REPORT:          '/_forensic/report',
    EVENTS:          '/_forensic/events',
};

/**
 * DEV_LOCK_UI: Lock-Schaltflächen sichtbar machen.
 * true  = DEV: Buttons 'Lock erwerben' / 'Lock freigeben' sichtbar.
 * false = PROD: Lock wird automatisch erworben und freigegeben;
 *               Buttons werden ausgeblendet, Aktionen via console.log.
 * Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
 */
// Build 114: DEV_LOCK_UI=false → Auto-Lock (kein manueller Lock-Button).
// Beleg: Projektgespraech 2026-05-07
const DEV_LOCK_UI = false;

// Regex für Beweisanker-Syntax [BELEG:annotation_id=N] im Berichtstext
const ANCHOR_PATTERN = /\[BELEG:annotation_id=(\d+)\]/g;

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------

/**
 * Formatiert einen Unix-Timestamp als deutsches Datum/Uhrzeit.
 * @param {number|null} ts - Unix-Timestamp in Sekunden
 * @returns {string}
 */
function formatTs(ts) {
    if (!ts) return '–';
    const d = new Date(ts * 1000);
    return d.toLocaleString('de-DE', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
}

/**
 * HTML-Sonderzeichen escapen.
 * @param {string} s
 * @returns {string}
 */
function esc(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/**
 * Beweisanker-Syntax [BELEG:annotation_id=N] in anklickbare Chips umwandeln.
 * @param {string} text - Rohtext mit Ankern
 * @returns {string} - HTML-String
 */
function renderAnchors(text) {
    return esc(text).replace(
        /\[BELEG:annotation_id=(\d+)\]/g,
        (_, id) => `<span class="anchor-chip" data-annotation-id="${id}"
            role="button" tabindex="0" title="Zur Annotation #${id} navigieren">` +
            `📌 Annotation #${id}</span>`
    );
}

// ---------------------------------------------------------------------------
// Kopier-Button-Initialisierung
// ---------------------------------------------------------------------------

function initCopyButtons() {
    document.querySelectorAll('.copy-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const target = btn.dataset.copyTarget;
            const el = target ? document.querySelector(target) : btn.previousElementSibling;
            if (!el) return;
            const text = el.textContent || el.innerText;
            navigator.clipboard.writeText(text).then(() => {
                const orig = btn.textContent;
                btn.textContent = '✓';
                setTimeout(() => { btn.textContent = orig; }, 1500);
            }).catch(() => {
                // Fallback: execCommand
                const area = document.createElement('textarea');
                area.value = text;
                area.style.position = 'fixed';
                area.style.opacity = '0';
                document.body.appendChild(area);
                area.select();
                document.execCommand('copy');
                document.body.removeChild(area);
            });
        });
    });
}

// ---------------------------------------------------------------------------
// Anker-Klick → Fenster 1 Navigation (§9.3 Bauplan B4)
// ---------------------------------------------------------------------------

function initAnchorNavigation(container) {
    container.addEventListener('click', evt => {
        const chip = evt.target.closest('.anchor-chip');
        if (!chip) return;
        const annotationId = parseInt(chip.dataset.annotationId, 10);
        if (isNaN(annotationId)) return;

        // Nachricht an Fenster 1 (Forum-Viewer) senden
        const target = window.opener || window.parent;
        if (target && target !== window) {
            target.postMessage(
                { type: 'navigate_to_annotation', annotation_id: annotationId },
                window.location.origin
            );
        }
    });

    // Tastaturzugang
    container.addEventListener('keydown', evt => {
        if (evt.key === 'Enter' || evt.key === ' ') {
            const chip = evt.target.closest('.anchor-chip');
            if (chip) {
                evt.preventDefault();
                chip.click();
            }
        }
    });
}

// ===========================================================================
// FENSTER 2 — Nutzerinfo-Tab
// ===========================================================================

/**
 * Statischen Phase-B-BLOB laden und in #userinfo-static einsetzen.
 *
 * Ruft /_forensic/userinfo/static ab. Bei HTTP 204 (Phase B noch nicht
 * gelaufen) wird ein Hinweistext angezeigt. Bei Fehler wird eine
 * Warnung ausgegeben ohne den restlichen Tab zu blockieren.
 *
 * Beleg: Projektgespräch 2026-04-18 — uid_*-Tabellen persistent,
 *        BLOB in static_pages['userinfo'].
 */
async function loadStaticBlob() {
    const container = document.getElementById('userinfo-static');
    if (!container) return;

    try {
        const resp = await fetch(FORENSIC_API.USERINFO_STATIC, {
            headers: { 'X-Forensic-Request': 'ajax' }
        });

        if (resp.status === 204) {
            container.innerHTML =
                '<p style="color:#9aa0b8;font-size:12px;padding:12px 0">' +
                'Forensische Nutzerdaten (Phase B) noch nicht verfügbar. ' +
                'Bitte scraper_stage1.py --only-phase-b ausführen.</p>';
            return;
        }

        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
        }

        const html = await resp.text();
        container.innerHTML = html;

        // Build 088: class und data-uid vom BLOB auf den Container übertragen.
        // Der Renderer erzeugt keinen Wrapper-Div mehr (Prepper Build 061).
        // forensic-userinfo und data-uid wurden vorher vom Wrapper-Div getragen.
        // Beleg: Projektgespräch 2026-05-05 -- doppeltes #userinfo-static.
        container.classList.add('forensic-userinfo');
        const uidMatch = html.match(/data-uid="(\d+)"/);
        if (uidMatch) container.dataset.uid = uidMatch[1];

        initHeatmap(container);
        initTimeline(container);
        initCollapseButtons(container);   // Einfahren-Schaltflächen (Build 013)
        initTabulatorTables(container);   // Filter/Sortierung via Tabulator.js (Build 084)

        // Inhaltsverzeichnis erst JETZT bauen: die BLOB-Karten existieren erst
        // nach container.innerHTML = html. Die aeusseren .ui-card-Bloecke sind
        // bereits im Ausgangs-HTML vorhanden. buildTableOfContents() scannt
        // beide Ebenen. Beleg: Bauplan Userinfo-Verschoenerung v0.2 Pkt.5.
        buildTableOfContents();

    } catch (err) {
        container.innerHTML =
            `<div class="status-msg status-msg-warn">` +
            `Forensische Nutzerdaten konnten nicht geladen werden: ${esc(String(err))}` +
            `</div>`;
    }
}

/**
 * Baut das Inhaltsverzeichnis (#ui-toc) im Kopf und verankert die Karten.
 *
 * Zweck (Beleg: Bauplan Userinfo-Verschoenerung v0.2 Pkt.5, mc 2026-07-10):
 *   Schneller Sprung zu den einzelnen Karten. Es gibt ZWEI Kartensorten:
 *     1. Aeussere Modulbloecke:  .ui-body .ui-card  (Titel = <h2>)
 *     2. BLOB-Karten:            #userinfo-static details.forensic-section
 *                                (Titel = <summary class="forensic-section-title">)
 *
 * Bewusste Entscheidung — Anker per JS statt im BLOB:
 *   Die BLOB-Karten liegen im VERSIEGELTEN forensic_<uid>.db. Wir vergeben die
 *   Anker-id daher zur Laufzeit hier, statt sie in den BLOB zu backen. So bleibt
 *   Welle A vollstaendig webserver-seitig und migrationsfrei.
 *
 * Robustheit:
 *   - Fehlt #ui-toc (alte Seite) -> stiller Abbruch, kein Fehler.
 *   - Werden keine Karten gefunden -> #ui-toc bleibt versteckt.
 *   - id-Kollisionen werden durch Zaehler-Suffix aufgeloest.
 */
function buildTableOfContents() {
    const toc = document.getElementById('ui-toc');
    if (!toc) {
        _dbg('buildTableOfContents: #ui-toc nicht vorhanden - uebersprungen');
        return;
    }

    // Sammel-Liste {el, title, kind}. el ist das Element, das die Anker-id
    // erhaelt (die .ui-card bzw. das <details>).
    const entries = [];

    // (1) Aeussere Modulbloecke
    document.querySelectorAll('.ui-body .ui-card').forEach((card) => {
        const h2 = card.querySelector('h2');
        if (!h2) return;
        entries.push({ el: card, title: h2.textContent.trim(), kind: 'card' });
    });

    // (2) BLOB-Karten (nur wenn bereits geladen)
    document.querySelectorAll('#userinfo-static details.forensic-section')
        .forEach((det) => {
            const sum = det.querySelector('summary.forensic-section-title');
            if (!sum) return;
            entries.push({ el: det, title: sum.textContent.trim(), kind: 'section' });
        });

    _dbg('buildTableOfContents: %d Karten gefunden', entries.length);

    if (entries.length === 0) {
        toc.hidden = true;
        return;
    }

    // Anker-id-Vergabe mit Slug + Kollisionsschutz.
    const seen = Object.create(null);
    const slug = (s) => {
        let base = 'toc-' + s.toLowerCase()
            .replace(/[^a-z0-9\u00e4\u00f6\u00fc\u00df]+/g, '-')
            .replace(/^-+|-+$/g, '')
            .slice(0, 40);
        if (!base || base === 'toc-') base = 'toc-karte';
        let id = base, n = 2;
        while (seen[id] || document.getElementById(id)) { id = base + '-' + (n++); }
        seen[id] = true;
        return id;
    };

    // TOC-Markup aufbauen. innerHTML einmalig, dann Click-Handler delegiert.
    let html = '<span class="ui-toc-label">Springe zu:</span>';
    entries.forEach((entry) => {
        // Vorhandene id respektieren, sonst neue vergeben.
        if (!entry.el.id) entry.el.id = slug(entry.title);
        html += `<a href="#${esc(entry.el.id)}" data-toc-target="${esc(entry.el.id)}">`
              + `${esc(entry.title)}</a>`;
    });
    toc.innerHTML = html;
    toc.hidden = false;

    // Delegierter Klick-Handler: sanftes Scrollen; falls Ziel ein
    // eingeklapptes <details> ist, vorher aufklappen, damit der Inhalt
    // sichtbar wird. Beleg: BLOB-Karten sind <details> und starten meist zu.
    toc.addEventListener('click', (evt) => {
        const a = evt.target.closest('a[data-toc-target]');
        if (!a) return;
        evt.preventDefault();
        const target = document.getElementById(a.dataset.tocTarget);
        if (!target) {
            _dbg('TOC-Klick: Ziel %s nicht gefunden', a.dataset.tocTarget);
            return;
        }
        if (target.tagName === 'DETAILS' && !target.open) {
            target.open = true;
        }
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        _dbg('TOC-Klick: zu %s gesprungen', a.dataset.tocTarget);
    });
}

/**
 * Dynamische Blöcke laden und in #userinfo-dynamic einsetzen.
 */
/**
 * Ermittlungsergebnis-Bewertung laden und rendern (Build 390).
 *
 * Ein Abruf liefert alles, was die Maske braucht (Katalog + Stand + Historie
 * + Kennzahl) — der Katalog ist DATEN (Build 387), nicht Code: die
 * Auswahlfelder werden daraus gebaut, nicht aus einer JS-Konstante.
 *
 * KEIN optimistisches UI: nach jedem Schreibvorgang wird neu geladen. Und ein
 * 403 (fehlende Faehigkeit) wird ANGEZEIGT, nicht in eine leere Karte
 * verwandelt — der Ermittler soll wissen, WARUM er nichts sieht.
 */
async function loadResults(pendingMsg) {
    const card = document.getElementById('userinfo-results');
    if (!card) return;
    const mod = window.AIWUserinfoResults;
    if (!mod) {
        card.innerHTML = `<h2>Ermittlungsergebnis · Bewertung</h2>
            <div class="status-msg status-msg-warn">Modul nicht geladen
            (userinfo_results.js).</div>`;
        return;
    }

    try {
        const resp = await fetch('/_forensic/results', {
            headers: { 'X-Forensic-Request': 'ajax' }
        });
        const data = await resp.json();

        if (!resp.ok) {
            // 403/500 mit Begruendung — sie wird gezeigt, nicht verschluckt.
            card.innerHTML = `<h2>Ermittlungsergebnis · Bewertung</h2>
                <div class="status-msg status-msg-warn">
                ${esc(String(data.detail || data.error || resp.status))}</div>`;
            return;
        }

        const view = mod.renderResults(card, data, {
            onAssess: async (body) => {
                try {
                    const r = await fetch('/_forensic/results/assess', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Forensic-Request': 'ajax'
                        },
                        body: JSON.stringify(body)
                    });
                    const res = await r.json();
                    if (!r.ok) {
                        throw new Error(res.detail || res.error || ('HTTP ' + r.status));
                    }
                    // Neu laden — angezeigt wird nur der bestaetigt
                    // geschriebene Zustand.
                    loadResults('Neuer Stand erfasst (Bewertung '
                        + res.result_id + ', Beleg #' + res.audit_seq
                        + '). Der bisherige Stand bleibt in der Historie.');
                } catch (err) {
                    loadResults('FEHLER: ' + String(err.message || err)
                        + ' — es wurde nichts geschrieben.');
                }
            }
        });

        if (view && pendingMsg) {
            view.setResult(pendingMsg, /^FEHLER/.test(pendingMsg));
        }
        _dbg('Ergebnisbewertung geladen:', (data.current || []).length,
             'aktuelle Bewertungen');
    } catch (err) {
        card.innerHTML = `<h2>Ermittlungsergebnis · Bewertung</h2>
            <div class="status-msg status-msg-warn">
            Bewertung konnte nicht geladen werden: ${esc(String(err))}</div>`;
    }
}

async function loadDynamicBlocks() {
    const container = document.getElementById('userinfo-dynamic');
    if (!container) return;

    try {
        const resp = await fetch(FORENSIC_API.USERINFO_DATA, {
            headers: { 'X-Forensic-Request': 'ajax' }
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        renderDynamicBlocks(container, data);
    } catch (err) {
        container.innerHTML = `<div class="status-msg status-msg-warn">
            Ermittlungsstand konnte nicht geladen werden: ${esc(String(err))}</div>`;
    }
}

/**
 * Dynamische Blöcke rendern.
 * @param {HTMLElement} container
 * @param {object} data - Antwort von /_forensic/userinfo/data
 */
function renderDynamicBlocks(container, data) {
    const {
        annotation_counts = {},
        annotations_total = 0,
        last_annotation   = null,
        investigation_status = null,
        report_status     = {},
        unreferenced_annotations = 0,
    } = data;

    // Annotationszähler
    const countsHtml = Object.entries(annotation_counts)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => `<div class="annotation-count-item">${esc(k)}: <strong>${v}</strong></div>`)
        .join('') || '<span class="negativ-befund">Keine Annotationen</span>';

    // Vollständigkeitsprüfung
    const unrefHtml = unreferenced_annotations > 0
        ? `<div class="unreferenced-warning">
            ⚠ <strong>${unreferenced_annotations}</strong> Annotation(en) ohne Berichtsbezug
           </div>`
        : '';

    // Ermittlungsstatus
    let statusHtml = '';
    if (investigation_status && investigation_status.error) {
        // Build 390 (Grundregel 1): Die Fallakte war NICHT lesbar. Frueher
        // wurde dieser Fehler still zu 'nicht zugewiesen' — der Ermittler
        // sah eine LUEGE statt einer Fehlermeldung (Ursache: JOIN auf die
        // seit M005 nicht mehr existierende Tabelle 'investigators').
        // Jetzt wird der Fehler ANGEZEIGT.
        statusHtml = `<p class="status-msg status-msg-warn">
            <strong>Fallakte nicht lesbar:</strong> ${esc(String(investigation_status.error))}
            <br>Der Zuweisungs- und Statuswert unten fehlt deshalb — er ist
            NICHT etwa leer.</p>`;
    } else if (investigation_status) {
        const { status, priority, assigned_to, note } = investigation_status;
        statusHtml = `<p><strong>Status:</strong> ${esc(status || '–')}
            | <strong>Priorität:</strong> ${priority ?? '–'}
            | <strong>Zugewiesen:</strong> ${esc(assigned_to || '–')}
            ${note ? `<br><em>${esc(note)}</em>` : ''}</p>`;
    }

    // Read-Only-Berichtsreiter
    const editBtn = `<button class="editor-btn" id="btn-open-report">Bearbeiten →</button>`;
    // Build 087: Aktualisieren-Schaltfläche entfernt (nur Bearbeiten in Toolbar). Beleg: Projektgespräch 2026-05-05.

    container.innerHTML = `
        <h3>Ermittlungsstand</h3>
        ${statusHtml}
        <div><strong>Annotationen gesamt:</strong> ${annotations_total}
            ${last_annotation
                ? ` | <span style="font-size:12px;color:#555">Letzter Eintrag: ${formatTs(last_annotation.ts)}
                    von ${esc(last_annotation.investigator)}</span>`
                : ''}
        </div>
        <div class="annotation-count-grid">${countsHtml}</div>
        ${unrefHtml}`;

    // Build 086: Buttons in die fixe Toolbar schreiben (nicht in roContainer).
    // Beleg: Projektgespräch 2026-05-05
    const toolbarActions = document.getElementById('userinfo-toolbar-actions');
    if (toolbarActions) {
        toolbarActions.innerHTML = editBtn;
        // Aktualisieren-Handler entfernt (Build 087).
        document.getElementById('btn-open-report')?.addEventListener('click', () => {
            window.open('/_forensic/report', 'forensic_report');
        });
    }

    // Berichts-Inhalt im normalen Abschnitts-Container sichtbar schalten und befüllen.
    // Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
    const roContainer = document.getElementById('userinfo-report-readonly');
    if (roContainer) {
        roContainer.style.display = '';
        roContainer.innerHTML = `
            <h3>Bericht <span id="report-draft-badge"></span></h3>
            <div id="report-readonly-content">
                <span class="loading-spinner"></span> Lade Berichtsinhalt…
            </div>`;
        loadReadonlyReport();
    }
}

/**
 * Berichtsinhalt in Read-Only-Reiter laden.
 */
async function loadReadonlyReport() {
    const container = document.getElementById('report-readonly-content');
    if (!container) return;

    try {
        const resp = await fetch(FORENSIC_API.REPORT + '?format=json', {
            headers: { 'X-Forensic-Request': 'ajax' }
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        renderReadonlyParagraphs(container, data.paragraphs || []);
    } catch (err) {
        container.innerHTML = `<div class="status-msg status-msg-warn">
            Bericht konnte nicht geladen werden: ${esc(String(err))}</div>`;
    }
}

/**
 * Paragraphen im Read-Only-Reiter rendern.
 * @param {HTMLElement} container
 * @param {Array} paragraphs
 */
function renderReadonlyParagraphs(container, paragraphs) {
    if (!paragraphs.length) {
        container.innerHTML = '<p class="negativ-befund">Noch kein Berichtstext vorhanden.</p>';
        return;
    }
    container.innerHTML = paragraphs.map(p => `
        <div class="report-paragraph">
            <div class="report-paragraph-author">
                ${esc(p.author)} · ${formatTs(p.created_at)}
                ${p.updated_at !== p.created_at ? ` (geändert: ${formatTs(p.updated_at)})` : ''}
            </div>
            <div class="report-paragraph-content">${renderAnchors(p.content)}</div>
        </div>`).join('');
    initAnchorNavigation(container);
}

/**
 * SSE-Stream für Fenster 2 einrichten.
 */
function initSSEWindow2() {
    // Preflight-Prüfung: Duplikat-SSE-Schutz (Build 265).
    // EventSource kann keinen HTTP-Status auslesen — fetch-Preflight nötig.
    // Beleg: Projektgespräch 2026-05-31.
    const _sseUrl = FORENSIC_API.EVENTS + '?role=userinfo';
    // Build 327: Preflight-Header 'X-Forensic-Preflight: 1' ist ZWINGEND — gleiche
    // Fehlerklasse wie Build 324 (role=main), hier fuer role=userinfo (Fenster 2,
    // eigener Preflight-Pfad OHNE SSELayer, siehe _showDuplicateHint). Ohne den
    // Header behandelt der Server (forensic_api/events.py) diesen GET als ECHTEN
    // SSE-Stream und ruft claim_sse_role('userinfo') auf; das danach geoeffnete
    // EventSource kollidiert dann mit dem eigenen Preflight-Stream -> HTTP 409,
    // Fenster 2 bekommt nie seinen Stream. Mit dem Header ist es ein reiner
    // Slot-Check (200 = frei, 409 = belegt). Beleg: Live-Diagnose 2026-07-07.
    fetch(_sseUrl, { method: 'GET', headers: { 'Accept': 'text/event-stream, application/json', 'X-Forensic-Preflight': '1' } })
        .then(function(resp) {
            if (resp.status === 409) {
                return resp.json().then(function(data) {
                    _showDuplicateHint('Nutzerinfo', data.active_window_id);
                });
            }
            _openSSEWindow2(_sseUrl);
        })
        .catch(function() { _openSSEWindow2(_sseUrl); });
}

/** Duplikat-Hinweis für userinfo-Fenster (ohne SSELayer). Beleg: 2026-05-31. */
function _showDuplicateHint(roleLabel, activeWindowId) {
    if (typeof BroadcastChannel !== 'undefined') {
        var bc = new BroadcastChannel('forensic_control');
        bc.postMessage({ type: 'request_focus', role: 'userinfo', active_window_id: activeWindowId });
        bc.close();
    }
    var msg = document.createElement('div');
    msg.style.cssText = 'position:fixed;inset:0;z-index:999999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);font-family:system-ui,sans-serif';
    msg.innerHTML = '<div style="background:#fff;border-radius:8px;padding:28px 32px;max-width:420px;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,0.35)">'
        + '<div style="font-size:2rem;margin-bottom:12px">\u26a0\ufe0f</div>'
        + '<h2 style="margin:0 0 12px;font-size:1.1rem;color:#b00">Duplikat-Fenster</h2>'
        + '<p style="color:#444;line-height:1.5">Ein <strong>' + roleLabel + '</strong>-Fenster ist bereits offen. Dieses Tab erhält keine Echtzeit-Updates.</p>'
        + '<button id="sse-dup-close" style="margin:12px 8px 0 0;padding:8px 16px;border:none;border-radius:5px;background:#c0392b;color:#fff;cursor:pointer;font-weight:600">Tab schließen</button>'
        + '<button id="sse-dup-keep" style="margin:12px 0 0;padding:8px 16px;border:1px solid #aaa;border-radius:5px;background:#f5f5f5;cursor:pointer">Trotzdem benutzen</button>'
        + '<p id="sse-dup-hint" style="display:none;margin-top:10px;color:#b00;font-size:0.88rem">Bitte schließe dieses Tab manuell mit Strg+W.</p>'
        + '</div>';
    document.body.appendChild(msg);
    document.getElementById('sse-dup-close').addEventListener('click', function() {
        window.close();
        setTimeout(function() { var h=document.getElementById('sse-dup-hint'); if(h) h.style.display='block'; }, 400);
    });
    document.getElementById('sse-dup-keep').addEventListener('click', function() {
        document.body.removeChild(msg);
    });
}

function _openSSEWindow2(sseUrl) {
    const evtSrc = new EventSource(sseUrl);

    evtSrc.addEventListener('annotation_added', () => {
        loadDynamicBlocks();
    });

    evtSrc.addEventListener('report_updated', () => {
        loadReadonlyReport();
    });

    evtSrc.addEventListener('status_changed', () => {
        loadDynamicBlocks();
    });

    evtSrc.onerror = () => {
        // EventSource reconnect ist automatisch — kein expliziter Code nötig
    };
}

// ===========================================================================
// FENSTER 3 — Bericht-Editor
// ===========================================================================

/** Editor-Zustand */
const EditorState = {
    lockId:     null,   // Aktuell gehaltene lock_id oder null
    sseClientId: null,  // SSE-Client-ID dieser Sitzung
    frozen:     false,  // true wenn Editor eingefroren (Duplikat-Fenster)
    instanceId: null,   // Zufällige ID für BroadcastChannel-Mechanismus
};
// Auf window exportieren damit editor.js (anderer Scope) darauf zugreifen kann.
// Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-20 — PoC bestaetigt
window.EditorState = EditorState;

/** BroadcastChannel für Schicht 1 des Lock-Mechanismus (§8.6 Bauplan B4). */
let _broadcastChannel = null;

/**
 * Editor initialisieren.
 */
async function initEditor() {
    _dbg('initEditor() gestartet');
    const body = document.getElementById('report-editor-body');
    if (!body) return;

    // Paket 9 / Build 254: Layer-Architektur wird von editor_bootstrap.js
    // initialisiert, das mit defer NACH userinfo.js geladen wird.
    // initEditor() muss warten bis alle Layer bereit sind, bevor es auf
    // window.lockLayer, window.reportLayer etc. zugreift.
    // Fallback: 10s Timeout damit die Seite nicht einfriert wenn Bootstrap fehlschlägt.
    // Beleg: editor_bootstrap.js ready-Kette, Paket 9
    if (window.documentLayer) {
        await window.documentLayer.ready;
    } else {
        await new Promise(resolve => {
            const t0 = Date.now();
            const poll = setInterval(() => {
                if (window.documentLayer) {
                    clearInterval(poll);
                    window.documentLayer.ready.then(resolve);
                } else if (Date.now() - t0 > 10000) {
                    clearInterval(poll);
                    console.warn('[userinfo] Timeout: documentLayer nicht bereit nach 10s');
                    resolve();
                }
            }, 50);
        });
    }

    // Eindeutige Instanz-ID aus sessionStorage lesen oder neu erzeugen
    EditorState.instanceId = sessionStorage.getItem('forensic_editor_instance')
        || (() => {
            const id = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
            sessionStorage.setItem('forensic_editor_instance', id);
            return id;
        })();

    // Build 113: report-editor-container entfernt.
    // Lock-UI-Elemente (report-lock-status, btn-acquire-lock, btn-release-lock,
    // btn-request-takeover) existieren jetzt als feste HTML-Elemente in der
    // Action-Bar (#report-action-bar-buttons) — kein dynamisches Injizieren.
    // editorjs-holder liegt direkt in #report-main-col.
    // Beleg: Projektgespraech 2026-05-07
    //
    // DEV_LOCK_UI: Lock-Buttons in Action-Bar einblenden
    if (DEV_LOCK_UI) {
        const bar = document.getElementById('report-action-bar-buttons');
        if (bar && !document.getElementById('btn-acquire-lock')) {
            const btnAcquire = document.createElement('button');
            btnAcquire.id = 'btn-acquire-lock';
            btnAcquire.className = 'report-btn report-btn-primary';
            btnAcquire.title = 'Editor-Lock erwerben';
            btnAcquire.textContent = '🔒 Lock erwerben';
            const btnRelease = document.createElement('button');
            btnRelease.id = 'btn-release-lock';
            btnRelease.className = 'report-btn';
            btnRelease.disabled = true;
            btnRelease.title = 'Editor-Lock freigeben';
            btnRelease.textContent = '🔓 Lock freigeben';
            const btnTakeover = document.createElement('button');
            btnTakeover.id = 'btn-request-takeover';
            btnTakeover.className = 'report-btn';
            btnTakeover.style.display = 'none';
            btnTakeover.title = 'Lock von anderem Ermittler anfordern';
            btnTakeover.textContent = '🔔 Lock anfordern';
            // Vor dem Lock-Indikator einfuegen
            const lockIndicator = document.getElementById('report-lock-indicator');
            if (lockIndicator) {
                bar.insertBefore(btnTakeover, lockIndicator);
                bar.insertBefore(btnRelease, lockIndicator);
                bar.insertBefore(btnAcquire, lockIndicator);
            } else {
                bar.appendChild(btnAcquire);
                bar.appendChild(btnRelease);
                bar.appendChild(btnTakeover);
            }
        }
    }

    // Schicht 1: BroadcastChannel — Duplikat-Erkennung (§8.6 Bauplan B4)
    initBroadcastLock();

    // Paket 9: SSE-Verbindung und Lock-Erwerb werden von editor_bootstrap.js
    // über die Layer-Architektur verwaltet. initSSEWindow3() und acquireLock()
    // sind Stubs; der eigentliche Lock-Erwerb läuft über LockLayer.
    // initReportSelector() startet den Bericht-Ladevorgang.
    // Beleg: editor_bootstrap.js, LockLayer.acquire(), Paket 9
    await initSSEWindow3(); // Stub — sofortiger Rückkehr, SSELayer läuft bereits
    document.getElementById('btn-annotations-sidebar')?.addEventListener('click', () => {
        if (window.toggleAnnotationSidebar) toggleAnnotationSidebar();
    });
    document.getElementById('btn-request-takeover')?.addEventListener('click', requestTakeover);

    // Lock bei Seitenentladung freigeben (§8.6 Bauplan B4 — beforeunload)
    // Vor dem Lock-Freigeben noch den aktuellen Editor-Zustand speichern.
    // Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
    window.addEventListener('beforeunload', () => {
        if (window.lockLayer?.lockId) {
            // Auto-Save-Timer sofort ausloesen (Debounce umgehen)
            if (window._editor && window._currentReportId) {
                window._editor.save().then(data => {
                    // Kein await moeglich in beforeunload — Fire-and-forget
                }).catch(() => {});
            }
            releaseLock(true);
        }
    });

    // Editor.js-Modul initialisieren (editor.js).
    // Beleg: AP-E4, Projektgespraech 2026-04-19
    if (window.initEditorModule) {
        await window.initEditorModule();
    }
}

/**
 * Schicht 1: BroadcastChannel für Duplikat-Fenstererkennung (§8.6 Bauplan B4).
 * sessionStorage wird beim Fenster-Duplizieren vererbt — genau dieselbe instanceId.
 * Empfängt 'claim' von anderen Instanzen und friert Duplikate ein.
 */
function initBroadcastLock() {
    if (!window.BroadcastChannel) return;

    _broadcastChannel = new BroadcastChannel('forensic_editor_lock');

    _broadcastChannel.addEventListener('message', evt => {
        const { type, instanceId } = evt.data || {};
        if (type === 'claim' && instanceId !== EditorState.instanceId) {
            // Andere Instanz hat denselben BroadcastChannel — wir sind Duplikat
            freezeEditor();
        }
    });

    // Eigenen Claim senden — andere Instanzen sehen ihn
    _broadcastChannel.postMessage({ type: 'claim', instanceId: EditorState.instanceId });
}

/**
 * Editor einfrieren (Duplikat-Fenster, §8.6 Bauplan B4 Schicht 1).
 */
function freezeEditor() {
    if (EditorState.frozen) return;
    EditorState.frozen = true;
    const overlay = document.getElementById('report-frozen-overlay');
    if (overlay) overlay.classList.add('visible');
    updateLockStatus('lock-frozen', 'Eingefroren (anderes Fenster aktiv)');
    // Alle Schaltflächen deaktivieren
    document.querySelectorAll('#report-editor-container button').forEach(b => b.disabled = true);
}

/**
 * Paket 9: initSSEWindow3() entfernt.
 * SSE wird jetzt von editor_bootstrap.js über SSELayer verwaltet.
 * Beleg: Paket 9, editor_bootstrap.js
 */
async function initSSEWindow3() {
    console.debug('[userinfo] initSSEWindow3: Paket 9 — SSELayer übernimmt. Stub.');
}

/**
 * Paket 9: acquireLock() entfernt.
 * Lock wird jetzt von editor_bootstrap.js über LockLayer verwaltet.
 * Beleg: Paket 9, LockLayer.acquire()
 */
async function acquireLock(reportId) {
    console.debug('[userinfo] acquireLock: Paket 9 — LockLayer übernimmt. Stub.');
    if (window.lockLayer) return window.lockLayer.acquire();
}

/**
 * Paket 9: releaseLock() entfernt.
 * Lock wird jetzt von editor_bootstrap.js über LockLayer verwaltet.
 * Beleg: Paket 9, LockLayer.release()
 */
function releaseLock(sync = false) {
    console.debug('[userinfo] releaseLock: Paket 9 — LockLayer übernimmt. Stub.');
    if (window.lockLayer) return window.lockLayer.release(sync);
}

/**
 * Paragraphen laden und rendern.
 */
async function reloadParagraphs() {
    const list = document.getElementById('report-paragraphs-list');
    if (!list) return;

    try {
        const resp = await fetch(FORENSIC_API.REPORT + '?format=json', {
            headers: { 'X-Forensic-Request': 'ajax' }
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        renderEditorParagraphs(list, data.paragraphs || []);
    } catch (err) {
        list.innerHTML = `<li><div class="status-msg status-msg-warn">
            Paragraphen konnten nicht geladen werden: ${esc(String(err))}</div></li>`;
    }
}

/**
 * Paragraphen im Editor rendern.
 * @param {HTMLElement} list
 * @param {Array} paragraphs
 */
function renderEditorParagraphs(list, paragraphs) {
    if (!paragraphs.length) {
        list.innerHTML = '<li><p class="negativ-befund">Noch kein Berichtstext. Lock erwerben und ersten Paragraph anlegen.</p></li>';
        return;
    }
    list.innerHTML = paragraphs.map(p => `
        <li class="editor-paragraph" data-id="${p.id}">
            <div class="editor-paragraph-header">
                <strong>${esc(p.author)}</strong>
                <span>${formatTs(p.created_at)}</span>
                ${p.status === 'superseded'
                    ? '<span style="color:#e65100">[überarbeitet]</span>'
                    : ''}
            </div>
            <div class="editor-paragraph-content">${renderAnchors(p.content)}</div>
            <div class="editor-paragraph-actions">
                <button class="editor-btn btn-suggest" data-id="${p.id}"
                    title="Änderungsvorschlag einreichen">Vorschlag</button>
            </div>
        </li>`).join('');

    // Anker-Navigation
    initAnchorNavigation(list);

    // Vorschlags-Buttons
    list.querySelectorAll('.btn-suggest').forEach(btn => {
        btn.addEventListener('click', () => openSuggestDialog(parseInt(btn.dataset.id, 10)));
    });
}

/**
 * Neuen Paragraph speichern.
 */
async function saveNewParagraph() {
    // Paket 9: Lock-Check über LockLayer. Beleg: Paket 9
    if (!window.lockLayer?.lockId) {
        showStatusMsg('Lock erforderlich.', 'warn');
        return;
    }
    const textarea = document.getElementById('report-new-content');
    const content = (textarea?.value || '').trim();
    if (!content) {
        showStatusMsg('Inhalt darf nicht leer sein.', 'warn');
        return;
    }

    try {
        const resp = await fetch(FORENSIC_API.REPORT, {
            method: 'POST',
            headers: {
                'Content-Type':        'application/json',
                'X-Forensic-Lock-Id':  window.lockLayer?.lockId,
            },
            body: JSON.stringify({ action: 'add_paragraph', content }),
        });
        const data = await resp.json();

        if (resp.ok) {
            if (textarea) textarea.value = '';
            showStatusMsg('Paragraph gespeichert.', 'ok');
            await reloadParagraphs();
        } else {
            showStatusMsg(`Fehler: ${esc(data.error || resp.status)}`, 'error');
        }
    } catch (err) {
        showStatusMsg(`Netzwerkfehler: ${esc(String(err))}`, 'error');
    }
}

// cancelNewParagraph() entfernt in AP-E4 — durch Editor.js ersetzt.

/**
 * Einfacher Änderungsvorschlags-Dialog (inline, kein Modal-Framework).
 */
function openSuggestDialog(paragraphId) {
    // Vorhandenen Dialog schließen
    document.getElementById('suggest-dialog')?.remove();

    const li = document.querySelector(`.editor-paragraph[data-id="${paragraphId}"]`);
    if (!li) return;

    const origContent = li.querySelector('.editor-paragraph-content')?.textContent || '';
    const dialog = document.createElement('div');
    dialog.id = 'suggest-dialog';
    dialog.style.cssText = 'margin-top:8px;background:#fff3e0;border:1px solid #ffcc80;border-radius:4px;padding:10px';
    dialog.innerHTML = `
        <div style="font-size:12px;margin-bottom:6px">Änderungsvorschlag für Paragraph #${paragraphId}:</div>
        <textarea id="suggest-content" style="width:100%;min-height:60px;font-size:13px;font-family:inherit;
            border:1px solid #ccc;border-radius:2px;padding:4px"
            aria-label="Vorschlag">${esc(origContent)}</textarea>
        <div style="margin-top:6px;display:flex;gap:6px">
            <button class="editor-btn editor-btn-primary" id="btn-submit-suggest">Einreichen</button>
            <button class="editor-btn" id="btn-cancel-suggest">Abbrechen</button>
        </div>`;

    li.appendChild(dialog);

    document.getElementById('btn-cancel-suggest')?.addEventListener('click', () => dialog.remove());
    document.getElementById('btn-submit-suggest')?.addEventListener('click', async () => {
        const content = (document.getElementById('suggest-content')?.value || '').trim();
        if (!content) return;
        try {
            const resp = await fetch(FORENSIC_API.REPORT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action:            'suggest_change',
                    paragraph_id:      paragraphId,
                    suggested_content: content,
                }),
            });
            const data = await resp.json();
            dialog.remove();
            if (resp.ok) {
                showStatusMsg('Vorschlag eingereicht.', 'ok');
            } else {
                showStatusMsg(`Fehler: ${esc(data.error || resp.status)}`, 'error');
            }
        } catch (err) {
            showStatusMsg(`Netzwerkfehler: ${esc(String(err))}`, 'error');
        }
    });
}

/**
 * Statusmeldung anzeigen (auto-fade nach 4s).
 */
function showStatusMsg(text, level) {
    const el = document.getElementById('report-status-msg');
    if (!el) return;
    el.innerHTML = `<div class="status-msg status-msg-${level}">${esc(text)}</div>`;
    setTimeout(() => { el.innerHTML = ''; }, 4000);
}

// ===========================================================================
// Initialisierung — Fenstererkennung
// ===========================================================================

/**
 * Einstiegspunkt: Fenster-Typ erkennen und passende Initialisierung starten.
 *
 * Absicherung gegen defer-Timing-Problem: Wenn readyState bereits 'complete'
 * oder 'interactive' ist (DOM fertig), wird der Handler sofort aufgerufen
 * statt auf DOMContentLoaded zu warten das bereits gefeuert hat.
 * Beleg: Build 257, Bugfix defer-Timing
 */
function _onDOMReady() {
    console.log('[userinfo.js] _onDOMReady() aufgerufen');
    _dbg('DOMContentLoaded: userinfo.js aktiv');
    const isEditor = !!document.getElementById('report-editor-body');
    const isNutzerinfo = !!document.getElementById('userinfo-static');

    if (isEditor) {
        // Fenster 3: Bericht-Editor
        initEditor();
    } else if (isNutzerinfo) {
        // Fenster 2: Nutzerinfo-Tab
        initCopyButtons();
        loadStaticBlob();       // Phase-B-BLOB in #userinfo-static (Build 037)
        loadDynamicBlocks();
        loadResults();          // Ergebnisbewertung (Build 390)
        initSSEWindow2();
        initForensicLinks();    // navigate_to_url via postMessage (Build 038)
    }
}

if (document.readyState === 'loading') {
    console.log('[userinfo.js] readyState=loading — addEventListener');
    document.addEventListener('DOMContentLoaded', _onDOMReady);
} else {
    console.log('[userinfo.js] readyState=' + document.readyState + ' — sofortiger Aufruf');
    _onDOMReady();
}


// ===========================================================================
// FENSTER 2 — Tabulator.js Filter/Sortierung auf forensic-data-Tabellen
// ===========================================================================

/**
 * Initialisiert Tabulator.js auf allen <table class="forensic-data"> im
 * gegebenen Container.
 *
 * Tabulator.js wird als statische Vendor-Bibliothek über
 * /_forensic/static/vendor/tabulator/ ausgeliefert (Build 084).
 * Es ersetzt die rohen <table>-Elemente durch interaktive Tabellen
 * mit Spalten-Sortierung und Zeilenfilterung.
 *
 * Forensische Grundregel: Der BLOB selbst bleibt unverändert (immutabel).
 * Tabulator.js operiert ausschließlich auf dem DOM nach der Injektion.
 * Beleg: Matrijoshka-Prinzip, Projektgespräch 2026-05-05.
 *
 * @param {HTMLElement} container — Wurzelelement (#userinfo-static)
 */
// BEKANNTER BUG (TODO-002): Gelegentliche Kollision zwischen Tabulator.js-Sortierpfeilen
// und dem _initLeftBorderCollapse-Click-Handler. Symptom: Klick auf Spaltenüberschrift
// klappt den Abschnitt ein statt zu sortieren. Reproduzierbarkeit noch unklar.
// Ursache: event.offsetX-Prüfung greift möglicherweise auch auf Klicks innerhalb
// der Tabulator-Tabellenköpfe. Workaround: Click-Handler prüft zusätzlich
// ob das Klickziel ein Tabulator-Element ist.
// Beleg: Projektgespräch 2026-05-05. Wird in eigenem Debug-Durchgang untersucht.
function initTabulatorTables(container) {
    if (typeof Tabulator === 'undefined') {
        // Tabulator.js nicht geladen — kein Fehler, tabellen bleiben statisch
        console.warn('[forensic] Tabulator.js nicht verfügbar — Tabellen ohne Filter/Sortierung.');
        return;
    }

    const tables = container.querySelectorAll('table.forensic-data');
    if (tables.length === 0) return;

    tables.forEach((table, idx) => {
        // Tabelle braucht eine ID für Tabulator
        if (!table.id) {
            table.id = `forensic-tabulator-${idx}`;
        }

        // Spaltendefinitionen aus <thead> extrahieren
        const headers = Array.from(table.querySelectorAll('thead th'));
        if (headers.length === 0) return;

        // Build 087: Zeitstempel-Sorter via data-ts-Attribut.
        // Wenn eine Zelle ein <span class="forensic-ts" data-ts="unix"> enthält,
        // wird der Unix-Timestamp als numerischer Sortierschlüssel verwendet.
        // Beleg: Projektgespräch 2026-05-05 — lexikografische Sortierung ist falsch
        //        wenn der Wochentag voransteht.
        function _tsSorter(a, b) {
            // Versuche data-ts aus dem HTML-Inhalt zu extrahieren
            function extractTs(html) {
                const m = html.match(/data-ts="(\d+)"/);
                return m ? parseInt(m[1], 10) : null;
            }
            const tsA = extractTs(a);
            const tsB = extractTs(b);
            // Wenn beide Timestamps vorhanden: numerisch vergleichen
            if (tsA !== null && tsB !== null) return tsA - tsB;
            // Fallback: Zeichenkettenvergleich
            return String(a).localeCompare(String(b));
        }

        const columns = headers.map((th, colIdx) => ({
            title:     th.textContent.trim(),
            field:     `col${colIdx}`,
            headerFilter: 'input',
            sorter:    _tsSorter,
            formatter: 'html',  // HTML-Inhalt (Links, Spans) erhalten
        }));

        // Datenzeilen aus <tbody> extrahieren (Build 687: inkl. Zeilenkopf-<th>)
        const rows = extractTabulatorRows(table, headers.length);

        // Wrapper-Div für Tabulator erstellen (ersetzt die Tabelle im DOM)
        const wrapper = document.createElement('div');
        wrapper.className = 'forensic-tabulator-wrapper';
        table.parentNode.insertBefore(wrapper, table);
        table.style.display = 'none';  // Original-Tabelle ausblenden (BLOB bleibt intakt)

        // Tabulator instanziieren. Konfiguration in buildTabulatorConfig()
        // ausgelagert (isoliert testbar). Variante A (Pkt.7): Inhaltshoehe,
        // kein maxHeight -> Pager wird nicht mehr gekappt.
        // eslint-disable-next-line no-new
        new Tabulator(wrapper, buildTabulatorConfig(rows, columns));
    });
}

/**
 * Liest die Datenzeilen einer BLOB-Tabelle fuer Tabulator aus.
 *
 * BEFUND (Ticket 1ad6bd69-730e-46d3-a2a3-aecfbd5a0a8f, Alex 2026-08-11,
 * betroffen 0.8.686): In der "Aktivitaets-Timeline (Jahr/Monat x Quelle)" blieb
 * die Spalte "Monat" leer; nur vereinzelt stand dort eine Zahl.
 *
 * URSACHE (belegt, nicht vermutet):
 *   Der Prepper rendert den Monat als ZEILENKOPF, nicht als Datenzelle:
 *     stage1/phase_b_html_renderer.py:1324  ->  f"<th>{MONTH_NAMES[month]}</th>"
 *   Die bisherige Auslese hier nahm ausschliesslich <td>:
 *     Array.from(tr.querySelectorAll('td'))
 *   Damit fehlte je Zeile die ERSTE Zelle. Alle uebrigen Werte rutschten um
 *   genau eine Spalte nach LINKS: col0 (Kopf "Monat") trug in Wahrheit den Wert
 *   der ersten Quellspalte, die letzte Spalte ("Summe") blieb leer.
 *
 * BELEG AUS DEM TICKET (DOM-Auszug, Zeile mit Summe 9):
 *   Kopf:  Monat | Bearbeitungen | ... | Abstimmungen | Beitraege | ... | Summe
 *   Daten: col0=1 | col4=1 | col5=7 | col7=9 | col8=(leer)
 *   9 Kopfspalten stehen 8 Datenzellen gegenueber; 1+1+7=9 landet in col7 statt
 *   in col8. Das erklaert BEIDE Symptome (leerer Monat, leere Summe) aus EINER
 *   Ursache und erklaert auch die "vereinzelten" Monatswerte: sichtbar wurde
 *   dort nicht der Monat, sondern der verrutschte Wert der Nachbarspalte.
 *
 * WARUM DER FIX HIER UND NICHT IM PREPPER LIEGT:
 *   Die Nutzerinfo-Seiten liegen als BLOB in evidence_<uid>.db. Ein geaenderter
 *   Prepper repariert nur KUENFTIG erzeugte BLOBs; alle bereits erfassten
 *   Faelle blieben falsch und muessten neu erhoben oder migriert werden
 *   (Wartungsvorbehalt ab 01.07.2026). Die Auslese im Webserver dagegen wirkt
 *   sofort auf JEDEN Bestand. <th> als Zeilenkopf ist ausserdem semantisch
 *   korrekt und bleibt zulaessig — diese Funktion nimmt beide Formen an.
 *
 * :scope-Selektor: nur die DIREKTEN Zellen der Zeile, damit eine kuenftig
 * verschachtelte Tabelle nicht Zellen in die Elternzeile einschleust.
 *
 * GRUNDREGEL 1 (kein stilles Uebergehen): Weicht die Zellenzahl einer Zeile von
 * der Zahl der Kopfspalten ab, wird das auf der Konsole vermerkt. Die Zeile
 * wird trotzdem uebernommen — ein unvollstaendiger Beleg ist besser als ein
 * unterschlagener —, aber der Befund ist auffindbar.
 *
 * @param   {HTMLTableElement} table          — Tabelle mit <thead> und <tbody>
 * @param   {number}           [columnCount]  — Zahl der Kopfspalten (Pruefmass)
 * @returns {Array<object>} Zeilenobjekte {col0..colN} mit innerHTML je Zelle
 */
function extractTabulatorRows(table, columnCount) {
    // ':scope > tbody > tr' statt 'tbody tr': eine verschachtelte Tabelle darf
    // ihre Zeilen nicht als Zeilen der AEUSSEREN Tabelle einschleusen. Der
    // HTML-Parser ergaenzt fehlende <tbody> selbsttaetig, die Auswahl bleibt
    // also auch bei Tabellen ohne ausgeschriebenes <tbody> vollstaendig.
    return Array.from(table.querySelectorAll(':scope > tbody > tr')).map((tr, rowIdx) => {
        // ':scope > th, :scope > td' liefert in DOKUMENTREIHENFOLGE — der
        // Zeilenkopf <th> steht damit korrekt an Position 0, unabhaengig von
        // der Reihenfolge im Selektor.
        const cells = Array.from(tr.querySelectorAll(':scope > th, :scope > td'));
        const row = {};
        cells.forEach((cell, colIdx) => {
            row[`col${colIdx}`] = cell.innerHTML;
        });
        if (typeof columnCount === 'number' && columnCount > 0
                && cells.length !== columnCount) {
            console.warn(
                '[forensic] Tabelle ' + (table.id || '(ohne ID)') + ', Zeile '
                + (rowIdx + 1) + ': ' + cells.length + ' Zellen bei '
                + columnCount + ' Kopfspalten — Spaltenzuordnung pruefen.'
            );
        }
        return row;
    });
}

/**
 * Baut die Tabulator-Konfiguration fuer eine BLOB-Tabelle.
 *
 * Variante A (Beleg: Bauplan Userinfo-Verschoenerung Pkt.7, Entscheidung
 * 2026-07-10): Inhaltshoehe statt fixer 600px.
 *
 * Ursache des fehlenden Blaetter-Pagers (Console-Diagnose 2026-07-10):
 *   maxHeight:'600px' zusammen mit Tabulators Basis-CSS
 *   .tabulator { overflow:hidden } kappte alles jenseits 600px — inklusive des
 *   im Fluss DARUNTER liegenden Footers/Paginators (footer war im DOM,
 *   display:block/visibility:visible, aber bei top~3920px ausserhalb der
 *   600px-Kappung). Kein Sichtbarkeits-, sondern ein Kappungsproblem.
 *
 * Fix: KEIN maxHeight, height:false -> die Tabelle ist so hoch wie ihr Inhalt,
 * der Pager fliesst immer sichtbar darunter. Nebenwirkung geschlossen (GR1):
 * auch NICHT-paginierte Tabellen (<=50 Zeilen) hoeher als 600px zeigten zuvor
 * ihre unteren Zeilen gar nicht (kein Scroll, kein Pager) — jetzt vollstaendig.
 *
 * Bewusst als eigene Funktion: so ist die Konfiguration ohne die Tabulator-
 * Bibliothek und ohne DOM unit-testbar (Anti-"gruen aber tot", B4-S12).
 *
 * @param {Array} rows    - Zeilendaten
 * @param {Array} columns - Spaltendefinitionen
 * @returns {object} Tabulator-Optionsobjekt
 */
function buildTabulatorConfig(rows, columns) {
    return {
        data:           rows,
        columns:        columns,
        layout:         'fitDataStretch',
        // Variante A: Inhaltshoehe. KEIN maxHeight (das kappte den Pager).
        height:         false,
        pagination:     rows.length > 50 ? 'local' : false,
        paginationSize: 50,
        locale:         'de-de',
        langs: {
            'de-de': {
                pagination: {
                    first:     'Erste',
                    first_title: 'Erste Seite',
                    last:      'Letzte',
                    last_title: 'Letzte Seite',
                    prev:      'Zurück',
                    prev_title: 'Vorherige Seite',
                    next:      'Weiter',
                    next_title: 'Nächste Seite',
                    all:       'Alle',
                    page_size: 'Zeilen pro Seite',
                    page_counter: '{count} von {total}',
                },
                headerFilters: {
                    default: 'Filtern…',
                },
            },
        },
    };
}

// ===========================================================================
// FENSTER 2 — Einfahren-Schaltflächen (Einklappen von unten)
// ===========================================================================

/**
 * Hängt an jedes geöffnete <details class="forensic-section"> einen Button
 * ans Ende von .forensic-section-body, mit dem der Abschnitt von unten
 * eingeklappt werden kann.
 *
 * Die CSS-Sichtbarkeit wird über details[open] .forensic-collapse-btn
 * gesteuert — der Button erscheint nur, wenn der Abschnitt geöffnet ist.
 *
 * Beleg: Projektgespräch 2026-05-04 — Einfahren-Schaltfläche (Build 013)
 *
 * @param {HTMLElement} container — Wurzelelement (#userinfo-static)
 */
/**
 * Linker-Rand-Klick: Klappt details[open].forensic-section ein wenn
 * der Klick innerhalb der linken 5px-Zone erfolgt.
 *
 * Hintergrund: CSS ::before-Pseudo-Elemente sind nicht direkt über
 * addEventListener ansprechbar. Stattdessen wird ein click-Handler auf
 * dem details-Element selbst registriert. event.offsetX gibt die
 * X-Position relativ zur Kante des Elements an — liegt sie <= 5px,
 * war der Klick auf dem ::before-Streifen.
 * Beleg: Projektgespräch 2026-05-05 (Build 085).
 *
 * @param {HTMLElement} details — das details.forensic-section-Element
 */
function _initLeftBorderCollapse(details) {
    details.addEventListener('click', (evt) => {
        // Nur wenn Abschnitt offen ist — sonst kein Rand sichtbar
        if (!details.open) return;

        // offsetX: X-Position relativ zur linken Kante von details.
        // Klick auf summary öffnet/schließt nativ — den überlassen wir
        // dem Browser. Wir greifen nur ein wenn offsetX <= 5 UND
        // der Klick NICHT auf dem summary-Element liegt.
        const onSummary = evt.target.closest('summary');
        if (onSummary) return;

        // Build 087: Tabulator-Elemente vom Collapse-Handler ausschließen.
        // Verhindert versehentliches Einklappen beim Klick auf Spaltenköpfe.
        // Beleg: TODO-002, Projektgespräch 2026-05-05.
        const onTabulator = evt.target.closest('.tabulator');
        if (onTabulator) return;

        if (evt.offsetX <= 5) {
            evt.preventDefault();
            evt.stopPropagation();
            details.open = false;
        }
    });
}

function initCollapseButtons(container) {
    container.querySelectorAll('details.forensic-section').forEach(details => {
        const body = details.querySelector('.forensic-section-body');
        if (!body) return;

        // Einfahren-Schaltfläche am unteren Ende des Abschnitts
        const btn = document.createElement('button');
        btn.className  = 'forensic-collapse-btn';
        btn.textContent = '▲ Einklappen';
        btn.setAttribute('type', 'button');
        btn.setAttribute('title', 'Abschnitt einklappen');
        btn.addEventListener('click', () => { details.open = false; });
        body.appendChild(btn);

        // Build 085: Linker 5px-Rand als zusätzliche Einklapp-Fläche
        _initLeftBorderCollapse(details);
    });
}

// ===========================================================================
// FENSTER 2 — Vollständiger Zeitstrahl §7.11
// ===========================================================================

/**
 * Initialisiert den interaktiven Zeitstrahl im #forensic-timeline-ui.
 *
 * Liest Ereignis-JSON aus <script id="forensic-timeline-data">,
 * rendert die Zeitleiste und verbindet Filter-Dropdown + Buttons.
 * Jahreszahl-Trennlinien werden automatisch eingefügt.
 * navigate_to_url via postMessage für verlinkbare Ereignisse.
 *
 * Beleg: Projektgespräch 2026-04-18 — §7.11 Zeitstrahl Cellebrite-Stil.
 *
 * @param {HTMLElement} container — Wurzelelement (#userinfo-static)
 */
function initTimeline(container) {
    if (!container) return;

    const dataEl = container.querySelector('#forensic-timeline-data');
    const ui     = container.querySelector('#forensic-timeline-ui');
    if (!dataEl || !ui) return;

    let payload;
    try {
        payload = JSON.parse(dataEl.textContent);
    } catch (e) {
        console.warn('[Forensic] Zeitstrahl: JSON-Parse fehlgeschlagen', e);
        return;
    }

    const events    = payload.events  || [];
    const typesMeta = payload.types   || [];
    if (events.length === 0) return;

    const tlContainer = ui.querySelector('#tl-container');
    const filterSel   = ui.querySelector('#tl-filter');
    const btnAll      = ui.querySelector('#tl-filter-all');
    const btnNone     = ui.querySelector('#tl-filter-none');
    const countEl     = ui.querySelector('#tl-count');

    // ---------------------------------------------------------------
    // Filter-Dropdown aufbauen
    // ---------------------------------------------------------------
    typesMeta.forEach(tm => {
        const opt = document.createElement('option');
        opt.value    = tm.type;
        opt.selected = true;
        opt.textContent = `${tm.icon} ${tm.label} (${tm.count})`;
        filterSel.appendChild(opt);
    });

    // ---------------------------------------------------------------
    // Ereignis-Nodes rendern
    // ---------------------------------------------------------------
    function formatDatetime(ts) {
        const d = new Date(ts * 1000);
        const date = d.toISOString().slice(0, 10);
        const time = d.toISOString().slice(11, 19) + ' UTC';
        return { date, time, year: d.getUTCFullYear() };
    }

    function buildEventEl(evt) {
        const { date, time } = formatDatetime(evt.ts);
        const el = document.createElement('div');
        el.className = `tl-event ${evt.css}`;
        el.dataset.type = evt.type;

        let linkHtml = '';
        if (evt.url) {
            linkHtml = `<span class="tl-link" data-forensic-url="${_escAttr(evt.url)}">↗</span>`;
        }

        el.innerHTML = `
            <div class="tl-datetime">
                <span class="tl-date">${date}</span>
                <span class="tl-time">${time}</span>
            </div>
            <div class="tl-connector"></div>
            <div class="tl-node" title="${_escAttr(evt.label)}">${evt.icon}</div>
            <div class="tl-body">
                <div class="tl-type-label">${_escHtml(evt.label)}</div>
                <div class="tl-detail">${_escHtml(evt.detail)}${linkHtml}</div>
            </div>`;
        return el;
    }

    function _escHtml(s) {
        return String(s || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
    function _escAttr(s) { return _escHtml(s); }

    // Alle Ereignis-Elemente vorab erzeugen (für schnelles Ein-/Ausblenden)
    let lastYear = null;
    const eventEls = [];

    events.forEach(evt => {
        const { year } = formatDatetime(evt.ts);

        // Jahres-Trennlinie
        if (year !== lastYear) {
            const marker = document.createElement('div');
            marker.className = 'tl-year-marker';
            marker.textContent = String(year);
            marker.dataset.year = String(year);
            tlContainer.appendChild(marker);
            lastYear = year;
        }

        const el = buildEventEl(evt);
        tlContainer.appendChild(el);
        eventEls.push(el);
    });

    // ---------------------------------------------------------------
    // Filterlogik
    // ---------------------------------------------------------------
    function getSelectedTypes() {
        return Array.from(filterSel.selectedOptions).map(o => o.value);
    }

    function applyFilter() {
        const selected = new Set(getSelectedTypes());
        let visible = 0;

        eventEls.forEach(el => {
            const show = selected.has(el.dataset.type);
            el.classList.toggle('tl-hidden', !show);
            if (show) visible++;
        });

        // Jahres-Trennlinien ausblenden wenn kein sichtbares Ereignis im Jahr
        tlContainer.querySelectorAll('.tl-year-marker').forEach(marker => {
            const yr = marker.dataset.year;
            // Suche nächstes sichtbares tl-event mit passendem Jahr
            let next = marker.nextElementSibling;
            let hasVisible = false;
            while (next && !next.classList.contains('tl-year-marker')) {
                if (next.classList.contains('tl-event') && !next.classList.contains('tl-hidden')) {
                    hasVisible = true;
                    break;
                }
                next = next.nextElementSibling;
            }
            marker.classList.toggle('tl-hidden', !hasVisible);
        });

        countEl.textContent = `${visible} von ${events.length} Ereignissen`;
    }

    filterSel.addEventListener('change', applyFilter);

    btnAll.addEventListener('click', () => {
        Array.from(filterSel.options).forEach(o => { o.selected = true; });
        applyFilter();
    });

    btnNone.addEventListener('click', () => {
        Array.from(filterSel.options).forEach(o => { o.selected = false; });
        applyFilter();
    });

    // ---------------------------------------------------------------
    // navigate_to_url für Zeitleisten-Links
    // ---------------------------------------------------------------
    tlContainer.addEventListener('click', evt => {
        const link = evt.target.closest('[data-forensic-url]');
        if (!link) return;
        evt.preventDefault();
        const url = link.dataset.forensicUrl;
        if (!url) return;
        const target = window.opener || window.parent;
        if (target && target !== window) {
            target.postMessage({ type: 'navigate_to_url', url }, window.location.origin);
        }
    });

    // Initialzähler setzen
    applyFilter();
}

// ===========================================================================
// FENSTER 2 — Grafische Heatmap
// ===========================================================================

/**
 * Färbt die Heatmap-Zellen im gegebenen Container anhand von data-intensity.
 *
 * Der BLOB enthält data-intensity="0..100" pro Zelle (berechnet vom
 * phase_b_html_renderer.py). initHeatmap() setzt data-level="0..7"
 * und einen Tooltip mit dem exakten Wert aus dem title-Attribut.
 *
 * Farbskala: weiß → tiefblau (7 Stufen + 0 = leer).
 * Beleg: Projektgespräch 2026-04-18.
 *
 * @param {HTMLElement} container — Wurzelelement des BLOBs (#userinfo-static)
 */
function initHeatmap(container) {
    if (!container) return;

    const cells = container.querySelectorAll('.forensic-hm-cell');
    if (cells.length === 0) return;

    // Maximalen intensity-Wert bestimmen (für relative Skalierung)
    let maxIntensity = 0;
    cells.forEach(cell => {
        const v = parseInt(cell.dataset.intensity || '0', 10);
        if (v > maxIntensity) maxIntensity = v;
    });

    if (maxIntensity === 0) return;   // Keine Aktivität — nichts zu färben

    cells.forEach(cell => {
        const intensity = parseInt(cell.dataset.intensity || '0', 10);

        // Stufe 0..7: 0 = leer, 1..7 = aufsteigende Intensität
        let level;
        if (intensity === 0) {
            level = 0;
        } else {
            // Gleichmäßige Verteilung auf Stufen 1–7
            level = Math.max(1, Math.min(7, Math.ceil((intensity / maxIntensity) * 7)));
        }

        cell.dataset.level = String(level);

        // Tooltip: exakten Wert aus title-Attribut (vom Renderer gesetzt) behalten
        // Stufe und Farb-Feedback in aria-label für Barrierefreiheit
        const title = cell.getAttribute('title') || '';
        cell.setAttribute('aria-label', title);
    });
}

// ===========================================================================
// FENSTER 2 — Forensische Links (navigate_to_url)
// ===========================================================================

/**
 * Fängt Klicks auf [data-forensic-url]-Elemente im #userinfo-static-Bereich ab
 * und sendet eine navigate_to_url-Nachricht an das Hauptfenster (opener/parent).
 *
 * Hintergrund: Der BLOB läuft in einem eingebetteten Kontext (iframe-ähnlich
 * oder separates Fenster). <a href target="_parent"> funktioniert nicht
 * zuverlässig für AJAX-Navigation im Hauptfenster. Stattdessen wird
 * postMessage verwendet, das NavigationModule.loadPage() im Hauptfenster aufruft.
 * Beleg: Projektgespräch 2026-04-18.
 *
 * Elemente mit data-forensic-url werden vom phase_b_html_renderer.py erzeugt,
 * z.B. in _render_aliases für source_url-Links.
 */
function initForensicLinks() {
    const container = document.getElementById('userinfo-static');
    if (!container) return;

    container.addEventListener('click', function (evt) {
        const link = evt.target.closest('[data-forensic-url]');
        if (!link) return;
        evt.preventDefault();
        evt.stopPropagation();

        const url = link.dataset.forensicUrl;
        if (!url) return;

        const target = window.opener || window.parent;
        if (target && target !== window) {
            target.postMessage(
                { type: 'navigate_to_url', url: url },
                window.location.origin
            );
        } else {
            // Fallback: direkte Navigation wenn kein opener/parent (z.B. standalone)
            window.location.href = url;
        }
    });
}

// Build 173: Fenster 2 (userinfo) beim Server registrieren.
// Heartbeat alle 30s damit TTL nicht abläuft.
// Beleg: Projektgespraech 2026-05-11
(function() {
    var _windowId = crypto.randomUUID ? crypto.randomUUID()
                  : Math.random().toString(36).slice(2);
    function _registerWindow() {
        fetch('/_forensic/windows', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Forensic-Request': 'ajax' },
            body: JSON.stringify({ window_id: _windowId, role: 'userinfo' }),
        }).catch(function() {});
    }
    _registerWindow();
    setInterval(_registerWindow, 30000);
    window.addEventListener('unload', function() {
        navigator.sendBeacon('/_forensic/windows',
            new Blob([JSON.stringify({ window_id: _windowId })],
                     { type: 'application/json' }));
    });

    // Bug 2.120 Fix Build 218: releaseLock und acquireLock ueber window exportieren
    // damit report_editor.js beim Bericht-Wechsel Lock korrekt uebergeben kann.
    // releaseLockAsync: awaitable Version fuer sequenziellen Ablauf
    // (Save → Release → neuen Bericht laden → Acquire).
    // Beleg: Bugfix Build 218, Projektgespraech 2026-05-17
    // Paket 9: _acquireLock/_releaseLockAsync delegieren an Layer.
/**
 * Lock-Status-Anzeige in der Action-Bar aktualisieren.
 * Setzt CSS-Klasse und Text auf #report-lock-indicator und #report-lock-status.
 * Wird von editor_bootstrap.js über window._updateLockStatus aufgerufen.
 * Beleg: Build 260, Bugfix fehlende Funktion
 * @param {string} cssClass  — z.B. 'lock-mine', 'lock-other', 'lock-free', 'lock-frozen'
 * @param {string} label     — Anzeigetext
 */
function updateLockStatus(cssClass, label) {
    const indicator = document.getElementById('report-lock-indicator');
    const statusEl  = document.getElementById('report-lock-status');
    const allClasses = ['lock-mine', 'lock-other', 'lock-free', 'lock-frozen', 'lock-none'];
    if (indicator) {
        indicator.classList.remove(...allClasses);
        indicator.classList.add(cssClass);
        indicator.title = label || '';
    }
    if (statusEl) {
        statusEl.classList.remove(...allClasses);
        statusEl.classList.add(cssClass);
        statusEl.textContent = label || '';
    }
}

    window._acquireLock = acquireLock;
    window._updateLockStatus = updateLockStatus;
    window._releaseLockAsync = function() {
        if (window.lockLayer) return window.lockLayer.release();
        return Promise.resolve();
    };

    // Bug 2.23 Fix Build 277: Manueller Lock-Toggle per Klick auf den
    // Lock-Indikator (#report-lock-indicator).
    //
    // Kein Lock gehalten → acquire() ausloesen.
    // Lock gehalten      → release() ausloesen.
    //
    // Das ist eine Notfall-Massnahme fuer den Fall dass der automatische
    // Acquire (z.B. nach Server-Neustart ohne SSE) fehlschlaegt.
    // Der Indikator ist als klickbar erkennbar durch cursor:pointer (CSS).
    // Beleg: Bugfix-Liste 2.23, Projektgespraech 2026-06-07
    (function _initLockIndicatorClickHandler() {
        const indicator = document.getElementById('report-lock-indicator');
        if (!indicator) return;

        // cursor:pointer signalisiert Klickbarkeit
        indicator.style.cursor = 'pointer';

        indicator.addEventListener('click', async function _onLockIndicatorClick(evt) {
            window._uevt?.(evt, 'userinfo', 'click:report-lock-indicator',
                { hasLock: !!window.lockLayer?.lockId }); // B200

            if (!window.lockLayer) {
                console.warn('[userinfo] lockLayer nicht verfuegbar — Klick ignoriert');
                return;
            }

            if (window.lockLayer.lockId) {
                // Lock gehalten → freigeben
                console.debug('[userinfo] Lock-Indikator: Lock freigeben (manuell)');
                window.lockLayer.release();
            } else {
                // Kein Lock → erwerben
                console.debug('[userinfo] Lock-Indikator: Lock erwerben (manuell)');
                // Sicherstellen dass sseLayer.ready abgewartet wurde
                const sseLayer = window.sseLayer;
                if (sseLayer?.ready) {
                    await sseLayer.ready;
                }
                window.lockLayer.acquire();
            }
        });
    })();

})();
})();
