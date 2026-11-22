"""
Invoice Desk on Supabase, phase 1 (21 Nov 2026). "TCP Invoice Desk on
Supabase: Design (v2.1)", approved by ChatGPT and Daniel.

These tests drive the desk's screens in a real (headless) Chrome. The
database is replaced by a STAND-IN (STANDIN below): a small in-memory copy of
the database functions the desk calls, which keeps the same rules the desk
relies on (numbering only on issue, frozen "billed to" at issue, one draft per
request id, staff-only access). The real database rules are tested on
Postgres by supabase/run-tests.sh, and end to end on the tcp-test project
from Daniel's phone. The stand-in exists because a local copy of Supabase's
API server could not be installed in the build environment.

  S01  kept out of search engines; not in the sitemap; no link to it
  S02  a build without database settings says "Not connected"
  S03  signing in: email, then the 6-digit code (or the email's link); a
       wrong code is refused;
       someone who is not active staff sees "No access"; finance too
  S04  a real estimate from the home page fills in every item, matched to
       the database price list, with the drop-off location
  S05  the customer: a phone number finds existing customers (shared
       numbers allowed); a new customer is added only once, on save
  S06  saving a draft: a dropped connection keeps the work on the phone
       and says so; the retry uses the SAME request id, so one draft only
  S07  issuing: the number comes from the database; the invoice becomes
       read-only; the PDF is drawn from the database record (A4, INVOICE,
       the name as issued even after the customer is renamed, every line,
       the database total) and the WhatsApp line names the invoice
  S08  removing access: the next action clears the screen and the phone's
       memory and signs out
  S09  an issued invoice is reopened from the database after a reload,
       never from the phone's copy
  S10  fits a 360 px and a 390 px phone without sideways scrolling
  S11  an expired sign-in keeps the unsent invoice; it returns after signing in
  S12  removed access: an empty lookup is checked and signs out; "No access"
       when opening the desk
  S13  a customer with no phone number, answer lost: added once (request id)
  S14  the sign-out notice from Supabase: no calls made inside its lock
  S15  an expired or used sign-in link says so, and the address is tidied
  S16  with the free-plan email (link only), no code box is shown
"""
import base64
import io
import json
import re
import urllib.parse

import pytest
from pypdf import PdfReader

from conftest import PRODUCTS, SITE_URL, settle, tidy_pdf_text, whatsapp_message

ASTRO = SITE_URL.startswith("http")
DESK = urllib.parse.urljoin(SITE_URL, "invoice-desk/")
pytestmark = pytest.mark.skipif(not ASTRO, reason="the Invoice Desk is part of the Astro build only")

# The price list as the database holds it: numeric ids, the website's id as
# site_id, current_price.
DB_PRODUCTS = [{"id": i + 1, "site_id": p["id"], "name": p["name"], "category": p["category"],
                "unit": p["unit"], "current_price": p["price"]} for i, p in enumerate(PRODUCTS)]
BY_SITE = {p["site_id"]: p for p in DB_PRODUCTS}

OWNER = {"id": "u-owner", "email": "owner@test.invalid"}

