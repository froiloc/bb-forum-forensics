# =============================================================================
# forensic_api/review_comment_view.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# Vermaehlung B6xB7 — SF-3, NACHGELIEFERTER EDITOR-LESEPFAD (Build 661)
# =============================================================================
# Zweck:
#   Die Lektorats- und Chef-Kommentare aus den Addendum-Dateien so aufbereiten,
#   dass der Berichtseditor (Fenster 3) sie je Block anzeigen kann.
#
# ── WARUM ES DIESES MODUL ERST JETZT GIBT (Vorgang a84766a7) ────────────────
#
#   Die Kommentar-Bruecke SF-3 war seit Build 412 nur zur HAELFTE gebaut. Das
#   Konzept Vermaehlung_B6_Editor_B7_Management v0.2 nennt in §3 (SF-3) und §4
#   ausdruecklich ZWEI Leser der Addendum-Dateien:
#
#       "Leser = Editor (B6) und Support-View, per Union-Glob
#        addenda/<bucket>/<uid>/*.db"
#
#   und fuehrt im Build-Schnitt §6 unter B-c den "Editor-Lesepfad (B6)" im
#   Touch-Set mit auf. Gebaut wurden Schreiber (db/review_addendum_db.py),
#   Management-Leser (management/reports/review_comment_reader.py) und die
#   Lektorat-Sicht. Der Editor-Lesepfad fehlte.
#
#   Der Umlauf war damit: Cockpit -> Addendum-Datei -> Cockpit. Die
#   verfassende Ermittlerin, AN DIE die Anmerkung gerichtet ist, sah sie nicht.
#   Aufgefallen bei Vorgang 317481d3 (Build 659), als zu klaeren war, wo ein
#   Kommentar zum Gesamtdokument in Baustelle 6 erschiene: an keiner Stelle —
#   und das galt fuer verankerte Kommentare genauso.
#
# ── RICHTUNG DES ZUGRIFFS: NUR LESEN ────────────────────────────────────────
#
#   Der Editor LIEST diese Kommentare und schreibt sie nie. Das ist keine
#   Bequemlichkeit, sondern die tragende Regel des Modells (Konzept §4):
#   "Eine Person, ein Fall, genau EINE Datei" — nur der Besitzer schreibt in
#   seine Addendum-Datei. Der Lebenszyklus des Kommentars bleibt bei der
#   kommentierenden Person: der Pruefer schliesst seinen Einwand, nicht der
#   Verfasser des Vermerks.
#
#   Praktisch heisst das: KEINE Erledigen-/Verwerfen-Schaltflaeche an einem
#   Review-Kommentar im Editor. Die Editor-eigenen Kommentare
#   (evidence.report_comments, forensic_api/editor_comment.py) bleiben davon
#   unberuehrt — sie sind ein anderes Modell mit einem anderen Schreibweg.
#
# ── ANKERLOSE KOMMENTARE GEHEN NICHT VERLOREN ───────────────────────────────
#
#   Ein Review-Kommentar kann eine block_id tragen, muss aber nicht
#   (review_comments.block_id ist nullable; seit Build 659 kann die
#   Lektorat-Maske ihn nicht mehr ohne Anker erzeugen, im Bestand sind solche
#   Zeilen aber denkbar). Ebenso kann ein Anker auf einen Block zeigen, den es
#   im Vermerk nicht mehr gibt — der Baustein wurde geloescht, der Kommentar
#   liegt in einer FREMDEN Datei und wusste nichts davon.
#
#   Beide Faelle landen in 'ohne_block'. Sie DUERFEN NICHT einfach in der
#   Zuordnung verschwinden: ein Kommentar, den niemand mehr sieht, ist von
#   einem nie geschriebenen nicht zu unterscheiden — Grundregel 1. Der
#   Editor zeigt sie gesondert am Dokument.
#
# Grundregeln: GR1 (nichts still auslassen), GR6, GR10 (eine Klasse je Datei).
# Version: v0.8.661 · Build: 661 · 2026-08-02
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

#: Felder, die aus einer review_comments-Zeile an den Editor gehen. BEWUSST
#  eine Positivliste und kein 'dict(row)': die Addendum-Datei ist die Datei
#  einer ANDEREN Person, und was von dort in eine weitere Oberflaeche wandert,
#  soll benannt sein und nicht davon abhaengen, welche Spalten dort einmal
#  hinzukommen. (Fallregel 3, sinngemaess: nur Geprueftes wandert weiter.)
FELDER = (
    "comment_id",
    "report_id",
    "block_id",
    "reviewer_pid",
    "reviewer_role",
    "comment_text",
    "suggested_content",
    "status",
    "block_sha256",
    "created_at",
    "resolved_at",
)


