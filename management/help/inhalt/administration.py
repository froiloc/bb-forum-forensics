# =============================================================================
# management/help/inhalt/administration.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H13)
# =============================================================================
# Zweck:
#   Die Hilfetexte der Nav-Gruppe "Administration". H13 (Build 604) verfasst
#   die ersten drei Kapitel: policy, integrity, audit. Die uebrigen Sichten
#   der Gruppe (handover, retention, promotion, releases) folgen in H14 und
#   kommen in DIESE Datei - eine Gruppe, eine Datei.
#
#   DAS DURCHGEHENDE THEMA DIESER DREI: das Protokollbuch. Die
#   Integritaetssicht sagt, ob es lueckenlos ist; der Explorer laesst es
#   durchblaettern; die Rechte-Sicht zeigt, wer ueberhaupt etwas hineinschreiben
#   darf. Alle drei sind REIN LESEND - keine von ihnen aendert etwas.
#
#   DIE HEIKELSTE AUSSAGE ist die Unversehrtheit. Sie ist die Grundlage dafuer,
#   dass die Arbeit dieses Werkzeugs vor Gericht Bestand hat. Deshalb sagt das
#   Integritaetskapitel im ersten Absatz, was "in Ordnung" bedeutet und was es
#   NICHT bedeutet: die Kette ist unversehrt - ob die Eintraege inhaltlich
#   richtig sind, sagt keine Pruefsumme.
#
#   SPRACHE (Regel H-1): das Protokollbuch heisst hier "Protokollbuch" und
#   seine Verkettung "lueckenlose Kette". Zwei Woerter der Oberflaeche bleiben
#   als WOERTLICHES ZITAT stehen, weil sie so auf dem Bildschirm stehen und die
#   Spalte sonst nicht auffindbar waere - siehe BILDSCHIRMZITATE in
#   management/help/pruefung.py.
#
# QUELLEN: cockpit_policy.js, cockpit_integrity.js, cockpit_audit.js,
#   management/server/management_app.py (Rechte).
#
# REGEL H-0: kein Falldatum, keine echte Kennung.
#
# Version: v0.8.604 - Build: 604 - 2026-07-31
# =============================================================================

from __future__ import annotations

from typing import Tuple

from management.help.modell import Abschnitt, Kontexthilfe, Sichthilfe

_STAND = 604


# =============================================================================
# 1) policy - "Rechte / Policy"
# =============================================================================

