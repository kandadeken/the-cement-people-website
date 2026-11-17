"""
Estimate redesign and brand identity V1.1 (17 Nov 2026)
=======================================================

Checks the changes agreed with Daniel and ChatGPT on 17 Nov 2026:

  E01  the estimate is split into Cement / Iron rods (single pieces and by
       the ton) / Binding wire, each with its quantity and subtotal, and
       "Your order at a glance" adds up to the same quantities
  E02  with 18 product lines, only the materials list scrolls: the heading,
       "View full estimate", "Clear estimate", the total and the WhatsApp
       button stay in the same place (computer, 390 px and 360 px phones)
  E03  nothing sticks out sideways on 360 px and 390 px phones
  E04  screen, WhatsApp message and PDF show the same figures, half tons included
  E05  folding a section keeps its quantity and subtotal visible
  E06  phones: "View full estimate" is in the estimate's heading and opens the
       full-screen view, where it is not shown twice
  E07  computers: "View full estimate" opens the large view; Escape closes it
  E08  phones show the full horizontal logo in the header, never the emblem alone
  E09  the Enquire menu offers WhatsApp and a call, and closes again
  E10  the PDF quotation: logo, sections, subtotals, "Total (excl. delivery)",
       delivery "To be confirmed" and the contact details

Plain-English notes are written above each check.
"""
import re

import pytest

from conftest import BY_ID, PRODUCTS, SITE_URL, money, print_pdf, settle, squash


def _astro(page):
    if not page.evaluate("!!document.getElementById('tcp-data')"):
        pytest.skip("estimate redesign is on the Astro site only")


def _open(browser, width, height, mobile=False):
    context = browser.new_context(viewport={"width": width, "height": height},
                                  is_mobile=mobile, has_touch=mobile,
                                  device_scale_factor=2 if mobile else 1)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(SITE_URL, wait_until="load")
    page.wait_for_selector("#list .row")
    settle(page)
    _astro(page)
    return page, errors


# Every product, as a builder might order: 40 bags of each cement, 12 of each
# single rod, 2.5 tons of each rod size, 6 rolls of wire. 17 lines.
def _fill_everything(page):
    page.evaluate("""() => { for (const p of P)
        qty[p.id] = p.unit === 'ton' ? 2.5 : p.cat === 'Cement' ? 40 : p.cat === 'Binding Wire' ? 6 : 12;
        renderList(); renderEst(); }""")


def _expected_total():
    def q(p):
        return 2.5 if p["unit"] == "ton" else 40 if p["category"] == "Cement" else 6 if p["category"] == "Binding Wire" else 12
    return sum(p["price"] * q(p) for p in PRODUCTS)


# ---- E01 -------------------------------------------------------------------
def test_e01_sections_quantities_and_subtotals(browser):
    page, errors = _open(browser, 1280, 900)
    _fill_everything(page)
    sections = page.evaluate("""() => [...document.querySelectorAll('#lines .es')].map(s => ({
        name: s.querySelector('.enm b').innerText, count: s.querySelector('.enm span').innerText,
        sub: s.querySelector('.esx').innerText, lines: s.querySelectorAll('.ln').length}))""")
    cement = sum(p["price"] * 40 for p in PRODUCTS if p["category"] == "Cement")
    pieces = sum(p["price"] * 12 for p in PRODUCTS if p["category"] == "Iron Rods (Single Piece)")
    tons = sum(p["price"] * 2.5 for p in PRODUCTS if p["unit"] == "ton")
    wire = sum(p["price"] * 6 for p in PRODUCTS if p["category"] == "Binding Wire")
    assert sections == [
        {"name": "CEMENT", "count": "160 bags", "sub": money(cement), "lines": 4},
        {"name": "IRON RODS", "count": "72 rods · 15 tons", "sub": money(pieces + tons), "lines": 12},
        {"name": "BINDING WIRE", "count": "6 rolls", "sub": money(wire), "lines": 1},
    ], sections
    # Inside "Iron rods": single pieces and by the ton, each with its own subtotal.
    subs = page.evaluate("[...document.querySelectorAll('#lines .es[data-g=rod] .est')].map(e => e.innerText.replace(/\\s+/g, ' '))")
    assert subs == [f"Single pieces subtotal {money(pieces)}", f"By the ton subtotal {money(tons)}",
                    f"Iron rods subtotal {money(pieces + tons)}"], subs
    glance = page.evaluate("[...document.querySelectorAll('#glance .tiles div')].map(e => e.innerText.replace(/\\s+/g, ' '))")
    assert glance == ["160 bags of cement", "72 individual rods", "15 tons of rods", "6 rolls of binding wire"], glance
    assert page.inner_text("#tot .gt").split("\n") == ["Total (excl. delivery)", money(_expected_total())]
    assert page.inner_text("#tot").split("\n")[:2] == ["Delivery", "To be confirmed"]
    assert not errors, errors
    page.context.close()


