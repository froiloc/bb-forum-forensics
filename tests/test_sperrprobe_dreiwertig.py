# =============================================================================
# tests/test_sperrprobe_dreiwertig.py
# IT-Forensisches Ermittlungswerkzeug - Vorgang 96f2b18f
# =============================================================================
# DIE SPERRPROBE IST DER NACHWEIS DER RUHIGSTELLUNG. Der Wartungsmodus stuetzt
# seinen ganzen Beweis auf einen Satz: "Die Bestaetigung allein ist nicht der
# Beweis - der Exklusiv-Lock-Erwerb ist es."
#
# Bis Build 647 kannte die Probe zwei Ausgaenge, und ein DRITTER Fall wurde
# dem ersten zugeschlagen, obwohl er das Gegenteil bedeutet: der Fall, in dem
# gar nicht gemessen werden konnte.
#
# =============================================================================
# WARUM DIESE SUITE EINEN FREMDEN BENUTZER BRAUCHT - und warum das kein
# Beiwerk ist, sondern der Kern
# =============================================================================
# Der Mangel zeigt sich NUR, wenn der messende Prozess kein Schreibrecht hat.
# Unter 'root' gibt es diesen Zustand nicht: root schreibt auch auf eine
# Datei mit 0444. Ein Test, der als root laeuft und die Rechtebits setzt,
# misst deshalb NICHTS - er sieht durchgehend das gute Verhalten und ist
# gruen, gleichgueltig ob der Mangel behoben ist.
#
# GENAU DIESER FEHLER IST BEIM BAUEN DIESER SUITE UNTERLAUFEN: Die erste
# Nachstellung lief als root, meldete das erwartete Verhalten und haette den
# Vorgang als unbegruendet erscheinen lassen. Erst der Wechsel auf einen
# fremden Benutzer hat ihn sichtbar gemacht. Das ist das Muster aus Vorgang
# c3f80e54 ("schwache Pruefungen erzeugen unwirkliche Testvorrichtungen") in
# freier Wildbahn.
#
# Deshalb: Diese Suite laeuft die heiklen Faelle in einem UNTERPROZESS unter
# 'nobody'. Geht das nicht (kein root, kein 'nobody', Windows), wird
# UEBERSPRUNGEN - mit Grund und namentlich. Ein nicht gefahrener Test ist
# kein bestandener Test.
#
# SP01  drei Zustaende, sauber getrennt
# SP02  'nicht messbar' ist NICHT ruhig (der Kern)
# SP03  ohne Schreibrecht: nicht messbar statt 'exklusiv erhalten'
# SP04  GEGENPROBE: mit Schreibrecht misst sie weiterhin richtig
# SP05  GEGENPROBE: ein SCHREIBER wird auch ohne Schreibrecht erkannt
# SP06  die alte zweiwertige Form faellt auf die sichere Seite
# SP07  nicht vorhandene Datei bleibt 'ruhig'
# SP08  sperren_pruefen ordnet die drei Zustaende zu
#
# MK01-MK04  Vorgang 1155da11 - 'maintenance_kill --all' zeigt vor der Wirkung,
#            wen es trifft, und fragt zurueck, sobald FREMDE Rechner dabei sind
#
# Version: v0.8.648 - Build: 648 - 2026-08-01
# =============================================================================

import os
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

from maintenance.cli_support import (exklusiv_beurteilen,       # noqa: E402
                                     exklusiv_pruefen)
from maintenance.exklusiv_befund import (BELEGT, NICHT_MESSBAR,  # noqa: E402
                                         RUHIG, ExklusivBefund,
                                         ExklusivBefundError)


