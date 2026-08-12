// =============================================================================
// management/server/static/cockpit_personnel.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Personalverwaltung
// =============================================================================
// Zweck (Build 503, Bauplan Build503 §4):
//   Die "Seite zum Verwalten der Anwender" (mc 2026-07-24): Personenliste mit
//   Aktiv-Status, Rollen-Flags und Rollenzuweisungen — plus der EINGEBUNDENE
//   AD-Abgleich (Wiederverwendung der Komponente AIWCockpitAdSync aus Build
//   502, KEINE Kopie).
//
//   Bedienelemente (nur bei can_edit):
//     - Flags (Ermittler/Supervisor/Support) als Checkboxen -> onFlags.
//     - Rollen-Chips mit Widerrufs-x -> onRevoke (Soft-Revoke, auditiert).
//     - Zuweisen-Dropdown (Rollenkatalog) + Knopf -> onAssign.
//   SELBSTSCHUTZ: die eigene Zeile (actor_person_id) zeigt KEINE
//   Bedienelemente — der Server weist eigene Aenderungen ohnehin mit 400 ab
//   (Lockout-Schutz, Bauplan §3); die Oberflaeche bietet sie gar nicht an.
//
//   AD-Abgleich-Abschnitt (nur bei can_sync): LAZY — der Knopf "AD-Vorschau
//   laden" holt /api/adsync erst auf Klick (kein LDAP-Zugriff beim blossen
//   Oeffnen der Seite; der Abruf kann je nach DC dauern) und rendert die
//   bestehende AdSync-Komponente in einen Unter-Container.
//
// Datenform GET /api/personnel (ManagementApp._personnel):
//   { persons: [{id, system_username, display_name, is_investigator,
//                is_supervisor, is_support, created_at, is_active,
//                deactivated_at, deactivated_reason,
//                roles: [{person_role_id, role_code, label, assigned_at}]}],
//     roles_catalog: [{code, label}],
//     actor_person_id, can_edit, can_sync }
//
// SCHREIBEN (opts -> cockpit.js -> postJson mit X-AIW-Token):
//   onFlags({person_id, <flag>: bool})       — genau EIN Flag je Klick.
//   onAssign({person_id, role_code})         — Rolle zuweisen.
//   onRevoke({person_role_id})               — Zuweisung widerrufen.
//   onSetActive({person_id, active, reason?, confirmation})
//                                            — Ruhestand setzen/aufheben
//                                              (Build 701).
//   onAdsyncLoad(containerEl, setResult)     — AD-Vorschau in den Container
//                                              laden (cockpit.js haelt die
//                                              fetch/post-Logik).
//   KEIN optimistisches UI: nach jedem Schreiben laedt cockpit.js die Sicht neu.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS: (1) IIFE + 'use strict'. (2) DEV-Logging
//   (AIW_COCKPIT_DEBUG). (3) ausfuehrliche Kommentare. (4) reine Funktionen
//   fassen NIE das DOM an -> vitest; opts.doc injizierbar (JSDOM).
// SICHERHEIT (XSS): alle variablen Texte via textContent.
//
// BUILD 548 — TABULATOR + GEMEINSAMES TABELLEN-WERKZEUG (mc 2026-07-26):
//   Die Personenliste war eine handgebaute <table> ohne Sortierung und ohne
//   Filter. Sie ist jetzt eine Tabulator-Tabelle mit Kopffiltern,
//   Trefferzaehler, 'Filter zuruecksetzen' und gesicherter Sortierung — also
//   dieselbe Bedienung wie in der Zuweisung und der Fall-Erkennung.
//
//   DIE ALTE BEGRUENDUNG WAR UEBERHOLT, NICHT FALSCH. Hier stand: "kein
//   Tabulator: die Zeilen tragen interaktive Elemente, die wir exakt
//   kontrollieren wollen". Das galt fuer Build 503 — das gemeinsame Werkzeug
//   kam erst mit Build 534, und seither steckt cockpit_cases.js (:528-552)
//   nachweislich Auswahlkaestchen mit eigenen Ereignisbehandlern in
//   Tabulator-Zellen, cockpit_assignment.js zusaetzlich Auswahllisten und
//   Knoepfe. Die Kontrolle ueber die Zellen geht durch Tabulator NICHT
//   verloren: sie entstehen weiterhin hier, in eigenen Formattern.
//
//   WAS SICH NICHT AENDERT — und das ist der Punkt bei einer Schreib-Sicht:
//   der SELBSTSCHUTZ (die eigene Zeile traegt keine Bedienelemente), das
//   Fehlen optimistischer Anzeige (nach jedem Schreiben laedt cockpit.js neu)
//   und der lazy AD-Abschnitt. Alle drei sind unveraendert und weiterhin
//   durch Tests gedeckt.
//
//   FILTER AUF WAHRHEITSWERTEN: die drei Flag-Spalten wuerden als true/false
//   eine Auswahlliste 'true'/'false' erzeugen. Deshalb tragen die Zeilen je
//   Flag ZUSAETZLICH ein Textfeld 'ja'/'nein' (toRows) — danach wird
//   gefiltert und sortiert, waehrend der Formatter den Wahrheitswert nimmt.
//   Ein Filter, den man nicht lesen kann, wird nicht benutzt.
//
//   HILFE-ANKER (data-hilfe-id): Spaltenkoepfe und Bedienelemente tragen
//   stabile Kennungen fuer die spaetere Schnellhilfe. Sie kosten jetzt fast
//   nichts; spaeter waeren dafuer alle Sichten ein zweites Mal anzufassen.
//
// Build 636 (Vorgang 17200856, Welle B4): HILFE-MARKEN fuer die
//   fuenf Bedienelemente mit GERECHNETER Kennung dieser Sicht.
//
// BUILD 701 — RUHESTAND VON HAND (Ticket 95139d2a "Benutzer auf inaktiv
//   setzen"):
//   Die Sicht ZEIGTE den Aktiv-Status seit Build 503, konnte ihn aber nicht
//   SETZEN. Der einzige Weg fuehrte ueber den AD-Abschnitt — und der kann nur
//   Kennungen anfassen, die das Verzeichnis bereits ausgetragen hat. Ein
//   Ermittler, der heute ausscheidet, war damit nicht abbildbar.
//
//   NEUE SPALTE "Ruhestand" mit EINEM Knopf je Zeile ("Inaktiv setzen" bzw.
//   "Reaktivieren"). Er vollzieht NICHTS, sondern oeffnet einen
//   Bestaetigungsblock unter der Tabelle.
//
//   WARUM EIN BLOCK UNTER DER TABELLE UND KEIN DIALOGFENSTER: Diese Sicht
//   fuehrt bereits eine solche Flaeche — die Kandidatenzeilen des
//   AD-Abgleichs (cockpit_adsync.js:227) mit Wort-Eingabe und Knoepfen. Die
//   Bedienung ist dieselbe Handlung mit derselben Verantwortung, also bekommt
//   sie dieselbe Gestalt. Ein zweites Muster (modales Fenster) haette
//   ausserdem fremdes CSS aus cockpit_notes.css mitbenutzt und dieser Sicht
//   eine Abhaengigkeit eingetragen, die sie bisher nicht hat.
//
//   DER BLOCK NENNT DIE OFFENEN FAELLE. Offene Faelle blockieren das
//   Inaktivsetzen NICHT (Entscheidung Alex, 12.08.2026: Ausscheiden ist eine
//   Tatsache, kein Antrag) — aber wer den Knopf drueckt, muss sehen, wieviel
//   Arbeit gerade unbeaufsichtigt bleibt. Eine stille Deaktivierung waere die
//   bequeme und die falsche Loesung.
//
//   BESTAETIGUNGSWORT: kommt VOM SERVER (data.confirm) wie im AD-Abschnitt —
//   eine Wahrheitsquelle. Der Browser prueft nur als Komfort vor dem
//   Absenden; verbindlich prueft /api/personnel/active.
// Version: v0.8.701 · Build: 701 · 2026-08-12
//   Build 503: Erstfassung (handgebaute Tabelle).
// =============================================================================

