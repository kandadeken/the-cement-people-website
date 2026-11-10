# The original 35 checks

The first version of these tests was a single script, written while refining
the PDF quotation and WhatsApp message. It is kept here unchanged as
`original_checks.py`, with its 35/35 result against commit `d3f0e86` in
`original_run_d3f0e86.txt`. It contains file paths from the temporary
workspace it was written in, so it is a record, not something to run.

Every one of the 35 checks now exists as its own test in
`../test_baseline_35.py`. None was removed. The table shows where each went
and what was strengthened.

| # | Original check | Test | Strengthened |
| --- | --- | --- | --- |
| 1 | Stepper +/−, typed qty and totals unchanged | `test_b01` | Iron rod 12 mm is now added through search and the Add button (was an internal function call). Every estimate line and every totals row is compared exactly (was: total appears somewhere) |
| 2 | Search still filters | `test_b02` | Exactly one result with its price; clearing the search restores all 17 |
| 3 | Category tabs still switch | `test_b03` | Also checks the correct slide is actually showing, for two tabs |
| 4 | Quotation hidden on screen | `test_b04` | Unchanged |
| 5 | WhatsApp: estimate reference | `test_b05` | Checks the full heading with reference and date |
| 6 | WhatsApp: drop-off location | `test_b06` | Checks the labelled line |
| 7 | WhatsApp: items, qty, unit price, line totals | `test_b07` | The whole items block is compared exactly |
| 8 | WhatsApp: materials total | `test_b08` | Unchanged |
| 9 | WhatsApp: confirm availability and delivery | `test_b09` | Checks the exact closing sentence |
| 10 | WhatsApp: no location line when empty | `test_b10` | Also checks the closing sentence changes |
| 11 | A4 page size | `test_b11` | Measured from the PDF itself on every page |
| 12 | Short estimate fits one page | `test_b12` | Unchanged |
| 13 | PDF quantities print as plain numbers | `test_b13` | **Was loose** (passed if a 9 appeared anywhere). Now every PDF row is read back and compared exactly, and quantity cells must contain digits only |
| 14 | PDF has ref, date, location | `test_b14` | Now checks the date too, with labels |
| 15 | Short PDF: 'Page 1 of 1' | `test_b15` | Unchanged |
| 16 | Short PDF: no continuation header on page 1 | `test_b16` | Unchanged |
| 17 | Short PDF: closing section | `test_b17` | Also checks the total and the "quote reference" sentence |
| 18 | Same ref on screen, PDF and WhatsApp | `test_b18` | Unchanged |
| 19 | Ref format TCP-YYMMDD-XXXXXX | `test_b19` | Unchanged |
| 20 | No website controls in PDF | `test_b20` | Now checks that only the quotation block prints and that it contains no buttons, inputs or links (was: a few words absent from the text) |
| 21 | Clear estimate issues a new reference | `test_b21` | Uses the real Clear button and adds the next item through the UI |
| 22 | 5,000 references all different | `test_b22` | Presses the real Clear button 5,000 times (was an internal function call). **Corrected:** now requires at least 4,998 of 5,000 to differ. Demanding all 5,000 fails by pure chance about once in 85 runs (it did, on the first GitHub run), because one pair in 5,000 can match among roughly a billion possible codes |
| 23 | Long estimate flows to extra pages | `test_b23` | All 62 items are added through search, Add and typed quantities |
| 24 | Column headings repeat on page 2 | `test_b24` | Checked on every page that has rows |
| 25 | All 62 rows printed, none lost | `test_b25` | **Was a count.** Now every row's number, name, category, unit, quantity, price and amount is compared exactly |
| 26 | Long PDF: different ref from short PDF | `test_b26` | Unchanged |
| 27 | Continuation pages: brand, ref, 'Page 2 of N' | `test_b27` | Checked on every continuation page, not only page 2 |
| 28 | Page 1 of long PDF has no continuation header | `test_b28` | Unchanged |
| 29 | Last page: 'Page N of N' and closing section | `test_b29` | Unchanged |
| 30 | Totals block intact on last page | `test_b30` | Checks the actual amounts |
| 31 | No script errors (desktop) | `test_b31` | Covers both desktop scenarios |
| 32 | Mobile: 'View estimate' opens full screen | `test_b32` | Also measures that the panel covers the whole screen |
| 33 | Mobile print: A4, content present | `test_b33` | Every row compared exactly; only the quotation prints |
| 34 | No script errors (mobile) | `test_b34` | Unchanged |
| 35 | No test items in the site code | `test_b35` | **Was a word search.** Now also checks a freshly opened price list shows exactly the 17 real products |

## The four weaknesses identified in review

1. *An item was added by calling an internal function.* Fixed: all items in
   all scenarios are added through search, Add, + / − and typed quantities.
2. *The quantity check was loose.* Fixed in `test_b13` and `test_b25`.
3. *PDFs are made by headless Chrome, not a phone's print dialog.* This cannot
   be automated. It is documented in `../README.md`, and `test_n06` was added
   to confirm the Print button triggers printing.
4. *The test-data check proved little.* Fixed in `test_b35`, and the new
   catalogue tests compare the site against `products.json`.

Each strengthened test was verified by deliberately breaking a copy of the
site (a changed price, a changed unit, a quantity printed as an input box, a
missing reference, a reference that does not change on Clear, two dropped
rows) and confirming the relevant tests failed.
