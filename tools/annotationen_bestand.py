#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# tools/annotationen_bestand.py
# IT-Forensisches Ermittlungswerkzeug - Bestandsaufnahme der Annotationen
# =============================================================================
# Zweck:
#   Etappe 0 des Arbeitsblocks "Annotationen verwendbar machen": ZAEHLEN, WAS
#   DA IST - ueber alle evidence_<uid>.db und die Kopfdaten der zugehoerigen
#   forensic_<uid>.db.
#
#   Der Vorgang steht in management/maintenance/annotation_bestand.py
#   (Grundregel 10). Diese Datei ist die Befehlszeile davor.
#
#   ES SCHREIBT NICHTS AN DEN BESTAND. Beide Datenbanken werden ueber
#   'file:...?mode=ro' geoeffnet - schreibgeschuetzt durch die Verbindung und
#   nicht durch Vorsatz. Geschrieben wird nur, was der Aufrufer mit
#   '--protokoll' und '--json' ausdruecklich verlangt.
#
# ── WARUM ES DIESES WERKZEUG GIBT ────────────────────────────────────────────
#
#   Weil in allen Laeufen der Builds 727 bis 754 von "477 Annotationen" die
#   Rede war, ohne dass feststand, ob das die Zahl ALLER Zeilen ist oder die
#   der AKTUELLEN. Geloeschte Zeilen (deleted_at) und ueberholte Generationen
#   (prev_id) waren nie getrennt ausgewiesen.
#
#   Etappe 4 des Arbeitsblocks wird fuer jede Annotation eine NEUE Zeile mit
#   Rueckverweis ueber prev_id schreiben. Wenn vorher nicht feststeht, wie
#   viele Zeilen es gibt und welche davon aktuell sind, stehen danach zwei
#   verschiedene Gesamtzahlen nebeneinander und keiner weiss, welche gilt.
#
# ── DIE ZWEI AUSGABEN ────────────────────────────────────────────────────────
#
#   Klartext  - fuer den Menschen: Zahlen mit Lesehilfe, '--protokoll'
#               schreibt dieselben Zeilen zusaetzlich in eine Datei.
#   JSON      - fuer die Weiterverarbeitung in Etappe 1: '--json <Datei>'.
#
#   BEIDE TRAGEN DIESELBEN WERTE. Die JSON-Fassung wird nicht aus dem Text
#   nachgebaut und der Text nicht aus dem JSON - beide entstehen aus demselben
#   Bestandsbefund. Zwei Darstellungen, von denen eine aus der anderen
#   abgeleitet wird, weichen frueher oder spaeter ab.
#
# ── PFADE ────────────────────────────────────────────────────────────────────
#
#   Vorrang wie projektweit: Argument > config.yaml > fester Vorgabewert.
#   Aufgeloest ueber core/werkzeug_konfig.py (Build 645), Schluessel
#   'paths.evidence_db_dir' und 'paths.forensic_db_dir'.
#
#   DER VORGABEWERT STEHT NICHT HIER. Er kommt aus
#   core.config_loader.coded_default() - der Datei, die als alleinige Heimat
#   der Vorgabewerte festgelegt ist (Build 720, Ticket 5a7e93b1). Ein
#   Literal an dieser Stelle waere ein ZWEITER Vorgabeort fuer dieselbe
#   Datenbank: harmlos, solange beide uebereinstimmen, und still falsch,
#   sobald einer geaendert wird. Der Waechter PH04 in
#   tests/test_konfig_pfadhoheit.py haelt das fest.
#
# Rueckgabewerte - siehe Katalogeintrag 'annotationen_bestand'.
# Version: 0.8.755 - Build 755
# =============================================================================

from __future__ import annotations

import argparse
import json
import os
import re
import sys

_WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WURZEL not in sys.path:
    sys.path.insert(0, _WURZEL)

from core import werkzeug_konfig                            # noqa: E402
from core.config_loader import coded_default               # noqa: E402
from management.help import cli_epilog                      # noqa: E402
from management.maintenance.annotation_bestand import (     # noqa: E402
    AUSGENOMMENE_KENNUNGEN, BestandsAufnahme, Bestandsbefund,
    PRODUKTIVBETRIEB_AB, TESTBESTAENDE, zeit)

