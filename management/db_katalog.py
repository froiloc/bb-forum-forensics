# =============================================================================
# management/db_katalog.py
# IT-Forensisches Ermittlungswerkzeug — Anlagenpflege
# =============================================================================
# Zweck (Build 657):
#   DIE EINE STELLE, an der steht, WELCHE Datenbanken dieses Werkzeug benutzt
#   und WIE bei jeder einzelnen der Schemastand festgestellt wird.
#
# ── DER ANLASS ──────────────────────────────────────────────────────────────
#
#   2026-08-02: Die Sicht "Baustein-Module" antwortete mit HTTP 500 und
#   schwieg dazu. Ursache war die nicht angewandte Migration aus Build 655 -
#   die templates.db lag im Rueckstand. Der Serverstart hatte nichts gesagt,
#   weil er den Migrationsstand NUR der coordinator.db prueft.
#
#   Gemessen an jenem Tag: der Servercode liest ZEHN Datenbankpfade. Beim
#   Start geprueft wurde EINER. Das war kein Versehen an einer Stelle,
#   sondern eine fehlende Liste - und ohne Liste faellt eine Luecke erst auf,
#   wenn jemand davorsteht.
#
#   VORLAEUFER, und er macht die Sache aerger: tools/migrate-dbs.py wurde am
#   2026-07-30 aus GENAU DEMSELBEN Anlass gebaut ("auf der Anlage fehlten
#   zwei Migrationen der templates.db seit dem 21./22. Juli. Es gab keinen
#   Fehler, nur Stille ... Die Suche kostete einen halben Tag."). Das Werkzeug
#   war da, vollstaendig und richtig. Es rief nur niemand auf. Diese Datei
#   schliesst die Luecke zwischen "es gibt ein Werkzeug" und "jemand merkt,
#   dass er es braucht".
#
# ── WAS DIESER KATALOG IST UND WAS NICHT ────────────────────────────────────
#
#   ER IST EINE LISTE, KEIN PRUEFER. Er sagt je Datenbank, WO sie liegt, WIE
#   ihr Stand abzulesen ist, OB ein Rueckstand den Start verhindert und
#   WELCHER Befehl ihn behebt. Die Pruefung selbst steht in
#   management/db_startbefund.py (Projektregel 10: jede Klasse in eine eigene
#   Datei).
#
#   ER IST VOLLZAEHLIG, UND ZWAR NACHWEISLICH. Auch Datenbanken, an denen es
#   NICHTS zu pruefen gibt, stehen darin - mit dem Grund. Eine Liste, aus der
#   das Unproblematische weggelassen wird, ist von einer unvollstaendigen
#   Liste nicht zu unterscheiden. Ein Regressionstest (DK05) haelt alle im
#   Servercode benutzten Pfade gegen diesen Katalog; eine kuenftige Datenbank,
#   die niemand eintraegt, faellt damit sofort auf.
#
# ── DER SERVER HEILT NICHT ──────────────────────────────────────────────────
#
#   Festlegung mc vom 2026-07-10 (management/server/migration_status.py) und
#   erneut am 2026-07-30 (tools/migrate-dbs.py, Punkt 2): "Das Anwenden von
#   Migrationen bleibt eine bewusste, protokollierte Handlung. Der Server
#   WARNT nur."
#
#   Diese Datei haelt sich daran, und zwar aus drei Gruenden, die seit dem
#   01.07.2026 schwerer wiegen als vorher:
#     (1) Ein Serverstart ist UNBEAUFSICHTIGT. Ein Neustart um drei Uhr
#         nachts wuerde stillschweigend das Schema aendern.
#     (2) Er laeuft unter der Kennung dessen, der ihn startet - eine so
#         ausgeloeste Migration waere niemandem zugerechnet.
#     (3) evidence_<uid>.db und assets_<uid>.db stehen unter dem
#         Migrationsvorbehalt mit Vier-Phasen-Workflow (Datenmigrations-
#         leitfaden). Ein selbstheilender Server umginge ihn vollstaendig.
#
#   Der Befund NENNT deshalb den Befehl - und er nennt das WERKZEUG
#   (tools/migrate-dbs.py), nicht das Einzelskript. Das ist die Lehre aus dem
#   2026-08-02: die Migration lief damals gegen einen von Hand getippten
#   Pfad und traf die falsche Datei. Das Werkzeug holt den Pfad aus
#   config.yaml und kann ihn nicht verfehlen.
#
# Version: v0.8.657 · Build: 657 · 2026-08-02
# Beleg: Vorfall 2026-08-02 (Sicht Baustein-Module, HTTP 500 ohne Logzeile);
#        tools/migrate-dbs.py Kopf (Festlegungen mc 2026-07-30);
#        management/server/migration_status.py (Entscheidung mc 2026-07-10).
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


