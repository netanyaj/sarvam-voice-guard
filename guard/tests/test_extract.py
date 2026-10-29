"""Offline tests for extract.py: clean-up rules, backstop and cache (the model is stubbed)."""
import extract
from conftest import T05, T05_SPAN, T14, TODAY


def ent(type, raw_span, value, date_kind="none", superseded=()):
    return {"type": type, "raw_span": raw_span, "value": value, "date_kind": date_kind,
            "superseded_raw_spans": list(superseded)}


# The two messy outputs sarvam-105b actually gave for T14 while choosing settings.
def test_tidy_drops_duplicates_and_parts_of_other_details():
    raw = [ent("phone", "9847012345", "9847012345"), ent("amount", "2450", "2450"),
           ent("date", "നവംബർ 5ന്", "2026-11-05", "due"), ent("phone", "9847012345", "9847012345"),
           ent("amount", "5ന്", "5")]
    kept, dropped = extract.tidy(raw)
    assert [e["type"] for e in kept] == ["phone", "amount", "date"]
    assert {d["dropped_because"].split()[0] for d in dropped} == {"duplicate", "part"}


def test_tidy_drops_date_without_date_words():
    kept, dropped = extract.tidy([ent("date", "മുമ്പ്", TODAY, "other")])
    assert kept == [] and dropped[0]["dropped_because"] == "no date words in the span"


def test_backstop_catches_a_dropped_phone_in_words():
    extra = extract.backstop(T05 + ", OTP 482913", [ent("otp", "482913", "482913")])
    assert [e["raw_span"] for e in extra] == [T05_SPAN]
    assert extra[0]["type"] == "unclassified_number"


def test_backstop_catches_a_dropped_digit_run():
    extra = extract.backstop(T14, [ent("amount", "2450", "2450"), ent("date", "നവംബർ 5ന്", "2026-11-05")])
    assert [e["raw_span"] for e in extra] == ["9847012345"]


def test_backstop_quiet_when_everything_is_covered():
    assert extract.backstop(T05 + ". ഇത് ഒന്ന് തിരിച്ചു പറയാമോ", [ent("phone", T05_SPAN, "9047012345")]) == []


def test_backstop_respects_self_correction():
    t = "എന്റെ നമ്പർ 98470... അല്ല, 98471 12345"
    assert extract.backstop(t, [ent("phone", "98471 12345", "9847112345", superseded=["98470"])]) == []
    assert [e["raw_span"] for e in extract.backstop(t, [ent("phone", "98471 12345", "9847112345")])] == ["98470"]


def test_model_calls_are_cached(monkeypatch, tmp_path):
    calls = []

    def fake_post(path, body, timeout):
        calls.append(body)
        return {"choices": [{"finish_reason": "stop", "message": {
            "content": '{"entities": [{"type": "otp", "raw_span": "482913", "value": "482913", '
                       '"date_kind": "none", "superseded_raw_spans": []}]}'}}]}

    monkeypatch.setattr(extract, "post_json", fake_post)
    monkeypatch.setattr(extract, "CACHE", str(tmp_path))
    first = extract.extract("OTP 482913", today=TODAY)
    second = extract.extract("OTP 482913", today=TODAY)
    assert len(calls) == 1 and not first["cached"] and second["cached"]
    assert calls[0]["reasoning_effort"] is None and calls[0]["response_format"] == {"type": "json_object"}
    assert second["entities"][0]["value"] == "482913"


def test_empty_model_reply_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(extract, "post_json", lambda *a, **k: {
        "choices": [{"finish_reason": "length", "message": {"content": None}}]})
    monkeypatch.setattr(extract, "CACHE", str(tmp_path))
    try:
        extract.extract("x", today=TODAY)
    except extract.SarvamError as e:
        assert "finish_reason=length" in str(e)
    else:
        raise AssertionError("expected SarvamError")


def test_backstop_catches_a_dropped_date():
    # one live run returned no details at all for R06
    extra = extract.backstop("അടുത്ത മാസം അഞ്ചാം തീയതി premium അടയ്ക്കാം", [])
    assert [(e["type"], e["raw_span"]) for e in extra] == [("unclassified_date", "തീയതി")]
    assert extract.backstop("നവംബർ 5ന്", [ent("date", "നവംബർ 5ന്", "2026-11-05")]) == []


def test_shape_check_keeps_only_known_well_formed_details():
    content = ('{"entities": [{"type": "phone", "raw_span": "98470", "value": 98470}, '
               '{"type": "email", "raw_span": "x@y"}, "junk", {"type": "otp", "raw_span": ""}]}')
    assert extract._check_shape(content) == [{"type": "phone", "raw_span": "98470", "value": "98470",
                                              "date_kind": "none", "superseded_raw_spans": []}]
