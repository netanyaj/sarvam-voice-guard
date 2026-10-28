"""Offline tests for stt.py (the API call is stubbed)."""
import json
import shutil
import subprocess

import pytest

import keyterms
import stt

T13 = "../api-tests/audio/T13_src.wav"


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_post(path, data, files):
        calls.append({"path": path, "data": data, "filename": files["file"][0], "mime": files["file"][2]})
        return {"transcript": "ok", "language_code": data["language_code"]}

    monkeypatch.setattr(stt, "post_multipart", fake_post)
    monkeypatch.setattr(keyterms, "_transliterate", lambda t, lang: {"Lulu Mall": "ലുലു മാൾ"}[t])
    return calls


def test_keyterms_go_out_in_native_script_as_json_array(sent):
    out = stt.transcribe(T13, keyterms=["Lulu Mall"])
    assert json.loads(sent[0]["data"]["keyterms"]) == ["ലുലു മാൾ", "Lulu Mall"]
    assert sent[0]["mime"] == "audio/wav"
    assert out["keyterms_sent"] == ["ലുലു മാൾ", "Lulu Mall"]


def test_as_given_skips_transliteration(sent):
    stt.transcribe(T13, keyterms=["Lulu Mall"], native_keyterms=False)
    assert json.loads(sent[0]["data"]["keyterms"]) == ["Lulu Mall"]


def test_no_keyterms_field_when_empty(sent):
    stt.transcribe(T13)
    assert "keyterms" not in sent[0]["data"]


def test_keyterms_rejected_on_v3():
    with pytest.raises(ValueError, match="saaras:v4"):
        stt.transcribe(T13, keyterms=["Lulu Mall"], model="saaras:v3")


def test_over_30_seconds_rejected_before_upload(sent):
    with pytest.raises(ValueError, match="Batch API"):
        stt.transcribe("../api-tests/audio/T16_long.wav")
    assert sent == []


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_m4a_is_converted_to_wav(sent, tmp_path):
    m4a = tmp_path / "R01.m4a"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", T13, str(m4a)], check=True)
    stt.transcribe(str(m4a))
    assert sent[0]["filename"] == "R01.wav" and sent[0]["mime"] == "audio/wav"
