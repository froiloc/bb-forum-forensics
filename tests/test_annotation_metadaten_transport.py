# =============================================================================
# tests/test_annotation_metadaten_transport.py
#
# Build 735: Die Metadaten einer Textmarkierung — post_id, Zeitstempel und
# Betreff — reisen im 'meta'-Unterknoten von 'selection' und muessen den
# annotate-Endpoint UNVERAENDERT passieren.
#
# WARUM DIESER TEST NOETIG IST, obwohl der Endpoint nichts tut
#
# Genau deshalb. Der Endpoint prueft die Selektion mit 'issubset' auf die
# Pflichtfelder; ZUSAETZLICHE Felder sind erlaubt und werden mitserialisiert.
# Das ist die Bedingung dafuer, dass dieser Schritt OHNE Schemaaenderung und
# damit OHNE Migration auskommt (Migrationsvorbehalt fuer
# 'evidence_<uid>.db' seit dem 01.07.2026). Diese Eigenschaft ist aber
# nirgends festgehalten — sie ergibt sich aus einer Zeile, die jemand beim
# naechsten Umbau zu einer Weissliste verschaerfen koennte, ohne zu ahnen,
# dass daran die Zeitstempel und Betreffe aller neuen Belege haengen.
#
# Ein Verhalten, auf das man sich verlaesst, gehoert unter einen Test — auch
# und gerade dann, wenn es 'von selbst' funktioniert.
#
# ME01  das vollstaendige 'meta' kommt unveraendert in 'selection_json' an
# ME02  die Spalte 'post_id' wird davon nicht beruehrt
# ME03  ALTE Marken OHNE 'meta' werden weiterhin angenommen (Rueckwaerts-
#       vertraeglichkeit — ohne sie waere der Schritt migrationspflichtig)
# ME04  GEGENPROBE: 'meta' allein macht eine unvollstaendige Selektion NICHT
#       gueltig
# ME05  Umlaute und Nicht-Latein ueberstehen den Weg (das Forum ist
#       mehrsprachig, UTF-8)
# ME06  Build 736: 'eroeffner': null ueberlebt den Weg als null und wird
#       NICHT zu false - der Unterschied zwischen 'nicht der Eroeffner' und
#       'darueber sagt die Seite nichts' ist der zwischen einem Befund und
#       einem Fehlschluss
#
# Beleg: forensic_api/annotate.py (Selektionspruefung); toolbar/toolbar.js
#        (PostMetaModule, Build 735); claude/Analyse_Sondenmessung_29082026.md
# =============================================================================

import json
from unittest.mock import MagicMock

from forensic_api.annotate import AnnotateEndpoint


# Ein 'meta', wie PostMetaModule es auf einer Themenseite bildet. Die Werte
# stammen aus dem Aufbau, gegen den die JavaScript-Seite prueft
# (tests/unit/test_annotation_metadaten.test.js).
META_VIEWTOPIC = {
    "ansicht": "viewtopic",
    "postId": 721603,
    "postIdWeg": "P1+P3",
    "postIdGegenprobe": 721603,
    "postIdSpalte": "P1+P3",
    "zeitRoh": "17.12.2022 08:14:00",
    "zeitIsoOhneZone": "2022-12-17T08:14:00",
    "zeitTeile": {"tag": 17, "monat": 12, "jahr": 2022,
                  "stunde": 8, "minute": 14, "sekunde": 0},
    "zeitWeg": "T1",
    "betreff": "Re: Ein Thema über Bonn",
    "betreffWeg": "S2",
    "themenbetreff": "Ein Thema über Bonn",
    "themenbetreffWeg": "S6a",
    # Build 736: Befunde der SEITE. 'eroeffner' kennt DREI Zustaende -
    # true, false und null (= unbekannt, weil die Seite keinen
    # Moderationshinweis traegt). Dass 'null' den Weg unveraendert uebersteht,
    # ist keine Nebensache: wuerde es unterwegs zu 'false', stuende in der
    # Akte eine Verneinung, fuer die es keinen Beleg gibt.
    "moderation": True,
    "eroeffner": True,
    "eroeffnerQuelle": "OP-Kennzeichen im Moderationshinweis",
    "hinweise": [],
}


def _endpoint():
    bundle = MagicMock()
    bundle.evidence.save_annotation.return_value = 42
    context = MagicMock()
    context.investigator_id = 110
    context.investigator_username = "paul"
    context.username = "paul"
    return AnnotateEndpoint(bundle, context, MagicMock()), bundle


def _post(ep, payload):
    handler = MagicMock()
    handler.command = "POST"
    ep.handle(handler, json.dumps(payload).encode("utf-8"))


def _selektion(meta=None):
    sel = {
        "xpathStart": "./div[4]/article[2]/div[1]/div[2]/text()[1]",
        "offsetStart": 0,
        "xpathEnd": "./div[4]/article[2]/div[1]/div[2]/text()[1]",
        "offsetEnd": 21,
        "textContent": "Ich komme mit dem Rad",
    }
    if meta is not None:
        sel["meta"] = meta
    return sel


