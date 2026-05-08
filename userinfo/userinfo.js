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
 * Version: v0.6.116 · Build: 116 · 2026-05-07
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

    } catch (err) {
        container.innerHTML =
            `<div class="status-msg status-msg-warn">` +
            `Forensische Nutzerdaten konnten nicht geladen werden: ${esc(String(err))}` +
            `</div>`;
    }
}

/**
 * Dynamische Blöcke laden und in #userinfo-dynamic einsetzen.
 */
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
    if (investigation_status) {
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
    const evtSrc = new EventSource(FORENSIC_API.EVENTS);

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

    // SSE-Verbindung aufbauen — Client-ID empfangen
    await initSSEWindow3();

    // Lock-Buttons verdrahten / ausblenden je nach DEV_LOCK_UI
    // Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
    if (!DEV_LOCK_UI) {
        // PROD: Buttons ausblenden, Lock automatisch erwerben
        document.getElementById('btn-acquire-lock')?.remove();
        document.getElementById('btn-release-lock')?.remove();
        // Greedy client: Lock sofort nach SSE-Aufbau anfordern.
        // sseClientId ist durch await initSSEWindow3() garantiert gesetzt.
        // Beleg: Build 098, Projektgespraech 2026-05-06
        acquireLock();
    } else {
        document.getElementById('btn-acquire-lock')?.addEventListener('click', acquireLock);
        document.getElementById('btn-release-lock')?.addEventListener('click', releaseLock);
    }
    document.getElementById('btn-annotations-sidebar')?.addEventListener('click', () => {
        if (window.toggleAnnotationSidebar) toggleAnnotationSidebar();
    });
    document.getElementById('btn-request-takeover')?.addEventListener('click', requestTakeover);

    // Lock bei Seitenentladung freigeben (§8.6 Bauplan B4 — beforeunload)
    // Vor dem Lock-Freigeben noch den aktuellen Editor-Zustand speichern.
    // Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
    window.addEventListener('beforeunload', () => {
        if (EditorState.lockId) {
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
 * SSE-Stream für Fenster 3 aufbauen.
 * Empfängt client_id und Editor-Lock-Events.
 */
async function initSSEWindow3() {
    _dbg('initSSEWindow3() gestartet');
    return new Promise(resolve => {
        // V1: resume_lock_id mitsenden falls Lock gehalten wird.
        // Der Server bindet den Lock an die neue SSE-client_id.
        // Beleg: Lock-System v2 V1, Projektgespraech 2026-04-21
        const resumeParam = EditorState.lockId
            ? `?resume_lock_id=${encodeURIComponent(EditorState.lockId)}`
            : '';
        const evtSrc = new EventSource(FORENSIC_API.EVENTS + resumeParam);
        let resolved = false;

        // SSE-Stream auf window exportieren fuer editor.js
        window._forensicEvtSrc = evtSrc;

        // Verbindungsabbruch — Benutzer informieren
        evtSrc.onerror = () => {
            if (evtSrc.readyState === EventSource.CLOSED) {
                showStatusMsg('SSE-Verbindung getrennt — wird wiederhergestellt…', 'warn');
            }
        };

        evtSrc.addEventListener('client_id', async evt => {
            try {
                const { client_id } = JSON.parse(evt.data);
                const isReconnect = !!EditorState.sseClientId;  // schon gesetzt?
                EditorState.sseClientId = client_id;

                if (isReconnect && EditorState.lockId) {
                    // SSE-Reconnect waehrend Lock gehalten wird.
                    // Lock-Bindung in DB auf neue SSE-client_id aktualisieren.
                    // Beleg: Lock-System v2 V1, Projektgespraech 2026-04-21
                    try {
                        const resp = await fetch(FORENSIC_API.REPORT, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                action: 'resume_lock',
                                lock_id: EditorState.lockId,
                                sse_client_id: client_id,
                            }),
                        });
                        const data = await resp.json();
                        if (data.ok) {
                            showStatusMsg('Verbindung wiederhergestellt.', 'ok');
                            console.debug('SSE-Reconnect: Lock erneuert', EditorState.lockId);
                        } else {
                            // Lock abgelaufen — aufräumen
                            EditorState.lockId = null;
                            sessionStorage.removeItem('forensic_lock_id');
                            updateLockStatus('lock-none', 'Kein Lock');
                            // Buttons optional (DEV_LOCK_UI)
                            document.getElementById('btn-acquire-lock')?.disable && (document.getElementById('btn-acquire-lock').disabled = false);
                            document.getElementById('btn-release-lock')?.disable && (document.getElementById('btn-release-lock').disabled = true);
                            if (window._editor && !window._editor.readOnly.isEnabled) {
                                window._editor.readOnly.toggle().catch(() => {});
                            }
                            // Greedy client: sofort neu versuchen
                            showStatusMsg('Lock abgelaufen — wird neu angefordert…', 'info');
                            setTimeout(acquireLock, 500);
                        }
                    } catch (err) {
                        console.warn('SSE-Reconnect: resume_lock fehlgeschlagen:', err);
                    }
                } else if (isReconnect) {
                    showStatusMsg('Verbindung wiederhergestellt.', 'ok');
                }
            } catch (_) {}
            if (!resolved) { resolved = true; resolve(); }
        });

        evtSrc.addEventListener('editor_lock_acquired', async evt => {
            try {
                const { locked_by, lock_id } = JSON.parse(evt.data);
                const ownName = document.getElementById('report-editor-body')?.dataset?.username || '';
                if (locked_by === ownName) {
                    // Lock gehoert uns — in EditorState eintragen.
                    // Noetig wenn Lock aus vorheriger Session stammt und
                    // beim SSE-Aufbau zurueckgemeldet wird.
                    // Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
                    if (!EditorState.lockId && lock_id) {
                        EditorState.lockId = lock_id;
                        sessionStorage.setItem('forensic_lock_id', lock_id);
                    }
                    updateLockStatus('lock-mine', 'Lock: ich');
                    const btnAcquire = document.getElementById('btn-acquire-lock');
                    const btnRelease = document.getElementById('btn-release-lock');
                    if (btnAcquire) btnAcquire.disabled = true;
                    if (btnRelease) btnRelease.disabled = false;
                    // Editor aus readOnly befreien — nur wenn:
                    // a) Editor noch readOnly ist, UND
                    // b) acquireLock() _reinitWithLock noch nicht aufgerufen hat.
                    //    Erkennbar daran ob _reinitWithLock gerade laeuft
                    //    (lock_id kam via SSE, nicht via direktem acquire).
                    // Hauptfall: Lock aus vorheriger Session (Seitenstart).
                    // Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-20
                    if (window._editor?.readOnly?.isEnabled && window._reinitWithLock
                            && !window._reinitInProgress) {
                        await window._reinitWithLock();
                    }
                } else {
                    updateLockStatus('lock-other', `Lock belegt: ${esc(locked_by)}`);
                    disableEditorControls(true);
                }
            } catch (_) {}
        });

        evtSrc.addEventListener('editor_lock_released', () => {
            // SSE-Event: Lock wurde freigegeben (Verbindungsabriss oder explizit).
            // Beleg: Build 098 Fix — greedy client, automatisches Re-Acquire
            const hadLock = !!EditorState.lockId;  // VOR dem Nullsetzen merken
            EditorState.lockId = null;
            sessionStorage.removeItem('forensic_lock_id');
            updateLockStatus('lock-none', 'Kein Lock');
            // Buttons (DEV_LOCK_UI-Modus)
            const btnAcquire = document.getElementById('btn-acquire-lock');
            const btnRelease = document.getElementById('btn-release-lock');
            if (btnAcquire) btnAcquire.disabled = false;
            if (btnRelease) btnRelease.disabled = true;
            // Editor in readOnly-Modus versetzen (nur wenn noch schreibbar)
            if (window._editor && !window._editor.readOnly.isEnabled) {
                window._editor.readOnly.toggle().catch(() => {});
            }
            // Greedy client: Lock immer sofort neu anfordern.
            // Kurze Verzoegerung damit der Server den Release vollstaendig
            // verarbeitet hat bevor der naechste Acquire ankommt.
            // Beleg: Build 098, Projektgespraech 2026-05-06
            if (hadLock) {
                showStatusMsg('Verbindung unterbrochen — Lock wird neu angefordert…', 'info');
            }
            // Nur im PROD-Modus (DEV_LOCK_UI=false) automatisch neu erwerben.
            // Im DEV-Modus erwirbt der Ermittler den Lock manuell per Button.
            // Automatisches Re-Acquire im DEV-Modus würde einen Retry-Sturm
            // auslösen wenn der Server nicht antworten kann.
            // Beleg: Bugfix Build 089, Projektgespräch 2026-05-07.
            if (!DEV_LOCK_UI) {
                setTimeout(acquireLock, 500);
            }
        });

        evtSrc.addEventListener('report_updated', () => {
            reloadParagraphs();
        });

        // V3: Takeover-Anfrage empfangen (bei Ermittler A = Lock-Inhaber)
        // Beleg: Lock-System v2 V3, Projektgespraech 2026-04-21
        evtSrc.addEventListener('lock_takeover_request', evt => {
            try {
                const { request_id, requested_by, countdown } = JSON.parse(evt.data);
                if (!EditorState.lockId) return;  // Nur wenn wir den Lock haben
                _showTakeoverDialog(request_id, requested_by, countdown ?? 60);
            } catch (_) {}
        });

        // V3: Takeover-Ergebnis empfangen (bei Ermittler B = Anfragender)
        evtSrc.addEventListener('lock_takeover_result', evt => {
            try {
                const { status, requested_by } = JSON.parse(evt.data);
                _handleTakeoverResult(status, requested_by);
            } catch (_) {}
        });

        // Timeout: nach 10s auch ohne client_id fortfahren.
        // 3s war zu knapp — beim Seitenstart bauen mehrere SSE-Verbindungen
        // gleichzeitig auf, der Server kann in dieser Phase langsamer antworten.
        // Im Normalfall kommt client_id in <100ms; 10s ist ein Sicherheitspuffer.
        // Beleg: Bugfix Build 089, Projektgespräch 2026-05-07.
        setTimeout(() => {
            if (!resolved) {
                console.warn(
                    '[userinfo.js] initSSEWindow3: client_id nicht innerhalb von 10s ' +
                    'empfangen — fortfahren ohne SSE-Client-ID. ' +
                    'acquireLock() wird blockiert bis SSE-Verbindung steht.'
                );
                resolved = true;
                resolve();
            }
        }, 10000);
    });
}

/**
 * Lock-Status-Anzeige aktualisieren.
 */
function updateLockStatus(cssClass, text) {
    const el = document.getElementById('report-lock-status');
    if (!el) return;
    el.className = `lock-status ${cssClass}`;
    el.textContent = text;
    // Bug 2.6 Fix Build 125: Lock-Indikator-Tooltip informativ gestalten.
    // Beleg: Bugfix Build 125, Projektgespraech 2026-05-08
    const lockIndicator = document.getElementById('report-lock-indicator');
    if (lockIndicator) {
        const titleMap = {
            'lock-none':    'Kein Lock — Editor nur lesend',
            'lock-mine':    'Lock gehalten — Bearbeitung möglich',
            'lock-self':    'Lock gehalten — Bearbeitung möglich',
            'lock-other':   `Lock belegt von: ${text.replace(/^Belegt:\s*/,'').replace(/^Lock belegt:\s*/,'')} — Bearbeitung gesperrt`,
            'lock-frozen':  'Lock eingefroren — anderes Fenster aktiv',
        };
        lockIndicator.title = titleMap[cssClass] || text;
        lockIndicator.textContent = cssClass === 'lock-none' ? '🔓'
            : cssClass === 'lock-mine' || cssClass === 'lock-self' ? '🔒'
            : cssClass === 'lock-other' ? '🔐'
            : '🔒';
    }
    // V3: 'Lock anfordern'-Button nur bei fremdem Lock anzeigen
    const btnTakeover = document.getElementById('btn-request-takeover');
    if (btnTakeover) {
        btnTakeover.style.display = cssClass === 'lock-other' ? '' : 'none';
    }
}

/**
 * Editor-Schaltflächen aktivieren / deaktivieren.
 */
function disableEditorControls(disable) {
    ['btn-save-paragraph', 'btn-acquire-lock'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.disabled = disable;
    });
    document.getElementById('btn-release-lock')?.setAttribute('disabled',
        disable ? '' : null);
}

