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
 * Version: v0.1.0 · Build: 012 · 2026-04-14
 */

'use strict';

// ---------------------------------------------------------------------------
// Konstanten
// ---------------------------------------------------------------------------

const FORENSIC_API = {
    USERINFO_DATA:   '/_forensic/userinfo/data',
    USERINFO_STATIC: '/_forensic/userinfo/static',
    REPORT:          '/_forensic/report',
    EVENTS:          '/_forensic/events',
};

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
    const refreshBtn = `<button class="editor-btn" id="btn-refresh-report">Aktualisieren</button>`;

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

    // Read-Only-Berichtsreiter
    const roContainer = document.getElementById('userinfo-report-readonly');
    if (roContainer) {
        roContainer.innerHTML = `
            <h3>Bericht <span id="report-draft-badge"></span></h3>
            <div class="report-actions">${refreshBtn} ${editBtn}</div>
            <div id="report-readonly-content">
                <span class="loading-spinner"></span> Lade Berichtsinhalt…
            </div>`;
        loadReadonlyReport();
        document.getElementById('btn-refresh-report')?.addEventListener('click', loadReadonlyReport);
        document.getElementById('btn-open-report')?.addEventListener('click', () => {
            window.open('/_forensic/report', 'forensic_report');
        });
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

/** BroadcastChannel für Schicht 1 des Lock-Mechanismus (§8.6 Bauplan B4). */
let _broadcastChannel = null;

/**
 * Editor initialisieren.
 */
async function initEditor() {
    const body = document.getElementById('report-editor-body');
    if (!body) return;

    // Eindeutige Instanz-ID aus sessionStorage lesen oder neu erzeugen
    EditorState.instanceId = sessionStorage.getItem('forensic_editor_instance')
        || (() => {
            const id = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
            sessionStorage.setItem('forensic_editor_instance', id);
            return id;
        })();

    // Editor-HTML-Grundstruktur aufbauen
    const container = document.getElementById('report-editor-container');
    if (container) {
        container.innerHTML = `
            <div id="report-editor-toolbar">
                <span id="report-lock-status" class="lock-none">Kein Lock</span>
                <button class="editor-btn editor-btn-primary" id="btn-acquire-lock"
                    title="Editor-Lock erwerben um schreiben zu können">Lock erwerben</button>
                <button class="editor-btn" id="btn-release-lock" disabled
                    title="Editor-Lock freigeben">Lock freigeben</button>
                <button class="editor-btn" id="btn-reload-paragraphs">Aktualisieren</button>
            </div>
            <div id="report-status-msg"></div>
            <ul id="report-paragraphs-list" aria-label="Berichtsparagraphen"></ul>
            <div id="report-new-paragraph" class="editor-new-paragraph" style="display:none">
                <textarea id="report-new-content"
                    placeholder="Neuer Paragraph (Beweisanker: [BELEG:annotation_id=N])"
                    aria-label="Neuer Paragraph"></textarea>
                <div style="margin-top:6px;display:flex;gap:6px">
                    <button class="editor-btn editor-btn-primary" id="btn-save-paragraph">Speichern</button>
                    <button class="editor-btn" id="btn-cancel-paragraph">Abbrechen</button>
                </div>
            </div>
            <div id="report-frozen-overlay">
                <div>
                    <strong>Dieser Editor ist bereits in einem anderen Fenster geöffnet.</strong><br>
                    Dieses Fenster ist schreibgeschützt.
                </div>
            </div>`;
    }

    // Schicht 1: BroadcastChannel — Duplikat-Erkennung (§8.6 Bauplan B4)
    initBroadcastLock();

    // SSE-Verbindung aufbauen — Client-ID empfangen
    await initSSEWindow3();

    // Paragraphen laden
    await reloadParagraphs();

    // Buttons verdrahten
    document.getElementById('btn-acquire-lock')?.addEventListener('click', acquireLock);
    document.getElementById('btn-release-lock')?.addEventListener('click', releaseLock);
    document.getElementById('btn-reload-paragraphs')?.addEventListener('click', reloadParagraphs);
    document.getElementById('btn-save-paragraph')?.addEventListener('click', saveNewParagraph);
    document.getElementById('btn-cancel-paragraph')?.addEventListener('click', cancelNewParagraph);

    // Lock bei Seitenentladung freigeben (§8.6 Bauplan B4 — beforeunload)
    window.addEventListener('beforeunload', () => {
        if (EditorState.lockId) {
            releaseLock(true); // synchron via sendBeacon
        }
    });
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
    return new Promise(resolve => {
        const evtSrc = new EventSource(FORENSIC_API.EVENTS);
        let resolved = false;

        evtSrc.addEventListener('client_id', evt => {
            try {
                const { client_id } = JSON.parse(evt.data);
                EditorState.sseClientId = client_id;
            } catch (_) {}
            if (!resolved) { resolved = true; resolve(); }
        });

        evtSrc.addEventListener('editor_lock_acquired', evt => {
            try {
                const { locked_by } = JSON.parse(evt.data);
                if (locked_by === (document.getElementById('report-editor-body')?.dataset?.investigator || '')) {
                    updateLockStatus('lock-mine', `Lock: ich`);
                } else {
                    updateLockStatus('lock-other', `Lock: ${esc(locked_by)}`);
                    disableEditorControls(true);
                }
            } catch (_) {}
        });

        evtSrc.addEventListener('editor_lock_released', () => {
            if (!EditorState.lockId) {
                updateLockStatus('lock-none', 'Kein Lock');
            }
        });

        evtSrc.addEventListener('report_updated', () => {
            reloadParagraphs();
        });

        // Timeout: nach 3s auch ohne client_id fortfahren
        setTimeout(() => {
            if (!resolved) { resolved = true; resolve(); }
        }, 3000);
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
    if (EditorState.frozen) return;
    if (!EditorState.sseClientId) {
        showStatusMsg('SSE-Verbindung nicht bereit — bitte Seite neu laden.', 'warn');
        return;
    }

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
            document.getElementById('report-new-paragraph').style.display = '';
            showStatusMsg('Lock erworben.', 'ok');
        } else if (resp.status === 423) {
            updateLockStatus('lock-other', `Belegt: ${esc(data.locked_by || '?')}`);
            showStatusMsg(`Lock bereits belegt von: ${esc(data.locked_by || '?')}`, 'warn');
        } else {
            showStatusMsg(`Fehler: ${esc(data.error || resp.status)}`, 'error');
        }
    } catch (err) {
        showStatusMsg(`Netzwerkfehler: ${esc(String(err))}`, 'error');
    }
}

/**
 * Lock freigeben (§8.5 Bauplan B4 — release_lock).
 * @param {boolean} sync - true = synchron via sendBeacon (beforeunload)
 */
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
            document.getElementById('report-new-paragraph').style.display = 'none';
            showStatusMsg('Lock freigegeben.', 'ok');
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

function cancelNewParagraph() {
    const textarea = document.getElementById('report-new-content');
    if (textarea) textarea.value = '';
    document.getElementById('report-new-paragraph').style.display = 'none';
}

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