# The stand-in for Supabase. window.TCPDeskApi replaces the real connection
# (see section 2 of public/scripts/invoice-desk.js). window.__db lets a test
# look inside, switch the connection off, or remove someone's access.
STANDIN = r"""
(() => {
  const cfg = JSON.parse(%CFG%);
  const db = window.__db = {
    products: cfg.products, staff: cfg.staff, users: cfg.users,
    customers: [], invoices: [], lines: [], counters: {customer: 0, invoice: 0},
    offline: false, offlineOnce: 0, dropReply: 0, expired: false, calls: [], session: null,
    signOutFns: [], inAuthCallback: false, lockViolations: [],
  };
  // Like Supabase: the sign-out notice is delivered while the sign-in lock is
  // held. Any call made during it is recorded as a violation (on a real
  // phone it can freeze the page).
  db.fireSignOut = () => { db.session = null; sessionStorage.removeItem("standin-session");
    db.inAuthCallback = true; try { db.signOutFns.forEach(f => f()); } finally { db.inAuthCallback = false; } };
  try { const s = sessionStorage.getItem("standin-session"); if (s) db.session = JSON.parse(s); } catch (e) {}
  try { const d = sessionStorage.getItem("standin-db"); if (d) Object.assign(db, JSON.parse(d), {calls: []}); } catch (e) {}
  const persist = () => { try { sessionStorage.setItem("standin-db", JSON.stringify(
      {customers: db.customers, invoices: db.invoices, lines: db.lines, counters: db.counters, staff: db.staff})); } catch (e) {} };
  const pad = n => String(n).padStart(4, "0");
  const net = async (name, fn) => {
    if (db.inAuthCallback) db.lockViolations.push(name);
    db.calls.push(name);
    await new Promise(r => setTimeout(r, 5));
    if (db.offline || db.offlineOnce > 0) { if (db.offlineOnce > 0) db.offlineOnce--; throw new TypeError("Failed to fetch"); }
    if (db.expired && db.session) throw Object.assign(new Error("JWT expired"), {code: "PGRST301", status: 401});
    const out = fn(); persist();
    // The database did the work, but the answer was lost on the way back.
    if (db.dropReply > 0) { db.dropReply--; throw new TypeError("Failed to fetch"); }
    return JSON.parse(JSON.stringify(out === undefined ? null : out));
  };
  const me = () => db.session && db.staff.find(s => s.user_id === db.session.id && s.active);
  // Plain reads under row-level security: empty, not refused, for non-staff.
  const rlsRead = rows => me() ? rows : [];
  const staffOnly = (...roles) => { const s = me();
    if (!s) throw Object.assign(new Error("Not allowed: only TCP staff can do this"), {code: "42501"});
    if (roles.length && !roles.includes(s.role)) throw Object.assign(new Error("Not allowed: the " + s.role + " role cannot do this"), {code: "42501"}); };
  const phone = p => { const d = String(p || "").replace(/\D/g, ""); if (!d) return null;
    if (d.length === 10 && d[0] === "0") return "+233" + d.slice(1); if (d.length === 12 && d.startsWith("233")) return "+" + d; if (d.length === 9) return "+233" + d;
    throw new Error("Not a Ghana phone number: " + p); };
  const total = id => db.lines.filter(l => l.invoice_id === id).reduce((a, l) => a + Math.round(l.quantity * l.unit_price * 100), 0) / 100;
  window.TCPDeskApi = {
    emailCode: cfg.emailCode,
    sendCode: email => net("sendCode", () => { db.codeFor = email; }),
    verifyCode: (email, code) => net("verifyCode", () => {
      if (code !== "123456" || email !== db.codeFor) throw new Error("Token has expired or is invalid");
      const u = db.users.find(x => x.email === email); if (!u) throw new Error("Signups not allowed");
      db.session = u; sessionStorage.setItem("standin-session", JSON.stringify(u)); return {user: u}; }),
    user: async () => db.session,
    signOut: async () => { if (db.inAuthCallback) db.lockViolations.push("signOut");
      const was = db.session; db.session = null; sessionStorage.removeItem("standin-session"); db.calls.push("signOut");
      if (was) { db.inAuthCallback = true; try { db.signOutFns.forEach(f => f()); } finally { db.inAuthCallback = false; } } },
    onSignOut: fn => { db.signOutFns.push(fn); },
    myStaff: () => net("myStaff", () => { staffOnly(); const s = me(); return {full_name: s.full_name, role: s.role}; }),
    products: () => net("products", () => rlsRead(db.products)),
    customersWithPhone: p => net("customersWithPhone", () => { const ph = phone(p); return rlsRead(db.customers.filter(c => c.phone === ph)); }),
    createCustomer: (p, name, req) => net("createCustomer", () => { staffOnly("owner", "sales");
      if (!p && !name) throw new Error('violates check constraint "customer_needs_phone_or_name"');
      const again = req && db.customers.find(c => c.request_id === req);
      if (again) { if (again.phone !== phone(p) || again.name !== (name || null)) throw new Error("This request id was already used for a different customer"); return again; }
      const c = {id: db.customers.length + 1, code: "TCP-C-" + pad(++db.counters.customer), phone: phone(p), name: name || null, request_id: req || null};
      db.customers.push(c); return c; }),
    saveDraft: a => net("saveDraft", () => { staffOnly("owner", "sales");
      let inv = a.p_invoice_id ? db.invoices.find(i => i.id === a.p_invoice_id) : (a.p_request_id && db.invoices.find(i => i.request_id === a.p_request_id));
      if (!inv) { inv = {id: db.invoices.length + 1, state: "draft", invoice_no: null, request_id: a.p_request_id}; db.invoices.push(inv); }
      if (inv.state !== "draft") throw new Error("Only a draft invoice can be changed");
      Object.assign(inv, {customer_id: a.p_customer_id, deliver_to_location: a.p_deliver_to_location, deliver_to_contact: a.p_deliver_to_contact,
        deliver_to_phone: phone(a.p_deliver_to_phone), due_date: a.p_due_date, notes: a.p_notes});
      db.lines = db.lines.filter(l => l.invoice_id !== inv.id);
      a.p_lines.forEach((l, i) => { const p = db.products.find(x => x.id === l.product_id);
        db.lines.push({invoice_id: inv.id, position: i + 1, kind: l.kind, product_id: l.product_id || null,
          description: l.description || (p && p.name), unit: l.unit || (p && p.unit), quantity: +l.quantity,
          unit_price: l.unit_price != null ? +l.unit_price : p.current_price}); });
      return inv.id; }),
    issue: id => net("issue", () => { staffOnly("owner", "sales"); const inv = db.invoices.find(i => i.id === id);
      if (!inv || inv.state !== "draft") throw new Error("Only a draft invoice can be issued");
      if (total(id) <= 0) throw new Error("An invoice total must be more than zero");
      const c = db.customers.find(x => x.id === inv.customer_id);
      Object.assign(inv, {state: "issued", invoice_no: "TCP-INV-" + pad(++db.counters.invoice), issued_at: new Date().toISOString(),
        issued_by: me().full_name, billed_to_name: c.name, billed_to_phone: c.phone}); return inv.invoice_no; }),
    document: id => net("document", () => { staffOnly(); const inv = db.invoices.find(i => i.id === id);
      if (!inv) throw new Error("No such invoice"); const c = db.customers.find(x => x.id === inv.customer_id);
      const issued = !!inv.invoice_no, t = total(id);
      return {id: inv.id, invoice_no: inv.invoice_no, state: inv.state, status: inv.state === "draft" ? "draft" : "unpaid",
        issued_at: inv.issued_at || null, issued_by: inv.issued_by || null, due_date: inv.due_date, notes: inv.notes,
        customer_id: inv.customer_id, customer_code: c.code,
        billed_to_name: issued ? inv.billed_to_name : c.name, billed_to_phone: issued ? inv.billed_to_phone : c.phone,
        deliver_to_location: inv.deliver_to_location, deliver_to_contact: inv.deliver_to_contact, deliver_to_phone: inv.deliver_to_phone,
        lines: db.lines.filter(l => l.invoice_id === id).map(l => ({...l, line_total: Math.round(l.quantity * l.unit_price * 100) / 100})),
        total: t, paid: 0, balance: t, payments: []}; }),
  };
})();
"""