/**
 * Lock erwerben (§8.5 Bauplan B4 — acquire_lock).
 */
async function acquireLock() {
    _dbg('acquireLock() aufgerufen, sseClientId=', EditorState.sseClientId);
    // Build 115: Guard — Lock bereits aus Resume-Session vorhanden → kein neuer Erwerb
    // Beleg: Projektgespraech 2026-05-07
    if (EditorState.lockId) {
        _dbg('acquireLock: Lock bereits vorhanden (', EditorState.lockId, ') — uebersprungen');
        return;
    }
    if (EditorState.frozen) return;
    if (!EditorState.sseClientId) {
        showStatusMsg('SSE-Verbindung nicht bereit — bitte Seite neu laden.', 'warn');
        return;
    }

    // Re-Entry-Guard: verhindert parallele Aufrufe durch mehrere Auslöser
    // (editor_lock_released-Event, client_id-Reconnect, DEV_LOCK_UI=false).
    // Beleg: Bugfix Build 089, Projektgespräch 2026-05-07.
    if (acquireLock._running) return;
    acquireLock._running = true;
    try {
        const resp = await fetch(FORENSIC_API.REPORT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action:     'acquire_lock',
                sse_client: EditorState.sseClientId,
            }),
        });
        const data = await resp.json();

        if (resp.ok && data.lock_id) {
            EditorState.lockId = data.lock_id;
            sessionStorage.setItem('forensic_lock_id', data.lock_id);
            updateLockStatus('lock-mine', 'Lock: ich');
            document.getElementById('btn-acquire-lock').disabled = true;
            document.getElementById('btn-release-lock').disabled = false;
            showStatusMsg('Lock erworben — Editor wird aktiviert…', 'ok');
            // Direkt reinitieren — nicht auf SSE warten (SSE-Interval = 15s).
            // SSE editor_lock_acquired bleibt als Backup fuer externe Events.
            // Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-20
            if (window._reinitWithLock) {
                await window._reinitWithLock();
                showStatusMsg('Editor aktiv.', 'ok');
            }
        } else if (resp.status === 423) {
            updateLockStatus('lock-other', `Belegt: ${esc(data.locked_by || '?')}`);
            showStatusMsg(`Lock bereits belegt von: ${esc(data.locked_by || '?')}`, 'warn');
        } else {
            showStatusMsg(`Fehler: ${esc(data.error || resp.status)}`, 'error');
        }
    } catch (err) {
        showStatusMsg(`Netzwerkfehler: ${esc(String(err))}`, 'error');
    } finally {
        // Guard zurücksetzen — nächster Aufruf ist wieder erlaubt.
        // Beleg: Bugfix Build 089, Projektgespräch 2026-05-07.
        acquireLock._running = false;
    }
}
// Initialer Zustand des Guards.
// Beleg: Bugfix Build 089, Projektgespräch 2026-05-07.
acquireLock._running = false;

