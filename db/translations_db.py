# =============================================================================
# db/translations_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 5: Datenbank-Interfaces
# =============================================================================
# Zweck:
#   Kapselt alle Lesezugriffe auf translations.db (KI-Uebersetzungen nicht
#   deutschsprachiger Beitraege ins Deutsche).
#
#   translations.db wird vom ConnectionManager READ-ONLY per ATTACH eingebunden
#   (Alias 'trdb'). Diese Klasse arbeitet AUSSCHLIESSLICH lesend — die DB wird
#   extern (lokales ollama, separater Prepper-Lauf) befuellt. Es findet KEIN
#   Schreibzugriff durch das Ermittlungswerkzeug statt.
#
#   Bereitgestellte Methoden:
#     list_translated_post_ids(topic_id) -- post_ids eines Topics mit fertiger
#                                            Uebersetzung (fuer Button-Injektion)
#     get_translation(post_id)           -- Einzelne fertige Uebersetzung
#
#   Abhaengigkeiten:
#     sqlite3 -- ausschliesslich Stdlib
#
#   Die Klasse erwartet eine bereits geoeffnete sqlite3.Connection, in der
#   translations.db als 'trdb' angebunden ist. Ist 'trdb' NICHT angebunden
#   (translations.db noch nicht vorhanden — die Uebersetzungen entstehen erst
#   ~2 Wochen nach Build 329), liefern alle Methoden leere Ergebnisse und
#   protokollieren einen WARNING-Log — kein Absturz (GR1: kein stiller Fehler,
#   aber auch kein Absturz). Exakt das Verhalten von TemplatesDb.
#
#   Reale Produktionstabelle (Projektgespraech 2026-07-07):
#     post_id PK, translated_text, model_used, created_at, updated_at,
#     source ('posts'|'pms', Default 'posts'), topic_id, forum_id.
#   Es gibt KEINE Spalte 'status' (anders als die fruehere Schema-Erstfassung
#   translations_db.sql, die status/confidence_markers fuehrte). Eine
#   Uebersetzung gilt daher als vorhanden, sobald die Zeile existiert UND
#   translated_text nicht-leer ist.
#
#   'source' trennt Forum-Beitraege ('posts') von privaten Nachrichten ('pms').
#   Beide Methoden filtern auf EINEN source-Wert (Default 'posts'), damit eine
#   PM-Uebersetzung niemals faelschlich fuer einen Forum-Post angezeigt wird
#   (forensische Trennschaerfe, GR1). Die PM-Anzeige ist ein spaeterer Build.
#
#   Spalten-Robustheit: Fehlt (wider Erwarten) topic_id, liefert
#   list_translated_post_ids() leer + WARNING statt Exception. Fehlt eine andere
#   erwartete Spalte, faengt der try/except je Methode das ebenfalls ab.
#
#   Bewusst NICHT gelesen: confidence_markers, processing_time_ms, error_message,
#   batch_id, worker_url, updated_at (updated_at bleibt fuer eine spaetere
#   Re-Uebersetzungs-Versionierung reserviert).
#
# Beleg: Bauplan Build 329 §2, Muster db/templates_db.py, ConnectionManager
#        _attach_readonly (connection_manager.py:520-544)
# Version: v0.7.331 · Build: 331 · 2026-07-07
#   Build 331: status-Filter entfernt (reale Produktionstabelle hat keine
#   status-Spalte), source-Trennung (posts/pms) ergaenzt.
#   Beleg: Projektgespraech 2026-07-07 (reales Schema geliefert).
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
class TranslationRecord:
    """Eine fertige Uebersetzung aus trdb.translations.

    Nur die fuer die Anzeige benoetigten Felder. Provenienz (model_used,
    created_at) laeuft laut GR1 untrennbar mit der Anzeige mit
    ('maschinell uebersetzt, nicht gerichtsverwertbar').
    Beleg: Bauplan Build 329 §2.2, §4.3
    """
    post_id:         int
    translated_text: str
    model_used:      Optional[str]
    created_at:      Optional[str]


