# =============================================================================
# management/help/inhalt/administration.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H13)
# =============================================================================
# Zweck:
#   Die Hilfetexte der Nav-Gruppe "Administration" - VOLLSTAENDIG seit Build
#   605: policy, integrity, audit (H13) sowie handover, retention, promotion,
#   releases (H14). Eine Gruppe, eine Datei.
#
#   MIT DIESER DATEI IST DIE FEHLLISTE LEER: alle 43 Sichten haben ein
#   Kapitel.
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
# Version: v0.8.605 - Build: 605 - 2026-07-31
# =============================================================================

from __future__ import annotations

from typing import Tuple

from management.help.modell import Abschnitt, Kontexthilfe, Sichthilfe

_STAND = 604

#: H14 (Build 605): die vier nachgetragenen Kapitel dieser Gruppe.
_STAND_H14 = 605


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
                "DIE SICHT PRÜFT NICHT, OB DIE EINTRÄGE ZUSAMMENPASSEN. Ein "
                "Grant kann auf ein Recht zeigen, das der „Katalog“ weiter "
                "unten gar nicht führt — dann steht es oben und fehlt unten, "
                "und niemand fällt darüber. Dass es so etwas gibt, ist am "
                "13.08.2026 aufgefallen. Wer das nachsehen will, fährt auf "
                "der Kommandozeile „Rechte-Matrix auf Verweise ins Leere "
                "prüfen“; das Werkzeug liest nur und nennt zu jedem Fund den "
                "Beleg.",
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
                "Rechte-Matrix auf Verweise ins Leere prüfen "
                "(Kommandozeile) — ob ein Grant auf eine Rolle, ein Recht "
                "oder einen Beleg zeigt, den es nicht gibt.",
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



# =============================================================================
# 4) handover - "Uebergabe-Protokoll"
# =============================================================================

