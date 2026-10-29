"""Turn flagged details into short Malayalam read-back questions, and speak them with bulbul:v3.

One question per flagged detail. Two kinds:
- "Is it X?" when there is a complete value to read back (a 10-digit phone, an amount, a date).
- "I heard X. Please say it again." when what was heard cannot be right as it stands (T05: only
  9 digits), because asking "is it 9 4 7 0 1, 2 3 4 5?" would invite a "yes" to a broken number.

Digits are written spaced and grouped (98470 12345 -> "9 8 4 7 0, 1 2 3 4 5"). Checked on
29 Oct 2026: bulbul:v3 (kavya and anand, pace 0.9) reads the spaced form one digit at a time
(same length as the digits written as words), and saaras:v4 hears all of them back correctly.

Audio is cached on disk by text, speaker and pace.

    ../.venv/bin/python confirm.py "എന്റെ നമ്പർ 98470 1234 ആണ്"
"""
import base64
import datetime as dt
import hashlib
import json
import os
import re
import sys

from sarvam import CACHE_DIR, post_json

MODEL = "bulbul:v3"
SPEAKER = "kavya"
PACE = 0.9
MAX_CHARS = 2500
CACHE = os.path.join(CACHE_DIR, "tts")

MONTHS_ML = ["ജനുവരി", "ഫെബ്രുവരി", "മാർച്ച്", "ഏപ്രിൽ", "മെയ്", "ജൂൺ", "ജൂലൈ", "ഓഗസ്റ്റ്", "സെപ്റ്റംബർ",
             "ഒക്ടോബർ", "നവംബർ", "ഡിസംബർ"]
SAY_AGAIN = "ഒരു അക്കം വീതം ഒന്നുകൂടി പറയാമോ?"  # "could you say it again, one digit at a time?"


def spaced(digits, size):
    """'9847012345', 5 -> '9 8 4 7 0, 1 2 3 4 5'"""
    chunks = [digits[i:i + size] for i in range(0, len(digits), size)]
    return ", ".join(" ".join(c) for c in chunks)


def spelled_id(value):
    """'SBL2047813' -> 'S B L, 2 0 4 7, 8 1 3'"""
    parts = re.findall(r"[A-Z]+|\d+", value.upper())
    return ", ".join(" ".join(p) if p.isalpha() else spaced(p, 4) for p in parts)


def rupees(n):
    """450000 -> '4,50,000' (Indian grouping)"""
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    head = ",".join(re.findall(r"\d{1,2}", head[::-1]))[::-1]
    return f"{head},{tail}"


def spoken_date(iso, today=None):
    d = dt.date.fromisoformat(iso)
    today = today or dt.date.today()
    year = "" if d.year == today.year else f" {d.year}"
    return f"{MONTHS_ML[d.month - 1]} {d.day}{year}"


def question(c, today=None):
    """Malayalam read-back question for one checked detail (output of validate.validate)."""
    t, value, reasons = c["type"], str(c.get("value") or ""), c.get("reasons", [])
    if t == "phone":
        if len(value) == 10:
            return f"നിങ്ങളുടെ നമ്പർ {spaced(value, 5)} ആണോ?"
        heard = f"ഞാൻ കേട്ടത് {spaced(value, 5)}. " if value else ""
        return f"{heard}ഒരു മൊബൈൽ നമ്പറിൽ 10 അക്കങ്ങൾ വേണം. നമ്പർ {SAY_AGAIN}"
    if t == "otp":
        if len(value) in (4, 6):
            return f"OTP {spaced(value, 3 if len(value) == 6 else 4)} ആണോ?"
        heard = f"ഞാൻ കേട്ടത് {spaced(value, 3)}. " if value else ""
        return f"{heard}OTP-യിൽ 4 അല്ലെങ്കിൽ 6 അക്കങ്ങൾ ഉണ്ടാകും. OTP {SAY_AGAIN}"
    if t == "amount":
        if isinstance(c.get("value"), int) and c["value"] > 0:
            return f"{rupees(c['value'])} രൂപ ആണോ?"
        return "തുക എത്രയാണെന്ന് ഒന്നുകൂടി പറയാമോ?"
    if t == "date":
        try:
            said = spoken_date(value, today)
        except ValueError:
            return "തീയതി ഒന്നുകൂടി പറയാമോ?"
        if any("in the past" in r for r in reasons):
            return f"ഞാൻ കേട്ടത് {said}. ആ തീയതി കഴിഞ്ഞുപോയി. ശരിയായ തീയതി പറയാമോ?"
        return f"{said} ആണോ?"
    if t == "policy_or_account_id":
        if any(r.startswith("should be") for r in reasons):
            heard = f"ഞാൻ കേട്ടത് {spelled_id(value)}. " if value else ""
            return f"{heard}പോളിസി നമ്പർ {SAY_AGAIN}"
        return f"പോളിസി നമ്പർ {spelled_id(value)} ആണോ?"
    if t in ("person_name", "place_name"):
        if c.get("suggestion"):
            return f"{c['suggestion']} എന്നാണോ ഉദ്ദേശിച്ചത്?"
        what = "സ്ഥലത്തിന്റെ പേര്" if t == "place_name" else "പേര്"
        return f"{what} ഒന്നുകൂടി പറയാമോ?"
    if t == "unclassified_date":
        return "തീയതി ഒന്നുകൂടി പറയാമോ?"
    # unclassified_number: a number nobody accounted for
    digits = re.sub(r"\D", "", value)
    heard = spaced(digits, 5) if digits else c["raw_span"]
    return f"{heard} എന്ന് കേട്ടു. ഇത് ഏത് നമ്പർ ആണ്?"


def speak(text, speaker=SPEAKER, pace=PACE):
    """WAV path for the spoken text (cached). Returns (path, cached)."""
    if len(text) > MAX_CHARS:
        raise ValueError(f"read-back is {len(text)} characters; {MODEL} takes at most {MAX_CHARS}")
    key = hashlib.sha256(json.dumps([MODEL, speaker, pace, text], ensure_ascii=False).encode()).hexdigest()[:24]
    path = os.path.join(CACHE, key + ".wav")
    if os.path.exists(path):
        return path, True
    j = post_json("/text-to-speech", {"text": text, "language_code": "ml-IN", "model": MODEL,
                                      "speaker": speaker, "pace": pace, "speech_sample_rate": 16000})
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "wb") as f:
        f.write(base64.b64decode(j["audios"][0]))
    return path, False


def confirm(checked, audio=True, speaker=SPEAKER, pace=PACE, today=None):
    """Read-back for every flagged detail, in transcript order: type, raw_span, text, audio path."""
    today = dt.date.fromisoformat(today) if isinstance(today, str) else today
    out = []
    for c in checked:
        if c["status"] != "flagged":
            continue
        text = question(c, today)
        out.append({"type": c["type"], "raw_span": c["raw_span"], "text": text,
                    "audio": speak(text, speaker, pace)[0] if audio else None})
    return out


if __name__ == "__main__":
    from extract import extract
    from validate import validate
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mock_customer.json"),
              encoding="utf-8") as f:
        record = json.load(f)
    transcript = " ".join(sys.argv[1:])
    checked = validate(transcript, extract(transcript)["entities"], record)
    print(json.dumps(confirm(checked), ensure_ascii=False, indent=1))
