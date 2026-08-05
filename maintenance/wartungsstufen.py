# =============================================================================
# maintenance/wartungsstufen.py
# IT-Forensisches Ermittlungswerkzeug - Wartungsvorbehalt
# =============================================================================
# Zweck:
#   DIE EINSTUFUNG ALLER SCHREIBENDEN WERKZEUGE - an EINER Stelle, mit einem
#   Grund je Werkzeug.
#
#   Vorgang: da6c16d0-ef1e-4052-8eb1-526c647de613
#   Grundlage: 'Vermerk_Wartungsvorbehalt_Analyse_K1_K8_v1_0.md' (Einstufung
#   der ersten sieben, von mc bestaetigt am 2026-07-31) und
#   'Nachpruefung_Wartungsvorbehalt_Vollstaendigkeit_v1_0.md' (die uebrigen
#   28, Alex 2026-08-05).
#
# =============================================================================
# WARUM DIESE LISTE UMGEZOGEN IST - und was daran wichtig ist
# =============================================================================
#   Bis hierher stand sie in tests/test_wartungsvorbehalt_einbau.py, mit der
#   ausdruecklichen Begruendung: "Sie steht hier und nirgends sonst, damit sie
#   EINE Fassung hat." Diese Begruendung bleibt richtig - die eine Fassung
#   wandert nur an einen Ort, an den mehr als ein Abnehmer greifen kann.
#
#   DER GRUND FUER DEN UMZUG: Ab jetzt wird die Liste von zweierlei gebraucht -
#   vom Einbautest (ruft jedes Stufe-A-Werkzeug den Vorbehalt?) UND vom
#   Vollstaendigkeitstest (ist jedes schreibende Werkzeug ueberhaupt
#   eingestuft?). Eine Liste, die in einer Testdatei wohnt, ist fuer den
#   zweiten Abnehmer nicht erreichbar, ohne dass ein Test einen anderen Test
#   importiert. Betriebswissen gehoert nicht in eine Testdatei.
#
# =============================================================================
# DIE DREI STUFEN
# =============================================================================
#   A  BRAUCHT EIN WARTUNGSFENSTER. Das Werkzeug ruft
#      maintenance.wartungsvorbehalt.wartungsvorbehalt() vor seinem scharfen
#      Lauf und gibt bei Verweigerung 3 zurueck, ohne etwas anzufassen.
#
#      TRAGENDE GRUENDE (einer genuegt):
#        * Tabellenumbau (Rebuild: CREATE -> INSERT...SELECT -> DROP/RENAME)
#        * Dateitausch oder -loeschung (os.replace / unlink / copy auf .db)
#        * ABSICHTLICHES UMSTELLEN des Journal- oder Sperrmodus
#        * Schreiben auf eine Beweismitteldatenbank
#          (evidence_/forensic_/assets_<uid>.db)
#        * eine Transaktion ueber den ganzen Lauf ohne Rueckspielweg
#
#   B  BETRIEBSVERTRAEGLICH MIT BENENNBARER EINSCHRAENKUNG. Kein Zwang, aber
#      der Vorbehalt steht im Dateikopf UND im Katalog. Typisch: es schreibt
#      nur ein Hilfsmittel, oder das Ergebnis kann unvollstaendig sein, oder
#      es schreibt an der auditierten Route vorbei.
#
#   C  OHNE EINSCHRAENKUNG. Rein lesend, oder es schreibt Nutzdaten ueber die
#      regulaere auditierte Route - so wie der Auswertungsdienst es auch tut.
#
# =============================================================================
# DAS KRITERIUM 'JOURNALMODUS' IST GESCHAERFT (Alex, 2026-08-05)
# =============================================================================
#   Es hiess bis hierher "aendert Dateikopf-Eigenschaften (journal_mode)".
#   WOERTLICH GENOMMEN waeren damit sieben weitere Werkzeuge Stufe A -
#   capacity_admin, case_events_admin, cases_admin, person_admin, rbac_admin,
#   backup_admin und setup_coordinator_dev rufen alle apply_journal_mode.
#
#   DAS IST NICHT GEMEINT, und der Grund ist nachlesbar: Es ist derselbe
#   Aufruf mit denselben Vorgabewerten, den der Auswertungsdienst beim Start
#   selbst faehrt (db/connection_manager.py Z. 218), und seit dem WAL-Verbot
#   (Build 499) laeuft 'auto' fest auf den Rollback-Rueckfall
#   (db/journal_policy.py Z. 337). Der Modus wird BESTAETIGT, nicht geaendert.
#
#   WARUM DAS MEHR IST ALS WORTKLAUBEREI: Der Kopf des Bauteils begruendet
#   selbst, warum ein zu weiter Vorbehalt schadet - "wer oft ohne Anlass
#   gefragt wird, tippt das Wort irgendwann, ohne zu lesen. Dann ist die
#   Sicherung genau dort wirkungslos, wo sie gebraucht wird." Sieben
#   Abfragen ohne Anlass waeren genau dieser Fall.
#
#   STUFE A GILT DESHALB NUR BEI ABSICHTLICHEM UMSTELLEN - also wenn ein
#   Werkzeug den Modus auf etwas ANDERES setzt als die geltende Vorschrift
#   (tools/convert_journal_mode.py), oder locking_mode=EXCLUSIVE nimmt.
#
# =============================================================================
# WER HIER FEHLT, MACHT DIE SUITE ROT
# =============================================================================
#   tests/test_wartungsstufen_vollstaendig.py haelt diese drei Listen gegen
#   den CLI-Katalog: JEDES Werkzeug, das dort als 'schreibend' oder
#   'gemischt' gefuehrt wird, muss in GENAU EINER Liste stehen.
#
#   DAS IST DER EIGENTLICHE GEWINN DIESES BAUTEILS. Bis hierher deckte die
#   Einstufung 7 von 35 schreibenden Werkzeugen, und niemand konnte das
#   sehen. management/migrate_templates_blocktyp.py (Build 655) ist NACH der
#   Analyse und NACH dem Einbau entstanden, fasst templates.db per ALTER an
#   und war nie eingestuft - aufgefallen ist es elf Builds spaeter bei einer
#   Nachpruefung. Mit diesem Waechter waere es beim Bau aufgefallen.
#
# Version: v0.8.686 - Build: 686 - 2026-08-05
# =============================================================================

