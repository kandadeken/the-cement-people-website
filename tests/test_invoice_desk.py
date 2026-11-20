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
  D06  the PDF (drawn in the page with jsPDF so it can be shared as a
       file): A4, titled INVOICE (never a tax invoice, no VAT lines), with
       the customer, every item and the right total; "Download PDF" names
       the file after the invoice
  D07  sharing: one short line goes with the PDF (20 Nov 2026, Daniel: not
       every item in the message); Ghana numbers turned into wa.me form for
       browsers that cannot share files
  D08  fits a 360 px and a 390 px phone without sideways scrolling
  D09  a long invoice runs onto more pages with the table heading repeated,
       a "Continued" line and page numbers, and the totals on the last page
  D10  a draft (with its payments) comes back after the page is reloaded
       (20 Nov 2026 fix: the desk used to reopen empty)

Payments and receipts (20 Nov 2026, Daniel: a short receipt that reads like
the website's "Your order at a glance"; part payments; Mobile Money, cash,
bank transfer):
  R01  the rules: no payment before the invoice is complete; amount, method
       and date needed; never more than the balance; "Whole balance";
       paid in full closes the form; only the latest payment can be removed
  R02  receipt numbers lead back to the invoice; the order at a glance uses
       the same counts and words as the website's own glance panel
  R03  the receipt PDF: A5, titled RECEIPT, the amount received, how it was
       paid, the glance tiles, no item prices, and the balance left, with
       "PAID IN FULL" on the last one
  R04  sharing a receipt: the PDF and one short line; "Download" names the
       file after the receipt
  R05  fits a 360 px phone with payments recorded