/**
 * Lock freigeben (§8.5 Bauplan B4 — release_lock).
 * @param {boolean} sync - true = synchron via sendBeacon (beforeunload)
 */
// ==========================================================================
// V3: Lock-Übernahme-Dialog
// Beleg: Lock-System v2 V3, Projektgespraech 2026-04-21
// ==========================================================================

let _takeoverCountdownTimer = null;

/**
 * Dialog bei Ermittler A anzeigen: jemand möchte den Lock übernehmen.
 * @param {number} requestId
 * @param {string} requestedBy  Benutzername des Anfragenden
 * @param {number} countdown    Sekunden bis zur automatischen Übergabe
 */
function _showTakeoverDialog(requestId, requestedBy, countdown) {
    // Bestehenden Dialog entfernen
    document.getElementById('takeover-dialog')?.remove();
    if (_takeoverCountdownTimer) clearInterval(_takeoverCountdownTimer);

    let remaining = countdown;
    const dialog = document.createElement('div');
    dialog.id = 'takeover-dialog';
    dialog.className = 'takeover-dialog';
    dialog.innerHTML = `
        <div class="takeover-dialog-inner">
            <div class="takeover-icon">🔔</div>
            <div class="takeover-text">
                <strong>${esc(requestedBy)}</strong> möchte den Lock übernehmen.<br>
                Übergabe in <span id="takeover-countdown">${remaining}</span>s.
            </div>
            <div class="takeover-actions">
                <button class="editor-btn editor-btn-primary" id="btn-takeover-grant">Jetzt übergeben</button>
                <button class="editor-btn" id="btn-takeover-deny">Ablehnen</button>
            </div>
        </div>`;

    document.getElementById('report-editor-body')?.appendChild(dialog);

    // Countdown
    _takeoverCountdownTimer = setInterval(() => {
        remaining--;
        const el = document.getElementById('takeover-countdown');
        if (el) el.textContent = remaining;
        if (remaining <= 0) {
            clearInterval(_takeoverCountdownTimer);
            dialog.remove();
            // Automatische Übergabe: Lock freigeben
            _respondTakeover(requestId, 'grant');
        }
    }, 1000);

    document.getElementById('btn-takeover-grant')?.addEventListener('click', () => {
        clearInterval(_takeoverCountdownTimer);
        dialog.remove();
        _respondTakeover(requestId, 'grant');
    });

    document.getElementById('btn-takeover-deny')?.addEventListener('click', () => {
        clearInterval(_takeoverCountdownTimer);
        dialog.remove();
        _respondTakeover(requestId, 'deny');
    });
}

