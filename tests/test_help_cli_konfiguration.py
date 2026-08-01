# =============================================================================
# tests/test_help_cli_konfiguration.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme
# =============================================================================
# Testsuite fuer Build 639, Ticket 60e4236e: "Hilfe mind. bei CLI-Hilfe um
# verwendete Eintraege in config.yaml erweitern".
#
# WAS DIESE SUITE LEISTET UND WAS SIE NICHT KANN:
#   Sie erzwingt, dass die Auskunft VOLLSTAENDIG und EHRLICH ist: jeder
#   erfasste Eintrag traegt Bedeutung, Vorgabewert und Fundstelle; die drei
#   Zustaende (erfasst / geprueft-keine / noch nicht erhoben) sind in beiden
#   Ausgaben unterscheidbar; die Fehlliste darf nur schrumpfen.
#   Sie kann NICHT pruefen, ob eine Bedeutung fachlich richtig beschrieben
#   ist - das bleibt die Vier-Augen-Lesung. WOHL ABER prueft sie, dass jeder
#   genannte Schluessel im ConfigLoader ueberhaupt existieren kann (KF06) und
#   dass jede genannte Belegdatei da ist (KF07). Ein Verweis ins Leere ist
#   kein Beleg, und das ist maschinell feststellbar.
#
# KF01 - die drei Zustaende sind unterscheidbar (der Kernfall)
# KF02 - jeder erfasste Eintrag ist vollstaendig (Pflichtfelder erzwungen)
# KF03 - die Textausgabe nennt alle drei Zustaende beim Namen
# KF04 - die HTML-Ausgabe nennt alle drei Zustaende beim Namen
# KF05 - keine Dopplung eines Schluessels innerhalb eines Werkzeugs
# KF06 - jeder genannte Schluessel ist in config.yaml oder in den Coded
#        Defaults auffindbar (kein erfundener Eintrag)
# KF07 - jede Fundstelle nennt eine Datei, die es gibt
# KF08 - die Fehlliste ist abgeleitet und schrumpft nur
# KF09 - die drei in Build 638/639 erfassten Werkzeuge sind erfasst
# KF10 - backup_admin nennt die im Ticket ausdruecklich verlangten Eintraege
# KF11 - db.journal_mode wird bei backup_admin NICHT behauptet (Gegenprobe)
# KF12 - 'liest keinen Eintrag' wird am Quelltext gegengeprueft (Build 641)
# KF13 - jede Fundstelle enthaelt den genannten Eintrag wirklich (Build 641)
#
# BUILD 641: Die Erhebung ist vollstaendig - 66 von 66 Werkzeugen. KF08 ist
# damit von einer Fehlliste zu einer SPERRE geworden: kein Werkzeug ohne
# Auskunft ueber config.yaml, ohne Einschraenkung und ohne Ausnahmeliste.
#
# Version: v0.8.641 - Build: 641 - 2026-08-01
# =============================================================================

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.help.cli_html import (                    # noqa: E402
    OHNE_KONFIGURATION_TEXT, kapitel_html,
    verify_abschnitte_vollstaendig,
)
from management.help.cli_katalog import (                 # noqa: E402
    CLI_KATALOG, eintrag, fehlliste_cli_konfiguration,
)
from management.help.cli_modell import (                  # noqa: E402
    KONFIG_KEINE, CliKonfig, CliModellError,
)
from management.help.cli_text import zeige_text           # noqa: E402

WURZEL = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STAND = os.path.join(os.path.dirname(__file__), "hilfe_fehlliste_stand.json")

#: Die Werkzeuge, deren Konfigurationsauskunft in Build 638/639 erhoben
#: wurde. Sie stehen hier NAMENTLICH, damit ein spaeterer Umbau, der die
#: Auskunft versehentlich wieder entfernt, auffaellt (Grundregel 1).
ERHOBEN_BUILD_639 = ("maintenance", "maintenance_kill", "backup_admin")


# -----------------------------------------------------------------------------
# KF01 - die drei Zustaende
# -----------------------------------------------------------------------------