@pytest.fixture
def offener_ordner():
    """
    Ein Wegwerf-Ordner, in den ein FREMDER Benutzer hineinsehen kann.

    pytest legt 'tmp_path' unter '/tmp/pytest-of-root/...' an, und die
    Zwischenverzeichnisse tragen 0700. 'nobody' kommt dort nicht einmal
    hinein - der Unterprozess scheiterte an einem PermissionError, noch bevor
    die Sperrprobe ueberhaupt lief. Das haette wie ein Befund ausgesehen und
    war keiner.
    """
    import shutil
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="aiw_sperrprobe_", dir="/tmp"))
    os.chmod(d, 0o755)
    try:
        yield d
    finally:
        for f in d.rglob("*"):
            try:
                os.chmod(f, 0o644)
            except OSError:
                pass
        shutil.rmtree(d, ignore_errors=True)


def _db(pfad: Path) -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(pfad))
    con.execute("PRAGMA journal_mode=DELETE")
    con.execute("CREATE TABLE t(a)")
    con.commit()
    con.close()
    return pfad


def _fremder_benutzer_moeglich() -> str:
    """Gibt den Grund zurueck, WARUM es nicht geht - oder '' wenn es geht."""
    if os.name != "posix":
        return "kein POSIX-System"
    if os.getuid() != 0:
        return ("laeuft nicht als root - der Rechtewechsel auf einen fremden "
                "Benutzer ist dann nicht moeglich")
    try:
        import pwd
        pwd.getpwnam("nobody")
    except Exception as exc:
        return "kein Benutzer 'nobody' (%s)" % exc
    return ""


def _als_nobody(db: Path, code: str) -> str:
    """
    Fuehrt 'code' als 'nobody' aus. 'code' bekommt die Variable DB.

    DER UNTERPROZESS IST NOETIG: setuid ist im laufenden Prozess nicht
    zurueckzunehmen. Ein Test, der die Rechte des Testlaufs selbst absenkt,
    zoege alle folgenden mit.
    """
    voll = textwrap.dedent("""
        import os, pwd, sys
        sys.path.insert(0, %r)
        u = pwd.getpwnam('nobody')
        os.setgroups([]); os.setgid(u.pw_gid); os.setuid(u.pw_uid)
        DB = %r
        from maintenance.cli_support import exklusiv_beurteilen, exklusiv_pruefen
    """ % (str(_WURZEL), str(db))) + textwrap.dedent(code)
    erg = subprocess.run([sys.executable, "-c", voll],
                         capture_output=True, text=True)
    if erg.returncode != 0:
        raise AssertionError("Unterprozess gescheitert:\n%s" % erg.stderr[-800:])
    return erg.stdout.strip()


# -----------------------------------------------------------------------------
# SP01 / SP02 - das Bauteil
# -----------------------------------------------------------------------------

def test_sp01_drei_zustaende_sind_sauber_getrennt():
    """SP01: Die Datenklasse laesst keinen vierten Zustand zu."""
    assert ExklusivBefund("/x", RUHIG, "g").ist_ruhig is True
    assert ExklusivBefund("/x", BELEGT, "g").ist_ruhig is False
    assert ExklusivBefund("/x", NICHT_MESSBAR, "g").ist_ruhig is False
    with pytest.raises(ExklusivBefundError):
        ExklusivBefund("/x", "vielleicht", "g")
    with pytest.raises(ExklusivBefundError):
        # Ein 'nicht messbar' ohne Grund waere fuer den Betrieb wertlos:
        # der Grund ist das Einzige, woraus abzuleiten ist, was zu tun ist.
        ExklusivBefund("/x", NICHT_MESSBAR, "   ")


def test_sp02_nicht_messbar_ist_nicht_ruhig():
    """
    SP02, DER KERN DES VORGANGS in einer Zeile: 'nicht messbar' darf nicht
    als Ruhe gelten. Vorher hat der unmessbare Fall als Ruhe gezaehlt, und
    der Wartungsmodus gab ein Fenster frei, dessen Nachweis nie erbracht war.
    """
    assert ExklusivBefund("/x", NICHT_MESSBAR, "grund").als_tupel() == (
        False, "grund")


# -----------------------------------------------------------------------------
# SP03-SP05 - gemessen, unter echten Rechten
# -----------------------------------------------------------------------------

