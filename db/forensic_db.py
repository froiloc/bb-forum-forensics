# =============================================================================
# db/forensic_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Kapselt alle Lesezugriffe auf die forensic_<uid>.db (ATTACH-Alias: fdb).
#   Stellt Methoden für BLOB-Lookup, Alias-Auflösungen und Integritätsprüfung
#   bereit. Schreibt niemals in fdb — READ-ONLY ist eine harte Invariante.
#
# BLOB-Lookup-View (temporär, angelegt beim Öffnen der Verbindung):
#   CREATE TEMP VIEW blob_lookup AS
#     SELECT ... FROM fdb.pages p
#     UNION ALL
#     SELECT ... FROM fdb.pages p JOIN fdb.page_aliases pa ON pa.page_id = p.id
#
#   Der View vereinheitlicht den Zugriff auf BLOBs: Die aufrufende Komponente
#   muss nicht unterscheiden, ob eine URL direkt in pages.url_canonical steht
#   oder über page_aliases aufgelöst werden muss.
#
# Alias-Auflösungen:
#   post_aliases:   post_id  → (topic_id, forum_id)
#   pm_aliases:     pm_post_id → pm_topic_id
#   notify_aliases: notify_id  → post_id
#
# Verbindungsmodell:
#   Diese Klasse erwartet eine bereits geöffnete sqlite3.Connection mit
#   korrekt angebundener fdb (ATTACH). Die Verbindung wird von
#   connection_manager.py verwaltet — forensic_db.py öffnet keine eigenen
#   Verbindungen.
#
# Forensische Relevanz:
#   Alle Methoden sind READ-ONLY. Ein versehentlicher Schreibversuch auf fdb
#   wird durch den URI mode=ro der Verbindung (in connection_manager.py)
#   auf Datenbankebene verhindert. Zusätzlich enthält keine Methode
#   hier INSERT/UPDATE/DELETE-Statements.
#
# Abhängigkeiten: sqlite3 — ausschließlich Stdlib
# Version: v0.1.0 · Build: 042 · 2026-04-19
# Änderungen Build 042:
#   - blob_lookup VIEW: method-Spalte aus fdb.pages einbezogen.
#   - get_page(): neuer optionaler Parameter method (Default 'GET').
#     Bei method='POST' wird der POST-BLOB der Seite geliefert
#     (Poll-Abstimmungsergebnis). Beleg: Projektgespräch 2026-04-19.
#   - PageRecord: neues Feld method.
#   - Änderungen Build 030-C (erhalten):
#     get_trace_elements_for_page() liefert DOM-Element-IDs.
# =============================================================================

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)

# SQL für den temporären BLOB-Lookup-View.
# Wird beim Initialisieren der Klasse einmalig ausgeführt.
# TEMP VIEW liegt in der Haupt-DB (evidence_db) — berührt fdb nicht.
def _make_blob_lookup_sql(forum_base_url: str = "") -> str:
    """
    Erzeugt das CREATE TEMP VIEW SQL für blob_lookup.

    url_raw in page_aliases kann vollständige Onion-URLs enthalten
    (z.B. 'http://alice4n...onion/forum/beginner/index.php').
    Wenn forum_base_url bekannt ist, wird er per REPLACE() entfernt,
    sodass der View nur den Pfad liefert ('/forum/beginner/index.php').

    pages.url_canonical wird ebenfalls bereinigt — es enthält ebenfalls
    die vollständige Onion-URL.

    Args:
        forum_base_url: Vollständige Basis-URL ohne abschließenden Slash,
                        z.B. 'http://alice4n...onion'. Leerstring = kein REPLACE.
    """
    if forum_base_url:
        # Einfaches Anführungszeichen escapen für SQL-String-Literal
        safe = forum_base_url.replace("'", "''")
        url_canonical_expr = f"REPLACE(p.url_canonical, '{safe}', '')"
        url_raw_expr       = f"REPLACE(pa.url_raw, '{safe}', '')"
    else:
        url_canonical_expr = "p.url_canonical"
        url_raw_expr       = "pa.url_raw"

    return f"""
CREATE TEMP VIEW blob_lookup AS
    SELECT
        p.id             AS page_id,
        {url_canonical_expr} AS url,
        p.url_canonical  AS canonical_url,
        p.html           AS html,
        p.fetched_at     AS fetched_at,
        p.http_status    AS http_status,
        p.scrape_context AS scrape_context,
        p.method         AS method
    FROM fdb.pages p
    UNION ALL
    SELECT
        p.id             AS page_id,
        {url_raw_expr}   AS url,
        p.url_canonical  AS canonical_url,
        p.html           AS html,
        p.fetched_at     AS fetched_at,
        p.http_status    AS http_status,
        p.scrape_context AS scrape_context,
        p.method         AS method
    FROM fdb.pages p
    JOIN fdb.page_aliases pa ON pa.page_id = p.id
"""


