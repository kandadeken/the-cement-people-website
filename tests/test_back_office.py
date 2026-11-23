"""
TCP Back Office, version 1 (22 Nov 2026), and the Invoice Desk (phase 1)
inside it. "TCP Back Office: Design Specification v1.1" and "TCP Invoice
Desk on Supabase: Design (v2.1)", both approved by ChatGPT and Daniel.

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

TCP Back Office v1.1 (spec section 10):
  B01  Home figures match the database; each figure opens its list
  B02  Home agrees with the list: every count, and "owed" = the balances
  B03  list order (newest started, then id), filters, paging without skips
       or repeats
  B17  every issued invoice shows its total and what is left; drafts and
       cancelled show none

Phase 1.1 (23 Nov 2026, "Phase 1 Acceptance: Technical Assessment and Fix
Plan", approved by ChatGPT and Daniel):
  F01  E-01 Share sends the PDF with no text; the message is copied once
  F02  C-02 wrong quantities and prices are flagged on their line as typed,
       Save and Issue name the line; fixing a value clears it
  F03  C-02 a GH₵0.00 price is a "Free item"; an all-free invoice cannot be
       issued; the delivery fee is checked the same way
  F04  C-01 adding a product already on the invoice adds to its quantity
  F05  C-01 the same product at an agreed price stays a separate line
  F06  C-01 lines made identical are flagged and can be combined; Save
       combines any left and says so; different prices are never combined
  F07  an issued invoice with repeated lines is shown as it was issued
  F08  badly formed numbers (1.2.3, 1,2,3, 1-2, 5-, --5) are "not a number";
       genuine formats (2,5 / 1,392.00 / 50,000 / 1.392,00 / GH₵98) read right
  F09  Issue never combines lines unseen: it combines, says so and stops;
       the next tap issues exactly what is shown
  F10  the PDF names a free item ("— Free item"), at GH₵0.00
  B04  phone search: four formats and a partial number find the same
       invoice; "233" is only removed when it is the country code
  B05  several matches are all listed; nothing is opened or chosen
  B06  number and name search
  B07  a draft from the list opens in the form, every field as saved
  B08  the "Johnny" case: save, sign out, sign in, the draft is in the list
  B09  unsaved changes: opening another draft asks first; Go back keeps them
  B10  an issued invoice opens read-only
  B11  finance: Home and the list; a draft opens read-only; no New invoice
  B12  discard draft: owner only, needs a reason, cancelled not deleted, one
       request for a double tap
  B13  removed access: an empty Home is checked and signs out
  B14  WhatsApp: the message is copied; a blocked clipboard shows Copy
  B15  /invoice-desk/ forwards with the query and the whole fragment kept;
       an old sign-in link and an expired link still work
  B16  every Back Office screen fits a 360 px and a 390 px phone
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
# The phase 1 tests (S01-S16) start on the New invoice screen; the Back
# Office tests (B01 onwards) start on Home.
BO = urllib.parse.urljoin(SITE_URL, "back-office/")
DESK = BO + "#/new"
OLD = urllib.parse.urljoin(SITE_URL, "invoice-desk/")
pytestmark = pytest.mark.skipif(not ASTRO, reason="the Invoice Desk is part of the Astro build only")

# The price list as the database holds it: numeric ids, the website's id as
# site_id, current_price.
DB_PRODUCTS = [{"id": i + 1, "site_id": p["id"], "name": p["name"], "category": p["category"],
                "unit": p["unit"], "current_price": p["price"]} for i, p in enumerate(PRODUCTS)]
BY_SITE = {p["site_id"]: p for p in DB_PRODUCTS}

OWNER = {"id": "u-owner", "email": "owner@test.invalid"}

# The stand-in for Supabase. window.TCPDeskApi replaces the real connection
# (see section 2 of public/scripts/back-office.js). window.__db lets a test
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
  // Status as invoice_summary works it out (payments: inv.paid).
  const today = new Date().toISOString().slice(0, 10);
  const status = inv => inv.state === "draft" ? "draft" : inv.state === "cancelled" ? "cancelled"
    : (inv.paid || 0) >= total(inv.id) ? "paid" : inv.due_date && inv.due_date < today ? "overdue" : (inv.paid || 0) > 0 ? "part_paid" : "unpaid";
  let clock = 0;
  const stamp = () => new Date(Date.UTC(2026, 10, 22, 8, 0, 0) + 1000 * (clock++)).toISOString();
  // invoice_list, as the view builds it.
  const listRow = inv => { const c = db.customers.find(x => x.id === inv.customer_id), t = total(inv.id);
    return {id: inv.id, invoice_no: inv.invoice_no, state: inv.state, status: status(inv), issued_at: inv.issued_at || null,
      created_at: inv.created_at, due_date: inv.due_date || null, total: t, balance: Math.round((t - (inv.paid || 0)) * 100) / 100,
      billed_to_name: inv.invoice_no ? inv.billed_to_name : c.name, billed_to_phone: inv.invoice_no ? inv.billed_to_phone : c.phone}; };
  // PostgREST "ilike" with * as the wildcard.
  const ilike = (v, pat) => v != null && new RegExp("^" + pat.split("*").map(p => p.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*") + "$", "i").test(String(v));
  // Test data straight into the "database" (as other staff would have made).
  db.seed = list => list.forEach(o => {
    let c = db.customers.find(x => x.phone === o.phone && x.name === o.name);
    if (!c) { c = {id: db.customers.length + 1, code: "TCP-C-" + pad(++db.counters.customer), phone: o.phone || null, name: o.name || null}; db.customers.push(c); }
    const inv = {id: db.invoices.length + 1, state: o.state || "draft", invoice_no: null, customer_id: c.id, due_date: o.due || null,
      paid: o.paid || 0, created_at: o.created_at || stamp(), notes: null, deliver_to_location: null};
    db.invoices.push(inv);
    (o.lines || [{qty: o.qty || 10}]).forEach((l, k) => db.lines.push({invoice_id: inv.id, position: k + 1, kind: "product",
      product_id: 1, description: "Supacem 32.5R", unit: "50 kg bag", quantity: l.qty, unit_price: l.price == null ? 75 : l.price}));
    if (inv.state !== "draft" && !o.never_issued) Object.assign(inv, {invoice_no: "TCP-INV-" + pad(++db.counters.invoice),
      issued_at: inv.created_at, issued_by: "Test Owner", billed_to_name: c.name, billed_to_phone: c.phone});
    if (o.state === "cancelled") inv.cancel_reason = "seeded";
    persist(); });
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
      if (!inv) { inv = {id: db.invoices.length + 1, state: "draft", invoice_no: null, request_id: a.p_request_id, created_at: stamp()}; db.invoices.push(inv); }
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
      return {id: inv.id, invoice_no: inv.invoice_no, state: inv.state, status: status(inv), cancel_reason: inv.cancel_reason || null, created_at: inv.created_at,
        issued_at: inv.issued_at || null, issued_by: inv.issued_by || null, due_date: inv.due_date, notes: inv.notes,
        customer_id: inv.customer_id, customer_code: c.code,
        billed_to_name: issued ? inv.billed_to_name : c.name, billed_to_phone: issued ? inv.billed_to_phone : c.phone,
        deliver_to_location: inv.deliver_to_location, deliver_to_contact: inv.deliver_to_contact, deliver_to_phone: inv.deliver_to_phone,
        lines: db.lines.filter(l => l.invoice_id === id).map(l => ({...l, line_total: Math.round(l.quantity * l.unit_price * 100) / 100})),
        total: t, paid: inv.paid || 0, balance: t - (inv.paid || 0), payments: []}; }),
    cancel: (id, reason) => net("cancel", () => { staffOnly("owner");
      if (!reason || !reason.trim()) throw new Error("A reason is needed to cancel an invoice");
      const inv = db.invoices.find(i => i.id === id);
      if (!inv || inv.state === "cancelled") throw new Error("Only a draft or issued invoice can be cancelled");
      Object.assign(inv, {state: "cancelled", cancel_reason: reason.trim()}); }),
    // back_office_home (runs with the caller's rights: zeros for non-staff).
    home: () => net("home", () => { const rows = me() ? db.invoices.map(listRow) : [], n = s => rows.filter(r => r.status === s).length;
      return {owed: rows.filter(r => ["unpaid", "part_paid", "overdue"].includes(r.status)).reduce((a, r) => a + r.balance, 0),
        unpaid: n("unpaid"), part_paid: n("part_paid"), overdue: n("overdue"), drafts: n("draft")}; }),
    // invoice_list with the desk's filters, newest first then id, paged.
    list: ({status: st, terms, offset, limit}) => net("list", () => {
      let rows = rlsRead(db.invoices.map(listRow));
      if (st === "owed") rows = rows.filter(r => ["unpaid", "part_paid", "overdue"].includes(r.status));
      else if (st && st !== "all") rows = rows.filter(r => r.status === st);
      if (terms && terms.length) rows = rows.filter(r => terms.some(t => ilike(r[t.col], t.pattern)));
      rows.sort((a, b) => (a.created_at < b.created_at) - (a.created_at > b.created_at) || b.id - a.id);
      db.lastTerms = terms;
      return {rows: rows.slice(offset, offset + limit), count: rows.length}; }),
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
    assert "invoice-desk" not in page.content() and "back-office" not in page.content()
    page.goto(SITE_URL, wait_until="load")
    assert page.locator('a[href*="invoice-desk"], a[href*="back-office"]').count() == 0
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


def test_s03_not_staff_sees_no_access(browser):
    stranger = {"id": "u-x", "email": "x@test.invalid"}
    page, _ = _desk(browser, signed_in=False, users=[stranger], staff=[])
    page.fill("#email", stranger["email"]); page.click("#emailForm button")
    page.wait_for_selector("#codeForm:not([hidden])")
    page.fill("#code", "123456"); page.click("#codeForm button")
    page.wait_for_selector("#noaccess:not([hidden])")
    assert stranger["email"] in page.text_content("#noEmail")
    assert not page.locator("#tool").is_visible()
    assert "products" not in page.evaluate("__db.calls")



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
    page.evaluate("""() => localStorage.setItem('tcp-desk-work-u-owner',
                             JSON.stringify({invoiceId: 1, dirty: false, name: 'From the phone', items: []}))""")
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
    page.click("#guardDiscard")   # the unsaved invoice: discard it
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



# ---- TCP Back Office v1.1 --------------------------------------------------------

def _bo(browser, width=390, route="#/", staff=None, users=None, seed=None, signed_in=True, perms=None, who=None):
    ctx = browser.new_context(viewport={"width": width, "height": 844}, device_scale_factor=2,
                              is_mobile=True, has_touch=True, locale="en-US", permissions=perms or [])
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    if signed_in:
        page.add_init_script("sessionStorage.setItem('standin-session', JSON.stringify(%s))" % json.dumps(who or OWNER))
    page.add_init_script(_standin(staff=staff, users=users))
    if seed:
        # Seeded once, before the first load (the stand-in keeps it per tab).
        page.add_init_script("if (!sessionStorage.getItem('seeded')) { window.__seed = %s; }" % json.dumps(seed))
        page.add_init_script("if (window.__seed) { __db.seed(window.__seed); sessionStorage.setItem('seeded', '1'); }")
    page.goto(BO + route, wait_until="load")
    page.wait_for_selector("#tool:not([hidden])")
    return page, errors


FIN = {"id": "u-f", "email": "fin@test.invalid"}
SALES = {"id": "u-s", "email": "sales@test.invalid"}
TEAM = [{"user_id": OWNER["id"], "full_name": "Test Owner", "role": "owner", "active": True},
        {"user_id": FIN["id"], "full_name": "Fin", "role": "finance", "active": True},
        {"user_id": SALES["id"], "full_name": "Sal", "role": "sales", "active": True}]
PAST, FUTURE = "2026-01-10", "2099-12-31"
# Each invoice: 10 bags x GH₵75 = GH₵750.
MIX = [
    {"name": "Kofi Draft", "phone": "+233201110001", "state": "draft"},
    {"name": "Ama Unpaid", "phone": "+233241234567", "state": "issued", "due": FUTURE},
    {"name": "Yaw Part", "phone": "+233552331234", "state": "issued", "due": FUTURE, "paid": 300},
    {"name": "Efua Paid", "phone": "+233271112223", "state": "issued", "due": FUTURE, "paid": 750},
    {"name": "Kwame Late", "phone": "+233501234000", "state": "issued", "due": PAST},
    {"name": "Esi Cancelled", "phone": "+233261110000", "state": "cancelled"},
]


def _list_count(page, status):
    page.evaluate("s => location.hash = '#/invoices' + (s === 'all' ? '' : '?status=' + s)", status)
    page.wait_for_function("document.querySelector('#listV') && !document.querySelector('#listV').hidden && !document.querySelector('#moreBtn').disabled")
    page.wait_for_timeout(100)
    return page.locator("#rows .dk-inv").count()


def test_b01_home_figures(browser):
    page, errors = _bo(browser, seed=MIX)
    page.wait_for_function("document.querySelector('#hOwed').textContent !== '—'")
    assert page.text_content("#hOwed") == "GH₵1,950.00"   # 750 + 450 left + 750
    assert [page.text_content(s) for s in ["#hUnpaid", "#hPart", "#hOverdue", "#hDrafts"]] == ["1", "1", "1", "1"]
    assert page.locator("#recent .dk-inv").count() == 5
    page.click('a.dk-fig[href="#/invoices?status=overdue"]')
    page.wait_for_function("location.hash === '#/invoices?status=overdue'")
    page.wait_for_selector("#rows .dk-inv")
    assert page.locator("#rows .dk-inv").count() == 1 and "Kwame Late" in page.text_content("#rows")
    assert not errors


def test_b02_home_agrees_with_the_list(browser):
    page, errors = _bo(browser, seed=MIX)
    page.wait_for_function("document.querySelector('#hOwed').textContent !== '—'")
    home = {k: int(page.text_content(s)) for k, s in [("unpaid", "#hUnpaid"), ("part_paid", "#hPart"), ("overdue", "#hOverdue"), ("draft", "#hDrafts")]}
    owed = page.text_content("#hOwed")
    for status, n in home.items():
        assert _list_count(page, status) == n, status
    # "Owed" = the balances ("… left") on the rows the list shows under Owed.
    _list_count(page, "owed")
    total = sum(float(t.replace("left", "").replace("GH₵", "").replace(",", "").strip())
                for t in page.locator("#rows .dk-left").all_text_contents())
    assert f"GH₵{total:,.2f}" == owed
    assert not errors


def test_b03_order_filters_and_paging(browser):
    # 35 drafts; ten of them started at the very same moment (a tie).
    seed = [{"name": f"Cust {i:02d}", "phone": f"+2332000000{i:02d}", "state": "draft",
             "created_at": "2026-11-22T09:00:00.000Z" if i < 10 else None} for i in range(35)]
    page, errors = _bo(browser, seed=seed, route="#/invoices")
    page.wait_for_selector("#rows .dk-inv")
    assert page.locator("#rows .dk-inv").count() == 30
    assert "35 invoices" in page.text_content("#listInfo")
    page.click("#moreBtn")
    page.wait_for_function("document.querySelectorAll('#rows .dk-inv').length === 35")
    ids = [int(x) for x in page.eval_on_selector_all("#rows .dk-inv", "els => els.map(e => e.dataset.id)")]
    assert len(set(ids)) == 35, "no invoice repeated or skipped across pages"
    rows = page.evaluate("() => __db.invoices.map(i => ({id: i.id, c: i.created_at}))")
    expected = [r["id"] for r in sorted(rows, key=lambda r: (r["c"], r["id"]), reverse=True)]
    assert ids == expected, "newest first, then the id: the tie always in the same order"
    assert not page.locator("#moreBtn").is_visible()
    # filters
    assert _list_count(page, "cancelled") == 0
    assert "No invoices match" in page.text_content("#rows")
    assert not errors


def _search(page, q):
    page.fill("#q", q)
    page.press("#q", "Enter")
    page.wait_for_function("q => location.hash.includes(encodeURIComponent(q).replace(/%20/g, '+')) || location.hash.includes('q=')", arg=q)
    page.wait_for_function("!document.querySelector('#moreBtn').disabled")
    page.wait_for_timeout(100)
    return page.eval_on_selector_all("#rows .dk-inv .dk-inv-who", "els => els.map(e => e.textContent)")


def test_b04_phone_search(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoices")
    page.wait_for_selector("#rows .dk-inv")
    for q in ["024 123 4567", "0241234567", "233241234567", "+233241234567", "+233 24 123 4567", "1234567"]:
        found = _search(page, q)
        assert any("Ama Unpaid" in f for f in found), q
    assert page.evaluate("TCPDesk.searchTerms('0241234567').find(t => t.col === 'billed_to_phone').pattern") == "*241234567*"
    assert page.evaluate("TCPDesk.searchTerms('+233241234567').find(t => t.col === 'billed_to_phone').pattern") == "*241234567*"
    # "233" is NOT removed unless it is the country code: here it is part of
    # the number (+233 55 233 1234), and it still finds it.
    assert page.evaluate("TCPDesk.searchTerms('233').find(t => t.col === 'billed_to_phone').pattern") == "*233*"
    assert page.evaluate("TCPDesk.searchTerms('2331234').find(t => t.col === 'billed_to_phone').pattern") == "*2331234*"
    found = _search(page, "2331234")
    assert any("Yaw Part" in f for f in found)
    # Characters that mean something to the database's filter syntax are dropped.
    assert all("," not in t["pattern"] and "(" not in t["pattern"] for t in page.evaluate("TCPDesk.searchTerms('a,b(c)')"))
    assert not errors


def test_b05_several_matches_all_listed(browser):
    seed = [{"name": "Kwame Mensah", "phone": "+233241234567", "state": "issued", "due": FUTURE},
            {"name": "Kwame Brother", "phone": "+233241234567", "state": "draft"},
            {"name": "Someone Else", "phone": "+233200000000", "state": "draft"}]
    page, errors = _bo(browser, seed=seed, route="#/invoices")
    page.wait_for_selector("#rows .dk-inv")
    found = _search(page, "0241234567")
    assert len(found) == 2 and any("Kwame Mensah" in f for f in found) and any("Kwame Brother" in f for f in found)
    assert page.locator("#listV").is_visible() and "#/invoices" in page.url, "nothing opened or chosen"
    found = _search(page, "kwame")
    assert len(found) == 2
    assert not errors


def test_b06_number_and_name_search(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoices")
    page.wait_for_selector("#rows .dk-inv")
    for q in ["0001", "INV-0001", "TCP-INV-0001"]:
        found = _search(page, q)
        assert any("Ama Unpaid" in f for f in found), q
    found = _search(page, "LATE")
    assert found == [f for f in found if "Kwame Late" in f] and len(found) == 1
    assert not errors


def test_b07_draft_opens_in_the_form(browser):
    page, errors = _bo(browser, route="#/new")
    _ready_invoice(page, browser)
    page.fill("#iNote", "Gate code 4411")
    page.click("#saveBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent === 'Draft saved.'")
    assert "#/invoice/1" in page.url
    page.click('#tabs a[data-tab="invoices"]')
    page.wait_for_selector('#rows .dk-inv[data-id="1"]')
    assert "Draft" in page.text_content('#rows .dk-inv[data-id="1"]')
    page.evaluate("localStorage.clear()")   # the phone forgets: the database must be enough
    page.click('#rows .dk-inv[data-id="1"]')
    page.wait_for_selector("#form:not([hidden])")
    assert page.input_value("#cName") == "Ama Owusu"
    assert page.input_value("#cSite") == "Buduburam"
    assert page.input_value("#iNote") == "Gate code 4411"
    assert page.input_value("#fee") == "350"
    assert len(page.evaluate("TCPDesk.state().items")) == 4
    assert not errors


def test_b08_draft_still_there_after_signing_out_and_in(browser):
    page, errors = _bo(browser, route="#/new")
    _ready_invoice(page, browser, name="Johnny")
    page.click("#saveBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent === 'Draft saved.'")
    page.click("#signOut")
    page.wait_for_selector("#signin:not([hidden])")
    assert page.evaluate("localStorage.getItem('tcp-desk-work-u-owner')") is None
    _sign_in(page)
    page.wait_for_selector("#tool:not([hidden])")
    page.click('#tabs a[data-tab="invoices"]')
    page.wait_for_selector("#rows .dk-inv")
    assert "Johnny" in page.text_content("#rows")
    assert page.text_content("#hDrafts") in ("—", "1")
    page.click("#rows .dk-inv")
    page.wait_for_selector("#form:not([hidden])")
    assert page.input_value("#cName") == "Johnny" and len(page.evaluate("TCPDesk.state().items")) == 4
    assert not errors


def test_b09_unsaved_changes_are_asked_about(browser):
    seed = [{"name": "Other Draft", "phone": "+233200000001", "state": "draft"}]
    page, errors = _bo(browser, seed=seed, route="#/new")
    _ready_invoice(page, browser)          # unsaved, new
    page.click('#tabs a[data-tab="invoices"]')
    page.wait_for_selector('#rows .dk-inv[data-id="1"]')
    page.click('#rows .dk-inv[data-id="1"]')
    page.wait_for_selector("#guard:not([hidden])")
    page.click("#guardBack")
    page.wait_for_selector("#guard", state="hidden")
    assert "#/invoices" in page.url and len(page.evaluate("TCPDesk.state().items")) == 4, "Go back changes nothing"
    page.click('#rows .dk-inv[data-id="1"]')
    page.wait_for_selector("#guard:not([hidden])")
    page.click("#guardSave")
    page.wait_for_selector("#form:not([hidden])")
    page.wait_for_function("document.querySelector('#cName').value === 'Other Draft'")
    assert page.evaluate("__db.invoices.length") == 2, "Save it saved the work in progress first"
    assert page.evaluate("__db.invoices[1].customer_id") != page.evaluate("__db.invoices[0].customer_id")
    assert not errors


def test_b10_issued_opens_read_only(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoices")
    page.wait_for_selector('#rows .dk-inv[data-id="2"]')
    page.click('#rows .dk-inv[data-id="2"]')
    page.wait_for_selector("#issuedSec:not([hidden])")
    assert not page.locator("#form").is_visible() and not page.locator("#saveBtn").is_visible()
    assert "TCP-INV-0001" in page.text_content("#viewTitle")
    assert "Supacem 32.5R" in page.text_content("#viewLines")
    assert page.locator("#shareBtn").is_visible() and page.locator("#pdfBtn").is_visible()
    assert not errors


def test_b11_finance_reads_only(browser):
    page, errors = _bo(browser, seed=MIX, staff=TEAM, users=[OWNER, FIN, SALES], who=FIN)
    page.wait_for_function("document.querySelector('#hOwed').textContent !== '—'")
    assert page.text_content("#hOwed") == "GH₵1,950.00"
    assert not page.locator("#tabNew").is_visible() and not page.locator("#hNew").is_visible()
    page.goto(BO + "#/invoice/1")       # the draft
    page.wait_for_selector("#issuedSec:not([hidden])")
    assert "Draft (read-only)" in page.text_content("#viewTitle")
    assert not page.locator("#form").is_visible()
    assert not page.locator("#shareRow").is_visible() and not page.locator("#discardBtn").is_visible()
    page.goto(BO + "#/new")
    page.wait_for_function("location.hash === '#/'")
    assert not page.locator("#form").is_visible()
    assert not errors


def test_b12_discard_draft(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/1")
    page.wait_for_selector("#form:not([hidden])")
    page.click("#discardBtn")
    page.wait_for_selector("#discardBox:not([hidden])")
    page.click("#discardYes")
    assert "reason" in page.text_content("#discardMsg")
    assert page.evaluate("__db.invoices[0].state") == "draft"
    page.fill("#discardWhy", "Customer bought elsewhere")
    page.evaluate("() => { const b = document.querySelector('#discardYes'); b.click(); b.click(); }")   # double tap
    page.wait_for_selector("#issuedSec:not([hidden])")
    assert page.evaluate("__db.calls.filter(c => c === 'cancel').length") == 1, "one request for a double tap"
    assert page.evaluate("__db.invoices[0].state") == "cancelled"
    assert page.evaluate("__db.invoices.length") == 6, "nothing deleted"
    assert "Customer bought elsewhere" in page.text_content("#issued")
    assert _list_count(page, "cancelled") == 2 and _list_count(page, "draft") == 0
    # Sales sees no Discard button.
    page2, _ = _bo(browser, seed=MIX, staff=TEAM, users=[OWNER, FIN, SALES], who=SALES, route="#/invoice/1")
    page2.wait_for_selector("#form:not([hidden])")
    assert not page2.locator("#discardBtn").is_visible()
    assert not errors


def test_b13_removed_access_on_home(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoices")
    page.wait_for_selector("#rows .dk-inv")
    page.evaluate("__db.staff[0].active = false")
    page.click('#tabs a[data-tab="home"]')
    page.wait_for_selector("#signin:not([hidden])")
    assert "access has ended" in page.text_content("#signMsg")
    assert page.locator("#recent .dk-inv").count() == 0
    assert not errors


def test_b14_whatsapp_message_copied(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/2", perms=["clipboard-read", "clipboard-write"])
    page.wait_for_selector("#issuedSec:not([hidden])")
    page.click("#shareBtn")
    page.wait_for_function("document.querySelector('#iMsg').textContent.includes('Message copied')")
    assert "paste it as the caption" in page.text_content("#iMsg")
    assert page.evaluate("navigator.clipboard.readText()") == "Hello Ama, here is your invoice TCP-INV-0001 from The Cement People."
    # The clipboard blocked: the message is shown with a Copy button.
    page.evaluate("() => { navigator.clipboard.writeText = () => Promise.reject(new Error('blocked')); }")
    page.click("#shareBtn")
    page.wait_for_selector("#copyBox:not([hidden])")
    assert page.input_value("#copyText") == "Hello Ama, here is your invoice TCP-INV-0001 from The Cement People."
    assert not errors


def _arrivals(browser, url, signed_in=False):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    # Record every address the browser arrives at, before any script tidies it.
    page.add_init_script("if (location.pathname.includes('back-office')) sessionStorage.setItem('arrived', location.href)")
    if signed_in:
        page.add_init_script("sessionStorage.setItem('standin-session', JSON.stringify(%s))" % json.dumps(OWNER))
    page.add_init_script(_standin())
    page.goto(url, wait_until="load")
    page.wait_for_function("location.pathname.endsWith('/back-office/')")
    page.wait_for_load_state("load")
    return page, page.evaluate("sessionStorage.getItem('arrived')")


def test_b15_old_address_forwards_everything(browser):
    frag = "#access_token=abc.def-ghi&expires_in=3600&refresh_token=xyz&token_type=bearer&type=magiclink"
    page, arrived = _arrivals(browser, OLD + frag, signed_in=True)
    assert arrived == BO + frag, "the whole fragment, character for character"
    page.wait_for_selector("#tool:not([hidden])")
    page.wait_for_function("!location.hash.includes('access_token')")   # then tidied away
    page, arrived = _arrivals(browser, OLD + "?a=1&b=two#x")
    assert arrived == BO + "?a=1&b=two#x"
    page, arrived = _arrivals(browser, OLD + "#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired")
    assert arrived.endswith("error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired")
    page.wait_for_function("document.querySelector('#signMsg').textContent.includes('expired or was already used')")
    # A new link straight to the Back Office.
    page, arrived = _arrivals(browser, BO + frag, signed_in=True)
    page.wait_for_selector("#tool:not([hidden])")
    # The old page itself is noindex and has a no-script link.
    ctx = browser.new_context(java_script_enabled=False)
    p2 = ctx.new_page(); p2.goto(OLD)
    assert "noindex" in p2.locator('meta[name="robots"]').get_attribute("content")
    assert p2.locator('noscript').count() == 1


@pytest.mark.parametrize("width", [360, 390])
@pytest.mark.parametrize("route", ["#/", "#/invoices", "#/invoice/2", "#/invoice/1"])
def test_b16_fits_a_phone(browser, route, width):
    page, errors = _bo(browser, width=width, seed=MIX, route=route)
    page.wait_for_timeout(400)
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    for a in page.locator("#tabs a").all():
        if a.is_visible():
            assert a.bounding_box()["height"] >= 44
    assert not errors



def test_b17_issued_invoices_show_what_is_left(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoices")
    page.wait_for_selector("#rows .dk-inv")
    def shown(i):
        row = page.locator(f'#rows .dk-inv[data-id="{i}"]')
        left = row.locator(".dk-left")
        return (row.locator(".dk-inv-bot b").evaluate("b => b.firstChild.textContent"),
                left.text_content() if left.count() else None)
    assert shown(2) == ("GH₵750.00", "GH₵750.00 left"), "unpaid: total and balance"
    assert shown(3) == ("GH₵750.00", "GH₵450.00 left"), "part paid"
    assert shown(4) == ("GH₵750.00", "GH₵0.00 left"), "paid"
    assert shown(5) == ("GH₵750.00", "GH₵750.00 left"), "overdue"
    assert shown(1) == ("GH₵750.00", None) and shown(6) == ("GH₵750.00", None), "draft and cancelled owe nothing"
    assert "newest first, by date started" in page.text_content("#listInfo")
    assert not errors



# ---- Phase 1.1 ---------------------------------------------------------------------

def _blank_with(page, *site_ids):
    page.click("#blankBtn")
    page.wait_for_selector("#form:not([hidden])")
    page.fill("#cName", "Test Customer")
    page.dispatch_event("#cName", "input")
    for sid in site_ids:
        page.select_option("#addSel", str(BY_SITE[sid]["id"]))
        page.click("#addBtn")


def _type(page, line, field, value):
    box = page.locator(f'#items .dk-line[data-i="{line}"] [data-f="{field}"]')
    box.fill(value)
    box.dispatch_event("input")


def test_f01_share_sends_the_pdf_only(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/2", perms=["clipboard-read", "clipboard-write"])
    page.wait_for_selector("#issuedSec:not([hidden])")
    # Pretend this phone can share files, and record what is handed over.
    page.evaluate("""() => { window.__shared = [];
        navigator.canShare = () => true;
        navigator.share = d => { window.__shared.push({keys: Object.keys(d), files: (d.files || []).length, text: d.text}); return Promise.resolve(); }; }""")
    page.click("#shareBtn")
    page.wait_for_function("window.__shared.length === 1")
    shared = page.evaluate("window.__shared[0]")
    assert shared["files"] == 1 and "text" not in shared["keys"], shared
    assert page.evaluate("navigator.clipboard.readText()") == "Hello Ama, here is your invoice TCP-INV-0001 from The Cement People."
    assert "paste it as the caption" in page.text_content("#iMsg")
    assert not errors


def test_f02_wrong_values_flagged_on_their_line(browser):
    page, errors = _bo(browser, route="#/new")
    _blank_with(page, "c1", "c2")
    line = lambda i: page.locator(f'#items .dk-line[data-i="{i}"]')
    for typed, message in [("0", "Quantity must be more than 0"), ("-5", "Quantity must be more than 0"),
                           ("abc", "Enter a number"), ("5abc", "Enter a number"), ("", "Enter a quantity")]:
        _type(page, 1, "qty", typed)
        assert line(1).locator(".dk-lerr").text_content() == message, typed
        assert "bad" in line(1).get_attribute("class")
        assert line(1).locator('[data-f="qty"]').get_attribute("aria-invalid") == "true"
        assert page.locator("#saveBtn").is_disabled() and page.locator("#issueBtn").is_disabled()
        assert f"Line 2: {message[0].lower() + message[1:]}." in page.text_content("#sMsg")
        assert page.text_content("#sTot") == "—"
    assert line(0).locator(".dk-lerr").text_content() == "", "the other line is not blamed"
    _type(page, 1, "qty", "3")
    assert line(1).locator(".dk-lerr").text_content() == "" and "bad" not in line(1).get_attribute("class")
    _type(page, 1, "price", "-10")
    assert line(1).locator(".dk-lerr").text_content() == "Price can't be below GH₵0"
    assert page.locator("#saveBtn").is_disabled()
    _type(page, 1, "price", "98")
    assert not page.locator("#saveBtn").is_disabled()
    assert page.evaluate("__db.calls.filter(c => c === 'saveDraft').length") == 0, "nothing was sent while wrong"
    assert not errors


def test_f03_free_items_and_the_delivery_fee(browser):
    page, errors = _bo(browser, route="#/new")
    _blank_with(page, "c1")
    page.check('input[name="dl"][value="free"]')
    _type(page, 0, "price", "0")
    assert "Free item" in page.text_content('#items .dk-line[data-i="0"] .dk-amt')
    assert page.locator('#items .dk-line[data-i="0"] .dk-lerr').text_content() == ""
    assert not page.locator("#saveBtn").is_disabled(), "a draft with a free item can be saved"
    assert page.locator("#issueBtn").is_disabled(), "but an invoice worth nothing cannot be issued"
    assert "total must be more than GH₵0.00" in page.text_content("#sMsg")
    page.select_option("#addSel", str(BY_SITE["c2"]["id"]))
    page.click("#addBtn")
    assert not page.locator("#issueBtn").is_disabled()
    # The delivery fee, checked as it is typed.
    page.check('input[name="dl"][value="fee"]')
    for typed, message in [("", "Enter the delivery fee"), ("0", "Delivery fee must be more than 0"),
                           ("-50", "Delivery fee must be more than 0"), ("abc", "Delivery fee: enter a number")]:
        page.fill("#fee", typed); page.dispatch_event("#fee", "input")
        assert page.text_content("#feeErr") == message, typed
        assert page.locator("#issueBtn").is_disabled()
    page.fill("#fee", "350"); page.dispatch_event("#fee", "input")
    assert page.text_content("#feeErr") == "" and not page.locator("#issueBtn").is_disabled()
    page.click("#saveBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent.startsWith('Draft saved.')")
    assert page.evaluate("__db.lines.find(l => l.position === 1).unit_price") == 0
    assert not errors


def test_f04_adding_a_product_again_adds_to_its_line(browser):
    page, errors = _bo(browser, route="#/new")
    _blank_with(page, "j3", "c1", "j3")
    assert page.locator("#items .dk-line").count() == 2
    assert page.evaluate("TCPDesk.state().items[0].qty") == 2
    assert "Already on the invoice: quantity now 2" in page.text_content('#items .dk-line[data-i="0"]')
    assert not errors


def test_f05_agreed_price_stays_a_separate_line(browser):
    page, errors = _bo(browser, route="#/new")
    _blank_with(page, "j3")
    _type(page, 0, "price", "6500")
    page.dispatch_event('#items .dk-line[data-i="0"] [data-f="price"]', "change")
    page.select_option("#addSel", str(BY_SITE["j3"]["id"]))
    page.click("#addBtn")
    assert page.locator("#items .dk-line").count() == 2
    assert "Line 1 has an agreed price of GH₵6,500.00; this line is at today's price." in page.text_content('#items .dk-line[data-i="1"]')
    page.click("#saveBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent.startsWith('Draft saved.')")
    assert page.evaluate("__db.lines.length") == 2, "different prices are never combined"
    assert not errors


def test_f06_identical_lines_flagged_combined_and_saved_once(browser):
    page, errors = _bo(browser, route="#/new")
    _blank_with(page, "j3")
    _type(page, 0, "price", "6500"); page.dispatch_event('#items .dk-line[data-i="0"] [data-f="price"]', "change")
    page.select_option("#addSel", str(BY_SITE["j3"]["id"])); page.click("#addBtn")
    page.select_option("#addSel", str(BY_SITE["c1"]["id"])); page.click("#addBtn")
    # Line 2 edited to the same price as line 1: flagged, then combined.
    _type(page, 1, "qty", "1.5"); _type(page, 1, "price", "6500")
    page.dispatch_event('#items .dk-line[data-i="1"] [data-f="price"]', "change")
    assert "Same product and price as line 1" in page.text_content('#items .dk-line[data-i="1"]')
    page.click('#items [data-combine="1"]')
    assert page.locator("#items .dk-line").count() == 2
    assert page.evaluate("TCPDesk.state().items[0].qty") == 2.5
    assert "Combined with line 2: 2.5 tons now." in page.text_content('#items .dk-line[data-i="0"]')
    # Made identical again and saved without pressing Combine: Save combines and says so.
    page.select_option("#addSel", str(BY_SITE["j3"]["id"])); page.click("#addBtn")
    _type(page, 2, "price", "6500"); page.dispatch_event('#items .dk-line[data-i="2"] [data-f="price"]', "change")
    page.click("#saveBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent.startsWith('Draft saved.')")
    assert "Lines 1 and 3 combined: Iron rod 12 mm, 3.5 tons." in page.text_content("#sMsg")
    assert page.evaluate("__db.lines.length") == 2
    assert page.evaluate("__db.lines.find(l => l.unit_price === 6500).quantity") == 3.5
    assert not errors


def test_f07_issued_invoice_keeps_its_repeated_lines(browser):
    seed = [{"name": "Yaro", "phone": "+233200000009", "state": "issued", "due": FUTURE,
             "lines": [{"qty": 1}, {"qty": 1}, {"qty": 2, "price": 0}]}]
    page, errors = _bo(browser, seed=seed, route="#/invoice/1")
    page.wait_for_selector("#issuedSec:not([hidden])")
    assert page.locator("#viewLines .dk-vline").count() == 3, "shown exactly as issued"
    assert "Free item" in page.text_content("#viewLines")
    assert not errors



def test_f08_badly_formed_numbers_are_not_numbers(browser):
    page, errors = _bo(browser, route="#/new")
    _blank_with(page, "c1")
    for typed in ["1.2.3", "1,2,3", "1-2", "5-", "--5", "1..5", "1,,5", "1 2", "12.", ",", "-", "1.234.5,6", "e5"]:
        _type(page, 0, "qty", typed)
        assert page.locator('#items .dk-line[data-i="0"] .dk-lerr').text_content() == "Enter a number", typed
        assert page.evaluate("Number.isNaN(TCPDesk.state().items[0].qty)"), typed
        assert page.locator("#saveBtn").is_disabled(), typed
        _type(page, 0, "price", typed)
        assert "Enter a number" in page.locator('#items .dk-line[data-i="0"] .dk-lerr').text_content(), typed
        _type(page, 0, "price", "75")
    for typed, value in [("2,5", 2.5), ("1,392.00", 1392), ("50,000", 50000), ("1.392,00", 1392), (".5", 0.5), ("12", 12), (" 3 ", 3)]:
        _type(page, 0, "qty", typed)
        assert page.evaluate("TCPDesk.state().items[0].qty") == value, typed
        assert page.locator('#items .dk-line[data-i="0"] .dk-lerr').text_content() == "", typed
    _type(page, 0, "price", "GH₵98.50")
    assert page.evaluate("TCPDesk.state().items[0].price") == 9850
    _type(page, 0, "qty", "-5")
    assert page.locator('#items .dk-line[data-i="0"] .dk-lerr').text_content() == "Quantity must be more than 0"
    assert not errors


def test_f09_issue_never_combines_unseen(browser):
    page, errors = _bo(browser, route="#/new")
    _blank_with(page, "j3")
    _type(page, 0, "price", "6500"); page.dispatch_event('#items .dk-line[data-i="0"] [data-f="price"]', "change")
    page.select_option("#addSel", str(BY_SITE["j3"]["id"])); page.click("#addBtn")
    _type(page, 1, "price", "6500"); page.dispatch_event('#items .dk-line[data-i="1"] [data-f="price"]', "change")
    page.check('input[name="dl"][value="free"]')
    page.click("#issueBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent.includes('tap Issue invoice again')")
    assert "Lines 1 and 2 combined: Iron rod 12 mm, 2 tons." in page.text_content("#sMsg")
    assert page.locator("#items .dk-line").count() == 1
    assert page.evaluate("__db.calls.filter(c => c === 'issue' || c === 'saveDraft').length") == 0, "nothing saved or issued yet"
    assert page.locator("#form").is_visible()
    page.click("#issueBtn")
    page.wait_for_selector("#issuedSec:not([hidden])")
    assert page.evaluate("__db.lines.length") == 1 and page.evaluate("__db.lines[0].quantity") == 2
    assert not errors


def test_f10_pdf_names_free_items(browser):
    seed = [{"name": "Yaro", "phone": "+233200000009", "state": "issued", "due": FUTURE,
             "lines": [{"qty": 3}, {"qty": 2, "price": 0}]}]
    page, errors = _bo(browser, seed=seed, route="#/invoice/1")
    page.wait_for_selector("#issuedSec:not([hidden])")
    texts, _ = _pdf(page)
    text = " ".join(texts)
    assert "Free item" in text
    assert text.count("Free item") == 1, "only the free line"
    assert "GH₵0.00" in text
    assert not errors