@dataclass
class TranslationMetaRecord:
    """Bericht-Metadaten zu einem uebersetzten Post (Build 341).

    Liefert dem Bericht per post_id den bereinigten ORIGINAL-Text
    (posts_cleaned.clean_text), die Ausgangssprache und die Provenienz.
    Der Bericht zitiert den ganzen Original-Post; die Provenienz dient als
    LIVE-Fallback, falls sie am Anker nicht eingefroren wurde (Build 340).
    Beleg: Bauplan Build 340/341 §3, §5.2.
    """
    post_id:       int
    original_text: str
    source_lang:   Optional[str]
    model_used:    Optional[str]
    created_at:    Optional[str]


# =============================================================================
# Hauptklasse
# =============================================================================

class TranslationsDb:
    """
    Kapselt alle Lesezugriffe auf translations.db (Alias 'trdb').

    Ist trdb nicht angebunden, liefern alle Methoden leere Ergebnisse
    (kein Absturz). Dadurch koennen die Endpoints /_forensic/translations
    und /_forensic/translate bereits ausgeliefert werden, bevor die
    Uebersetzungsdaten vorliegen (GR2: jede Version lauffaehig/getestet).
    Beleg: Bauplan Build 329 §1.3, §2.2
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._available = self._check_available()
        # topic_id-Spalte nur pruefen, wenn die Tabelle ueberhaupt da ist.
        self._has_topic_id = (
            self._check_topic_id_column() if self._available else False
        )

    def _check_available(self) -> bool:
        """
        Prueft ob trdb angebunden und die Tabelle 'translations' vorhanden ist.
        Wird einmalig beim Init aufgerufen.
        """
        try:
            self._con.execute("SELECT 1 FROM trdb.translations LIMIT 1")
            logger.debug("TranslationsDb: trdb verfuegbar und initialisiert.")
            return True
        except sqlite3.OperationalError as exc:
            logger.warning(
                "TranslationsDb: trdb nicht verfuegbar ('%s'). "
                "Alle Methoden liefern leere Ergebnisse. translations.db "
                "wird extern befuellt (ollama-Prepper) und dann als 'trdb' "
                "angebunden.",
                exc,
            )
            return False

    def _check_topic_id_column(self) -> bool:
        """
        Prueft per PRAGMA, ob translations.topic_id existiert.

        Der Topic-Endpoint filtert auf topic_id; fehlt die Spalte (Schema noch
        ohne die angekuendigte Ergaenzung), liefert list_translated_post_ids()
        leer + WARNING statt einer OperationalError-Exception.
        Beleg: Bauplan Build 329 §2.2, §2.4
        """
        try:
            rows = self._con.execute(
                "PRAGMA trdb.table_info(translations)"
            ).fetchall()
            # PRAGMA table_info liefert (cid, name, type, notnull, dflt, pk)
            cols = {str(r[1]) for r in rows}
            if "topic_id" not in cols:
                logger.warning(
                    "TranslationsDb: Spalte translations.topic_id fehlt — "
                    "list_translated_post_ids() liefert leer. Vorhandene "
                    "Spalten: %s",
                    sorted(cols),
                )
                return False
            return True
        except sqlite3.OperationalError as exc:
            logger.warning(
                "TranslationsDb: topic_id-Pruefung fehlgeschlagen: %s", exc
            )
            return False

    # ------------------------------------------------------------------
    # Topic-Ebene: welche Posts eines Topics haben eine Uebersetzung?
    # ------------------------------------------------------------------

    def list_translated_post_ids(
        self, topic_id: int, source: str = "posts"
    ) -> list[int]:
        """
        Liefert die post_ids eines Topics, fuer die eine Uebersetzung vorliegt
        (Zeile vorhanden UND nicht-leerer translated_text), gefiltert auf den
        angegebenen source-Wert.

        Die Toolbar ruft dies einmal je Seite auf, cached das Ergebnis als
        Set und injiziert nur dort eine Flaggen-Schaltflaeche, wo die post_id
        enthalten ist (Uebermenge ueber mehrere Topic-Seiten ist unschaedlich —
        die Toolbar schneidet gegen die tatsaechlich vorhandenen #p<id>-Container).
        Beleg: Bauplan Build 329 §2.2, §4.2; Build 331 (source-Trennung).

        Args:
            topic_id: Topic-ID aus der viewtopic.php?id=<topic_id>-URL.
            source:   'posts' (Default, Forum-Beitraege) oder 'pms'. Trennt
                      Beitraege von privaten Nachrichten (GR1: Trennschaerfe).

        Returns:
            Liste von post_ids (int). Leer, wenn trdb nicht angebunden oder
            die Spalte topic_id fehlt.
        """
        if not self._available or not self._has_topic_id:
            return []
        try:
            rows = self._con.execute(
                "SELECT post_id FROM trdb.translations "
                "WHERE topic_id = ? "
                "  AND source = ? "
                "  AND translated_text IS NOT NULL "
                "  AND translated_text <> ''",
                (topic_id, source),
            ).fetchall()
            return [int(r[0]) for r in rows]
        except sqlite3.OperationalError as exc:
            logger.warning(
                "TranslationsDb.list_translated_post_ids(%r) fehlgeschlagen: %s",
                topic_id, exc,
            )
            return []

    # ------------------------------------------------------------------
    # Post-Ebene: die konkrete Uebersetzung eines Posts
    # ------------------------------------------------------------------

    def get_translation(
        self, post_id: int, source: str = "posts"
    ) -> Optional[TranslationRecord]:
        """
        Gibt die Uebersetzung eines einzelnen Posts zurueck (source-gefiltert).

        Args:
            post_id: Primaerschluessel aus trdb.translations.
            source:  'posts' (Default) oder 'pms'. Verhindert, dass eine
                     PM-Uebersetzung fuer einen Forum-Post ausgegeben wird
                     (relevant, falls post_id-Werte kollidieren) — GR1.

        Returns:
            TranslationRecord oder None, wenn keine (nicht-leere) Uebersetzung
            fuer diesen post_id/source vorliegt bzw. trdb nicht angebunden.
        """
        if not self._available:
            return None
        try:
            row = self._con.execute(
                "SELECT post_id, translated_text, model_used, created_at "
                "FROM trdb.translations "
                "WHERE post_id = ? "
                "  AND source = ? "
                "  AND translated_text IS NOT NULL "
                "  AND translated_text <> ''",
                (post_id, source),
            ).fetchone()
            return self._row_to_translation(row) if row else None
        except sqlite3.OperationalError as exc:
            logger.warning(
                "TranslationsDb.get_translation(%r) fehlgeschlagen: %s",
                post_id, exc,
            )
            return None

    def get_meta(
        self, post_id: int, source: str = "posts"
    ) -> Optional["TranslationMetaRecord"]:
        """Bericht-Metadaten zu einem Post: Original-Text + Sprache + Provenienz.

        Read-only aus trdb: posts_cleaned.clean_text (bereinigter Original-Text)
        und source_lang; die Provenienz (model_used/created_at) als LEFT JOIN auf
        translations (LIVE-Fallback; primaer wird sie am Anker eingefroren, Build
        340). Gibt None zurueck, wenn der Post nicht in posts_cleaned steht oder
        trdb nicht angebunden ist (GR1: keine stille Annahme).
        Beleg: Bauplan Build 340/341 §5.2.
        """
        if not self._available:
            return None
        try:
            row = self._con.execute(
                "SELECT pc.post_id AS post_id, pc.clean_text AS clean_text, "
                "       pc.source_lang AS source_lang, "
                "       t.model_used AS model_used, t.created_at AS created_at "
                "FROM trdb.posts_cleaned pc "
                "LEFT JOIN trdb.translations t "
                "       ON t.post_id = pc.post_id AND t.source = ? "
                "WHERE pc.post_id = ?",
                (source, post_id),
            ).fetchone()
            if not row:
                return None
            return TranslationMetaRecord(
                post_id=int(row["post_id"]),
                original_text=(str(row["clean_text"])
                               if row["clean_text"] is not None else ""),
                source_lang=row["source_lang"],
                model_used=row["model_used"],
                created_at=row["created_at"],
            )
        except sqlite3.OperationalError as exc:
            logger.warning(
                "TranslationsDb.get_meta(%r) fehlgeschlagen: %s", post_id, exc
            )
            return None

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_translation(row: sqlite3.Row) -> TranslationRecord:
        return TranslationRecord(
            post_id=int(row["post_id"]),
            translated_text=str(row["translated_text"]),
            model_used=row["model_used"],
            created_at=row["created_at"],
        )
