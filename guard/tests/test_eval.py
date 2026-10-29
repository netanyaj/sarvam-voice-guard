import datetime as dt

import pytest

import eval as E


def test_cases_load():
    cs = E.cases()
    clips = [c["clip"] for c in cs]
    assert clips[:5] == ["T13", "T15 low noise", "T15 medium noise", "T15 high noise", "T14"]
    assert "T05" in clips and "R11 typed" not in clips and "R12 typed" not in clips
    r01 = next(c for c in cs if c["clip"] == "R01 typed")
    assert r01["transcript"] == "എന്റെ നമ്പർ 98470 12345 ആണ്"  # stage direction removed
    r06 = next(c for c in cs if c["clip"] == "R06 typed")
    assert r06["truth"] == [("date", "2026-11-05")]
    r09 = next(c for c in cs if c["clip"] == "R09 typed")
    assert r09["truth"] == [("place_name", "തൃപ്പൂണിത്തുറ"), ("person_name", "Anand")]


def test_resolve_next_month_wraps_year():
    assert E.resolve_truth("next month 5th (x)", dt.date(2026, 12, 20)) == "2027-01-05"
    assert E.resolve_truth("9847012345", dt.date(2026, 12, 20)) == "9847012345"


def test_is_right(offline_translit):
    assert E.is_right("phone", "+91 98470 12345", "9847012345")
    assert E.is_right("amount", 2450, "2450")
    assert not E.is_right("phone", "947012345", "9847012345")
    assert E.is_right("place_name", "ലുലു മാളിൽ", "Lulu Mall")
    assert E.is_right("place_name", "Lulu Mall", "Lulu Mall")
    assert not E.is_right("place_name", "എടപ്പള്ളി", "Edappally")
    assert not E.is_right("place_name", "ലൂമാല്യ", "Lulu Mall")


def c(type_, value, status="ok"):
    return {"type": type_, "raw_span": str(value), "value": value, "status": status, "reasons": []}


def test_guard_outcomes(offline_translit):
    truth = [("phone", "9847012345"), ("amount", "2450"), ("otp", "482913"), ("date", "2026-11-05"),
             ("place_name", "Edappally")]
    checked = [c("phone", "9847012345", "flagged"), c("amount", 2400, "flagged"), c("otp", "482910"),
               c("unclassified_number", "2026", "flagged")]
    scores, extra = E.score_guard(truth, checked)
    assert [s["result"] for s in scores] == ["false alarm", "caught", "wrong, passed", "caught", "missed"]
    assert extra == []


def test_extra_flags_are_counted():
    scores, extra = E.score_guard([("phone", "9847012345")], [c("phone", "9847012345"), c("amount", 5, "flagged")])
    assert scores[0]["result"] == "correct" and len(extra) == 1


def test_baseline_outcomes():
    out = E.score_baseline([("phone", "9847012345"), ("amount", "2450")], [c("phone", "947012345")])
    assert [s["result"] for s in out] == ["wrong, passed", "missed"]


def test_match_prefers_the_right_one(offline_translit):
    truth = [("place_name", "Edappally"), ("place_name", "Lulu Mall")]
    ents = [c("place_name", "ലുലു മാൾ"), c("place_name", "ഇടപ്പള്ളി")]
    pairs, _ = E.match(truth, ents)
    assert pairs == [1, 0]


@pytest.mark.live
def test_full_eval_no_wrong_value_passes_with_guard():
    rows = E.main()
    assert rows and all(s["result"] != "wrong, passed" for r in rows for s in r["guard_scores"])
