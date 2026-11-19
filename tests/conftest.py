"""Shared setup for The Cement People regression tests.

How the suite works
-------------------
Each "scenario" below opens the website in a real (headless) Chrome browser,
uses it the way a customer would -- searching, tapping Add, typing quantities,
typing a drop-off location, printing -- and records what it observed.
The test files then make one assertion per check against those observations.

The site under test defaults to ../index.html from this checkout.
Set TCP_SITE_URL to test a deployed copy instead, for example:

    TCP_SITE_URL=https://thecementpeople.com python -m pytest tests
"""
import json
import os
import re
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import expect, sync_playwright
from pypdf import PdfReader

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
# Where generated PDFs go. TCP_TEST_OUTPUT can point somewhere else, so that
# several copies of the suite can run at once without sharing files.
OUT = Path(os.environ.get("TCP_TEST_OUTPUT", "").strip() or TESTS / "output")
SITE_URL = os.environ.get("TCP_SITE_URL", "").strip() or (ROOT / "index.html").as_uri()

BASELINE = json.loads((TESTS / "baseline" / "products.json").read_text(encoding="utf-8"))
PRODUCTS = BASELINE["products"]
# The Astro site's prices are in "products". The single-file rollback copy
# (index.html at the repository root) is not edited when prices change, so
# its older prices are recorded under "singleFilePrices" and used whenever
# this run tests that copy (no TCP_SITE_URL given). Since 19 Nov 2026.
SINGLE_FILE_RUN = SITE_URL == (ROOT / "index.html").as_uri()
if SINGLE_FILE_RUN:
    for _p in PRODUCTS:
        _p["price"] = BASELINE.get("singleFilePrices", {}).get(_p["id"], _p["price"])
BY_ID = {p["id"]: p for p in PRODUCTS}
SYMBOL = BASELINE["currency_symbol"]

WA_PREFIX = "https://wa.me/233558463468?text="
REF_PATTERN = r"TCP-\d{6}-[2-9A-HJ-NP-Z]{6}"
# Typeface. The Astro site serves Montserrat from its own /fonts folder, so
# it always loads. The old single-file page (the rollback copy) asks Google
# Fonts for it. So that a test run never depends on the internet, the test
# browser is started with Google Fonts switched off (see the "browser"
# fixture): the single-file page then always uses its fallback font, on every
# machine. A failed request to these hosts is not a fault in the website.
FONT_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")
# Where screenshots and traces of a failed test are kept (uploaded by CI).
FAILURES = OUT / "failures"
A4_POINTS = (595.276, 841.89)

# Synthetic products used ONLY by the long-quotation test. They are added to
# the browser's memory for that one page and never exist in the website files.
SYNTHETIC = [
    {"id": f"t{k}", "category": "Iron Rods (Single Piece)", "name": f"Test item {k + 1}",
     "unit": "30 ft rod", "price": 10 + k}
    for k in range(45)
]


def pytest_report_header(config):
    return f"Site under test: {SITE_URL}"


def money(n):
    """Format a number the way the site shows prices, e.g. GH₵1,392.00."""
    return f"{SYMBOL}{n:,.2f}"


def squash(text):
    """Remove all whitespace and upper-case, so letter-spaced headings compare cleanly."""
    return re.sub(r"\s+", "", text).upper()


# --------------------------------------------------------------------------
# Waiting for the page to be ready (test-reliability pass, 15 Nov 2026)
# --------------------------------------------------------------------------
# The tests used to pause for a fixed time (say 0.9 s) after a tap and hope
# the page had finished moving. On a slow machine it sometimes had not. These
# helpers wait for the page to actually reach the expected state instead,
# for up to WAIT milliseconds, and carry on the moment it does.
WAIT = 8000


def settle(page):
    """Wait until fonts have loaded and the page has drawn, so sizes are final."""
    page.evaluate("""async () => { await document.fonts.ready;
        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); }""")


def _until(page, script, arg=None, must=True):
    """Wait for a condition in the page. With must=False a time-out is left
    for the test's own assertion to report, with its clearer message."""
    try:
        page.wait_for_function(script, arg=arg, timeout=WAIT)
        return True
    except PlaywrightTimeout:
        if must:
            raise
        return False


def wait_slide(page, index, must=True):
    """Wait until the price list has finished sliding to slide number `index`
    and that slide's tab is the selected one."""
    return _until(page, """i => { const L = document.querySelector('#list');
        const tabs = [...document.querySelectorAll('#tabs button')];
        return Math.abs(L.scrollLeft - i * L.clientWidth) < 2
            && tabs.findIndex(b => b.getAttribute('aria-pressed') === 'true') === i; }""", index, must)


