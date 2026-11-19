"""
Estimate refinements (Daniel and ChatGPT, 17 Nov 2026)
======================================================

  R01  the category tiles come before the search box
  R02  estimate: no repeated "Line total" labels; an open section's heading
       shows only its name; delivery is explained once, and the price
       disclaimer stays on screen; the help says "Choose a category"
  R03  phones, full-screen estimate: the list gets at least 60% of the
       screen at 360 and 390 px; "Clear estimate" sits in the dark heading
       beside the date; the fixed bottom keeps the total and both buttons
  R04  computers, full view: a back arrow and a working close button (✕)
  R05  PDF: a subtotal never starts a page and a section heading never ends
       one; contact details one per line; no "Materials" line without tax;
       every quantity carries its unit
  R06  Contact: phone/WhatsApp first and large, then Enquire, then the rest

All shared between light and dark mode (checked in both where it matters).
"""
import re

import pytest

from conftest import BY_ID, PRODUCTS, SITE_URL, money, print_pdf, settle


def _open(browser, width=1280, height=900, mobile=False, scheme="light"):
    context = browser.new_context(viewport={"width": width, "height": height}, is_mobile=mobile,
                                  has_touch=mobile, color_scheme=scheme)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(SITE_URL, wait_until="load")
    page.wait_for_selector("#list .row")
    settle(page)
    if not page.evaluate("!!document.getElementById('tcp-data')"):
        pytest.skip("Astro site only")
    return page, errors


SMALL = "() => { const q = {c1: 40, c3: 25, i3: 30, j3: 2.5, i8: 6}; for (const k in q) qty[k] = q[k]; renderList(); renderEst(); }"
BIG = """() => { for (const p of P) qty[p.id] = p.unit === 'ton' ? 2.5 : p.cat === 'Cement' ? 120 : p.cat === 'Binding Wire' ? 6 : 24;
          renderList(); renderEst(); }"""


@pytest.mark.parametrize("width,mobile", [(390, True), (1280, False)])
def test_r01_tiles_before_search(browser, width, mobile):
    page, errors = _open(browser, width, 844, mobile)
    tiles = page.locator("#tabs").bounding_box()
    search = page.locator("#q").bounding_box()
    assert tiles["y"] + tiles["height"] <= search["y"] + 1, (tiles, search)
    page.context.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_r02_estimate_reads_more_simply(browser, scheme):
    page, errors = _open(browser, scheme=scheme)
    assert "Choose a category in the price list" in page.inner_text("#start")
    page.evaluate(SMALL)
    est = page.inner_text("#est")
    assert "Line total" not in est
    # Open sections: name only. Folded: quantity and total too.
    head = page.locator("#lines .es[data-g=rod] .esh")
    assert head.inner_text().split("\n") == ["IRON RODS"]  # no "02" since 18 Nov 2026
    head.click()
    assert "30 rods · 2.5 tons" in head.inner_text() and money(30 * BY_ID["i3"]["price"] + 2.5 * BY_ID["j3"]["price"]) in head.inner_text()
    # All subtotals kept, including the combined iron-rods line.
    head.click()
    subs = page.evaluate("[...document.querySelectorAll('#lines .es[data-g=rod] .est span')].map(s => s.textContent)")
    assert subs == ["Single pieces subtotal", "By the ton subtotal", "Iron rods subtotal"], subs
    # Each section starts with a thin ochre rule.
    assert page.evaluate("getComputedStyle(document.querySelector('#lines .es')).borderTopColor") == "rgb(255, 152, 2)"
    # Delivery explained once; the price disclaimer still shown.
    assert est.count("delivery cost") == 1, est
    assert page.inner_text(".fine") == "Estimates are indicative; final prices and availability are confirmed with you."
    assert not errors, errors
    page.context.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width,height", [(360, 740), (390, 844)])
