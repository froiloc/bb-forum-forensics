# =============================================================================
# management/migrations/coordinator/m038_caseoverview_rbac.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Rechtetrennung (Build 698)
# =============================================================================
# Zweck:
#   RBAC-Seed fuer die Falluebersicht:
#     caseoverview.view — die Falltabelle sehen (Sicht, Kachel, Fallsuche).
#   Zusaetzlich wird der TEXT von 'dashboard.view' berichtigt, weil dieses
#   Recht mit diesem Vorgang auf das Kachel-Dashboard verengt wird.
#
#   Vorgang: 60fe72fb-b0bb-4c29-9a80-3ac1996bba78
#   Muster M014/M021/M026/M028/M029/M030/M031 (reiner Capability-Seed). Die
#   Werte sind eine EINGEFRORENE Kopie des Katalogs
#   (management/rbac/catalog.py) — NIE importieren (m005-Prinzip: eine
#   angewandte Migration darf ihr Laufzeitverhalten nie aendern).
#
# ── WARUM EIN EIGENES RECHT ─────────────────────────────────────────────────
#
#   Bis Build 696 trug 'dashboard.view' ZWEI Dinge. Als das Dashboard AUS der
#   Falltabelle bestand, war das dasselbe Recht fuer dieselbe Sache. Seit dem
#   Umbau auf das Kachelsystem ist das Dashboard ein RAHMEN, dessen Inhalt
#   jede Kachel ueber ihr eigenes Recht mitbringt (siehe
#   management/viewprefs/viewpref_katalog.py: escalation.view, ops.view,
#   limitation.view ... je Kachel eines). Die Falltabelle war die einzige
#   Kachel ohne eigenes Recht — sie lief auf dem Recht des Rahmens mit.
#
#   Damit bekam jede Person, die den Ueberblick oeffnen darf, die
#   vollstaendige Fallliste mit Beschuldigten-Kontonamen ungefragt dazu. Das
#   ist eine Zweckbindungsfrage und keine Aufraeumarbeit — dieselbe
#   Begruendung, mit der M030 (retention.view) und M031 (limitation.view)
#   jeweils ein eigenes Recht bekommen haben statt 'dashboard.view'
#   mitzubenutzen.
#
# ── WARUM DER TEXT VON 'dashboard.view' MITGEAENDERT WIRD ───────────────────
#
#   M006 hat ihn als "Ampel-Dashboard sehen" / "Falluebersicht mit Ampel und
#   Kennzahlen lesen" eingefroren. Nach dieser Trennung beschreibt dieser Satz
#   GENAU DAS, was das Recht nicht mehr kann. Die RBAC-Matrix (Sicht
#   'policy.view') zeigt diese Texte woertlich an; wer dort Rechte vergibt,
#   entscheidet nach ihnen. Ein stehengelassener Text waere also keine
#   Kleinigkeit, sondern eine Falschangabe an der Stelle, an der ueber Zugang
#   entschieden wird.
#
#   GEAENDERT WIRD AUSSCHLIESSLICH BESCHRIFTUNG UND BESCHREIBUNG. Der Code
#   'dashboard.view' bleibt, alle Grants darauf bleiben unangetastet, kein
#   Zugang aendert sich durch diese Migration.
#
# ── BERICHTIGUNG BUILD 711 — DER WAECHTER WAR EIN SPERRRIEGEL ───────────────
#
#   Vorgang 9c4e17b2. Bis Build 710 endete diese Migration mit einer
#   ABSOLUTEN Zaehlung: 'traegt caseoverview.view irgendwelche Grants? dann
#   Abbruch'. Gemeint war etwas anderes — der Kommentar daneben sagte es
#   woertlich: 'haette DIESE MIGRATION versehentlich einen Grant erzeugt,
#   faende er sich hier'. Das ist eine DELTA-Frage (vorher gegen nachher) und
#   wurde als Bestandsfrage geschrieben.
#
#   WAS DAS ANRICHTETE (belegt am Bestand vom 13.08.2026): Wer den
#   Uebernahmelauf 'rbac_admin migrate-grants' VOR dieser Migration fuhr,
#   bekam einen ordentlich belegten Grant auf ein Recht, das im Katalog der
#   Datenbank noch fehlte — die Katalogpruefung in RbacRepo prueft gegen
#   catalog.py im Code, und die Fremdschluessel der coordinator.db greifen
#   bei foreign_keys=OFF nicht. Danach war der Bestand VERRIEGELT: die
#   Migration rollte zurueck, die Faehigkeit entstand nie, der Start-Check
#   des Managements verweigerte den Dienst mit genau der Faehigkeit, die
#   diese Migration angelegt haette.
#
#   UND DER SAUBERE RUECKWEG HALF NICHT. Gegenprobe gefahren: den Grant per
#   'revoke-grant' zurueckzunehmen (Soft-Revoke, append-only, der vorgesehene
#   Weg) aenderte nichts, weil die Zaehlung 'revoked_at' nicht filterte. Es
#   blieb allein ein hartes DELETE auf rbac_grant — also das Zerreissen der
#   Beleg-Kopplung, um eine Migration freizubekommen. Ein Waechter, der als
#   einzigen Ausweg den Bruch der Beweiskette laesst, schuetzt nichts.
#
#   SEIT BUILD 711 wird gemessen statt behauptet: Grants VOR dem Seed zaehlen,
#   nach dem Seed erneut, und nur ein ZUWACHS bricht ab. Vorgefundene Grants
#   sind nicht die Sache dieser Migration — sie tragen ihren eigenen Beleg in
#   audit_log und werden mit Rolle, Umfang und Beleg-seq BENANNT (Grundregel
#   1), nicht verschwiegen und nicht bestraft.
#
#   AENDERUNG AN EINER MIGRATION — WARUM SIE HIER ZULAESSIG IST: M038 war zum
#   Zeitpunkt der Berichtigung NIRGENDS angewandt (Alex, 13.08.2026; im
#   betroffenen Bestand belegt durch das Fehlen der Zeile version=38 in
#   schema_migrations). Es gibt also keinen Bestand, dessen gespeicherte
#   Pruefsumme abweichen koennte, und keine Historie, die umgeschrieben wuerde.
#   Waere sie irgendwo angewandt gewesen, haette der Weg anders aussehen
#   muessen — eine nachgelagerte Migration haette nicht geholfen, weil M038
#   vor ihr laeuft und den Lauf abbricht.
#
# ── WAS DIESE MIGRATION AUSDRUECKLICH NICHT TUT: GRANTS ─────────────────────
#
#   Sie vergibt das neue Recht an KEINE Rolle. Das ist keine Nachlaessigkeit,
#   sondern die Bauregel aus M006: rbac_grant.audit_seq ist NOT NULL, jeder
#   Grant traegt den Beleg seiner Vergabe. Eine Migration hat keinen Akteur
#   und keinen Beleg — ein von ihr geschriebener Grant waere ein Zugang, den
#   niemand vergeben hat.
#
#   FOLGE, UND SIE IST WICHTIG: Unmittelbar nach dieser Migration sieht
#   NIEMAND mehr die Falluebersicht — auch nicht, wer heute 'dashboard.view'
#   besitzt. Der Zustand ist gewollt sichtbar und nicht still: die Sicht
#   verschwindet aus der Navigation, die Kachel aus dem Ueberblick, und
#   /api/overview antwortet mit 403 unter Nennung des fehlenden Rechts.
#
#   DIE UEBERNAHME DER BESTEHENDEN RECHTE IST EIN EIGENER, AUDITIERTER LAUF:
#     python -m management.rbac.rbac_admin migrate-grants \
#            --from dashboard.view --to caseoverview.view --probe   # Probelauf
#     python -m management.rbac.rbac_admin migrate-grants \
#            --from dashboard.view --to caseoverview.view --actor <SYSUSER>
#   Er uebernimmt je Rolle den Scope 1:1 und schreibt je Grant einen eigenen
#   Beleg. Er gehoert in DASSELBE Wartungsfenster wie das Einspielen.
#
# ── MIGRATIONSVORBEHALT (ab 01.07.2026) ─────────────────────────────────────
#
#   NUR coordinator.db. evidence_<uid>.db, forensic_<uid>.db und
#   assets_<uid>.db werden NICHT beruehrt. Es gehen keine Ermittlerdaten
#   verloren: geschrieben werden eine Katalogzeile und zwei Textfelder einer
#   bestehenden Katalogzeile. Kein Tabellenumbau, kein executescript().
#
#   RUECKWEG: 'DELETE FROM rbac_capability WHERE code=''caseoverview.view''"
#   ist moeglich, solange kein Grant darauf zeigt; die Textberichtigung an
#   dashboard.view laesst sich mit den hier festgehaltenen Altwerten
#   (_ALT_DASHBOARD) woertlich zuruecknehmen. Beides ist Handarbeit unter
#   Aufsicht und kein Bestandteil dieser Migration.
#
# IDEMPOTENZ: INSERT OR IGNORE + Guards + Inline-Verifikation.
# Version: v0.8.698 · Build: 698 · 2026-08-11
#   berichtigt v0.8.711 · Build: 711 · 2026-08-13 (Delta- statt Bestandszaehlung
#   der Grants; noch nirgends angewandt, keine Pruefsummen-Abweichung moeglich)
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 38
NAME = "RBAC-Seed Falluebersicht (caseoverview.view) + Text dashboard.view"
KIND = "additive"

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("caseoverview.view", "Falluebersicht sehen",
     "Die Falltabelle mit Ampel, Prioritaet und Zuweisung lesen — "
     "als Sicht, als Kachel des Ueberblicks und ueber die Fallsuche "
     "der Kommandopalette. Scope 'eigene' beschraenkt auf die "
     "zugewiesenen Faelle."),
)

