"""Phase 2: search-engine and AI discoverability checks for the Astro site.

These tests read the page the way a search engine or AI crawler does: mostly
as plain HTML, WITHOUT running any JavaScript. They check that the products,
the business details and the machine-readable descriptions are all there,
are correct, and contain nothing invented.

Reference files (independent of the website's own source):
    baseline/products.json   the 17 products
    baseline/business.json   the confirmed business details, title, description

Where they run: only against a served site (TCP_SITE_URL=http://...), which
in practice means the Astro build. The original single-file site, tested by
opening index.html from disk, predates all of this, so there the whole file
is skipped (and reported as skipped, not passed).

Only Python's standard library is used, plus the browser already used by the
other tests for the two checks that need one.
"""
import json
import re
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import pytest

from conftest import PRODUCTS, SITE_URL, TESTS, add_item, money, open_site

SERVED = SITE_URL.startswith("http")
pytestmark = pytest.mark.skipif(
    not SERVED,
    reason="SEO checks need a served site (set TCP_SITE_URL); the original single-file site predates them")

BUSINESS = json.loads((TESTS / "baseline" / "business.json").read_text(encoding="utf-8"))
SITE = BUSINESS["siteUrl"]            # the public address, https://thecementpeople.com
CANONICAL = SITE + "/"

# Images that are decoration only and so correctly have empty alt text.
# Images with empty alt text on purpose: the iron-rods banner (the tab heading
# and note under it say the same thing). The hero photo is described.
DECORATIVE_IMAGES = {"/images/products/iron-rods-1086.webp"}

# Every property the Store description may carry. Adding one means adding it
# here on purpose, with a confirmed source in baseline/business.json.
STORE_PROPERTIES = {
    "@type", "@id", "name", "url", "description", "logo", "image", "telephone", "email",
    "address", "geo", "hasMap", "openingHoursSpecification", "areaServed", "currenciesAccepted"}
# Things that must not appear anywhere in the structured data in this phase.
FORBIDDEN_KEYS = {"aggregateRating", "review", "reviews", "offers", "makesOffer",
                  "hasOfferCatalog", "price", "priceRange", "sameAs"}
FORBIDDEN_TYPES = {"Product", "Offer", "AggregateOffer", "Review", "AggregateRating"}

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # talk to the local server directly


def local(url_or_path):
    """Turn a public address or a /path into the address on the server under test."""
    if url_or_path.startswith(SITE):
        url_or_path = url_or_path[len(SITE):] or "/"
    return urllib.parse.urljoin(SITE_URL, url_or_path.lstrip("/"))


def fetch(url_or_path):
    with _OPENER.open(local(url_or_path), timeout=15) as response:
        assert response.status == 200, f"{url_or_path} returned {response.status}"
        return response.read()


class Page(HTMLParser):
    """Collects what a crawler sees in the raw HTML. No JavaScript is run."""
    VOID = {"meta", "link", "img", "br", "input", "hr"}
    HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.titles, self.metas, self.links, self.images = [], [], [], []
        self.headings, self.anchors, self.ids, self.scripts, self.json_ld = [], [], set(), [], []
        self.text = []
        self._stack, self._heading, self._title, self._script = [], None, None, None
        self.feed(html)
        self.visible_text = re.sub(r"\s+", " ", " ".join(self.text)).strip()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "meta":
            self.metas.append(a)
        elif tag == "link":
            self.links.append(a)
        elif tag == "img":
            self.images.append(a)
        elif tag == "a":
            self.anchors.append(a)
        elif tag == "title":
            self._title = []
        elif tag == "script":
            self.scripts.append(a)
            self._script = [] if a.get("type") == "application/ld+json" else None
        elif tag in self.HEADINGS:
            self._heading = [tag, []]
        if tag not in self.VOID:
            self._stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "title" and self._title is not None:
            self.titles.append("".join(self._title).strip())
            self._title = None
        elif tag == "script" and self._script is not None:
            self.json_ld.append("".join(self._script))
            self._script = None
        elif tag in self.HEADINGS and self._heading:
            self.headings.append((int(tag[1]), re.sub(r"\s+", " ", "".join(self._heading[1])).strip()))
            self._heading = None
        if tag in self._stack:
            while self._stack and self._stack.pop() != tag:
                pass

    def handle_data(self, data):
        if self._title is not None:
            self._title.append(data)
        if self._script is not None:
            self._script.append(data)
        if self._heading:
            self._heading[1].append(data)
        if not {"script", "style", "title", "head"} & set(self._stack):
            self.text.append(data)

    def meta(self, key):
        """All content values for <meta name=key> or <meta property=key>."""
        return [m.get("content") for m in self.metas if key in (m.get("name"), m.get("property"))]


@pytest.fixture(scope="module")
def html():
    return fetch("/").decode("utf-8")


