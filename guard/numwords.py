"""Read Malayalam number words (and digits) deterministically, and say when they do not add up.

Malayalam joins number words: a "linking" form ending in -ി (തൊണ്ണൂറ്റി = "ninety-and") must be
followed by something smaller (തൊണ്ണൂറ്റിയെട്ട് = 98). T05 heard "തൊണ്ണൂറ്റി നാൽപ്പത്തേഴ്": ninety-and
followed by forty-seven. That does not combine, so we mark it ambiguous instead of guessing
(the literal reading 90 47 gives 9047..., a valid-looking but wrong phone number).

parse(text) returns groups. Words that combine form one group (പതിനാലായിരത്തി നാനൂറ്റി പതിനഞ്ച് =
14415); separate numbers said one after another (digit by digit, or "98470 12345") are separate
groups, and their digits are concatenated by digits().
"""
import re
import unicodedata
from dataclasses import dataclass, field
from fractions import Fraction

CHILLU = {"ൺ": "ണ്", "ൻ": "ന്", "ർ": "ര്", "ൽ": "ല്", "ൾ": "ള്", "ൿ": "ക്"}
SIGN_TO_VOWEL = {"ാ": "ആ", "ി": "ഇ", "ീ": "ഈ", "ു": "ഉ", "ൂ": "ഊ", "െ": "എ", "േ": "ഏ", "ൈ": "ഐ",
                 "ൊ": "ഒ", "ോ": "ഓ", "ൗ": "ഔ"}
VIRAMA = "്"


def normalize(text):
    """NFC, old-style chillu (consonant + virama + ZWJ) to atomic chillu, drop joiners."""
    text = unicodedata.normalize("NFC", text)
    for atomic, base in CHILLU.items():
        text = text.replace(base + "‍", atomic)
    return text.replace("‍", "").replace("‌", "")


def dechillu(text):
    """Atomic chillu to consonant + virama, so ൽ and ല് compare equal."""
    for atomic, base in CHILLU.items():
        text = text.replace(atomic, base)
    return text


@dataclass
class Morph:
    kind: str            # "num", "mult", "half", "digits"
    value: Fraction
    link: bool = False   # linking form: must be followed by something smaller than `place`
    place: int = 1
    digits: str = ""     # for "digits": the literal digit string


