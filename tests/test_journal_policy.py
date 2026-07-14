# =============================================================================
# tests/test_journal_policy.py
# IT-Forensisches Ermittlungswerkzeug — Tests zu db/journal_policy.py
# =============================================================================
# Prueft die Journalmodus-Weiche (Build 408) gegen die ECHTE Funktion — kein
# Nachbau der Logik im Test ('gruen aber tot' vermeiden).
#
# Der Netzlaufwerk-Fall laesst sich in der Testumgebung nicht herstellen (dort
# gibt es kein SMB-Share). Er wird deshalb an der einzigen Stelle simuliert, an
# der er sich fuer den Code ueberhaupt aeussert: 'con.execute(...)' wirft bei
# 'journal_mode=WAL' einen sqlite3.OperationalError('disk I/O error'). Genau das
# ist der auf S:\ gemessene Fehler (extended code 8714). Alles andere in der
# Kette bleibt echt.
#
# Version: v0.7.408 · Build: 408 · 2026-07-14
# =============================================================================

import sqlite3

import pytest

from db.journal_policy import (
    JournalPolicyError,
    apply_journal_mode,
    is_network_path,
    journal_stamp,
    resolve_fallback,
    resolve_mode,
)


# -----------------------------------------------------------------------------
# Hilfsmittel
# -----------------------------------------------------------------------------