def goto_tab(page, category=None, text=None, must=True):
    """Click a category tab (by exact name, or by part of its text) and wait
    for the list to finish sliding there."""
    index = page.evaluate(
        """([c, t]) => [...document.querySelectorAll('#tabs button')]
            .findIndex(b => c ? b.dataset.cat === c : (b.dataset.cat + ' ' + b.innerText).includes(t))""", [category, text])
    assert index >= 0, f"no tab for {category or text!r}"
    page.locator("#tabs button").nth(index).click()
    return wait_slide(page, index, must)


def wait_bar(page, shown, must=True):
    """Wait until the phone estimate bar is fully shown (docked at the bottom
    of the screen) or fully out of the way."""
    return _until(page, """shown => { const b = document.querySelector('#bar'), cs = getComputedStyle(b);
        const visible = cs.display !== 'none' && cs.visibility === 'visible';
        if (!shown) return !visible;
        return visible && Math.abs(b.getBoundingClientRect().bottom - innerHeight) <= 1; }""", shown, must)


def wait_rows(page, count, must=True):
    """Wait until the price list shows exactly `count` product rows (search results)."""
    return _until(page, "n => document.querySelectorAll('#list .row').length === n", count, must)


# --------------------------------------------------------------------------
# Browser helpers
# --------------------------------------------------------------------------
def open_site(browser, mobile=False, init_script=None):
    """Open the site in a fresh browser window. Returns (page, errors)."""
    options = {"locale": "en-US"}
    if mobile:
        options.update(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                       is_mobile=True, has_touch=True)
    else:
        options.update(viewport={"width": 1280, "height": 900})
    context = browser.new_context(**options)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(f"script exception: {exc}"))

    def on_console(msg):
        if msg.type != "error":
            return
        where = (msg.location or {}).get("url", "")
        if any(host in where or host in msg.text for host in FONT_HOSTS):
            return
        errors.append(f"console error: {msg.text}")

    page.on("console", on_console)
    if init_script:
        page.add_init_script(init_script)
    page.goto(SITE_URL, wait_until="load")
    page.wait_for_selector("#list .row")
    settle(page)
    return page, errors


def add_item(page, product, qty):
    """Add a product the way a customer does: search, tap Add, type the quantity."""
    pid = product["id"]
    page.fill("#q", product["name"])
    page.click(f'#list [data-inc="{pid}"]')
    if qty != 1:
        box = page.locator(f'#list input[data-qty="{pid}"]')
        box.fill(str(qty))
        box.press("Tab")
    shown = page.locator(f'#est input[data-qty="{pid}"]').input_value()
    assert shown == str(qty), f"{product['name']}: typed {qty}, estimate shows {shown}"


def clear_search(page):
    page.fill("#q", "")
    page.wait_for_selector("#list .slide")


def type_location(page, text):
    page.fill("#loc", text)


def read_ref(page):
    return page.inner_text("#ref").replace("Ref ", "").strip()


def whatsapp_message(page):
    """The text the 'Send my estimate on WhatsApp' button would send."""
    href = page.get_attribute("#send", "href") or ""
    assert href.startswith(WA_PREFIX), f"unexpected WhatsApp link: {href[:60]}"
    return urllib.parse.unquote(href[len(WA_PREFIX):])


def click_tab(page, category):
    """Tap a category tab; report whether it is selected and which slide is showing."""
    goto_tab(page, category, must=False)  # the caller's assertions report a failure
    pressed = page.get_attribute(f'#tabs button[data-cat="{category}"]', "aria-pressed")
    slide = page.evaluate(
        "() => { const L = document.querySelector('#list');"
        " return Math.round(L.scrollLeft / L.clientWidth); }")
    return SimpleNamespace(pressed=pressed, slide=slide)


def price_list(page):
    """Read the visible price list: one entry per product row."""
    return page.evaluate("""() =>
        [...document.querySelectorAll('#list section')].flatMap(sec => {
            // The category heading is the first heading in its section: <h2> on the
            // original single-file site, <h3> on the Astro site (corrected outline).
            const category = sec.querySelector('h2, h3').textContent.trim();
            return [...sec.querySelectorAll('.row')].map(row => {
                const nm = row.querySelector('.nm');
                return {
                    category,
                    // Astro since 18 Nov 2026: the name is in its label (.pn), after
                // the product number; the single-file site has plain text.
                name: (nm.querySelector('.pn') || nm.childNodes[0]).textContent.trim(),
                    unit: nm.querySelector('small').textContent.trim().replace(/^per /, ''),
                    price: row.querySelector('.pr').textContent.trim(),
                };
            });
        })""")


