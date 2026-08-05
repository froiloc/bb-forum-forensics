#!/usr/bin/env python3
# =============================================================================
# tools/diag_spurensequenz_luecken.py
# IT-Forensisches Ermittlungswerkzeug — DIAGNOSE (kein Produktivcode)
# =============================================================================
# Zweck:
#   Zaehlt aus, wie viele erfasste Seiten die Spurensequenz UEBERGEHT.
#   Beleg zu Vorgang 2f1044b9 (Sequenz fuehrt je Thema nur eine Seite),
#   Nebenmessung zu aa0d9033 (Gruppe 'profile' bleibt leer).
#
# WAS GEMESSEN WIRD — und warum ueberhaupt:
#   get_trace_sequence() (db/forensic_db.py) sucht je Erfassungsziel GENAU
#   EINE URL:
#
#       SELECT url FROM blob_lookup WHERE url LIKE ? LIMIT 1
#
#   Das Muster ist '%<fragment><id>%', z.B. '%viewtopic.php?id=120870%'.
#   Ein LIMIT 1 OHNE ORDER BY liefert eine beliebige der passenden Zeilen.
#   Hat ein Thema mehrere erfasste Seiten, gelangt hoechstens eine davon in
#   die Sequenz. Am 05.08.2026 wurde in der VM gemessen: von 6347 Eintraegen
#   traegt KEIN EINZIGER einen Seitenteil (?p= / &p=).
#
#   Dieses Werkzeug beantwortet die Frage, die daraus folgt und die aus dem
#   Browser nicht zu beantworten ist: WIE VIELE Seiten sind es im Bestand?
#   Erst diese Zahl macht aus einem Einzelfall einen Befund - und sie ist
#   zugleich der Nachweis der Behebung, denn nach der Behebung muss sie 0
#   sein.
#
# WAS ES ANFASST:
#   AUSSCHLIESSLICH die forensic_<uid>.db, und die nur LESEND ueber die
#   URI-Form 'mode=ro'. Kein PRAGMA, das den Header beruehren koennte, keine
#   TEMP-VIEW, keine Schreiboperation, keine Kopie.
#
#   Die evidence_<uid>.db wird NICHT geoeffnet. Das ist keine Sparsamkeit,
#   sondern eine Feststellung: 'blob_lookup' ist eine TEMP-VIEW allein ueber
#   fdb.pages und fdb.page_aliases (db/forensic_db.py, _make_blob_lookup_sql).
#   Die Beweismitteldatenbank traegt zu dieser Messung nichts bei - also
#   bleibt sie zu.
#
# SELBSTPROBE:
#   Vor der eigentlichen Messung baut das Werkzeug einen kleinen Bestand mit
#   EINER BEKANNTEN Luecke im Arbeitsspeicher und verlangt, dass die Messung
#   sie findet. Findet sie sie nicht, ist die Messung blind, und das Werkzeug
#   sagt das und bricht ab. Ein 'keine Luecken' von einer Probe, die nichts
#   messen kann, waere schlimmer als kein Ergebnis - es beendet die Suche.
#   (Dasselbe Vorgehen wie in tools/diag_backup_verdraengung.py.)
#
# Aufruf (in der VM, aus dem Verzeichnis des Webservers):
#     python tools/diag_spurensequenz_luecken.py --forensic-db .\data\forensic_2948078.db
#     python tools/diag_spurensequenz_luecken.py --forensic-db ... --json befund.json
#
# Rueckgabewerte:
#     0 = gelaufen, KEINE Luecke gefunden
#     1 = gelaufen, LUECKE gefunden (das ist ein Befund, kein Fehler)
#     2 = Aufruf- oder Zugriffsfehler (Datei fehlt, nicht lesbar, Tabelle fehlt)
#     3 = Selbstprobe fehlgeschlagen - die Messung ist blind, kein Ergebnis
#
# Ausgabe: Konsole und 'diag_spurensequenz_luecken.log' im aktuellen
#          Verzeichnis; mit '--json' zusaetzlich maschinenlesbar.
#
# Abhaengigkeiten: nur Stdlib.
#
# AENDERUNG BUILD 672 - BERICHTIGUNG EINER FALSCHEN ZAHL:
#   Die Fassung aus Build 671 zaehlte URLs statt Seiten. Gegen den echten
#   Bestand (forensic_1488.db, 05.08.2026) meldete sie 73.796 uebergangene
#   "Seiten". Nach Seiten gezaehlt sind es rund 2.000. Die Differenz waren
#   Zweitadressen DERSELBEN Seite: Sprungmarken ('...id=5136#p33461', 65.216
#   Stueck) und ein zweiter Pfad ('/forum/beginner/...', 6.346 Stueck). Beide
#   stehen in page_aliases und tragen dieselbe page_id.
#   Gezaehlt wird jetzt nach page_id. Die Selbstprobe fuehrt seither zwei
#   Zweitadressen mit und verlangt, dass sie NICHT als Luecke gelten.
# Version: v0.8.672 · Build: 672 · 2026-08-05
# =============================================================================

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

