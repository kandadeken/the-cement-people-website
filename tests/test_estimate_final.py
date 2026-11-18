"""
Final estimate refinements (Daniel and ChatGPT, 18 Nov 2026)
============================================================

  R07  the estimate on the page: heading as large as "Products and prices"
       and a 3 px ochre top edge; the full view (phone and computer) keeps
       its smaller title and no edge
  R08  "View full estimate" has an ochre outline, not a solid fill;
       Clear estimate stays a quiet text link
  R09  phones (360 and 390 px): quantity and line total on one line for a
       normal order; very large amounts drop underneath; no digit, amount
       or control is ever cut off, and the page never scrolls sideways
  R10  subtotals are light shaded strips whose text keeps good contrast,
       in light and dark
  R11  WhatsApp opens with the agreed sentence, keeps every item, and its
       total matches the screen and the PDF
  R12  sticky parts: the bottom bar shows while choosing products and hides
       once the estimate is on screen; no new sticky row in the estimate
  R13  phones: more room between the end of the estimate and About us
  R14  each product name sits in a small label (name only; the unit price
       stays outside, under it): deep charcoal with white text in light
       mode, soft ivory with charcoal text in dark mode
  R15  "Total (excl. delivery)" is a dark bar with an ochre left edge and
       white text, on the page and in the full view, light and dark; it
       fits on one line at 360 px; delivery stays a separate line on the
       page on phones and in the full view (not pinned in the desktop
       panel, where the Delivery box explains it); the WhatsApp button keeps
       the only ochre fill
"""
import re

import pytest

from conftest import SITE_URL, money, print_pdf, settle

ORDER = "() => { const q = {c2: 3, c3: 3, c4: 3, i2: 5, i3: 5, i5: 5, j3: 2, i8: 6}; for (const k in q) qty[k] = q[k]; renderList(); renderEst(); }"
ORDER_TOTAL = 3 * 100 + 3 * 110 + 3 * 120 + 5 * 75 + 5 * 58 + 5 * 40 + 2 * 7000 + 6 * 60
HUGE = "() => { const q = {c2: 50000, j3: 50000, i3: 999, j5: 20}; for (const k in q) qty[k] = q[k]; renderList(); renderEst(); }"


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


def _px(page, selector, prop):
    return float(page.evaluate(f"parseFloat(getComputedStyle(document.querySelector('{selector}'))['{prop}'])"))


CONTRAST = """(sel) => { const lum = c => { const v = c.match(/[\\d.]+/g).slice(0, 3).map(Number).map(x => { x /= 255; return x <= .03928 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4 }); return .2126 * v[0] + .7152 * v[1] + .0722 * v[2] };
  return [...document.querySelectorAll(sel)].map(e => { let b = e, bg; while (b) { bg = getComputedStyle(b).backgroundColor; if (!/rgba\\(0, 0, 0, 0\\)|transparent/.test(bg)) break; b = b.parentElement }
    const x = lum(getComputedStyle(e).color), y = lum(bg); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05) }) }"""


