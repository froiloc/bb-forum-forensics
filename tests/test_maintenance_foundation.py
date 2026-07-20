# =============================================================================
# tests/test_maintenance_foundation.py
# IT-Forensisches Ermittlungswerkzeug — Tests zum Wartungsmodus-Fundament
# =============================================================================
# Prueft das dateibasierte Steuerprotokoll (Build 435, maintenance/-Paket) gegen
# ECHTE Dateien in tmp_path: atomares Schreiben/Lesen, (De-)Serialisierung,
# Zustandslogik und das laute Melden kaputter Steuerdateien (Grundregel 1).
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import json
from pathlib import Path

import pytest

from maintenance import (AckFile, MaintenancePaths, MaintenanceProtocolError,
                         PresenceBeacon, ServerRegistration, WindowFlag)
from maintenance.atomic_io import lies_json, schreibe_json_atomar


@pytest.fixture
def paths(tmp_path):
    p = MaintenancePaths(tmp_path / "data")
    p.verzeichnisse_anlegen()
    return p


# -----------------------------------------------------------------------------
# 1) MaintenancePaths — Layout und Windows-sichere Dateinamen
# -----------------------------------------------------------------------------

def test_paths_layout(tmp_path):
    p = MaintenancePaths(tmp_path / "data")
    assert p.window_datei == tmp_path / "data" / "_maintenance" / "window.json"
    assert p.presence_dir.name == "presence"
    assert p.ack_dir.name == "ack"
    assert p.servers_dir.name == "servers"


def test_paths_dateiname_windows_sicher(paths):
    # ':' aus 'webserver:1488' ist unter NTFS in Dateinamen unzulaessig.
    f = paths.presence_datei("KKVM-1488", 12345, "webserver:1488")
    assert ":" not in f.name
    assert f.name == "KKVM-1488__12345__webserver-1488.json"
    a = paths.ack_datei("host", 1, "management")
    assert a.name == "host__1__management.ack"


# -----------------------------------------------------------------------------
# 2) atomic_io — Roundtrip, ASCII, kein Temp-Rest, laute Fehler
# -----------------------------------------------------------------------------

def test_atomar_roundtrip_und_ascii(tmp_path):
    ziel = tmp_path / "sub" / "x.json"
    schreibe_json_atomar(ziel, {"grund": "Umlaut-Test: \u00e4\u00f6\u00fc"})
    # Datei ist reines ASCII (ensure_ascii=True escaped Nicht-ASCII)
    roh = ziel.read_bytes()
    assert all(b < 128 for b in roh)
    assert lies_json(ziel)["grund"] == "Umlaut-Test: \u00e4\u00f6\u00fc"
    # Kein zurueckgebliebener Temp-Rest im Verzeichnis
    assert [x.name for x in ziel.parent.iterdir()] == ["x.json"]


def test_lies_json_fehlend_ist_none(tmp_path):
    assert lies_json(tmp_path / "gibtsnicht.json") is None


def test_lies_json_kaputt_meldet_laut(tmp_path):
    kaputt = tmp_path / "kaputt.json"
    kaputt.write_text("{ das ist kein json", encoding="ascii")
    with pytest.raises(MaintenanceProtocolError):
        lies_json(kaputt)


def test_lies_json_kein_objekt_meldet_laut(tmp_path):
    liste = tmp_path / "liste.json"
    liste.write_text("[1, 2, 3]", encoding="ascii")
    with pytest.raises(MaintenanceProtocolError):
        lies_json(liste)


# -----------------------------------------------------------------------------
# 3) WindowFlag — Erzeugung, Persistenz, Ablauf, Zielbereich, Validierung
# -----------------------------------------------------------------------------

def test_window_roundtrip(paths):
    w = WindowFlag.neu("H0A2898", "Umstempelung", ["coordinator"],
                       bei_aktivierung="beenden", min_build=433)
    w.schreiben(paths)
    w2 = WindowFlag.laden(paths)
    assert w2.window_id == w.window_id
    assert w2.bei_aktivierung == "beenden"
    assert w2.min_build == 433
    assert w2.ziel == ["coordinator"]


def test_window_entfernen_und_none(paths):
    assert WindowFlag.laden(paths) is None
    WindowFlag.neu("x", "y", ["all"]).schreiben(paths)
    assert WindowFlag.laden(paths) is not None
    WindowFlag.entfernen(paths)
    assert WindowFlag.laden(paths) is None


def test_window_ablauf(paths):
    w = WindowFlag.neu("x", "y", ["all"], ablauf_am=1000)
    assert w.ist_abgelaufen(jetzt=1001) is True
    assert w.ist_abgelaufen(jetzt=999) is False
    assert w.ist_aktiv(jetzt=999) is True


def test_window_aktives_fenster_beachtet_ablauf(paths):
    WindowFlag.neu("x", "y", ["all"], ablauf_am=1000).schreiben(paths)
    assert WindowFlag.aktives_fenster(paths, jetzt=999) is not None
    assert WindowFlag.aktives_fenster(paths, jetzt=1001) is None   # abgelaufen


def test_window_betrifft(paths):
    w = WindowFlag.neu("x", "y", ["coordinator", "evidence:1488"])
    assert w.betrifft("coordinator.db") is True
    assert w.betrifft("evidence_1488.db") is True
    assert w.betrifft("forensic_1488.db") is False
    assert WindowFlag.neu("x", "y", ["all"]).betrifft("irgendwas.db") is True