# --- Wie ist der Stand ablesbar? ---------------------------------------------
#: Register in der Datei (schema_migrations) - massgeblich fuer coordinator.db.
STAND_REGISTER = "register"
#: An Spuren abgelesen (eine Tabelle, eine Spalte, ein CHECK-Wortlaut).
STAND_SPUREN = "spuren"
#: Versiegeltes Beweismittel: Schemaversion und SHA-256, NIE migriert.
STAND_VERSIEGELT = "versiegelt"
#: Fremde Datei (Prepper). Genannt, aber nicht bewertet.
STAND_FREMD = "fremd"
#: Kein Schemastand vorhanden - die Datei legt ihre Tabellen selbst an.
STAND_OHNE = "ohne_schemastand"

#: Anlagendatenbank: EINE Datei, beim Start pruefbar.
ART_ANLAGE = "anlage"
#: Falldatenbank: eine Datei JE FALL. Beim Start nur zusammengefasst.
ART_FALL = "fall"


@dataclass(frozen=True)
class DbEintrag:
    """
    Ein Eintrag des Katalogs. REINES DATENOBJEKT, keine Pruefung.

    begruendung ist PFLICHT und darf nicht leer sein (DK02). Ein Eintrag ohne
    Begruendung waere eine Behauptung: der naechste Leser koennte nicht
    erkennen, ob 'nicht geprueft' eine Entscheidung war oder ein Versaeumnis -
    und genau dieser Unterschied hat am 2026-08-02 eine Stunde gekostet.
    """
    kennung: str
    name: str
    art: str
    stand: str
    #: Der config.yaml-Schluessel. None = die Datei hat keinen.
    config_schluessel: Optional[str]
    #: Vorgabewert, wenn config.yaml nichts sagt. None = kein Vorgabewert.
    vorgabe: Optional[str]
    #: Verhindert ein Rueckstand den Serverstart?
    blockierend: bool
    #: Der Befehl, der den Rueckstand behebt. None = es gibt nichts zu heilen.
    befehl: Optional[str]
    #: WARUM diese Einstufung. Pflicht.
    begruendung: str
    #: Welche Server benutzen sie? ('verwaltung', 'ermittler')
    server: Tuple[str, ...]


#: DAS WERKZEUG, auf das jeder Befund zeigt. An EINER Stelle, damit Meldung
#: und Dokumentation nicht auseinanderlaufen (Muster: MIGRATE_COMMAND in
#: management/server/migration_status.py).
WERKZEUG = "python3 tools/migrate-dbs.py"


