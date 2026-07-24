# =============================================================================
# management/external/ldap_group_reader.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AD-Schicht (Build 501)
# =============================================================================
# Zweck:
#   LIVE-Leseschicht auf das Active Directory fuer den AD-Abgleich der
#   Ermittlerstammdaten (Bauplan Build501_502 §3). Liefert die Mitglieder der
#   konfigurierten Ermittler-Gruppe (rekursiv, inkl. verschachtelter Gruppen)
#   als Liste {sam, display_name}.
#
#   Die Logik ist die 1:1-Uebernahme des in der PROD-Umgebung verifizierten
#   PoC 'get-members4.py' (Beleg: Projektgespraech 2026-07-24):
#     1. DC-Ermittlung ueber ms_active_directory.ADDomain(domain).get_ldap_uris()
#     2. Bind per Kerberos/SSPI (ldap3 SASL/GSSAPI) — KEINE Zugangsdaten in
#        Konfiguration oder Code; es wirkt die angemeldete Windows-Sitzung.
#     3. Gruppen-DN per (&(objectClass=group)(cn=<target_group>)) unter base_dn.
#     4. Mitglieder REKURSIV per AD-Matching-Rule 1.2.840.113556.1.4.1941
#        (LDAP_MATCHING_RULE_IN_CHAIN) unter user_base — loest auch
#        verschachtelte Gruppen (SEC -> VR -> Benutzer) auf.
#
# Bewusste Entwurfsentscheidungen:
#   - NUR LESEND. Es gibt keinen Schreibpfad ins AD.
#   - Muster F4 (ad_directory.py / identity.py): die Aufrufer (SyncExecutor,
#     CLI, Management-Server) erhalten den Reader INJIZIERT und mocken ihn in
#     Tests. KEIN Live-LDAP in Tests.
#   - LAZY IMPORTS: ldap3/ms_active_directory werden erst in fetch_members()
#     importiert, damit Dev-/Testumgebungen ohne diese Pakete das Modul laden
#     koennen (die Pakete stehen seit Build 500 in requirements.txt, sind aber
#     nur in der Windows-PROD-VM funktionsfaehig — winkerberos/SSPI).
#   - JEDER Fehlschlag (Konfiguration leer, kein DC, Bind-/Suchfehler, Gruppe
#     nicht gefunden) => LdapError mit Klartext. NIE stilles Weiterlaufen,
#     nie stilles leeres Ergebnis (Grundregel 1) — eine faelschlich leere
#     Antwort wuerde sonst alle Ermittler zu Entfernungs-Kandidaten machen.
#   - Leerer displayName im AD faellt NICHT hier auf den sam zurueck; das ist
#     Sache des Planners (sync_plan.py), damit die Regel an genau einer Stelle
#     liegt und rein testbar ist.
#
# Version: v0.8.501 · Build: 501 · 2026-07-24
# =============================================================================

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

#: AD-Matching-Rule fuer rekursive Gruppenmitgliedschaft
#: (LDAP_MATCHING_RULE_IN_CHAIN, wie im PoC get-members4.py).
MATCHING_RULE_IN_CHAIN = "1.2.840.113556.1.4.1941"

#: Die vier Pflicht-Konfigurationsschluessel unter ad.ldap.* (Bauplan §2).
REQUIRED_KEYS = ("domain_dns_name", "base_dn", "user_base", "target_group")


class LdapError(Exception):
    """AD-Zugriff fehlgeschlagen oder nicht konfiguriert (Klartext-Grund)."""


