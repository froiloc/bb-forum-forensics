# =============================================================================
# core/bildschleier_regel.py
# IT-Forensisches Ermittlungswerkzeug — Bildschleier (Build 772)
# =============================================================================
# Zweck:
#   Die EINE Stelle, die entscheidet, ob eine Bild-URL vom Bildschleier
#   AUSGENOMMEN ist. Alle anderen Bausteine fragen hier:
#     * core/bildschleier_seitenausnahmen.py — welche <img> einer Seite
#       unverschleiert bleiben (Build 772)
#     * core/bildschleier_css_umschreiber.py — welche url(...) in CSS
#       ersetzt werden (Build 773)
#     * server/bildschleier_huelle.py        — ob ein Direktaufruf eine
#       Huelle bekommt (Build 773)
#
# ── DIE REGEL (Alex, 09.10.2026; Bauplan §2 F5, F6, F6a, F6b) ──────────────
#
#   Ausgenommen (unverschleiert) ist eine URL GENAU DANN, wenn
#     1. sie auf dem FORENHOST liegt — relativ oder wurzelrelativ geschrieben,
#        oder absolut mit einem Host aus 'image_veil.forum_hosts', und
#     2. ihr Pfad unter einer Wurzel aus 'image_veil.roots' ("/forum/", "/")
#        mit einem Verzeichnis aus 'exempt_dirs' beginnt ("img/", "style/",
#        "v4/style/") oder genau eine Datei aus 'exempt_files' ist ("1bg.png"),
#     3. und NICHT unter einem Verzeichnis aus 'excluded_dirs' liegt
#        ("img/avatars/", "img/signatures/") — unter JEDER Wurzel.
#
#   Alles andere wird verschleiert, gleich von welcher Quelle.
#
#   WURZELN (F6a): die Dokumentwurzel des Original-Webservers ist
#   forum/html/; '/X' im Forenquelltext und '/forum/X' bezeichnen dieselbe
#   Datei. Deshalb gilt jede Ausnahme UND jeder Ausschluss unter beiden
#   Wurzeln — '/img/avatars/1.jpg' bleibt so verschleiert wie
#   '/forum/img/avatars/1.jpg'.
#
#   DER HOST ALLEIN NIMMT NIE AUS. Der Image-Hoster des Forums
#   (alicefe3...onion) liefert unter '/images/' die BB-Code-Bilder
#   (forum/html/include/parser.php Z. 523-525) — er steht deshalb gar nicht
#   in forum_hosts, und selbst ein Forenhost nimmt nur Host + Pfad aus.
#
# ── IM ZWEIFEL: VERSCHLEIERN ────────────────────────────────────────────────
#
#   Jede Schreibweise, deren Bedeutung der Browser anders aufloesen koennte
#   als diese Klasse, wird NICHT ausgenommen. Das kostet im ungluecklichsten
#   Fall ein verschleiertes Forensymbol und nie ein unverschleiertes Bild.
#   Im Einzelnen (jeweils ein Waechter in tests/test_bildschleier_regel.py):
#     * Punktsegmente '.' und '..' im aufgeloesten Pfad
#     * Prozentkodierte Punkte, Schraegstriche und Rueckstriche (%2e, %2f,
#       %5c) — der Browser dekodiert %2e zu '.', diese Klasse muesste raten
#     * Rueckstriche — der Browser liest sie in http(s) als '/'
#     * doppelte Schraegstriche im Pfad
#     * Zugangsdaten oder Port im Host ('user@host', 'host:81')
#     * jedes Schema ausser http/https (data:, blob:, javascript:, file: ...)
#     * Steuerzeichen und Leerraum IN der URL (fuehrenden und folgenden
#       Leerraum entfernt der Browser bei src selbst — hier ebenso)
#
#   Gross-/Kleinschreibung: Ausnahmen werden EXAKT verglichen, Ausschluesse
#   OHNE Ruecksicht auf die Schreibung. '/forum/img/Avatars/x.jpg' ist also
#   ausgeschlossen, '/forum/IMG/x.png' nicht ausgenommen.
#
# ── DIE UMGESCHRIEBENE FORM ─────────────────────────────────────────────────
#
#   server/blob_handler.py ersetzt bei der Auslieferung volle URLs, die in
#   assets_<uid>.db liegen, durch '/_forensic/fileasset?url=<kodiert>'
#   (_rewrite_asset_urls). Diese Form wird hier ENTPACKT und die innere URL
#   geprueft — sie ist dann immer absolut, der Host entscheidet also mit.
#
# Abhaengigkeiten: ausschliesslich Stdlib.
# Version: v0.8.772 · Build: 772 · 2026-10-09
# =============================================================================

