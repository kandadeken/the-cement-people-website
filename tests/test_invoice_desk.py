"""
Invoice Desk (/invoice-desk/), 20 Nov 2026 - "option A" agreed with Daniel
and ChatGPT: a private page that turns the estimate a customer sends on
WhatsApp into a branded PDF invoice. No database; nothing leaves the
browser; prices from the same products.json as the public site.

  D01  kept out of search engines: noindex, not in the sitemap, no link to
       it from the public site, robots.txt does not name it
  D02  locked until the passphrase is entered; a wrong one is refused
       (the real passphrase is never in the repository: set TCP_DESK_PASS
       to also test unlocking with it)
  D03  a real estimate from the home page, pasted from WhatsApp, fills in
       every item, the estimate reference and the drop-off location
  D04  reading copes with what WhatsApp and phones do to the text: * marks
       dropped, decimal commas, dotted thousands, a product that is no
       longer in the price list, a price that changed since the estimate
  D05  the rules: no invoice until delivery is agreed; delivery fee, free
       delivery and pickup; agreed prices; the invoice number and revisions
  D06  the PDF: A4, titled INVOICE (never a tax invoice, no VAT lines),
       with the customer, every item and the right total
  D07  WhatsApp: Ghana numbers turned into wa.me form; the message carries
       the invoice number and total
  D08  fits a 360 px and a 390 px phone without sideways scrolling
"""
import os
import re
import urllib.parse

import pytest

from conftest import PRODUCTS, SITE_URL, money, print_pdf, settle, whatsapp_message

ASTRO = SITE_URL.startswith("http")
DESK = urllib.parse.urljoin(SITE_URL, "invoice-desk/")
pytestmark = pytest.mark.skipif(not ASTRO, reason="the Invoice Desk is part of the Astro build only")
BY_ID = {p["id"]: p for p in PRODUCTS}


def _desk(browser, width=390, unlock=True):
    ctx = browser.new_context(viewport={"width": width, "height": 844}, device_scale_factor=2,
                              is_mobile=True, has_touch=True, locale="en-US")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    if unlock:
        # Opened in this tab, as after a correct passphrase (see D02).
        page.add_init_script("try{sessionStorage.setItem('tcp-desk-open','1')}catch(e){}")
    page.goto(DESK, wait_until="load")
    return page, errors


def _read(page, text):
    page.fill("#paste", text)
    page.click("#readBtn")
    page.wait_for_selector("#form:not([hidden])")


def _estimate_message(browser, order, loc=""):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
    page = ctx.new_page()
    page.goto(SITE_URL, wait_until="load")
    page.wait_for_selector("#list .row")
    settle(page)
    page.evaluate("o => { for (const k in o) qty[k] = o[k]; renderList(); renderEst(); }", order)
    if loc:
        page.fill("#loc", loc)
    msg = whatsapp_message(page)
    ctx.close()
    return msg


ORDER = {"c2": 9, "i3": 24, "j3": 2.5, "i8": 6}


# ---- D01 --------------------------------------------------------------------
def test_d01_kept_out_of_search_engines(browser):
    page, errors = _desk(browser, unlock=False)
    robots = page.evaluate("[...document.querySelectorAll('meta[name=robots]')].map(m => m.content)")
    assert robots == ["noindex, nofollow"], robots
    assert page.evaluate("!document.querySelector('link[rel=canonical], script[type=\"application/ld+json\"]')")
    for path in ("sitemap.xml", "robots.txt"):
        text = page.evaluate("u => fetch(u).then(r => r.text())", urllib.parse.urljoin(SITE_URL, path))
        assert "invoice-desk" not in text, f"{path} names the desk"
    home = page.evaluate("u => fetch(u).then(r => r.text())", SITE_URL)
    assert "invoice-desk" not in home, "the public home page links to the desk"
    assert not errors, errors
    page.context.close()


