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
#   Spalten-Robustheit: Der Topic-Endpoint benoetigt die Spalte
#   translations.topic_id. Die Schema-Erstfassung (translations_db.sql) fuehrt
#   topic_id nur in posts_cleaned; die Produktionstabelle wird um topic_id/
#   forum_id ergaenzt (Projektgespraech). Fehlt topic_id dennoch, liefert
#   list_translated_post_ids() leer + WARNING statt Exception.
#
#   Bewusst NICHT gelesen: confidence_markers (die einpflegende Software traegt
#   dort keine sinnvollen Daten ein — Projektgespraech), sowie processing_time_ms,
#   error_message, batch_id, worker_url, updated_at.
#
# Beleg: Bauplan Build 329 §2, Muster db/templates_db.py, ConnectionManager
#        _attach_readonly (connection_manager.py:520-544)
# Version: v0.7.329 · Build: 329 · 2026-07-07
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

    def list_translated_post_ids(self, topic_id: int) -> list[int]:
        """
        Liefert die post_ids eines Topics, fuer die eine FERTIGE Uebersetzung
        vorliegt (status='completed' und nicht-leerer translated_text).

        Die Toolbar ruft dies einmal je Seite auf, cached das Ergebnis als
        Set und injiziert nur dort eine Flaggen-Schaltflaeche, wo die post_id
        enthalten ist (Uebermenge ueber mehrere Topic-Seiten ist unschaedlich —
        die Toolbar schneidet gegen die tatsaechlich vorhandenen #p<id>-Container).
        Beleg: Bauplan Build 329 §2.2, §4.2

        Args:
            topic_id: Topic-ID aus der viewtopic.php?id=<topic_id>-URL.

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
                "  AND status = 'completed' "
                "  AND translated_text IS NOT NULL "
                "  AND translated_text <> ''",
                (topic_id,),
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

    def get_translation(self, post_id: int) -> Optional[TranslationRecord]:
        """
        Gibt die fertige Uebersetzung eines einzelnen Posts zurueck.

        Args:
            post_id: Primaerschluessel aus trdb.translations.

        Returns:
            TranslationRecord oder None, wenn keine fertige Uebersetzung
            vorliegt (kein 'completed', leerer Text) bzw. trdb nicht angebunden.
        """
        if not self._available:
            return None
        try:
            row = self._con.execute(
                "SELECT post_id, translated_text, model_used, created_at "
                "FROM trdb.translations "
                "WHERE post_id = ? "
                "  AND status = 'completed' "
                "  AND translated_text IS NOT NULL "
                "  AND translated_text <> ''",
                (post_id,),
            ).fetchone()
            return self._row_to_translation(row) if row else None
        except sqlite3.OperationalError as exc:
            logger.warning(
                "TranslationsDb.get_translation(%r) fehlgeschlagen: %s",
                post_id, exc,
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
