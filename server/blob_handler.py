# =============================================================================
# server/blob_handler.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Der einzige Auslieferungspfad für BLOB-Inhalte.
#   Beantwortet AJAX-Requests auf /_forensic/page?url=...
#   sowie direkte AJAX-Requests auf Forum-URLs (via router.py).
#   Gibt einen JSON-Envelope zurück, den toolbar.js in #forensic-viewport
#   injiziert.
#
# JSON-Envelope:
#   {
#     "html":           "<body-Inhalt oder null>",
#     "head": {
#       "title":         "<Seitentitel oder null>",
#       "stylesheets":   ["<href1>", "<href2>", ...],
#       "inline_styles": ["<CSS-Inhalt>", ...]
#     },
#     "scrape_context": "user|investigator|actor:<uid>",
#     "http_status":    200,
#     "fetch_failed":   false,
#     "in_scope":       true,
#     "url_canonical":  "/forum/viewtopic.php?id=42",
#     "fragment":       "p12345"   (oder null),
#     "trace_elements": ["p1891354", "p1903927"],  (Build 030-C)
#     "fragment_source": "gemessen"                (Build 699, s.u.)
#   }
#
# URL-Auflösung (Reihenfolge):
#   1. Fragment-Anker extrahieren und entfernen
#   2. ?pid=<post_id>   → Seite, die den Beitrag TRAEGT (Build 699)
#   3. ?notify=<id>     → notify_aliases → post_id → wie 2.
#   4. Direkt in blob_lookup suchen
#   5. Ankerprobe: traegt der gefundene BLOB den Anker '#p<post_id>'
#      wirklich? Wenn nein, wird die Seite gesucht, die ihn traegt (Build 699)
#
# fragment_source — Herkunft der ausgelieferten Seite bei Beitragsankern:
#   null           kein Beitragsanker im Spiel (kein '#p<id>')
#   "bestaetigt"   der ausgelieferte BLOB traegt den Anker (Regelfall)
#   "gemessen"     Seite ueber fdb.post_aliases.page bestimmt (Prepper-Messung)
#   "nachgemessen" Seite hier im BLOB nachgemessen (Prepper-Messung fehlte)
#   "unaufgeloest" KEINE erfasste Seite traegt den Anker — ausgeliefert wird
#                  die erste Seite des Themas, der Anker laeuft ins Leere
#   "unpruefbar"   der BLOB fehlt (fetch_failed) — die Probe ist nicht moeglich
#   Das Feld ist Beleg, nicht Zierde: ohne es waere ein Sprung, der sein Ziel
#   verfehlt, von einem, der es trifft, nicht zu unterscheiden (Grundregel 1).
#
# page_visit-Protokollierung:
#   Erfolgt hier nach erfolgreichem BLOB-Lookup (in_scope=True).
#   Nicht bei NOT_IN_SCOPE und nicht bei Shell-Load.
#
# Forensische Relevanz:
#   Sonderfälle werden niemals still übergangen:
#   - NOT_IN_SCOPE:   in_scope=False im JSON
#   - fetch_failed:   fetch_failed=True + http_status im JSON
#   - investigator:   scrape_context='investigator' im JSON
#   Alle drei Zustände sind für toolbar.js sichtbar und werden angezeigt.
#
# Abhängigkeiten: json, urllib.parse — Stdlib + interne Module
# Version: v0.1.0 · Build: 699 · 2026-08-12
#
# Changelog Build 699 (2026-08-12) — Vorgang f5956e6b:
#   - Beitragsverweise in mehrseitigen Themen landeten stets auf Seite 1.
#     '?pid=<id>' wird nicht mehr auf '?id=<topic>' (= erster Chunk)
#     abgebildet, sondern ueber ForensicDb.resolve_post_page() auf die Seite,
#     die den Beitrag TRAEGT.
#   - Neue Ankerprobe nach dem BLOB-Lookup: traegt der gefundene BLOB den
#     Anker '#p<post_id>' nicht, wird die Seite gesucht, die ihn traegt.
#     Damit ist auch die zweite Verweisform '?id=<topic>#p<post_id>'
#     (Verweise INNERHALB des Forums) abgedeckt.
#   - Neues Envelope-Feld 'fragment_source' (s.o.).
#     Beleg: Vorgang f5956e6b; aiw_sqlite_prepper stage2/post_page_measurer.py.
#
# Changelog Build 270 (2026-05-31):
#   - _rewrite_asset_urls(): ersetzt vollständige URLs die in assets_<uid>.db
#     vorhanden sind durch /_forensic/fileasset?url=<encoded>.
#     Wird auf body_html nach _extract_body() angewendet.
#     Beleg: Projektgespräch 2026-05-31.
# Änderungen Build 042:
#   - handle(): neuer Parameter original_method (Default 'GET').
#   - handle_with_fragment(): neuer Parameter original_method (Default 'GET').
#   - _resolve_and_build(): original_method an get_page() weitergeleitet.
#     'POST' liefert den Poll-Abstimmungsergebnis-BLOB.
#     Beleg: Projektgespräch 2026-04-19.
# Änderungen Build 030-C:
#   - Envelope: trace_elements ["p<id>", ...] aus get_trace_elements_for_page().
#   - Beide Envelope-Zweige (in_scope + NOT_IN_SCOPE) enthalten trace_elements.
# =============================================================================

