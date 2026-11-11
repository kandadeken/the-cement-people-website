"""
Product images on the price list (added on the product-images branch).

These checks make sure the pictures load, that every tab keeps its visible text
heading, that both iron rod tabs share one photo (downloaded once, in a size
that suits the screen), that the rod sizes are real text, that a missing photo
is simply left out, and that the images don't make the page wider than a phone.
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
ROD_TABS = {
    "Iron Rods (Single Piece)": "Sold by the piece. Each rod is 30 ft long.",
    "Iron Rods (Per Ton)": "Sold by the ton, in each size.",
}

# Reads one tab: its banner photo, heading and note. Waits for the photo.
READ_TAB = """async cat => {
    await document.fonts.ready;
    const sec = [...document.querySelectorAll('#list .slide section')]
        .find(s => s.querySelector('h2').textContent.trim() === cat);
    const img = sec.querySelector('img.banner');
    if (img && !img.complete) await new Promise(r => {
        img.addEventListener('load', r, {once: true});
        img.addEventListener('error', r, {once: true});
    });
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const h2 = sec.querySelector('h2'), note = sec.querySelector('.cat-note');
    const hb = h2.getBoundingClientRect(), ib = img && img.getBoundingClientRect();
    return {
        img: img && {src: img.currentSrc.split('/').pop(), loaded: img.naturalWidth > 0,
                     alt: img.getAttribute('alt'), lazy: img.loading === 'lazy',
                     shown: ib.width > 0, width: Math.round(ib.width),
                     right: Math.round(ib.right), bottom: ib.bottom},
        heading: {text: h2.textContent.trim(), width: hb.width, height: hb.height, top: hb.top},
        note: note && note.textContent.trim(),
        viewport: innerWidth, page: document.documentElement.scrollWidth,
    };
}"""


def _tab(page, category):
    page.click(f'#tabs button[data-cat="{category}"]')
    page.wait_for_timeout(600)


def test_p01_image_files_exist():
    names = ["supacem-32-5", "supacem-42-5", "dzata-42-5", "ghacem-waterproof-42-5",
             "binding-wire", "iron-rods-720", "iron-rods-1086", "iron-rods-1440"]
    for n in names:
        f = IMAGES / f"{n}.webp"
        assert f.is_file(), f"missing {f.relative_to(ROOT)}"
        assert f.stat().st_size < 150_000, f"{f.name} is larger than 150 KB"
    # The phone-sized rod photo must really be smaller than the desktop one.
    assert (IMAGES / "iron-rods-720.webp").stat().st_size < (IMAGES / "iron-rods-1086.webp").stat().st_size


@needs_live_layout
def test_p02_cement_and_wire_rows_show_a_loaded_photo_with_alt_text(browser):
    page, errors = open_site(browser)
    for cat in ["Cement", "Iron Rods (Single Piece)"]:
        _tab(page, cat)
    page.wait_for_load_state("networkidle")
    info = page.evaluate("""ids => ids.map(id => {
        const row = document.querySelector(`#list [data-inc="${id}"]`).closest('.row');
        const img = row.querySelector('img.thumb');
        return img && {id, ok: img.complete && img.naturalWidth > 0, alt: img.alt,
                       lazy: img.loading === 'lazy'};
    })""", CEMENT_AND_WIRE)
    for item in info:
        assert item, "a cement or binding wire row has no photo"
        assert item["ok"], f"{item['id']}: photo did not load"
        assert item["alt"].strip(), f"{item['id']}: photo has no alt text"
        assert not item["lazy"], f"{item['id']}: photo should load straight away"
    assert not errors, errors
    page.context.close()


@needs_live_layout
def test_p03_rod_tabs_show_shared_photo_then_visible_heading_and_note(browser):
    page, errors = open_site(browser)
    seen = set()
    for cat, note in ROD_TABS.items():
        _tab(page, cat)
        t = page.evaluate(READ_TAB, cat)
        assert t["img"]["loaded"], f"{cat}: rod photo did not load"
        assert t["img"]["src"].startswith("iron-rods-"), t["img"]
        assert t["img"]["alt"] == "", "rod photo is decorative; heading and note carry the text"
        assert not t["img"]["lazy"], "rod photo should load with the page"
        assert t["heading"]["text"] == cat
        assert t["heading"]["width"] > 50 and t["heading"]["height"] > 10, f"{cat}: heading not visible"
        assert t["heading"]["top"] >= t["img"]["bottom"] - 1, f"{cat}: heading should sit under the photo"
        assert t["note"] == note
        seen.add(t["img"]["src"])
    assert len(seen) == 1, f"both rod tabs should use the same photo, got {seen}"
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
def test_p05_missing_photo_is_left_out_and_heading_stays(browser):
    page, _ = open_site(browser)
    # Point the rod photo at files that don't exist, then redraw the list.
    page.evaluate("""() => {
        ROD_PHOTO.src = 'images/products/does-not-exist.webp';
        ROD_PHOTO.srcset = 'images/products/does-not-exist.webp 1086w';
        document.querySelector('#clear').click();
    }""")
    _tab(page, "Iron Rods (Single Piece)")
    page.wait_for_timeout(800)
    t = page.evaluate("""() => {
        const sec = [...document.querySelectorAll('#list .slide section')]
            .find(s => s.querySelector('h2').textContent.includes('Single Piece'));
        const r = sec.querySelector('h2').getBoundingClientRect();
        return {left_out: sec.classList.contains('nobanner'),
                img_shown: sec.querySelector('img.banner').getBoundingClientRect().height > 0,
                w: r.width, h: r.height};
    }""")
    assert t["left_out"] and not t["img_shown"], "a broken photo should be hidden"
    assert t["w"] > 50 and t["h"] > 10, "heading should stay visible"
    page.context.close()


@needs_live_layout
def test_p06_no_sideways_scrolling_on_a_phone(browser):
    # Checks the page as it opens, then each iron rod tab once its web font
    # and photo have finished loading: an earlier version of the banner only
    # widened the page after the Montserrat font had loaded.
    page, _ = open_site(browser, mobile=True)
    width = page.evaluate("[innerWidth, document.documentElement.scrollWidth]")
    assert width == [390, 390], f"page is wider than the phone screen on opening: {width}"
    for cat in ROD_TABS:
        _tab(page, cat)
        t = page.evaluate(READ_TAB, cat)
        assert t["img"]["loaded"], f"{cat}: rod photo did not load"
        assert t["viewport"] == 390 and t["page"] == 390, \
            f"{cat}: page is wider than the phone screen: {t}"
        assert 0 < t["img"]["width"] <= 390 and t["img"]["right"] <= 390, \
            f"{cat}: photo does not fit the screen: {t['img']}"
    page.context.close()


@needs_live_layout
def test_p07_phone_uses_the_small_rod_photo_for_both_tabs(browser):
    # Both tabs pointing at the same file means the browser downloads it once.
    # 390 px wide at 2x pixel density needs about 716 px: the 720 px copy.
    page, _ = open_site(browser, mobile=True)
    used = []
    for cat in ROD_TABS:
        _tab(page, cat)
        used.append(page.evaluate(READ_TAB, cat)["img"]["src"])
    assert used == ["iron-rods-720.webp", "iron-rods-720.webp"], f"rod photo on a phone: {used}"
    page.context.close()
