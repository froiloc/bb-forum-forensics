# =============================================================================
# management/migrate_templates_full_templates.py
# IT-Forensisches Ermittlungswerkzeug — Migration der templates.db (Build 388)
# =============================================================================
# Zweck:
#   1. Legt die Tabelle report_templates an: VOLLSTAENDIGE Berichtsvorlagen.
#   2. Seedet die vier fehlenden {{a:}}-Queries, die der Spurenvermerk braucht.
#   3. Seedet die Vorlage 'vermerk.nicht_identifiziert' (Spurenvermerk fuer
#      Faelle, in denen der Forennutzer NICHT identifiziert werden konnte).
#
#   ABGRENZUNG MODUL <-> VORLAGE (die zentrale Neuerung dieses Builds):
#     report_modules   -- EIN Textbaustein. Wird vom Client als EIN
#                         paragraph-Block eingefuegt (module_panel.js:903).
#                         Eine Tabelle ist damit nicht darstellbar.
#     report_templates -- EIN VOLLSTAENDIGES Berichtsgerueste aus MEHREREN
#                         typisierten Editor.js-Bloecken (header, paragraph,
#                         table). Wird serverseitig und TRANSAKTIONAL ueber
#                         die Aktion 'insert_template' eingefuegt.
#
#   IDEMPOTENT: mehrfaches Ausfuehren ist unschaedlich (Tabelle, Queries und
#   Vorlage werden nur angelegt, wenn noch nicht vorhanden). templates.db
#   enthaelt KEINE Ermittler-Ergebnisse (im Betrieb read-only) — dennoch VOR
#   dem Ausfuehren ein verifiziertes Backup anlegen (besondere Sorgfalt bei
#   Produktiv-Datenbanken, Datenmigrationsleitfaden).
#
#   Aufruf:
#     python -m management.migrate_templates_full_templates --templates-db PATH
#     python -m management.migrate_templates_full_templates --config ./config.yaml
#     (--dry-run zeigt nur an, was getan WUERDE)
#
# Beleg: Bauplan Build 388 §4, Projektgespraech 2026-07-12
# Version: v0.7.388 · Build: 388 · 2026-07-12
# =============================================================================

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from management.help import cli_epilog  # noqa: E402
# Build 646: Vorrangregel an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402

TEMPLATE_KEY = "vermerk.nicht_identifiziert"

# =============================================================================
# 1) DDL
# =============================================================================

_DDL_REPORT_TEMPLATES = """
CREATE TABLE IF NOT EXISTS report_templates (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    template_key TEXT    NOT NULL,
    title        TEXT    NOT NULL,
    description  TEXT,
    report_type  TEXT    NOT NULL
                 CHECK(report_type IN ('interim', 'final', 'addendum')),
    blocks_json  TEXT    NOT NULL,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_by   TEXT    NOT NULL,
    created_at   INTEGER NOT NULL,
    updated_at   INTEGER NOT NULL
);
"""

_DDL_REPORT_TEMPLATES_IDX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS rt_key_idx "
    "ON report_templates(template_key)"
)
_DDL_REPORT_TEMPLATES_ACTIVE_IDX = (
    "CREATE INDEX IF NOT EXISTS rt_active_idx "
    "ON report_templates(is_active, sort_order)"
)

# =============================================================================
# 2) Fehlende {{a:}}-Queries
# =============================================================================
# Alle Queries laufen gegen die forensic_<uid>.db (Alias fdb, unqualifiziert
# aufloesbar) — siehe forensic_api/placeholders.py::_execute_query.
#
# WARUM DIESE VIER NEU SIND (gemessen am Bestand, nicht geraten):
#   user.registered_datetime -- 'user.registered_date' liefert NUR das Datum.
#                               Der Spurenvermerk verlangt Datum UND Uhrzeit
#                               mit ausdruecklicher Zeitzonenangabe (UTC).
#                               Ohne die Angabe (UTC) ist die Zeit wertlos.
#   user.activity_range      -- Erster Beitrag bis letzte Aktivitaet. Bestand
#                               hatte nur die Einzelwerte first_post_date und
#                               last_active.
#   user.pm_conversations    -- Anzahl der PN-GESPRAECHE. Der stat_key
#                               'pm_topics_total' existiert bereits
#                               (phase_b_exporter.py), war aber nicht als
#                               Platzhalter verfuegbar. NICHT zu verwechseln
#                               mit 'pn_partners' (Gespraechspartner) oder
#                               'pm_posts_total' (Einzelnachrichten).
#   user.shares_total        -- 'Verbreitungshandlungen'. stat_key
#                               'shares_total' (Quelltabelle 'content').
#                               Bestand hatte nur 'shared_files_count'.
# =============================================================================