@pytest.mark.parametrize("width,mobile", [(360, True), (390, True), (1280, False)])
def test_r07_estimate_heading(browser, width, mobile):
    page, errors = _open(browser, width, 844, mobile)
    page.evaluate(ORDER)
    section = _px(page, "#catalog h2", "fontSize")
    assert _px(page, "#est .dh b", "fontSize") == section
    assert _px(page, "#est", "borderTopWidth") == 3
    assert page.evaluate("getComputedStyle(document.querySelector('#est')).borderTopColor") == \
        page.evaluate("getComputedStyle(document.querySelector('.eno')).backgroundColor")
    # the title stays on one line
    assert page.evaluate("document.querySelector('#est .dh b').getClientRects().length") == 1
    assert _px(page, "#est .dh b", "height") < section * 1.6
    page.evaluate("openEst()" if mobile else "fullEst(true)")
    assert _px(page, "#est .dh b", "fontSize") < section
    assert _px(page, "#est", "borderTopWidth") <= 1
    assert not errors, errors
    page.context.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_r08_view_full_estimate_outline(browser, scheme):
    page, errors = _open(browser, 390, 844, True, scheme)
    page.evaluate(ORDER)
    ochre = page.evaluate("getComputedStyle(document.querySelector('.eno')).backgroundColor")
    s = page.evaluate("(() => { const s = getComputedStyle(document.querySelector('#full')); return [s.borderTopColor, s.borderTopWidth, s.backgroundColor, s.textDecorationLine] })()")
    assert s[0] == ochre and float(s[1].rstrip("px")) >= 1, s
    assert s[2] in ("rgba(0, 0, 0, 0)", "transparent"), s
    clear = page.evaluate("(() => { const s = getComputedStyle(document.querySelector('#clear')); return [s.borderTopWidth, s.backgroundColor, s.textDecorationLine] })()")
    assert clear[0] == "0px" and clear[1] in ("rgba(0, 0, 0, 0)", "transparent") and "underline" in clear[2], clear
    # both sit together at the top of the estimate, above the order summary
    full, clr, glance = page.evaluate("['#full', '#clear', '#glance'].map(s => { const r = document.querySelector(s).getBoundingClientRect(); return r.top + r.height / 2 })")
    assert abs(full - clr) < 8 and full < glance, (full, clr, glance)
    assert not errors, errors
    page.context.close()


ROWS = """() => [...document.querySelectorAll('#lines .ln')].map(l => { const q = l.querySelector('.qty').getBoundingClientRect(), a = l.querySelector('.amt'), r = a.getBoundingClientRect(), i = l.querySelector('input');
  return {amt: a.innerText, oneLine: Math.abs(q.top - r.top) < 14, inputFits: i.scrollWidth <= i.clientWidth, amtFits: a.scrollWidth <= a.clientWidth + 1 && r.right <= l.getBoundingClientRect().right + 0.5} })"""


@pytest.mark.parametrize("width", [360, 390])
@pytest.mark.parametrize("view", ["page", "full"])
def test_r09_quantity_and_total_on_one_line(browser, width, view):
    page, errors = _open(browser, width, 800, True)
    page.evaluate(ORDER)
    if view == "full":
        page.evaluate("openEst()")
    rows = page.evaluate(ROWS)
    assert len(rows) == 8 and all(r["oneLine"] for r in rows), rows
    # and not by a hair: at least 8 px to spare, so small differences in
    # how a phone draws text do not push the total onto the next line
    spare = page.evaluate("Math.min(...[...document.querySelectorAll('#lines .ln')].map(l => l.getBoundingClientRect().width - l.querySelector('.qty').getBoundingClientRect().width - l.querySelector('.amt').getBoundingClientRect().width - parseFloat(getComputedStyle(l).columnGap)))")
    assert spare >= 8, spare
    assert all(r["inputFits"] and r["amtFits"] for r in rows), rows
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    # Very large amounts: allowed onto their own line, never cut off
    page.evaluate(HUGE)
    rows = page.evaluate(ROWS)
    assert any(r["amt"] == money(350_000_000) for r in rows), rows
    assert all(r["inputFits"] and r["amtFits"] for r in rows), rows
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not errors, errors
    page.context.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_r10_subtotal_strips(browser, scheme):
    page, errors = _open(browser, 390, 844, True, scheme)
    page.evaluate(ORDER)
    fill = page.evaluate("getComputedStyle(document.querySelector('#glance .tiles div')).backgroundColor")
    strips = page.evaluate("[...document.querySelectorAll('#lines .est')].map(e => getComputedStyle(e).backgroundColor)")
    # cement, single pieces, by the ton, iron rods (combined), binding wire
    assert len(strips) == 5 and all(s == fill for s in strips), strips
    labels = page.evaluate("[...document.querySelectorAll('#lines .est span')].map(e => e.innerText)")
    assert labels == ["Cement subtotal", "Single pieces subtotal", "By the ton subtotal",
                      "Iron rods subtotal", "Binding wire subtotal"], labels
    assert min(page.evaluate(CONTRAST, "#lines .est span, #lines .est b")) >= 4.5
    assert _px(page, "#lines .est b", "fontSize") > _px(page, "#lines .est span", "fontSize")
    assert not errors, errors
    page.context.close()


