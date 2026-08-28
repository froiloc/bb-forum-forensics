# =============================================================================
# report_render/quellen_kunde.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Beweismittelgruppen)
# =============================================================================
# Zweck:
#   SAGEN, WOHER EIN BELEG STAMMT. Zu einer Annotation liefert diese Datei:
#   die Art der Quelle (Forenbeitrag oder private Nachricht), den Betreff des
#   Themas bzw. den Gespraechspartner, das Datum DES BEITRAGS und die
#   Fundstelle.
#
# DER AUFTRAG (Chef-Ermittlerin, 27.08.2026, Anforderungen 4, 5 und 7):
#   "Als Datum soll nur das Originaldatum der Quelle und nicht das der
#   Annotation angegeben werden." - "Der Link soll angegeben werden." - "Es
#   soll die Art der Quelle benannt werden, also entweder 'Beitrag zum Thema
#   ...' oder 'Private Nachricht mit ...'."
#
# ── DAS DATUM IST EINE FALLE, UND ZWAR EINE STILLE ───────────────────────────
#
#   'annotations.ts' ist der Zeitpunkt, zu dem der ERMITTLER markiert hat -
#   also ein Datum aus 2026. Der Beitrag ist Jahre aelter. Wer die beiden
#   verwechselt, schreibt in eine Akte, der Beschuldigte habe etwas an einem
#   Tag geschrieben, an dem er es nicht geschrieben hat. Der Berichtseditor
#   zeigt in der Variante 'Zitat' heute genau das an
#   (userinfo/report_editor.js Z. 3423: 'new Date(ann.createdAt)'). Die
#   Vollzitat-Darstellung nimmt deshalb ausschliesslich die Inhaltszeit.
#
#   Sie kommt aus zwei GETRENNTEN Tabellen mit UEBERLAPPENDEN ID-Raeumen:
#   fdb.uid_posts.posted_ts fuer Forenbeitraege, fdb.uid_pms_posts.posted_ts
#   fuer private Nachrichten. Dieselbe Zahl kann beides bezeichnen. Die
#   Unterscheidung trifft die Adresse (_is_pm_url) - falsch gewaehlt, liefert
#   die Abfrage nicht etwa nichts, sondern womoeglich ein PLAUSIBLES falsches
#   Datum.
#
# ── DER GESPRAECHSPARTNER (Anforderung 7, zweiter Teil) ──────────────────────
#
#   Er steht in fdb.uid_pms_posts.partner_username - SOFERN der Prepper die
#   Spalte fuehrt. Sie kommt mit der Prepper-Erweiterung zu diesem Auftrag
#   (Weisung Alex, 27.08.2026: "Fuer die Datenbank forensic_<uid>.db muss die
#   Tabelle um die Felder partner_user_id und partner_username erweitert
#   werden. Das muss im Prepper geschehen."). Bis ein Paket damit neu erzeugt
#   ist, fehlt die Spalte - und dann wird das GESAGT statt geraten.
#
#   Warum nicht aus uid_pn_network: jene Tabelle fuehrt den Partner, aber
#   OHNE pm_topic_id (forensic_uid.db.schema.sql, Z. 300-316). Es gibt im
#   ausgelieferten Paket keinen Verbindungsschluessel von einer Nachricht zu
#   ihrem Partner. Das ist keine fehlende Abfrage, sondern ein fehlendes Feld.
#
# ── ES WIRD NUR GELESEN ──────────────────────────────────────────────────────
#
#   Alle Abfragen laufen gegen fdb (ATTACH read-only). Kein Schema, keine
#   Migration, kein Schreibzugriff; der Migrationsvorbehalt ab 01.07.2026 ist
#   nicht beruehrt.
#
#   JEDE ABFRAGE IST GEGEN EINE FEHLENDE TABELLE ODER SPALTE ABGESICHERT -
#   aber NICHT nach dem Muster von get_post_times(), das einen Fehlschlag
#   protokolliert und ein leeres Ergebnis liefert. Genau dieses Muster hat
#   dort einen Ausfall ueber rund hundert Builds verdeckt (s. Docstring
#   db/forensic_db.py:764-776). Hier wird der Ausfall als WARNUNG bis in den
#   Bericht durchgereicht: der Abschnitt "Hinweise zur Erzeugung" nennt ihn,
#   und der Leser weiss, dass eine Angabe fehlt statt nicht zu existieren.
#
# Grundregeln: GR1, GR6, GR10.
# Version: v0.8.725 - Build: 725 - 2026-08-27
# =============================================================================

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.logger import get_logger

