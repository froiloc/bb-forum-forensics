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


def _progress_value(ann_count: int, last_viewed) -> int:
    """
    Einheitliche Fortschritts-Formel (Platzhalter — OP-KN-1, Baustelle 5).

    Eine Stelle für search_pages() UND resolve_posts_progress(), damit beide
    nicht auseinanderlaufen. Wird der echte Fortschritt (Baustelle 5)
    implementiert, ist nur diese Funktion zu ändern.

      100 — annotiert UND betrachtet
       50 — nur betrachtet
        0 — sonst
    """
    if ann_count > 0 and last_viewed:
        return 100
    if last_viewed:
        return 50
    return 0


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

    def get_page_by_url(self, url: str) -> Optional[dict]:
        """
        Gibt Page-Metadaten + BLOB als Dict zurueck.
        Wrapper fuer get_page() — wird von _write_cross_annotation() genutzt
        um den Page-BLOB in die Transportdatei zu kopieren.

        Build 182 (Bug 2.78). Build 185 (Bug 3.10): lookup() existiert nicht,
        korrekte Methode ist get_page().
        Beleg: Webserver-Log 2026-05-12 — 'ForensicDb has no attribute lookup'.
        """
        record = self.get_page(url)
        if record is None:
            return None
        return {
            "html_blob":      record.html,
            "http_status":    record.http_status,
            "scrape_context": record.scrape_context,
            "fetched_at":     record.fetched_at,
            "title":          None,
            "in_scope":       1,
        }

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

    # ------------------------------------------------------------------
    # Build 430 (B4 Welle 3): Inhaltszeit (Post-Zeitstempel) fuer den Zeitstrahl
    # ------------------------------------------------------------------

    def get_post_times(self, post_ids) -> "dict[int, int]":
        """
        Liefert die Inhaltszeit (Unix-Epoch, Sekunden, UTC) zu Forum-post_ids
        aus fdb.uid_posts (Spalten: post_id, posted_ts).

        BELEG (Build 528, KORREKTUR): forensic_uid.db.schema.sql — das
        vollstaendige DDL der forensic_<uid>.db, uebergeben am 2026-07-25,
        bestaetigt durch zwei Sondenlaeufe in DEV und PROD.

        WAS HIER BIS BUILD 527 STAND UND WARUM ES FALSCH WAR: Die Spalten waren
        als 'id' und 'posted' angegeben, mit tests/test_build388_vorlagen.py:356
        als Beleg. Diese Zeile ist eine TESTVORRICHTUNG, die die Tabelle SELBST
        mit genau diesen Spalten anlegt — ein zirkulaerer Beleg. In den echten
        Datenbanken heissen sie 'post_id' und 'posted_ts'. Die Abfrage schlug
        deshalb in PROD IMMER fehl; die defensive Behandlung unten hat den
        Fehlschlag abgefangen und ein leeres Mapping geliefert, so dass die
        Inhaltszeit des Zeitstrahls seit Build 430 NIE funktioniert hat, ohne
        dass es auffiel (Befund aus der Laufzeitmessung mc 2026-07-25).

        Rein lesend. DEFENSIV: existiert fdb.uid_posts in einer (aelteren)
        forensic_db nicht, wird ein LEERES Mapping geliefert und geloggt — der
        Zeitstrahl fuehrt die betroffenen Annotationen dann sichtbar in der Spur
        'ohne Inhaltszeit' (kein stiller Ausfall, Grundregel 1). Der Endpunkt
        bleibt dadurch in jedem Fall funktionsfaehig.

        Args:
            post_ids: iterable von post_ids (int).

        Returns:
            { post_id (int): posted (int, Sekunden) }
        """
        ids = sorted({int(p) for p in post_ids if p is not None})
        if not ids:
            return {}

        out: "dict[int, int]" = {}
        chunk_size = 500  # unter dem SQLite-Parameterlimit bleiben
        try:
            for start in range(0, len(ids), chunk_size):
                chunk = ids[start:start + chunk_size]
                placeholders = ",".join("?" * len(chunk))
                rows = self._con.execute(
                    f"SELECT post_id, posted_ts FROM fdb.uid_posts "
                    f"WHERE post_id IN ({placeholders})",
                    chunk,
                ).fetchall()
                for row in rows:
                    if row["posted_ts"] is not None:
                        out[int(row["post_id"])] = int(row["posted_ts"])
        except sqlite3.OperationalError as exc:
            logger.warning(
                "get_post_times: fdb.uid_posts nicht verfuegbar (%s) — leeres Mapping",
                exc,
            )
            return {}
        return out

    def get_pm_post_times(self, pm_post_ids) -> "dict[int, int]":
        """
        Build 432 (B4 Welle 3, E2): Liefert die Inhaltszeit (Unix-Epoch,
        Sekunden, UTC) zu PN-Post-IDs aus fdb.uid_pms_posts
        (Spalten: pm_post_id, posted_ts).

        Beleg Spaltenname: Entwicklerangabe 2026-07-15 (uid_pms_posts.posted_ts);
        Tabelle dokumentiert in forensic_api/userinfo_static.py:12.

        Verhalten und Defensivitaet identisch zu get_post_times(): fehlt die
        Tabelle/Spalte, wird {} geliefert und geloggt (GR1). Getrennte Methode,
        weil PN-IDs (pm_post_id) einen EIGENEN ID-Raum bilden — nicht mit
        uid_posts.id vermischen.

        Args:
            pm_post_ids: iterable von pm_post_ids (int).

        Returns:
            { pm_post_id (int): posted_ts (int, Sekunden) }
        """
        ids = sorted({int(p) for p in pm_post_ids if p is not None})
        if not ids:
            return {}

        out: "dict[int, int]" = {}
        chunk_size = 500
        try:
            for start in range(0, len(ids), chunk_size):
                chunk = ids[start:start + chunk_size]
                placeholders = ",".join("?" * len(chunk))
                rows = self._con.execute(
                    f"SELECT pm_post_id, posted_ts FROM fdb.uid_pms_posts "
                    f"WHERE pm_post_id IN ({placeholders})",
                    chunk,
                ).fetchall()
                for row in rows:
                    if row["posted_ts"] is not None:
                        out[int(row["pm_post_id"])] = int(row["posted_ts"])
        except sqlite3.OperationalError as exc:
            logger.warning(
                "get_pm_post_times: fdb.uid_pms_posts nicht verfuegbar (%s) — leeres Mapping",
                exc,
            )
            return {}
        return out

    # ------------------------------------------------------------------
    # Build 303: pid → Seite (pages.id) + Fortschritt
    # ------------------------------------------------------------------

    def resolve_posts_progress(self, post_ids: "list[int]") -> "dict[int, dict]":
        """
        Löst eine Liste von post_ids auf ihre gescrapte Seite und deren
        Fortschritt auf. Datenquelle: fdb.post_aliases.page (= pages.id,
        gemessen vom PostPageMeasurer per direkter Anker-Mitgliedschaft;
        Beleg: aiw_sqlite_prepper Build 100/101).

        Verwendet für die Fortschrittsrahmen auf
        search.php?action=show_user_posts (Treffer-Links viewtopic.php?pid=…),
        die NICHT die kanonische Seiten-URL tragen und daher nicht direkt
        gegen /_forensic/search gematcht werden können.

        Args:
            post_ids: Liste von post_ids (aus den pid-Links der Trefferseite).

        Returns:
            { post_id: { "topicId", "forumId", "pageId", "url",
                         "progressPercent", "resolved" } }
            resolved=False, wenn post_aliases.page NULL/0 ist (nicht
            aufgelöst — z. B. Folgeseite nicht gescrapt). Dann fehlen
            pageId/url/progressPercent. KEIN Raten (Grundregel 1).
        """
        result: dict[int, dict] = {}
        if not post_ids:
            return result

        # Defensive: page/page_resolved erst ab Prepper-Build 098 vorhanden.
        cols = {r["name"] for r in
                self._con.execute("PRAGMA fdb.table_info(post_aliases)")}
        has_page = "page" in cols and "page_resolved" in cols
        if not has_page:
            logger.warning(
                "resolve_posts_progress: post_aliases ohne page/page_resolved — "
                "erneuten Prepper-Lauf (Build 101+) durchführen. Alle "
                "Treffer gelten als nicht aufgelöst."
            )

        # post_aliases in Batches abfragen (SQLite-Parameterlimit).
        rows_by_pid: dict[int, sqlite3.Row] = {}
        page_ids: set[int] = set()
        CHUNK = 800
        page_sel = "page, page_resolved" if has_page else "NULL AS page, 0 AS page_resolved"
        for i in range(0, len(post_ids), CHUNK):
            batch = post_ids[i:i + CHUNK]
            ph = ",".join("?" * len(batch))
            try:
                cur = self._con.execute(
                    f"SELECT post_id, topic_id, forum_id, {page_sel} "
                    f"FROM fdb.post_aliases WHERE post_id IN ({ph})",
                    batch,
                )
            except sqlite3.OperationalError as exc:
                logger.error("resolve_posts_progress: Abfrage fehlgeschlagen: %s", exc)
                return result
            for row in cur:
                rows_by_pid[int(row["post_id"])] = row
                if has_page and row["page_resolved"] and row["page"]:
                    page_ids.add(int(row["page"]))

        # Fortschritt + URL je aufgelöster Seite (eine Sammelabfrage).
        page_info = self._progress_for_page_ids(list(page_ids)) if page_ids else {}

        for pid in post_ids:
            row = rows_by_pid.get(pid)
            if row is None:
                # post_id nicht in post_aliases (untypisch) → nicht aufgelöst.
                result[pid] = {"resolved": False}
                continue
            entry = {
                "topicId": int(row["topic_id"]),
                "forumId": int(row["forum_id"]),
                "resolved": False,
            }
            if has_page and row["page_resolved"] and row["page"]:
                pinfo = page_info.get(int(row["page"]))
                if pinfo is not None:
                    entry.update({
                        "pageId": int(row["page"]),
                        "url": pinfo["url"],
                        "progressPercent": pinfo["progressPercent"],
                        "resolved": True,
                    })
            result[pid] = entry

        return result

    def _progress_for_page_ids(self, page_ids: "list[int]") -> "dict[int, dict]":
        """
        Liefert pro pages.id { "url", "progressPercent" }.

        Spiegelt exakt die Fortschritts-Datenquelle von search_pages():
        Annotationen (annotations.page_url) und letzte Ansicht
        (page_visits.ts), gejoint über die basis-bereinigte url_canonical.
        Formel via _progress_value(). url = url_canonical ohne Basis-URL
        (identisch zum 'url'-Feld von search_pages, damit der Wert konsistent
        ist).
        """
        out: dict[int, dict] = {}
        if not page_ids:
            return out
        base_url = self.get_forum_base_url() or ""
        CHUNK = 800
        for i in range(0, len(page_ids), CHUNK):
            batch = page_ids[i:i + CHUNK]
            ph = ",".join("?" * len(batch))
            try:
                cur = self._con.execute(
                    f"""
                    SELECT
                        p.id                       AS page_id,
                        REPLACE(p.url_canonical, ?, '') AS url,
                        COUNT(DISTINCT a.id)       AS ann_count,
                        MAX(pv.ts)                 AS last_viewed
                    FROM fdb.pages p
                    LEFT JOIN annotations a
                        ON a.page_url = REPLACE(p.url_canonical, ?, '')
                    LEFT JOIN page_visits pv
                        ON pv.page_url = REPLACE(p.url_canonical, ?, '')
                    WHERE p.id IN ({ph})
                    GROUP BY p.id
                    """,
                    [base_url, base_url, base_url, *batch],
                )
            except sqlite3.OperationalError as exc:
                logger.error("_progress_for_page_ids: Abfrage fehlgeschlagen: %s", exc)
                return out
            for row in cur:
                out[int(row["page_id"])] = {
                    "url": str(row["url"] or ""),
                    "progressPercent": _progress_value(
                        int(row["ann_count"] or 0), row["last_viewed"]
                    ),
                }
        return out

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

    def get_user_profile(self) -> Optional[dict]:
        """
        Liest den Kern des Profils des untersuchten Nutzers aus fdb.uid_profile.

        Zweck (Beleg: Bauplan Userinfo-Verschoenerung v0.2, Pkt. 4; mc 2026-07-10):
          Der Kopf des Userinfo-Tabs soll den ECHTEN Benutzernamen
          (users.username) und die Originalgruppe anzeigen — nicht den
          Platzhalter 'uid_<id>'. uid_profile.username ist die autoritative,
          direkt aus users.username uebernommene Quelle (NOT NULL). Die
          Gruppen-Anzeige nutzt group_details_json ({g_id, g_title,
          g_user_title}); das JSON wird bewusst NICHT hier geparst, sondern
          roh zurueckgegeben — Praesentationslogik gehoert in den Renderer,
          diese Klasse bleibt reiner Lesezugriff.

          uid_profile enthaelt genau eine Zeile (id = user_id des untersuchten
          Nutzers). Beleg: _DDL_UID_PROFILE, phase_b_exporter.py:263 ff.

          Hinweis zur Gruppe 110: In der Prepper-Arbeits-DB wird die
          Gruppenzugehoerigkeit NICHT veraendert (nur in der Original-Forums-DB
          zum Scraping) — group_id steht hier also als Originalgruppe. Keine
          Sonderbehandlung noetig. Beleg: Projektgespraech 2026-07-10, Nachtrag 5.

        Returns:
            Dict {username, group_id, group_details_json} oder None, wenn
            uid_profile fehlt (z.B. Phase B noch nicht gelaufen) oder leer ist.
            Grundregel 1: eine fehlende Tabelle wird als None gemeldet, nicht
            still zu einem falschen Wert verbogen.
        """
        try:
            row = self._con.execute(
                "SELECT username, group_id, group_details_json "
                "FROM fdb.uid_profile LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError as exc:
            # uid_profile nicht vorhanden (alte/unvollstaendige DB) — kein
            # stiller Fallback auf einen erfundenen Namen, sondern None.
            logger.warning("get_user_profile(): uid_profile nicht lesbar: %s", exc)
            return None
        if row is None:
            logger.warning("get_user_profile(): uid_profile leer.")
            return None
        return {
            "username":            row["username"],
            "group_id":            row["group_id"],
            "group_details_json":  row["group_details_json"],
        }

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

        # Forenübersicht-Seiten (viewforum.php): Topic-Zeilen markieren.
        #
        # Auf viewforum.php-Seiten gibt es keine Post-IDs im DOM — die Zeilen
        # sind <tr>-Elemente mit Links der Form:
        #   <a href="viewtopic.php?id=66118&uid=2948078">Titel</a>
        #
        # Für jede topic_id aus scrape_targets, die auf dieser Forenseite
        # gelistet ist, liefern wir "topic:<id>" — ein Token-Format das der
        # Client (MinimapModule, TraceNavigationModule) per
        #   document.querySelector('a[href*="viewtopic.php?id=<id>&uid="]')
        #   .closest("tr")
        # auflöst.
        #
        # Erkennung: url_canonical der Seite enthält 'viewforum.php'.
        # Beleg: HTML-Analyse viewforum.php, Build 082.
        try:
            url_row = self._con.execute(
                "SELECT url_canonical FROM fdb.pages WHERE id = ? LIMIT 1",
                (page_id,),
            ).fetchone()
            if url_row and "viewforum.php" in str(url_row[0]):
                # forum_id dieser Seite aus URL extrahieren
                # URL-Form: .../viewforum.php?id=<forum_id>[&p=<page>]
                url_str = str(url_row[0])
                forum_id = None
                import re as _re
                m = _re.search(r"[?&]id=(\d+)", url_str)
                if m:
                    forum_id = int(m.group(1))

                if forum_id is not None:
                    # Alle topic_ids aus scrape_targets für dieses Forum
                    topic_rows = self._con.execute(
                        """
                        SELECT DISTINCT st.topic_id
                        FROM fdb.scrape_targets st
                        WHERE st.topic_id IS NOT NULL
                          AND st.forum_id = ?
                        ORDER BY st.topic_id
                        """,
                        (forum_id,),
                    ).fetchall()
                    for trow in topic_rows:
                        results.append(f"topic:{trow[0]}")
                else:
                    logger.debug(
                        "get_trace_elements_for_page: viewforum-Seite ohne "
                        "erkennbare forum_id (page_id=%d, url=%s)",
                        page_id, url_str,
                    )
        except Exception as exc:
            logger.warning(
                "get_trace_elements_for_page: viewforum-Topic-Abfrage "
                "fehlgeschlagen (page_id=%d): %s", page_id, exc
            )

        return results

    def search_pages(
        self,
        limit: int = 50,
        offset: int = 0,
        sort: str = "last_viewed_desc",
        q: str = "",
        scrape_context_filter: "list[str] | None" = None,
        fetch_failed_only: bool = False,
        has_annotations: "bool | None" = None,
        progress_filter: "str | None" = None,
        progress_threshold: int = 100,  # Build 194: Schwellenwert für 'open' (0–99)
        progress_direction: str = "lt",   # Build 195: 'lt'=< / 'gte'=>= Schwellenwert
        viewed_from: "int | None" = None,
        viewed_to: "int | None" = None,
        tags_filter: "list[str] | None" = None,
        categories_filter: "list[str] | None" = None,
        nur_zaehlen: bool = False,
    ) -> "list[dict] | int":
        """
        Liefert eine gefilterte, sortierte Liste von PageSummaryRecords für
        den Kontext-Navigator (/_forensic/search, Bauplan KN §4 + §7.3).

        Jeder Eintrag entspricht exakt dem PageSummaryRecord-Interface-Kontrakt
        (Bauplan KN §4), wie ihn toolbar.js erwartet. Felder:
          url, title, scrapeContext, fetchFailed, progressPercent,
          traceCountTotal, annotationsTotal, tagList,
          lastViewedAt, firstViewedAt

        Architektur-Entscheidungen (Beleg: Bauplan KN §9, Build 070):
          - Basisabfrage gegen fdb.pages (ATTACH-DB) — enthält alle Seiten
            dieses Benutzers.
          - title: Direkt aus fdb.pages.title (Build 071 — Spalte pages.title
            verfügbar seit aiw_sqlite_prepper Build 010). Kein BLOB-Parsing
            mehr nötig. Beleg: forensic_2948078_db.sql — pages.title TEXT.
          - annotationsTotal + tagList: LEFT JOIN auf evidence_db.annotations
            (selbe Verbindung, keine ATTACH nötig).
          - lastViewedAt / firstViewedAt: MAX/MIN aus evidence_db.page_visits.
          - traceCountTotal: Anzahl der Spuren AUF DIESER SEITE, ermittelt
            über get_trace_elements_for_page() — dieselbe Vorschrift, aus der
            Minimap und Spurennavigation ihre Marken beziehen (Build 678,
            Vorgang 1157e5f3). Gerechnet wird nur für die gelieferten Zeilen.
            -1 bedeutet 'nicht ermittelbar' und ist von 0 zu unterscheiden.
            BIS BUILD 677 stand hier eine Näherung über eine Verbindung zu
            fdb.scrape_targets, die auf Gruppennamen statt auf url_type-Werte
            prüfte und deshalb IMMER 0 lieferte.
          - progressPercent: 100 wenn annotationsTotal > 0 AND lastViewedAt
            IS NOT NULL, sonst 50 wenn nur lastViewedAt gesetzt, sonst 0.
            (Platzhalter — echte Fortschrittsberechnung via page_progress-
            Hilfstabelle folgt in Baustelle 5, OP-KN-1.)
          - filter: q, scrape_context, fetch_failed, has_annotations,
            progress, viewed_from/to — serverseitig via SQL.
          - q durchsucht URL UND TITEL (Build 676, Vorgang d76c412d).

        nur_zaehlen (Build 676, Vorgang 36dcdfd8):
            True liefert statt der Liste die ANZAHL der Treffer VOR der
            Begrenzung durch limit/offset — als int. Rückgabe -1 bedeutet
            'nicht ermittelbar' und ist ausdrücklich von 0 zu unterscheiden:
            0 heißt 'keine Treffer', -1 heißt 'die Zählung ist gescheitert'.
            Ein Aufrufer, der beides gleich behandelt, meldet eine leere
            Ergebnismenge, wo er 'unbekannt' melden müsste.
          - tags_filter und categories_filter — werden gegen annotations-
            Tabelle geprüft (subquery).
          - sort: last_viewed_desc (default), last_viewed_asc,
            url_asc, url_desc, progress_desc, progress_asc,
            annotations_desc, traces_desc.

        Args:
            limit:                  Max. Anzahl Ergebnisse (1–200, default 50).
            offset:                 Paginierungs-Offset.
            sort:                   Sortierfeld (s.o.).
            q:                      Freitext gegen URL (LIKE).
            scrape_context_filter:  Liste erlaubter scrape_context-Werte.
            fetch_failed_only:      Nur Seiten mit http_status != 200.
            has_annotations:        True = nur mit, False = nur ohne Anns.
            progress_filter:        'open' | 'closed' | None.
            progress_threshold:     0–99 — Schwellenwert (Build 194).
            progress_direction:     'lt' = progress < threshold (Standard),
                                    'gte' = progress >= threshold (Build 195).
            viewed_from:            Unix-ms — nur Seiten ab diesem Zeitpunkt.
            viewed_to:              Unix-ms — nur Seiten bis zu diesem Zeitpunkt.
            tags_filter:            Nur Seiten mit mind. einem dieser Tags.
            categories_filter:      Nur Seiten mit mind. einer dieser Kategorien.

        Returns:
            Liste von dicts (PageSummaryRecord-kompatibel), bereits sortiert.
        """
        limit  = max(1, min(200, int(limit)))
        offset = max(0, int(offset))

        # ------------------------------------------------------------------
        # Basisabfrage: alle Seiten aus fdb.pages, LEFT JOINs auf evidence_db
        # ------------------------------------------------------------------
        # evidence_db ist die Haupt-DB (kein ATTACH-Alias nötig).
        # fdb.pages ist per ATTACH als 'fdb' verfügbar.
        #
        # page_visits.ts ist in Sekunden (INTEGER). Für lastViewedAt/firstViewedAt
        # liefern wir Millisekunden (× 1000) an das Frontend.
        sql = """
            SELECT
                p.id              AS page_id,
                p.url_canonical   AS url_canonical,
                p.title           AS title,
                p.http_status     AS http_status,
                p.scrape_context  AS scrape_context,
                COUNT(DISTINCT a.id)        AS ann_count,
                GROUP_CONCAT(DISTINCT a.tags_json) AS tags_concat,
                MAX(pv.ts) * 1000           AS last_viewed_ms,
                MIN(pv.ts) * 1000           AS first_viewed_ms
            FROM fdb.pages p
            LEFT JOIN annotations a
                ON a.page_url = REPLACE(p.url_canonical, :base_url, '')
            LEFT JOIN page_visits pv
                ON pv.page_url = REPLACE(p.url_canonical, :base_url, '')
        """
        # ---------------------------------------------------------------------
        # BUILD 678 (Vorgang 1157e5f3): DIE SPURENZAEHLUNG IST AUS DIESER
        # ABFRAGE ENTFERNT - sie war falsch UND teuer.
        #
        # HIER STAND EINE VERBINDUNG ZU fdb.scrape_targets mit dieser
        # Bedingung:
        #     (st.url_type = 'topic'   AND st.topic_id     IS NOT NULL)
        #  OR (st.url_type = 'pm'      AND st.pm_topic_id  IS NOT NULL)
        #  OR (st.url_type = 'profile' AND st.actor_user_id IS NOT NULL)
        #  OR (st.url_type = 'forum')
        #
        # DER FEHLER: 'topic', 'pm' und 'forum' sind GRUPPENNAMEN der
        # Spurennavigation, KEINE Werte von scrape_targets.url_type. Dort
        # stehen 'viewtopic', 'viewforum', 'pmsnew_topic', 'pmsnew_post',
        # 'pms_partner', 'profile', 'other_profile', 'wholikes' und so fort -
        # nachzulesen in der TYPE_MAP von get_trace_sequence(), die am realen
        # Bestand belegt ist. Von den vier Zweigen konnte also nur einer je
        # zutreffen: 'profile'. Fuer jede Themen-, Forums- und PN-Seite kam
        # zwangslaeufig 0 heraus - genau der gemeldete Befund.
        #
        # DAZU KAM DER PREIS: die Bedingung verglich per LIKE OHNE ANKER jede
        # Seite mit jedem Erfassungsziel. Bei 6.500 Seiten und 19.000 Zielen
        # sind das ueber 120 Millionen Zeichenkettenvergleiche - fuer eine
        # Zahl, die immer 0 war.
        #
        # WARUM NICHT EINFACH DIE url_type-WERTE BERICHTIGEN: weil dann eine
        # ZWEITE Vorschrift entstuende, was eine Spur auf einer Seite ist.
        # Die erste steht in get_trace_elements_for_page() und wird vom
        # Werkzeug bereits benutzt - sie liefert die Marken, die Minimap und
        # Spurennavigation anzeigen. Zwei Vorschriften waeren binnen weniger
        # Builds auseinandergelaufen, und dann haette die Uebersicht eine
        # andere Zahl gezeigt als die Seite selbst. Gezaehlt wird deshalb ab
        # jetzt mit derselben Funktion - siehe weiter unten.
        # ---------------------------------------------------------------------
        # ---------------------------------------------------------------------
        # BUILD 677: Filterbedingungen werden GESAMMELT, nicht angehaengt.
        #
        # Grund: die Zaehlung (nur_zaehlen) braucht dieselben Bedingungen, aber
        # NICHT dieselben Verbindungen (JOINs). Solange die Bedingungen direkt
        # an die grosse Abfrage gehaengt wurden, liess sich das eine nicht ohne
        # das andere haben - und die Zaehlung schleppte eine Verbindung mit,
        # die sie nie braucht und die eine Minute kostet. Naeheres bei
        # 'zaehl_sql' weiter unten.
        # ---------------------------------------------------------------------
        where_teile: list[str] = []
        having_teile: list[str] = []

        params: dict = {
            "base_url": self.get_forum_base_url() or "",
            "limit":    limit,
            "offset":   offset,
        }

        # Freitextfilter — URL UND TITEL (Build 676, Vorgang d76c412d)
        #
        # BIS BUILD 675 wurde ausschliesslich die URL durchsucht. Das fiel
        # nicht auf, solange das Kontext-Dropdown gar nicht fragte und
        # stattdessen im Browser filterte - und der oertliche Filter sieht
        # URL UND Titel an (toolbar.js, _renderList). Sobald die Suche an den
        # Server geht, waere die Titelsuche also STILL verschwunden: wer
        # 'Annual badge' eingibt, faende nichts mehr, obwohl es die Seite
        # gibt.
        #
        # ZUR ENTSCHEIDUNG (Alex, 05.08.2026): gebunden und identifiziert wird
        # ueber die URL, weil sie eineindeutig ist - ein Themenbetreff kann
        # mehrfach vorkommen. Beim SUCHEN ist genau das aber kein Schaden,
        # sondern der Zweck: wer einen Betreff eingibt, will alle Seiten
        # sehen, die so heissen.
        if q:
            where_teile.append(
                "(REPLACE(p.url_canonical, :base_url, '') LIKE :q_like"
                " OR p.title LIKE :q_like)")
            params["q_like"] = f"%{q}%"

        # scrape_context-Filter
        if scrape_context_filter:
            placeholders = ", ".join(f":ctx_{i}" for i in range(len(scrape_context_filter)))
            where_teile.append(f"p.scrape_context IN ({placeholders})")
            for i, ctx in enumerate(scrape_context_filter):
                params[f"ctx_{i}"] = ctx

        # fetch_failed-Filter (http_status != 200 gilt als fehlgeschlagen)
        if fetch_failed_only:
            where_teile.append("(p.html IS NULL OR p.http_status != 200)")

        # Betrachtungszeitraum (viewed_from / viewed_to in Unix-ms)
        if viewed_from is not None:
            where_teile.append("MAX(pv.ts) * 1000 >= :viewed_from")
            params["viewed_from"] = viewed_from
        if viewed_to is not None:
            where_teile.append("MAX(pv.ts) * 1000 <= :viewed_to")
            params["viewed_to"] = viewed_to

        # HAVING-Filter (nach Aggregation)
        if has_annotations is True:
            having_teile.append("ann_count > 0")
        elif has_annotations is False:
            having_teile.append("ann_count = 0")

        # Bedingungen zusammensetzen - fuer die grosse Abfrage.
        bedingungen = " WHERE " + " AND ".join(["1=1"] + where_teile)
        gruppierung = " GROUP BY p.id"
        nachbedingung = (" HAVING " + " AND ".join(having_teile)
                         if having_teile else "")
        sql += bedingungen + gruppierung + nachbedingung

        # Sortierung (Bauplan KN §8.2)
        sort_map = {
            "last_viewed_desc": "last_viewed_ms DESC NULLS LAST",
            "last_viewed_asc":  "last_viewed_ms ASC  NULLS LAST",
            "url_asc":          "url_canonical ASC",
            "url_desc":         "url_canonical DESC",
            "annotations_desc": "ann_count DESC",
        }
        # BUILD 678: 'traces_desc' steht NICHT mehr in dieser Zuordnung.
        #
        # Die Spurenzahl entsteht seit dieser Fassung nicht mehr in SQL,
        # sondern je Seite ueber get_trace_elements_for_page(). Danach in SQL
        # zu sortieren ist damit unmoeglich - und in Python zu sortieren waere
        # FALSCH, solange LIMIT vorher greift: sortiert wuerde dann nur die
        # ohnehin schon ausgewaehlte Seite.
        #
        # DAS IST KEIN VERLUST, den jemand bemerken wird: die Sortierung war
        # bisher wirkungslos, weil trace_count IMMER 0 war. Sie sortierte also
        # nach einer Konstanten. Wichtiger ist, was NICHT passiert: der
        # Endpunkt faellt fuer diesen Wert auf 'last_viewed_desc' zurueck und
        # SAGT DAS in der Antwort (Feld 'sortierung_ersetzt'), statt still
        # etwas anderes zu liefern als bestellt.
        #
        # Eine tragfaehige Sortierung nach Spuren braucht die Zahl fuer ALLE
        # Treffer, nicht nur fuer die gelieferten. Das ist ein eigener
        # Arbeitsschritt und gehoert nicht in diese Behebung.
        # ---------------------------------------------------------------------
        # BUILD 676 (Vorgang 36dcdfd8): die WAHRE Trefferzahl.
        #
        # Bis hierher hat der Endpunkt 'total' aus len(pages) gebildet - also
        # aus der Zahl der GELIEFERTEN Zeilen. Bei limit=200 stand dort 200,
        # und ob das die Trefferzahl war oder die erreichte Grenze, liess sich
        # nicht unterscheiden. In einem Werkzeug, dessen Zahlen in eine
        # Ermittlungsakte geraten, ist das keine Kleinigkeit: eine Grenze, die
        # sich als Trefferzahl ausgibt, ist eine falsche Angabe.
        #
        # Gezaehlt wird GENAU DIESELBE Abfrage, nur ohne ORDER BY, LIMIT und
        # OFFSET - deshalb steht die Zaehlung hier und nicht in einer eigenen
        # Funktion mit eigener Filterlogik. Zwei Abfragen mit zwei Wahrheiten
        # waeren binnen zweier Builds auseinandergelaufen.
        #
        # Die Umhuellung ist noetig, weil die Abfrage GROUP BY (und ggf.
        # HAVING) traegt: COUNT(*) darueber zaehlt Gruppen, nicht Zeilen.
        # ---------------------------------------------------------------------
        if nur_zaehlen:
            # -----------------------------------------------------------------
            # BUILD 677 - DIE ZAEHLUNG LAESST WEG, WAS SIE NICHT BRAUCHT.
            #
            # GEMESSEN am 05.08.2026 in der VM: die Warnleiste brauchte bei
            # einem grossen Fall (Administrator, >10.000 Beitraege, 800 MB)
            # rund eine Minute fuer die Zahl. Alex sah sie erst nach der
            # Rueckkehr aus einem anderen Fenster.
            #
            # DIE URSACHE liegt in der Verbindung zu fdb.scrape_targets. Sie
            # verknuepft JEDE Seite mit JEDEM Erfassungsziel ueber ein LIKE
            # ohne Anker: bei 6.500 Seiten und 19.000 Zielen sind das ueber
            # 120 Millionen Zeichenkettenvergleiche - fuer EINE Zahl.
            #
            # SIE WIRD FUER DIE ZAEHLUNG NICHT GEBRAUCHT. Der Beleg ist
            # nachlesbar und nicht bloss plausibel:
            #   * Ein LEFT JOIN entfernt keine Zeile der linken Seite.
            #   * Gruppiert wird nach p.id, gezaehlt werden also SEITEN.
            #   * scrape_targets kommt in KEINER Bedingung vor - weder in
            #     WHERE noch in HAVING. Es liefert allein 'trace_count', und
            #     das braucht nur die Liste, nicht die Zahl.
            # Dieselbe Ueberlegung gilt fuer annotations und page_visits: sie
            # werden nur dann verbunden, wenn ein Filter sie wirklich
            # anspricht.
            #
            # DASS BEIDE WEGE DASSELBE ERGEBEN, ist nicht nur argumentiert,
            # sondern gemessen: Testfall SG04 vergleicht die Zahl mit der
            # Laenge der Liste ueber mehrere Filterkombinationen, SG08 haelt
            # ausdruecklich fest, dass die Zaehlabfrage scrape_targets nicht
            # erwaehnt.
            # -----------------------------------------------------------------
            zaehl_von = ["fdb.pages p"]
            zaehl_auswahl = ["p.id"]

            # annotations nur, wenn ein HAVING sie anspricht.
            if having_teile:
                zaehl_von.append(
                    "LEFT JOIN annotations a "
                    "ON a.page_url = REPLACE(p.url_canonical, :base_url, '')")
                zaehl_auswahl.append("COUNT(DISTINCT a.id) AS ann_count")

            # page_visits nur, wenn der Betrachtungszeitraum gefiltert wird.
            if viewed_from is not None or viewed_to is not None:
                zaehl_von.append(
                    "LEFT JOIN page_visits pv "
                    "ON pv.page_url = REPLACE(p.url_canonical, :base_url, '')")

            zaehl_innen = ("SELECT " + ", ".join(zaehl_auswahl)
                           + " FROM " + " ".join(zaehl_von)
                           + bedingungen + gruppierung + nachbedingung)
            zaehl_sql = "SELECT COUNT(*) FROM (" + zaehl_innen + ")"
            try:
                row = self._con.execute(zaehl_sql, params).fetchone()
            except Exception as exc:
                logger.error("search_pages(nur_zaehlen) fehlgeschlagen: %s", exc)
                return -1        # -1 = unbekannt, NICHT 0. Siehe Aufrufer.
            return int(row[0]) if row else 0

        order_clause = sort_map.get(sort, sort_map["last_viewed_desc"])
        sql += f" ORDER BY {order_clause} LIMIT :limit OFFSET :offset"

        try:
            rows = self._con.execute(sql, params).fetchall()
        except Exception as exc:
            logger.error("search_pages() SQL fehlgeschlagen: %s", exc)
            return []

        # Basis-URL für URL-Normalisierung
        base_url = self.get_forum_base_url() or ""

        results = []
        for row in rows:
            # URL normalisieren (Onion-Präfix entfernen)
            url_raw      = str(row["url_canonical"] or "")
            url_norm     = url_raw.replace(base_url, "") if base_url else url_raw

            # fetch_failed: html IS NULL oder http_status nicht 200
            # html wird nicht mehr geladen — fetch_failed via http_status
            fetch_failed = int(row["http_status"] or 0) not in (200, 0)

            # Titel direkt aus pages.title (Build 071 — kein BLOB-Parsing mehr)
            title_raw = row["title"]
            title = str(title_raw).strip() if title_raw else None

            # Annotations-Zähler
            ann_count = int(row["ann_count"] or 0)

            # Tags aus GROUP_CONCAT der tags_json-Felder zusammenführen
            tag_set: set[str] = set()
            tags_concat = row["tags_concat"]
            if tags_concat:
                import json as _json
                for tags_json_str in str(tags_concat).split(","):
                    tags_json_str = tags_json_str.strip()
                    if not tags_json_str:
                        continue
                    try:
                        parsed = _json.loads(tags_json_str)
                        if isinstance(parsed, list):
                            tag_set.update(str(t) for t in parsed)
                    except Exception:
                        pass
            tag_list = sorted(tag_set)

            # Tag- und Kategorie-Filter (post-hoc, da GROUP_CONCAT in SQL schwierig)
            if tags_filter and not any(t in tag_set for t in tags_filter):
                continue
            if categories_filter:
                # Wird für Phase KN-7 vollständig implementiert — hier Platzhalter
                pass

            # Fortschritt — gemeinsame Formel (siehe _progress_value).
            last_viewed_ms  = row["last_viewed_ms"]
            first_viewed_ms = row["first_viewed_ms"]
            progress = _progress_value(ann_count, last_viewed_ms)

            # progress_filter (Build 194/195: Schwellenwert + Richtung)
            if progress_filter == "open":
                if progress_direction == "gte":
                    # >= Schwellenwert: Seiten die mindestens so weit sind
                    if progress < progress_threshold:
                        continue
                else:
                    # < Schwellenwert (Standard): noch nicht abgeschlossen
                    if progress >= progress_threshold:
                        continue
            if progress_filter == "closed" and progress < 100:
                continue

            # BUILD 678 (Vorgang 1157e5f3): DIESELBE Vorschrift wie die Seite
            # selbst. get_trace_elements_for_page() liefert die Marken, die
            # Minimap und Spurennavigation anzeigen; ihre Anzahl ist die
            # Spurenzahl der Seite. Damit kann die Uebersicht gar nicht mehr
            # etwas anderes behaupten als die Seite.
            #
            # GERECHNET WIRD NUR FUER DIE GELIEFERTEN ZEILEN - hoechstens so
            # viele, wie 'limit' zulaesst. Die alte Fassung rechnete fuer
            # ALLE Seiten und kam trotzdem auf 0.
            try:
                trace_count = len(
                    self.get_trace_elements_for_page(int(row["page_id"])))
            except Exception as exc:
                # Eine Seite, deren Spuren sich nicht ermitteln lassen, darf
                # die Uebersicht nicht sprengen. Sie wird mit -1 als
                # 'unbekannt' ausgewiesen - NICHT mit 0, denn das hiesse
                # 'keine Spuren' und waere eine Behauptung.
                logger.warning(
                    "search_pages: Spurenzahl fuer page_id=%s nicht "
                    "ermittelbar: %s", row["page_id"], exc)
                trace_count = -1

            results.append({
                "url":             url_norm,
                "title":           title,
                "scrapeContext":   str(row["scrape_context"] or "user"),
                "fetchFailed":     fetch_failed,
                "progressPercent": progress,
                "traceCountTotal": trace_count,
                "annotationsTotal": ann_count,
                "tagList":         tag_list,
                "lastViewedAt":    int(last_viewed_ms) if last_viewed_ms else None,
                "firstViewedAt":   int(first_viewed_ms) if first_viewed_ms else None,
            })

        return results

    def get_trace_sequence(self) -> "list[dict]":
        """
        Liefert die geordnete Spurensequenz aller Seiten mit Spuren des
        Beschuldigten für die seitenübergreifende Spur-Navigation (OP-KN-7).

        Reihenfolge: Gruppe (profile → pm → topic → other),
        innerhalb Gruppe: scrape_targets.id ASC (= Autoincrement =
        chronologische Erfassungsreihenfolge).

        Nur Seiten die in fdb.pages existieren (gescrapte Seiten mit BLOB)
        werden geliefert — Scrape-Targets ohne zugehörige Seite werden
        übersprungen.

        url_type-Mapping (Beleg: reale forensic_2948078.db, 2026-04-27):
          viewtopic        → Gruppe 'topic',   JOIN auf topic_id
          viewforum        → Gruppe 'other',   JOIN auf forum_id
          pmsnew_topic     → Gruppe 'pm',      JOIN auf pm_topic_id
          pmsnew_post      → Gruppe 'pm',      JOIN auf pm_topic_id
          pms_partner      → Gruppe 'pm',      JOIN auf actor_user_id (sid=)
          pms_overview     → Gruppe 'pm',      keine ID (fixe URL pmsnew.php)
          profile          → Gruppe 'profile', JOIN auf actor_user_id
          other_profile    → Gruppe 'profile', JOIN auf actor_user_id
          wholikes         → Gruppe 'other',   JOIN auf post_id
          notifications    → Gruppe 'other',   keine ID (fixe URL)
          notification_item→ Gruppe 'other',   keine ID (fixe URL)
          pgp_probe        → Gruppe 'other',   JOIN auf actor_user_id
          static           → übersprungen

        Returns:
            Liste von dicts: url, title, group, trace_id
        Beleg: OP-KN-7, Build 074 — Korrektur der url_type-Werte.
        """
        base_url = self.get_forum_base_url() or ""

        # url_type → (navigationsgruppe, id_spalte_in_scrape_targets, url_fragment_template)
        # id_spalte None = fixe URL ohne ID-Parameter (pms_overview, notifications)
        # url_fragment None = nur LIKE '%<url_type_keyword>%' Matching
        TYPE_MAP = {
            "viewtopic":        ("topic",   "topic_id",      "viewtopic.php?id="),
            "viewforum":        ("other",   "forum_id",      "viewforum.php?id="),
            "pmsnew_topic":     ("pm",      "pm_topic_id",   "pmsnew.php?mdl=topic&tid="),
            "pmsnew_post":      ("pm",      "pm_topic_id",   "pmsnew.php?mdl=topic&tid="),
            "pms_partner":      ("pm",      "actor_user_id", "pmsnew.php?mdl=list&sid="),
            "pms_overview":     ("pm",      None,            "pmsnew.php?mdl=list"),
            "profile":          ("profile", "actor_user_id", "profile.php?id="),
            "other_profile":    ("profile", "actor_user_id", "profile.php?id="),
            "wholikes":         ("other",   "post_id",       "wholikes.php?pid="),
            "notifications":    ("other",   None,            "notifications.php"),
            "notification_item":("other",   None,            "notifications.php"),
            "pgp_probe":        ("other",   "actor_user_id", "profile.php?id="),
            # static → nicht gelistet, wird unten übersprungen
        }

        GROUP_ORDER = {"profile": 0, "pm": 1, "topic": 2, "other": 3}

        try:
            rows = self._con.execute("""
                SELECT
                    st.id           AS trace_id,
                    st.url_type     AS url_type,
                    st.topic_id     AS topic_id,
                    st.forum_id     AS forum_id,
                    st.pm_topic_id  AS pm_topic_id,
                    st.post_id      AS post_id,
                    st.actor_user_id AS actor_user_id
                FROM fdb.scrape_targets st
                WHERE st.url_type != 'static'
                ORDER BY st.id ASC
            """).fetchall()
        except Exception as exc:
            logger.error("get_trace_sequence() Abfrage fehlgeschlagen: %s", exc)
            return []

        seen_urls: set[str] = set()
        raw_entries = []

        for row in rows:
            url_type = str(row["url_type"] or "")
            if url_type not in TYPE_MAP:
                logger.debug("get_trace_sequence: unbekannter url_type '%s' — übersprungen", url_type)
                continue

            group, id_col, url_fragment = TYPE_MAP[url_type]

            # ID-Wert bestimmen
            id_val = None
            if id_col:
                id_val = row[id_col]

            # URL in blob_lookup suchen
            try:
                if id_val is not None:
                    pattern = f"%{url_fragment}{id_val}%"
                    bl_row = self._con.execute(
                        "SELECT url FROM blob_lookup WHERE url LIKE ? LIMIT 1",
                        (pattern,),
                    ).fetchone()
                else:
                    # Fixe URL — exakter LIKE auf Fragment
                    pattern = f"%{url_fragment}%"
                    bl_row = self._con.execute(
                        "SELECT url FROM blob_lookup WHERE url LIKE ? LIMIT 1",
                        (pattern,),
                    ).fetchone()
            except Exception as exc:
                logger.debug("get_trace_sequence: blob_lookup für '%s' fehlgeschlagen: %s", url_type, exc)
                continue

            if not bl_row:
                continue

            url_norm = str(bl_row["url"] or "")
            if not url_norm or url_norm in seen_urls:
                continue
            seen_urls.add(url_norm)

            # Titel aus fdb.pages über blob_lookup.page_id
            try:
                t_row = self._con.execute(
                    "SELECT p.title FROM fdb.pages p "
                    "INNER JOIN blob_lookup bl ON bl.page_id = p.id "
                    "WHERE bl.url = ? LIMIT 1",
                    (url_norm,),
                ).fetchone()
                title = str(t_row["title"]).strip() if t_row and t_row["title"] else None
            except Exception:
                title = None

            raw_entries.append({
                "url":       url_norm,
                "title":     title,
                "group":     group,
                "trace_id":  int(row["trace_id"]),
                "_sort_key": GROUP_ORDER.get(group, 3),
            })

        # Stabile Sortierung: Gruppe zuerst, dann trace_id ASC
        raw_entries.sort(key=lambda e: (e["_sort_key"], e["trace_id"]))

        return [
            {"url": e["url"], "title": e["title"],
             "group": e["group"], "trace_id": e["trace_id"]}
            for e in raw_entries
        ]

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
