"""M3 deliverable: read-back audio for T05, checked by playing it back into saaras:v4.

Writes eval/readback/*.wav and eval/m3_readback.json.
"""
import json
import os
import re
import shutil

import pytest

import confirm
import numwords
from conftest import T05, TODAY
from extract import extract
from sarvam import HERE
from stt import transcribe
from validate import validate

pytestmark = pytest.mark.live
OUT = os.path.join(HERE, "eval", "readback")

# T05 through the real pipeline, plus one read-back of each other kind
CASES = {
    "T05": None,
    "phone_yes_no": {"type": "phone", "raw_span": "r", "value": "9847012345", "status": "flagged", "reasons": ["x"]},
    "policy_id": {"type": "policy_or_account_id", "raw_span": "r", "value": "SBL2047831", "status": "flagged",
                  "reasons": ["does not match the policy or account number on file"]},
    "amount": {"type": "amount", "raw_span": "r", "value": 450000, "status": "flagged", "reasons": ["x"]},
    "place": {"type": "place_name", "raw_span": "എടാപ്പള്ളി", "value": "എടാപ്പള്ളി", "status": "flagged",
              "reasons": ["x"], "suggestion": "ഇടപ്പള്ളി"},
}


def heard_digits(text):
    """Digits in what saaras:v4 heard back, written as numerals or as Malayalam words (T14)."""
    return re.sub(r"\D", "", text) + "|" + numwords.digits(text)[0]


def expected_digits(c):
    return re.sub(r"\D", "", str(c["value"])) if c["type"] in ("phone", "policy_or_account_id") else None


@pytest.fixture(scope="module")
def results():
    with open(os.path.join(HERE, "data", "mock_customer.json"), encoding="utf-8") as f:
        record = json.load(f)
    os.makedirs(OUT, exist_ok=True)
    out = {}
    for name, c in CASES.items():
        if c is None:
            checked = validate(T05, extract(T05, today=TODAY)["entities"], record, today=TODAY)
            [c] = [x for x in checked if x["type"] == "phone"]
        [q] = confirm.confirm([c], audio=False, today=TODAY)
        for speaker in ("kavya", "anand"):
            path, _ = confirm.speak(q["text"], speaker)
            keep = os.path.join(OUT, f"{name}_{speaker}.wav")
            shutil.copyfile(path, keep)
            back = transcribe(keep)["transcript"]
            out[f"{name}_{speaker}"] = {"checked": c, "question": q["text"], "speaker": speaker,
                                        "audio": os.path.relpath(keep, HERE), "heard_back": back}
    with open(os.path.join(HERE, "eval", "m3_readback.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


def test_t05_readback(results):
    for speaker in ("kavya", "anand"):
        r = results[f"T05_{speaker}"]
        assert r["checked"]["status"] == "flagged"
        assert r["question"].startswith("ഞാൻ കേട്ടത്")
        # every digit read back is heard back, in order
        assert expected_digits(r["checked"]) in heard_digits(r["heard_back"])


@pytest.mark.parametrize("name", ["phone_yes_no", "policy_id"])
def test_digits_survive_tts(results, name):
    for speaker in ("kavya", "anand"):
        r = results[f"{name}_{speaker}"]
        assert expected_digits(r["checked"]) in heard_digits(r["heard_back"]), r


def test_all_cases_spoken(results):
    assert len(results) == 2 * len(CASES)
    assert all(os.path.getsize(os.path.join(HERE, r["audio"])) > 10_000 for r in results.values())


def test_amount_and_place_survive_tts(results):
    for speaker in ("kavya", "anand"):
        assert "450000" in heard_digits(results[f"amount_{speaker}"]["heard_back"])
        assert "ഇടപ്പള്ളി" in results[f"place_{speaker}"]["heard_back"]