# --- Textberichtigung an 'dashboard.view' (ebenfalls eingefroren) ------------
#  _ALT_DASHBOARD haelt fest, was M006 gesetzt hat. Es steht hier NICHT zur
#  Zierde: die Migration aendert den Text nur, wenn sie GENAU diesen Altwert
#  vorfindet. Hat ihn jemand von Hand angefasst, bleibt seine Fassung stehen
#  und der Fall wird gemeldet — eine Migration, die fremde Aenderungen
#  ueberschreibt, macht aus einer Berichtigung einen Datenverlust.
_ALT_DASHBOARD = (
    "Ampel-Dashboard sehen",
    "Falluebersicht mit Ampel und Kennzahlen lesen.",
)
_NEU_DASHBOARD = (
    "Kachel-Dashboard sehen",
    "Den Ueberblick mit seinen Kacheln oeffnen. Das Recht traegt "
    "den RAHMEN, nicht den Inhalt: welche Kacheln erscheinen, "
    "entscheidet je Kachel deren eigenes Recht.",
)


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _cap_exists(con: sqlite3.Connection, code: str) -> bool:
    return con.execute(
        "SELECT 1 FROM rbac_capability WHERE code=?",
        (code,)).fetchone() is not None


def _grant_zahl(con: sqlite3.Connection, code: str) -> int:
    """
    Zahl ALLER Grant-Zeilen auf 'code' — auch der zurueckgenommenen.

    Bewusst OHNE Filter auf revoked_at: gezaehlt wird, was diese Migration
    selbst geschrieben haben koennte, und sie schreibt keine Ruecknahmen. Der
    Wert ist nur als VERGLEICHSMASS gegen sich selbst gedacht (vorher/nachher);
    fuer eine Aussage ueber die Rechtelage ist er der falsche Wert.
    """
    if not _table_exists(con, "rbac_grant"):
        return 0
    return con.execute(
        "SELECT COUNT(*) FROM rbac_grant WHERE capability_code=?",
        (code,)).fetchone()[0]


