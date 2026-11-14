"""
Parity checks added in Phase 3 (moving the live site to Astro).

Before the switch-over, the Astro build in web/ must do everything the live
single-file site does. Most of that was already covered by the other test
files; these checks cover the gaps found when the migration plan was written
(14 Nov 2026):

  T01  the sticky estimate bar on phones: hidden when empty, shows the running
       total once something is added, opens the full-screen estimate, and
       "Back to products" closes it
  T02  sliding the price list sideways on a phone switches the selected tab
  T03  search words customers use: "tonne", "ton", "iron rods", a rod size and
       "binding" each find exactly the right products
  T04  header, hero and About text and links are unchanged; Contact and footer
       match the approved text for each version (tests/baseline/page-sections.json)
  T05  the four favicon files exist, are linked from the page and are the same
       files in both versions

Like every file in tests/, these run against the live index.html by default
and against the Astro build when TCP_SITE_URL points at it.
"""
import json
import urllib.request

import pytest

from conftest import ROOT, SITE_URL, open_site

SECTIONS = json.loads((ROOT / "tests" / "baseline" / "page-sections.json").read_text(encoding="utf-8"))

# Reads the visible text (spaces tidied) and every link of one page section.
READ_SECTION = """sel => { const e = document.querySelector(sel);
    return {text: e.innerText.replace(/\\s+/g, ' ').trim(),
            links: [...e.querySelectorAll('a')].map(a => ({
                text: a.innerText.replace(/\\s+/g, ' ').trim(), href: a.getAttribute('href')}))}; }"""


def _is_astro(page):
    # Only the Astro build carries its products in a <script id="tcp-data"> block.
    return page.evaluate("!!document.getElementById('tcp-data')")


def test_t01_phone_estimate_bar_shows_total_and_opens_estimate(browser):
    page, errors = open_site(browser, mobile=True)
    bar = page.locator("#bar")
    assert not bar.is_visible(), "the estimate bar should be hidden while the estimate is empty"
    page.click('#list [data-inc="c1"]')  # Supacem 32.5R, GH₵75.00
    assert bar.is_visible(), "the estimate bar should appear once something is added"
    assert page.inner_text("#barTxt") == "Estimate: GH₵75.00 (1 item)"
    page.click('#list [data-inc="c1"]')
    assert page.inner_text("#barTxt") == "Estimate: GH₵150.00 (1 item)"
    # The bar stays at the bottom of the screen while scrolling.
    page.mouse.wheel(0, 1500)
    page.wait_for_timeout(300)
    box = bar.bounding_box()
    assert abs(box["y"] + box["height"] - 844) <= 1, f"bar is not docked at the bottom: {box}"
    # "View estimate" opens the full-screen estimate; "Back to products" closes it.
    page.click("#barBtn")
    assert "open" in page.get_attribute("#est", "class")
    est = page.locator("#est").bounding_box()
    assert est["width"] == 390 and est["height"] >= 844, f"estimate is not full screen: {est}"
    page.click("#dclose")
    assert "open" not in page.get_attribute("#est", "class")
    # Removing the last item hides the bar again.
    page.click('#list [data-dec="c1"]')
    page.click('#list [data-dec="c1"]')
    assert not bar.is_visible(), "the estimate bar should hide when the estimate is empty again"
    assert not errors, errors
    page.context.close()


def test_t02_sliding_the_price_list_switches_the_tab(browser):
    # A finger swipe scrolls the list sideways one slide; the page then marks
    # that slide's tab as selected. Here the same sideways scroll is made
    # directly, which runs the same code as a swipe.
    page, errors = open_site(browser, mobile=True)
    tabs = page.evaluate("[...document.querySelectorAll('#tabs button')].map(b => b.dataset.cat)")
    assert len(tabs) >= 2
    for i, cat in enumerate(tabs):
        page.evaluate("i => { const L = document.querySelector('#list'); L.scrollTo({left: i * L.clientWidth}); }", i)
        page.wait_for_timeout(500)
        selected = page.evaluate(
            "[...document.querySelectorAll('#tabs button')].filter(b => b.getAttribute('aria-pressed') === 'true').map(b => b.dataset.cat)")
        assert selected == [cat], f"after sliding to slide {i + 1}, selected tab is {selected}, expected {cat}"
    assert page.evaluate("document.documentElement.scrollWidth") == 390, "page scrolls sideways"
    assert not errors, errors
    page.context.close()


@pytest.mark.parametrize("words,expected", [
    ("tonne", ["j1", "j2", "j3", "j4", "j5", "j6"]),
    ("ton", ["j1", "j2", "j3", "j4", "j5", "j6"]),
    ("iron rods", ["i1", "i2", "i3", "i4", "i5", "i6", "i8", "j1", "j2", "j3", "j4", "j5", "j6"]),
    ("12 mm", ["i3", "j3"]),
    ("binding", ["i8"]),
])
def test_t03_search_words_find_the_right_products(browser, words, expected):
    # "iron rods" also finds binding wire: it is listed in the rods tab.
    page, errors = open_site(browser)
    page.fill("#q", words)
    found = page.evaluate("[...document.querySelectorAll('#list [data-inc]')].map(b => b.dataset.inc)")
    assert found == expected, f"search {words!r} found {found}"
    assert not errors, errors
    page.context.close()


def test_t04_page_sections_text_and_links_unchanged(browser):
    page, _ = open_site(browser)
    for name, sel in [("header", "header"), ("hero", ".hero .htx"), ("about", "#about")]:
        assert page.evaluate(READ_SECTION, sel) == SECTIONS["shared"][name], f"{name} text or links changed"
    version = "astro" if _is_astro(page) else "single_file"
    for name, sel in [("contact", "#contact"), ("footer", "footer")]:
        assert page.evaluate(READ_SECTION, sel) == SECTIONS[version][name], f"{name} text or links changed ({version})"
    page.context.close()


FAVICONS = {"/favicon.ico": "icon", "/favicon.svg": "icon",
            "/favicon-96x96.png": "icon", "/apple-touch-icon.png": "apple-touch-icon"}


def test_t05_favicons_are_linked_and_identical(browser):
    page, _ = open_site(browser)
    linked = page.evaluate("[...document.querySelectorAll('link[rel=icon], link[rel=apple-touch-icon]')]"
                           ".map(l => [l.getAttribute('href'), l.getAttribute('rel')])")
    assert sorted(map(tuple, linked)) == sorted(FAVICONS.items()), f"favicon links: {linked}"
    page.context.close()
    for path in FAVICONS:
        reference = (ROOT / path.lstrip("/")).read_bytes()
        assert reference, f"{path} is empty"
        # The Astro copy must be the same file, byte for byte.
        assert (ROOT / "web" / "public" / path.lstrip("/")).read_bytes() == reference, f"{path} differs in web/public"
        if SITE_URL.startswith("http"):
            with urllib.request.urlopen(SITE_URL.rstrip("/") + path) as r:
                assert r.read() == reference, f"{path} served by the site differs from the repository copy"