def estimate_lines(page):
    """Read the on-screen estimate panel: one entry per line."""
    return page.evaluate("""() =>
        [...document.querySelectorAll('#lines .ln')].map(ln => {
            const nm = ln.querySelector('.nm');
            return {
                // Astro since 18 Nov 2026: the name is in its label (.pn), after
                // the product number; the single-file site has plain text.
                name: (nm.querySelector('.pn') || nm.childNodes[0]).textContent.trim(),
                detail: nm.querySelector('small').textContent.trim(),
                qty: ln.querySelector('input[data-qty]').value,
                amount: ln.querySelector('.amt').textContent.trim(),
            };
        })""")


# --------------------------------------------------------------------------
# PDF helpers
# --------------------------------------------------------------------------
# One item row of the PDF, as read back out of it. Since 17 Nov 2026 the
# Astro site's quantity carries its unit word ("9 bags", "24 pcs"), the same
# word as beside the quantity box on screen. Two layouts:
# - Astro site since 17 Nov 2026, one line:
#   "3 Iron rod 16 mm per 30 ft rod 12 GH₵102.00 GH₵1,224.00"
#   (the material's kind is in the section heading above it)
# - original single-file site (kept at the repository root as the rollback
#   site), three lines: "3 Iron rod 16 mm" / "Iron Rods (Single Piece), per
#   30 ft rod" / "12 GH₵102.00 GH₵1,224.00"
ROW = re.compile(
    r"^(\d+) (.+?) per (.+) (\d{1,3}(?:,\d{3})*(?:\.\d+)?)(?: [a-z]+)? " + re.escape(SYMBOL) + r"([\d,]+\.\d{2}) "
    + re.escape(SYMBOL) + r"([\d,]+\.\d{2})$", re.M)
ROW_SINGLE_FILE = re.compile(
    r"^(\d+) (.+)\n.+, per (.+)\n(\d+) " + re.escape(SYMBOL) + r"([\d,]+\.\d{2}) "
    + re.escape(SYMBOL) + r"([\d,]+\.\d{2})$", re.M)


def is_astro(page):
    """True on the Astro site; False on the original single-file site."""
    return page.evaluate("!!document.getElementById('tcp-data')")


# Binding wire has its own category on the Astro site since 17 Nov 2026
# (tests/baseline/products.json); the single-file site still lists it with
# the single-piece rods.
SINGLE_FILE_CATEGORY = {"i8": "Iron Rods (Single Piece)"}


def category_on(product, astro):
    return product["category"] if astro else SINGLE_FILE_CATEGORY.get(product["id"], product["category"])


def tidy_pdf_text(text):
    """Remove spacing differences that depend on which font the PDF was drawn with.

    The cedi sign is not in every typeface. When the browser has to borrow it
    from another font, the PDF's text comes out as "GH ₵ 44.00" instead of
    "GH₵44.00". The printed page looks the same either way.
    """
    cedi = re.escape(SYMBOL[-1])
    text = re.sub(r"GH\s*" + cedi + r"\s*", SYMBOL, text)
    return re.sub(r"[ \t\u00a0]+", " ", text)


def parse_rows(page_text):
    """Pull every table row out of one PDF page: (#, name, unit, qty, unit price, amount)."""
    found = ROW.findall(page_text) or ROW_SINGLE_FILE.findall(page_text)
    # Quantities are printed with thousands separators ("50,000") since 17 Nov 2026.
    return [(int(n), name, unit, float(qty.replace(",", "")) if "." in qty else int(qty.replace(",", "")), price, amount)
            for n, name, unit, qty, price, amount in found]


def in_sections(items, astro=True):
    """Put (product, qty) pairs in the order the estimate and PDF list them
    on the Astro site since 17 Nov 2026: cement, single rods, rods by the
    ton, binding wire. Within a section the order is unchanged. The
    single-file site keeps the order the items were added in."""
    if not astro:
        return list(items)
    def part(product):
        if product["category"] == "Cement":
            return 0
        if product["unit"] == "ton":
            return 2
        if product["category"] == "Binding Wire":
            return 3
        return 1
    return sorted(items, key=lambda item: part(item[0]))


def expected_row(number, product, qty):
    return (number, product["name"], product["unit"], qty,
            f"{product['price']:,.2f}", f"{product['price'] * qty:,.2f}")


