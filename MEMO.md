# Memo: make every number a voice agent acts on safe to act on

Netanya Jaison, 30 Oct 2026. Evidence: `sarvam-error-log.xlsx` (26 tests, 28-29 Oct) and `guard/eval/results.md` (run 29 Oct).

## The problem

A voice agent for a bank or insurer earns its keep on a handful of words: a phone number, an OTP, a policy number, an amount, a due date, a branch or a name. If one of those is heard wrong, the call doesn't just go badly; the agent acts on the wrong value.

In Malayalam-English speech, those are the words that broke in my testing, while the rest of the sentence held up:

- A phone number I said to Indus came back two digits short. Speech-to-text heard number words that don't add up to one number, and the model turned them into a number anyway. (Indus did notice and asked me to confirm.)
- Place and brand names broke. The same sentence at three noise levels came back with "Lulu Mall" spelled three different ways, while the rest of the sentence stayed identical. The name was the weak point, not the noise.
- Name hints for speech-to-text only worked when written in Malayalam script. Hints written in English were ignored without any warning.

## The bet

Put a verification step between speech-to-text and the agent, as part of the voice-agent platform rather than something each customer builds:

1. Send the customer's own names (branches, places, people on file) to speech-to-text as hints in the right script, automatically.
2. Pick out every high-stakes detail and check it with fixed rules: a mobile number has 10 digits, number words must combine into one number, a name must match something on file.
3. When a detail fails, ask the caller one short question in their language before the agent acts, and hand off to a person if it fails again.

## Why this fits

- It protects the calls that matter most to a lender or insurer: payments, renewals, policy servicing, collections.
- The fix depends on knowing how people actually say numbers and names in each Indian language and script, which is the hard part and the part a team that owns the speech and language models is best placed to solve.
- The script issue also affects developers building on the platform themselves: following the obvious path, their hints silently do nothing.

## What the prototype shows so far

On 38 expected details, wrong values acted on fell from 3 to 0, with no false alarms, and the rule checks added about 1 ms. This is a small, mostly synthetic set: the 3 wrong values came from generated test audio and one logged transcript, and my own 12 recordings had no errors to catch. It shows the idea works and stays quiet when nothing is wrong. It does not yet show how often it catches errors on real calls.

The prototype covers steps 1 and 2 and asks the question in step 3. It does not yet understand the caller's answer or hand off to a person, and it checks recorded clips, not live calls.

## How I would test it with a customer (4-6 weeks)

1. **Pick one number-heavy flow** with one lender or insurer, for example premium due dates or payment confirmation.
2. **Shadow mode first (2-3 weeks):** run the checks on live calls but ask nothing. Log every flag and have someone review a sample against the recordings.
3. **Decide from the shadow data:** how often a wrong value would have gone through, and how often the guard would have asked when nothing was wrong.
4. **Go live on a small share of calls** with read-back questions, and compare against the rest.

What to measure:
- Wrong values acted on, per 1,000 calls (the number this exists to drive down).
- Questions asked when the value was right (the cost to the caller).
- Added time before the agent replies.
- Calls resolved without a person, and handoffs, before and after.

I would set targets after shadow mode, not before.

## Risks

- **Too many questions annoy callers.** Shadow mode exists to tune this before anyone hears a question.
- **OTPs should not be read aloud.** The prototype currently reads a doubtful OTP back to the caller; for a live product it should ask the caller to repeat or re-enter the code instead.
- **Latency on live calls.** The checks are fast; the spoken question adds about a second and has to fit the turn.
- **Each language says numbers differently.** Hindi, Tamil and the others each need their own number reader, starting with the most common flows.
- **Some of this may already exist** inside the voice-agent platform. I've only tested the public APIs and the chat app.

## Open questions

- Which customer flows lose the most calls to a wrong number or name today?
- Do customers already ask for a confirmation step, or build their own?
- Is the script issue with name hints known, and would an automatic fix or a warning be welcome?
