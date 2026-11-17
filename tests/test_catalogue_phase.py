"""
Catalogue and estimate phase checks (added 14 Nov 2026).

  C01  on a computer, clicking each category tab with the mouse brings that
       category into view (the list slides across, as it always has)
  C02  the same with the keyboard: Tab to a category tab, press Enter/Space
  C03  the price list keeps its sideways slide on computers and phones, so
       trackpad and touch swiping between categories keep working
       (Daniel, 15 Nov 2026: the original behaviour is the one to keep)
  C04  rods by the ton: the shared price (GH₵7,000.00 per ton) is shown once
       under the heading, not on every row; other tabs and search results
       still show a price on every row
  C05  rods by the ton go up and down in half tons (Add starts at 1 ton,
       smallest amount 0.5); the estimate, WhatsApp message and printed
       quotation use the half-ton amounts; cement still counts whole bags
  C06  on a phone the black estimate bar slides away while the estimate
       panel is on screen, and comes back when you scroll up
  C08  estimate totals: label left, amount right, with a clear gap, and the
       amount never wraps, on narrow phones even with a large total
  C09  the "tons" word stays on the same line as its quantity box, in the
       price list and in the estimate, at every width
  C10  around the 900 px change-over (860 to 940 px) nothing sticks out past
       the edge of the screen, with items in the estimate
  C11  single rods show "pc"/"pcs" beside the quantity box in the price list
       and in the estimate; the printed quotation names the unit on every
       line ("per 30 ft rod", "per ton"); cement and binding wire show no
       unit word
  C07  "Clear estimate" can be undone for 10 seconds: items, drop-off
       location, reference and date all come back

Only for the Astro build (the old single-file page is the rollback copy and
is not changed), so they are skipped when the single file is under test.
"""
import pytest

from playwright.sync_api import expect

from conftest import SITE_URL, goto_tab, open_site, settle, wait_bar, wait_rows, wait_slide

# Which slide is lined up with the list's left edge, which tab is pressed,
# and the heading of the slide that is showing.
STATE = """() => { const L = document.querySelector('#list'), l = L.getBoundingClientRect();
  const i = [...L.children].findIndex(s => Math.abs(s.getBoundingClientRect().left - l.left) < 2);
  return {shown: i, heading: i < 0 ? null : L.children[i].querySelector('h3').innerText.trim(),
          pressed: [...document.querySelectorAll('#tabs button')].findIndex(b => b.getAttribute('aria-pressed') === 'true'),
          names: [...document.querySelectorAll('#tabs button')].map(b => b.dataset.cat)}; }"""


def _settled(page, i):
    """Wait for the list to finish sliding to slide number i."""
    wait_slide(page, i, must=False)  # the assertions that follow report a failure


def _skip_unless_astro(page):
    if not page.evaluate("!!document.getElementById('tcp-data')"):
        page.context.close()
        pytest.skip("applies to the Astro build only")


@pytest.mark.parametrize("width", [1024, 1440])
def test_c01_desktop_mouse_click_switches_tab(browser, width):
    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    page.goto(SITE_URL, wait_until="load")
    page.wait_for_selector("#list .row")
    settle(page)
    _skip_unless_astro(page)
    names = page.evaluate(STATE)["names"]
    for i in [1, 2, 0, 2, 1]:
        page.locator("#tabs button").nth(i).click()  # a real mouse click
        _settled(page, i)
        s = page.evaluate(STATE)
        assert s["pressed"] == i and s["shown"] == i, f"clicked '{names[i]}' at {width} px, got {s}"
        assert s["heading"] == names[i], s
    context.close()


