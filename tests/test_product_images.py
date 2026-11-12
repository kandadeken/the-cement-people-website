"""
Product images on the price list (added on the product-images branch).

These checks make sure the pictures load, that every tab keeps its visible text
heading, that both iron rod tabs share one photo (downloaded once, in a size
that suits the screen), that the rod sizes are real text, that a missing photo
is simply left out, and that the images don't make the page wider than a phone.
The last checks cover the thumbnail sizes: 96 px on computers and tablets,
80 px on phones, with each screen downloading the size that suits it.
"""
import os

import pytest

from PIL import Image

from conftest import ROOT, SITE_URL, open_site

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


# ---------------------------------------------------------------------------
# Thumbnail sizes (added on the responsive-thumbnails branch, approved
# 12 Nov 2026): 96 x 96 px on computers and tablets, 80 x 80 px on phones, each
# photo in several sizes so every screen downloads only what it needs.
# ---------------------------------------------------------------------------
THUMBS = ["supacem-32-5", "supacem-42-5", "dzata-42-5", "ghacem-waterproof-42-5", "binding-wire"]
THUMB_WIDTHS = [80, 96, 120, 160, 192, 240, 288]


def test_p08_every_thumbnail_exists_in_every_size():
    # Square, the size its name says, and each one smaller than the next.
    for n in THUMBS:
        last = 0
        for w in THUMB_WIDTHS + [360]:
            f = IMAGES / (f"{n}.webp" if w == 360 else f"{n}-{w}.webp")
            assert f.is_file(), f"missing {f.relative_to(ROOT)}"
            with Image.open(f) as im:
                assert im.format == "WEBP" and im.size == (w, w), f"{f.name}: {im.format} {im.size}"
            size = f.stat().st_size
            assert size > last, f"{f.name} should be larger than the next size down"
            last = size


def _open(browser, width, height, scale, mobile=False):
    context = browser.new_context(viewport={"width": width, "height": height},
                                  device_scale_factor=scale, is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    page.goto(SITE_URL, wait_until="load")
    page.wait_for_load_state("networkidle")
    return page


# Reads every visible thumbnail: the file the browser chose, the size of the
# photo itself, and where the name, price and Add button sit in its row.
READ_THUMBS = """() => [...document.querySelectorAll('#list img.thumb')]
    .filter(i => i.getBoundingClientRect().width > 0).map(i => {
        const row = i.closest('.row'), r = i.getBoundingClientRect();
        const nm = row.querySelector('.nm').getBoundingClientRect();
        const pr = row.querySelector('.pr').getBoundingClientRect();
        const bt = row.querySelector('[data-inc]').getBoundingClientRect();
        return {file: i.currentSrc.split('/').pop(), loaded: i.naturalWidth > 0,
                box: [r.width, r.height], photo: [i.clientWidth, i.clientHeight],
                sizes: i.sizes, srcset: i.srcset,
                nameAfterPhoto: nm.left >= r.right, nameOneLine: nm.height < 60,
                priceInsideRow: pr.right <= row.getBoundingClientRect().right + 0.5,
                buttonInsideRow: bt.right <= row.getBoundingClientRect().right + 0.5};
    })"""


@needs_live_layout
@pytest.mark.parametrize("width,height,scale,mobile,shown,expected_file", [
    (1536, 742, 1.0, False, 96, "-96.webp"),    # ordinary PC screen
    (1536, 742, 1.25, False, 96, "-120.webp"),  # PC with 125% display scaling
    (1440, 900, 2.0, False, 96, "-192.webp"),   # high-resolution laptop
    (820, 1180, 2.0, True, 96, "-192.webp"),    # tablet
    (390, 844, 3.0, True, 80, "-240.webp"),     # typical phone
    (360, 800, 2.0, True, 80, "-160.webp"),     # small phone
])
def test_p09_thumbnail_size_and_file_suit_the_screen(browser, width, height, scale, mobile,
                                                     shown, expected_file):
    page = _open(browser, width, height, scale, mobile)
    for t in page.evaluate(READ_THUMBS):
        assert t["loaded"], t
        # The whole box is photo: the frame is drawn outside it, not inside.
        assert t["box"] == [shown, shown] and t["photo"] == [shown, shown], t
        assert t["file"].endswith(expected_file), f"{width}px @{scale}x chose {t['file']}"
        assert t["sizes"] == "(max-width:560px) 80px, 96px", t["sizes"]
        assert t["nameAfterPhoto"] and t["nameOneLine"], f"name crowded or wrapped: {t}"
        assert t["priceInsideRow"] and t["buttonInsideRow"], f"price or button pushed out: {t}"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "page scrolls sideways"
    page.context.close()


@needs_live_layout
def test_p10_phone_thumbnail_is_no_taller_than_the_row_text(browser):
    # On a phone the name, unit and price stack beside the photo. The 80 px
    # photo must be no taller than that stack, so it doesn't make rows longer.
    page = _open(browser, 390, 844, 3.0, True)
    rows = page.evaluate("""() => [...document.querySelectorAll('#list .row.has-img')]
        .filter(r => r.getBoundingClientRect().width > 0).map(r => {
            const nm = r.querySelector('.nm').getBoundingClientRect();
            const pr = r.querySelector('.pr').getBoundingClientRect();
            return {photo: r.querySelector('img.thumb').getBoundingClientRect().height,
                    text: Math.max(pr.bottom, r.querySelector('[data-inc]').getBoundingClientRect().bottom) - nm.top};
        })""")
    assert rows, "no phone rows with photos found"
    for r in rows:
        assert r["photo"] <= r["text"] + 1, f"photo taller than the row text: {r}"
    page.context.close()