# ---- E02 -------------------------------------------------------------------
PINNED = ["#est .dh", "#clear", "#tot .gt", "#send"]


@pytest.mark.parametrize("size", [(1440, 900, False), (390, 844, True), (360, 740, True)],
                         ids=["computer", "390px", "360px"])
def test_e02_only_the_materials_scroll(browser, size):
    width, height, mobile = size
    page, errors = _open(browser, width, height, mobile)
    # One more line than every product: a long, made-up name to test wrapping.
    page.evaluate("""() => { P.push({id: 'zz', cat: 'Cement', name: 'Extra-long test product name for wrapping checks 42.5R premium grade', unit: '50 kg bag', price: 99}); }""")
    _fill_everything(page)
    assert page.locator("#lines .ln").count() == 18
    if mobile:
        page.click("#barBtn")
    else:
        page.evaluate("scrollTo({top: document.querySelector('#products').offsetTop, behavior: 'instant'})")
    page.wait_for_timeout(200)
    where = lambda: [round(page.locator(s).bounding_box()["y"]) for s in PINNED]
    before = where()
    scroll = page.evaluate("(() => { const e = document.querySelector('#escroll'); return [e.scrollHeight, e.clientHeight]; })()")
    assert scroll[0] > scroll[1] + 200, f"the list should be long enough to scroll: {scroll}"
    for top in (300, 900, 99999):
        page.evaluate("t => { document.querySelector('#escroll').scrollTop = t; }", top)
        page.wait_for_timeout(80)
        assert where() == before, f"{width} px: pinned parts moved while scrolling the list to {top}"
    # Everything pinned is on screen.
    for s in PINNED:
        box = page.locator(s).bounding_box()
        assert 0 <= box["y"] and box["y"] + box["height"] <= height + 1, f"{s} is off screen: {box}"
    # The section heading sticks to the top of the list while scrolling through it.
    page.evaluate("document.querySelector('#escroll').scrollTop = 0")
    page.evaluate("""() => { const s = document.querySelector('#lines .es[data-g=rod]');
        const L = document.querySelector('#escroll');
        L.scrollTop = s.offsetTop - L.offsetTop + 400; }""")
    page.wait_for_timeout(80)
    gap = page.evaluate("""() => document.querySelector('#lines .es[data-g=rod] .esh').getBoundingClientRect().top
        - document.querySelector('#escroll').getBoundingClientRect().top""")
    assert abs(gap) <= 1, f"the Iron rods heading should stick to the top of the list ({gap} px)"
    assert not errors, errors
    page.context.close()


# ---- E03 -------------------------------------------------------------------
@pytest.mark.parametrize("width", [360, 390])
def test_e03_no_sideways_overflow_on_phones(browser, width):
    page, errors = _open(browser, width, 800, mobile=True)
    _fill_everything(page)
    page.fill("#loc", "Krispol City Road, Kasoa, near the Goil filling station, opposite the big blue gate")
    for state in ("page", "open"):
        if state == "open":
            page.click("#barBtn")
            page.wait_for_timeout(150)
        w = page.evaluate("[innerWidth, document.documentElement.scrollWidth]")
        assert w[1] <= w[0], f"{width} px ({state}): page is wider than the screen: {w}"
        out = page.evaluate("""() => { const bad = [], R = innerWidth;
            for (const e of document.querySelectorAll('#est *')) { const r = e.getBoundingClientRect();
                if (r.width && r.right > R + 0.5) bad.push([e.className || e.tagName, Math.round(r.right - R)]); }
            return bad.slice(0, 5); }""")
        assert not out, f"{width} px ({state}): these stick out: {out}"
    assert not errors, errors
    page.context.close()