_NEW_QUERIES = [
    {
        "id": "user.registered_datetime",
        "title": "Registrierungszeitpunkt (Datum und Uhrzeit, UTC)",
        "description": (
            "Zeitpunkt der Kontoregistrierung mit Uhrzeit und ausdruecklicher "
            "Zeitzonenangabe (UTC). Die Zeitzone MUSS im Wert stehen: eine "
            "Uhrzeit ohne Bezugszeitzone ist forensisch nicht verwertbar."
        ),
        "sql_query": (
            "SELECT strftime('%d.%m.%Y, %H:%M', datetime(registered, 'unixepoch')) "
            "|| ' Uhr (UTC)' FROM uid_profile WHERE id = :uid"
        ),
        "tags": "identitaet,datum,registrierung,spurenvermerk",
        "return_type": "scalar",
    },
    {
        "id": "user.activity_range",
        "title": "Aktivitaetszeitraum (erster Beitrag bis letzte Aktivitaet)",
        "description": (
            "Zeitraum zwischen dem ersten nachweisbaren Foreneintrag und der "
            "letzten protokollierten Aktivitaet des Kontos."
        ),
        # Hat der Nutzer KEINEN Beitrag verfasst, ist MIN(posted) NULL. Dann
        # liefert die Query den Leerstring — der Platzhalter faellt auf seinen
        # Default zurueck. Das ist gewollt: ein Konto ohne Beitrag hat keinen
        # belegbaren Aktivitaetszeitraum, und ein erfundener waere schlimmer
        # als 'unbekannt'.
        "sql_query": (
            # Build 528 (KORREKTUR): 'posted' -> 'posted_ts'. Die Spalte
            # 'posted' existiert in den echten forensic_<uid>.db NICHT; das DDL
            # (forensic_uid.db.schema.sql, uebergeben 2026-07-25) fuehrt
            # 'posted_ts'. Bis Build 527 schlug diese Query in PROD IMMER fehl,
            # der Platzhalter blieb also unaufgeloest und fiel auf seinen
            # Default 'unbekannt' — ohne dass jemand den Grund erfuhr.
            "SELECT CASE WHEN (SELECT MIN(posted_ts) FROM uid_posts) IS NULL "
            "THEN '' ELSE "
            "strftime('%d.%m.%Y', datetime((SELECT MIN(posted_ts) FROM uid_posts), 'unixepoch')) "
            "|| ' bis ' || "
            "strftime('%d.%m.%Y', datetime((SELECT last_active FROM uid_profile "
            "WHERE id = :uid), 'unixepoch')) END"
        ),
        "tags": "aktivitaet,zeitraum,spurenvermerk",
        "return_type": "scalar",
    },
    {
        "id": "user.pm_conversations",
        "title": "Anzahl Nachrichtenkonversationen",
        "description": (
            "Anzahl der Privatnachrichten-GESPRAECHE (Topics), an denen der "
            "Nutzer als Starter oder Empfaenger beteiligt war. Nicht zu "
            "verwechseln mit der Anzahl einzelner Nachrichten "
            "(user.pn_total) oder der Anzahl der Gespraechspartner "
            "(user.pn_partners)."
        ),
        "sql_query": (
            "SELECT val_computed FROM uid_stats WHERE stat_key = 'pm_topics_total'"
        ),
        "tags": "kommunikation,pn,statistik,spurenvermerk",
        "return_type": "scalar",
    },
    {
        "id": "user.shares_total",
        "title": "Anzahl Verbreitungshandlungen",
        "description": (
            "Anzahl der Verbreitungshandlungen des Nutzers (Eintraege in der "
            "Tabelle 'content', verknuepft ueber seine Beitraege). Quelle: "
            "uid_stats.shares_total."
        ),
        "sql_query": (
            "SELECT val_computed FROM uid_stats WHERE stat_key = 'shares_total'"
        ),
        "tags": "verbreitung,shares,statistik,strafrecht,spurenvermerk",
        "return_type": "scalar",
    },
]