POLICY = Sichthilfe(
    sicht="policy",
    titel="Rechte / Policy",
    recht_klartext=(
        "Recht: policy.view. Mit dem Umfang „alle“ sehen Sie die vollständige "
        "Rechtelage der Dienststelle, sonst nur die eigene."
    ),
    anker_praefixe=("policy", "policy_grants", "policy_assign"),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Sicht beantwortet zwei Fragen: Welche Rolle darf was? "
                "Und wer hat welche Rolle?",
                "Sie ist die Stelle, an der sich nachlesen lässt, WARUM "
                "jemand etwas sehen oder tun kann — und warum jemand anderes "
                "es nicht kann. Ohne diese Sicht bliebe eine Verweigerung "
                "eine Behauptung des Werkzeugs.",
                "Die Sicht ist REIN LESEND. Rollen werden in der "
                "Personalverwaltung zugewiesen; welche Rolle welches Recht "
                "trägt, wird über die Kommandozeile gepflegt.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "policy.view. Der zugeteilte Umfang steht als Klartext unter "
                "der Überschrift: „vollständige Policy-Matrix“ oder „nur "
                "eigene Rechte“.",
                "Der Umfang „eigene“ ist kein Notbehelf, sondern der "
                "Normalfall: die eigene Rechtelage darf jede Person "
                "nachsehen, die Rechtelage aller anderen ist eine "
                "Leitungsauskunft.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift mit der Umfangszeile und den beiden Zahlen. "
                "Darunter drei Abschnitte.",
                "„Grants“ verbindet eine Rolle mit einem einzelnen Recht — "
                "mit dem Umfang, in dem es gilt, und der Belegnummer. "
                "„Rollen-Zuweisungen“ verbindet eine Person mit einer Rolle. "
                "Der „Katalog“ listet die vorhandenen Rollen und Rechte mit "
                "ihren Bezeichnungen auf.",
                "DIE KETTE IST ZWEIGLIEDRIG: Person → Rolle → Recht. Wer "
                "wissen will, warum jemand etwas darf, liest von rechts nach "
                "links.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "„Warum darf sie das?“ — im zweiten Abschnitt die Person "
                "suchen, ihre Rollen ablesen, im ersten Abschnitt nach diesen "
                "Rollen filtern.",
                "„Wer darf das?“ — im ersten Abschnitt nach dem Recht "
                "filtern, die Rollen ablesen, im zweiten Abschnitt nach ihnen "
                "suchen.",
                "„Was bedeutet dieses Kürzel?“ — der Katalog nennt zu jedem "
                "Kürzel die Bezeichnung.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "DIE SICHT ÄNDERT NICHTS. Sie zeigt die Rechtelage; geändert "
                "wird sie anderswo.",
                "DER UMFANG EINES RECHTS IST TEIL DES RECHTS. Dasselbe Recht "
                "mit dem Umfang „eigene“ und mit dem Umfang „alle“ sind zwei "
                "verschiedene Rechte — die Spalte daneben ist deshalb kein "
                "Beiwerk.",
                "WAS HIER NICHT STEHT, IST NICHT ERLAUBT. Das Werkzeug "
                "verweigert im Zweifel; es gibt keine stillen "
                "Zusatzberechtigungen.",
                "Mit dem Umfang „eigene“ ist die Liste unvollständig — das "
                "ist kein Fehler, sondern die Rechtelage. Die Zeile unter der "
                "Überschrift sagt es.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Personalverwaltung — wo Rollen zugewiesen und widerrufen "
                "werden.",
                "Protokollbuch — wann eine Rechteänderung eingetragen wurde.",
                "Unversehrtheit — ob das Protokollbuch lückenlos ist.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "policy.titel", "Rechte / Policy",
            "Zeigt, welche Rolle welches Recht trägt und wer welche Rolle "
            "hat. Rein lesend.",
            verweis="policy#zweck"),
        Kontexthilfe(
            "policy.kennzeile", "Umfang und Zahlen",
            "Nennt, ob Sie die vollständige Rechtelage sehen oder nur die "
            "eigene — und wie viele Einträge es in beiden Abschnitten gibt.",
            verweis="policy#rechte"),
        Kontexthilfe(
            "policy.abschnitt.grants", "Abschnitt „Grants“",
            "Verbindet eine Rolle mit einem einzelnen Recht, samt Umfang und "
            "Belegnummer. Hier steht, was eine Rolle darf.",
            verweis="policy#aufbau"),
        Kontexthilfe(
            "policy.abschnitt.zuweisungen", "Abschnitt „Rollen-Zuweisungen“",
            "Verbindet eine Person mit einer Rolle. Hier steht, wer eine "
            "Rolle hat.",
            verweis="policy#aufbau"),
        Kontexthilfe(
            "policy.abschnitt.katalog", "Abschnitt „Katalog“",
            "Listet die vorhandenen Rollen und Rechte mit ihren "
            "Bezeichnungen auf — die Übersetzung der Kürzel."),
        Kontexthilfe(
            "policy_grants.spalte.role_code", "Spalte „Rolle“",
            "Das Kürzel der Rolle. Der Katalog weiter unten nennt die "
            "ausgeschriebene Bezeichnung."),
        Kontexthilfe(
            "policy_grants.spalte.capability_code", "Spalte „Faehigkeit“",
            "Das Kürzel des einzelnen Rechts. Genau dieses Kürzel nennt das "
            "Werkzeug, wenn es eine Handlung verweigert.",
            verweis="policy#ablaeufe"),
        Kontexthilfe(
            "policy_grants.spalte.capability_label", "Spalte „Bezeichnung“",
            "Das Recht in Worten — was es erlaubt."),
        Kontexthilfe(
            "policy_grants.spalte.scope", "Spalte „Scope“",
            "Der Umfang, in dem das Recht gilt: „alle“ oder „eigene“. Der "
            "Umfang ist Teil des Rechts, nicht ein Zusatz dazu.",
            verweis="policy#grenzen"),
        Kontexthilfe(
            "policy_grants.spalte.audit_seq", "Spalte „Beleg“",
            "Die Nummer im Protokollbuch, unter der diese Vergabe eingetragen "
            "ist. Über sie ist im Explorer nachzulesen, wer sie wann "
            "vorgenommen hat.",
            verweis="audit#zweck"),
        Kontexthilfe(
            "policy_grants.spalte.note", "Spalte „Notiz“",
            "Der bei der Vergabe hinterlegte Vermerk, sofern einer "
            "hinterlegt wurde."),
        Kontexthilfe(
            "policy_grants.werkzeug.filter_entfernen", "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Tabelle auf einmal."),
        Kontexthilfe(
            "policy_grants.werkzeug.trefferzahl", "Trefferanzeige",
            "Nennt, wie viele Zeilen sichtbar sind; bei gesetztem Filter "
            "„sichtbar von gesamt“."),
        Kontexthilfe(
            "policy_assign.spalte.display_name", "Spalte „Person“",
            "Der Anzeigename der Person, der die Rolle zugewiesen ist."),
        Kontexthilfe(
            "policy_assign.spalte.system_username", "Spalte „Kennung“",
            "Der Anmeldename derselben Person."),
        Kontexthilfe(
            "policy_assign.spalte.role_code", "Spalte „Rolle“",
            "Die zugewiesene Rolle. Was sie erlaubt, steht im Abschnitt "
            "darüber.",
            verweis="policy#ablaeufe"),
        Kontexthilfe(
            "policy_assign.spalte.audit_seq", "Spalte „Beleg“",
            "Die Nummer im Protokollbuch, unter der diese Zuweisung "
            "eingetragen ist.",
            verweis="audit#zweck"),
        Kontexthilfe(
            "policy_assign.werkzeug.filter_entfernen", "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Tabelle auf einmal."),
        Kontexthilfe(
            "policy_assign.werkzeug.trefferzahl", "Trefferanzeige",
            "Nennt, wie viele Zeilen sichtbar sind; bei gesetztem Filter "
            "„sichtbar von gesamt“."),
    ),
)


