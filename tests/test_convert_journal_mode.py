# =============================================================================
# tests/test_convert_journal_mode.py
# IT-Forensisches Ermittlungswerkzeug — Tests zu tools/convert_journal_mode.py
# =============================================================================
# Prueft das Umstempel-Werkzeug (Build 408) gegen ECHTE SQLite-Dateien:
# es wird eine WAL-gestempelte forensic-DB mit gueltigem Siegel gebaut, umgestempelt
# und danach mit der Pruefroutine des SERVERS (StartupChecker) gegengeprueft.
# Kein Nachbau der Hash-Logik im Test.
#
# Kernaussage, die hier belegt wird:
#   Das Umstempeln aendert nur den Header-Stempel (Byte 18/19), NICHT den Inhalt.
#   Das Siegel der Beweismitteldatenbank bleibt gueltig — weil es inhaltsbasiert
#   ist (core/startup_checks.py, _compute_content_sha256).
#
# Version: v0.7.408 · Build: 408 · 2026-07-14
# =============================================================================

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from core.startup_checks import StartupChecker

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _lade_werkzeug():
    """
    Laedt tools/convert_journal_mode.py als Modul (tools/ ist kein Paket).
    Wichtig: es wird die ECHTE Datei geladen, die auch ausgeliefert wird.
    """
    pfad = _REPO_ROOT / "tools" / "convert_journal_mode.py"
    spec = importlib.util.spec_from_file_location("convert_journal_mode", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


werkzeug = _lade_werkzeug()


def _stempel(db: Path) -> int:
    """write_version aus dem SQLite-Header: 1 = Rollback-Journal, 2 = WAL."""
    with db.open("rb") as fh:
        return fh.read(100)[18]


@pytest.fixture
def datenverzeichnis(tmp_path):
    """
    Baut ein realistisches data/-Verzeichnis:
      forensic/forensic_9.db  — WAL-gestempelt, versiegelt, schreibgeschuetzt
      evidence/evidence_9.db  — WAL-gestempelt
      templates.db            — bereits Rollback-Journal (darf nicht angefasst werden)
    """
    data = tmp_path / "data"
    (data / "forensic").mkdir(parents=True)
    (data / "evidence").mkdir()

    forensic = data / "forensic" / "forensic_9.db"
    con = sqlite3.connect(str(forensic))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE pages (id INTEGER PRIMARY KEY, html TEXT)")
    con.execute("INSERT INTO pages VALUES (1, 'seite')")
    con.execute("CREATE TABLE forensic_meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO forensic_meta VALUES ('schema_version', '2')")
    con.commit()
    siegel = StartupChecker(None, None)._compute_content_sha256(con)
    con.execute("INSERT INTO forensic_meta VALUES ('sha256', ?)", (siegel,))
    con.commit()
    con.close()

    evidence = data / "evidence" / "evidence_9.db"
    con = sqlite3.connect(str(evidence))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE annotations (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()

    templates = data / "templates.db"
    con = sqlite3.connect(str(templates))
    con.execute("CREATE TABLE bausteine (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()

    return {"data": data, "forensic": forensic, "evidence": evidence,
            "templates": templates, "siegel": siegel}


# -----------------------------------------------------------------------------
# 1) Ausgangslage — genau die des Testsystems S:\ (Diagnose 2026-07-14)
# -----------------------------------------------------------------------------

def test_ausgangslage_ist_wal_gestempelt(datenverzeichnis):
    assert _stempel(datenverzeichnis["forensic"]) == 2
    assert _stempel(datenverzeichnis["evidence"]) == 2
    assert _stempel(datenverzeichnis["templates"]) == 1


# -----------------------------------------------------------------------------
# 2) Trockenlauf schreibt NICHTS
# -----------------------------------------------------------------------------

def test_trockenlauf_veraendert_keine_datei(datenverzeichnis, capsys):
    vorher = {p: p.read_bytes() for p in
              (datenverzeichnis["forensic"], datenverzeichnis["evidence"],
               datenverzeichnis["templates"])}

    rc = werkzeug.main(["--data-dir", str(datenverzeichnis["data"])])
    assert rc == 0

    for p, inhalt in vorher.items():
        assert p.read_bytes() == inhalt, f"{p.name} wurde im Trockenlauf veraendert"

    ausgabe = capsys.readouterr().out
    assert "TROCKENLAUF" in ausgabe
    assert "2 von 3" in ausgabe            # templates.db ist schon 'delete'


# -----------------------------------------------------------------------------
# 3) Scharfer Lauf — Stempel geaendert, Siegel unveraendert
# -----------------------------------------------------------------------------

def test_apply_stempelt_um_und_haelt_das_siegel(datenverzeichnis, capsys):
    rc = werkzeug.main(["--data-dir", str(datenverzeichnis["data"]), "--apply"])
    assert rc == 0

    assert _stempel(datenverzeichnis["forensic"]) == 1
    assert _stempel(datenverzeichnis["evidence"]) == 1
    assert _stempel(datenverzeichnis["templates"]) == 1

    # Gegenprobe mit der Pruefroutine des Servers: Siegel muss weiter passen.
    con = sqlite3.connect(str(datenverzeichnis["forensic"]))
    try:
        gespeichert = con.execute(
            "SELECT value FROM forensic_meta WHERE key='sha256'"
        ).fetchone()[0]
        berechnet = StartupChecker(None, None)._compute_content_sha256(con)
    finally:
        con.close()

    assert gespeichert == berechnet == datenverzeichnis["siegel"]

    ausgabe = capsys.readouterr().out
    assert "UMGESTEMPELT auf 'delete'" in ausgabe
    # Die bereits passende DB wird gemeldet, nicht still uebergangen (Grundregel 1)
    assert "Bereits im Zielzustand" in ausgabe


# -----------------------------------------------------------------------------
# 4) Idempotenz — zweiter Lauf aendert nichts mehr
# -----------------------------------------------------------------------------

def test_zweiter_lauf_ist_idempotent(datenverzeichnis, capsys):
    werkzeug.main(["--data-dir", str(datenverzeichnis["data"]), "--apply"])
    capsys.readouterr()

    inhalte = {p: p.read_bytes() for p in
               (datenverzeichnis["forensic"], datenverzeichnis["evidence"])}
    rc = werkzeug.main(["--data-dir", str(datenverzeichnis["data"]), "--apply"])
    assert rc == 0
    for p, inhalt in inhalte.items():
        assert p.read_bytes() == inhalt

    assert "0 von 3" in capsys.readouterr().out


# -----------------------------------------------------------------------------
# 5) Rueckweg — 'delete' -> 'wal' (fuer den Fall, dass eine DB lokal betrieben wird)
# -----------------------------------------------------------------------------

def test_rueckweg_nach_wal(datenverzeichnis):
    werkzeug.main(["--data-dir", str(datenverzeichnis["data"]), "--apply"])
    rc = werkzeug.main(["--data-dir", str(datenverzeichnis["data"]),
                        "--to", "wal", "--apply"])
    assert rc == 0
    assert _stempel(datenverzeichnis["evidence"]) == 2
    assert _stempel(datenverzeichnis["forensic"]) == 2


# -----------------------------------------------------------------------------
# 6) Fehlendes Verzeichnis -> Exitcode 1, keine stille Nichtbehandlung
# -----------------------------------------------------------------------------

def test_fehlendes_verzeichnis(tmp_path):
    assert werkzeug.main(["--data-dir", str(tmp_path / "gibtsnicht")]) == 1


# -----------------------------------------------------------------------------
# 7) --db: genau EINE Datenbank konvertieren (Build 433)
# -----------------------------------------------------------------------------

def test_db_einzeldatei_konvertiert_nur_diese(datenverzeichnis, capsys):
    """--db stempelt gezielt eine Datei um; die uebrigen bleiben unberuehrt.

    Das ist der PROD-Weg: forensic_<uid>.db/evidence_<uid>.db umstempeln, ohne an
    einer gesperrten geteilten coordinator.db zu haengen.
    """
    rc = werkzeug.main(["--db", str(datenverzeichnis["forensic"]), "--apply"])
    assert rc == 0
    assert _stempel(datenverzeichnis["forensic"]) == 1     # umgestempelt
    assert _stempel(datenverzeichnis["evidence"]) == 2     # NICHT angefasst

    ausgabe = capsys.readouterr().out
    assert "Einzeldatei" in ausgabe

    # Gegenprobe: Siegel der Beweismitteldatenbank haelt (inhaltsbasiert).
    con = sqlite3.connect(str(datenverzeichnis["forensic"]))
    try:
        berechnet = StartupChecker(None, None)._compute_content_sha256(con)
    finally:
        con.close()
    assert berechnet == datenverzeichnis["siegel"]


def test_db_nicht_vorhanden_exit1(tmp_path):
    assert werkzeug.main(["--db", str(tmp_path / "gibtsnicht.db"), "--apply"]) == 1


# -----------------------------------------------------------------------------
# 8) --skip-on-error: operative Fehler ueberspringen (Build 433)
# -----------------------------------------------------------------------------

def test_skip_on_error_ueberspringt_operativen_fehler(datenverzeichnis, capsys,
                                                      monkeypatch):
    """Ein gesperrter Datensatz (simuliert) wird gemeldet und uebersprungen,
    die uebrigen DBs laufen normal. Exitcode 2 signalisiert 'nicht alles fertig'.
    """
    echt = werkzeug.verarbeite

    def fake(db, ziel, apply):
        # evidence_* verhaelt sich wie eine gesperrte DB in PROD.
        if db.name.startswith("evidence_"):
            raise werkzeug.ConvertError(
                f"SQLite-Fehler bei '{db}': database is locked")
        return echt(db, ziel, apply)

    monkeypatch.setattr(werkzeug, "verarbeite", fake)

    rc = werkzeug.main(["--data-dir", str(datenverzeichnis["data"]),
                        "--skip-on-error", "--apply"])
    assert rc == 2                                    # partiell: >=1 uebersprungen
    assert _stempel(datenverzeichnis["forensic"]) == 1   # trotzdem konvertiert
    assert _stempel(datenverzeichnis["evidence"]) == 2   # uebersprungen -> WAL

    ausgabe = capsys.readouterr().out
    assert "UEBERSPRUNGEN" in ausgabe
    assert "evidence_9.db" in ausgabe                 # namentlich gemeldet (GR1)


def test_ohne_skip_bricht_bei_operativem_fehler_ab(datenverzeichnis, monkeypatch):
    """Rueckwaertskompatibel: ohne --skip-on-error fuehrt ein operativer Fehler
    weiterhin zum harten Abbruch (Exitcode 1).
    """
    def fake(db, ziel, apply):
        raise werkzeug.ConvertError("database is locked")
    monkeypatch.setattr(werkzeug, "verarbeite", fake)
    assert werkzeug.main(["--data-dir", str(datenverzeichnis["data"]),
                          "--apply"]) == 1


def test_siegelbruch_wird_nie_uebersprungen(datenverzeichnis, capsys, monkeypatch):
    """Kernaussage: Ein SealError (Inhalts-Hash-Abweichung) bricht IMMER hart ab,
    selbst mit --skip-on-error. Ehre der Beweiskraft vor Bequemlichkeit.
    """
    def fake(db, ziel, apply):
        if db.name.startswith("forensic_"):
            raise werkzeug.SealError("INHALTS-HASH HAT SICH GEAENDERT")
        return False
    monkeypatch.setattr(werkzeug, "verarbeite", fake)

    rc = werkzeug.main(["--data-dir", str(datenverzeichnis["data"]),
                        "--skip-on-error", "--apply"])
    assert rc == 1
    assert "SIEGELBRUCH" in capsys.readouterr().err
