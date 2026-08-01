# =============================================================================
# tests/test_maintenance_wartungsvorbehalt.py
# IT-Forensisches Ermittlungswerkzeug - Wartungsvorbehalt (Build 610/611)
# =============================================================================
# Prueft maintenance/wartungsvorbehalt.py.
#
# DIE PRUEFUNGEN SIND IN VIER GRUPPEN GEGLIEDERT:
#   WV01-WV05  die reine Entscheidung (ohne Konsole, ohne Dateisystem)
#   WV06-WV12  der vollstaendige Ablauf gegen echte Dateien in tmp_path
#   WV13-WV20  die Form: Rueckgabewerte, ASCII, Breite, Zweitschrift, Umschrift
#   WV21-WV29  der Schreibschutz - und was aus dem Befund von mc folgt
#
# DIE VIERTE GRUPPE HAT EINE GESCHICHTE, die im Kopf jener Gruppe steht. Kurz:
# die Vermutung aus dem Vermerk zu Build 609 war falsch, mcs Regressionslauf
# hat das gezeigt, und die Tests halten seither den BEFUND fest statt der
# Vermutung.
#
# Version: v0.8.611 - Build: 611 - 2026-07-31
# =============================================================================

import os
import re
import sqlite3
import stat
from pathlib import Path

import pytest

from maintenance.cli_support import exklusiv_pruefen
from maintenance.paths import MaintenancePaths
from maintenance.window_flag import WindowFlag
from maintenance.wartungsvorbehalt import (
    BESTAETIGUNGSWORT, BREITE, ERGEBNIS_ABGELEHNT, ERGEBNIS_GESPERRT,
    ERGEBNIS_KEIN_TERMINAL, ERGEBNIS_LAUF, ERGEBNIS_WORTABFRAGE,
    RUECKGABE_LAUF, RUECKGABE_VORBEHALT, ZUSTAND_BELEGT, ZUSTAND_RUHIG,
    ZUSTAND_UNPRUEFBAR, Befund, Sperrbefund, WartungsvorbehaltError,
    aktives_fenster, fenster_deckt, hat_terminal, ist_versiegelt,
    naechster_schritt, nur_ascii, sperren_pruefen, text_abgelehnt,
    text_frage, text_gesperrt, text_kein_terminal, text_lauf, umbrechen,
    wartungsvorbehalt, wort_akzeptiert,
)

_QUELLE = Path(__file__).resolve().parent.parent / "maintenance" / \
    "wartungsvorbehalt.py"


# -----------------------------------------------------------------------------
# Hilfsmittel
# -----------------------------------------------------------------------------

