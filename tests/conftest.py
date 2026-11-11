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
from playwright.sync_api import sync_playwright
from pypdf import PdfReader

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
OUT = TESTS / "output"
SITE_URL = os.environ.get("TCP_SITE_URL", "").strip() or (ROOT / "index.html").as_uri()

BASELINE = json.loads((TESTS / "baseline" / "products.json").read_text(encoding="utf-8"))
PRODUCTS = BASELINE["products"]
BY_ID = {p["id"]: p for p in PRODUCTS}
SYMBOL = BASELINE["currency_symbol"]

WA_PREFIX = "https://wa.me/233558463468?text="
REF_PATTERN = r"TCP-\d{6}-[2-9A-HJ-NP-Z]{6}"
# The site loads its typeface from Google Fonts. A machine without internet
# access falls back to a system font; that is not a fault in the website.
FONT_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")
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
    page.click(f'#tabs button[data-cat="{category}"]')
    page.wait_for_timeout(900)
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
                    name: nm.childNodes[0].textContent.trim(),
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
                name: nm.childNodes[0].textContent.trim(),
                detail: nm.querySelector('small').textContent.trim(),
                qty: ln.querySelector('input[data-qty]').value,
                amount: ln.querySelector('.amt').textContent.trim(),
            };
        })""")


# --------------------------------------------------------------------------
# PDF helpers
# --------------------------------------------------------------------------
ROW = re.compile(
    r"^(\d+) (.+)\n(.+), per (.+)\n(\d+) " + re.escape(SYMBOL) + r"([\d,]+\.\d{2}) "
    + re.escape(SYMBOL) + r"([\d,]+\.\d{2})$", re.M)


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
    """Pull every table row out of one PDF page: (#, name, category, unit, qty, unit price, amount)."""
    return [(int(n), name, cat, unit, int(qty), price, amount)
            for n, name, cat, unit, qty, price, amount in ROW.findall(page_text)]


def expected_row(number, product, qty):
    return (number, product["name"], product["category"], product["unit"], qty,
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
    qty_cells = page.evaluate(
        "() => [...document.querySelectorAll('#quote tbody tr')]"
        ".map(r => r.cells.length === 5 ? r.cells[2].innerHTML : null)")
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
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


LOCATION = "Buduburam, Block 4 near the clinic"


@pytest.fixture(scope="session")
def short(browser):
    """A two-item estimate on a desktop screen, built entirely through the UI."""
    page, errors = open_site(browser)
    s = SimpleNamespace(errors=errors)
    s.page_source_on_load = page.content()
    s.quote_visible_on_screen = page.is_visible("#quote")

    # Supacem 42.5: tap Add in the price list, tap + nine times, later tap - once -> 9
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

    # Start a new quotation with the Clear button
    page.click("#clear")
    s.ref_after_clear = read_ref(page)
    s.lines_after_clear = estimate_lines(page)
    add_item(page, BY_ID["c1"], 2)
    clear_search(page)
    s.message_after_clear = whatsapp_message(page)

    # Press the real Clear button 5,000 times and collect every reference issued
    s.unique_refs = page.evaluate("""() => {
        const seen = new Set(), button = document.querySelector('#clear');
        for (let i = 0; i < 5000; i++) {
            button.click();
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
    s = SimpleNamespace(errors=errors, expected=[])
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
    s = SimpleNamespace(errors=errors)
    s.items = [(BY_ID["c1"], 40), (BY_ID["c4"], 12), (BY_ID["j3"], 2), (BY_ID["i8"], 5)]
    for product, qty in s.items:
        add_item(page, product, qty)
    clear_search(page)
    page.click("#barBtn")
    page.wait_for_timeout(300)
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
    s = SimpleNamespace(errors=errors)
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