def test_sp03_ohne_schreibrecht_ist_nicht_messbar(offener_ordner):
    """
    SP03, DER GEMESSENE BEFUND. Eine Datei, die der messende Prozess nicht
    beschreiben darf, liefert 'nicht messbar' statt 'exklusiv erhalten' -
    und zwar OHNE dass irgendjemand die Datei haelt.

    GEMESSEN WIRD MIT 0644, NICHT MIT 0444, und das ist Absicht: Der Vorgang
    nannte die VERSIEGELTEN Dateien. Entscheidend ist aber nicht die
    Versiegelung, sondern das Schreibrecht des messenden Prozesses. 0644
    heisst 'voellig gewoehnliche Datei, die jemand anderem gehoert' - auf
    einem geteilten Laufwerk der Normalfall und nicht die Ausnahme.
    """
    grund = _fremder_benutzer_moeglich()
    if grund:
        pytest.skip("Rechtewechsel nicht moeglich: %s" % grund)

    db = _db(offener_ordner / "fremd.db")
    os.chmod(offener_ordner, 0o755)
    os.chmod(db, 0o644)                      # lesbar fuer alle, schreibbar nur fuer den Eigentuemer
    ausgabe = _als_nobody(db, """
        b = exklusiv_beurteilen(DB)
        print(b.zustand, '|', os.access(DB, os.W_OK))
    """)
    zustand, _, schreibrecht = ausgabe.partition(" | ")
    assert schreibrecht == "False", "Die Vorrichtung greift nicht - der " \
                                    "Unterprozess darf die Datei schreiben."
    assert zustand == NICHT_MESSBAR, (
        "Ohne Schreibrecht meldet die Probe wieder eine folgenlose Zusage. "
        "Das ist der Rueckfall in 96f2b18f. Gemessen: %r" % ausgabe)


def test_sp04_mit_schreibrecht_misst_sie_weiterhin(tmp_path):
    """
    SP04, DIE GEGENPROBE (TE5): Mit Schreibrecht muss die Probe nach wie vor
    'ruhig' melden. Ohne sie bestuende SP03 auch dann, wenn die Probe
    inzwischen ALLES fuer unmessbar haelt - und der Wartungsmodus gaebe nie
    wieder ein Fenster frei.
    """
    db = _db(tmp_path / "eigen.db")
    b = exklusiv_beurteilen(db)
    assert b.zustand == RUHIG and b.ist_ruhig is True, b.grund


def test_sp05_ein_schreiber_wird_auch_ohne_schreibrecht_erkannt(offener_ordner):
    """
    SP05, DIE ZWEITE GEGENPROBE - sie grenzt den Mangel ein.

    Haelt ein SCHREIBER eine EXCLUSIVE-Sperre, dann blockiert die schon das
    LESEN; die Probe meldet deshalb auch ohne Schreibrecht 'belegt'. Dieser
    Fall war NIE blind, und das gehoert zum Befund dazu: Der Vorgang
    behauptete auch fuer ihn Blindheit; nachgemessen trifft das nicht zu.

    Eine Behebung, die diesen Fall mit umbaut, haette etwas repariert, das
    nicht kaputt war.
    """
    grund = _fremder_benutzer_moeglich()
    if grund:
        pytest.skip("Rechtewechsel nicht moeglich: %s" % grund)

    db = _db(offener_ordner / "gehalten.db")
    os.chmod(offener_ordner, 0o755)
    halter = subprocess.Popen([
        sys.executable, "-c",
        "import sqlite3,time;c=sqlite3.connect(%r,isolation_level=None);"
        "c.execute('BEGIN EXCLUSIVE');c.execute('INSERT INTO t VALUES (1)');"
        "time.sleep(9)" % str(db)])
    try:
        import time
        time.sleep(1.5)
        os.chmod(db, 0o644)
        for anhang in ("-journal",):
            if (Path(str(db) + anhang)).exists():
                os.chmod(str(db) + anhang, 0o644)
        zustand = _als_nobody(db, """
            print(exklusiv_beurteilen(DB, 0.5).zustand)
        """)
        assert zustand == BELEGT, (
            "Ein Schreiber mit EXCLUSIVE-Sperre muss auch ohne Schreibrecht "
            "erkannt werden - eine EXCLUSIVE-Sperre blockiert schon das "
            "Lesen. Gemessen: %r" % zustand)
    finally:
        halter.kill()
        halter.wait()


