"""Pull high-stakes details out of a transcript with sarvam-105b, then check what it missed.

Model settings, from trying them on the T14 transcript (29 Oct 2026):
- reasoning_effort is sent as null. With "low" the model still thought for 3,000+ tokens
  (18 s on two sentences, and an empty reply at the default 2,048-token cap); null answers in ~1 s.
- JSON mode ("json_object") with the shape spelled out in the prompt, not strict json_schema.
  With json_schema the reply often turned into blank space until the token cap (6 of 6 runs with
  this schema). JSON mode gave the right shape in 16 of 16 runs; the shape is still checked here.
- Same input can give different output even at temperature 0 (one run dropped a date), which is
  one more reason for the backstop below.

Afterwards, fixed rules (no model):
- drop exact duplicates, and any detail whose words sit inside another detail's words
  (the "5" inside "നവംബർ 5ന്");
- drop a date whose words contain no number, month or day word (the model once tagged "മുമ്പ്",
  "before", as today's date);
- backstop: every digit run, every run of two or more number words, and any date words
  (month names, തീയതി, നാളെ...) must belong to some detail. Anything left over is added as
  "unclassified_number" or "unclassified_date" so it gets flagged, not lost.

Responses are cached on disk by transcript, date and prompt, so eval reruns are cheap.

    ../.venv/bin/python extract.py "എന്റെ നമ്പർ 98470 12345 ആണ്"
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time

import numwords
from sarvam import CACHE_DIR, SarvamError, post_json

MODEL = "sarvam-105b"
TYPES = ["phone", "otp", "amount", "date", "policy_or_account_id", "person_name", "place_name"]
CACHE = os.path.join(CACHE_DIR, "extract")

PROMPT = """You extract high-stakes details from one customer-care call transcript (Malayalam, English, or mixed). Today is {today}.

Detail types: phone, otp, amount, date, policy_or_account_id, person_name, place_name.

Rules:
1. Only extract what is in the transcript. Never invent, guess, or correct anything.
2. raw_span: copy the exact words of that one detail from the transcript, character for character, without surrounding words like "എന്റെ നമ്പർ" or "ആണ്".
3. value:
   - phone, otp: digits only. Convert Malayalam number words to digits, word by word, in order.
   - policy_or_account_id: capital Latin letters and digits, no spaces. Spelled letters such as "എസ് ബി എൽ" become "SBL".
   - amount: rupees as a whole number in digits (4.5 ലക്ഷം -> 450000, പതിനാലായിരത്തി നാനൂറ്റി പതിനഞ്ച് -> 14415).
   - date: YYYY-MM-DD. Resolve relative dates ("അടുത്ത മാസം അഞ്ചാം തീയതി") from today.
   - person_name, place_name: the name as written in the transcript, in the same script, without case endings (ഇടപ്പള്ളിയിൽ -> ഇടപ്പള്ളി) or titles (sir, സാർ). Keep the spelling exactly as heard, even if it looks wrong.
4. If the speaker corrects themselves, extract only the final value and put the abandoned words in superseded_raw_spans. Otherwise superseded_raw_spans is [].
5. Extract each detail once. A number that is part of a date or amount is not a separate detail. Words like "ഒന്ന്" used to mean "please" or "once" are not numbers. Words like "മുമ്പ്" (before) are not dates.
6. date_kind: "due" for a deadline, payment, or appointment; "other" for any other date; "none" for details that are not dates.

