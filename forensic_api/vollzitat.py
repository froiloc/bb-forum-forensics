# =============================================================================
# forensic_api/vollzitat.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Beweismittelgruppen)
# =============================================================================
# Zweck:
#   GET /_forensic/vollzitat?ids=4711,4712,4730[&label=...]
#
#   Liefert dem Berichtseditor GENAU DAS, was auch im Bericht steht: den
#   umschliessenden Absatz mit hinterlegter Markierung, die Art der Quelle,
#   das Originaldatum, die Fundstelle, die Notiz und den Nachnamen des
#   Ermittlers - gruppiert nach Quelle.
#
# WARUM DER BILDSCHIRM DAS NICHT SELBST RECHNET. Er koennte es nicht: der
#   umschliessende Absatz steht im gesicherten Seitenabzug (fdb.pages), der
#   Themenbetreff in fdb.uid_topics, der Ermittlername in cdb.person - der
#   Editor sieht keine dieser Tabellen, er hat nur den Annotations-Speicher
#   (window._evidenceAnnotationCache).
#
#   Er SOLLTE es aber auch dann nicht, wenn er es koennte. Bildschirm und
#   Akte muessen dasselbe zeigen; das ist die Paritaetszusage der
#   Berichtsausgabe (report_render/html_renderer.py, Kopf, "Paritaet, §6").
#   Zwei Stellen, die dieselbe Frage beantworten, geben irgendwann zwei
#   Antworten - daran ist der Zitatblock schon einmal zerbrochen (Vorgang
#   9c41a7e6). Deshalb ruft dieser Endpunkt denselben VollzitatBauer, den
#   report_source ruft, und schickt dessen Ergebnis als JSON.
#
# ES WIRD NICHTS GESCHRIEBEN. Rein lesend auf evidence (annotations), fdb
#   (pages/uid_posts/uid_topics/uid_pms_posts) und cdb (person). Kein Schema,
#   keine Migration, kein Schreibzugriff - der Migrationsvorbehalt ab
#   01.07.2026 ist nicht beruehrt. Kein Lock noetig (anders als bei
#   /_forensic/editor/evidence, das schreibt).
#
# DIE OBERGRENZE IST KEINE SCHIKANE. Eine Beweismittelgruppe mit 300 Belegen
#   auf 300 verschiedenen Themenseiten hiesse 300 Seitenabzuege zerlegen,
#   waehrend der Bearbeiter auf die Ansicht wartet. Ueberzaehlige Belege
#   werden deshalb NICHT verschwiegen, sondern gemeldet ('abgeschnitten' in
#   der Antwort) - GR1 verlangt, dass eine Auslassung benannt wird, nicht
#   dass es sie nicht gibt.
#
# Grundregeln: GR1, GR6, GR10.
# Version: v0.8.726 - Build: 726 - 2026-08-27
# =============================================================================

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, List

from core.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from db.connection_manager import DatabaseBundle
    from server.request_handler import ForensicRequestHandler

logger = get_logger(__name__)

#: Hoechstzahl der Belege je Anfrage - s. Kopf.
MAX_BELEGE = 120


