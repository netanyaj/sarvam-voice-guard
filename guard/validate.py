"""Check each extracted detail with fixed rules and mark it ok or flagged, with a plain reason.

The model's value is never trusted on its own. For numbers, the words actually heard (raw_span)
are read again by numwords.py and must agree with the model's value. If the words do not combine
cleanly (T05), the detail is flagged even when the model's answer looks valid.
"""
import datetime as dt
import difflib
import re

import numwords
from keyterms import to_native

# Words that ride along with a name but are not part of it ("Anand sir", "തൃപ്പൂണിത്തുറ branch")
NOT_NAME = {"സാർ", "സർ", "sir", "മാഡം", "madam", "മാം", "ചേട്ടൻ", "ചേച്ചി", "mr", "mrs", "ms",
            "branch", "ബ്രാഞ്ച്", "office", "ഓഫീസ്", "metro", "മെട്രോ", "station", "സ്റ്റേഷൻ"}
# Case endings, after chillu letters are written out (ൽ -> ല്)
SUFFIXES = sorted(numwords.dechillu(s) for s in [
    "യിലേക്ക്", "ിലേക്ക്", "യിലെ", "ിലെ", "യിൽ", "ിൽ", "യുടെ", "ിന്റെ", "ിൻ്റെ", "ന്റെ", "ൻ്റെ", "ിനെ", "യെ",
    "ിന്", "ക്ക്", "ലെ", "ൽ", "ൾ", "ആണ്", "ാണ്"])
SUFFIXES.sort(key=len, reverse=True)
NAME_OK = 0.999
NAME_SUGGEST = 0.6
NAME_FIND = 0.82  # set from few examples: thanks->Anand 0.80 (must not match), എടാപ്പള്ളി 0.84 (must)


def _span_check(raw_span, value_digits, what):
    """Digits read from the words heard vs the model's digits."""
    heard, reasons = numwords.digits(raw_span)
    if heard and value_digits and heard != value_digits:
        reasons.append(f"the words heard read as {heard}, but the {what} was taken as {value_digits}")
    return heard, reasons


def _strip_prefix(digits):
    """+91 or a leading 0 in front of a 10-digit mobile number."""
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        return digits[1:]
    return digits


def check_phone(e, record):
    value = _strip_prefix(re.sub(r"\D", "", e["value"]))
    heard, reasons = numwords.digits(e["raw_span"])
    heard = _strip_prefix(heard)
    if heard and heard != value:
        reasons.append(f"the words heard read as {heard}, but the number was taken as {value}")
    if len(value) != 10:
        reasons.insert(0, f"only {len(value)} digits heard, a mobile number has 10" if len(value) < 10
                       else f"{len(value)} digits heard, a mobile number has 10")
    elif value[0] not in "6789":
        reasons.insert(0, f"starts with {value[0]}; Indian mobile numbers start with 6, 7, 8 or 9")
    return value, heard, reasons, None


def check_otp(e, record):
    value = re.sub(r"\D", "", e["value"])
    heard, reasons = _span_check(e["raw_span"], value, "OTP")
    if len(value) not in (4, 6):
        reasons.insert(0, f"{len(value)} digits heard; an OTP has 4 or 6")
    return value, heard, reasons, None


def check_amount(e, record):
    reasons = []
    try:
        value = int(re.sub(r"[^\d]", "", e["value"]) or "x")
    except ValueError:
        return e["value"], None, ["could not read the amount as a number"], None
    groups = numwords.parse(e["raw_span"])
    reasons += list(dict.fromkeys(g.reason for g in groups if g.ambiguous))
    readings = list(dict.fromkeys(g.value for g in groups))
    heard = None
    if not groups:
        reasons.append("no number found in the words heard")
    elif len(readings) > 1:
        has_both = any(g.has_words for g in groups) and any(not g.has_words for g in groups)
        nums = ", ".join(numwords._fmt(r) for r in readings)
        reasons.append(f"digits and words disagree ({nums})" if has_both
                       else f"several numbers heard here ({nums}); not clear which is the amount")
    else:
        heard = readings[0]
        if heard.denominator != 1:
            reasons.append(f"amount comes to {float(heard)} rupees, not a whole number")
        elif int(heard) != value:
            reasons.append(f"the words heard come to {int(heard)}, but the amount was taken as {value}")
        heard = numwords._fmt(heard)
    if value <= 0:
        reasons.insert(0, "amount is zero")
    return value, heard, reasons, None


def check_date(e, record, today):
    try:
        d = dt.date.fromisoformat(e["value"])
    except ValueError:
        return e["value"], None, ["could not pin this down to a calendar date"], None
    reasons = []
    if e.get("date_kind") == "due" and d < today:
        reasons.append(f"due date {d.isoformat()} is in the past")
    return d.isoformat(), None, reasons, None


def id_pattern(example):
    """'SBL2047813' -> regex for 3 letters then 7 digits, and a plain description."""
    parts = re.findall(r"[A-Z]+|\d+", example.upper())
    regex = "".join(f"[A-Z]{{{len(p)}}}" if p.isalpha() else f"\\d{{{len(p)}}}" for p in parts)
    desc = " then ".join(f"{len(p)} {'letters' if p.isalpha() else 'digits'}" for p in parts)
    return re.compile(f"^{regex}$"), desc


def check_id(e, record):
    value = re.sub(r"[^A-Z0-9]", "", e["value"].upper())
    heard, reasons = _span_check(e["raw_span"], re.sub(r"\D", "", value), "number")
    on_file = (record or {}).get("policy_or_account_id")
    if on_file:
        pattern, desc = id_pattern(on_file)
        if not pattern.match(value):
            reasons.insert(0, f"should be {desc}; heard {value}")
        elif value != on_file.upper():
            reasons.insert(0, "does not match the policy or account number on file")
    return value, heard, reasons, None