DB_KATALOG: Tuple[DbEintrag, ...] = (
    DbEintrag(
        kennung="coordinator", name="coordinator.db",
        art=ART_ANLAGE, stand=STAND_REGISTER,
        config_schluessel="paths.coordinator_db",
        vorgabe="./data/coordinator.db",
        blockierend=False,
        befehl="python3 -m management.migrate --deployed-by <KENNUNG>",
        begruendung=(
            "Fuehrt seit jeher das Register schema_migrations und hat einen "
            "eigenen Einstiegspunkt, der zusaetzlich das Audit-Log bedient "
            "(deployed_by). Wird seit Build 376 beim Start geprueft - dieser "
            "Katalog uebernimmt jene Pruefung, er ersetzt sie nicht. "
            "NICHT blockierend nach Entscheidung mc 2026-07-10."),
        server=("verwaltung",),
    ),
    DbEintrag(
        kennung="templates", name="templates.db",
        art=ART_ANLAGE, stand=STAND_SPUREN,
        config_schluessel="paths.templates_db",
        vorgabe="./data/templates.db",
        blockierend=False,
        befehl=WERKZEUG + " --db templates --apply",
        begruendung=(
            "Hat KEIN Register; der Stand wird an Spuren abgelesen "
            "(management/templates_db_status.py). Sie traegt die "
            "Redaktionsarbeit - Bausteine, Vorlagen, Platzhalter -, aber "
            "keine Ermittlungsergebnisse; im Datenmigrationsleitfaden 6.0 "
            "als 'nur-lesend / reduzierte Zeremonie' gefuehrt. NICHT "
            "blockierend: betroffen sind die drei Redaktionssichten, nicht "
            "der Betrieb. DAS IST DIE DATENBANK DES VORFALLS VOM "
            "2026-08-02."),
        server=("verwaltung", "ermittler"),
    ),
    DbEintrag(
        kennung="evidence", name="evidence_<uid>.db",
        art=ART_FALL, stand=STAND_REGISTER,
        config_schluessel="paths.evidence_db_dir",
        vorgabe="./data/evidence/",
        blockierend=False,
        befehl=WERKZEUG + " --subject-id <uid> --apply",
        begruendung=(
            "Eine Datei JE FALL, mit Register und Spuren. Steht seit dem "
            "01.07.2026 unter dem Migrationsvorbehalt - eine Migration "
            "verlangt den Vier-Phasen-Workflow des Datenmigrations"
            "leitfadens. Beim Start wird deshalb nur ZUSAMMENGEFASST "
            "gemeldet, wie viele Falldatenbanken im Rueckstand sind; das "
            "Anwenden gehoert ausdruecklich nicht an den Start."),
        server=("verwaltung", "ermittler"),
    ),
    DbEintrag(
        kennung="assets", name="assets_<uid>.db",
        art=ART_FALL, stand=STAND_REGISTER,
        config_schluessel="paths.assets_db_dir",
        vorgabe="./data/assets/",
        blockierend=False,
        befehl=WERKZEUG + " --subject-id <uid> --apply",
        begruendung=(
            "Wie evidence_<uid>.db: eine Datei je Fall, Register vorhanden, "
            "seit dem 01.07.2026 unter Migrationsvorbehalt."),
        server=("verwaltung", "ermittler"),
    ),
    DbEintrag(
        kennung="forensic", name="forensic_<uid>.db",
        art=ART_FALL, stand=STAND_VERSIEGELT,
        config_schluessel="paths.forensic_db_dir",
        vorgabe="./data/forensic/",
        blockierend=True,
        befehl=None,
        begruendung=(
            "DAS VERSIEGELTE BEWEISMITTEL. Sie wird NIE migriert - "
            "tools/migrate-dbs.py laesst sie auch scharfgeschaltet "
            "unberuehrt ('Ein Werkzeug, das dort schreibt, veraendert "
            "Beweise. Das ist keine Vorsichtsmassnahme, sondern eine "
            "Grenze'). Geprueft werden Schemaversion und SHA-256, und ZWAR "
            "BLOCKIEREND: ein Betrieb mit veraenderter forensic_db ist nicht "
            "zulaessig (core/startup_checks.py). Es gibt deshalb auch keinen "
            "Heilbefehl - eine Abweichung ist kein Rueckstand, sondern ein "
            "Vorfall."),
        server=("ermittler",),
    ),
    DbEintrag(
        kennung="default", name="default.db",
        art=ART_ANLAGE, stand=STAND_FREMD,
        config_schluessel="paths.default_db",
        vorgabe="./data/default.db",
        blockierend=False,
        befehl=None,
        begruendung=(
            "Stammt aus dem Prepper. Festlegung mc 2026-07-30: GENANNT, aber "
            "nicht bewertet - eine noetige Migration gehoert in den Prepper, "
            "nicht hierher. Sie stillschweigend wegzulassen waere falsch, "
            "dann fragte sich jemand, warum sie fehlt."),
        server=("ermittler",),
    ),
    DbEintrag(
        kennung="translations", name="translations.db",
        art=ART_ANLAGE, stand=STAND_FREMD,
        config_schluessel="paths.translations_db",
        vorgabe="./data/translations.db",
        blockierend=False,
        befehl=None,
        begruendung="Wie default.db: aus dem Prepper, genannt, nicht bewertet.",
        server=("ermittler",),
    ),
    DbEintrag(
        kennung="search_index", name="Suchindex",
        art=ART_ANLAGE, stand=STAND_OHNE,
        config_schluessel="paths.search_index_db",
        vorgabe=None,
        blockierend=False,
        befehl=None,
        begruendung=(
            "Legt ihre Tabellen selbst an (CREATE TABLE IF NOT EXISTS, "
            "db/search_index_db.py) und fuehrt keinen Migrationsstand. Es "
            "gibt hier nichts zu pruefen - das steht hier ausdruecklich, "
            "damit niemand sie fuer vergessen haelt. BEFUND NEBENBEI: sie "
            "hat KEINEN Eintrag in config.yaml und laeuft auf einen "
            "Vorgabewert im Quelltext."),
        server=("verwaltung",),
    ),
    DbEintrag(
        kennung="approved_reports", name="Freigegebene Berichte",
        art=ART_ANLAGE, stand=STAND_OHNE,
        config_schluessel="paths.approved_reports_db",
        vorgabe=None,
        blockierend=False,
        befehl=None,
        begruendung=(
            "Legt ihre Tabellen selbst an (CREATE TABLE IF NOT EXISTS, "
            "management/reports/approved_reports_db.py), kein "
            "Migrationsstand. BEFUND NEBENBEI: ebenfalls ohne Eintrag in "
            "config.yaml."),
        server=("verwaltung",),
    ),
    DbEintrag(
        kennung="migration", name="migration.db (Flotte)",
        art=ART_ANLAGE, stand=STAND_OHNE,
        config_schluessel="paths.migration_db",
        vorgabe=None,
        blockierend=False,
        befehl=None,
        begruendung=(
            "Katalog/Inventar/Ledger der Flotten-Migration. AUF DIESER "
            "ANLAGE NICHT IN BETRIEB - tools/migrate-dbs.py haelt fest: 'der "
            "Verweis auf die Flotten-Schicht ist entfallen, sie ist auf "
            "dieser Anlage nicht in Betrieb, und migration.db existiert "
            "nicht.' Sie steht hier, weil migration_fleet_admin.py den "
            "Pfad liest; geprueft wird nichts."),
        server=(),
    ),
)


