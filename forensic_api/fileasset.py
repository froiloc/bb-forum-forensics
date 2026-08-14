# =============================================================================
# forensic_api/fileasset.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt GET /_forensic/fileasset?url=<encoded_full_url>
#
#   Liefert ein Asset aus assets_<uid>.db anhand seiner vollständigen
#   Original-URL (z.B. http://filer.onion/images/.../hash).
#
#   Wird ausschließlich vom Browser aufgerufen wenn blob_handler.py beim
#   Ausliefern von HTML/CSS die Original-URLs ersetzt hat:
#     http://filer.onion/img/x.jpg
#     → /_forensic/fileasset?url=http%3A%2F%2Ffiler.onion%2Fimg%2Fx.jpg
#
#   Der Browser kennt die Original-URL nicht mehr — er sieht nur den
#   lokalen Proxy-Pfad. Die forensische Integrität der gespeicherten
#   BLOBs bleibt unberührt, da das Rewriting nur bei der Auslieferung
#   stattfindet.
#
# Lookup:
#   assets_<uid>.db via AssetsDb.get_asset_by_full_url(url)
#   Kein Fallback auf default.db — Filehoster-Assets sind nutzerspezifisch.
#   Kein Live-Fetch — nur was in der DB ist wird ausgeliefert.
#
# Fehlerverhalten (BERICHTIGT IN BUILD 722, Ticket c9d24a7f):
#   Kein url-Parameter        → HTTP 400
#   URL nicht in DB           → HTTP 404
#   assets_db nicht angebunden→ HTTP 404 (Regelfall vor dem asset_importer)
#   Abfrage GESCHEITERT       → HTTP 503, code DB_UNAVAILABLE   ← NEU
#
#   Bis Build 721 stand hier pauschal 'assets_db nicht verfügbar → HTTP 404'.
#   Das war richtig beschrieben und trotzdem falsch: die drei Faelle
#   'nicht angebunden', 'kein Treffer' und 'Abfrage aufgegeben' ergaben
#   ALLE ein 404 (Beleg: db/assets_db.py, _retryable_query Z. 296-298 gab
#   nach drei Versuchen None zurueck - genau wie ein Treffer ins Leere).
#   Ein Ermittler sah in beiden Faellen ein fehlendes Bild und hatte keinen
#   Anlass nachzufragen. Das ist der stille Fehlschlag aus Grundregel 1.
#
# Forensische Relevanz:
#   Kein Schreiben, kein Netzwerkzugriff. READ-ONLY.
#   Beleg: Projektgespräch 2026-05-31.
#
# Version: v0.8.722 · Build: 722 · 2026-08-14
#
# Changelog Build 272 (2026-05-31):
#   - urllib.parse.unquote() auf den url-Parameter entfernt.
#     parse_qs() dekodiert den Query-Parameter bereits einmal.
#     Ein zweites unquote() dekodiert zu viel: %252F → %2F statt %252F,
#     der resultierende String stimmt nicht mit der DB-URL überein.
#     Beleg: URL-Roundtrip-Analyse 2026-05-31.
# Changelog Build 722 (2026-08-14, Ticket c9d24a7f):
#   - Schutzhuelle (forensic_api/db_guard.geschuetzt) gegen den
#     Verbindungsabbruch, wie bei templates_ep seit Build 578.
#   - Ein GESCHEITERTER Lookup wird als 503 benannt statt als 404 verkleidet.
#     Die Huelle allein haette das NICHT geleistet - AssetsDb faengt seine
#     Fehler selbst ab und gibt None zurueck; die Huelle kaeme nie zum Zuge.
#     Das ist derselbe Befund wie bei templates_ep in Build 579.
# =============================================================================

from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

from core.logger import get_logger
from db.assets_db import BEFUND_ABFRAGEFEHLER, BEFUND_NICHT_ANGEBUNDEN

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle

logger = get_logger(__name__)


