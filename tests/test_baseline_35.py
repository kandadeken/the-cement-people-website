"""The original 35 quotation checks, one test each, in their original order.

Numbering (b01-b35) matches tests/baseline/ORIGINAL_35_CHECKS.md, which maps
each test to the check it came from and records what was strengthened.
No original check has been removed.
"""
import re

from conftest import (A4_POINTS, BY_ID, LOCATION, PRODUCTS, REF_PATTERN, SYNTHETIC,
                      expected_row, money, squash)

CONTROL_LABELS = ("Send my estimate", "Clear estimate", "Print or save", "Swipe",
                  "Search materials", "View estimate", "Enquire on WhatsApp")


def is_a4(size):
    return abs(size[0] - A4_POINTS[0]) < 1 and abs(size[1] - A4_POINTS[1]) < 1


# ---- Estimate behaviour ---------------------------------------------------
def test_b01_steppers_typed_quantity_and_totals(short):
    assert short.c2_after_plus == "10", "Add then + nine times should give 10"
    assert short.lines == [
        {"name": "Supacem 42.5", "detail": f"{money(100)} per 50 kg bag", "qty": "9",
         "amount": money(900)},
        {"name": "Iron rod 12 mm", "detail": f"{money(58)} per 30 ft rod", "qty": "24",
         "amount": money(1392)},
    ]
    assert short.totals.split("\n") == [
        "Materials", money(2292), "Delivery", "Quoted separately",
        "Total before delivery", money(2292)]


def test_b02_search_filters(short):
    assert [(r["name"], r["price"]) for r in short.search_rows] == [("Dzata 42.5", money(110))]
    assert short.rows_after_clearing_search == len(PRODUCTS)


def test_b03_category_tabs_switch(short):
    assert short.tab_per_ton.pressed == "true"
    assert short.tab_per_ton.slide == 2, "the Per Ton slide should be showing"
    assert short.tab_cement.pressed == "true"
    assert short.tab_cement.slide == 0, "the Cement slide should be showing"


def test_b04_print_quotation_hidden_on_screen(short):
    assert short.quote_visible_on_screen is False


# ---- WhatsApp message -----------------------------------------------------
def test_b05_whatsapp_has_estimate_reference(short):
    assert f"*Estimate {short.ref}* ({short.date})" in short.message


def test_b06_whatsapp_has_drop_off_location(short):
    assert f"*Drop-off location:* {LOCATION}" in short.message


def test_b07_whatsapp_items_quantities_prices_line_totals(short):
    items = short.message.split("*Items*\n")[1].split("\n\n")[0]
    assert items == (
        "1. Supacem 42.5 (50 kg bag)\n"
        f"   9 × {money(100)} = {money(900)}\n"
        "2. Iron rod 12 mm (30 ft rod)\n"
        f"   24 × {money(58)} = {money(1392)}")


def test_b08_whatsapp_materials_total(short):
    assert f"*Materials total: {money(2292)}*" in short.message


def test_b09_whatsapp_asks_to_confirm_availability_and_delivery(short):
    assert short.message.endswith(
        "Please confirm availability and the delivery cost to this location.")


def test_b10_whatsapp_omits_location_when_empty(short):
    assert "Drop-off location" not in short.message_without_location
    assert short.message_without_location.endswith(
        "Please confirm availability and the delivery cost.")


# ---- A4 PDF, short quotation ----------------------------------------------
def test_b11_pdf_is_a4(short):
    assert all(is_a4(size) for size in short.pdf.sizes), short.pdf.sizes


def test_b12_short_quotation_fits_one_page(short):
    assert short.pdf.count == 1


def test_b13_pdf_quantities_are_plain_numbers(short):
    # Every row read back out of the PDF, compared exactly.
    assert short.pdf.rows == [
        expected_row(1, BY_ID["c2"], 9),
        expected_row(2, BY_ID["i3"], 24),
    ]
    # And the quantity cells contain only digits: no input boxes or buttons.
    assert short.pdf.qty_cells == ["9", "24"]


def test_b14_pdf_has_reference_date_location(short):
    page = short.pdf.pages[0]
    assert f"Reference {short.ref}" in page
    assert f"Date {short.date}" in page
    assert LOCATION in page


def test_b15_short_pdf_page_number(short):
    assert "Page 1 of 1" in short.pdf.pages[0]


def test_b16_short_pdf_has_no_continuation_header(short):
    assert "Continued" not in short.pdf.pages[0]
    assert f"Estimate {short.ref}" not in short.pdf.pages[0]


def test_b17_short_pdf_closing_section(short):
    page = short.pdf.pages[0]
    assert "DELIVERYANDTERMS" in squash(page)
    assert "TOORDER" in squash(page)
    assert squash(f"quote reference {short.ref}.") in squash(page)
    assert f"Total before delivery {money(2292)}" in page


def test_b18_same_reference_on_screen_pdf_and_whatsapp(short):
    assert short.ref in short.message
    assert short.pdf.text.count(short.ref) >= 2  # header and "To order" line


def test_b19_reference_format(short):
    assert re.fullmatch(REF_PATTERN, short.ref), short.ref


