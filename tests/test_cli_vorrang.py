# =============================================================================
# tests/test_cli_vorrang.py
# IT-Forensisches Ermittlungswerkzeug — Vorrangregel der Kommandozeile
# =============================================================================
# Prueft die projektweite Vorrangregel
#
#     Argument  >  aus einem Argument abgeleitet  >  config.yaml  >  Vorgabewert
#
# in ihrem Bauteil (core/setting_resolver.py), in ihrer Anwendung auf die
# Wartungswerkzeuge (maintenance/cli_config.py) und am gemeldeten Vorfall
# selbst (Ticket 15429c75).
#
# WARUM DIE GEGENPROBEN HIER SO AUSFUEHRLICH SIND (TE5): Eine Pruefung, die
# nur die oberste Stufe belegt, schlaegt bei einer kaputten Vorrangregel nie
# an. Jede Stufe wird deshalb EINZELN erzwungen, indem die jeweils hoehere
# weggelassen wird — und jede Pruefung stellt zusaetzlich fest, dass die
# HERKUNFT richtig benannt wird. Ein richtiger Wert aus der falschen Quelle
# ist ein Zufallstreffer und kein Beleg.
#
# Kennungen:
#   VR01-VR04  Der Aufloeser: die vier Stufen einzeln.
#   VR05-VR07  Der Aufloeser: Randfaelle, an denen die alte Fassung scheiterte.
#   VR10-VR15  Die Wartungswerkzeuge: coordinator_db und data_dir.
#   VR20-VR22  Der gemeldete Vorfall (15429c75) und die Herkunftsausgabe.
#   VR30-VR32  ConfigLoader.stammt_aus_datei (Build 638).
#
# Version: v0.8.638 · Build: 638 · 2026-08-01
# =============================================================================

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.config_loader import ConfigLoader                      # noqa: E402
from core.setting_resolver import (SettingResolver,              # noqa: E402
                                   SettingResolverError, als_pfad)
from maintenance.cli_config import (VORGABEN, pfade_aufloesen,   # noqa: E402
                                    resolver_bauen)


def _lade(relpfad: str, name: str):
    spec = importlib.util.spec_from_file_location(name, _REPO_ROOT / relpfad)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


maint = _lade("tools/maintenance.py", "vorrang_maint_tool")


class _Args:
    """
    Attrappe eines argparse-Ergebnisses. Bewusst SO einfach: die Werkzeuge
    lesen ihre Argumente ueber getattr(args, name, None), und genau dieses
    Verhalten soll hier geprueft werden — nicht argparse.
    """

    def __init__(self, **werte):
        self.config = None
        self.data_dir = None
        self.coordinator_db = None
        for schluessel, wert in werte.items():
            setattr(self, schluessel, wert)


def _config_schreiben(pfad: Path, inhalt: str) -> Path:
    """
    Schreibt eine config.yaml, die den Pflichtteil der Validierung erfuellt.
    ConfigLoader._validate() verlangt gueltige server./logging.-Werte; ohne
    sie kaeme der Aufloeser gar nicht bis zu dem Eintrag, um den es geht.
    """
    pfad.write_text(
        "server:\n  host: \"127.0.0.2\"\n  port: 8080\n  mode: \"cli\"\n"
        "logging:\n  level: \"info\"\n"
        + inhalt, encoding="utf-8")
    return pfad


# =============================================================================
# VR01-VR04 — Der Aufloeser: die vier Stufen einzeln
# =============================================================================

def test_vr01_argument_schlaegt_alles(tmp_path):
    """VR01: Das Argument gewinnt gegen config.yaml UND gegen den Vorgabewert."""
    cfg = _config_schreiben(tmp_path / "config.yaml",
                            "paths:\n  coordinator_db: \"/aus/config.db\"\n")
    r = SettingResolver(config_path=str(cfg))
    e = r.aufloesen(name="coordinator_db", arg_wert="/aus/argument.db",
                    arg_name="--coordinator-db",
                    abgeleitet="/abgeleitet.db",
                    abgeleitet_quelle="aus --data-dir",
                    config_schluessel="paths.coordinator_db",
                    default="/vorgabe.db")
    assert e.wert == "/aus/argument.db"
    assert e.herkunft == "argument"
    assert "--coordinator-db" in e.quelle


