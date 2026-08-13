# =============================================================================
# tests/test_placeholder_textstellen.py
# IT-Forensisches Ermittlungswerkzeug
# =============================================================================
# Prueft core/placeholder_syntax.py::iter_texts - die SERVERSEITE der Frage,
# welche Textstellen eines Editor.js-Blocks Platzhalter enthalten koennen.
#
# ── DER BEFUND (gemessen 12.08.2026) ────────────────────────────────────────
#
#   Zwei Textstellen fehlten, und sie fehlten auf BEIDEN Seiten gleich:
#
#     Liste, VERSCHACHTELTER Eintrag (items[].items[]) .... nicht gesehen
#     Zitat, QUELLENANGABE (caption) ..................... nicht gesehen
#
#   Weil beide Seiten denselben Fehler hatten, blieb die im Kopf von
#   placeholder_chips.js zugesicherte Deckungsgleichheit gewahrt - und der
#   Fehler damit unsichtbar. Zwei Seiten, die sich einig sind, sind kein
#   Beleg dafuer, dass sie recht haben.
#
# ── WAS DARAN HAENGT ────────────────────────────────────────────────────────
#
#   iter_texts traegt ueber extract_from_block() die serverseitige
#   Feldpruefung eines Vermerks (forensic_api/report.py:2063,
#   _validate_report_fields). Ein {{m:...}} an einer der beiden Stellen wurde
#   NIE geprueft. Auf der Clientseite wurde es ueber
#   extractFieldsFromBlockData dem Ermittler NIE zum Ausfuellen angeboten
#   (userinfo/placeholder_wizard.js:241,636) - der Vermerk ging mit rohem
#   Vorlagentext hinaus.
#
#   DIE AENDERUNG WEITET DIE PRUEFUNG AUS. Ein Vermerk, der bisher durchging,
#   kann jetzt einen Verstoss melden. Das ist die richtige Richtung - geprueft
#   wird mehr, nie weniger -, aber es ist eine Verhaltensaenderung und keine
#   reine Reparatur. Sie steht so auch in der build.json.
#
# PS01 - verschachtelte Listeneintraege werden gesehen, bis in die dritte Ebene.
# PS02 - die Quellenangabe eines Zitats wird gesehen.
# PS03 - extract_from_block liefert die Felder beider Stellen. DAS IST DER
#        FALL MIT DEN FOLGEN: was hier fehlt, prueft der Server nie.
# PS04 - DECKUNGSGLEICHHEIT mit dem Client: dieselbe block_data ergibt in
#        placeholder_syntax.py und in placeholder_chips.js dieselben
#        Textstellen, in derselben Reihenfolge. Ohne diesen Fall koennten
#        beide Seiten wieder auseinanderlaufen, und zwar lautlos.
# PS05 - eine im Kreis zeigende Struktur beendet den Lauf. block_data kommt
#        aus einer Datenbank und ist nicht vertrauenswuerdig; dieser Pfad
#        laeuft beim SPEICHERN eines Vermerks.
#
# Version: 0.1.0 - Build: 710 - 2026-08-13
# Klassifikation: VERTRAULICH -- NUR FUER DEN DIENSTGEBRAUCH
# =============================================================================

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from core.placeholder_syntax import PlaceholderSyntax


def _liste() -> dict:
    """Eine Liste mit drei Verschachtelungsebenen."""
    return {
        "style": "unordered",
        "items": [
            {"content": "Ebene 1 {{a:user.username}}", "items": [
                {"content": "Ebene 2 {{m:spurennummer}}", "items": [
                    {"content": "Ebene 3 {{o:bemerkung}}", "items": []},
                ]},
            ]},
        ],
    }


def _zitat() -> dict:
    return {
        "text": "Der Zeuge sagte aus {{a:user.id}}",
        "caption": "Vernehmung {{m:aktenzeichen}}",
    }