# ---- E04 -------------------------------------------------------------------
def test_e04_screen_whatsapp_and_pdf_match(browser):
    page, errors = _open(browser, 1280, 900)
    _fill_everything(page)
    page.fill("#loc", "Kasoa, near Goil")
    screen = page.evaluate("""() => [...document.querySelectorAll('#lines .ln')].map(l => [
        l.querySelector('.nm').childNodes[0].textContent.trim(), l.querySelector('input').value,
        l.querySelector('.amt').childNodes[0].textContent.trim()])""")
    total = page.inner_text("#tot .gt").split("\n")[1]
    href = page.get_attribute("#send", "href")
    import urllib.parse
    message = urllib.parse.unquote(href.split("text=")[1])
    for i, (name, q, amount) in enumerate(screen, start=1):
        assert f"{i}. {name} (" in message, name
        assert f"   {q} × " in message and f" = {amount}" in message, (name, q, amount)
    assert f"*Materials total: {total}*" in message
    assert "2.5 × " in message, "half tons must be kept"
    pdf = print_pdf(page, "redesign-full-quotation.pdf")
    rows = page.evaluate("""() => [...document.querySelectorAll('#quote tbody tr')].filter(r => r.cells.length === 5)
        .map(r => [r.cells[1].childNodes[0].textContent.trim(), r.cells[2].innerText.trim(), r.cells[4].innerText.trim()])""")
    assert rows == screen
    assert f"Total (excl. delivery) {total}" in pdf.text
    assert "2.5" in pdf.text
    assert total == money(_expected_total())
    assert not errors, errors
    page.context.close()


# ---- E05 -------------------------------------------------------------------
def test_e05_folded_section_keeps_its_figures(browser):
    page, errors = _open(browser, 1280, 900)
    _fill_everything(page)
    head = page.locator("#lines .es[data-g=cem] .esh")
    assert head.get_attribute("aria-expanded") == "true", "sections start open"
    text = head.inner_text()
    head.click()
    assert head.get_attribute("aria-expanded") == "false"
    assert page.locator("#lines .es[data-g=cem] .ln").first.is_hidden()
    assert head.inner_text() == text and "160 bags" in text
    # Still folded after a quantity changes elsewhere; opens again on a tap.
    page.click('#est [data-inc="i8"]')
    assert page.locator("#lines .es[data-g=cem]").get_attribute("class").count("shut") == 1
    page.locator("#lines .es[data-g=cem] .esh").click()
    assert page.locator("#lines .es[data-g=cem] .ln").first.is_visible()
    assert not errors, errors
    page.context.close()


# ---- E06 -------------------------------------------------------------------
def test_e06_phone_view_full_estimate_in_the_heading(browser):
    page, errors = _open(browser, 390, 844, mobile=True)
    assert page.locator("#full").is_hidden(), "no tools while the estimate is empty"
    page.click('#list [data-inc="c1"]')
    page.evaluate("document.querySelector('#est').scrollIntoView({behavior: 'instant'})")
    assert page.locator("#full").is_visible(), "'View full estimate' should be in the estimate's heading"
    page.click("#full")
    assert "open" in page.get_attribute("#est", "class")
    # In the full-screen view the button would only reopen itself: hidden, not duplicated.
    assert page.locator("#full").is_hidden() and page.locator("#clear").is_visible()
    page.click("#dclose")
    assert "open" not in page.get_attribute("#est", "class")
    assert not errors, errors
    page.context.close()


# ---- E07 -------------------------------------------------------------------
def test_e07_computer_full_view(browser):
    page, errors = _open(browser, 1440, 900)
    _fill_everything(page)
    page.click("#full")
    box = page.locator("#est").bounding_box()
    assert "full" in page.get_attribute("#est", "class") and box["width"] > 700, box
    assert page.inner_text("#full") == "Back to the price list"
    page.keyboard.press("Escape")
    assert "full" not in page.get_attribute("#est", "class")
    assert page.locator("#escrim").is_hidden()
    assert not errors, errors
    page.context.close()