from __future__ import annotations

from typing import Dict, Tuple

#: Die Stufenbezeichner. Als Zeichenketten und nicht als Zahlen: sie stehen
#: so auch in den Dateikoepfen und im Katalog, und drei Schreibweisen
#: derselben Sache laufen erfahrungsgemaess auseinander.
STUFE_A = "A"
STUFE_B = "B"
STUFE_C = "C"
STUFEN: Tuple[str, ...] = (STUFE_A, STUFE_B, STUFE_C)


# -----------------------------------------------------------------------------
# STUFE A - braucht ein Wartungsfenster und setzt es selbst durch
# -----------------------------------------------------------------------------
# Der Wert ist der TRAGENDE GRUND, nicht eine Beschreibung des Werkzeugs. Er
# steht so auch in der Meldung, wenn der Einbautest anschlaegt - wer ihn liest,
# soll ohne Rueckfrage wissen, warum hier nicht nachgegeben werden darf.

WERKZEUGE_A: Dict[str, str] = {
    "management/migrate.py":
        "coordinator.db, Tabellenumbau ohne Backup",
    "tools/migrate-dbs.py":
        "templates.db, evidence_<uid>.db, assets_<uid>.db",
    "management/migration_fleet/migration_fleet_admin.py":
        "companion --confirm; der Rueckweg kopiert ueber das Original",
    "management/consolidate_default_db.py":
        "--overwrite loescht die Ziel-Datei vor der Transaktion",
    "tools/forensic_index_upgrade.py":
        "--ausfuehren schreibt in die versiegelte forensic_<uid>.db",
    # BUILD 615 - Nachtrag, angestossen von mc am 2026-07-31.
    "tools/convert_journal_mode.py":
        "--apply aendert den Dateikopf (Journalstempel), nimmt "
        "locking_mode=EXCLUSIVE und hebt dafuer den Schreibschutz auf",

    # ------------------------------------------------------------------
    # BUILD 686 - DREI NACHTRAEGE aus der Vollstaendigkeitspruefung.
    #
    # Alle drei erfuellen die Stufe-A-Gruende und riefen den Vorbehalt
    # nicht. Bei den ersten beiden ist das nur beim DIREKTAUFRUF offen -
    # ueber 'migrate-dbs --apply' laufen sie hinter dem Vorbehalt
    # (migrate-dbs.py Z. 155-162, 273-299, 531). Ihre eigenen Dateikoepfe
    # fordern den Direktaufruf aber ausdruecklich ("standalone
    # auszufuehren"), und eine Sicherung, die nur auf einem von zwei Wegen
    # greift, ist keine.
    # ------------------------------------------------------------------
    "management/migrate_templates_placeholders.py":
        "DROP TABLE placeholder_queries (Z. 235) und zwei vollstaendige "
        "Rebuilds in EINER Transaktion (Z. 211-249); setzt dabei "
        "journal_mode=delete (Z. 183). Die Nachpruefungen laufen erst NACH "
        "dem COMMIT",
    "management/migrate_templates_audit_check.py":
        "DROP TABLE templates_audit_log + RENAME (Z. 95-98) OHNE Backup und "
        "ohne Trockenlauf; setzt journal_mode=delete (Z. 88)",
    "management/repair_block_types.py":
        "--apply schreibt in evidence_<uid>.db - eine Ermittler-"
        "Ergebnisdatenbank. Die vorhandene Sperre --ja-backup-vorhanden "
        "FRAGT den Bediener, MISST aber nicht, ob ein Dienst die Datei "
        "gerade haelt",
}