def test_ME01_meta_kommt_unveraendert_an():
    ep, bundle = _endpoint()
    _post(ep, {"page_url": "/forum/viewtopic.php?pid=721598",
               "category": "CAT_OTHER", "post_id": 721603,
               "selection": _selektion(META_VIEWTOPIC)})
    kwargs = bundle.evidence.save_annotation.call_args.kwargs
    assert kwargs["selection_json"] is not None
    gespeichert = json.loads(kwargs["selection_json"])
    # Nicht nur 'vorhanden' — IDENTISCH. Ein Endpoint, der einzelne Felder
    # durchreicht und andere verschluckt, waere schlimmer als einer, der
    # alles verwirft: der Verlust fiele niemandem auf.
    assert gespeichert["meta"] == META_VIEWTOPIC
    # Und die Herkunft jedes Wertes ist mitgereist. Ein Wert ohne Herkunft
    # ist in einer Akte nicht ueberpruefbar (Grundregel 1).
    assert gespeichert["meta"]["zeitWeg"] == "T1"
    assert gespeichert["meta"]["themenbetreffWeg"] == "S6a"
    assert gespeichert["meta"]["eroeffnerQuelle"] == "OP-Kennzeichen im Moderationshinweis"


def test_ME02_die_spalte_post_id_bleibt_unberuehrt():
    ep, bundle = _endpoint()
    _post(ep, {"page_url": "/forum/viewtopic.php?pid=721598",
               "category": "CAT_OTHER", "post_id": 721603,
               "selection": _selektion(META_VIEWTOPIC)})
    kwargs = bundle.evidence.save_annotation.call_args.kwargs
    # Die Nummer steht bewusst an zwei Stellen: in der Spalte (fuer die
    # Auswertung) und in 'meta' (mit ihrer Herkunft und der Gegenprobe).
    assert kwargs["post_id"] == 721603
    assert json.loads(kwargs["selection_json"])["meta"]["postId"] == 721603


def test_ME03_selektion_ohne_meta_wird_weiterhin_angenommen():
    # DAS IST DIE BEDINGUNG DAFUER, DASS DIESER SCHRITT OHNE MIGRATION
    # AUSKOMMT: Alle Annotationen aus der Zeit vor Build 735 haben kein
    # 'meta'. Waere es Pflicht, muesste jeder Bestand angefasst werden.
    ep, bundle = _endpoint()
    _post(ep, {"page_url": "/forum/viewtopic.php?id=1",
               "category": "CAT_OTHER", "selection": _selektion()})
    kwargs = bundle.evidence.save_annotation.call_args.kwargs
    assert kwargs["selection_json"] is not None
    assert "meta" not in json.loads(kwargs["selection_json"])


def test_ME04_gegenprobe_meta_ersetzt_die_pflichtfelder_nicht():
    # Ohne diese Probe waere ME01 auch mit einem Endpoint gruen, der jede
    # Selektion durchwinkt, sobald 'meta' dabei ist — und dann landeten
    # ankerlose Marken im Bestand.
    ep, bundle = _endpoint()
    _post(ep, {"page_url": "/x", "category": "CAT_OTHER",
               "selection": {"meta": META_VIEWTOPIC}})
    kwargs = bundle.evidence.save_annotation.call_args.kwargs
    assert kwargs["selection_json"] is None


def test_ME05_umlaute_und_nichtlatein_ueberstehen_den_weg():
    # Erkenntnis zum Fall Nr. 2: das Forum ist mehrsprachig, es sind die
    # unterschiedlichsten Zeichensaetze zu erwarten. Der Endpoint
    # serialisiert mit ensure_ascii=False; das muss auch fuer den neuen
    # Unterknoten gelten.
    meta = dict(META_VIEWTOPIC)
    meta["themenbetreff"] = "Приветствие — Grüße aus Köln · 東京"
    meta["betreff"] = "Re: Приветствие — Grüße aus Köln · 東京"
    ep, bundle = _endpoint()
    _post(ep, {"page_url": "/forum/viewtopic.php?id=1",
               "category": "CAT_OTHER", "selection": _selektion(meta)})
    kwargs = bundle.evidence.save_annotation.call_args.kwargs
    gespeichert = json.loads(kwargs["selection_json"])
    assert gespeichert["meta"]["themenbetreff"] == meta["themenbetreff"]
    # Und zwar als Zeichen, nicht als \\u-Fluchtfolge — sonst waere der Wert
    # zwar wiederherstellbar, in einer Sichtpruefung des JSON aber unlesbar.
    assert "Grüße" in kwargs["selection_json"]


def test_ME06_unbekannte_eroeffnerschaft_bleibt_unbekannt():
    # DREI ZUSTAENDE, NICHT ZWEI. Ohne Moderationshinweis rendert das Forum
    # keinen Kasten, und die Seite sagt ueber die Eroeffnerschaft NICHTS.
    # Wuerde 'null' unterwegs zu 'false', stuende in jedem Beleg einer
    # gewoehnlichen Seite eine Verneinung ohne Beleg - ein entlastender
    # Schluss, den niemand gezogen hat.
    #
    # Diese Probe misst den Transport, nicht die Erhebung: json.dumps macht
    # aus None ein JSON-null, und json.loads macht daraus wieder None. Genau
    # das soll festgehalten sein, damit eine spaetere Normalisierung
    # ("leere Werte vereinheitlichen") hier anschlaegt.
    meta = dict(META_VIEWTOPIC)
    meta["moderation"] = False
    meta["eroeffner"] = None
    meta["eroeffnerQuelle"] = None
    meta["hinweise"] = ["keine Moderationsanzeige - die Seite sagt ueber die "
                        "Eroeffnerschaft NICHTS (nicht: sie verneint sie)"]
    ep, bundle = _endpoint()
    _post(ep, {"page_url": "/forum/viewtopic.php?id=1",
               "category": "CAT_OTHER", "selection": _selektion(meta)})
    kwargs = bundle.evidence.save_annotation.call_args.kwargs
    gespeichert = json.loads(kwargs["selection_json"])
    assert gespeichert["meta"]["eroeffner"] is None
    assert gespeichert["meta"]["eroeffner"] is not False
    assert "sagt ueber die" in gespeichert["meta"]["hinweise"][0]