# =============================================================================
# 2) integrity - "Integritaet / Betrieb"
# =============================================================================

INTEGRITY = Sichthilfe(
    sicht="integrity",
    titel="Integrität / Betrieb",
    recht_klartext=(
        "Recht: ops.view — dasselbe wie für das Protokollbuch. Ohne dieses "
        "Recht bleibt auch die Anzeige am oberen Rand still."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Diese Sicht beantwortet die Frage, von der alles andere "
                "abhängt: Ist das Protokollbuch lückenlos?",
                "Jeder Eintrag trägt eine Prüfsumme, die den vorhergehenden "
                "Eintrag einschließt. Dadurch entsteht eine Kette: Wird ein "
                "Eintrag nachträglich verändert oder entfernt, passt die "
                "Kette ab dieser Stelle nicht mehr. Genau das misst diese "
                "Sicht.",
                "„IN ORDNUNG“ HEISST: DIE KETTE IST UNVERSEHRT. Es heißt "
                "NICHT, dass die Einträge inhaltlich richtig sind — das kann "
                "keine Prüfsumme sagen. Sie sagt nur, dass niemand "
                "nachträglich daran gearbeitet hat.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "ops.view. Wer das Recht hat, sieht die Anzeige am oberen "
                "Rand jeder Sicht und kann hier die Einzelheiten nachlesen.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, Hinweiszeile und eine Karte mit vier Angaben: "
                "der Zustand mit Ampelpunkt, die Spitze der Kette, die erste "
                "fehlerhafte Stelle und der ausführliche Befund.",
                "Dieselbe Aussage steht durchgehend am oberen Rand des "
                "Werkzeugs. Sie ist dort absichtlich immer sichtbar: eine "
                "Unversehrtheit, die man erst suchen muss, ist keine "
                "Zusicherung.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Vor jeder Berichtsabgabe: den Zustand ansehen. Ein Bericht "
                "auf einer gebrochenen Kette ist angreifbar.",
                "Bei einem Bruch: die genannte Stelle notieren und die "
                "Ermittlungsleitung sowie den technischen Betrieb "
                "unterrichten — sofort und BEVOR weitergearbeitet wird.",
                "Zum Nachvollziehen: die genannte Stelle im Protokollbuch "
                "aufschlagen; der Explorer lässt sich auf einen "
                "Nummernbereich einstellen.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "DIE PRÜFUNG SAGT NICHTS ÜBER DEN INHALT. Sie sagt, dass "
                "nichts nachträglich verändert wurde — nicht, dass alles "
                "richtig eingetragen wurde.",
                "EIN BRUCH IST KEIN ANZEIGEFEHLER. Er ist ein Vorfall und "
                "gehört gemeldet. Auch wenn die genannte Stelle unbekannt "
                "bleibt, wird das ausgewiesen und nicht verschwiegen.",
                "Die Sicht REPARIERT NICHTS. Sie kann es auch nicht: das "
                "Protokollbuch lässt sich nur ergänzen, nicht ändern — und "
                "genau darauf beruht seine Beweiskraft.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Protokollbuch — die Einträge selbst.",
                "Rechte / Policy — wer überhaupt etwas eintragen darf.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "integrity.titel", "Integrität / Betrieb",
            "Zeigt, ob das Protokollbuch lückenlos ist. Das ist die "
            "Grundlage der Beweiskraft aller hier festgehaltenen Arbeit.",
            verweis="integrity#zweck"),
        Kontexthilfe(
            "integrity.kennzeile", "Was geprüft wird",
            "Jeder Eintrag schließt den vorhergehenden in seine Prüfsumme "
            "ein. Wird nachträglich etwas verändert, passt die Kette ab "
            "dieser Stelle nicht mehr.",
            verweis="integrity#zweck"),
        Kontexthilfe(
            "integrity.status", "Zustand der Kette",
            "Grün heißt: unversehrt. Rot heißt: ab einer bestimmten Stelle "
            "passt die Kette nicht mehr — ein Vorfall, kein Anzeigefehler.",
            verweis="integrity#grenzen"),
        Kontexthilfe(
            "integrity.kettenspitze", "Spitze der Kette",
            "Die Nummer des jüngsten Eintrags. Bis hierhin wurde geprüft."),
        Kontexthilfe(
            "integrity.erster_fehler", "Erste fehlerhafte Stelle",
            "Ab welcher Nummer die Kette nicht mehr passt. Ein Gedankenstrich "
            "heißt: es gibt keine solche Stelle.",
            verweis="integrity#ablaeufe"),
        Kontexthilfe(
            "integrity.detail", "Befund im Wortlaut",
            "Der ausführliche Befund der Prüfung. Bei einer Meldung an den "
            "technischen Betrieb gehört dieser Wortlaut dazu."),
    ),
)