@pytest.fixture(scope="module")
def page(html):
    return Page(html)


@pytest.fixture(scope="module")
def graph(page):
    """Every structured-data description on the page, as a flat list."""
    nodes = []
    for block in page.json_ld:
        data = json.loads(block)
        assert data.get("@context") == "https://schema.org", "structured data must use the schema.org vocabulary"
        nodes.extend(data["@graph"] if "@graph" in data else [data])
    return nodes


def node(graph, kind):
    matches = [n for n in graph if n.get("@type") == kind]
    assert len(matches) == 1, f"expected exactly one {kind}, found {len(matches)}"
    return matches[0]


def walk(value):
    """Every dictionary nested anywhere inside a JSON value."""
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)


def jpeg_size(data):
    """Width and height of a JPEG, read from the file itself."""
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        if marker == 0xFF or marker == 0x01 or 0xD0 <= marker <= 0xD8:
            i += 1 if marker == 0xFF else 2
            continue
        i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    raise AssertionError("not a readable JPEG")


def webp_size(data):
    """Width and height of a WebP file, read from its header."""
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP", "not a WebP file"
    kind = data[12:16]
    if kind == b"VP8 ":
        return (int.from_bytes(data[26:28], "little") & 0x3FFF,
                int.from_bytes(data[28:30], "little") & 0x3FFF)
    if kind == b"VP8L":
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if kind == b"VP8X":
        return int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    raise AssertionError(f"unknown WebP type {kind!r}")


def svg_size(data):
    """Width and height of an SVG drawing, rounded to whole pixels (the V1.1
    logos are drawn at sizes such as 733.6 x 275)."""
    svg = ET.fromstring(data)
    return round(float(svg.get("width"))), round(float(svg.get("height")))


def image_size(data):
    """Width and height of a JPEG, WebP or SVG file."""
    if data[:4] == b"RIFF":
        return webp_size(data)
    if b"<svg" in data[:400]:
        return svg_size(data)
    return jpeg_size(data)


# ---- Products are readable without JavaScript ------------------------------
# A price-list row. Since Phase 3 a row may start with a product photo
# (class "row has-img" + <img class="thumb">), and a rod's name holds its size
# as a bold tag ("Iron rod <b class="sz">16 mm</b>"). The name is read with
# its tags removed, so it must still say exactly "Iron rod 16 mm".
# Catalogue phase: where a whole tab shares one price (rods by the ton), the
# row's price is still in the HTML but wrapped in <span class="vh"> (hidden
# from view, shown once under the heading instead).
ROW = re.compile(r'<div class="row(?: has-img)?(?: one)?">(?:<img class="thumb"[^>]*>)?<div class="nm">(.+?)<small>per ([^<]+)</small></div>'
                 r'(?:<div class="buy">)?<div class="pr">(?:<span class="vh">)?([^<]+)(?:</span>)?</div>')
TAGS = re.compile(r"<[^>]+>")


def test_s01_all_17_products_are_in_the_html_without_javascript(html, page):
    rows = [(TAGS.sub("", name), unit, price) for name, unit, price in ROW.findall(html)]
    assert len(rows) == len(PRODUCTS) == 17
    assert sorted(rows) == sorted((p["name"], p["unit"], money(p["price"])) for p in PRODUCTS)
    # Each category is a heading a crawler can read, under "Products and prices".
    # ("Delivery" is the estimate panel's own small heading, 17 Nov 2026.)
    headings = [text for level, text in page.headings if level == 3 and text != "Delivery"]
    assert headings == list(dict.fromkeys(p["category"] for p in PRODUCTS))


def test_s02_html_catalogue_is_identical_to_what_the_engine_draws(browser):
    # The page with scripts switched off (what a crawler gets) ...
    context = browser.new_context(java_script_enabled=False, locale="en-US",
                                  viewport={"width": 1280, "height": 900})
    static = context.new_page()
    static.goto(SITE_URL, wait_until="load")
    # (The category tiles under the hero, "#cats", were removed in the
    # design-system phase; the tabs and the list are compared.)
    parts = ("#tabs", "#list")
    without_js = [static.locator(part).inner_html() for part in parts]
    list_class = static.locator("#list").get_attribute("class")
    context.close()
    # ... and the same page once the quotation engine has drawn everything.
    live, errors = open_site(browser)
    with_js = [live.locator(part).inner_html() for part in parts]
    live_class = live.get_attribute("#list", "class")
    live.context.close()
    assert without_js[0] == with_js[0], "category tabs differ"
    assert without_js[1] == with_js[1], "price list differs"
    assert list_class == live_class == "snap"
    assert errors == []