def _standin(staff=None, users=None, email_code=True):
    # email_code: the sign-in email carries a 6-digit code (TCP's own email
    # sending). False is today's free-plan email: a link only.
    cfg = {"products": DB_PRODUCTS, "emailCode": email_code,
           "staff": staff if staff is not None else [{"user_id": OWNER["id"], "full_name": "Test Owner", "role": "owner", "active": True}],
           "users": users if users is not None else [OWNER]}
    return STANDIN.replace("%CFG%", json.dumps(json.dumps(cfg)))


def _desk(browser, width=390, standin=True, signed_in=True, **kw):
    ctx = browser.new_context(viewport={"width": width, "height": 844}, device_scale_factor=2,
                              is_mobile=True, has_touch=True, locale="en-US")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    if standin:
        # Signed in already (as after S03), set before the stand-in starts.
        if signed_in:
            page.add_init_script("sessionStorage.setItem('standin-session', JSON.stringify(%s))" % json.dumps(OWNER))
        page.add_init_script(_standin(**kw))
    page.goto(DESK, wait_until="load")
    return page, errors


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


def _ready_invoice(page, browser, name="Ama Owusu", phone="0241234567", fee="350"):
    page.wait_for_selector("#tool:not([hidden])")
    page.fill("#paste", _estimate_message(browser, ORDER, loc="Buduburam"))
    page.click("#readBtn")
    page.wait_for_selector("#form:not([hidden])")
    page.fill("#cPhone", phone)
    page.dispatch_event("#cPhone", "change")
    page.fill("#cName", name)
    page.check('input[name="dl"][value="fee"]')
    page.fill("#fee", fee)