@dataclass
class PageRecord:
    """
    Ergebnisobjekt eines BLOB-Lookups.

    Felder:
        page_id        — Primärschlüssel in fdb.pages
        url            — URL unter der diese Seite gefunden wurde
                         (kann url_canonical oder url_raw aus page_aliases sein)
        canonical_url  — Immer pages.url_canonical — die echte URL des Dokuments,
                         unabhängig davon ob via Alias oder direkt gefunden.
                         Beispiel: url='/', canonical_url='http://alice4n...onion/forum/beginner/'
        html           — HTML-BLOB als bytes, oder None wenn Abruf fehlschlug
        fetched_at     — Unix-Timestamp des Abrufs durch Stage 2
        http_status    — HTTP-Statuscode des Abrufs (200=OK, 0=Verbindungsfehler)
        scrape_context — Session-Kontext: 'user', 'investigator', 'actor:<uid>'
        fetch_failed   — True wenn html IS NULL (Abruf fehlgeschlagen)
    """
    page_id:       int
    url:           str
    canonical_url: str
    html:          Optional[bytes]
    fetched_at:    int
    http_status:   int
    scrape_context: str
    method:        str = "GET"
    # HTTP-Methode mit der diese Seite gespeichert wurde ('GET' oder 'POST').
    # 'POST' = Poll-Abstimmungsergebnis. Beleg: Projektgespräch 2026-04-19.

    @property
    def fetch_failed(self) -> bool:
        """True wenn der Abruf in Stage 2 fehlgeschlagen ist (html IS NULL)."""
        return self.html is None


@dataclass(frozen=True)
class PostAliasRecord:
    """Ergebnis einer post_alias-Auflösung."""
    post_id:  int
    topic_id: int
    forum_id: int


@dataclass(frozen=True)
class PmAliasRecord:
    """Ergebnis einer pm_alias-Auflösung."""
    pm_post_id:  int
    pm_topic_id: int


@dataclass(frozen=True)
class NotifyAliasRecord:
    """Ergebnis einer notify_alias-Auflösung."""
    notify_id: int
    post_id:   int