class VollzitatEndpoint:
    """Endpunkt /_forensic/vollzitat - liefert fertige Vollzitat-Gruppen."""

    def __init__(self, bundle: "DatabaseBundle", context: Any = None,
                 config: Any = None) -> None:
        self._bundle = bundle
        self._context = context

    # ------------------------------------------------------------------
    def handle(self, handler: "ForensicRequestHandler", params: dict) -> None:
        """GET /_forensic/vollzitat?ids=4711,4712"""
        roh = (params.get("ids", [""])[0] or "").strip()
        label = (params.get("label", [""])[0] or "").strip()

        ids: List[int] = []
        ungueltig: List[str] = []
        for stueck in roh.split(","):
            stueck = stueck.strip()
            if not stueck:
                continue
            try:
                ids.append(int(stueck))
            except ValueError:
                ungueltig.append(stueck)

        abgeschnitten = 0
        if len(ids) > MAX_BELEGE:
            abgeschnitten = len(ids) - MAX_BELEGE
            ids = ids[:MAX_BELEGE]

        try:
            from report_render.vollzitat_bauer import VollzitatBauer
            bauer = VollzitatBauer(
                evidence=self._bundle.evidence,
                forensic=getattr(self._bundle, "forensic", None),
                con=self._bundle.connection,
            )
            gruppe = bauer.baue(ids, label)
        except Exception as exc:  # pragma: no cover - defensiver 500
            logger.exception("Vollzitat konnte nicht gebaut werden: %s", exc)
            self._json(handler, 500, {
                "error": "vollzitat_failed",
                "detail": str(exc),
            })
            return

        nutzlast = self._als_json(gruppe)
        if ungueltig:
            nutzlast["warnungen"].append(
                "Nicht auswertbare Beleg-Nummern uebergangen: %s."
                % ", ".join(repr(u) for u in ungueltig))
        if abgeschnitten:
            nutzlast["warnungen"].append(
                "Die Gruppe traegt mehr als %d Belege; %d weitere sind in "
                "dieser Ansicht NICHT enthalten. Im ausgelieferten Bericht "
                "sind sie vollstaendig enthalten."
                % (MAX_BELEGE, abgeschnitten))
        nutzlast["abgeschnitten"] = abgeschnitten

        self._json(handler, 200, nutzlast)

    # ------------------------------------------------------------------
    @staticmethod
    def _als_json(gruppe) -> Dict[str, Any]:
        """
        Die Vollzitat-Gruppe in eine JSON-Nutzlast umsetzen.

        DIE FELDNAMEN SIND DIE DER DATENKLASSEN und nicht kuerzer: wer im
        Browser 'befund.absatz_weg' liest, findet dasselbe Wort in
        report_render/vollzitat_satz.py wieder. Abkuerzungen waeren hier
        eine Uebersetzungstabelle, die niemand fuehrt.
        """
        return {
            "beschriftung": gruppe.beschriftung,
            "beleg_anzahl": gruppe.beleg_anzahl,
            "quellen_anzahl": gruppe.quellen_anzahl,
            "warnungen": list(gruppe.warnungen),
            "unterbloecke": [
                {
                    "bezeichnung": ub.quelle.bezeichnung(),
                    "ist_pn": ub.quelle.ist_pn,
                    # Build 727: ein Beleg, den es nicht (mehr) gibt. Der
                    # Bildschirm zeigte ihn bis Build 726 als gewoehnlichen
                    # Forenbeitrag mit fehlendem Absatz - eine erfundene
                    # Quellenart mit glaubwuerdigem Aussehen.
                    "fehlt": ub.quelle.ist_unbekannt,
                    "post_quelle": ub.quelle.post_quelle,
                    "betreff": ub.quelle.betreff,
                    "partner": ub.quelle.partner,
                    "posted_ts": ub.quelle.posted_ts,
                    "post_id": ub.quelle.post_id,
                    "link": ub.quelle.link,
                    "absaetze": [
                        {"html": a.html, "nummern": a.nummern,
                         "ersatz": a.ersatz, "moeglich": a.moeglich,
                         "von_gesamt": list(a.von_gesamt) if a.von_gesamt
                                       else None}
                        for a in ub.absaetze
                    ],
                    "befunde": [
                        {
                            "nummer": b.nummer,
                            "annotation_id": b.annotation_id,
                            "kategorie": b.kategorie,
                            "kategorie_text": b.kategorie_text,
                            "css_klasse": b.css_klasse,
                            "farbe": b.farbe,
                            "markierung": b.markierung,
                            "notiz": b.notiz,
                            "ermittler": b.ermittler,
                            "name_quelle": b.name_quelle,
                            "absatz_weg": b.absatz_weg,
                            "hinweis": b.hinweis,
                        }
                        for b in ub.befunde
                    ],
                }
                for ub in gruppe.unterbloecke
            ],
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _json(handler: "ForensicRequestHandler", status: int,
              nutzlast: Dict[str, Any]) -> None:
        body = json.dumps(nutzlast, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            status=status,
            content_type="application/json; charset=utf-8",
            body=body,
        )
