"""
Visual refinements (Daniel and ChatGPT, 18 Nov 2026)
====================================================

  V01  price list: each category heading has working ‹ › buttons that move
       to the previous / next category; disabled at the ends; labelled for
       screen readers; also work from the keyboard; search results have none
  V02  price list: the heading is a shaded bar holding the title and the
       buttons; buttons are 44 px tall; text keeps good contrast
  V03  estimate: category headings are shaded strips without "01" markers;
       the thin ochre line between categories stays
  V04  estimate: products numbered 1, 2, 3... straight across categories, in
       a soft ochre square with charcoal numerals (28 px, 24 px on phones),
       all in one column; the same numbers as WhatsApp and the PDF
  V05  estimate name labels: charcoal with white text in light mode; a
       transparent box with a thin outline in dark mode
  V06  quantity and line total still share one line on phones
  V07  the PDF keeps its "01 · CEMENT" category markers
"""
import re

import pytest

from conftest import SITE_URL, print_pdf, settle

ORDER = "() => { const q = {c2: 3, c3: 3, c4: 3, i2: 5, i3: 5, i5: 5, j3: 2, i8: 6}; for (const k in q) qty[k] = q[k]; renderList(); renderEst(); }"
CATS = ["Cement, bags", "Iron rods, single pieces", "Iron rods, per ton", "Binding wire, rolls"]


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
        context.close()
        pytest.skip("Astro site only")
    return page, errors


CONTRAST = """(sel) => { const lum = c => { const v = c.match(/[\\d.]+/g).slice(0, 3).map(Number).map(x => { x /= 255; return x <= .03928 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4 }); return .2126 * v[0] + .7152 * v[1] + .0722 * v[2] };
  return [...document.querySelectorAll(sel)].filter(e => e.getClientRects().length).map(e => { let b = e, bg; while (b) { bg = getComputedStyle(b).backgroundColor; if (!/rgba\\(0, 0, 0, 0\\)|transparent/.test(bg)) break; b = b.parentElement }
    const x = lum(getComputedStyle(e).color), y = lum(bg); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05) }) }"""

ACTIVE = "document.querySelector('#tabs [aria-pressed=true]').innerText.replace(/\\s+/g, ' ').replace(/^\\d+ /, '')"
SHOWN = "(() => { const L = document.querySelector('#list'); return Math.round(L.scrollLeft / L.clientWidth) })()"


@pytest.mark.parametrize("width,mobile", [(390, True), (1280, False)])
def test_v01_category_arrows_move_between_categories(browser, width, mobile):
    page, errors = _open(browser, width, 844, mobile)
    labels = page.evaluate("[...document.querySelectorAll('#list .slide')].map(s => [...s.querySelectorAll('h3 .sgo')].map(b => [b.disabled, b.getAttribute('aria-label')]))")
    assert labels == [
        [[True, "Previous category"], [False, f"Next category: {CATS[1]}"]],
        [[False, f"Previous category: {CATS[0]}"], [False, f"Next category: {CATS[2]}"]],
        [[False, f"Previous category: {CATS[1]}"], [False, f"Next category: {CATS[3]}"]],
        [[False, f"Previous category: {CATS[2]}"], [True, "Next category"]],
    ], labels
    slide = lambda i: page.locator("#list .slide").nth(i)
    for i, expect in [(0, "Iron rods Single pieces"), (1, "Iron rods Per ton"), (2, "Binding wire Rolls")]:
        slide(i).locator(".sgo").nth(1).click()
        page.wait_for_timeout(700)
        assert page.evaluate(ACTIVE) == expect and page.evaluate(SHOWN) == i + 1
    slide(3).locator(".sgo").nth(0).click()
    page.wait_for_timeout(700)
    assert page.evaluate(ACTIVE) == "Iron rods Per ton" and page.evaluate(SHOWN) == 2
    # keyboard: focus the button and press Enter
    slide(2).locator(".sgo").nth(0).focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(700)
    assert page.evaluate(ACTIVE) == "Iron rods Single pieces" and page.evaluate(SHOWN) == 1
    # search results are a plain list: no arrows
    page.fill("#q", "12 mm")
    page.wait_for_timeout(200)
    assert page.locator("#list .sgo").count() == 0
    assert not errors, errors
    page.context.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_v02_shaded_heading_bar(browser, scheme):
    page, errors = _open(browser, 390, 844, True, scheme)
    bar = page.evaluate("(() => { const h = document.querySelector('#list .slide h3'), c = document.querySelector('#catalog'); return [getComputedStyle(h).backgroundColor, getComputedStyle(c).backgroundColor, getComputedStyle(h).borderBottomStyle] })()")
    assert bar[0] not in ("rgba(0, 0, 0, 0)", bar[1]) and bar[2] == "none", bar
    assert min(page.evaluate(CONTRAST, "#list .slide h3")) >= 7
    # title and both buttons inside the bar, on one line
    inside = page.evaluate("""(() => { const h = document.querySelector('#list .slide h3').getBoundingClientRect();
        return [...document.querySelectorAll('#list .slide:first-child h3 .sgo')].map(b => { const r = b.getBoundingClientRect(); return r.top >= h.top && r.bottom <= h.bottom && r.right <= h.right && r.height >= 44 }) })()""")
    assert inside == [True, True], inside
    assert not errors, errors
    page.context.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_v03_estimate_headings(browser, scheme):
    page, errors = _open(browser, 1280, 900, False, scheme)
    page.evaluate(ORDER)
    heads = page.evaluate("[...document.querySelectorAll('#lines .esh')].map(h => h.innerText.trim())")
    assert heads == ["CEMENT", "IRON RODS", "BINDING WIRE"], heads
    assert page.locator("#lines .eno").count() == 0
    fill = page.evaluate("getComputedStyle(document.querySelector('#glance .tiles div')).backgroundColor")
    assert page.evaluate("[...document.querySelectorAll('#lines .esh')].map(h => getComputedStyle(h).backgroundColor)") == [fill] * 3
    ochre = page.evaluate("getComputedStyle(document.querySelector('#send')).backgroundColor")
    lines = page.evaluate("[...document.querySelectorAll('#lines .es')].map(e => [getComputedStyle(e).borderTopColor, getComputedStyle(e).borderTopWidth])")
    assert lines == [[ochre, "2px"]] * 3, lines
    assert min(page.evaluate(CONTRAST, "#lines .esh b")) >= 7
    assert not errors, errors
    page.context.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width,size", [(360, 24), (390, 24), (1280, 28)])