# =============================================================================
# 3) Die Vorlage: Spurenvermerk (Nutzer nicht identifiziert)
# =============================================================================
# Aufbau (7 Bloecke). Die Staatsanwaltschaft verlangt einen knappen Vermerk von
# hoechstens einer DIN-A4-Seite — die Vorlage ist entsprechend kurz gehalten.
#
# Platzhalter-Typen:
#   {{a:...}}  automatisch aus forensic_<uid>.db
#   {{m:...}}  PFLICHT  -- Spurennummer (mit Formatregel 'rule:spurennummer')
#   {{o:...}}  optional -- Felder, die wir NICHT belegen koennen
#
# Warum Logins und Passwort NICHT automatisch sind:
#   uid_surveillance.login_success ist vielfach NULL; die Stats
#   'surveillance_success'/'surveillance_failed' wurden im Prepper (Build 006)
#   deshalb ENTFERNT. Eine automatisch erzeugte Login-Zahl waere also eine
#   Zahl ohne Beleg. Beide Felder sind Freitext mit Default 'unbekannt' — der
#   Ermittler traegt nur ein, was er im Einzelfall belegen kann.
#   Beleg: phase_b_exporter.py (Kommentar zu Build 006), Entwicklerfestlegung
#          2026-07-12.
# =============================================================================

_SPURENNUMMER_PH = (
    "{{m:spurennummer||Spurennummer aus der Vorgangsverwaltung"
    "|rule:spurennummer}}"
)

_TEMPLATE_BLOCKS = [
    {
        "block_type": "header",
        "block_data": {
            "text": "Spurenvermerk zur Spurennummer " + _SPURENNUMMER_PH,
            "level": 2,
        },
    },
    {
        "block_type": "paragraph",
        "block_data": {
            "text": (
                "Untersuchter Forennutzer: <b>{{a:user.username}}</b> "
                "(Benutzer-ID: {{a:user.id}})"
            ),
        },
    },
    {
        "block_type": "header",
        "block_data": {"text": "1. Identifizierung des Nutzers", "level": 3},
    },
    {
        "block_type": "paragraph",
        "block_data": {"text": "Identifizierung erfolgt: <b>nein</b>"},
    },
    {
        "block_type": "header",
        "block_data": {
            "text": "2. Feststellungen zum Nutzer {{a:user.username}}",
            "level": 3,
        },
    },
    {
        # Editor.js-Table-Block. withHeadings=false: die linke Spalte ist die
        # Bezeichnung, die rechte der Wert — eine Kopfzeile waere sinnlos.
        "block_type": "table",
        "block_data": {
            "withHeadings": False,
            "content": [
                ["Registrierungsdatum",
                 "{{a:user.registered_datetime|unbekannt}}"],
                ["Aktivitaetszeitraum",
                 "{{a:user.activity_range|unbekannt}}"],
                ["Anzahl erfolgreicher Logins",
                 "{{o:logins_erfolgreich|unbekannt|Anzahl erfolgreicher "
                 "Anmeldungen, sofern im Einzelfall belegbar}}"],
                ["Genutztes Passwort",
                 "{{o:passwort|unbekannt|Im Klartext bekanntes Passwort, "
                 "sofern im Einzelfall belegbar}}"],
                ["Anzahl Beitraege",
                 "{{a:user.posts_total|0}}"],
                ["Anzahl Nachrichtenkonversationen",
                 "{{a:user.pm_conversations|0}}"],
                ["Anzahl Verbreitungshandlungen",
                 "{{a:user.shares_total|0}}"],
                ["Weitere bekannte Accounts",
                 "{{a:user.aliases|keine bekannt}}"],
                ["Benutzername in weiteren Foren",
                 "{{o:username_andere_foren|unbekannt|Benutzername des "
                 "Nutzers auf anderen Plattformen, sofern ermittelt}}"],
            ],
        },
    },
    {
        "block_type": "paragraph",
        "block_data": {
            "text": (
                "Die zu dem Nutzer vorhandenen Inhalte wurden vollst\u00e4ndig "
                "ausgewertet. Zudem wurden Recherchen im Clearweb sowie in "
                "polizeilichen Auskunftssystemen durchgef\u00fchrt. Hierbei "
                "konnten keine Erkenntnisse festgestellt werden, die zur "
                "Identifizierung des Nutzers beitragen k\u00f6nnten."
            ),
        },
    },
]