# =============================================================================
# 3) audit - "Audit-Explorer"
# =============================================================================

AUDIT = Sichthilfe(
    sicht="audit",
    titel="Protokollbuch (Audit-Explorer)",
    recht_klartext=(
        "Recht: ops.view — dasselbe wie für die Unversehrtheit. Die Sicht ist "
        "rein lesend; einen Schreibweg gibt es nicht."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Das Protokollbuch hält jede Handlung fest, die im Werkzeug "
                "etwas verändert: wer, wann, woran, mit welchem Inhalt. Diese "
                "Sicht lässt es durchblättern und einschränken.",
                "Es lässt sich nur ERGÄNZEN, nicht ändern und nicht löschen. "
                "Darauf beruht seine Beweiskraft — und deshalb gibt es hier "
                "keinen Schreibweg.",
                "Fast jede andere Sicht nennt zu einem Vorgang eine "
                "Belegnummer. Hier ist die Stelle, an der sich diese Nummer "
                "aufschlagen lässt.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "ops.view. Das Protokollbuch enthält Angaben aus allen "
                "Verfahren; das Recht ist deshalb nicht auf die eigenen Fälle "
                "eingeschränkt und wird entsprechend zurückhaltend vergeben.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, Hinweiszeile, dann die Filterleiste: Ereignis, "
                "handelnde Person, Art des Ziels und ein Nummernbereich. "
                "Daneben die beiden Knöpfe „Filtern“ und „Gerichtsfester "
                "Export“.",
                "Darunter die Trefferzeile, die Liste mit sechs Spalten und "
                "die Blätterknöpfe. Die Liste zeigt die jüngsten Einträge "
                "zuerst.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Eine Belegnummer aufschlagen: dieselbe Zahl in „seq ab“ und "
                "„seq bis“ eintragen und filtern.",
                "Einen Vorgang nachvollziehen: nach der handelnden Person "
                "und einem Zeitraum einschränken und die Einträge der Reihe "
                "nach lesen.",
                "Für die Akte: „Gerichtsfester Export“. Er bildet GENAU die "
                "eingestellte Auswahl ab und trägt eine Prüfsumme sowie den "
                "Stand der Unversehrtheit.",
                "Blättern: „‹ Neuere“ und „Aeltere ›“. Ist ein Knopf grau, "
                "gibt es in diese Richtung nichts mehr.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "DIE SICHT ÄNDERT NICHTS UND KANN NICHTS ÄNDERN. Es gibt "
                "keinen Schreibweg; das Protokollbuch nimmt nur Ergänzungen "
                "an.",
                "EINE LEERE LISTE HEISST „NICHTS FÜR DIESE EINSCHRÄNKUNG“ — "
                "nicht „nichts geschehen“. Die Sicht sagt das ausdrücklich. "
                "Bevor Sie daraus etwas schließen, prüfen Sie die "
                "Filterleiste.",
                "DER EXPORT BILDET DIE EINGESTELLTE AUSWAHL AB, nicht das "
                "ganze Buch. Was Sie ausgeblendet haben, ist auch im Export "
                "nicht enthalten — das ist gewollt, muss aber bei der "
                "Verwendung mitgedacht werden.",
                "Die Zeitangaben stehen in UTC — bewusst, weil eine Zeitzone, "
                "die vom Arbeitsplatz abhängt, in einer Akte nicht "
                "nachprüfbar wäre.",
                "Die letzte Spalte zeigt den Inhalt des Eintrags GEKÜRZT. "
                "Für den vollen Wortlaut ist der Export zu nehmen.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Unversehrtheit — ob die Kette lückenlos ist.",
                "Rechte / Policy — wer eintragen darf.",
                "Meine Historie — die eigenen Einträge, ohne Umweg über die "
                "Einschränkung.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "audit.titel", "Protokollbuch",
            "Jede verändernde Handlung des Werkzeugs mit Person, Zeitpunkt "
            "und Inhalt. Rein lesend — Einträge lassen sich nur ergänzen.",
            verweis="audit#zweck"),
        Kontexthilfe(
            "audit.kennzeile", "Was das Protokollbuch ist",
            "Weist auf zweierlei hin: es wird nur ergänzt, und der Export "
            "trägt eine Prüfsumme sowie den Stand der Unversehrtheit.",
            verweis="audit#grenzen"),
        Kontexthilfe(
            "audit.trefferzeile", "Trefferzeile",
            "Wie viele Einträge die Einschränkung durchlässt und welcher "
            "Ausschnitt davon gerade angezeigt wird.",
            verweis="audit#grenzen"),
        Kontexthilfe(
            "audit.bedienung.ereignis", "Ereignis",
            "Schränkt auf eine Art von Handlung ein. Angeboten wird, was im "
            "Bestand tatsächlich vorkommt."),
        Kontexthilfe(
            "audit.bedienung.akteur", "Akteur",
            "Schränkt auf eine handelnde Person ein."),
        Kontexthilfe(
            "audit.bedienung.zieltyp", "Ziel-Typ",
            "Schränkt auf eine Art von Gegenstand ein — etwa Fall, Bericht "
            "oder Person."),
        Kontexthilfe(
            "audit.bedienung.seq_von", "seq ab",
            "Untere Grenze des Nummernbereichs. Für einen einzelnen Beleg "
            "dieselbe Zahl hier und bei „seq bis“ eintragen.",
            verweis="audit#ablaeufe"),
        Kontexthilfe(
            "audit.bedienung.seq_bis", "seq bis",
            "Obere Grenze des Nummernbereichs."),
        Kontexthilfe(
            "audit.bedienung.filtern", "Filtern",
            "Wendet die eingestellte Einschränkung an. Erst danach zeigt die "
            "Liste die neue Auswahl."),
        Kontexthilfe(
            "audit.bedienung.export", "Gerichtsfester Export",
            "Erzeugt aus GENAU der eingestellten Auswahl ein in sich "
            "geschlossenes Dokument mit Prüfsumme, Erzeugungsvermerk und dem "
            "Stand der Unversehrtheit.",
            verweis="audit#grenzen"),
        Kontexthilfe(
            "audit.bedienung.neuere", "Neuere",
            "Blättert zu den jüngeren Einträgen. Grau heißt: Sie sind bereits "
            "am Anfang."),
        Kontexthilfe(
            "audit.bedienung.aeltere", "Ältere",
            "Blättert zu den älteren Einträgen. Grau heißt: es gibt keine "
            "weiteren."),
    ),
)


#: Der Teilbestand dieser Nav-Gruppe. H13 (Build 604) verfasst die ersten
#: drei Kapitel; handover, retention, promotion und releases folgen in H14
#: und kommen in diese Datei.
ADMINISTRATION: Tuple[Sichthilfe, ...] = (POLICY, INTEGRITY, AUDIT)
