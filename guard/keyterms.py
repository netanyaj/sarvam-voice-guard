"""Build speech-to-text keyterms in the script the transcript will be written in.

Finding T26: saaras:v4 keyterms only help when they are in the output script. English keyterms
["Lulu Mall", "Edappally"] changed nothing on a Malayalam transcript; Malayalam-script keyterms
fixed "ലുലു". So for a Malayalam call we transliterate each English term and send the native form
first, keeping the English original only while there is room under the 50-term limit.

Transliteration is phonetic, not a spelling dictionary ("Tripunithura" comes back as
ത്രിപുണിത്തുറ, the usual spelling is തൃപ്പൂണിത്തുറ). Known spellings in data/native_spellings.json
win over transliteration.
"""
import json
import os

from sarvam import CACHE_DIR, HERE, post_json

MAX_TERMS = 50
MAX_CHARS = 64
SPELLINGS_PATH = os.path.join(HERE, "data", "native_spellings.json")
CACHE_PATH = os.path.join(CACHE_DIR, "transliterate.json")


def _load_json(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def known_spellings(language_code):
    return _load_json(SPELLINGS_PATH).get(language_code, {})


def _transliterate(term, language_code):
    cache = _load_json(CACHE_PATH)
    key = f"{language_code}|{term}"
    if key not in cache:
        j = post_json("/transliterate", {"input": term, "source_language_code": "en-IN",
                                         "target_language_code": language_code})
        cache[key] = j["transliterated_text"]
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1)
    return cache[key]


def to_native(term, language_code):
    """Native-script form of an English term. Terms already in a non-Latin script pass through."""
    if not term.isascii():
        return term
    spellings = known_spellings(language_code)
    if term in spellings:
        return spellings[term]
    return _transliterate(term, language_code)


def build_keyterms(terms, language_code="ml-IN", keep_original=True):
    """Return the keyterms list to send for this language: native forms first, then originals."""
    terms = [t.strip() for t in terms if t and t.strip()]
    if language_code in ("en-IN", "unknown"):
        # English output, or a script we cannot know in advance: send the terms as given.
        candidates = terms
    else:
        candidates = [to_native(t, language_code) for t in terms]
        if keep_original:
            candidates += terms
    out = []
    for t in candidates:
        if len(t) <= MAX_CHARS and t not in out:
            out.append(t)
    return out[:MAX_TERMS]