RUECK_OHNE_BEFUND = 0
RUECK_BEFUND = 1
RUECK_ABBRUCH = 2

#: Dateiname einer Beweismitteldatenbank.
_RE_EVIDENCE = re.compile(r"^evidence_(\d+)\.db$")


def _pad(s, n) -> str:
    s = str(s)
    return s + " " * max(0, n - len(s))


def _bestaende_finden(evidence_dir: str) -> list:
    """
    Alle evidence_<uid>.db im Verzeichnis, nach uid sortiert.

    Es wird NICHT auf das Vorhandensein der forensic_<uid>.db geprueft. Ein
    Bestand ohne Seitenkopfdaten ist ein BEFUND und kein Grund, ihn
    wegzulassen (Grundregel 1).
    """
    if not os.path.isdir(evidence_dir):
        return []
    gefunden = []
    for name in sorted(os.listdir(evidence_dir)):
        m = _RE_EVIDENCE.match(name)
        if m:
            gefunden.append((m.group(1), os.path.join(evidence_dir, name)))
    return sorted(gefunden, key=lambda p: int(p[0]))


def _tabelle(sag, ueberschrift: str, paare, breite: int = 42) -> None:
    """Eine Zaehlung als zweispaltige Tabelle. Leere Ueberschrift = keine."""
    if ueberschrift:
        sag("  %s" % ueberschrift)
    for name, wert in paare:
        sag("    %s %s" % (_pad(name, breite), wert))


