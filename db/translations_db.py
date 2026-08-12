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
    updated_at:      Optional[str] = None
    # Build 703: updated_at kommt hinzu, WEIL BEI PRIVATEN NACHRICHTEN
    # created_at LEER IST (Datenprobe Alex, 12.08.2026 — der PM-Lauf setzt nur
    # updated_at). Ohne dieses Feld traege die Pflichtkopfzeile der Anzeige bei
    # jeder PM-Uebersetzung KEIN Datum: 'maschinell uebersetzt' ohne Zeitpunkt.
    # Die beiden Werte werden NICHT vermischt (kein COALESCE): 'erstellt' und
    # 'zuletzt geaendert' sind verschiedene Aussagen, und die Anzeige benennt,
    # welche von beiden sie zeigt.


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
        # Build 703: updated_at ist in der gelieferten translations.db
        # vorhanden, in aelteren Bestaenden/Fixtures aber nicht. Die Spalte
        # wird deshalb wie topic_id einmalig geprueft und im SELECT nur dann
        # angefordert — sonst scheiterte die Abfrage GANZ, und mit ihr die
        # Anzeige der Uebersetzung, wegen eines blossen Zusatzdatums.
        self._has_updated_at = (
            self._check_column("updated_at") if self._available else False
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

    def _check_column(self, name: str) -> bool:
        """
        Prueft per PRAGMA, ob trdb.translations die Spalte <name> fuehrt.

        Allgemein gehalten (Build 703), weil dieselbe Frage nun fuer mehr als
        eine Spalte gestellt wird. Ein fehlgeschlagener PRAGMA-Aufruf gilt als
        'Spalte nicht vorhanden' — die vorsichtige Annahme, die im
        Zweifelsfall weniger abfragt statt zu scheitern.
        """
        try:
            rows = self._con.execute(
                "PRAGMA trdb.table_info(translations)"
            ).fetchall()
            return name in {str(r[1]) for r in rows}
        except sqlite3.OperationalError as exc:
            logger.warning(
                "TranslationsDb: Spaltenpruefung '%s' fehlgeschlagen: %s",
                name, exc,
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
            updated_sel = ("updated_at" if self._has_updated_at
                           else "NULL AS updated_at")
            row = self._con.execute(
                "SELECT post_id, translated_text, model_used, created_at, "
                f"       {updated_sel} "
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

    # ------------------------------------------------------------------
    # Build 703: Welche AUS EINER VORGEGEBENEN MENGE sind uebersetzt?
    # ------------------------------------------------------------------

    def filter_translated_post_ids(
        self, post_ids: "list[int]", source: str = "posts"
    ) -> "list[int]":
        """
        Schneidet eine vorgegebene Menge von IDs gegen die vorhandenen
        Uebersetzungen (Zeile vorhanden UND nicht-leerer translated_text).

        WOZU ES DIESEN WEG NEBEN list_translated_post_ids() GIBT: Jener fragt
        ueber trdb.translations.topic_id. Bei privaten Nachrichten ist diese
        Spalte LEER (Datenprobe Alex, 12.08.2026) — die Frage 'welche
        Nachrichten dieses Dialogs sind uebersetzt?' ist dort also gar nicht
        beantwortbar. Sie wird stattdessen zweistufig gestellt: der Dialog
        liefert seine Nachrichten (fdb.pm_aliases), und diese Methode sagt,
        welche davon eine Uebersetzung haben.

        Der Umweg ist auch der sicherere: die Zugehoerigkeit einer Nachricht
        zu einem Dialog steht im forensischen Bestand, nicht in der extern
        erzeugten Uebersetzungsdatenbank.

        Args:
            post_ids: Zu pruefende IDs (bei PN: pm_post_ids).
            source:   'posts' oder 'pms'.

        Returns:
            Teilmenge von post_ids mit Uebersetzung; Reihenfolge unbestimmt.
            Leere Liste bei leerer Eingabe oder nicht angebundener trdb.
        """
        if not self._available or not post_ids:
            return []
        treffer: list[int] = []
        # SQLite begrenzt die Zahl der Parameter (Standard 999). Ein Dialog
        # kann mehrere hundert Nachrichten fuehren (gemessen: 283 Container
        # auf einer PN-Dialogseite, scroll_memory.js) — also in Stapeln.
        CHUNK = 800
        try:
            for i in range(0, len(post_ids), CHUNK):
                batch = [int(p) for p in post_ids[i:i + CHUNK]]
                ph = ",".join("?" * len(batch))
                rows = self._con.execute(
                    f"SELECT post_id FROM trdb.translations "
                    f"WHERE post_id IN ({ph}) "
                    f"  AND source = ? "
                    f"  AND translated_text IS NOT NULL "
                    f"  AND translated_text <> ''",
                    batch + [source],
                ).fetchall()
                treffer.extend(int(r[0]) for r in rows)
        except (sqlite3.OperationalError, ValueError, TypeError) as exc:
            logger.warning(
                "TranslationsDb.filter_translated_post_ids(source=%r) "
                "fehlgeschlagen: %s", source, exc,
            )
            return []
        return treffer

    def get_meta(
        self, post_id: int, source: str = "posts"
    ) -> Optional["TranslationMetaRecord"]:
        """Bericht-Metadaten zu einem Post/einer PM: Original-Text + Sprache + Provenienz.

        Read-only aus trdb. Die QUELLE haengt an 'source' — und WIE sie
        aufgeloest wird, entscheidet der Aufbau der vorgefundenen Datenbank
        (Build 703, gepruefte Spalten statt angenommener Tabellen):

          (A) posts_cleaned MIT Spalte 'source' — so sieht die gelieferte
              translations.db aus (Schema Alex, 12.08.2026: PK
              (post_id, source)). Dann traegt EINE Tabelle beide Quellen, und
              gefiltert wird ueber die Spalte.
          (B) posts_cleaned OHNE 'source' und daneben pms_cleaned — die
              Annahme aus Build 398 ('Option B: getrennte Tabellen'). Sie
              bleibt bedient, damit ein aelterer Bestand weiter lesbar ist.

        WARUM DIE PRUEFUNG UND NICHT EINE FESTE WAHL: Build 398 hat auf eine
        Tabelle 'pms_cleaned' gebaut, die es in der gelieferten Datenbank NICHT
        gibt. get_meta(source='pms') haette dort ausnahmslos None geliefert —
        die PN-Uebersetzung waere im Bericht stillschweigend leer geblieben.
        Ein PRAGMA je Aufruf ist gegen diesen Fehler ein guenstiger Preis.

        In BEIDEN Faellen bleiben Forenbeitrag und private Nachricht mit
        gleicher ID getrennt: in (A) ueber die Spalte, in (B) ueber die
        Tabelle. Diese Trennung ist der Kern (GR1) — Forenpost- und PM-IDs
        stammen aus eigenen, ueberlappenden ID-Raeumen.

        Die Provenienz (model_used/created_at) kommt per LEFT JOIN aus
        trdb.translations — dort ist die Quelle Teil des Schluessels
        (post_id, source), daher wird hier zwingend auf source gefiltert.
        (Primaer wird die Provenienz beim Markieren eingefroren, Build 340; dies
        ist der LIVE-Fallback.)

        Gibt None zurueck, wenn die Quelltabelle fehlt (z. B. pms_cleaned vor der
        PM-Extraktion) oder der Datensatz nicht existiert — kein stiller Fehler:
        der Aufrufer liefert dann found:false.
        Beleg: Bauplan Build 340/341 §5.2; Bauplan PM-Uebersetzung Option B §4.3.
        """
        if not self._available:
            return None
        if source not in ("posts", "pms"):
            logger.warning("TranslationsDb.get_meta: unbekannte source %r", source)
            return None

        table, mit_source_spalte = self._quelltabelle_fuer(source)
        if table is None:
            return None
        # Bei Aufbau (A) grenzt die Spalte die Quelle ein, bei (B) tut das
        # bereits die Tabellenwahl. Der Filter wird deshalb nur dort gesetzt,
        # wo es die Spalte gibt — ein 'AND pc.source = ?' auf einer Tabelle
        # ohne diese Spalte waere ein OperationalError.
        quellfilter = " AND pc.source = ?" if mit_source_spalte else ""
        parameter = ([source, post_id, source] if mit_source_spalte
                     else [source, post_id])
        try:
            row = self._con.execute(
                "SELECT pc.post_id AS post_id, pc.clean_text AS clean_text, "
                "       pc.source_lang AS source_lang, "
                "       t.model_used AS model_used, t.created_at AS created_at "
                f"FROM {table} pc "
                "LEFT JOIN trdb.translations t "
                "       ON t.post_id = pc.post_id AND t.source = ? "
                f"WHERE pc.post_id = ?{quellfilter}",
                parameter,
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
            # Haeufigster Fall: pms_cleaned existiert noch nicht (PM-Extraktion
            # noch nicht gelaufen). Kein Absturz, aber IMMER protokolliert (GR1).
            logger.warning(
                "TranslationsDb.get_meta(post_id=%r, source=%r) fehlgeschlagen "
                "(Tabelle %s evtl. nicht vorhanden): %s",
                post_id, source, table, exc,
            )
            return None

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _quelltabelle_fuer(self, source: str) -> "tuple[Optional[str], bool]":
        """
        Bestimmt fuer get_meta() die Quelle des Original-Textes (Build 703).

        Returns:
            (Tabellenname mit trdb-Praefix oder None, ob nach 'source'
            zu filtern ist). None heisst: fuer diese Quelle liegt in dieser
            Datenbank keine Tabelle vor — der Aufrufer meldet 'nicht
            gefunden', er raet nicht.

        Die Entscheidung wird bei JEDEM Aufruf frisch getroffen und nicht im
        Init zwischengespeichert: der Aufbau der extern befuellten
        translations.db kann sich zwischen zwei Prepper-Laeufen aendern,
        waehrend der Server laeuft.
        """
        try:
            rows = self._con.execute(
                "PRAGMA trdb.table_info(posts_cleaned)"
            ).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning(
                "TranslationsDb: posts_cleaned nicht lesbar: %s", exc
            )
            rows = []
        spalten = {str(r[1]) for r in rows}

        if source == "posts":
            if not spalten:
                logger.warning(
                    "TranslationsDb.get_meta: trdb.posts_cleaned fehlt — "
                    "kein Original-Text abrufbar."
                )
                return None, False
            # Aufbau (A): auch fuer 'posts' auf die Spalte filtern, sonst
            # koennte eine gleichnamige PN-Zeile zurueckkommen.
            return "trdb.posts_cleaned", "source" in spalten

        # source == 'pms'
        if "source" in spalten:
            return "trdb.posts_cleaned", True
        # Aufbau (B): getrennte Tabelle, sofern vorhanden.
        try:
            pms_rows = self._con.execute(
                "PRAGMA trdb.table_info(pms_cleaned)"
            ).fetchall()
        except sqlite3.OperationalError:
            pms_rows = []
        if pms_rows:
            return "trdb.pms_cleaned", False
        logger.warning(
            "TranslationsDb.get_meta(source='pms'): weder eine Spalte "
            "'source' in posts_cleaned noch eine Tabelle pms_cleaned — der "
            "Original-Text privater Nachrichten ist in dieser "
            "translations.db nicht hinterlegt."
        )
        return None, False

    @staticmethod
    def _row_to_translation(row: sqlite3.Row) -> TranslationRecord:
        # updated_at defensiv: aeltere Testbestaende/Schemata fuehren die
        # Spalte nicht. sqlite3.Row wirft bei unbekanntem Schluessel IndexError
        # — ein fehlendes Datum darf die Anzeige der Uebersetzung nicht
        # verhindern.
        try:
            updated = row["updated_at"]
        except (IndexError, KeyError):
            updated = None
        return TranslationRecord(
            post_id=int(row["post_id"]),
            translated_text=str(row["translated_text"]),
            model_used=row["model_used"],
            created_at=row["created_at"],
            updated_at=updated,
        )
