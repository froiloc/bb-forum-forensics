# =============================================================================
# tests/test_annotate_translation_selection.py
# Build 336: Der annotate-Endpoint muss die Uebersetzungs-OFFSET-Selektion
# akzeptieren und speichern (frueher verwarf er sie still -> selection_json=None,
# Marke ohne Anker). XPath-Selektion muss weiterhin gespeichert werden;
# unvollstaendige Selektionen werden weiterhin verworfen.
# Beleg: Live-Diagnose 2026-07-07 (/annotate-POST-Probe + annotate.py XPath-Pruefung).
# =============================================================================

import json
from unittest.mock import MagicMock

from forensic_api.annotate import AnnotateEndpoint


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


def test_uebersetzungs_offset_selektion_wird_gespeichert():
    ep, bundle = _endpoint()
    sel = {
        "target": "translation", "source": "posts", "postId": 705985,
        "charStart": 149, "charEnd": 188, "textLen": 569, "textHash": "fac28bb4",
        "textContent": "Telegram-Gruppen und ein Telegram-Konto",
    }
    _post(ep, {
        "page_url": "/forum/viewtopic.php?id=69192", "category": "CAT_VICTIM",
        "post_id": 705985, "selection": sel, "tags": ["#KI-Übersetzung"],
        "local_id": "abc",
    })
    kwargs = bundle.evidence.save_annotation.call_args.kwargs
    # Kern des Bugs: selection_json war None (verworfen)
    assert kwargs["selection_json"] is not None
    stored = json.loads(kwargs["selection_json"])
    assert stored["target"] == "translation"
    assert stored["postId"] == 705985
    assert stored["charStart"] == 149 and stored["charEnd"] == 188
    # Option B: post_id-Spalte gesetzt
    assert kwargs["post_id"] == 705985


def test_xpath_selektion_wird_weiterhin_gespeichert():
    ep, bundle = _endpoint()
    sel = {
        "xpathStart": "./p[1]/text()[1]", "offsetStart": 0,
        "xpathEnd": "./p[1]/text()[1]", "offsetEnd": 5, "textContent": "Hallo",
    }
    _post(ep, {"page_url": "/forum/viewtopic.php?id=1",
               "category": "CAT_OTHER", "selection": sel})
    kwargs = bundle.evidence.save_annotation.call_args.kwargs
    assert kwargs["selection_json"] is not None
    assert json.loads(kwargs["selection_json"])["xpathStart"] == "./p[1]/text()[1]"


def test_unvollstaendige_selektion_wird_verworfen():
    ep, bundle = _endpoint()
    _post(ep, {"page_url": "/x", "category": "CAT_OTHER",
               "selection": {"foo": "bar"}})
    kwargs = bundle.evidence.save_annotation.call_args.kwargs
    assert kwargs["selection_json"] is None


def test_translation_ohne_pflichtfelder_wird_verworfen():
    # target=translation, aber ohne charStart/charEnd/... -> verworfen
    ep, bundle = _endpoint()
    _post(ep, {"page_url": "/x", "category": "CAT_OTHER",
               "selection": {"target": "translation", "postId": 1}})
    kwargs = bundle.evidence.save_annotation.call_args.kwargs
    assert kwargs["selection_json"] is None
