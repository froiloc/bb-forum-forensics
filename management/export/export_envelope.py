# =============================================================================
# management/export/export_envelope.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Zweck (Idee 1 — einheitlicher Kopf/Fuss, Pruefsumme, Erzeugungsvermerk):
#   ExportEnvelope kapselt den GEMEINSAMEN Rahmen jedes Management-Exports:
#     * Aktenkopf   — Behoerde, Aktenzeichen/Fall, Klassifikation.
#     * Erzeugungsvermerk — wer (SAMAccountName, stabile forensische Identitaet,
#                   Beleg management/server/identity.py), wann, mit welcher
#                   Buildnummer, auf welcher Integritaets-Kettenspitze
#                   (verify_chain-Ergebnis + audit_log-tip). So zertifiziert der
#                   Export SELBST die Belegkette, aus der er stammt — dasselbe
#                   Prinzip wie die bestehenden html_export.py-Integritaets-
#                   banner (support_overview/html_export.py Kopf), hier
#                   vereinheitlicht.
#     * Pruefsumme  — SHA-256 des Nutzinhalts (management.export.checksum), vom
#                   Empfaenger unabhaengig nachrechenbar.
#
#   REINE KLASSE: keine DB-/Datei-/Netz-/Uhr-Zugriffe. ALLE veraenderlichen
#   Werte (Ersteller, Zeitpunkt, Ketten-Status) werden INJIZIERT — der Aufrufer
#   (CLI/Endpunkt) loest Identitaet und Zeit auf, der Rahmen bleibt
#   deterministisch und vollstaendig automatisiert testbar (Muster der
#   bestehenden html_export.py: reine Render-Funktion, Daten vom Aufrufer).
#
#   SICHERHEIT: Alle in HTML eingebetteten Werte (Anzeigenamen, Aktenzeichen —
#   beliebiger UTF-8-Text aus multilingualen Quellen) werden mit html.escape()
#   entschaerft. UTF-8 bleibt erhalten (escape kodiert nur < > & " ').
#
# BUILD 702 (Vorgang ff7e80ab) — DER VERMERK SAGT JETZT AUCH, WAS IHM FEHLT:
#   Der Erzeugungsvermerk fuehrt seit diesem Build die 'rahmen_befunde' mit
#   (management/export/rahmen_befund.py). Konnte eine Angabe beim Zusammenbau
#   nicht ermittelt werden, steht das in der betroffenen ZEILE ('Werkzeug-Build:
#   nicht ermittelbar' statt 'Werkzeug-Build: 0') und der Grund darunter.
#   Vorher trug der Vermerk in dieser Lage die Ausfallwerte 0 und 'unbekannt',
#   die im fertigen Dokument wie regulaere Angaben aussehen — ein still
#   uebersprungener Beleg (GR1) an der Stelle, die die Herkunft eines
#   Abgabedokuments belegen soll.
#
#   OHNE BEFUND AENDERT SICH NICHTS. Das ist Absicht und nicht nur Ruecksicht
#   auf bestehende Tests: der Regelfall ist der haeufige Fall, und ein Vermerk,
#   der auch dann ueber sich selbst spricht, wenn nichts fehlt, stumpft ab.
#
# BUILD 708 (Vorgang 5001d293) — EIN FELD, DAS DER VERMERK NICHT ZEIGT:
#   ExportContext bekommt 'chain_detail' (Klartext der Kettenpruefung). Es
#   wird von erzeugungsvermerk_lines() NICHT gerendert - der Vermerk bleibt
#   Zeichen fuer Zeichen der aus Build 469. Das Feld traegt die Auskunft fuer
#   den AUFRUFER; 'export_admin' meldet damit eine gebrochene Kette samt
#   Fundstelle, ohne sich die Pruefung selbst nachbauen zu muessen.
#
# Version: v0.8.708 · Build: 708 · 2026-08-12
# =============================================================================

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Optional, Tuple

from management.export.checksum import content_sha256_bytes, content_sha256_text
from management.export.rahmen_befund import (
    FELD_BUILD,
    FELD_ERSTELLER,
    FELD_RAHMEN,
    RahmenBefund,
)


