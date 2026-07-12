# =============================================================================
# db/templates_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Zweck:
#   Kapselt alle Lesezugriffe auf templates.db (Berichtsvorlagen-Datenbank).
#
#   templates.db wird vom ConnectionManager READ-ONLY per ATTACH eingebunden
#   (Alias 'tdb'). Diese Klasse arbeitet ausschliesslich lesend. Schreibzugriff
#   erfolgt ausschliesslich ueber das Verwaltungswerkzeug der Chef-Ermittlerin
#   (Baustelle 7, /_forensic/admin/templates).
#
#   Bereitgestellte Methoden:
#     get_module(id)         -- Einzelnes Modul mit Body
#     list_modules(role, topic, search) -- Gefilterte Modulliste fuer Auswahl-Panel
#     get_query(query_id)    -- Einzelne Query-Definition aus placeholder_queries
#     list_queries(tags, search) -- Gefilterte Query-Bibliothek
#
#   Abhaengigkeiten:
#     sqlite3 -- ausschliesslich Stdlib
#
#   Die Klasse erwartet eine bereits geoeffnete sqlite3.Connection, in der
#   templates.db als 'tdb' angebunden ist. Ist 'tdb' nicht angebunden
#   (templates.db noch nicht vorhanden), liefern alle Methoden leere
#   Ergebnisse und protokollieren einen WARNING-Log — kein Absturz.
#
# Beleg: Bauplan B6 v0.3 §2.1, §3.3, Projektgespraech 2026-05-05
# Version: v0.6.089 · Build: 089 · 2026-05-05
# =============================================================================

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class ModuleRecord:
    """Ein Berichtsmodul aus templates.report_modules.
    Beleg: Bauplan B6 v0.3 §2.1
    """
    id:          int
    title:       str
    description: Optional[str]
    role:        str
    topic:       str
    body:        str
    sort_order:  int
    is_active:   bool


@dataclass
class QueryRecord:
    """Eine Query-Definition aus templates.placeholder_queries.
    Beleg: Bauplan B6 v0.3 §2.1, §3.4
    """
    id:          str    # query_id, z.B. 'user.username'
    title:       str
    description: str
    sql_query:   str
    tags:        Optional[str]   # CSV-String, z.B. 'identitaet,name'
    return_type: str
    is_active:   bool


@dataclass
class TemplateRecord:
    """Eine VOLLSTAENDIGE Berichtsvorlage aus templates.report_templates.

    Abgrenzung zu ModuleRecord (WICHTIG, haeufige Verwechslung):
      ModuleRecord   = EIN Textbaustein -> wird als EIN paragraph-Block
                       eingefuegt (module_panel.js:903).
      TemplateRecord = ein VOLLSTAENDIGES Berichtsgeruest -> wird als MEHRERE
                       typisierte Editor.js-Bloecke eingefuegt (header,
                       paragraph, table, ...). blocks_json haelt diese Bloecke
                       in ihrer Reihenfolge.

    blocks_json (JSON-Text) hat die Form:
      [ {"block_type": "header", "block_data": {"text": "...", "level": 2}},
        {"block_type": "table",  "block_data": {"withHeadings": false,
                                                "content": [["A","B"], ...]}} ]
    Die Bloecke duerfen Platzhalter in Template-Syntax enthalten
    ({{a:}}/{{m:}}/{{o:}}) — sie werden BEIM EINFUEGEN NICHT aufgeloest,
    sondern bleiben als Chips erhalten (Festlegung 2026-07-12, Variante A).

    Beleg: Bauplan Build 388 §4
    """
    id:          int
    template_key: str          # STABILE Kennung, z.B. 'vermerk.nicht_identifiziert'
    title:       str
    description: Optional[str]
    report_type: str           # 'interim' | 'final' | 'addendum'
    blocks_json: str
    sort_order:  int
    is_active:   bool


# =============================================================================
# Hauptklasse
# =============================================================================

