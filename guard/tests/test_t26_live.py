"""T26 reproduced against the live API: keyterms only help in the output script.

Writes eval/t26_keyterms.json so the README can quote what happened.
"""
import json
import os

import pytest

from keyterms import build_keyterms
from sarvam import HERE, SarvamError, api_key
from stt import transcribe

try:
    api_key()
    HAVE_KEY = True
except SarvamError:
    HAVE_KEY = False

pytestmark = [pytest.mark.live, pytest.mark.skipif(not HAVE_KEY, reason="no SARVAM_API_KEY")]

T13 = os.path.join(HERE, "..", "api-tests", "audio", "T13_src.wav")
TERMS = ["Lulu Mall", "Edappally"]


def test_t26_native_keyterms_fix_lulu():
    runs = {
        "none": transcribe(T13),
        "english": transcribe(T13, keyterms=TERMS, native_keyterms=False),
        "native_only": transcribe(T13, keyterms=build_keyterms(TERMS, keep_original=False), native_keyterms=False),
        "native_plus_english": transcribe(T13, keyterms=TERMS),  # the guard's default
    }
    for r in runs.values():
        r["has_lulu"] = "ലുലു" in r["transcript"]
        r["has_edappally"] = "ഇടപ്പള്ളി" in r["transcript"]
    with open(os.path.join(HERE, "eval", "t26_keyterms.json"), "w", encoding="utf-8") as f:
        json.dump(runs, f, ensure_ascii=False, indent=1)
    for name, r in runs.items():
        print(f"\n{name:20} {r['keyterms_sent']}\n{'':20} {r['transcript']}")

    assert not runs["none"]["has_lulu"]
    assert not runs["english"]["has_lulu"], "English keyterms should not fix Lulu (T26)"
    assert runs["native_only"]["has_lulu"]
    assert runs["native_plus_english"]["has_lulu"], "guard default must keep the T26 fix"