# Direktaufruf als Skript: das Paketverzeichnis muss im Suchpfad liegen,
# sonst findet der Import aus "management/" nichts (Muster aus tools/hilfe.py).
_WURZEL = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _WURZEL not in sys.path:
    sys.path.insert(0, _WURZEL)

try:
    from management.help import cli_epilog  # noqa: E402
    _EPILOG = cli_epilog.epilog("diag_spurensequenz_luecken")
    _FORMAT = cli_epilog.HilfeFormat
except Exception:                                    # pragma: no cover
    # Das Werkzeug muss auch dann laufen, wenn der Hilfekatalog (noch) keinen
    # Eintrag kennt. Eine fehlende Hilfe darf eine Messung nicht verhindern.
    _EPILOG = None
    _FORMAT = argparse.HelpFormatter


# -----------------------------------------------------------------------------
# TYPE_MAP — WORTGLEICHE ABSCHRIFT aus db/forensic_db.py, get_trace_sequence().
#
# Absicht: Dieses Werkzeug soll messen, was das Werkzeug HEUTE tut, nicht was
# es tun sollte. Jede Abweichung von der Abschrift wuerde die Messung
# wertlos machen. Wird die Zuordnung dort geaendert, ist sie hier
# nachzuziehen - der Testfall SL05 wacht darueber.
# -----------------------------------------------------------------------------
TYPE_MAP = {
    "viewtopic":         ("topic",   "topic_id",      "viewtopic.php?id="),
    "viewforum":         ("other",   "forum_id",      "viewforum.php?id="),
    "pmsnew_topic":      ("pm",      "pm_topic_id",   "pmsnew.php?mdl=topic&tid="),
    "pmsnew_post":       ("pm",      "pm_topic_id",   "pmsnew.php?mdl=topic&tid="),
    "pms_partner":       ("pm",      "actor_user_id", "pmsnew.php?mdl=list&sid="),
    "pms_overview":      ("pm",      None,            "pmsnew.php?mdl=list"),
    "profile":           ("profile", "actor_user_id", "profile.php?id="),
    "other_profile":     ("profile", "actor_user_id", "profile.php?id="),
    "wholikes":          ("other",   "post_id",       "wholikes.php?pid="),
    "notifications":     ("other",   None,            "notifications.php"),
    "notification_item": ("other",   None,            "notifications.php"),
    "pgp_probe":         ("other",   "actor_user_id", "profile.php?id="),
}

AUSGABEDATEI = "diag_spurensequenz_luecken.log"
LOGLINES: list[str] = []


def log(msg: str = "") -> None:
    """Gibt eine Zeile aus und merkt sie fuer die Protokolldatei vor."""
    print(msg)
    LOGLINES.append(msg)


# =============================================================================
# Datenbeschaffung — ausschliesslich lesend
# =============================================================================

def oeffne_lesend(pfad: Path) -> sqlite3.Connection:
    """
    Oeffnet die Datenbank ueber die URI-Form mit 'mode=ro'.

    'mode=ro' ist die einzige Zusicherung, die SQLite selbst durchsetzt: ein
    Schreibversuch scheitert dann mit einem Fehler, statt stillzuschweigen.
    Fragezeichen und Rautezeichen im Pfad muessen maskiert werden, sonst
    deutet SQLite sie als Beginn der Abfrage- bzw. Fragmentkomponente.
    """
    uri = "file:" + str(pfad).replace("?", "%3f").replace("#", "%23") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def basis_url(con: sqlite3.Connection) -> str:
    """
    Baut die Basis-URL aus forensic_meta ('protocol' + 'domainname').

    Sie wird gebraucht, weil pages.url_canonical und page_aliases.url_raw die
    vollstaendige Onion-Adresse tragen, die Sequenz aber mit dem blossen Pfad
    arbeitet - genau wie der blob_lookup-View sie per REPLACE() entfernt.
    Fehlt eine der beiden Angaben, wird nichts ersetzt; das ist derselbe
    Rueckfall wie im Produktivcode.
    """
    werte = {}
    try:
        for row in con.execute(
                "SELECT key, value FROM forensic_meta "
                "WHERE key IN ('protocol', 'domainname')"):
            werte[row["key"]] = row["value"]
    except sqlite3.Error:
        return ""
    protokoll = werte.get("protocol")
    domain = werte.get("domainname")
    if not protokoll or not domain:
        return ""
    return "%s://%s" % (protokoll, domain)


