# =============================================================================
# tests/test_regelwerk_register.py
# IT-Forensisches Ermittlungswerkzeug - Das Regelwerk fuehrt sich selbst
# =============================================================================
# Testsuite fuer Build 649, Vorgaenge c3f80e54 und 2f8a61d0.
#
# DER ANLASS: documents/rules-index.md verlangt seit Build 607 eine
#   Pflegepflicht - "Wer eine neue Regel einfuehrt, legt sie hier ab und nennt
#   ihre Durchsetzung. Eine Regel, die nur in einem Dateikopf steht, gilt
#   zwar, ist aber fuer die naechste Person unauffindbar." Diese Pflicht war
#   bis Build 648 UNGEPRUEFT, und sie wurde prompt verletzt:
#   documents/rules-leerbefund.md ist in Build 647 entstanden und stand zwei
#   Builds lang nicht in der Uebersicht. Aufgefallen ist es beim Anlegen des
#   naechsten Blattes - also durch Zufall, nicht durch eine Pruefung.
#
# EINE REGEL OHNE DURCHSETZUNG IST EINE BITTE. Der Satz steht im Kopf von
#   rules-index.md selbst. Diese Suite ist seine Durchsetzung, und sie ist
#   bewusst klein: Sie prueft die AUFFINDBARKEIT, nicht den Inhalt. Ob eine
#   Regel gut ist, entscheidet kein Test.
#
# RW01 - jedes Blatt 'documents/rules-*.md' steht in der Uebersicht
# RW02 - die Uebersicht nennt kein Blatt, das es nicht gibt (TE6)
# RW03 - jedes Blatt traegt einen Stand (Buildnummer und Datum)
# RW04 - die beiden Lehrblaetter nennen die Vorgaenge, aus denen sie stammen
# RW05 - GEGENPROBE: die Suche nach Blaettern findet ueberhaupt welche (TE5)
#
# WAS DIESE SUITE NICHT KANN (TE4):
#   * Sie prueft nicht, ob eine Regel EINGEHALTEN wird - dafuer sind die
#     Suiten der jeweiligen Regel zustaendig (PY01-PY10c, LB01-LB22, ...).
#   * Sie prueft nicht, ob eine Regel, die irgendwo im Bestand gilt, hier
#     ueberhaupt aufgeschrieben wurde. Eine Regel, die nur in einem
#     Dateikopf steht, faellt hier NICHT auf - genau das ist der Fall, den
#     die Pflegepflicht meint, und er ist maschinell nicht zu fassen.
#   * Sie liest die Tabelle der Uebersicht als Text. Wer ein Blatt im
#     Fliesstext erwaehnt, statt es in die Tabelle aufzunehmen, kommt hier
#     durch. Das ist bewusst so: die Alternative waere ein Markdown-Parser
#     fuer eine Frage, die er nicht besser beantwortet.
#
# Version: v0.8.649 - Build: 649 - 2026-08-01
# =============================================================================

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WURZEL = Path(__file__).resolve().parent.parent
DOKUMENTE = WURZEL / "documents"
UEBERSICHT = DOKUMENTE / "rules-index.md"

#: Die Uebersicht selbst steht nicht in ihrer eigenen Tabelle - sie ist die
#: Tabelle. Das ist keine Auslassung, sondern die Sache selbst.
NICHT_IN_DER_TABELLE = {"rules-index.md"}


def _blaetter():
    """Alle Regelblaetter im Verzeichnis, ohne die Uebersicht selbst."""
    return sorted(p.name for p in DOKUMENTE.glob("rules-*.md")
                  if p.name not in NICHT_IN_DER_TABELLE)


def _uebersicht():
    return UEBERSICHT.read_text(encoding="utf-8")


# --- RW05: erst die Gegenprobe, dann die Forderung ---------------------------
def test_rw05_es_gibt_ueberhaupt_regelblaetter():
    """
    TE5. Faende die Suche keine Blaetter, waeren RW01 und RW03 leere
    Schleifen und stuenden trotzdem gruen im Lauf - der schlechteste aller
    Zustaende, weil er wie eine Zusicherung aussieht.
    """
    blaetter = _blaetter()
    assert len(blaetter) >= 6, (
        "Es wurden nur %d Regelblaetter gefunden (%s). Bei Build 649 sind es "
        "sieben; weniger heisst, dass die Suche oder das Verzeichnis kaputt "
        "ist." % (len(blaetter), ", ".join(blaetter)))
    assert UEBERSICHT.is_file(), "documents/rules-index.md fehlt."


