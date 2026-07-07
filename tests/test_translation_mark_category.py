# =============================================================================
# tests/test_translation_mark_category.py
# Build 333: Kategorie 'Uebersetzungsfund' (CAT_TRANSLATION) registriert?
# Beleg: Bauplan Build 333 §3; annotate.py importiert VALID_CATEGORIES aus
#        evidence_db -> ein Eintrag deckt Endpoint-Validierung + DB ab.
# =============================================================================

from db.evidence_db import VALID_CATEGORIES


def test_uebersetzungsfund_kategorie_gueltig():
    # Ohne diesen Eintrag wuerde der annotate-Endpoint CAT_TRANSLATION mit 400
    # ablehnen und Uebersetzungs-Markierungen koennten nicht gespeichert werden.
    assert "CAT_TRANSLATION" in VALID_CATEGORIES


def test_bestehende_kategorien_unveraendert():
    for cat in ("CAT_PERSON", "CAT_LOCATION", "CAT_176", "CAT_184",
                "CAT_VICTIM", "CAT_OTHER"):
        assert cat in VALID_CATEGORIES