# -----------------------------------------------------------------------------
# SP06-SP08 - die Anschlussstellen
# -----------------------------------------------------------------------------

def test_sp06_alte_form_faellt_auf_die_sichere_seite(tmp_path, monkeypatch):
    """
    SP06: Wer die alte zweiwertige Form benutzt, bekommt bei 'nicht messbar'
    ein False. Lieber ein 'nicht frei' zu viel als eine Ruhe, die nie
    gemessen wurde.
    """
    import maintenance.cli_support as cs
    db = _db(tmp_path / "x.db")

    def _wirft(*_a, **_k):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(cs.sqlite3, "connect", _wirft)
    ok, grund = exklusiv_pruefen(db)
    assert ok is False
    assert "nicht pruefbar" in grund


def test_sp07_nicht_vorhandene_datei_bleibt_ruhig(tmp_path):
    """
    SP07: Eine Datei, die es nicht gibt, ist ruhig - hier gibt es nichts zu
    sperren. Das ist KEIN Leerbefund im Sinne von rules-leerbefund.md: Die
    Aussage 'diese Datei haelt niemand' ist ueber eine nicht vorhandene Datei
    zutreffend und nicht bloss unmessbar.
    """
    b = exklusiv_beurteilen(tmp_path / "gibtsnicht.db")
    assert b.zustand == RUHIG
    assert "nicht vorhanden" in b.grund


def test_sp08_wartungsvorbehalt_ordnet_die_drei_zustaende_zu(tmp_path, offener_ordner):
    """
    SP08: Der Wartungsvorbehalt kannte schon drei Zustaende und hat den
    dritten bis Build 647 SELBST hergestellt (Vorabfrage 'ist_versiegelt').
    Jetzt ordnet er nur noch zu - und deckt damit auch die Faelle ab, die
    die Vorabfrage nicht kannte.
    """
    from maintenance.wartungsvorbehalt import (ZUSTAND_RUHIG,
                                               ZUSTAND_UNPRUEFBAR,
                                               sperren_pruefen)
    db = _db(tmp_path / "ruhig.db")
    befunde = sperren_pruefen([db])
    assert befunde[0].zustand == ZUSTAND_RUHIG

    # Ein Verzeichnis ohne Schreibrecht ist einer der Faelle, den die alte
    # Vorabfrage NICHT kannte - sie sah nur den Dateimodus.
    grund = _fremder_benutzer_moeglich()
    if grund:
        pytest.skip("Rechtewechsel nicht moeglich: %s" % grund)
    db2 = _db(offener_ordner / "fremd.db")
    os.chmod(db2, 0o644)
    zustand = _als_nobody(db2, """
        from maintenance.wartungsvorbehalt import sperren_pruefen
        print(sperren_pruefen([DB])[0].zustand)
    """)
    assert zustand == ZUSTAND_UNPRUEFBAR, (
        "Eine nicht messbare Datei muss als UNPRUEFBAR gefuehrt werden - "
        "nicht als BELEGT und erst recht nicht als RUHIG. Gemessen: %r"
        % zustand)


# =============================================================================
# 1155da11 - maintenance_kill --all trifft auch die Dienste anderer Personen
# =============================================================================

import importlib.util  # noqa: E402


