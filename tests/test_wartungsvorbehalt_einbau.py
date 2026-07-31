# =============================================================================
# tests/test_wartungsvorbehalt_einbau.py
# IT-Forensisches Ermittlungswerkzeug - Wartungsvorbehalt (Build 612)
# =============================================================================
# Prueft, dass JEDES Werkzeug der Stufe A den Wartungsvorbehalt tatsaechlich
# aufruft - und dass er wirkt.
#
# WARUM ES DIESEN TEST BRAUCHT, obwohl der Einbau doch gerade gemacht wurde:
#   Ein Bauteil, das nur an fuenf Stellen aufgerufen wird, verschwindet beim
#   naechsten Umbau still. Kein Fehler, keine Meldung - es faellt nur eine
#   Zeile weg, und die Sicherung ist weg. Genau das ist der Grund, aus dem
#   der Vorbehalt ueberhaupt gebaut wurde: was man sich merken muss, vergisst
#   man. Dieser Test erinnert sich statt unser.
#
# ZWEI EBENEN, weil eine allein nicht traegt:
#   EB01-EB05  AM QUELLTEXT: der Aufruf steht da, und sein Ergebnis wird
#              ausgewertet. Das faengt den Fall "jemand hat die Zeile
#              geloescht" - auch dann, wenn es fuer das Werkzeug gerade
#              keinen ausfuehrbaren Testaufbau gibt.
#   EB06-EB09  AM VERHALTEN: das Werkzeug wird mit einer BELEGTEN Datei
#              aufgerufen und muss 3 zurueckgeben, ohne etwas anzufassen.
#              Das faengt den Fall "der Aufruf steht da, wirkt aber nicht"
#              - etwa weil er hinter dem scharfen Lauf gelandet ist.
#
# Eine Quelltextpruefung allein waere Buchstabenzaehlerei, eine
# Verhaltenspruefung allein liesse die Werkzeuge ungedeckt, fuer die ein
# vollstaendiger Aufbau (migration.db, Katalog, Sicherungsverzeichnis) mehr
# Gestell als Aussage waere. Zusammen decken sie beide Richtungen ab.
#
# Version: v0.8.612 - Build: 612 - 2026-07-31
# =============================================================================

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

from maintenance.paths import MaintenancePaths            # noqa: E402
from maintenance.wartungsvorbehalt import (               # noqa: E402
    RUECKGABE_VORBEHALT, datenwurzel,
)


# -----------------------------------------------------------------------------
# DIE LISTE DER STUFE-A-WERKZEUGE.
#
# Sie steht hier und nirgends sonst, damit sie EINE Fassung hat. Grundlage ist
# 'Vermerk_Wartungsvorbehalt_Analyse_K1_K8_v1_0.md', Einstufung von mc
# bestaetigt am 2026-07-31: fuenfmal A, einmal B (index_cli - betriebs-
# vertraeglich, schreibt nur in ein Hilfsmittel).
#
# WER HIER DAZUKOMMT, kommt nicht in eine Fehlliste: er wird eingebaut. Eine
# Fehlliste waere hier das falsche Mittel - sie ist gut fuer Inhalte, die noch
# entstehen muessen, und schlecht fuer eine Sicherung, die entweder greift
# oder nicht.
# -----------------------------------------------------------------------------

STUFE_A = {
    "management/migrate.py": "coordinator.db, Tabellenumbau ohne Backup",
    "tools/migrate-dbs.py": "templates.db, evidence_<uid>.db, assets_<uid>.db",
    "management/migration_fleet/migration_fleet_admin.py":
        "companion --confirm; der Rueckweg kopiert ueber das Original",
    "management/consolidate_default_db.py":
        "--overwrite loescht die Ziel-Datei vor der Transaktion",
    "tools/forensic_index_upgrade.py":
        "--ausfuehren schreibt in die versiegelte forensic_<uid>.db",
}

