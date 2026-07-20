# =============================================================================
# tests/test_startup_journal_stamps.py
# IT-Forensisches Ermittlungswerkzeug — Tests zu StartupChecker._check_journal_stamps
# =============================================================================
# Prueft die Fruehwarnung aus Build 409 gegen die ECHTE Pruefmethode.
#
# Der Netzlaufwerk-Zustand laesst sich in der Testumgebung nicht herstellen. Er
# wird an der einzigen Stelle simuliert, an der er sich fuer den Code aeussert:
# 'is_network_path()'. Alles andere — echte SQLite-Dateien, echte Header-Bytes,
# echte Pruefmethode — bleibt unveraendert.
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import core.startup_checks as sc
from core.startup_checks import StartupCheckError, StartupChecker


class KonfigAttrappe:
    """Verhaelt sich wie ConfigLoader.get(key, default)."""

    def __init__(self, werte=None) -> None:
        self._werte = werte or {}

    def get(self, key, default=None):
        return self._werte.get(key, default)


def _db(pfad: Path, wal: bool) -> Path:
    con = sqlite3.connect(str(pfad))
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t (x)")
    con.commit()
    con.close()
    return pfad


@pytest.fixture
def umgebung(tmp_path):
    """forensic (WAL) + evidence/default/coordinator (rollback) — wie auf S:\\."""
    ctx = SimpleNamespace(
        mode="cli",
        subject_id=9,
        forensic_db=_db(tmp_path / "forensic_9.db", wal=False),
        evidence_db=_db(tmp_path / "evidence_9.db", wal=False),
        default_db=_db(tmp_path / "default.db", wal=False),
        coordinator_db=_db(tmp_path / "coordinator.db", wal=False),
        assets_db=None,
    )
    return ctx, tmp_path


def test_alles_rollback_gestempelt_laeuft_durch(umgebung, monkeypatch):
    ctx, _ = umgebung
    monkeypatch.setattr(sc, "is_network_path", lambda p: True)   # Netzlaufwerk
    StartupChecker(ctx, KonfigAttrappe())._check_journal_stamps()  # kein Fehler


def test_wal_gestempelte_db_auf_netzlaufwerk_bricht_mit_klartext_ab(umgebung, monkeypatch):
    ctx, tmp = umgebung
    # Genau der reale Fall: EINE Datei blieb WAL-gestempelt (evidence_524888.db).
    ctx.evidence_db.unlink()
    _db(ctx.evidence_db, wal=True)
    monkeypatch.setattr(sc, "is_network_path", lambda p: True)

    with pytest.raises(StartupCheckError) as exc:
        StartupChecker(ctx, KonfigAttrappe())._check_journal_stamps()

    text = str(exc.value)
    assert "evidence_db" in text
    assert "convert_journal_mode.py" in text          # Handlungsanweisung, kein Raetsel
    assert "--apply" in text


def test_wal_gestempelte_db_auf_lokaler_platte_ist_kein_fehler(umgebung, monkeypatch):
    ctx, _ = umgebung
    ctx.evidence_db.unlink()
    _db(ctx.evidence_db, wal=True)
    monkeypatch.setattr(sc, "is_network_path", lambda p: False)  # lokale Platte
    # Auf lokaler Platte ist WAL voellig in Ordnung — kein Fehlalarm.
    StartupChecker(ctx, KonfigAttrappe())._check_journal_stamps()


def test_unbekannte_laufwerksart_loest_keinen_fehlalarm_aus(umgebung, monkeypatch):
    ctx, _ = umgebung
    ctx.evidence_db.unlink()
    _db(ctx.evidence_db, wal=True)
    monkeypatch.setattr(sc, "is_network_path", lambda p: None)   # nicht entscheidbar
    StartupChecker(ctx, KonfigAttrappe())._check_journal_stamps()


def test_erzwungenes_wal_auf_netzlaufwerk_bricht_ab(umgebung, monkeypatch):
    ctx, _ = umgebung
    monkeypatch.setattr(sc, "is_network_path", lambda p: True)
    cfg = KonfigAttrappe({"db.journal_mode": "wal"})
    with pytest.raises(StartupCheckError) as exc:
        StartupChecker(ctx, cfg)._check_journal_stamps()
    assert "journal_mode" in str(exc.value)


def test_pruefung_laeuft_vor_dem_ersten_sqlite_zugriff():
    """
    Reihenfolge in run_all(): der Stempel-Check MUSS vor Schema- und
    Integritaetspruefung stehen — beide oeffnen die forensic_db per SQLite und
    wuerden auf einem Netzlaufwerk mit rohem 'disk I/O error' abbrechen.
    Geprueft wird der echte Quelltext von run_all(), nicht ein Nachbau.
    """
    import inspect

    quelltext = inspect.getsource(StartupChecker.run_all)
    pos_stempel = quelltext.index("_check_journal_stamps")
    pos_schema = quelltext.index("_check_forensic_db_schema_version")
    pos_integritaet = quelltext.index("_check_forensic_db_integrity")
    assert pos_stempel < pos_schema < pos_integritaet