class LdapGroupReader:
    """Gekapselte, injizierbare Live-Leseschicht: Gruppenmitglieder aus dem AD."""

    def __init__(self, domain_dns_name: str, base_dn: str,
                 user_base: str, target_group: str) -> None:
        """
        Wirft LdapError, wenn einer der vier Parameter leer ist (DEFAULT-DENY —
        ein Abgleich ohne vollstaendige Konfiguration darf nie starten).
        """
        values = {
            "domain_dns_name": (domain_dns_name or "").strip(),
            "base_dn": (base_dn or "").strip(),
            "user_base": (user_base or "").strip(),
            "target_group": (target_group or "").strip(),
        }
        missing = [k for k in REQUIRED_KEYS if not values[k]]
        if missing:
            raise LdapError(
                "AD-Abgleich nicht konfiguriert: ad.ldap.%s in config.yaml "
                "ist leer. Alle vier Werte (%s) sind Pflicht."
                % (", ad.ldap.".join(missing), ", ".join(REQUIRED_KEYS)))
        self._domain = values["domain_dns_name"]
        self._base_dn = values["base_dn"]
        self._user_base = values["user_base"]
        self._target_group = values["target_group"]

    # ---------------------------------------------------------------- Fabrik
    @classmethod
    def from_config(cls, config_path: str = "./config.yaml") -> "LdapGroupReader":
        """Baut den Reader aus config.yaml (ad.ldap.*, Bauplan §2)."""
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=config_path)
        return cls(
            domain_dns_name=cfg.get("ad.ldap.domain_dns_name", "") or "",
            base_dn=cfg.get("ad.ldap.base_dn", "") or "",
            user_base=cfg.get("ad.ldap.user_base", "") or "",
            target_group=cfg.get("ad.ldap.target_group", "") or "",
        )

    # ----------------------------------------------------------------- Lesen
    @property
    def target_group(self) -> str:
        """Name der konfigurierten Ermittler-Gruppe (fuer Belege/Anzeige)."""
        return self._target_group

    def fetch_members(self) -> List[Dict[str, str]]:
        """
        Liest die Mitglieder der Zielgruppe (rekursiv) aus dem AD.

        Rueckgabe: Liste von {"sam": <sAMAccountName>, "display_name":
        <displayName oder "">}. Reihenfolge wie vom Server geliefert.
        Wirft LdapError bei JEDEM Fehlschlag (kein stilles leeres Ergebnis).
        """
        # Lazy Imports (siehe Kopfkommentar): erst hier, nicht beim Modul-Load.
        try:
            from ldap3 import Server, Connection, SASL, GSSAPI, SUBTREE
            from ldap3.utils.conv import escape_filter_chars
            from ms_active_directory import ADDomain
        except ImportError as exc:
            raise LdapError(
                "LDAP-Pakete nicht installiert (ldap3/ms_active_directory, "
                "requirements.txt seit Build 500): %s" % exc) from exc

        conn = None
        try:
            # 1. DC ueber die Domaene ermitteln (wie PoC).
            try:
                domain = ADDomain(self._domain)
                ldap_uris = domain.get_ldap_uris()
            except Exception as exc:
                raise LdapError(
                    "AD-Server fuer Domaene %r nicht ermittelbar: %s"
                    % (self._domain, exc)) from exc
            if not ldap_uris:
                raise LdapError(
                    "AD-Server fuer Domaene %r nicht ermittelbar "
                    "(leere LDAP-URI-Liste)." % self._domain)
            ldap_uri = ldap_uris[0]
            logger.debug("LdapGroupReader: verwende Server %s "
                         "(Kandidaten: %s)", ldap_uri, ldap_uris)

            # 2. Kerberos/SSPI-Bind (wie PoC: ohne session_security — der in
            #    der PROD-Umgebung verifizierte Stand).
            try:
                conn = Connection(
                    Server(ldap_uri),
                    authentication=SASL,
                    sasl_mechanism=GSSAPI,
                    auto_bind=True,
                    auto_referrals=False,
                )
            except Exception as exc:
                raise LdapError(
                    "LDAP-Bind an %s fehlgeschlagen (Kerberos/SSPI): %s"
                    % (ldap_uri, exc)) from exc

            # 3. Gruppen-DN aufloesen.
            group_filter = (
                "(&(objectClass=group)(cn=%s))"
                % escape_filter_chars(self._target_group))
            ok = conn.search(
                search_base=self._base_dn,
                search_filter=group_filter,
                search_scope=SUBTREE,
                attributes=["cn"],
            )
            if not ok:
                # conn.result enthaelt den wahren Grund (z. B.
                # strongerAuthRequired, referral) — in den Klartext uebernehmen.
                raise LdapError(
                    "Gruppensuche fehlgeschlagen: %s" % (conn.result,))
            if not conn.entries:
                raise LdapError(
                    "AD-Gruppe %r unter %r nicht gefunden "
                    "(Server-Antwort: %s)."
                    % (self._target_group, self._base_dn, conn.result))
            group_dn = conn.entries[0].entry_dn
            logger.debug("LdapGroupReader: Gruppe gefunden: %s", group_dn)

            # 4. Mitglieder rekursiv ueber die Matching-Rule.
            user_filter = (
                "(&(objectClass=user)(memberOf:%s:=%s))"
                % (MATCHING_RULE_IN_CHAIN, escape_filter_chars(group_dn)))
            ok = conn.search(
                search_base=self._user_base,
                search_filter=user_filter,
                search_scope=SUBTREE,
                attributes=["displayName", "sAMAccountName"],
            )
            if not ok:
                raise LdapError(
                    "Benutzersuche fehlgeschlagen: %s" % (conn.result,))

            members: List[Dict[str, str]] = []
            for entry in conn.entries:
                sam = (str(entry.sAMAccountName)
                       if "sAMAccountName" in entry else "")
                display = (str(entry.displayName)
                           if "displayName" in entry else "")
                if not sam.strip():
                    # Ein Benutzerobjekt ohne sAMAccountName ist nicht
                    # abbildbar (person.system_username ist die Identitaet) —
                    # NIE still ueberspringen (Grundregel 1).
                    raise LdapError(
                        "AD-Eintrag %r ohne sAMAccountName — Abgleich "
                        "abgebrochen." % entry.entry_dn)
                members.append({"sam": sam.strip(),
                                "display_name": display.strip()})
            logger.info("LdapGroupReader: %d Mitglieder in %r gelesen.",
                        len(members), self._target_group)
            return members
        finally:
            if conn is not None and conn.bound:
                conn.unbind()