def lade_urls(con: sqlite3.Connection, basis: str) -> list[tuple[int, str]]:
    """
    Stellt dieselbe URL-Menge zusammen wie der blob_lookup-View:
    pages.url_canonical, dazu je Alias page_aliases.url_raw - beide um die
    Basis-URL bereinigt.

    BEWUSST OHNE die Spalte 'html': die BLOBs sind der weitaus groesste Teil
    der Datei, und fuer diese Messung wird kein einziges Byte davon gebraucht.
    """
    def putz(u: str) -> str:
        return u.replace(basis, "") if basis else u

    urls: list[tuple[int, str]] = []
    for row in con.execute("SELECT id, url_canonical FROM pages"):
        urls.append((int(row["id"]), putz(str(row["url_canonical"] or ""))))
    try:
        for row in con.execute(
                "SELECT page_id, url_raw FROM page_aliases"):
            urls.append((int(row["page_id"]), putz(str(row["url_raw"] or ""))))
    except sqlite3.Error:
        # page_aliases fehlt in aelteren Bestaenden. Das ist kein Abbruchgrund,
        # aber es gehoert gesagt - sonst haelt man die Zahlen fuer vollstaendig.
        log("   HINWEIS: Tabelle 'page_aliases' nicht lesbar - Aliasse fehlen "
            "in dieser Messung.")
    return urls