from __future__ import annotations

import re
import urllib.parse
from typing import Any, Iterable, Optional, Tuple

from core.logger import get_logger

logger = get_logger(__name__)

#: Pfad, unter dem _rewrite_asset_urls() volle URLs ausliefert.
FILEASSET_PFAD = "/_forensic/fileasset"

#: Kunstursprung fuer die Aufloesung, wenn die Basis nur ein Pfad ist. Er
#: steht nie in forum_hosts — eine relative URL wird deshalb nicht ueber
#: den Host, sondern ueber ihre Relativitaet als 'Forenhost' erkannt.
_KUNSTURSPRUNG = "http://aiw-bildschleier.invalid"

#: Prozentkodierte Zeichen, deren Dekodierung den Pfad veraendern wuerde.
_GEFAEHRLICH_KODIERT = re.compile(r"%(?:2e|2f|5c|00)", re.IGNORECASE)
#: Steuerzeichen und Leerraum — der Browser entfernt oder ersetzt sie
#: teilweise; was er dann aufruft, weiss diese Klasse nicht sicher.
_STEUERZEICHEN = re.compile(r"[\x00-\x20\x7f]")


class BildschleierRegel:
    """Entscheidet, ob eine Bild-URL vom Schleier ausgenommen ist."""

    def __init__(
        self,
        *,
        forum_hosts: Iterable[str],
        roots: Iterable[str],
        exempt_dirs: Iterable[str],
        exempt_files: Iterable[str],
        excluded_dirs: Iterable[str],
    ) -> None:
        self._hosts = frozenset(h.strip().lower() for h in forum_hosts
                                if h and h.strip())
        self._roots = self._pruefe_wurzeln(roots)
        self._exempt_dirs = self._pruefe_teile(exempt_dirs, "exempt_dirs",
                                               verzeichnis=True)
        self._exempt_files = self._pruefe_teile(exempt_files, "exempt_files",
                                                verzeichnis=False)
        self._excluded_dirs = self._pruefe_teile(excluded_dirs,
                                                 "excluded_dirs",
                                                 verzeichnis=True)
        # Die vollstaendigen Pfadpraefixe, einmal gebildet.
        self._ausnahme_praefixe: Tuple[str, ...] = tuple(
            w + d for w in self._roots for d in self._exempt_dirs)
        self._ausnahme_dateien = frozenset(
            w + f for w in self._roots for f in self._exempt_files)
        self._ausschluss_praefixe: Tuple[str, ...] = tuple(
            (w + d).lower() for w in self._roots for d in self._excluded_dirs)

    # ------------------------------------------------------- Konstruktion ---
    @classmethod
    def aus_konfiguration(cls, config: Any) -> "BildschleierRegel":
        """Baut die Regel aus config.yaml (Abschnitt 'image_veil')."""
        def _liste(schluessel: str):
            wert = config.get("image_veil." + schluessel, None)
            if wert is None:
                return []
            if not isinstance(wert, (list, tuple)):
                raise ValueError(
                    "image_veil.%s muss eine Liste sein, erhalten: %r"
                    % (schluessel, wert))
            return [str(x) for x in wert]
        return cls(
            forum_hosts=_liste("forum_hosts"),
            roots=_liste("roots"),
            exempt_dirs=_liste("exempt_dirs"),
            exempt_files=_liste("exempt_files"),
            excluded_dirs=_liste("excluded_dirs"),
        )

    @staticmethod
    def _pruefe_wurzeln(roots: Iterable[str]) -> Tuple[str, ...]:
        ergebnis = []
        for w in roots:
            if not (w.startswith("/") and w.endswith("/")):
                raise ValueError(
                    "image_veil.roots: '%s' muss mit '/' beginnen und enden."
                    % w)
            ergebnis.append(w)
        return tuple(ergebnis)

    @staticmethod
    def _pruefe_teile(teile: Iterable[str], name: str, *,
                      verzeichnis: bool) -> Tuple[str, ...]:
        ergebnis = []
        for t in teile:
            if t.startswith("/") or ".." in t or "\\" in t:
                raise ValueError(
                    "image_veil.%s: '%s' muss relativ zur Wurzel sein "
                    "(ohne fuehrenden '/', ohne '..')." % (name, t))
            if verzeichnis and not t.endswith("/"):
                raise ValueError(
                    "image_veil.%s: '%s' muss mit '/' enden." % (name, t))
            if not verzeichnis and t.endswith("/"):
                raise ValueError(
                    "image_veil.%s: '%s' ist eine Datei, kein Verzeichnis."
                    % (name, t))
            ergebnis.append(t)
        return tuple(ergebnis)

    # ------------------------------------------------------------ Abfrage ---
    @property
    def forum_hosts(self) -> frozenset:
        return self._hosts

    def ist_ausgenommen(self, wert: Optional[str], basis: str = "/") -> bool:
        """
        True, wenn das Bild unter 'wert' UNVERSCHLEIERT gezeigt werden darf.

        wert  — der Attributwert, wie ihn der Browser sieht (Entitaeten
                bereits aufgeloest), oder eine url(...) aus CSS.
        basis — wogegen eine relative Angabe aufgeloest wird: die volle
                Seiten-URL, '<base href>' oder ein Pfad wie '/forum/'.
        """
        if wert is None:
            return False
        roh = wert.strip()
        if not roh or _STEUERZEICHEN.search(roh) or "\\" in roh:
            return False

        teile = urllib.parse.urlsplit(roh)
        # Die umgeschriebene fileasset-Form entpacken.
        if not teile.scheme and not teile.netloc \
                and teile.path == FILEASSET_PFAD:
            innen = urllib.parse.parse_qs(teile.query).get("url")
            if not innen or len(innen) != 1:
                return False
            return self._absolut_ausgenommen(innen[0])

        if teile.scheme or teile.netloc:
            # absolut oder protokollrelativ ('//host/...')
            if teile.scheme and teile.scheme.lower() not in ("http", "https"):
                return False
            if not teile.scheme:
                roh = "http:" + roh
            return self._absolut_ausgenommen(roh)

        # Relativ: gegen die Basis aufloesen. Die Basis selbst kann absolut
        # sein (volle Seiten-URL, absolutes <base href>) — dann muss IHR Host
        # ein Forenhost sein, sonst zeigt auch die relative Angabe woandershin.
        basis_teile = urllib.parse.urlsplit(basis or "/")
        if basis_teile.scheme or basis_teile.netloc:
            if not self._host_ist_forum(basis_teile):
                return False
            aufgeloest = urllib.parse.urljoin(basis, roh)
        else:
            aufgeloest = urllib.parse.urljoin(
                _KUNSTURSPRUNG + (basis if basis.startswith("/") else "/"),
                roh)
        return self._pfad_ausgenommen(urllib.parse.urlsplit(aufgeloest).path,
                                      roh)

    # ------------------------------------------------------------ intern ---
    def _host_ist_forum(self, teile: urllib.parse.SplitResult) -> bool:
        netloc = teile.netloc
        # Zugangsdaten oder Port: nicht ausnehmen (der Browser koennte einen
        # anderen Host ansprechen, als der Text auf den ersten Blick sagt).
        if "@" in netloc or ":" in netloc:
            return False
        return netloc.lower() in self._hosts

    def _absolut_ausgenommen(self, url: str) -> bool:
        if _STEUERZEICHEN.search(url) or "\\" in url:
            return False
        teile = urllib.parse.urlsplit(url)
        if teile.scheme.lower() not in ("http", "https"):
            return False
        if not self._host_ist_forum(teile):
            return False
        return self._pfad_ausgenommen(teile.path, url)

    def _pfad_ausgenommen(self, pfad: str, roh: str) -> bool:
        if not pfad.startswith("/"):
            return False
        if _GEFAEHRLICH_KODIERT.search(roh):
            return False
        if "//" in pfad:
            return False
        # Punktsegmente: bei relativen Angaben hat urljoin sie bereits so
        # aufgeloest wie der Browser (RFC 3986, remove_dot_segments); was hier
        # noch steht, stammt aus einer ABSOLUTEN Angabe, die nicht aufgeloest
        # wird — also nicht ausnehmen.
        segmente = pfad.split("/")
        if any(s in (".", "..") for s in segmente):
            return False

        klein = pfad.lower()
        for p in self._ausschluss_praefixe:
            if klein.startswith(p):
                return False
        if pfad in self._ausnahme_dateien:
            return True
        for p in self._ausnahme_praefixe:
            if pfad.startswith(p) and len(pfad) > len(p):
                return True
        return False