class ReviewCommentView:
    """
    Ordnet Review-Kommentare den Bloecken eines Vermerks zu.

    Reine Umwandlung: kein Datenbankzugriff, kein Dateizugriff. Der Aufrufer
    (forensic_api/report.py) bringt die bereits gelesenen Zeilen mit.
    """

    def __init__(self, kommentare: Optional[Iterable[Mapping[str, Any]]] = None,
                 fehler: Optional[Iterable[Mapping[str, str]]] = None) -> None:
        self._roh: List[Mapping[str, Any]] = [
            k for k in (kommentare or []) if isinstance(k, Mapping)
        ]
        self._fehler: List[Dict[str, str]] = [
            {"datei": str(f.get("datei", "?")), "grund": str(f.get("grund", ""))}
            for f in (fehler or []) if isinstance(f, Mapping)
        ]

    # ------------------------------------------------------------------
    @staticmethod
    def _eintrag(zeile: Mapping[str, Any]) -> Dict[str, Any]:
        """Eine Zeile auf die Positivliste reduzieren."""
        return {feld: zeile.get(feld) for feld in FELDER}

    # ------------------------------------------------------------------
    def je_block(self, bekannte_block_ids: Iterable[str]) -> Dict[str, List[dict]]:
        """
        Abbildung block_id -> Liste der Review-Kommentare, aufsteigend nach
        created_at. Nur Bloecke, die es im Vermerk WIRKLICH gibt; alles
        andere geht ueber ohne_block().
        """
        bekannt = {str(b) for b in bekannte_block_ids}
        zuordnung: Dict[str, List[dict]] = {}
        for zeile in self._roh:
            bid = zeile.get("block_id")
            if bid is None or str(bid) == "" or str(bid) not in bekannt:
                continue
            zuordnung.setdefault(str(bid), []).append(self._eintrag(zeile))
        for liste in zuordnung.values():
            liste.sort(key=lambda c: int(c.get("created_at") or 0))
        return zuordnung

    # ------------------------------------------------------------------
    def ohne_block(self, bekannte_block_ids: Iterable[str]) -> List[dict]:
        """
        Kommentare, die KEINEM Block des Vermerks zugeordnet werden konnten —
        zwei verschiedene Lagen, beide mit demselben Ergebnis fuer die
        Anzeige, aber unterscheidbar benannt:

          grund='ohne_anker'      block_id ist leer (Bestand vor Build 659)
          grund='block_unbekannt' der Anker zeigt auf einen Baustein, den es
                                  im Vermerk nicht (mehr) gibt

        Die Unterscheidung steht im Eintrag, damit die Oberflaeche nicht
        raten muss und die verfassende Person weiss, ob sie eine geloeschte
        Stelle sucht oder eine allgemeine Anmerkung liest.
        """
        bekannt = {str(b) for b in bekannte_block_ids}
        heimatlos: List[dict] = []
        for zeile in self._roh:
            bid = zeile.get("block_id")
            leer = bid is None or str(bid) == ""
            if not leer and str(bid) in bekannt:
                continue
            eintrag = self._eintrag(zeile)
            eintrag["grund"] = "ohne_anker" if leer else "block_unbekannt"
            heimatlos.append(eintrag)
        heimatlos.sort(key=lambda c: int(c.get("created_at") or 0))
        return heimatlos

    # ------------------------------------------------------------------
    def fehler(self) -> List[Dict[str, str]]:
        """
        Addendum-Dateien, die nicht gelesen werden konnten.

        Der Editor MUSS das anzeigen. 'Keine Anmerkung' und 'ihre Datei war
        nicht lesbar' fuehren sonst zur selben Anzeige, und die verfassende
        Person gibt den Vermerk frei, ohne dass jemand die fehlende Rueckmeldung
        vermisst (Grundregel 1).
        """
        return list(self._fehler)

    # ------------------------------------------------------------------
    def anzahl(self) -> int:
        """Zahl aller gelesenen Review-Kommentare (auch der heimatlosen)."""
        return len(self._roh)
