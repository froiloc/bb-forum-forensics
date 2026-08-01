# =============================================================================
# tests/test_leerbefund.py
# IT-Forensisches Ermittlungswerkzeug - "Leerbefund ist kein Erfolg"
# =============================================================================
# Drei Vorgaenge, ein Muster - deshalb stehen sie in EINER Suite:
#
#   d30b3d95  'ausschleus_admin verify' meldete OK auf einem leeren Verzeichnis
#   0329896b  'prepare_deployment' endete mit 0 trotz gescheitertem Download
#   e9522fe2  'backup_admin list' lieferte immer 0, auch bei defekten Sicherungen
#
# DAS MUSTER: Ein Werkzeug findet nichts vor - und meldet Erfolg. Aus "es gibt
# nichts zu pruefen" wird "alles geprueft und in Ordnung". Wer den
# Rueckgabewert auswertet statt die Ausgabe zu lesen - und genau dafuer ist er
# da -, bekommt eine Bestaetigung fuer etwas, das nicht existiert.
#
# In einem forensischen Verfahren wiegt das schwer: Die Ausschleusung ist der
# Weg, auf dem Material das Haus verlaesst; die Auslieferung ist der Weg, auf
# dem die Anlage auf die VM kommt; die Sicherung ist das, worauf man sich
# verlaesst, wenn alles andere weg ist.
#
# LB01-LB05  d30b3d95 - drei Lagen statt zwei
# LB10-LB13  0329896b - Vollzaehligkeit und Rueckgabewert
# LB20-LB22  e9522fe2 - der Befund im Rueckgabewert (in Build 626/627 behoben,
#            hier zum ersten Mal maschinell nachgehalten)
#
# Version: v0.8.647 - Build: 647 - 2026-08-01
# =============================================================================

import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

from management.export.export_envelope import ExportContext      # noqa: E402
from management.export.staging import StagingArea                # noqa: E402
from management.export import ausschleus_admin                   # noqa: E402


def _kontext() -> ExportContext:
    return ExportContext(behoerde="Polizei NRW", aktenzeichen="AZ-1",
                         ersteller="pruefer", build_number=647,
                         generated_at="2026-08-01T00:00:00Z")


def _datei(verz: Path, name: str, inhalt: bytes = b"X") -> str:
    p = verz / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(inhalt)
    return str(p)


# =============================================================================
# d30b3d95 - 'verify' unterscheidet drei Lagen statt zwei
# =============================================================================

def test_lb01_kein_manifest_ist_kein_ok(tmp_path):
    """
    LB01, DER KERN DES VORGANGS. Ein leeres Verzeichnis ohne Manifest darf
    kein 'ok' liefern.

    GEMESSEN VOR DER BEHEBUNG (Build 646): 'verify --dir /tmp/leer' meldete
    "OK - alle Artefakte stimmen mit dem Manifest ueberein" und den
    Rueckgabewert 0. Der Grund lag in 'load()': Es liefert bei fehlendem
    Manifest ein frisches Grundgeruest mit LEERER Artefaktliste, und danach
    waren alle drei Befundlisten leer.
    """
    leer = tmp_path / "leer"
    leer.mkdir()
    res = StagingArea(str(leer)).verify()
    assert res["kein_manifest"] is True
    assert res["ok"] is False, (
        "Ohne Manifest darf 'ok' nicht True sein - die Listen sind nur "
        "deshalb leer, weil nichts da war, woran man haette messen koennen.")


def test_lb02_leeres_paket_mit_manifest_bleibt_gueltig(tmp_path):
    """
    LB02, DIE ABGRENZUNG - und sie ist der Grund, warum die Behebung nicht
    einfach 'leeres Verzeichnis = Fehler' lauten durfte.

    Ein Paket OHNE Artefakte, aber MIT Manifest, ist eine Aussage: Jemand hat
    ein Paket erzeugt, das nichts enthaelt. Das ist ungewoehnlich, aber
    gueltig - und es unterscheidet sich von "hier wurde nie etwas erzeugt".
    """
    d = tmp_path / "leerpaket"
    area = StagingArea(str(d))
    area.finalize(_kontext())
    res = area.verify()
    assert res["kein_manifest"] is False
    assert res["ok"] is True, "Ein leeres Paket MIT Manifest bleibt gueltig."


def test_lb03_befund_bleibt_befund(tmp_path):
    """
    LB03, DIE GEGENPROBE ZUR GEGENPROBE (TE5): Die Behebung darf die
    bisherigen Befunde nicht verschluckt haben. Ein manipuliertes Artefakt
    muss weiterhin auffallen - und zwar als Abweichung, NICHT als
    'kein Manifest'.
    """
    d = tmp_path / "paket"
    area = StagingArea(str(d))
    area.add_artifact(_datei(tmp_path, "a.pdf", b"ORIG"), kind="k",
                      source_ref="s", unbedenklich=True, cleared_by="h1",
                      added_at="t")
    assert area.verify()["ok"] is True
    (d / "a.pdf").write_bytes(b"MANIPULIERT")
    res = area.verify()
    assert res["ok"] is False
    assert res["kein_manifest"] is False
    assert res["mismatched"] == ["a.pdf"]


