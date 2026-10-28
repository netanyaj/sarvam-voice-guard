# Recording script (about 15 minutes)

Record each line as a separate clip on your phone (Voice Memos) or QuickTime. Speak naturally, the way
you would to a customer-care agent. Keep each clip under 25 seconds. Save as R01.m4a ... R12.m4a in
`guard/data/recordings/`. Ground truth is already filled in `data/recordings.csv`; if you say something
different, edit that row.

| Clip | Say this | What it tests |
|---|---|---|
| R01 | എന്റെ നമ്പർ 98470 12345 ആണ് (say it in groups, the way you normally would) | phone, grouped |
| R02 | എന്റെ നമ്പർ 9 8 4 7 0 1 2 3 4 5 (digit by digit) | phone, digit by digit |
| R03 | OTP 4 8 2 9 1 3 ആണ് | otp |
| R04 | എന്റെ EMI പതിനാലായിരത്തി നാനൂറ്റി പതിനഞ്ച് രൂപയാണ് | amount in words |
| R05 | നാലര ലക്ഷം രൂപയുടെ loan ആണ് എടുത്തത് | lakh |
| R06 | അടുത്ത മാസം അഞ്ചാം തീയതി premium അടയ്ക്കാം | relative date |
| R07 | എന്റെ policy number SBL 2 0 4 7 8 1 3 ആണ് | alphanumeric id |
| R08 | ഇടപ്പള്ളി Lulu Mall ന്റെ അടുത്താണ് വീട് | place names in code-mix |
| R09 | തൃപ്പൂണിത്തുറ branch ലെ Anand sir ആണ് എന്നെ വിളിച്ചത് | place + person name |
| R10 | എന്റെ നമ്പർ 98470... അല്ല, 98471 12345 | self-correction |
| R11 | Repeat R01 with a fan or TV on nearby | noise |
| R12 | Repeat R07 quickly | fast speech |