(function () {
    'use strict';

    function debugOn() {
        return (typeof window !== 'undefined')
            && window.AIW_COCKPIT_DEBUG === true;
    }
    function log() {
        if (!debugOn()) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-Personnel]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '—';
    var SICHT = 'personnel';   // Praefix der Hilfe-Anker + Zustandsschluessel

    // Zugriff auf das gemeinsame Tabellen-Werkzeug. LAZY (in der Funktion,
    // nicht beim Laden): die Skripte tragen alle 'defer' und laufen in
    // Dokumentreihenfolge, aber ein spaeterer Umbau der Reihenfolge soll diese
    // Sicht nicht lautlos brechen. Muster cockpit_assignment.js:131.
    function _tk() {
        return (typeof window !== 'undefined' && window.AIWTableKit)
            ? window.AIWTableKit : null;
    }

    //: Reihenfolge + Beschriftung der Flag-Spalten (person-Schema, Build 310).
    var FLAGS = [
        { key: 'is_investigator', label: 'Ermittler:in' },
        { key: 'is_supervisor', label: 'Supervisor' },
        { key: 'is_support', label: 'Support' }
    ];

    // ------------------------------------------------------------------ Helfer
    // (REINE Funktionen — kein DOM, kein Netz; vitest-geprueft.)

    // statusText: Anzeige des Aktiv-Status. Inaktive tragen Zeitpunkt+Grund
    // (forensische Nachvollziehbarkeit direkt in der Liste).
    function statusText(p) {
        if (p && p.is_active === false) {
            var since = p.deactivated_at
                ? new Date(p.deactivated_at * 1000).toISOString().slice(0, 10)
                : '?';
            var reason = p.deactivated_reason || '';
            return 'inaktiv seit ' + since + (reason ? ' (' + reason + ')' : '');
        }
        return 'aktiv';
    }

    // ---------------------------------------------- Ruhestand (Build 701)
    // confirmWords: die vom SERVER vorgegebenen Bestaetigungsworte. Der
    // Rueckfall dient NUR einem Altserver ohne das Feld — er darf nicht dazu
    // verleiten, die Worte hier zu pflegen; die Wahrheit steht im Server
    // (management_app._personnel bzw. ad_sync/sync_executor.py).
    function confirmWords(data) {
        var c = (data && data.confirm) || {};
        return {
            deactivate: c.deactivate || 'Entfernen',
            reactivate: c.reactivate || 'Reaktivieren'
        };
    }

    // validateWort: Komfort-Vorpruefung. EXAKT wie am Server: kein trim,
    // keine Normalisierung — 'entfernen' zaehlt nicht. Eine grosszuegigere
    // Pruefung hier waere schlimmer als gar keine: sie liesse etwas durch,
    // das der Server dann doch abweist, und der Nutzer suchte den Fehler an
    // der falschen Stelle.
    function validateWort(erwartet, getippt) {
        return typeof getippt === 'string' && getippt === erwartet;
    }

    // ruhestandFrage: welche Handlung bietet diese Zeile an? null = keine
    // (kein Aenderungsrecht oder eigene Zeile — Selbstschutz).
    //
    // SELBSTSCHUTZ IST HIER BESONDERS WICHTIG: wer sich selbst inaktiv setzt,
    // kommt nicht wieder herein — identity.py weist inaktive Konten an der
    // Anmeldung ab. Das waere der vollstaendige Lockout mit einem Klick.
    function ruhestandFrage(row, words) {
        if (!row || !row.editierbar) { return null; }
        words = words || { deactivate: 'Entfernen',
                           reactivate: 'Reaktivieren' };
        if (row.status === 'inaktiv') {
            return {
                aktion: 'reactivate', active: true,
                knopf: 'Reaktivieren',
                wort: words.reactivate,
                braucht_grund: false
            };
        }
        return {
            aktion: 'deactivate', active: false,
            knopf: 'Inaktiv setzen',
            wort: words.deactivate,
            braucht_grund: true
        };
    }

    // offeneFaelleText: der Satz, der im Bestaetigungsblock steht. Er ist
    // bewusst unterschiedlich formuliert — "keine offenen Faelle" ist eine
    // Entwarnung und darf nicht wie eine Warnung aussehen, und umgekehrt.
    function offeneFaelleText(person) {
        var n = (person && typeof person.offene_faelle === 'number')
            ? person.offene_faelle : null;
        if (n === null) {
            return 'Zahl der offenen Fälle nicht bekannt — bitte vor dem '
                + 'Vollzug in der Zuweisung nachsehen.';
        }
        if (n === 0) {
            return 'Keine offenen Fälle zugewiesen.';
        }
        return 'ACHTUNG: trägt noch ' + n + ' offene'
            + (n === 1 ? 'n Fall' : ' Fälle')
            + '. Die Zuweisung bleibt bestehen — sie muss gesondert '
            + 'umverteilt werden.';
    }

    // activeBody: Request-Koerper fuer POST /api/personnel/active.
    // 'reason' wandert nur beim Inaktivsetzen mit (beim Reaktivieren gibt es
    // nichts zu begruenden — der alte Grund steht im Beleg der Deaktivierung
    // und wird beim Reaktivieren als alt->neu mitgefuehrt).
    function activeBody(personId, active, reason, confirmation) {
        var body = { person_id: personId, active: !!active,
                     confirmation: confirmation };
        if (!active) { body.reason = reason || ''; }
        return body;
    }

    // assignableRoles: Katalogrollen, die die Person noch NICHT aktiv hat
    // (kein No-op-Angebot im Dropdown; der Server prueft verbindlich).
    function assignableRoles(person, catalog) {
        var have = {};
        ((person && person.roles) || []).forEach(function (r) {
            have[r.role_code] = true;
        });
        return (catalog || []).filter(function (r) { return !have[r.code]; });
    }

    // isSelf: die eigene Zeile (Selbstschutz — keine Bedienelemente).
    function isSelf(person, data) {
        return !!(person && data
            && person.id === data.actor_person_id);
    }

    // canEditRow: Bedienelemente nur mit Recht UND nicht auf der eigenen Zeile.
    function canEditRow(person, data) {
        return !!(data && data.can_edit) && !isSelf(person, data);
    }

    // toRows: Personen -> Tabellenzeilen. REIN (kein DOM) und damit
    // vitest-geprueft; hier entstehen alle abgeleiteten Felder, nach denen
    // gefiltert und sortiert wird.
    //
    // WARUM ABGELEITETE FELDER STATT FILTER AUF DEN ROHWERTEN:
    //   * 'status' ist 'aktiv'/'inaktiv' — zwei Werte, also eine Auswahlliste.
    //     Der VOLLE Text (mit Zeitpunkt und Grund) steht in 'status_detail'
    //     und erscheint als Tooltip; er taugt nicht als Filterwert, weil er
    //     bei jeder Person anders lautet.
    //   * 'f_<flag>' ist 'ja'/'nein' statt true/false — siehe Modulkopf.
    //   * 'rollen_text' macht die Rollen ueberhaupt erst durchsuchbar
    //     ("wer hat searchagent?"). Die Chips selbst sind DOM und filterbar
    //     waeren sie nicht.
    function toRows(data) {
        var d = data || {};
        return (d.persons || []).map(function (p) {
            var row = {
                id: p.id,
                system_username: p.system_username || '',
                display_name: p.display_name || '',
                status: (p.is_active === false) ? 'inaktiv' : 'aktiv',
                status_detail: statusText(p),
                rollen: (p.roles || []).slice(),
                rollen_text: (p.roles || []).map(function (r) {
                    return r.role_code;
                }).join(', '),
                ist_selbst: isSelf(p, d),
                editierbar: canEditRow(p, d),
                // Build 701: die Zahl offener Faelle wandert in die Zeile,
                // damit der Bestaetigungsblock sie nennen kann, ohne ein
                // zweites Mal nachzufragen. Fehlt sie (Altserver), bleibt
                // sie null — und der Block sagt "nicht bekannt" statt "0".
                offene_faelle: (typeof p.offene_faelle === 'number')
                    ? p.offene_faelle : null,
                _person: p
            };
            FLAGS.forEach(function (f) {
                row[f.key] = p[f.key] === true;
                row['f_' + f.key] = (p[f.key] === true) ? 'ja' : 'nein';
            });
            return row;
        });
    }

    // spalten: die Spaltendefinition inklusive Formatter.
    // Braucht 'doc' (Formatter bauen DOM) und 'opts' (Rueckrufe).
    function spalten(doc, data, opts) {
        var TK = _tk();
        function titel(text, id, erklaerung) {
            return (TK && TK.titelMitHilfe)
                ? TK.titelMitHilfe(doc, text, SICHT + '.spalte.' + id,
                                   erklaerung)
                : undefined;
        }
        function anker(el, id) {
            return (TK && TK.hilfeAnker) ? TK.hilfeAnker(el, id) : el;
        }

        var cols = [
            {
                title: 'Kennung', field: 'system_username', widthGrow: 2,
                titleFormatter: titel('Kennung', 'kennung',
                    'Anmeldename aus dem Active Directory.'),
                formatter: function (cell) {
                    var d = cell.getData();
                    var sp = doc.createElement('span');
                    sp.className = 'aiw-pers-kennung'
                        + (d.ist_selbst ? ' self' : '')
                        + (d.status === 'inaktiv' ? ' inactive' : '');
                    sp.textContent = d.system_username
                        + (d.ist_selbst ? ' (ich)' : '');
                    if (d.ist_selbst) {
                        sp.title = 'Ihre eigene Kennung — an der eigenen '
                            + 'Person sind keine Änderungen möglich '
                            + '(Lockout-Schutz).';
                    }
                    return sp;
                }
            },
            {
                title: 'Anzeigename', field: 'display_name', widthGrow: 2,
                titleFormatter: titel('Anzeigename', 'anzeigename',
                    'Name aus dem Active Directory.'),
                formatter: 'plaintext'
            },
            {
                title: 'Status', field: 'status', width: 110,
                titleFormatter: titel('Status', 'status',
                    'Aktiv oder deaktiviert. Bei Deaktivierten nennt der '
                    + 'Tooltip Zeitpunkt und Grund.'),
                formatter: function (cell) {
                    var d = cell.getData();
                    var sp = doc.createElement('span');
                    sp.className = 'aiw-pers-status ' + d.status;
                    sp.textContent = d.status;
                    sp.title = d.status_detail;
                    return sp;
                }
            }
        ];

        // --- Die drei Flag-Spalten -----------------------------------------
        FLAGS.forEach(function (f) {
            cols.push({
                title: f.label, field: 'f_' + f.key, width: 120,
                hozAlign: 'center',
                titleFormatter: titel(f.label, f.key.replace('is_', ''),
                    'Merkmal der Person. Es steuert, wo sie zur Auswahl '
                    + 'angeboten wird — nicht ihre Rechte; die kommen aus '
                    + 'den Rollen.'),
                formatter: function (cell) {
                    var d = cell.getData();
                    if (!d.editierbar) {
                        var sp = doc.createElement('span');
                        sp.textContent = d[f.key] ? '✓' : EM_DASH;
                        sp.title = d.ist_selbst
                            ? 'Eigene Person — nicht änderbar.'
                            : 'Kein Änderungsrecht.';
                        return sp;
                    }
                    var cb = doc.createElement('input');
                    cb.type = 'checkbox';
                    cb.className = 'aiw-pers-flag-cb';
                    cb.checked = d[f.key] === true;
                    cb.setAttribute('aria-label',
                        f.label + ' für ' + d.system_username);
                    // Je Merkmal ein EIGENER Anker: 'Ermittler:in',
                    // 'Supervisor' und 'Support' bedeuten Verschiedenes und
                    // brauchen spaeter verschiedene Erklaerungen. Ein
                    // gemeinsamer Anker haette drei Begriffe in einen Text
                    // gezwungen.
                    // Build 636 (Vorgang 17200856): Die Kennung war
                    // GERECHNET (SICHT + '.bedienung.' + f.key...). Die drei
                    // Texte gab es seit Build 603 im Register - erreichbar
                    // waren sie nie, denn weder die Paritaetspruefung
                    // SP01/SP02 noch die Erhebung sieht eine gerechnete
                    // Kennung. Jetzt drei literale Zweige.
                    if (f.key === 'is_investigator') {
                        cb.setAttribute('data-hilfe-id',
                            'personnel.bedienung.flag_investigator');
                    } else if (f.key === 'is_supervisor') {
                        cb.setAttribute('data-hilfe-id',
                            'personnel.bedienung.flag_supervisor');
                    } else {
                        cb.setAttribute('data-hilfe-id',
                            'personnel.bedienung.flag_support');
                    }
                    cb.addEventListener('click', function (e) {
                        e.stopPropagation();
                    });
                    cb.addEventListener('change', function () {
                        var body = { person_id: d.id };
                        body[f.key] = cb.checked;
                        if (typeof opts.onFlags === 'function') {
                            opts.onFlags(body);
                        }
                    });
                    return cb;
                }
            });
        });

        // --- Rollen: Chips + Zuweisen-Auswahl ------------------------------
        cols.push({
            title: 'Rollen', field: 'rollen_text', widthGrow: 3,
            titleFormatter: titel('Rollen', 'rollen',
                'Aktive Rollenzuweisungen. Sie tragen die Rechte. Der '
                + 'Filter durchsucht die Rollenkürzel.'),
            formatter: function (cell) {
                var d = cell.getData();
                var wrap = doc.createElement('div');
                wrap.className = 'aiw-pers-roles';

                d.rollen.forEach(function (r) {
                    var chip = doc.createElement('span');
                    chip.className = 'aiw-pers-chip';
                    var lbl = doc.createElement('span');
                    lbl.textContent = r.role_code;
                    lbl.title = r.label || r.role_code;
                    chip.appendChild(lbl);
                    if (d.editierbar) {
                        var x = doc.createElement('button');
                        x.type = 'button';
                        x.className = 'aiw-pers-chip-x';
                        x.textContent = '×';
                        x.title = 'Zuweisung widerrufen (auditiert, '
                            + 'Soft-Revoke)';
                        x.setAttribute('aria-label',
                            'Rolle ' + r.role_code + ' widerrufen');
                        x.setAttribute('data-hilfe-id',
                            'personnel.bedienung.rolle_widerrufen');
                        x.addEventListener('click', function (e) {
                            e.stopPropagation();
                            if (typeof opts.onRevoke === 'function') {
                                opts.onRevoke(
                                    { person_role_id: r.person_role_id });
                            }
                        });
                        chip.appendChild(x);
                    }
                    wrap.appendChild(chip);
                });

                if (d.editierbar) {
                    var candidates = assignableRoles(d._person,
                                                     (data || {}).roles_catalog);
                    if (candidates.length) {
                        var sel = doc.createElement('select');
                        sel.className = 'aiw-pers-assign-sel';
                        sel.setAttribute('aria-label',
                            'Rolle zuweisen für ' + d.system_username);
                        sel.setAttribute('data-hilfe-id',
                            'personnel.bedienung.rolle_zuweisen');
                        var ph = doc.createElement('option');
                        ph.value = '';
                        ph.textContent = 'Rolle zuweisen …';
                        sel.appendChild(ph);
                        candidates.forEach(function (r) {
                            var o = doc.createElement('option');
                            o.value = r.code;
                            o.textContent = r.code + ' (' + r.label + ')';
                            sel.appendChild(o);
                        });
                        sel.addEventListener('click', function (e) {
                            e.stopPropagation();
                        });
                        sel.addEventListener('change', function () {
                            if (!sel.value) { return; }
                            if (typeof opts.onAssign === 'function') {
                                opts.onAssign({ person_id: d.id,
                                                role_code: sel.value });
                            }
                        });
                        wrap.appendChild(sel);
                    }
                }
                return wrap;
            }
        });

        // --- Ruhestand: EIN Knopf je Zeile (Build 701) ---------------------
        // KEIN FILTER auf dieser Spalte (kein_filter): sie traegt keine
        // Angabe, sondern eine Handlung. Wonach man hier filtern wollte —
        // aktiv/inaktiv — steht bereits in der Spalte "Status"; ein zweiter
        // Filter fuer dieselbe Sache waere eine zweite Wahrheitsquelle.
        var words = confirmWords(data);
        cols.push({
            title: 'Ruhestand', field: 'ruhestand', width: 150,
            kein_filter: true, headerSort: false,
            titleFormatter: titel('Ruhestand', 'ruhestand',
                'Eine ausgeschiedene Person inaktiv setzen oder eine '
                + 'zurückgekehrte wieder in Betrieb nehmen. Gelöscht wird '
                + 'nie — die Zeile bleibt als Beleg.'),
            formatter: function (cell) {
                var d = cell.getData();
                var frage = ruhestandFrage(d, words);
                if (!frage) {
                    // Kein Knopf: eigene Zeile oder kein Aenderungsrecht.
                    // Der Grund wird BENANNT (Tooltip) — eine leere Zelle
                    // liesse offen, ob die Funktion fehlt oder das Recht.
                    var sp = doc.createElement('span');
                    sp.textContent = EM_DASH;
                    sp.title = d.ist_selbst
                        ? 'Eigene Person — nicht änderbar (Lockout-Schutz).'
                        : 'Kein Änderungsrecht.';
                    return sp;
                }
                var btn = doc.createElement('button');
                btn.type = 'button';
                btn.className = 'aiw-pers-ruhe-btn '
                    + (frage.active ? 'react' : 'deact');
                btn.textContent = frage.knopf;
                btn.setAttribute('aria-label',
                    frage.knopf + ' für ' + d.system_username);
                // ZWEI literale Zweige statt einer gerechneten Kennung:
                // Inaktivsetzen und Reaktivieren sind verschiedene
                // Handlungen mit verschiedenen Folgen und brauchen
                // verschiedene Erklaerungen. Eine gerechnete Kennung saehe
                // ausserdem weder SP01/SP02 noch die Erhebung (Befund
                // Build 636).
                if (frage.active) {
                    btn.setAttribute('data-hilfe-id',
                        'personnel.bedienung.ruhestand_reaktivieren');
                } else {
                    btn.setAttribute('data-hilfe-id',
                        'personnel.bedienung.ruhestand_inaktiv');
                }
                btn.addEventListener('click', function (e) {
                    e.stopPropagation();
                    if (typeof opts.onRuhestandFrage === 'function') {
                        opts.onRuhestandFrage(d, frage);
                    }
                });
                return btn;
            }
        });
        return cols;
    }

    // ------------------------------------------------- Bestaetigungsblock
    // renderRuhestandBlock: die Flaeche unter der Tabelle, die nach dem Klick
    // auf "Inaktiv setzen"/"Reaktivieren" erscheint.
    //
    // SIE VOLLZIEHT ERST NACH ZWEI EINGABEN (beim Inaktivsetzen): Grund und
    // woertliches Bestaetigungswort. Der Grund ist Pflicht, weil er im Beleg
    // steht und spaeter die einzige Auskunft darueber ist, WARUM jemand aus
    // den Listen verschwunden ist ("ausgeschieden zum 31.08." gegen
    // "versehentlich"). Das Wort ist der Glitch-Schutz — dieselbe Begruendung
    // wie im AD-Abgleich (mc 2026-07-24).
    //
    // Gibt {el, fokus} zurueck; el ist NICHT angehaengt (der Aufrufer
    // entscheidet, wohin).
    function renderRuhestandBlock(doc, row, frage, opts, setResult) {
        var box = doc.createElement('div');
        box.className = 'aiw-pers-ruhestand '
            + (frage.active ? 'react' : 'deact');

        var h = doc.createElement('h3');
        h.className = 'aiw-pers-sect' + (frage.active ? '' : ' warn');
        h.textContent = '[' + frage.knopf + '] ' + EM_DASH + ' '
            + row.system_username + ' · ' + row.display_name;
        h.setAttribute('data-hilfe-id', 'personnel.abschnitt.ruhestand');
        box.appendChild(h);

        var hinweis = doc.createElement('p');
        hinweis.className = 'aiw-pers-hint';
        hinweis.textContent = frage.active
            ? ('Die Person erscheint danach wieder in allen Auswahllisten. '
               + 'Historische Rollenzuweisungen werden wieder wirksam.')
            : (offeneFaelleText(row) + ' Die Person verschwindet danach aus '
               + 'den Auswahllisten, NICHT aus den Belegen: Zuweisungen, '
               + 'Protokolle und Audit-Einträge bleiben unverändert und '
               + 'weiterhin mit ihrem Namen beschriftet.');
        box.appendChild(hinweis);

        var zeile = doc.createElement('div');
        zeile.className = 'aiw-pers-cand';

        var grund = null;
        if (frage.braucht_grund) {
            grund = doc.createElement('input');
            grund.type = 'text';
            grund.className = 'aiw-pers-grund';
            grund.placeholder = 'Grund (Pflicht — steht später im Beleg)';
            grund.setAttribute('autocomplete', 'off');
            grund.setAttribute('aria-label', 'Grund der Deaktivierung');
            grund.setAttribute('data-hilfe-id',
                'personnel.bedienung.ruhestand_grund');
            zeile.appendChild(grund);
        }

        var wort = doc.createElement('input');
        wort.type = 'text';
        wort.className = 'aiw-pers-wort';
        wort.placeholder = frage.wort;
        wort.setAttribute('autocomplete', 'off');
        wort.setAttribute('aria-label',
            'Bestätigungswort ' + frage.wort + ' eingeben');
        wort.setAttribute('data-hilfe-id',
            'personnel.bedienung.ruhestand_wort');
        zeile.appendChild(wort);

        var ok = doc.createElement('button');
        ok.type = 'button';
        ok.className = 'aiw-pers-ruhe-btn vollzug';
        ok.textContent = frage.knopf;
        ok.setAttribute('data-hilfe-id',
            'personnel.bedienung.ruhestand_vollzug');
        ok.addEventListener('click', function () {
            var g = grund ? grund.value : '';
            // Reihenfolge der Pruefungen: erst der Grund, dann das Wort.
            // Wer beides falsch hat, soll zuerst vom Pflichtfeld erfahren —
            // das Wort noch einmal zu tippen, waere sonst umsonst gewesen.
            if (frage.braucht_grund && !String(g).trim()) {
                setResult('Nicht vollzogen: der Grund ist Pflicht (er steht '
                    + 'später im Beleg).', true);
                return;
            }
            if (!validateWort(frage.wort, wort.value)) {
                setResult('Nicht vollzogen: Bestätigungswort entspricht '
                    + 'nicht exakt „' + frage.wort + '“.', true);
                return;
            }
            if (typeof opts.onSetActive === 'function') {
                opts.onSetActive(activeBody(row.id, frage.active, g,
                                            wort.value));
            }
        });
        zeile.appendChild(ok);

        var weg = doc.createElement('button');
        weg.type = 'button';
        weg.className = 'aiw-pers-ruhe-btn abbruch';
        weg.textContent = 'Abbrechen';
        weg.setAttribute('data-hilfe-id',
            'personnel.bedienung.ruhestand_abbruch');
        weg.addEventListener('click', function () {
            // ABBRECHEN IST HIER FOLGENLOS und wird BEWUSST NICHT protokolliert
            // — anders als der Abbruch im AD-Abgleich. Dort ist der Abbruch die
            // Antwort auf eine vom System GESTELLTE Frage ("diese Kennung ist
            // nicht mehr im AD — was nun?"), und dass sie unbeantwortet blieb,
            // ist die Erkenntnis. Hier hat der Bedienende die Frage selbst
            // aufgeworfen; ein Beleg darueber, dass jemand einen Knopf gedrueckt
            // und es sich anders ueberlegt hat, waere Rauschen in der Audit-Kette.
            if (box.parentNode) { box.parentNode.removeChild(box); }
            setResult('', false);
        });
        zeile.appendChild(weg);

        box.appendChild(zeile);
        return { el: box, fokus: (grund || wort) };
    }

    // ---------------------------------------------------------------- Render
    function renderPersonnel(mainEl, data, opts) {
        opts = opts || {};
        var doc = opts.doc
            || (typeof document !== 'undefined' ? document : null);
        if (!mainEl || !doc || !data) { return { setResult: function () {} }; }

        mainEl.textContent = '';

        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Personalverwaltung';
        // Build 603 (Baustelle H / H12): literale Hilfe-Marken.
        h.setAttribute('data-hilfe-id', 'personnel.titel');
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = 'Anwender der Anlage: Aktiv-Status, Rollen-Flags und '
            + 'Rollenzuweisungen. Jede Aenderung wird auditiert; die eigene '
            + 'Person ist hier unantastbar (Lockout-Schutz), die Grants der '
            + 'Rollen-Matrix pflegt weiterhin die CLI (policy_admin).';
        sub.setAttribute('data-hilfe-id', 'personnel.kennzeile');
        mainEl.appendChild(sub);

        // --- Ergebniszeile ---------------------------------------------------
        var result = doc.createElement('div');
        result.className = 'aiw-pers-result';
        function setResult(text, isError) {
            result.textContent = text || '';
            result.classList.toggle('error', isError === true);
            result.classList.toggle('ok', isError === false);
        }
        mainEl.appendChild(result);

        // --- Personenliste als Tabulator-Tabelle -----------------------------
        // Build 549: die Verdrahtung (Werkzeugleiste, Kopffilter,
        // Trefferzahl, Zustandssicherung, Hilfe-Anker) kommt jetzt aus
        // TK.tabelleAufbauen und steht nicht mehr hier.
        //
        // DAS WAR EIN BEFUND DER KONFORMITAETSSUITE, kein Aufräumen: Build 548
        // hatte die Leiste von Hand verdrahtet und ihr die Kennung
        // 'aiw-pers-tk' gegeben, waehrend alle uebrigen Sichten
        // 'aiw-<sicht>-tk' benutzen. Ausgerechnet die Sicht, die Vorlage sein
        // soll, waere die Ausnahme gewesen.
        // --- Aufnahmeflaeche des Ruhestands-Blocks (Build 701) ---------------
        // Sie wird IMMER angelegt (auch ohne Aenderungsrecht) und bleibt leer,
        // bis jemand einen Knopf der Spalte "Ruhestand" drueckt. Der Block
        // steht damit an einer festen Stelle — unter der Tabelle, ueber dem
        // AD-Abschnitt — und springt nicht je nach Zeile umher.
        var ruheHost = doc.createElement('div');
        ruheHost.className = 'aiw-pers-ruhehost';
        var offenerBlock = null;

        function ruhestandFrageOeffnen(row, frage) {
            // IMMER NUR EINE FRAGE OFFEN. Zwei gleichzeitig geoeffnete Bloecke
            // mit je einer Wort-Eingabe waeren die perfekte Falle: man tippt
            // das Wort in den einen und drueckt den Knopf des anderen.
            if (offenerBlock && offenerBlock.parentNode) {
                offenerBlock.parentNode.removeChild(offenerBlock);
            }
            var b = renderRuhestandBlock(doc, row, frage, opts, setResult);
            offenerBlock = b.el;
            ruheHost.appendChild(b.el);
            setResult('', false);
            if (b.fokus && typeof b.fokus.focus === 'function') {
                b.fokus.focus();
            }
        }

        // Die Spalten brauchen den Oeffner, der Aufrufer soll ihn nicht
        // kennen muessen: flache Kopie der opts mit einem Zusatz (ES5, kein
        // Object.assign — dieselbe Zurueckhaltung wie im uebrigen Bestand).
        var spaltenOpts = {};
        Object.keys(opts).forEach(function (k) { spaltenOpts[k] = opts[k]; });
        spaltenOpts.onRuhestandFrage = ruhestandFrageOeffnen;

        var TK = _tk();
        var rows = toRows(data);
        var cols = spalten(doc, data, spaltenOpts);
        var table = null;
        var leiste = null;

        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);

        if (!TK) {
            var warn = doc.createElement('div');
            warn.className = 'aiw-placeholder';
            warn.textContent = 'Gemeinsames Tabellen-Werkzeug nicht geladen — '
                + 'die Personenliste kann nicht angezeigt werden. Es sind '
                + rows.length + ' Anwender hinterlegt.';
            mainEl.appendChild(warn);
        } else {
            var auf = TK.tabelleAufbauen(doc, mainEl, {
                sicht: SICHT,
                rows: rows,
                columns: cols,
                Ctor: Ctor,
                einheit: 'Anwender',
                tabulator: {
                    index: 'id',
                    initialSort: [{ column: 'system_username', dir: 'asc' }],
                    // Zeilenmarkierung: eigene Person und Deaktivierte sind
                    // auf einen Blick zu erkennen. Die Klassen sind dieselben
                    // wie vor dem Umbau, damit Stil und Tests nicht
                    // auseinanderlaufen.
                    rowFormatter: function (row) {
                        var d = row.getData();
                        var el = row.getElement();
                        if (!el || !el.classList) { return; }
                        el.classList.add('aiw-pers-row');
                        if (d.ist_selbst) { el.classList.add('self'); }
                        if (d.status === 'inaktiv') {
                            el.classList.add('inactive');
                        }
                    }
                }
            });
            table = auf.table;
            leiste = auf.leiste;
            if (auf.host) { auf.host.classList.add('aiw-pers-table'); }
        }
        mainEl.appendChild(ruheHost);

        // --- Hinweis, falls die Fallzahlen nicht ermittelt werden konnten ----
        // Er steht bewusst HIER und nicht erst im Bestaetigungsblock: wer die
        // Liste ansieht, soll wissen, dass eine Angabe fehlt, bevor er auf
        // ihrer Grundlage entscheidet (Grundregel 1 — keine stille Luecke).
        if (data.offene_faelle_hinweis) {
            var lueck = doc.createElement('p');
            lueck.className = 'aiw-pers-hint warn';
            lueck.textContent = 'Hinweis: ' + data.offene_faelle_hinweis;
            mainEl.appendChild(lueck);
        }

        // --- AD-Abgleich (lazy, nur mit personnel.sync) ----------------------
        if (data.can_sync) {
            var h3 = doc.createElement('h3');
            h3.className = 'aiw-pers-sect';
            h3.textContent = 'AD-Abgleich';
            h3.setAttribute('data-hilfe-id', 'personnel.abschnitt.adsync');
            mainEl.appendChild(h3);

            var hint = doc.createElement('p');
            hint.className = 'aiw-pers-hint';
            hint.textContent = 'Die Vorschau fragt das Live-AD ab und wird '
                + 'deshalb erst auf Anforderung geladen.';
            mainEl.appendChild(hint);

            var box = doc.createElement('div');
            box.className = 'aiw-pers-adsync';
            var loadBtn = doc.createElement('button');
            loadBtn.type = 'button';
            loadBtn.className = 'aiw-adsync-btn aiw-pers-adsync-load';
            loadBtn.textContent = 'AD-Vorschau laden';
            loadBtn.setAttribute('data-hilfe-id',
                                 'personnel.bedienung.adsync_laden');
            loadBtn.addEventListener('click', function () {
                loadBtn.disabled = true;  // Doppelklick-Schutz
                if (typeof opts.onAdsyncLoad === 'function') {
                    opts.onAdsyncLoad(box, setResult);
                }
            });
            mainEl.appendChild(loadBtn);
            mainEl.appendChild(box);
            // Nach einer AD-Aktion laedt cockpit.js die Sicht mit offenem
            // Abschnitt neu (opts.adsyncOpen) — dann sofort laden, ohne Klick.
            if (opts.adsyncOpen === true
                    && typeof opts.onAdsyncLoad === 'function') {
                loadBtn.disabled = true;
                opts.onAdsyncLoad(box, setResult);
            }
        }

        log('gerendert:', (data.persons || []).length, 'Personen');
        return { setResult: setResult, table: table, leiste: leiste };
    }

    // ------------------------------------------------------------------ Export
    var api = {
        renderPersonnel: renderPersonnel,
        // reine Funktionen fuer vitest:
        statusText: statusText,
        assignableRoles: assignableRoles,
        isSelf: isSelf,
        canEditRow: canEditRow,
        toRows: toRows,
        spalten: spalten,
        FLAGS: FLAGS,
        SICHT: SICHT,
        // Build 701 (Ruhestand von Hand) — reine Funktionen fuer vitest:
        confirmWords: confirmWords,
        validateWort: validateWort,
        ruhestandFrage: ruhestandFrage,
        offeneFaelleText: offeneFaelleText,
        activeBody: activeBody,
        renderRuhestandBlock: renderRuhestandBlock
    };
    if (typeof window !== 'undefined') {
        window.AIWCockpitPersonnel = api;
    }
})();