def test_c02_desktop_keyboard_switches_tab(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.goto(SITE_URL, wait_until="load")
    page.wait_for_selector("#list .row")
    settle(page)
    _skip_unless_astro(page)
    for i in [2, 1, 0]:
        page.locator("#tabs button").nth(i).focus()
        page.keyboard.press("Enter")
        _settled(page, i)
        s = page.evaluate(STATE)
        assert s["pressed"] == i and s["shown"] == i, f"Enter on tab {i}: {s}"
    page.locator("#tabs button").nth(1).focus()
    page.keyboard.press("Space")
    _settled(page, 1)
    assert page.evaluate(STATE)["shown"] == 1
    context.close()


def test_c03_list_keeps_its_sideways_slide(browser):
    for mobile in (False, True):
        page, _ = open_site(browser, mobile=mobile)
        _skip_unless_astro(page)
        css = page.evaluate("(() => { const s = getComputedStyle(document.querySelector('#list')); return [s.overflowX, s.scrollSnapType]; })()")
        assert css[0] == "auto" and css[1].startswith("x"), f"list should slide and snap (mobile={mobile}): {css}"
        page.context.close()


def _goto_tab(page, name):
    goto_tab(page, text=name)


def test_c04_per_ton_price_shown_once(browser):
    page, errors = open_site(browser)
    _skip_unless_astro(page)
    per_ton = page.evaluate("""() => { const sec = [...document.querySelectorAll('#list .slide')]
        .find(s => s.querySelector('h3').innerText.includes('Per Ton'));
        return {once: sec.querySelector('.cat-price')?.innerText.trim(),
                rowPrices: [...sec.querySelectorAll('.row .pr')].map(e => e.getBoundingClientRect().width > 2 ? e.innerText.trim() : ''),
                hiddenPrices: [...sec.querySelectorAll('.row .pr .vh')].map(e => e.textContent.trim())}; }""")
    assert per_ton["once"] == "GH₵7,000.00 per ton, all sizes", per_ton
    assert per_ton["rowPrices"] and all(p == "" for p in per_ton["rowPrices"]), f"rows should not show the price: {per_ton}"
    # ...but each row keeps it, hidden from view, for screen readers and search engines.
    assert per_ton["hiddenPrices"] == ["GH₵7,000.00"] * 6, per_ton
    others = page.evaluate("""() => [...document.querySelectorAll('#list .slide')]
        .filter(s => !s.querySelector('h3').innerText.includes('Per Ton'))
        .map(s => [!!s.querySelector('.cat-price'), [...s.querySelectorAll('.row .pr')].every(e => e.innerText.trim())])""")
    # Cement, single pieces and (since 17 Nov 2026) binding wire's own tab.
    assert others == [[False, True], [False, True], [False, True]], f"cement and single-piece rows must keep their prices: {others}"
    page.fill("#q", "ton")
    wait_rows(page, 6)  # the six rods sold by the ton
    found = page.evaluate("[...document.querySelectorAll('#list .row .pr')].map(e => e.innerText.trim())")
    assert found and all(p == "GH₵7,000.00" for p in found), f"search results should show each price: {found}"
    assert not errors, errors
    page.context.close()


def _qty(page, pid):
    v = page.evaluate(f"document.querySelector('#est input[data-qty=\"{pid}\"]')?.value ?? null")
    return None if v is None else float(v.replace(",", ""))  # boxes show 1,200 since 17 Nov 2026


def test_c05_half_ton_steps(browser):
    page, errors = open_site(browser)
    _skip_unless_astro(page)
    _goto_tab(page, "Per Ton")
    page.click('#list [data-inc="j3"]')            # Add: 1 ton
    assert _qty(page, "j3") == 1
    page.click('#list [data-inc="j3"]')            # + : 1.5
    assert _qty(page, "j3") == 1.5
    assert page.inner_text('#est .ln .amt') == "GH₵10,500.00"
    assert page.inner_text('#est .ln .u') == "tons"
    page.click('#est [data-dec="j3"]')
    page.click('#est [data-dec="j3"]')             # down to 0.5
    assert _qty(page, "j3") == 0.5
    assert page.inner_text('#tot .gt').endswith("GH₵3,500.00")
    for typed, expect in (("2.3", 2.5), ("0.2", 0.5), ("3", 3)):
        box = page.locator('#est input[data-qty="j3"]')
        box.fill(typed)
        box.press("Tab")
        assert _qty(page, "j3") == expect, f"typed {typed}"
    page.click('#est [data-dec="j3"]')             # 2.5
    msg = page.evaluate("decodeURIComponent(document.querySelector('#send').href.split('text=')[1])")
    assert "2.5 × GH₵7,000.00 = GH₵17,500.00" in msg, msg
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    # The quotation now has section rows ("01 · Iron rods"); read the item row.
    assert page.evaluate("[...document.querySelectorAll('#quote tbody tr')].filter(r => r.cells.length === 5)[0].cells[2].innerText.trim()") == "2.5"
    for _ in range(5):
        page.click('#est [data-dec="j3"]')
        if _qty(page, "j3") is None:
            break
    assert _qty(page, "j3") is None, "taking away the last half ton removes the line"
    # Cement still counts whole bags, typed amounts cut to whole numbers as before.
    _goto_tab(page, "Cement")
    page.click('#list [data-inc="c1"]')
    page.click('#list [data-inc="c1"]')
    assert _qty(page, "c1") == 2
    box = page.locator('#est input[data-qty="c1"]')
    box.fill("2.7")
    box.press("Tab")
    assert _qty(page, "c1") == 2
    assert not errors, errors
    page.context.close()


def test_c06_phone_bar_steps_aside_for_the_estimate(browser):
    page, errors = open_site(browser, mobile=True)
    _skip_unless_astro(page)
    page.click('#list [data-inc="c1"]')
    page.evaluate("scrollTo({top: 0, behavior: 'instant'})")
    assert wait_bar(page, True, must=False), "bar should show while the estimate is off screen"
    page.evaluate("document.querySelector('#est').scrollIntoView({block: 'end', behavior: 'instant'})")
    assert wait_bar(page, False, must=False), "bar should step aside while the estimate is on screen"
    assert page.evaluate("getComputedStyle(document.querySelector('#bar')).visibility") == "hidden"
    # The point of the fix: nothing covers the estimate's last lines. Bring
    # the very bottom of the small print exactly to the bottom edge of the
    # screen (where the bar used to sit), then check what is on top there.
    # (Measured from the element itself, not from "scroll into view", which
    # can land a pixel or two differently from one machine to another.)
    page.evaluate("""() => { const r = document.querySelector('#est .fine').getBoundingClientRect();
        scrollBy({top: r.bottom - innerHeight, behavior: 'instant'}); }""")
    page.wait_for_function("Math.abs(document.querySelector('#est .fine').getBoundingClientRect().bottom - innerHeight) <= 1", timeout=8000)
    assert wait_bar(page, False, must=False), "bar should stay away while the estimate's last lines are on screen"
    on_top = page.evaluate("""() => { const r = document.querySelector('#est .fine').getBoundingClientRect();
        const e = document.elementFromPoint(r.left + r.width / 2, r.bottom - 6);
        return e ? (e.closest('#bar') ? 'bar' : e.closest('#est') ? 'estimate' : e.tagName) : 'nothing'; }""")
    assert on_top == "estimate", f"the estimate's last line is covered by: {on_top}"
    page.evaluate("scrollTo({top: 0, behavior: 'instant'})")
    assert wait_bar(page, True, must=False), "bar should come back when scrolling up to the price list"
    assert not errors, errors
    page.context.close()


def test_c07_undo_clear_estimate(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.clock.install()
    page.goto(SITE_URL, wait_until="load")
    page.wait_for_selector("#list .row")
    settle(page)
    _skip_unless_astro(page)
    page.click('#list [data-inc="c1"]')
    page.click('#list [data-inc="c1"]')
    page.fill("#loc", "Kasoa, near Goil")
    ref, date = page.inner_text("#ref"), page.inner_text("#date")
    # Since 17 Nov 2026 Clear asks first; "Keep estimate" changes nothing.
    page.click("#clear")
    assert page.locator("#clearAsk").is_visible()
    page.click("#clearNo")
    assert page.locator("#clearAsk").is_hidden() and _qty(page, "c1") == 2
    page.click("#clear")
    page.click("#clearYes")
    assert page.locator("#est .ln").count() == 0
    assert page.inner_text("#ref") != ref
    assert page.locator("#undo").is_visible()
    page.click("#undo")
    assert _qty(page, "c1") == 2
    assert page.input_value("#loc") == "Kasoa, near Goil"
    assert page.inner_text("#ref") == ref and page.inner_text("#date") == date
    msg = page.evaluate("decodeURIComponent(document.querySelector('#send').href.split('text=')[1])")
    assert ref.replace("Ref ", "") in msg and "Kasoa, near Goil" in msg
    # The Undo goes away after 10 seconds...
    page.click("#clear")
    page.click("#clearYes")
    page.clock.fast_forward(10_001)
    expect(page.locator("#undo")).to_have_count(0)
    assert "empty" in page.inner_text("#lines")
    # ...or as soon as something new is added.
    page.click('#list [data-inc="c2"]')
    page.click("#clear")
    page.click("#clearYes")
    page.click('#list [data-inc="c3"]')
    page.click('#est [data-dec="c3"]')
    assert page.locator("#undo").count() == 0
    context.close()


def _fresh(browser, width, height=800, touch=False):
    context = browser.new_context(viewport={"width": width, "height": height}, is_mobile=touch, has_touch=touch)
    page = context.new_page()
    page.goto(SITE_URL, wait_until="load")
    page.wait_for_selector("#list .row")
    settle(page)
    return page


def _add_rods(page):
    """3 single rods and 2.5 tons, giving a long total (GH₵17,806.00)."""
    _goto_tab(page, "Single Piece")
    for _ in range(3):
        page.click('#list [data-inc="i1"]')
    _goto_tab(page, "Per Ton")
    for _ in range(4):
        page.click('#list [data-inc="j3"]')


@pytest.mark.parametrize("width", [320, 360, 375, 414])
def test_c08_estimate_totals_have_room(browser, width):
    page = _fresh(browser, width, touch=True)
    _skip_unless_astro(page)
    _add_rods(page)
    rows = page.evaluate("""() => [...document.querySelectorAll('#tot div')].map(d => {
        const [a, b] = d.children, ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect(), rd = d.getBoundingClientRect();
        // right edge of the label's actual text (a wrapped label is narrower than its box)
        const r = document.createRange(); r.selectNodeContents(a);
        const textRight = Math.max(...[...r.getClientRects()].map(c => c.right));
        // sameLine: on narrow phones the total's amount may move under its label (17 Nov 2026)
        return {label: a.innerText, amount: b.innerText, gap: Math.round(rb.left - textRight), sameLine: rb.top < ra.bottom - 2,
                amountLines: Math.round(rb.height / parseFloat(getComputedStyle(b).lineHeight)),
                flushRight: Math.abs(rb.right - (rd.right - parseFloat(getComputedStyle(d).paddingRight))) < 1.5}; })""")
    assert rows[-1]["label"] == "Total (excl. delivery)" and rows[-1]["amount"] == "GH₵17,806.00", rows
    for r in rows:
        assert r["gap"] >= 12 or not r["sameLine"], f"{width} px: label and amount too close: {r}"
        assert r["amountLines"] == 1 and r["flushRight"], f"{width} px: amount should be one line, right-aligned: {r}"
    page.context.close()


@pytest.mark.parametrize("width", [320, 375, 560, 900, 1024, 1440])
def test_c09_tons_label_stays_with_its_stepper(browser, width):
    page = _fresh(browser, width, touch=width < 600)
    _skip_unless_astro(page)
    _add_rods(page)
    pairs = page.evaluate("""() => [...document.querySelectorAll('.qty')].filter(q => q.querySelector('.u')).map(q => {
        const s = q.querySelector('.step').getBoundingClientRect(), u = q.querySelector('.u').getBoundingClientRect();
        return {where: q.closest('#est') ? 'estimate' : 'list', text: q.querySelector('.u').innerText,
                gap: Math.round(u.left - s.right), sameLine: u.top >= s.top - 1 && u.bottom <= s.bottom + 1,
                // must not run into the line amount beside it (estimate)
                clear: (() => { const m = q.parentElement.querySelector('.amt'); if (!m) return true;
                    const r = m.getBoundingClientRect(); return u.right <= r.left - 4 || r.top >= u.bottom - 1; })()}; })""")
    assert sorted((p["where"], p["text"]) for p in pairs) == [
        ("estimate", "pcs"), ("estimate", "tons"), ("list", "pcs"), ("list", "tons")], pairs
    for p in pairs:
        assert p["sameLine"] and 0 <= p["gap"] <= 12, f"{width} px: {p}"
        assert p["clear"], f"{width} px: unit word runs into the amount: {p}"
    page.context.close()


@pytest.mark.parametrize("width", [860, 880, 899, 900, 910, 940])
def test_c10_nothing_sticks_out_around_900px(browser, width):
    page = _fresh(browser, width)
    _skip_unless_astro(page)
    _add_rods(page)
    page.fill("#loc", "Krispol City Road, Kasoa, near the Goil filling station")
    for tab in ("Cement", "Single Piece", "Per Ton"):
        _goto_tab(page, tab)
        w = page.evaluate("[innerWidth, document.documentElement.scrollWidth]")
        assert w[1] <= w[0], f"{width} px, {tab}: page is wider than the screen: {w}"
        out = page.evaluate("""() => { const L = document.querySelector('#list').getBoundingClientRect();
            const vis = e => { const r = e.getBoundingClientRect(); return r.width && r.left >= L.left - 1 && r.left < L.right; };
            const bad = [];
            for (const e of document.querySelectorAll('#list .row > *, #list .cat-price, #est .ln > *, #tot div > *, .ctas a, .hin > *'))
                if (vis(e) || !e.closest('#list')) { const r = e.getBoundingClientRect(), p = e.parentElement.getBoundingClientRect();
                    if (r.width && r.right > p.right + 1.5) bad.push([e.className || e.tagName, Math.round(r.right - p.right)]); }
            return bad; }""")
        assert not out, f"{width} px, {tab}: these stick out of their box: {out}"
    page.context.close()


@pytest.mark.parametrize("mobile", [True, False], ids=["phone", "computer"])
def test_c11_single_rods_show_pcs(browser, mobile):
    page, errors = open_site(browser, mobile=mobile)
    _skip_unless_astro(page)
    unit = lambda where, pid: page.evaluate(
        f"document.querySelector('{where} input[data-qty=\"{pid}\"]')?.closest('.qty').querySelector('.u')?.innerText ?? null")
    _goto_tab(page, "Single Piece")
    page.click('#list [data-inc="i1"]')
    assert unit("#list", "i1") == "pc" and unit("#est", "i1") == "pc", "one rod reads '1 pc'"
    page.click('#list [data-inc="i1"]')
    assert unit("#list", "i1") == "pcs" and unit("#est", "i1") == "pcs"
    # In the list the word sits on the stepper's line, right beside it.
    box = page.evaluate("""() => { const q = document.querySelector('#list input[data-qty="i1"]').closest('.qty');
        const s = q.querySelector('.step').getBoundingClientRect(), u = q.querySelector('.u').getBoundingClientRect();
        return {gap: Math.round(u.left - s.right), sameLine: u.top >= s.top - 1 && u.bottom <= s.bottom + 1,
                fits: u.right <= document.documentElement.clientWidth}; }""")
    assert box["sameLine"] and 0 <= box["gap"] <= 12 and box["fits"], box
    # Since 17 Nov 2026 binding wire (its own tab now) reads "roll" and
    # cement reads "bag", so every quantity says what it counts.
    _goto_tab(page, "Binding Wire")
    page.click('#list [data-inc="i8"]')
    assert unit("#list", "i8") == "roll" and unit("#est", "i8") == "roll"
    _goto_tab(page, "Cement")
    page.click('#list [data-inc="c1"]')
    assert unit("#est", "c1") == "bag"
    _goto_tab(page, "Per Ton")
    page.click('#list [data-inc="j3"]')
    # Printed quotation: every line names its unit under the description.
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    lines = page.evaluate("[...document.querySelectorAll('#quote tbody tr')].filter(r => r.cells.length === 5 && !r.classList.length).map(r => [r.children[1].firstChild.textContent.trim(), r.children[1].querySelector('small').textContent.trim(), r.children[2].textContent.trim()])")
    assert ["Iron rod 16 mm", "per 30 ft rod", "2"] in lines, lines
    assert ["Iron rod 12 mm", "per ton", "1"] in lines, lines
    assert not errors, errors
    page.context.close()
