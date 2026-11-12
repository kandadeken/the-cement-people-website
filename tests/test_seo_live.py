"""Search-engine basics on the LIVE site (the root index.html, robots.txt and
sitemap.xml that GitHub Pages publishes today).

Added 12 Nov 2026 after Google Search Console showed the live site had never
been indexed. The full SEO work (test_seo.py) is for the Astro version in web/,
which is not live yet; these checks cover the small subset ported to the live
site so Google can find and understand it now:

- the page title is just "The Cement People" (the owner's choice)
- a description, a canonical address and structured data describing the shop
- robots.txt lets search engines in and points them to the sitemap
- sitemap.xml lists the homepage
- GitHub Pages actually publishes robots.txt and sitemap.xml
- after printing an estimate, the page title goes back to normal

Every business detail is compared with tests/baseline/business.json, the
owner-confirmed reference, so nothing invented can slip in. These read the
files from disk, so they need no server and no extra packages.
"""
import json
import os
import re
import urllib.robotparser
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import pytest

from conftest import ROOT, TESTS, open_site

BUSINESS = json.loads((TESTS / "baseline" / "business.json").read_text(encoding="utf-8"))
SITE = BUSINESS["siteUrl"]
CANONICAL = SITE + "/"
HTML = (ROOT / "index.html").read_text(encoding="utf-8")

# The structured data may only use these properties on the Store. Adding one
# means adding it here on purpose, with a confirmed source in business.json.
STORE_PROPERTIES = {
    "@type", "@id", "name", "url", "description", "telephone", "email", "address",
    "geo", "hasMap", "openingHoursSpecification", "areaServed", "currenciesAccepted"}
# Must not appear anywhere: nothing confirmed supports ratings, reviews or prices.
FORBIDDEN_KEYS = {"aggregateRating", "review", "reviews", "offers", "makesOffer",
                  "hasOfferCatalog", "price", "priceRange"}


class Head(HTMLParser):
    """Collects the <head> tags a search engine reads, without running scripts."""

    def __init__(self):
        super().__init__()
        self.titles, self.metas, self.links, self.jsonld = [], [], [], []
        self._in_title = self._in_ld = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
            self.titles.append("")
        elif tag == "meta":
            self.metas.append(a)
        elif tag == "link":
            self.links.append(a)
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in_ld = True
            self.jsonld.append("")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_ld = False

    def handle_data(self, data):
        if self._in_title:
            self.titles[-1] += data
        elif self._in_ld:
            self.jsonld[-1] += data


HEAD = Head()
HEAD.feed(HTML)


def _graph():
    assert len(HEAD.jsonld) == 1, f"expected one structured data block, found {len(HEAD.jsonld)}"
    data = json.loads(HEAD.jsonld[0])  # fails here if the JSON is invalid
    assert data["@context"] == "https://schema.org"
    return {node["@type"]: node for node in data["@graph"]}