def eintrag(kennung: str) -> Optional[DbEintrag]:
    """Der Eintrag zu einer Kennung, oder None."""
    for e in DB_KATALOG:
        if e.kennung == kennung:
            return e
    return None


def nach_config_schluessel(schluessel: str) -> Optional[DbEintrag]:
    """Der Eintrag zu einem config.yaml-Schluessel, oder None (fuer DK05)."""
    for e in DB_KATALOG:
        if e.config_schluessel == schluessel:
            return e
    return None


def config_schluessel_alle() -> Tuple[str, ...]:
    """Alle im Katalog gefuehrten config.yaml-Schluessel."""
    return tuple(e.config_schluessel for e in DB_KATALOG
                 if e.config_schluessel)


def pruefbare(server: str) -> Tuple[DbEintrag, ...]:
    """
    Die Eintraege, die fuer EINEN Server tatsaechlich zu pruefen sind.

    Ausgenommen sind die, bei denen es nichts zu pruefen GIBT (fremde Dateien
    und solche ohne Schemastand) - nicht, weil sie unwichtig waeren, sondern
    weil eine Pruefung ohne Gegenstand nur Laerm erzeugt. Sie bleiben im
    Katalog und tragen ihren Grund.
    """
    return tuple(e for e in DB_KATALOG
                 if server in e.server
                 and e.stand in (STAND_REGISTER, STAND_SPUREN,
                                 STAND_VERSIEGELT))
