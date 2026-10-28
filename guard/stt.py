"""Speech-to-text with saaras:v4, sending keyterms in the output script (see keyterms.py).

    ../.venv/bin/python stt.py ../api-tests/audio/T13_src.wav --keyterms "Lulu Mall" Edappally
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time

from keyterms import build_keyterms
from sarvam import post_multipart

MAX_SECONDS = 30  # REST limit; longer audio needs the Batch API


def duration(path):
    if not shutil.which("ffprobe"):
        return None
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else None


def _as_wav(path, tmpdir):
    """Phone recordings arrive as .m4a; convert anything that is not WAV to 16 kHz mono WAV."""
    if path.lower().endswith(".wav"):
        return path
    out = os.path.join(tmpdir, os.path.splitext(os.path.basename(path))[0] + ".wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-ar", "16000", "-ac", "1", out], check=True)
    return out


def transcribe(path, language_code="ml-IN", keyterms=None, model="saaras:v4", native_keyterms=True):
    """Transcribe one clip. keyterms are plain terms (usually English); with native_keyterms=True they
    are converted to the output script first. Returns transcript, keyterms_sent and latency_s."""
    if keyterms and model != "saaras:v4":
        raise ValueError("keyterms are only supported on saaras:v4")
    seconds = duration(path)
    if seconds is not None and seconds > MAX_SECONDS:
        raise ValueError(f"{os.path.basename(path)} is {seconds:.1f}s; the REST API takes at most "
                         f"{MAX_SECONDS}s (longer audio needs the Batch API)")
    sent = []
    if keyterms:
        sent = build_keyterms(keyterms, language_code) if native_keyterms else list(keyterms)
    data = {"model": model, "language_code": language_code}
    if sent:
        data["keyterms"] = json.dumps(sent, ensure_ascii=False)
    with tempfile.TemporaryDirectory() as tmp:
        wav = _as_wav(path, tmp)
        t = time.time()
        with open(wav, "rb") as f:
            j = post_multipart("/speech-to-text", data, {"file": (os.path.basename(wav), f, "audio/wav")})
        latency = round(time.time() - t, 2)
    return {"transcript": j.get("transcript"), "language_code": j.get("language_code"),
            "model": model, "keyterms_sent": sent, "latency_s": latency}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("audio")
    p.add_argument("--language", default="ml-IN")
    p.add_argument("--keyterms", nargs="*", default=[])
    p.add_argument("--as-given", action="store_true", help="send keyterms as typed, without transliteration")
    a = p.parse_args()
    out = transcribe(a.audio, a.language, a.keyterms, native_keyterms=not a.as_given)
    print(json.dumps(out, ensure_ascii=False, indent=1))