logger = get_logger(__name__)

#: Die Quellenarten.
ART_BEITRAG = "beitrag"
ART_PN = "pn"
#: Build 727: die Quelle ist NICHT bestimmbar - der Beleg existiert nicht
#: (mehr). Bis Build 726 bekam ein solcher Beleg ART_BEITRAG und erschien im
#: Bericht als "Beitrag zum Thema »(Betreff nicht ermittelbar)«". Das war eine
#: BEHAUPTUNG: niemand weiss, ob es je ein Beitrag war. In einer Akte ist eine
#: erfundene Quellenart schlimmer als eine fehlende, weil sie glaubwuerdig
#: aussieht (Befund aus der Sichtpruefung Alex, 28.08.2026).
ART_UNBEKANNT = "unbekannt"

#: Woher die Beitragsnummer stammt - sie wandert bis in den Bericht.
POST_AUS_ANNOTATION = "annotation"   # annotations.post_id / element_id
POST_AUS_SEITENABZUG = "seitenabzug"  # Vorfahr mit id="p<n>" im BLOB
POST_KEINE = "keine"


@dataclass
class Quelle:
    """
    Die Herkunft eines Belegs.

    Felder:
        art          - ART_BEITRAG | ART_PN
        post_id      - post_id bzw. pm_post_id (getrennte ID-Raeume!)
        topic_id     - topic_id bzw. pm_topic_id, wenn ermittelbar
        betreff      - topics.subject bzw. der Betreff der PN; None = unbekannt
        partner      - nur bei ART_PN: Benutzername des Gespraechspartners
        posted_ts    - Inhaltszeit in Sekunden (UTC); None = unbekannt
        seiten_url   - kanonische Adresse der Seite (annotations.page_url)
        anker        - '#p<id>' oder "" - die Sprungmarke auf der Seite
        verfasser    - Benutzername des Verfassers, falls aus dem Seitenabzug
                       ablesbar; sonst None (kein Pflichtfeld, s. unten)
        post_quelle  - POST_AUS_ANNOTATION | POST_AUS_SEITENABZUG | POST_KEINE
                       (Build 727 - der Weg zur Beitragsnummer wird benannt)
        warnungen    - Klartextmeldungen fuer den Hinweisabschnitt (R2)

    'verfasser' IST BEWUSST OHNE WARNUNG: Er steht in keiner Anforderung der
    Chef-Ermittlerin und ist eine Zugabe aus dem ohnehin zerlegten
    Seitenabzug. Fehlt er, fehlt kein Beleg - nur eine Bequemlichkeit. Eine
    Warnung dafuer wuerde die Liste verwaessern, auf die es bei den echten
    Ausfaellen ankommt.
    """
    art: str
    post_id: Optional[int] = None
    topic_id: Optional[int] = None
    betreff: Optional[str] = None
    partner: Optional[str] = None
    posted_ts: Optional[int] = None
    seiten_url: str = ""
    anker: str = ""
    verfasser: Optional[str] = None
    post_quelle: str = POST_KEINE
    warnungen: List[str] = field(default_factory=list)

    @property
    def ist_pn(self) -> bool:
        return self.art == ART_PN

    @property
    def ist_unbekannt(self) -> bool:
        return self.art == ART_UNBEKANNT

    @property
    def link(self) -> str:
        """Die vollstaendige Fundstelle - Seite plus Sprungmarke."""
        if self.anker and not self.seiten_url.endswith(self.anker):
            return "%s%s" % (self.seiten_url, self.anker)
        return self.seiten_url

    def bezeichnung(self) -> str:
        """
        Die Zeile, die im Bericht ueber dem Absatz steht.

        Wortlaut nach Anforderung 7. Fehlt der Betreff bzw. der Partner, wird
        das AN DIESER STELLE gesagt und nicht durch Weglassen verdeckt - ein
        Beleg ohne Quellenbenennung waere fuer die Staatsanwaltschaft nicht
        zuzuordnen.
        """
        if self.ist_unbekannt:
            # Build 727: KEINE erfundene Quellenart. S. Kopf bei
            # ART_UNBEKANNT.
            return "Beleg nicht mehr vorhanden"
        if self.ist_pn:
            wer = self.partner or "(Gespraechspartner nicht ermittelbar)"
            return "Private Nachricht mit »%s«" % wer
        was = self.betreff or "(Betreff nicht ermittelbar)"
        return "Beitrag zum Thema »%s«" % was


