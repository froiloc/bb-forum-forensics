# =============================================================================
# tests/test_backup_verdraengung.py
# IT-Forensisches Ermittlungswerkzeug - Vorgang 651e6d84
# =============================================================================
# Macht aus der EINMALIGEN Nachpruefung eine STEHENDE.
#
# WARUM DAS DER EIGENTLICHE GEWINN IST: Ein Werkzeug, das man von Hand faehrt,
# beantwortet die Frage einmal. Der Vorgang 651e6d84 ist aber kein Ereignis,
# sondern eine Eigenschaft der Aufbewahrung - und die kann bei jedem Umbau von
# '_prune' wieder verlorengehen. Ab hier faellt das im naechsten
# Regressionslauf auf und nicht erst, wenn jemand eine Wiederherstellung
# braucht.
#
# Die Proben stehen NICHT hier, sondern in tools/diag_backup_verdraengung.py.
# Das ist Absicht: Betrieb und Regressionslauf sollen DIESELBE Messung fahren.
# Zwei Fassungen derselben Probe waeren zwei Gelegenheiten, sie verschieden
# falsch zu machen - und die Betriebsseite haette am Ende ein Werkzeug, dessen
# Ergebnis niemand mit dem Testlauf vergleichen kann.
#
# BV01 - die SELBSTPROBE: die Nachpruefung sieht den alten Fehler ueberhaupt
# BV02 - eine defekte Kopie verdraengt KEINE gute Generation (der Kernfall)
# BV03 - die Gegenprobe: die Aufbewahrung loescht ueberhaupt etwas
# BV04 - ein echter Abbruchrest wird beiseitegelegt und zaehlt nicht
# BV05 - das Werkzeug im Ganzen, ueber main(), Rueckgabewert 0
# BV06 - das Werkzeug verweigert ein nicht leeres Arbeitsverzeichnis
#
# Version: v0.8.642 - Build: 642 - 2026-08-01
# =============================================================================

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

from management.backup.backup_executor import (              # noqa: E402
    DEFEKT_ENDUNG, BackupExecutor,
)