def test_r11_whatsapp_screen_and_pdf_agree(browser):
    page, errors = _open(browser, 1280, 900)
    page.evaluate(ORDER)
    msg = page.evaluate("decodeURIComponent(document.querySelector('#send').href.split('text=')[1])")
    assert msg.startswith("Hello The Cement People,\n\nI'd like to enquire about the following estimate. "
                          "Please confirm product availability and delivery cost.\n\n*Estimate TCP-")
    items = re.findall(r"^\d+\. .+\n   ([\d,.]+) × GH₵([\d,]+\.\d\d) = GH₵([\d,]+\.\d\d)$", msg, re.M)
    assert len(items) == 8
    for q, price, amount in items:
        assert abs(float(q.replace(",", "")) * float(price.replace(",", "")) - float(amount.replace(",", ""))) < 0.005
    assert sum(float(a.replace(",", "")) for _, _, a in items) == ORDER_TOTAL
    assert f"*Materials total: {money(ORDER_TOTAL)}*" in msg
    assert money(ORDER_TOTAL) in page.inner_text("#tot")
    pdf = print_pdf(page, "final-order.pdf")
    assert f"Total (excl. delivery) {money(ORDER_TOTAL)}" in pdf.text
    assert not errors, errors
    page.context.close()


def test_r12_sticky_parts(browser):
    page, errors = _open(browser, 390, 844, True)
    page.evaluate(ORDER)
    shown = "(() => { const b = document.querySelector('.bar'); return !!b && getComputedStyle(b).display !== 'none' && b.getBoundingClientRect().top < innerHeight })()"
    page.evaluate("window.scrollTo(0, document.querySelector('#list').getBoundingClientRect().top + scrollY - 90)")
    page.wait_for_timeout(300)
    assert page.evaluate(shown)
    page.evaluate("window.scrollTo(0, document.querySelector('#est').getBoundingClientRect().top + scrollY - 80)")
    page.wait_for_timeout(300)
    assert not page.evaluate(shown)
    # no new pinned row in the estimate: the only pinned parts are the
    # section headings (01 Cement, ...), which already were
    pinned = page.evaluate("[...document.querySelectorAll('#est *')].filter(e => ['sticky', 'fixed'].includes(getComputedStyle(e).position)).map(e => e.className)")
    assert all(c == "esh" for c in pinned), pinned
    # scrolling on, View full estimate scrolls away with the estimate
    page.evaluate("window.scrollTo(0, document.querySelector('#tot').getBoundingClientRect().top + scrollY - 200)")
    page.wait_for_timeout(300)
    assert page.locator("#full").bounding_box()["y"] < 0
    assert not errors, errors
    page.context.close()


def test_r13_room_before_about(browser):
    page, errors = _open(browser, 390, 844, True)
    page.evaluate(ORDER)
    gap = page.evaluate("document.querySelector('#about h2').getBoundingClientRect().top - document.querySelector('#est').getBoundingClientRect().bottom")
    assert gap >= 60, gap
    assert not errors, errors
    page.context.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [360, 390, 1280])