def _pdf(page):
    b64 = page.evaluate("async () => (await TCPDesk.makePdf(TCPDesk.doc())).output('datauristring').split(',')[1]")
    reader = PdfReader(io.BytesIO(base64.b64decode(b64)))
    return [tidy_pdf_text(p.extract_text()) for p in reader.pages], [(float(p.mediabox.width), float(p.mediabox.height)) for p in reader.pages]


# ---- S01 ----------------------------------------------------------------------
def test_s01_kept_out_of_search_engines(browser):
    page, errors = _desk(browser, standin=False)
    robots = page.locator('meta[name="robots"]').get_attribute("content")
    assert "noindex" in robots and "nofollow" in robots
    page.goto(urllib.parse.urljoin(SITE_URL, "sitemap.xml"))
    assert "invoice-desk" not in page.content()
    page.goto(SITE_URL, wait_until="load")
    assert page.locator('a[href*="invoice-desk"]').count() == 0
    assert not errors


# ---- S02 ----------------------------------------------------------------------
def test_s02_not_connected_without_settings(browser):
    # The test build has no database settings (as on a fork or a preview).
    page, errors = _desk(browser, standin=False)
    settings = json.loads(page.locator("#desk-data").text_content())
    if settings["supabaseUrl"]:
        pytest.skip("this build is connected to a database")
    assert page.locator("#setup").is_visible()
    assert not page.locator("#signin").is_visible() and not page.locator("#tool").is_visible()
    assert not errors


# ---- S03 ----------------------------------------------------------------------
def test_s03_sign_in_with_email_code(browser):
    page, errors = _desk(browser, signed_in=False)
    page.wait_for_selector("#signin:not([hidden])")
    assert not page.locator("#tool").is_visible()
    page.fill("#email", OWNER["email"])
    page.click("#emailForm button")
    page.wait_for_selector("#codeForm:not([hidden])")
    assert "sign-in email was sent" in page.text_content("#signMsg")
    page.fill("#code", "999999")
    page.click("#codeForm button")
    page.wait_for_function("document.querySelector('#signMsg').textContent.includes('not right')")
    assert not page.locator("#tool").is_visible()
    page.fill("#code", "123 456")
    page.click("#codeForm button")
    page.wait_for_selector("#tool:not([hidden])")
    assert "Test Owner" in page.text_content("#who")
    assert not errors


def test_s03_not_staff_and_finance_see_no_access(browser):
    stranger = {"id": "u-x", "email": "x@test.invalid"}
    page, _ = _desk(browser, signed_in=False, users=[stranger], staff=[])
    page.fill("#email", stranger["email"]); page.click("#emailForm button")
    page.wait_for_selector("#codeForm:not([hidden])")
    page.fill("#code", "123456"); page.click("#codeForm button")
    page.wait_for_selector("#noaccess:not([hidden])")
    assert stranger["email"] in page.text_content("#noEmail")
    assert not page.locator("#tool").is_visible()
    assert "products" not in page.evaluate("__db.calls")

    fin = {"id": "u-f", "email": "f@test.invalid"}
    page, _ = _desk(browser, signed_in=False, users=[fin],
                    staff=[{"user_id": "u-f", "full_name": "Fin", "role": "finance", "active": True}])
    page.fill("#email", fin["email"]); page.click("#emailForm button")
    page.wait_for_selector("#codeForm:not([hidden])")
    page.fill("#code", "123456"); page.click("#codeForm button")
    page.wait_for_selector("#noaccess:not([hidden])")
    assert "owner or sales" in page.text_content("#noWhy")


# ---- S04 ----------------------------------------------------------------------
def test_s04_estimate_fills_items_from_the_database_price_list(browser):
    page, errors = _desk(browser)
    page.wait_for_selector("#tool:not([hidden])")
    page.fill("#paste", _estimate_message(browser, ORDER, loc="Buduburam"))
    page.click("#readBtn")
    page.wait_for_selector("#form:not([hidden])")
    items = page.evaluate("TCPDesk.state().items")
    got = {i["pid"]: i["qty"] for i in items}
    assert got == {BY_SITE[k]["id"]: v for k, v in ORDER.items()}
    assert all(i["price"] == round(BY_SITE[k]["current_price"] * 100) for k in ORDER for i in items if i["pid"] == BY_SITE[k]["id"])
    assert page.input_value("#cSite") == "Buduburam"
    assert "Read 4 items" in page.text_content("#readMsg")
    assert not errors