def print_pdf(page, filename):
    """Print the page to PDF exactly as the browser's print function would."""
    OUT.mkdir(exist_ok=True)
    path = OUT / filename
    page.emulate_media(media="print")
    page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    printed_blocks = page.evaluate(
        "() => [...document.body.children]"
        ".filter(e => getComputedStyle(e).display !== 'none')"
        ".map(e => e.id || e.tagName.toLowerCase())")
    controls = page.locator(
        "#quote input, #quote button, #quote select, #quote textarea, #quote a").count()
    # Item rows only: since 17 Nov 2026 the quotation also has section rows
    # ("01 · Cement") and subtotal rows, which have fewer cells.
    qty_cells = page.evaluate(
        "() => [...document.querySelectorAll('#quote tbody tr')]"
        ".filter(r => r.cells.length === 5 && !r.classList.length).map(r => r.cells[2].innerHTML)")
    page.pdf(path=str(path), prefer_css_page_size=True, print_background=True)
    page.evaluate("window.dispatchEvent(new Event('afterprint'))")
    page.emulate_media(media="screen")

    reader = PdfReader(str(path))
    texts = [tidy_pdf_text(p.extract_text()) for p in reader.pages]
    return SimpleNamespace(
        path=path,
        pages=texts,
        text="\n".join(texts),
        count=len(reader.pages),
        sizes=[(float(p.mediabox.width), float(p.mediabox.height)) for p in reader.pages],
        rows=[row for t in texts for row in parse_rows(t)],
        printed_blocks=printed_blocks,
        controls=controls,
        qty_cells=qty_cells,
    )


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def browser():
    global _BROWSER
    with sync_playwright() as pw:
        # Google Fonts switched off, so no test depends on the internet (see
        # FONT_HOSTS above).
        b = pw.chromium.launch(args=[
            "--host-rules=" + ", ".join(f"MAP {h} 0.0.0.0" for h in FONT_HOSTS)])
        # Every browser window records a "trace" (what was clicked, what the
        # page looked like at each step). It is only saved if a test fails.
        make_context = b.new_context

        def new_context(**options):
            context = make_context(**options)
            try:
                context.tracing.start(screenshots=True, snapshots=True)
            except Exception:
                pass
            return context

        b.new_context = new_context
        _BROWSER = b
        yield b
        _BROWSER = None
        b.close()


_BROWSER = None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """When a test fails, keep a screenshot of every open page and the
    recorded trace in tests/output/failures/ (CI uploads that folder). Open a
    trace with:  python -m playwright show-trace <file>.zip"""
    report = (yield).get_result()
    if not report.failed or _BROWSER is None:
        return
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", item.nodeid.split("::", 1)[-1])[:90]
    try:
        FAILURES.mkdir(parents=True, exist_ok=True)
        for c, context in enumerate(_BROWSER.contexts):
            for n, page in enumerate(context.pages):
                try:
                    page.screenshot(path=str(FAILURES / f"{name}-window{c}-page{n}.png"))
                except Exception:
                    pass
            try:
                context.tracing.stop(path=str(FAILURES / f"{name}-window{c}-trace.zip"))
                context.tracing.start(screenshots=True, snapshots=True)
            except Exception:
                pass
    except Exception:
        pass


LOCATION = "Buduburam, Block 4 near the clinic"