class QuellenKunde:
    """
    Beantwortet Herkunftsfragen zu Annotationen - mit Zwischenspeicher.

    Eine Instanz je Berichtsaufbau. Braucht eine Verbindung, auf der fdb
    angebunden ist (die Buendelverbindung; in beiden Exportwegen vorhanden).
    """

    def __init__(self, con: Optional[sqlite3.Connection]) -> None:
        self._con = con
        self._spalten: Dict[str, set] = {}
        self._beitrag: Dict[int, Any] = {}
        self._pn: Dict[int, Any] = {}
        #: Einmalige Meldungen - damit ein Bericht mit 200 Belegen nicht
        #: 200-mal dieselbe fehlende Spalte meldet.
        self._gemeldet: set = set()

    # ------------------------------------------------------------------
    def _tabellenspalten(self, tabelle: str) -> set:
        """Die Spalten einer fdb-Tabelle; leere Menge, wenn es sie nicht gibt."""
        if tabelle in self._spalten:
            return self._spalten[tabelle]
        spalten: set = set()
        if self._con is not None:
            try:
                spalten = {
                    r[1] for r in self._con.execute(
                        "PRAGMA fdb.table_info(%s)" % tabelle)
                }
            except sqlite3.Error as exc:
                logger.warning("fdb.%s nicht lesbar (%s).", tabelle, exc)
        self._spalten[tabelle] = spalten
        return spalten

    # ------------------------------------------------------------------
    def _einmal(self, schluessel: str, meldung: str, warnungen: List[str]) -> None:
        """Eine Warnung genau einmal je Bericht in die Liste legen."""
        if schluessel in self._gemeldet:
            return
        self._gemeldet.add(schluessel)
        warnungen.append(meldung)

    # ------------------------------------------------------------------
    def ermitteln(
        self,
        *,
        page_url: str,
        post_id: Optional[int],
        element_id: Optional[str],
        post_quelle: str = POST_AUS_ANNOTATION,
    ) -> Quelle:
        """
        Die Quelle zu einer Annotation bestimmen.

        page_url entscheidet ueber die Art (und damit ueber die Zeittabelle);
        post_id ist bereits aus post_id/element_id abgeleitet (der Aufrufer
        benutzt dafuer forensic_api.annotations._derive_post_id, damit die
        Ableitung nicht zweimal geschrieben wird).
        """
        from forensic_api.annotations import _is_pm_url

        # Die Sprungmarke auf der Seite (Anforderung 5).
        #
        # BUILD 727: Sie haengt jetzt an der BEITRAGSNUMMER, nicht mehr an
        # 'element_id'. Bei Textmarkierungen ist element_id leer (toolbar.js,
        # Build 336) - die Fundstelle blieb deshalb die blosse Seitenadresse,
        # und wer sie in einer Akte anklickte, landete am Seitenanfang statt
        # am Beitrag. Beide Ansichten des Forums kennzeichnen einen Beitrag
        # mit 'p<Nummer>' (Forenquelltext viewtopic.php und pmsnew topic.php),
        # die Marke ist also fuer Beitraege und private Nachrichten dieselbe.
        anker = ""
        if post_id is not None:
            anker = "#p%d" % int(post_id)
        elif element_id and str(element_id).strip().startswith("p"):
            anker = "#%s" % str(element_id).strip()

        quelle = Quelle(
            art=ART_PN if _is_pm_url(page_url) else ART_BEITRAG,
            post_id=post_id,
            seiten_url=str(page_url or ""),
            anker=anker,
        )

        quelle.post_quelle = post_quelle if post_id is not None else POST_KEINE
        if post_id is None:
            quelle.warnungen.append(
                "Beleg ohne Beitragsbezug: weder 'post_id' noch eine "
                "Elementkennung der Form 'p<Nummer>', und im Seitenabzug war "
                "der Beitrag nicht zu bestimmen. Betreff und Originaldatum "
                "sind damit nicht bestimmbar; die Fundstelle bleibt die "
                "Seitenadresse.")
            return quelle

        if quelle.ist_pn:
            self._fuelle_pn(quelle)
        else:
            self._fuelle_beitrag(quelle)
        return quelle

    # ------------------------------------------------------------------
    def _fuelle_beitrag(self, q: Quelle) -> None:
        zeile = self._beitrag.get(q.post_id)
        if zeile is None:
            zeile = self._lies_beitrag(q.post_id, q.warnungen)
            self._beitrag[q.post_id] = zeile
        if not zeile:
            q.warnungen.append(
                "Beitrag #%d ist in fdb.uid_posts und fdb.post_aliases nicht "
                "verzeichnet - Thema und Originaldatum sind unbekannt."
                % q.post_id)
            return
        q.topic_id = zeile.get("topic_id")
        q.posted_ts = zeile.get("posted_ts")
        q.betreff = zeile.get("subject")
        if q.posted_ts is None:
            # Die Begruendung nennt die TATSAECHLICH benutzte Tabelle. Ein
            # Beitrag, der nur ueber post_aliases bekannt ist, hat dort kein
            # Datumsfeld - "posted_ts ist leer" waere in diesem Fall eine
            # falsche Auskunft ueber die Datenlage.
            if zeile.get("_herkunft") == "post_aliases":
                q.warnungen.append(
                    "Beitrag #%d steht nicht in fdb.uid_posts, sondern nur in "
                    "fdb.post_aliases (passive Erwaehnung). Das Thema ist "
                    "damit bekannt, ein Originaldatum fuehrt diese Tabelle "
                    "nicht." % q.post_id)
            else:
                q.warnungen.append(
                    "Beitrag #%d ohne Originaldatum "
                    "(fdb.uid_posts.posted_ts ist leer)." % q.post_id)
        if q.betreff is None and q.topic_id is not None:
            q.warnungen.append(
                "Zu Thema #%s fuehrt fdb.uid_topics keinen Betreff. Der "
                "Prepper legt fuer geloeschte Themen eine Zeile mit leerem "
                "Betreff an (Grundregel 1) - das Thema bestand also, sein "
                "Titel ist im Abzug nicht mehr enthalten." % q.topic_id)

    # ------------------------------------------------------------------
    def _lies_beitrag(self, post_id: int, warnungen: List[str]):
        if self._con is None:
            return None
        hat_posts = bool(self._tabellenspalten("uid_posts"))
        hat_topics = "subject" in self._tabellenspalten("uid_topics")

        if not hat_posts:
            self._einmal(
                "uid_posts",
                "fdb.uid_posts fehlt in diesem Paket - fuer keinen Beleg "
                "koennen Thema und Originaldatum bestimmt werden. Das Paket "
                "stammt aus einem Prepper-Stand vor Build 108.",
                warnungen)
        if not hat_topics:
            self._einmal(
                "uid_topics",
                "fdb.uid_topics fehlt in diesem Paket - die Themenbetreffe "
                "bleiben leer.",
                warnungen)

        zeile = None
        if hat_posts:
            # (Herkunftsvermerk wird unten gesetzt - er begruendet spaeter die
            #  Warnung zum fehlenden Datum.)
            sql = ("SELECT p.topic_id AS topic_id, p.posted_ts AS posted_ts"
                   + (", t.subject AS subject" if hat_topics else
                      ", NULL AS subject")
                   + " FROM fdb.uid_posts p"
                   + (" LEFT JOIN fdb.uid_topics t ON t.topic_id = p.topic_id"
                      if hat_topics else "")
                   + " WHERE p.post_id = ?")
            zeile = self._eine_zeile(sql, (post_id,))

        if zeile is None:
            # Rueckfall: post_aliases kennt die Themenzuordnung auch dann,
            # wenn der Beitrag selbst nicht in uid_posts steht (passive
            # Erwaehnung). Das Datum gibt es dort nicht - dafuer aber den
            # Betreff, und der ist die Quellenbenennung.
            if self._tabellenspalten("post_aliases"):
                sql = ("SELECT a.topic_id AS topic_id, NULL AS posted_ts"
                       + (", t.subject AS subject" if hat_topics else
                          ", NULL AS subject")
                       + " FROM fdb.post_aliases a"
                       + (" LEFT JOIN fdb.uid_topics t "
                          "ON t.topic_id = a.topic_id" if hat_topics else "")
                       + " WHERE a.post_id = ?")
                zeile = self._eine_zeile(sql, (post_id,))
                if zeile is not None:
                    zeile["_herkunft"] = "post_aliases"
        elif zeile is not None:
            zeile["_herkunft"] = "uid_posts"
        return zeile

    # ------------------------------------------------------------------
    def _fuelle_pn(self, q: Quelle) -> None:
        zeile = self._pn.get(q.post_id)
        if zeile is None:
            zeile = self._lies_pn(q.post_id, q.warnungen)
            self._pn[q.post_id] = zeile
        if not zeile:
            q.warnungen.append(
                "Private Nachricht #%d ist in fdb.uid_pms_posts nicht "
                "verzeichnet - Gespraechspartner und Originaldatum sind "
                "unbekannt." % q.post_id)
            return
        q.topic_id = zeile.get("pm_topic_id")
        q.posted_ts = zeile.get("posted_ts")
        q.betreff = zeile.get("topic_subject")
        q.partner = zeile.get("partner_username")
        if q.posted_ts is None:
            q.warnungen.append(
                "Private Nachricht #%d ohne Originaldatum "
                "(fdb.uid_pms_posts.posted_ts ist leer)." % q.post_id)

    # ------------------------------------------------------------------
    def _lies_pn(self, pm_post_id: int, warnungen: List[str]):
        if self._con is None:
            return None
        spalten = self._tabellenspalten("uid_pms_posts")
        if not spalten:
            self._einmal(
                "uid_pms_posts",
                "fdb.uid_pms_posts fehlt in diesem Paket - fuer private "
                "Nachrichten koennen Partner und Originaldatum nicht "
                "bestimmt werden.",
                warnungen)
            return None

        hat_partner = "partner_username" in spalten
        if not hat_partner:
            self._einmal(
                "pms_partner",
                "fdb.uid_pms_posts fuehrt keine Spalte 'partner_username'. "
                "Das Paket stammt aus einem Prepper-Stand vor der "
                "Erweiterung vom 27.08.2026; der Gespraechspartner wird "
                "deshalb bei ALLEN privaten Nachrichten dieses Berichts "
                "nicht benannt. Er ist im Paket nicht enthalten und laesst "
                "sich auch nicht aus uid_pn_network herleiten - dort fehlt "
                "die Zuordnung zur Unterhaltung. Abhilfe: das Paket mit "
                "einem neueren Prepper erneut erzeugen.",
                warnungen)

        felder = ["pm_topic_id", "posted_ts"]
        felder.append("topic_subject" if "topic_subject" in spalten
                      else "NULL AS topic_subject")
        felder.append("partner_username" if hat_partner
                      else "NULL AS partner_username")
        return self._eine_zeile(
            "SELECT %s FROM fdb.uid_pms_posts WHERE pm_post_id = ?"
            % ", ".join(felder), (pm_post_id,))

    # ------------------------------------------------------------------
    def _eine_zeile(self, sql: str, parameter):
        try:
            row = self._con.execute(sql, parameter).fetchone()
        except sqlite3.Error as exc:
            # Kein stiller Rueckfall auf {}: die Meldung geht ins Protokoll
            # UND der Aufrufer sieht None und warnt im Bericht.
            logger.warning("QuellenKunde: Abfrage fehlgeschlagen (%s): %s",
                           exc, sql)
            return None
        return dict(row) if row is not None else None