HANDOVER = Sichthilfe(
    sicht="handover",
    titel="Übergabe-Protokoll",
    recht_klartext=(
        "Recht: handover.view. Die Sicht ist rein lesend; sie übergibt keinen "
        "Fall und ändert keine Zuständigkeit."
    ),
    stand=_STAND_H14,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Das Protokoll beantwortet: Wer hat wann welchen Fall an wen "
                "übergeben — und wer hat es veranlasst?",
                "Es wird bei jedem Aufruf NEU aus dem Protokollbuch "
                "zusammengesetzt. Es gibt kein zweites Verzeichnis, das von "
                "der Fallakte abweichen könnte, und nichts an dieser Liste "
                "lässt sich nachträglich zurechtrücken.",
                "Jede Zeile trägt ihre Belegnummer. Das macht sie prüfbar: "
                "mit dieser Nummer lässt sich der Vorgang im Protokollbuch "
                "aufschlagen.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "handover.view. Das Protokoll umfasst alle Fälle; es ist "
                "nicht auf die eigene Zuständigkeit eingeschränkt.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter eine Zeile, die den gezeigten "
                "Ausschnitt benennt und die beiden Zahlen nennt. Dann die "
                "Einschränkung auf eine Fallnummer und die Liste.",
                "Die Liste hat sieben Spalten: Beleg, Zeitpunkt, Fall, Art, "
                "von, an und „veranlasst von“. Die JÜNGSTE Übergabe steht "
                "oben.",
                "Es gibt drei Arten: Erstzuweisung, Übergabe und Rückgabe in "
                "den Rückstau. Unter der Liste steht, woher die Angaben "
                "stammen.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Einen Fall verfolgen: die Fallnummer eintragen und "
                "„Einschränken“. Sie sehen dann seine ganze Kette.",
                "Zur Gesamtsicht zurück: „Alle Fälle“.",
                "Eine Angabe belegen: die Belegnummer der Zeile im "
                "Protokollbuch aufschlagen.",
                "„Wer hat das entschieden?“ — die letzte Spalte lesen. Sie "
                "nennt oft eine dritte Person: die Leitung, die die Übergabe "
                "veranlasst hat.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "EINE LEERE SPALTE „VON“ IST KEINE LÜCKE. Bei einer "
                "Erstzuweisung gab es keinen Vorgänger; dort steht „(aus dem "
                "Rückstau)“. Ebenso bei einer Rückgabe: dort gibt es keinen "
                "Empfänger.",
                "EIN EINGESCHRÄNKTES PROTOKOLL IST EIN AUSSCHNITT. Die Zeile "
                "über der Liste sagt das, und die beiden Zahlen beziehen sich "
                "dann ausdrücklich nur auf diesen Ausschnitt — sonst sähe ein "
                "Ausschnitt wie ein vollständiges Protokoll mit wenigen "
                "Einträgen aus.",
                "„KEINE ÜBERGABE ZU DIESEM FALL“ HEISST NICHT, DASS ES DEN "
                "FALL NICHT GIBT. Es heißt: zu ihm ist kein Zuweisungsbeleg "
                "eingetragen.",
                "Lässt sich das Protokoll nicht abrufen, sagt die Sicht das "
                "ausdrücklich. Das ist KEIN Leerbefund — es ist dann "
                "unbekannt, ob Übergaben stattgefunden haben.",
                "Die Reihenfolge wird nicht verändert. Sie ist die des "
                "Protokollbuchs, und eine zweite Sortierung wäre eine zweite "
                "Auskunft über dieselbe Sache.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Zuweisung — wo Zuständigkeiten geändert werden.",
                "Protokollbuch — der Beleg zu jeder Zeile.",
                "Onboarding / Offboarding — warum eine Übergabe nötig wurde.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "handover.titel", "Übergabe-Protokoll",
            "Wer hat wann welchen Fall an wen übergeben. Aus dem "
            "Protokollbuch zusammengesetzt und deshalb nicht nachträglich "
            "veränderbar.",
            verweis="handover#zweck"),
        Kontexthilfe(
            "handover.kennzeile", "Ausschnitt und Zahlen",
            "Nennt, ob Sie alle Fälle oder nur einen sehen — und wie viele "
            "Übergaben in wie vielen Fällen im GEZEIGTEN AUSSCHNITT liegen.",
            verweis="handover#grenzen"),
        Kontexthilfe(
            "handover.bedienung.fallnummer", "Fallnummer",
            "Schränkt das Protokoll auf einen einzelnen Fall ein. Der "
            "Ausschnitt wird nie stillschweigend gewechselt.",
            verweis="handover#ablaeufe"),
        Kontexthilfe(
            "handover.bedienung.einschraenken", "Einschränken",
            "Wendet die eingetragene Fallnummer an."),
        Kontexthilfe(
            "handover.bedienung.alle", "Alle Fälle",
            "Hebt die Einschränkung auf und zeigt wieder das ganze "
            "Protokoll."),
        Kontexthilfe(
            "handover.herkunft", "Herkunft der Angaben",
            "Erklärt, warum dieses Protokoll nicht manipulierbar ist: es wird "
            "bei jedem Aufruf neu aus dem Protokollbuch zusammengesetzt.",
            verweis="handover#zweck"),
    ),
)


# =============================================================================
# 5) retention - "Aufbewahrungsfristen"
# =============================================================================