def _db(pfad: Path) -> Path:
    """Legt eine echte, winzige SQLite-Datei an."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(pfad))
    con.execute("CREATE TABLE IF NOT EXISTS t (a INTEGER)")
    con.commit()
    con.close()
    return pfad


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    MaintenancePaths(d).verzeichnisse_anlegen()
    return d


class _Mitschrift:
    """Sammelt, was ausgegeben wurde, und was gefragt wurde."""

    def __init__(self, antwort=None):
        self.ausgaben = []
        self.fragen = []
        self._antwort = antwort

    def ausgabe(self, text):
        self.ausgaben.append(text)

    def eingabe(self, prompt):
        self.fragen.append(prompt)
        if self._antwort is None:
            raise AssertionError(
                "Es wurde eine Bestaetigung abgefragt, obwohl der Test das "
                "ausdruecklich nicht erwartet.")
        return self._antwort


def _ruhig(name="a.db"):
    return Sperrbefund(pfad=name, zustand=ZUSTAND_RUHIG,
                       grund="exklusiv erhalten")


def _belegt(name="b.db"):
    return Sperrbefund(pfad=name, zustand=ZUSTAND_BELEGT,
                       grund="database is locked")


def _unpruefbar(name="forensic_1488.db"):
    return Sperrbefund(pfad=name, zustand=ZUSTAND_UNPRUEFBAR,
                       grund="schreibgeschuetzt - die Sperrprobe kann hier "
                             "nicht messen, ob jemand die Datei geoeffnet "
                             "haelt")


# -----------------------------------------------------------------------------
# WV01-WV05 - die reine Entscheidung
# -----------------------------------------------------------------------------

def test_wv01_belegte_datei_schlaegt_alles_andere():
    """
    WV01 - Eine belegte Datei bricht ab, auch bei aktivem Fenster und
    verfuegbarem Terminal. DAS IST DIE KERNAUSSAGE DES BAUTEILS: das Fenster
    belegt die Absicht, die Sperre belegt die Ruhe - und nur die Ruhe darf
    entscheiden (Befund 1 des Vermerks zu Build 609).
    """
    befunde = (_ruhig(), _belegt())
    for deckt in (True, False):
        for terminal in (True, False):
            assert naechster_schritt(deckt, befunde, terminal) == \
                ERGEBNIS_GESPERRT


def test_wv02_fenster_und_ruhe_laufen_durch():
    """WV02 - Alles ruhig und ein deckendes Fenster: keine Rueckfrage."""
    assert naechster_schritt(True, (_ruhig(), _ruhig("c.db")), True) == \
        ERGEBNIS_LAUF
    # Auch ohne Terminal: bei gesetztem Fenster ist nichts zu fragen.
    assert naechster_schritt(True, (_ruhig(),), False) == ERGEBNIS_LAUF


def test_wv03_kein_fenster_kein_terminal_bricht_ab():
    """WV03 - Ohne Fenster und ohne Terminal wird nicht geraten."""
    assert naechster_schritt(False, (_ruhig(),), False) == \
        ERGEBNIS_KEIN_TERMINAL


def test_wv04_kein_fenster_mit_terminal_fuehrt_zur_wortabfrage():
    """WV04 - Der einzige Weg zur Rueckfrage."""
    assert naechster_schritt(False, (_ruhig(),), True) == ERGEBNIS_WORTABFRAGE


def test_wv05_wortpruefung():
    """
    WV05 - Nachsichtig bei Leerzeichen, streng bei der Schreibweise.

    Die Begruendung steht in der Funktion: Leerzeichen sind ein Tippartefakt,
    die Kleinschreibung ist ein Zeichen dafuer, dass das Wort nicht gelesen,
    sondern erinnert wurde - und das Lesen ist der Zweck der Abfrage.
    """
    assert wort_akzeptiert(BESTAETIGUNGSWORT) is True
    assert wort_akzeptiert("  " + BESTAETIGUNGSWORT + "  ") is True
    assert wort_akzeptiert("OHNE   WARTUNGSFENSTER") is True
    assert wort_akzeptiert("\tOHNE WARTUNGSFENSTER\n") is True

    assert wort_akzeptiert("ohne wartungsfenster") is False
    assert wort_akzeptiert("Ohne Wartungsfenster") is False
    assert wort_akzeptiert("OHNEWARTUNGSFENSTER") is False
    assert wort_akzeptiert("OHNE WARTUNGSFENSTER!") is False
    assert wort_akzeptiert("j") is False
    assert wort_akzeptiert("ja") is False
    assert wort_akzeptiert("") is False
    assert wort_akzeptiert(None) is False


# -----------------------------------------------------------------------------
# WV06-WV12 - der vollstaendige Ablauf gegen echte Dateien
# -----------------------------------------------------------------------------

def test_wv06_bestaetigung_gibt_frei(data_dir):
    """WV06 - Ohne Fenster, alles ruhig, Wort getippt: Freigabe."""
    db = _db(data_dir / "coordinator.db")
    m = _Mitschrift(antwort=BESTAETIGUNGSWORT)
    befund = wartungsvorbehalt(
        data_dir, [db], werkzeug="migrate",
        was_geschieht="baut Tabellen der coordinator.db um",
        eingabe=m.eingabe, ausgabe=m.ausgabe, terminal=True)

    assert befund.ergebnis == ERGEBNIS_LAUF
    assert befund.erlaubt is True
    assert befund.rueckgabewert == RUECKGABE_LAUF
    assert befund.fenster_id is None
    # Die Sachlage wurde VOR der Frage ausgegeben, und genau einmal.
    assert len(m.ausgaben) == 1 and len(m.fragen) == 1
    assert BESTAETIGUNGSWORT in m.ausgaben[0]
    assert "baut Tabellen der coordinator.db um" in m.ausgaben[0]
    # Der Fragetext steht NICHT noch einmal im Befund - sonst laese man ihn
    # zweimal.
    assert "Momentaufnahme" not in befund.text


def test_wv07_falsches_wort_bricht_ab(data_dir):
    """WV07 - Jede andere Eingabe bricht ab; ein zweiter Versuch entfaellt."""
    db = _db(data_dir / "coordinator.db")
    m = _Mitschrift(antwort="ja")
    befund = wartungsvorbehalt(
        data_dir, [db], werkzeug="migrate", was_geschieht="baut Tabellen um",
        eingabe=m.eingabe, ausgabe=m.ausgabe, terminal=True)

    assert befund.ergebnis == ERGEBNIS_ABGELEHNT
    assert befund.erlaubt is False
    assert befund.rueckgabewert == RUECKGABE_VORBEHALT
    assert len(m.fragen) == 1, "Es darf genau einen Versuch geben."
    assert "NICHT ausgefuehrt" in befund.text
    assert "nichts geschrieben" in befund.text


def test_wv08_belegte_datei_fragt_nicht(data_dir):
    """
    WV08 - Bei belegter Datei wird NICHT gefragt.

    _Mitschrift(antwort=None) laesst den Test scheitern, sobald eine Frage
    gestellt wird. Das ist die eigentliche Zusicherung dieses Tests: hier ist
    nachweislich jemand an der Datei, und das ist keine Ermessensfrage.
    """
    ruhig = _db(data_dir / "templates.db")
    belegt = _db(data_dir / "coordinator.db")
    halter = sqlite3.connect(str(belegt))
    halter.execute("BEGIN EXCLUSIVE")
    try:
        m = _Mitschrift(antwort=None)
        befund = wartungsvorbehalt(
            data_dir, [ruhig, belegt], werkzeug="migrate",
            was_geschieht="baut Tabellen um", timeout_s=0.3,
            eingabe=m.eingabe, ausgabe=m.ausgabe, terminal=True)
    finally:
        halter.rollback()
        halter.close()

    assert befund.ergebnis == ERGEBNIS_GESPERRT
    assert befund.rueckgabewert == RUECKGABE_VORBEHALT
    assert m.fragen == [] and m.ausgaben == []
    assert "coordinator.db" in befund.text
    # Auch die ruhige Datei steht im Bericht: wer den Lauf nachvollzieht,
    # will wissen, WAS geprueft wurde (Grundregel 1).
    assert "templates.db" in befund.text
    assert len(befund.belegte()) == 1
    assert len(befund.befunde) == 2


def test_wv09_aktives_fenster_fragt_nicht(data_dir):
    """WV09 - Ein deckendes, aktives Fenster laeuft ohne Rueckfrage durch."""
    db = _db(data_dir / "coordinator.db")
    paths = MaintenancePaths(data_dir)
    flag = WindowFlag.neu(angefordert_von="pruefer", grund="Test",
                          ziel=["coordinator"])
    flag.schreiben(paths)

    m = _Mitschrift(antwort=None)
    befund = wartungsvorbehalt(
        data_dir, [db], werkzeug="migrate", was_geschieht="baut Tabellen um",
        eingabe=m.eingabe, ausgabe=m.ausgabe, terminal=True)

    assert befund.ergebnis == ERGEBNIS_LAUF
    assert befund.fenster_id == flag.window_id
    assert m.fragen == []
    assert flag.window_id in befund.text


def test_wv10_fenster_das_die_datei_nicht_nennt_deckt_nicht(data_dir):
    """
    WV10 - Ein Fenster fuer 'coordinator' deckt keine evidence_1488.db.

    Sonst waere ein enges Fenster ein Freibrief fuer alles andere.
    """
    evidence = _db(data_dir / "evidence" / "evidence_1488.db")
    paths = MaintenancePaths(data_dir)
    WindowFlag.neu(angefordert_von="pruefer", grund="Test",
                   ziel=["coordinator"]).schreiben(paths)

    m = _Mitschrift(antwort=BESTAETIGUNGSWORT)
    befund = wartungsvorbehalt(
        data_dir, [evidence], werkzeug="migrate-dbs",
        was_geschieht="schreibt evidence_1488.db",
        eingabe=m.eingabe, ausgabe=m.ausgabe, terminal=True)

    assert len(m.fragen) == 1, "Ohne deckendes Fenster muss gefragt werden."
    assert befund.ergebnis == ERGEBNIS_LAUF
    assert befund.fenster_id is None

    # Gegenprobe: 'all' deckt ab (Begruendung im Kopf von fenster_deckt).
    WindowFlag.entfernen(paths)
    WindowFlag.neu(angefordert_von="pruefer", grund="Test",
                   ziel=["all"]).schreiben(paths)
    assert fenster_deckt(aktives_fenster(data_dir), [evidence]) is True


def test_wv11_ohne_terminal_wird_abgebrochen(data_dir):
    """WV11 - Aufruf aus einem Skript: Abbruch mit Anleitung."""
    db = _db(data_dir / "coordinator.db")
    m = _Mitschrift(antwort=None)
    befund = wartungsvorbehalt(
        data_dir, [db], werkzeug="migrate", was_geschieht="baut Tabellen um",
        eingabe=m.eingabe, ausgabe=m.ausgabe, terminal=False)

    assert befund.ergebnis == ERGEBNIS_KEIN_TERMINAL
    assert befund.rueckgabewert == RUECKGABE_VORBEHALT
    assert m.fragen == []
    assert "tools/maintenance.py enter" in befund.text
    assert "nichts geschrieben" in befund.text


def test_wv12_abgebrochene_eingabe_ist_keine_bestaetigung(data_dir):
    """
    WV12 - EOF und Strg-C waehrend der Abfrage bedeuten 'nein'.

    Ein durchschlagender EOFError waere ein Absturz mit unbestimmtem
    Rueckgabewert - und ein unbestimmter Rueckgabewert ist genau das, was ein
    aufrufendes Skript nicht auswerten kann.
    """
    db = _db(data_dir / "coordinator.db")

    for ausnahme in (EOFError, KeyboardInterrupt):
        def _wirft(_prompt, exc=ausnahme):
            raise exc()

        befund = wartungsvorbehalt(
            data_dir, [db], werkzeug="migrate",
            was_geschieht="baut Tabellen um",
            eingabe=_wirft, ausgabe=lambda _t: None, terminal=True)
        assert befund.ergebnis == ERGEBNIS_ABGELEHNT
        assert befund.rueckgabewert == RUECKGABE_VORBEHALT


# -----------------------------------------------------------------------------
# WV13-WV17 - die Form
# -----------------------------------------------------------------------------

def test_wv13_befund_haelt_erlaubnis_und_rueckgabewert_zusammen():
    """
    WV13 - Ein Befund, der den Lauf verbietet und trotzdem 0 zurueckgibt,
    laesst sich gar nicht erst bauen. Das ist die gefaehrlichste Form von
    "es hat ja funktioniert", und sie wird im Datentyp verhindert.
    """
    with pytest.raises(WartungsvorbehaltError):
        Befund(ergebnis=ERGEBNIS_ABGELEHNT, erlaubt=False, fenster_id=None,
               befunde=(), text="x", rueckgabewert=RUECKGABE_LAUF)
    with pytest.raises(WartungsvorbehaltError):
        Befund(ergebnis=ERGEBNIS_LAUF, erlaubt=True, fenster_id=None,
               befunde=(), text="x", rueckgabewert=RUECKGABE_VORBEHALT)
    with pytest.raises(WartungsvorbehaltError):
        Befund(ergebnis=ERGEBNIS_GESPERRT, erlaubt=True, fenster_id=None,
               befunde=(), text="x", rueckgabewert=RUECKGABE_LAUF)
    with pytest.raises(WartungsvorbehaltError):
        Befund(ergebnis="irgendwas", erlaubt=True, fenster_id=None,
               befunde=(), text="x", rueckgabewert=RUECKGABE_LAUF)
    # Ein Sperrbefund ohne Begruendung ist kein Befund.
    with pytest.raises(WartungsvorbehaltError):
        Sperrbefund(pfad="a.db", zustand=ZUSTAND_RUHIG, grund="  ")
    # Und ein Zustand, den es nicht gibt, ist ebenfalls kein Befund.
    with pytest.raises(WartungsvorbehaltError):
        Sperrbefund(pfad="a.db", zustand="vielleicht", grund="x")


def test_wv14_unvollstaendiger_aufruf_faellt_sofort_auf(data_dir):
    """
    WV14 - Fehlende Angaben brechen beim ERSTEN Aufruf ab, nicht erst dann,
    wenn eine ungeprueft gebliebene Datei beschaedigt ist.
    """
    db = _db(data_dir / "coordinator.db")
    with pytest.raises(WartungsvorbehaltError):
        wartungsvorbehalt(data_dir, [], werkzeug="migrate",
                          was_geschieht="x", terminal=False)
    with pytest.raises(WartungsvorbehaltError):
        wartungsvorbehalt(data_dir, [db], werkzeug="  ",
                          was_geschieht="x", terminal=False)
    with pytest.raises(WartungsvorbehaltError):
        wartungsvorbehalt(data_dir, [db], werkzeug="migrate",
                          was_geschieht="", terminal=False)


def test_wv15_doppelte_pfade_werden_einmal_geprueft(data_dir):
    """WV15 - Zwei Migrationen an derselben Datei ergeben einen Befund."""
    db = _db(data_dir / "coordinator.db")
    befund = wartungsvorbehalt(
        data_dir, [db, Path(str(db)), db], werkzeug="migrate",
        was_geschieht="baut Tabellen um", terminal=False)
    assert len(befund.befunde) == 1


def test_wv16_ausgabe_ist_ascii_und_haelt_die_breite():
    """
    WV16 - Reines ASCII, 78 Zeichen.

    AUSNAHME, ausdruecklich geprueft: eine Zeile darf laenger sein, wenn sie
    nach dem Einzug aus EINEM Wort besteht - ein zerschnittener Pfad ist
    unbrauchbar. Dieselbe Ausnahme gilt in management/help/cli_text.py (CT09).
    """
    befunde = (_ruhig("data/templates.db"),
               _belegt("data/evidence/evidence_1488.db"))
    mit_offener = (_ruhig("data/coordinator.db"),
                   _unpruefbar("data/forensic/forensic_1488.db"))
    texte = [
        text_gesperrt("migrate", befunde),
        text_gesperrt("migrate", befunde + mit_offener),
        text_frage("forensic_index_upgrade", "baut Indizes auf", mit_offener),
        text_kein_terminal("forensic_index_upgrade", mit_offener),
        text_lauf("forensic_index_upgrade", None, mit_offener),
        text_frage("migrate", "baut Tabellen der coordinator.db um",
                   (_ruhig("data/coordinator.db"),)),
        text_kein_terminal("migrate", (_ruhig("data/coordinator.db"),)),
        text_abgelehnt("migrate"),
        text_lauf("migrate", "1234-abcd", (_ruhig(),)),
        text_lauf("migrate", None, (_ruhig(),)),
    ]
    for text in texte:
        assert text.isascii(), "Nicht-ASCII in der Konsolenausgabe"
        assert "\x1b" not in text, "Escape-Sequenz in der Konsolenausgabe"
        # Ein '(en)' im Fliesstext liest sich wie ein Formular, und ein
        # Formular liest niemand aufmerksam.
        assert "(en)" not in text and "(n)" not in text
        assert "\n\n\n" not in text, "Doppelte Leerzeile in der Ausgabe"
        for zeile in text.split("\n"):
            if len(zeile) <= BREITE:
                continue
            assert len(zeile.split()) == 1, \
                "Zu lange Zeile, die sich haette umbrechen lassen: %r" % zeile


def test_wv17_umbruch_ist_zeichengleich_mit_der_hilfe():
    """
    WV17 - Die Zweitschrift von umbrechen() darf nicht auseinanderlaufen.

    Die Verdopplung ist gewollt (Begruendung in der Funktion); dieser Test
    ist der Preis dafuer. Eine Abweichung faellt hier auf und nicht erst
    dann, wenn zwei Werkzeuge unterschiedlich aussehen.
    """
    from management.help.cli_text import umbrechen as umbrechen_hilfe

    faelle = [
        ("", 78, "", None),
        ("kurz", 78, "", None),
        ("ein etwas laengerer Satz, der ueber die Breite hinausgeht und "
         "deshalb umbrochen werden muss", 40, "", None),
        ("mit Einzug und einem sehr langen Wort "
         "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa danach", 30,
         "    ", None),
        ("erster Einzug abweichend", 20, "  ", ""),
        ("   ", 78, "", None),
    ]
    for text, breite, einzug, erster in faelle:
        assert umbrechen(text, breite, einzug, erster) == \
            umbrechen_hilfe(text, breite, einzug, erster), \
            "Abweichung bei %r" % (text[:30],)


def test_wv18_bauteil_schreibt_nichts():
    """
    WV18 - Der Vorbehalt laeuft in dem Moment, in dem noch nichts entschieden
    ist. Er darf keine Spur hinterlassen.

    Geprueft wird am QUELLTEXT und nicht am Verhalten: ein Verhaltenstest
    zeigte nur, dass bei DIESEM Aufruf nichts geschrieben wurde. Dasselbe
    Verfahren wie CT11 in tests/test_help_cli_text.py.
    """
    quelle = _QUELLE.read_text(encoding="utf-8")
    # Kommentare und Zeichenketten enthalten die Begriffe absichtlich; geprueft
    # wird deshalb der Code ohne Kommentarzeilen.
    code = "\n".join(z for z in quelle.split("\n")
                     if not z.lstrip().startswith("#"))
    for verboten in ("import sqlite3", "schreibe_json", "os.remove",
                     "unlink(", "shutil.", "subprocess"):
        assert verboten not in code, \
            "Der Wartungsvorbehalt darf '%s' nicht verwenden." % verboten
    assert not re.search(r"open\([^)]*['\"][wax]", code), \
        "Der Wartungsvorbehalt oeffnet eine Datei zum Schreiben."


def test_wv19_bestaetigungswort_ist_nicht_versehentlich_tippbar():
    """
    WV19 - Das Wort muss ein Wort sein und kein Tastendruck.

    Die Festlegung steht in documents/rules-cli.md Abschnitt 7: "Kein blosser
    Tastendruck - ein Tastendruck ist eine Reflexbewegung, ein getipptes Wort
    ist eine Entscheidung."
    """
    assert BESTAETIGUNGSWORT == "OHNE WARTUNGSFENSTER"
    assert BESTAETIGUNGSWORT.isascii()
    assert BESTAETIGUNGSWORT == BESTAETIGUNGSWORT.upper()
    assert " " in BESTAETIGUNGSWORT
    assert len(BESTAETIGUNGSWORT) >= 15
    # Die drei ueblichen Schnellantworten duerfen nicht durchgehen.
    for schnell in ("y", "Y", "j", "J", "ja", "yes", "\n", " "):
        assert wort_akzeptiert(schnell) is False


def test_wv20_umschrift_ersetzt_sichtbar():
    """
    WV20 - Umlaute werden umgeschrieben, alles Weitere wird zu '?'.

    Ein Fragezeichen faellt beim Lesen auf, ein stillschweigend geloeschtes
    Zeichen nicht - deshalb wird ersetzt und nicht entfernt.
    """
    assert nur_ascii("Schemaänderung") == "Schemaaenderung"
    assert nur_ascii("Grösse ÄÖÜ") == "Groesse AeOeUe"
    # Der lange Gedankenstrich kommt aus den Begruendungen von cli_support.
    assert nur_ascii("Datei nicht vorhanden — nichts zu sperren") == \
        "Datei nicht vorhanden - nichts zu sperren"
    assert nur_ascii("Tür 你") == "Tuer ?"
    assert nur_ascii("") == ""
    assert nur_ascii(None) == ""


# -----------------------------------------------------------------------------
# WV21-WV22 und WV25-WV29 - der Schreibschutz
#
# DIE GESCHICHTE DIESER GRUPPE, weil sie erklaert, warum sie so aussieht:
#
#   Der Vermerk zu Build 609 (Abschnitt 6) hielt fest, dass der
#   read-only-Zweig von exklusiv_pruefen im Bestand von keinem Test beruehrt
#   wird, und vermutete, eine versiegelte Datei melde "readonly" und gelte
#   damit zu Recht als ruhig. In Build 610 stand hier ein Test, der genau
#   diese Vermutung geprueft hat.
#
#   DER REGRESSIONSLAUF VON mc HAT SIE WIDERLEGT. Auf einer echten
#   schreibgeschuetzten Datei meldet die Probe nicht "readonly", sondern
#   "exklusiv erhalten" - und zwar AUCH DANN, wenn ein Leser oder sogar ein
#   Schreiber die Datei haelt. Nachgestellt am 2026-07-31 als
#   Nicht-root-Eigentuemer, Journalmodus 'delete':
#
#     schreibbar, Leser haelt SHARED   -> (False, 'database is locked')  richtig
#     versiegelt, Leser haelt SHARED   -> (True,  'exklusiv erhalten')   BLIND
#     versiegelt, Schreiber haelt EX   -> (True,  'exklusiv erhalten')   BLIND
#
#   Der Grund: SQLite stuft eine nicht beschreibbare Datei still auf
#   nur-lesend zurueck, und eine nur lesende Verbindung nimmt beim
#   'BEGIN EXCLUSIVE' keine Sperre - es gelingt folgenlos.
#
#   FOLGE FUER DAS BAUTEIL (Build 611): Eine schreibgeschuetzte Datei wird gar
#   nicht erst geprobt, sondern als UNPRUEFBAR gefuehrt und benannt. Die
#   Tests hier pruefen jetzt das BELEGTE Verhalten, nicht mehr die widerlegte
#   Vermutung.
# -----------------------------------------------------------------------------

def test_wv21_readonly_meldung_ist_KEINE_ruhe(monkeypatch):
    """
    WV21 - MELDET die Sperrprobe 'readonly', dann ist das NICHT MESSBAR.

    ================================================================
    DIESER TEST IST IN BUILD 648 UMGEDREHT WORDEN (Vorgang 96f2b18f).
    ================================================================
    Bis Build 647 hiess er 'readonly_meldung_gilt_als_ruhig' und verlangte
    ok is True. Er bildete damit die WIDERLEGTE VERMUTUNG aus dem Vermerk zu
    Build 609 ab: eine versiegelte Datei melde 'readonly' und gelte deshalb
    zu Recht als ruhig.

    Beide Haelften des Satzes sind falsch. Die zweite zuerst: Eine Meldung
    'readonly' heisst, dass NICHT GEMESSEN werden konnte - nicht, dass
    niemand die Datei haelt. Ein Beweis, der auch dann gelingt, wenn gar
    nicht gemessen wurde, ist keiner.

    (Die erste Haelfte - dass eine versiegelte Datei ueberhaupt 'readonly'
    meldet - war ebenfalls falsch; sie meldete 'exklusiv erhalten'. Das ist
    der Gegenstand von WV22.)

    Geprueft mit einer gestellten Meldung, damit die Aussage auf jedem System
    dieselbe ist: hier geht es um die EINORDNUNG der Meldung, nicht um das
    Betriebssystem.
    """
    import maintenance.cli_support as cs

    def _wirft(*_a, **_k):
        raise sqlite3.OperationalError("attempt to write a readonly database")

    monkeypatch.setattr(cs.sqlite3, "connect", _wirft)
    befund = cs.exklusiv_beurteilen(_QUELLE)      # existierende Datei
    assert befund.zustand == "nicht_messbar"
    assert befund.ist_ruhig is False
    assert "readonly" in befund.grund.lower()
    # Und die alte, zweiwertige Form sagt jetzt ebenfalls 'nicht frei' -
    # die sichere Seite fuer Aufrufer, die die Dreiwertigkeit nicht kennen.
    assert cs.exklusiv_pruefen(_QUELLE)[0] is False


def test_wv22_sperrprobe_ist_auf_schreibgeschuetzten_dateien_nicht_mehr_blind(tmp_path):
    """
    WV22 - AUS DEM BEFUND IST DIE BEHEBUNG GEWORDEN (Build 648).

    Bis Build 647 hielt dieser Test den MANGEL fest: Er verlangte, dass die
    Sperrprobe auf einer schreibgeschuetzten Datei 'exklusiv erhalten'
    meldet, obwohl ein Leser sie haelt. Sein eigener Kopf sagte dazu: "Wuerde
    SQLite oder cli_support das eines Tages aendern, faellt dieser Test auf."

    GENAU DAS IST EINGETRETEN - nicht durch SQLite, sondern durch die
    Behebung von 96f2b18f. Der Test verlangt jetzt das Gegenteil: eine
    Datei, die der ausfuehrende Prozess nicht beschreiben kann, ist NICHT
    MESSBAR und zaehlt nicht als Ruhe.

    Setzt das ausfuehrende Konto den Schreibschutz nicht durch (root unter
    Linux uebergeht die Rechtebits des Eigentuemers), wird die Pruefung mit
    ANGEGEBENEM Grund uebersprungen - ein ausgewiesenes Auslassen und kein
    stilles (Grundregel 1). Die daraus gezogene FOLGE ist ueber WV25-WV28
    auf jedem System gedeckt.
    """
    db = _db(tmp_path / "versiegelt.db")
    os.chmod(db, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    try:
        try:
            with open(db, "ab"):
                pass
            pytest.skip(
                "Das ausfuehrende Konto uebergeht den Schreibschutz "
                "(root/Administrator). Der Befund laesst sich hier nicht "
                "nachstellen; die Folge daraus ist ueber WV25-WV28 gedeckt.")
        except (PermissionError, OSError):
            pass

        # Ein LESER haelt die Datei - auf einer schreibbaren Datei wuerde die
        # Probe das erkennen (siehe tests/test_maintenance_cli.py).
        leser = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
        leser.execute("BEGIN")
        leser.execute("SELECT * FROM t").fetchall()
        try:
            ok, grund = exklusiv_pruefen(db, timeout_s=0.5)
        finally:
            leser.rollback()
            leser.close()

        assert ok is False, (
            "Die Sperrprobe meldet auf einer schreibgeschuetzten Datei "
            "wieder eine folgenlose Zusage (%r). Das ist der Rueckfall in "
            "96f2b18f." % (grund,))
        assert ist_versiegelt(db) is True
    finally:
        os.chmod(db, stat.S_IRUSR | stat.S_IWUSR)


def test_wv25_unpruefbar_erzwingt_die_wortabfrage_trotz_fenster():
    """
    WV25 - Eine unpruefbare Datei nimmt dem Wartungsfenster seine Wirkung.

    Ueber eine Datei, deren Ruhe niemand MESSEN kann, hat auch das Fenster
    nichts ausgesagt. Die Wortabfrage ist dann die einzige verbleibende
    Stelle, an der noch ein Mensch hinsieht.
    """
    befunde = (_ruhig(), _unpruefbar())
    assert naechster_schritt(True, befunde, True) == ERGEBNIS_WORTABFRAGE
    assert naechster_schritt(False, befunde, True) == ERGEBNIS_WORTABFRAGE
    # Ohne Terminal bleibt es beim Abbruch - auch mit Fenster.
    assert naechster_schritt(True, befunde, False) == ERGEBNIS_KEIN_TERMINAL
    # Und BELEGT schlaegt weiterhin alles.
    assert naechster_schritt(True, (_belegt(), _unpruefbar()), True) == \
        ERGEBNIS_GESPERRT


def test_wv26_unpruefbare_datei_wird_benannt():
    """
    WV26 - Sie steht in jedem Text, in dem sie vorkommen kann, unter eigener
    Ueberschrift - nicht unauffaellig zwischen den ruhigen.
    """
    befunde = (_ruhig("data/coordinator.db"),
               _unpruefbar("data/forensic/forensic_1488.db"))

    frage = text_frage("forensic_index_upgrade", "baut Indizes auf", befunde)
    assert "NICHT PRUEFBAR" in frage
    assert "forensic_1488.db" in frage
    assert "schreibgeschuetzt" in frage
    # Die Ueberschrift darf NICHT behaupten, es fehle ein Fenster - es kann
    # eines gesetzt sein und trotzdem gefragt werden.
    assert "kein Wartungsfenster gesetzt" not in frage.split("\n")[0]
    # GENAU EINMAL genannt: doppelt gelesener Text wird beim dritten Mal
    # ueberblaettert, und dann steht der Hinweis zwar da, wird aber nicht
    # gelesen.
    assert frage.count("forensic_1488.db") == 1
    assert frage.count("coordinator.db") == 1

    # Sonderfall: gar keine ruhige Datei. Der Text muss trotzdem tragen.
    nur_offen = text_frage("forensic_index_upgrade", "baut Indizes auf",
                           (_unpruefbar("data/forensic_1488.db"),))
    assert "NICHT PRUEFBAR" in nur_offen
    assert "Geprobt und ruhig" not in nur_offen
    assert BESTAETIGUNGSWORT in nur_offen

    ohne_terminal = text_kein_terminal("forensic_index_upgrade", befunde)
    assert "NICHT PRUEFBAR" in ohne_terminal
    assert "Ein Wartungsfenster hilft hier NICHT weiter" in ohne_terminal

    gesperrt = text_gesperrt("x", (_belegt("data/a.db"),) + befunde)
    assert "NICHT PRUEFBAR" in gesperrt


def test_wv27_freigabe_verschweigt_nicht_worauf_sie_sich_nicht_stuetzt():
    """
    WV27 - Wer die Freigabezeile spaeter im Protokoll liest, soll sehen, dass
    hier eine Entscheidung getroffen und nicht ein Messwert abgelesen wurde.
    """
    text = text_lauf("forensic_index_upgrade", None,
                     (_ruhig(), _unpruefbar("data/forensic_1488.db")))
    assert "NICHT messbar" in text
    assert "forensic_1488.db" in text
    assert "Entscheidung der aufrufenden Person" in text
    # Ohne unpruefbare Datei steht der Vermerk nicht da - sonst laese man
    # ihn irgendwann nicht mehr.
    assert "NICHT messbar" not in text_lauf("migrate", None, (_ruhig(),))


def test_wv28_versiegelte_datei_wird_gar_nicht_erst_geprobt(data_dir,
                                                            monkeypatch):
    """
    WV28 - Der vollstaendige Ablauf mit einer versiegelten Datei.

    Der Schreibschutz wird hier GESTELLT (ist_versiegelt wird ersetzt) statt
    ueber die Rechte des Dateisystems gesetzt: als root laesst er sich nicht
    herstellen, und dieser Test soll auf jedem System dasselbe sagen. Was er
    prueft, ist das Verhalten des Bauteils - nicht das des Betriebssystems.

    Zusaetzlich wird belegt, dass die Sperrprobe fuer diese Datei GAR NICHT
    AUFGERUFEN wird: eine Probe, deren Ergebnis feststeht, ist keine.
    """
    coordinator = _db(data_dir / "coordinator.db")
    forensic = _db(data_dir / "forensic" / "forensic_1488.db")

    import maintenance.wartungsvorbehalt as wv
    monkeypatch.setattr(wv, "ist_versiegelt",
                        lambda p: Path(p).name.startswith("forensic_"))
    geprobt = []
    # BUILD 648: Die Sperrprobe heisst jetzt 'exklusiv_beurteilen' und
    # liefert drei Zustaende. DIE AUSSAGE DIESES TESTS BLEIBT DIESELBE -
    # eine versiegelte Datei wird gar nicht erst angefasst; nur der
    # ueberwachte Name hat sich geaendert.
    echt = wv.exklusiv_beurteilen

    def _mitschreiben(pfad, **kw):
        geprobt.append(Path(pfad).name)
        return echt(pfad, **kw)

    monkeypatch.setattr(wv, "exklusiv_beurteilen", _mitschreiben)

    # Ein Fenster ist gesetzt und deckt alles ab - es hilft trotzdem nicht.
    WindowFlag.neu(angefordert_von="pruefer", grund="Test",
                   ziel=["all"]).schreiben(MaintenancePaths(data_dir))

    m = _Mitschrift(antwort=BESTAETIGUNGSWORT)
    befund = wv.wartungsvorbehalt(
        data_dir, [coordinator, forensic],
        werkzeug="forensic_index_upgrade",
        was_geschieht="baut Indizes in forensic_1488.db auf",
        eingabe=m.eingabe, ausgabe=m.ausgabe, terminal=True)

    assert geprobt == ["coordinator.db"], \
        "Die versiegelte Datei darf gar nicht erst geprobt werden."
    assert len(m.fragen) == 1, "Trotz Fenster muss gefragt werden."
    assert len(befund.unpruefbare()) == 1
    assert befund.ergebnis == ERGEBNIS_LAUF
    assert "NICHT messbar" in befund.text

    # Gegenprobe: ohne Terminal bricht derselbe Aufruf ab.
    m2 = _Mitschrift(antwort=None)
    befund2 = wv.wartungsvorbehalt(
        data_dir, [coordinator, forensic],
        werkzeug="forensic_index_upgrade",
        was_geschieht="baut Indizes auf",
        eingabe=m2.eingabe, ausgabe=m2.ausgabe, terminal=False)
    assert befund2.ergebnis == ERGEBNIS_KEIN_TERMINAL
    assert befund2.rueckgabewert == RUECKGABE_VORBEHALT


def test_wv29_ist_versiegelt_fragt_nur_und_fasst_nichts_an(tmp_path):
    """
    WV29 - Die Erkennung darf die Datei nicht anfassen.

    Ein Schreibversuch waere das naheliegende Mittel und das falsche: dieses
    Bauteil laeuft, wenn noch nichts entschieden ist. os.access fragt nur.
    """
    fehlt = tmp_path / "gibtsnicht.db"
    assert ist_versiegelt(fehlt) is False, \
        "Eine nicht vorhandene Datei ist nicht versiegelt - sie ist ruhig."
    assert not fehlt.exists(), "Die Erkennung hat eine Datei angelegt."

    db = _db(tmp_path / "normal.db")
    vorher = db.stat().st_mtime_ns
    assert ist_versiegelt(db) is False
    assert db.stat().st_mtime_ns == vorher, \
        "Die Erkennung hat die Datei veraendert."


def test_wv23_nicht_vorhandene_datei_steht_im_bericht(data_dir):
    """
    WV23 - Eine noch nicht angelegte Datei gilt als ruhig - und taucht
    trotzdem im Bericht auf, mit ihrem Grund.

    Das ist der Regelfall bei einer Erstmigration. Wichtig ist, dass die
    Auskunft im Text steht: 'ruhig, weil es sie noch nicht gibt' ist eine
    andere Aussage als 'ruhig, weil sie niemand haelt'.
    """
    fehlt = data_dir / "gibtsnochnicht.db"
    befunde = sperren_pruefen([fehlt])
    assert len(befunde) == 1 and befunde[0].ist_ruhig()
    assert "nicht vorhanden" in befunde[0].grund

    text = text_kein_terminal("consolidate_default_db", befunde)
    assert "gibtsnochnicht.db" in text
    assert "nicht vorhanden" in text


def test_wv24_hat_terminal_ist_nicht_ueber_eine_pipe_zu_haben():
    """
    WV24 - Massgeblich ist die Standardeingabe.

    Sonst genuegte ein 'echo "OHNE WARTUNGSFENSTER" | python ...', um den
    Vorbehalt zu umgehen - und er waere eine Formalie.
    """
    class _Pipe:
        def isatty(self):
            return False

    class _Tty:
        def isatty(self):
            return True

    class _Kaputt:
        def isatty(self):
            raise ValueError("I/O operation on closed file")

    assert hat_terminal(_Pipe()) is False
    assert hat_terminal(_Tty()) is True
    assert hat_terminal(_Kaputt()) is False
    # Ohne Argument wird sys.stdin befragt; unter pytest ist das kein
    # Terminal - der Aufruf muss trotzdem ohne Ausnahme durchlaufen.
    assert isinstance(hat_terminal(), bool)