def test_vr02_abgeleitet_schlaegt_config(tmp_path):
    """
    VR02: Ohne unmittelbares Argument gewinnt der aus einem ANDEREN Argument
    abgeleitete Wert — er beruht auf einer Angabe des Aufrufers.
    """
    cfg = _config_schreiben(tmp_path / "config.yaml",
                            "paths:\n  coordinator_db: \"/aus/config.db\"\n")
    r = SettingResolver(config_path=str(cfg))
    e = r.aufloesen(name="coordinator_db", arg_wert=None,
                    arg_name="--coordinator-db",
                    abgeleitet="/abgeleitet.db",
                    abgeleitet_quelle="aus --data-dir",
                    config_schluessel="paths.coordinator_db",
                    default="/vorgabe.db")
    assert e.wert == "/abgeleitet.db"
    assert e.herkunft == "abgeleitet"


def test_vr03_config_schlaegt_vorgabewert(tmp_path):
    """VR03: Ohne jedes Argument gewinnt der Eintrag aus config.yaml."""
    cfg = _config_schreiben(tmp_path / "config.yaml",
                            "paths:\n  coordinator_db: \"/aus/config.db\"\n")
    r = SettingResolver(config_path=str(cfg))
    e = r.aufloesen(name="coordinator_db", arg_wert=None,
                    arg_name="--coordinator-db", abgeleitet=None,
                    config_schluessel="paths.coordinator_db",
                    default="/vorgabe.db")
    assert e.wert == "/aus/config.db"
    assert e.herkunft == "config.yaml"
    assert "paths.coordinator_db" in e.quelle


def test_vr04_vorgabewert_wenn_nichts_gesetzt(tmp_path):
    """VR04: Steht der Schluessel NICHT in der Datei, gilt der Vorgabewert."""
    cfg = _config_schreiben(tmp_path / "config.yaml", "")
    r = SettingResolver(config_path=str(cfg))
    e = r.aufloesen(name="stale", arg_wert=None, arg_name="--stale",
                    config_schluessel="maintenance.stale_seconds", default=30)
    assert e.wert == 30
    assert e.herkunft == "default"


# =============================================================================
# VR05-VR07 — Randfaelle
# =============================================================================

def test_vr05_coded_default_des_configloaders_ist_keine_configquelle(tmp_path):
    """
    VR05: DIE ENTSCHEIDENDE ABGRENZUNG. 'paths.coordinator_db' hat in
    core/config_loader._DEFAULTS einen Coded Default. Steht der Schluessel
    NICHT in der Datei, darf die Herkunft trotzdem nicht 'config.yaml'
    lauten — sonst waere die Herkunftsangabe eine unbelegte Behauptung.
    """
    cfg = _config_schreiben(tmp_path / "config.yaml", "")
    r = SettingResolver(config_path=str(cfg))
    assert r._config.get("paths.coordinator_db")  # Coded Default liefert etwas
    e = r.aufloesen(name="coordinator_db", arg_wert=None,
                    arg_name="--coordinator-db",
                    config_schluessel="paths.coordinator_db",
                    default="/vorgabe.db")
    assert e.herkunft == "default"
    assert e.wert == "/vorgabe.db"


def test_vr06_argumentwert_null_ist_gesetzt(tmp_path):
    """
    VR06: 0 / '' / False sind GESETZTE Argumente und gewinnen. Nur None heisst
    'nicht angegeben'. Sonst koennte man '--ablauf-min 0' (Fenster laeuft nie
    ab) nicht mehr gegen eine Standortvorgabe durchsetzen.
    """
    cfg = _config_schreiben(tmp_path / "config.yaml",
                            "maintenance:\n  ablauf_min: 45\n")
    r = SettingResolver(config_path=str(cfg))
    e = r.aufloesen(name="ablauf_min", arg_wert=0, arg_name="--ablauf-min",
                    config_schluessel="maintenance.ablauf_min", default=0)
    assert e.wert == 0
    assert e.herkunft == "argument"