def test_lb04_werkzeug_liefert_drei_rueckgabewerte(tmp_path, capsys):
    """
    LB04: Am Werkzeug gemessen, nicht nur am Bauteil - 0, 1 und 2 muessen
    unterscheidbar sein, ohne dass jemand die Ausgabe liest.
    """
    class _Args:
        def __init__(self, d): self.dir = str(d)

    # (a) kein Manifest -> 2
    leer = tmp_path / "leer"
    leer.mkdir()
    assert ausschleus_admin._do_verify(_Args(leer)) == 2
    ausgabe = capsys.readouterr()
    assert "KEIN PAKET" in ausgabe.err
    assert "OK" not in ausgabe.out

    # (b) heiles Paket -> 0
    d = tmp_path / "paket"
    area = StagingArea(str(d))
    area.add_artifact(_datei(tmp_path, "b.pdf"), kind="k", source_ref="s",
                      unbedenklich=True, cleared_by="h1", added_at="t")
    assert ausschleus_admin._do_verify(_Args(d)) == 0

    # (c) Abweichung -> 1
    (d / "b.pdf").write_bytes(b"ANDERS")
    assert ausschleus_admin._do_verify(_Args(d)) == 1


def test_lb05_meldung_nennt_das_verzeichnis(tmp_path, capsys):
    """
    LB05: Die Meldung nennt das VERZEICHNIS. Wer 'verify' in einem Skript
    ueber mehrere Pakete laufen laesst, muss ohne Nachdenken sehen, welches
    gemeint ist.
    """
    class _Args:
        def __init__(self, d): self.dir = str(d)
    leer = tmp_path / "ganz_bestimmtes_verzeichnis"
    leer.mkdir()
    ausschleus_admin._do_verify(_Args(leer))
    assert "ganz_bestimmtes_verzeichnis" in capsys.readouterr().err


# =============================================================================
# 0329896b - Vollzaehligkeit der Offline-Pakete
# =============================================================================