def _lade():
    spec = importlib.util.spec_from_file_location(
        "diag_backup_verdraengung_tool",
        _WURZEL / "tools" / "diag_backup_verdraengung.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


diag = _lade()


class _StillerBericht(diag.Bericht):
    """Wie der Bericht des Werkzeugs, nur ohne Ausgabe auf die Konsole."""

    def sagen(self, text: str = "") -> None:
        self.zeilen.append(text)


@pytest.fixture
def arbeit(tmp_path):
    d = tmp_path / "p651"
    d.mkdir()
    diag._db_bauen(d / "quelle_klein.db", zeilen=200)
    return d


# -----------------------------------------------------------------------------
# BV01 - die Selbstprobe
# -----------------------------------------------------------------------------

def test_bv01_selbstprobe_sieht_den_alten_fehler(arbeit):
    """
    BV01, UND SIE STEHT MIT ABSICHT AN ERSTER STELLE.

    Bevor irgendetwas anderes geprueft wird, muss feststehen, dass die
    Nachpruefung den Fehler ueberhaupt sehen KANN. Gefahren wird derselbe
    Fall gegen den Stand VOR Build 625 - '_traegt_inhalt' liefert dort immer
    True, das ist genau die Pruefung, die Build 625 hinzugefuegt hat.

    Schlaegt BV01 nicht an, sind BV02 und BV04 blind, und ihr 'bestanden'
    belegt nichts. Genau dieser Fall - eine gruene Pruefung, die nichts misst
    - ist schlimmer als eine rote: er beendet die Suche.
    """
    ber = _StillerBericht()
    assert diag.probe_s(arbeit, ber) is True, "\n".join(ber.zeilen)
    # Und die Zahlen dazu, damit im Fehlerfall lesbar ist, WAS passiert ist:
    text = "\n".join(ber.zeilen)
    assert "Gute ueberlebt: 2 von 3" in text, text
    assert "Defekte zaehlt: JA" in text, text


# -----------------------------------------------------------------------------
# BV02 / BV03 - der Kernfall und seine Gegenprobe
# -----------------------------------------------------------------------------

def test_bv02_defekte_kopie_verdraengt_keine_gute_generation(arbeit):
    """
    BV02, DER KERNFALL DES VORGANGS 651e6d84.

    Drei gute Generationen, dazu eine 0-Byte-Datei mit dem JUENGSTEN
    Zeitstempel und einem zaehlenden Namen. Aufbewahrung 3.

    Das ist keine Nachstellung des Symptoms - es IST der Zustand, den der
    Vorgang beschreibt: 'die Datei bleibt liegen und traegt den aktuellen
    Zeitstempel im Namen'.
    """
    ber = _StillerBericht()
    assert diag.probe_a(arbeit, ber) is True, "\n".join(ber.zeilen)

    dest = arbeit / "probe_a"
    zaehlend = diag._zaehlende(dest, "coordinator")
    beiseite = [n for n in os.listdir(dest) if n.endswith(DEFEKT_ENDUNG)]
    assert len(zaehlend) == 3
    assert len(beiseite) == 1
    # Die defekte Datei ist NICHT geloescht worden - sie ist ein Beleg.
    assert (dest / beiseite[0]).exists()


def test_bv03_gegenprobe_die_aufbewahrung_loescht_ueberhaupt(arbeit):
    """
    BV03: Bei VIER guten Generationen und Aufbewahrung 3 muss die aelteste
    verschwinden.

    Ohne diese Gegenprobe bestuende BV02 auch dann, wenn '_prune' gar nichts
    mehr loescht. Das waere kein behobener Vorgang, sondern ein neuer: ein
    unbegrenzt wachsender Sicherungsordner, bis die Platzvorabpruefung jeden
    weiteren Lauf verweigert (TE5).
    """
    ber = _StillerBericht()
    assert diag.probe_b(arbeit, ber) is True, "\n".join(ber.zeilen)
    assert len(diag._zaehlende(arbeit / "probe_b", "coordinator")) == 3


# -----------------------------------------------------------------------------
# BV04 - der echte Abbruchrest
# -----------------------------------------------------------------------------

def test_bv04_echter_abbruchrest_zaehlt_nicht(arbeit):
    """
    BV04: Ein ECHTER Abbruchrest - erzeugt, indem ein laufendes
    'VACUUM INTO' abgeschossen wird.

    DIESE PRUEFUNG DECKT DEN ZWEITEN BEFUND AUS BUILD 625 MIT AB, und der
    ist der schwerere: 'PRAGMA integrity_check' meldet auf der
    zurueckgerollten 0-Byte-Datei 'ok'. Wer nur den integrity_check prueft,
    bekommt hier ein 'bestanden' fuer ein Nichts.

    UEBERSPRUNGEN STATT ERFUNDEN: Ist die Platte so schnell, dass das
    'VACUUM INTO' fertig ist, bevor der Abbruch greift, wird die Pruefung
    als skipped gemeldet - mit Grund. Ein nicht gefahrener Test ist kein
    bestandener Test (Grundregel 1); ein gruenes Ergebnis fuer eine Messung,
    die nicht stattgefunden hat, waere eine Unwahrheit.
    """
    diag._db_bauen(arbeit / "quelle_gross.db",
                   zeilen=diag.ABBRUCH_QUELLE_MB * 1800)
    ber = _StillerBericht()
    ergebnis = diag.probe_c(arbeit, ber)

    if ber.nicht_gefahren:
        pytest.skip("Abbruchrest nicht erzeugbar: %s"
                    % ber.nicht_gefahren[0][1])
    assert ergebnis is True, "\n".join(ber.zeilen)
    text = "\n".join(ber.zeilen)
    assert "Zaehlt noch  : NEIN" in text, text


# -----------------------------------------------------------------------------
# BV05 / BV06 - das Werkzeug im Ganzen
# -----------------------------------------------------------------------------

def test_bv05_werkzeug_laeuft_durch_und_meldet_0(tmp_path, capsys):
    """
    BV05: Der Aufruf, den die Betriebsseite faehrt - ueber main().

    Geprueft wird auch, dass die NICHT gefahrene Probe C namentlich im
    Schlussbericht steht. Ein halber Lauf darf nicht aussehen wie ein
    ganzer.
    """
    ziel = tmp_path / "lauf"
    rc = diag.main(["--arbeitsverzeichnis", str(ziel)])
    ausgabe = capsys.readouterr().out
    assert rc == 0, ausgabe
    assert "S - Selbstprobe" in ausgabe
    assert "NICHT GEPRUEFT (1)" in ausgabe
    assert "C - echter Abbruchrest" in ausgabe
    # Ohne '--behalten' bleibt nichts liegen.
    assert not ziel.exists()


def test_bv06_nicht_leeres_verzeichnis_wird_abgelehnt(tmp_path):
    """
    BV06: Das Werkzeug legt nur in einem eigenen, leeren Verzeichnis an.

    Das ist keine Bequemlichkeit, sondern die Zusage, auf die sich jemand
    verlaesst, der es in einer PROD-Umgebung aufruft: Ein vorhandener
    Bestand wird nicht angetastet. Rueckgabewert 2 - nicht geprueft, nicht
    bestanden.
    """
    ziel = tmp_path / "belegt"
    ziel.mkdir()
    (ziel / "wichtig.db").write_bytes(b"nicht anfassen")
    assert diag.main(["--arbeitsverzeichnis", str(ziel)]) == 2
    assert (ziel / "wichtig.db").read_bytes() == b"nicht anfassen"
