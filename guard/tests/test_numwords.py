import pytest

import numwords
from conftest import T05_SPAN


@pytest.mark.parametrize("text,value", [
    ("പതിനാലായിരത്തി നാനൂറ്റി പതിനഞ്ച്", 14415),     # R04
    ("നാലര ലക്ഷം", 450000),                            # R05
    ("4.5 ലക്ഷം", 450000),
    ("ഒന്നര ലക്ഷം", 150000),
    ("രണ്ടു ലക്ഷത്തി അമ്പതിനായിരം", 250000),
    ("അയ്യായിരത്തി അഞ്ഞൂറ്", 5500),
    ("രണ്ടായിരത്തി ഇരുപത്തിയാറ്", 2026),
    ("തൊണ്ണൂറ്റിയെട്ട്", 98),
    ("ഇരുപത്തഞ്ച്", 25),
    ("ഇരുപത്തിയഞ്ച്", 25),
    ("നാൽപ്പത്തേഴ്", 47),
    ("നാല്പത്തിയേഴ്", 47),
    ("നൂറ്റിയൊന്ന്", 101),
    ("പത്തൊമ്പത്", 19),
    ("₹2,450", 2450),
    ("14,415", 14415),
])
def test_single_numbers(text, value):
    groups = numwords.parse(text)
    assert len(groups) == 1 and not groups[0].ambiguous
    assert groups[0].value == value


@pytest.mark.parametrize("text,digits", [
    ("98470 12345", "9847012345"),
    ("9 8 4 7 0 1 2 3 4 5", "9847012345"),
    ("നാല് എട്ട് രണ്ട് ഒമ്പത് ഒന്ന് മൂന്ന്", "482913"),          # R03 said digit by digit
    ("തൊണ്ണൂറ്റിയെട്ട് നാൽപ്പത്തിയേഴ് പൂജ്യം ഒന്ന് രണ്ട് മൂന്ന് നാല് അഞ്ച്", "9847012345"),
    ("പൂജ്യം നാല് എട്ട്", "048"),
    ("SBL 2 0 4 7 8 1 3", "2047813"),
])
def test_digit_sequences(text, digits):
    assert numwords.digits(text) == (digits, [])


def test_t05_does_not_combine():
    heard, reasons = numwords.digits(T05_SPAN)
    assert heard == "9047012345"   # the literal reading: 10 digits, starts with 9, and wrong
    assert len(reasons) == 1 and "തൊണ്ണൂറ്റി നാൽപ്പത്തേഴ്" in reasons[0]


def test_dangling_joining_form_is_ambiguous():
    assert numwords.parse("തൊണ്ണൂറ്റി")[0].ambiguous


def test_old_style_chillu_is_normalised():
    assert numwords.parse("നാല്‍പ്പത്തേഴ്")[0].value == 47


def test_number_runs_skip_please():
    assert numwords.number_runs("ഇത് ഒന്ന് തിരിച്ചു പറയാമോ") == []
    assert numwords.number_runs("OTP നാല് എട്ട് രണ്ട് ആണ്") == ["നാല് എട്ട് രണ്ട്"]