def test_b20_no_website_controls_in_pdf(short):
    assert short.pdf.printed_blocks == ["quote"], "only the quotation may print"
    assert short.pdf.controls == 0, "the quotation must contain no buttons, inputs or links"
    for label in CONTROL_LABELS:
        assert label not in short.pdf.text, label


# ---- References -----------------------------------------------------------
def test_b21_clear_estimate_issues_new_reference(short):
    assert short.lines_after_clear == []
    assert re.fullmatch(REF_PATTERN, short.ref_after_clear)
    assert short.ref_after_clear != short.ref
    assert short.ref_after_clear in short.message_after_clear
    assert short.ref not in short.message_after_clear


def test_b22_five_thousand_references_do_not_repeat(short):
    # A reference ends in 6 random characters: about 1.07 billion possibilities
    # per day. Among 5,000 references there is roughly a 1.2% chance that one
    # pair matches by pure chance, so demanding 5,000 out of 5,000 would fail
    # about once in 85 runs with nothing wrong. Allowing two chance repeats
    # brings a false alarm down to about 1 run in 4 million, while a real
    # fault (a stuck or badly generated reference) still fails by a wide margin.
    assert short.unique_refs >= 4998, f"only {short.unique_refs} of 5000 references were different"


# ---- Long quotation (17 real + 45 synthetic rows) --------------------------
def test_b23_long_quotation_flows_to_extra_pages(long):
    assert long.pdf.count >= 2
    assert all(abs(w - A4_POINTS[0]) < 1 and abs(h - A4_POINTS[1]) < 1
               for w, h in long.pdf.sizes)


def test_b24_column_headings_repeat_on_every_page_with_rows(long):
    for number, page in enumerate(long.pdf.pages, start=1):
        if re.search(r"^\d+ Test item \d+$|^\d+ Supacem", page, re.M):
            assert "#DESCRIPTIONQTYUNITPRICEAMOUNT" in squash(page), f"page {number}"
    assert "#DESCRIPTIONQTYUNITPRICEAMOUNT" in squash(long.pdf.pages[1])


def test_b25_all_62_rows_printed_exactly(long):
    expected = [expected_row(i, product, qty)
                for i, (product, qty) in enumerate(long.expected, start=1)]
    assert len(expected) == len(PRODUCTS) + len(SYNTHETIC) == 62
    assert long.pdf.rows == expected


def test_b26_long_pdf_has_its_own_reference(short, long):
    assert re.fullmatch(REF_PATTERN, long.ref)
    assert long.ref != short.ref
    assert long.ref in long.pdf.text and short.ref not in long.pdf.text


def test_b27_continuation_pages_show_brand_reference_and_page_number(long):
    total = long.pdf.count
    for number in range(2, total + 1):
        page = long.pdf.pages[number - 1]
        assert squash(f"The Cement People · Estimate {long.ref}") in squash(page), f"page {number}"
        assert "Continued" in page, f"page {number}"
        assert f"Page {number} of {total}" in page, f"page {number}"


def test_b28_first_page_of_long_pdf_has_no_continuation_header(long):
    first = long.pdf.pages[0]
    assert "Continued" not in first
    assert f"Page 1 of {long.pdf.count}" in first


def test_b29_last_page_number_and_closing_section(long):
    last = long.pdf.pages[-1]
    assert f"Page {long.pdf.count} of {long.pdf.count}" in last
    assert "DELIVERYANDTERMS" in squash(last)
    assert "TOORDER" in squash(last)


def test_b30_totals_block_intact_on_last_page(long):
    last = long.pdf.pages[-1]
    assert f"Materials {money(long.materials_total)}" in last
    assert "Delivery Quoted separately" in last
    assert f"Total before delivery {money(long.materials_total)}" in last


# ---- Mobile and errors ----------------------------------------------------
def test_b31_no_script_errors_on_desktop(short, long):
    assert short.errors == []
    assert long.errors == []


def test_b32_mobile_view_estimate_opens_full_screen(mobile):
    assert mobile.estimate_open is True
    box, view = mobile.estimate_box, mobile.viewport
    assert box["x"] <= 0 and box["y"] <= 0
    assert box["width"] >= view["width"] and box["height"] >= view["height"]


def test_b33_mobile_print_is_a4_with_full_content(mobile):
    assert all(is_a4(size) for size in mobile.pdf.sizes)
    assert mobile.pdf.rows == [
        expected_row(i, product, qty)
        for i, (product, qty) in enumerate(
            sorted(mobile.items, key=lambda item: PRODUCTS.index(item[0])), start=1)]
    assert "Kasoa, Millennium City" in mobile.pdf.text
    assert mobile.ref in mobile.pdf.text
    assert mobile.pdf.printed_blocks == ["quote"]


def test_b34_no_script_errors_on_mobile(mobile):
    assert mobile.errors == []


# ---- Code check -----------------------------------------------------------
def test_b35_no_test_items_on_the_website(short, catalogue):
    # The page as delivered contains no synthetic test data ...
    assert "Test item" not in short.page_source_on_load
    assert '"t0"' not in short.page_source_on_load
    # ... and a freshly opened price list shows the real products only.
    names = [row["name"] for row in catalogue.price_list]
    assert len(names) == len(PRODUCTS)
    assert not [n for n in names if re.search(r"test", n, re.I)]
