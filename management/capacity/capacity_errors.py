# =============================================================================
# management/capacity/capacity_errors.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaet (Welle 0)
# =============================================================================
# Gemeinsame Ausnahme der Kapazitaets-Schreibpfade. Klarer Fehler statt stillem
# No-op (Grundregel 1) — z.B. bei ungueltigen Werten oder beim Entfernen einer
# nicht (mehr) vorhandenen Zeile.
# Version: v0.8.560 · Build: 560 · 2026-07-29
# =============================================================================


class CapacityError(Exception):
    """
    Ungueltige Kapazitaets-Operation (Validierung / nicht vorhanden).

    Build 560: die Ausnahme kann OPTIONAL sagen, WELCHES Feld sie ausgeloest
    hat. Grund: die Pflegemaske soll das schuldige Eingabefeld markieren
    koennen, statt nur einen Satz unter das Formular zu schreiben - bei
    sieben Minutenfeldern nebeneinander ist "mon_min muss eine Minutenzahl
    >= 0 sein" sonst eine Suchaufgabe.

    Der Parameter ist NACHGESTELLT und hat einen Vorgabewert; alle
    bestehenden Aufrufe der Form CapacityError("text") bleiben unveraendert
    gueltig. Wer kein Feld nennt, bekommt feld=None - die Oberflaeche zeigt
    dann die Meldung ohne Markierung, statt irgendein Feld zu raten.
    """

    def __init__(self, message: str, feld: str = None) -> None:
        super().__init__(message)
        self.feld = feld