class FileassetEndpoint:
    """
    Endpunkt /_forensic/fileasset?url=<encoded_full_url>

    Liefert Assets aus assets_<uid>.db anhand ihrer vollständigen
    Original-URL (nicht dem lokalen Pfad).
    Beleg: Projektgespräch 2026-05-31.
    """

    def __init__(self, bundle: "DatabaseBundle") -> None:
        self._bundle = bundle

    def handle(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        """
        Verarbeitet GET /_forensic/fileasset?url=<encoded>.

        Args:
            handler: ForensicRequestHandler-Instanz.
            params:  URL-Query-Parameter aus urllib.parse.parse_qs.
                     Erwartet: url (vollständige URL, URL-encoded).
        """
        # BUILD 722 (Ticket c9d24a7f): DIE HUELLE SITZT AM EINGANG.
        #
        # Wie bei templates_ep (Build 578) umschliesst sie den GANZEN
        # Handler und nicht einzelne Aufrufe. Gefangen werden ausdruecklich
        # nur sqlite3.Error und OSError - ein Programmierfehler soll ein
        # Programmierfehler bleiben (die Begruendung steht in db_guard.py).
        #
        # Sie ist hier das ZWEITE Netz. Das erste ist die Befundauswertung
        # in _liefere(): AssetsDb faengt seine Datenbankfehler selbst ab, die
        # Huelle allein saehe davon nichts. Genau dieser Irrtum hat in Build
        # 578/579 zwei Anlaeufe gekostet.
        from forensic_api.db_guard import geschuetzt
        geschuetzt(handler, "assets_<uid>.db",
                   lambda: self._liefere(handler, params))

    def _liefere(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        """Die eigentliche Auslieferung (von handle umhuellt aufgerufen)."""
        # url-Parameter dekodieren
        raw = (params.get("url") or [None])[0]
        if not raw:
            logger.debug("/_forensic/fileasset: kein url-Parameter")
            handler.send_response_body(
                400, b"url-Parameter fehlt",
                content_type="text/plain; charset=utf-8",
            )
            return

        # url-Parameter: parse_qs() hat ihn bereits einmal dekodiert.
        # Kein weiteres unquote() — das würde eine Kodierungsebene zu viel
        # entfernen und den String von der DB-URL abweichen lassen.
        # Beispiel: DB hat %252F; nach parse_qs: %252F; nach extra unquote: %2F → Mismatch.
        # Beleg: URL-Roundtrip-Analyse 2026-05-31.
        full_url = raw
        logger.debug("/_forensic/fileasset: Lookup '%s'", full_url[:80])

        # Lookup in assets_<uid>.db per vollständiger URL.
        #
        # BUILD 722: MIT BEFUND. Bis Build 721 stand hier
        # get_asset_by_full_url(), und ein None wurde ausnahmslos zu 404.
        asset, befund = self._bundle.assets.get_asset_by_full_url_befund(
            full_url)

        if befund == BEFUND_ABFRAGEFEHLER:
            # DER EINE FALL, DER NICHT WIE EIN FEHLENDES BILD AUSSEHEN DARF.
            # Die Datenbank ist da, die Abfrage ist gescheitert - der
            # Ermittler sieht sonst ein fehlendes Bild und hat keinen Anlass
            # nachzufragen. Der Pfad geht ins Protokoll, nicht in die
            # Antwort (Festlegung db_guard.py).
            from forensic_api.db_guard import db_fehler_koerper
            logger.error(
                "/_forensic/fileasset: Abfrage auf assets_<uid>.db "
                "gescheitert — URL '%s'", full_url[:120])
            handler.send_response_body(
                503,
                db_fehler_koerper(
                    "assets_<uid>.db", "abfragefehler",
                    massnahme=(
                        "Die Datenbank ist angebunden, die Abfrage ist "
                        "gescheitert. Serverprotokoll lesen (Pfad und "
                        "SQLite-Meldung stehen dort). Das Bild ist NICHT "
                        "als fehlend belegt - es wurde nicht nachgesehen.")),
                content_type="application/json; charset=utf-8",
            )
            return

        if asset is None:
            # 'nicht angebunden' und 'kein Treffer' bleiben 404 - beides ist
            # eine Tatsache ueber den Bestand und kein Fehlschlag. Sie werden
            # aber UNTERSCHIEDLICH protokolliert, damit die Betriebsseite den
            # nicht gelaufenen asset_importer erkennen kann, ohne raten zu
            # muessen (Entscheidung Alex, 14.08.2026).
            if befund == BEFUND_NICHT_ANGEBUNDEN:
                logger.info(
                    "/_forensic/fileasset: assets_<uid>.db ist nicht "
                    "angebunden — es wird KEIN Asset ausgeliefert. Das ist "
                    "der Regelfall vor dem asset_importer-Lauf. URL: '%s'",
                    full_url[:80])
            else:
                logger.debug(
                    "/_forensic/fileasset: nicht in assets_db: '%s'",
                    full_url[:80])
            handler.send_response_body(404, b"")
            return

        data = asset.data or b""
        mime = asset.mime_type or "application/octet-stream"

        logger.debug(
            "/_forensic/fileasset: ausgeliefert '%s' (%s, %d bytes)",
            full_url[:60], mime, len(data),
        )
        handler.send_response_body(
            200, data,
            content_type=mime,
            extra_headers={"Cache-Control": "max-age=3600, immutable"},
        )