# ---- E08 -------------------------------------------------------------------
@pytest.mark.parametrize("width", [360, 390, 768])
def test_e08_phone_header_shows_the_full_horizontal_logo(browser, width):
    page, errors = _open(browser, width, 800, mobile=width < 600)
    logo = page.evaluate("""() => { const i = document.querySelector('header .brand img'), r = i.getBoundingClientRect();
        return {src: i.currentSrc, w: r.width, h: r.height, right: r.right}; }""")
    assert logo["src"].endswith("/brand/tcp-logo-horizontal-on-light.svg"), logo
    assert abs(logo["w"] / logo["h"] - 5.92) < 0.05, f"logo squashed or cropped: {logo}"
    assert logo["right"] <= width - 50, f"logo runs into the menu button: {logo}"
    page.context.close()
    page, errors = _open(browser, 1280, 800)
    src = page.evaluate("document.querySelector('header .brand img').currentSrc")
    assert src.endswith("/brand/tcp-logo-primary-on-light.svg"), src
    page.context.close()


# ---- E09 -------------------------------------------------------------------
@pytest.mark.parametrize("mobile", [False, True], ids=["computer", "phone"])
def test_e09_enquire_menu(browser, mobile):
    page, errors = _open(browser, 390 if mobile else 1280, 844, mobile)
    assert page.locator("header .enq, header a[href^='https://wa.me']").count() == 0, "no Enquire in the header"
    menu = page.locator("#enq-hero")
    assert menu.is_hidden()
    page.click('[aria-controls="enq-hero"]')
    assert menu.is_visible()
    links = menu.locator("a")
    assert links.count() == 2
    assert links.nth(0).get_attribute("href").startswith("https://wa.me/233558463468")
    assert links.nth(1).get_attribute("href") == "tel:+233558463468"
    page.keyboard.press("Escape")
    assert menu.is_hidden()
    assert page.get_attribute('[aria-controls="enq-hero"]', "aria-expanded") == "false"
    assert not errors, errors
    page.context.close()


# ---- E10 -------------------------------------------------------------------
def test_e10_branded_pdf_quotation(browser):
    page, errors = _open(browser, 1280, 900)
    _fill_everything(page)
    page.fill("#loc", "Kasoa, near Goil")
    pdf = print_pdf(page, "redesign-quotation-sample.pdf")
    first = squash(pdf.pages[0])
    for words in ("ESTIMATE", "Reference", "Date", "DROP-OFFLOCATION", "Kasoa,nearGoil",
                  "055 846 3468", "01·CEMENT", "02·IRONRODS"):
        assert squash(words) in first, words
    assert page.locator("#quote .q-logo path").count() >= 2, "the logo is drawn in the quotation"
    text = squash(pdf.text)
    assert squash("03 · Binding wire") in text
    assert squash("Iron rods, single pieces subtotal") in text and squash("Iron rods, by the ton subtotal") in text
    assert squash(f"Delivery To be confirmed") in text
    assert squash(f"Total (excl. delivery) {money(_expected_total())}") in text
    assert pdf.printed_blocks == ["quote"] and pdf.controls == 0
    # Nothing in the totals box is cut off, even for a large order
    # (a six-figure total was clipped on 17 Nov 2026).
    page.evaluate("() => { qty.c4 = 50000; qty.j1 = 500; renderEst(); }")
    page.emulate_media(media="print")
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    clipped = page.evaluate("""() => [...document.querySelectorAll('#quote .q-sum div')].flatMap(d => [...d.children].map(c => {
        const r = c.getBoundingClientRect(), D = d.getBoundingClientRect();
        return c.scrollWidth > c.clientWidth + 1 || r.right > D.right - 1 ? c.innerText : null; })).filter(Boolean)""")
    assert not clipped, f"cut off in the PDF totals: {clipped}"
    page.emulate_media(media="screen")
    assert not errors, errors
    page.context.close()


# ---- E06b ------------------------------------------------------------------
# "View full estimate" and "Clear estimate" each stay on one line on phones.
@pytest.mark.parametrize("width", [360, 390])
def test_e06b_estimate_tools_on_one_line(browser, width):
    page, errors = _open(browser, width, 800, mobile=True)
    page.click('#list [data-inc="c1"]')
    heights = page.evaluate("[...document.querySelectorAll('#etools .etool')].map(e => Math.round(e.getBoundingClientRect().height))")
    # Lines of text in each link (a range over the text gives one box per line).
    lines = page.evaluate("""[...document.querySelectorAll('#etools .etool span')].map(s => {
        const r = document.createRange(); r.selectNodeContents(s);
        return new Set([...r.getClientRects()].map(c => Math.round(c.top))).size; })""")
    assert lines == [1, 1], f"{width} px: the links wrap ({lines}, heights {heights})"
    page.context.close()