# ---- D02 --------------------------------------------------------------------
def test_d02_locked_until_the_passphrase(browser):
    page, errors = _desk(browser, unlock=False)
    assert page.is_visible("#gate") and page.is_hidden("#tool")
    page.fill("#pass", "not-the-passphrase-1")
    page.click("#gateForm button")
    page.wait_for_function("document.querySelector('#gateMsg').textContent.includes('not right')", timeout=20000)
    assert page.is_hidden("#tool")
    # The passphrase itself is not in the page, only its slow fingerprint.
    script = page.evaluate("fetch(document.querySelector('script[src*=\"invoice-desk.js\"]').src).then(r => r.text())")
    assert "ROUNDS=310000" in script and re.search(r'HASH="[0-9a-f]{64}"', script)
    real = os.environ.get("TCP_DESK_PASS")
    if real:
        page.fill("#pass", real)
        page.click("#gateForm button")
        page.wait_for_selector("#tool:not([hidden])", timeout=20000)
    assert not errors, errors
    page.context.close()


# ---- D03 --------------------------------------------------------------------
def test_d03_reads_a_real_estimate_from_the_home_page(browser):
    msg = _estimate_message(browser, ORDER, loc="Buduburam, near the school")
    ref = re.search(r"TCP-\d{6}-[A-Z0-9]{6}", msg).group(0)
    page, errors = _desk(browser)
    _read(page, msg)
    s = page.evaluate("TCPDesk.state()")
    assert s["ref"] == ref and s["code"] == ref[-6:]
    assert s["site"] == "Buduburam, near the school"
    got = [(l["pid"], l["qty"], l["price"]) for l in s["items"]]
    assert got == [(k, q, round(BY_ID[k]["price"] * 100)) for k, q in ORDER.items()], got
    assert f"Read 4 items from estimate {ref}" in page.inner_text("#readMsg")
    materials = sum(BY_ID[k]["price"] * q for k, q in ORDER.items())
    assert page.inner_text("#sMat") == money(materials)
    assert not errors, errors
    page.context.close()


# ---- D04 --------------------------------------------------------------------
def test_d04_reading_copes_with_whatsapp_and_phones(browser):
    page, errors = _desk(browser)
    c2 = BY_ID["c2"]["price"]
    text = ("Estimate TCP-261120-ABCDE2 (20 Nov 2026)\n"
            "Drop-off location: Kasoa Old Barrier\n\nItems\n"
            "1. Supacem 42.5R (50 kg bag)\n   10 × GH₵100.00 = GH₵1.000,00\n"
            "2. Iron rod 12 mm (ton)\n   2,5 × GH₵6.800,00 = GH₵17.000,00\n"
            "3. Roofing sheet (bundle)\n   3 × GH₵450.00 = GH₵1,350.00\n")
    r = page.evaluate("t => TCPDesk.parseEstimate(t)", text)
    assert r["ref"] == "TCP-261120-ABCDE2" and r["loc"] == "Kasoa Old Barrier"
    a, b, c = r["items"]
    # A price that moved since the estimate: today's price is used, the old one kept to show.
    assert a["pid"] == "c2" and a["qty"] == 10 and a["price"] == round(c2 * 100) and a["quoted"] == 10000
    assert b["pid"] == "j3" and b["qty"] == 2.5
    # Not in today's list: kept with the estimate's own price, and flagged.
    assert c["pid"] is None and c["name"] == "Roofing sheet" and c["price"] == 45000
    for s, want in [("1,392.00", 1392), ("1.392,00", 1392), ("2,5", 2.5), ("50,000", 50000), ("GH₵98.00", 98)]:
        assert page.evaluate("s => TCPDesk.num(s)", s) == want, s
    _read(page, text)
    assert "not in today's price list" in page.inner_text("#items").lower()
    assert "The estimate said" in page.inner_text("#items")
    assert "changed since the estimate" in page.inner_text("#readMsg")
    nothing = page.evaluate("TCPDesk.parseEstimate('Hello, how much is cement?')")
    assert nothing["items"] == []
    assert not errors, errors
    page.context.close()