def _kill_werkzeug():
    spec = importlib.util.spec_from_file_location(
        "maint_kill_1155", _WURZEL / "tools" / "maintenance_kill.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Anmeldung:
    """Attrappe einer Server-Anmeldung - nur die gelesenen Felder."""

    def __init__(self, uuid, host, rolle="job", pid=111, build=648,
                 window_id="w1"):
        self.uuid, self.host, self.role = uuid, host, rolle
        self.pid, self.build, self.window_id = pid, build, window_id
        self.kill_angefordert = False

    def kill_anfordern(self, paths, von):
        self.kill_angefordert = True


def test_mk01_fremde_rechner_werden_erkannt():
    """
    MK01: Der Vergleich ist unempfindlich gegen Gross-/Kleinschreibung und
    gegen einen angehaengten Domaenenteil.

    WARUM DAS NOETIG IST: Auf einem geteilten Laufwerk melden sich Rechner
    nicht zwingend unter demselben Namen an, unter dem der aufrufende Rechner
    sich selbst kennt - 'KK31-PC7' gegen 'kk31-pc7.polizei.example.nrw'. Ein
    Vergleich auf Zeichengleichheit haette JEDEN Rechner fuer fremd gehalten
    und die Rueckfrage zur Gewohnheit gemacht. Eine Rueckfrage, die immer
    kommt, wird weggeklickt.
    """
    mk = _kill_werkzeug()
    regs = {"a": _Anmeldung("a", "KK31-PC7"),
            "b": _Anmeldung("b", "kk31-pc7.polizei.example.nrw"),
            "c": _Anmeldung("c", "KK31-PC9")}
    fremde = mk._fremde_rechner(regs, ["a", "b", "c"], "kk31-pc7")
    assert fremde == ["KK31-PC9"], (
        "Nur der wirklich andere Rechner ist fremd. Gemessen: %s" % fremde)


def test_mk02_rueckfrage_bei_fremden_rechnern(capsys, monkeypatch):
    """
    MK02, DER KERN DES VORGANGS: Sind Dienste auf ANDEREN Rechnern betroffen,
    wird zurueckgefragt - und ohne das Bestaetigungswort geschieht NICHTS.
    """
    mk = _kill_werkzeug()
    eigen = _Anmeldung("a", __import__("socket").gethostname())
    fremd = _Anmeldung("b", "ein-anderer-rechner")
    # UEBER monkeypatch, NICHT durch Zuweisung: ServerRegistration ist
    # dieselbe Klasse wie im uebrigen Testlauf. Eine direkte Zuweisung
    # blieb bis zum Ende des Laufs stehen und hat drei fremde Tests
    # umgebracht - aufgefallen erst im Vollauf, nicht im Einzellauf.
    monkeypatch.setattr(mk.ServerRegistration, "alle_laden",
                        staticmethod(lambda _p: [eigen, fremd]))

    rc = mk.cmd_kill(None, [], alle=True, wait_timeout=0, von="pruefer",
                     eingabe=lambda _frage: "nein")
    ausgabe = capsys.readouterr()
    assert rc == 1
    assert "ABGEBROCHEN" in ausgabe.err
    assert eigen.kill_angefordert is False, "Es darf NICHTS beendet worden sein."
    assert fremd.kill_angefordert is False
    # Und die Auflistung stand VOR der Rueckfrage da.
    assert "Betroffene Anmeldungen (2)" in ausgabe.out
    assert "ein-anderer-rechner" in ausgabe.out


def test_mk03_gegenprobe_kein_fremder_rechner_keine_rueckfrage(capsys, monkeypatch):
    """
    MK03, DIE GEGENPROBE (TE5): Sind nur Dienste des EIGENEN Rechners
    betroffen, wird NICHT gefragt.

    Ohne diese Probe bestuende MK02 auch dann, wenn das Werkzeug bei jedem
    Aufruf fragte - und eine Rueckfrage, die immer kommt, ist keine Warnung
    mehr, sondern eine Taste.
    """
    mk = _kill_werkzeug()
    eigen = _Anmeldung("a", __import__("socket").gethostname())
    # UEBER monkeypatch, NICHT durch Zuweisung: ServerRegistration ist
    # dieselbe Klasse wie im uebrigen Testlauf. Eine direkte Zuweisung
    # blieb bis zum Ende des Laufs stehen und hat drei fremde Tests
    # umgebracht - aufgefallen erst im Vollauf, nicht im Einzellauf.
    monkeypatch.setattr(mk.ServerRegistration, "alle_laden",
                        staticmethod(lambda _p: [eigen]))

    def _darf_nicht_fragen(_frage):
        raise AssertionError("Es wurde gefragt, obwohl nur der eigene "
                             "Rechner betroffen ist.")

    rc = mk.cmd_kill(None, [], alle=True, wait_timeout=0, von="pruefer",
                     eingabe=_darf_nicht_fragen)
    assert eigen.kill_angefordert is True
    assert rc in (0, 2)          # 0 = beendet, 2 = Nachzuegler (Attrappe bleibt)
    assert "Betroffene Anmeldungen (1)" in capsys.readouterr().out


def test_mk05_uuid_wird_nicht_zurueckgefragt(capsys, monkeypatch):
    """
    MK05, DIE ZWEITE ABGRENZUNG: Bei '--uuid' wird NICHT gefragt - auch nicht
    bei einem fremden Rechner.

    Wer eine bestimmte Anmeldung benennt, hat sie vorher in '--list' gesehen
    und sich entschieden. Der Vorgang richtet sich gegen den ungesehenen
    Rundumschlag von '--all', nicht gegen die bewusste Einzelentscheidung.
    Eine Rueckfrage bei jedem Aufruf waere binnen einer Woche eine Taste.
    """
    mk = _kill_werkzeug()
    fremd = _Anmeldung("b", "ein-anderer-rechner")
    # UEBER monkeypatch, NICHT durch Zuweisung: ServerRegistration ist
    # dieselbe Klasse wie im uebrigen Testlauf. Eine direkte Zuweisung
    # blieb bis zum Ende des Laufs stehen und hat drei fremde Tests
    # umgebracht - aufgefallen erst im Vollauf, nicht im Einzellauf.
    monkeypatch.setattr(mk.ServerRegistration, "alle_laden",
                        staticmethod(lambda _p: [fremd]))

    def _darf_nicht_fragen(_frage):
        raise AssertionError("Bei '--uuid' darf nicht gefragt werden.")

    mk.cmd_kill(None, ["b"], alle=False, wait_timeout=0, von="pruefer",
                eingabe=_darf_nicht_fragen)
    assert fremd.kill_angefordert is True
    # Die Auflistung steht trotzdem da.
    assert "Betroffene Anmeldungen (1)" in capsys.readouterr().out


def test_mk04_ja_uebergeht_die_rueckfrage(capsys, monkeypatch):
    """
    MK04: '--ja' uebergeht die Rueckfrage - fuer Skripte. Die AUFLISTUNG
    bleibt trotzdem stehen: Sie ist der Beleg im Sitzungsprotokoll darueber,
    wessen Lauf abgebrochen wurde.
    """
    mk = _kill_werkzeug()
    fremd = _Anmeldung("b", "ein-anderer-rechner")
    # UEBER monkeypatch, NICHT durch Zuweisung: ServerRegistration ist
    # dieselbe Klasse wie im uebrigen Testlauf. Eine direkte Zuweisung
    # blieb bis zum Ende des Laufs stehen und hat drei fremde Tests
    # umgebracht - aufgefallen erst im Vollauf, nicht im Einzellauf.
    monkeypatch.setattr(mk.ServerRegistration, "alle_laden",
                        staticmethod(lambda _p: [fremd]))

    def _darf_nicht_fragen(_frage):
        raise AssertionError("Mit '--ja' darf nicht gefragt werden.")

    mk.cmd_kill(None, [], alle=True, wait_timeout=0, von="pruefer",
                bestaetigt=True, eingabe=_darf_nicht_fragen)
    assert fremd.kill_angefordert is True
    assert "ein-anderer-rechner" in capsys.readouterr().out