_TEMPLATE_TITLE = "Spurenvermerk \u2013 Nutzer nicht identifiziert"
_TEMPLATE_DESCRIPTION = (
    "Vollst\u00e4ndiger, standardisierter Kurzvermerk (max. eine DIN-A4-Seite) "
    "f\u00fcr F\u00e4lle, in denen der Forennutzer durch die Auswertung NICHT "
    "identifiziert werden konnte. Die Feststellungen werden automatisch "
    "bef\u00fcllt; verpflichtend einzutragen ist allein die Spurennummer."
)


# =============================================================================
# Migration
# =============================================================================

def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def apply_migration(con: sqlite3.Connection, dry_run: bool = False) -> dict:
    """
    Wendet die Migration idempotent auf eine offene templates.db-Verbindung an.

    Returns:
        Bericht ueber die durchgefuehrten Schritte (fuer die Ausgabe).
    """
    report: dict = {
        "table_created":    False,
        "queries_added":    [],
        "queries_skipped":  [],
        "template_added":   False,
        "template_skipped": False,
    }
    now = int(time.time())
    actor = "migrate_templates_full_templates"

    # --- 1) Tabelle -------------------------------------------------------
    if not _table_exists(con, "report_templates"):
        report["table_created"] = True
        if not dry_run:
            con.execute(_DDL_REPORT_TEMPLATES)
            con.execute(_DDL_REPORT_TEMPLATES_IDX)
            con.execute(_DDL_REPORT_TEMPLATES_ACTIVE_IDX)
    else:
        # Indizes trotzdem sicherstellen (aeltere Teil-Anwendung).
        if not dry_run:
            con.execute(_DDL_REPORT_TEMPLATES_IDX)
            con.execute(_DDL_REPORT_TEMPLATES_ACTIVE_IDX)

    # --- 2) Queries -------------------------------------------------------
    # Build 489 (Platzhalter-Neuordnung): Ziel ist die einheitliche Tabelle
    # 'placeholders' (Typ 'a'). REIHENFOLGE der Standalone-Migrationen:
    # migrate_templates_placeholders ZUERST — dieses Skript bricht sonst mit
    # klarer Ansage ab (kein stilles Seeden in eine Alt-Tabelle).
    if not _table_exists(con, "placeholders"):
        raise SystemExit(
            "[migrate-full-templates] Tabelle 'placeholders' fehlt — bitte "
            "zuerst 'python -m management.migrate_templates_placeholders' "
            "ausfuehren (Build 489).")
    for q in _NEW_QUERIES:
        exists = con.execute(
            "SELECT 1 FROM placeholders WHERE id = ?", (q["id"],)
        ).fetchone()
        if exists:
            # GRUNDREGEL 1: NICHT ueberschreiben. Eine bereits vorhandene Query
            # koennte im Betrieb angepasst worden sein; ein stilles Ueberbuegeln
            # waere eine unbemerkte Aenderung der Beweisgrundlage.
            report["queries_skipped"].append(q["id"])
            continue
        report["queries_added"].append(q["id"])
        if dry_run:
            continue
        con.execute(
            "INSERT INTO placeholders "
            "(id, title, description, type, sql_query, tags, return_type, "
            " is_active, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, 'a', ?, ?, ?, 1, ?, ?, ?)",
            (q["id"], q["title"], q["description"], q["sql_query"],
             q["tags"], q["return_type"], actor, now, now),
        )
        con.execute(
            "INSERT INTO templates_audit_log "
            "(action, target_id, target_type, changed_by, changed_at, "
            " old_value, new_value) "
            "VALUES ('add_query', ?, 'query', ?, ?, NULL, ?)",
            (q["id"], actor, now, json.dumps(q, ensure_ascii=True)),
        )

    # --- 3) Vorlage -------------------------------------------------------
    tpl_exists = False
    if _table_exists(con, "report_templates"):
        tpl_exists = con.execute(
            "SELECT 1 FROM report_templates WHERE template_key = ?",
            (TEMPLATE_KEY,),
        ).fetchone() is not None

    if tpl_exists:
        report["template_skipped"] = True
    else:
        report["template_added"] = True
        if not dry_run:
            blocks_json = json.dumps(_TEMPLATE_BLOCKS, ensure_ascii=False)
            con.execute(
                "INSERT INTO report_templates "
                "(template_key, title, description, report_type, blocks_json, "
                " sort_order, is_active, created_by, created_at, updated_at) "
                "VALUES (?, ?, ?, 'final', ?, 10, 1, ?, ?, ?)",
                (TEMPLATE_KEY, _TEMPLATE_TITLE, _TEMPLATE_DESCRIPTION,
                 blocks_json, actor, now, now),
            )
            # Belegpflicht: die Aufnahme einer Vorlage ist eine Aenderung an
            # der Berichtsgrundlage und gehoert ins Audit-Log.
            con.execute(
                "INSERT INTO templates_audit_log "
                "(action, target_id, target_type, changed_by, changed_at, "
                " old_value, new_value) "
                "VALUES ('add_template', ?, 'module', ?, ?, NULL, ?)",
                (TEMPLATE_KEY, actor, now,
                 json.dumps({"template_key": TEMPLATE_KEY,
                             "title": _TEMPLATE_TITLE,
                             "report_type": "final",
                             "block_count": len(_TEMPLATE_BLOCKS)},
                            ensure_ascii=True)),
            )

    if not dry_run:
        con.commit()
    return report


