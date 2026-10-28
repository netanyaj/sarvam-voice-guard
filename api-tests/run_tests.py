"""Sarvam API tests (T13-T25). Run from ~/sarvam-tests with the venv:
    .venv/bin/python run_tests.py
Reads SARVAM_API_KEY from .env, saves audio to ./audio, writes results.json.
"""
import base64, json, os, subprocess, time
import requests

BASE = "https://api.sarvam.ai"
HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(HERE, "audio")
os.makedirs(AUDIO, exist_ok=True)


def load_key():
    env = os.path.join(HERE, ".env")
    env = env if os.path.exists(env) else os.path.join(HERE, "..", ".env")
    with open(env) as f:
        for line in f:
            if line.strip().startswith("SARVAM_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("SARVAM_API_KEY not found in .env")


H = {"api-subscription-key": load_key()}
results = {}


def timed(fn):
    t = time.time()
    try:
        out = fn()
    except Exception as e:  # keep going on any failure
        out = {"error": f"{type(e).__name__}: {e}"}
    return out, round(time.time() - t, 2)


def post_json(path, body):
    r = requests.post(BASE + path, headers=H, json=body, timeout=120)
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:500]}
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}", "body": j}
    return j


def tts(text, name, sr=16000, model="bulbul:v3"):
    def call():
        j = post_json("/text-to-speech", {"text": text, "language_code": "ml-IN", "model": model,
                                          "speech_sample_rate": sr})
        if "error" in j:
            return j
        path = os.path.join(AUDIO, f"{name}.wav")
        with open(path, "wb") as f:
            f.write(base64.b64decode(j["audios"][0]))
        return {"file": path}
    return timed(call)


def stt(path, model="saaras:v4", language_code="ml-IN", mode=None):
    def call():
        data = {"model": model, "language_code": language_code}
        if mode:
            data["mode"] = mode
        with open(path, "rb") as f:
            r = requests.post(BASE + "/speech-to-text", headers=H, data=data,
                              files={"file": (os.path.basename(path), f, "audio/wav")}, timeout=180)
        j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:500]}
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}", "body": j}
        return {"transcript": j.get("transcript"), "language_code": j.get("language_code"),
                "language_probability": j.get("language_probability")}
    return timed(call)


def translate(text, src, tgt, mode="formal", model="mayura:v1"):
    return timed(lambda: post_json("/translate", {"input": text, "source_language_code": src,
                                                  "target_language_code": tgt, "mode": mode, "model": model}))


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return round(float(out), 1) if out else None


# ---------- STT (synthetic: Sarvam TTS clip -> Sarvam STT) ----------
T13 = ("ഇന്നലെ ഞാൻ Lulu Mall ൽ പോയി, പക്ഷേ parking full ആയിരുന്നു, so ഞങ്ങൾ Edappally metro station ൽ "
       "നിന്ന് auto പിടിച്ചു.")
T14 = "എന്റെ phone number 98470 12345 ആണ്. ₹2,450 ന്റെ bill നവംബർ 5-ന് മുമ്പ് അടയ്ക്കണം."

src13, lat = tts(T13, "T13_src")
results["T13_tts_src"] = {"out": src13, "latency": lat}
if "file" in src13:
    out, lat = stt(src13["file"])
    results["T13"] = {"out": out, "latency": lat, "audio_s": duration(src13["file"])}
    # T23: same audio, older model in codemix mode
    out, lat = stt(src13["file"], model="saaras:v3", mode="codemix")
    results["T23"] = {"out": out, "latency": lat}
    # T25: same audio, language auto-detect
    out, lat = stt(src13["file"], language_code="unknown")
    results["T25"] = {"out": out, "latency": lat}
    # T15: add pink noise at three levels
    t15 = {}
    for lvl, amp in (("low", 0.03), ("medium", 0.1), ("high", 0.25)):
        noisy = os.path.join(AUDIO, f"T15_{lvl}.wav")
        try:
            ffmpeg("-i", src13["file"], "-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude={amp}:sample_rate=16000",
                   "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:normalize=0", "-ar", "16000",
                   "-ac", "1", noisy)
            out, lat = stt(noisy)
            t15[lvl] = {"out": out, "latency": lat}
        except Exception as e:
            t15[lvl] = {"out": {"error": str(e)}}
    results["T15"] = t15

src14, lat = tts(T14, "T14_src")
if "file" in src14:
    out, lat = stt(src14["file"])
    results["T14"] = {"out": out, "latency": lat, "audio_s": duration(src14["file"])}

