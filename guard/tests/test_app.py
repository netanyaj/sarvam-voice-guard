import io

import pytest

import app
import confirm
from conftest import T05, T05_SPAN, TODAY


def test_run_text_offline(record, offline_translit, monkeypatch):
    ents = [{"type": "phone", "raw_span": T05_SPAN, "value": "947012345", "date_kind": "none",
             "superseded_raw_spans": []}]
    monkeypatch.setattr(app, "extract", lambda t, today: {"entities": ents, "model_raw": ents, "dropped": [],
                                                          "latency_s": 0.5})
    monkeypatch.setattr(confirm, "speak", lambda text, speaker, pace: ("/tmp/x.wav", True))
    app.run.clear()  # run() is cached in memory; start clean so the stubs above are used
    res = app.run(None, T05, record, [], TODAY, "anand")
    assert res["base_text"] == res["guard_text"] == T05
    [c] = res["checked"]
    assert c["status"] == "flagged"
    [q] = res["readbacks"]
    assert q["text"].startswith("ഞാൻ കേട്ടത് 9 4 7 0 1, 2 3 4 5.") and q["audio"] == "/tmp/x.wav"
    assert q["text_en"].startswith("I heard 9 4 7 0 1, 2 3 4 5.")


def test_save_upload_names_by_content(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "UPLOADS", str(tmp_path))

    class F:
        name = "Clip.M4A"
        def getvalue(self):
            return b"abc"
    p1, p2 = app.save_upload(F()), app.save_upload(F())
    assert p1 == p2 and p1.endswith(".m4a") and open(p1, "rb").read() == b"abc"


@pytest.mark.live
def test_app_shows_the_t05_story():
    """Whole page, headless: T05 is the first call and runs without a click."""
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file("../app.py", default_timeout=120).run()
    assert not at.exception
    page = " ".join(m.value for m in at.markdown)
    assert "Without the guard, the agent acts on 947012345 instead of 98470 12345." in page
    assert "The guard stops and asks the caller one question first." in page
    assert "ഞാൻ കേട്ടത് 9 4 7 0 1, 2 3 4 5." in page
    assert "I heard 9 4 7 0 1, 2 3 4 5. A mobile number needs 10 digits." in page


def test_pretty_values():
    assert app.pretty("phone", "9847012345") == "98470 12345"
    assert app.pretty("phone", "947012345") == "947012345"
    assert app.pretty("amount", 450000) == "₹4,50,000"
    assert app.pretty("date", "2026-11-05") == "5 Nov 2026"
    assert app.pretty("date", "next week") == "next week"


def test_digit_boxes_line_up_with_the_right_answer():
    import re
    cells = lambda h: re.findall(r'class="d ([a-z]*)">([^<]*)<|class="(sep)"', h)
    got = cells(app.digit_boxes("947012345", "9847012345"))
    # 9, a dashed box where the 8 was dropped, 4 7 0, the gap after five, then 1 2 3 4 5
    assert got[:6] == [("", "9", ""), ("missing", "", ""), ("", "4", ""), ("", "7", ""), ("", "0", ""), ("", "", "sep")]
    assert len(got) == 11
    wrong = cells(app.digit_boxes("9847112345", "9847012345"))
    assert ("wrong", "1", "") in wrong


def test_headline():
    rows = [{"type": "phone", "truth": "9847012345", "base": "947012345", "base_result": "wrong, passed",
             "guard": {"status": "flagged"}}]
    assert app.headline(rows, [("phone", "9847012345")]) == \
        "Without the guard, the agent acts on 947012345 instead of 98470 12345. " \
        "The guard stops and asks the caller one question first."
    rows = [{"type": "amount", "truth": "2450", "base": "2450", "base_result": "correct", "guard": {"status": "ok"}}]
    assert app.headline(rows, [("amount", "2450")]).startswith("Every detail in this call was heard right.")


def test_highlight_marks_flagged_words():
    out = app.highlight("എന്റെ നമ്പർ 98470 1234 ആണ്", ["എന്റെ"], ["98470 1234"])
    assert '<u class="flag">98470 1234</u>' in out and "<u>എന്റെ</u>" in out
    assert app.highlight("<b>", ["<b>"]) == "<u>&lt;b&gt;</u>"  # transcript text is escaped