#: Werkzeuge, die der Vermerk ausdruecklich NICHT als Stufe A einstuft. Sie
#: stehen hier, damit die Abgrenzung geprueft ist und nicht nur behauptet.
NICHT_STUFE_A = {
    "management/search/index_cli.py":
        "Stufe B - schreibt ausschliesslich in search_index.db, die kein "
        "anderer Dienst offen haelt",
}


def _quelle(relpfad: str) -> str:
    return (_WURZEL / relpfad).read_text(encoding="utf-8")


def _lade(relpfad: str, name: str):
    """Ein Werkzeug als Modul laden (Muster aus test_maintenance_cli.py)."""
    spec = importlib.util.spec_from_file_location(name, _WURZEL / relpfad)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _db(pfad: Path) -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(pfad))
    con.execute("CREATE TABLE IF NOT EXISTS t (a INTEGER)")
    con.commit()
    con.close()
    return pfad


class _Halter:
    """Haelt eine exklusive Sperre auf einer Datei - der belegte Zustand."""

    def __init__(self, pfad: Path):
        self._con = sqlite3.connect(str(pfad))

    def __enter__(self):
        self._con.execute("BEGIN EXCLUSIVE")
        return self

    def __exit__(self, *_a):
        self._con.rollback()
        self._con.close()
        return False


@pytest.fixture
def anlage(tmp_path):
    """Ein Wegwerf-Datenverzeichnis mit _maintenance und leeren Datenbanken."""
    d = tmp_path / "data"
    MaintenancePaths(d).verzeichnisse_anlegen()
    return d


# -----------------------------------------------------------------------------
# EB01-EB05 - am Quelltext
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("relpfad", sorted(STUFE_A))
def test_eb01_stufe_a_ruft_den_vorbehalt(relpfad):
    """
    EB01 - Jedes Stufe-A-Werkzeug importiert das Bauteil und ruft es auf.
    """
    quelle = _quelle(relpfad)
    assert "from maintenance.wartungsvorbehalt import" in quelle, (
        "%s (%s) importiert den Wartungsvorbehalt nicht."
        % (relpfad, STUFE_A[relpfad]))
    assert "wartungsvorbehalt(" in quelle, (
        "%s importiert das Bauteil, ruft es aber nicht auf." % relpfad)


@pytest.mark.parametrize("relpfad", sorted(STUFE_A))
def test_eb02_das_ergebnis_wird_ausgewertet(relpfad):
    """
    EB02 - Der Rueckgabewert wird nicht nur geholt, sondern befolgt.

    Ein Aufruf ohne Auswertung waere die teuerste Form von Sicherheit: sie
    kostet Rechenzeit und Bildschirm und verhindert nichts.
    """
    quelle = _quelle(relpfad)
    assert "not befund.erlaubt" in quelle, (
        "%s wertet 'befund.erlaubt' nicht aus." % relpfad)
    assert "return befund.rueckgabewert" in quelle, (
        "%s reicht 'befund.rueckgabewert' nicht nach aussen weiter - ein "
        "Skript koennte den Abbruch dann nicht erkennen." % relpfad)
    assert "print(befund.text)" in quelle, (
        "%s gibt den Befundtext nicht aus. Dann stuende die aufrufende "
        "Person vor einem stillen Abbruch." % relpfad)


@pytest.mark.parametrize("relpfad", sorted(STUFE_A))
def test_eb03_der_dateikopf_nennt_die_einstufung(relpfad):
    """
    EB03 - Die Einstufung steht im Kopf des Werkzeugs, nicht nur im Vermerk.

    Wer die Datei oeffnet, um sie zu aendern, liest den Kopf. Wer den Vermerk
    im Projektspeicher liest, aendert gerade keine Datei.
    """
    kopf = "\n".join(_quelle(relpfad).split("\n")[:80])
    assert "WARTUNGSVORBEHALT" in kopf, (
        "%s nennt den Wartungsvorbehalt nicht im Dateikopf." % relpfad)
    assert "STUFE A" in kopf, (
        "%s nennt die Stufe nicht im Dateikopf." % relpfad)
    assert "3" in kopf, "%s nennt den Rueckgabewert 3 nicht." % relpfad