# Standard-Klassifikation des Projekts (aus den Bauplan-Koepfen uebernommen).
DEFAULT_KLASSIFIKATION = "VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH"


@dataclass(frozen=True)
class ExportContext:
    """
    Alle Werte fuer Aktenkopf + Erzeugungsvermerk. Unveraenderlich (frozen):
    ein einmal gestempelter Export-Rahmen wird nicht nachtraeglich veraendert.

    Pflichtfelder:
      behoerde        — z. B. "Polizei NRW — EK Zarewitsch".
      aktenzeichen    — Fall-/Aktenkennung (z. B. subject_id-Label oder Az.).
      ersteller       — SAMAccountName der ausfuehrenden Person (stabile
                        forensische Identitaet; NICHT der AD-Anzeigename).
      build_number    — Buildnummer des erzeugenden Werkzeugs (GR4).
      generated_at    — Zeitstempel als bereits formatierter String (injiziert;
                        keine Uhr in der reinen Klasse -> deterministisch).

    Optional (Integritaets-Kettenspitze; None = nicht geprueft/nicht anwendbar):
      chain_ok        — Ergebnis von AuditLog.verify_chain (True/False/None).
      chain_tip_seq   — seq der letzten audit_log-Zeile zum Exportzeitpunkt.
      chain_tip_hash  — row_hash der letzten audit_log-Zeile.
      chain_detail    — (Build 708, Vorgang 5001d293) der Klartext aus
                        VerifyResult.detail: bei einer gebrochenen Kette die
                        Fundstelle ('prev_hash-Bruch bei seq=41'), sonst
                        'OK (n Eintraege)'.

                        ER WIRD IM VERMERK NICHT GERENDERT, und das ist
                        Absicht: der Vermerk ist Zeichen fuer Zeichen der aus
                        Build 469, und eine Aenderung dort haette alle
                        bestehenden Abgabedokumente von den kuenftigen
                        unterscheidbar gemacht. Das Feld traegt die Auskunft
                        fuer den AUFRUFER - 'export_admin' meldet damit eine
                        gebrochene Kette samt Fundstelle auf der
                        Fehlerausgabe, so wie vor der Umstellung auf den
                        context_builder.

                        DASS DER VERMERK DIE FUNDSTELLE NICHT NENNT, ist eine
                        eigene Frage und hier nicht entschieden - er sagt
                        'GEBROCHEN' und nennt die Kettenspitze, was fuer sich
                        genommen eine vollstaendige Aussage ist.
      klassifikation  — Vertraulichkeitsvermerk (Default s. o.).
      anzeigename     — optionaler AD-Anzeigename, nur zur Anzeige neben dem
                        SAMAccountName (Beleg identity.py: display_name).
      rahmen_befunde  — (Build 702, Vorgang ff7e80ab) die Ausfaelle, die beim
                        Zusammenbau dieses Rahmens aufgetreten sind. LEER =
                        alle Angaben sind ermittelt. Nicht leer = mindestens
                        eine Angabe ist ein Ersatzwert; welche und warum, sagt
                        der jeweilige RahmenBefund. Das Feld traegt die
                        Auskunft mit dem Rahmen mit, statt sie am Ort des
                        Ausfalls auszugeben — nur der Aufrufer weiss, wohin
                        eine Meldung gehoert (Fehlerausgabe, Protokoll,
                        HTTP-Antwort).

                        TUPEL, nicht Liste: der ExportContext ist frozen, und
                        eine veraenderliche Vorgabe waere es nur dem Namen
                        nach.
    """
    behoerde: str
    aktenzeichen: str
    ersteller: str
    build_number: int
    generated_at: str
    chain_ok: Optional[bool] = None
    chain_tip_seq: Optional[int] = None
    chain_tip_hash: Optional[str] = None
    chain_detail: Optional[str] = None
    klassifikation: str = DEFAULT_KLASSIFIKATION
    anzeigename: Optional[str] = None
    rahmen_befunde: Tuple[RahmenBefund, ...] = field(default_factory=tuple)

    def hat_befund(self, feld: str) -> bool:
        """
        True, wenn die Angabe 'feld' nicht ermittelt werden konnte.

        FELD_RAHMEN schlaegt auf JEDE Angabe durch: konnte der Rahmen als
        Ganzes nicht gebildet werden, ist keine einzelne Angabe belastbar —
        auch dann nicht, wenn zufaellig ein plausibler Wert dasteht.
        """
        return any(b.feld in (feld, FELD_RAHMEN) for b in self.rahmen_befunde)

    def rahmen_vollstaendig(self) -> bool:
        """True, wenn der Erzeugungsvermerk ohne Ersatzwerte zustande kam."""
        return not self.rahmen_befunde