def test_vr07_unwandelbarer_configwert_bricht_ab(tmp_path):
    """
    VR07: Ein nicht wandelbarer Wert aus config.yaml ist ein ABBRUCH, kein
    stiller Rueckfall auf den Vorgabewert (Grundregel 1).
    """
    cfg = _config_schreiben(tmp_path / "config.yaml",
                            "maintenance:\n  stale_seconds: \"viel\"\n")
    r = SettingResolver(config_path=str(cfg))
    with pytest.raises(SettingResolverError):
        r.aufloesen(name="stale", arg_wert=None, arg_name="--stale",
                    config_schluessel="maintenance.stale_seconds",
                    default=30, wandler=int)


def test_vr07b_ausdrueckliche_config_die_fehlt_bricht_ab(tmp_path):
    """
    VR07b: Wer --config nennt, bekommt keine andere Datei untergeschoben.
    Ohne --config bleibt eine fehlende Datei dagegen folgenlos — dann aber
    MIT Meldung, nicht still.
    """
    fehlt = str(tmp_path / "gibtsnicht.yaml")
    with pytest.raises(SettingResolverError):
        SettingResolver(config_path=fehlt, pflicht=True)
    r = SettingResolver(config_path=fehlt, pflicht=False)
    assert r.config_geladen is False
    assert r.config_meldung and "config.yaml" in r.config_meldung
    assert any("config.yaml" in z for z in r.protokoll_zeilen())


def test_vr07c_leerer_configwert_faellt_durch(tmp_path):
    """
    VR07c: Ein eingetragener, aber LEERER Wert ist ein Platzhalter und keine
    Einstellung — er faellt auf den Vorgabewert durch (sichtbar ueber die
    Herkunft, nicht heimlich).
    """
    cfg = _config_schreiben(tmp_path / "config.yaml",
                            "maintenance:\n  data_dir: \"\"\n")
    r = SettingResolver(config_path=str(cfg))
    e = r.aufloesen(name="data_dir", arg_wert=None, arg_name="--data-dir",
                    config_schluessel="maintenance.data_dir", default="./data")
    assert e.wert == "./data"
    assert e.herkunft == "default"


# =============================================================================
# VR10-VR15 — Die Wartungswerkzeuge: coordinator_db und data_dir
# =============================================================================

def _aufloesen(tmp_path, config_inhalt="", **args_werte):
    cfg = _config_schreiben(tmp_path / "config.yaml", config_inhalt)
    args = _Args(config=str(cfg), **args_werte)
    resolver = resolver_bauen(args)
    data_dir, coord = pfade_aufloesen(args, resolver)
    return data_dir, coord, resolver


def test_vr10_coordinator_db_argument_behaelt_den_dateinamen(tmp_path):
    """
    VR10: DER KERN VON 15429c75. Der uebergebene DATEINAME muss erhalten
    bleiben. Bis Build 637 wurde nur das Elternverzeichnis weitergereicht und
    darauf wieder 'coordinator.db' gesetzt.
    """
    _dd, coord, _r = _aufloesen(
        tmp_path, coordinator_db="/srv/data/coordinator_2.db")
    assert coord == Path("/srv/data/coordinator_2.db")
    assert coord.name == "coordinator_2.db"


def test_vr11_coordinator_db_aus_data_dir_abgeleitet(tmp_path):
    """VR11: Ohne --coordinator-db, aber mit --data-dir: <data-dir>/coordinator.db."""
    _dd, coord, r = _aufloesen(
        tmp_path, data_dir="/srv/anders",
        config_inhalt="paths:\n  coordinator_db: \"/aus/config.db\"\n")
    assert coord == Path("/srv/anders/coordinator.db")
    assert r.herkunft("coordinator_db").herkunft == "abgeleitet"


def test_vr12_coordinator_db_aus_config(tmp_path):
    """VR12: Ohne beide Argumente greift paths.coordinator_db aus config.yaml."""
    _dd, coord, r = _aufloesen(
        tmp_path,
        config_inhalt="paths:\n  coordinator_db: \"/aus/config_2.db\"\n")
    assert coord == Path("/aus/config_2.db")
    assert r.herkunft("coordinator_db").herkunft == "config.yaml"


def test_vr13_coordinator_db_vorgabewert(tmp_path):
    """VR13: Ohne Argumente und ohne Eintrag gilt der Vorgabewert."""
    _dd, coord, r = _aufloesen(tmp_path)
    assert coord == Path(VORGABEN["coordinator_db"])
    assert r.herkunft("coordinator_db").herkunft == "default"


