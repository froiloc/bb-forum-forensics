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
# 1) WAL-VERBOT (Build 499): 'auto' liefert NIE WAL — direkt der Rollback-Modus.
#    (Frueher lieferte 'auto' auf lokaler Platte WAL; das ist projektweit
#     abgeschafft, weil das PROD-Citrix-Laufwerk sich als lokal tarnt.)
# -----------------------------------------------------------------------------

def test_auto_setzt_delete_nicht_wal(db):
    con, pfad = db
    # Selbst auf lokaler Platte (wo WAL frueher gesetzt wurde): jetzt delete.
    assert apply_journal_mode(con, pfad, mode="auto") == "delete"
    assert aktiv(con) == "delete"


def test_auto_versucht_KEIN_wal_mehr(db):
    # Die Netzlaufwerk-Attrappe wirft NUR bei 'journal_mode=wal'. Wenn 'auto'
    # kein WAL mehr versucht, wird sie GAR NICHT ausgeloest (wal_versuche == 0).
    con, pfad = db
    fake = NetzlaufwerkConnection(con)
    ergebnis = apply_journal_mode(fake, pfad, mode="auto", fallback="delete")
    assert ergebnis == "delete"
    assert aktiv(con) == "delete"
    assert fake.wal_versuche == 0        # <-- WAL wird NICHT (mehr) versucht


def test_rueckfall_auf_truncate_ist_konfigurierbar(db):
    con, pfad = db
    assert apply_journal_mode(con, pfad, mode="auto", fallback="truncate") == "truncate"
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


def test_auto_setzt_delete_und_liest_delete_zurueck(db):
    # 'auto' setzt delete; die Attrappe meldet delete zurueck -> uebernommen.
    ergebnis = apply_journal_mode(
        StillIgnorierendeConnection(), "x.db", mode="auto", fallback="delete"
    )
    assert ergebnis == "delete"


# -----------------------------------------------------------------------------
# 3b) WAL-VERBOT: ein zurueckgelesenes 'wal' verweigert den Betrieb (Riegel).
#     Tritt real auf, wenn eine WAL-gestempelte Datei read-only geoeffnet wird:
#     das Setz-PRAGMA laeuft durch, aendert aber nichts -> aktiv bleibt 'wal'.
# -----------------------------------------------------------------------------

class WalHartnaeckigConnection:
    """PRAGMA laeuft fehlerfrei, aktiver Modus bleibt aber 'wal' (read-only WAL)."""

    def execute(self, sql: str, *args):
        return _Cursor(["wal"])


def test_riegel_verweigert_wenn_aktiv_wal_bleibt(db):
    with pytest.raises(JournalPolicyError) as exc:
        apply_journal_mode(WalHartnaeckigConnection(), "x.db", mode="delete")
    assert "WAL" in str(exc.value)
    assert "verweigert" in str(exc.value).lower() or "verboten" in str(exc.value).lower()


# -----------------------------------------------------------------------------
# 4) Expliziter Modus: kein Rueckfall, harter Fehler
# -----------------------------------------------------------------------------

def test_expliziter_modus_delete(db):
    con, pfad = db
    assert apply_journal_mode(con, pfad, mode="delete") == "delete"


def test_expliziter_modus_wal_ist_verboten(db):
    # Build 499: 'wal' ist projektweit verboten — apply weist ihn mit eigenem
    # Klartext ab, OHNE die DB anzufassen.
    con, pfad = db
    with pytest.raises(JournalPolicyError) as exc:
        apply_journal_mode(con, pfad, mode="wal")
    assert "verboten" in str(exc.value).lower() or "verweigert" in str(exc.value).lower()
    assert aktiv(con) != "wal"


def test_resolve_mode_verbietet_wal():
    # Build 499: db.journal_mode: 'wal' in der config -> harter Fehler.
    with pytest.raises(JournalPolicyError) as exc:
        resolve_mode(KonfigAttrappe({"db.journal_mode": "wal"}))
    assert "wal" in str(exc.value).lower()


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
        # Build 499: 'auto' setzt auch auf dem ATTACH-Alias delete, NICHT wal.
        assert apply_journal_mode(con, cdb, schema="cdb", mode="auto") == "delete"
        assert str(con.execute("PRAGMA cdb.journal_mode").fetchone()[0]).lower() == "delete"
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

