# =============================================================================
# tests/test_maintenance_cli.py
# IT-Forensisches Ermittlungswerkzeug — Tests zu den Wartungs-Werkzeugen
# =============================================================================
# Prueft maintenance/cli_support.py (Ziel-Pfade, Exklusiv-Lock-Beweis,
# Quiesce-Status) sowie tools/maintenance.py (enter/exit/status) und
# tools/maintenance_kill.py gegen echte Dateien in tmp_path.
#
# Version: v0.7.438 · Build: 438 · 2026-07-19
# =============================================================================

import importlib.util
import getpass
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from maintenance import (AckFile, MaintenancePaths, PresenceBeacon,
                         ServerRegistration, WindowFlag)
from maintenance.cli_support import (exklusiv_pruefen, quiesce_status,
                                     ziel_pfade, ziel_zu_pfad)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _lade(relpfad: str, name: str):
    spec = importlib.util.spec_from_file_location(name, _REPO_ROOT / relpfad)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


maint = _lade("tools/maintenance.py", "maint_cli_tool")
killer = _lade("tools/maintenance_kill.py", "maint_kill_tool")


def _baue_berechtigte_coordinator(pfad: Path) -> None:
    """
    Minimale coordinator.db, die den AKTUELLEN OS-Benutzer fuer
    'wartung.durchfuehren' berechtigt (Rolle maintenance + Grant). Damit
    passieren die enter/exit/kill-Tests das RBAC-Gate (Build 439). Es sind nur
    die Tabellen enthalten, die IdentityResolver + RbacResolver lesen.
    """
    con = sqlite3.connect(str(pfad))
    con.executescript(
        "CREATE TABLE person (id INTEGER PRIMARY KEY, system_username TEXT "
        "UNIQUE, display_name TEXT, is_investigator INT, is_supervisor INT, "
        "is_support INT, created_at INT);"
        "CREATE TABLE person_role (id INTEGER PRIMARY KEY, person_id INT, "
        "role_code TEXT, revoked_at INT);"
        "CREATE TABLE rbac_grant (id INTEGER PRIMARY KEY, role_code TEXT, "
        "capability_code TEXT, scope TEXT, revoked_at INT);"
    )
    con.execute("INSERT INTO person VALUES (5, ?, 'CLI', 1, 0, 0, 0)",
                (getpass.getuser(),))
    con.execute("INSERT INTO person_role (person_id, role_code, revoked_at) "
                "VALUES (5, 'maintenance', NULL)")
    con.execute("INSERT INTO rbac_grant (role_code, capability_code, scope, "
                "revoked_at) VALUES ('maintenance', 'wartung.durchfuehren', "
                "NULL, NULL)")
    con.commit()
    con.close()


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    (d / "evidence").mkdir(parents=True)
    # coordinator.db dient sowohl als Ziel des Lock-Beweises als auch als
    # RBAC-Quelle (Build 439): der aktuelle OS-Benutzer ist berechtigt.
    _baue_berechtigte_coordinator(d / "coordinator.db")
    return d


# -----------------------------------------------------------------------------
# 1) cli_support — Ziel-Pfade
# -----------------------------------------------------------------------------

def test_ziel_zu_pfad(data_dir):
    assert ziel_zu_pfad(data_dir, "coordinator") == data_dir / "coordinator.db"
    assert ziel_zu_pfad(data_dir, "evidence:1488") == data_dir / "evidence" / "evidence_1488.db"
    assert ziel_zu_pfad(data_dir, "templates") == data_dir / "templates.db"
    assert ziel_zu_pfad(data_dir, "all") is None


def test_ziel_pfade_all_nimmt_toplevel(data_dir):
    (data_dir / "default.db").touch()
    pfade = ziel_pfade(data_dir, ["all"])
    namen = {p.name for p in pfade}
    assert "coordinator.db" in namen and "default.db" in namen


# -----------------------------------------------------------------------------
# 2) cli_support — Exklusiv-Lock-Beweis
# -----------------------------------------------------------------------------

def test_exklusiv_frei_und_gesperrt(data_dir):
    db = data_dir / "coordinator.db"
    ok, _ = exklusiv_pruefen(db)
    assert ok is True

    halter = sqlite3.connect(str(db))
    halter.execute("BEGIN EXCLUSIVE")
    try:
        ok, grund = exklusiv_pruefen(db, timeout_s=0.5)
        assert ok is False and "locked" in grund.lower()
    finally:
        halter.rollback()
        halter.close()

    ok, _ = exklusiv_pruefen(db)
    assert ok is True


def test_exklusiv_nicht_vorhanden_ist_ok(data_dir):
    ok, grund = exklusiv_pruefen(data_dir / "gibtsnicht.db")
    assert ok is True and "nicht vorhanden" in grund


# -----------------------------------------------------------------------------
# 3) cli_support — Quiesce-Status
# -----------------------------------------------------------------------------

def test_quiesce_status_klassifiziert(data_dir):
    paths = MaintenancePaths(data_dir)
    paths.verzeichnisse_anlegen()
    # zwei lebende Server ohne ACK
    PresenceBeacon("webserver:1", "h", 1, 436).schreiben(paths)
    PresenceBeacon("webserver:2", "h", 2, 436).schreiben(paths)
    # Server 1 hat geackt fuer Fenster W1
    AckFile("webserver:1", "h", 1, window_id="W1").schreiben(paths)
    st = quiesce_status(paths, "W1", stale_s=30)
    assert {b.role for b in st["gequiesct"]} == {"webserver:1"}
    assert {b.role for b in st["offen"]} == {"webserver:2"}
    assert st["tot"] == []


