import json
import os

import pytest

import keyterms
from sarvam import HERE

# T05 as logged in sarvam-error-log.xlsx: Indus voice heard the spoken 98470 12345 as below.
# Only the phone part of the transcript was logged, so that is all we use.
T05 = "എൻ്റെ നമ്പർ തൊണ്ണൂറ്റി നാൽപ്പത്തേഴ് പൂജ്യം ഒന്ന് രണ്ട് മൂന്ന് നാല് അഞ്ച്"
T05_SPAN = "തൊണ്ണൂറ്റി നാൽപ്പത്തേഴ് പൂജ്യം ഒന്ന് രണ്ട് മൂന്ന് നാല് അഞ്ച്"
# T14: saaras:v4 transcript of TTS audio for "98470 12345 ... ₹2,450 ... നവംബർ 5"
T14 = "എൻ്റെ ഫോൺ നമ്പർ 9847012345 ആണ്. 2450 റുപ്പീസിൻ്റെ ബിൽ നവംബർ 5ന് മുമ്പ് അടയ്ക്കണം."
TODAY = "2026-10-29"

TRANSLIT = {"Edappally": "ഇടപ്പള്ളി", "Lulu Mall": "ലുലു മാൾ", "Vyttila": "വൈറ്റില", "Kakkanad": "കാക്കനാട്",
            "Anand": "ആനന്ദ്", "Netanya": "നെതന്യ", "Tripunithura": "ത്രിപുണിത്തുറ"}


@pytest.fixture
def record():
    with open(os.path.join(HERE, "data", "mock_customer.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def offline_translit(monkeypatch):
    monkeypatch.setattr(keyterms, "_transliterate", lambda t, lang: TRANSLIT[t])