def test_vr14_data_dir_folgt_dem_coordinator_argument(tmp_path):
    """
    VR14: Die BISHERIGE Regel bleibt: das Elternverzeichnis von
    --coordinator-db ist das Datenverzeichnis, auch wenn --data-dir daneben
    steht. Diese Reihenfolge stand seit Build 438 im Dateikopf beider
    Werkzeuge; sie wird durch die Behebung NICHT umgedreht.
    """
    data_dir, _coord, r = _aufloesen(
        tmp_path, data_dir="/srv/anders",
        coordinator_db="/srv/data/coordinator_2.db")
    assert data_dir == Path("/srv/data")
    assert r.herkunft("data_dir").herkunft == "argument"


def test_vr15_data_dir_stufen_ohne_coordinator_argument(tmp_path):
    """VR15: --data-dir > maintenance.data_dir > Elternverzeichnis der DB."""
    data_dir, _c, r = _aufloesen(
        tmp_path, data_dir="/srv/argument",
        config_inhalt="maintenance:\n  data_dir: \"/srv/config\"\n")
    assert data_dir == Path("/srv/argument")
    assert r.herkunft("data_dir").herkunft == "abgeleitet"

    data_dir, _c, r = _aufloesen(
        tmp_path, config_inhalt="maintenance:\n  data_dir: \"/srv/config\"\n")
    assert data_dir == Path("/srv/config")
    assert r.herkunft("data_dir").herkunft == "config.yaml"

    # Ohne maintenance.data_dir folgt das Datenverzeichnis der in config.yaml
    # verlegten Datenbank — ohne dass dafuer ein zweiter Eintrag noetig waere.
    data_dir, _c, _r = _aufloesen(
        tmp_path, config_inhalt="paths:\n  coordinator_db: \"/netz/x/coord.db\"\n")
    assert data_dir == Path("/netz/x")


# =============================================================================
# VR20-VR22 — Der gemeldete Vorfall und die Herkunftsausgabe
# =============================================================================

def _coordinator_mit_grant(pfad: Path, sysuser: str) -> None:
    """Minimale coordinator.db, die 'sysuser' fuer die Wartung berechtigt."""
    con = sqlite3.connect(str(pfad))
    con.executescript(
        "CREATE TABLE person (id INTEGER PRIMARY KEY, system_username TEXT "
        "UNIQUE, display_name TEXT, is_investigator INT, is_supervisor INT, "
        "is_support INT, created_at INT);"
        "CREATE TABLE person_role (id INTEGER PRIMARY KEY, person_id INT, "
        "role_code TEXT, revoked_at INT);"
        "CREATE TABLE rbac_grant (id INTEGER PRIMARY KEY, role_code TEXT, "
        "capability_code TEXT, scope TEXT, revoked_at INT);")
    con.execute("INSERT INTO person VALUES (5, ?, 'CLI', 1, 0, 0, 0)", (sysuser,))
    con.execute("INSERT INTO person_role (person_id, role_code, revoked_at) "
                "VALUES (5, 'maintenance', NULL)")
    con.execute("INSERT INTO rbac_grant (role_code, capability_code, scope, "
                "revoked_at) VALUES ('maintenance', 'wartung.durchfuehren', "
                "NULL, NULL)")
    con.commit()
    con.close()


def test_vr20_gemeldeter_aufruf_laeuft_durch(tmp_path, capsys):
    """
    VR20: DER GEMELDETE FALL, nachgestellt. Die coordinator.db heisst
    'coordinator_2.db'; eine 'coordinator.db' gibt es NICHT. Bis Build 637
    brach das mit '[RBAC] coordinator.db fehlt (.../coordinator.db)' ab.

    Gefahren wird der Originalaufruf aus dem Ticket, nur mit
    '--wait-timeout 0' (das Warten selbst ist hier nicht der Gegenstand).
    """
    import getpass
    daten = tmp_path / "data"
    daten.mkdir()
    _coordinator_mit_grant(daten / "coordinator_2.db", getpass.getuser())
    assert not (daten / "coordinator.db").exists()

    rc = maint.main([
        "enter", "--reason", "Einpflegen neuer Daten", "--ablauf-min", "10",
        "--data-dir", str(daten), "--poll", "3",
        "--coordinator-db", str(daten / "coordinator_2.db"),
        "--ziel", "coordinator", "--wait-timeout", "0"])
    ausgabe = capsys.readouterr().out
    assert rc == 0, ausgabe
    assert "erlaubt" in ausgabe
    # Die Datei, die es nie gab, darf in keiner Meldung mehr auftauchen.
    assert "coordinator.db fehlt" not in ausgabe
    maint.main(["exit", "--data-dir", str(daten),
                "--coordinator-db", str(daten / "coordinator_2.db")])


