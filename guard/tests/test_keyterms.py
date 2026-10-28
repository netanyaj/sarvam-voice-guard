"""Offline tests for keyterms.py (transliteration is stubbed)."""
import pytest

import keyterms

FAKE = {"Lulu Mall": "ലുലു മാൾ", "Edappally": "ഇടപ്പള്ളി", "Tripunithura": "ത്രിപുണിത്തുറ"}


@pytest.fixture(autouse=True)
def stub_transliterate(monkeypatch):
    calls = []

    def fake(term, language_code):
        calls.append(term)
        return FAKE.get(term, f"<{term}>")

    monkeypatch.setattr(keyterms, "_transliterate", fake)
    return calls


def test_native_first_then_original():
    assert keyterms.build_keyterms(["Lulu Mall", "Edappally"]) == ["ലുലു മാൾ", "ഇടപ്പള്ളി", "Lulu Mall", "Edappally"]


def test_native_only():
    assert keyterms.build_keyterms(["Lulu Mall"], keep_original=False) == ["ലുലു മാൾ"]


def test_english_output_sends_terms_as_given(stub_transliterate):
    assert keyterms.build_keyterms(["Lulu Mall"], "en-IN") == ["Lulu Mall"]
    assert keyterms.build_keyterms(["Lulu Mall"], "unknown") == ["Lulu Mall"]
    assert stub_transliterate == []


def test_native_script_input_is_not_transliterated(stub_transliterate):
    assert keyterms.build_keyterms(["ഇടപ്പള്ളി"]) == ["ഇടപ്പള്ളി"]
    assert stub_transliterate == []


def test_known_spelling_beats_transliteration(stub_transliterate):
    assert keyterms.build_keyterms(["Tripunithura"], keep_original=False) == ["തൃപ്പൂണിത്തുറ"]
    assert stub_transliterate == []


def test_dedupe_and_blank_terms():
    assert keyterms.build_keyterms(["Edappally", " Edappally ", "", "ഇടപ്പള്ളി"]) == ["ഇടപ്പള്ളി", "Edappally"]


def test_limit_keeps_native_forms_first():
    terms = [f"Place{i}" for i in range(40)]
    out = keyterms.build_keyterms(terms)
    assert len(out) == keyterms.MAX_TERMS
    assert out[:40] == [f"<Place{i}>" for i in range(40)]
    assert out[40:] == [f"Place{i}" for i in range(10)]


def test_terms_over_64_chars_are_dropped():
    long = "x" * 65
    assert long not in keyterms.build_keyterms([long])