class NetzlaufwerkConnection:
    """
    Verbindungs-Attrappe: verhaelt sich wie eine echte sqlite3-Verbindung,
    laesst aber 'PRAGMA journal_mode=wal' mit 'disk I/O error' scheitern —
    so wie SQLite es auf einem UNC-Share tut (Shared Memory nicht verfuegbar).
    Alle anderen Anweisungen laufen gegen eine ECHTE SQLite-Verbindung.
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self.wal_versuche = 0

    def execute(self, sql: str, *args):
        if "journal_mode=wal" in sql.replace(" ", "").lower():
            self.wal_versuche += 1
            raise sqlite3.OperationalError("disk I/O error")
        return self._con.execute(sql, *args)


class LoggerAttrappe:
    """
    Sammelt die Log-Meldungen der Funktion.

    Build 409: Vorher nutzten diese Tests 'caplog'. Das ging in der Cloud-
    Umgebung gut, in der VM aber nicht: Der Projekt-Logger reicht seine Records
    nicht an den Root-Logger weiter (propagate=False), und caplog haengt am
    Root. Die Meldung KAM (sie stand im 'Captured stderr'), sie war fuer caplog
    nur unsichtbar. Der Test darf sich also nicht auf pytest-Interna stuetzen,
    sondern gibt der ECHTEN Funktion ueber ihren vorhandenen 'log'-Parameter
    einen eigenen Logger mit. Beleg: Regressionslauf VM 2026-07-14.
    """

    def __init__(self) -> None:
        self.meldungen: list[str] = []

    def _sammeln(self, msg, *args):
        self.meldungen.append(str(msg) % args if args else str(msg))

    warning = _sammeln
    info = _sammeln
    debug = _sammeln
    error = _sammeln

    @property
    def text(self) -> str:
        return " ".join(self.meldungen)


class KonfigAttrappe:
    """Minimale ConfigLoader-Attrappe (nur .get(key, default) wird benutzt)."""

    def __init__(self, werte: dict) -> None:
        self._werte = werte

    def get(self, key, default=None):
        return self._werte.get(key, default)


@pytest.fixture
def db(tmp_path):
    """Echte SQLite-Datei auf lokaler Platte."""
    pfad = tmp_path / "test.db"
    con = sqlite3.connect(str(pfad))
    yield con, pfad
    con.close()


def aktiv(con) -> str:
    return str(con.execute("PRAGMA journal_mode").fetchone()[0]).lower()


# -----------------------------------------------------------------------------
# 1) Regelfall (PROD, lokale Platte): 'auto' liefert WAL — unveraendertes Verhalten
# -----------------------------------------------------------------------------

def test_auto_setzt_wal_auf_lokaler_platte(db):
    con, pfad = db
    assert apply_journal_mode(con, pfad, mode="auto") == "wal"
    assert aktiv(con) == "wal"


# -----------------------------------------------------------------------------
# 2) Netzlaufwerk: WAL scheitert -> protokollierter Rueckfall auf DELETE
# -----------------------------------------------------------------------------

def test_auto_faellt_auf_delete_zurueck_wenn_wal_scheitert(db):
    con, pfad = db
    fake = NetzlaufwerkConnection(con)
    log = LoggerAttrappe()

    ergebnis = apply_journal_mode(fake, pfad, mode="auto", fallback="delete", log=log)

    assert ergebnis == "delete"
    assert aktiv(con) == "delete"        # echt zurueckgelesen, nicht behauptet
    assert fake.wal_versuche == 1        # WAL wurde zuerst versucht
    # Kein stiller Rueckfall (Grundregel 1):
    assert "WAL-Modus nicht verfuegbar" in log.text
    assert "disk I/O error" in log.text


def test_rueckfall_auf_truncate_ist_konfigurierbar(db):
    con, pfad = db
    fake = NetzlaufwerkConnection(con)
    assert apply_journal_mode(fake, pfad, mode="auto", fallback="truncate") == "truncate"
    assert aktiv(con) == "truncate"


# -----------------------------------------------------------------------------
# 3) 'gruen aber tot': PRAGMA laeuft durch, uebernimmt aber nicht
# -----------------------------------------------------------------------------

class StillIgnorierendeConnection:
    """PRAGMA wirft keinen Fehler, der Modus bleibt aber 'delete'."""

    def execute(self, sql: str, *args):
        return _Cursor(["delete"])


class _Cursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


def test_auto_erkennt_nicht_uebernommenes_wal_und_faellt_zurueck(db):
    con, pfad = db
    log = LoggerAttrappe()
    ergebnis = apply_journal_mode(
        StillIgnorierendeConnection(), pfad, mode="auto", fallback="delete", log=log
    )
    # WAL wurde fehlerfrei 'gesetzt', aktiv blieb 'delete' -> das ist der
    # Rueckfallfall, den ein reines try/except NICHT faengt.
    assert ergebnis == "delete"
    assert "aktiv blieb aber 'delete'" in log.text


# -----------------------------------------------------------------------------
# 4) Expliziter Modus: kein Rueckfall, harter Fehler
# -----------------------------------------------------------------------------

def test_expliziter_modus_delete(db):
    con, pfad = db
    assert apply_journal_mode(con, pfad, mode="delete") == "delete"


def test_expliziter_modus_wal_bricht_ab_wenn_er_scheitert(db):
    con, pfad = db
    fake = NetzlaufwerkConnection(con)
    with pytest.raises(JournalPolicyError) as exc:
        apply_journal_mode(fake, pfad, mode="wal")
    assert "Netzlaufwerk" in str(exc.value)     # Klartexthinweis liegt bei
    assert aktiv(con) != "wal"


def test_unzulaessiger_modus(db):
    con, pfad = db
    with pytest.raises(JournalPolicyError):
        apply_journal_mode(con, pfad, mode="memory")


# -----------------------------------------------------------------------------
# 5) ATTACH-Alias (schema='cdb')
# -----------------------------------------------------------------------------

def test_schema_praefix_wirkt_auf_attach(tmp_path):
    haupt = tmp_path / "main.db"
    cdb = tmp_path / "coordinator.db"
    sqlite3.connect(str(cdb)).close()

    con = sqlite3.connect(str(haupt))
    try:
        con.execute("ATTACH DATABASE ? AS cdb", (str(cdb),))
        assert apply_journal_mode(con, cdb, schema="cdb", mode="auto") == "wal"
        assert str(con.execute("PRAGMA cdb.journal_mode").fetchone()[0]).lower() == "wal"
        # main bleibt unberuehrt (Default 'delete')
        assert aktiv(con) == "delete"
    finally:
        con.close()


# -----------------------------------------------------------------------------
# 6) Konfigurationsaufloesung
# -----------------------------------------------------------------------------

def test_resolve_mode_default_ist_auto():
    assert resolve_mode(KonfigAttrappe({})) == "auto"
    assert resolve_fallback(KonfigAttrappe({})) == "delete"


def test_resolve_mode_liest_konfiguration():
    cfg = KonfigAttrappe({"db.journal_mode": "DELETE",
                          "db.journal_mode_fallback": "truncate"})
    assert resolve_mode(cfg) == "delete"          # Gross/Kleinschreibung egal
    assert resolve_fallback(cfg) == "truncate"


def test_resolve_mode_meldet_unfug_statt_ihn_still_zu_biegen():
    with pytest.raises(JournalPolicyError):
        resolve_mode(KonfigAttrappe({"db.journal_mode": "schnell"}))
    with pytest.raises(JournalPolicyError):
        resolve_fallback(KonfigAttrappe({"db.journal_mode_fallback": "off"}))


# -----------------------------------------------------------------------------
# 7) Netzpfad-Erkennung und Header-Stempel (Build 409)
# -----------------------------------------------------------------------------

def test_unc_pfad_gilt_als_netzlaufwerk():
    # Genau die Form des Testsystems (Diagnose 2026-07-14).
    assert is_network_path(r"\\KK31Storage15\Volume 1\aiw\data\x.db") is True
    assert is_network_path("//server/share/x.db") is True


def test_journal_stempel_wird_ohne_sqlite_gelesen(tmp_path):
    # Der Stempel MUSS ohne SQLite lesbar sein — eine WAL-DB auf dem Netzlaufwerk
    # laesst sich sonst gar nicht erst oeffnen.
    wal = tmp_path / "wal.db"
    con = sqlite3.connect(str(wal))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t (x)")
    con.commit()
    con.close()

    rollback = tmp_path / "rollback.db"
    con = sqlite3.connect(str(rollback))
    con.execute("CREATE TABLE t (x)")
    con.commit()
    con.close()

    keine_db = tmp_path / "kaputt.db"
    keine_db.write_bytes(b"kein sqlite")

    assert journal_stamp(wal) == 2
    assert journal_stamp(rollback) == 1
    assert journal_stamp(keine_db) is None
    assert journal_stamp(tmp_path / "gibtsnicht.db") is None

