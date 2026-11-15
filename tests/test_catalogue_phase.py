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
  C07  "Clear estimate" can be undone for 10 seconds: items, drop-off
       location, reference and date all come back

Only for the Astro build (the old single-file page is the rollback copy and
is not changed), so they are skipped when the single file is under test.
"""
import pytest

from conftest import SITE_URL, open_site

# Which slide is lined up with the list's left edge, which tab is pressed,
# and the heading of the slide that is showing.
STATE = """() => { const L = document.querySelector('#list'), l = L.getBoundingClientRect();
  const i = [...L.children].findIndex(s => Math.abs(s.getBoundingClientRect().left - l.left) < 2);
  return {shown: i, heading: i < 0 ? null : L.children[i].querySelector('h3').innerText.trim(),
          pressed: [...document.querySelectorAll('#tabs button')].findIndex(b => b.getAttribute('aria-pressed') === 'true'),
          names: [...document.querySelectorAll('#tabs button')].map(b => b.innerText.trim())}; }"""


def _settled(page, i):
    """Wait (up to 3 s) for the list to finish sliding to slide number i."""
    page.wait_for_function(
        "i => { const L = document.querySelector('#list'); return Math.abs(L.scrollLeft - i * L.clientWidth) < 2; }",
        arg=i, timeout=3000)


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
    page.locator("#tabs button", has_text=name).click()
    page.wait_for_timeout(900)  # let the list finish sliding across


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
    assert others == [[False, True], [False, True]], f"cement and single-piece rows must keep their prices: {others}"
    page.fill("#q", "ton")
    page.wait_for_timeout(150)
    found = page.evaluate("[...document.querySelectorAll('#list .row .pr')].map(e => e.innerText.trim())")
    assert found and all(p == "GH₵7,000.00" for p in found), f"search results should show each price: {found}"
    assert not errors, errors
    page.context.close()


def _qty(page, pid):
    v = page.evaluate(f"document.querySelector('#est input[data-qty=\"{pid}\"]')?.value ?? null")
    return None if v is None else float(v)


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
    assert page.evaluate("[...document.querySelectorAll('#quote tbody td')].map(t => t.innerText.trim())")[2] == "2.5"
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
    page.wait_for_timeout(400)
    assert page.locator("#bar").is_visible(), "bar should show while the estimate is off screen"
    page.evaluate("document.querySelector('#est').scrollIntoView({block: 'end', behavior: 'instant'})")
    page.wait_for_timeout(500)
    assert page.evaluate("getComputedStyle(document.querySelector('#bar')).visibility") == "hidden"
    fine = page.locator("#est .fine").bounding_box()
    assert fine["y"] + fine["height"] <= 844, "the estimate's last lines should be fully visible"
    page.evaluate("scrollTo({top: 0, behavior: 'instant'})")
    page.wait_for_timeout(500)
    assert page.evaluate("getComputedStyle(document.querySelector('#bar')).visibility") == "visible"
    assert not errors, errors
    page.context.close()


def test_c07_undo_clear_estimate(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.clock.install()
    page.goto(SITE_URL, wait_until="load")
    page.wait_for_selector("#list .row")
    _skip_unless_astro(page)
    page.click('#list [data-inc="c1"]')
    page.click('#list [data-inc="c1"]')
    page.fill("#loc", "Kasoa, near Goil")
    ref, date = page.inner_text("#ref"), page.inner_text("#date")
    page.click("#clear")
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
    page.clock.fast_forward(10_001)
    page.wait_for_timeout(50)
    assert page.locator("#undo").count() == 0
    assert "empty" in page.inner_text("#lines")
    # ...or as soon as something new is added.
    page.click('#list [data-inc="c2"]')
    page.click("#clear")
    page.click('#list [data-inc="c3"]')
    page.click('#est [data-dec="c3"]')
    assert page.locator("#undo").count() == 0
    context.close()
