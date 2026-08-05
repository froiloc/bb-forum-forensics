# =============================================================================
# tests/test_poc_m019_sperrliste.py
# IT-Forensisches Ermittlungswerkzeug - Wartungsvorbehalt (Build 686)
# =============================================================================
# Prueft die Sperrliste von tools/poc_m019_weg_a.py.
#
# WORUM ES GEHT: Das Werkzeug benennt neun Spalten einer coordinator.db um -
# in EINER Transaktion, ohne Rueckspielweg. Sein Kopf sagt seit Build 469 zu,
# es arbeite "NUR auf der uebergebenen Datei - niemals auf der Produktions-DB
# selbst"; sein eigener Kommentar sagte zugleich, dass nichts das durchsetzt.
#
# STATT EINES WARTUNGSVORBEHALTS bekommt es eine Sperrliste (Entscheidung
# Alex, 2026-08-05): Das Werkzeug SOLL auf einer Wegwerfkopie laufen: fuer
# eine Wegwerfkopie ein Wartungsfenster zu verlangen waere Reibung ohne
# Schutzgewinn - und es schuetzte gerade nicht vor dem wirklichen Fehlgriff,
# naemlich das Werkzeug auf die echte Datei zu richten.
#
# PM01 - die produktive coordinator.db wird abgewiesen (Rueckgabewert 3)
# PM02 - und dabei wird sie NICHT einmal geoeffnet
# PM03 - ein anderer Pfad wird nicht abgewiesen
# PM04 - ohne lesbare config.yaml greift die Sperre nicht (und das ist Absicht)
# PM05 - der Abbruch sagt, WIE man zu einer Kopie kommt
#
# Version: v0.8.686 - Build: 686 - 2026-08-05
# =============================================================================

import importlib.util
import os
import sqlite3
import sys
from pathlib import Path

import pytest

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))


def _lade():
    spec = importlib.util.spec_from_file_location(
        "poc_m019_weg_a", _WURZEL / "tools" / "poc_m019_weg_a.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def anlage(tmp_path, monkeypatch):
    """Ein Wegwerf-Bestand samt config.yaml, in dem gearbeitet wird."""
    (tmp_path / "data").mkdir()
    prod = tmp_path / "data" / "coordinator.db"
    con = sqlite3.connect(str(prod))
    con.execute("CREATE TABLE cases (user_id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()
    (tmp_path / "config.yaml").write_text(
        "paths:\n  coordinator_db: %s\n" % prod, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path, prod


def test_pm01_die_produktive_datenbank_wird_abgewiesen(anlage, capsys, monkeypatch):
    """PM01 - Rueckgabewert 3, und der Grund steht in der Ausgabe."""
    _tmp, prod = anlage
    mod = _lade()
    monkeypatch.setattr(sys, "argv", ["poc_m019_weg_a.py", str(prod)])
    rc = mod.main()
    assert rc == 3
    ausgabe = capsys.readouterr().out
    assert "PRODUKTIVE" in ausgabe
    assert str(prod) in ausgabe


def test_pm02_die_datei_wird_nicht_einmal_geoeffnet(anlage, capsys, monkeypatch):
    """
    PM02 - der Abbruch kommt VOR dem sqlite3.connect.

    DAS IST DER UNTERSCHIED ZWISCHEN EINER SPERRE UND EINER WARNUNG. Ein
    Abbruch nach dem Verbindungsaufbau haette die Datei bereits angefasst -
    und bei einem liegengebliebenen Journal rollt SQLite es beim Oeffnen
    zurueck (gemessen 2026-08-01: aus 34 MB werden 0 Byte).
    """
    _tmp, prod = anlage
    mod = _lade()

    geoeffnet = []
    echt = sqlite3.connect

    def _merken(*a, **kw):
        geoeffnet.append(a[0] if a else kw.get("database"))
        return echt(*a, **kw)

    monkeypatch.setattr(mod.sqlite3, "connect", _merken)
    monkeypatch.setattr(sys, "argv", ["poc_m019_weg_a.py", str(prod)])
    rc = mod.main()
    assert rc == 3
    assert geoeffnet == [], "Die Datei wurde geoeffnet: %s" % geoeffnet


def test_pm03_eine_kopie_wird_nicht_abgewiesen(anlage, capsys, monkeypatch):
    """
    PM03 - die Sperre trifft GENAU eine Datei und nicht jede.

    Ohne diese Gegenprobe koennte die Sperre alles abweisen und PM01 bliebe
    gruen - ein Schutz, der auch das Erlaubte verhindert, wird umgangen.
    """
    tmp, prod = anlage
    kopie = tmp / "kopie.db"
    con = sqlite3.connect(str(kopie))
    con.execute("CREATE TABLE cases (user_id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()

    mod = _lade()
    monkeypatch.setattr(sys, "argv", ["poc_m019_weg_a.py", str(kopie)])
    # DER LAUF KOMMT AN DER SPERRE VORBEI und scheitert erst weiter hinten
    # an den fehlenden Tabellen dieses Wegwerf-Bestands. Genau das ist die
    # Aussage: die Sperre hat ihn nicht angehalten. Die OperationalError
    # gehoert zum Aufbau des Tests und nicht zum Befund - deshalb wird sie
    # ausdruecklich erwartet und nicht verschwiegen.
    with pytest.raises(sqlite3.OperationalError):
        mod.main()
    ausgabe = capsys.readouterr().out
    assert "PRODUKTIVE" not in ausgabe
    assert "PoC Weg A" in ausgabe, (
        "Der Lauf ist gar nicht erst angelaufen - dann sagt dieser Test "
        "nichts ueber die Sperrliste aus.")


def test_pm04_ohne_config_greift_die_sperre_nicht(tmp_path, monkeypatch, capsys):
    """
    PM04 - keine lesbare config.yaml, keine Sperre. UND DAS IST ABSICHT.

    Dieses Werkzeug wird auf Wegwerfkopien gefahren, oft ausserhalb der
    Anlage. Wer es dort mit einer unlesbaren Konfiguration abwiese, machte
    den Nachweislauf unmoeglich, ohne irgendetwas zu schuetzen. Die Grenze
    des Schutzes gehoert ausgesprochen - deshalb steht sie hier als Test und
    nicht nur als Satz im Dateikopf.
    """
    monkeypatch.chdir(tmp_path)
    mod = _lade()
    assert mod._produktivpfad() == ""


def test_pm05_der_abbruch_sagt_wie_man_zu_einer_kopie_kommt(
        anlage, capsys, monkeypatch):
    """
    PM05 - die Meldung nennt den Weg, nicht nur das Verbot.

    Ein Abbruch, der jemanden ratlos zuruecklaesst, wird umgangen: dann
    kopiert man eben irgendwie, und die naechste Frage ist, ob die Kopie
    konsistent war. Deshalb steht 'VACUUM INTO' in der Meldung.
    """
    _tmp, prod = anlage
    mod = _lade()
    monkeypatch.setattr(sys, "argv", ["poc_m019_weg_a.py", str(prod)])
    mod.main()
    ausgabe = capsys.readouterr().out
    assert "VACUUM INTO" in ausgabe
    assert "kopie.db" in ausgabe