# -----------------------------------------------------------------------------
# STUFE B - betriebsvertraeglich, aber mit benennbarer Einschraenkung
# -----------------------------------------------------------------------------
# Der Wert ist die EINSCHRAENKUNG. Sie gehoert in den Dateikopf und in den
# Katalog - ein Werkzeug, dessen Grenze nur hier steht, hat sie nicht.

WERKZEUGE_B: Dict[str, str] = {
    "management/search/index_cli.py":
        "Stufe B - schreibt ausschliesslich in search_index.db, die kein "
        "anderer Dienst offen haelt. ABER: eine gerade beschriebene "
        "evidence-Datei kann es nicht lesen; dann bleibt dieser Fall "
        "unvollstaendig und der Lauf endet mit 2",
    "management/backup/backup_admin.py":
        "'run' konkurriert unter dem Rollback-Journal mit den Schreibern, "
        "und der Sicherungssatz ist nicht punktgleich (Kennzeichnung statt "
        "Wartungsfenster, Entscheidung mc 2026-07-31). 'restore' legt nur "
        "eine Datei NEBEN das Original (Build 680)",
    "management/distribution/lkae_admin.py":
        "schreibt allein in ein frisches --target-Verzeichnis; der Schutz "
        "gegen ein produktives Ziel ist ausdruecklich 'best effort' und "
        "faellt bei unlesbarer config.yaml auf zwei Standardpfade zurueck",
    "setup_coordinator_dev.py":
        "schreibt coordinator.db mit eigenem SQL an der auditierten Route "
        "vorbei (kein CoordinatorWriter, kein Auditbeleg) und hat keine "
        "Sperre dagegen, auf eine produktive Datei gerichtet zu werden",
    "tools/poc_m019_weg_a.py":
        "benennt neun Spalten einer coordinator.db um (ALTER TABLE RENAME "
        "COLUMN, eine Transaktion ueber den ganzen Lauf). Es soll auf einer "
        "WEGWERFKOPIE laufen - dafuer sorgt seit Build 686 eine Sperrliste "
        "gegen paths.coordinator_db, NICHT der Wartungsvorbehalt: ein "
        "Fenster fuer eine Wegwerfkopie zu verlangen waere Reibung ohne "
        "Schutzgewinn (Entscheidung Alex, 2026-08-05)",

    # --- Die vier additiven Templates-Schritte -------------------------
    # Sie aendern das SCHEMA einer Datenbank, die der Dienst offen haelt -
    # aber nur ADDITIV: ADD COLUMN, CREATE ... IF NOT EXISTS, ein Seed.
    # Keine Bestandszeile wird angefasst, nichts wird gedroppt. Der
    # schlimmste Teilzustand nach einem Abbruch ist "Spalte da, Seed
    # fehlt", und den loest der naechste Lauf auf (alle vier sind
    # idempotent). Die benennbare Einschraenkung ist der ALTER selbst: er
    # braucht eine Schreibsperre, und haelt der Dienst sie, scheitert der
    # Lauf - ohne Schaden, aber er scheitert.
    "management/migrate_templates_full_templates.py":
        "legt eine NEUE Tabelle an und fuegt Zeilen ein; fasst nichts "
        "Bestehendes an. Hat als einziges der sechs einen echten --dry-run",
    "management/migrate_templates_blocktyp.py":
        "ADD COLUMN mit Backup (.pre655.bak); fasst nachweislich keine "
        "Bestandszeile an (block_data bleibt NULL)",
    "management/migrate_templates_ci.py":
        "ADD COLUMN ... DEFAULT 0 mit Backup (.pre497.bak); bestehende "
        "Zeilen erhalten den Vorgabewert, kein Beleg aendert sich",
    "management/migrate_templates_module_key.py":
        "ADD COLUMN + Index IF NOT EXISTS + ein Seed-INSERT. KEIN Backup im "
        "Code - die Sicherung steht nur als Satz im Dateikopf",
}