@pytest.mark.parametrize("relpfad", sorted(NICHT_STUFE_A))
def test_eb04_abgrenzung_ist_geprueft_und_nicht_behauptet(relpfad):
    """
    EB04 - Ein Werkzeug, das NICHT Stufe A ist, ruft den Vorbehalt auch nicht.

    Das ist keine Formalie: Ein Vorbehalt an einer Stelle, an der er nicht
    hingehoert, erzeugt Rueckfragen ohne Anlass - und wer oft ohne Anlass
    gefragt wird, tippt das Wort irgendwann, ohne zu lesen. Dann ist die
    Sicherung genau dort wirkungslos, wo sie gebraucht wird.
    """
    quelle = _quelle(relpfad)
    assert "wartungsvorbehalt" not in quelle, (
        "%s ist als %s eingestuft und darf den Vorbehalt nicht aufrufen."
        % (relpfad, NICHT_STUFE_A[relpfad]))


def test_eb05_die_liste_deckt_sich_mit_dem_vermerk():
    """
    EB05 - Fuenf Stufe-A-Werkzeuge, und alle fuenf gibt es wirklich.

    Ein Eintrag, der auf keine Datei zeigt, waere eine Sicherung, die niemand
    vermisst - der Test ueber ihn liefe gruen, weil er nichts findet.
    """
    assert len(STUFE_A) == 5, \
        "Der Vermerk stuft fuenf Werkzeuge als Stufe A ein."
    for relpfad in list(STUFE_A) + list(NICHT_STUFE_A):
        assert (_WURZEL / relpfad).is_file(), \
            "%s ist eingetragen, existiert aber nicht." % relpfad


# -----------------------------------------------------------------------------
# EB06-EB09 - am Verhalten
#
# In allen vier Faellen wird eine betroffene Datei EXKLUSIV GESPERRT gehalten.
# Der Vorbehalt muss dann abbrechen, und zwar OHNE Rueckfrage - der belegte
# Zustand ist ein Messwert und keine Ermessensfrage. Deshalb braucht keiner
# dieser Tests ein Terminal, und keiner haengt an einer Eingabe.
# -----------------------------------------------------------------------------

def test_eb06_migrate_bricht_bei_belegter_coordinator_ab(anlage, capsys):
    """EB06 - management/migrate.py gibt 3 zurueck und fasst nichts an."""
    db = _db(anlage / "coordinator.db")
    from management import migrate

    with _Halter(db):
        rc = migrate.main(["--coordinator-db", str(db)])

    assert rc == RUECKGABE_VORBEHALT
    ausgabe = capsys.readouterr().out
    assert "WARTUNGSVORBEHALT" in ausgabe
    assert "coordinator.db" in ausgabe
    # Die Migration selbst ist gar nicht erst angelaufen.
    assert "Angewandte Migrationen" not in ausgabe
    with sqlite3.connect(str(db)) as con:
        namen = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
    assert namen == ["t"], \
        "Der Vorbehalt hat den Lauf nicht vor der ersten Schreiboperation " \
        "angehalten: %s" % namen


def test_eb07_consolidate_bricht_bei_belegtem_ziel_ab(anlage, capsys):
    """EB07 - management/consolidate_default_db.py gibt 3 zurueck."""
    ziel = _db(anlage / "default.db")
    quelle = _db(anlage / "quelle" / "default.db")
    from management import consolidate_default_db as tool

    with _Halter(ziel):
        rc = tool.main(["--target", str(ziel), "--source", str(quelle),
                        "--overwrite"])

    assert rc == RUECKGABE_VORBEHALT
    ausgabe = capsys.readouterr().out
    assert "WARTUNGSVORBEHALT" in ausgabe
    # Die Ziel-Datei ist NICHT geloescht worden - genau der Befund, wegen
    # dessen das Werkzeug Stufe A ist.
    assert ziel.is_file()


