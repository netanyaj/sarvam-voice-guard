"""Before/after evaluation: what an agent would act on without the guard, and with it.

Without the guard: plain saaras:v4 (no keyterms), then the same sarvam-105b extraction, and the
agent acts on whatever comes out. No rule checks, no backstop, no read-back.
With the guard: saaras:v4 with native-script keyterms, extraction + clean-up + backstop, rule
checks, and a read-back question for anything flagged.

Both sides use the same model for extraction, so the difference is what the guard adds. (A regex
baseline cannot read number words at all, so it would make the guard look better than it is.)

Each expected detail ends up as one of:
- correct: right value, passed (guard: and not flagged)
- wrong, passed: wrong value that the agent would act on silently
- caught: wrong or missing value, and the guard asks a read-back question about it
- false alarm: right value, but the guard flagged it anyway (an unneeded question)
- missed: no value at all and nothing asked

Cases:
- test audio from the error log: T13 and T15 (low/medium/high noise) for names, T14 for numbers
- T05: the Indus voice transcript as logged (text only)
- the recording script typed as text (R01-R10; R11 and R12 repeat R01 and R07 as audio tests)
- Netanya's recordings in data/recordings/R01.m4a ... once they exist

Writes eval/results.md, eval/results.csv and eval/results.json.

    ../.venv/bin/python eval.py
"""
import csv
import datetime as dt
import glob
import hashlib
import json
import os
import re
import statistics
import time

import confirm
import validate as V
from extract import extract
from keyterms import to_native
from sarvam import CACHE_DIR, HERE, ROOT
from stt import transcribe

TODAY = "2026-10-29"  # the test audio and T05 were made on 28-29 Oct 2026
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "eval")
AUDIO = os.path.join(ROOT, "api-tests", "audio")
STT_CACHE = os.path.join(CACHE_DIR, "stt")

T05 = "എൻ്റെ നമ്പർ തൊണ്ണൂറ്റി നാൽപ്പത്തേഴ് പൂജ്യം ഒന്ന് രണ്ട് മൂന്ന് നാല് അഞ്ച്"
LULU_EDAPPALLY = [("place_name", "Lulu Mall"), ("place_name", "Edappally")]
TEST_AUDIO = [
    ("T13", "T13_src.wav", LULU_EDAPPALLY, "names in code-mixed speech"),
    ("T15 low noise", "T15_low.wav", LULU_EDAPPALLY, "T13 with low noise"),
    ("T15 medium noise", "T15_medium.wav", LULU_EDAPPALLY, "T13 with medium noise"),
    ("T15 high noise", "T15_high.wav", LULU_EDAPPALLY, "T13 with high noise"),
    ("T14", "T14_src.wav", [("phone", "9847012345"), ("amount", "2450"), ("date", "2026-11-05")],
     "phone, amount, date"),
]
GROUPS = {"audio": "Test audio (made with text-to-speech, from the error log)",
          "text": "Text only (T05 as logged, and the recording script typed in)",
          "recording": "Netanya's recordings"}
RESULTS = ["correct", "wrong, passed", "caught", "false alarm", "missed"]


# ---------- cases ----------

def load_record():
    with open(os.path.join(DATA, "mock_customer.json"), encoding="utf-8") as f:
        return json.load(f)