def _grants_benennen(con: sqlite3.Connection, code: str) -> None:
    """
    Vorgefundene Grants mit Rolle, Umfang und Beleg-seq protokollieren.

    WARUM UEBERHAUPT: Ein Grant auf ein Recht, das der Katalog der Datenbank
    erst mit dieser Migration bekommt, ist ungewoehnlich genug, um genannt zu
    werden — er ist in aller Regel ein Uebernahmelauf, der zu frueh gefahren
    wurde. Er ist aber kein Fehler DIESER Migration und darf sie nicht
    aufhalten: er traegt seinen eigenen Beleg in audit_log, und wer ihn
    nachvollziehen will, findet mit der hier genannten seq den Akteur.
    """
    for row in con.execute(
            "SELECT id, role_code, scope, audit_seq, revoked_at FROM "
            "rbac_grant WHERE capability_code=? ORDER BY id", (code,)):
        logger.warning(
            "M038: '%s' trug vor dem Seed bereits Grant #%s (rolle=%s, "
            "umfang=%s, Beleg-seq=%s, %s). Diese Migration vergibt keine — "
            "Herkunft ueber audit_log seq=%s nachvollziehbar. Der Grant "
            "bleibt unveraendert.",
            code, row[0], row[1], row[2] or "-", row[3],
            "zurueckgenommen" if row[4] else "aktiv", row[3])