def _prep():
    spec = importlib.util.spec_from_file_location(
        "prepare_deployment_tool", _WURZEL / "prepare_deployment.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_lb10_fehlende_raeder_werden_gefunden(tmp_path):
    """
    LB10: Die Vollzaehligkeitspruefung findet ein fehlendes Paket.

    DIE NAMENSANGLEICHUNG IST DER HEIKLE TEIL: Der Dateiname eines Rades
    traegt den Verteilungsnamen mit '_' statt '-' ('python_docx-1.2.0-...').
    Ohne die Angleichung faende die Pruefung genau die Pakete nicht, deren
    Name einen Bindestrich hat - und meldete sie faelschlich als fehlend.
    """
    pd = _prep()
    w = tmp_path / "wheels"
    w.mkdir()
    (w / "pyyaml-6.0.3-cp314-cp314-win_amd64.whl").write_bytes(b"x")
    (w / "python_docx-1.2.0-py3-none-any.whl").write_bytes(b"x")

    fehlt = pd._fehlende_raeder(w, ["pyyaml", "python-docx", "reportlab"])
    assert fehlt == ["reportlab"], (
        "Erwartet war genau 'reportlab'. 'python-docx' liegt als "
        "'python_docx-...' vor und darf NICHT als fehlend gelten.")


def test_lb11_leeres_verzeichnis_meldet_alles_als_fehlend(tmp_path):
    """
    LB11: Ein leeres oder nicht vorhandenes Verzeichnis meldet ALLE Pakete
    als fehlend - nicht etwa nichts. Das ist derselbe Leerbefund wie bei
    d30b3d95, nur an anderer Stelle.
    """
    pd = _prep()
    assert pd._fehlende_raeder(tmp_path / "gibtsnicht", ["a", "b"]) == ["a", "b"]
    leer = tmp_path / "leer"
    leer.mkdir()
    assert pd._fehlende_raeder(leer, ["a", "b"]) == ["a", "b"]


def test_lb12_aehnliche_namen_werden_nicht_verwechselt(tmp_path):
    """
    LB12, DIE GEGENPROBE GEGEN DEN FALSCHEN TREFFER: 'pytest_asyncio-...'
    darf NICHT als Rad fuer 'pytest' durchgehen. Sonst meldete die Pruefung
    Vollzaehligkeit, wo ein Paket fehlt - und waere schlimmer als keine.
    """
    pd = _prep()
    w = tmp_path / "wheels"
    w.mkdir()
    (w / "pytest_asyncio-1.3.0-py3-none-any.whl").write_bytes(b"x")
    assert pd._fehlende_raeder(w, ["pytest"]) == ["pytest"]
    assert pd._fehlende_raeder(w, ["pytest-asyncio"]) == []


def test_lb13_zielversion_steht_in_der_konstanten():
    """
    LB13: Die geforderte Python-Nebenversion steht als KONSTANTE da und wird
    im pip-Aufruf daraus genommen.

    Bis Build 646 stand '314' nur als Zeichenkette im Aufruf und NIRGENDS in
    der Ausgabe. Wer auf der Zielanlage eine andere Nebenversion einsetzt,
    findet die Raeder nicht - auch dann nicht, wenn die Datei im Verzeichnis
    liegt - und sucht den Fehler beim Paket statt bei der Version.
    """
    pd = _prep()
    assert pd.ZIEL_PYTHON_VERSION == "314"
    assert pd.ZIEL_PYTHON_KLARTEXT == "3.14"
    quelle = (_WURZEL / "prepare_deployment.py").read_text(encoding="utf-8")
    assert '"--python-version", ZIEL_PYTHON_VERSION' in quelle, (
        "Die Version muss AUS DER KONSTANTEN kommen - sonst laufen Aufruf "
        "und Auskunft auseinander, sobald jemand eine davon aendert.")
    assert "ZIEL_PYTHON_KLARTEXT" in quelle


# =============================================================================
# e9522fe2 - der Befund im Rueckgabewert (Behebung aus Build 626/627)
# =============================================================================

def test_lb20_backup_list_meldet_defekte_ueber_den_rueckgabewert():
    """
    LB20: 'backup_admin list' liefert einen Wert ungleich 0, wenn mindestens
    eine registrierte Sicherung als nicht integer gefuehrt ist.

    DIE BEHEBUNG STAMMT AUS BUILD 626 - maschinell nachgehalten wird sie
    erst hier. Ein behobener Vorgang ohne Pruefung ist ein Vorgang, der
    wiederkommen darf.

    Geprueft wird am QUELLTEXT und nicht durch einen Lauf: 'list' braucht
    eine eingerichtete coordinator.db mit der backups-Registratur; ein
    Wegwerf-Bestand dafuer waere teurer als die Aussage wert ist. Was hier
    zaehlt, ist, dass der Zaehlzweig existiert und den Rueckgabewert setzt.
    """
    quelle = (_WURZEL / "management" / "backup" / "backup_admin.py").read_text(
        encoding="utf-8")
    assert "defekt = 0" in quelle
    assert 'if not r["integrity_ok"]:' in quelle
    assert "if defekt:" in quelle
    # Und der Leerbefund bleibt eine 0 - "keine Sicherungen registriert" ist
    # kein Defekt, sondern eine andere Auskunft.
    assert "Keine registrierten Backups." in quelle


def test_lb21_backup_list_liest_nur():
    """
    LB21: 'list' ist im Katalog als lesend gefuehrt und oeffnet die
    coordinator.db seit Build 627 auch technisch nur lesend.

    Das ist der zweite, kleinere Punkt aus e9522fe2. PY01 (test_py4_lesend)
    deckt ihn fuer 'lesende' Werkzeuge ab - backup_admin ist aber 'gemischt'
    und faellt dort heraus (das ist der offene Vorgang 88dc129b). Deshalb
    hier eigens.
    """
    quelle = (_WURZEL / "management" / "backup" / "backup_admin.py").read_text(
        encoding="utf-8")
    assert "def _open_con_ro(" in quelle
    assert "mode=ro" in quelle
    # In cmd_list wird die nur-lesende Verbindung benutzt.
    ab = quelle.index("def cmd_list(")
    bis = quelle.index("def ", ab + 10)
    assert "_open_con_ro(" in quelle[ab:bis], (
        "cmd_list muss die nur-lesende Verbindung benutzen.")


def test_lb22_alle_drei_vorgaenge_haben_dieselbe_lehre():
    """
    LB22 IST KEINE PRUEFUNG DES CODES, SONDERN DER LEHRE - und steht hier,
    weil eine Lehre, die nur in einem Vermerk steht, beim naechsten Umbau
    niemandem begegnet.

    Alle drei Vorgaenge dieser Suite haben dieselbe Form: Ein Werkzeug findet
    nichts vor und meldet Erfolg. Wer kuenftig ein Werkzeug baut, das einen
    Bestand prueft, beantworte vorher DREI Fragen statt zwei:
      1. Ist alles in Ordnung?
      2. Gibt es eine Abweichung?
      3. War ueberhaupt etwas da, woran man messen konnte?
    Die dritte Frage ist die, die in allen drei Faellen gefehlt hat.
    """
    lehre = (_WURZEL / "documents" / "rules-leerbefund.md")
    assert lehre.is_file(), (
        "Die Lehre gehoert in den Bestand, nicht nur in den Vorgang: "
        "documents/rules-leerbefund.md fehlt.")
    text = lehre.read_text(encoding="utf-8")
    for kennung in ("d30b3d95", "0329896b", "e9522fe2"):
        assert kennung in text, (
            "Die Regel nennt die Vorgaenge, aus denen sie stammt - sonst "
            "ist sie in zwei Jahren eine Behauptung. Fehlt: %s" % kennung)