# ---- S05 ----------------------------------------------------------------------
def test_s05_customer_found_by_phone_or_added_once(browser):
    page, errors = _desk(browser)
    page.wait_for_selector("#tool:not([hidden])")
    page.evaluate("""() => { __db.customers.push({id: 1, code: 'TCP-C-0001', phone: '+233241234567', name: 'Kwame Mensah'},
                                             {id: 2, code: 'TCP-C-0002', phone: '+233241234567', name: 'Kwame Brother'});
                             __db.counters.customer = 2; }""")
    page.click("#blankBtn")
    page.fill("#cPhone", "024 123 4567")
    page.dispatch_event("#cPhone", "change")
    page.wait_for_selector("[data-cid]")
    assert page.locator("[data-cid]").count() == 2
    page.click('[data-cid="1"]')
    assert page.input_value("#cName") == "Kwame Mensah"
    assert "TCP-C-0001" in page.text_content("#custPicked")
    page.select_option("#addSel", str(BY_SITE["c1"]["id"]))
    page.click("#addBtn")
    page.click("#saveBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent === 'Draft saved.'")
    assert page.evaluate("__db.customers.length") == 2, "an existing customer was used, none added"
    assert page.evaluate("__db.invoices[0].customer_id") == 1

    # A new number: added once, on save.
    page.click("#newBtn")
    page.click("#blankBtn")
    page.fill("#cPhone", "020 555 1234")
    page.dispatch_event("#cPhone", "change")
    page.wait_for_function("document.querySelector('#matches').textContent.includes('New customer')")
    page.fill("#cName", "Efua")
    page.select_option("#addSel", str(BY_SITE["c1"]["id"]))
    page.click("#addBtn")
    page.click("#saveBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent === 'Draft saved.'")
    assert page.evaluate("__db.customers.length") == 3
    assert page.evaluate("__db.customers[2].phone") == "+233205551234"
    assert not errors


# ---- S06 ----------------------------------------------------------------------
def test_s06_dropped_connection_keeps_work_and_retries_once(browser):
    page, errors = _desk(browser)
    _ready_invoice(page, browser)
    page.evaluate("__db.offline = true")
    page.click("#saveBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent.includes('no connection')")
    kept = page.evaluate("JSON.parse(localStorage.getItem('tcp-desk-work-u-owner'))")
    assert len(kept["items"]) == 4 and kept["name"] == "Ama Owusu"
    assert page.evaluate("__db.invoices.length") == 0

    # The database got the draft, but the answer was lost on the way back:
    # simulated by letting the save through, then failing the reply once.
    page.evaluate("__db.offline = false")
    req = kept["draftRequest"]
    page.evaluate("""async r => { const s = TCPDesk.state();
        await TCPDeskApi.createCustomer(s.phone, s.name);
        await TCPDeskApi.saveDraft({p_invoice_id: null, p_customer_id: 1, p_lines: [], p_request_id: r}); }""", req)
    page.click("#saveBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent === 'Draft saved.'")
    assert page.evaluate("__db.invoices.length") == 1, "the retry found the same draft (same request id)"
    assert page.evaluate("__db.invoices[0].request_id") == req
    assert page.evaluate("__db.customers.length") == 1, "the retry reused the customer already added"
    assert page.evaluate("__db.lines.length") == 5, "4 items and the delivery fee"
    assert not errors


# ---- S07 ----------------------------------------------------------------------
def test_s07_issue_number_from_database_and_pdf_from_record(browser):
    page, errors = _desk(browser)
    _ready_invoice(page, browser)
    page.click("#issueBtn")
    page.wait_for_selector("#issuedSec:not([hidden])")
    assert "TCP-INV-0001" in page.text_content("#issued")
    assert not page.locator("#form").is_visible(), "an issued invoice cannot be edited"
    assert "Test Owner" in page.text_content("#issued")

    # The customer is renamed afterwards; the issued invoice keeps the name.
    page.evaluate("__db.customers[0].name = 'Ama Renamed'")
    page.click("#pdfBtn")  # reads the record again, as Share does
    page.wait_for_function("!document.querySelector('#pdfBtn').disabled")
    texts, sizes = _pdf(page)
    text = " ".join(texts)
    assert all(abs(w - 595.28) < 1 and abs(h - 841.89) < 1 for w, h in sizes), "A4"
    assert "INVOICE" in text and "TCP-INV-0001" in text
    assert "Ama Owusu" in text and "Ama Renamed" not in text
    assert "TAX" not in text.upper().replace("TOTAL", "")
    for k in ORDER:
        assert BY_SITE[k]["name"] in text
    expected = sum(round(BY_SITE[k]["current_price"] * 100 * v) for k, v in ORDER.items()) + 35000
    total = page.evaluate("TCPDesk.doc().total")
    assert round(total * 100) == expected
    assert "GH₵" + f"{expected / 100:,.2f}" in text
    assert "Delivery to Buduburam" in text
    assert page.evaluate("TCPDesk.waText(TCPDesk.doc())") == "Hello Ama, here is your invoice TCP-INV-0001 from The Cement People."
    # Issuing again is impossible from the screen; the number was used once.
    assert page.evaluate("__db.counters.invoice") == 1
    assert not errors


