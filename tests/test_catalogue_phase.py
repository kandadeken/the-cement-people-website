"""
Catalogue and estimate phase checks (added 14 Nov 2026).

  C01  on a computer, clicking each category tab with the mouse shows that
       category straight away (bug: the Iron Rods tabs seemed to do nothing
       on desktop, though they worked on phones)
  C02  the same with the keyboard: Tab to a category tab and press Enter
  C03  on a computer the price list does not swipe or snap; on a phone it
       still does

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
        page.wait_for_timeout(120)  # far less than any smooth scroll would take
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
        page.wait_for_timeout(120)
        s = page.evaluate(STATE)
        assert s["pressed"] == i and s["shown"] == i, f"Enter on tab {i}: {s}"
    page.locator("#tabs button").nth(1).focus()
    page.keyboard.press("Space")
    page.wait_for_timeout(120)
    assert page.evaluate(STATE)["shown"] == 1
    context.close()


def test_c03_swipe_only_on_touch_screens(browser):
    page, _ = open_site(browser)  # computer
    _skip_unless_astro(page)
    css = page.evaluate("(() => { const s = getComputedStyle(document.querySelector('#list')); return [s.overflowX, s.scrollSnapType]; })()")
    assert css[0] == "hidden" and css[1] == "none", f"desktop list should not swipe or snap: {css}"
    page.context.close()
    page, _ = open_site(browser, mobile=True)  # phone
    css = page.evaluate("(() => { const s = getComputedStyle(document.querySelector('#list')); return [s.overflowX, s.scrollSnapType]; })()")
    assert css[0] == "auto" and css[1].startswith("x"), f"phone list should still swipe and snap: {css}"
    page.context.close()