def test_window_ungueltige_aktivierung(paths):
    with pytest.raises(MaintenanceProtocolError):
        WindowFlag.neu("x", "y", ["all"], bei_aktivierung="loeschen")


def test_window_leeres_ziel(paths):
    with pytest.raises(MaintenanceProtocolError):
        WindowFlag.neu("x", "y", [])


def test_window_kaputte_datei_meldet_laut(paths):
    paths.window_datei.write_text('{"window_id": "x"}', encoding="ascii")  # Felder fehlen
    with pytest.raises(MaintenanceProtocolError):
        WindowFlag.laden(paths)


# -----------------------------------------------------------------------------
# 4) PresenceBeacon — Touch aktualisiert, Alter, alle_laden, Fehlersammler
# -----------------------------------------------------------------------------

def test_presence_touch_aktualisiert(paths):
    b = PresenceBeacon(role="management", host="h", pid=7, build=435,
                       letzter_touch=1000)
    b.schreiben(paths)      # setzt letzter_touch auf jetzt (>> 1000)
    geladen = PresenceBeacon.alle_laden(paths)
    assert len(geladen) == 1
    assert geladen[0].letzter_touch > 1000


def test_presence_ist_veraltet():
    b = PresenceBeacon(role="r", host="h", pid=1, build=435, letzter_touch=1000)
    assert b.ist_veraltet(max_alter_s=30, jetzt=1040) is True
    assert b.ist_veraltet(max_alter_s=30, jetzt=1020) is False


def test_presence_mehrere_und_entfernen(paths):
    PresenceBeacon("webserver:1", "h", 1, 435).schreiben(paths)
    PresenceBeacon("webserver:2", "h", 2, 435).schreiben(paths)
    assert len(PresenceBeacon.alle_laden(paths)) == 2
    b = PresenceBeacon("webserver:1", "h", 1, 435)
    b.entfernen(paths)
    assert len(PresenceBeacon.alle_laden(paths)) == 1


def test_presence_kaputte_datei_wird_gesammelt(paths):
    PresenceBeacon("webserver:1", "h", 1, 435).schreiben(paths)
    (paths.presence_dir / "muell.json").write_text("nicht json", encoding="ascii")
    # Ohne Sammler: laut
    with pytest.raises(MaintenanceProtocolError):
        PresenceBeacon.alle_laden(paths)
    # Mit Sammler: gueltige zurueck, kaputte gemeldet (GR1)
    fehler = []
    gueltig = PresenceBeacon.alle_laden(paths, fehler=fehler)
    assert len(gueltig) == 1
    assert len(fehler) == 1 and "muell.json" in str(fehler[0][0])


# -----------------------------------------------------------------------------
# 5) AckFile — Persistenz und Fensterbindung
# -----------------------------------------------------------------------------

def test_ack_roundtrip_und_fuer_fenster(paths):
    AckFile("webserver:1", "h", 1, window_id="W1").schreiben(paths)
    AckFile("webserver:2", "h", 2, window_id="W1").schreiben(paths)
    AckFile("management", "h", 3, window_id="W-ALT").schreiben(paths)
    assert len(AckFile.alle_laden(paths)) == 3
    nur_w1 = AckFile.fuer_fenster(paths, "W1")
    assert len(nur_w1) == 2
    assert all(a.window_id == "W1" for a in nur_w1)


# -----------------------------------------------------------------------------
# 6) ServerRegistration — Anmeldung, Laden, dateivermittelter Kill
# -----------------------------------------------------------------------------

def test_registration_roundtrip(paths):
    r = ServerRegistration.neu(role="webserver:1488", host="KKVM", pid=999,
                               build=435, window_id="W1", port=8409,
                               subject_id=1488, config="config-hello77.yaml")
    r.schreiben(paths)
    geladen = ServerRegistration.laden(paths, r.uuid)
    assert geladen is not None
    assert geladen.subject_id == 1488
    assert geladen.port == 8409
    assert geladen.kill_angefordert is False


def test_registration_kill_kanal(paths):
    r = ServerRegistration.neu(role="webserver:1488", host="KKVM", pid=999,
                               build=435, window_id="W1")
    r.schreiben(paths)
    # Server sieht zunaechst keinen Kill
    assert r.ist_kill_angefordert(paths) is False
    # Werkzeug-Seite fordert Kill an (laedt frisch, setzt Feld, schreibt neu)
    vom_werkzeug = ServerRegistration.laden(paths, r.uuid)
    vom_werkzeug.kill_anfordern(paths, von="supervisor")
    # Server-Seite erkennt den Kill beim naechsten Poll
    assert r.ist_kill_angefordert(paths) is True
    frisch = ServerRegistration.laden(paths, r.uuid)
    assert frisch.kill_angefordert is True
    assert frisch.kill_von == "supervisor"
    assert frisch.kill_am is not None


def test_registration_alle_laden_und_entfernen(paths):
    a = ServerRegistration.neu("webserver:1", "h", 1, 435, "W1")
    b = ServerRegistration.neu("webserver:2", "h", 2, 435, "W1")
    a.schreiben(paths)
    b.schreiben(paths)
    assert len(ServerRegistration.alle_laden(paths)) == 2
    a.entfernen(paths)
    assert len(ServerRegistration.alle_laden(paths)) == 1
    # Nach Entfernen meldet der Kill-Poll False (Datei weg = kein Auftrag)
    assert a.ist_kill_angefordert(paths) is False