/**
 * Auf Takeover-Anfrage antworten.
 * @param {number} requestId
 * @param {'grant'|'deny'} response
 */
async function _respondTakeover(requestId, response) {
    try {
        const lockId = EditorState.lockId;
        if (!lockId) return;
        await fetch(FORENSIC_API.REPORT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'respond_takeover',
                request_id: requestId,
                response,
                lock_id: lockId,
            }),
        });
        if (response === 'grant') {
            // Lock wurde übergeben — releaseLock() aufräumen
            releaseLock();
        }
    } catch (err) {
        console.warn('_respondTakeover Fehler:', err);
    }
}

/**
 * Takeover-Ergebnis bei Ermittler B verarbeiten.
 * @param {'granted'|'denied'|'expired'} status
 * @param {string} requestedBy  eigener Username (zur Verifikation)
 */
function _handleTakeoverResult(status, requestedBy) {
    document.getElementById('takeover-waiting-msg')?.remove();
    if (status === 'granted' || status === 'expired') {
        showStatusMsg('Lock freigegeben — jetzt erwerben.', 'ok');
        // btn-acquire-lock aktivieren
        document.getElementById('btn-acquire-lock').disabled = false;
    } else {
        showStatusMsg('Anfrage abgelehnt.', 'warn');
    }
}