def test_eb08_forensic_index_upgrade_bricht_bei_belegter_datei_ab(anlage,
                                                                 capsys):
    """
    EB08 - tools/forensic_index_upgrade.py --ausfuehren gibt 3 zurueck.

    Zusaetzlich die Gegenprobe: der TROCKENLAUF laeuft weiterhin ohne
    Vorbehalt durch. Eine Vorschau, die erst nach einer Rueckfrage kommt,
    wird uebersprungen - und dann sieht niemand mehr, was passieren wuerde.
    """
    verz = anlage / "forensic"
    db = _db(verz / "forensic_1488.db")
    werkzeug = _lade("tools/forensic_index_upgrade.py", "fiu_einbau")

    with _Halter(db):
        rc = werkzeug.main(["--forensic-dir", str(verz), "--ausfuehren"])
        assert rc == RUECKGABE_VORBEHALT
        assert "WARTUNGSVORBEHALT" in capsys.readouterr().out

        rc_trocken = werkzeug.main(["--forensic-dir", str(verz)])
    trocken = capsys.readouterr().out
    assert rc_trocken != RUECKGABE_VORBEHALT
    assert "WARTUNGSVORBEHALT" not in trocken, \
        "Der Trockenlauf darf keinen Vorbehalt ausloesen."


def test_eb09_migrate_dbs_trockenuebung_bleibt_frei(anlage, capsys):
    """
    EB09 - tools/migrate-dbs.py ohne --apply loest keinen Vorbehalt aus.

    Der scharfe Lauf dieses Werkzeugs braucht einen vollstaendigen
    Migrationsstand als Aufbau; hier wird die andere Richtung gesichert - dass
    die Trockenuebung ungestoert bleibt. Der scharfe Zweig ist ueber EB01/EB02
    am Quelltext gedeckt und ueber die Stelle des Aufrufs: er steht NACH der
    Abfrage 'nicht args.apply' und VOR der ersten Sicherung.
    """
    _db(anlage / "templates.db")
    werkzeug = _lade("tools/migrate-dbs.py", "migrate_dbs_einbau")

    rc = werkzeug.main(["--data-dir", str(anlage)])
    ausgabe = capsys.readouterr().out
    assert rc != RUECKGABE_VORBEHALT
    assert "WARTUNGSVORBEHALT" not in ausgabe

    # Die Reihenfolge im Quelltext, als Beleg fuer den scharfen Zweig.
    quelle = _quelle("tools/migrate-dbs.py")
    vorbehalt = quelle.index("befund = wartungsvorbehalt(")
    assert quelle.index("if not args.apply:") < vorbehalt, \
        "Der Vorbehalt liegt vor der Trockenuebungs-Abfrage - dann wuerde " \
        "auch die Vorschau nachfragen."
    assert vorbehalt < quelle.index('print("SCHARFGESCHALTET'), \
        "Der Vorbehalt liegt hinter dem Beginn des scharfen Laufs."


def test_eb10_datenwurzel_findet_das_wartungsverzeichnis(anlage, tmp_path):
    """
    EB10 - Alle fuenf Werkzeuge finden dasselbe Wartungsverzeichnis.

    Sie bekommen ganz verschiedene Pfade genannt - eine Datei, ein
    Datenverzeichnis, ein Unterverzeichnis. Wuerde jedes fuer sich raten, wo
    die Wurzel liegt, waere das fuenfmal dieselbe Annahme an fuenf Stellen.
    """
    tief = anlage / "forensic"
    tief.mkdir(exist_ok=True)
    datei = _db(anlage / "coordinator.db")

    assert datenwurzel(datei) == anlage
    assert datenwurzel(anlage) == anlage
    assert datenwurzel(tief) == anlage

    # Ohne _maintenance in der Naehe: Rueckfall auf den Ausgangspunkt. Dort
    # gibt es dann kein Fenster - der Vorbehalt fragt nach, er laesst nicht
    # etwa durch.
    fremd = tmp_path / "woanders"
    fremd.mkdir()
    assert datenwurzel(fremd) == fremd
