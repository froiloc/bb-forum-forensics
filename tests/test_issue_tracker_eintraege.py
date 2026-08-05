# =============================================================================
# tests/test_issue_tracker_eintraege.py
# IT-Forensisches Ermittlungswerkzeug -- Issue-Tracker
# =============================================================================
# Prueft die Eintragsdateien issue-tracker/eintraege_claude_Build*.json,
# BEVOR sie eingemischt werden (Build 668).
#
# WARUM AUF DER ERSTELLERSEITE: das Einmischen laeuft mit
# '--auto-resolve source', ersetzt einen vorhandenen Vorgang also vollstaendig
# durch den gelieferten. Das ist gewollt - der gelieferte Stand ist der neuere.
# Es hat aber eine Kehrseite: bringt die gelieferte Fassung die bereits
# vorhandenen Update-Eintraege NICHT mit, verschwinden sie beim Einmischen.
# Und zwar lautlos: merge.py meldet einen erfolgreichen Merge, und niemand
# sieht, dass eine Zeile Historie fehlt.
#
# Genau das war am 04.08.2026 der Fall: fuer 65a230fd und d3f933cd haette der
# Eintrag "Issue erstellt" (Alex, 2026-08-03) den Vorgang nicht ueberlebt.
# Aufgefallen ist es nur, weil vor dem Einmischen nachgelesen wurde, was die
# beiden Strategien wirklich tun.
#
# Der Tracker ist Teil der Projektdokumentation. Verlorene Historie ist dort
# dasselbe wie eine stille Auslassung im Befund (Grundregel 1).
#
# IT01 - jede Eintragsdatei ist gueltiges JSON mit der erwarteten Struktur.
# IT02 - jeder Vorgang traegt die Pflichtfelder des Schemas.
# IT02b - und HAELT DEREN GRENZEN EIN (Laenge, Aufzaehlung, Muster, Minimum).
#         BUILD 669, aus eigenem Schaden: IT02 prueft nur, OB ein Feld da ist.
#         Der Titel des Vorgangs f39ad572 war 85 Zeichen lang, das Schema
#         erlaubt 80 - IT02 war gruen, und merge.py wies die Datei auf der
#         Einspielseite ab. Ein Waechter, der nur die Anwesenheit prueft,
#         gibt eine Sicherheit vor, die er nicht hat.
# IT03 - WAECHTER: liegt ein Vorgang bereits in data/issues.json, enthaelt die
#        gelieferte Fassung ALLE dort vorhandenen Update-Zeitstempel.
# IT04 - keine doppelten Kennungen innerhalb einer Datei.
# IT05 - Zeitstempel der Updates sind aufsteigend sortiert.
#
# Version: v0.8.668 - Build: 668 - 2026-08-05
# =============================================================================

import json
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
TRACKER = WURZEL / "issue-tracker"
BESTAND = TRACKER / "data" / "issues.json"


def _eintragsdateien():
    return sorted(TRACKER.glob("eintraege_claude_Build*.json"))


def _lade(pfad):
    with open(pfad, encoding="utf-8") as f:
        return json.load(f)