def _bestand_ausgeben(b: Bestandsbefund, sag) -> None:
    """Einen Bestandsbefund im Klartext ausgeben."""
    sag("=" * 78)
    kennung = "BESTAND %s" % b.uid
    if b.testbestand:
        kennung += "   [TESTBESTAND - Annotationen sind im Einzelfall zu " \
                   "bewerten]"
    sag(kennung)
    sag("  Beweismittel : %s%s"
        % (b.evidence_pfad, "" if b.evidence_lesbar else "  (NICHT LESBAR)"))
    if b.forensic_lesbar:
        zusatz = ""
    else:
        zusatz = "  (%s)" % (b.m7_seiten.get("hinweis")
                             or "nicht ausgewertet")
    sag("  Seitendaten  : %s%s" % (b.forensic_pfad or "(keiner)", zusatz))
    sag("=" * 78)
    for f in b.fehler:
        sag("  FEHLER: %s" % f)
    if not b.evidence_lesbar:
        return

    m1 = b.m1_zeilenbestand
    sag("")
    sag("M1 ZEILENBESTAND")
    _tabelle(sag, "", (
        ("Zeilen in 'annotations' insgesamt", m1["zeilen_gesamt"]),
        ("davon geloescht (deleted_at gesetzt)", m1["geloescht"]),
        ("davon ueberholt (ein prev_id zeigt darauf)", m1["ueberholt"]),
        ("mit prev_id (haben einen Vorgaenger)", m1["mit_prev_id"]),
        ("AKTUELL (nicht geloescht, nicht ueberholt)", m1["aktuell"]),
    ))
    _tabelle(sag, "Generationen (version_nr):",
             sorted(m1["generationen"].items(), key=lambda p: int(p[0])))
    if m1["kettenbruch_anzahl"]:
        sag("  KETTENBRUCH: %d Zeile(n) verweisen mit prev_id auf eine Zeile, "
            "die es nicht gibt." % m1["kettenbruch_anzahl"])
        sag("    betroffene ids: %s"
            % ", ".join(str(i) for i in m1["kettenbruch_ids"][:30]))

    m2 = b.m2_spalten
    sag("")
    sag("M2 SPALTENBELEGUNG")
    _tabelle(sag, "gesetzt / leer je Spalte:",
             [(name, "%d / %d" % (w["gesetzt"], w["leer"]))
              for name, w in m2.items()
              if isinstance(w, dict) and "gesetzt" in w])
    f = m2["element_id_form"]
    _tabelle(sag, "Form von element_id:", (
        ("'p<post_id>' (Beitragsbehaelter)", f["p_zahl"]),
        ("'pp<n>' (Altform)", f["pp_zahl"]),
        ("sonstige Form", f["sonstige"]),
    ))
    if f["beispiele_sonstige"]:
        sag("    Beispiele sonstiger Formen: %s"
            % ", ".join(f["beispiele_sonstige"][:10]))
    g = m2["element_id_gegen_post_id"]
    _tabelle(sag, "element_id gegen post_id (wo beide gesetzt sind):", (
        ("beide gesetzt", g["beide_gesetzt"]),
        ("sagen dasselbe", g["gleich"]),
        ("WIDERSPRECHEN sich", g["ungleich"]),
    ))
    _tabelle(sag, "Kategorien:", list(m2["kategorien"].items()))

    m3 = b.m3_page_url
    sag("")
    sag("M3 PAGE_URL")
    _tabelle(sag, "", (
        ("verschiedene Adressen", m3["adressen_verschieden"]),
    ))
    _tabelle(sag, "Annotationen je Skript:", list(m3["je_skript"].items()))
    _tabelle(sag, "Annotationen je Query-Parameter:",
             list(m3["je_parameter"].items()))
    sag("  Adressen mit den meisten Annotationen:")
    for d in m3["haeufigste_adressen"]:
        sag("    %s %s" % (_pad(d["annotationen"], 6), d["url"]))
    if m3["teilmengenpaare_anzahl"]:
        sag("  DIESELBE SEITE UNTER MEHREREN ADRESSEN (%d Paar(e)):"
            % m3["teilmengenpaare_anzahl"])
        for p in m3["teilmengenpaare"][:20]:
            sag("    %s  (%d Annot.)" % (p["kurz"], p["annotationen_kurz"]))
            sag("    %s  (%d Annot.)  zusaetzlich: %s"
                % (p["lang"], p["annotationen_lang"],
                   ", ".join(p["zusatz"]) or "(nichts)"))
    else:
        sag("  Keine Adresse ist Teilmenge einer anderen desselben Pfades.")

    m4 = b.m4_selection
    sag("")
    sag("M4 SELECTION_JSON")
    _tabelle(sag, "", (
        ("NULL (= Variante 'whole post')", m4["null"]),
        ("leere Zeichenkette", m4["leer"]),
        ("kein gueltiges JSON-Objekt", m4["ungueltig"]),
        ("gueltiges JSON-Objekt", m4["gueltig"]),
        ("verschiedene Schluesselsignaturen", m4["signaturen_anzahl"]),
    ))
    sag("  Signaturen (sortierte Schluesselmenge):")
    for d in m4["signaturen"]:
        sag("    %s %s" % (_pad(d["anzahl"], 6), d["signatur"]))
    _tabelle(sag, "Haeufigkeit einzelner Schluessel:",
             list(m4["schluessel"].items()))

    off = m4["offsets"]
    sag("  OFFSETS - ein Vergleich ist NUR bei xpathStart == xpathEnd "
        "aussagekraeftig.")
    sag("  offsetStart zaehlt im Knoten von xpathStart, offsetEnd im Knoten "
        "von xpathEnd;")
    sag("  bei verschiedenen Knoten fehlt der gemeinsame Bezugspunkt und es "
        "gibt KEIN Urteil.")
    _tabelle(sag, "", (
        ("vergleichbar (selber Knoten)", off["vergleichbar_selber_knoten"]),
        ("  davon in Ordnung (Ende nach Anfang)", off["in_ordnung"]),
        ("  davon Ende VOR Anfang", off["ende_vor_anfang"]),
        ("  davon Laenge null (Ende == Anfang)", off["laenge_null"]),
        ("NICHT vergleichbar (andere Knoten)",
         off["nicht_vergleichbar_andere_knoten"]),
        ("ohne verwertbare Offsets", off["ohne_offsets"]),
        ("BEANSTANDET (nur aus der ersten Gruppe)", off["beanstandet"]),
    ))
    for d in off["faelle"][:40]:
        sag("    BEANSTANDET id=%s %s offsetStart=%s offsetEnd=%s"
            % (d["id"], _pad(d["art"], 18), d["offsetStart"], d["offsetEnd"]))

    wl = m4["wortlaut"]
    sag("  WORTLAUT - die belastbare Leerpruefung. Eine Markierung ohne "
        "Wortzeichen")
    sag("  traegt keinen Wortlaut, auch wenn sie Zeichen enthaelt "
        "('---', '...').")
    _tabelle(sag, "", (
        ("textContent fehlt", wl["fehlt"]),
        ("textContent ist leer", wl["leer"]),
        ("textContent nur Leerraum", wl["nur_leerraum"]),
        ("textContent OHNE Wortzeichen", wl["ohne_wortzeichen"]),
        ("BEANSTANDET", wl["beanstandet"]),
    ))
    for d in wl["faelle"][:40]:
        sag("    BEANSTANDET id=%s %s laenge=%s probe=%s"
            % (d["id"], _pad(d["art"], 18), d["laenge"], d["probe"]))
    tl = m4["textcontent_laenge"]
    sag("    %s min=%s  median=%s  max=%s"
        % (_pad("Laenge textContent", 42), tl["min"], tl["median"], tl["max"]))

    m5 = b.m5_xpath
    sag("")
    sag("M5 SYNTAX DER XPATH-AUSDRUECKE  (rein als Zeichenkette gemessen)")
    _tabelle(sag, "", (
        ("ohne xpathStart", m5["ohne_xpathstart"]),
        ("ohne xpathEnd", m5["ohne_xpathende"]),
        ("xpathStart == xpathEnd", m5["start_gleich_ende"]),
        ("Praefix './' (aktuell)", m5["praefix"]["punkt"]),
        ("Praefix '//' (Altform Build 029)", m5["praefix"]["doppel"]),
        ("Praefix sonstiges", m5["praefix"]["sonstige"]),
        ("Textknoten als 'text()[n]' (aktuell)", m5["textknoten_neuform"]),
        ("Textknoten als '#text[n]' (Altform 029)", m5["textknoten_altform"]),
        ("endet auf einem Textknoten", m5["endet_auf_textknoten"]),
    ))
    t = m5["tiefe"]
    sag("    %s min=%s  median=%s  max=%s"
        % (_pad("Anzahl Schritte je Ausdruck", 42),
           t["min"], t["median"], t["max"]))
    _tabelle(sag, "Tagnamen in den Schritten (Vorkommen):",
             list(m5["tagnamen"].items())[:15])

    m6 = b.m6_zeit
    sag("")
    sag("M6 ZEIT")
    _tabelle(sag, "", (
        ("frueheste Markierung", m6["frueheste"]),
        ("spaeteste Markierung", m6["spaeteste"]),
        ("VOR dem Produktivbetrieb (%s)" % m6["trennlinie"],
         m6["vor_produktivbetrieb"]),
        ("AB dem Produktivbetrieb", m6["ab_produktivbetrieb"]),
        ("ohne brauchbaren Zeitstempel", m6["ohne_zeitstempel"]),
        ("Zeitstempel in Millisekunden", m6["in_millisekunden"]),
    ))
    _tabelle(sag, "Markierungen je Monat:", list(m6["je_monat"].items()))

    m7 = b.m7_seiten
    sag("")
    sag("M7 SEITENKOPFDATEN  (der BLOB-INHALT wird NICHT gelesen)")
    if not m7.get("vorhanden"):
        sag("  %s" % m7.get("hinweis", "keine Seitendaten"))
        return
    _tabelle(sag, "", (
        ("Seiten in 'pages'", m7["seiten_gesamt"]),
        ("html IS NULL", m7["html_null"]),
        ("html mit Laenge 0", m7["html_leer"]),
    ))
    _tabelle(sag, "typeof(html):", list(m7["html_typ"].items()))
    _tabelle(sag, "http_status:", list(m7["http_status"].items()))
    hl = m7["laenge"]
    sag("  Laenge der gespeicherten Seiten:")
    sag("    %s min=%s  median=%s  max=%s"
        % (_pad("length(html) in Byte", 42), hl["min"], hl["median"],
           hl["max"]))
    sag("  Haeufigste Seitentitel (ein Titel, der ueberall gleich ist, ist "
        "ein Hinweis auf")
    sag("  eine fehlgeschlagene Anmeldung - die Anmeldeseite kommt mit "
        "HTTP 200):")
    for d in m7["titel_haeufigste"]:
        sag("    %s %s" % (_pad(d["seiten"], 6), d["titel"]))
    sag("  Die %d kuerzesten Seiten:" % len(m7["kuerzeste_seiten"]))
    for d in m7["kuerzeste_seiten"]:
        sag("    id=%s len=%s status=%s  %s"
            % (_pad(d["id"], 6), _pad(d["laenge"], 9),
               _pad(d["http_status"], 5), d["url"]))
        sag("           Titel: %s   erstellt: %s"
            % (d["titel"], d["erstellt"]))
    _tabelle(sag, "Zuordnung Annotation -> Seite:", (
        ("Adressen MIT Seite", m7["adressen_mit_seite"]),
        ("Adressen OHNE Seite", m7["adressen_ohne_seite"]),
        ("Annotationen MIT Seite", m7["annotationen_mit_seite"]),
        ("Annotationen OHNE Seite", m7["annotationen_ohne_seite"]),
        ("Annotationen auf LEERER Seite", m7["annotationen_auf_leerer_seite"]),
    ))
    for d in m7["fehlende_adressen"][:20]:
        sag("    OHNE SEITE: %s  (%d Annotationen)"
            % (d["url"], d["annotationen"]))
    for d in m7["leere_seiten_mit_annotationen"][:20]:
        sag("    LEERE SEITE: %s  (%d Annotationen, page_id=%s, len=%s, "
            "status=%s)" % (d["url"], d["annotationen"], d["page_id"],
                            d["laenge"], d["http_status"]))
        sag("           Titel: %s   erstellt: %s"
            % (d["titel"], d["erstellt"]))