# -----------------------------------------------------------------------------
# STUFE C - ohne Einschraenkung
# -----------------------------------------------------------------------------
# Der Wert ist der Grund, aus dem hier NICHTS zu tun ist. Auch das ist eine
# Feststellung und keine Leerstelle: 'nicht eingestuft' und 'geprueft und fuer
# unbedenklich befunden' duerfen nicht gleich aussehen (Grundregel 1).

WERKZEUGE_C: Dict[str, str] = {
    # --- Der Dienst selbst --------------------------------------------
    # AUSDRUECKLICH EINE DEFINITIONSAUSNAHME UND KEIN BEFUND: Nach dem
    # Wortlaut waere main.py Stufe A - es schreibt evidence_<uid>.db,
    # faehrt ALTER TABLE ADD COLUMN (db/evidence_db.py Z. 678) und
    # stempelt den Journalmodus. Es ist aber genau der Dienst, gegen den
    # Stufe C definiert ist; ein Wartungsvorbehalt darin verboete den
    # Normalbetrieb.
    "main.py":
        "der Auswertungsdienst selbst - die Route, gegen die Stufe C "
        "definiert ist (Definitionsausnahme, kein Befund)",

    # --- Einrichtung, laeuft nicht im Betrieb --------------------------
    "install.py":
        "Einrichtung vor der Inbetriebnahme; oeffnet keine Datenbank, "
        "schreibt nur ins Dateisystem",
    "prepare_deployment.py":
        "laeuft auf einem Rechner MIT Internetzugang, nicht auf der Anlage; "
        "schreibt nur unter setup/",

    # --- Die Wartungswerkzeuge selbst ----------------------------------
    # Ein Wartungsvorbehalt darin waere zirkulaer.
    "tools/maintenance.py":
        "schreibt keine Datenbank, nur die Steuerdateien unter "
        "_maintenance/. FUSSNOTE: die Sperrprobe von 'enter' oeffnet die "
        "Ziel-Datenbank schreibfaehig (cli_support.py Z. 184-186), ueber "
        "'--ziel evidence:1488' auch ein Beweismittel - ob dabei der in "
        "Build 680 beschriebene Journal-Rueckrollvorgang eintreten kann, "
        "ist NICHT nachgemessen",
    "tools/maintenance_kill.py":
        "schreibt keine Datenbank, nur die Anmelde-Steuerdateien; ein "
        "regulaerer Dienst ist ueber diesen Weg nicht erreichbar "
        "(Vermerk K1-K8, Abschnitt 4)",

    # --- Nutzdaten ueber die regulaere auditierte Route -----------------
    # Alle folgenden schreiben coordinator.db ueber CoordinatorWriter /
    # audited_write - dieselbe Route, die der Auswertungsdienst benutzt.
    "management/ad_sync/ad_sync_admin.py":
        "coordinator.db ueber CoordinatorWriter (auditiert)",
    "management/capacity/capacity_admin.py":
        "coordinator.db ueber CoordinatorWriter (auditiert)",
    "management/case_events/case_events_admin.py":
        "coordinator.db ueber CoordinatorWriter (auditiert)",
    "management/cases/cases_admin.py":
        "coordinator.db ueber CoordinatorWriter (auditiert)",
    "management/external/case_release_admin.py":
        "coordinator.db ueber CoordinatorWriter (auditiert)",
    "management/external/external_admin.py":
        "coordinator.db ueber CoordinatorWriter (auditiert)",
    "management/onboarding/onboarding_admin.py":
        "coordinator.db ueber CoordinatorWriter (auditiert)",
    "management/ops/promotion_admin.py":
        "coordinator.db ueber CoordinatorWriter (auditiert)",
    "management/person/person_admin.py":
        "coordinator.db ueber CoordinatorWriter (auditiert)",
    "management/rbac/rbac_admin.py":
        "coordinator.db ueber CoordinatorWriter (auditiert)",
    "management/results/catalog_admin.py":
        "coordinator.db ueber CoordinatorWriter (auditiert)",
    "management/results/results_admin.py":
        "coordinator.db ueber CoordinatorWriter (auditiert)",
}