def test_kf01_drei_zustaende_sind_unterscheidbar():
    """
    KF01, DER KERNFALL. 'geprueft, liest keinen Eintrag' und 'noch nicht
    erhoben' muessen zwei verschiedene Zustaende sein.

    Waeren sie es nicht, wuerde die Fehlliste ungepruefte Werkzeuge als
    erledigt ausweisen - eine Luecke, die als geschlossen gemeldet wird, ist
    schlimmer als eine offene (Grundregel 1).
    """
    e_erhoben = eintrag("maintenance")
    assert e_erhoben.konfiguration_geprueft() is True
    assert e_erhoben.hat_konfiguration() is True

    # Ein Werkzeug mit KONFIG_KEINE: geprueft, aber ohne Eintraege.
    leer = eintrag("maintenance").__class__(
        schluessel="attrappe", pfad="tools/attrappe.py",
        aufruf="python tools/attrappe.py", titel="Attrappe",
        gruppe="Diagnose", zweck="Nur fuer die Pruefung.", art="lesend",
        betrieb="jederzeit", konfiguration=KONFIG_KEINE)
    assert leer.konfiguration_geprueft() is True
    assert leer.hat_konfiguration() is False

    # Ein Werkzeug ohne Angabe: NICHT geprueft.
    ungeprueft = eintrag("maintenance").__class__(
        schluessel="attrappe2", pfad="tools/attrappe2.py",
        aufruf="python tools/attrappe2.py", titel="Attrappe",
        gruppe="Diagnose", zweck="Nur fuer die Pruefung.", art="lesend",
        betrieb="jederzeit")
    assert ungeprueft.konfiguration_geprueft() is False
    assert ungeprueft.hat_konfiguration() is False

    # Und die Fehlliste unterscheidet sie: nur der dritte gehoert hinein.
    assert leer.schluessel not in fehlliste_cli_konfiguration()


# -----------------------------------------------------------------------------
# KF02 / KF05 - Vollstaendigkeit der erfassten Eintraege
# -----------------------------------------------------------------------------

def test_kf02_pflichtfelder_werden_erzwungen():
    """
    KF02: Ein Eintrag ohne Fundstelle oder ohne Vorgabewert ist nicht
    nachpruefbar und wird schon beim Bau abgewiesen.
    """
    CliKonfig(schluessel="a.b", bedeutung="tut etwas", vorgabe="7",
              beleg="datei.py Z. 1")  # geht
    for fehlt in ("schluessel", "bedeutung", "vorgabe", "beleg"):
        werte = {"schluessel": "a.b", "bedeutung": "tut etwas",
                 "vorgabe": "7", "beleg": "datei.py Z. 1"}
        werte[fehlt] = "   "
        with pytest.raises(CliModellError):
            CliKonfig(**werte)


def test_kf05_kein_schluessel_doppelt_je_werkzeug():
    """
    KF05: Derselbe Eintrag zweimal bei einem Werkzeug waere entweder ein
    Kopierfehler oder ein Widerspruch - beides faellt hier auf.
    """
    for e in CLI_KATALOG:
        if not e.hat_konfiguration():
            continue
        namen = [k.schluessel for k in e.konfiguration]
        doppelt = sorted({n for n in namen if namen.count(n) > 1})
        assert not doppelt, ("%s nennt Eintraege doppelt: %s"
                             % (e.schluessel, ", ".join(doppelt)))


def test_kf06_jeder_schluessel_ist_auffindbar():
    """
    KF06: Jeder genannte Schluessel muss entweder in der ausgelieferten
    config.yaml stehen ODER in den Coded Defaults des ConfigLoaders ODER in
    der ausgelieferten config.yaml AUSKOMMENTIERT vorkommen.

    WARUM DER DRITTE FALL ZAEHLT: Der Abschnitt 'maintenance' ist bewusst
    auskommentiert ausgeliefert (Build 638) - ein eingetragener Wert waere
    eine Standortfestlegung, die niemand bestellt hat. Er ist trotzdem ein
    echter, wirksamer Einstellpunkt. Ohne diesen Fall muesste man ihn
    entweder verschweigen oder ihn unbestellt setzen.

    Was dieser Fall AUSSCHLIESST, ist der erfundene Schluessel: ein Name, den
    es weder in der Datei noch im Code gibt.
    """
    from core.config_loader import ConfigLoader
    cfg = ConfigLoader(config_path=os.path.join(WURZEL, "config.yaml"))
    roh = open(os.path.join(WURZEL, "config.yaml"), encoding="utf-8").read()

    for e in CLI_KATALOG:
        if not e.hat_konfiguration():
            continue
        for k in e.konfiguration:
            if cfg.get(k.schluessel) is not None:
                continue
            blatt = k.schluessel.split(".")[-1]
            # Auskommentiert: '#   stale_seconds: 30' o. ae.
            if re.search(r"^\s*#.*\b%s\s*:" % re.escape(blatt), roh,
                         re.MULTILINE):
                continue
            pytest.fail(
                "%s nennt '%s'. Der Schluessel steht weder in config.yaml "
                "(auch nicht auskommentiert) noch in den Coded Defaults des "
                "ConfigLoaders." % (e.schluessel, k.schluessel))