class ForensicDb:
    """
    Kapselt alle Lesezugriffe auf fdb (forensic_<uid>.db).

    Verwendung:
        fdb = ForensicDb(con)          # con hat fdb per ATTACH angebunden
        page = fdb.get_page("/forum/viewtopic.php?id=42")
        if page:
            print(page.scrape_context)

    Die Instanz hält keine eigene Verbindung — sie arbeitet auf der
    übergebenen Verbindung von connection_manager.py.
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        """
        Initialisiert ForensicDb und legt den temporären BLOB-Lookup-View an.

        Args:
            con: Geöffnete sqlite3.Connection mit angebundener fdb.
                 Muss von connection_manager.py stammen.

        Raises:
            sqlite3.OperationalError: Wenn fdb nicht angebunden ist oder
                                      der View nicht angelegt werden kann.
        """
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._setup_view()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_view(self) -> None:
        """
        Legt den temporären BLOB-Lookup-View an.
        Bestehender View wird zuerst gedroppt, damit Schemaänderungen
        (z.B. neue Spalten) auch in laufenden Sessions wirksam werden.

        Liest forum_base_url aus forensic_meta um Onion-Präfixe aus
        url_canonical und url_raw zu entfernen.
        """
        try:
            # forum_base_url aus forensic_meta lesen (kann None sein)
            forum_base_url = self.get_forum_base_url() or ""
            view_sql = _make_blob_lookup_sql(forum_base_url)
            self._con.execute("DROP VIEW IF EXISTS blob_lookup")
            self._con.execute(view_sql)
            self._con.commit()
            logger.debug(
                "blob_lookup TEMP VIEW angelegt (forum_base_url='%s')",
                forum_base_url or "(leer)",
            )
        except sqlite3.OperationalError as exc:
            raise sqlite3.OperationalError(
                f"blob_lookup-View konnte nicht angelegt werden. "
                f"Ist fdb korrekt per ATTACH angebunden?\n"
                f"SQLite-Fehler: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # BLOB-Lookup
    # ------------------------------------------------------------------

    def get_page(self, url: str, method: str = "GET") -> Optional[PageRecord]:
        """
        Sucht eine Seite anhand ihrer URL im blob_lookup-View.

        Der View deckt sowohl direkte URL-Treffer (pages.url_canonical)
        als auch Alias-Treffer (page_aliases.url_raw) ab.

        Args:
            url:    Normalisierte Forum-URL (ohne Fragment-Anker).
            method: HTTP-Methode des Originalrequests ('GET' oder 'POST').
                    Default 'GET'. 'POST' liefert den Poll-Ergebnis-BLOB.
                    Beleg: Projektgespräch 2026-04-19.

        Returns:
            PageRecord wenn gefunden, None wenn die URL nicht im Scope liegt.
        """
        try:
            row = self._con.execute(
                "SELECT page_id, url, canonical_url, html, fetched_at, http_status, "
                "scrape_context, method "
                "FROM blob_lookup WHERE url = ? AND method = ? LIMIT 1",
                (url, method.upper()),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            logger.error("BLOB-Lookup fehlgeschlagen für '%s': %s", url, exc)
            return None

        if row is None:
            logger.debug("Seite nicht im Scope: '%s' (method=%s)", url, method)
            return None

        record = PageRecord(
            page_id=int(row["page_id"]),
            url=str(row["url"]),
            canonical_url=str(row["canonical_url"]),
            html=row["html"],   # bytes oder None
            fetched_at=int(row["fetched_at"]),
            http_status=int(row["http_status"]),
            scrape_context=str(row["scrape_context"]),
            method=str(row["method"]),
        )
        logger.debug(
            "Seite gefunden: '%s' [%s] → page_id=%d, context=%s, fetch_failed=%s",
            url, method, record.page_id, record.scrape_context, record.fetch_failed,
        )
        return record

    def get_page_by_id(self, page_id: int) -> Optional[PageRecord]:
        """
        Sucht eine Seite anhand ihrer page_id (direkt in fdb.pages).

        Args:
            page_id: Primärschlüssel in fdb.pages.

        Returns:
            PageRecord wenn gefunden, None sonst.
        """
        try:
            row = self._con.execute(
                "SELECT id AS page_id, url_canonical AS url, "
                "url_canonical AS canonical_url, html, "
                "fetched_at, http_status, scrape_context "
                "FROM fdb.pages WHERE id = ?",
                (page_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            logger.error("get_page_by_id fehlgeschlagen für id=%d: %s", page_id, exc)
            return None

        if row is None:
            return None

        return PageRecord(
            page_id=int(row["page_id"]),
            url=str(row["url"]),
            canonical_url=str(row["canonical_url"]),
            html=row["html"],
            fetched_at=int(row["fetched_at"]),
            http_status=int(row["http_status"]),
            scrape_context=str(row["scrape_context"]),
        )

    # ------------------------------------------------------------------
    # Alias-Auflösungen
    # ------------------------------------------------------------------

    def resolve_post_alias(self, post_id: int) -> Optional[PostAliasRecord]:
        """
        Löst eine post_id auf das zugehörige Topic auf.

        Verwendet für URLs der Form: ?pid=<post_id>#p<post_id>

        Args:
            post_id: ID des Posts aus fdb.post_aliases.

        Returns:
            PostAliasRecord mit topic_id und forum_id, oder None.
        """
        try:
            row = self._con.execute(
                "SELECT post_id, topic_id, forum_id "
                "FROM fdb.post_aliases WHERE post_id = ?",
                (post_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            logger.error("resolve_post_alias(%d) fehlgeschlagen: %s", post_id, exc)
            return None

        if row is None:
            return None

        return PostAliasRecord(
            post_id=int(row["post_id"]),
            topic_id=int(row["topic_id"]),
            forum_id=int(row["forum_id"]),
        )

    def resolve_pm_alias(self, pm_post_id: int) -> Optional[PmAliasRecord]:
        """
        Löst eine pm_post_id auf die zugehörige PN-Konversation auf.

        Args:
            pm_post_id: ID des PN-Posts aus fdb.pm_aliases.

        Returns:
            PmAliasRecord mit pm_topic_id, oder None.
        """
        try:
            row = self._con.execute(
                "SELECT pm_post_id, pm_topic_id "
                "FROM fdb.pm_aliases WHERE pm_post_id = ?",
                (pm_post_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            logger.error("resolve_pm_alias(%d) fehlgeschlagen: %s", pm_post_id, exc)
            return None

        if row is None:
            return None

        return PmAliasRecord(
            pm_post_id=int(row["pm_post_id"]),
            pm_topic_id=int(row["pm_topic_id"]),
        )

    def resolve_notify_alias(self, notify_id: int) -> Optional[NotifyAliasRecord]:
        """
        Löst eine notify_id auf den zugehörigen Post auf.

        Args:
            notify_id: Benachrichtigungs-ID aus fdb.notify_aliases.

        Returns:
            NotifyAliasRecord mit post_id, oder None.
        """
        try:
            row = self._con.execute(
                "SELECT notify_id, post_id "
                "FROM fdb.notify_aliases WHERE notify_id = ?",
                (notify_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            logger.error("resolve_notify_alias(%d) fehlgeschlagen: %s", notify_id, exc)
            return None

        if row is None:
            return None

        return NotifyAliasRecord(
            notify_id=int(row["notify_id"]),
            post_id=int(row["post_id"]),
        )

    # ------------------------------------------------------------------
    # Metadaten
    # ------------------------------------------------------------------

    def get_meta(self, key: str) -> Optional[str]:
        """
        Liest einen Wert aus fdb.forensic_meta.

        Args:
            key: Schlüssel, z.B. 'user_id', 'username', 'schema_version'.

        Returns:
            Wert als String, oder None wenn nicht gefunden.
        """
        try:
            row = self._con.execute(
                "SELECT value FROM fdb.forensic_meta WHERE key = ?",
                (key,),
            ).fetchone()
            return str(row["value"]) if row else None
        except sqlite3.OperationalError as exc:
            logger.error("get_meta('%s') fehlgeschlagen: %s", key, exc)
            return None

    def get_forum_base_url(self) -> Optional[str]:
        """
        Liest 'protocol' und 'domainname' aus fdb.forensic_meta und gibt die
        vollständige Basis-URL zurück, z.B. 'http://alice4n...onion'.

        Wird vom connection_manager genutzt, um AssetsDb und DefaultDb mit dem
        Onion-Präfix zu versorgen, der in asset_urls als URL-Präfix gespeichert ist.

        Returns:
            Basis-URL als String (ohne abschließenden Slash), z.B.
            'http://alice4n4kd5gga3xqggygi6r7q7l7bb2wg5lcykh22ilxomk2jmpcbyd.onion',
            oder None wenn 'protocol' oder 'domainname' nicht in forensic_meta
            eingetragen sind.
        """
        protocol = self.get_meta("protocol")
        domainname = self.get_meta("domainname")
        if not protocol or not domainname:
            logger.warning(
                "get_forum_base_url(): 'protocol' oder 'domainname' fehlt in "
                "forensic_meta — Asset-Lookup ohne URL-Präfix."
            )
            return None
        base_url = f"{protocol}://{domainname}"
        logger.debug("get_forum_base_url(): '%s'", base_url)
        return base_url

    def get_scrape_context(self, url: str) -> Optional[str]:
        """
        Gibt den scrape_context einer URL zurück, ohne den vollen BLOB zu laden.
        Effizienter als get_page() wenn nur der Kontext benötigt wird.

        Args:
            url: Normalisierte Forum-URL.

        Returns:
            scrape_context-String ('user', 'investigator', 'actor:<uid>'),
            oder None wenn nicht gefunden.
        """
        try:
            row = self._con.execute(
                "SELECT scrape_context FROM blob_lookup WHERE url = ? LIMIT 1",
                (url,),
            ).fetchone()
            return str(row["scrape_context"]) if row else None
        except sqlite3.OperationalError as exc:
            logger.error("get_scrape_context('%s') fehlgeschlagen: %s", url, exc)
            return None

    def get_trace_elements_for_page(self, page_id: int) -> list[str]:
        """
        Gibt die Liste der DOM-Element-IDs zurück, an denen der Beschuldigte
        auf dieser Seite Spuren hinterlassen hat.

        Verbindungskette:
          Forum-Posts:
            fdb.post_aliases.topic_id
              ← fdb.scrape_targets.post_id = fdb.post_aliases.post_id
            fdb.page_aliases.page_id = page_id
              ← fdb.page_aliases.url_raw enthält 'id=<topic_id>'
            Kurzweg: scrape_targets.topic_id = post_aliases.topic_id
                     AND post_aliases.post_id in page_aliases via topic

          Einfachster korrekter Weg ohne pages.topic_id (existiert nicht):
            post_aliases verknüpft post_id ↔ topic_id.
            page_aliases verknüpft url_raw ↔ page_id.
            Eine Seite mit page_id gehört zu einer topic_id wenn
            irgendein post auf dieser Seite in post_aliases auf dieselbe
            topic_id zeigt wie ein scrape_target.post_id.

            Konkret: alle post_ids aus post_aliases wo topic_id in der Menge
            der topic_ids liegt die über page_aliases → page_id erreichbar sind.

        Beleg: forensic_schema_db.sql — pages hat kein topic_id-Feld.
               Verbindung läuft ausschließlich über post_aliases/pm_aliases.

        Args:
            page_id: fdb.pages.id der aktuellen Seite.

        Returns:
            Sortierte Liste von Element-IDs, z.B. ['p1891354', 'p1903927'].
        """
        results: list[str] = []

        # Forum-Posts auf Topic-Seiten.
        #
        # Logik:
        #   1. Alle post_ids aus post_aliases ermitteln deren topic_id
        #      irgendein post auf dieser page_id hat.
        #      Eine page gehört zu topic_id T wenn mindestens ein post_alias
        #      mit topic_id=T über page_aliases auf diese page_id zeigt:
        #        page_aliases.page_id = page_id
        #        → page_aliases verknüpft url_raw mit page_id
        #        → aber url_raw enthält die topic-URL, nicht post-URL
        #      Einfacherer direkter Weg:
        #        scrape_targets.post_id → post_aliases.topic_id
        #        post_aliases.topic_id ist die topic_id der Seite
        #        page_id stammt aus blob_lookup der topic-URL
        #        → Die topic_id der Seite ermitteln wir über:
        #          SELECT topic_id FROM post_aliases
        #          WHERE post_id IN (
        #            SELECT post_id FROM scrape_targets WHERE post_id IS NOT NULL
        #          )
        #          AND topic_id IN (
        #            SELECT pa2.topic_id FROM post_aliases pa2
        #            JOIN page_aliases pga ON pga.url_raw LIKE '%id=' || pa2.topic_id || '%'
        #            WHERE pga.page_id = page_id
        #          )
        #
        #      Das ist zu komplex. Robustere Lösung: alle topic_ids dieser
        #      page_id über page_aliases + URL-Muster auslesen:
        try:
            rows = self._con.execute(
                """
                SELECT DISTINCT st.post_id
                FROM fdb.scrape_targets st
                JOIN fdb.post_aliases pa ON pa.post_id = st.post_id
                WHERE st.post_id IS NOT NULL
                  AND pa.topic_id IN (
                      SELECT CAST(
                          SUBSTR(pga.url_raw,
                                 INSTR(pga.url_raw, 'id=') + 3)
                          AS INTEGER)
                      FROM fdb.page_aliases pga
                      WHERE pga.page_id = ?
                        AND pga.url_raw LIKE '%id=%'
                      UNION
                      SELECT CAST(
                          SUBSTR(p2.url_canonical,
                                 INSTR(p2.url_canonical, 'id=') + 3)
                          AS INTEGER)
                      FROM fdb.pages p2
                      WHERE p2.id = ?
                        AND p2.url_canonical LIKE '%id=%'
                  )
                ORDER BY st.post_id
                """,
                (page_id, page_id),
            ).fetchall()
            for row in rows:
                results.append(f"p{row[0]}")
        except Exception as exc:
            logger.warning(
                "get_trace_elements_for_page: Forum-Post-Abfrage fehlgeschlagen "
                "(page_id=%d): %s", page_id, exc
            )

        # PM-Posts auf PN-Seiten.
        # pm_aliases verknüpft pm_post_id ↔ pm_topic_id.
        # Die pm_topic_id der Seite ermitteln wir analog über URL-Muster.
        try:
            rows = self._con.execute(
                """
                SELECT DISTINCT st.pm_post_id
                FROM fdb.scrape_targets st
                JOIN fdb.pm_aliases pma ON pma.pm_post_id = st.pm_post_id
                WHERE st.pm_post_id IS NOT NULL
                  AND pma.pm_topic_id IN (
                      SELECT CAST(
                          SUBSTR(pga.url_raw,
                                 INSTR(pga.url_raw, 'id=') + 3)
                          AS INTEGER)
                      FROM fdb.page_aliases pga
                      WHERE pga.page_id = ?
                        AND pga.url_raw LIKE '%id=%'
                      UNION
                      SELECT CAST(
                          SUBSTR(p2.url_canonical,
                                 INSTR(p2.url_canonical, 'id=') + 3)
                          AS INTEGER)
                      FROM fdb.pages p2
                      WHERE p2.id = ?
                        AND p2.url_canonical LIKE '%id=%'
                  )
                ORDER BY st.pm_post_id
                """,
                (page_id, page_id),
            ).fetchall()
            for row in rows:
                results.append(f"p{row[0]}")
        except Exception as exc:
            logger.warning(
                "get_trace_elements_for_page: PM-Post-Abfrage fehlgeschlagen "
                "(page_id=%d): %s", page_id, exc
            )

        return results

    def page_count(self) -> int:
        """
        Gibt die Anzahl der gespeicherten Seiten in fdb.pages zurück.
        Für Statusanzeigen und Tests.
        """
        try:
            row = self._con.execute("SELECT COUNT(*) FROM fdb.pages").fetchone()
            return int(row[0]) if row else 0
        except sqlite3.OperationalError:
            return 0

    def get_userinfo_blob(self) -> "str | None":
        """
        Liest den statischen HTML-BLOB für den Nutzerinfo-Tab aus
        fdb.static_pages WHERE key='userinfo'.

        Gibt den HTML-String zurück, oder None wenn die Tabelle nicht
        existiert oder kein Eintrag vorhanden ist.

        Beleg: phase_b_exporter.py _step7_html_blob — schreibt BLOB als
        UTF-8-kodiertes bytes-Objekt in static_pages.html.
        Beleg: Projektgespräch 2026-04-18.
        """
        try:
            row = self._con.execute(
                "SELECT html FROM fdb.static_pages WHERE key = 'userinfo'"
            ).fetchone()
            if row is None:
                return None
            blob = row[0]
            # BLOB wird als bytes gespeichert (phase_b_exporter Schritt 7)
            if isinstance(blob, (bytes, bytearray)):
                return blob.decode("utf-8")
            return str(blob)
        except sqlite3.OperationalError:
            # Tabelle existiert noch nicht (ältere forensic_db ohne Phase B)
            return None