#: Alle Einstufungen in einer Abbildung - Pfad -> (Stufe, Grund).
#: Sie wird GEBILDET und nicht gepflegt: eine vierte Liste waere eine vierte
#: Gelegenheit, sie auseinanderlaufen zu lassen.
ALLE: Dict[str, Tuple[str, str]] = {}
for _pfad, _grund in WERKZEUGE_A.items():
    ALLE[_pfad] = (STUFE_A, _grund)
for _pfad, _grund in WERKZEUGE_B.items():
    ALLE[_pfad] = (STUFE_B, _grund)
for _pfad, _grund in WERKZEUGE_C.items():
    ALLE[_pfad] = (STUFE_C, _grund)
del _pfad, _grund


def stufe(pfad: str) -> str:
    """
    Die Stufe eines Werkzeugs - oder "" fuer 'nicht eingestuft'.

    DIE LEERE ZEICHENKETTE IST EINE ANTWORT UND KEIN FEHLER: Sie sagt, dass
    dieses Werkzeug nie beurteilt wurde. Das ist etwas anderes als Stufe C
    ('geprueft und unbedenklich') und muss auch anders aussehen - sonst
    verschwindet ein neu gebautes Werkzeug lautlos in der harmlosesten
    Schublade.
    """
    eintrag = ALLE.get(str(pfad))
    return eintrag[0] if eintrag else ""


def grund(pfad: str) -> str:
    """Der tragende Grund der Einstufung - oder "" fuer 'nicht eingestuft'."""
    eintrag = ALLE.get(str(pfad))
    return eintrag[1] if eintrag else ""


def ist_stufe_a(pfad: str) -> bool:
    """Kurzform fuer den haeufigsten Fall."""
    return stufe(pfad) == STUFE_A
