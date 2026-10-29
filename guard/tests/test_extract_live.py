"""extract + validate against the live sarvam-105b. Writes eval/m2_extract_live.json.

Text cases are the recording-script lines typed in as text: they test extraction alone,
as if speech-to-text had been perfect. Audio comes in M4.
"""
import json
import os

import pytest

from conftest import T05, T14, TODAY
from extract import extract
from sarvam import HERE, SarvamError, api_key
from validate import validate

try:
    api_key()
    HAVE_KEY = True
except SarvamError:
    HAVE_KEY = False

pytestmark = [pytest.mark.live, pytest.mark.skipif(not HAVE_KEY, reason="no SARVAM_API_KEY")]

# id: (transcript, expected [(type, value, status)])
CASES = {
    "T05": (T05, [("phone", None, "flagged")]),
    "T14": (T14, [("phone", "9847012345", "ok"), ("amount", 2450, "ok"), ("date", "2026-11-05", "ok")]),
    "R04_text": ("എന്റെ EMI പതിനാലായിരത്തി നാനൂറ്റി പതിനഞ്ച് രൂപയാണ്", [("amount", 14415, "ok")]),
    "R05_text": ("നാലര ലക്ഷം രൂപയുടെ loan ആണ് എടുത്തത്", [("amount", 450000, "ok")]),
    "R06_text": ("അടുത്ത മാസം അഞ്ചാം തീയതി premium അടയ്ക്കാം", [("date", "2026-11-05", "ok")]),
    "R07_text": ("എന്റെ policy number SBL 2 0 4 7 8 1 3 ആണ്", [("policy_or_account_id", "SBL2047813", "ok")]),
    "R09_text": ("തൃപ്പൂണിത്തുറ branch ലെ Anand sir ആണ് എന്നെ വിളിച്ചത്",
                 [("place_name", None, "ok"), ("person_name", None, "ok")]),
    "R10_text": ("എന്റെ നമ്പർ 98470... അല്ല, 98471 12345", [("phone", "9847112345", "ok")]),
}


@pytest.fixture(scope="module")
def results():
    with open(os.path.join(HERE, "data", "mock_customer.json"), encoding="utf-8") as f:
        record = json.load(f)
    out = {}
    for cid, (transcript, _) in CASES.items():
        x = extract(transcript, today=TODAY)
        x["checked"] = validate(transcript, x["entities"], record=record, today=TODAY)
        out[cid] = x
    with open(os.path.join(HERE, "eval", "m2_extract_live.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    return out


@pytest.mark.parametrize("cid", CASES)
def test_case(results, cid):
    r = results[cid]
    print(f"\n{cid} ({r['latency_s']}s{', cached' if r['cached'] else ''}): {r['transcript']}")
    for c in r["checked"]:
        print(f"   {c['type']:22} {c['raw_span']!r:45} -> {c['value']!s:12} {c['status']:8} {'; '.join(c['reasons'])}")
    for d in r["dropped"]:
        print(f"   dropped {d['type']} {d['raw_span']!r}: {d['dropped_because']}")
    got = sorted(((c["type"], c["value"], c["status"]) for c in r["checked"]), key=lambda x: x[0])
    expected = sorted(CASES[cid][1], key=lambda x: x[0])
    assert len(got) == len(expected), got
    for (t, v, s), (gt, gv, gs) in zip(expected, got):
        assert (t, s) == (gt, gs) and (v is None or v == gv), got