class EintraegeTests(unittest.TestCase):

    # IT01 -------------------------------------------------------------------
    def test_it01_dateien_sind_gueltiges_json(self):
        for pfad in _eintragsdateien():
            with self.subTest(datei=pfad.name):
                d = _lade(pfad)
                self.assertIn("issues", d)
                self.assertIsInstance(d["issues"], list)
                self.assertGreater(len(d["issues"]), 0,
                                   "Eine leere Eintragsdatei waere ein "
                                   "Versehen, kein Inhalt.")

    # IT02 -------------------------------------------------------------------
    def test_it02_pflichtfelder_des_schemas(self):
        schema = _lade(TRACKER / "issue-tracker.schema.json")
        pflicht = schema["properties"]["issues"]["items"]["required"]
        for pfad in _eintragsdateien():
            for e in _lade(pfad)["issues"]:
                with self.subTest(datei=pfad.name, id=e.get("id", "?")):
                    fehlend = [k for k in pflicht if k not in e]
                    self.assertEqual([], fehlend,
                                     "Fehlende Pflichtfelder: %s" % fehlend)

    # IT02b ------------------------------------------------------------------
    def test_it02b_grenzen_des_schemas_werden_eingehalten(self):
        """
        Prueft die EINSCHRAENKUNGEN des Schemas, nicht nur die Anwesenheit
        der Felder: maxLength, minLength, enum, pattern, minimum, maximum.

        Bewusst von Hand statt ueber eine Bibliothek: 'jsonschema' ist keine
        Abhaengigkeit dieses Projekts, und die Produktionsumgebung ist
        offline. Ein Waechter, der nur dort laeuft, wo man Pakete
        nachinstallieren kann, hilft genau dann nicht, wenn man ihn braucht.
        """
        import re
        schema = _lade(TRACKER / "issue-tracker.schema.json")
        felder = schema["properties"]["issues"]["items"]["properties"]
        verstoesse = []
        for pfad in _eintragsdateien():
            for e in _lade(pfad)["issues"]:
                kennung = "%s (%s)" % (e.get("id", "?")[:8], pfad.name)
                for name, regel in felder.items():
                    if name not in e or e[name] is None:
                        continue
                    wert = e[name]
                    if "maxLength" in regel and isinstance(wert, str) \
                            and len(wert) > regel["maxLength"]:
                        verstoesse.append(
                            "%s: %s ist %d Zeichen lang, erlaubt sind %d"
                            % (kennung, name, len(wert), regel["maxLength"]))
                    if "minLength" in regel and isinstance(wert, str) \
                            and len(wert) < regel["minLength"]:
                        verstoesse.append(
                            "%s: %s ist zu kurz (%d < %d)"
                            % (kennung, name, len(wert), regel["minLength"]))
                    if "enum" in regel and wert not in regel["enum"]:
                        verstoesse.append(
                            "%s: %s='%s' steht nicht in der Aufzaehlung %s"
                            % (kennung, name, wert, regel["enum"]))
                    if "pattern" in regel and isinstance(wert, str) \
                            and not re.match(regel["pattern"], wert):
                        verstoesse.append(
                            "%s: %s='%s' passt nicht auf %s"
                            % (kennung, name, wert, regel["pattern"]))
                    if "minimum" in regel and isinstance(wert, (int, float)) \
                            and wert < regel["minimum"]:
                        verstoesse.append(
                            "%s: %s=%s unterschreitet %s"
                            % (kennung, name, wert, regel["minimum"]))
                    if "maximum" in regel and isinstance(wert, (int, float)) \
                            and wert > regel["maximum"]:
                        verstoesse.append(
                            "%s: %s=%s ueberschreitet %s"
                            % (kennung, name, wert, regel["maximum"]))
        self.assertEqual(
            [], verstoesse,
            "Die Einspielseite wuerde diese Vorgaenge abweisen:\n  "
            + "\n  ".join(verstoesse))

    # IT03 -------------------------------------------------------------------
    def test_it03_keine_historie_geht_beim_einmischen_verloren(self):
        """
        DER EIGENTLICHE WAECHTER.

        '--auto-resolve source' ersetzt den vorhandenen Vorgang vollstaendig.
        Was in der gelieferten Fassung nicht steht, ist danach weg - ohne
        Meldung. Dieser Fall prueft deshalb VOR dem Einmischen, dass jede
        gelieferte Fassung die schon vorhandene Historie mitbringt.
        """
        if not BESTAND.is_file():
            self.skipTest("data/issues.json nicht vorhanden")
        bestand = {i["id"]: i for i in _lade(BESTAND)["issues"]}
        verluste = []
        for pfad in _eintragsdateien():
            for e in _lade(pfad)["issues"]:
                alt = bestand.get(e["id"])
                if not alt:
                    continue                      # neuer Vorgang, nichts zu verlieren
                geliefert = {u.get("timestamp")
                             for u in (e.get("updates") or [])}
                for u in (alt.get("updates") or []):
                    if u.get("timestamp") not in geliefert:
                        verluste.append(
                            "%s (%s): Update %s von %s ginge verloren"
                            % (e["id"][:8], pfad.name, u.get("timestamp"),
                               u.get("author")))
        self.assertEqual(
            [], verluste,
            "Beim Einmischen mit --auto-resolve source wuerde Historie "
            "verschwinden, und zwar lautlos:\n  " + "\n  ".join(verluste))

    # IT04 -------------------------------------------------------------------
    def test_it04_keine_doppelten_kennungen(self):
        for pfad in _eintragsdateien():
            with self.subTest(datei=pfad.name):
                ids = [e["id"] for e in _lade(pfad)["issues"]]
                doppelt = [i for i in set(ids) if ids.count(i) > 1]
                self.assertEqual([], doppelt)

    # IT05 -------------------------------------------------------------------
    def test_it05_updates_sind_chronologisch(self):
        for pfad in _eintragsdateien():
            for e in _lade(pfad)["issues"]:
                stempel = [u.get("timestamp", "")
                           for u in (e.get("updates") or [])]
                with self.subTest(datei=pfad.name, id=e["id"][:8]):
                    # Eine Historie, die nicht in der Reihenfolge steht, in der
                    # sie entstanden ist, laedt zu Fehlschluessen ein.
                    self.assertEqual(sorted(stempel), stempel)


if __name__ == "__main__":
    unittest.main()