# ---- S08 ----------------------------------------------------------------------
def test_s08_removed_access_clears_and_signs_out(browser):
    page, errors = _desk(browser)
    _ready_invoice(page, browser)
    page.click("#issueBtn")
    page.wait_for_selector("#issuedSec:not([hidden])")
    page.evaluate("__db.staff[0].active = false")
    page.click("#pdfBtn")
    page.wait_for_selector("#signin:not([hidden])")
    assert "access has ended" in page.text_content("#signMsg")
    assert not page.locator("#tool").is_visible()
    assert page.text_content("#issued") == ""
    assert page.evaluate("localStorage.getItem('tcp-desk-work-u-owner')") is None
    assert page.evaluate("TCPDesk.doc()") is None
    assert "signOut" in page.evaluate("__db.calls")
    assert not errors


# ---- S09 ----------------------------------------------------------------------
def test_s09_issued_invoice_reopens_from_the_database(browser):
    page, errors = _desk(browser)
    _ready_invoice(page, browser)
    page.click("#issueBtn")
    page.wait_for_selector("#issuedSec:not([hidden])")
    # Tamper with the phone's copy: it must not be used for an issued invoice.
    page.evaluate("""() => { const k = 'tcp-desk-work-u-owner', s = JSON.parse(localStorage.getItem(k));
                             s.name = 'From the phone'; localStorage.setItem(k, JSON.stringify(s)); }""")
    page.reload(wait_until="load")
    page.wait_for_selector("#issuedSec:not([hidden])")
    assert "TCP-INV-0001" in page.text_content("#issued")
    assert "Ama Owusu" in page.text_content("#issued")
    assert "From the phone" not in page.text_content("#issued")
    assert not errors


# ---- S10 ----------------------------------------------------------------------
@pytest.mark.parametrize("width", [360, 390])
def test_s10_fits_a_phone(browser, width):
    page, errors = _desk(browser, width=width)
    _ready_invoice(page, browser)
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    page.click("#issueBtn")
    page.wait_for_selector("#issuedSec:not([hidden])")
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    for sel in ["#shareBtn", "#pdfBtn"]:
        box = page.locator(sel).bounding_box()
        assert box["height"] >= 44
    assert not errors


# ---- After ChatGPT's review of PR #35 ------------------------------------------

def _sign_in(page):
    page.wait_for_selector("#signin:not([hidden])")
    page.fill("#email", OWNER["email"]); page.click("#emailForm button")
    page.wait_for_selector("#codeForm:not([hidden])")
    page.fill("#code", "123456"); page.click("#codeForm button")


# S11: an expired sign-in is not removed access: the unsent invoice is kept
# and comes back after signing in again.
def test_s11_expired_sign_in_keeps_unsent_work(browser):
    page, errors = _desk(browser)
    _ready_invoice(page, browser)
    page.evaluate("__db.expired = true")
    page.click("#saveBtn")
    page.wait_for_selector("#signin:not([hidden])")
    assert "expired" in page.text_content("#signMsg") and "kept" in page.text_content("#signMsg")
    assert not page.locator("#tool").is_visible()
    assert page.evaluate("TCPDesk.state().items.length") == 0, "nothing left in the page's memory"
    kept = page.evaluate("JSON.parse(localStorage.getItem('tcp-desk-work-u-owner'))")
    assert len(kept["items"]) == 4 and kept["name"] == "Ama Owusu"
    page.evaluate("__db.expired = false")
    _sign_in(page)
    page.wait_for_selector("#form:not([hidden])")
    assert page.input_value("#cName") == "Ama Owusu"
    assert len(page.evaluate("TCPDesk.state().items")) == 4
    page.click("#saveBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent === 'Draft saved.'")
    assert page.evaluate("__db.invoices.length") == 1
    assert not errors