def lade_ziele(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Erfassungsziele in derselben Reihenfolge wie get_trace_sequence(): id ASC."""
    return list(con.execute(
        "SELECT id, url_type, forum_id, topic_id, post_id, pm_topic_id, "
        "       actor_user_id "
        "FROM scrape_targets WHERE url_type != 'static' ORDER BY id ASC"))


# =============================================================================
# Die Messung
# =============================================================================

def muster_fuer(row: sqlite3.Row) -> tuple[str, str, str] | None:
    """
    Liefert (gruppe, url_typ, suchtext) fuer ein Erfassungsziel - oder None,
    wenn der url_type der Zuordnung unbekannt ist (dann uebergeht ihn auch
    der Produktivcode).
    """
    url_typ = str(row["url_type"] or "")
    if url_typ not in TYPE_MAP:
        return None
    gruppe, id_spalte, fragment = TYPE_MAP[url_typ]

    # -------------------------------------------------------------------------
    # BUILD 675 - BERICHTIGUNG EINES MODELLFEHLERS.
    #
    # Bis Build 674 stand hier: 'ist die Spalte belegt? sonst suche
    # <fragment>None' - was nie passt. Das war eine EIGENE Erfindung und nicht
    # das, was der Produktivcode tut. get_trace_sequence() (db/forensic_db.py,
    # Z. 1350-1369) verzweigt naemlich auf den WERT, nicht auf die Spalte:
    #
    #     id_val = None
    #     if id_col:
    #         id_val = row[id_col]
    #     if id_val is not None:
    #         pattern = f"%{url_fragment}{id_val}%"
    #     else:
    #         pattern = f"%{url_fragment}%"          # <-- der Rueckfall
    #
    # Ein Ziel MIT ID-Spalte, deren Wert aber NULL ist, faellt also in den
    # Rueckfall und sucht das BLOSSE Fragment. Genau das lag im Bestand vor:
    # das einzige 'pgp_probe'-Ziel (st.id 1091) traegt actor_user_id NULL,
    # sucht damit '%profile.php?id=%' und nimmt die erste Profilseite in die
    # Sequenz - unter der Gruppe 'other'.
    #
    # WAS DIESER FEHLER ANGERICHTET HAT: Er ist die Erklaerung fuer die
    # Abweichung 6346 gegen 6347, die ich am 05.08.2026 der fehlenden
    # Reihenfolgezusicherung von 'LIMIT 1' zugeschrieben hatte. Diese Deutung
    # ist damit WIDERLEGT - der eine fehlende Eintrag war mein Modellfehler,
    # nicht SQLite. Der Hinweis auf die unzugesicherte Reihenfolge bleibt
    # sachlich richtig, aber er hatte hier nichts zu suchen: ich habe eine
    # eigene Abweichung mit einer fremden Ursache erklaert.
    # -------------------------------------------------------------------------
    wert = row[id_spalte] if id_spalte else None
    if wert is None:
        return gruppe, url_typ, fragment
    return gruppe, url_typ, fragment + str(wert)


def messe(urls: list[tuple[int, str]],
          ziele: list[sqlite3.Row]) -> dict:
    """
    Fuehrt beide Rechnungen nebeneinander:

      (a) WAS DIE SEQUENZ HEUTE FUEHRT - je Ziel die ERSTE passende URL, und
          eine schon vergebene URL wird uebersprungen (seen_urls). Das ist die
          Abschrift von get_trace_sequence().
      (b) WAS ES GAEBE - je Ziel ALLE passenden URLs.

    Die Differenz aus (b) und (a) ist die Luecke: erfasste Seiten, die zu
    einem Erfassungsziel gehoeren und die die Navigation nie anlaeuft.

    ZUR TREFFERPRUEFUNG: SQLite vergleicht mit LIKE fuer ASCII-Zeichen ohne
    Ruecksicht auf Gross- und Kleinschreibung. Deshalb wird hier ebenfalls in
    Kleinschreibung verglichen - eine Messung, die strenger prueft als der
    gemessene Code, wuerde Treffer erfinden, die es dort nicht gibt.
    """
    urls_klein = [(pid, u, u.lower()) for pid, u in urls]

    gesehen: set[str] = set()
    sequenz: list[dict] = []           # (a)
    vollstaendig: list[dict] = []      # (b)
    ohne_treffer: list[dict] = []      # Ziele, die gar nichts finden
    mehrdeutig: list[dict] = []        # Ziele, deren Muster fremde IDs trifft

    for row in ziele:
        m = muster_fuer(row)
        if m is None:
            continue
        gruppe, url_typ, suchtext = m
        nadel = suchtext.lower()

        treffer = [(pid, u) for pid, u, uk in urls_klein if nadel in uk]

        if not treffer:
            ohne_treffer.append({
                "trace_id": int(row["id"]), "url_type": url_typ,
                "muster": suchtext,
            })
            continue

        # (a) Abschrift des Produktivverhaltens: die erste passende Zeile.
        #     'LIMIT 1 ohne ORDER BY' hat keine zugesicherte Reihenfolge;
        #     die Zeilenfolge der Tabelle ist die naheliegendste Annahme und
        #     wird hier benutzt. Das ist eine ANNAHME und keine Zusicherung -
        #     sie steht auch im Bericht.
        erste_pid, erste = treffer[0]
        if erste not in gesehen:
            gesehen.add(erste)
            sequenz.append({
                "trace_id": int(row["id"]), "url": erste,
                "page_id": erste_pid,
                "gruppe": gruppe, "url_type": url_typ,
            })

        # (b) alle Treffer
        for pid, u in treffer:
            vollstaendig.append({
                "trace_id": int(row["id"]), "url": u, "page_id": pid,
                "gruppe": gruppe, "url_type": url_typ,
            })

        # Mehrdeutigkeit: trifft das Muster auch URLs mit einer LAENGEREN
        # Kennung? '%viewtopic.php?id=120%' passt auch auf 'id=1200'. Das ist
        # kein Schoenheitsfehler - es kann die Seite eines FREMDEN Themas in
        # die Spurenliste eines Beschuldigten holen.
        if suchtext[-1].isdigit():
            fremd = [u for _pid, u in treffer
                     if _ziffer_danach(u.lower(), nadel)]
            if fremd:
                mehrdeutig.append({
                    "trace_id": int(row["id"]), "muster": suchtext,
                    "anzahl": len(fremd), "beispiele": fremd[:3],
                })

    # -------------------------------------------------------------------------
    # DIE LUECKE WIRD NACH SEITE GEZAEHLT, NICHT NACH URL.
    #
    # BUILD 672, nach dem ersten Lauf gegen einen echten Bestand - und gegen
    # meine eigene erste Fassung. Sie zaehlte URLs, und das hat die Zahl um mehr
    # als das Dreissigfache aufgeblaeht: gemeldet wurden 73.796 uebergangene
    # "Seiten", tatsaechlich waren es rund 2.000. Der Rest waren Zweitadressen
    # DERSELBEN Seite:
    #
    #   /forum/viewtopic.php?id=5136#p33461   - Sprungmarke in dieselbe Seite
    #   /forum/beginner/pmsnew.php?...        - zweiter Pfad zu derselben Seite
    #
    # Beide stehen in page_aliases und tragen dieselbe page_id. Eine Zahl, die
    # eine Sprungmarke als uebergangenen Beleg zaehlt, ist nicht bloss ungenau -
    # sie laesst einen Befund dreissigmal groesser aussehen, als er ist, und
    # beschaedigt damit genau das Vertrauen, das eine Messung herstellen soll.
    #
    # page_id ist der Schluessel der SEITE. Nach ihm zu zaehlen legt Pfad- und
    # Ankervarianten von selbst zusammen.
    # -------------------------------------------------------------------------
    seiten_in_sequenz = {e["page_id"] for e in sequenz}
    luecke: dict[int, dict] = {}
    for e in vollstaendig:
        if e["page_id"] not in seiten_in_sequenz and e["page_id"] not in luecke:
            luecke[e["page_id"]] = e

    return {
        "sequenz": sequenz,
        "vollstaendig_seiten": len({e["page_id"] for e in vollstaendig}),
        "vollstaendig_urls": len({e["url"] for e in vollstaendig}),
        "luecke": list(luecke.values()),
        # Die Zaehlung, die Build 671 ausgewiesen hat: URLs, die nicht selbst
        # als Sequenz-URL vorkommen. Sie bleibt im Bericht stehen, damit die
        # Berichtigung nachvollziehbar ist und niemand die alte Zahl fuer
        # verschwunden haelt (Grundregel 1 gilt auch fuer eigene Fehler).
        "luecke_urls": len({e["url"] for e in vollstaendig
                            if e["url"] not in gesehen}),
        "ohne_treffer": ohne_treffer,
        "mehrdeutig": mehrdeutig,
    }


def _ziffer_danach(url_klein: str, nadel: str) -> bool:
    """
    Wahr, wenn direkt hinter dem Suchtext noch eine Ziffer steht - dann hat
    das Muster eine LAENGERE Kennung getroffen als gemeint.
    """
    i = url_klein.find(nadel)
    while i >= 0:
        j = i + len(nadel)
        if j < len(url_klein) and url_klein[j].isdigit():
            return True
        i = url_klein.find(nadel, i + 1)
    return False


# =============================================================================
# Selbstprobe
# =============================================================================

def selbstprobe() -> tuple[bool, str]:
    """
    Baut einen kleinen Bestand mit EINER BEKANNTEN Luecke und verlangt, dass
    die Messung sie findet.

    Aufbau: Thema 120870 mit drei erfassten Seiten, dazu die Seiten der
    Themen 12 und 120, und zwei Erfassungsziele (120870 und 12).

    ERWARTET WERDEN VIER LUECKEN, und die vierte ist der Grund, warum diese
    Probe so und nicht einfacher gebaut ist. Beim Bauen war ich von DREI
    ausgegangen; die Probe hat mich widerlegt, und ihre Rechnung ist richtig:

      Ziel 120870 findet die Seiten 1, 2, 3 -> Seite 1 kommt in die Sequenz,
      die Seiten 2 und 3 fehlen. Das sind die beiden erwarteten Luecken.

      Ziel 12 sucht mit '%viewtopic.php?id=12%'. Dieses Muster passt AUCH auf
      '...id=120870' - und zwar zuerst. Der Produktivcode nimmt die erste
      Zeile, findet sie in seen_urls schon vergeben und ueberspringt das Ziel
      vollstaendig. Ergebnis: das Thema 12 hat ein Erfassungsziel, eine
      erfasste Seite - und KEINEN EINZIGEN Eintrag in der Sequenz. Seine
      eigene Seite ist ueber die Navigation nicht erreichbar, weil ein
      fremdes Thema mit laengerer Kennung sie verdraengt hat.

    Die Probe verlangt deshalb beides: die vier Luecken UND dass Ziel 12
    keinen Eintrag beisteuert.

    OHNE SQLITE, und das ist Absicht. Ein 'lesend' gefuehrtes Werkzeug darf
    keine schreibfaehige Verbindung oeffnen - auch keine auf ':memory:'.
    Die Regel PY4 (tests/test_py4_lesend.py, Fall PY01) prueft das am
    Quelltext und kann nicht unterscheiden, ob hinter der Verbindung eine
    Datei oder nur Arbeitsspeicher steht. Eine Ausnahme dafuer einzutragen
    waere der falsche Weg: sie wuerde die Pruefung fuer dieses Werkzeug
    dauerhaft blind machen, um eine Bequemlichkeit zu retten. messe() braucht
    ohnehin nur zwei Listen - die lassen sich von Hand hinschreiben.
    Aufgefallen beim Regressionslauf zu Build 671.

    Rueckgabe: (bestanden, Begruendung)
    """
    def ziel(kennung: int, url_typ: str, **spalten):
        # Nachbau einer Zeile aus scrape_targets. messe() greift ueber
        # row["<spalte>"] zu - ein dict genuegt dafuer vollstaendig.
        zeile = {"id": kennung, "url_type": url_typ, "forum_id": None,
                 "topic_id": None, "post_id": None, "pm_topic_id": None,
                 "actor_user_id": None}
        zeile.update(spalten)
        return zeile

    # Die beiden letzten Zeilen tragen die page_id 1 - sie sind ZWEITADRESSEN
    # der ersten Seite (Sprungmarke bzw. zweiter Pfad), wie sie in
    # page_aliases stehen. Sie duerfen NICHT als uebergangene Seite zaehlen.
    # Build 672: genau das hat die erste Fassung getan.
    urls = [
        (1, "/forum/viewtopic.php?id=120870"),
        (2, "/forum/viewtopic.php?id=120870&p=2"),
        (3, "/forum/viewtopic.php?id=120870&p=3"),
        (4, "/forum/viewtopic.php?id=12"),
        (5, "/forum/viewtopic.php?id=120"),
        (1, "/forum/viewtopic.php?id=120870#p4711"),
        (1, "/forum/beginner/viewtopic.php?id=120870"),
    ]
    ziele = [
        ziel(1, "viewtopic", topic_id=120870),
        ziel(2, "viewtopic", topic_id=12),
    ]
    erg = messe(urls, ziele)

    luecken_urls = sorted(e["url"] for e in erg["luecke"])
    erwartet = ["/forum/viewtopic.php?id=12",
                "/forum/viewtopic.php?id=120",
                "/forum/viewtopic.php?id=120870&p=2",
                "/forum/viewtopic.php?id=120870&p=3"]
    if luecken_urls != erwartet:
        return False, ("erwartet wurden die Luecken %s, gefunden wurden %s"
                       % (erwartet, luecken_urls))
    if not erg["mehrdeutig"]:
        return False, "die Mehrdeutigkeit id=12 gegen id=120870 wurde nicht erkannt"
    ziele_in_sequenz = {e["trace_id"] for e in erg["sequenz"]}
    if 2 in ziele_in_sequenz:
        return False, ("Ziel 12 steuert wider Erwarten einen Sequenzeintrag "
                       "bei - die Verdraengung durch die laengere Kennung "
                       "wird nicht mehr nachgestellt")
    if any(e["page_id"] == 1 for e in erg["luecke"]):
        return False, ("eine Zweitadresse der ersten Seite (Sprungmarke oder "
                       "zweiter Pfad) wird als uebergangene Seite gezaehlt - "
                       "genau der Fehler aus Build 671")
    return True, ("4 bekannte Luecken gefunden, Mehrdeutigkeit erkannt "
                  "(%d Ziel(e)), das verdraengte Ziel steuert wie erwartet "
                  "nichts bei, und die beiden Zweitadressen zaehlen nicht mit"
                  % len(erg["mehrdeutig"]))


# =============================================================================
# Bericht
# =============================================================================

def bericht(erg: dict, gesamt_urls: int, gesamt_ziele: int) -> None:
    """Schreibt die Zahlen so auf, dass sie ohne Rueckfrage lesbar sind."""
    sequenz = erg["sequenz"]
    luecke = erg["luecke"]

    log("ERGEBNIS")
    log("-" * 78)
    log("  ES WIRD NACH SEITEN GEZAEHLT (page_id), NICHT NACH URLs. Eine Seite")
    log("  traegt oft mehrere Adressen - eine Sprungmarke ('...#p4711') und")
    log("  einen zweiten Pfad ('/forum/beginner/...') - und ist trotzdem EINE")
    log("  Seite. Build 671 zaehlte URLs und meldete dadurch die dreissigfache")
    log("  Menge. Die URL-Zahlen stehen weiter unten zum Vergleich.")
    log()
    log("  URLs im Bestand (pages + Aliasse) : %d" % gesamt_urls)
    log("  Erfassungsziele (ohne 'static')   : %d" % gesamt_ziele)
    log("  Eintraege in der Sequenz (heute)  : %d" % len(sequenz))
    log("  Erreichbare SEITEN               : %d" % erg["vollstaendig_seiten"])
    log("  DAVON NICHT IN DER SEQUENZ        : %d   <== die Luecke" % len(luecke))
    log("     zum Vergleich, nach URLs gezaehlt: %d von %d"
        % (erg["luecke_urls"], erg["vollstaendig_urls"]))
    log()

    if luecke:
        mit_seitenteil = [e for e in luecke
                          if "?p=" in e["url"] or "&p=" in e["url"]]
        log("  davon mit Seitenteil (?p= / &p=)  : %d" % len(mit_seitenteil))
        nach_gruppe: dict[str, int] = {}
        for e in luecke:
            nach_gruppe[e["gruppe"]] = nach_gruppe.get(e["gruppe"], 0) + 1
        log("  nach Gruppe: %s" % nach_gruppe)
        log()
        log("  Die ersten 15 uebergangenen Seiten:")
        for e in luecke[:15]:
            log("    [%s] %s" % (e["gruppe"], e["url"]))
        if len(luecke) > 15:
            log("    ... und %d weitere (vollstaendig mit '--json')"
                % (len(luecke) - 15))
        log()

    gruppen: dict[str, int] = {}
    for e in sequenz:
        gruppen[e["gruppe"]] = gruppen.get(e["gruppe"], 0) + 1
    log("  Verteilung der Sequenz nach Gruppe: %s" % gruppens(gruppen))
    if gruppen.get("profile", 0) == 0:
        log("    BEFUND zu aa0d9033: die Gruppe 'profile' ist LEER.")
        prof_in_other = [e for e in sequenz
                         if e["gruppe"] == "other" and "profile.php" in e["url"]]
        log("    Profilseiten, die in der Gruppe 'other' stehen: %d"
            % len(prof_in_other))
        if prof_in_other:
            log("    Ursache im Code: 'pgp_probe' bildet auf dasselbe "
                "URL-Fragment ab wie 'profile' und belegt die URL zuerst.")
    log()

    if erg["ohne_treffer"]:
        log("  ERFASSUNGSZIELE OHNE JEDE PASSENDE SEITE: %d"
            % len(erg["ohne_treffer"]))
        log("    Der Produktivcode uebergeht sie stillschweigend "
            "(get_trace_sequence: 'if not bl_row: continue').")
        typen: dict[str, int] = {}
        for e in erg["ohne_treffer"]:
            typen[e["url_type"]] = typen.get(e["url_type"], 0) + 1
        log("    nach url_type: %s" % typen)
        log()

    if erg["mehrdeutig"]:
        log("  MEHRDEUTIGE MUSTER: %d Erfassungsziel(e)" % len(erg["mehrdeutig"]))
        log("    Das Muster trifft auch Seiten mit einer LAENGEREN Kennung -")
        log("    '%viewtopic.php?id=120%' passt auch auf 'id=1200'. Dadurch "
            "kann")
        log("    die Seite eines fremden Themas in die Spurenliste geraten.")
        for e in erg["mehrdeutig"][:5]:
            log("    Ziel %d, Muster '%s': %d Fremdtreffer, z.B. %s"
                % (e["trace_id"], e["muster"], e["anzahl"], e["beispiele"][0]))
        log()


def gruppens(d: dict) -> str:
    """Gruppenzaehlung in fester Reihenfolge - sonst wechselt sie je Lauf."""
    return ", ".join("%s: %d" % (g, d.get(g, 0))
                     for g in ("profile", "pm", "topic", "other"))


# =============================================================================
# main
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Diagnose: welche erfassten Seiten uebergeht die "
                    "Spurensequenz? (nur lesend)",
        epilog=_EPILOG,
        formatter_class=_FORMAT,
    )
    ap.add_argument("--forensic-db", required=True,
                    help="Pfad zur forensic_<uid>.db (wird NUR gelesen)")
    ap.add_argument("--json", default=None,
                    help="Zusaetzlich einen maschinenlesbaren Befund schreiben")
    ap.add_argument("--ohne-selbstprobe", action="store_true",
                    help="Selbstprobe auslassen (nicht empfohlen)")
    args = ap.parse_args()

    log("=" * 78)
    log("DIAGNOSE: Luecken der Spurensequenz (Vorgang 2f1044b9)")
    log("=" * 78)
    log("Python      : %s" % sys.version.split()[0])
    log("sqlite3-Lib : %s" % sqlite3.sqlite_version)
    log("Datenbank   : %s" % args.forensic_db)
    log("Zugriff     : ausschliesslich lesend (URI mode=ro)")
    log()

    # --- Selbstprobe --------------------------------------------------------
    if args.ohne_selbstprobe:
        log("SELBSTPROBE AUSGELASSEN. Das Ergebnis dieses Laufs ist damit "
            "nicht abgesichert.")
        log()
    else:
        log("SELBSTPROBE (bekannte Luecke im Arbeitsspeicher)")
        ok, warum = selbstprobe()
        if not ok:
            log("   FEHLGESCHLAGEN: %s" % warum)
            log()
            log("   Die Messung kann nicht messen, was sie messen soll. Es "
                "wird KEIN Ergebnis")
            log("   ausgewiesen - ein 'keine Luecken' von einer blinden Probe "
                "beendet die Suche,")
            log("   statt sie zu fuehren.")
            schreibe_protokoll()
            return 3
        log("   BESTANDEN: %s" % warum)
        log()

    # --- Bestand oeffnen ----------------------------------------------------
    pfad = Path(args.forensic_db)
    if not pfad.is_file():
        log("FEHLER: '%s' ist keine Datei." % pfad)
        schreibe_protokoll()
        return 2
    try:
        con = oeffne_lesend(pfad)
        basis = basis_url(con)
        log("Basis-URL   : %s" % (basis or "(keine - es wird nichts ersetzt)"))
        urls = lade_urls(con, basis)
        ziele = lade_ziele(con)
        con.close()
    except sqlite3.Error as exc:
        log("FEHLER beim Lesen: %s" % exc)
        schreibe_protokoll()
        return 2

    log("Gelesen     : %d URLs, %d Erfassungsziele" % (len(urls), len(ziele)))
    log()

    erg = messe(urls, ziele)
    bericht(erg, len(urls), len(ziele))

    log("ZUR EINORDNUNG")
    log("-" * 78)
    log("  'LIMIT 1 ohne ORDER BY' hat keine zugesicherte Reihenfolge. Dieses")
    log("  Werkzeug nimmt die Zeilenfolge der Tabelle an - dieselbe Annahme,")
    log("  die SQLite in der Praxis meist erfuellt. Welche EINZELNE Seite je")
    log("  Ziel in der Sequenz landet, kann davon abweichen.")
    log()
    log("  BUILD 671 STAND HIER: 'wie viele Seiten uebergangen werden, steht")
    log("  fest'. Das war zu fest behauptet. Eine Groesse wackelt wirklich:")
    log("    - Die Trefferpruefung ist eine Teilzeichenkette. Das Muster")
    log("      'sid=2' passt auch auf 'sid=202313'. Solche Fremdtreffer")
    log("      stehen oben unter MEHRDEUTIGE MUSTER und koennen die Zahl der")
    log("      erreichbaren Seiten nach OBEN verfaelschen.")
    log("  Die Zahl ist damit eine belastbare OBERGRENZE, kein Endstand.")
    log()
    log("  ZURUECKGENOMMEN (Build 675): hier stand, die Abweichung von genau")
    log("  einem Eintrag gegenueber dem laufenden Server (6346 gegen 6347) sei")
    log("  der Beleg fuer die unzugesicherte Reihenfolge von 'LIMIT 1'. Das war")
    log("  falsch. Der fehlende Eintrag war ein Modellfehler dieses Werkzeugs:")
    log("  ein Erfassungsziel mit ID-Spalte, deren Wert NULL ist, faellt im")
    log("  Produktivcode auf das BLOSSE Fragment zurueck - hier wurde statt")
    log("  dessen nach '<fragment>None' gesucht. Berichtigt; die Zahl sollte")
    log("  jetzt mit dem Server uebereinstimmen. Der Hinweis auf die")
    log("  Reihenfolge bleibt sachlich richtig, war hier aber die falsche")
    log("  Erklaerung fuer eine eigene Abweichung.")
    log()

    if args.json:
        try:
            Path(args.json).write_text(
                json.dumps(erg, ensure_ascii=False, indent=2), encoding="utf-8")
            log("Maschinenlesbarer Befund geschrieben: %s" % args.json)
        except OSError as exc:
            log("WARNUNG: '%s' nicht schreibbar: %s" % (args.json, exc))

    schreibe_protokoll()
    return 1 if erg["luecke"] else 0


def schreibe_protokoll() -> None:
    """Protokoll ablegen - ein Lauf, dessen Ausgabe nur im Fenster stand, ist
    spaeter kein Beleg mehr."""
    try:
        Path(AUSGABEDATEI).write_text("\n".join(LOGLINES) + "\n",
                                      encoding="utf-8")
        print("\nProtokoll: %s" % Path(AUSGABEDATEI).resolve())
    except OSError as exc:                            # pragma: no cover
        print("\nWARNUNG: Protokoll nicht schreibbar: %s" % exc)


if __name__ == "__main__":
    sys.exit(main())