Reply with JSON only, exactly in this shape (an empty list if there are no details):
{{"entities": [{{"type": "phone", "raw_span": "...", "value": "...", "date_kind": "none", "superseded_raw_spans": []}}]}}"""

MONTHS = ["ജനുവരി", "ഫെബ്രുവരി", "മാർച്ച്", "ഏപ്രിൽ", "മെയ്", "ജൂൺ", "ജൂലൈ", "ഓഗസ്റ്റ്", "ആഗസ്റ്റ്",
          "സെപ്റ്റംബർ", "ഒക്ടോബർ", "നവംബർ", "ഡിസംബർ", "january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]
DAY_WORDS = ["ഇന്ന്", "നാളെ", "മറ്റന്നാൾ", "ഇന്നലെ", "തീയതി", "മാസം", "ആഴ്ച", "ഞായർ", "തിങ്കൾ", "ചൊവ്വ",
             "ബുധൻ", "വ്യാഴം", "വെള്ളി", "ശനി", "today", "tomorrow", "monday", "tuesday", "wednesday",
             "thursday", "friday", "saturday", "sunday"]
# words that only appear when someone is giving a date (not "ഇന്ന്", which also means "now")
DATE_ONLY_WORDS = ["തീയതി", "നാളെ", "മറ്റന്നാൾ", "tomorrow"]
DIGIT_RUN = re.compile(r"\d(?:[\d,.]|\s(?=\d))*\d|\d")


def _cache_key(transcript, today):
    blob = json.dumps([MODEL, PROMPT, transcript, today], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def call_model(transcript, today):
    """Raw entities from the model (cached). Returns (entities, latency_s, cached)."""
    path = os.path.join(CACHE, _cache_key(transcript, today) + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            hit = json.load(f)
        return hit["entities"], hit["latency_s"], True
    t = time.time()
    j = post_json("/v1/chat/completions", {
        "model": MODEL, "temperature": 0, "reasoning_effort": None, "max_tokens": 2000,
        "messages": [{"role": "system", "content": PROMPT.format(today=today)},
                     {"role": "user", "content": transcript}],
        "response_format": {"type": "json_object"},
    }, timeout=120)
    latency = round(time.time() - t, 2)
    choice = j["choices"][0]
    if not choice["message"].get("content"):
        raise SarvamError(f"empty reply from {MODEL} (finish_reason={choice.get('finish_reason')})")
    entities = _check_shape(choice["message"]["content"])
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"transcript": transcript, "today": today, "entities": entities, "latency_s": latency},
                  f, ensure_ascii=False, indent=1)
    return entities, latency, False


def _check_shape(content):
    """Parse the reply and keep only well-formed details of a known type."""
    try:
        items = json.loads(content)["entities"]
    except (ValueError, KeyError, TypeError) as e:
        raise SarvamError(f"{MODEL} reply is not the expected JSON: {content[:200]!r}") from e
    out = []
    for e in items if isinstance(items, list) else []:
        if not isinstance(e, dict) or e.get("type") not in TYPES or not e.get("raw_span"):
            continue
        spans = e.get("superseded_raw_spans") or []
        out.append({"type": e["type"], "raw_span": str(e["raw_span"]), "value": str(e.get("value", "")),
                    "date_kind": e.get("date_kind") if e.get("date_kind") in ("due", "other") else "none",
                    "superseded_raw_spans": [str(x) for x in spans] if isinstance(spans, list) else []})
    return out


def _digits(s):
    return re.sub(r"\D", "", s)


def _has_date_words(span):
    s = numwords.normalize(span).lower()
    return bool(re.search(r"\d", s) or numwords.parse(s) or any(w in s for w in MONTHS + DAY_WORDS))


def tidy(entities):
    """Fixed clean-up of the model output. Returns (kept, dropped); dropped items carry a reason."""
    kept, dropped, seen = [], [], set()
    for e in entities:
        e = {**e, "raw_span": numwords.normalize(e["raw_span"]).strip(),
             "superseded_raw_spans": [numwords.normalize(s) for s in e.get("superseded_raw_spans", [])]}
        key = (e["type"], e["raw_span"], e["value"])
        if key in seen:
            dropped.append({**e, "dropped_because": "duplicate"})
            continue
        seen.add(key)
        if e["type"] == "date" and not _has_date_words(e["raw_span"]):
            dropped.append({**e, "dropped_because": "no date words in the span"})
            continue
        kept.append(e)
    final = []
    for e in kept:
        inside = next((o for o in kept if o is not e and e["raw_span"] != o["raw_span"]
                       and e["raw_span"] in o["raw_span"]), None)
        if inside:
            dropped.append({**e, "dropped_because": f"part of the {inside['type']} '{inside['raw_span']}'"})
        else:
            final.append(e)
    return final, dropped


def backstop(transcript, entities):
    """Numbers in the transcript that no detail accounts for, as unclassified_number entities."""
    transcript = numwords.normalize(transcript)
    spans = [e["raw_span"] for e in entities] + [s for e in entities for s in e.get("superseded_raw_spans", [])]
    covered_digits = [_digits(e["value"]) for e in entities] + [_digits(s) for s in spans]
    extra = []
    for m in DIGIT_RUN.finditer(transcript):
        run = m.group(0).strip()
        if not any(_digits(run) and _digits(run) in d for d in covered_digits):
            extra.append(run)
    for run in numwords.number_runs(transcript):
        words = run.split()
        if not any(sum(w in s.split() for w in words) * 2 >= len(words) for s in spans):
            extra.append(run)
    out = [{"type": "unclassified_number", "raw_span": r, "value": numwords.digits(r)[0],
            "date_kind": "none", "superseded_raw_spans": []} for r in extra]
    if not any(e["type"] == "date" for e in entities):
        low = transcript.lower()
        words = [w for w in MONTHS + DATE_ONLY_WORDS if w in low]
        if words:
            out.append({"type": "unclassified_date", "raw_span": words[0], "value": "", "date_kind": "none",
                        "superseded_raw_spans": []})
    return out


def extract(transcript, today=None):
    today = today or dt.date.today().isoformat()
    raw, latency, cached = call_model(transcript, today)
    entities, dropped = tidy(raw)
    entities += backstop(transcript, entities)
    return {"transcript": transcript, "today": today, "entities": entities, "dropped": dropped,
            "model_raw": raw, "latency_s": latency, "cached": cached}


if __name__ == "__main__":
    print(json.dumps(extract(" ".join(sys.argv[1:])), ensure_ascii=False, indent=1))
