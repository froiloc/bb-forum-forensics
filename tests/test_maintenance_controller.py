# =============================================================================
# tests/test_maintenance_controller.py
# IT-Forensisches Ermittlungswerkzeug — Tests zu Gate/Controller/Poller
# =============================================================================
# Prueft die Wartungslogik der Webserver-Integration (Build 436) OHNE echten
# HTTP-Server/DB: Gate-Drain, die Entscheidungslogik des Controllers gegen echte
# Flag-Dateien und den Poller-Zyklus mit Fake-Callbacks.
#
# Version: v0.7.436 · Build: 436 · 2026-07-19
# =============================================================================

import threading
import time

import pytest

from maintenance import (Aktion, MaintenanceController, MaintenanceGate,
                         MaintenancePaths, MaintenancePoller, ServerRegistration,
                         WindowFlag)


@pytest.fixture
def paths(tmp_path):
    p = MaintenancePaths(tmp_path / "data")
    p.verzeichnisse_anlegen()
    return p


# -----------------------------------------------------------------------------
# 1) MaintenanceGate — enter/leave, Blockade, Drain
# -----------------------------------------------------------------------------

def test_gate_enter_leave():
    g = MaintenanceGate()
    assert g.enter() is True
    assert g.inflight == 1
    g.leave()
    assert g.inflight == 0


def test_gate_blockiert_weist_ab_und_drained():
    g = MaintenanceGate()
    assert g.enter() is True                      # in-flight 1
    assert g.block_and_drain(timeout=0.05) is False   # noch in-flight -> Timeout
    assert g.is_blocked() is True
    assert g.enter() is False                     # neue Requests -> 503
    g.leave()                                     # in-flight 0
    assert g.block_and_drain(timeout=0.05) is True    # jetzt ausgetrudelt
    g.unblock()
    assert g.enter() is True
    g.leave()


def test_gate_drain_wird_durch_leave_geweckt():
    g = MaintenanceGate()
    g.enter()
    ergebnis = {}

    def drain():
        ergebnis["ok"] = g.block_and_drain(timeout=2.0)

    t = threading.Thread(target=drain)
    t.start()
    time.sleep(0.05)
    g.leave()                                     # weckt den Drain-Warter
    t.join(timeout=2.0)
    assert ergebnis["ok"] is True


# -----------------------------------------------------------------------------
# 2) MaintenanceController — Normalserver
# -----------------------------------------------------------------------------

def test_controller_kein_fenster_keine_aktion(paths):
    c = MaintenanceController(paths, own_build=436)
    assert c.naechste_aktion() == Aktion.KEINE


def test_controller_pause_dann_resume(paths):
    c = MaintenanceController(paths, own_build=436)
    WindowFlag.neu("op", "Wartung", ["all"], bei_aktivierung="pause").schreiben(paths)
    assert c.naechste_aktion() == Aktion.QUIESCE_PAUSE
    assert c.state == MaintenanceController.QUIESCED
    assert c.naechste_aktion() == Aktion.KEINE          # Fenster besteht weiter
    WindowFlag.entfernen(paths)
    assert c.naechste_aktion() == Aktion.RESUME
    assert c.state == MaintenanceController.LAEUFT


def test_controller_beenden(paths):
    c = MaintenanceController(paths, own_build=436)
    WindowFlag.neu("op", "Migration", ["all"], bei_aktivierung="beenden").schreiben(paths)
    assert c.naechste_aktion() == Aktion.QUIESCE_BEENDEN


def test_controller_versionswaechter(paths):
    # Eigener Build 435 < min_build 440 -> nach Fensterende BEENDEN statt RESUME.
    c = MaintenanceController(paths, own_build=435)
    WindowFlag.neu("op", "Migration", ["all"], bei_aktivierung="pause",
                   min_build=440).schreiben(paths)
    assert c.naechste_aktion() == Aktion.QUIESCE_PAUSE
    WindowFlag.entfernen(paths)
    assert c.naechste_aktion() == Aktion.BEENDEN_VERSIONSWAECHTER