# T16: ~2 minute clip built from several TTS paragraphs
paras = [
    "കൊച്ചി കേരളത്തിലെ ഏറ്റവും വലിയ നഗരങ്ങളിൽ ഒന്നാണ്. ഇവിടെ മെട്രോയും വാട്ടർ മെട്രോയും ഉണ്ട്, അതുകൊണ്ട് യാത്ര എളുപ്പമാണ്.",
    "എല്ലാ ദിവസവും രാവിലെ ആയിരക്കണക്കിന് ആളുകൾ ഇൻഫോപാർക്കിലേക്കും നഗരത്തിലെ ഓഫീസുകളിലേക്കും ജോലിക്ക് പോകുന്നു.",
    "മഴക്കാലത്ത് റോഡുകളിൽ വെള്ളം കയറുന്നത് ഒരു വലിയ പ്രശ്നമാണ്. നഗരസഭ ഓടകൾ വൃത്തിയാക്കാൻ പുതിയ പദ്ധതികൾ തുടങ്ങിയിട്ടുണ്ട്.",
    "ഫോർട്ട് കൊച്ചിയും മട്ടാഞ്ചേരിയും വിനോദസഞ്ചാരികൾക്ക് പ്രിയപ്പെട്ട സ്ഥലങ്ങളാണ്. ചീനവലകളും പഴയ കെട്ടിടങ്ങളും കാണാൻ നിരവധി പേർ എത്തുന്നു.",
    "വൈകുന്നേരം മറൈൻ ഡ്രൈവിൽ നടക്കാനും സൂര്യാസ്തമയം കാണാനും കുടുംബങ്ങൾ ഒത്തുകൂടുന്നു. അവിടത്തെ ചായക്കടകളിൽ നല്ല തിരക്കായിരിക്കും.",
    "അടുത്ത വർഷം നഗരത്തിൽ കൂടുതൽ ഇലക്ട്രിക് ബസുകൾ ഓടിത്തുടങ്ങുമെന്നാണ് പ്രതീക്ഷ. ഇത് മലിനീകരണം കുറയ്ക്കാൻ സഹായിക്കും.",
]
parts = []
for i, p in enumerate(paras):
    o, _ = tts(p, f"T16_part{i}")
    if "file" in o:
        parts.append(o["file"])
if parts:
    listfile = os.path.join(AUDIO, "T16_list.txt")
    with open(listfile, "w") as f:
        for _ in range(2):  # repeat to reach roughly 2 minutes
            for p in parts:
                f.write(f"file '{p}'\n")
    long_path = os.path.join(AUDIO, "T16_long.wav")
    try:
        ffmpeg("-f", "concat", "-safe", "0", "-i", listfile, "-ar", "16000", "-ac", "1", long_path)
        out, lat = stt(long_path)
        results["T16"] = {"out": out, "latency": lat, "audio_s": duration(long_path),
                          "source_text": " ".join(paras) + " | (repeated twice)"}
    except Exception as e:
        results["T16"] = {"out": {"error": str(e)}}

# ---------- TTS (audio saved for listening; STT round-trip as a proxy check) ----------
TTS_TESTS = {
    "T17": "നിങ്ങളുടെ EMI ₹14,415 ആണ്, അടുത്ത due date 05/11/2026. സംശയങ്ങൾക്ക് 1800 425 1234 ൽ വിളിക്കുക.",
    "T18": "തൃപ്പൂണിത്തുറ, കൊടുങ്ങല്ലൂർ, ഇരിങ്ങാലക്കുട എന്നിവിടങ്ങളിൽ Swiggy, Zomato, PhonePe ഇപ്പോൾ ലഭ്യമാണ്.",
    "T19": "നിങ്ങളുടെ order confirm ആയിട്ടുണ്ട്, delivery ഇന്ന് evening 6 മണിക്ക് മുമ്പ് ഉണ്ടാകും.",
}
for tid, text in TTS_TESTS.items():
    o, lat = tts(text, tid, sr=22050)
    entry = {"out": o, "latency": lat}
    if "file" in o:
        entry["audio_s"] = duration(o["file"])
        rt, _ = stt(o["file"])
        entry["stt_roundtrip"] = rt
    results[tid] = entry

# ---------- Translation ----------
T20 = ("It's raining cats and dogs, so your delivery may be delayed. We sincerely apologise for the "
       "inconvenience and appreciate your patience.")
o, lat = translate(T20, "en-IN", "ml-IN")
results["T20"] = {"out": o, "latency": lat}
o, lat = translate(T20, "en-IN", "ml-IN", mode="modern-colloquial")
results["T24"] = {"out": o, "latency": lat}

T21 = ("Please carry your Aadhaar card and arrive 15 minutes before your appointment; late arrivals may need "
       "to reschedule.")
o1, lat1 = translate(T21, "en-IN", "ml-IN")
entry = {"out_ml": o1, "latency": lat1}
if "translated_text" in o1:
    o2, lat2 = translate(o1["translated_text"], "ml-IN", "en-IN")
    entry["out_back_en"] = o2
    entry["latency"] = round(lat1 + lat2, 2)
results["T21"] = entry

T22 = ("Hi Arjun, your refund of ₹1,299 for order #KX-48213 will reach your HDFC account by 2 Nov. "
       "Track it at www.example.in/track.")
o, lat = translate(T22, "en-IN", "ml-IN")
results["T22"] = {"out": o, "latency": lat}

with open(os.path.join(HERE, "results.json"), "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(json.dumps(results, ensure_ascii=False, indent=1))
