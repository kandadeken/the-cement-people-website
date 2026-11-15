"""
Page and script always match (added 15 Nov 2026).

  K01  the page loads quote-engine.js with a fingerprint in its address
       ("?v=..."), and the fingerprint is the one for the script actually
       being served. So a browser holding an older copy of the script can
       never pair it with a newer page.

Why: just after the design-system update went live, a desktop browser that
still held the previous script got the new page with it. The old script
stopped part-way (it looked for the category cards, which the new page no
longer has), and the Iron Rods tabs did nothing until the browser fetched
the new script.

Astro build only; the single-file page has its script inside the page.
"""
import hashlib
import re
import urllib.request

import pytest

from conftest import SITE_URL


def test_k01_script_address_carries_its_fingerprint():
    if not SITE_URL.startswith("http"):
        pytest.skip("applies to the Astro build only")
    html = urllib.request.urlopen(SITE_URL).read().decode()
    if 'id="tcp-data"' not in html:
        pytest.skip("applies to the Astro build only")
    m = re.search(r'<script src="(/scripts/quote-engine\.js)\?v=([0-9a-f]{10})"', html)
    assert m, "quote-engine.js is linked without a ?v= fingerprint"
    script = urllib.request.urlopen(SITE_URL.rstrip("/") + m.group(1)).read()
    assert hashlib.sha256(script).hexdigest()[:10] == m.group(2), "fingerprint does not match the script being served"