def test_quiesce_status_veraltet_ist_tot(data_dir):
    paths = MaintenancePaths(data_dir)
    paths.verzeichnisse_anlegen()
    b = PresenceBeacon("webserver:9", "h", 9, 436, letzter_touch=1000)
    b.schreiben(paths)   # setzt letzter_touch auf jetzt -> muss ueberschrieben werden
    # Datei manuell auf alt setzen: neu schreiben mit altem letzter_touch
    from maintenance.atomic_io import schreibe_json_atomar
    d = b.to_dict(); d["letzter_touch"] = 1000
    schreibe_json_atomar(b.datei(paths), d)
    st = quiesce_status(paths, "W1", stale_s=30, jetzt=2000)
    assert {x.role for x in st["tot"]} == {"webserver:9"}


# -----------------------------------------------------------------------------
# 4) tools/maintenance.py — enter/status/exit
# -----------------------------------------------------------------------------

def test_enter_ohne_server_freigegeben(data_dir):
    rc = maint.main(["enter", "--reason", "T", "--ziel", "coordinator",
                     "--wait-timeout", "0", "--data-dir", str(data_dir)])
    assert rc == 0
    # Fenster ist gesetzt
    assert WindowFlag.laden(MaintenancePaths(data_dir)) is not None


def test_enter_mit_nachzuegler_rc2(data_dir):
    paths = MaintenancePaths(data_dir)
    paths.verzeichnisse_anlegen()
    PresenceBeacon("webserver:7", "h", 7, 436).schreiben(paths)   # lebt, keine ACK
    rc = maint.main(["enter", "--reason", "T", "--ziel", "coordinator",
                     "--wait-timeout", "0", "--data-dir", str(data_dir)])
    assert rc == 2   # Nachzuegler -> nicht freigegeben, Fenster bleibt aktiv
    assert WindowFlag.aktives_fenster(paths) is not None


def test_enter_verweigert_bei_aktivem_fenster(data_dir):
    maint.main(["enter", "--reason", "A", "--ziel", "coordinator",
                "--wait-timeout", "0", "--data-dir", str(data_dir)])
    rc = maint.main(["enter", "--reason", "B", "--ziel", "coordinator",
                     "--wait-timeout", "0", "--data-dir", str(data_dir)])
    assert rc == 1   # bereits aktiv


def test_exit_entfernt_fenster(data_dir):
    maint.main(["enter", "--reason", "T", "--ziel", "coordinator",
                "--wait-timeout", "0", "--data-dir", str(data_dir)])
    rc = maint.main(["exit", "--data-dir", str(data_dir)])
    assert rc == 0
    assert WindowFlag.laden(MaintenancePaths(data_dir)) is None


def test_status_laeuft(data_dir, capsys):
    maint.main(["enter", "--reason", "T", "--ziel", "coordinator",
                "--wait-timeout", "0", "--data-dir", str(data_dir)])
    rc = maint.main(["status", "--data-dir", str(data_dir)])
    assert rc == 0
    assert "AKTIV" in capsys.readouterr().out


# -----------------------------------------------------------------------------
# 5) tools/maintenance_kill.py
# -----------------------------------------------------------------------------

def test_kill_list(data_dir, capsys):
    paths = MaintenancePaths(data_dir)
    paths.verzeichnisse_anlegen()
    ServerRegistration.neu("webserver:1488", "h", 1, 436, "W1").schreiben(paths)
    rc = killer.main(["--list", "--data-dir", str(data_dir)])
    assert rc == 0
    assert "webserver:1488" in capsys.readouterr().out


def test_kill_setzt_flag_und_meldet_nachzuegler(data_dir):
    paths = MaintenancePaths(data_dir)
    paths.verzeichnisse_anlegen()
    reg = ServerRegistration.neu("webserver:1488", "h", 1, 436, "W1")
    reg.schreiben(paths)
    # Server reagiert NICHT -> wait-timeout 0 -> rc 2, aber Kill-Flag ist gesetzt
    rc = killer.main(["--uuid", reg.uuid, "--wait-timeout", "0",
                      "--data-dir", str(data_dir)])
    assert rc == 2
    assert ServerRegistration.laden(paths, reg.uuid).kill_angefordert is True


def test_kill_bestaetigt_wenn_server_verschwindet(data_dir):
    paths = MaintenancePaths(data_dir)
    paths.verzeichnisse_anlegen()
    reg = ServerRegistration.neu("webserver:1488", "h", 1, 436, "W1")
    reg.schreiben(paths)

    def entferne_spaeter():
        time.sleep(0.3)
        reg.entfernen(paths)          # simuliert die Selbstbeendigung des Servers

    t = threading.Thread(target=entferne_spaeter)
    t.start()
    rc = killer.main(["--uuid", reg.uuid, "--wait-timeout", "5",
                      "--data-dir", str(data_dir)])
    t.join(timeout=5)
    assert rc == 0                     # Verschwinden der Anmeldung = Bestaetigung


def test_kill_unbekannte_uuid(data_dir):
    paths = MaintenancePaths(data_dir)
    paths.verzeichnisse_anlegen()
    ServerRegistration.neu("webserver:1", "h", 1, 436, "W1").schreiben(paths)
    rc = killer.main(["--uuid", "gibt-es-nicht", "--wait-timeout", "0",
                      "--data-dir", str(data_dir)])
    assert rc == 1                     # keine der UUIDs angemeldet
