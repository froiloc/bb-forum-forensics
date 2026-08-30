# =============================================================================
# tests/test_laufkopf.py
#
# Build 746: Der Herkunftsnachweis eines Laufs.
#
# WOZU DAS UNTER EINEN TEST GEHOERT
#
# Am 31.08.2026 lag eine Ausgabe von tools/postid_nachtragen.py vor, die
# ZEICHENGLEICH war mit der aus dem Build davor. Zwei Erklaerungen waren
# damit gleich gut vereinbar: der neue Stand ist nicht eingespielt worden -
# oder er ist eingespielt und hat an dieser Stelle nichts geaendert. Das
# sind zwei voellig verschiedene Lagen mit zwei voellig verschiedenen
# naechsten Schritten, und die Ausgabe liess nicht erkennen, welche vorlag.
#
# Grundregel 8 verlangt MD5-Pruefsummen der im Einsatz befindlichen Dateien.
# Bisher wurden sie ANGEFORDERT; ab jetzt gibt der Lauf sie von sich aus
# aus. Diese Tests halten fest, dass er das auch weiter tut - und dass er
# ein Nichtwissen als Nichtwissen ausweist statt als Zahl.
#
# LK01  die Pruefsumme stimmt mit der von hashlib gebildeten ueberein
# LK02  eine fehlende Datei wird als FEHLT benannt, nicht uebergangen
# LK03  eine unlesbare build.json ergibt 'NICHT FESTSTELLBAR', nicht 0
# LK04  der Kopf nennt Werkzeug, Build, Python und jede Datei
# LK05  er wirft nie - auch nicht bei einer Datei ohne Leserecht
#
# Beleg: management/maintenance/laufkopf.py
# =============================================================================

import hashlib

from management.maintenance.laufkopf import Laufkopf, WURZEL


def test_LK01_die_pruefsumme_ist_die_von_hashlib():
    # GEGEN DIE ECHTE DATEI, nicht gegen eine erfundene: eine Pruefsumme,
    # die nur mit sich selbst uebereinstimmt, belegt nichts.
    rel = "management/maintenance/laufkopf.py"
    soll = hashlib.md5((WURZEL / rel).read_bytes()).hexdigest()
    assert Laufkopf.md5_von(WURZEL / rel) == soll


def test_LK02_eine_fehlende_datei_wird_benannt():
    # GRUNDREGEL 1: nichts still uebergehen. Eine Datei, die der Kopf
    # auslaesst, ist eine Datei, deren Version niemand geprueft hat.
    zeilen = Laufkopf("probe", ["gibt/es/nicht.py"]).zeilen()
    text = "\n".join(zeilen)
    assert "gibt/es/nicht.py" in text
    assert "FEHLT" in text


def test_LK03_unlesbare_buildnummer_ist_nicht_null(monkeypatch):
    # 0 WAERE EINE BUILDNUMMER. 'nicht feststellbar' ist etwas anderes, und
    # die beiden zu vermengen hiesse, ein Nichtwissen als Wissen auszugeben.
    monkeypatch.setattr(Laufkopf, "buildnummer", staticmethod(lambda: None))
    text = "\n".join(Laufkopf("probe", []).zeilen())
    assert "NICHT FESTSTELLBAR" in text
    assert "Build    : 0" not in text


def test_LK04_der_kopf_nennt_alles_noetige():
    rel = "management/maintenance/laufkopf.py"
    text = "\n".join(Laufkopf("anker_diagnose", [rel]).zeilen())
    assert "Grundregel 8" in text
    assert "Werkzeug : anker_diagnose" in text
    assert "Build    :" in text
    assert "Python   :" in text
    assert rel in text
    # Und die Anleitung, was mit den Summen zu tun ist - eine Zahl ohne
    # Auslegung wird ausgelegt, und zwar von dem, der sie zuerst liest.
    assert "MD5SUMS" in text
    # BUILD 747: html5lib bestimmt die Zerlegung mit und gehoert deshalb in
    # den Herkunftsnachweis - eine andere Fassung kann ein anderes Ergebnis
    # bedeuten.
    assert "html5lib :" in text


def test_LK05_der_kopf_wirft_nie(tmp_path):
    # Ein Diagnosewerkzeug, das wegen seines eigenen Kopfes nicht laeuft,
    # ist schlimmer als eines mit unvollstaendigem Kopf.
    verzeichnis = tmp_path / "kein_file"
    verzeichnis.mkdir()
    # Ein Verzeichnis statt einer Datei: open() scheitert, der Kopf nicht.
    ergebnis = Laufkopf.md5_von(verzeichnis)
    assert "nicht lesbar" in ergebnis


def test_LK06_die_werkzeuge_nennen_ihre_tragenden_dateien():
    # GEGENPROBE ZUM SINN DER SACHE: der Kopf nuetzt nur, wenn er die Datei
    # nennt, an der die Aenderung sitzt. Fuer beide Werkzeuge ist das die
    # Annaeherung - sie hat den Ankerbruch verursacht UND behoben.
    # Geladen wird ueber den Dateipfad: 'tools/' ist bewusst KEIN Paket
    # (die Werkzeuge setzen sich ihren Pfad selbst), und ein __init__.py nur
    # fuer einen Test waere eine Aenderung am Auslieferungsstand um des
    # Tests willen.
    import importlib.util
    for name in ("anker_diagnose", "postid_nachtragen"):
        spec = importlib.util.spec_from_file_location(
            "werkzeug_" + name, str(WURZEL / "tools" / (name + ".py")))
        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)
        getragen = modul._GETRAGEN_VON
        assert "report_render/html5_zerleger.py" in getragen, modul.__name__
        assert "report_render/absatz_finder.py" in getragen, modul.__name__
