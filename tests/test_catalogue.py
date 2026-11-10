"""New in Phase 0: the product catalogue matches the reference copy.

tests/baseline/products.json records all 17 product names, units and prices
as published at commit d3f0e86 (tag v1-single-file). These tests fail if any
of them differs anywhere a customer can see it: the price list, the on-screen
estimate, the WhatsApp message or the PDF quotation.
"""
from conftest import BASELINE, PRODUCTS, add_item, expected_row, money, open_site

TOTAL = sum(p["price"] for p in PRODUCTS)


def test_n01_baseline_file_is_sound():
    assert BASELINE["source_commit"] == "d3f0e86"
    assert len(PRODUCTS) == 17
    assert len({p["id"] for p in PRODUCTS}) == 17, "product ids must be unique"
    assert len({(p["category"], p["name"]) for p in PRODUCTS}) == 17
    for p in PRODUCTS:
        assert p["name"].strip() and p["unit"].strip() and p["category"].strip()
        assert isinstance(p["price"], (int, float)) and p["price"] > 0, p


def test_n02_price_list_matches_baseline(catalogue):
    shown = sorted((r["category"], r["name"], r["unit"], r["price"])
                   for r in catalogue.price_list)
    expected = sorted((p["category"], p["name"], p["unit"], money(p["price"]))
                      for p in PRODUCTS)
    assert shown == expected


def test_n03_estimate_uses_baseline_prices(catalogue):
    assert catalogue.lines == [
        {"name": p["name"], "detail": f"{money(p['price'])} per {p['unit']}", "qty": "1",
         "amount": money(p["price"])}
        for p in PRODUCTS]
    assert catalogue.totals.split("\n")[1] == money(TOTAL)
    assert catalogue.totals.split("\n")[-1] == money(TOTAL)


def test_n04_whatsapp_message_uses_baseline_prices(catalogue):
    items = catalogue.message.split("*Items*\n")[1].split("\n\n")[0]
    assert items == "\n".join(
        f"{i}. {p['name']} ({p['unit']})\n   1 × {money(p['price'])} = {money(p['price'])}"
        for i, p in enumerate(PRODUCTS, start=1))
    assert f"*Materials total: {money(TOTAL)}*" in catalogue.message


def test_n05_pdf_quotation_uses_baseline_prices(catalogue):
    assert catalogue.pdf.rows == [expected_row(i, p, 1)
                                  for i, p in enumerate(PRODUCTS, start=1)]
    assert f"Total before delivery {money(TOTAL)}" in catalogue.pdf.pages[-1]
    assert catalogue.errors == []


def test_n06_print_button_opens_the_print_dialog(browser):
    # The suite prints through the browser's PDF function; this confirms the
    # on-page "Print or save as PDF" button really asks the browser to print.
    page, errors = open_site(
        browser, init_script="window.__prints = 0; window.print = () => { window.__prints++; };")
    add_item(page, PRODUCTS[0], 1)
    page.click("#print")
    assert page.evaluate("window.__prints") == 1
    assert errors == []
    page.context.close()

