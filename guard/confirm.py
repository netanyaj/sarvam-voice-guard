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
import time

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


def spoken_date(iso, today=None, english=False):
    d = dt.date.fromisoformat(iso)
    today = today or dt.date.today()
    year = "" if d.year == today.year else f" {d.year}"
    return f"{d.day} {d.strftime('%B')}{year}" if english else f"{MONTHS_ML[d.month - 1]} {d.day}{year}"


def _question(c, today=None):
    """(Malayalam question, English meaning) for one checked detail."""
    t, value, reasons = c["type"], str(c.get("value") or ""), c.get("reasons", [])
    if t == "phone":
        if len(value) == 10:
            g = spaced(value, 5)
            return f"നിങ്ങളുടെ നമ്പർ {g} ആണോ?", f"Is your number {g}?"
        g = spaced(value, 5)
        heard = (f"ഞാൻ കേട്ടത് {g}. ", f"I heard {g}. ") if value else ("", "")
        return (f"{heard[0]}ഒരു മൊബൈൽ നമ്പറിൽ 10 അക്കങ്ങൾ വേണം. നമ്പർ {SAY_AGAIN}",
                f"{heard[1]}A mobile number needs 10 digits. Could you say the number again, one digit at a time?")
    if t == "otp":
        if len(value) in (4, 6):
            g = spaced(value, 3 if len(value) == 6 else 4)
            return f"OTP {g} ആണോ?", f"Is the OTP {g}?"
        g = spaced(value, 3)
        heard = (f"ഞാൻ കേട്ടത് {g}. ", f"I heard {g}. ") if value else ("", "")
        return (f"{heard[0]}OTP-യിൽ 4 അല്ലെങ്കിൽ 6 അക്കങ്ങൾ ഉണ്ടാകും. OTP {SAY_AGAIN}",
                f"{heard[1]}An OTP has 4 or 6 digits. Could you say the OTP again, one digit at a time?")
    if t == "amount":
        if isinstance(c.get("value"), int) and c["value"] > 0:
            r = rupees(c["value"])
            return f"{r} രൂപ ആണോ?", f"Is it ₹{r}?"
        return "തുക എത്രയാണെന്ന് ഒന്നുകൂടി പറയാമോ?", "Could you say the amount again?"
    if t == "date":
        try:
            said, said_en = spoken_date(value, today), spoken_date(value, today, english=True)
        except ValueError:
            return "തീയതി ഒന്നുകൂടി പറയാമോ?", "Could you say the date again?"
        if any("in the past" in r for r in reasons):
            return (f"ഞാൻ കേട്ടത് {said}. ആ തീയതി കഴിഞ്ഞുപോയി. ശരിയായ തീയതി പറയാമോ?",
                    f"I heard {said_en}. That date has passed. Could you give the right date?")
        return f"{said} ആണോ?", f"Is it {said_en}?"
    if t == "policy_or_account_id":
        s = spelled_id(value)
        if any(r.startswith("should be") for r in reasons):
            heard = (f"ഞാൻ കേട്ടത് {s}. ", f"I heard {s}. ") if value else ("", "")
            return (f"{heard[0]}പോളിസി നമ്പർ {SAY_AGAIN}",
                    f"{heard[1]}Could you say the policy number again, one digit at a time?")
        return f"പോളിസി നമ്പർ {s} ആണോ?", f"Is the policy number {s}?"
    if t in ("person_name", "place_name"):
        if c.get("suggestion"):
            return f"{c['suggestion']} എന്നാണോ ഉദ്ദേശിച്ചത്?", f"Did you mean {c['suggestion']}?"
        if t == "place_name":
            return "സ്ഥലത്തിന്റെ പേര് ഒന്നുകൂടി പറയാമോ?", "Could you say the name of the place again?"
        return "പേര് ഒന്നുകൂടി പറയാമോ?", "Could you say the name again?"
    if t == "unclassified_date":
        return "തീയതി ഒന്നുകൂടി പറയാമോ?", "Could you say the date again?"
    # unclassified_number: a number nobody accounted for
    digits = re.sub(r"\D", "", value)
    heard = spaced(digits, 5) if digits else c["raw_span"]
    return f"{heard} എന്ന് കേട്ടു. ഇത് ഏത് നമ്പർ ആണ്?", f"I heard {heard}. What is this number for?"


def question(c, today=None):
    """Malayalam read-back question for one checked detail (output of validate.validate)."""
    return _question(c, today)[0]


def question_en(c, today=None):
    """What the question means in English, for people who do not read Malayalam."""
    return _question(c, today)[1]


def speak(text, speaker=SPEAKER, pace=PACE):
    """WAV path for the spoken text (cached). Returns (path, cached)."""
    if len(text) > MAX_CHARS:
        raise ValueError(f"read-back is {len(text)} characters; {MODEL} takes at most {MAX_CHARS}")
    key = hashlib.sha256(json.dumps([MODEL, speaker, pace, text], ensure_ascii=False).encode()).hexdigest()[:24]
    path = os.path.join(CACHE, key + ".wav")
    if os.path.exists(path):
        return path, True
    t = time.time()
    j = post_json("/text-to-speech", {"text": text, "language_code": "ml-IN", "model": MODEL,
                                      "speaker": speaker, "pace": pace, "speech_sample_rate": 16000})
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "wb") as f:
        f.write(base64.b64decode(j["audios"][0]))
    with open(path[:-4] + ".json", "w", encoding="utf-8") as f:
        json.dump({"text": text, "speaker": speaker, "pace": pace, "latency_s": round(time.time() - t, 2)},
                  f, ensure_ascii=False)
    return path, False


def speak_latency(path):
    """Seconds the TTS call took when this audio was first made (None if not recorded)."""
    try:
        with open(path[:-4] + ".json", encoding="utf-8") as f:
            return json.load(f)["latency_s"]
    except (OSError, KeyError, ValueError):
        return None


def confirm(checked, audio=True, speaker=SPEAKER, pace=PACE, today=None):
    """Read-back for every flagged detail, in transcript order: type, raw_span, text, audio path."""
    today = dt.date.fromisoformat(today) if isinstance(today, str) else today
    out = []
    for c in checked:
        if c["status"] != "flagged":
            continue
        text, text_en = _question(c, today)
        out.append({"type": c["type"], "raw_span": c["raw_span"], "text": text, "text_en": text_en,
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