def test_r03_phone_full_estimate_has_room(browser, width, height, scheme):
    page, errors = _open(browser, width, height, True, scheme)
    page.evaluate(SMALL)
    page.evaluate("openEst()")
    page.wait_for_timeout(150)
    r = page.evaluate("""() => { const s = document.querySelector('#escroll'), c = document.querySelector('#clear').getBoundingClientRect(),
        d = document.querySelector('.dm').getBoundingClientRect();
        return {share: s.clientHeight / innerHeight, clearBesideDate: Math.abs(c.top - d.top) < 24 && c.left > d.left,
                clearOnDark: getComputedStyle(document.querySelector('#etools')).backgroundColor,
                deliveryInFoot: document.querySelector('.tdl').getBoundingClientRect().height,
                sw: document.documentElement.scrollWidth}; }""")
    assert r["share"] >= 0.60, f"{width} px: the list gets only {r['share']:.0%} of the screen"
    assert r["clearBesideDate"], r
    assert r["clearOnDark"] == page.evaluate("getComputedStyle(document.querySelector('.dm')).backgroundColor"), r
    assert r["deliveryInFoot"] == 0, "delivery is explained in the Delivery box, not repeated in the fixed bottom"
    assert r["sw"] == width
    for sel in ("#tot .gt", "#send", "#print"):
        box = page.locator(sel).bounding_box()
        assert box and box["y"] + box["height"] <= height + 1, sel
    page.click("#clear")
    assert page.locator("#clearAsk").is_visible()
    assert not errors, errors
    page.context.close()


def test_r04_desktop_full_view_controls(browser):
    page, errors = _open(browser, 1440, 900)
    page.evaluate(SMALL)
    assert page.locator("#fullX").is_hidden()
    page.click("#full")
    assert page.locator("#full .i-back").is_visible() and page.locator("#full .i-open").is_hidden()
    assert page.inner_text("#full") == "Back to the price list"
    page.click("#fullX")
    assert "full" not in (page.get_attribute("#est", "class") or "")
    assert page.locator("#escrim").is_hidden()
    assert not errors, errors
    page.context.close()


def test_r05_pdf_page_breaks_and_details(browser):
    page, errors = _open(browser, 1280, 900)
    page.evaluate(BIG)
    page.fill("#loc", "Krispol City Road, Kasoa, near the Goil filling station")
    pdf = print_pdf(page, "refinements-large-order.pdf")
    assert pdf.count >= 2
    for n, text in enumerate(pdf.pages, start=1):
        lines = [l for l in text.split("\n") if l.strip()]
        # first table line after the repeated column headings
        try:
            i = next(k for k, l in enumerate(lines) if "UNIT PRICE" in l.upper() and "AMOUNT" in l.upper())
        except StopIteration:
            continue
        if n > 1:
            assert "subtotal" not in lines[i + 1].lower(), f"page {n} starts with a subtotal: {lines[i + 1]!r}"
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    # (the quotation is hidden on screen, so read its line breaks from the markup)
    contact = page.evaluate("document.querySelectorAll('#quote .q-to p')[2].innerHTML").split("<br>")
    assert contact[0].startswith("055 846 3468") and len(contact) == 3, contact
    assert page.locator("#quote .q-mat").count() == 0
    qtys = page.evaluate("[...document.querySelectorAll('#quote tbody tr')].filter(r => r.cells.length === 5 && !r.classList.length).map(r => r.cells[2].innerText)")
    assert all(re.fullmatch(r"[\d,.]+ (bags?|pcs?|tons?|rolls?)", q) for q in qtys), qtys
    assert "120 bags" in qtys and "2.5 tons" in qtys and "6 rolls" in qtys and "24 pcs" in qtys
    total = sum(p["price"] * (2.5 if p["unit"] == "ton" else 120 if p["category"] == "Cement" else 6 if p["category"] == "Binding Wire" else 24) for p in PRODUCTS)
    assert f"Total (excl. delivery) {money(total)}" in pdf.text
    assert not errors, errors
    page.context.close()


@pytest.mark.parametrize("width,mobile", [(390, True), (1280, False)])
def test_r06_contact_leads_with_the_phone(browser, width, mobile):
    page, errors = _open(browser, width, 844, mobile)
    order = page.evaluate("""() => ['.cphone', '#contact .enq', '.cdetails'].map(s => document.querySelector(s).getBoundingClientRect().top)""")
    assert order == sorted(order), order
    a = page.locator(".cphone a")
    assert a.get_attribute("href") == "tel:+233558463468" and a.inner_text() == "055 846 3468"
    assert float(page.evaluate("parseFloat(getComputedStyle(document.querySelector('.cphone a')).fontSize)")) >= 26
    assert "Phone and WhatsApp" not in page.inner_text(".cdetails")
    page.context.close()
