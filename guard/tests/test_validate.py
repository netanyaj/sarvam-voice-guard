import pytest

from conftest import T05, T05_SPAN, T14, TODAY
from validate import validate


def ent(type, raw_span, value, date_kind="none"):
    return {"type": type, "raw_span": raw_span, "value": value, "date_kind": date_kind, "superseded_raw_spans": []}


def one(transcript, e, record=None, **kw):
    return validate(transcript, [e], record=record, today=TODAY, **kw)[0]


# T05: whatever the model makes of the words, the guard must not let it through.
@pytest.mark.parametrize("model_value,extra", [
    ("97012345", "only 8 digits"),      # what Indus actually read back
    ("9047012345", None),               # literal reading: looks valid
    ("9847012345", "read as 9047012345"),  # a model that "fixes" it is still guessing
])
def test_t05_phone_is_flagged(model_value, extra):
    r = one(T05, ent("phone", T05_SPAN, model_value))
    assert r["status"] == "flagged"
    assert any("does not combine" in x for x in r["reasons"])
    if extra:
        assert any(extra in x for x in r["reasons"])


def test_t14_all_ok():
    out = validate(T14, [ent("phone", "9847012345", "9847012345"),
                         ent("amount", "2450 റുപ്പീസിൻ്റെ", "2450"),
                         ent("date", "നവംബർ 5ന്", "2026-11-05", "due")], today=TODAY)
    assert [r["status"] for r in out] == ["ok", "ok", "ok"]
    assert out[1]["value"] == 2450


@pytest.mark.parametrize("span,value,reason", [
    ("58470 12345", "5847012345", "starts with 5"),
    ("98470 1234", "984701234", "only 9 digits"),
    ("98470 12345 6", "98470123456", "11 digits"),
])
def test_phone_rules(span, value, reason):
    r = one(f"നമ്പർ {span}", ent("phone", span, value))
    assert r["status"] == "flagged" and any(reason in x for x in r["reasons"])


def test_phone_with_country_code_ok():
    assert one("+91 98470 12345", ent("phone", "91 98470 12345", "919847012345"))["status"] == "ok"


def test_otp():
    assert one("OTP 482913", ent("otp", "482913", "482913"))["status"] == "ok"
    r = one("OTP 48291", ent("otp", "48291", "48291"))
    assert r["status"] == "flagged" and "5 digits" in r["reasons"][0]


def test_amount_lakh_ok():
    r = one("നാലര ലക്ഷം രൂപയുടെ loan", ent("amount", "നാലര ലക്ഷം", "450000"))
    assert r["status"] == "ok" and r["value"] == 450000


def test_amount_wrong_lakh_conversion_flagged():
    r = one("നാലര ലക്ഷം രൂപയുടെ loan", ent("amount", "നാലര ലക്ഷം", "45000"))
    assert r["status"] == "flagged" and "come to 450000" in r["reasons"][0]


def test_amount_words_and_digits_disagree():
    t = "₹2,450 (രണ്ടായിരത്തി നാനൂറ്റി അറുപത്) അടയ്ക്കണം"
    r = one(t, ent("amount", "₹2,450 (രണ്ടായിരത്തി നാനൂറ്റി അറുപത്)", "2450"))
    assert r["status"] == "flagged" and "disagree" in r["reasons"][0]


def test_amount_words_and_digits_agree():
    t = "₹2,450 (രണ്ടായിരത്തി നാനൂറ്റി അമ്പത്)"
    assert one(t, ent("amount", t, "2450"))["status"] == "ok"


def test_amount_half_rupee_flagged():
    r = one("നാലര രൂപ", ent("amount", "നാലര", "4"))
    assert r["status"] == "flagged"


def test_date_rules():
    assert one("നവംബർ 5", ent("date", "നവംബർ 5", "2026-11-05", "due"))["status"] == "ok"
    past = one("ഒക്ടോബർ 5", ent("date", "ഒക്ടോബർ 5", "2026-10-05", "due"))
    assert past["status"] == "flagged" and "past" in past["reasons"][0]
    assert one("ഒക്ടോബർ 5", ent("date", "ഒക്ടോബർ 5", "2026-10-05", "other"))["status"] == "ok"
    assert one("ഫെബ്രുവരി 30", ent("date", "ഫെബ്രുവരി 30", "2027-02-30", "due"))["status"] == "flagged"


def test_policy_id(record):
    t = "policy number SBL 2 0 4 7 8 1 3 ആണ്"
    assert one(t, ent("policy_or_account_id", "SBL 2 0 4 7 8 1 3", "SBL2047813"), record)["status"] == "ok"
    short = one(t, ent("policy_or_account_id", "SBL 2 0 4 7 8 1 3", "SBL204781"), record)
    assert short["status"] == "flagged" and "3 letters then 7 digits" in short["reasons"][0]
    other = one("SBL 2047814", ent("policy_or_account_id", "SBL 2047814", "SBL2047814"), record)
    assert other["status"] == "flagged" and "on file" in other["reasons"][0]


@pytest.mark.parametrize("transcript,span,status,suggestion", [
    ("ഞാൻ ലുലു മാളിൽ പോയി", "ലുലു മാളിൽ", "ok", None),
    ("ഞാൻ ലു മാളിൽ പോയി", "ലു മാളിൽ", "flagged", "ലുലു മാൾ"),             # T13
    ("എടാപ്പള്ളി മെട്രോ", "എടാപ്പള്ളി", "flagged", "ഇടപ്പള്ളി"),           # T13
    ("എടപ്പള്ളി മെട്രോ", "എടപ്പള്ളി", "flagged", "ഇടപ്പള്ളി"),             # T26 with keyterms
    ("ഇടപ്പള്ളിയിൽ ആണ് വീട്", "ഇടപ്പള്ളിയിൽ", "ok", None),
    ("തൃപ്പൂണിത്തുറ branch", "തൃപ്പൂണിത്തുറ", "ok", None),
    ("Lulu Mall ന്റെ അടുത്ത്", "Lulu Mall", "ok", None),
    ("Edapally", "Edapally", "flagged", "Edappally"),
    ("മുംബൈ", "മുംബൈ", "flagged", None),
])
def test_place_names(offline_translit, record, transcript, span, status, suggestion):
    r = one(transcript, ent("place_name", span, span), record)
    assert (r["status"], r["suggestion"]) == (status, suggestion)


def test_person_name_with_title(offline_translit, record):
    assert one("ആനന്ദ് സാർ ആണ് വിളിച്ചത്", ent("person_name", "ആനന്ദ് സാർ", "ആനന്ദ്"), record)["status"] == "ok"


def test_span_not_in_transcript_flagged():
    r = one("എന്റെ നമ്പർ 9847012345", ent("phone", "9847012346", "9847012346"))
    assert r["status"] == "flagged" and "not in the transcript" in r["reasons"][0]


def test_unclassified_number_flagged():
    r = one("കോഡ് 7731", ent("unclassified_number", "7731", "7731"))
    assert r["status"] == "flagged"


def test_name_with_branch_word(offline_translit, record):
    t = "തൃപ്പൂണിത്തുറ branch ലെ Anand sir"
    assert one(t, ent("place_name", "തൃപ്പൂണിത്തുറ branch", "തൃപ്പൂണിത്തുറ branch"), record)["status"] == "ok"
    assert one(t, ent("person_name", "Anand sir", "Anand sir"), record)["status"] == "ok"
