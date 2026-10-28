# Number & Name Guard: build brief

## The problem (one paragraph)
Voice agents for banks and insurers live on numbers and names: phone numbers, OTPs, policy numbers,
amounts, due dates, branch and customer names. In Malayalam-English speech these are exactly what
breaks (see ../CLAUDE.md findings T05, T13, T26). Today a wrong digit can pass through silently and
the transaction fails or goes to the wrong account. The guard sits between speech-to-text and the
agent: it pulls out the high-stakes details, checks them, and when something looks wrong it asks a
short read-back question in the caller's language instead of acting on a bad value.

## What v1 does (scope for today)
1. Transcribe audio with saaras:v4, sending keyterms in the output script (fix from T26).
2. Extract entities into a fixed schema: phone, otp, amount, date, policy_or_account_id, person_name, place_name. Each entity keeps the raw span from the transcript and a normalised value (digits, ISO date, rupees as integer).
3. Validate each entity with deterministic rules, then mark it ok / flagged with a plain-language reason.
4. For flagged entities, generate a Malayalam read-back question and speak it with bulbul:v3 (digits spaced so they are read one by one).
5. A small web demo and an evaluation that compares "no guard" vs "guard" on the same audio.

Out of scope for v1 (name these in the README as next steps): live calls or streaming, languages beyond Malayalam, learning from corrections, CRM integration beyond a mock record.

## Design
```
audio -> stt.py (saaras:v4 + native-script keyterms)
      -> extract.py (sarvam-105b, json_schema, reasoning_effort=low) + regex backstop for digits
      -> validate.py (rules + mock customer record)
      -> confirm.py (Malayalam read-back text -> bulbul:v3 audio)
      -> app.py (Streamlit demo)      eval.py (before/after table)
```

### keyterms.py
- Input: English terms (e.g. "Lulu Mall", "Edappally") + target language.
- If target is not en-IN, transliterate each with /transliterate (en-IN -> ml-IN) and send the native-script form (keep the original too if under the 50-term limit).
- Unit test: reproduce T26 (English-only vs native-script keyterms on ../api-tests/audio/T13_src.wav).

### extract.py
- One chat call to sarvam-105b with a json_schema response. Prompt: extract only what is in the transcript, never invent; Malayalam number words must be converted to digits; keep the exact raw span.
- Regex backstop: any digit run in the transcript must appear in some entity; if the model dropped it, add it as "unclassified_number" and flag it.
- Cache responses on disk by transcript hash so eval reruns are cheap.

### validate.py (each rule returns ok or a reason)
- phone: exactly 10 digits, first digit 6-9. Reason examples: "only 8 digits heard", "starts with 5".
- otp: 4 or 6 digits.
- amount: positive; if the transcript has both digits and words for it, they must agree; lakh/crore converted correctly.
- date: valid calendar date, not in the past for due dates.
- policy_or_account_id: matches the mock record's pattern and value.
- names: fuzzy match (normalise script with transliterate, then similarity) against the mock record and the keyterm list; below threshold -> flag with the closest known name as a suggestion.
- Ambiguity rule: if the raw span contains number words that do not combine cleanly (T05: "തൊണ്ണൂറ്റി നാൽപ്പത്തേഴ്" = 90 + 47?), flag instead of guessing.

### confirm.py
- Build one short question per flagged entity, e.g. "നിങ്ങളുടെ നമ്പർ 9 8 4 7 0, 1 2 3 4 5 ആണോ?" or for a name "ഇടപ്പള്ളി എന്നാണോ ഉദ്ദേശിച്ചത്?".
- Space out digits and group them (5+5 for phones) so TTS reads them digit by digit.
- TTS with bulbul:v3, speaker kavya or anand, pace 0.9. Save WAV.

### app.py (Streamlit)
- Upload audio or pick a sample. Optional: edit mock customer record and keyterms in the sidebar.
- Show: transcript, entity table (raw span / value / status / reason), the read-back question with an audio player, and a side-by-side "without guard: this would have gone through".

### eval.py
- Inputs: data/recordings.csv (Netanya's clips with ground truth) + synthetic cases: ../api-tests/audio/T13_src.wav, T14_src.wav, and the T05 transcript as a text-only case.
- Baseline = transcript -> naive extraction (regex digits, no validation) -> what the agent would act on.
- Guard = full pipeline.
- Per clip: ground truth value, baseline value, guard value, guard status.
- Metrics (report counts, not just percentages): wrong values that pass silently (baseline vs guard), wrong values caught by a read-back, correct values wrongly flagged (false alarms), and median added latency.
- Write eval/results.md and eval/results.csv. The README quotes only these numbers.

## Milestones (stop for review after each)
- M1 (45 min): keyterms.py + stt.py, T26 reproduced as a test.
- M2 (60 min): extract.py + validate.py, unit tests with the T05 transcript and hand-written edge cases.
- M3 (45 min): confirm.py, read-back audio for T05.
- M4 (45 min): eval.py on synthetic cases, then on recordings once they exist.
- M5 (45 min): app.py demo.
- M6 (30 min): README (problem, what it catches, results table, limits, next steps) + one flow diagram exported to PNG.