def _m8_m9_ausgeben(b: Bestandsbefund, sag) -> None:
    """M8 und M9 im Klartext. Getrennte Funktion, damit _bestand_ausgeben
    nicht ueber die Lesbarkeitsgrenze waechst."""
    m8 = b.m8_urheber
    sag("")
    sag("M8 URHEBER (created_by)")
    sag("  Gueltig ist eine Kennung, die mit 'H0' oder 'h0' beginnt. "
        "Ausgenommen sind")
    sag("  nachweisliche Test- und Entwicklungskonten. Leer und NULL "
        "gelten als ungueltig.")
    _tabelle(sag, "", (
        ("gueltige Ermittlerkennung", m8["gueltige_kennung"]),
        ("ausgenommen (Test-/Entwicklungskonto)", m8["ausgenommen"]),
        ("ungueltige Kennung", m8["ungueltige_kennung"]),
        ("  davon leer oder NULL", m8["leer_oder_null"]),
        ("verschiedene Kennungen", m8["verschiedene_kennungen"]),
    ))
    sag("  %s %7s %7s %7s  %s" % (_pad("Kennung", 22), "Anzahl", "vor", "ab",
                                  "Zeitraum"))
    for d in m8["je_wert"]:
        marke = {"gueltig": "  ", "ausgenommen": "X ",
                 "ungueltig": "! "}[d["klasse"]]
        sag("  %s%s %7d %7d %7d  %s .. %s"
            % (marke, _pad(d["wert"], 20), d["anzahl"],
               d["vor_produktivbetrieb"], d["ab_produktivbetrieb"],
               d["frueheste"], d["spaeteste"]))
    sag("    X = ausgenommen, ! = ungueltige Kennung")
    sag("    Ausschlussliste: %s" % ", ".join(m8["ausschlussliste"]))

    m9 = b.m9_variante
    sag("")
    sag("M9 ANNOTATIONSVARIANTE")
    sag("  Variante 1 'whole post': ganzer Beitrag, kein selection_json, "
        "nur post_id.")
    sag("  Variante 2 'text range': Textpassage, mit selection_json.")
    _tabelle(sag, "", (
        ("Variante 1 'whole post'", m9["whole_post"]),
        ("Variante 2 'text range' gesamt", m9["text_range"]),
        ("  davon OHNE post_id/element_id", m9["text_range_ohne_ort"]),
        ("  davon MIT post_id/element_id (nachgetragen)",
         m9["text_range_mit_ort"]),
        ("WEDER NOCH (darf es nicht geben)", m9["weder_noch"]),
    ))
    sag("    'text range' MIT Ort ist kein Fehler: seit der Ueberarbeitung "
        "wird die")
    sag("    post_id nachgetragen. Nach Etappe 4 soll das der Normalfall "
        "sein.")
    if m9["weder_noch_ids"]:
        sag("    WEDER NOCH, ids: %s"
            % ", ".join(str(i) for i in m9["weder_noch_ids"]))