/**
 * Lock-Übernahme anfragen (bei Ermittler B = kein Lock).
 */
async function requestTakeover() {
    const lock = await fetch(FORENSIC_API.REPORT + '?format=json', {
        headers: { 'X-Forensic-Request': 'ajax' }
    }).then(r => r.json()).then(d => d.lock).catch(() => null);

    if (!lock) {
        showStatusMsg('Kein Lock vorhanden — direkt erwerben.', 'ok');
        return;
    }

    try {
        const resp = await fetch(FORENSIC_API.REPORT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'request_takeover' }),
        });
        const data = await resp.json();
        if (data.queued) {
            showStatusMsg(
                `Anfrage gesendet — Lock-Inhaber hat ${data.countdown}s Zeit zu antworten.`,
                'ok'
            );
            // Warte-Hinweis
            const msg = document.createElement('div');
            msg.id = 'takeover-waiting-msg';
            msg.className = 'status-msg status-msg-ok';
            msg.style.cssText = 'margin:8px 0;font-size:12px';
            msg.textContent = `Warte auf Antwort von ${esc(lock.locked_by)}…`;
            document.getElementById('report-status-msg')?.appendChild(msg);
        } else {
            showStatusMsg(data.error || 'Anfrage fehlgeschlagen.', 'error');
        }
    } catch (err) {
        showStatusMsg('Netzwerkfehler bei Takeover-Anfrage.', 'error');
    }
}