# ---- E11 -------------------------------------------------------------------
# Reported by Daniel from his Android phone (17 Nov 2026): with larger text,
# the price ran into the stepper's "–" button on products in the estimate.
# Here every font is made 15% larger (like the phone's text-size setting) and
# the price's actual text must stay clear of the stepper.
@pytest.mark.parametrize("width,scale", [(360, 1), (390, 1), (412, 1), (380, 1.15), (412, 1.15)])
def test_e11_price_never_touches_the_stepper(browser, width, scale):
    page, errors = _open(browser, width, 900, mobile=True)
    page.evaluate("() => { qty.c1 = 1699; qty.c2 = 5; qty.c3 = 364; qty.c4 = 6; renderList(); renderEst(); }")
    if scale != 1:
        page.evaluate("""s => { const all = [...document.querySelectorAll('body *')];
            const sizes = all.map(e => parseFloat(getComputedStyle(e).fontSize));
            all.forEach((e, i) => { e.style.fontSize = sizes[i] * s + 'px'; }); }""", scale)
    rows = page.evaluate("""() => [...document.querySelectorAll('#list .slide:first-child .row')].map(r => {
        const range = document.createRange(); range.selectNodeContents(r.querySelector('.pr'));
        const t = range.getBoundingClientRect(), s = r.querySelector('.qty, .add').getBoundingClientRect(),
              R = r.getBoundingClientRect();
        const apart = t.right <= s.left - 8 || s.top >= t.bottom - 1;
        return {apart, inside: s.right <= R.right + 0.5}; })""")
    assert rows and all(r["apart"] and r["inside"] for r in rows), f"{width} px x{scale}: {rows}"
    page.context.close()


# ---- E12 -------------------------------------------------------------------
# The most of one product is 50,000 (was 9,999; Daniel, 17 Nov 2026). Typing
# more is lowered to 50,000, and five digits fit in the quantity box.
@pytest.mark.parametrize("mobile", [False, True], ids=["computer", "phone"])
def test_e12_up_to_50000_of_one_product(browser, mobile):
    page, errors = _open(browser, 390 if mobile else 1280, 900, mobile)
    page.fill("#q", "Supacem 32.5R")
    page.click('#list [data-inc="c1"]')
    for typed, expect in (("50000", "50000"), ("12345", "12345"), ("60000", "50000")):
        box = page.locator('#list input[data-qty="c1"]')
        box.fill(typed)
        box.press("Tab")
        assert page.input_value('#est input[data-qty="c1"]') == expect, typed
    page.click('#est [data-inc="c1"]')  # + at the limit stays at 50,000
    assert page.input_value('#est input[data-qty="c1"]') == "50000"
    assert page.inner_text("#tot .gt").split("\n")[1] == money(75 * 50000)
    # Read with a thousands separator everywhere it is shown (the typing box
    # stays plain digits: a comma typed there means a decimal point).
    assert page.inner_text("#glance .tiles div") == "50,000 bags of cement"
    assert "50,000 bags" in page.inner_text("#lines .es[data-g=cem] .enm span")
    import urllib.parse
    assert "   50,000 × GH₵75.00 = GH₵3,750,000.00" in urllib.parse.unquote(page.get_attribute("#send", "href"))
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    assert page.evaluate("[...document.querySelectorAll('#quote tbody tr')].filter(r => r.cells.length === 5 && !r.classList.length)[0].cells[2].innerText") == "50,000"
    fits = page.evaluate("""() => [...document.querySelectorAll('input[data-qty="c1"]')].map(i => {
        const c = document.createElement('canvas').getContext('2d'), s = getComputedStyle(i);
        c.font = `${s.fontWeight} ${s.fontSize} ${s.fontFamily}`;
        return c.measureText(i.value).width <= i.clientWidth - 2; })""")
    assert fits and all(fits), f"50000 does not fit in the quantity box: {fits}"
    assert not errors, errors
    page.context.close()