# S12: once access is removed, a phone lookup comes back EMPTY (row-level
# security), not refused. The desk must sign out, not offer "New customer".
def test_s12_empty_lookup_after_removal_signs_out(browser):
    page, errors = _desk(browser)
    _ready_invoice(page, browser, phone="0200000000")
    page.evaluate("__db.staff[0].active = false")
    page.click("#newBtn")
    page.click("#blankBtn")
    page.fill("#cPhone", "0241234567")
    page.dispatch_event("#cPhone", "change")
    page.wait_for_selector("#signin:not([hidden])")
    assert "access has ended" in page.text_content("#signMsg")
    assert page.evaluate("localStorage.getItem('tcp-desk-work-u-owner')") is None
    assert not errors


# S12b: opening the desk after removal: "No access", and any work left on
# the phone from before is removed.
def test_s12b_removed_staff_opening_the_desk(browser):
    page, errors = _desk(browser, staff=[{"user_id": OWNER["id"], "full_name": "Test Owner", "role": "owner", "active": False}])
    page.wait_for_selector("#noaccess:not([hidden])")
    assert "products" not in page.evaluate("__db.calls")
    assert not errors


# S13: a new customer with no phone number, and the answer lost on the way
# back: the retry uses the same request id, so there is no twin.
def test_s13_customer_without_phone_added_once(browser):
    page, errors = _desk(browser)
    page.wait_for_selector("#tool:not([hidden])")
    page.click("#blankBtn")
    page.fill("#cName", "Site foreman Yaw")
    page.select_option("#addSel", str(BY_SITE["c1"]["id"]))
    page.click("#addBtn")
    page.evaluate("__db.dropReply = 1")
    page.click("#saveBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent.includes('no connection')")
    assert page.evaluate("__db.customers.length") == 1, "the database did add them"
    page.click("#saveBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent === 'Draft saved.'")
    assert page.evaluate("__db.customers.length") == 1, "the retry returned the same customer"
    assert page.evaluate("__db.invoices.length") == 1
    assert not errors


# S14: Supabase signs the phone out by itself (the sign-in could not be
# renewed). The notice arrives while Supabase holds its sign-in lock: the
# desk makes no call during it, then treats it as an expired sign-in.
def test_s14_sign_out_notice_makes_no_calls_inside_the_lock(browser):
    page, errors = _desk(browser)
    _ready_invoice(page, browser)
    page.evaluate("__db.fireSignOut()")
    page.wait_for_selector("#signin:not([hidden])")
    assert page.evaluate("__db.lockViolations") == []
    assert "expired" in page.text_content("#signMsg")
    assert len(page.evaluate("JSON.parse(localStorage.getItem('tcp-desk-work-u-owner'))")["items"]) == 4
    # Our own sign-out (the button) clears everything, also without calls
    # inside the lock.
    _sign_in(page)
    page.wait_for_selector("#form:not([hidden])")
    page.click("#signOut")
    page.wait_for_selector("#signin:not([hidden])")
    assert page.evaluate("__db.lockViolations") == []
    assert page.evaluate("localStorage.getItem('tcp-desk-work-u-owner')") is None
    assert not errors


# S15: Supabase's free plan sends a link, not a code. A link that has
# expired or was already used comes back with the reason in the address.
def test_s15_expired_sign_in_link(browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(_standin())
    page.goto(DESK + "#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired",
              wait_until="load")
    page.wait_for_function("document.querySelector('#signMsg').textContent.includes('expired or was already used')")
    assert page.locator("#signin").is_visible()
    assert "error" not in page.url
    assert not errors


# S16: today's free-plan email has a link and no code, so after sending it
# the desk only says to open the link: no code box to confuse anyone.
def test_s16_link_only_email_shows_no_code_box(browser):
    page, errors = _desk(browser, signed_in=False, email_code=False)
    page.wait_for_selector("#signin:not([hidden])")
    page.fill("#email", OWNER["email"])
    page.click("#emailForm button")
    page.wait_for_function("document.querySelector('#signMsg').textContent.includes('Open its link')")
    assert "code" not in page.text_content("#signMsg").lower()
    assert not page.locator("#codeForm").is_visible()
    assert "sendCode" in page.evaluate("__db.calls")
    assert not errors
