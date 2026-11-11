"""
Product images on the price list (added on the product-images branch).

These checks make sure the pictures load, that every section still has a real
text heading for screen readers and search engines, that the rod sizes are
real text, that a missing banner falls back to the normal heading, and that the
images don't make the page wider than a phone screen.
"""
import os

import pytest

from conftest import ROOT, open_site

# The Astro version in web/ doesn't have the product images yet; they are
# carried over before the switch-over (see web/README.md, "Product images").
# GitHub runs the whole tests/ folder against the Astro build on port 4321,
# so the in-browser checks are skipped there until that work is done.
ASTRO_BUILD = os.environ.get("TCP_SITE_URL", "").startswith("http://127.0.0.1:4321")
needs_live_layout = pytest.mark.skipif(
    ASTRO_BUILD, reason="product images not yet carried over to the Astro version")

IMAGES = ROOT / "images" / "products"
CEMENT_AND_WIRE = ["c1", "c2", "c3", "c4", "i8"]
BANNERS = {
    "Iron Rods (Single Piece)": "iron-rods-single-piece.webp",
    "Iron Rods (Per Ton)": "iron-rods-per-ton.webp",
}


def _tab(page, category):
    page.click(f'#tabs button[data-cat="{category}"]')
    page.wait_for_timeout(600)


def test_p01_image_files_exist():
    names = ["supacem-32-5", "supacem-42-5", "dzata-42-5", "ghacem-waterproof-42-5",
             "binding-wire", "iron-rods-single-piece", "iron-rods-per-ton"]
    for n in names:
        f = IMAGES / f"{n}.webp"
        assert f.is_file(), f"missing {f.relative_to(ROOT)}"
        assert f.stat().st_size < 150_000, f"{f.name} is larger than 150 KB"


@needs_live_layout
def test_p02_cement_and_wire_rows_show_a_loaded_photo_with_alt_text(browser):
    page, errors = open_site(browser)
    for cat in ["Cement", "Iron Rods (Single Piece)"]:
        _tab(page, cat)
    page.wait_for_load_state("networkidle")
    info = page.evaluate("""ids => ids.map(id => {
        const row = document.querySelector(`#list [data-inc="${id}"]`).closest('.row');
        const img = row.querySelector('img.thumb');
        return img && {id, ok: img.complete && img.naturalWidth > 0, alt: img.alt};
    })""", CEMENT_AND_WIRE)
    for item in info:
        assert item, "a cement or binding wire row has no photo"
        assert item["ok"], f"{item['id']}: photo did not load"
        assert item["alt"].strip(), f"{item['id']}: photo has no alt text"
    assert not errors, errors
    page.context.close()


@needs_live_layout
def test_p03_rod_tabs_show_banner_and_keep_a_text_heading(browser):
    page, errors = open_site(browser)
    for cat, file in BANNERS.items():
        _tab(page, cat)
        page.wait_for_load_state("networkidle")
        found = page.evaluate("""cat => {
            const sec = [...document.querySelectorAll('#list .slide section')]
                .find(s => s.querySelector('h2').textContent.trim() === cat);
            const img = sec.querySelector('img.banner');
            return {src: img.getAttribute('src'), ok: img.complete && img.naturalWidth > 0,
                    heading: sec.querySelector('h2').textContent.trim()};
        }""", cat)
        assert found["src"].endswith(file)
        assert found["ok"], f"{cat}: banner did not load"
        assert found["heading"] == cat
    assert not errors, errors
    page.context.close()


@needs_live_layout
def test_p04_rod_sizes_are_text_tags(browser):
    page, _ = open_site(browser)
    tags = page.evaluate(
        "[...document.querySelectorAll('#list .sz')].map(b => b.textContent.trim())")
    sizes = ["16 mm", "14 mm", "12 mm", "11.5 mm", "10 mm", "8 mm"]
    assert tags == sizes + sizes  # single piece tab, then per ton tab
    page.context.close()


@needs_live_layout
def test_p05_missing_banner_falls_back_to_visible_heading(browser):
    page, _ = open_site(browser)
    # Point the banner at a file that doesn't exist, then redraw the list.
    page.evaluate("""() => {
        BANNER['Iron Rods (Single Piece)'] = 'images/products/does-not-exist.webp';
        document.querySelector('#clear').click();
    }""")
    _tab(page, "Iron Rods (Single Piece)")
    page.wait_for_timeout(800)
    box = page.evaluate("""() => {
        const sec = [...document.querySelectorAll('#list .slide section')]
            .find(s => s.querySelector('h2').textContent.includes('Single Piece'));
        const r = sec.querySelector('h2').getBoundingClientRect();
        return {fallback: sec.classList.contains('nobanner'), w: r.width, h: r.height};
    }""")
    assert box["fallback"], "banner failure was not detected"
    assert box["w"] > 50 and box["h"] > 10, "heading stayed hidden after banner failed"
    page.context.close()


@needs_live_layout
def test_p06_no_sideways_scrolling_on_a_phone(browser):
    page, _ = open_site(browser, mobile=True)
    width = page.evaluate("[innerWidth, document.documentElement.scrollWidth]")
    assert width == [390, 390], f"page is wider than the phone screen: {width}"
    page.context.close()
