# =============================================================================
# management/reports/readonly_report_bundle.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung Berichtseditor (B6) x Management (B7) — SF-1 (Build 410)
# =============================================================================
# Zweck:
#   Baut fuer EINEN Fall (uid) das serverunabhaengige Renderer-Eingangsbuendel
#   (evidence/templates/assets + forensic_con) AUSSCHLIESSLICH READ-ONLY auf,
#   damit das Management (Lektorat W4 / Chef-Freigabe W5) den Berichtstext
#   byte-identisch zum Export (report_render) anzeigen kann.
#
#   Warum eine eigene Klasse (Grundregel 10):
#     - Der Webserver baut dieses Buendel R/W ueber db/connection_manager.py.
#       Das Management darf die evidence_<uid>.db NIEMALS schreiben
#       (Migrationsvorbehalt ab 01.07.2026; Grundregel "nie zwei Schreiber pro
#       Datei" — der Ermittler-Webserver haelt dieselbe Datei live offen).
#     - Deshalb: Hauptverbindung mit URI 'mode=ro', alle Fach-DBs read-only
#       per ATTACH; EvidenceDb wird mit read_only=True konstruiert (kein
#       Schema-Setup/keine Migration).
#
#   Paritaet zum Export (report_render, Feinabnahme Build 399 §6):
#     Der ATTACH-Aufbau (fdb/ddb/adb/tdb) und die forum_base_url-Ermittlung
#     spiegeln db/connection_manager.py:_open_normal — damit Platzhalter- und
#     Bild-Aufloesung dieselben Quellen sehen wie der Ermittler-Export.
#
# Journalmodus:
#   Entfaellt — 'mode=ro'-Verbindungen schreiben nicht (kein WAL/kein Journal;
#   konsistent mit management/reports/reports_repo.py und report_sealer.py).
#
# Version: v0.7.410 · Build: 410 · 2026-07-14
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

from db.evidence_db import EvidenceDb
from db.templates_db import TemplatesDb
from db.assets_db import AssetsDb
from db.forensic_db import ForensicDb

logger = logging.getLogger(__name__)