def _resolve_db_path(args) -> str:
    """
    Die Vorlagen-Datenbank: Argument --templates-db > paths.templates_db > Abbruch.

    BUILD 646 - UMGESTELLT, UND DIE BEGRUENDUNG DAFUER GEHOERT HIERHER.
    Bis Build 645 las diese Funktion die config.yaml UNMITTELBAR mit
    'yaml.safe_load', am ConfigLoader vorbei. Der Kommentar nannte als Grund,
    das Skript ohne den Paket-Import lauffaehig zu halten.

    DIESER GRUND TRAEGT NICHT MEHR: Seit dem Rollout des Epilogs (Build 624)
    importiert diese Datei ohnehin 'management.help.cli_epilog' - sie laeuft
    also schon lange nicht mehr ohne das Paket. Die Sonderbehandlung war
    damit eine Abweichung ohne Nutzen, aber mit Preis: zwei Wege, dieselbe
    Frage zu beantworten.

    WAS SICH NICHT AENDERT - und das war die Sorge bei dieser Umstellung:
    Der Abbruch bei fehlendem Eintrag BLEIBT. Die Coded Defaults des
    ConfigLoaders greifen hier NICHT durch, weil die Aufloesung ueber
    'stammt_aus_datei' geht und nicht ueber 'get': Es zaehlt nur, was in der
    DATEI steht. Ein Werkzeug, das den Bestand veraendert, darf nicht
    stillschweigend auf './data/...' ausweichen.

    WAS BESSER WIRD: Eine fehlende config.yaml fuehrte bisher zu einem
    FileNotFoundError mitsamt Rueckverfolgung; jetzt ist es ein Abbruch mit
    Klartext, der beide Wege nennt.
    """
    return werkzeug_konfig.db_pfad(
        "migrate_templates_full_templates", args, arg_attribut="templates_db", arg_name="--templates-db",
        config_schluessel="paths.templates_db", name="templates_db")

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build 388: report_templates + Spurenvermerk-Vorlage seeden.",
        epilog=cli_epilog.epilog("migrate_templates_full_templates"),
        formatter_class=cli_epilog.HilfeFormat,
    )
    parser.add_argument("--templates-db", default=None,
                        help="Pfad zur templates.db")
    parser.add_argument("--config", default="./config.yaml",
                        help="config.yaml (wenn --templates-db fehlt)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Nur anzeigen, was getan wuerde.")
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args)
    if not os.path.exists(db_path):
        print("FEHLER: templates.db nicht gefunden: %s" % db_path, file=sys.stderr)
        return 2

    print("templates.db: %s%s" % (db_path, "  [DRY-RUN]" if args.dry_run else ""))
    con = sqlite3.connect(db_path)
    try:
        rep = apply_migration(con, dry_run=args.dry_run)
    finally:
        con.close()

    print("  Tabelle report_templates angelegt : %s"
          % ("ja" if rep["table_created"] else "nein (bestand bereits)"))
    print("  Queries neu aufgenommen           : %s"
          % (", ".join(rep["queries_added"]) or "keine"))
    print("  Queries uebersprungen (vorhanden) : %s"
          % (", ".join(rep["queries_skipped"]) or "keine"))
    print("  Vorlage '%s': %s" % (
        TEMPLATE_KEY,
        "aufgenommen" if rep["template_added"] else "bestand bereits (unveraendert)",
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
