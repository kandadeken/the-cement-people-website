"""
Design-system checks (added Nov 2026, design-system phase).

These check the agreed look in the Design-System Proposal, so later changes
can't quietly undo it:

  D01  the typeface comes from the website itself: no requests to Google
       Fonts or any other outside server
  D02  everything a customer taps (buttons, tabs, inputs, menu and nav links,
       quantity buttons and the number box between them) is at least 44 px tall, on a phone and on a computer
  D03  the quantity stepper is only as wide as its buttons and box (before,
       it stretched into an empty white strip on phones)
  D04  one content width: the header, the price list and the About section
       start at the same left edge on a wide screen
  D05  the hero keeps a clear main button: "View products" is TCP yellow,
       "Call us" is white with a dark border, so they never look equal
  D06  the category cards under the hero are gone (the tabs do that job)
  D07  from 900 px up, the two hero buttons sit side by side

They only apply to the Astro build (the old single-file index.html keeps its
old look), so they are skipped when the single file is under test.
"""
import pytest

from conftest import SITE_URL, open_site, settle

TAP = 44  # minimum height in CSS pixels for anything a customer taps


def _is_astro(page):
    return page.evaluate("!!document.getElementById('tcp-data')")


def _skip_unless_astro(page):
    if not _is_astro(page):
        page.context.close()
        pytest.skip("design-system checks apply to the Astro build only")


# Returns [selector, text, height] for every visible tappable control
# smaller than the minimum.
SMALL_CONTROLS = """min => {
  const sel = ['.ctas a', '.add', '.step button', '.step input', '.tabs button', 'input[type=search]',
               '#loc', '.acts .cta', '.ghost', 'header .wa', '#menu', 'nav a', '.bar button'];
  const out = [];
  for (const s of sel) for (const e of document.querySelectorAll(s)) {
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height || getComputedStyle(e).visibility === 'hidden') continue;
    if (r.height < min - 0.5) out.push([s, e.innerText.trim().slice(0, 30), Math.round(r.height)]);
  }
  return out; }"""


def test_d01_no_outside_font_requests(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    outside, fonts = [], []
    page.on("request", lambda r: (fonts.append(r.url) if r.resource_type == "font" else None,
                                  outside.append(r.url) if "fonts.g" in r.url else None))
    page.goto(SITE_URL, wait_until="networkidle")
    _skip_unless_astro(page)
    page.evaluate("document.fonts.ready")
    assert not outside, f"the page still asks Google Fonts for files: {outside}"
    assert fonts and all("/fonts/montserrat-" in u for u in fonts), fonts
    loaded = page.evaluate("[...document.fonts].filter(f => f.status === 'loaded').map(f => f.family + ' ' + f.weight)")
    assert any("Montserrat" in f for f in loaded), f"Montserrat did not load: {loaded}"
    context.close()


@pytest.mark.parametrize("mobile", [True, False], ids=["phone", "computer"])
def test_d02_tap_targets_at_least_44px(browser, mobile):
    page, errors = open_site(browser, mobile=mobile)
    _skip_unless_astro(page)
    page.click('#list [data-inc="c1"]')  # makes a stepper, the estimate buttons and the bar appear
    if mobile:
        page.click("#menu")  # opens the menu so its links are measured too
    small = page.evaluate(SMALL_CONTROLS, TAP)
    assert not small, f"controls under {TAP} px tall: {small}"
    assert not errors, errors
    page.context.close()


@pytest.mark.parametrize("mobile", [True, False], ids=["phone", "computer"])
def test_d03_stepper_is_only_as_wide_as_its_contents(browser, mobile):
    page, _ = open_site(browser, mobile=mobile)
    _skip_unless_astro(page)
    page.click('#list [data-inc="c1"]')
    widths = page.evaluate("""() => [...document.querySelectorAll('.step')].map(s => {
        const inner = [...s.children].reduce((w, c) => w + c.getBoundingClientRect().width, 0);
        return [Math.round(s.getBoundingClientRect().width), Math.round(inner)]; })""")
    assert widths, "no quantity stepper found after tapping Add"
    for outer, inner in widths:
        assert outer <= inner + 4, f"stepper is {outer} px wide but its contents are {inner} px"
    page.context.close()


def test_d04_one_content_width(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.goto(SITE_URL, wait_until="load")
    settle(page)
    _skip_unless_astro(page)
    lefts = page.evaluate("""() => {
        const x = s => { const e = document.querySelector(s); if (!e) return null;
            return Math.round(e.getBoundingClientRect().left + parseFloat(getComputedStyle(e).paddingLeft)); };
        return {header: x('.hin'), prices: x('main'), about: x('#about .wrap')}; }""")
    assert None not in lefts.values(), lefts
    assert max(lefts.values()) - min(lefts.values()) <= 2, f"sections start at different edges: {lefts}"
    context.close()


def test_d05_hero_buttons_keep_their_hierarchy(browser):
    page, _ = open_site(browser)
    _skip_unless_astro(page)
    style = page.evaluate("""() => { const s = e => getComputedStyle(document.querySelector(e));
        return {main: s('.ctas .cta').backgroundColor, second: s('.ctas .btn2').backgroundColor,
                border: s('.ctas .btn2').borderTopColor}; }""")
    # Brand identity V1.1 (17 Nov 2026): interface ochre #FF9802, charcoal #131514;
    # the second button is "Enquire" (WhatsApp or call) instead of "Call us".
    assert style["main"] == "rgb(255, 152, 2)", f"'View products' should be TCP ochre: {style}"
    assert style["second"] == "rgb(255, 255, 255)", f"'Enquire' should be white: {style}"
    assert style["border"] == "rgb(19, 21, 20)", f"'Enquire' should have a dark border: {style}"
    page.context.close()


def test_d06_category_cards_removed(browser):
    page, _ = open_site(browser)
    _skip_unless_astro(page)
    assert page.locator("#cats, .cats").count() == 0, "the category cards under the hero are back"
    page.context.close()


@pytest.mark.parametrize("width", [900, 960, 1024, 1440])
def test_d07_hero_buttons_side_by_side_on_wide_screens(browser, width):
    # From 900 px up the hero is photo left, text right; "View products" and
    # "Call us" should sit on one line, not stacked (ChatGPT review, 14 Nov).
    context = browser.new_context(viewport={"width": width, "height": 800})
    page = context.new_page()
    page.goto(SITE_URL, wait_until="load")
    settle(page)
    _skip_unless_astro(page)
    # "Enquire" is a button (it opens WhatsApp / call); its menu links are hidden.
    tops = page.evaluate("[...document.querySelectorAll('.ctas > a, .ctas .enq-btn')].map(a => Math.round(a.getBoundingClientRect().top))")
    assert len(tops) == 2 and tops[0] == tops[1], f"hero buttons are stacked at {width} px: {tops}"
    # And with room to spare: text is drawn a pixel or two wider on some
    # computers (GitHub's test machines), so 1 px of slack is not enough.
    slack = page.evaluate("""() => { const c = document.querySelector('.ctas'), k = [...c.children];
        return c.clientWidth - k.reduce((a, e) => a + e.getBoundingClientRect().width, 0)
               - (parseFloat(getComputedStyle(c).columnGap) || 0) * (k.length - 1); }""")
    assert slack >= 12, f"only {slack:.0f} px to spare beside the hero buttons at {width} px"
    context.close()