def _gesamtbilanz(befunde, sag) -> int:
    """Die Summen ueber alle Bestaende. Rueckgabe: Anzahl der Befunde."""
    sag("=" * 78)
    sag("GESAMTBILANZ UEBER %d BESTAND/BESTAENDE" % len(befunde))
    sag("=" * 78)
    sag("  %s %7s %8s %7s %7s %8s %7s %7s"
        % (_pad("Bestand", 12), "Zeilen", "AKTUELL", "wholeP", "textR",
           "ERMITTL", "ausgen.", "unguelt"))
    sag("  " + "-" * 74)
    s_zeilen = s_akt = s_wp = s_tr = s_erm = s_aus = s_ung = 0
    for b in befunde:
        if not b.evidence_lesbar:
            sag("  %s  NICHT LESBAR" % _pad(b.uid, 12))
            continue
        m1, m8, m9 = b.m1_zeilenbestand, b.m8_urheber, b.m9_variante
        kennung = b.uid + (" *" if b.testbestand else "")
        sag("  %s %7d %8d %7d %7d %8d %7d %7d"
            % (_pad(kennung, 12), m1["zeilen_gesamt"], m1["aktuell"],
               m9["whole_post"], m9["text_range"], m8["gueltige_kennung"],
               m8["ausgenommen"], m8["ungueltige_kennung"]))
        s_zeilen += m1["zeilen_gesamt"]; s_akt += m1["aktuell"]
        s_wp += m9["whole_post"]; s_tr += m9["text_range"]
        s_erm += m8["gueltige_kennung"]; s_aus += m8["ausgenommen"]
        s_ung += m8["ungueltige_kennung"]
    sag("  " + "-" * 74)
    sag("  %s %7d %8d %7d %7d %8d %7d %7d"
        % (_pad("SUMME", 12), s_zeilen, s_akt, s_wp, s_tr, s_erm, s_aus,
           s_ung))
    sag("")
    sag("  ERMITTL = created_by beginnt mit 'H0'/'h0' und steht NICHT auf "
        "der Ausschlussliste.")
    sag("  Diese Spalte ist die Trennlinie zwischen Ermittlerarbeit und "
        "Testbetrieb - nicht")
    sag("  der Bestand und nicht der Zeitpunkt. Die Zahlen umfassen ALLE "
        "Zeilen, auch")
    sag("  geloeschte und ueberholte; 'AKTUELL' steht daneben zum "
        "Vergleich.")
    sag("")
    sag("  * = Testbestand (%s). Er wird MITGEZAEHLT und nicht "
        "herausgerechnet;" % ", ".join(TESTBESTAENDE))
    sag("    ob eine dort gesetzte Annotation zu erhalten ist, ist eine "
        "Einzelfallentscheidung.")
    sag("")

    # Die Befunde, die eine Entscheidung verlangen. Sie werden GEZAEHLT und
    # nicht bewertet - ein Schwellwert waere geraten.
    befundzahl = 0
    zeilen = []
    for b in befunde:
        if not b.evidence_lesbar:
            zeilen.append("Bestand %s: evidence_<uid>.db nicht lesbar" % b.uid)
            befundzahl += 1
            continue
        m4, m7, m1 = b.m4_selection, b.m7_seiten, b.m1_zeilenbestand
        m9 = b.m9_variante
        if m4["offsets"]["beanstandet"]:
            zeilen.append(
                "Bestand %s: %d Marke(n) mit unbrauchbaren Offsets IM SELBEN "
                "Knoten, ids %s"
                % (b.uid, m4["offsets"]["beanstandet"],
                   ", ".join(str(d["id"]) for d in m4["offsets"]["faelle"][:20])))
            befundzahl += 1
        if m4["wortlaut"]["beanstandet"]:
            zeilen.append(
                "Bestand %s: %d Marke(n) ohne Wortlaut, ids %s"
                % (b.uid, m4["wortlaut"]["beanstandet"],
                   ", ".join(str(d["id"]) for d in m4["wortlaut"]["faelle"][:20])))
            befundzahl += 1
        if m9["weder_noch"]:
            zeilen.append("Bestand %s: %d Zeile(n) OHNE selection_json und "
                          "OHNE post_id/element_id - Bezug nicht ermittelbar, "
                          "ids %s"
                          % (b.uid, m9["weder_noch"],
                             ", ".join(str(i) for i in m9["weder_noch_ids"][:20])))
            befundzahl += 1
        if m1["kettenbruch_anzahl"]:
            zeilen.append("Bestand %s: %d Kettenbruch/-brueche bei prev_id"
                          % (b.uid, m1["kettenbruch_anzahl"]))
            befundzahl += 1
        if not m7.get("vorhanden"):
            zeilen.append("Bestand %s: keine Seitendaten (%s)"
                          % (b.uid, m7.get("hinweis", "")))
            befundzahl += 1
            continue
        if m7["html_null"] or m7["html_leer"]:
            zeilen.append("Bestand %s: %d Seite(n) ohne Inhalt (html NULL "
                          "oder Laenge 0)"
                          % (b.uid, m7["html_null"] + m7["html_leer"]))
            befundzahl += 1
        if m7["annotationen_ohne_seite"]:
            zeilen.append("Bestand %s: %d Annotation(en) ohne zugehoerige "
                          "Seite" % (b.uid, m7["annotationen_ohne_seite"]))
            befundzahl += 1
        if m7["annotationen_auf_leerer_seite"]:
            zeilen.append("Bestand %s: %d Annotation(en) auf einer LEEREN "
                          "Seite" % (b.uid, m7["annotationen_auf_leerer_seite"]))
            befundzahl += 1
    sag("  BEFUNDE, DIE EINE ENTSCHEIDUNG VERLANGEN: %d" % befundzahl)
    for z in zeilen:
        sag("    - %s" % z)
    if not zeilen:
        sag("    (keine)")
    sag("")
    sag("  LESEHILFE: Dieses Werkzeug ZAEHLT. Es legt keine Schwelle fest, ab")
    sag("  der eine Seite als defekt oder eine Annotation als sinnfrei gilt.")
    sag("  Der BLOB-Inhalt wurde nicht gelesen; M7 beruht ausschliesslich auf")
    sag("  typeof(html), length(html), http_status, title und fetched_at.")
    sag("=" * 78)
    sag("Es wurde nichts am Bestand geaendert.")
    return befundzahl