class TemplatesDb:
    """
    Kapselt alle Lesezugriffe auf templates.db (Alias 'tdb').

    Ist tdb nicht angebunden, liefern alle Methoden leere Ergebnisse
    (kein Absturz). Dadurch kann der Webserver starten bevor
    setup_templates.py ausgefuehrt wurde.
    Beleg: Bauplan B6 v0.3 §2.1
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._available = self._check_available()

    def _check_available(self) -> bool:
        """
        Prueft ob tdb angebunden und die Kerntabellen vorhanden sind.
        Wird einmalig beim Init aufgerufen.
        """
        try:
            self._con.execute(
                "SELECT 1 FROM tdb.placeholder_queries LIMIT 1"
            )
            logger.debug("TemplatesDb: tdb verfuegbar und initialisiert.")
            return True
        except sqlite3.OperationalError as exc:
            logger.warning(
                "TemplatesDb: tdb nicht verfuegbar ('%s'). "
                "Alle Methoden liefern leere Ergebnisse. "
                "setup_templates.py ausfuehren um templates.db anzulegen.",
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # Modul-Zugriff
    # ------------------------------------------------------------------

    def get_module(self, module_id: int) -> Optional[ModuleRecord]:
        """
        Gibt ein einzelnes aktives Modul zurueck.

        Args:
            module_id: Primaerschluessel aus tdb.report_modules.

        Returns:
            ModuleRecord oder None wenn nicht vorhanden/inaktiv.
        """
        if not self._available:
            return None
        try:
            row = self._con.execute(
                "SELECT id, title, description, role, topic, body, "
                "       sort_order, is_active "
                "FROM tdb.report_modules "
                "WHERE id = ? AND is_active = 1",
                (module_id,),
            ).fetchone()
            return self._row_to_module(row) if row else None
        except sqlite3.OperationalError as exc:
            logger.warning("TemplatesDb.get_module fehlgeschlagen: %s", exc)
            return None

    def get_module_by_key(self, module_key: str) -> Optional[ModuleRecord]:
        """Gibt ein aktives Modul ueber die STABILE Kennung module_key zurueck.

        Build 341: module_key ist reorganisationssicher (anders als die
        AUTOINCREMENT-id). Defensiv: fehlt die Spalte module_key noch
        (templates.db nicht migriert), wird None zurueckgegeben (OperationalError
        abgefangen) — der Aufrufer behandelt 'Baustein fehlt' ohnehin, so bleibt
        der Code vor und nach der Migration lauffaehig.
        """
        if not self._available or not module_key:
            return None
        try:
            row = self._con.execute(
                "SELECT id, title, description, role, topic, body, "
                "       sort_order, is_active "
                "FROM tdb.report_modules "
                "WHERE module_key = ? AND is_active = 1",
                (module_key,),
            ).fetchone()
            return self._row_to_module(row) if row else None
        except sqlite3.OperationalError as exc:
            logger.warning(
                "TemplatesDb.get_module_by_key(%r) fehlgeschlagen "
                "(module_key-Spalte evtl. noch nicht migriert): %s",
                module_key, exc,
            )
            return None

    def list_modules(
        self,
        role: Optional[str] = None,
        topic: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[ModuleRecord]:
        """
        Liefert gefilterte Modulliste fuer das Modul-Auswahl-Panel.

        Filter:
            role:   Filtert auf exakte role-Uebereinstimmung.
            topic:  Filtert auf exakte topic-Uebereinstimmung.
            search: Volltextsuche in title und description (LIKE, case-insensitiv).

        Nur aktive Module (is_active = 1) werden zurueckgegeben.
        Sortierung: sort_order ASC, id ASC.
        Beleg: Bauplan B6 v0.3 §4.4
        """
        if not self._available:
            return []
        try:
            sql = (
                "SELECT id, title, description, role, topic, body, "
                "       sort_order, is_active "
                "FROM tdb.report_modules "
                "WHERE is_active = 1"
            )
            params: list = []

            if role:
                sql += " AND role = ?"
                params.append(role)
            if topic:
                sql += " AND topic = ?"
                params.append(topic)
            if search:
                sql += " AND (title LIKE ? OR description LIKE ?)"
                like = f"%{search}%"
                params.extend([like, like])

            sql += " ORDER BY sort_order ASC, id ASC"

            rows = self._con.execute(sql, params).fetchall()
            return [self._row_to_module(r) for r in rows]
        except sqlite3.OperationalError as exc:
            logger.warning("TemplatesDb.list_modules fehlgeschlagen: %s", exc)
            return []

    def list_topics(self) -> list[str]:
        """
        Gibt alle vorhandenen topic-Werte aktiver Module zurueck.
        Wird vom Modul-Auswahl-Panel fuer den Topic-Filter benoetigt.
        Beleg: Bauplan B6 v0.3 §2.1 (topic-Hinweis)
        """
        if not self._available:
            return []
        try:
            rows = self._con.execute(
                "SELECT DISTINCT topic FROM tdb.report_modules "
                "WHERE is_active = 1 ORDER BY topic ASC"
            ).fetchall()
            return [str(r[0]) for r in rows]
        except sqlite3.OperationalError as exc:
            logger.warning("TemplatesDb.list_topics fehlgeschlagen: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Query-Bibliothek
    # ------------------------------------------------------------------

    def get_query(self, query_id: str) -> Optional[QueryRecord]:
        """
        Gibt eine einzelne Query-Definition zurueck.

        Args:
            query_id: Primaerschluessel aus tdb.placeholder_queries,
                      z.B. 'user.username'.

        Returns:
            QueryRecord oder None wenn nicht vorhanden/inaktiv.
        """
        if not self._available:
            return None
        try:
            row = self._con.execute(
                "SELECT id, title, description, sql_query, tags, "
                "       return_type, is_active "
                "FROM tdb.placeholder_queries "
                "WHERE id = ? AND is_active = 1",
                (query_id,),
            ).fetchone()
            return self._row_to_query(row) if row else None
        except sqlite3.OperationalError as exc:
            logger.warning(
                "TemplatesDb.get_query('%s') fehlgeschlagen: %s", query_id, exc
            )
            return None

    def list_queries(
        self,
        tags: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[QueryRecord]:
        """
        Liefert die durchsuchbare Query-Bibliothek.

        Filter:
            tags:   Kommagetrennte Tag-Liste. Nur Queries zurueckgeben,
                    deren tags-Feld mindestens einen der angegebenen Tags
                    enthaelt (LIKE-Suche je Tag).
            search: Volltextsuche in title und description (LIKE).

        Nur aktive Queries (is_active = 1) werden zurueckgegeben.
        Sortierung: id ASC.
        Beleg: Bauplan B6 v0.3 §3.3
        """
        if not self._available:
            return []
        try:
            sql = (
                "SELECT id, title, description, sql_query, tags, "
                "       return_type, is_active "
                "FROM tdb.placeholder_queries "
                "WHERE is_active = 1"
            )
            params: list = []

            if tags:
                # Jeder angegebene Tag muss in tags-CSV enthalten sein (LIKE)
                for tag in tags.split(","):
                    tag = tag.strip()
                    if tag:
                        sql += " AND tags LIKE ?"
                        params.append(f"%{tag}%")

            if search:
                sql += " AND (title LIKE ? OR description LIKE ?)"
                like = f"%{search}%"
                params.extend([like, like])

            sql += " ORDER BY id ASC"

            rows = self._con.execute(sql, params).fetchall()
            return [self._row_to_query(r) for r in rows]
        except sqlite3.OperationalError as exc:
            logger.warning("TemplatesDb.list_queries fehlgeschlagen: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Vorlagen-Zugriff (VOLLSTAENDIGE Berichtsgeruueste, Build 388)
    # ------------------------------------------------------------------
    # GRUNDREGEL 1: Fehlt die Tabelle report_templates (Seed-Skript noch nicht
    # gelaufen), liefern diese Methoden eine LEERE Liste — und protokollieren
    # das als WARNUNG. Der Reiter 'Vorlagen' zeigt dann eine Leermeldung an,
    # statt dem Ermittler eine funktionierende, aber leere Bibliothek
    # vorzutaeuschen.
    # ------------------------------------------------------------------

    def list_templates(self, search: Optional[str] = None) -> list[TemplateRecord]:
        """Alle aktiven Vorlagen (ohne blocks_json — das kann gross sein)."""
        if not self._available:
            return []
        try:
            sql = (
                "SELECT id, template_key, title, description, report_type, "
                "       '' AS blocks_json, sort_order, is_active "
                "FROM tdb.report_templates WHERE is_active = 1"
            )
            params: list = []
            if search:
                sql += " AND (title LIKE ? OR description LIKE ?)"
                like = f"%{search}%"
                params.extend([like, like])
            sql += " ORDER BY sort_order ASC, id ASC"

            rows = self._con.execute(sql, params).fetchall()
            return [self._row_to_template(r) for r in rows]
        except sqlite3.OperationalError as exc:
            logger.warning(
                "TemplatesDb.list_templates fehlgeschlagen ('%s'). Vermutlich "
                "ist das Seed-Skript management/migrate_templates_full_templates.py "
                "noch nicht gelaufen.", exc,
            )
            return []

    def get_template_by_key(self, template_key: str) -> Optional[TemplateRecord]:
        """Eine Vorlage MIT blocks_json ueber ihre stabile Kennung."""
        if not self._available or not template_key:
            return None
        try:
            row = self._con.execute(
                "SELECT id, template_key, title, description, report_type, "
                "       blocks_json, sort_order, is_active "
                "FROM tdb.report_templates "
                "WHERE template_key = ? AND is_active = 1",
                (template_key,),
            ).fetchone()
            return self._row_to_template(row) if row else None
        except sqlite3.OperationalError as exc:
            logger.warning(
                "TemplatesDb.get_template_by_key('%s') fehlgeschlagen: %s",
                template_key, exc,
            )
            return None

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_template(row: sqlite3.Row) -> TemplateRecord:
        return TemplateRecord(
            id=int(row["id"]),
            template_key=str(row["template_key"]),
            title=str(row["title"]),
            description=row["description"],
            report_type=str(row["report_type"]),
            blocks_json=str(row["blocks_json"] or ""),
            sort_order=int(row["sort_order"]),
            is_active=bool(row["is_active"]),
        )

    @staticmethod
    def _row_to_module(row: sqlite3.Row) -> ModuleRecord:
        return ModuleRecord(
            id=int(row["id"]),
            title=str(row["title"]),
            description=row["description"],
            role=str(row["role"]),
            topic=str(row["topic"]),
            body=str(row["body"]),
            sort_order=int(row["sort_order"]),
            is_active=bool(row["is_active"]),
        )

    @staticmethod
    def _row_to_query(row: sqlite3.Row) -> QueryRecord:
        return QueryRecord(
            id=str(row["id"]),
            title=str(row["title"]),
            description=str(row["description"]),
            sql_query=str(row["sql_query"]),
            tags=row["tags"],
            return_type=str(row["return_type"]),
            is_active=bool(row["is_active"]),
        )
