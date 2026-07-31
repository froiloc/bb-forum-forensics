/**
 * tests/unit/_hilfe_schluessel.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle H: Hilfesysteme (H12)
 *
 * DIE KONTEXTSCHLUESSEL DES HILFEREGISTERS, GELESEN AUS DEM REGISTER SELBST.
 *
 * WARUM ES DIESE DATEI GIBT (Befund Build 602, nicht geplant):
 *   Die vitest-Seite braucht die Liste der vorhandenen Hilfetexte, um zu
 *   pruefen, ob jeder im Browser entstehende Anker auch einen Text hat. Bisher
 *   las sie diese Liste mit einem regulaeren Ausdruck aus den Python-Dateien —
 *   sie fand also nur Schluessel, die dort WOERTLICH stehen.
 *
 *   Beim Verfassen der Support-Historie kam heraus, warum das zu wenig ist:
 *   diese Sicht fuehrt drei Tabellen mit drei Kennungen, ihre Spaltentexte
 *   entstehen deshalb in einer Schleife ("%s.spalte.%s" % (praefix, feld)).
 *   Ein regulaerer Ausdruck sieht davon nichts. Die Pruefung haette also
 *   Schluessel fuer FEHLEND gehalten, die es gibt — und umgekehrt waere ein
 *   Text, den niemand je zu sehen bekommt, unbemerkt geblieben.
 *
 *   Deshalb wird jetzt das Register selbst gefragt: ein kurzer Python-Aufruf,
 *   der genau die Funktion benutzt, die auch der Webserver benutzt. Damit gibt
 *   es EINE Quelle statt einer Quelle und einer Vermutung ueber sie.
 *
 * WELCHER PYTHON-AUFRUF:
 *   1. AIW_PYTHON — von run_tests.py gesetzt (sys.executable). Das ist der
 *      Normalfall und trifft immer denselben Interpreter wie die pytest-Seite.
 *   2. sonst 'python3', dann 'python' — fuer den direkten Aufruf von
 *      'npx vitest' ohne den gemeinsamen Testrunner.
 *   Findet sich keiner, SCHEITERT die Pruefung mit einer benannten Ursache.
 *   Sie zu ueberspringen waere das stille Uebergehen aus Grundregel 1: eine
 *   gruene Suite, die nichts gemessen hat.
 *
 * Version: v0.8.603 · Build: 603 · 2026-07-31
 */

import { execFileSync } from "child_process";

/** Das Programm, das Schluessel und verfasste Praefixe ausgibt — bewusst ohne
 *  Zwischendatei (der Bauplan verbietet generierte Zwischenbestaende). */
const PROG = [
  "import json,sys",
  "sys.path.insert(0,'.')",
  "from management.help.inhalt import lade_register",
  "r = lade_register()",
  "praefixe = sorted({p for s in r.sichten for p in s.praefixe()})",
  "print(json.dumps({",
  "    'schluessel': sorted(set(r.kontext_schluessel())),",
  "    'praefixe': praefixe}))",
].join("\n");

let _zwischenspeicher = null;

/** Register einmal je Testlauf holen — sonst kostet jeder Test einen
 *  Prozessstart. */
function _lies() {
  if (_zwischenspeicher) { return _zwischenspeicher; }

  const kandidaten = [];
  if (process.env.AIW_PYTHON) { kandidaten.push(process.env.AIW_PYTHON); }
  kandidaten.push("python3", "python");

  const fehler = [];
  for (const exe of kandidaten) {
    try {
      const roh = execFileSync(exe, ["-c", PROG], {
        encoding: "utf-8", cwd: process.cwd(),
      });
      const gelesen = JSON.parse(roh);
      _zwischenspeicher = {
        schluessel: new Set(gelesen.schluessel),
        praefixe: new Set(gelesen.praefixe),
      };
      return _zwischenspeicher;
    } catch (e) {
      fehler.push(exe + ": " + (e && e.message ? e.message.split("\n")[0] : e));
    }
  }
  throw new Error(
    "Das Hilferegister liess sich nicht lesen — kein Python gefunden oder "
    + "der Aufruf schlug fehl. Versuche:\n  " + fehler.join("\n  ")
    + "\nAbhilfe: die Tests ueber 'python run_tests.py' starten (setzt "
    + "AIW_PYTHON) oder python3/python in den Pfad legen.");
}

/** Alle Kontextschluessel des Registers als Set. */
export function registerSchluessel() {
  return _lies().schluessel;
}

/**
 * Die Ankerpraefixe der Sichten, deren Kapitel VERFASST ist.
 *
 * Wozu: eine Marke ohne Text ist waehrend der Inhaltswellen richtig — sie
 * zeigt "Hilfe folgt". Fuer eine FERTIGE Sicht ist sie dagegen ein Fehler.
 * Dieselbe Unterscheidung trifft SP01 auf der Python-Seite; sie hier noch
 * einmal von Hand zu pflegen hiesse, zwei Listen synchron halten zu muessen.
 */
export function verfasstePraefixe() {
  return _lies().praefixe;
}