RETENTION = Sichthilfe(
    sicht="retention",
    titel="Aufbewahrungsfristen",
    recht_klartext=(
        "Recht: retention.view. Die Sicht ist rein lesend — und zwar "
        "notwendigerweise: sie hat keinen Weg, etwas zu löschen."
    ),
    stand=_STAND_H14,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "DIESE SICHT IST EIN PRÜFVORSCHLAG. Sie zeigt, welche "
                "abgeschlossenen Fälle die Aufbewahrungsfrist überschritten "
                "haben. SIE LÖSCHT NICHTS UND KANN NICHTS LÖSCHEN: dafür gibt "
                "es im Werkzeug keinen Weg.",
                "Das Löschen von Beweismitteln ist eine Entscheidung "
                "außerhalb dieses Werkzeugs. Diese Liste ist eine Vorlage für "
                "diese Entscheidung — kein Arbeitsauftrag.",
                "Der Vorbehalt steht deshalb ganz oben in der Sicht und nicht "
                "als Fußnote. Fehlt er einmal, MELDET die Sicht das "
                "ausdrücklich: eine unbelegte Beruhigung wäre hier schlimmer "
                "als gar keine.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "retention.view. Es gibt kein zugehöriges Änderungsrecht, "
                "weil es keine Änderung gibt.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter der Löschvorbehalt in eigener "
                "Auszeichnung, dann die Zahlenzeile und die Liste. Ganz unten "
                "die angewandte Frist.",
                "Die Liste hat sechs Spalten: Fall, Status, Bezugsfeld, "
                "Bezugszeitpunkt, aufbewahrt und „über der Frist“. Die "
                "stärkste Überschreitung steht oben.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Die Liste durchsehen und der Ermittlungsleitung als Vorlage "
                "geben.",
                "Vor jeder Bewertung die Zahl der UNGEPRÜFTEN Fälle lesen — "
                "sie steht in der Zahlenzeile.",
                "Bei einer Zeile prüfen, ab welchem Zeitpunkt gerechnet "
                "wurde: das Bezugsfeld steht daneben.",
                "Die angewandte Frist unten mitlesen. „742 Tage aufbewahrt“ "
                "ist erst zusammen mit ihr eine Aussage.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "HIER WIRD NICHTS GELÖSCHT UND HIER KANN NICHTS GELÖSCHT "
                "WERDEN. Es gibt keinen Knopf, keine Auswahl und keinen "
                "Schreibweg.",
                "„OHNE ERMITTELBAREN BEZUGSZEITPUNKT“ HEISST UNGEPRÜFT — "
                "weder Kandidat noch unverdächtig. Diese Zahl ist die "
                "wichtigste der Sicht: ohne sie sähe eine kurze Liste wie "
                "eine vollständige Prüfung aus.",
                "EIN LEERBEFUND IST NICHT „ALLES IN ORDNUNG“. Er heißt: kein "
                "Fall über der Frist — bei den Fällen, die sich prüfen "
                "ließen. Die Sicht nennt beim Leerbefund ausdrücklich, wie "
                "viele sich NICHT prüfen ließen.",
                "DAS BEZUGSFELD ÄNDERT DAS ERGEBNIS. Ob die Frist ab der "
                "Freigabe oder ab der letzten Änderung läuft, ist eine "
                "nachprüfbare Tatsache und keine Nebensache; sie steht "
                "deshalb in jeder Zeile.",
                "Lässt sich die Übersicht nicht abrufen, sagt die Sicht das "
                "ausdrücklich. Es ist dann UNBEKANNT, ob Fristen "
                "überschritten sind.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Fallübersicht — der Stand der Fälle.",
                "Fristen (Verjährung) — die andere Frist, die dieses Werkzeug "
                "kennt; sie hat mit dieser nichts zu tun.",
                "Protokollbuch — wann ein Fall abgeschlossen wurde.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "retention.titel", "Aufbewahrungsfristen",
            "Zeigt, welche abgeschlossenen Fälle die Aufbewahrungsfrist "
            "überschritten haben. Ein Prüfvorschlag — kein Arbeitsauftrag.",
            verweis="retention#zweck"),
        Kontexthilfe(
            "retention.vorbehalt", "Löschvorbehalt",
            "Die Zusicherung, dass diese Sicht nichts löscht und nichts "
            "löschen kann. Steht dort stattdessen eine Warnung, ist die "
            "Herkunft der Liste zu klären, BEVOR jemand mit ihr arbeitet.",
            verweis="retention#grenzen"),
        Kontexthilfe(
            "retention.kennzeile", "Die vier Zahlen",
            "Wie viele Fälle über der Frist liegen, wie viele sich MANGELS "
            "BEZUGSZEITPUNKT NICHT PRÜFEN LIESSEN, wie viele abgeschlossen "
            "sind und wie viele es insgesamt gibt.",
            verweis="retention#grenzen"),
        Kontexthilfe(
            "retention.frist", "Angewandte Frist",
            "Der Maßstab, gegen den gerechnet wurde. Ohne ihn ist keine "
            "Angabe dieser Sicht einzuordnen — auch ein Leerbefund nicht.",
            verweis="retention#ablaeufe"),
    ),
)