def lauf(evidence_dir: str, forensic_dir: str, nur_uids, sag,
         kuerzeste: int, json_ziel, ausgenommen=()):
    gefunden = _bestaende_finden(evidence_dir)
    if not gefunden:
        sag("Keine evidence_<uid>.db in %s gefunden." % evidence_dir)
        return RUECK_ABBRUCH
    if nur_uids:
        gewuenscht = {str(u) for u in nur_uids}
        gefunden = [g for g in gefunden if g[0] in gewuenscht]
        if not gefunden:
            sag("Keiner der genannten Bestaende liegt in %s." % evidence_dir)
            return RUECK_ABBRUCH

    sag("=" * 78)
    sag("BESTANDSAUFNAHME DER ANNOTATIONEN - es wird NICHTS geschrieben")
    sag("  Beweismittel : %s" % evidence_dir)
    sag("  Seitendaten  : %s" % forensic_dir)
    sag("  Produktivbetrieb ab: %s" % zeit(PRODUKTIVBETRIEB_AB))
    sag("=" * 78)

    befunde = []
    for uid, pfad in gefunden:
        f_pfad = os.path.join(forensic_dir, "forensic_%s.db" % uid)
        aufnahme = BestandsAufnahme(uid, pfad, f_pfad,
                                    kuerzeste=kuerzeste,
                                    ausgenommen=tuple(ausgenommen))
        b = aufnahme.erheben()
        befunde.append(b)
        _bestand_ausgeben(b, sag)
        _m8_m9_ausgeben(b, sag)
        sag("")

    befundzahl = _gesamtbilanz(befunde, sag)

    if json_ziel:
        inhalt = {
            "werkzeug": "annotationen_bestand",
            "build": 755,
            "evidence_dir": evidence_dir,
            "forensic_dir": forensic_dir,
            "produktivbetrieb_ab": PRODUKTIVBETRIEB_AB,
            "testbestaende": list(TESTBESTAENDE),
            "ausschlussliste": list(AUSGENOMMENE_KENNUNGEN)
                               + list(ausgenommen),
            "bestaende": [b.als_dict() for b in befunde],
        }
        try:
            with open(json_ziel, "w", encoding="utf-8") as fh:
                json.dump(inhalt, fh, ensure_ascii=True, indent=1,
                          sort_keys=True)
        except OSError as exc:
            sag("JSON-Datei nicht schreibbar: %s" % exc)
            return RUECK_ABBRUCH
        sag("JSON geschrieben: %s" % json_ziel)
    return RUECK_BEFUND if befundzahl else RUECK_OHNE_BEFUND


