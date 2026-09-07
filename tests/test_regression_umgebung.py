# -*- coding: utf-8 -*-
"""
tests/test_regression_umgebung.py — BUILD 764

Zwei Waechter, die aus EINEM Regressionslauf entstanden sind (Alex,
07.09.2026): 65 Fehlschlaege und ein Sammelfehler, alle mit derselben Ursache
— das Temporaerverzeichnis war voll. Keine einzige Zusicherung ist gefallen.

Was der Lauf gezeigt hat:

1. DIE URSACHE KAM NICHT AN. Bei vollem Traeger schlaegt 'COMMIT' fehl; SQLite
   rollt die Transaktion dabei selbst zurueck. Das anschliessende 'ROLLBACK' im
   Fehlerzweig von MigrationRunner._apply() warf daraufhin 'cannot rollback -
   no transaction is active' und ERSETZTE die urspruengliche Ausnahme. 13 der
   65 Fehlschlaege nannten deshalb einen Grund, der nicht der Grund war.

2. DER LAUF HAETTE GAR NICHT STARTEN DUERFEN. Sechseinhalb Minuten Laufzeit fuer
   ein Ergebnis, das nichts ueber den Code aussagt — und in dem ein echter
   Fehlschlag zwischen den unechten untergegangen waere.

Kennungen: RU01 bis RU04.
"""
import os
import sqlite3
import sys
import types
from pathlib import Path

import pytest

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

from management.migrations.runner import MigrationRunner       # noqa: E402


class _ScheiterndeVerbindung:
    """
    Eine Verbindung, die bei 'COMMIT' scheitert und bei 'ROLLBACK' ebenfalls —
    genau die Lage bei vollem Datentraeger.
    """

    def __init__(self, con):
        self._con = con
        self.rollback_versucht = False

    def execute(self, sql, *args, **kwargs):
        oben = sql.strip().upper()
        if oben.startswith("COMMIT"):
            raise sqlite3.OperationalError("database or disk is full")
        if oben.startswith("ROLLBACK"):
            self.rollback_versucht = True
            raise sqlite3.OperationalError(
                "cannot rollback - no transaction is active")
        return self._con.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._con, name)


def _migrationsmodul(tmp_path):
    """Ein Migrationsmodul, das nichts tut ausser aufloesen zu koennen."""
    pfad = tmp_path / "m999_probe.py"
    pfad.write_text("def up(con):\n    pass\n", encoding="utf-8")
    mod = types.ModuleType("m999_probe")
    mod.VERSION = 999
    mod.NAME = "Probe"
    mod.KIND = "additive"
    mod.__file__ = str(pfad)
    mod.up = lambda con: None
    return mod


def test_RU01_die_wahre_ursache_ueberlebt_den_gescheiterten_rollback(tmp_path):
    """
    DER KERN. Scheitert 'COMMIT' und scheitert danach auch 'ROLLBACK', muss die
    Ausnahme, die beim Aufrufer ankommt, die von 'COMMIT' sein.

    Vor Build 764 kam 'cannot rollback - no transaction is active' an — eine
    Meldung, die von der Ursache wegfuehrt.
    """
    roh = sqlite3.connect(str(tmp_path / "p.db"))
    roh.isolation_level = None
    con = _ScheiterndeVerbindung(roh)
    laeufer = MigrationRunner(con, [], audit=None, deployed_by="probe")
    laeufer.ensure_registry()

    with pytest.raises(sqlite3.OperationalError) as gefangen:
        laeufer._apply(_migrationsmodul(tmp_path))

    assert "disk is full" in str(gefangen.value), str(gefangen.value)
    assert "cannot rollback" not in str(gefangen.value), str(gefangen.value)
    assert con.rollback_versucht, \
        "Der Rueckrollversuch muss weiterhin unternommen werden"


def test_RU02_gegenprobe_ein_gelingender_rollback_aendert_nichts(tmp_path):
    """
    OHNE DIESE PROBE waere RU01 auch mit einer Fassung gruen, die den
    Rueckrollversuch ganz weglaesst. Gelingt er, kommt trotzdem die
    urspruengliche Ausnahme an — und die Transaktion ist beendet.
    """
    class NurCommitScheitert(_ScheiterndeVerbindung):
        def execute(self, sql, *args, **kwargs):
            oben = sql.strip().upper()
            if oben.startswith("COMMIT"):
                raise sqlite3.OperationalError("database or disk is full")
            if oben.startswith("ROLLBACK"):
                self.rollback_versucht = True
                return self._con.execute("ROLLBACK")
            return self._con.execute(sql, *args, **kwargs)

    roh = sqlite3.connect(str(tmp_path / "p2.db"))
    roh.isolation_level = None
    con = NurCommitScheitert(roh)
    laeufer = MigrationRunner(con, [], audit=None, deployed_by="probe")
    laeufer.ensure_registry()

    with pytest.raises(sqlite3.OperationalError) as gefangen:
        laeufer._apply(_migrationsmodul(tmp_path))
    assert "disk is full" in str(gefangen.value), str(gefangen.value)
    assert con.rollback_versucht
    assert not roh.in_transaction, "keine offene Transaktion zurueckgelassen"


def test_RU03_vorpruefung_bricht_bei_zu_wenig_platz_ab(monkeypatch):
    """
    Die Vorpruefung meldet den Plattenmangel EINMAL und verstaendlich, statt
    ihn in Dutzenden Testfehlern erscheinen zu lassen.

    Die Schwelle wird so hoch gesetzt, dass sie auf jedem Bausystem greift —
    geprueft wird die Entscheidung, nicht der tatsaechliche Platz.
    """
    import tests.conftest as ct

    monkeypatch.setenv("AIW_TESTS_MIN_TMP_MB", str(10 ** 9))
    with pytest.raises(pytest.UsageError) as gefangen:
        ct.pytest_configure(None)
    meldung = str(gefangen.value)
    # Die Meldung muss den Grund tragen, nicht nur die Tatsache.
    assert "Temporaerverzeichnis" in meldung, meldung
    assert "MB frei" in meldung, meldung
    assert "AIW_TESTS_MIN_TMP_MB" in meldung, meldung


def test_RU04_gegenprobe_die_vorpruefung_laesst_sich_abschalten(monkeypatch):
    """
    OHNE DIESE PROBE waere RU03 auch mit einer Fassung gruen, die IMMER
    abbricht. Wer die Schwelle auf 0 setzt, faehrt ohne Vorpruefung — und ein
    normaler Wert laesst den Lauf ebenfalls durch.
    """
    import tests.conftest as ct

    monkeypatch.setenv("AIW_TESTS_MIN_TMP_MB", "0")
    ct.pytest_configure(None)          # darf nicht werfen

    monkeypatch.setenv("AIW_TESTS_MIN_TMP_MB", "1")
    ct.pytest_configure(None)          # 1 MB ist praktisch immer frei

    # Ein unbrauchbarer Wert faellt auf die Vorgabe zurueck und wirft nicht.
    monkeypatch.setenv("AIW_TESTS_MIN_TMP_MB", "keine Zahl")
    ct.pytest_configure(None)