# ---- Titles, descriptions and link previews ---------------------------------
def test_s03_title_description_canonical_and_link_preview(page):
    assert page.lang == "en"
    assert page.titles == [BUSINESS["page"]["title"]], "exactly one title, the brand name only"
    assert page.meta("description") == [BUSINESS["page"]["description"]]
    canonicals = [l.get("href") for l in page.links if l.get("rel") == "canonical"]
    assert canonicals == [CANONICAL], "exactly one canonical address, absolute and https"
    assert page.meta("og:title") == page.titles
    assert page.meta("og:description") == page.meta("description")
    assert page.meta("og:url") == [CANONICAL]
    assert page.meta("og:site_name") == [BUSINESS["name"]]
    assert page.meta("og:type") == ["website"]
    # Nothing tells search engines to stay away.
    assert page.meta("robots") == [] and page.meta("googlebot") == []
    # The preview picture: full https address, real size, described.
    [image] = page.meta("og:image")
    assert image.startswith(CANONICAL)
    width, height = jpeg_size(fetch(image))
    assert page.meta("og:image:width") == [str(width)]
    assert page.meta("og:image:height") == [str(height)]
    [alt] = page.meta("og:image:alt")
    assert alt.strip()


# ---- Structured data ---------------------------------------------------------
def test_s04_structured_data_is_valid_and_linked(page, graph):
    assert len(page.json_ld) == 1, "one structured-data block"
    assert sorted(n["@type"] for n in graph) == ["Store", "WebPage", "WebSite"]
    known = {n["@id"] for n in graph}
    assert len(known) == 3 and all(i.startswith(CANONICAL) for i in known)
    # Every pointer to another description leads somewhere.
    for d in walk(graph):
        if set(d) == {"@id"}:
            assert d["@id"] in known, f"dangling reference {d['@id']}"
    website, webpage, store = node(graph, "WebSite"), node(graph, "WebPage"), node(graph, "Store")
    assert website["publisher"] == {"@id": store["@id"]}
    assert webpage["isPartOf"] == {"@id": website["@id"]}
    assert webpage["about"] == {"@id": store["@id"]}
    assert website["url"] == webpage["url"] == store["url"] == CANONICAL
    assert website["name"] == BUSINESS["name"]
    assert webpage["name"] == BUSINESS["page"]["title"]
    assert webpage["description"] == BUSINESS["page"]["description"]


def test_s05_structured_data_contains_only_confirmed_details(graph):
    store = node(graph, "Store")
    assert set(store) == STORE_PROPERTIES, "Store carries a property with no confirmed source, or lost one"
    assert store["name"] == BUSINESS["name"]
    assert store["telephone"] == BUSINESS["phoneInternational"]
    assert store["email"] == BUSINESS["publicEmail"]
    assert store["description"] == BUSINESS["page"]["description"]
    address = BUSINESS["address"]
    assert store["address"] == {
        "@type": "PostalAddress",
        "streetAddress": f"{address['street']}, {address['area']}",
        "addressLocality": address["locality"],
        "addressRegion": address["region"],          # Central Region: the address is not in Greater Accra
        "addressCountry": address["countryCode"]}
    assert store["geo"] == {"@type": "GeoCoordinates", **BUSINESS["geo"]}
    assert store["hasMap"] == BUSINESS["mapUrl"]
    assert store["openingHoursSpecification"] == [
        {"@type": "OpeningHoursSpecification", "dayOfWeek": block["days"],
         "opens": block["opens"], "closes": block["closes"]}
        for block in BUSINESS["openingHours"]]
    opened = {day for spec in store["openingHoursSpecification"] for day in spec["dayOfWeek"]}
    assert not opened & set(BUSINESS["closedDays"]), "a closed day is listed as open"
    assert [place["name"] for place in store["areaServed"]] == BUSINESS["deliveryAreas"]
    assert store["currenciesAccepted"] == BUSINESS["currencyCode"]
    # No ratings, reviews, products, offers or prices anywhere, and no claimed
    # profile links until they are verified.
    for d in walk(graph):
        assert not FORBIDDEN_KEYS & set(d), f"unexpected {FORBIDDEN_KEYS & set(d)}"
        kinds = d.get("@type", [])
        assert not FORBIDDEN_TYPES & set([kinds] if isinstance(kinds, str) else kinds)


def test_s06_business_details_are_visible_in_the_html(page):
    text = page.visible_text
    for detail in (BUSINESS["name"], BUSINESS["addressLine"], BUSINESS["landmark"], BUSINESS["plusCode"],
                   BUSINESS["openingHoursText"], BUSINESS["closedText"], BUSINESS["phone"],
                   BUSINESS["publicEmail"], *BUSINESS["deliveryAreas"]):
        assert detail in text, f"not visible on the page: {detail}"
    hrefs = {a.get("href") for a in page.anchors}
    assert f"tel:{BUSINESS['phoneInternational']}" in hrefs
    assert f"mailto:{BUSINESS['publicEmail']}" in hrefs
    # The address must never be described as being in Greater Accra.
    assert "Kasoa, Greater Accra" not in text