from __future__ import annotations

import json
import re
import urllib.parse
from typing import TYPE_CHECKING, Optional

from core.logger import get_logger
from server.head_extractor import HeadExtractor

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# Regex für Fragment-Anker der Form #p<post_id>
_FRAGMENT_POST_RE = re.compile(r"^p(\d+)$")


class BlobHandler:
    """
    Liefert BLOB-Inhalte als JSON-Envelope für AJAX-Requests.

    Wird von router.py für AJAX-Forum-Requests aufgerufen.
    Wird auch von forensic_api/page.py für /_forensic/page aufgerufen.

    Verwendung:
        blob_handler.handle(request_handler, canonical_url)
        # oder mit explizitem Fragment:
        blob_handler.handle_with_fragment(request_handler, url, fragment)
    """

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle  = bundle
        self._context = context
        self._config  = config

        # Alias-Muster aus config.yaml
        self._post_id_param  = config.get("url_patterns.alias_patterns.post_id_param",  "pid")
        self._notify_param   = config.get("url_patterns.alias_patterns.notify_param",    "notify")
        self._fragment_post  = config.get("url_patterns.alias_patterns.fragment_post",   "p")
        self._head_extractor = HeadExtractor()

    def handle(
        self,
        handler: "ForensicRequestHandler",
        canonical_url: str,
        original_method: str = "GET",
    ) -> None:
        """
        Verarbeitet einen AJAX-Request für eine Forum-URL.

        Args:
            handler:         ForensicRequestHandler-Instanz.
            canonical_url:   Normalisierte URL (ohne Fragment).
            original_method: HTTP-Methode des Originalrequests ('GET' oder 'POST').
                             Default 'GET'. 'POST' für Poll-Ergebnisseiten.
                             Beleg: Projektgespräch 2026-04-19.
        """
        self.handle_with_fragment(handler, canonical_url, fragment=None,
                                  original_method=original_method)

    def handle_with_fragment(
        self,
        handler: "ForensicRequestHandler",
        url: str,
        fragment: Optional[str],
        original_method: str = "GET",
    ) -> None:
        """
        Verarbeitet einen AJAX-Request mit optionalem Fragment-Anker.

        Args:
            handler:         ForensicRequestHandler-Instanz.
            url:             URL (ohne Fragment).
            fragment:        Fragment-Anker ohne #, z.B. "p12345", oder None.
            original_method: HTTP-Methode des Originalrequests ('GET' oder 'POST').
                             Default 'GET'. Beleg: Projektgespräch 2026-04-19.
        """
        envelope = self._resolve_and_build(url, fragment, original_method)
        body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")

        # page_visit protokollieren wenn Seite im Scope und BLOB vorhanden
        if envelope["in_scope"]:
            try:
                self._bundle.evidence.log_page_visit(
                    page_url=envelope["url_canonical"],
                    scrape_context=envelope["scrape_context"],
                    investigator_id=self._context.investigator_id,
                )
            except Exception as exc:
                # Protokollfehler dürfen die Auslieferung nicht blockieren
                logger.warning("page_visit-Protokollierung fehlgeschlagen: %s", exc)

        handler.send_response_body(
            status=200,
            body=body,
            content_type="application/json; charset=utf-8",
        )

    # ------------------------------------------------------------------
    # URL-Auflösung und Envelope-Aufbau
    # ------------------------------------------------------------------

    def _resolve_and_build(
        self, url: str, fragment: Optional[str], original_method: str = "GET"
    ) -> dict:
        """
        Löst die URL auf und baut den JSON-Envelope auf.

        Args:
            original_method: HTTP-Methode des Originalrequests ('GET'/'POST').
                             Wird an get_page() weitergeleitet, damit der
                             korrekte BLOB (GET=Formular, POST=Ergebnis)
                             geladen wird. Beleg: Projektgespräch 2026-04-19.

        Returns:
            Dict mit allen Envelope-Feldern.
        """
        # Schritt 1: URL und Fragment parsen
        parsed   = urllib.parse.urlparse(url)
        url_path = parsed.path
        params   = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)

        # Fragment aus URL extrahieren falls vorhanden (normalerweise leer
        # in HTTP-Requests, aber zur Sicherheit behandeln)
        if parsed.fragment and not fragment:
            fragment = parsed.fragment
        url_no_fragment = urllib.parse.urlunparse(
            parsed._replace(fragment="")
        )

        # Schritt 2: Alias-Auflösung
        resolved_url, fragment, fragment_source = self._resolve_aliases(
            url_no_fragment, url_path, params, fragment
        )

        # Schritt 3: BLOB-Lookup — original_method bestimmt welcher BLOB geladen wird.
        # Bei GET: Abstimmungsformular. Bei POST: Abstimmungsergebnis.
        # Beleg: Projektgespräch 2026-04-19.
        page = self._bundle.forensic.get_page(resolved_url, method=original_method)

        # Schritt 3b (Build 699, Vorgang f5956e6b): Ankerprobe.
        # Erst hier, weil sie den BLOB braucht — und nach dem Lookup, damit sie
        # BEIDE Verweisformen erfasst: '?pid=<id>' (oben aufgeloest) und
        # '?id=<topic>#p<id>' (Verweise innerhalb des Forums, die gar keine
        # Aufloesung ausloesen und deshalb bis Build 698 ungeprueft auf dem
        # ersten Chunk landeten).
        page, resolved_url, fragment_source = self._anker_seite_sichern(
            page, resolved_url, fragment, fragment_source, original_method
        )

        # Schritt 4: Envelope zusammenbauen
        if page is None:
            logger.debug("BlobHandler: NOT_IN_SCOPE für '%s'", resolved_url)
            return {
                "html":           None,
                "head":           None,
                "scrape_context": "unknown",
                "http_status":    0,
                "fetch_failed":   True,
                "in_scope":       False,
                "url_canonical":  resolved_url,
                "fragment":       fragment,
                "trace_elements": [],
                "fragment_source": fragment_source,
            }

        # <head>-Elemente aus BLOB extrahieren
        head_data = None
        if page.html:
            extracted = self._head_extractor.extract(page.html)

            # base_href: explizites <base href> aus BLOB hat Vorrang.
            # Fallback: Pfad aus pages.url_canonical (immer die echte Dokument-URL,
            # auch bei Alias-Auflösung). Protokoll und Domain werden abgeschnitten.
            # Beispiel: canonical_url = 'http://alice4n...onion/forum/beginner/'
            #           → base_href   = '/forum/beginner/'
            #           canonical_url = 'http://alice4n...onion/forum/viewtopic.php?id=42'
            #           → base_href   = '/forum/'
            if extracted.base_href is not None:
                base_href = extracted.base_href
            else:
                parsed_canonical = urllib.parse.urlparse(page.canonical_url)
                canon_path = parsed_canonical.path or "/"
                last_slash = canon_path.rfind("/")
                base_href = canon_path[:last_slash + 1] if last_slash >= 0 else "/"

            head_data = {
                "title":         extracted.title,
                "base_href":     base_href,
                "stylesheets":   extracted.stylesheets,
                "inline_styles": extracted.inline_styles,
            }

        # <body>-Inhalt aus BLOB extrahieren
        body_html = self._extract_body(page.html) if page.html else None

        # URL-Rewriting: vollständige Asset-URLs die in assets_<uid>.db
        # vorhanden sind, werden durch /_forensic/fileasset?url=... ersetzt.
        # Beleg: Projektgespräch 2026-05-31.
        if body_html:
            body_html = self._rewrite_asset_urls(body_html)

        logger.debug(
            "BlobHandler: '%s' → page_id=%d, context=%s, failed=%s",
            resolved_url, page.page_id, page.scrape_context, page.fetch_failed,
        )

        # Benutzer-Spuren für diese Seite ermitteln (Build 030-C).
        # Liefert DOM-Element-IDs aller Posts/PMs des Beschuldigten auf dieser
        # Seite — für die Minimap in toolbar.js (MinimapModule).
        # Gibt leere Liste zurück wenn keine Spuren vorhanden oder bei Fehler.
        trace_elements = self._bundle.forensic.get_trace_elements_for_page(
            page.page_id
        )

        return {
            "html":            body_html,
            "head":            head_data,
            "scrape_context":  page.scrape_context,
            "http_status":     page.http_status,
            "fetch_failed":    page.fetch_failed,
            "in_scope":        True,
            "url_canonical":   page.url,
            "fragment":        fragment,
            "trace_elements":  trace_elements,  # z.B. ["p1891354", "p1903927"]
            "fragment_source": fragment_source,  # Build 699, s. Kopf
        }

    def _resolve_aliases(
        self,
        url: str,
        url_path: str,
        params: dict,
        fragment: Optional[str],
    ) -> tuple[str, Optional[str], Optional[str]]:
        """
        Löst URL-Aliasse auf und gibt (aufgelöste_url, fragment,
        fragment_source) zurück.

        Auflösungsreihenfolge:
          1. ?pid=<post_id>    → Seite, die den Beitrag traegt (Build 699)
          2. ?notify=<notify>  → notify_aliases → post_id → wie 1.
          3. Direkt (keine Auflösung nötig)

        Build 699 (Vorgang f5956e6b): Stufe 1 und 2 bauten bis Build 698 die
        Adresse '<pfad>?id=<topic_id>'. Diese Adresse bezeichnet bei einem
        Thema mit mehreren erfassten Seiten IMMER die erste — der verlinkte
        Beitrag steht dort nur, wenn er zufaellig auf Seite 1 liegt. Jetzt
        wird die Seite gefragt, die den Beitrag traegt; der alte Weg bleibt
        als Rueckfall und wird dann als 'unaufgeloest' ausgewiesen, NICHT
        stillschweigend gegangen (Grundregel 1).

        Der dritte Rueckgabewert ist die Herkunft dieser Entscheidung; die
        Bedeutungen stehen im Dateikopf.
        """
        fdb = self._bundle.forensic

        # Fragment aus Alias-Mustern ableiten falls nicht gesetzt
        # z.B. ?pid=12345 → fragment = "p12345"
        if not fragment:
            pid_val = self._get_single_param(params, self._post_id_param)
            if pid_val:
                fragment = f"{self._fragment_post}{pid_val}"

        # Auflösung 1: ?pid=<post_id>
        pid_str = self._get_single_param(params, self._post_id_param)
        if pid_str:
            try:
                post_id = int(pid_str)
            except (ValueError, TypeError):
                post_id = None
            if post_id is not None:
                aufloesung = self._seite_des_beitrags(post_id)
                if aufloesung is not None:
                    resolved, quelle = aufloesung
                    logger.debug(
                        "pid=%d → '%s' (%s)", post_id, resolved, quelle,
                    )
                    return resolved, fragment, quelle

                # Rueckfall: Thema bekannt, Seite nicht belegbar.
                alias = fdb.resolve_post_alias(post_id)
                if alias:
                    resolved = f"{url_path}?id={alias.topic_id}"
                    logger.warning(
                        "pid=%d: keine erfasste Seite traegt den Beitrag — "
                        "Rueckfall auf die erste Seite von topic_id=%d ('%s'). "
                        "Der Anker '#p%d' wird dort ins Leere laufen.",
                        post_id, alias.topic_id, resolved, post_id,
                    )
                    return resolved, fragment, "unaufgeloest"

        # Auflösung 2: ?notify=<notify_id>
        notify_str = self._get_single_param(params, self._notify_param)
        if notify_str:
            try:
                notify_id = int(notify_str)
                notify_alias = fdb.resolve_notify_alias(notify_id)
                if notify_alias:
                    post_id  = notify_alias.post_id
                    fragment = f"{self._fragment_post}{post_id}"
                    aufloesung = self._seite_des_beitrags(post_id)
                    if aufloesung is not None:
                        resolved, quelle = aufloesung
                        logger.debug(
                            "notify=%d → post_id=%d → '%s' (%s)",
                            notify_id, post_id, resolved, quelle,
                        )
                        return resolved, fragment, quelle

                    post_alias = fdb.resolve_post_alias(post_id)
                    if post_alias:
                        resolved = f"{url_path}?id={post_alias.topic_id}"
                        logger.warning(
                            "notify=%d → post_id=%d: keine erfasste Seite "
                            "traegt den Beitrag — Rueckfall auf die erste "
                            "Seite von topic_id=%d ('%s').",
                            notify_id, post_id, post_alias.topic_id, resolved,
                        )
                        return resolved, fragment, "unaufgeloest"
            except (ValueError, TypeError):
                pass

        # Keine Auflösung — URL direkt verwenden
        return url, fragment, None

    def _seite_des_beitrags(self, post_id: int) -> Optional[tuple[str, str]]:
        """
        Fragt die Datenbankschicht nach der Seite, die den Beitrag traegt.

        Rueckgabe: (lookup_url, fragment_source) oder None.

        Eigene kleine Methode, weil dieselbe Frage an drei Stellen gestellt
        wird (pid, notify, Ankerprobe) und die Uebersetzung der internen
        Quellenbezeichnung in die des Envelopes ('blob' → 'nachgemessen')
        genau einmal geschrieben gehoert. Sie faengt zudem den Fall ab, dass
        die Datenbankschicht die Methode nicht kennt (aeltere ForensicDb in
        einem Test-Doppel): dann gilt der Beitrag als nicht aufloesbar — das
        alte Verhalten, aber nicht still.
        """
        fdb = self._bundle.forensic
        aufloeser = getattr(fdb, "resolve_post_page", None)
        if aufloeser is None:
            logger.warning(
                "ForensicDb ohne resolve_post_page() — Seitenbestimmung fuer "
                "post_id=%d nicht moeglich.", post_id,
            )
            return None
        treffer = aufloeser(post_id)
        if treffer is None:
            return None
        quelle = "nachgemessen" if treffer.quelle == "blob" else "gemessen"
        return treffer.url, quelle

    # ------------------------------------------------------------------
    # Ankerprobe (Build 699, Vorgang f5956e6b)
    # ------------------------------------------------------------------

    def _anker_seite_sichern(
        self,
        page,
        resolved_url: str,
        fragment: Optional[str],
        fragment_source: Optional[str],
        original_method: str,
    ):
        """
        Prueft, ob der gefundene BLOB den Beitragsanker '#p<post_id>' wirklich
        traegt — und holt andernfalls die Seite, die ihn traegt.

        Rueckgabe: (page, resolved_url, fragment_source).

        WARUM DIESE PROBE ZUSAETZLICH ZUR AUFLOESUNG NOETIG IST: Verweise
        INNERHALB des Forums haben die Form '?id=<topic>#p<post_id>' und
        loesen keinerlei Aufloesung aus — sie zeigen von sich aus auf den
        ersten Chunk des Themas. Der Anker gehoert aber zu einem Beitrag, der
        auf Chunk 2..n stehen kann. Ohne diese Probe bliebe genau diese
        Verweisform falsch, obwohl der pid-Weg richtiggestellt ist.

        WAS SIE NICHT TUT: Sie greift nur bei Themenseiten (viewtopic). Ein
        Anker '#p<n>' auf einer anderen Seite (z. B. einer Trefferliste) meint
        nicht denselben Beitragscontainer; ihn dorthin aufzuloesen wuerde die
        Ermittlerin von der angeforderten Seite wegfuehren.

        WAS BEI FEHLENDEM BLOB GILT: html IS NULL heisst 'Abruf fehlgeschlagen'
        (fetch_failed). Ein fehlender Inhalt belegt NICHT, dass der Beitrag
        woanders steht. Es wird deshalb nicht umgeleitet, sondern
        'unpruefbar' ausgewiesen.
        """
        post_id = self._post_id_aus_fragment(fragment)
        if post_id is None:
            # Kein Beitragsanker im Spiel — nichts zu belegen.
            return page, resolved_url, None
        if page is None:
            # NOT_IN_SCOPE: die Aussage der Aufloesung bleibt stehen.
            return page, resolved_url, fragment_source
        if not self._ist_themenseite(resolved_url) and \
           not self._ist_themenseite(page.url):
            return page, resolved_url, None

        from db.forensic_db import blob_enthaelt_anker

        if page.html is None:
            logger.warning(
                "Ankerprobe fuer '#p%d' auf '%s' nicht moeglich: BLOB fehlt "
                "(fetch_failed).", post_id, resolved_url,
            )
            return page, resolved_url, "unpruefbar"

        if blob_enthaelt_anker(page.html, post_id):
            # Der Regelfall. 'gemessen'/'nachgemessen' bleiben stehen, weil
            # sie mehr sagen als 'bestaetigt': sie nennen, WIE die Seite
            # gefunden wurde. Ohne Vorgeschichte gilt 'bestaetigt'.
            return page, resolved_url, fragment_source or "bestaetigt"

        # Der Anker fehlt — die bislang ausgelieferte Seite ist die falsche.
        logger.info(
            "Ankerprobe: '%s' traegt '#p%d' NICHT — Seite des Beitrags wird "
            "gesucht.", resolved_url, post_id,
        )
        aufloesung = self._seite_des_beitrags(post_id)
        if aufloesung is None:
            logger.warning(
                "Ankerprobe: keine erfasste Seite traegt '#p%d'. Ausgeliefert "
                "wird '%s'; der Sprung wird dort ins Leere laufen.",
                post_id, resolved_url,
            )
            return page, resolved_url, "unaufgeloest"

        neue_url, quelle = aufloesung
        if neue_url == resolved_url:
            # Die Datenbank benennt dieselbe Seite, in der der Anker gerade
            # nicht gefunden wurde. Das ist ein Widerspruch im Bestand und
            # wird als solcher gemeldet statt geraten.
            logger.warning(
                "Ankerprobe: Bestand nennt '%s' als Seite von '#p%d', der "
                "Anker steht dort aber nicht. Quelle: %s.",
                neue_url, post_id, quelle,
            )
            return page, resolved_url, "unaufgeloest"

        neue_page = self._bundle.forensic.get_page(
            neue_url, method=original_method
        )
        if neue_page is None:
            # Die richtige Seite ist unter dieser Methode nicht abrufbar
            # (z. B. POST-Sonderfall). Lieber die alte Seite mit ehrlichem
            # Vermerk als gar keine.
            logger.warning(
                "Ankerprobe: '%s' (Seite von '#p%d') ist unter method=%s "
                "nicht abrufbar — es bleibt bei '%s'.",
                neue_url, post_id, original_method, resolved_url,
            )
            return page, resolved_url, "unaufgeloest"

        logger.info(
            "Ankerprobe: '#p%d' steht auf '%s' (%s) — statt '%s' wird diese "
            "Seite ausgeliefert.", post_id, neue_url, quelle, resolved_url,
        )
        return neue_page, neue_url, quelle

    @staticmethod
    def _post_id_aus_fragment(fragment: Optional[str]) -> Optional[int]:
        """
        Liest die post_id aus einem Anker der Form 'p<ziffern>'.
        Alles andere (leer, 'top', 'p' ohne Ziffern) ergibt None.
        """
        if not fragment:
            return None
        treffer = _FRAGMENT_POST_RE.match(fragment)
        if not treffer:
            return None
        try:
            return int(treffer.group(1))
        except (ValueError, TypeError):     # pragma: no cover — Regex liefert Ziffern
            return None

    @staticmethod
    def _ist_themenseite(url: Optional[str]) -> bool:
        """
        True, wenn die Adresse eine Themenseite (viewtopic) bezeichnet.

        Absichtlich eine Teilzeichenkettenpruefung: die Adressen liegen hier
        teils mit, teils ohne Basis-URL und mit unterschiedlichen Pfaden
        ('/forum/viewtopic.php', '/forum/beginner/viewtopic.php') vor.
        """
        return bool(url) and "viewtopic.php" in url

    @staticmethod
    def _get_single_param(params: dict, key: str) -> Optional[str]:
        """
        Gibt den ersten Wert eines Query-Parameters zurück, oder None.
        parse_qs liefert Listen — wir nehmen immer den ersten Wert.
        """
        values = params.get(key)
        return values[0] if values else None

    def _rewrite_asset_urls(self, html_str: str) -> str:
        """
        Ersetzt vollständige Asset-URLs in HTML die in assets_<uid>.db
        vorhanden sind durch /_forensic/fileasset?url=<encoded>.

        Ablauf:
          1. Alle http(s)://... URLs aus src= und href= Attributen extrahieren.
          2. Einmal get_known_full_urls() gegen assets_<uid>.db — ein IN-Query.
          3. Nur Treffer ersetzen; alle anderen URLs bleiben original.

        Forensische Integrität: der gespeicherte BLOB bleibt unberührt;
        das Rewriting geschieht ausschließlich bei der Auslieferung.
        Beleg: Projektgespräch 2026-05-31.
        """
        import re
        # URLs aus src="..." und href="..." extrahieren (einfache Regex).
        # Wir suchen nach vollständigen http(s)-URLs in Attributwerten.
        _URL_PATTERN = re.compile(
            r'(?:src|href)=["\']((https?://[^"\'>\s]+))["\']',
            re.IGNORECASE,
        )
        candidates = set(m.group(1) for m in _URL_PATTERN.finditer(html_str))
        if not candidates:
            return html_str

        # Welche davon sind in der assets_<uid>.db bekannt?
        known = self._bundle.assets.get_known_full_urls(candidates)
        if not known:
            return html_str

        logger.debug(
            "_rewrite_asset_urls: %d/%d URLs ersetzt", len(known), len(candidates)
        )

        # Ersetzen: nur bekannte URLs werden umgeschrieben.
        # Längstes-zuerst um Teilstring-Kollisionen zu vermeiden.
        for url in sorted(known, key=len, reverse=True):
            proxy = "/_forensic/fileasset?url=" + urllib.parse.quote(url, safe="")
            html_str = html_str.replace(url, proxy)

        return html_str

    @staticmethod
    def _extract_body(html: bytes) -> str:
        """
        Extrahiert den Inhalt zwischen <body> und </body>.
        Gibt den gesamten HTML-String zurück wenn kein <body>-Tag gefunden.

        Verwendet einfache String-Suche statt HTML-Parser für Geschwindigkeit
        bei großen BLOBs. Die gespeicherten Forum-Seiten haben immer ein
        klar strukturiertes <body>-Tag.
        """
        html_str = html.decode("utf-8", errors="replace")

        # <body ...> suchen (mit möglichen Attributen)
        body_start_idx = html_str.lower().find("<body")
        if body_start_idx == -1:
            return html_str

        # Ende des öffnenden Tags suchen
        tag_end_idx = html_str.find(">", body_start_idx)
        if tag_end_idx == -1:
            return html_str

        content_start = tag_end_idx + 1

        # </body> suchen
        body_end_idx = html_str.lower().rfind("</body>")
        if body_end_idx == -1:
            return html_str[content_start:]

        return html_str[content_start:body_end_idx]