def up(con: sqlite3.Connection) -> None:
    if not _table_exists(con, "rbac_capability"):
        raise RuntimeError(
            "M038: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    # --- (0) Ausgangsstand MESSEN, bevor irgendetwas geschrieben wird ------
    #  Ohne diese Messung liesse sich am Ende nicht unterscheiden, ob ein
    #  Grant durch diesen Lauf entstanden oder schon vorher da gewesen ist —
    #  und genau diese Unterscheidung ist der Zweck des Waechters unten.
    grants_vorher = {code: _grant_zahl(con, code) for code, _l, _d in _SEED_CAPS}

    now = int(time.time())

    # --- (a) Das neue Recht ------------------------------------------------
    for code, label, desc in _SEED_CAPS:
        con.execute(
            "INSERT OR IGNORE INTO rbac_capability "
            "(code, label, description, created_at) VALUES (?, ?, ?, ?)",
            (code, label, desc, now),
        )

    # --- (b) Der berichtigte Text an 'dashboard.view' -----------------------
    row = con.execute(
        "SELECT label, description FROM rbac_capability WHERE code=?",
        ("dashboard.view",)).fetchone()
    if row is None:
        raise RuntimeError(
            "M038: 'dashboard.view' fehlt — M006 ist nicht angewandt oder "
            "das Recht wurde entfernt.")
    vorgefunden = (row[0], row[1])
    if vorgefunden == _ALT_DASHBOARD:
        con.execute(
            "UPDATE rbac_capability SET label=?, description=? WHERE code=?",
            (_NEU_DASHBOARD[0], _NEU_DASHBOARD[1], "dashboard.view"))
        logger.info("M038: Text von 'dashboard.view' berichtigt.")
    elif vorgefunden == _NEU_DASHBOARD:
        logger.info("M038: Text von 'dashboard.view' bereits berichtigt "
                    "— No-op.")
    else:
        # KEIN Abbruch: der Seed des neuen Rechts ist davon unabhaengig und
        # soll nicht an einer Textfrage scheitern. Aber auch kein Schweigen —
        # wer den Text angepasst hat, muss erfahren, dass er jetzt von der
        # Katalogfassung abweicht (Grundregel 1).
        logger.warning(
            "M038: 'dashboard.view' traegt einen fremden Text und bleibt "
            "UNVERAENDERT. Vorgefunden: %r / %r. Erwartet war die Fassung aus "
            "M006. Der Text weicht damit von management/rbac/catalog.py ab — "
            "bitte von Hand angleichen.", vorgefunden[0], vorgefunden[1])

    # --- (c) Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) --
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError(
                "M038: Faehigkeit '%s' fehlt nach dem Seed." % code)

    # Diese Migration vergibt keine Grants — siehe Kopf. Belegt statt
    # angenommen: haette sie versehentlich einen erzeugt, faende er sich als
    # ZUWACHS gegenueber dem gemessenen Ausgangsstand.
    #
    # NUR DER ZUWACHS BRICHT AB (Build 711). Ein vorgefundener Grant gehoert
    # nicht dieser Migration: er traegt seinen eigenen Beleg, und ihn hier zum
    # Abbruchgrund zu machen hiesse, den Bestand zu verriegeln — die Faehigkeit
    # entstuende nie, und der einzige Ausweg waere ein DELETE auf eine belegte
    # Zeile. Die Begruendung in voller Laenge steht im Kopf.
    for code, _l, _d in _SEED_CAPS:
        vorher = grants_vorher[code]
        nachher = _grant_zahl(con, code)
        if vorher:
            _grants_benennen(con, code)
        if nachher > vorher:
            raise RuntimeError(
                "M038: '%s' hat waehrend dieses Laufs %d Grant(s) "
                "hinzubekommen (vorher %d, jetzt %d). Diese Migration vergibt "
                "keine — der Lauf wird zurueckgerollt."
                % (code, nachher - vorher, vorher, nachher))

    logger.info("M038: Faehigkeit 'caseoverview.view' geseedet (ohne Grants). "
                "Uebernahme der bestehenden Rechte: "
                "'rbac_admin migrate-grants --from dashboard.view "
                "--to caseoverview.view'.")