"""
import base64
import io
import os
import re
import urllib.parse

import pytest
from pypdf import PdfReader

from conftest import PRODUCTS, SITE_URL, money, settle, tidy_pdf_text, whatsapp_message

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


def _pdf(page):
    """The invoice PDF exactly as Share and Download make it."""
    b64 = page.evaluate("async () => (await TCPDesk.makePdf(TCPDesk.state())).output('datauristring').split(',')[1]")
    reader = PdfReader(io.BytesIO(base64.b64decode(b64)))
    pages = [tidy_pdf_text(p.extract_text()) for p in reader.pages]
    return pages, [(float(p.mediabox.width), float(p.mediabox.height)) for p in reader.pages]


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
    page.fill("#iPay", "MTN MoMo 055 000 0000\nName: The Cement People")
    no = page.inner_text("#sNo")
    pages, sizes = _pdf(page)
    assert len(pages) == 1 and all(abs(w - 595.28) < 1 and abs(h - 841.89) < 1 for w, h in sizes), sizes
    text = pages[0]
    assert "INVOICE" in text and no in text and "Kwame Mensah" in text and "0241234567" in text
    for k, q in ORDER.items():
        p = BY_ID[k]
        assert p["name"] in text and money(p["price"] * q) in text, p["name"]
    total = sum(BY_ID[k]["price"] * q for k, q in ORDER.items()) + 250
    assert f"Total due {money(total)}" in text, text[-400:]
    assert "Delivery fee" in text and "MTN MoMo 055 000 0000" in text and "Name: The Cement People" in text
    assert "Page 1 of 1" in text and "GH₵" in text
    assert not re.search(r"\bVAT\b|\btax invoice\b|\bNHIL\b|GETFund", text, re.I), "the invoice must not look like a tax invoice"
    with page.expect_download() as dl:
        page.click("#pdfBtn")
    assert dl.value.suggested_filename == f"TCP Invoice {no}.pdf"
    assert not errors, errors
    page.context.close()


# ---- D07 --------------------------------------------------------------------
def test_d07_sharing(browser):
    page, errors = _desk(browser)
    for typed, want in [("024 123 4567", "233241234567"), ("+233 24 123 4567", "233241234567"),
                        ("00233241234567", "233241234567"), ("241234567", "233241234567"), ("0241", "")]:
        assert page.evaluate("p => TCPDesk.waNumber(p)", typed) == want, typed
    _read(page, _estimate_message(browser, {"c2": 2}))
    page.fill("#cName", "Ama Owusu")
    page.fill("#cPhone", "020 555 1234")
    assert page.is_disabled("#shareBtn")
    page.check('input[name="dl"][value="pickup"]')
    assert not page.is_disabled("#shareBtn")
    no = page.inner_text("#sNo")
    line = page.evaluate("TCPDesk.waText(TCPDesk.state())")
    assert line == f"Hello Ama, here is your invoice {no} from The Cement People.", line
    # What the phone's share menu receives: the PDF file and that one line.
    page.evaluate("""() => { window.__shared = null;
        navigator.canShare = d => !!(d && d.files && d.files.length);
        navigator.share = async d => { window.__shared = {names: d.files.map(f => f.name), types: d.files.map(f => f.type), text: d.text}; }; }""")
    page.click("#shareBtn")
    page.wait_for_function("window.__shared")
    shared = page.evaluate("window.__shared")
    assert shared == {"names": [f"TCP Invoice {no}.pdf"], "types": ["application/pdf"], "text": line}, shared
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


# ---- D09 --------------------------------------------------------------------
def test_d09_long_invoice_runs_onto_more_pages(browser):
    page, errors = _desk(browser, width=1280)
    page.click("#blankBtn")
    for i in range(34):
        page.select_option("#addSel", index=i % len(PRODUCTS))
        page.click("#addBtn")
    page.fill("#cName", "Big Order Ltd")
    page.fill("#cPhone", "0201234567")
    page.check('input[name="dl"][value="free"]')
    no = page.inner_text("#sNo")
    pages, _ = _pdf(page)
    assert len(pages) >= 2, len(pages)
    for n, text in enumerate(pages, 1):
        assert f"Page {n} of {len(pages)}" in text and "DESCRIPTION" in text
        if n > 1:
            assert f"Invoice {no}" in text and "Continued" in text
    total = 2 * sum(p["price"] for p in PRODUCTS)
    assert f"Total due {money(total)}" in pages[-1] and "Total due" not in "".join(pages[:-1])
    assert not errors, errors
    page.context.close()


# ---- D10 --------------------------------------------------------------------
def test_d10_draft_comes_back_after_a_reload(browser):
    page, errors = _desk(browser)
    page.on("dialog", lambda d: d.accept())
    _read(page, _estimate_message(browser, {"c2": 4}))
    page.fill("#cName", "Esi Boateng")
    page.fill("#cPhone", "0277000000")
    page.check('input[name="dl"][value="pickup"]')
    page.fill("#pAmt", "100")
    page.check('input[name="pm"][value="cash"]')
    page.click("#payBtn")
    page.reload(wait_until="load")
    page.wait_for_selector("#form:not([hidden])", timeout=5000)
    assert page.input_value("#cName") == "Esi Boateng"
    assert page.evaluate("TCPDesk.state().payments.length") == 1
    assert page.inner_text("#pPaid") == money(100)
    assert not errors, errors
    page.context.close()


# ---- Payments and receipts --------------------------------------------------
def _ready_invoice(browser, order, width=390, fee=None):
    """The desk with a complete invoice for this order (pickup, or a delivery fee)."""
    page, errors = _desk(browser, width=width)
    page.on("dialog", lambda d: d.accept())
    msg = _estimate_message(browser, order)
    _read(page, msg)
    page.fill("#cName", "Kofi Mensah")
    page.fill("#cPhone", "024 123 4567")
    page.fill("#iDate", "2026-11-20")
    if fee:
        page.check('input[name="dl"][value="fee"]')
        page.fill("#fee", str(fee))
    else:
        page.check('input[name="dl"][value="pickup"]')
    return page, errors, msg


def _pay(page, amount, method, date="2026-11-21", net=None, ref=""):
    page.fill("#pAmt", amount)
    page.fill("#pDate", date)
    page.check(f'input[name="pm"][value="{method}"]')
    if net:
        page.select_option("#pNet", net)
    if ref:
        page.fill("#pRef", ref)
    page.click("#payBtn")


def _receipt(page, i):
    b64 = page.evaluate("async i => (await TCPDesk.makeReceipt(TCPDesk.state(), i)).output('datauristring').split(',')[1]", i)
    reader = PdfReader(io.BytesIO(base64.b64decode(b64)))
    return ([tidy_pdf_text(p.extract_text()) for p in reader.pages],
            [(float(p.mediabox.width), float(p.mediabox.height)) for p in reader.pages])


def test_r01_payment_rules(browser):
    page, errors = _desk(browser)
    page.on("dialog", lambda d: d.accept())
    _read(page, _estimate_message(browser, {"c2": 10}))
    # Not before the invoice is complete.
    assert page.is_disabled("#payBtn") and "Finish the invoice" in page.inner_text("#pMsg")
    page.fill("#cName", "Kofi Mensah")
    page.fill("#cPhone", "024 123 4567")
    page.check('input[name="dl"][value="fee"]')
    page.fill("#fee", "20")
    total = 10 * BY_ID["c2"]["price"] + 20
    assert not page.is_disabled("#payBtn")
    assert page.inner_text("#pTot") == money(total) and page.inner_text("#pBal") == money(total)
    # Each of these is refused, with a reason.
    page.fill("#pAmt", "")
    page.click("#payBtn")
    assert "amount received" in page.inner_text("#pMsg")
    page.fill("#pAmt", "100")
    page.click("#payBtn")
    assert "how the customer paid" in page.inner_text("#pMsg")
    page.check('input[name="pm"][value="cash"]')
    page.fill("#pAmt", str(total + 1))
    page.click("#payBtn")
    assert f"more than the balance of {money(total)}" in page.inner_text("#pMsg")
    assert page.evaluate("TCPDesk.state().payments.length") == 0
    # The network and reference boxes follow the method.
    assert page.is_hidden("#netBox") and page.is_hidden("#refBox")
    page.check('input[name="pm"][value="momo"]')
    assert page.is_visible("#netBox") and page.is_visible("#refBox")
    page.check('input[name="pm"][value="bank"]')
    assert page.is_hidden("#netBox") and "Bank reference" in page.inner_text("#refLbl")
    # A part payment, then the whole balance.
    _pay(page, "500", "momo", net="MTN MoMo", ref="4471829")
    assert page.inner_text("#pPaid") == money(500) and page.inner_text("#pBal") == money(total - 500)
    page.click("#pFull")
    assert page.input_value("#pAmt") == f"{total - 500:.2f}"
    page.check('input[name="pm"][value="cash"]')
    page.click("#payBtn")
    assert page.inner_text("#pBal") == "Paid in full" and page.is_hidden("#payForm")
    # Only the latest payment has a Remove button.
    assert page.locator("[data-rrm]").count() == 1 and page.get_attribute("[data-rrm]", "data-rrm") == "1"
    page.click("[data-rrm]")
    assert page.evaluate("TCPDesk.state().payments.length") == 1 and page.is_visible("#payForm")
    assert not errors, errors
    page.context.close()


def test_r02_receipt_numbers_and_the_glance(browser):
    order = {"c2": 205, "c3": 10, "i3": 85, "i6": 15, "j3": 5.5, "i8": 6}
    # The website's own "Your order at a glance" for this order.
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
    home = ctx.new_page()
    home.goto(SITE_URL, wait_until="load")
    home.wait_for_selector("#list .row")
    home.evaluate("o => { for (const k in o) qty[k] = o[k]; renderList(); renderEst(); }", order)
    site_tiles = [re.sub(r"\s+", " ", t).strip() for t in home.eval_on_selector_all("#glance .tiles > div", "e => e.map(d => d.textContent)")]
    ctx.close()
    assert site_tiles == ["215 bags of cement", "100 individual rods", "5.5 tons of rods", "6 rolls of binding wire"], site_tiles
    page, errors, msg = _ready_invoice(browser, order)
    desk_tiles = [f"{t['n']:,g} {t['label']}" for t in page.evaluate("TCPDesk.glance(TCPDesk.state())")]
    assert desk_tiles == site_tiles, (desk_tiles, site_tiles)
    code = re.search(r"TCP-\d{6}-([A-Z0-9]{6})", msg).group(1)
    _pay(page, "1000", "cash", date="2026-11-21")
    _pay(page, "2000", "bank", date="2026-11-22", ref="GCB-55120")
    nos = [page.evaluate("i => TCPDesk.receiptNo(TCPDesk.state(), i)", i) for i in (0, 1)]
    assert nos == [f"TCP-RCT-261121-{code}-1", f"TCP-RCT-261122-{code}-2"], nos
    assert page.evaluate("TCPDesk.methodText(TCPDesk.state().payments[1])") == "Bank transfer · Ref GCB-55120"
    assert nos[0] in page.inner_text("#pays") and nos[1] in page.inner_text("#pays")
    assert not errors, errors
    page.context.close()


def test_r03_the_receipt_pdf(browser):
    order = {"c2": 20, "i3": 24, "i8": 2}
    page, errors, _ = _ready_invoice(browser, order, width=1280, fee=300)
    total = sum(BY_ID[k]["price"] * q for k, q in order.items()) + 300
    _pay(page, "1500", "momo", net="Telecel Cash", ref="4471829")
    _pay(page, f"{total - 1500:.2f}", "cash")
    inv = page.inner_text("#sNo")
    pages, sizes = _receipt(page, 0)
    assert len(pages) == 1 and abs(sizes[0][0] - 419.53) < 1 and abs(sizes[0][1] - 595.28) < 1, sizes
    text = pages[0]
    no = page.evaluate("TCPDesk.receiptNo(TCPDesk.state(), 0)")
    for want in ("RECEIPT", no, inv, "Kofi Mensah", "024 123 4567", "AMOUNT RECEIVED", money(1500),
                 "Telecel Cash · Ref 4471829", "1 of this order", "YOUR ORDER AT A GLANCE",
                 "20 bags of cement", "24 individual rods", "2 rolls of binding wire",
                 f"Invoice total {money(total)}", f"Balance due {money(total - 1500)}"):
        assert want in text, (want, text)
    # Short: no item list or unit prices; the invoice has those.
    assert money(BY_ID["c2"]["price"]) not in text and BY_ID["c2"]["name"] not in text
    assert "PAID IN FULL" not in text
    last, _ = _receipt(page, 1)
    for want in ("Cash", "2 of this order", f"Paid before (1 payment) {money(1500)}",
                 f"This payment {money(total - 1500)}", "PAID IN FULL"):
        assert want in last[0], (want, last[0])
    assert "Balance due" not in last[0]
    assert not re.search(r"\bVAT\b|\btax invoice\b", text, re.I)
    assert not errors, errors
    page.context.close()


def test_r04_sharing_a_receipt(browser):
    page, errors, _ = _ready_invoice(browser, {"c2": 3})
    _pay(page, "100", "cash")
    no = page.evaluate("TCPDesk.receiptNo(TCPDesk.state(), 0)")
    line = page.evaluate("TCPDesk.receiptText(TCPDesk.state(), 0)")
    assert line == f"Hello Kofi, here is your receipt {no} for {money(100)} from The Cement People. Thank you!", line
    page.evaluate("""() => { window.__shared = null;
        navigator.canShare = d => !!(d && d.files && d.files.length);
        navigator.share = async d => { window.__shared = {names: d.files.map(f => f.name), types: d.files.map(f => f.type), text: d.text}; }; }""")
    page.click("[data-rshare='0']")
    page.wait_for_function("window.__shared")
    assert page.evaluate("window.__shared") == {"names": [f"TCP Receipt {no}.pdf"], "types": ["application/pdf"], "text": line}
    with page.expect_download() as dl:
        page.click("[data-rpdf='0']")
    assert dl.value.suggested_filename == f"TCP Receipt {no}.pdf"
    assert not errors, errors
    page.context.close()


def test_r05_payments_fit_a_phone(browser):
    page, errors, _ = _ready_invoice(browser, ORDER, width=360)
    page.check('input[name="pm"][value="momo"]')
    _pay(page, "250", "momo", net="AT Money", ref="TX-0000000000-LONG-REFERENCE")
    widest = page.evaluate("document.documentElement.scrollWidth")
    assert widest <= 360, f"360 px phone: page is {widest} px wide"
    assert not errors, errors
    page.context.close()
