# Regression tests

These tests are the safety net for thecementpeople.com. They open the website
in a real (headless) Chrome browser, use it the way a customer would, and
check that the price list, the estimate, the PDF quotation and the WhatsApp
message all still behave correctly.

They run automatically on GitHub for every pull request. A red cross means
the change broke something and should not be merged.

## What is tested

| File | Tests | What it covers |
| --- | --- | --- |
| `test_baseline_35.py` | 35 | The original quotation checks: estimate behaviour, WhatsApp message, A4 PDF, references, long quotations, mobile, script errors |
| `test_catalogue.py` | 6 | All 17 product names, units and prices match `baseline/products.json` on the price list, the estimate, the WhatsApp message and the PDF; the Print button works |
| `test_product_images.py` | 15 | Product photos exist and stay small; cement and wire photos load straight away with alt text; both rod tabs show the same shared photo, then a visible heading and a "how it's sold" note; rod sizes are text tags; a missing photo is left out while the heading stays; no sideways scrolling on a phone, including on the rod tabs once the font and photo load; a phone gets the small 720 px rod photo for both tabs; every thumbnail exists in every size (80 to 360 px); thumbnails show at 96 px on computers and tablets and 80 px on phones, with the whole box used for the photo, and each screen (1×, 1.25×, 2×, 3×) downloads the size that suits it without names wrapping or prices being pushed out; the phone photo is no taller than the row's text |
| `test_seo.py` | 13 | Search-engine and AI readability of the Astro site: all 17 products present in the HTML without JavaScript and identical to what the engine draws; title, description, canonical address and link preview; structured data valid and containing only the confirmed details in `baseline/business.json`; business details visible; heading outline; image descriptions and sizes; sitemap; robots.txt; no broken links; logo file |
| `test_seo_live.py` | 8 | Search-engine basics on the live single-file site: title is only "The Cement People"; description and canonical address; structured data valid, linked and containing only the confirmed details in `baseline/business.json` (one shop in Kasoa, delivery areas as areas served, no ratings or prices); robots.txt lets search engines in and names the sitemap; sitemap.xml lists the homepage; GitHub Pages publishes both files; the title goes back to normal after printing |

`baseline/ORIGINAL_35_CHECKS.md` maps each of the 35 tests to the check it
came from and records what was strengthened. Nothing was removed.

## Running the tests on your own computer

You need Python 3.10 or newer. From the top folder of the repository:

```bash
pip install -r tests/requirements.txt
python -m playwright install chromium
python -m pytest tests -v
```

On Linux, if the browser fails to start, install its system libraries once
with `python -m playwright install --with-deps chromium`.

A full run takes about 30 seconds. The PDFs the tests generate are saved in
`tests/output/` so you can open and look at them.

### Testing the published website instead of the local files

```bash
TCP_SITE_URL=https://thecementpeople.com python -m pytest tests -v
```

On Windows PowerShell: `$env:TCP_SITE_URL="https://thecementpeople.com"; python -m pytest tests -v`

## How the tests are built

- `conftest.py` holds four scenarios (`short`, `long`, `mobile`, `catalogue`).
  Each one drives the site through its real controls: it searches, taps
  **Add**, taps **+** and **−**, types quantities, types a drop-off location,
  taps the category tabs and **Clear estimate**, then prints to PDF.
- Each test makes one assertion about what a scenario observed.
- PDFs are read back with `pypdf`, and every table row (number, product,
  category, unit, quantity, unit price, amount) is compared exactly.

## Which tests run where

- **Original site** (`index.html` opened from disk): the 41 quotation and
  catalogue tests. The 13 SEO tests are reported as *skipped*, because that
  site predates them.
- **Astro build** (served, `TCP_SITE_URL=http://127.0.0.1:4321/`): all 54.

`test_seo.py` mostly reads the page as plain HTML with no JavaScript, the way
a crawler does, using only Python's standard library.

## Changing a business detail

`baseline/business.json` is the reference copy of the confirmed business
details (address, phone, email, hours, delivery areas, page title and
description). The structured-data test accepts only the properties and values
recorded there, so nothing unconfirmed can be published by accident. To change
a detail, change it in `web/src/config/business.ts` and in that file, in the
same pull request.

## Changing a price

`baseline/products.json` is the reference copy of the catalogue. If a price,
name or unit changes on the website, the tests fail on purpose until the same
change is made in that file, in the same pull request. That makes every price
change deliberate and visible in review.

## Known limits

- **Print dialog.** Tests create the PDF with Chrome's built-in PDF function
  after firing the same "about to print" signal a real print does. They cannot
  click through a phone's own print dialog. `test_n06` confirms the on-page
  Print button asks the browser to print.
- **Browsers.** Only Chrome/Chromium is tested. Safari on iPhone prints the
  quotation but does not print page numbers or the continuation header; that
  is a browser limitation, not covered here.
- **Long quotation.** The site has 17 products, which fit on one page. To test
  multi-page quotations, the `long` scenario adds 45 synthetic "Test item"
  products to the browser's memory for that one page. They never exist in the
  website files; `test_b35` checks that. The items are then added to the
  estimate through the normal search and Add controls.
- **5,000 references.** `test_b22` presses the real **Clear estimate** button
  5,000 times from a script inside the page, rather than 5,000 separate
  simulated mouse clicks, to keep the run fast. It requires at least 4,998 of the
  5,000 to be different: with about a billion possible codes a day, one chance
  repeat in 5,000 happens in roughly 1 run in 85, so demanding a perfect 5,000
  would raise false alarms. At a realistic volume the risk is tiny (about 1 in
  200,000 for 100 quotations in one day), but references are not guaranteed
  unique without a database.
- **Fonts.** The site loads Montserrat from Google Fonts. On a machine without
  internet access the browser falls back to a system font; the tests ignore
  that one network error and do not depend on exact page counts for long
  quotations. The cedi sign (₵) is drawn from a fallback font when Montserrat is
  loaded, which changes the spacing of the PDF's text ("GH ₵ 44.00"); the tests
  normalise this, so results are the same with or without the web font.
- **Prices in numbers.** The browser is set to US English number formatting
  (`1,392.00`). A visitor whose phone uses a different locale may see a
  different thousands separator.

## Files

```
tests/
├─ README.md                  this file
├─ requirements.txt           the three Python packages the tests need
├─ conftest.py                scenarios and helpers
├─ test_baseline_35.py        the original 35 checks
├─ test_catalogue.py          catalogue and print-button checks
├─ test_product_images.py     product photos, banners and rod size tags
├─ screenshots/               review screenshots attached to pull requests
├─ test_seo.py                search-engine checks (Astro site only)
├─ test_seo_live.py           search-engine basics on the live site
├─ baseline/
│  ├─ products.json           reference copy of the 17 products
│  ├─ business.json           reference copy of the confirmed business details
│  ├─ ORIGINAL_35_CHECKS.md   mapping from the original checks to today's tests
│  ├─ original_checks.py      the original script, kept unchanged for the record
│  └─ original_run_d3f0e86.txt  its 35/35 result against commit d3f0e86
└─ output/                    generated PDFs (not committed)
```
