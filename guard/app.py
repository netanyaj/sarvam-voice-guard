"""Demo: the same call with and without the Number & Name Guard.

    ../.venv/bin/streamlit run app.py

Layout: a list of calls on the left; on the right, one sentence saying what happened, then a
table comparing what the caller said, what the agent would act on without the guard, and what
the guard does. Phone and policy numbers are drawn digit by digit, lined up against the right
answer, so a dropped or wrong digit is visible at a glance. Samples run as soon as they are
picked (results are cached on disk).
"""
import datetime as dt
import difflib
import hashlib
import html
import json
import os
import re
import time

import streamlit as st

import confirm
import eval as E
import validate as V
from extract import extract
from sarvam import CACHE_DIR, HERE, SarvamError

LABELS = {"phone": "Phone number", "otp": "OTP", "amount": "Amount", "date": "Date",
          "policy_or_account_id": "Policy number", "person_name": "Person", "place_name": "Place",
          "unclassified_number": "Unmatched number", "unclassified_date": "Unclear date"}
DIGIT_TYPES = {"phone", "otp", "policy_or_account_id"}
NAMES = {"person_name", "place_name"}
UPLOADS = os.path.join(CACHE_DIR, "uploads")

# The call list: (key, title, one-line description). Keys are eval.py clip ids.
CALLS = [
    ("T05", "Phone number misheard", "Logged transcript from Indus voice"),
    ("T13", "Place names in mixed speech", "Malayalam with English names"),
    ("T15 high noise", "Place names on a noisy line", "Same sentence, heavy background noise"),
    ("T14", "Clean call", "Phone, amount and date, all heard right"),
    ("R10", "Caller corrects themselves", "Recording: “98470… no, 98471 12345”"),
    ("R08", "Place names, real voice", "Recording: Edappally and Lulu Mall"),
    ("other", "Another test case", "Any case from the evaluation"),
]

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Anek+Latin:wght@400;500;600;700&family=Anek+Malayalam:wght@400;500;600&display=swap');
:root { --ink:#17213A; --slate:#5A6478; --line:#E2E5EA; --panel:#F5F6F8; --accent:#3A4BB0; --accent-bg:#EEF0FA;
        --wrong:#B42318; --wrong-bg:#FDECEA; --ask:#A15C07; --ask-bg:#FDF3E2; --ok:#1E7A5A; --ok-bg:#E6F4EE; }
.stApp, .stApp p, .stApp label, .stApp button, .stApp input, .stApp textarea, .stApp li, .stApp td, .stApp th {
  font-family: 'Anek Latin', 'Anek Malayalam', system-ui, sans-serif; }
.stApp { color: var(--ink); }
/* Streamlit greys out the page while it reruns; results here are cached, so the fade only reads as lag */
[data-stale="true"], .stale-element { opacity: 1 !important; transition: none !important; }
.block-container { padding-top: 3.2rem; max-width: 1240px; }
.ml { font-family: 'Anek Malayalam', 'Anek Latin', sans-serif; }

.top h1 { font-size: 1.9rem; font-weight: 700; letter-spacing: -0.015em; margin: 0; padding: 0; color: var(--ink); }
.top p { font-size: 1.05rem; color: var(--slate); margin: .25rem 0 1.6rem 0; max-width: 64ch; }

/* call list: one radio group drawn as a list */
div[data-testid="stRadio"] [role="radiogroup"] { gap: 2px; width: 100%; }
div[data-testid="stRadio"] [role="radiogroup"] > div { width: 100%; padding: .5rem .7rem .55rem .8rem;
  border-left: 3px solid transparent; border-radius: 0 8px 8px 0; cursor: pointer; }
div[data-testid="stRadio"] [role="radiogroup"] > div:hover { background: var(--panel); }
div[data-testid="stRadio"] [role="radiogroup"] > div[data-selected="true"] { background: var(--accent-bg);
  border-left-color: var(--accent); }
div[data-testid="stRadio"] [data-testid="stRadioOption"] > div > div:first-child { display: none; }
div[data-testid="stRadio"] [data-testid="stRadioOption"] p { font-size: 1rem; font-weight: 600; color: var(--ink); }
div[data-testid="stRadio"] [data-testid="stRadioCaption"] { margin: 0; padding: 0; }
div[data-testid="stRadio"] [data-testid="stRadioCaption"] p { font-size: .88rem; color: var(--slate); }
div[data-testid="stRadio"] [role="radiogroup"] > div:nth-child(7) { margin-top: .9rem; }
.listhead { font-size: .9rem; color: var(--slate); margin: 0 0 .35rem .9rem; }

.verdict { font-size: 1.4rem; line-height: 1.35; font-weight: 600; letter-spacing: -0.01em; max-width: 52ch;
           margin: .1rem 0 1.3rem 0; color: var(--ink); }

.listen { font-size: .9rem; color: var(--slate); margin: 0 0 .2rem 0; }
.detail { border-top: 1px solid var(--line); padding: 1rem 0 1.1rem 0; }
.detail:last-of-type { border-bottom: 1px solid var(--line); }
.dhead { display: flex; align-items: baseline; gap: .8rem; margin-bottom: .6rem; }
.dlabel { font-weight: 600; font-size: 1.05rem; }
.line { display: grid; grid-template-columns: 10.5rem 1fr; align-items: start; column-gap: 1rem; padding: .3rem 0; }
.who { color: var(--slate); font-size: .95rem; line-height: 1.8rem; }
.line .note { display: inline; margin: 0 0 0 .7rem; }
.val { font-size: 1.15rem; font-weight: 600; font-variant-numeric: tabular-nums; }
.muted { color: var(--slate); font-weight: 400; }
.note { font-size: .88rem; margin-top: .3rem; }
.note.wrong { color: var(--wrong); } .note.right { color: var(--slate); }
.reasons { margin: .35rem 0 0 0; padding-left: 1rem; font-size: .88rem; color: var(--slate); }
.reasons li { margin: .1rem 0; }

.status { display: inline-block; font-size: .88rem; font-weight: 600; padding: .1rem .55rem; border-radius: 4px; }
.status.ask { color: var(--ask); background: var(--ask-bg); }
.status.ok { color: var(--ok); background: var(--ok-bg); }
.status.miss { color: var(--wrong); background: var(--wrong-bg); }

.digits { display: inline-flex; gap: 2px; flex-wrap: nowrap; }
.digits .d { display: inline-flex; align-items: center; justify-content: center; width: 1.3rem; height: 1.8rem;
             border: 1px solid var(--line); border-radius: 4px; font-size: 1.05rem; font-weight: 600;
             font-variant-numeric: tabular-nums; background: #fff; }
.digits .d.wrong { border-color: var(--wrong); color: var(--wrong); background: var(--wrong-bg); }
.digits .d.missing { border: 1px dashed var(--wrong); background: transparent; }
.digits .sep { width: .4rem; flex: none; }

.section { font-size: .95rem; font-weight: 600; color: var(--ink); margin: 0 0 .5rem 0; }
.reply { border-left: 3px solid var(--accent); padding: .2rem 0 .2rem 1rem; margin-bottom: .5rem; }
.reply .q { font-size: 1.2rem; font-weight: 500; line-height: 1.55; }
.reply .en { font-size: .98rem; color: var(--slate); margin-top: .2rem; }

.heard { font-size: 1rem; line-height: 1.8; margin: 0 0 .4rem 0; }
.heard .which { color: var(--slate); font-size: .88rem; display: block; line-height: 1.3; }
.heard u { text-decoration: none; border-bottom: 2px solid #9DB6E6; }
.heard u.flag { border-bottom-color: #E0A43B; background: var(--ask-bg); }


/* results of testing: pinned to the bottom of the window, same place for every call */
.block-container { padding-bottom: 6rem; }
.footer { position: fixed; left: 0; right: 0; bottom: 0; z-index: 99; background: #fff; border-top: 1px solid var(--line); }
.footer .inner { max-width: 1240px; margin: 0 auto; padding: .7rem 2.5rem; display: flex; flex-wrap: wrap;
                 align-items: baseline; column-gap: 1.5rem; row-gap: .2rem; font-size: .9rem; color: var(--slate); }
.footer .fh { font-weight: 600; color: var(--ink); }
.footer b { color: var(--ink); font-size: 1.05rem; font-variant-numeric: tabular-nums; margin-right: .25rem; }
.footer b.good { color: var(--ok); }

/* "check your own call": actions at the top right, apart from the sample list */
.own { font-size: .9rem; color: var(--slate); margin: .35rem 0 .35rem 0; }
.stApp button[kind="secondary"] { border: 1px solid var(--accent); color: var(--accent); font-weight: 600; }
.stApp button[kind="secondary"]:hover { background: var(--accent-bg); color: var(--accent); border-color: var(--accent); }
.stApp button[kind="primary"] { font-weight: 600; }
.ownhead { font-size: 1.15rem; font-weight: 600; margin: 0 0 .6rem 0; }
</style>
"""


# ---------- pipeline (same steps as eval.run_case, with the side panel's record and names) ----------

def save_upload(f):
    data = f.getvalue()
    os.makedirs(UPLOADS, exist_ok=True)
    path = os.path.join(UPLOADS, hashlib.sha256(data).hexdigest()[:16] + os.path.splitext(f.name)[1].lower())
    with open(path, "wb") as out:
        out.write(data)
    return path


@st.cache_data(show_spinner="Transcribing and checking", max_entries=256)
def run(audio, text, record, extra, today, speaker):
    """Both sides for one input. Kept in memory per input, so going back to a call is instant; the spinner
    only shows when a call has not been checked yet in this session."""
    out = {"timings": {}}
    if audio:
        terms = list(dict.fromkeys(E.keyterms_for(record) + extra))
        plain, guarded = E.stt_cached(audio, []), E.stt_cached(audio, terms)
        out["base_text"], out["guard_text"] = plain["transcript"], guarded["transcript"]
        out["keyterms_sent"] = guarded["keyterms_sent"]
        out["timings"]["Speech-to-text, no keyterms"] = plain["latency_s"]
        out["timings"]["Speech-to-text, with keyterms"] = guarded["latency_s"]
    else:
        out["base_text"] = out["guard_text"] = text
    base = extract(out["base_text"], today=today)
    guard = base if out["guard_text"] == out["base_text"] else extract(out["guard_text"], today=today)
    out["timings"]["Extraction (sarvam-105b)"] = guard["latency_s"]
    t = time.perf_counter()
    out["checked"] = V.validate(out["guard_text"], guard["entities"], record, extra_terms=extra, today=today)
    out["timings"]["Rule checks"] = f"{(time.perf_counter() - t) * 1000:.1f} ms"
    out["readbacks"] = confirm.confirm(out["checked"], speaker=speaker, today=today)
    out["base_entities"], out["dropped"] = base["model_raw"], guard["dropped"]
    return out


@st.cache_data(show_spinner=False)
def load_cases():
    return E.cases()


@st.cache_data(show_spinner=False)
def load_results(mtime):
    """eval/results.json, re-read only when the file changes."""
    with open(os.path.join(HERE, "eval", "results.json"), encoding="utf-8") as f:
        return json.load(f)


# ---------- display helpers ----------

def esc(s):
    return html.escape(str(s))


def pretty(type_, value):
    """How a value is shown to people: 98470 12345, ₹4,50,000, 5 Nov 2026."""
    v = str(value or "")
    if type_ == "phone":
        d = re.sub(r"\D", "", v)
        return f"{d[:5]} {d[5:]}" if len(d) == 10 else d
    if type_ == "amount" and re.sub(r"\D", "", v):
        return "₹" + confirm.rupees(int(re.sub(r"\D", "", v)))
    if type_ == "date":
        try:
            return dt.date.fromisoformat(v).strftime("%-d %b %Y")
        except ValueError:
            return v
    return v


def chars(type_, value):
    v = str(value or "").upper()
    return re.sub(r"\D", "", v) if type_ in ("phone", "otp") else re.sub(r"[^A-Z0-9]", "", v)


def digit_boxes(heard, truth=None, group=5):
    """Heard characters as boxes, lined up against the right answer: a dropped character is an empty
    dashed box, a wrong or extra one is red. The gap after `group` follows the right answer."""
    truth = truth or heard
    cells, pos = [], 0  # pos: index in the right answer, for the group gap

    def add(ch, cls=""):
        nonlocal pos
        if pos == group and group < len(truth):
            cells.append('<span class="sep"></span>')
        cells.append(f'<span class="d {cls}">{esc(ch)}</span>')

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, truth, heard, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                add(heard[j1 + k]); pos += 1
        elif tag == "replace":
            n = max(i2 - i1, j2 - j1)
            for k in range(n):
                if j1 + k < j2:
                    add(heard[j1 + k], "wrong")
                else:
                    add("", "missing")
                if i1 + k < i2:
                    pos += 1
        elif tag == "delete":
            for _ in range(i2 - i1):
                add("", "missing"); pos += 1
        else:  # insert: extra characters that were not said
            for k in range(j2 - j1):
                add(heard[j1 + k], "wrong")
    return f'<span class="digits">{"".join(cells)}</span>'


def show_value(type_, value, truth=None):
    if value in (None, ""):
        return '<span class="val muted">nothing</span>'
    if type_ in DIGIT_TYPES and chars(type_, value):
        group = 5 if type_ == "phone" else 3 if type_ == "otp" else 3
        if type_ == "policy_or_account_id":
            m = re.match(r"[A-Z]+", chars(type_, truth or value))
            group = len(m.group(0)) if m else 3
        return digit_boxes(chars(type_, value), chars(type_, truth) if truth else None, group)
    return f'<span class="val ml">{esc(pretty(type_, value))}</span>'


def same_kind(a, b):
    return a == b or (a in NAMES and b in NAMES)


def sample_label(c):
    kind = {"audio": "test audio", "text": "text", "recording": "recording"}[c["group"]]
    note = f": {c['note']}" if c["note"] else ""
    return f"{c['clip']} ({kind}){note}"


def highlight(text, spans, flagged=()):
    """Transcript with the checked words underlined; flagged ones in amber."""
    out = esc(text)
    for s in sorted({s for s in [*spans, *flagged] if s}, key=len, reverse=True):
        cls = ' class="flag"' if s in flagged else ""
        out = out.replace(esc(s), f"<u{cls}>{esc(s)}</u>", 1)
    return out


def join_and(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# ---------- what happened ----------

def rows_for(res, truth):
    """One row per detail: label, type, right answer, value without guard, its result, guard item."""
    checked, rows = res["checked"], []
    if truth:
        base = E.score_baseline(truth, res["base_entities"])
        guard, _ = E.score_guard(truth, checked)
        used = set()
        for (t, v), b, g in zip(truth, base, guard):
            c = checked[g["index"]] if g["index"] is not None else None
            used.add(g["index"])
            rows.append({"type": t, "truth": v, "base": b["value"], "base_result": b["result"], "guard": c})
        for i, c in enumerate(checked):
            if i not in used and c["status"] == "flagged":
                rows.append({"type": c["type"], "truth": None, "base": None, "base_result": None, "guard": c})
        return rows
    left = list(res["base_entities"])
    for c in checked:
        match = next((e for e in left if e["type"] == c["type"] and e["raw_span"] == c["raw_span"]), None) or \
            next((e for e in left if same_kind(e["type"], c["type"])), None)
        if match:
            left.remove(match)
        rows.append({"type": c["type"], "truth": None, "base": match["value"] if match else None,
                     "base_result": None, "guard": c})
    return rows


def headline(rows, truth):
    flagged = sum(1 for r in rows if r["guard"] and r["guard"]["status"] == "flagged")
    wrong = [r for r in rows if r["base_result"] == "wrong, passed"]
    missed = [r for r in rows if r["base_result"] == "missed"]
    if wrong:
        first = "Without the guard, the agent acts on " + join_and(
            f"{pretty(r['type'], r['base'])} instead of {pretty(r['type'], r['truth'])}" for r in wrong) + "."
    elif missed:
        first = "Without the guard, the agent never picks up " + join_and(r["truth"] for r in missed) + "."
    elif truth:
        first = "Every detail in this call was heard right."
    else:
        n = len(rows)
        first = f"Found {n} detail{'s' if n != 1 else ''}." if n else "No details found."
    if flagged:
        second = (f"The guard stops and asks the caller {'one question' if flagged == 1 else f'{flagged} questions'}"
                  " first.")
    else:
        second = "The guard checks each one and lets the agent go ahead." if rows else ""
    return f"{first} {second}".strip()


def guard_cell(r):
    c = r["guard"]
    if c is None:
        return '<span class="status miss">Missed</span>'
    # what the guard itself heard, when it differs from the value without the guard (names, mostly)
    differs = c["type"] not in DIGIT_TYPES and pretty(c["type"], c["value"]) != pretty(r["type"], r["base"])
    heard_as = (f'<span class="val ml">{esc(pretty(c["type"], c["value"]))}</span>' if differs else "")
    found = ('<div class="note right">Found by matching the transcript against the names on file</div>'
             if c.get("found_by") == "name check" else "")
    if c["status"] == "flagged":
        reasons = "".join(f"<li>{esc(x)}</li>" for x in c["reasons"])
        return (f'{heard_as}<span class="status ask" style="margin-left:{".7rem" if heard_as else "0"}">Asks the '
                f'caller</span><ul class="reasons">{reasons}</ul>{found}')
    return (f'{heard_as}<span class="status ok" style="margin-left:{".7rem" if heard_as else "0"}">Passes</span>'
            f'{found}')


def base_cell(r):
    if r["base_result"] == "missed":
        return '<span class="val muted">nothing</span><span class="note wrong">Not picked up, so never checked</span>'
    html_ = show_value(r["type"], r["base"], r["truth"])
    if r["base_result"] == "wrong, passed":
        html_ += '<span class="note wrong">Wrong, and the agent acts on it</span>'
    elif r["base_result"] == "correct":
        html_ += '<span class="note right">Right</span>'
    return html_


def comparison(rows, truth):
    """One block per detail. The right answer and the value the agent would act on sit on lines
    directly above each other, so for numbers the digit boxes line up."""
    blocks = []
    for r in rows:
        lines = ""
        if truth:
            said = show_value(r["type"], r["truth"]) if r["truth"] is not None else \
                '<span class="muted">not a detail in this call</span>'
            lines += f'<div class="line"><span class="who">Caller said</span><span>{said}</span></div>'
        lines += (f'<div class="line"><span class="who">Without the guard</span><span>{base_cell(r)}</span></div>'
                  f'<div class="line"><span class="who">With the guard</span><span>{guard_cell(r)}</span></div>')
        blocks.append(f'<div class="detail"><div class="dhead"><span class="dlabel">'
                      f'{esc(LABELS.get(r["type"], r["type"]))}</span></div>{lines}</div>')
    if not blocks:
        blocks = ['<div class="detail muted">No phone numbers, amounts, dates or names in this call.</div>']
    st.markdown('<div style="margin-bottom:1.6rem">' + "".join(blocks) + "</div>", unsafe_allow_html=True)


def replies(res, record, extra):
    if not res["readbacks"]:
        return
    st.markdown('<div class="section">What the caller hears instead</div>', unsafe_allow_html=True)
    names = V.known_names(record, extra)
    for q in res["readbacks"]:
        en = q["text_en"]
        for form, english in names.items():  # "Did you mean ഇടപ്പള്ളി?" -> "Did you mean Edappally (ഇടപ്പള്ളി)?"
            if not form.isascii() and f"mean {form}?" in en:
                en = en.replace(f"mean {form}?", f"mean {english} ({form})?")
        st.markdown(f'<div class="reply"><div class="q ml">{esc(q["text"])}</div>'
                    f'<div class="en">{esc(en)}</div></div>', unsafe_allow_html=True)
        st.audio(q["audio"], format="audio/wav")


def heard(res):
    ok = [c["raw_span"] for c in res["checked"] if c["status"] == "ok"]
    flagged = [c["raw_span"] for c in res["checked"] if c["status"] == "flagged"]
    st.markdown('<div class="section" style="margin-top:1.4rem">What speech-to-text heard</div>',
                unsafe_allow_html=True)
    if res["base_text"] != res["guard_text"]:
        st.markdown(f'<p class="heard ml"><span class="which">Without name hints</span>{esc(res["base_text"])}</p>'
                    f'<p class="heard ml"><span class="which">With the customer\'s names as hints</span>'
                    f'{highlight(res["guard_text"], ok, flagged)}</p>', unsafe_allow_html=True)
    else:
        st.markdown(f'<p class="heard ml">{highlight(res["guard_text"], ok, flagged)}</p>', unsafe_allow_html=True)


def tested():
    """Results of the last eval.py run (eval/results.json), as a bar pinned to the bottom of the window.
    Test cases and recordings are counted apart, as in results.md."""
    path = os.path.join(HERE, "eval", "results.json")
    if not os.path.exists(path):
        return
    rows = load_results(os.path.getmtime(path))
    tests = [r for r in rows if r["group"] != "recording"]
    recs = [r for r in rows if r["group"] == "recording"]
    b, g, rg = E.counts(tests, "baseline"), E.counts(tests, "guard"), E.counts(recs, "guard")
    items = [f'<span><b>{b["wrong, passed"]} → {g["wrong, passed"]}</b>wrong values acted on, without → with the guard'
             f'</span>', f'<span><b>{g["caught"]}</b>asked about</span>',
             f'<span><b class="good">{g["false alarm"] + rg["false alarm"]}</b>false alarms</span>']
    if recs:
        items.append(f'<span><b>{rg["correct"]} of {sum(rg.values())}</b>recorded details passed with no '
                     f'questions</span>')
    note = (f"{sum(b.values())} test details from the error log, {sum(rg.values())} in {len(recs)} recordings. "
            "From the last run of eval.py; full table in eval/results.md")
    st.markdown(f'<div class="footer" title="{esc(note)}">'
                f'<div class="inner"><span class="fh">In testing</span>{"".join(items)}</div></div>',
                unsafe_allow_html=True)


# ---------- inputs ----------

def side_panel():
    st.sidebar.markdown("### Customer on file")
    st.sidebar.caption("The guard checks names and policy numbers against this record, and gives the names "
                       "to speech-to-text as hints.")
    r = E.load_record()
    record = {
        "name": st.sidebar.text_input("Name", r["name"]),
        "phone": st.sidebar.text_input("Phone", r["phone"]),
        "policy_or_account_id": st.sidebar.text_input("Policy number", r["policy_or_account_id"]),
        "emi_amount": r["emi_amount"],
        "branch": st.sidebar.text_input("Branch", r["branch"]),
        "known_places": [s.strip() for s in st.sidebar.text_area(
            "Places, one per line", "\n".join(r["known_places"])).splitlines() if s.strip()],
        "known_people": [s.strip() for s in st.sidebar.text_area(
            "People, one per line", "\n".join(r["known_people"])).splitlines() if s.strip()],
    }
    extra = [s.strip() for s in st.sidebar.text_area("Other names to listen for", "").splitlines() if s.strip()]
    speaker = st.sidebar.selectbox("Voice for questions", ["kavya", "anand"])
    return record, extra, speaker


def call_list(cases, by_clip):
    """The sample calls on the left. Returns the chosen clip id, or None while checking your own call."""
    calls = [c for c in CALLS if c[0] in by_clip or c[0] == "other"]
    st.markdown('<div class="listhead">Sample calls</div>', unsafe_allow_html=True)
    st.radio("Call", [c[0] for c in calls], key="call", on_change=lambda: st.session_state.update(mode="sample"),
             format_func=lambda k: next(c[1] for c in calls if c[0] == k), captions=[c[2] for c in calls],
             label_visibility="collapsed")
    st.caption("The customer on file and the question voice are in the side panel.")
    return st.session_state.get("call")


def own_call_actions():
    """Two buttons at the top right: check your own audio or text instead of a sample."""
    mode = st.session_state["mode"]

    def pick(m):
        st.session_state.update(mode=m, call=None)  # clears the sample list's selection

    st.markdown('<div class="own">Check your own call</div>', unsafe_allow_html=True)
    a, b = st.columns(2, gap="small")
    a.button("Upload audio", icon=":material/upload:", width="stretch", on_click=pick, args=("upload",),
             type="primary" if mode == "upload" else "secondary")
    b.button("Type text", icon=":material/edit_note:", width="stretch", on_click=pick, args=("type",),
             type="primary" if mode == "type" else "secondary")


def call_input(key, cases, by_clip):
    """Inputs shown above the result. Returns (audio, text, truth, today, auto_run)."""
    today = dt.date.today().isoformat()
    mode = st.session_state["mode"]
    if mode == "upload":
        st.markdown('<div class="ownhead">Upload a clip</div>', unsafe_allow_html=True)
        f = st.file_uploader("Audio, up to 30 seconds: wav, m4a, mp3, ogg or flac",
                             type=["wav", "m4a", "mp3", "ogg", "flac"])
        if f:
            st.audio(f)
        return (save_upload(f) if f else None), None, [], today, False
    if mode == "type":
        st.markdown('<div class="ownhead">Type a transcript</div>', unsafe_allow_html=True)
        text = st.text_area("Transcript, as speech-to-text would write it", "എന്റെ നമ്പർ 98470 1234 ആണ്", height=90)
        return None, text, [], today, False
    if key == "other":
        c = st.selectbox("Test case", cases, format_func=sample_label)
    else:
        c = by_clip[key]
    if c.get("audio"):
        st.markdown('<div class="listen">The call</div>', unsafe_allow_html=True)
        st.audio(c["audio"])
    return c.get("audio"), c.get("transcript"), c["truth"], c["today"], True


# ---------- page ----------

def main():
    st.set_page_config(page_title="Number & Name Guard", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(CSS, unsafe_allow_html=True)
    st.session_state.setdefault("mode", "sample")
    st.session_state.setdefault("call", CALLS[0][0])
    if st.session_state["mode"] == "sample" and st.session_state.get("call") is None:
        st.session_state["call"] = CALLS[0][0]
    cases = load_cases()
    by_clip = {c["clip"]: c for c in cases}

    title, actions = st.columns([3, 1.3], gap="large", vertical_alignment="bottom")
    title.markdown('<div class="top"><h1>Number &amp; Name Guard</h1><p>A check between speech-to-text and a '
                   'voice agent. It reads back phone numbers, amounts and names that look wrong, in Malayalam, '
                   'before the agent acts on them.</p></div>', unsafe_allow_html=True)
    with actions:
        own_call_actions()
    record, extra, speaker = side_panel()
    left, right = st.columns([1, 3], gap="large")
    with left:
        key = call_list(cases, by_clip)
    with right:
        audio, text, truth, today, auto = call_input(key, cases, by_clip)
        state = json.dumps([audio, text, record, extra, today, speaker], ensure_ascii=False)
        ready = bool(audio or (text and text.strip()))
        if not auto and st.button("Check this call", type="primary", disabled=not ready):
            st.session_state["go"] = state
        if ready and (auto or st.session_state.get("go") == state):
            try:
                res = run(audio, text, record, extra, today, speaker)
            except (SarvamError, ValueError) as e:
                st.error(str(e))
            else:
                rows = rows_for(res, truth)
                st.markdown(f'<div class="verdict">{esc(headline(rows, truth))}</div>', unsafe_allow_html=True)
                comparison(rows, truth)
                replies(res, record, extra)
                heard(res)
                with st.expander("Technical details"):
                    st.json({"timings_s": res["timings"], "hints_sent": res.get("keyterms_sent", []),
                             "dropped_by_clean_up": res["dropped"], "checked": res["checked"]})
    tested()


if __name__ == "__main__":
    main()