@pytest.fixture(scope="session")
def short(browser):
    """A two-item estimate on a desktop screen, built entirely through the UI."""
    page, errors = open_site(browser)
    s = SimpleNamespace(errors=errors, astro=is_astro(page))
    s.page_source_on_load = page.content()
    s.quote_visible_on_screen = page.is_visible("#quote")

    # Supacem 42.5R: tap Add in the price list, tap + nine times, later tap - once -> 9
    page.click('#list [data-inc="c2"]')
    for _ in range(9):
        page.click('#est [data-inc="c2"]')
    s.c2_after_plus = page.locator('#est input[data-qty="c2"]').input_value()
    # Iron rod 12 mm (single piece): search, tap Add, type 25, then retype 24 in the estimate
    add_item(page, BY_ID["i3"], 25)
    clear_search(page)
    box = page.locator('#est input[data-qty="i3"]')
    box.fill("24")
    box.press("Tab")
    page.click('#est [data-dec="c2"]')
    s.lines = estimate_lines(page)
    s.totals = page.inner_text("#tot")

    # Search
    page.fill("#q", "dzata")
    s.search_rows = price_list(page)
    clear_search(page)
    s.rows_after_clearing_search = len(price_list(page))

    # Category tabs
    s.tab_per_ton = click_tab(page, "Iron Rods (Per Ton)")
    s.tab_cement = click_tab(page, "Cement")

    # WhatsApp message with and without a drop-off location
    s.ref = read_ref(page)
    s.date = page.inner_text("#date").strip()
    type_location(page, LOCATION)
    s.message = whatsapp_message(page)
    type_location(page, "")
    s.message_without_location = whatsapp_message(page)
    type_location(page, LOCATION)

    s.pdf = print_pdf(page, "short-quotation.pdf")

    # Start a new quotation with the Clear button. Since 17 Nov 2026 it asks
    # first ("Remove everything from this estimate?"); "Clear all" clears.
    page.click("#clear")
    if s.astro:
        page.click("#clearYes")
    s.ref_after_clear = read_ref(page)
    s.lines_after_clear = estimate_lines(page)
    add_item(page, BY_ID["c1"], 2)
    clear_search(page)
    s.message_after_clear = whatsapp_message(page)

    # Press the real Clear button 5,000 times and collect every reference issued
    s.unique_refs = page.evaluate("""() => {
        // Each round: "Clear estimate", then "Clear all" if it asks (it only
        // asks while the estimate has items in it).
        const seen = new Set(), button = document.querySelector('#clear'), yes = document.querySelector('#clearYes');
        for (let i = 0; i < 5000; i++) {
            button.click();
            if (yes && !yes.closest('[hidden]')) yes.click();
            seen.add(document.querySelector('#ref').textContent);
        }
        return seen.size;
    }""")
    page.context.close()
    return s


@pytest.fixture(scope="session")
def long(browser):
    """A 62-row estimate: the 17 real products plus 45 synthetic ones, to force extra pages."""
    page, errors = open_site(browser)
    # Test fixture: extend the catalogue in this browser tab's memory only.
    page.evaluate(
        "items => { for (const it of items) P.push({id: it.id, cat: it.category,"
        " name: it.name, unit: it.unit, price: it.price}); }", SYNTHETIC)
    s = SimpleNamespace(errors=errors, expected=[], astro=is_astro(page))
    for product in PRODUCTS:
        add_item(page, product, 3)
        s.expected.append((product, 3))
    for k, product in enumerate(SYNTHETIC):
        add_item(page, product, k + 1)
        s.expected.append((product, k + 1))
    clear_search(page)
    s.ref = read_ref(page)
    s.materials_total = sum(p["price"] * q for p, q in s.expected)
    s.pdf = print_pdf(page, "long-quotation.pdf")
    page.context.close()
    return s


@pytest.fixture(scope="session")
def mobile(browser):
    """A four-item estimate on a phone-sized touch screen."""
    page, errors = open_site(browser, mobile=True)
    s = SimpleNamespace(errors=errors, astro=is_astro(page))
    s.items = [(BY_ID["c1"], 40), (BY_ID["c4"], 12), (BY_ID["j3"], 2), (BY_ID["i8"], 5)]
    for product, qty in s.items:
        add_item(page, product, qty)
    clear_search(page)
    # Back at the top of the page, where the estimate panel is off screen and
    # the bar shows. (Since the catalogue phase the bar steps aside while the
    # estimate panel itself is on screen.)
    page.evaluate("scrollTo({top: 0, behavior: 'instant'})")
    wait_bar(page, True)
    page.click("#barBtn")
    _until(page, "() => document.querySelector('#est').classList.contains('open')", must=False)
    settle(page)
    s.estimate_open = page.evaluate(
        "document.querySelector('#est').classList.contains('open')")
    s.estimate_box = page.locator("#est").bounding_box()
    s.viewport = page.viewport_size
    type_location(page, "Kasoa, Millennium City")
    s.ref = read_ref(page)
    s.pdf = print_pdf(page, "mobile-quotation.pdf")
    page.context.close()
    return s


@pytest.fixture(scope="session")
def catalogue(browser):
    """Every real product, at quantity 1, on every surface a customer sees."""
    page, errors = open_site(browser)
    s = SimpleNamespace(errors=errors, astro=is_astro(page))
    s.price_list = price_list(page)
    for product in PRODUCTS:
        add_item(page, product, 1)
    clear_search(page)
    s.lines = estimate_lines(page)
    s.totals = page.inner_text("#tot")
    s.message = whatsapp_message(page)
    s.pdf = print_pdf(page, "catalogue-quotation.pdf")
    page.context.close()
    return s