# =============================================================================
# 6) promotion - "Fremdforum-Promotion"
# =============================================================================

PROMOTION = Sichthilfe(
    sicht="promotion",
    titel="Fremdforum-Promotion",
    recht_klartext=(
        "Rechte: ops.view zum Lesen, ops.promote zum Entscheiden. Ohne das "
        "Entscheidungsrecht zeigt die Sicht den Stand, bietet aber keine "
        "Aktion an."
    ),
    stand=_STAND_H14,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Ein Kandidat ist ein Fall, zu dem die Aufbereitung Material "
                "geliefert hat, zu dem es aber noch keinen Arbeitsstand gibt. "
                "Jemand muss entscheiden, ob er in die eigene Ermittlung "
                "übernommen wird.",
                "Diese Entscheidung wurde bisher stillschweigend getroffen — "
                "dadurch, dass jemand anfing zu arbeiten oder eben nicht. "
                "Hier wird sie sichtbar, begründet und festgehalten.",
                "ZWEI ZUSTÄNDE SIND ENDGÜLTIG: „in Ermittlung übernommen“ und "
                "„fremdzuständig“. Aus ihnen führt kein Weg zurück. Ein "
                "Irrtum wird durch eine NEUE Entscheidung berichtigt, nicht "
                "durch Zurücknehmen.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "ops.view zum Lesen. Das Entscheiden braucht ops.promote — es "
                "ist eine Leitungshandlung. Ohne dieses Recht steht in der "
                "Aktionsspalte kein Knopf, und die Sicht sagt das ausdrücklich.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, Hinweiszeile, dann fünf Zähler — einer je "
                "Zustand. Darunter die Zeile für Rückmeldungen, das "
                "Entscheidungsfeld und die Liste.",
                "DIE LISTE IST NACH HANDLUNGSBEDARF GEORDNET: offen, "
                "gesichtet, zurückgestellt, übernommen, fremdzuständig. Das "
                "ist keine alphabetische Ordnung, und das ist Absicht — "
                "alphabetisch stünde der Endzustand vor dem Handlungsbedarf.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Durchsicht: die offenen Kandidaten von oben abarbeiten.",
                "Vormerken: „Als gesichtet markieren“ — das hält fest, dass "
                "jemand hingesehen hat, ohne schon zu entscheiden.",
                "Übernehmen oder abgeben: „Uebernehmen“ bzw. "
                "„Fremdzustaendig“. Beides ist ENDGÜLTIG; die Sicht warnt vor "
                "dem Bestätigen ausdrücklich.",
                "Vertagen: „Zurueckstellen“, mit Pflichtgrund. Dieser Zustand "
                "lässt sich später ändern.",
                "Die Herkunft eintragen, wenn sie bekannt ist — sie sagt "
                "später, woher das Material stammte.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "ZWEI ZUSTÄNDE SIND ENDGÜLTIG. Was übernommen oder als "
                "fremdzuständig eingestuft ist, lässt sich nicht "
                "zurücknehmen. Diese Entscheidung ist vor dem Bestätigen zu "
                "prüfen, nicht danach.",
                "DER GRUND IST PFLICHT bei „Zurueckstellen“ und "
                "„Fremdzustaendig“. Ohne ihn wird nichts geschrieben. Eine "
                "abgegebene Zuständigkeit ohne Begründung wäre später nicht "
                "zu verteidigen.",
                "DIE SICHT ÜBERNIMMT KEINEN FALL. Sie hält die Entscheidung "
                "fest; die Bearbeitung beginnt danach an anderer Stelle.",
                "Ein Zustand, den das Werkzeug nicht kennt, verschwindet "
                "nicht — er wird angezeigt und ans Ende sortiert. Angeboten "
                "wird dann keine Aktion: lieber gar keine als eine geratene.",
                "Eine leere Liste heißt, dass es zurzeit keinen Kandidaten "
                "gibt. Die Sicht sagt auch, was das bedeutet.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Fallübersicht — die Fälle, die bereits in Bearbeitung sind.",
                "Zuweisung — wer den übernommenen Fall bekommt.",
                "Protokollbuch — der Beleg zu jeder Entscheidung.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "promotion.titel", "Fremdforum-Promotion",
            "Fälle, zu denen Material vorliegt, aber noch kein Arbeitsstand. "
            "Hier wird entschieden, ob sie übernommen werden.",
            verweis="promotion#zweck"),
        Kontexthilfe(
            "promotion.kennzeile", "Was ein Kandidat ist",
            "Erklärt die Lage dieser Fälle und weist darauf hin, dass "
            "„übernommen“ und „fremdzuständig“ endgültig sind.",
            verweis="promotion#grenzen"),
        Kontexthilfe(
            "promotion.zahlen", "Zähler je Zustand",
            "Wie viele Kandidaten in welchem Zustand sind — von "
            "handlungsbedürftig bis abgeschlossen."),
        Kontexthilfe(
            "promotion.warnung", "Warnung vor einer endgültigen Entscheidung",
            "Erscheint, wenn der gewählte Zustand endgültig ist. Es gibt "
            "danach keinen Weg zurück; ein Irrtum wird durch eine neue "
            "Entscheidung berichtigt.",
            verweis="promotion#grenzen"),
        Kontexthilfe(
            "promotion.bedienung.entscheiden", "Entscheidung wählen",
            "Öffnet das Feld für diese Entscheidung. Angeboten wird nur, was "
            "vom jetzigen Zustand aus zulässig ist.",
            verweis="promotion#ablaeufe"),
        Kontexthilfe(
            "promotion.bedienung.bestaetigen", "Bestätigen",
            "Schreibt die Entscheidung fest. Fehlt ein pflichtiger Grund, "
            "wird nichts geschrieben.",
            verweis="promotion#grenzen"),
        Kontexthilfe(
            "promotion.bedienung.abbrechen", "Abbrechen",
            "Schließt das Feld. Es wird nichts geschrieben."),
        # Die beiden Eingabezeilen des Entscheidungsfeldes (Build 636).
        Kontexthilfe(
            "promotion.bedienung.herkunft", "Herkunft",
            "Aus welchem Forum der Hinweis stammt — freiwillig. Die Angabe "
            "ist die einzige Spur zurück zur Quelle; ohne sie lässt sich eine "
            "Rückfrage später nicht mehr stellen."),
        Kontexthilfe(
            "promotion.bedienung.grund", "Grund",
            "Warum so entschieden wird. Bei „zurückgestellt“ und "
            "„fremdzuständig“ ist die Angabe PFLICHT: Beides sieht später wie "
            "Untätigkeit aus, wenn der Grund fehlt.",
            verweis="promotion#grenzen"),
        Kontexthilfe(
            "promotion.spalte.subject_id", "Spalte „Fall (subject_id)“",
            "Der Ermittlungsschlüssel des Falls."),
        Kontexthilfe(
            "promotion.spalte.zustand", "Spalte „Zustand“",
            "Der Stand der Entscheidung. Die Spalte sortiert nach "
            "HANDLUNGSBEDARF und nicht alphabetisch — sonst stünde der "
            "Endzustand vor dem, was noch zu tun ist.",
            verweis="promotion#aufbau"),
        Kontexthilfe(
            "promotion.spalte.grund", "Spalte „Grund“",
            "Die Begründung der Entscheidung. Bei „zurückgestellt“ und "
            "„fremdzuständig“ ist sie Pflicht."),
        Kontexthilfe(
            "promotion.spalte.herkunft", "Spalte „Herkunft“",
            "Woher das Material stammt, soweit hinterlegt. Die Angabe ist "
            "freiwillig."),
        Kontexthilfe(
            "promotion.spalte.aktion", "Aktionsspalte",
            "Die von hier aus zulässigen Entscheidungen. „endgueltig“ heißt: "
            "der Fall ist entschieden.",
            verweis="promotion#grenzen"),
        Kontexthilfe(
            "promotion.werkzeug.filter_entfernen", "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Sicht auf einmal."),
        Kontexthilfe(
            "promotion.werkzeug.trefferzahl", "Trefferanzeige",
            "Nennt, wie viele Zeilen sichtbar sind; bei gesetztem Filter "
            "„sichtbar von gesamt“."),
    ),
)