# ---- Page structure, images, files -------------------------------------------
def test_s07_heading_outline(page):
    levels = [level for level, _ in page.headings]
    assert levels.count(1) == 1, "exactly one main heading"
    assert levels[0] == 1
    for previous, current in zip(levels, levels[1:]):
        assert current <= previous + 1, f"heading level jumps from h{previous} to h{current}"
    assert (2, "Products and prices") in page.headings
    # Binding wire: its own category heading since 17 Nov 2026 (was an h4
    # inside the single-piece rods).
    assert (3, "Binding Wire") in page.headings


def test_s08_images_have_descriptions_and_real_dimensions(page):
    assert page.images, "the page has images"
    described = 0
    for image in page.images:
        src = image["src"]
        assert "alt" in image, f"{src} has no alt attribute"
        if image["alt"].strip():
            described += 1
        else:
            assert src in DECORATIVE_IMAGES, f"{src} has empty alt text but is not listed as decorative"
        width, height = image_size(fetch(src))
        if image.get("srcset"):
            # Product photos come in several sizes (srcset); their width and
            # height give the size they are shown at (96 x 96), so here only the
            # shape must match the file, to within one percent.
            w, h = int(image["width"]), int(image["height"])
            assert abs(w / h - width / height) < 0.01, f"{src}: {w}x{h} attributes, file is {width}x{height}"
        else:
            assert (image.get("width"), image.get("height")) == (str(width), str(height)), src
    assert described >= 1


def test_s09_sitemap_is_valid_and_complete(page):
    root = ET.fromstring(fetch("/sitemap.xml"))
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    assert root.tag == namespace + "urlset"
    addresses = [loc.text for loc in root.iter(namespace + "loc")]
    assert CANONICAL in addresses
    assert len(addresses) == len(set(addresses))
    for address in addresses:
        assert address.startswith(CANONICAL), f"{address} is not an https address on the site"
        fetch(address)  # every listed page is really served
    assert [l.get("href") for l in page.links if l.get("rel") == "sitemap"] == ["/sitemap.xml"]


def test_s10_robots_txt_allows_crawlers_and_names_the_sitemap():
    robots = urllib.robotparser.RobotFileParser()
    robots.parse(fetch("/robots.txt").decode("utf-8").splitlines())
    for crawler in ("*", "Googlebot", "Bingbot", "GPTBot", "ClaudeBot", "PerplexityBot"):
        assert robots.can_fetch(crawler, CANONICAL), f"{crawler} is blocked from the home page"
        assert robots.can_fetch(crawler, SITE + "/sitemap.xml")
    assert robots.site_maps() == [SITE + "/sitemap.xml"]


def test_s11_no_broken_links_or_missing_files(page, graph):
    for anchor in page.anchors:
        href = anchor.get("href")
        if href is None:
            continue  # the WhatsApp estimate button gets its link from the engine
        if href.startswith("#"):
            assert href[1:] in page.ids, f"link to {href} goes nowhere"
        else:
            assert href.startswith(("tel:", "mailto:", "https://")), f"unexpected link {href}"
    files = [i["src"] for i in page.images]
    files += [s["src"] for s in page.scripts if s.get("src")]
    files += [l["href"] for l in page.links
              if l.get("rel") in ("stylesheet", "sitemap") and not l["href"].startswith("https://")]
    files += page.meta("og:image")
    assert files
    for path in files:
        assert fetch(path), f"{path} is empty"


def test_s12_logo_file_is_a_real_svg_and_is_the_declared_logo(graph):
    store = node(graph, "Store")
    assert store["logo"] == SITE + "/images/logo.svg"
    svg = ET.fromstring(fetch(store["logo"]))
    assert svg.tag == "{http://www.w3.org/2000/svg}svg"
    assert float(svg.get("width")) >= 112 and float(svg.get("height")) >= 112
    # Brand identity V1.1 (17 Nov 2026): the diamond emblem in Ochre A over
    # the charcoal wordmark (was the four-brick stair mark).
    fills = [p.get("fill", "").lower() for p in svg.iter("{http://www.w3.org/2000/svg}path")]
    assert "#d27d02" in fills and "#131514" in fills, fills


def test_s13_page_title_is_restored_after_printing(browser):
    # Printing renames the page so the PDF is saved under the quotation
    # reference; afterwards the page must get its own title back.
    live, errors = open_site(browser)
    add_item(live, PRODUCTS[0], 1)
    live.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    assert re.fullmatch(r"The Cement People Estimate TCP-\d{6}-[2-9A-HJ-NP-Z]{6}", live.title())
    live.evaluate("window.dispatchEvent(new Event('afterprint'))")
    assert live.title() == BUSINESS["page"]["title"]
    assert errors == []
    live.context.close()