def test_v04_products_numbered(browser, scheme, width, size):
    page, errors = _open(browser, width, 844, width < 900, scheme)
    page.evaluate(ORDER)
    nums = page.evaluate("""[...document.querySelectorAll('#lines .ln')].map(l => { const n = l.querySelector('.lno'), r = n.getBoundingClientRect(), s = getComputedStyle(n), p = l.querySelector('.pn').getBoundingClientRect();
        return {n: n.innerText, left: Math.round(r.left), w: Math.round(r.width), h: Math.round(r.height), bg: s.backgroundColor, ink: s.color, before: r.right <= p.left, smaller: r.height <= p.height + 2} })""")
    assert [x["n"] for x in nums] == [str(i) for i in range(1, 9)], nums
    assert len({x["left"] for x in nums}) == 1, "all numbers in one column"
    assert all(x["w"] == size and x["h"] == size for x in nums), nums
    assert all(x["bg"] == "rgb(255, 181, 73)" and x["ink"] == "rgb(41, 45, 43)" for x in nums), nums
    assert all(x["before"] and x["smaller"] for x in nums), nums
    assert min(page.evaluate(CONTRAST, "#lines .lno")) >= 7
    # the same numbers as the WhatsApp message
    names = page.evaluate("[...document.querySelectorAll('#lines .ln')].map(l => l.querySelector('.lno').innerText + '. ' + l.querySelector('.pn').innerText)")
    msg = page.evaluate("decodeURIComponent(document.querySelector('#send').href.split('text=')[1])")
    assert [m.split(" (")[0] for m in re.findall(r"^\d+\. .+$", msg, re.M)] == names
    assert not errors, errors
    page.context.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_v05_name_labels_by_theme(browser, scheme):
    page, errors = _open(browser, 390, 844, True, scheme)
    page.evaluate(ORDER)
    pn = page.evaluate("(() => { const s = getComputedStyle(document.querySelector('#lines .pn')); return [s.backgroundColor, s.color, s.boxShadow, s.fontWeight] })()")
    if scheme == "light":
        assert pn[0] == "rgb(41, 45, 43)" and pn[1] == "rgb(255, 255, 255)" and pn[2] in ("none", "rgba(0, 0, 0, 0) 0px 0px 0px 1.5px inset"), pn
    else:
        assert pn[0] == "rgba(0, 0, 0, 0)" and pn[1] == "rgb(243, 244, 242)" and "1.5px inset" in pn[2] and pn[3] == "700", pn
    assert not errors, errors
    page.context.close()


@pytest.mark.parametrize("width", [360, 390])
def test_v06_quantity_and_total_still_one_line(browser, width):
    page, errors = _open(browser, width, 800, True)
    page.evaluate(ORDER)
    for view in ("page", "full"):
        if view == "full":
            page.evaluate("openEst()")
        rows = page.evaluate("[...document.querySelectorAll('#lines .ln')].map(l => Math.abs(l.querySelector('.qty').getBoundingClientRect().top - l.querySelector('.amt').getBoundingClientRect().top) < 14)")
        assert rows == [True] * 8, (view, rows)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not errors, errors
    page.context.close()


def test_v07_pdf_keeps_category_markers(browser):
    page, errors = _open(browser)
    page.evaluate(ORDER)
    pdf = print_pdf(page, "v07-order.pdf")
    text = " ".join(pdf.text.split())
    for marker in ("01 · CEMENT", "02 · IRON RODS", "03 · BINDING WIRE"):
        assert marker in text, (marker, text[:600])
    assert not errors, errors
    page.context.close()