# =============================================================================
# 7) releases - "Externe Fallfreigabe"
# =============================================================================

RELEASES = Sichthilfe(
    sicht="releases",
    titel="Externe Fallfreigabe",
    recht_klartext=(
        "Rechte: release.view zum Lesen, release.grant zum Freigeben und "
        "Widerrufen. Ohne das Schreibrecht fehlen das Formular und der "
        "Widerrufsknopf."
    ),
    stand=_STAND_H14,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Eine Freigabe macht einen Fall einer bestätigten Person "
                "außerhalb der eigenen Dienststelle zugänglich — belegt, "
                "geprüft und widerrufbar.",
                "DREI BEDINGUNGEN MÜSSEN ERFÜLLT SEIN, und keine davon lässt "
                "sich hier umgehen: die empfangende Person muss in der "
                "hinterlegten Liste stehen, die Unbedenklichkeit muss "
                "begründet sein, und der Vorgang wird festgehalten.",
                "EINE FREIGABE ENDET NICHT VON SELBST. Es gibt keine Frist "
                "und kein Ablaufdatum — der Zugriff besteht, bis ihn jemand "
                "widerruft.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "release.view zum Lesen. Das Erteilen und das Widerrufen "
                "brauchen release.grant; beides ist eine Leitungshandlung.",
                "Die empfangende Person muss in der hinterlegten Liste "
                "stehen. Ist die Liste leer, sagt die Sicht das ausdrücklich "
                "und bietet gar kein Formular an — im Zweifel wird nicht "
                "freigegeben.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift mit dem Hinweis, welche Gruppe empfangen darf. "
                "Darunter zwei Zähler: freigegeben und widerrufen.",
                "Mit Schreibrecht folgt das Formular „Neue Freigabe“ mit vier "
                "Angaben: Fall, Empfänger, Umfang und die "
                "Unbedenklichkeits-Grundlage. Dann die Rückmeldezeile und die "
                "Liste.",
                "Der Umfang sagt, WAS freigegeben wird — der gesiegelte "
                "Bericht, die vollständige Akte oder ein geprüfter Auszug. Er "
                "ist die eigentliche Entscheidung über die Weitergabetiefe.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Freigeben: Fall, Empfänger und Umfang wählen, die "
                "Unbedenklichkeit begründen, „Freigeben“.",
                "Widerrufen: „Widerrufen“ in der Zeile, Grund eintragen, "
                "bestätigen.",
                "Regelmäßig durchsehen: Was hier als freigegeben steht, IST "
                "freigegeben — auch Monate später. Es läuft nichts von selbst "
                "aus.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "ES GIBT KEINE BEFRISTUNG. Eine Freigabe bleibt bestehen, bis "
                "sie widerrufen wird. Wer sie zeitlich begrenzen will, muss "
                "den Widerruf selbst veranlassen — das Werkzeug erinnert "
                "nicht daran.",
                "DIE UNBEDENKLICHKEITS-GRUNDLAGE IST PFLICHT. Ohne sie wird "
                "nichts freigegeben. Sie ist der Nachweis, dass geprüft wurde "
                "— nicht eine Formalie.",
                "EIN WIDERRUF IST ENDGÜLTIG. Er lässt sich nicht "
                "zurücknehmen; eine erneute Freigabe ist ein NEUER Vorgang "
                "mit eigener Prüfung und eigenem Beleg. Auch der Widerruf "
                "braucht einen Grund.",
                "OHNE BERECHTIGTE EMPFÄNGER GIBT ES KEIN FORMULAR. Das ist "
                "kein Fehler, sondern der Grundsatz: was nicht ausdrücklich "
                "erlaubt ist, ist nicht erlaubt.",
                "Die Liste kann sich ändern, ohne dass Sie etwas tun — auch "
                "eine andere Person kann freigeben oder widerrufen.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Berichte — was als gesiegelter Bericht freigegeben werden "
                "kann.",
                "Chef-Freigabe — die Abnahme VOR der Weitergabe.",
                "Protokollbuch — der Beleg zu jeder Freigabe und jedem "
                "Widerruf.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "releases.titel", "Externe Fallfreigabe",
            "Weitergabe eines Falls an eine bestätigte Person außerhalb der "
            "Dienststelle — geprüft, belegt und widerrufbar.",
            verweis="releases#zweck"),
        Kontexthilfe(
            "releases.kennzeile", "Bedingungen der Weitergabe",
            "Nennt die Voraussetzungen und die Gruppe, aus der Empfänger "
            "stammen dürfen.",
            verweis="releases#rechte"),
        Kontexthilfe(
            "releases.zahlen", "Zähler",
            "Wie viele Freigaben aktiv sind und wie viele widerrufen wurden. "
            "Aktive Freigaben bestehen, bis jemand sie widerruft.",
            verweis="releases#grenzen"),
        Kontexthilfe(
            "releases.abschnitt.neue_freigabe", "Neue Freigabe",
            "Das Formular für eine Weitergabe. Alle vier Angaben werden "
            "festgehalten und sind später nachprüfbar."),
        Kontexthilfe(
            "releases.hinweis.keine_empfaenger", "Keine berechtigten Empfänger",
            "Es ist keine empfangsberechtigte Stelle hinterlegt — deshalb "
            "gibt es kein Formular. Das ist der Grundsatz und kein Fehler: "
            "was nicht ausdrücklich erlaubt ist, ist nicht erlaubt.",
            verweis="releases#grenzen"),
        Kontexthilfe(
            "releases.bedienung.fall", "Fall",
            "Der Ermittlungsschlüssel des freizugebenden Falls."),
        Kontexthilfe(
            "releases.bedienung.empfaenger", "Empfänger",
            "Die empfangende Person. Angeboten wird nur, wer hinterlegt ist.",
            verweis="releases#rechte"),
        Kontexthilfe(
            "releases.bedienung.umfang", "Umfang",
            "WAS weitergegeben wird: der gesiegelte Bericht, die vollständige "
            "Akte oder ein geprüfter Auszug. Das ist die Entscheidung über "
            "die Weitergabetiefe.",
            verweis="releases#aufbau"),
        Kontexthilfe(
            "releases.bedienung.grundlage", "Unbedenklichkeit — Grundlage",
            "Worauf sich die Unbedenklichkeit stützt. Pflichtangabe: ohne sie "
            "wird nichts freigegeben.",
            verweis="releases#grenzen"),
        Kontexthilfe(
            "releases.bedienung.freigeben", "Freigeben",
            "Erteilt die Freigabe. Sie gilt ab sofort und OHNE Frist — bis "
            "jemand sie widerruft.",
            verweis="releases#grenzen"),
        Kontexthilfe(
            "releases.bedienung.widerrufen", "Widerrufen",
            "Öffnet den Widerruf dieser Freigabe. Der Knopf erscheint nur an "
            "aktiven Freigaben."),
        Kontexthilfe(
            "releases.warnung", "Warnung vor dem Widerruf",
            "Ein Widerruf lässt sich nicht zurücknehmen. Eine erneute "
            "Freigabe ist ein neuer Vorgang mit eigener Prüfung.",
            verweis="releases#grenzen"),
        Kontexthilfe(
            "releases.bedienung.widerrufsgrund", "Grund des Widerrufs",
            "Pflichtangabe. Ein Widerruf ohne nachvollziehbaren Grund wäre "
            "später nicht einzuordnen."),
        Kontexthilfe(
            "releases.bedienung.widerruf_bestaetigen", "Widerruf bestätigen",
            "Beendet den externen Zugriff. Endgültig."),
        Kontexthilfe(
            "releases.bedienung.abbrechen", "Abbrechen",
            "Schließt den Widerruf. Es wird nichts geschrieben."),
    ),
)


#: Der Teilbestand dieser Nav-Gruppe - VOLLSTAENDIG seit Build 605.
#: Reihenfolge = Katalogreihenfolge des VIEW_CATALOG.
ADMINISTRATION: Tuple[Sichthilfe, ...] = (
    POLICY, INTEGRITY, AUDIT, HANDOVER, RETENTION, PROMOTION, RELEASES,
)