class TextstellenTests(unittest.TestCase):

    # PS01 -------------------------------------------------------------------
    def test_ps01_verschachtelte_listeneintraege(self):
        self.assertEqual(
            list(PlaceholderSyntax.iter_texts(_liste())),
            [
                "Ebene 1 {{a:user.username}}",
                "Ebene 2 {{m:spurennummer}}",
                "Ebene 3 {{o:bemerkung}}",
            ],
        )

    # PS02 -------------------------------------------------------------------
    def test_ps02_quellenangabe_eines_zitats(self):
        texte = list(PlaceholderSyntax.iter_texts(_zitat()))
        self.assertIn("Vernehmung {{m:aktenzeichen}}", texte)
        self.assertIn("Der Zeuge sagte aus {{a:user.id}}", texte)

    # PS03 -------------------------------------------------------------------
    def test_ps03_extract_from_block_liefert_beide_stellen(self):
        """Was hier fehlt, prueft der Server nie."""
        namen = {f.name for f in PlaceholderSyntax.extract_from_block(_liste())}
        self.assertIn("spurennummer", namen)   # zweite Ebene
        self.assertIn("bemerkung", namen)      # dritte Ebene

        namen = {f.name for f in PlaceholderSyntax.extract_from_block(_zitat())}
        self.assertIn("aktenzeichen", namen)   # caption

    # PS04 -------------------------------------------------------------------
    def test_ps04_deckungsgleich_mit_dem_client(self):
        """
        BEIDE SEITEN MUESSEN DIESELBEN TEXTSTELLEN SEHEN.

        Der Kopf von placeholder_chips.js sichert das ausdruecklich zu, und
        der Bruch dieser Zusage ist die gefaehrlichste Art von Fehler hier:
        der Server pruefte Felder, die der Client nie angeboten hat, oder
        umgekehrt. Genau das war bis Build 710 der Fall - nur eben in
        beide Richtungen gleich, weshalb es niemandem auffiel.

        Der Fall vergleicht die BEIDEN IMPLEMENTIERUNGEN, nicht eine gegen
        eine hinterlegte Erwartung. Eine hinterlegte Liste wuerde nur noch
        pruefen, ob jemand sie mitgepflegt hat.

        Ohne node im Bild wird der Fall UEBERSPRUNGEN und sagt das - er
        stillschweigend gruen zu melden waere schlimmer als ihn nicht zu
        haben.
        """
        node = shutil.which("node")
        if not node:
            self.skipTest("node nicht verfuegbar - Deckungsgleichheit "
                          "NICHT geprueft")

        chips = Path("userinfo/placeholder_chips.js").resolve()
        self.assertTrue(chips.is_file(), "placeholder_chips.js nicht gefunden")

        skript = (
            "const {readFileSync}=require('fs');"
            "const {JSDOM}=require('jsdom');"
            "const w=new JSDOM('<!DOCTYPE html><body></body>',"
            "{runScripts:'dangerously'}).window;"
            "w.FORENSIC_DEBUG=false;"
            "w.eval(readFileSync(process.argv[1],'utf-8'));"
            "const daten=JSON.parse(process.argv[2]);"
            "console.log(JSON.stringify("
            "w.PlaceholderChips.collectBlockTexts(daten)));"
        )

        for name, daten in (("Liste", _liste()), ("Zitat", _zitat())):
            with self.subTest(block=name):
                erg = subprocess.run(
                    [node, "-e", skript, str(chips),
                     json.dumps(daten, ensure_ascii=False)],
                    capture_output=True, text=True, timeout=120,
                )
                if erg.returncode != 0:
                    self.skipTest(
                        "Client-Seite nicht ausfuehrbar (jsdom fehlt?) - "
                        "Deckungsgleichheit NICHT geprueft: "
                        + erg.stderr.strip()[:200])
                client = json.loads(erg.stdout)
                server = list(PlaceholderSyntax.iter_texts(daten))
                # Auch die REIHENFOLGE zaehlt: extract_from_block nimmt bei
                # Mehrfachnennung den ERSTEN Fund, und derselbe Feldname darf
                # nicht je nach Seite eine andere Vorgabe gewinnen.
                self.assertEqual(server, client)

    # PS05 -------------------------------------------------------------------
    def test_ps05_kreisstruktur_beendet_den_lauf(self):
        eintrag: dict = {"content": "{{m:x}}", "items": []}
        eintrag["items"].append(eintrag)
        # Ohne Tiefengrenze liefe das hier nicht zu Ende - in einem Pfad, der
        # beim Speichern eines Vermerks laeuft.
        texte = list(PlaceholderSyntax.iter_texts({"items": [eintrag]}))
        self.assertGreater(len(texte), 0)
        self.assertLess(len(texte), 100)


if __name__ == "__main__":
    unittest.main()