def _all_keys(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(value, list):
        for v in value:
            yield from _all_keys(v)


def test_l01_title_is_only_the_brand_name():
    assert [t.strip() for t in HEAD.titles] == ["The Cement People"]
    assert BUSINESS["page"]["title"] == "The Cement People"


def test_l02_description_and_canonical():
    desc = [m.get("content") for m in HEAD.metas if m.get("name") == "description"]
    assert desc == [BUSINESS["page"]["description"]], desc
    assert 50 <= len(desc[0]) <= 200, "description should be a sentence or two"
    canon = [l.get("href") for l in HEAD.links if l.get("rel") == "canonical"]
    assert canon == [CANONICAL], canon
    # Nothing tells search engines to stay away.
    robots_meta = [m for m in HEAD.metas if m.get("name") in ("robots", "googlebot")]
    assert not any("noindex" in (m.get("content") or "") for m in robots_meta)


def test_l03_structured_data_is_valid_and_linked():
    g = _graph()
    assert set(g) == {"Store", "WebSite", "WebPage"}, set(g)
    store, site, page = g["Store"], g["WebSite"], g["WebPage"]
    assert store["@id"] == f"{SITE}/#store" and store["url"] == CANONICAL
    assert site["publisher"] == {"@id": store["@id"]} and site["url"] == CANONICAL
    assert page["isPartOf"] == {"@id": site["@id"]} and page["about"] == {"@id": store["@id"]}
    assert page["url"] == CANONICAL and page["name"] == "The Cement People"


def test_l04_structured_data_contains_only_confirmed_details():
    store = _graph()["Store"]
    assert set(store) <= STORE_PROPERTIES, f"unexpected properties: {set(store) - STORE_PROPERTIES}"
    assert store["name"] == BUSINESS["name"]
    assert store["description"] == BUSINESS["page"]["description"]
    assert store["telephone"] == BUSINESS["phoneInternational"]
    assert store["email"] == BUSINESS["publicEmail"]
    a, ba = store["address"], BUSINESS["address"]
    assert a == {"@type": "PostalAddress", "streetAddress": f"{ba['street']}, {ba['area']}",
                 "addressLocality": ba["locality"], "addressRegion": ba["region"],
                 "addressCountry": ba["countryCode"]}
    assert store["geo"] == {"@type": "GeoCoordinates", **BUSINESS["geo"]}
    assert store["hasMap"] == BUSINESS["mapUrl"]
    assert store["openingHoursSpecification"] == [
        {"@type": "OpeningHoursSpecification", "dayOfWeek": b["days"],
         "opens": b["opens"], "closes": b["closes"]} for b in BUSINESS["openingHours"]]
    # Delivery areas are places served, not extra shops.
    assert store["areaServed"] == [{"@type": "Place", "name": n} for n in BUSINESS["deliveryAreas"]]
    assert store["currenciesAccepted"] == BUSINESS["currencyCode"]
    found = set(_all_keys(json.loads(HEAD.jsonld[0]))) & FORBIDDEN_KEYS
    assert not found, f"structured data must not contain {found}"
    # Exactly one business location.
    assert HEAD.jsonld[0].count('"PostalAddress"') == 1


def test_l05_robots_txt_lets_search_engines_in_and_names_the_sitemap():
    text = (ROOT / "robots.txt").read_text(encoding="utf-8")
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(text.splitlines())
    for agent in ("Googlebot", "Bingbot", "*"):
        assert rp.can_fetch(agent, CANONICAL), f"{agent} is blocked"
    assert rp.site_maps() == [f"{SITE}/sitemap.xml"]


def test_l06_sitemap_is_valid_and_lists_the_homepage():
    tree = ET.parse(ROOT / "sitemap.xml")  # fails here if the XML is invalid
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    assert tree.getroot().tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset"
    locs = [e.text for e in tree.getroot().findall("s:url/s:loc", ns)]
    assert locs == [CANONICAL], locs


def test_l07_github_pages_publishes_robots_and_sitemap():
    # _config.yml lists what the GitHub Pages build leaves out. Make sure the
    # two new root files are not caught by it.
    config = (ROOT / "_config.yml").read_text(encoding="utf-8")
    excluded = re.findall(r"^\s*-\s*(\S+)", config, re.M)
    for name in ("robots.txt", "sitemap.xml", "index.html"):
        assert name not in excluded, f"{name} is excluded from the published site"
        assert not name.startswith(("_", ".")), "Jekyll skips files starting with _ or ."
        # Jekyll would process a file starting with '---' as a template.
        assert not (ROOT / name).read_text(encoding="utf-8").startswith("---")


ASTRO_BUILD = os.environ.get("TCP_SITE_URL", "").startswith("http://127.0.0.1:4321")


@pytest.mark.skipif(ASTRO_BUILD, reason="checks the live single-file site's print code")
def test_l08_title_goes_back_to_normal_after_printing(browser):
    page, errors = open_site(browser)
    page.evaluate("dispatchEvent(new Event('beforeprint'))")
    assert page.title().startswith("The Cement People Estimate TCP-"), page.title()
    page.evaluate("dispatchEvent(new Event('afterprint'))")
    assert page.title() == "The Cement People"
    assert not errors, errors
    page.context.close()