def test_vr21_herkunft_wird_ausgegeben(tmp_path, capsys):
    """
    VR21: Jeder Aufruf legt offen, woher seine Werte stammen. Der Vorfall
    waere damit in der ERSTEN Zeile sichtbar gewesen statt erst an einer
    Fehlermeldung ueber eine nie genannte Datei.
    """
    daten = tmp_path / "data"
    daten.mkdir()
    maint.main(["status", "--data-dir", str(daten)])
    ausgabe = capsys.readouterr().out
    assert "[Konfig] coordinator_db = " in ausgabe
    assert "[Konfig] data_dir = " in ausgabe
    assert "--data-dir" in ausgabe


def test_vr22_unzulaessiges_on_active_aus_config_wird_abgewiesen(tmp_path, capsys):
    """
    VR22: 'on_active' kann jetzt aus config.yaml stammen und ist dort nicht
    durch argparse-'choices' gedeckt. Ein unbekannter Wert wird beim Aufruf
    abgewiesen und nicht ins Wartungsfenster geschrieben.
    """
    daten = tmp_path / "data"
    daten.mkdir()
    cfg = _config_schreiben(tmp_path / "config.yaml",
                            "maintenance:\n  on_active: \"abschalten\"\n")
    rc = maint.main(["enter", "--reason", "T", "--config", str(cfg),
                     "--data-dir", str(daten), "--wait-timeout", "0"])
    assert rc == 1
    assert "abschalten" in capsys.readouterr().err


# =============================================================================
# VR30-VR32 — ConfigLoader.stammt_aus_datei
# =============================================================================

def test_vr30_stammt_aus_datei_unterscheidet_datei_und_default(tmp_path):
    """VR30: Nur was in der Datei steht, gilt als aus der Datei stammend."""
    cfg = _config_schreiben(tmp_path / "config.yaml",
                            "paths:\n  coordinator_db: \"/x/y.db\"\n")
    c = ConfigLoader(config_path=str(cfg))
    assert c.stammt_aus_datei("paths.coordinator_db") is True
    # In _DEFAULTS vorhanden, in dieser Datei nicht:
    assert c.get("paths.default_db")
    assert c.stammt_aus_datei("paths.default_db") is False
    assert c.stammt_aus_datei("gibt.es.nicht") is False


def test_vr31_cli_overrides_aendern_die_beleglage_nicht(tmp_path):
    """
    VR31: Ein CLI-Override setzt einen Wert, aber er steht nicht in der Datei.
    Die Beleglage darf er deshalb nicht veraendern.
    """
    cfg = _config_schreiben(tmp_path / "config.yaml", "")
    c = ConfigLoader(config_path=str(cfg),
                     cli_overrides={"paths.coordinator_db": "/aus/cli.db"})
    assert c.get("paths.coordinator_db") == "/aus/cli.db"
    assert c.stammt_aus_datei("paths.coordinator_db") is False


def test_vr32_bestandsconfig_ist_weiterhin_ladbar():
    """
    VR32: Die config.yaml des Bestands laedt und der neue, auskommentierte
    'maintenance'-Abschnitt aendert nichts an ihr. Ein Tippfehler im
    Kommentarblock faellt hier auf.
    """
    c = ConfigLoader(config_path=str(_REPO_ROOT / "config.yaml"))
    assert c.get("server.host")
    assert c.stammt_aus_datei("paths.coordinator_db") is True
    # Auskommentiert => nicht eingetragen => Vorgabewerte der Werkzeuge gelten.
    assert c.stammt_aus_datei("maintenance") is False


def test_vr33_als_pfad_weist_leere_angabe_ab():
    """VR33: Ein leerer Pfad faellt hier auf, nicht erst beim Oeffnen der DB."""
    assert als_pfad(" /srv/x.db ") == Path("/srv/x.db")
    with pytest.raises(ValueError):
        als_pfad("   ")