def truth_rows():
    """{clip: [(type, expected value), ...]} from data/recordings.csv"""
    out = {}
    with open(os.path.join(DATA, "recordings.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            types, values = row["entity_type"].split("|"), row["expected_value"].split("|")
            types = types * len(values) if len(types) == 1 else types
            out[row["clip"]] = list(zip(types, values))
    return out


def script_lines():
    """{clip: line to say} from RECORDING_SCRIPT.md, without stage directions."""
    out = {}
    with open(os.path.join(HERE, "RECORDING_SCRIPT.md"), encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\|\s*(R\d\d)\s*\|\s*(.+?)\s*\|", line)
            if m and not m.group(2).startswith("Repeat"):
                out[m.group(1)] = re.sub(r"\s*\(.*?\)\s*", " ", m.group(2)).strip()
    return out


def resolve_truth(value, today):
    """'next month 5th (resolve from recording date)' -> ISO date"""
    m = re.match(r"next month (\d+)", value)
    if not m:
        return value
    y, mo = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return dt.date(y, mo, int(m.group(1))).isoformat()


def cases():
    truth = truth_rows()
    out = [{"group": "audio", "clip": c, "audio": os.path.join(AUDIO, f), "truth": t, "note": n, "today": TODAY}
           for c, f, t, n in TEST_AUDIO]
    out.append({"group": "text", "clip": "T05", "transcript": T05, "truth": [("phone", "9847012345")],
                "note": "Indus voice transcript, as logged", "today": TODAY})
    for clip, line in script_lines().items():
        out.append({"group": "text", "clip": f"{clip} typed", "transcript": line, "truth": truth[clip],
                    "note": "recording script line, typed", "today": TODAY})
    for path in sorted(glob.glob(os.path.join(DATA, "recordings", "R[0-9][0-9].*"))):
        clip = os.path.splitext(os.path.basename(path))[0]
        if clip in truth:
            day = dt.date.fromtimestamp(os.path.getmtime(path)).isoformat()
            out.append({"group": "recording", "clip": clip, "audio": path, "truth": truth[clip],
                        "note": "", "today": day})
    for c in out:
        c["truth"] = [(t, resolve_truth(v, dt.date.fromisoformat(c["today"]))) for t, v in c["truth"]]
    return out


# ---------- scoring ----------

def norm(type_, value):
    value = str(value or "")
    if type_ == "phone":
        return V._strip_prefix(re.sub(r"\D", "", value))
    if type_ in ("otp", "amount"):
        return re.sub(r"\D", "", value).lstrip("0") or ("0" if value else "")
    if type_ == "policy_or_account_id":
        return re.sub(r"[^A-Z0-9]", "", value.upper())
    return value.strip()


def is_right(type_, value, expected, language_code="ml-IN"):
    if type_ in ("person_name", "place_name"):
        if not value:
            return False
        forms = {expected, to_native(expected, language_code)} if expected.isascii() else {expected}
        keys = {V._name_key(f) for f in forms}
        return any(c in keys for c in V._candidates(str(value)))
    return norm(type_, value) == norm(type_, expected)


def match(truth, entities, language_code="ml-IN"):
    """Pair each expected detail with one extracted detail of the same kind (right one first)."""
    names = {"person_name", "place_name"}
    used, pairs = set(), []
    for type_, expected in truth:
        same = [i for i, e in enumerate(entities) if i not in used and
                (e["type"] == type_ or (type_ in names and e["type"] in names))]
        right = [i for i in same if is_right(type_, entities[i]["value"], expected, language_code)]
        pick = (right or same or [None])[0]
        if pick is not None:
            used.add(pick)
        pairs.append(pick)
    return pairs, used


def score_baseline(truth, entities):
    pairs, _ = match(truth, entities)
    out = []
    for (type_, expected), i in zip(truth, pairs):
        if i is None:
            out.append({"value": None, "result": "missed"})
        else:
            v = entities[i]["value"]
            out.append({"value": v, "result": "correct" if is_right(type_, v, expected) else "wrong, passed"})
    return out


def score_guard(truth, checked):
    pairs, used = match(truth, checked)
    spare_flags = [i for i, c in enumerate(checked) if i not in used and c["status"] == "flagged"
                   and c["type"].startswith("unclassified")]
    out = []
    for (type_, expected), i in zip(truth, pairs):
        if i is None and spare_flags:  # the backstop asked about it
            i = spare_flags.pop(0)
            used.add(i)
        if i is None:
            out.append({"value": None, "status": None, "result": "missed", "reasons": [], "index": None})
            continue
        c = checked[i]
        right = is_right(type_, c["value"], expected) and not c["type"].startswith("unclassified")
        flagged = c["status"] == "flagged"
        result = ("false alarm" if flagged else "correct") if right else ("caught" if flagged else "wrong, passed")
        out.append({"value": c["value"], "status": c["status"], "result": result, "reasons": c["reasons"],
                    "index": i})
    extra = [checked[i] for i, c in enumerate(checked) if i not in used and c["status"] == "flagged"]
    return out, extra


# ---------- running ----------

def stt_cached(path, keyterms):
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()[:16]
    key = hashlib.sha256(json.dumps([digest, keyterms], ensure_ascii=False).encode()).hexdigest()[:24]
    cache = os.path.join(STT_CACHE, key + ".json")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return json.load(f)
    r = transcribe(path, keyterms=keyterms or None)
    os.makedirs(STT_CACHE, exist_ok=True)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False)
    return r


def keyterms_for(record):
    return [record["name"], record["branch"], *record["known_places"], *record["known_people"]]


def run_case(case, record):
    out = {k: v for k, v in case.items() if k != "audio"}
    if "audio" in case:
        out["audio"] = os.path.relpath(case["audio"], ROOT)
        plain = stt_cached(case["audio"], [])
        guarded = stt_cached(case["audio"], keyterms_for(record))
        out["baseline_transcript"], out["guard_transcript"] = plain["transcript"], guarded["transcript"]
        out["stt_s"], out["stt_keyterms_s"] = plain["latency_s"], guarded["latency_s"]
        out["keyterms_sent"] = guarded["keyterms_sent"]
    else:
        out["baseline_transcript"] = out["guard_transcript"] = case["transcript"]
    base = extract(out["baseline_transcript"], today=case["today"])
    guard = base if out["guard_transcript"] == out["baseline_transcript"] else \
        extract(out["guard_transcript"], today=case["today"])
    t = time.perf_counter()
    checked = V.validate(out["guard_transcript"], guard["entities"], record, today=case["today"])
    out["check_ms"] = round((time.perf_counter() - t) * 1000, 1)
    readbacks = confirm.confirm(checked, today=case["today"])
    for r in readbacks:
        r["tts_s"] = confirm.speak_latency(r["audio"])
        if r["tts_s"] is None:  # audio saved before timings were recorded: make it once more to time it
            os.remove(r["audio"])
            r["tts_s"] = confirm.speak_latency(confirm.speak(r["text"])[0])
        r["audio"] = None  # cache path, not kept in the results
    out["extract_s"] = guard["latency_s"]
    out["baseline_entities"], out["checked"], out["readbacks"] = base["model_raw"], checked, readbacks
    out["baseline_scores"] = score_baseline(case["truth"], base["model_raw"])
    out["guard_scores"], out["extra_flags"] = score_guard(case["truth"], checked)
    by_span = {r["raw_span"]: r["text"] for r in readbacks}
    for s in out["guard_scores"]:
        s["readback"] = by_span.get(checked[s["index"]]["raw_span"]) if s["index"] is not None else None
    return out


# ---------- reporting ----------

def counts(rows, side):
    c = {k: 0 for k in RESULTS}
    for r in rows:
        for s in r[f"{side}_scores"]:
            c[s["result"]] += 1
    return c


def med(xs):
    xs = [x for x in xs if x is not None]
    return (round(statistics.median(xs), 2), len(xs)) if xs else (None, 0)


def fmt(v):
    return "" if v is None else str(v).replace("|", "/")


def write(rows):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "results.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1, default=str)
    flat = []
    for r in rows:
        for (type_, expected), b, g in zip(r["truth"], r["baseline_scores"], r["guard_scores"]):
            flat.append({"group": r["group"], "clip": r["clip"], "type": type_, "expected": expected,
                         "without_guard": fmt(b["value"]), "without_guard_result": b["result"],
                         "with_guard": fmt(g["value"]), "with_guard_result": g["result"],
                         "guard_reason": "; ".join(g["reasons"]), "readback": g["readback"] or ""})
    with open(os.path.join(OUT, "results.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(flat[0]))
        w.writeheader()
        w.writerows(flat)

    lines = ["# Guard evaluation", "",
             f"Generated by `eval.py` on {dt.date.today().isoformat()}. Every number below comes from this run.", "",
             "**Without the guard:** speech-to-text with no keyterms, the same sarvam-105b extraction, and the "
             "agent acts on what comes out. **With the guard:** speech-to-text with Malayalam-script keyterms, "
             "extraction, rule checks, and a read-back question for anything that looks wrong.", "",
             "- **correct**: right value, and the guard did not ask about it",
             "- **wrong, passed**: a wrong value the agent would act on without anyone noticing",
             "- **caught**: wrong or missing, and the guard asks the caller about it",
             "- **false alarm**: the value was right, but the guard asked anyway",
             "- **missed**: nothing extracted and nothing asked", ""]
    groups = [g for g in GROUPS if any(r["group"] == g for r in rows)]
    if not any(r["group"] == "recording" for r in rows):
        lines += ["No recordings yet: `data/recordings/` is empty, so this run covers the test audio and text "
                  "cases only.", ""]
    lines += ["## Summary (counts of expected details)", "",
              "| Cases | Details | Wrong, passed: without guard | Wrong, passed: with guard | Caught | "
              "False alarms | Missed (without / with) |", "|---|---|---|---|---|---|---|"]
    for g in groups + ["all"]:
        rs = [r for r in rows if g == "all" or r["group"] == g]
        b, w = counts(rs, "baseline"), counts(rs, "guard")
        n = sum(b.values())
        label = "**All**" if g == "all" else GROUPS[g]
        lines.append(f"| {label} | {n} | {b['wrong, passed']} | {w['wrong, passed']} | {w['caught']} | "
                     f"{w['false alarm']} | {b['missed']} / {w['missed']} |")
    extra = sum(len(r["extra_flags"]) for r in rows)
    lines += ["", f"Questions about things that were not expected details at all: {extra}.", ""]

    check, nc = med([r["check_ms"] for r in rows])
    tts, nt = med([q["tts_s"] for r in rows for q in r["readbacks"][:1]])
    ext, ne = med([r["extract_s"] for r in rows])
    audio = [r for r in rows if "stt_s" in r]
    stt, ns = med([r["stt_s"] for r in audio])
    sttk, _ = med([r["stt_keyterms_s"] for r in audio])
    lines += ["## Time", "", "Medians, in seconds unless marked. The extraction call is the same with or without the guard.", "",
              "| Step | Median | Measured on |", "|---|---|---|",
              f"| Rule checks (added by the guard) | {check} ms | {nc} cases |",
              f"| Making the first read-back audio (added, only when something is flagged) | {tts} | {nt} flagged cases |",
              f"| Speech-to-text, no keyterms | {stt} | {ns} clips |",
              f"| Speech-to-text, with keyterms | {sttk} | {ns} clips |",
              f"| Extraction (sarvam-105b, both sides) | {ext} | {ne} cases |", ""]

    lines += ["## Every expected detail", "",
              "| Clip | Detail | Expected | Without guard | With guard | Read-back question |",
              "|---|---|---|---|---|---|"]
    for x in flat:
        wo = f"{x['without_guard'] or '(nothing)'}: {x['without_guard_result']}"
        wi = f"{x['with_guard'] or '(nothing)'}: {x['with_guard_result']}"
        lines.append(f"| {x['clip']} | {x['type']} | {x['expected']} | {wo} | {wi} | {fmt(x['readback'])} |")
    if extra:
        lines += ["", "## Questions about things that were not expected details", "",
                  "| Clip | Detail | Heard | Reason |", "|---|---|---|---|"]
        for r in rows:
            for e in r["extra_flags"]:
                lines.append(f"| {r['clip']} | {e['type']} | {fmt(e['raw_span'])} | {fmt('; '.join(e['reasons']))} |")
    lines += ["", "## Transcripts (audio cases)", "", "| Clip | Without keyterms | With keyterms |", "|---|---|---|"]
    for r in audio:
        lines.append(f"| {r['clip']} | {fmt(r['baseline_transcript'])} | {fmt(r['guard_transcript'])} |")
    with open(os.path.join(OUT, "results.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return flat


def main():
    record = load_record()
    rows = [run_case(c, record) for c in cases()]
    flat = write(rows)
    for x in flat:
        print(f"{x['clip']:18} {x['type']:20} {x['expected']:12} | without: {x['without_guard']:14} "
              f"{x['without_guard_result']:14} | with: {x['with_guard']:14} {x['with_guard_result']}")
    return rows


if __name__ == "__main__":
    main()
