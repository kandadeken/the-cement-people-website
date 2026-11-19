"""
PDF refinements (Daniel and ChatGPT, 19 Nov 2026)
=================================================

  P01  category headings without "01 ·" numbers; products numbered 1, 2,
       3... straight through, the same as the screen and WhatsApp
  P02  an empty drop-off location reads "To be agreed"; a given one is shown
  P03  product numbers in charcoal semibold, product names in semibold
       ("per 50 kg bag" stays regular), the Delivery line in semibold
  P04  totals and page counts unchanged (small: 1 page, large: 2 pages)
  P05  every product row, and only product rows, carry data-row="item"
"""
import json
import re
from pathlib import Path

import pytest

from conftest import SITE_URL, money, print_pdf, settle

SMALL = {"c2": 3, "c3": 3, "c4": 3, "i2": 5, "i3": 5, "i5": 5, "j3": 2, "i8": 6}
PRODUCTS = {p["id"]: p for p in json.loads((Path(__file__).parent.parent / "web/src/data/products.json").read_text())}
LARGE = {k: (2.5 if p["unit"] == "ton" else 120 if p["category"] == "Cement" else 6 if p["category"] == "Binding Wire" else 24)
         for k, p in PRODUCTS.items()}


def _open(browser, order):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(SITE_URL, wait_until="load")
    page.wait_for_selector("#list .row")
    settle(page)
    if not page.evaluate("!!document.getElementById('tcp-data')"):
        context.close()
        pytest.skip("Astro site only")
    page.evaluate("q => { for (const k in q) qty[k] = q[k]; renderList(); renderEst(); }", order)
    return page, errors


def test_p01_one_numbering_system(browser):
    page, errors = _open(browser, SMALL)
    pdf = print_pdf(page, "p01.pdf")
    text = " ".join(pdf.text.split())
    assert not re.search(r"\b0\d · ", text), text[:800]
    heads = page.evaluate("[...document.querySelectorAll('#quote tr.q-sec td')].map(t => t.firstChild.textContent.trim())")
    assert heads == ["Cement", "Iron rods", "Binding wire"], heads
    nums = page.evaluate("[...document.querySelectorAll('#quote tr[data-row=item] td.n')].map(t => t.textContent)")
    assert nums == [str(i) for i in range(1, 9)], nums
    # the same numbers and names as the screen
    screen = page.evaluate("[...document.querySelectorAll('#lines .ln')].map(l => l.querySelector('.lno').textContent + ' ' + l.querySelector('.pn').textContent)")
    pdfrows = page.evaluate("[...document.querySelectorAll('#quote tr[data-row=item]')].map(r => r.cells[0].textContent + ' ' + r.cells[1].firstChild.textContent.trim())")
    assert screen == pdfrows, (screen, pdfrows)
    assert not errors, errors
    page.context.close()


def test_p02_drop_off_location_wording(browser):
    page, errors = _open(browser, SMALL)
    pdf = print_pdf(page, "p02-empty.pdf")
    assert "To be agreed" in pdf.text and "Not provided" not in pdf.text
    page.fill("#loc", "Opposite the Total filling station, Kasoa")
    pdf = print_pdf(page, "p02-given.pdf")
    assert "Opposite the Total filling station, Kasoa" in " ".join(pdf.text.split())
    assert "To be agreed" not in pdf.text
    assert not errors, errors
    page.context.close()


def test_p03_weights(browser):
    page, errors = _open(browser, SMALL)
    page.emulate_media(media="print")
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    w = page.evaluate("""(() => { const r = document.querySelector('#quote tr[data-row=item]'), s = e => getComputedStyle(e);
        return {num: [s(r.cells[0]).fontWeight, s(r.cells[0]).color], name: s(r.cells[1]).fontWeight, unit: s(r.cells[1].querySelector('small')).fontWeight,
                qty: s(r.cells[2]).fontWeight, del: s(document.querySelector('#quote .q-sum .q-del')).fontWeight} })()""")
    assert w == {"num": ["600", "rgb(19, 21, 20)"], "name": "600", "unit": "400", "qty": "400", "del": "600"}, w
    assert not errors, errors
    page.context.close()


def _total(order):
    """The order's total from the product list, so a price change needs no edit here."""
    return sum(q * PRODUCTS[k]["price"] for k, q in order.items())


@pytest.mark.parametrize("order,pages,total", [(SMALL, 1, _total(SMALL)), (LARGE, 2, _total(LARGE))], ids=["small", "large"])
def test_p04_totals_and_pages_unchanged(browser, order, pages, total):
    page, errors = _open(browser, order)
    pdf = print_pdf(page, f"p04-{pages}.pdf")
    assert f"Total (excl. delivery) {money(total)}" in " ".join(pdf.text.split())
    assert pdf.count == pages
    assert not errors, errors
    page.context.close()


def test_p05_product_rows_marked(browser):
    page, errors = _open(browser, LARGE)
    page.emulate_media(media="print")
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    marked = page.evaluate("document.querySelectorAll('#quote tr[data-row=item]').length")
    assert marked == len(LARGE) == page.evaluate("document.querySelectorAll('#quote td.n:not(th)').length")
    assert page.evaluate("[...document.querySelectorAll('#quote tr[data-row=item]')].every(r => !r.className)")
    assert not errors, errors
    page.context.close()