def test_r14_product_name_box(browser, scheme, width):
    page, errors = _open(browser, width, 844, width < 900, scheme)
    page.evaluate(ORDER)
    fill = "rgb(41, 45, 43)" if scheme == "light" else "rgb(232, 230, 223)"
    ink = "rgb(255, 255, 255)" if scheme == "light" else "rgb(41, 45, 43)"
    assert page.evaluate("[...document.querySelectorAll('#lines .pn')].every(e => getComputedStyle(e).color === '%s' && +getComputedStyle(e).fontWeight >= 600)" % ink)
    names = page.evaluate("""[...document.querySelectorAll('#lines .ln')].map(l => { const pn = l.querySelector('.pn'), sm = l.querySelector('.nm small'), r = pn.getBoundingClientRect(), q = sm.getBoundingClientRect();
        return {text: pn.innerText, bg: getComputedStyle(pn).backgroundColor, below: q.top >= r.bottom - 1, outside: !pn.contains(sm), narrow: r.width < l.getBoundingClientRect().width * 0.9 || pn.innerText.length > 24, h: r.height} })""")
    assert len(names) == 8, names
    assert all(n["bg"] == fill and n["below"] and n["outside"] and n["narrow"] for n in names), names
    assert all(n["h"] < 30 for n in names), names
    assert min(page.evaluate(CONTRAST, "#lines .ln .pn")) >= 7
    assert not errors, errors
    page.context.close()


BAR = """(() => { const g = document.querySelector('.tot .gt'), s = getComputedStyle(g), k = g.children;
  return {bg: s.backgroundColor, edge: s.borderLeftColor, edgeW: parseFloat(s.borderLeftWidth), color: s.color, label: k[0].innerText, amt: k[1].innerText,
          oneLine: Math.abs(k[0].getBoundingClientRect().top - k[1].getBoundingClientRect().top) < 12,
          spare: g.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight) - k[0].getBoundingClientRect().width - k[1].getBoundingClientRect().width - parseFloat(s.columnGap)} })()"""


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [360, 390, 1280])
def test_r15_total_bar(browser, scheme, width):
    phone = width < 900
    page, errors = _open(browser, width, 844 if width > 360 else 740, phone, scheme)
    page.evaluate(ORDER)
    dark = page.evaluate("getComputedStyle(document.querySelector('#est .dh')).backgroundColor")
    ochre = page.evaluate("getComputedStyle(document.querySelector('.eno')).backgroundColor")
    for view in ("page", "full"):
        if view == "full":
            page.evaluate("openEst()" if phone else "fullEst(true)")
        b = page.evaluate(BAR)
        assert b["bg"] == dark and b["edge"] == ochre and b["edgeW"] >= 3, (view, b)
        assert b["bg"] != ochre and b["label"] == "Total (excl. delivery)" and b["amt"] == money(ORDER_TOTAL), (view, b)
        assert b["oneLine"] and b["spare"] >= 8, (view, b)
        assert min(page.evaluate(CONTRAST, ".tot .gt span")) >= 7
        assert page.evaluate("getComputedStyle(document.querySelector('#send')).backgroundColor") == ochre
        if view == "page" and not phone:
            # desktop panel: no pinned delivery line (Option A, 18 Nov 2026);
            # the Delivery box in the list explains it
            assert page.evaluate("getComputedStyle(document.querySelector('.tot .tdl')).display") == "none"
            assert "To be confirmed" not in page.inner_text("#est .efoot")
            assert "Not included in the total" in page.inner_text("#est .edeliv")
        if view == "full" and not phone:
            assert page.evaluate("getComputedStyle(document.querySelector('.tot .tdl')).display") != "none"
        if view == "page" and phone:
            # delivery: its own line above the bar, still "To be confirmed"
            d = page.evaluate("(() => { const d = document.querySelector('.tot .tdl'), g = document.querySelector('.tot .gt'); return [d.innerText.replace(/\\s+/g, ' '), d.getBoundingClientRect().bottom <= g.getBoundingClientRect().top] })()")
            assert d == ["Delivery To be confirmed", True], d
    if phone:
        share = page.evaluate("document.querySelector('#escroll').clientHeight / innerHeight")
        assert share >= 0.60, share
    assert not errors, errors
    page.context.close()