class ExportEnvelope:
    """
    Erzeugt Aktenkopf, Erzeugungsvermerk und Pruefsumme in HTML und Klartext.

    Verwendung (durch die konkreten Exporte ab B441):
        env = ExportEnvelope(context)
        digest = env.checksum_text(body_html)      # oder checksum_bytes(...)
        seite  = env.header_html(titel) + body_html + env.footer_html(digest)
    """

    def __init__(self, context: ExportContext) -> None:
        self._ctx = context

    # -- Pruefsumme des Nutzinhalts ------------------------------------------

    def checksum_bytes(self, payload: bytes) -> str:
        """SHA-256 ueber die exakten Nutzinhalt-Bytes (jedes Format)."""
        return content_sha256_bytes(payload)

    def checksum_text(self, payload: str, *, encoding: str = "utf-8") -> str:
        """SHA-256 ueber den Nutzinhalt als Text (UTF-8)."""
        return content_sha256_text(payload, encoding=encoding)

    # -- Erzeugungsvermerk (strukturiert) ------------------------------------

    def integrity_line(self) -> str:
        """
        Klartext-Zeile zur Integritaets-Kettenspitze. Fehlt die Pruefung
        (chain_ok is None) -> ausdruecklicher Vermerk statt stiller Luecke (GR1).
        """
        c = self._ctx
        if c.chain_ok is None:
            return "Audit-Kette: nicht geprueft"
        status = "INTAKT" if c.chain_ok else "GEBROCHEN"
        seq = c.chain_tip_seq if c.chain_tip_seq is not None else "?"
        tip = c.chain_tip_hash or "?"
        return "Audit-Kette: %s (Spitze seq=%s, hash=%s)" % (status, seq, tip)

    def erzeugungsvermerk_lines(self) -> list:
        """
        Der Erzeugungsvermerk als Liste von Klartext-Zeilen (Reihenfolge stabil).
        Basis fuer header/footer in beiden Ausgabeformen.

        BUILD 702 (Vorgang ff7e80ab) — ZWEI AENDERUNGEN, BEIDE NUR IM AUSFALL:
        (1) Eine nicht ermittelte Angabe wird IN IHRER ZEILE als solche
            benannt. Vorher stand dort der Ersatzwert (Buildnummer 0,
            Ersteller 'unbekannt'), der sich von einer echten Angabe nicht
            unterscheiden laesst. Wer den Vermerk liest, um die Herkunft eines
            Abgabedokuments zu pruefen, bekaeme so eine Falschauskunft.
        (2) Unter den Angaben folgt je Ausfall EINE Befundzeile mit dem Grund.
            Die Zeilen stehen am ENDE und in der Reihenfolge ihres Auftretens:
            der Vermerk behaelt seinen gewohnten Aufbau, und das Zusaetzliche
            steht dort, wo es niemanden ueberliest.

        Bei vollstaendigem Rahmen ist die Ausgabe Zeichen fuer Zeichen die aus
        Build 469.

        Der ERSTELLER wird anders behandelt als die Buildnummer, und das ist
        kein Versehen: scheitert die Aufloesung, steht dort immer noch der
        Rohwert aus --actor bzw. der OS-Identitaet (Beleg context_builder.
        _resolve_actor). Dieser Name ist nicht falsch, er ist nur UNGEPRUEFT.
        Ihn durch 'nicht ermittelbar' zu ersetzen, wuerde eine vorhandene Spur
        vernichten; der Zusatz kennzeichnet sie stattdessen.
        """
        c = self._ctx
        ersteller = c.ersteller
        if c.anzeigename:
            ersteller = "%s (%s)" % (c.anzeigename, c.ersteller)
        if c.hat_befund(FELD_ERSTELLER):
            ersteller = "%s [nicht aufgeloest]" % ersteller

        if c.hat_befund(FELD_BUILD):
            build_zeile = "Werkzeug-Build: nicht ermittelbar"
        else:
            build_zeile = "Werkzeug-Build: %d" % c.build_number

        lines = [
            "Erstellt von: %s" % ersteller,
            "Erstellt am: %s" % c.generated_at,
            build_zeile,
            self.integrity_line(),
        ]
        lines.extend(b.als_zeile() for b in c.rahmen_befunde)
        return lines

    # -- Aktenkopf -----------------------------------------------------------

    def header_text(self, titel: str) -> str:
        """Aktenkopf als Klartext (fuer TXT/CSV-Praeambel)."""
        c = self._ctx
        return (
            "%s\n%s\nBehoerde: %s\nAktenzeichen: %s\n%s\n"
            % (c.klassifikation, titel, c.behoerde, c.aktenzeichen,
               "=" * 72)
        )

    def header_html(self, titel: str) -> str:
        """
        Aktenkopf als HTML-Block. Alle Werte html-escaped (Injektionsschutz),
        UTF-8 erhalten. Selbst-enthaltend (Inline-Style), passend zu den
        bestehenden self-contained html_export.py.
        """
        c = self._ctx
        return (
            '<header class="aiw-export-head">\n'
            '  <div class="aiw-klass">%s</div>\n'
            '  <h1>%s</h1>\n'
            '  <div class="aiw-akte">Behörde: %s · Aktenzeichen: %s</div>\n'
            '</header>\n'
            % (html.escape(c.klassifikation), html.escape(titel),
               html.escape(c.behoerde), html.escape(c.aktenzeichen))
        )

    def classification_band_html(self) -> str:
        """
        Schlanker Aktenkopf-BAND zum Einbetten OBERHALB einer Sicht, die bereits
        eine eigene Ueberschrift traegt (die self-contained html_export.py der
        Cockpit-Sichten). Enthaelt NUR Klassifikation + Behoerde/Aktenzeichen —
        KEIN <h1>, um die vorhandene Seitenueberschrift nicht zu doppeln. Werte
        html-escaped, UTF-8 erhalten.
        """
        c = self._ctx
        return (
            '<div class="aiw-export-band">\n'
            '  <span class="aiw-klass">%s</span>\n'
            '  <span class="aiw-akte">Behörde: %s · Aktenzeichen: %s</span>\n'
            '</div>\n'
            % (html.escape(c.klassifikation), html.escape(c.behoerde),
               html.escape(c.aktenzeichen))
        )

    # -- Fuss / Erzeugungsvermerk + Pruefsumme -------------------------------

    def footer_text(self, payload_digest: str) -> str:
        """Erzeugungsvermerk + Pruefsumme als Klartext-Fuss."""
        lines = self.erzeugungsvermerk_lines()
        lines.append("Pruefsumme (SHA-256): %s" % payload_digest)
        return "=" * 72 + "\n" + "\n".join(lines) + "\n"

    def footer_html(self, payload_digest: str) -> str:
        """
        Erzeugungsvermerk + Pruefsumme als HTML-Fuss. Werte html-escaped.
        Die Pruefsumme deckt den NUTZINHALT ab (nicht Kopf/Fuss) — so kann der
        Empfaenger sie unabhaengig ueber den Inhalt nachrechnen.
        """
        rows = "".join(
            "    <li>%s</li>\n" % html.escape(line)
            for line in self.erzeugungsvermerk_lines()
        )
        return (
            '<footer class="aiw-export-foot">\n'
            '  <ul class="aiw-erzeugungsvermerk">\n'
            '%s'
            '    <li>Prüfsumme (SHA-256): <code>%s</code></li>\n'
            '  </ul>\n'
            '</footer>\n'
            % (rows, html.escape(payload_digest))
        )