# --- RW01 --------------------------------------------------------------------
def test_rw01_jedes_blatt_steht_in_der_uebersicht():
    """
    RW01: Die Pflegepflicht aus rules-index.md, maschinell gehalten.

    DER FALL, DER DIESE PRUEFUNG AUSGELOEST HAT: rules-leerbefund.md,
    entstanden in Build 647, fehlte bis Build 649 in der Uebersicht. Es
    galt trotzdem - aber wer die Uebersicht las, um zu erfahren, welche
    Regeln es gibt, erfuhr es nicht. Genau davor warnt die Uebersicht in
    ihrem eigenen Kopf.
    """
    text = _uebersicht()
    fehlend = [b for b in _blaetter() if b not in text]
    assert not fehlend, (
        "Diese Regelblaetter stehen nicht in documents/rules-index.md: %s. "
        "Wer eine Regel einfuehrt, traegt sie IM SELBEN BUILD in die "
        "Uebersicht ein - sonst gilt sie zwar, ist aber unauffindbar."
        % ", ".join(fehlend))


# --- RW02 --------------------------------------------------------------------
def test_rw02_die_uebersicht_nennt_kein_blatt_das_es_nicht_gibt():
    """
    RW02 (TE6): Die Gegenrichtung. Ein Verweis auf ein Blatt, das umbenannt
    oder geloescht wurde, ist schlimmer als kein Verweis: Er sieht aus wie
    eine Auskunft und schickt den Leser ins Leere.
    """
    genannt = set(re.findall(r"`(rules-[a-z0-9_-]+\.md)`", _uebersicht()))
    vorhanden = set(p.name for p in DOKUMENTE.glob("rules-*.md"))
    tot = sorted(genannt - vorhanden)
    assert not tot, (
        "Die Uebersicht verweist auf Blaetter, die es nicht gibt: %s"
        % ", ".join(tot))


# --- RW03 --------------------------------------------------------------------
def test_rw03_jedes_blatt_traegt_einen_stand():
    """
    RW03: Ein Regelblatt ohne Stand laesst offen, ob es noch gilt. Verlangt
    wird eine Zeile mit '**Stand:**', einer Buildnummer und einem Datum -
    dieselbe Form, die alle bestehenden Blaetter schon haben.
    """
    muster = re.compile(r"\*\*Stand:\*\*.*?Build\s+(\d+).*?(\d{4}-\d{2}-\d{2})",
                        re.DOTALL)
    maengel = []
    for name in _blaetter() + sorted(NICHT_IN_DER_TABELLE):
        p = DOKUMENTE / name
        if not p.is_file():
            continue
        kopf = p.read_text(encoding="utf-8")[:1200]
        if not muster.search(kopf):
            maengel.append(name)
    assert not maengel, (
        "Diese Regelblaetter tragen im Kopf keinen Stand (Buildnummer und "
        "Datum): %s" % ", ".join(maengel))


# --- RW04 --------------------------------------------------------------------
@pytest.mark.parametrize("blatt,vorgaenge", [
    ("rules-leerbefund.md", ("d30b3d95", "0329896b", "e9522fe2")),
    ("rules-nachstellung.md", ("c3f80e54", "2f8a61d0")),
])
def test_rw04_ein_lehrblatt_nennt_seine_vorgaenge(blatt, vorgaenge):
    """
    RW04: Eine Lehre ohne Fundstelle ist in zwei Jahren eine Behauptung
    (GR1: kein Beleg darf ausgelassen werden). Die Blaetter, die aus
    einzelnen Vorgaengen abgeleitet sind, nennen diese Vorgaenge
    namentlich.

    NICHT FUER ALLE BLAETTER: rules-coding.md oder rules-ux.md sind
    Sammlungen und nicht aus einem Vorgang abgeleitet. Eine Forderung
    'jedes Blatt nennt einen Vorgang' waere dort erfunden.
    """
    p = DOKUMENTE / blatt
    assert p.is_file(), (
        "Die Lehre gehoert in den Bestand, nicht nur in den Vorgang: "
        "documents/%s fehlt." % blatt)
    text = p.read_text(encoding="utf-8")
    fehlend = [v for v in vorgaenge if v not in text]
    assert not fehlend, (
        "%s nennt die Vorgaenge nicht, aus denen es stammt. Fehlt: %s"
        % (blatt, ", ".join(fehlend)))
