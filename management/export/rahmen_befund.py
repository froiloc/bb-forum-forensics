# =============================================================================
# management/export/rahmen_befund.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem
# =============================================================================
# Zweck (Vorgang ff7e80ab):
#   Ein RahmenBefund haelt EINEN Ausfall beim Zusammenbau des
#   Erzeugungsvermerks fest: WELCHE Angabe fehlt und WARUM.
#
# WARUM ES DIESEN TYP GIBT — DER BEFUND, DER DAZU GEFUEHRT HAT:
#   Bis Build 698 hat der context_builder seine eigenen Ausfaelle still
#   aufgefangen: unlesbare build.json -> Buildnummer 0, nicht aufloesbare
#   Identitaet -> Ersteller 'unbekannt', fehlendes audit_log -> Kette None.
#   Der Bericht entstand danach ganz normal. Die Werte 0 und 'unbekannt'
#   sehen im fertigen Dokument aus wie regulaere Angaben; der Grund war zu
#   diesem Zeitpunkt bereits verloren. Das ist ein still uebersprungener
#   Beleg (GR1) an genau der Stelle, ueber die sich spaeter nachvollziehen
#   laesst, WER ein Abgabedokument mit WELCHEM Stand erzeugt hat.
#
#   Der Befund wird deshalb DORT festgehalten, wo der Ausfall auftritt (im
#   context_builder), und mit dem ExportContext weitergereicht. Er wird
#   NICHT sofort ausgegeben: der Builder ist die gemeinsame Quelle fuer CLIs
#   UND fuer die Endpunkte des Management-Servers; wo eine Meldung hingehoert
#   (Fehlerausgabe, Protokoll, Antwort), weiss nur der Aufrufer. Der Builder
#   stellt die Auskunft bereit, er entscheidet nicht ueber ihren Weg.
#
# WARUM EIN FELDSCHLUESSEL UND NICHT NUR EIN TEXT:
#   Der Erzeugungsvermerk muss die betroffene ZEILE kennzeichnen koennen
#   ('Werkzeug-Build: nicht ermittelbar' statt 'Werkzeug-Build: 0'). Aus
#   einem freien Text laesst sich das nicht ableiten, ohne die Werte selbst
#   zu beschnueffeln — und 'unbekannt' kann als --actor auch legitim
#   uebergeben werden. Der Schluessel benennt die Angabe eindeutig.
#
# REINE KLASSE: keine DB-/Datei-/Netz-/Uhr-Zugriffe, keine Ausgabe.
#
# Version: v0.8.702 · Build: 702 · 2026-08-12
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass


# -- Feldschluessel -----------------------------------------------------------
# Je Schluessel genau EINE Angabe des Erzeugungsvermerks. FELD_RAHMEN ist der
# Sonderfall 'gar kein Rahmen zu bekommen' (siehe unten).
FELD_BUILD = "build_number"
FELD_ERSTELLER = "ersteller"
FELD_KETTE = "kette"

# FELD_RAHMEN: der Rahmen konnte ALS GANZES nicht gebildet werden — z. B.
# weil der context_builder nicht einmal importierbar war. Dann ist KEINE der
# drei Angaben belastbar, und der Ersatzvermerk besteht nur aus Vorgabewerten.
FELD_RAHMEN = "rahmen"

# Klartextbezeichnung je Schluessel. Bewusst hier und nicht beim Aufrufer:
# derselbe Ausfall soll in CLI-Meldung, HTML-Fuss, PDF und Staging-Manifest
# gleich heissen — sonst liest sich derselbe Sachverhalt an vier Stellen
# verschieden.
BEZEICHNUNG = {
    FELD_BUILD: "Buildnummer",
    FELD_ERSTELLER: "Identitaet der erzeugenden Person",
    FELD_KETTE: "Stand der Belegkette",
    FELD_RAHMEN: "Erzeugungsrahmen",
}


@dataclass(frozen=True)
class RahmenBefund:
    """
    EIN Ausfall beim Zusammenbau des Erzeugungsvermerks.

    feld  — einer der Feldschluessel oben. Benennt die betroffene Angabe.
    grund — Klartext, warum sie fehlt (in aller Regel der Text der
            aufgefangenen Ausnahme). Er wird MITGEFUEHRT und nicht
            zusammengefasst: 'nicht ermittelbar' allein beantwortet nicht die
            Frage, ob eine Datei fehlt oder ein Verzeichnisdienst schweigt —
            und genau diese Frage entscheidet, ob der Lauf zu wiederholen ist.

    frozen: ein einmal festgestellter Ausfall wird nicht nachtraeglich
    umgeschrieben — dasselbe Prinzip wie beim ExportContext selbst.
    """

    feld: str
    grund: str

    def bezeichnung(self) -> str:
        """Klartextname der betroffenen Angabe; unbekannte Schluessel roh."""
        return BEZEICHNUNG.get(self.feld, self.feld)

    def als_zeile(self) -> str:
        """
        Eine Zeile fuer den Erzeugungsvermerk (HTML-Fuss, Textfuss, PDF,
        Staging-Manifest). Das Praefix nennt zuerst die FOLGE und dann den
        Grund: wer den Vermerk ueberfliegt, soll nicht erst den Grund lesen
        muessen, um zu erkennen, dass etwas fehlt.
        """
        return "Erzeugungsvermerk unvollstaendig — %s nicht ermittelbar: %s" % (
            self.bezeichnung(), self.grund)

    def als_meldung(self, praefix: str) -> str:
        """
        Eine Zeile fuer die Fehlerausgabe eines Werkzeugs. 'praefix' ist das
        uebliche Werkzeug-Praefix in eckigen Klammern (z. B.
        '[forecast_report]'), damit sich die Meldung in ein Sammelprotokoll
        einordnet wie jede andere Meldung desselben Werkzeugs.
        """
        return "%s WARNUNG: %s nicht ermittelbar (%s)." % (
            praefix, self.bezeichnung(), self.grund)