class ReadonlyReportBundle:
    """
    Read-only Eingangsbuendel fuer report_render.ReportSource zu EINEM Fall.

    Nutzung (Kontextmanager schliesst die Verbindung sicher):

        with ReadonlyReportBundle(evidence_dir=..., forensic_dir=...,
                                  assets_dir=..., templates_db=...,
                                  default_db=..., uid=700) as b:
            doc = ReportSource(evidence=b.evidence, templates=b.templates,
                               assets=b.assets, forensic_con=b.connection,
                               uid=700, username=..., generated_at=...).build(rid)

    Attribute nach open():
        connection — die read-only Hauptverbindung (Traeger der ATTACHs
                     fdb/ddb/adb/tdb); dient ReportSource als forensic_con.
        evidence   — EvidenceDb(read_only=True) auf evidence_<uid>.db (Haupt-DB).
        templates  — TemplatesDb (tdb); liefert leer, wenn templates.db fehlt.
        forensic   — ForensicDb (fdb) fuer die Seitenabzuege (Vollzitat,
                     Build 725); None, wenn fdb nicht anbindbar war.
        assets     — AssetsDb (adb) oder AssetsDb(None), wenn assets_<uid>.db
                     fehlt (dann liefern Asset-Lookups None -> Bild-Verweis
                     wird zu 'missing_image'-Warnung, R2).
    """

    def __init__(
        self,
        *,
        evidence_dir: str,
        forensic_dir: str,
        assets_dir: str,
        templates_db: str,
        uid: int,
        default_db: Optional[str] = None,
        coordinator_db: Optional[str] = None,
    ) -> None:
        self._uid = int(uid)
        self._evidence_path = Path(evidence_dir) / ("evidence_%d.db" % self._uid)
        self._forensic_path = Path(forensic_dir) / ("forensic_%d.db" % self._uid)
        self._assets_path = Path(assets_dir) / ("assets_%d.db" % self._uid)
        self._templates_path = Path(templates_db)
        self._default_path = Path(default_db) if default_db else None
        self._coordinator_path = Path(coordinator_db) if coordinator_db else None

        self._con: Optional[sqlite3.Connection] = None
        self.connection: Optional[sqlite3.Connection] = None
        self.evidence: Optional[EvidenceDb] = None
        self.templates: Optional[TemplatesDb] = None
        self.assets: Optional[AssetsDb] = None
        #: Build 725: der ForensicDb-Griff wird BEHALTEN statt weggeworfen.
        #: Er entstand hier schon vorher, nur fluechtig (zum Lesen von
        #: forum_base_url). Das Vollzitat braucht ihn fuer die Seitenabzuege,
        #: aus denen es den umschliessenden Absatz holt.
        self.forensic: Optional[ForensicDb] = None

    # ------------------------------------------------------------------
    def open(self) -> "ReadonlyReportBundle":
        """Oeffnet alle Verbindungen read-only und baut die Fach-DB-Wrapper."""
        if not self._evidence_path.exists():
            # Grundregel 1: kein stiller Fehlschlag — der Aufrufer wandelt das
            # in einen sichtbaren 404 um.
            raise FileNotFoundError(
                "evidence_%d.db nicht gefunden: %s"
                % (self._uid, self._evidence_path)
            )

        con = sqlite3.connect(
            "file:%s?mode=ro" % self._evidence_path.resolve(),
            uri=True,
            check_same_thread=False,
        )
        con.row_factory = sqlite3.Row
        self._con = con
        self.connection = con

        # ATTACHs (alle READ-ONLY). Reihenfolge/Aliase wie connection_manager.
        self._attach_ro(con, self._forensic_path, "fdb")          # Platzhalter {{a:}}
        if self._default_path is not None:
            self._attach_ro(con, self._default_path, "ddb")       # Asset-Fallback
        adb_attached = self._attach_ro(con, self._assets_path, "adb")
        self._attach_ro(con, self._templates_path, "tdb")         # Query-Definitionen
        # Build 725: cdb READ-ONLY. Bis dahin band dieses Buendel cdb NICHT
        # an, der Webserver dagegen schon (db/connection_manager.py Z. 231-243).
        #
        # WARUM DAS EIN MANGEL WAR UND NICHT NUR EINE LUECKE: Seit dem
        # Vollzitat steht der Ermittlername im Bericht, und der kommt aus
        # cdb.person. Ohne diesen ATTACH zeigte DERSELBE Bericht im
        # Management-Lektorat Kuerzel, wo der Ermittler-Export Klarnamen
        # zeigt - zwei Fassungen einer Akte, unterschieden nur dadurch, wer
        # sie erzeugt hat. Die Paritaetszusage im Kopf dieser Datei
        # ("byte-identisch zum Export") waere gebrochen gewesen.
        #
        # READ-ONLY bleibt es auch hier: das Management schreibt ueber dieses
        # Buendel nichts, in keine Datenbank.
        if self._coordinator_path is not None:
            self._attach_ro(con, self._coordinator_path, "cdb")

        # forum_base_url wie im Webserver aus forensic_meta lesen (Paritaet der
        # Bild-/Asset-Aufloesung). Faellt das aus (fdb fehlt/leer), sauberer
        # Rueckfall auf None -> AssetsDb sucht den Pfad unveraendert.
        forum_base_url: Optional[str] = None
        try:
            self.forensic = ForensicDb(con)
            forum_base_url = self.forensic.get_forum_base_url()
        except Exception as exc:  # pragma: no cover - defensiver Rueckfall
            logger.warning(
                "ReadonlyReportBundle(uid=%d): forum_base_url nicht lesbar (%s)"
                " — Fallback None.", self._uid, exc,
            )

        # EvidenceDb READ-ONLY (kein Schema-Setup/keine Migration, Build 410).
        self.evidence = EvidenceDb(
            con, db_path=str(self._evidence_path), read_only=True,
        )
        # TemplatesDb ist tolerant: fehlt tdb, meldet _check_available() False
        # und alle get_*-Methoden liefern leer (Platzhalter bleiben unaufgeloest).
        self.templates = TemplatesDb(con)
        # AssetsDb nur mit con, wenn adb wirklich angebunden ist; sonst None
        # (die Klasse gibt dann fuer alle Lookups None/False zurueck).
        self.assets = AssetsDb(con if adb_attached else None,
                               forum_base_url=forum_base_url)
        return self

    # ------------------------------------------------------------------
    @staticmethod
    def _attach_ro(con: sqlite3.Connection, path: Path, alias: str) -> bool:
        """
        Bindet 'path' READ-ONLY unter 'alias' an. Gibt True zurueck, wenn
        angebunden, sonst False (Datei fehlt -> optionaler ATTACH entfaellt).
        'alias' ist ein festes internes Literal (kein Nutzereingang) -> die
        String-Formatierung ist unkritisch; der Dateiname wird parametrisiert.
        """
        p = Path(path)
        if not p.exists():
            logger.info(
                "ReadonlyReportBundle: %s nicht gefunden (%s) — '%s' nicht "
                "angebunden.", p.name, p, alias,
            )
            return False
        con.execute(
            "ATTACH DATABASE ? AS %s" % alias,
            ("file:%s?mode=ro" % p.resolve(),),
        )
        return True

    # ------------------------------------------------------------------
    def close(self) -> None:
        """Schliesst die Hauptverbindung (und damit alle ATTACHs)."""
        if self._con is not None:
            try:
                self._con.close()
            except Exception:  # pragma: no cover - defensiv
                pass
            self._con = None
            self.connection = None

    def __enter__(self) -> "ReadonlyReportBundle":
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False