def test_kf07_jede_fundstelle_nennt_eine_vorhandene_datei():
    """
    KF07: Aus jeder Fundstelle wird der Dateipfad herausgeloest und geprueft.
    Ein Verweis ins Leere ist kein Beleg - und im Unterschied zur
    inhaltlichen Richtigkeit ist das maschinell feststellbar.
    """
    muster = re.compile(r"[\w./_-]+\.py")
    for e in CLI_KATALOG:
        if not e.hat_konfiguration():
            continue
        for k in e.konfiguration:
            dateien = muster.findall(k.beleg)
            assert dateien, ("%s / %s: die Fundstelle nennt keine Datei: %r"
                             % (e.schluessel, k.schluessel, k.beleg))
            for d in dateien:
                assert os.path.isfile(os.path.join(WURZEL, d)), (
                    "%s / %s: Fundstelle verweist auf '%s' - die Datei gibt "
                    "es nicht." % (e.schluessel, k.schluessel, d))


# -----------------------------------------------------------------------------
# KF03 / KF04 - die beiden Ausgaben
# -----------------------------------------------------------------------------

def test_kf03_textausgabe_nennt_alle_drei_zustaende():
    """
    KF03: In der Textausgabe ist der Abschnitt IMMER da - mit den Eintraegen,
    mit dem Satz 'wertet KEINEN Eintrag aus' oder mit dem Satz 'noch nicht
    erhoben'. Ein fehlender Abschnitt liesse den Leser raten.
    """
    for e in CLI_KATALOG:
        text = zeige_text(e)
        # Die Ausgabe ist auf 78 Zeichen umbrochen; ein Satz steht deshalb
        # nicht zwingend in EINER Zeile. Fuer den Vergleich wird der
        # Zeilenumbruch eingeebnet - geprueft wird der Satz, nicht sein Satzbild.
        flach = " ".join(text.split())
        assert "Einstellungen in config.yaml" in flach, e.schluessel
        if e.hat_konfiguration():
            for k in e.konfiguration:
                assert k.schluessel in flach, (e.schluessel, k.schluessel)
                assert "ohne Eintrag: " in flach
                assert "Fundstelle: " in flach
        elif e.konfiguration_geprueft():
            assert "wertet KEINEN Eintrag" in flach, e.schluessel
        else:
            assert "noch nicht erhoben" in flach, e.schluessel
            assert "Das heisst NICHT, dass es keine gibt." in flach, e.schluessel


def test_kf04_htmlausgabe_nennt_alle_drei_zustaende():
    """KF04: Dasselbe fuer die Vollhilfe - beide Ausgaben sagen dasselbe."""
    verify_abschnitte_vollstaendig()
    for e in CLI_KATALOG:
        html = kapitel_html(e)
        assert "Einstellungen in config.yaml" in html, e.schluessel
        assert 'id="cli-%s-einstellungen"' % e.schluessel in html
        if e.hat_konfiguration():
            for k in e.konfiguration:
                assert k.schluessel in html, (e.schluessel, k.schluessel)
                assert k.beleg.split(",")[0] in html
        elif e.konfiguration_geprueft():
            assert "wertet keinen Eintrag aus config.yaml aus" in html
        else:
            assert OHNE_KONFIGURATION_TEXT in html, e.schluessel


# -----------------------------------------------------------------------------
# KF08 / KF09 - die Fehlliste
# -----------------------------------------------------------------------------

