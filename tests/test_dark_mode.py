"""
Dark mode (17 Nov 2026)
=======================

  K01  light mode is the default, even when the phone or computer is set to
       dark (Daniel and ChatGPT, 17 Nov 2026: dark mode is an option)
  K02  the moon/sun button switches mode and the choice is remembered after
       reloading the page (on this device)
  K03  dark mode shows the logos with the white wordmark, on phones and computers
  K04  text in dark mode is easy to read: main text, secondary text, prices,
       ochre buttons (contrast checked against WCAG AA, 4.5:1)
  K05  the PDF quotation is the same in dark mode: white paper, dark text
  K06  phones: "Dark mode" is in the ☰ menu with an on/off switch
"""
import pytest

from conftest import SITE_URL, print_pdf, settle


def _open(browser, scheme, width=1280, height=900, mobile=False, context=None):
    """Open the site; scheme "dark" means the customer has switched dark mode on."""
    context = context or browser.new_context(viewport={"width": width, "height": height}, color_scheme=scheme.replace("-device", ""),
                                             is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    if scheme == "dark":
        page.add_init_script("try { if (!sessionStorage.getItem('k')) { localStorage.setItem('tcp-theme', 'dark'); sessionStorage.setItem('k', 1); } } catch (e) {}")
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(SITE_URL, wait_until="load")
    page.wait_for_selector("#list .row")
    settle(page)
    if not page.evaluate("!!document.getElementById('tcp-data')"):
        pytest.skip("dark mode is on the Astro site only")
    return page, errors


theme = lambda page: page.evaluate("document.documentElement.dataset.theme")
bg = lambda page, sel: page.evaluate(f"getComputedStyle(document.querySelector('{sel}')).backgroundColor")


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_k01_light_by_default_whatever_the_device_setting(browser, scheme):
    page, errors = _open(browser, scheme + "-device")
    assert theme(page) == "light"
    assert bg(page, "header") == "rgb(255, 255, 255)"
    assert page.get_attribute("#theme", "aria-pressed") == "false"
    assert not errors, errors
    page.context.close()


def test_k02_button_switches_and_remembers(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme="light")
    page, errors = _open(browser, "light", context=context)
    page.click("#theme")
    assert theme(page) == "dark" and page.get_attribute("#theme", "aria-pressed") == "true"
    page.reload(wait_until="load")
    assert theme(page) == "dark", "the choice should be remembered"
    page.click("#theme")
    page.reload(wait_until="load")
    assert theme(page) == "light"
    assert not errors, errors
    context.close()


@pytest.mark.parametrize("width,mobile,logo", [(1280, False, "primary"), (390, True, "horizontal")])
def test_k03_white_wordmark_logo_in_dark_mode(browser, width, mobile, logo):
    page, errors = _open(browser, "dark", width, 844, mobile)
    shown = page.evaluate("""() => [...document.querySelectorAll('header .brand img')]
        .filter(i => i.getBoundingClientRect().width > 0).map(i => i.currentSrc)""")
    assert len(shown) == 1 and shown[0].endswith(f"/brand/tcp-logo-{logo}-on-dark.svg"), shown
    page.context.close()


def _contrast_script():
    return """sels => { const rgb = c => c.match(/[\\d.]+/g).slice(0, 3).map(Number);
        const lum = c => { const [r, g, b] = rgb(c).map(v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; });
            return .2126 * r + .7152 * g + .0722 * b; };
        const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + .05) / (y + .05); };
        const backOf = e => { for (; e; e = e.parentElement) { const c = getComputedStyle(e).backgroundColor;
            if (!/rgba\\(.*, 0\\)$/.test(c) && c !== 'transparent') return c; } return getComputedStyle(document.body).backgroundColor; };
        return sels.map(s => { const e = document.querySelector(s); return [s, +ratio(getComputedStyle(e).color, backOf(e)).toFixed(1)]; }); }"""


def test_k04_dark_mode_text_is_readable(browser):
    page, errors = _open(browser, "dark")
    page.evaluate("() => { qty.c1 = 3; qty.j3 = 1.5; renderList(); renderEst(); }")
    checks = page.evaluate(_contrast_script(), [
        "h1", ".hero p", "nav a", "#list .row .nm", "#list .row .nm small", "#list .row .pr",
        ".ctas .cta", ".ctas .enq-btn", ".dh b", ".dm", "#glance h3", ".esh .enm span", ".ln .amt",
        "#tot .gt", "#send", ".fine", "#about p", ".foot p", ".tabs button[aria-pressed=false]"])
    low = [c for c in checks if c[1] < 4.5]
    assert not low, f"too little contrast in dark mode: {low}"
    assert not errors, errors
    page.context.close()


def test_k05_pdf_unchanged_in_dark_mode(browser):
    page, errors = _open(browser, "dark")
    page.evaluate("() => { qty.c1 = 3; renderList(); renderEst(); }")
    page.emulate_media(media="print")
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    colours = page.evaluate("""() => [getComputedStyle(document.body).backgroundColor,
        getComputedStyle(document.querySelector('#quote')).color,
        getComputedStyle(document.querySelector('#quote td')).color]""")
    assert colours == ["rgb(255, 255, 255)", "rgb(19, 21, 20)", "rgb(19, 21, 20)"], colours
    page.emulate_media(media="screen")
    pdf = print_pdf(page, "dark-mode-quotation.pdf")
    assert pdf.printed_blocks == ["quote"]
    assert not errors, errors
    page.context.close()


def test_k06_phone_menu_has_the_dark_mode_switch(browser):
    page, errors = _open(browser, "light", 390, 844, True)
    assert page.locator("#theme").is_hidden(), "inside the closed menu"
    page.click("#menu")
    box = page.locator("#theme").bounding_box()
    assert page.locator("#theme").is_visible() and box["width"] > 300, box
    assert page.inner_text("#theme").strip() == "Dark mode"
    page.click("#theme")
    assert theme(page) == "dark"
    assert page.evaluate("document.documentElement.scrollWidth") == 390
    assert not errors, errors
    page.context.close()


# ---- K07 -------------------------------------------------------------------
# Dark mode is built in visible layers (revised 17 Nov 2026 for readability):
# page < surfaces (header, price list, estimate) < fills (stepper buttons,
# summary tiles, section headings); boxes you type in have a border that
# stands out at least 3:1 (WCAG 1.4.11), on phones and computers.
@pytest.mark.parametrize("width,mobile", [(390, True), (1280, False)])
def test_k07_dark_mode_has_clear_layers(browser, width, mobile):
    page, errors = _open(browser, "dark", width, 844, mobile)
    page.evaluate("() => { qty.c1 = 3; qty.j3 = 1.5; renderList(); renderEst(); }")
    r = page.evaluate("""() => { const rgb = c => c.match(/[\\d.]+/g).slice(0, 3).map(Number);
        const lum = c => { const [r, g, b] = rgb(c).map(v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; });
            return .2126 * r + .7152 * g + .0722 * b; };
        const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return +((x + .05) / (y + .05)).toFixed(2); };
        const cs = s => getComputedStyle(document.querySelector(s));
        const page = cs('body').backgroundColor, surface = cs('#catalog').backgroundColor;
        return {pageVsSurface: ratio(page, surface), surfaceVsHeader: ratio(surface, cs('header').backgroundColor),
                surfaceVsFill: ratio(surface, cs('#est .step button').backgroundColor),
                searchBorder: ratio(cs('#q').borderTopColor, surface),
                stepperBorder: ratio(cs('#est .step').borderTopColor, cs('#est .esb').backgroundColor),
                locBorder: ratio(cs('#loc').borderTopColor, cs('.edeliv').backgroundColor),
                addBorder: ratio(cs('#list .add').borderTopColor, surface)}; }""")
    assert r["pageVsSurface"] >= 1.25, r
    assert r["surfaceVsHeader"] == 1, r
    assert r["surfaceVsFill"] >= 1.2, r
    for k in ("searchBorder", "stepperBorder", "addBorder"):
        assert r[k] >= 3, f"{k}: {r}"
    assert r["locBorder"] >= 2.4, r
    assert not errors, errors
    page.context.close()
