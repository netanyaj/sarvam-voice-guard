# Sarvam voice guard

Voice agents for banks and insurers act on phone numbers, OTPs, amounts, dates, policy numbers and
names. In Malayalam-English speech, these are the words speech-to-text gets wrong. This repo holds a
check that sits between speech-to-text and the voice agent: it verifies each of those details and,
when one looks wrong, asks the caller a short question in Malayalam before the agent acts.

It is built on the Sarvam APIs (saaras:v4 speech-to-text, sarvam-105b, bulbul:v3 text-to-speech).

![How the guard works](guard/docs/flow.png)

**Start with [guard/README.md](guard/README.md)**: what it catches, the results with and without the
guard, how to run the demo, and what is not built yet.

## What is in this repo

| Folder or file | What it holds |
|---|---|
| [`MEMO.md`](MEMO.md) | Short memo: the problem, the bet, how I'd test it with a customer, risks |
| [`guard/`](guard/) | The guard itself, its tests, the evaluation and the demo page |
| [`guard/eval/results.md`](guard/eval/results.md) | Every tested detail, with and without the guard |
| [`api-tests/`](api-tests/) | The script and raw output from hand-testing the Sarvam APIs in Malayalam and English |
| `sarvam-error-log.xlsx` | The log of those tests, which the guard is built on |

## Run the demo

You need Python 3 and a Sarvam API key in a `.env` file at the top of the repo, as
`SARVAM_API_KEY=...`.

```bash
python3 -m venv .venv
.venv/bin/pip install -r guard/requirements.txt
cd guard && ../.venv/bin/streamlit run app.py
```