def test_kf08_fehlliste_ist_abgeleitet_und_schrumpft_nur():
    """
    KF08: Die Fehlliste wird gerechnet, nicht gepflegt, und darf gegenueber
    dem eingecheckten Stand nur schrumpfen. Ein NEUER Eintrag heisst: ein
    Werkzeug ist ohne diese Auskunft hinzugekommen, oder eine bestehende
    Auskunft ist verlorengegangen. Beides ist ein Befund.

    BUILD 641 - DIE PRUEFUNG WECHSELT IHRE AUFGABE, wie CK07 es in Build 620
    getan hat. Solange die Liste Eintraege hatte, konnte sie nur verlangen,
    dass es nicht schlechter wird. Seit die Erhebung vollstaendig ist, gilt
    der Satz selbst: KEIN WERKZEUG OHNE AUSKUNFT UEBER config.yaml.

    Unterschieden wird am STANDBUILD und nicht am Zufall einer leeren Liste:
    Bis Build 640 hiesse eine leere eingecheckte Liste 'sie wurde nie
    gefuehrt' - eine stille Unwahrheit. Ab Standbuild 641 heisst sie das
    Gegenteil. Der Schrumpfvergleich darunter bleibt in Kraft; er ist das
    zweite Netz, falls die erste Bedingung je gelockert wird.
    """
    with open(STAND, encoding="utf-8") as fh:
        stand = json.load(fh)
    eingecheckt = set(stand.get("cli_ohne_konfiguration", []))
    aktuell = set(fehlliste_cli_konfiguration())

    if stand.get("stand_build", 0) < 641:
        assert eingecheckt, (
            "Die eingecheckte Liste 'cli_ohne_konfiguration' ist leer. Bis "
            "Build 640 hiesse das, dass sie nie gefuehrt wurde.")
    else:
        assert not aktuell, (
            "Der Stand ist ab Build 641 eingecheckt, aber es gibt wieder "
            "Werkzeuge ohne Auskunft ueber config.yaml: %s. Wer ein Werkzeug "
            "aufnimmt, traegt im selben Build ein, welche Eintraege es liest "
            "- oder KONFIG_KEINE, wenn es keine liest."
            % ", ".join(sorted(aktuell)))

    neu = sorted(aktuell - eingecheckt)
    assert not neu, (
        "Die Konfigurations-Fehlliste ist GEWACHSEN um: %s." % ", ".join(neu))


def test_kf12_konfig_keine_wird_am_quelltext_gegengeprueft():
    """
    KF12, DIE GEGENPROBE ZUR BEQUEMEN ANTWORT (NEU Build 641).

    'KONFIG_KEINE' ist die billigste Angabe im ganzen Katalog: Sie kostet
    keine Recherche und sieht aus wie Arbeit. Genau deshalb wird sie gegen
    den Quelltext geprueft - ein Werkzeug, das den ConfigLoader importiert,
    kann nicht 'liest keinen Eintrag' sein.

    WAS DIESE PRUEFUNG NICHT LEISTET: Sie findet keinen Zugriff, der ohne
    das Wort 'ConfigLoader' auskommt - repair_block_types.py etwa liest die
    config.yaml unmittelbar mit yaml.safe_load. Deshalb steht daneben die
    zweite Bedingung. Beide zusammen sind kein Beweis, aber sie fangen den
    Fall ab, um den es geht: die aus Bequemlichkeit gesetzte Leerangabe.
    """
    verdaechtig = re.compile(r'^\s*[^#\n]*\byaml\.safe_load\s*\(', re.MULTILINE)
    geprueft = 0
    for e in CLI_KATALOG:
        if e.konfiguration_geprueft() and not e.hat_konfiguration():
            geprueft += 1
            quelle = open(os.path.join(WURZEL, e.pfad),
                          encoding="utf-8", errors="replace").read()
            assert "ConfigLoader" not in quelle, (
                "%s ist als 'liest keinen Eintrag aus config.yaml' gefuehrt, "
                "importiert aber den ConfigLoader (%s)."
                % (e.schluessel, e.pfad))
            assert not verdaechtig.search(quelle), (
                "%s ist als 'liest keinen Eintrag aus config.yaml' gefuehrt, "
                "ruft aber yaml.safe_load auf (%s). Bitte nachsehen, WAS "
                "dort gelesen wird." % (e.schluessel, e.pfad))
    # Eine Gegenprobe, die nichts prueft, belegt nichts (TE5).
    assert geprueft >= 15, (
        "Es sind nur %d Werkzeuge mit KONFIG_KEINE geprueft worden - "
        "erwartet werden mindestens 15. Ist die Angabe verlorengegangen?"
        % geprueft)