def test_controller_abgelaufenes_fenster_ist_inaktiv(paths):
    c = MaintenanceController(paths, own_build=436)
    WindowFlag.neu("op", "x", ["all"], ablauf_am=1000).schreiben(paths)
    # jetzt=2000 -> Fenster abgelaufen -> als gaebe es keins
    assert c.naechste_aktion(jetzt=2000) == Aktion.KEINE


# -----------------------------------------------------------------------------
# 3) MaintenanceController — --maintenance-Test-Server
# -----------------------------------------------------------------------------

def test_controller_maintenance_laeuft_und_selbstbeendigung(paths):
    WindowFlag.neu("op", "Wartung", ["all"]).schreiben(paths)
    c = MaintenanceController(paths, own_build=436, im_wartungsmodus_gestartet=True)
    assert c.naechste_aktion() == Aktion.KEINE       # Fenster aktiv -> normal
    WindowFlag.entfernen(paths)
    assert c.naechste_aktion() == Aktion.SELBSTBEENDIGUNG_FENSTERENDE


def test_controller_maintenance_kill(paths):
    WindowFlag.neu("op", "Wartung", ["all"]).schreiben(paths)
    reg = ServerRegistration.neu("webserver:1488", "h", 1, 436, "W1")
    reg.schreiben(paths)
    c = MaintenanceController(paths, own_build=436, im_wartungsmodus_gestartet=True,
                              registration=reg)
    assert c.naechste_aktion() == Aktion.KEINE
    # Kill anfordern (wie das Kill-Werkzeug es tut)
    ServerRegistration.laden(paths, reg.uuid).kill_anfordern(paths, von="supervisor")
    assert c.naechste_aktion() == Aktion.KILL


# -----------------------------------------------------------------------------
# 4) MaintenancePoller — Zyklus mit Fake-Callbacks (Voll-Ablauf)
# -----------------------------------------------------------------------------

def test_poller_ruft_richtige_callbacks_und_touch(paths):
    aufrufe = []
    touches = {"n": 0}

    def touch():
        touches["n"] += 1

    aktionen = {
        Aktion.QUIESCE_PAUSE: lambda: aufrufe.append("quiesce_pause"),
        Aktion.RESUME: lambda: aufrufe.append("resume"),
    }
    c = MaintenanceController(paths, own_build=436)
    poller = MaintenancePoller(c, intervall_s=999, aktionen=aktionen,
                               on_touch=touch)

    # 1. kein Fenster -> KEINE, aber on_touch laeuft
    assert poller.tick() == Aktion.KEINE
    assert touches["n"] == 1

    # 2. Pause-Fenster -> QUIESCE_PAUSE-Callback
    WindowFlag.neu("op", "Wartung", ["all"], bei_aktivierung="pause").schreiben(paths)
    assert poller.tick() == Aktion.QUIESCE_PAUSE
    assert aufrufe == ["quiesce_pause"]

    # 3. Fenster besteht -> KEINE
    assert poller.tick() == Aktion.KEINE

    # 4. Fenster weg -> RESUME-Callback
    WindowFlag.entfernen(paths)
    assert poller.tick() == Aktion.RESUME
    assert aufrufe == ["quiesce_pause", "resume"]
    assert touches["n"] == 4


def test_poller_unbekannte_aktion_kein_absturz(paths):
    # Keine Callback fuer QUIESCE_BEENDEN registriert -> darf nicht abstuerzen.
    c = MaintenanceController(paths, own_build=436)
    WindowFlag.neu("op", "x", ["all"], bei_aktivierung="beenden").schreiben(paths)
    poller = MaintenancePoller(c, intervall_s=999, aktionen={})
    assert poller.tick() == Aktion.QUIESCE_BEENDEN   # gemeldet, kein Crash
