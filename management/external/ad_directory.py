# =============================================================================
# management/external/ad_directory.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AD-Schicht (Fundament F4)
# =============================================================================
# Zweck (Fundament F4 — AD-Integrationsschicht, "gekapselt, mockbar, nur lesend"):
#   Aufloesung und PRUEFUNG externer Empfaenger-Kennungen (Windows-SAMAccount-
#   Name) fuer die externe Fallfreigabe (Idee 26). Die Schicht beantwortet genau
#   zwei Fragen:
#     * Ist eine Kennung Mitglied der berechtigten NRW-Gruppe? (Gruppenabgleich)
#     * Wie lautet ihr Anzeigename? (Anzeige statt SAMAccountName)
#
#   OFFLINE-VM: Es gibt KEIN Live-AD. Die Mitgliedschaft wird daher aus einer
#   KONFIGURATIONS-ALLOWLIST gelesen (config.yaml -> ad.release_recipients).
#   Fehlt sie oder ist die Kennung nicht enthalten, ist der Empfaenger NICHT
#   freigabefaehig (DEFAULT-DENY -> ADDirectoryError). Nichts wird still
#   uebersprungen (Grundregel 1).
#
#   Exakt das Muster von server/identity.py: die Quelle (das Empfaenger-Mapping)
#   ist INJIZIERBAR. Im Test wird ein Mapping direkt uebergeben; im Betrieb baut
#   from_config() es aus config.yaml. Damit bleibt der AD-Zugriff an genau einer
#   Stelle gekapselt und ersetzbar — ein spaeterer echter LDAP-Anschluss tauscht
#   nur die Quelle, nicht die Aufrufer.
#
#   SAMAccountName ist AD-seitig NICHT case-sensitiv. Die Aufloesung vergleicht
#   daher case-insensitiv, liefert aber die KANONISCHE (konfigurierte) Schreib-
#   weise der Kennung zurueck — damit im Freigabe-Record und im Audit-Beleg ein
#   und dieselbe Kennung eindeutig steht (kein 'h0B1234' vs 'h0b1234').
#
# REIN LESEND. Keine DB, keine Uhr. Vollstaendig in pytest pruefbar.
#
# Version: v0.7.462 · Build: 462 · 2026-07-20
# =============================================================================

from typing import Dict, List, Optional


class ADDirectoryError(Exception):
    """Empfaenger ist nicht (als Mitglied der berechtigten Gruppe) aufloesbar."""


class ADDirectory:
    """Gekapselte, mockbare AD-Leseschicht (Gruppenabgleich + Anzeigename)."""

    def __init__(self, recipients: Optional[Dict[str, str]] = None,
                 group: Optional[str] = None) -> None:
        """
        recipients — Mapping SAMAccountName -> Anzeigename der BERECHTIGTEN
                     NRW-Empfaenger. None/leer == niemand ist freigabefaehig
                     (Default-Deny).
        group      — Name der berechtigten AD-Gruppe (nur Vermerk/Anzeige).
        """
        self._group = group
        # Kanonische Ablage: Original-Schreibweise erhalten; zusaetzlich ein
        # case-insensitiver Index fuer die Aufloesung.
        self._recipients: Dict[str, str] = {}
        self._index: Dict[str, str] = {}   # lower(kennung) -> kanonische Kennung
        for kennung, display in (recipients or {}).items():
            k = str(kennung).strip()
            if not k:
                continue
            disp = str(display).strip() if display is not None else ""
            self._recipients[k] = disp or k
            self._index[k.lower()] = k

    # ---------------------------------------------------------------- Fabrik
    @classmethod
    def from_config(cls, config_path: str = "./config.yaml") -> "ADDirectory":
        """
        Baut die Schicht aus config.yaml (ad.release_recipients / ad.release_group).
        Faellt die Konfiguration aus, ist das KEIN Grund fuer eine stille
        Freigabe: die Allowlist bleibt leer (Default-Deny) und der Ausfall wird
        vom Aufrufer protokolliert.
        """
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=config_path)
        recipients = cfg.get("ad.release_recipients", {}) or {}
        if not isinstance(recipients, dict):
            raise ADDirectoryError(
                "config ad.release_recipients muss eine Zuordnung "
                "Kennung -> Anzeigename sein.")
        group = cfg.get("ad.release_group", None)
        return cls(recipients=recipients, group=group)

    # ----------------------------------------------------------------- Lesen
    @property
    def group(self) -> Optional[str]:
        return self._group

    def is_member(self, kennung: str) -> bool:
        """True, wenn 'kennung' (case-insensitiv) in der Allowlist steht."""
        return str(kennung or "").strip().lower() in self._index

    def resolve_recipient(self, kennung: str) -> Dict[str, str]:
        """
        Loest eine Empfaenger-Kennung auf. -> {'kennung', 'display_name'}.
        Unbekannt/leer -> ADDirectoryError (DEFAULT-DENY, nie stille Freigabe).
        """
        raw = str(kennung or "").strip()
        if not raw:
            raise ADDirectoryError("Empfaenger-Kennung fehlt.")
        canonical = self._index.get(raw.lower())
        if canonical is None:
            raise ADDirectoryError(
                "Kennung '%s' ist nicht in der berechtigten Gruppe%s "
                "freigegeben (Default-Deny)."
                % (raw, " '%s'" % self._group if self._group else ""))
        return {"kennung": canonical,
                "display_name": self._recipients[canonical]}

    def members(self) -> List[Dict[str, str]]:
        """Alle berechtigten Empfaenger (fuer Auswahllisten/CLI), sortiert."""
        return [{"kennung": k, "display_name": self._recipients[k]}
                for k in sorted(self._recipients)]