def test_kf13_erhobene_werkzeuge_nennen_ihre_quelle_im_quelltext():
    """
    KF13, DIE GEGENRICHTUNG (NEU Build 641).

    Bei jedem Werkzeug MIT Eintraegen muss der genannte Schluessel - oder
    zumindest sein Blatt - auch tatsaechlich in einer der genannten
    Belegdateien vorkommen. Das schlaegt den Fall, dass ein Eintrag aus einem
    anderen Werkzeug herueberkopiert wurde und die Fundstelle mitgereist ist.

    Geprueft wird gegen das BLATT ('coordinator_db') und nicht gegen den
    vollen Schluessel: Mehrere Werkzeuge setzen ihn zusammen ('paths.' + key,
    cfg.get("paths", {}).get("coordinator_db")), und eine Pruefung auf den
    vollen Schluessel wuerde genau diese Schreibweisen zu Unrecht melden.
    """
    datei = re.compile(r"[\w./_-]+\.py")
    for e in CLI_KATALOG:
        if not e.hat_konfiguration():
            continue
        for k in e.konfiguration:
            blatt = k.schluessel.split(".")[-1]
            gefunden = False
            for d in datei.findall(k.beleg):
                pfad = os.path.join(WURZEL, d)
                if not os.path.isfile(pfad):
                    continue
                if blatt in open(pfad, encoding="utf-8",
                                 errors="replace").read():
                    gefunden = True
                    break
            assert gefunden, (
                "%s / %s: Das Blatt '%s' kommt in keiner der genannten "
                "Belegdateien vor (%s). Entweder stimmt die Fundstelle nicht, "
                "oder der Eintrag gehoert zu einem anderen Werkzeug."
                % (e.schluessel, k.schluessel, blatt, k.beleg))


def test_kf09_die_erhobenen_werkzeuge_bleiben_erhoben():
    """
    KF09: Die in Build 638/639 erhobenen Werkzeuge stehen NAMENTLICH. Wer
    ihre Auskunft bei einem spaeteren Umbau entfernt, faellt hier auf und
    nicht erst dem Leser der Hilfe.
    """
    offen = set(fehlliste_cli_konfiguration())
    for schluessel in ERHOBEN_BUILD_639:
        e = eintrag(schluessel)
        assert e is not None, schluessel
        assert schluessel not in offen, schluessel
        assert e.hat_konfiguration(), schluessel


def test_kf10_backup_admin_nennt_die_im_ticket_verlangten_eintraege():
    """
    KF10: Das Ticket 60e4236e nennt 'backup_admin' als Beispiel. Die
    Stellgroessen der Sicherung - Ziel, Aufbewahrung, Platzreserve - muessen
    dort auftauchen, sonst ist das Ticket der Sache nach nicht erledigt.
    """
    e = eintrag("backup_admin")
    genannt = {k.schluessel for k in e.konfiguration}
    for pflicht in ("backup.dest_dir", "backup.retention_count",
                    "backup.min_free_factor", "backup.checkpoint",
                    "backup.include_shared_dbs"):
        assert pflicht in genannt, pflicht


def test_kf11_db_journal_mode_wird_bei_backup_admin_nicht_behauptet():
    """
    KF11, DIE GEGENPROBE ZUR VERSUCHUNG. Es liegt nahe, bei einem
    Sicherungswerkzeug 'db.journal_mode' aufzufuehren. backup_admin wertet
    den Eintrag NICHT aus: es ruft apply_journal_mode(con, db_path) ohne
    'mode' auf und bekommt damit den Vorgabewert aus db/journal_policy.py.

    Diese Pruefung haelt die Beleglage fest. Wer den Eintrag spaeter
    aufnimmt, muss vorher den Aufruf aendern - sonst faellt es hier auf.
    """
    from management.backup import backup_admin as ba
    quelle = open(ba.__file__.replace(".pyc", ".py"), encoding="utf-8").read()
    assert "apply_journal_mode(con, db_path)" in quelle, (
        "Der Aufruf hat sich geaendert. Bitte pruefen, ob backup_admin jetzt "
        "db.journal_mode auswertet - und den Katalogeintrag nachziehen.")
    genannt = {k.schluessel for k in eintrag("backup_admin").konfiguration}
    assert "db.journal_mode" not in genannt