function releaseLock(sync = false) {
    const lockId = EditorState.lockId || sessionStorage.getItem('forensic_lock_id');
    if (!lockId) return;

    const body = JSON.stringify({ action: 'release_lock', lock_id: lockId });

    if (sync) {
        // beforeunload: sendBeacon ist einzige zuverlässige synchrone Methode
        navigator.sendBeacon(FORENSIC_API.REPORT, new Blob([body], { type: 'application/json' }));
    } else {
        fetch(FORENSIC_API.REPORT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body,
        }).then(() => {
            EditorState.lockId = null;
            sessionStorage.removeItem('forensic_lock_id');
            updateLockStatus('lock-none', 'Kein Lock');
            document.getElementById('btn-acquire-lock').disabled = false;
            document.getElementById('btn-release-lock').disabled = true;
            showStatusMsg('Lock freigegeben.', 'ok');
            // Editor in readOnly versetzen (nur wenn noch schreibbar)
            if (window._editor && !window._editor.readOnly.isEnabled) {
                window._editor.readOnly.toggle().then(() => {
                    // Placeholder zuruecksetzen
                    if (window.updateEditorPlaceholder) updateEditorPlaceholder(false);
                }).catch(() => {});
            } else if (window.updateEditorPlaceholder) {
                updateEditorPlaceholder(false);
            }
        }).catch(err => {
            showStatusMsg(`Fehler beim Freigeben: ${esc(String(err))}`, 'error');
        });
    }

    EditorState.lockId = null;
    sessionStorage.removeItem('forensic_lock_id');
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
    if (!EditorState.lockId) {
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
                'X-Forensic-Lock-Id':  EditorState.lockId,
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

document.addEventListener('DOMContentLoaded', () => {
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
        initSSEWindow2();
        initForensicLinks();    // navigate_to_url via postMessage (Build 038)
    }
});


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

        // Datenzeilen aus <tbody> extrahieren
        const rows = Array.from(table.querySelectorAll('tbody tr')).map(tr => {
            const cells = Array.from(tr.querySelectorAll('td'));
            const row = {};
            cells.forEach((td, colIdx) => {
                row[`col${colIdx}`] = td.innerHTML;
            });
            return row;
        });

        // Wrapper-Div für Tabulator erstellen (ersetzt die Tabelle im DOM)
        const wrapper = document.createElement('div');
        wrapper.className = 'forensic-tabulator-wrapper';
        table.parentNode.insertBefore(wrapper, table);
        table.style.display = 'none';  // Original-Tabelle ausblenden (BLOB bleibt intakt)

        // Tabulator instanziieren
        // eslint-disable-next-line no-new
        new Tabulator(wrapper, {
            data:           rows,
            columns:        columns,
            layout:         'fitDataStretch',
            height:         'auto',
            maxHeight:      '600px',
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
        });
    });
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

})();