# ---- D05 --------------------------------------------------------------------
def test_d05_rules_totals_and_invoice_number(browser):
    msg = _estimate_message(browser, {"c2": 9, "i3": 24})
    ref = re.search(r"TCP-\d{6}-([A-Z0-9]{6})", msg).group(1)
    page, errors = _desk(browser)
    _read(page, msg)
    page.fill("#cName", "Kwame Mensah")
    page.fill("#cPhone", "024 123 4567")
    page.fill("#iDate", "2026-11-20")
    assert page.is_disabled("#pdfBtn") and "Agree the delivery" in page.inner_text("#sMsg")
    mat = 9 * BY_ID["c2"]["price"] + 24 * BY_ID["i3"]["price"]
    page.check('input[name="dl"][value="fee"]')
    assert page.is_disabled("#pdfBtn") and "delivery fee" in page.inner_text("#sMsg")
    page.fill("#fee", "350")
    assert page.inner_text("#sTot") == money(mat + 350) and not page.is_disabled("#pdfBtn")
    page.check('input[name="dl"][value="pickup"]')
    assert page.inner_text("#sTot") == money(mat)
    page.check('input[name="dl"][value="free"]')
    assert page.inner_text("#sTot") == money(mat)
    # An agreed price on the first line changes this invoice only.
    page.fill('.dk-line[data-i="0"] input[data-f="price"]', "95")
    assert page.inner_text("#sTot") == money(mat - 9 * (BY_ID["c2"]["price"] - 95))
    assert "Agreed price" in page.inner_text('.dk-line[data-i="0"]')
    assert page.inner_text("#sNo") == f"TCP-INV-261120-{ref}"
    page.select_option("#iRev", "2")
    assert page.inner_text("#sNo") == f"TCP-INV-261120-{ref}-2"
    page.fill("#cName", "")
    assert page.is_disabled("#pdfBtn") and "customer's name" in page.inner_text("#sMsg")
    assert not errors, errors
    page.context.close()


# ---- D06 --------------------------------------------------------------------
def test_d06_the_invoice_pdf(browser):
    msg = _estimate_message(browser, ORDER, loc="Buduburam")
    page, errors = _desk(browser, width=1280)
    _read(page, msg)
    page.fill("#cName", "Kwame Mensah")
    page.fill("#cPhone", "0241234567")
    page.check('input[name="dl"][value="fee"]')
    page.fill("#fee", "250")
    page.fill("#iPay", "MTN MoMo 055 000 0000 (The Cement People)")
    no = page.inner_text("#sNo")
    pdf = print_pdf(page, "invoice-desk-d06.pdf")
    assert pdf.printed_blocks == ["quote"], pdf.printed_blocks
    assert all(abs(w - 595.28) < 1 and abs(h - 841.89) < 1 for w, h in pdf.sizes), pdf.sizes
    text = pdf.text
    assert "INVOICE" in text and no in text and "Kwame Mensah" in text and "0241234567" in text
    for k in ORDER:
        assert BY_ID[k]["name"] in text, BY_ID[k]["name"]
    total = sum(BY_ID[k]["price"] * q for k, q in ORDER.items()) + 250
    assert f"Total due {money(total)}" in text, text[-400:]
    assert "Delivery fee" in text and "MTN MoMo 055 000 0000" in text
    assert not re.search(r"\bVAT\b|\btax invoice\b|\bNHIL\b|GETFund", text, re.I), "the invoice must not look like a tax invoice"
    assert not errors, errors
    page.context.close()


# ---- D07 --------------------------------------------------------------------
def test_d07_whatsapp(browser):
    page, errors = _desk(browser)
    for typed, want in [("024 123 4567", "233241234567"), ("+233 24 123 4567", "233241234567"),
                        ("00233241234567", "233241234567"), ("241234567", "233241234567"), ("0241", "")]:
        assert page.evaluate("p => TCPDesk.waNumber(p)", typed) == want, typed
    msg = _estimate_message(browser, {"c2": 2})
    _read(page, msg)
    page.fill("#cName", "Ama Owusu")
    page.fill("#cPhone", "020 555 1234")
    page.check('input[name="dl"][value="pickup"]')
    href = page.get_attribute("#waBtn", "href")
    assert href.startswith("https://wa.me/233205551234?text=")
    text = urllib.parse.unquote(href.split("text=", 1)[1])
    assert text.startswith("Hello Ama,") and page.inner_text("#sNo") in text
    assert f"*Total due: {money(2 * BY_ID['c2']['price'])}*" in text
    assert not errors, errors
    page.context.close()


# ---- D08 --------------------------------------------------------------------
@pytest.mark.parametrize("width", [360, 390])
def test_d08_fits_a_phone(browser, width):
    page, errors = _desk(browser, width=width)
    _read(page, _estimate_message(browser, ORDER))
    widest = page.evaluate("document.documentElement.scrollWidth")
    assert widest <= width, f"{width} px phone: page is {widest} px wide"
    assert not errors, errors
    page.context.close()