def main(argv=None) -> int:
    zerleger = argparse.ArgumentParser(
        prog="annotationen_bestand",
        description="Bestandsaufnahme der Annotationen: sieben Messbloecke "
                    "ueber evidence_<uid>.db und die KOPFDATEN der "
                    "forensic_<uid>.db. Rein lesend; der BLOB-Inhalt wird "
                    "nicht gelesen.",
        epilog=cli_epilog.epilog("annotationen_bestand"),
        formatter_class=cli_epilog.HilfeFormat)
    zerleger.add_argument("--config", default="./config.yaml",
                          help="Pfad zur config.yaml (Vorgabe: "
                               "./config.yaml)")
    zerleger.add_argument("--evidence-dir", default=None,
                          help="Verzeichnis der evidence_<uid>.db; "
                               "ueberstimmt paths.evidence_db_dir")
    zerleger.add_argument("--forensic-dir", default=None,
                          help="Verzeichnis der forensic_<uid>.db; "
                               "ueberstimmt paths.forensic_db_dir")
    zerleger.add_argument("--uid", action="append", default=[],
                          help="nur diesen Bestand aufnehmen; mehrfach "
                               "angebbar. Ohne Angabe: alle gefundenen.")
    zerleger.add_argument("--kuerzeste", type=int, default=20,
                          help="wie viele der kuerzesten Seiten namentlich "
                               "genannt werden (Vorgabe: 20)")
    zerleger.add_argument("--ausschluss", default="",
                          help="weitere Kennungen, die NICHT als "
                               "Ermittlerarbeit gelten sollen; "
                               "kommagetrennt. ERGAENZT die eingebaute "
                               "Liste (%s), ersetzt sie nicht."
                               % ", ".join(AUSGENOMMENE_KENNUNGEN))
    zerleger.add_argument("--protokoll", default=None,
                          help="dieselben Zeilen zusaetzlich in diese Datei "
                               "schreiben (eingebautes 'tee')")
    zerleger.add_argument("--json", dest="json_ziel", default=None,
                          help="die Zahlen zusaetzlich maschinenlesbar in "
                               "diese Datei schreiben")
    args = zerleger.parse_args(argv)

    # Vorrang Argument > config.yaml > Vorgabewert. Ein gemeinsamer Aufloeser
    # fuer beide Verzeichnisse: so wird die config.yaml einmal gelesen und
    # beide Herkunftszeilen stehen in EINEM Protokoll.
    aufl = werkzeug_konfig.resolver(args)
    evidence_dir = werkzeug_konfig.wert(
        "annotationen_bestand", args, arg_attribut="evidence_dir",
        arg_name="--evidence-dir", config_schluessel="paths.evidence_db_dir",
        default=coded_default("paths.evidence_db_dir"),
        name="evidence_db_dir", r=aufl)
    forensic_dir = werkzeug_konfig.wert(
        "annotationen_bestand", args, arg_attribut="forensic_dir",
        arg_name="--forensic-dir", config_schluessel="paths.forensic_db_dir",
        default=coded_default("paths.forensic_db_dir"),
        name="forensic_db_dir", r=aufl)

    mitschrift = None
    if args.protokoll:
        try:
            mitschrift = open(args.protokoll, "w", encoding="utf-8")
        except OSError as exc:
            print("Protokolldatei nicht schreibbar: %s" % exc)
            return RUECK_ABBRUCH

    def sag(text=""):
        print(text)
        if mitschrift is not None:
            mitschrift.write(text + "\n")

    try:
        zusatz = tuple(t.strip() for t in args.ausschluss.split(",")
                       if t.strip())
        return lauf(str(evidence_dir), str(forensic_dir), args.uid, sag,
                    args.kuerzeste, args.json_ziel, zusatz)
    finally:
        if mitschrift is not None:
            mitschrift.close()


if __name__ == "__main__":
    raise SystemExit(main())
