import os

import pytest

import confirm
from confirm import question, rupees, spaced, spelled_id
from conftest import T05, T05_SPAN, TODAY
from validate import validate


def flagged(type_, value, reasons=("x",), **kw):
    return {"type": type_, "raw_span": "r", "value": value, "status": "flagged", "reasons": list(reasons), **kw}


def test_spacing():
    assert spaced("9847012345", 5) == "9 8 4 7 0, 1 2 3 4 5"
    assert spaced("947012345", 5) == "9 4 7 0 1, 2 3 4 5"
    assert spelled_id("SBL2047813") == "S B L, 2 0 4 7, 8 1 3"
    assert [rupees(n) for n in (450, 2450, 14415, 450000, 12345678)] == \
        ["450", "2,450", "14,415", "4,50,000", "1,23,45,678"]


@pytest.mark.parametrize("model_value", ["97012345", "947012345"])
def test_t05_asks_again_instead_of_yes_no(record, model_value):
    """A broken number is read back as heard, then the caller is asked to repeat it."""
    checked = validate(T05, [{"type": "phone", "raw_span": T05_SPAN, "value": model_value}], record, today=TODAY)
    [q] = confirm.confirm(checked, audio=False)
    assert q["text"].startswith(f"ഞാൻ കേട്ടത് {spaced(model_value, 5)}.")
    assert q["text"].endswith("ഒരു അക്കം വീതം ഒന്നുകൂടി പറയാമോ?")
    assert "ആണോ?" not in q["text"]


def test_t05_model_fixes_it_still_asks(record):
    """Model 'repairs' T05 to a valid number: still flagged, so a yes/no read-back of that number."""
    checked = validate(T05, [{"type": "phone", "raw_span": T05_SPAN, "value": "9847012345"}], record, today=TODAY)
    [q] = confirm.confirm(checked, audio=False)
    assert q["text"] == "നിങ്ങളുടെ നമ്പർ 9 8 4 7 0, 1 2 3 4 5 ആണോ?"


def test_ok_details_get_no_question():
    assert confirm.confirm([{**flagged("phone", "9847012345"), "status": "ok"}], audio=False) == []


def test_each_type():
    today = confirm.dt.date.fromisoformat(TODAY)
    assert question(flagged("otp", "482913"), today) == "OTP 4 8 2, 9 1 3 ആണോ?"
    assert question(flagged("otp", "48291"), today).startswith("ഞാൻ കേട്ടത് 4 8 2, 9 1.")
    assert question(flagged("amount", 450000), today) == "4,50,000 രൂപ ആണോ?"
    assert question(flagged("amount", "abc"), today) == "തുക എത്രയാണെന്ന് ഒന്നുകൂടി പറയാമോ?"
    assert question(flagged("date", "2026-11-05"), today) == "നവംബർ 5 ആണോ?"
    assert question(flagged("date", "2027-01-05"), today) == "ജനുവരി 5 2027 ആണോ?"
    assert "കഴിഞ്ഞുപോയി" in question(flagged("date", "2026-10-01", ["due date 2026-10-01 is in the past"]), today)
    assert question(flagged("policy_or_account_id", "SBL2047831",
                            ["does not match the policy or account number on file"]), today) == \
        "പോളിസി നമ്പർ S B L, 2 0 4 7, 8 3 1 ആണോ?"
    assert question(flagged("policy_or_account_id", "SB2047813", ["should be 3 letters then 7 digits; heard SB2047813"]),
                    today).startswith("ഞാൻ കേട്ടത് S B, 2 0 4 7, 8 1 3.")
    assert question(flagged("place_name", "എടാപ്പള്ളി", suggestion="ഇടപ്പള്ളി"), today) == "ഇടപ്പള്ളി എന്നാണോ ഉദ്ദേശിച്ചത്?"
    assert question(flagged("place_name", "x"), today) == "സ്ഥലത്തിന്റെ പേര് ഒന്നുകൂടി പറയാമോ?"
    assert question(flagged("unclassified_number", "2450"), today) == "2 4 5 0 എന്ന് കേട്ടു. ഇത് ഏത് നമ്പർ ആണ്?"
    assert question(flagged("unclassified_date", ""), today) == "തീയതി ഒന്നുകൂടി പറയാമോ?"


def test_speak_uses_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(confirm, "CACHE", str(tmp_path))
    calls = []
    monkeypatch.setattr(confirm, "post_json", lambda path, body: calls.append(body) or {"audios": ["UklGRg=="]})
    p1, c1 = confirm.speak("നമസ്കാരം")
    p2, c2 = confirm.speak("നമസ്കാരം")
    assert (c1, c2) == (False, True) and p1 == p2 and len(calls) == 1
    assert calls[0]["speaker"] == "kavya" and calls[0]["pace"] == 0.9 and calls[0]["model"] == "bulbul:v3"
    assert open(p1, "rb").read() == b"RIFF"


def test_too_long():
    with pytest.raises(ValueError):
        confirm.speak("അ" * 2501)


def test_english_meaning_matches_each_kind():
    today = confirm.dt.date.fromisoformat(TODAY)
    assert confirm.question_en(flagged("phone", "9847012345"), today) == "Is your number 9 8 4 7 0, 1 2 3 4 5?"
    assert confirm.question_en(flagged("amount", 450000), today) == "Is it ₹4,50,000?"
    assert confirm.question_en(flagged("date", "2026-11-05"), today) == "Is it 5 November?"
    assert confirm.question_en(flagged("place_name", "x", suggestion="ഇടപ്പള്ളി"), today) == "Did you mean ഇടപ്പള്ളി?"
    assert confirm.question_en(flagged("unclassified_date", ""), today) == "Could you say the date again?"