def _lexicon():
    lex = {}

    def add(forms, m):
        for f in forms:
            lex[dechillu(f)] = m

    units = {0: ["പൂജ്യം", "സീറോ"], 1: ["ഒന്ന്", "ഒന്നു"], 2: ["രണ്ട്", "രണ്ടു"], 3: ["മൂന്ന്", "മൂന്നു"],
             4: ["നാല്", "നാലു"], 5: ["അഞ്ച്", "അഞ്ചു"], 6: ["ആറ്", "ആറു"], 7: ["ഏഴ്", "ഏഴു"],
             8: ["എട്ട്", "എട്ടു"], 9: ["ഒമ്പത്", "ഒൻപത്", "ഒമ്പതു"]}
    teens = {10: ["പത്ത്", "പത്തു"], 11: ["പതിനൊന്ന്"], 12: ["പന്ത്രണ്ട്"], 13: ["പതിമൂന്ന്"],
             14: ["പതിനാല്", "പതിനാലു"], 15: ["പതിനഞ്ച്"], 16: ["പതിനാറ്"], 17: ["പതിനേഴ്"],
             18: ["പതിനെട്ട്"], 19: ["പത്തൊമ്പത്", "പത്തൊൻപത്"]}
    for v, forms in {**units, **teens}.items():
        add(forms, Morph("num", Fraction(v)))
    for v, stems in TENS_STEMS.items():
        for s in stems:
            add([s[:-2] + VIRAMA, s[:-2] + "ു"], Morph("num", Fraction(v)))   # ഇരുപത്, ഇരുപതു
            add([s + "ി"], Morph("num", Fraction(v), link=True, place=10))   # ഇരുപത്തി
    for v, forms in HUNDREDS.items():
        add(forms, Morph("num", Fraction(v)))
        for f in forms:
            linked = f[:-1] + "ത്തി" if f.endswith("ം") else f[:-2] + "റ്റി"  # തൊള്ളായിരത്തി, നൂറ്റി
            add([linked], Morph("num", Fraction(v), link=True, place=100))
    for v, (plain, linked) in MULTS.items():
        add(plain, Morph("mult", Fraction(v), place=v))
        add(linked, Morph("mult", Fraction(v), link=True, place=v))
    for f, v in IRREGULAR_THOUSANDS.items():
        add([f], Morph("num", Fraction(v // 1000)))
    add(["അര"], Morph("half", Fraction(1, 2)))
    return lex


TENS_STEMS = {20: ["ഇരുപത്ത"], 30: ["മുപ്പത്ത"], 40: ["നാൽപ്പത്ത", "നാല്പത്ത", "നാൽപത്ത"],
              50: ["അമ്പത്ത", "അൻപത്ത"], 60: ["അറുപത്ത"], 70: ["എഴുപത്ത"], 80: ["എൺപത്ത", "എമ്പത്ത"],
              90: ["തൊണ്ണൂറ്റ"]}
HUNDREDS = {100: ["നൂറ്", "നൂറു"], 200: ["ഇരുനൂറ്"], 300: ["മുന്നൂറ്"], 400: ["നാനൂറ്"], 500: ["അഞ്ഞൂറ്"],
            600: ["അറുനൂറ്"], 700: ["എഴുനൂറ്"], 800: ["എണ്ണൂറ്"], 900: ["തൊള്ളായിരം"]}
MULTS = {1000: (["ആയിരം", "thousand"], ["ആയിരത്തി"]),
         100000: (["ലക്ഷം", "lakh", "lakhs"], ["ലക്ഷത്തി"]),
         10000000: (["കോടി", "crore", "crores"], [])}
IRREGULAR_THOUSANDS = {"മൂവായിരം": 3000, "അയ്യായിരം": 5000, "പതിനായിരം": 10000}
THOUSAND_SUFFIXES = ["ിനായിരത്തി", "ിനായിരം", "ായിരത്തി", "ായിരം"]
LEX = _lexicon()
LINK_PREFIXES = sorted((f for f, m in LEX.items() if m.link), key=len, reverse=True)
TENS_SANDHI = sorted(((dechillu(s), v) for v, ss in TENS_STEMS.items() for s in ss), key=lambda x: -len(x[0]))


def _restore_initial(rest):
    """After a joined prefix the next word loses its first vowel: യെട്ട് / െട്ട് -> എട്ട്."""
    if len(rest) > 1 and rest[0] == "യ":           # ഇരുപത്തി|യഞ്ച് -> അഞ്ച്, |യെട്ട് -> എട്ട്
        if rest[1] in SIGN_TO_VOWEL:
            return [SIGN_TO_VOWEL[rest[1]] + rest[2:]]
        if rest[1] != VIRAMA:
            return ["അ" + rest[1:]]
    if rest[0] in SIGN_TO_VOWEL:
        return [SIGN_TO_VOWEL[rest[0]] + rest[1:]]
    out = ["അ" + rest]                                # ഇരുപത്ത|ഞ്ച് -> അഞ്ച്
    if len(rest) > 2 and rest[1] == VIRAMA and rest[0] == rest[2]:
        out.insert(0, rest[2:])                      # doubled consonant: നൂറ്റി|പ്പത്ത് -> പത്ത്
    return [rest] + out


def segment(token):
    """Split one written word into number parts, or None if it is not a number word."""
    t = dechillu(normalize(token))
    if not t:
        return None
    if t in LEX:
        m = LEX[t]
        if dechillu(t) in IRREGULAR_THOUSANDS:
            return [m, Morph("mult", Fraction(1000), place=1000)]
        return [m]
    for f, v in IRREGULAR_THOUSANDS.items():
        if t == f[:-1] + "ത്തി":                      # അയ്യായിരത്തി
            return [Morph("num", Fraction(v // 1000)), Morph("mult", Fraction(1000), link=True, place=1000)]
    for suf in THOUSAND_SUFFIXES:                    # പതിനാലായിരത്തി = പതിനാല് + ആയിരത്തി
        if t.endswith(suf) and len(t) > len(suf):
            base = t[:-len(suf)]
            for cand in (base + VIRAMA, base):
                head = segment(cand)
                if head and not head[-1].link:
                    return head + [Morph("mult", Fraction(1000), link=suf.endswith("ി"), place=1000)]
    for mult, (plain, linked) in MULTS.items():      # നാലുലക്ഷം
        for f in plain[:1] + linked:
            if t.endswith(f) and len(t) > len(f):
                head = segment(t[:-len(f)])
                if head and not head[-1].link:
                    return head + [Morph("mult", Fraction(mult), link=f in linked, place=mult)]
    if t.endswith("ര") and len(t) > 1:              # നാലര = നാല് + അര
        head = segment(t[:-1] + VIRAMA)
        if head and not head[-1].link:
            return head + [Morph("half", Fraction(1, 2))]
    if t.endswith("ാം") and len(t) > 2:             # അഞ്ചാം (fifth)
        head = segment(t[:-2] + VIRAMA)
        if head:
            return head
    for p in LINK_PREFIXES:                          # നൂറ്റിയൊന്ന് = നൂറ്റി + ഒന്ന്
        if t.startswith(p) and len(t) > len(p):
            for rest in _restore_initial(t[len(p):]):
                tail = segment(rest)
                if tail:
                    return [LEX[p]] + tail
    for stem, v in TENS_SANDHI:                      # നാൽപ്പത്തേഴ് = നാൽപ്പത്ത + ഏഴ്
        if t.startswith(stem) and len(t) > len(stem):
            for rest in _restore_initial(t[len(stem):]):
                tail = segment(rest)
                if tail and len(tail) == 1 and tail[0].kind == "num" and 1 <= tail[0].value <= 9:
                    return [Morph("num", Fraction(v), link=True, place=10)] + tail
    return None


@dataclass
class Group:
    morphs: list = field(default_factory=list)
    words: list = field(default_factory=list)
    ambiguous: bool = False
    reason: str = ""

    @property
    def value(self):
        total, cur = Fraction(0), None
        for m in self.morphs:
            if m.kind in ("num", "digits"):
                cur = (cur or 0) + m.value
            elif m.kind == "half":
                cur = (cur or 0) + m.value
            elif m.kind == "mult":
                total += (cur if cur is not None else 1) * m.value
                cur = None
        return total + (cur or 0)

    @property
    def digits(self):
        """Digit string as spoken. A lone digit token keeps leading zeros."""
        if len(self.morphs) == 1 and self.morphs[0].kind == "digits":
            return self.morphs[0].digits
        v = self.value
        return str(int(v)) if v.denominator == 1 else None

    @property
    def has_words(self):
        return any(m.kind != "digits" for m in self.morphs)

    @property
    def text(self):
        return " ".join(self.words)


TOKEN = re.compile(r"\d+(?:[.,]\d+)*|[^\s\d.,!?;:()\"'₹/\-]+")


def _magnitude(morphs, i):
    """Size of the number that starts at morphs[i] (a following multiplier counts)."""
    v = morphs[i].value
    if i + 1 < len(morphs) and morphs[i + 1].kind == "mult":
        v *= morphs[i + 1].value
    return v


def parse(text):
    seq = []  # (morph or None for a non-number word, word, token index)
    for idx, tok in enumerate(m.group(0) for m in TOKEN.finditer(normalize(text))):
        if tok[0].isdigit():
            clean = tok.replace(",", "")
            seq.append((Morph("digits", Fraction(clean), digits=clean.replace(".", "")), tok, idx))
            continue
        parts = segment(tok) or ([LEX[tok.lower()]] if tok.lower() in LEX else None)
        if parts is None:
            seq.append((None, tok, idx))
        else:
            seq.extend((p, tok, idx) for p in parts)

    groups, cur, last_idx = [], None, None

    def close():
        nonlocal cur
        if cur and cur.morphs:
            if cur.morphs[-1].link and not cur.ambiguous:
                cur.ambiguous = True
                cur.reason = f"'{cur.text}' ends in a joining form with nothing after it"
            groups.append(cur)
        cur = None

    for k, (m, word, idx) in enumerate(seq):
        if m is None:
            close()
            continue
        prev = cur.morphs[-1] if cur else None
        if prev is None:
            cur = Group()
        elif m.kind in ("mult", "half"):
            pass                                     # multipliers and "half" attach to what came before
        elif prev.link:
            size = m.value
            if k + 1 < len(seq) and seq[k + 1][0] is not None and seq[k + 1][0].kind == "mult":
                size *= seq[k + 1][0].value
            if size >= prev.place:
                reason = (f"'{cur.text} {word}' does not combine into one number, "
                          "so any digits read from it are a guess")
                cur.ambiguous, cur.reason = True, reason
                groups.append(cur)
                cur = Group(ambiguous=True, reason=reason)
        else:
            close()
            cur = Group()
        cur.morphs.append(m)
        if idx != last_idx or not cur.words:
            cur.words.append(word)
        last_idx = idx
    close()
    return groups


def _fmt(v):
    return str(int(v)) if v.denominator == 1 else str(float(v))


def digits(text):
    """(digit string, list of ambiguity reasons) for a span read as a sequence of numbers."""
    gs = parse(text)
    reasons = [g.reason for g in gs if g.ambiguous and g.reason]
    return "".join(g.digits or "" for g in gs), list(dict.fromkeys(reasons))


def number_runs(text):
    """Runs of consecutive number words: two or more words, or one with lakh/thousand. A lone ഒന്ന്
    is skipped because it usually means "please" ("ഇത് ഒന്ന് പറയാമോ")."""
    runs, cur = [], []

    def flush():
        if cur and (len(cur) >= 2 or any(m.kind == "mult" for w in cur for m in (segment(w) or []))):
            runs.append(" ".join(cur))
        cur.clear()

    for m in TOKEN.finditer(normalize(text)):
        w = m.group(0)
        if not w[0].isdigit() and (segment(w) or w.lower() in LEX):
            cur.append(w)
        else:
            flush()
    flush()
    return runs