def known_names(record, extra_terms=(), language_code="ml-IN"):
    """{written form: English name} for every name the guard knows, in both scripts."""
    record = record or {}
    names = [record.get("name"), record.get("branch"), *record.get("known_places", []),
             *record.get("known_people", []), *extra_terms]
    out = {}
    for n in filter(None, names):
        out[n] = n
        out[to_native(n, language_code)] = n
    return out


def _name_key(s):
    s = numwords.dechillu(numwords.normalize(s)).lower()
    return s.rstrip("്").replace(" ", "")


def _candidates(raw):
    words = [w for w in numwords.normalize(raw).split() if w.lower().strip(".") not in NOT_NAME]
    base = numwords.dechillu(" ".join(words))
    out = [base]
    for suf in SUFFIXES:
        if base.endswith(suf) and len(base) > len(suf) + 1:
            out.append(base[:-len(suf)])
    return [_name_key(c) for c in out]


def check_name(e, record, names):
    if not names:
        return e["value"], None, [], None
    best, best_name = 0.0, None
    for cand in _candidates(e["raw_span"]):
        for form in names:
            score = difflib.SequenceMatcher(None, cand, _name_key(form)).ratio()
            if score > best:
                best, best_name = score, form
    if best >= NAME_OK:
        return e["value"], None, [], None
    if best >= NAME_SUGGEST:
        # suggest in the script that was heard
        english = names[best_name]
        native = next((f for f, en in names.items() if en == english and not f.isascii()), best_name)
        suggestion = english if e["raw_span"].isascii() else native
        return e["value"], None, [f"heard '{e['raw_span']}'; the closest name on file is '{suggestion}'"], suggestion
    return e["value"], None, ["not a name on file"], None


def _name_score(text, form):
    return max(difflib.SequenceMatcher(None, c, _name_key(form)).ratio() for c in _candidates(text))


def name_backstop(transcript, entities, record, names):
    """Names on file that appear in the transcript but were not extracted (the model often skips
    place names in casual speech: T13, and "Lulu Mall" in R08). Every window of words as long as a
    known name is scored against it; a score of NAME_FIND or more adds the name as a detail, so
    validate() checks it like any other. NAME_FIND is stricter than NAME_SUGGEST because here
    every word is a candidate: "നന്ദി" (thanks) scores 0.80 against ആനന്ദ് (Anand)."""
    text = numwords.normalize(transcript)
    spans = []
    for m in re.finditer(r"[^\s.,!?;:()\"']+", text):
        spans.append((m.start(), m.end()))
    covered = []
    for e in entities:
        i = text.find(numwords.normalize(e["raw_span"]))
        if i >= 0:
            covered.append((i, i + len(numwords.normalize(e["raw_span"]))))
    people = {(record or {}).get("name"), *(record or {}).get("known_people", [])}
    have = {names[f] for e in entities if e["type"] in ("person_name", "place_name")
            for f in names if _name_score(e["value"] or e["raw_span"], f) >= NAME_FIND}
    found = {}
    for form, english in names.items():
        if english in have:
            continue
        n = len(form.split())
        for k in range(len(spans) - n + 1):
            start, end = spans[k][0], spans[k + n - 1][1]
            if any(start < b and a < end for a, b in covered):
                continue
            score = _name_score(text[start:end], form)
            if score >= NAME_FIND and score > found.get(english, (0,))[0]:
                found[english] = (score, start, end)
    out = []
    for english, (_, start, end) in sorted(found.items(), key=lambda x: x[1][1]):
        if any(start < b and a < end for a, b in covered):
            continue
        covered.append((start, end))
        out.append({"type": "person_name" if english in people else "place_name", "raw_span": text[start:end],
                    "value": text[start:end], "date_kind": "none", "superseded_raw_spans": [],
                    "found_by": "name check"})
    return out


def validate(transcript, entities, record=None, extra_terms=(), today=None, language_code="ml-IN"):
    today = dt.date.fromisoformat(today) if isinstance(today, str) else (today or dt.date.today())
    names = None
    if record or extra_terms:
        names = known_names(record, extra_terms, language_code)
        entities = list(entities) + name_backstop(transcript, entities, record, names)
    text = numwords.normalize(transcript)
    out = []
    for e in entities:
        t = e["type"]
        if t == "phone":
            value, heard, reasons, sugg = check_phone(e, record)
        elif t == "otp":
            value, heard, reasons, sugg = check_otp(e, record)
        elif t == "amount":
            value, heard, reasons, sugg = check_amount(e, record)
        elif t == "date":
            value, heard, reasons, sugg = check_date(e, record, today)
        elif t == "policy_or_account_id":
            value, heard, reasons, sugg = check_id(e, record)
        elif t in ("person_name", "place_name"):
            if names is None:
                names = known_names(record, extra_terms, language_code)
            value, heard, reasons, sugg = check_name(e, record, names)
        elif t == "unclassified_date":
            value, heard, reasons, sugg = "", None, ["a date was mentioned but not understood"], None
        else:  # unclassified_number from the backstop
            value, heard, reasons, sugg = e["value"], e["value"], ["a number was heard but not matched to any detail"], None
        if numwords.normalize(e["raw_span"]) not in text:
            reasons.insert(0, "these words are not in the transcript")
        out.append({"type": t, "raw_span": e["raw_span"], "value": value, "heard_as": heard,
                    "status": "flagged" if reasons else "ok", "reasons": reasons, "suggestion": sugg,
                    "found_by": e.get("found_by", "model")})
    return out
