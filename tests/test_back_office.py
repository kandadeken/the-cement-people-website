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
  F11  a saved draft reopened with identical lines: Issue combines them and
       marks them unsaved; leaving asks Save / Discard / Go back
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

Phase 2, payments and receipts ("TCP Back Office: Phase 2 Design, Payments
and Receipts (v1)", GitHub issue #39):
  P01  a part payment, then the full balance: receipts, balances, PAID IN
       FULL, the invoice becomes paid and Record payment goes away
  P02  amounts checked on the form: empty, not a number, zero, more than is
       owed; a reference is needed for Mobile Money and bank, not cash
  P03  a date in the future is refused on the form and by the "database"
  P04  a lost reply, no connection and a double tap: recorded once, the
       retry keeps the same request id and gives back the same receipt
  P05  an expired sign-in keeps the unfinished payment (and its request id)
       and brings it back after signing in; removed access clears it
  P06  the receipt PDF: A4, RECEIPT, the figures as recorded (paid before,
       balance after) even after later payments; PAID IN FULL when cleared
  P07  sharing a receipt: the PDF only, the message copied (with "paid in
       full" when cleared); a refund can be shared, a correction cannot
  P08  correcting a payment (finance): reason needed, confirm step, the
       balance goes back up, the payment is marked corrected
  P09  refunds: partial, more than is left refused, "All that is left",
       correcting after a refund refused
  P10  roles: sales records payments but sees no Correct or Refund (and the
       "database" refuses them); finance and the owner see both
  P11  drafts, cancelled and paid invoices have no Record payment
  P12  the payment, refund and receipt screens fit 360 px and 390 px phones

Amendment, 23 Nov 2026 (Option B: an unconfirmed operation is noted on the
phone so it is never recorded twice):
  P13  a refund saved by the database with its reply lost, then the
       sign-in expires and the page reloads: after signing in it is found
       by its request id, exactly one refund, the original receipt shown
  P14  the same for a correction
  P15  sign-out warns first and then removes the note; a note older than
       24 hours is dropped; another staff member never sees it; while the
       outcome can't be checked nothing new can be recorded
  P16  the note holds no customer name or phone, only the allowed fields
  P17  a record found by request id that is a DIFFERENT operation (other
       invoice, kind, payment or amount) is never taken as success, and
       nothing new can be recorded

Phase 2.1, the Payments tab and cancelling invoices ("TCP Back Office:
Phase 2.1 Design, Payments Ledger and Cancelling Invoices (v1.1)"):
  L01  Today: received (corrected payments left out), refunded, net,
       records, the method split; each kind said in words; Home's Received
       today is the same figure
  L02  All time: net = every stored amount = every invoice's paid
  L03  kind and method filters narrow the list, never the totals; the
       address keeps the view
  L04  more than 30 records: the totals count them all; Show more adds rows
       and leaves the totals as they were
  L05  search: receipt, invoice, name, part of a reference, and a phone
       typed as 0…, +233…, spaced or its last digits
  L06  roles: owner, sales and finance see Payments; only the owner sees
       Cancel invoice
  L07  cancelling an unpaid invoice: reason, confirm, the Cancelled view
       (when, by whom, why), no Share or Record payment, a PDF marked
       CANCELLED, and it leaves Owed
  L08  an invoice holding money can't be cancelled (and the "database"
       refuses it); after a full refund it can, keeping its history
  L09  the Payments tab and the Cancel box fit 360 px and 390 px phones
  L10  a long cancellation reason appears in full in the PDF, never over
       the footer; CANCELLED is on every page of a long invoice

Phase 2.2, notes from estimate to receipt ("TCP Back Office: Phase 2.2
Design, Notes from Estimate to Receipt (v1.6)"):
  N01  the estimator's note: in the WhatsApp message and the printed
       estimate only when filled in; without one the message is as before
  N02  an estimate's note goes into the draft's internal notes once;
       Copy to note to customer; gone after issue; the invoice PDF prints
       the note to the customer and never an internal note
  N03  adding a note: General by default, a double tap and a lost reply
       give one note, changed words are a new note
  N04  payment notes: both on the receipt view, only the customer's on the
       PDF, neither in WhatsApp; the payment history; the ledger marker
  N05  correcting a note and its correction: struck through, "Corrected 2
       times", Correct this note only on the latest, the same in search
  N06  correcting payment, refund and correction notes: the same latest
       correction on the receipt view, payment history and search; the
       receipt unchanged; a correction offers no note to the customer
  N07  two people correcting at once: told, shown the first correction,
       typed words kept in a box against the latest
  N08  Notes search: 3 letters a word, filters, marked words, Leave out
       corrected notes, the address with no note text, links
  N09  a lost payment reply then a reload: no note text kept on the phone,
       the form says notes were not kept, nothing recorded twice
  N10  notes, forms and search fit 360 px and 390 px phones
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
    customers: [], invoices: [], lines: [], payments: [], notes: [], counters: {customer: 0, invoice: 0, receipt: 0},
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
      {customers: db.customers, invoices: db.invoices, lines: db.lines, payments: db.payments, notes: db.notes, counters: db.counters, staff: db.staff, clock: db.clock})); } catch (e) {} };
  const pad = n => String(n).padStart(4, "0");
  const net = async (name, fn) => {
    if (db.inAuthCallback) db.lockViolations.push(name);
    db.calls.push(name);
    await new Promise(r => setTimeout(r, 5));
    if ((db.offlineFor || []).includes(name)) throw new TypeError("Failed to fetch");
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
  // Paid = the sum of every receipt on the invoice (refunds and corrections
  // are stored below zero), as invoice_summary works it out.
  const paidOf = id => Math.round(db.payments.filter(p => p.invoice_id === id).reduce((a, p) => a + Math.round(p.amount * 100), 0)) / 100;
  const pd = new Date(), today = pd.getFullYear() + "-" + String(pd.getMonth() + 1).padStart(2, "0") + "-" + String(pd.getDate()).padStart(2, "0");
  const status = inv => inv.state === "draft" ? "draft" : inv.state === "cancelled" ? "cancelled"
    : paidOf(inv.id) >= total(inv.id) ? "paid" : inv.due_date && inv.due_date < today ? "overdue" : paidOf(inv.id) > 0 ? "part_paid" : "unpaid";
  let clock = 0;
  // The clock carries on across reloads (kept with the data), so a record
  // made after a reload is always later than the ones before it.
  const stamp = () => { db.clock = (db.clock || 0) + 1; clock = db.clock; return new Date(Date.UTC(2026, 10, 22, 8, 0, 0) + 1000 * (db.clock - 1)).toISOString(); };
  // invoice_list, as the view builds it.
  const listRow = inv => { const c = db.customers.find(x => x.id === inv.customer_id), t = total(inv.id);
    return {id: inv.id, invoice_no: inv.invoice_no, state: inv.state, status: status(inv), issued_at: inv.issued_at || null,
      created_at: inv.created_at, due_date: inv.due_date || null, total: t, balance: Math.round((t - paidOf(inv.id)) * 100) / 100,
      billed_to_name: inv.invoice_no ? inv.billed_to_name : c.name, billed_to_phone: inv.invoice_no ? inv.billed_to_phone : c.phone}; };
  // PostgREST "ilike" with * as the wildcard.
  const ilike = (v, pat) => v != null && new RegExp("^" + pat.split("*").map(p => p.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*") + "$", "i").test(String(v));
  // Test data straight into the "database" (as other staff would have made).
  db.seed = list => list.forEach(o => {
    let c = db.customers.find(x => x.phone === o.phone && x.name === o.name);
    if (!c) { c = {id: db.customers.length + 1, code: "TCP-C-" + pad(++db.counters.customer), phone: o.phone || null, name: o.name || null}; db.customers.push(c); }
    const inv = {id: db.invoices.length + 1, state: o.state || "draft", invoice_no: null, customer_id: c.id, due_date: o.due || null,
      created_at: o.created_at || stamp(), notes: o.notes || null, deliver_to_location: null};
    db.invoices.push(inv);
    (o.lines || [{qty: o.qty || 10}]).forEach((l, k) => db.lines.push({invoice_id: inv.id, position: k + 1, kind: "product",
      product_id: 1, description: "Supacem 32.5R", unit: "50 kg bag", quantity: l.qty, unit_price: l.price == null ? 75 : l.price}));
    if (inv.state !== "draft" && !o.never_issued) Object.assign(inv, {invoice_no: "TCP-INV-" + pad(++db.counters.invoice),
      issued_at: inv.created_at, issued_by: "Test Owner", billed_to_name: c.name, billed_to_phone: c.phone});
    if (o.state === "cancelled") inv.cancel_reason = "seeded";
    // "paid" in the test data = one cash receipt for that amount.
    if (o.paid) addPay({invoice_id: inv.id, kind: "payment", amount: o.paid, method: "cash", reference: null, paid_on: inv.created_at.slice(0, 10), recorded_by: "Test Owner"});
    persist(); });
  // A new receipt: the next number, and the balance after it, stored.
  function addPay(p) { const row = {id: db.payments.length + 1, receipt_no: "TCP-RCT-" + pad(++db.counters.receipt), reason: null,
      reverses_payment_id: null, request_id: null, customer_note: null, internal_note: null, recorded_at: stamp(),
      recorded_by_id: me() ? me().user_id : null, ...p};
    db.payments.push(row); row.balance_after = Math.round((total(row.invoice_id) - paidOf(row.invoice_id)) * 100) / 100; persist(); return row; }
  // tcp_private.repeat_of: the same request id gives back the first receipt;
  // a different request under that id is refused.
  // A database refusal (raise exception) carries a Postgres error code.
  const dbErr = m => Object.assign(new Error(m), {code: "P0001"});
  function repeatOf(req, kind, inv, rev, amt, method, reason, cnote, inote) { if (!req) return null;
    const e = db.payments.find(p => p.request_id === req); if (!e) return null;
    if (e.kind !== kind || e.invoice_id !== inv || (e.reverses_payment_id || null) !== (rev || null) || Math.abs(e.amount - amt) > 1e-9
        || e.method !== method || (e.reason || "").trim() !== (reason || "").trim()
        || (e.customer_note || null) !== (cnote || null) || (e.internal_note || null) !== (inote || null)) throw dbErr("This request id was already used for a different payment");
    return e; }
  // Phase 2.2: tcp_private.note_chain, the corrections of a note or of a
  // payment's internal note, oldest first.
  const staffName = id => { const s = db.staff.find(x => x.user_id === id); return s ? s.full_name : null; };
  function noteChain(noteId, payId) { const out = [];
    let c = db.notes.find(n => noteId ? n.corrects_note_id === noteId : n.corrects_payment_id === payId);
    while (c) { out.push({id: c.id, body: c.body, category: c.category, by: staffName(c.created_by), at: c.created_at});
      const cur = c; c = db.notes.find(n => n.corrects_note_id === cur.id); }
    return out; }
  const noteText = s => { const t = s == null ? "" : String(s).trim(); return t || null; };
  const payNotes = p => ({customer_note: p.customer_note, internal_note: p.internal_note, recorded_at: p.recorded_at,
    internal_note_chain: noteChain(null, p.id)});
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
    // invoice_document's answer, built without a network call (the receipt
    // uses it too).
    __doc: id => { const inv = db.invoices.find(i => i.id === id);
      if (!inv) throw new Error("No such invoice"); const c = db.customers.find(x => x.id === inv.customer_id);
      const issued = !!inv.invoice_no, t = total(id);
      return {id: inv.id, invoice_no: inv.invoice_no, state: inv.state, status: status(inv), cancel_reason: inv.cancel_reason || null, created_at: inv.created_at,
        cancelled_at: inv.cancelled_at || null, cancelled_by: inv.cancelled_by || null,
        issued_at: inv.issued_at || null, issued_by: inv.issued_by || null, due_date: inv.due_date, notes: inv.notes,
        customer_id: inv.customer_id, customer_code: c.code,
        billed_to_name: issued ? inv.billed_to_name : c.name, billed_to_phone: issued ? inv.billed_to_phone : c.phone,
        deliver_to_location: inv.deliver_to_location, deliver_to_contact: inv.deliver_to_contact, deliver_to_phone: inv.deliver_to_phone,
        lines: db.lines.filter(l => l.invoice_id === id).map(l => ({...l, line_total: Math.round(l.quantity * l.unit_price * 100) / 100})),
        total: t, paid: paidOf(id), balance: Math.round((t - paidOf(id)) * 100) / 100, payments: db.payments.filter(p => p.invoice_id === id).map(p => ({...p,
          reverses_receipt_no: p.reverses_payment_id ? db.payments.find(o => o.id === p.reverses_payment_id).receipt_no : null,
          corrected: p.kind === "payment" && db.payments.some(c => c.reverses_payment_id === p.id && c.kind === "correction"),
          refunded: p.kind === "payment" ? -db.payments.filter(r => r.reverses_payment_id === p.id && r.kind === "refund").reduce((a, r) => a + r.amount, 0) : null,
          ...payNotes(p)})),
        internal_notes: db.notes.filter(n => n.invoice_id === id).map(n => { const cp = db.payments.find(x => x.id === n.corrects_payment_id),
            by = db.notes.find(c => c.corrects_note_id === n.id);
          return {id: n.id, body: n.body, category: n.category, by: staffName(n.created_by), at: n.created_at, estimate_ref: n.estimate_ref || null,
            corrects_note_id: n.corrects_note_id || null, corrects_payment_id: n.corrects_payment_id || null,
            corrects_receipt_no: cp ? cp.receipt_no : null, corrects_kind: cp ? cp.kind : null, corrected_by_note_id: by ? by.id : null}; })}; },
    document: id => net("document", () => { staffOnly(); return window.TCPDeskApi.__doc(id); }),
    // Phase 2, with record_payment / correct_payment / refund_payment's rules.
    recordPayment: a => net("recordPayment", () => { staffOnly("owner", "sales", "finance");
      const again = repeatOf(a.p_request_id, "payment", a.p_invoice_id, null, Math.round(a.p_amount * 100) / 100, a.p_method, null,
        noteText(a.p_customer_note), noteText(a.p_internal_note)); if (again) return again;
      const inv = db.invoices.find(i => i.id === a.p_invoice_id);
      if (!inv || inv.state !== "issued") throw dbErr("Payments can only be recorded against an issued invoice");
      if (!(a.p_amount > 0)) throw dbErr("A payment must be more than zero");
      if (!a.p_paid_on || a.p_paid_on > today) throw dbErr("A payment date cannot be in the future");
      const owed = Math.round((total(inv.id) - paidOf(inv.id)) * 100) / 100;
      if (a.p_amount > owed) throw dbErr(`GH₵ ${a.p_amount.toFixed(2)} is more than the GH₵ ${owed.toFixed(2)} still owed`);
      return addPay({invoice_id: inv.id, kind: "payment", amount: Math.round(a.p_amount * 100) / 100, method: a.p_method, reference: a.p_reference || null,
        paid_on: a.p_paid_on, request_id: a.p_request_id, recorded_by: me().full_name,
        customer_note: noteText(a.p_customer_note), internal_note: noteText(a.p_internal_note)}); }),
    correctPayment: a => net("correctPayment", () => { staffOnly("owner", "finance");
      const o = db.payments.find(p => p.id === a.p_payment_id);
      const again = o && repeatOf(a.p_request_id, "correction", o.invoice_id, o.id, -o.amount, o.method, a.p_reason, null, noteText(a.p_internal_note)); if (again) return again;
      if (!o || o.kind !== "payment") throw dbErr("Only a payment can be corrected");
      if (!a.p_reason || !a.p_reason.trim()) throw dbErr("A reason is needed");
      if (db.payments.some(c => c.reverses_payment_id === o.id && c.kind === "correction")) throw dbErr("This payment has already been corrected");
      if (db.payments.some(c => c.reverses_payment_id === o.id && c.kind === "refund")) throw dbErr("This payment has refunds against it and can no longer be corrected");
      return addPay({invoice_id: o.invoice_id, kind: "correction", amount: -o.amount, method: o.method, reference: o.reference, paid_on: today,
        reverses_payment_id: o.id, reason: a.p_reason.trim(), request_id: a.p_request_id, recorded_by: me().full_name,
        internal_note: noteText(a.p_internal_note)}); }),
    refundPayment: a => net("refundPayment", () => { staffOnly("owner", "finance");
      const o = db.payments.find(p => p.id === a.p_payment_id), amt = Math.round(a.p_amount * 100) / 100;
      const again = o && repeatOf(a.p_request_id, "refund", o.invoice_id, o.id, -amt, a.p_method, a.p_reason,
        noteText(a.p_customer_note), noteText(a.p_internal_note)); if (again) return again;
      if (!o || o.kind !== "payment") throw dbErr("Only a payment can be refunded");
      if (db.payments.some(c => c.reverses_payment_id === o.id && c.kind === "correction")) throw dbErr("This payment was corrected; there is nothing left to refund");
      if (!(amt > 0)) throw dbErr("A refund must be more than zero");
      if (!a.p_reason || !a.p_reason.trim()) throw dbErr("A reason is needed");
      const before = -db.payments.filter(r => r.reverses_payment_id === o.id && r.kind === "refund").reduce((x, r) => x + r.amount, 0);
      if (before + amt > o.amount + 1e-9) throw dbErr(`Refunds would total GH₵ ${(before + amt).toFixed(2)}, more than the GH₵ ${o.amount.toFixed(2)} paid`);
      return addPay({invoice_id: o.invoice_id, kind: "refund", amount: -amt, method: a.p_method, reference: a.p_reference || null, paid_on: today,
        reverses_payment_id: o.id, reason: a.p_reason.trim(), request_id: a.p_request_id, recorded_by: me().full_name,
        customer_note: noteText(a.p_customer_note), internal_note: noteText(a.p_internal_note)}); }),
    // A plain read of the payments table by request id (row-level security:
    // nothing for non-staff).
    byRequest: req => net("byRequest", () => { const p = me() && db.payments.find(x => x.request_id === req);
      return p ? {id: p.id, receipt_no: p.receipt_no, kind: p.kind, invoice_id: p.invoice_id,
        reverses_payment_id: p.reverses_payment_id || null, amount: p.amount} : null; }),
    receipt: id => net("receipt", () => { staffOnly(); const p = db.payments.find(x => x.id === id);
      if (!p) throw new Error("No such receipt");
      const doc = window.TCPDeskApi.__doc(p.invoice_id), earlier = db.payments.filter(x => x.invoice_id === p.invoice_id && x.id < p.id);
      ["payments", "paid", "balance", "status", "internal_notes"].forEach(k => delete doc[k]);
      return {receipt_no: p.receipt_no, kind: p.kind, amount: p.amount, method: p.method, reference: p.reference, paid_on: p.paid_on,
        reason: p.reason || null, reverses_receipt_no: p.reverses_payment_id ? db.payments.find(o => o.id === p.reverses_payment_id).receipt_no : null,
        balance_after: p.balance_after, recorded_by: p.recorded_by, payments_before: earlier.length, ...payNotes(p),
        paid_before: Math.round(earlier.reduce((a, x) => a + x.amount * 100, 0)) / 100, invoice: doc}; }),
    cancel: (id, reason) => net("cancel", () => { staffOnly("owner");
      if (!reason || !reason.trim()) throw new Error("A reason is needed to cancel an invoice");
      const inv = db.invoices.find(i => i.id === id);
      if (!inv || inv.state === "cancelled") throw dbErr("Only a draft or issued invoice can be cancelled");
      const held = paidOf(id);
      if (held !== 0) throw dbErr(`This invoice still holds GH₵ ${held.toFixed(2)} in payments; correct or refund them first`);
      Object.assign(inv, {state: "cancelled", cancel_reason: reason.trim(), cancelled_at: stamp(), cancelled_by: me().full_name}); }),
    // Phase 2.1: payment_totals, with the database's rules (corrected
    // payments count nothing; refunds are money out; "today" is the
    // stand-in's own date, as the database's Ghana date).
    totals: period => net("totals", () => { staffOnly("owner", "sales", "finance");
      const d = new Date(today + "T00:00:00"), iso = x => x.getFullYear() + "-" + String(x.getMonth() + 1).padStart(2, "0") + "-" + String(x.getDate()).padStart(2, "0");
      let from, to;
      if (period === "today") { from = to = today; }
      else if (period === "week") { const w = new Date(d); w.setDate(d.getDate() - ((d.getDay() + 6) % 7)); from = iso(w); to = today; }
      else if (period === "month") { from = today.slice(0, 8) + "01"; to = today; }
      else if (period === "all") { from = to = null; }
      else throw dbErr("Unknown period: " + period);
      const rows = db.payments.filter(p => (!from || p.paid_on >= from) && (!to || p.paid_on <= to));
      const corrected = p => p.kind === "payment" && db.payments.some(c => c.reverses_payment_id === p.id && c.kind === "correction");
      const sum = (f, m) => Math.round(rows.filter(p => f(p) && p.method === m).reduce((a, p) => a + p.amount * 100, 0)) / 100;
      const split = f => { const o = {mobile_money: sum(f, "mobile_money"), cash: sum(f, "cash"), bank_transfer: sum(f, "bank_transfer")};
        o.total = Math.round((o.mobile_money + o.cash + o.bank_transfer) * 100) / 100; return o; };
      const received = split(p => p.kind === "payment" && !corrected(p));
      const refunded = split(p => p.kind === "refund"); ["mobile_money", "cash", "bank_transfer", "total"].forEach(k => refunded[k] = -refunded[k] || 0);
      return {period, from, to, received, refunded, net: Math.round((received.total - refunded.total) * 100) / 100, records: rows.length}; }),
    // payment_ledger (row rules: nothing for non-staff), newest first, paged.
    ledger: ({from, to, kind: k, method: m, terms, offset, limit}) => net("ledger", () => {
      let rows = rlsRead(db.payments.map(p => { const inv = db.invoices.find(i => i.id === p.invoice_id), o = db.payments.find(x => x.id === p.reverses_payment_id);
        const phone = inv.billed_to_phone || "";
        return {id: p.id, receipt_no: p.receipt_no, kind: p.kind, amount: p.amount, method: p.method, reference: p.reference, paid_on: p.paid_on,
          invoice_id: p.invoice_id, invoice_no: inv.invoice_no, billed_to_name: inv.billed_to_name, billed_to_phone: phone || null,
          reverses_receipt_no: o ? o.receipt_no : null,
          corrected: p.kind === "payment" && db.payments.some(c => c.reverses_payment_id === p.id && c.kind === "correction"),
          customer_note: p.customer_note || null, internal_note: p.internal_note || null,
          search_text: [p.receipt_no, inv.invoice_no, inv.billed_to_name, p.reference, o && o.receipt_no, phone, p.customer_note, p.internal_note,
            phone.startsWith("+233") ? "0" + phone.slice(4) : null].filter(Boolean).join(" ").toLowerCase()}; }));
      if (from) rows = rows.filter(r => r.paid_on >= from);
      if (to) rows = rows.filter(r => r.paid_on <= to);
      if (k && k !== "all") rows = rows.filter(r => r.kind === k);
      if (m && m !== "all") rows = rows.filter(r => r.method === m);
      if (terms && terms.length) rows = rows.filter(r => terms.some(t => ilike(r.search_text, t)));
      rows.sort((a, b) => a.paid_on < b.paid_on ? 1 : a.paid_on > b.paid_on ? -1 : b.id - a.id);
      return {rows: rows.slice(offset, offset + limit).map(({search_text, ...r}) => r), count: rows.length}; }),
    // back_office_home (runs with the caller's rights: zeros for non-staff).
    home: () => net("home", () => { const rows = me() ? db.invoices.map(listRow) : [], n = s => rows.filter(r => r.status === s).length;
      return {owed: rows.filter(r => ["unpaid", "part_paid", "overdue"].includes(r.status)).reduce((a, r) => a + r.balance, 0),
        unpaid: n("unpaid"), part_paid: n("part_paid"), overdue: n("overdue"), drafts: n("draft")}; }),
    // Phase 2.2: add_invoice_note, with the database's rules (a correction
    // corrects one note once; the same request id gives the first note).
    addNote: a => net("addNote", () => { staffOnly("owner", "sales", "finance");
      const inv = db.invoices.find(i => i.id === a.p_invoice_id); if (!inv) throw dbErr("No such invoice");
      if (a.p_corrects_note_id && a.p_corrects_payment_id) throw dbErr("A correction corrects one note");
      let cat = a.p_category || null;
      if (a.p_corrects_note_id) { const t = db.notes.find(n => n.id === a.p_corrects_note_id);
        if (!t || t.invoice_id !== inv.id) throw dbErr("That note is not on this invoice"); cat = cat || t.category; }
      if (a.p_corrects_payment_id) { const t = db.payments.find(x => x.id === a.p_corrects_payment_id);
        if (!t || t.invoice_id !== inv.id) throw dbErr("That receipt is not on this invoice");
        if (!t.internal_note) throw dbErr("That receipt has no internal note to correct"); cat = cat || "payment"; }
      cat = cat || "general"; const body = String(a.p_body || "").trim();
      const e = a.p_request_id && db.notes.find(n => n.request_id === a.p_request_id);
      if (e) { if (e.invoice_id !== inv.id || e.body !== body || e.category !== cat || (e.corrects_note_id || null) !== (a.p_corrects_note_id || null)
            || (e.corrects_payment_id || null) !== (a.p_corrects_payment_id || null)) throw dbErr("This request id was already used for a different note");
        return e; }
      if (!body) throw dbErr("A note cannot be empty");
      if (body.length > 1000) throw dbErr("A note can be at most 1,000 characters");
      if (!["general", "payment", "delivery", "customer_request", "complaint", "stock", "follow_up"].includes(cat)) throw dbErr("Unknown note category: " + cat);
      const done = db.notes.find(n => (a.p_corrects_note_id && n.corrects_note_id === a.p_corrects_note_id) || (a.p_corrects_payment_id && n.corrects_payment_id === a.p_corrects_payment_id));
      if (done) throw dbErr(`This note was just corrected by ${staffName(done.created_by)}. Here is the latest; correct that instead.`);
      const n = {id: db.notes.length + 1, invoice_id: inv.id, body, category: cat, corrects_note_id: a.p_corrects_note_id || null,
        corrects_payment_id: a.p_corrects_payment_id || null, estimate_ref: a.p_estimate_ref || null, created_by: me().user_id,
        created_at: stamp(), request_id: a.p_request_id || null};
      db.notes.push(n); return n; }),
    noteAuthors: () => net("noteAuthors", () => { staffOnly("owner", "sales", "finance");
      return db.staff.map(s => ({id: s.user_id, name: s.full_name, active: s.active})); }),
    // search_notes: the four sources, filters, newest first, paged.
    searchNotes: a => net("searchNotes", () => { staffOnly("owner", "sales", "finance");
      const words = (a.p_words || []).map(w => String(w).trim()).filter(Boolean);
      if (words.some(w => w.length < 3)) throw dbErr("Type at least 3 letters or digits for each word");
      const hits = [];
      db.notes.forEach(n => hits.push({kind: "invoice_note", category: n.category, note_id: n.id, payment_id: null, invoice_id: n.invoice_id, body: n.body,
        author: n.created_by, at: n.created_at, corrects_note_id: n.corrects_note_id, corrects_payment_id: n.corrects_payment_id,
        corrected: db.notes.some(c => c.corrects_note_id === n.id)}));
      db.payments.forEach(p => { if (p.internal_note) hits.push({kind: "payment_note", category: "payment", note_id: null, payment_id: p.id, invoice_id: p.invoice_id,
          body: p.internal_note, author: p.recorded_by_id, at: p.recorded_at, corrected: db.notes.some(c => c.corrects_payment_id === p.id)});
        if (p.customer_note) hits.push({kind: "receipt_customer_note", category: null, payment_id: p.id, invoice_id: p.invoice_id, body: p.customer_note,
          author: p.recorded_by_id, at: p.recorded_at, corrected: false}); });
      db.invoices.forEach(i => { const t = String(i.notes || "").split("\n").filter(l => l && l !== "Customer pickup" && l !== "Free delivery" && !/^Estimate TCP-\d{6}-[A-Z0-9]{6}$/.test(l)).join("\n");
        if (t) hits.push({kind: "invoice_customer_note", category: null, invoice_id: i.id, body: t, author: null, at: i.created_at, corrected: false}); });
      let rows = hits.filter(h => words.every(w => h.body.toLowerCase().includes(w.toLowerCase()))
        && (!a.p_category || h.category === a.p_category) && (!a.p_author || h.author === a.p_author)
        && (!a.p_from || h.at.slice(0, 10) >= a.p_from) && (!a.p_to || h.at.slice(0, 10) <= a.p_to)
        && !(a.p_hide_corrected && h.corrected));
      rows.sort((x, y) => (x.at < y.at) - (x.at > y.at));
      const count = rows.length;
      rows = rows.slice(a.p_offset || 0, (a.p_offset || 0) + (a.p_limit || 30)).map(h => { const inv = db.invoices.find(i => i.id === h.invoice_id),
          p = db.payments.find(x => x.id === h.payment_id), t = total(inv.id), c = db.customers.find(x => x.id === inv.customer_id),
          cn = db.notes.find(n => n.id === h.corrects_note_id), cp = db.payments.find(x => x.id === h.corrects_payment_id);
        return {kind: h.kind, category: h.category, note_id: h.note_id || null, payment_id: h.payment_id || null, record_kind: p ? p.kind : null,
          receipt_no: p ? p.receipt_no : null, invoice_id: inv.id, invoice_no: inv.invoice_no, invoice_state: inv.state,
          customer: inv.invoice_no ? inv.billed_to_name : c.name, status: status(inv), balance: Math.round((t - paidOf(inv.id)) * 100) / 100,
          body: h.body, by: staffName(h.author), at: h.at, corrected: h.corrected,
          chain: h.corrected ? noteChain(h.note_id, h.kind === "payment_note" ? h.payment_id : null) : null,
          corrects_note_id: h.corrects_note_id || null, corrects_payment_id: h.corrects_payment_id || null,
          corrects_by: cn ? staffName(cn.created_by) : null, corrects_at: cn ? cn.created_at : null,
          corrects_receipt_no: cp ? cp.receipt_no : null, corrects_record_kind: cp ? cp.kind : null}; });
      return {count, rows}; }),
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


def _estimate_message(browser, order, loc="", note=""):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
    page = ctx.new_page()
    page.goto(SITE_URL, wait_until="load")
    page.wait_for_selector("#list .row")
    settle(page)
    page.evaluate("o => { for (const k in o) qty[k] = o[k]; renderList(); renderEst(); }", order)
    if loc:
        page.fill("#loc", loc)
    if note:
        page.fill("#enote", note)
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
        # Signed in on every load, unless a test has signed out for real
        # and wants to sign in again after a true page reload.
        page.add_init_script("if (!sessionStorage.getItem('no-auto-sign-in')) sessionStorage.setItem('standin-session', JSON.stringify(%s))" % json.dumps(who or OWNER))
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



def test_f11_combining_on_issue_is_unsaved_work(browser):
    # A draft saved before phase 1.1, with the same product twice at the
    # same price, and delivery already agreed (so nothing else is changed).
    seed = [{"name": "Johnny Two", "phone": "+233200000010", "state": "draft", "notes": "Free delivery",
             "lines": [{"qty": 1}, {"qty": 2}]}]
    page, errors = _bo(browser, seed=seed, route="#/invoice/1")
    page.wait_for_selector("#form:not([hidden])")
    assert page.evaluate("TCPDesk.state().dirty") is False
    assert page.text_content("#state") == "Draft saved"
    page.click("#issueBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent.includes('tap Issue invoice again')")
    assert page.locator("#items .dk-line").count() == 1 and page.evaluate("TCPDesk.state().items[0].qty") == 3
    assert page.evaluate("TCPDesk.state().dirty") is True
    assert page.text_content("#state") == "Draft: changes not saved yet"
    assert page.evaluate("__db.calls.filter(c => c === 'issue' || c === 'saveDraft').length") == 0
    # Leaving now asks first; Go back keeps the combined line.
    page.click('#tabs a[data-tab="invoices"]')
    page.wait_for_function("location.hash === '#/invoices'")
    page.wait_for_selector("#rows .dk-inv")
    page.click('#tabs a[data-tab="new"]')   # a new invoice would replace the combined draft
    page.wait_for_selector("#guard:not([hidden])")
    page.click("#guardBack")
    page.wait_for_selector("#guard", state="hidden")
    assert page.evaluate("TCPDesk.state().items.length") == 1 and page.evaluate("TCPDesk.state().items[0].qty") == 3
    assert not errors


# ---- Phase 2: payments and receipts -------------------------------------------
# MIX: invoice 2 = TCP-INV-0001 Ama, GH₵750 unpaid; invoice 3 = TCP-INV-0002
# Yaw, GH₵300 paid (receipt TCP-RCT-0001), GH₵450 left; invoice 4 = Efua,
# paid in full (TCP-RCT-0002); 1 is a draft; 6 is cancelled.
def _open_pay(page):
    page.wait_for_selector("#payBtn:not([hidden])")
    page.click("#payBtn")
    page.wait_for_selector("#payForm:not([hidden])")


def _pay(page, amount, method="cash", ref="", date=None, confirm=True):
    page.fill("#pAmt", amount)
    page.check(f'input[name="pm"][value="{method}"]')
    page.fill("#pRef", ref)
    if date:
        page.fill("#pDate", date)
    page.click("#pNext")
    if confirm:
        page.wait_for_selector("#pConfirm:not([hidden])")
        page.click("#pYes")


def _receipt_shown(page, no):
    page.wait_for_selector("#rcptSec:not([hidden])")
    page.wait_for_function(f"document.querySelector('#rTitle').textContent.includes('{no}')")
    return {r.locator("span").text_content(): r.locator("b").text_content()
            for r in page.locator("#rcpt .dk-sum > div").all()}


def test_p01_part_then_full_payment(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/2")
    _open_pay(page)
    assert page.input_value("#pDate") == page.evaluate("new Date().toLocaleDateString('en-CA')"), "the date starts as today"
    _pay(page, "300", "mobile_money", "MP2611231234", confirm=False)
    page.wait_for_selector("#pConfirm:not([hidden])")
    summary = page.text_content("#pSummary")
    assert "GH₵300.00 by Mobile Money (ref MP2611231234) for TCP-INV-0001" in summary and "Balance after: GH₵450.00" in summary
    assert page.evaluate("__db.payments.length") == 2, "nothing is recorded before the confirm step"
    page.click("#pYes")
    rows = _receipt_shown(page, "TCP-RCT-0003")
    assert rows["Amount received"] == "GH₵300.00" and rows["Paid before this receipt"] == "GH₵0.00"
    assert rows["Balance after"] == "GH₵450.00" and rows["Reference"] == "MP2611231234"
    assert not page.locator(".dk-paidfull").is_visible()
    # Back to the invoice: the receipt is listed, part paid.
    page.click("#rInv")
    page.wait_for_selector("#issuedSec:not([hidden])")
    assert "TCP-RCT-0003" in page.text_content("#payList")
    assert "Paid GH₵300.00" in page.text_content("#paySum") and "Left GH₵450.00" in page.text_content("#paySum")
    assert page.evaluate("TCPDesk.doc().status") == "part_paid"
    _open_pay(page)
    page.click("#pFull")
    assert page.input_value("#pAmt") == "450.00"
    _pay(page, "450.00", "cash")
    rows = _receipt_shown(page, "TCP-RCT-0004")
    assert rows["Balance after"] == "GH₵0.00" and rows["Paid before this receipt"] == "GH₵300.00"
    assert page.locator(".dk-paidfull").is_visible()
    page.click("#rInv")
    page.wait_for_selector("#issuedSec:not([hidden])")
    assert page.evaluate("TCPDesk.doc().status") == "paid"
    assert not page.locator("#payBtn").is_visible(), "nothing left to pay"
    page.goto(BO + "#/")
    page.wait_for_function("document.querySelector('#hOwed').textContent !== '—'")
    assert page.text_content("#hOwed") == "GH₵1,200.00", "Home: 450 (Yaw) + 750 (Kwame) still owed"
    assert not errors


def test_p02_amount_and_reference_checks(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/3")
    _open_pay(page)
    for typed, msg in [("", "Enter the amount received."), ("abc", "Enter a number."), ("1.2.3", "Enter a number."),
                       ("0", "more than GH₵0.00"), ("450.01", "more than the GH₵450.00 left to pay")]:
        page.fill("#pAmt", typed); page.check('input[name="pm"][value="cash"]'); page.click("#pNext")
        assert msg in page.text_content("#pAmtErr"), typed
        assert not page.locator("#pConfirm").is_visible()
    page.fill("#pAmt", "100")
    for method, needed in [("mobile_money", "MoMo transaction ID"), ("bank_transfer", "bank reference")]:
        page.check(f'input[name="pm"][value="{method}"]'); page.fill("#pRef", ""); page.click("#pNext")
        assert needed in page.text_content("#pErr") and needed in page.text_content("#pRefLabel"), method
    page.check('input[name="pm"][value="cash"]'); page.fill("#pRef", ""); page.click("#pNext")
    page.wait_for_selector("#pConfirm:not([hidden])"), "cash needs no reference"
    # Over the balance straight to the "database": refused there too.
    err = page.evaluate("""() => TCPDeskApi.recordPayment({p_invoice_id: 3, p_amount: 500, p_method: 'cash', p_paid_on: '2026-01-10',
        p_request_id: crypto.randomUUID()}).then(() => 'recorded', e => e.message)""")
    assert "more than the GH₵ 450.00 still owed" in err
    assert page.evaluate("__db.payments.length") == 2
    assert not errors


def test_p03_future_date_refused(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/2")
    _open_pay(page)
    assert page.get_attribute("#pDate", "max") == page.evaluate("new Date().toLocaleDateString('en-CA')")
    _pay(page, "100", "cash", date="2099-01-01", confirm=False)
    assert "can't be in the future" in page.text_content("#pErr")
    assert not page.locator("#pConfirm").is_visible()
    err = page.evaluate("""() => TCPDeskApi.recordPayment({p_invoice_id: 2, p_amount: 100, p_method: 'cash', p_paid_on: '2099-01-01',
        p_request_id: crypto.randomUUID()}).then(() => 'recorded', e => e.message)""")
    assert err == "A payment date cannot be in the future"
    # A past date is fine and goes on the receipt.
    page.fill("#pDate", "2026-11-01"); page.click("#pNext"); page.click("#pYes")
    rows = _receipt_shown(page, "TCP-RCT-0003")
    assert rows["Date"] == "1 November 2026"
    assert not errors


def test_p04_lost_reply_offline_and_double_tap_record_once(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/2")
    _open_pay(page)
    req = page.evaluate("TCPDesk.pay().req")
    # The database records it, but the answer is lost on the way back.
    page.evaluate("__db.dropReply = 1")
    _pay(page, "200", "cash")
    page.wait_for_function("document.querySelector('#pMsg').textContent.includes('No connection')")
    assert "never recorded twice" in page.text_content("#pMsg")
    assert page.evaluate("TCPDesk.op().req") == req, "noted on the phone until the outcome is known"
    assert page.evaluate("__db.payments.length") == 3
    assert page.evaluate("TCPDesk.pay().req") == req, "the retry keeps the same request id"
    page.click("#pYes")
    _receipt_shown(page, "TCP-RCT-0003")
    assert page.evaluate("__db.payments.length") == 3, "the retry gave back the first receipt"
    assert "already recorded" in page.text_content("#rMsg")
    assert page.evaluate("TCPDesk.op()") is None
    # No connection at all, then a double tap.
    page.goto(BO + "#/invoice/2"); _open_pay(page)
    page.evaluate("__db.offlineOnce = 1")
    _pay(page, "100", "cash")
    page.wait_for_function("document.querySelector('#pMsg').textContent.includes('No connection')")
    assert page.evaluate("__db.payments.length") == 3
    page.evaluate("__db.calls = []")
    page.dblclick("#pYes")
    _receipt_shown(page, "TCP-RCT-0004")
    assert page.evaluate("__db.calls.filter(c => c === 'recordPayment').length") == 1
    assert page.evaluate("__db.payments.length") == 4
    # The same request id for a different amount is refused.
    err = page.evaluate("""() => TCPDeskApi.recordPayment({p_invoice_id: 2, p_amount: 1, p_method: 'cash', p_paid_on: '2026-11-01',
        p_request_id: __db.payments[3].request_id}).then(() => 'recorded', e => e.message)""")
    assert err == "This request id was already used for a different payment"
    assert not errors


def test_p05_expired_sign_in_keeps_the_payment_removed_access_clears_it(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/2")
    _open_pay(page)
    req = page.evaluate("TCPDesk.pay().req")
    assert page.evaluate("TCPDesk.op()") is None, "nothing is kept on the phone while the form is filled in"
    page.evaluate("__db.expired = true")
    _pay(page, "250", "bank_transfer", "GCB-77")
    page.wait_for_selector("#signin:not([hidden])")
    kept = page.evaluate("JSON.parse(localStorage.getItem('tcp-desk-op-u-owner'))")
    assert kept["req"] == req and kept["amount"] == 250 and kept["ref"] == "GCB-77" and kept["type"] == "payment"
    page.evaluate("__db.expired = false")
    # Signing in by link reloads the page: a true reload, memory gone.
    page.evaluate("sessionStorage.setItem('no-auto-sign-in', '1')"); page.reload()
    assert page.evaluate("TCPDesk.pay()") is None
    _sign_in(page)
    # Straight back to its invoice; the database says it was not recorded,
    # so it is offered again under the same request id.
    page.wait_for_selector("#payForm:not([hidden])")
    assert page.input_value("#pAmt") == "250.00" and page.input_value("#pRef") == "GCB-77"
    assert page.is_checked('input[name="pm"][value="bank_transfer"]')
    assert "not recorded" in page.text_content("#pMsg")
    assert page.evaluate("TCPDesk.pay().req") == req
    page.click("#pNext"); page.click("#pYes")
    _receipt_shown(page, "TCP-RCT-0003")
    assert page.evaluate("localStorage.getItem('tcp-desk-op-u-owner')") is None
    # Removed access in the middle of a payment: signed out, nothing kept.
    page.goto(BO + "#/invoice/3"); _open_pay(page)
    page.evaluate("__db.staff[0].active = false")
    _pay(page, "50", "cash")
    page.wait_for_selector("#signin:not([hidden])")
    assert "access has ended" in page.text_content("#signMsg")
    assert page.evaluate("localStorage.getItem('tcp-desk-op-u-owner')") is None
    assert page.evaluate("__db.payments.length") == 3
    assert not errors


def _receipt_pdf(page):
    b64 = page.evaluate("async () => (await TCPDesk.makeReceiptPdf(TCPDesk.receipt())).output('datauristring').split(',')[1]")
    reader = PdfReader(io.BytesIO(base64.b64decode(b64)))
    return [tidy_pdf_text(p.extract_text()) for p in reader.pages], [(float(p.mediabox.width), float(p.mediabox.height)) for p in reader.pages]


def test_p06_receipt_pdf_is_frozen_at_the_moment(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/3")
    # TCP-RCT-0001: GH₵300 paid before anything else.
    page.goto(BO + "#/receipt/1")
    _receipt_shown(page, "TCP-RCT-0001")
    texts, sizes = _receipt_pdf(page)
    assert len(texts) == 1 and abs(sizes[0][0] - 595.28) < 1 and abs(sizes[0][1] - 841.89) < 1, "one A4 page"
    t = texts[0]
    for want in ["RECEIPT", "TCP-RCT-0001", "TCP-INV-0002", "Yaw Part", "GH₵300.00", "Cash", "Paid before this receipt GH₵0.00",
                 "Balance after GH₵450.00", "Invoice TCP-INV-0002 total GH₵750.00", "Test Owner"]:
        assert want in t, (want, t)
    assert "PAID IN FULL" not in t
    # A later payment clears the invoice; the first receipt does not change.
    page.goto(BO + "#/invoice/3"); _open_pay(page); page.click("#pFull"); _pay(page, "450.00", "cash")
    _receipt_shown(page, "TCP-RCT-0003")
    t2 = _receipt_pdf(page)[0][0]
    assert "PAID IN FULL" in t2 and "Paid before this receipt GH₵300.00" in t2 and "Balance after GH₵0.00" in t2
    page.goto(BO + "#/receipt/1"); _receipt_shown(page, "TCP-RCT-0001")
    assert _receipt_pdf(page)[0][0] == t, "an old receipt is drawn exactly as before"
    assert not errors


def _fake_share(page):
    page.evaluate("""() => { window.__shared = [];
        navigator.canShare = () => true;
        navigator.share = d => { window.__shared.push({keys: Object.keys(d), files: (d.files || []).map(f => f.name), text: d.text}); return Promise.resolve(); }; }""")


def test_p07_sharing_receipts(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/3", perms=["clipboard-read", "clipboard-write"], staff=TEAM, users=[OWNER, FIN, SALES])
    _open_pay(page); _pay(page, "200", "mobile_money", "MP1")
    _receipt_shown(page, "TCP-RCT-0003")
    _fake_share(page)
    page.click("#rShare")
    page.wait_for_function("window.__shared.length === 1")
    shared = page.evaluate("window.__shared[0]")
    assert shared["files"] == ["TCP Receipt TCP-RCT-0003.pdf"] and "text" not in shared["keys"], shared
    assert page.evaluate("navigator.clipboard.readText()") == \
        "Hello Yaw, here is your receipt TCP-RCT-0003 for GH₵200.00 on invoice TCP-INV-0002. Balance: GH₵250.00."
    assert "paste it as the caption" in page.text_content("#rMsg")
    # Paid in full: the message says so.
    page.goto(BO + "#/invoice/3"); _open_pay(page); page.click("#pFull"); _pay(page, "250.00", "cash")
    _receipt_shown(page, "TCP-RCT-0004"); _fake_share(page)
    page.click("#rShare"); page.wait_for_function("window.__shared.length === 1")
    assert page.evaluate("navigator.clipboard.readText()") == \
        "Hello Yaw, here is your receipt TCP-RCT-0004 for GH₵250.00 on invoice TCP-INV-0002. Invoice TCP-INV-0002 is now paid in full. Thank you."
    # A refund can be shared; a correction cannot (decision 5).
    page.evaluate("TCPDeskApi.refundPayment({p_payment_id: 3, p_amount: 50, p_method: 'cash', p_reason: 'Short delivery', p_request_id: crypto.randomUUID()})")
    page.evaluate("TCPDeskApi.correctPayment({p_payment_id: 1, p_reason: 'Wrong invoice', p_request_id: crypto.randomUUID()})")
    page.goto(BO + "#/receipt/5"); _receipt_shown(page, "TCP-RCT-0005")
    assert page.text_content("#rTitle") == "Refund TCP-RCT-0005" and page.locator("#rShare").is_visible()
    _fake_share(page); page.click("#rShare"); page.wait_for_function("window.__shared.length === 1")
    assert page.evaluate("navigator.clipboard.readText()") == \
        "Hello Yaw, here is your refund receipt TCP-RCT-0005 for GH₵50.00 on invoice TCP-INV-0002. Balance: GH₵50.00."
    page.goto(BO + "#/receipt/6"); _receipt_shown(page, "TCP-RCT-0006")
    assert page.text_content("#rTitle") == "Correction TCP-RCT-0006"
    assert not page.locator("#rShare").is_visible() and page.locator("#rInternal").is_visible()
    assert page.locator("#rPdf").is_visible(), "a correction still has its PDF"
    t = _receipt_pdf(page)[0][0]
    assert "CORRECTION" in t and "Wrong invoice" in t and "TCP-RCT-0001" in t
    assert "AMOUNT REVERSED\n-GH₵300.00" in t and "This correction -GH₵300.00" in t, "a reversal never prints as money in"
    assert not errors


def test_p08_correcting_a_payment(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/3", staff=TEAM, users=[OWNER, FIN, SALES], who=FIN)
    page.wait_for_selector("#issuedSec:not([hidden])")
    page.click('[data-fix="correction"][data-pid="1"]')
    page.wait_for_selector("#fixForm:not([hidden])")
    assert not page.locator("#fixMoney").is_visible(), "a correction reverses the whole payment"
    page.click("#fNext")
    assert "Give a reason" in page.text_content("#fErr")
    page.fill("#fWhy", "Recorded on the wrong invoice")
    page.click("#fNext")
    page.wait_for_selector("#fConfirm:not([hidden])")
    assert "Reverse TCP-RCT-0001 (GH₵300.00)" in page.text_content("#fSummary") and "Balance after: GH₵750.00" in page.text_content("#fSummary")
    page.click("#fYes")
    rows = _receipt_shown(page, "TCP-RCT-0003")
    assert rows["Amount reversed"] == "−GH₵300.00" and rows["Reverses"] == "TCP-RCT-0001"
    assert rows["Reason"] == "Recorded on the wrong invoice" and rows["Balance after"] == "GH₵750.00" and rows["Recorded by"] == "Fin"
    page.click("#rInv"); page.wait_for_selector("#issuedSec:not([hidden])")
    first = page.locator(".dk-pay").first
    assert "corrected" in first.text_content()
    assert first.locator("[data-fix]").count() == 0, "a corrected payment can't be corrected or refunded"
    assert page.evaluate("TCPDesk.doc().status") == "unpaid"
    err = page.evaluate("""() => TCPDeskApi.correctPayment({p_payment_id: 1, p_reason: 'again', p_request_id: crypto.randomUUID()})
        .then(() => 'done', e => e.message)""")
    assert err == "This payment has already been corrected"
    assert not errors


def test_p09_refunds_and_their_limits(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/3", staff=TEAM, users=[OWNER, FIN, SALES], who=FIN)
    page.wait_for_selector("#issuedSec:not([hidden])")
    page.click('[data-fix="refund"][data-pid="1"]')
    page.wait_for_selector("#fixForm:not([hidden])")
    assert "Up to GH₵300.00 can be refunded" in page.text_content("#fixFor")
    page.fill("#fAmt", "100"); page.check('input[name="fm"][value="mobile_money"]'); page.fill("#fWhy", "Two bags returned")
    page.click("#fNext")
    assert "MoMo transaction ID" in page.text_content("#fErr")
    page.fill("#fRef", "MP99"); page.click("#fNext"); page.click("#fYes")
    rows = _receipt_shown(page, "TCP-RCT-0003")
    assert rows["Amount refunded"] == "−GH₵100.00" and rows["Balance after"] == "GH₵550.00"
    page.click("#rInv"); page.wait_for_selector("#issuedSec:not([hidden])")
    first = page.locator(".dk-pay").first
    assert "GH₵100.00 refunded" in first.text_content()
    assert first.locator('[data-fix="correction"]').count() == 0, "no correcting after a refund"
    first.locator('[data-fix="refund"]').click()
    page.wait_for_selector("#fixForm:not([hidden])")
    page.fill("#fAmt", "250"); page.check('input[name="fm"][value="cash"]'); page.fill("#fWhy", "More returned"); page.click("#fNext")
    assert "At most GH₵200.00 can be refunded from TCP-RCT-0001" in page.text_content("#fErr")
    page.click("#fAll"); assert page.input_value("#fAmt") == "200.00"
    page.click("#fNext"); page.click("#fYes")
    _receipt_shown(page, "TCP-RCT-0004")
    page.click("#rInv"); page.wait_for_selector("#issuedSec:not([hidden])")
    assert page.locator(".dk-pay").first.locator("[data-fix]").count() == 0, "nothing left to refund"
    for call, want in [("correctPayment({p_payment_id: 1, p_reason: 'x', p_request_id: crypto.randomUUID()})",
                        "This payment has refunds against it and can no longer be corrected"),
                       ("refundPayment({p_payment_id: 1, p_amount: 1, p_method: 'cash', p_reason: 'x', p_request_id: crypto.randomUUID()})",
                        "Refunds would total GH₵ 301.00, more than the GH₵ 300.00 paid")]:
        assert page.evaluate(f"() => TCPDeskApi.{call}.then(() => 'done', e => e.message)") == want
    assert not errors


@pytest.mark.parametrize("who,can_fix", [(SALES, False), (FIN, True), (OWNER, True)])
def test_p10_roles(browser, who, can_fix):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/3", staff=TEAM, users=[OWNER, FIN, SALES], who=who)
    page.wait_for_selector("#issuedSec:not([hidden])")
    assert page.locator("#payBtn").is_visible(), "every role records payments (decision 1)"
    assert (page.locator("[data-fix]").count() == 2) == can_fix
    if not can_fix:
        err = page.evaluate("""() => TCPDeskApi.refundPayment({p_payment_id: 1, p_amount: 1, p_method: 'cash', p_reason: 'x',
            p_request_id: crypto.randomUUID()}).then(() => 'done', e => e.message)""")
        assert "sales role cannot do this" in err
    _open_pay(page); _pay(page, "50", "cash")
    _receipt_shown(page, "TCP-RCT-0003")
    assert not errors


@pytest.mark.parametrize("inv", [1, 4, 6])
def test_p11_no_record_payment_on_drafts_cancelled_or_paid(browser, inv):
    page, errors = _bo(browser, seed=MIX, route=f"#/invoice/{inv}")
    # The owner's draft opens in the form; the others open read-only.
    page.wait_for_selector("#form:not([hidden])" if inv == 1 else "#issuedSec:not([hidden])")
    page.wait_for_timeout(200)
    assert not page.locator("#payBtn").is_visible()
    if inv == 1:
        assert not page.locator("#payBox").is_visible(), "a draft has no payments section"
    err = page.evaluate(f"""() => TCPDeskApi.recordPayment({{p_invoice_id: {inv}, p_amount: 1, p_method: 'cash', p_paid_on: '2026-01-10',
        p_request_id: crypto.randomUUID()}}).then(() => 'recorded', e => e.message)""")
    assert err != "recorded"
    assert not errors


@pytest.mark.parametrize("width", [360, 390])
def test_p12_payment_screens_fit_a_phone(browser, width):
    page, errors = _bo(browser, width=width, seed=MIX, route="#/invoice/3", staff=TEAM, users=[OWNER, FIN, SALES], who=FIN)
    fits = lambda: page.evaluate("document.documentElement.scrollWidth") <= width
    page.wait_for_selector("#payBtn:not([hidden])"); assert fits()
    _open_pay(page); page.check('input[name="pm"][value="bank_transfer"]'); assert fits()
    page.click("#pFull"); page.fill("#pRef", "GCB-1"); page.click("#pNext"); page.wait_for_selector("#pConfirm:not([hidden])"); assert fits()
    page.click("#pYes"); _receipt_shown(page, "TCP-RCT-0003"); assert fits()
    page.click("#rInv"); page.wait_for_selector("#issuedSec:not([hidden])")
    page.click('[data-fix="refund"][data-pid="1"]'); page.wait_for_selector("#fixForm:not([hidden])"); assert fits()
    assert not errors



def _fix(page, kind, pid, why, amount=None, method="cash", ref=""):
    page.click(f'[data-fix="{kind}"][data-pid="{pid}"]')
    page.wait_for_selector("#fixForm:not([hidden])")
    if amount:
        page.fill("#fAmt", amount); page.check(f'input[name="fm"][value="{method}"]'); page.fill("#fRef", ref)
    page.fill("#fWhy", why); page.click("#fNext")
    page.wait_for_selector("#fConfirm:not([hidden])"); page.click("#fYes")


@pytest.mark.parametrize("kind", ["refund", "correction"])
def test_p13_p14_lost_reply_then_expired_sign_in_records_once(browser, kind):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/3", staff=TEAM, users=[OWNER, FIN, SALES], who=FIN)
    page.wait_for_selector("#issuedSec:not([hidden])")
    # The database saves it, but the answer is lost on the way back.
    page.evaluate("__db.dropReply = 1")
    _fix(page, kind, 1, "Customer returned the goods", amount="120" if kind == "refund" else None)
    page.wait_for_function("document.querySelector('#fMsg').textContent.includes('may or may not')")
    req = page.evaluate("TCPDesk.fix().req")
    assert page.evaluate(f"__db.payments.filter(p => p.kind === '{kind}').length") == 1
    # Then the sign-in runs out on the retry, and the page is reloaded (as
    # opening the sign-in email's link does): everything in memory is gone.
    page.evaluate("__db.expired = true")
    page.click("#fYes")
    page.wait_for_selector("#signin:not([hidden])")
    kept = page.evaluate("JSON.parse(localStorage.getItem('tcp-desk-op-u-f'))")
    assert kept["req"] == req and kept["type"] == kind and kept["payId"] == 1
    page.evaluate("__db.expired = false")
    page.evaluate("sessionStorage.setItem('no-auto-sign-in', '1')"); page.reload()
    assert page.evaluate("TCPDesk.fix()") is None, "a true reload: nothing left in memory"
    page.wait_for_selector("#signin:not([hidden])")
    page.fill("#email", FIN["email"]); page.click("#emailForm button")
    page.wait_for_selector("#codeForm:not([hidden])"); page.fill("#code", "123456"); page.click("#codeForm button")
    # The app goes to the invoice, finds the request in the database and
    # shows the original receipt: nothing recorded twice.
    _receipt_shown(page, "TCP-RCT-0003")
    assert "already recorded" in page.text_content("#rMsg")
    assert page.evaluate(f"__db.payments.filter(p => p.kind === '{kind}').length") == 1
    assert page.evaluate("__db.payments.find(p => p.receipt_no === 'TCP-RCT-0003').request_id") == req
    assert page.evaluate("localStorage.getItem('tcp-desk-op-u-f')") is None
    page.click("#rInv"); page.wait_for_selector("#issuedSec:not([hidden])")
    assert not page.locator("#opBox").is_visible() and page.locator("#payBtn").is_visible()
    assert not errors


def test_p15_sign_out_expiry_isolation_and_unknown_outcome(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/2")
    _open_pay(page)
    page.evaluate("__db.offline = true")
    _pay(page, "100", "cash")
    page.wait_for_function("document.querySelector('#pMsg').textContent.includes('No connection')")
    # Cancel can't drop it while the outcome is unknown.
    page.click("#pChange"); page.click("#pCancel")
    page.wait_for_function("document.querySelector('#pMsg').textContent.includes(\"Can't cancel yet\")")
    assert page.evaluate("TCPDesk.op()") is not None
    # Reopening the invoice when the check can't reach the database:
    # nothing new can be started, and "Check again" is offered.
    page.evaluate("__db.offline = false; __db.offlineFor = ['byRequest']; location.hash = '#/invoices'")
    page.wait_for_selector("#listV:not([hidden])")
    page.evaluate("location.hash = '#/invoice/2'")
    page.wait_for_selector("#opCheck:not([hidden])")
    assert "Could not check" in page.text_content("#opMsg")
    assert not page.locator("#payBtn").is_visible()
    # Another invoice: told to check the first one, no Record payment.
    page.evaluate("location.hash = '#/invoice/3'")
    page.wait_for_selector("#opOpen:not([hidden])")
    assert not page.locator("#payBtn").is_visible()
    # Sign out warns first; "Sign out anyway" removes the note.
    page.click("#signOut")
    page.wait_for_selector("#soBox:not([hidden])")
    assert "Signing out abandons it" in page.text_content("#soMsg") and page.locator("#tool").is_visible()
    page.click("#soGo")
    page.wait_for_selector("#signin:not([hidden])")
    assert page.evaluate("localStorage.getItem('tcp-desk-op-u-owner')") is None
    assert page.evaluate("__db.payments.length") == 2
    # A note older than 24 hours is dropped.
    page.evaluate("__db.offlineFor = []")
    old = {"user": "u-owner", "at": 0, "type": "payment", "invoiceId": 2, "req": "11111111-1111-4111-8111-111111111111",
           "amount": 100, "method": "cash", "ref": None, "date": "2026-11-01", "reason": None, "payId": None}
    page.evaluate("o => localStorage.setItem('tcp-desk-op-u-owner', JSON.stringify(o))", old)
    page.evaluate("o => localStorage.setItem('tcp-desk-op-u-f', JSON.stringify({...o, at: Date.now()}))", old)
    # (The test's sign-in is restored on every load.)
    page.evaluate("location.hash = '#/invoice/2'"); page.reload()
    page.wait_for_selector("#payBtn:not([hidden])")
    assert page.evaluate("localStorage.getItem('tcp-desk-op-u-owner')") is None, "over 24 hours: dropped"
    assert not page.locator("#opBox").is_visible()
    assert page.evaluate("__db.calls.filter(c => c === 'byRequest').length") == 0
    assert not errors


def test_p15b_another_staff_member_never_inherits_it(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/2", staff=TEAM, users=[OWNER, FIN, SALES], who=SALES)
    fresh = {"user": "u-owner", "at": 0, "type": "payment", "invoiceId": 2, "req": "22222222-2222-4222-8222-222222222222",
             "amount": 100, "method": "cash", "ref": None, "date": "2026-11-01", "reason": None, "payId": None}
    # The owner's note, and a copy filed under the sales login but still
    # naming the owner.
    page.evaluate("o => { const now = {...o, at: Date.now()}; localStorage.setItem('tcp-desk-op-u-owner', JSON.stringify(now));"
                  " localStorage.setItem('tcp-desk-op-u-s', JSON.stringify(now)); }", fresh)
    page.reload(); page.wait_for_selector("#payBtn:not([hidden])")
    assert not page.locator("#opBox").is_visible()
    assert page.evaluate("localStorage.getItem('tcp-desk-op-u-s')") is None, "a note naming someone else is dropped"
    assert page.evaluate("localStorage.getItem('tcp-desk-op-u-owner')") is not None, "the owner's own note is left for the owner"
    assert not errors


def test_p16_the_note_holds_nothing_about_the_customer(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/3", staff=TEAM, users=[OWNER, FIN, SALES], who=FIN)
    page.wait_for_selector("#issuedSec:not([hidden])")
    page.evaluate("__db.offline = true")
    _fix(page, "refund", 1, "Two bags returned", amount="50", method="mobile_money", ref="MP42")
    page.wait_for_function("document.querySelector('#fMsg').textContent.includes('No connection')")
    raw = page.evaluate("localStorage.getItem('tcp-desk-op-u-f')")
    kept = json.loads(raw)
    assert set(kept) == {"user", "at", "type", "invoiceId", "payId", "req", "amount", "method", "ref", "date", "reason"}
    for private in ["Yaw", "Part", "233552331234", "552331234", "TCP-C-"]:
        assert private not in raw, private
    everything = page.evaluate("JSON.stringify(Object.fromEntries(Object.entries(localStorage)))")
    assert "Yaw" not in everything and "552331234" not in everything
    assert not errors



@pytest.mark.parametrize("change", ["invoice", "kind", "payment", "amount"])
def test_p17_request_id_match_alone_is_not_success(browser, change):
    page, errors = _bo(browser, seed=MIX, route="#/invoices")
    page.wait_for_selector("#listV:not([hidden])")
    # A real refund of GH₵40 from TCP-RCT-0001 (invoice 3), request id R.
    page.evaluate("""TCPDeskApi.refundPayment({p_payment_id: 1, p_amount: 40, p_method: 'cash', p_reason: 'r',
        p_request_id: '33333333-3333-4333-8333-333333333333'})""")
    note = {"user": "u-owner", "type": "refund", "invoiceId": 3, "payId": 1, "req": "33333333-3333-4333-8333-333333333333",
            "amount": 40, "method": "cash", "ref": None, "date": None, "reason": "r"}
    note.update({"invoice": {"invoiceId": 2}, "kind": {"type": "correction"}, "payment": {"payId": 2},
                 "amount": {"amount": 41}}[change])
    page.evaluate("o => localStorage.setItem('tcp-desk-op-u-owner', JSON.stringify({...o, at: Date.now()}))", note)
    page.evaluate(f"location.hash = '#/invoice/{note['invoiceId']}'")
    page.wait_for_function("document.querySelector('#opMsg').textContent.includes('matches a different record')")
    assert "TCP-RCT-0003" in page.text_content("#opMsg")
    assert not page.locator("#rcptSec").is_visible(), "not shown as its receipt"
    assert not page.locator("#payBtn").is_visible() and page.locator("[data-fix]").count() == 0, "nothing new can be recorded"
    assert page.evaluate("TCPDesk.op()") is not None
    assert page.evaluate("__db.payments.length") == 3
    assert not errors



# ---- Phase 2.1: the Payments tab and cancelling invoices ---------------------
# MIX: invoices of GH₵750: 2 = TCP-INV-0001 Ama (+233241234567), unpaid;
# 3 = TCP-INV-0002 Yaw, GH₵300 paid (TCP-RCT-0001, dated 22 Nov 2026);
# 4 = Efua, paid (TCP-RCT-0002); 5 = Kwame, unpaid and overdue.
def _api(page, js):
    return page.evaluate("async () => { const today = new Date().toLocaleDateString('en-CA'); return " + js + "; }")


def _ledger(page, hash_="#/payments"):
    page.evaluate("h => location.hash = h", hash_)
    page.wait_for_selector("#ledV:not([hidden])")
    page.wait_for_function("document.querySelector('#tNet').textContent !== '—' && !document.querySelector('#ledMore').disabled")


def _today_records(page):
    """Today: 200 MoMo on Ama (then corrected), 300 cash on Yaw (50 refunded)."""
    _api(page, """(async () => {
      const a = await TCPDeskApi.recordPayment({p_invoice_id: 2, p_amount: 200, p_method: 'mobile_money', p_reference: 'MP5551234',
        p_paid_on: today, p_request_id: crypto.randomUUID()});
      const b = await TCPDeskApi.recordPayment({p_invoice_id: 3, p_amount: 300, p_method: 'cash', p_paid_on: today, p_request_id: crypto.randomUUID()});
      await TCPDeskApi.correctPayment({p_payment_id: a.id, p_reason: 'Never arrived', p_request_id: crypto.randomUUID()});
      await TCPDeskApi.refundPayment({p_payment_id: b.id, p_amount: 50, p_method: 'cash', p_reason: 'One bag back', p_request_id: crypto.randomUUID()});
    })()""")


def test_l01_today_totals_kinds_and_home(browser):
    page, errors = _bo(browser, seed=MIX, route="#/")
    page.wait_for_function("document.querySelector('#hToday').textContent !== '—'")
    assert page.text_content("#hToday") == "GH₵0.00", "nothing received today yet"
    _today_records(page)
    _ledger(page)
    assert "Today" in page.text_content("#ledWhen")
    assert page.text_content("#tNet") == "GH₵250.00"
    assert page.text_content("#tRec") == "GH₵300.00"
    assert page.text_content("#tRecBy") == "MoMo GH₵0.00 · Cash GH₵300.00 · Bank GH₵0.00", "the corrected MoMo payment counts nothing"
    assert page.text_content("#tRef") == "GH₵50.00" and page.locator("#tRefBox").is_visible()
    assert page.text_content("#tCount") == "4"
    assert "Recorded by TCP staff" in page.text_content("#ledTotals")
    rows = {r.locator(".dk-led-top b").text_content(): (r.locator(".dk-kind").text_content(), r.locator(".amt").text_content())
            for r in page.locator("#ledRows .dk-led").all()}
    assert rows == {"TCP-RCT-0006": ("Refund of TCP-RCT-0004", "−GH₵50.00"),
                    "TCP-RCT-0005": ("Correction of TCP-RCT-0003", "Reverses GH₵200.00"),
                    "TCP-RCT-0004": ("Payment", "+GH₵300.00"),
                    "TCP-RCT-0003": ("Payment · corrected", "GH₵200.00")}, rows
    assert page.locator(".dk-led.k-corrected .amt s").count() == 1, "the corrected payment is struck through, and still listed"
    # Rows open their receipts.
    page.click('#ledRows [data-rid="6"]')
    _receipt_shown(page, "TCP-RCT-0006")
    # Home's Received today is the same figure.
    page.goto(BO + "#/")
    page.wait_for_function("document.querySelector('#hToday').textContent !== '—'")
    assert page.text_content("#hToday") == "GH₵250.00"
    page.click("#hTodayLink")
    page.wait_for_selector("#ledV:not([hidden])")
    assert not errors


def test_l02_all_time_three_sums_agree(browser):
    page, errors = _bo(browser, seed=MIX, route="#/")
    _today_records(page)
    _ledger(page, "#/payments?period=all")
    assert page.text_content("#ledWhen") == "All time"
    ledger_sum = page.evaluate("Math.round(__db.payments.reduce((a, p) => a + p.amount * 100, 0)) / 100")
    paid_sum = page.evaluate("[1,2,3,4,5,6].map(i => TCPDeskApi.__doc(i).paid).reduce((a, b) => a + b, 0)")
    assert ledger_sum == paid_sum == 1300, (ledger_sum, paid_sum)   # 300 + 750 seeded, + 200 - 200 + 300 - 50
    assert page.text_content("#tNet") == "GH₵1,300.00"
    assert page.text_content("#tRec") == "GH₵1,350.00" and page.text_content("#tRef") == "GH₵50.00"
    assert page.text_content("#tCount") == "6"
    assert not errors


def test_l03_filters_narrow_the_list_not_the_totals(browser):
    page, errors = _bo(browser, seed=MIX, route="#/")
    _today_records(page)
    _ledger(page)
    before = [page.text_content(x) for x in ("#tNet", "#tRec", "#tRef", "#tCount")]
    page.click('#kinds [data-kind="refund"]')
    page.wait_for_function("location.hash.includes('kind=refund')")
    _ledger(page, page.evaluate("location.hash"))
    assert page.locator("#ledRows .dk-led").count() == 1 and "1 record match" in page.text_content("#ledInfo")
    assert [page.text_content(x) for x in ("#tNet", "#tRec", "#tRef", "#tCount")] == before
    page.click('#kinds [data-kind="all"]'); page.click('#methods [data-method="mobile_money"]')
    page.wait_for_function("location.hash.includes('method=mobile_money') && !location.hash.includes('kind=')")
    _ledger(page, page.evaluate("location.hash"))
    assert page.locator("#ledRows .dk-led").count() == 2, "the MoMo payment and its correction"
    assert [page.text_content(x) for x in ("#tNet", "#tRec", "#tRef", "#tCount")] == before
    # Back returns to the previous view.
    page.go_back()
    page.wait_for_function("!location.hash.includes('method=')")
    assert not errors


def test_l04_paging_never_changes_the_totals(browser):
    page, errors = _bo(browser, seed=MIX, route="#/")
    _api(page, """(async () => { for (let i = 0; i < 35; i++) await TCPDeskApi.recordPayment({p_invoice_id: 2, p_amount: 1,
        p_method: 'cash', p_paid_on: today, p_request_id: crypto.randomUUID()}); })()""")
    _ledger(page)
    assert page.text_content("#tCount") == "35" and page.text_content("#tNet") == "GH₵35.00"
    assert page.locator("#ledRows .dk-led").count() == 30 and page.locator("#ledMore").is_visible()
    page.click("#ledMore")
    page.wait_for_function("document.querySelectorAll('#ledRows .dk-led').length === 35")
    assert not page.locator("#ledMore").is_visible()
    assert page.text_content("#tCount") == "35" and page.text_content("#tNet") == "GH₵35.00"
    ids = page.evaluate("[...document.querySelectorAll('#ledRows .dk-led')].map(a => +a.dataset.rid)")
    assert len(set(ids)) == 35 and ids == sorted(ids, reverse=True), "no record skipped or repeated, newest first"
    assert not errors


@pytest.mark.parametrize("typed,want", [
    ("0241234567", {"TCP-RCT-0003", "TCP-RCT-0005"}),        # Ama's number, the way staff type it
    ("024 123 4567", {"TCP-RCT-0003", "TCP-RCT-0005"}),
    ("+233 24 123 4567", {"TCP-RCT-0003", "TCP-RCT-0005"}),
    ("4567", {"TCP-RCT-0003", "TCP-RCT-0005"}),              # its last digits
    ("mp555", {"TCP-RCT-0003", "TCP-RCT-0005"}),              # part of the MoMo reference (its correction carries it too)
    ("RCT-0006", {"TCP-RCT-0006"}),
    ("TCP-INV-0002", {"TCP-RCT-0001", "TCP-RCT-0004", "TCP-RCT-0006"}),
    ("yaw", {"TCP-RCT-0001", "TCP-RCT-0004", "TCP-RCT-0006"}),
])
def test_l05_search_on_stored_formats(browser, typed, want):
    page, errors = _bo(browser, seed=MIX, route="#/")
    _today_records(page)
    _ledger(page, "#/payments?period=all")
    page.fill("#lq", typed)
    page.wait_for_function("n => document.querySelectorAll('#ledRows .dk-led').length === n && location.hash.includes('q=')", arg=len(want))
    got = {b.text_content() for b in page.locator("#ledRows .dk-led-top b").all()}
    assert got == want, (typed, got)
    assert page.text_content("#tCount") == "6", "search narrows the list only"
    assert not errors


@pytest.mark.parametrize("who,owner", [(OWNER, True), (SALES, False), (FIN, False)])
def test_l06_roles(browser, who, owner):
    page, errors = _bo(browser, seed=MIX, route="#/payments", staff=TEAM, users=[OWNER, FIN, SALES], who=who)
    page.wait_for_selector("#ledV:not([hidden])")
    page.wait_for_function("document.querySelector('#tNet').textContent !== '—'")
    assert page.locator('#tabs [data-tab="payments"]').is_visible()
    page.evaluate("location.hash = '#/invoice/2'")
    page.wait_for_selector("#issuedSec:not([hidden])")
    assert page.locator("#cxBox").is_visible() == owner
    if not owner:
        err = page.evaluate("() => TCPDeskApi.cancel(2, 'x').then(() => 'done', e => e.message)")
        assert "role cannot do this" in err
    assert not errors


def test_l07_cancel_an_unpaid_invoice(browser):
    page, errors = _bo(browser, seed=MIX, route="#/")
    page.wait_for_function("document.querySelector('#hOwed').textContent !== '—'")
    owed = page.text_content("#hOwed")
    page.evaluate("location.hash = '#/invoice/2'")
    page.wait_for_selector("#cxBox:not([hidden])")
    assert "cannot be undone" in page.text_content("#cxHeld")
    page.click("#cxOpen"); page.click("#cxNext")
    assert "Give a reason" in page.text_content("#cxErr")
    page.fill("#cxWhy", "Customer changed their mind"); page.click("#cxNext")
    page.wait_for_selector("#cxConfirm:not([hidden])")
    summary = page.text_content("#cxSummary")
    assert "Cancel TCP-INV-0001 for Ama Unpaid, GH₵750.00?" in summary and "cannot be undone" in summary
    assert page.evaluate("TCPDeskApi.__doc(2).state") == "issued", "nothing happens before the confirm"
    page.click("#cxKeep"); assert not page.locator("#cxConfirm").is_visible()
    page.click("#cxOpen"); page.fill("#cxWhy", "Customer changed their mind"); page.click("#cxNext"); page.click("#cxYes")
    page.wait_for_function("document.querySelector('#viewTitle').textContent === 'Cancelled invoice'")
    sumtext = page.text_content("#issued")
    assert "Cancelled because" in sumtext and "Customer changed their mind" in sumtext and "by Test Owner" in sumtext
    assert not page.locator("#shareBtn").is_visible() and page.locator("#pdfBtn").is_enabled()
    assert not page.locator("#payBtn").is_visible() and not page.locator("#cxBox").is_visible()
    # The PDF, marked CANCELLED, named so.
    t = _pdf(page)[0][0]
    assert "CANCELLED on" in t and "Customer changed their mind" in t and "TCP-INV-0001" in t
    with page.expect_download() as d:
        page.click("#pdfBtn")
    assert d.value.suggested_filename == "TCP Invoice TCP-INV-0001 CANCELLED.pdf"
    page.goto(BO + "#/")
    page.wait_for_function("o => document.querySelector('#hOwed').textContent !== '—' && document.querySelector('#hOwed').textContent !== o", arg=owed)
    assert page.text_content("#hOwed") == "GH₵1,200.00", "only Yaw's 450 and Kwame's 750 are owed now"
    assert not errors


def test_l08_money_held_then_refunded_in_full(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/3")
    page.wait_for_selector("#cxBox:not([hidden])")
    assert "holds GH₵300.00 in payments" in page.text_content("#cxHeld")
    assert not page.locator("#cxOpen").is_visible()
    err = page.evaluate("() => TCPDeskApi.cancel(3, 'x').then(() => 'done', e => e.message)")
    assert "still holds GH₵ 300.00" in err
    _api(page, "TCPDeskApi.refundPayment({p_payment_id: 1, p_amount: 300, p_method: 'cash', p_reason: 'Order called off', p_request_id: crypto.randomUUID()})")
    page.reload(); page.wait_for_selector("#cxOpen:not([hidden])")
    page.click("#cxOpen"); page.fill("#cxWhy", "Order called off"); page.click("#cxNext"); page.click("#cxYes")
    page.wait_for_function("document.querySelector('#viewTitle').textContent === 'Cancelled invoice'")
    hist = page.text_content("#payList")
    assert "TCP-RCT-0001" in hist and "Refund of TCP-RCT-0001" in hist, "the history stays: payment, then refund"
    assert not errors


@pytest.mark.parametrize("width", [360, 390])
def test_l09_payments_and_cancel_fit_a_phone(browser, width):
    page, errors = _bo(browser, width=width, seed=MIX, route="#/")
    _today_records(page)
    fits = lambda: page.evaluate("document.documentElement.scrollWidth") <= width
    _ledger(page); assert fits()
    _ledger(page, "#/payments?period=all"); assert fits()
    page.evaluate("location.hash = '#/invoice/5'"); page.wait_for_selector("#cxBox:not([hidden])")
    page.click("#cxOpen"); page.fill("#cxWhy", "x"); page.click("#cxNext"); page.wait_for_selector("#cxConfirm:not([hidden])"); assert fits()
    assert not errors



LONG_WHY = ("Customer cancelled the order after delivery arrangements changed and the materials were no longer required; "
            "the site manager confirmed by phone on Monday that the foundation work has been postponed until the new year, "
            "so nothing will be delivered and nothing is owed on this invoice.")


@pytest.mark.parametrize("lines", [1, 40])
def test_l10_long_cancellation_reason_in_full(browser, lines):
    page, errors = _bo(browser, seed=[{"name": "Ama Unpaid", "phone": "+233241234567", "state": "issued", "due": FUTURE,
                                       "lines": [{"qty": 1, "price": 10}] * lines}], route="#/invoice/1")
    page.wait_for_selector("#cxBox:not([hidden])")
    page.click("#cxOpen"); page.fill("#cxWhy", LONG_WHY); page.click("#cxNext"); page.click("#cxYes")
    page.wait_for_function("document.querySelector('#viewTitle').textContent === 'Cancelled invoice'")
    texts, _ = _pdf(page)
    whole = " ".join(" ".join(t.split()) for t in texts)
    assert ("Reason: " + LONG_WHY) in whole, "the whole reason, word for word"
    assert all("CANCELLED" in t for t in texts), "every page is marked"
    # Nothing is drawn into the footer band (below 282 mm = 799.4 pt from the
    # top) but the footer itself and the short CANCELLED line: word boxes
    # from pdfminer (pure Python, so it runs the same on GitHub's runners).
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer, LTTextLine
    b64 = page.evaluate("async () => (await TCPDesk.makePdf(TCPDesk.doc())).output('datauristring').split(',')[1]")
    footer_words = set("CANCELLED on November 2026. The reason is in the cancellation note. thecementpeople.com · 055 846 3468 Page of".split())
    low = []
    for pg in extract_pages(io.BytesIO(base64.b64decode(b64))):
        for box in pg:
            if not isinstance(box, LTTextContainer):
                continue
            for line in box:
                if isinstance(line, LTTextLine) and pg.height - line.y0 > 799.4:   # its bottom edge, from the top
                    low += [w for w in line.get_text().split() if w not in footer_words and not w.isdigit()]
    assert not low, low
    assert len(texts) == (1 if lines == 1 else len(texts)) and (lines == 1 or len(texts) >= 2)
    assert not errors


# ---- Phase 2.2: notes from estimate to receipt --------------------------------
# An unusual phrase written into internal notes: it must never appear in a
# PDF, a WhatsApp message or the address (design, "Search security").
SECRET = "ZEBRAQUARTZ internal only"
NOTE_TEAM = TEAM


def _add_note(page, body, cat="general"):
    page.wait_for_selector("#nAdd:not([hidden])")
    page.fill("#nBody", body)
    page.check(f'input[name="ncat"][value="{cat}"]')
    page.click("#nSave")
    page.wait_for_function("document.querySelector('#nMsg').textContent === 'Note saved.'")


def _correct(page, button, body):
    """Tap a Correct link, type the correction and save it."""
    button.click()
    page.wait_for_selector("#ncBox")
    page.fill("#ncText", body)
    page.click("#ncSave")
    page.wait_for_function("!document.querySelector('#ncBox')")


def _seed_note(page, invoice_id, body, by="u-s", corrects_note=None, corrects_payment=None, at="2026-11-22T09:00:00.000Z", cat="general"):
    """A note added by another staff member, straight into the database."""
    page.evaluate("""a => { __db.notes.push({id: __db.notes.length + 1, invoice_id: a.inv, body: a.body, category: a.cat,
        corrects_note_id: a.cn, corrects_payment_id: a.cp, estimate_ref: null, created_by: a.by, created_at: a.at, request_id: null}); }""",
                  {"inv": invoice_id, "body": body, "cat": cat, "cn": corrects_note, "cp": corrects_payment, "by": by, "at": at})


def _latest(locator):
    """The latest-correction line under a corrected note, as shown."""
    return " ".join(locator.locator(".dk-note-latest").first.text_content().split())


# N01: the estimator's note: in the WhatsApp message and the printed
# estimate only when filled in; a message without a note is as before.
def test_n01_estimator_note(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
    page = ctx.new_page()
    page.goto(SITE_URL, wait_until="load")
    page.wait_for_selector("#list .row")
    settle(page)
    page.evaluate("o => { for (const k in o) qty[k] = o[k]; renderList(); renderEst(); }", ORDER)
    page.fill("#loc", "Buduburam")
    before = whatsapp_message(page)
    assert "Note:" not in before and page.locator(".q-note").count() == 0
    assert page.get_attribute("#enote", "maxlength") == "300"
    page.fill("#enote", "Please call  before\ndelivery, gate is blue")
    msg = whatsapp_message(page)
    assert "*Drop-off location:* Buduburam\n*Note:* Please call before delivery, gate is blue\n" in msg
    assert msg.replace("*Note:* Please call before delivery, gate is blue\n", "") == before, "only the note line is added"
    assert "Please call before delivery, gate is blue" in page.text_content(".q-note")
    page.fill("#enote", "")
    assert whatsapp_message(page) == before, "cleared: exactly as before"
    ctx.close()


# N02: the reader puts an estimate's note into the draft's internal notes
# (once, on the first save); Copy to note to customer fills the note to the
# customer and leaves the internal note; after issue the button is gone, and
# the invoice PDF prints the note to the customer, never internal notes.
def test_n02_estimate_note_to_internal_notes_and_copy(browser):
    page, errors = _desk(browser)
    page.wait_for_selector("#tool:not([hidden])")
    page.fill("#paste", _estimate_message(browser, ORDER, loc="Buduburam", note="Deliver after 2pm please"))
    page.click("#readBtn")
    page.wait_for_selector("#form:not([hidden])")
    page.wait_for_selector("#nEst:not([hidden])")
    assert "Deliver after 2pm please" in page.text_content("#nEst") and page.locator("#nNeedSave").is_visible()
    page.fill("#cPhone", "0241234567"); page.dispatch_event("#cPhone", "change"); page.fill("#cName", "Ama Owusu")
    page.check('input[name="dl"][value="pickup"]')
    page.evaluate("__db.dropReply = 0")
    page.click("#saveBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent.startsWith('Draft saved.')")
    page.wait_for_selector("#nList .dk-note")
    notes = page.evaluate("__db.notes")
    assert len(notes) == 1 and notes[0]["body"] == "Deliver after 2pm please" and notes[0]["category"] == "general"
    assert notes[0]["estimate_ref"] and notes[0]["estimate_ref"].startswith("TCP-")
    assert "From estimate" in page.text_content("#nList") and not page.locator("#nEst").is_visible()
    page.click("#saveBtn")
    page.wait_for_function("document.querySelector('#sMsg').textContent.startsWith('Draft saved.')")
    assert page.evaluate("__db.notes.length") == 1, "saving again never adds it twice"
    # Copy to note to customer.
    page.click("#nList [data-ncopy]")
    assert page.input_value("#iNote") == "Deliver after 2pm please"
    assert page.evaluate("__db.notes[0].body") == "Deliver after 2pm please", "the internal note stays"
    _add_note(page, SECRET)
    page.click("#issueBtn")
    page.wait_for_selector("#issuedSec:not([hidden])")
    page.wait_for_selector("#notesSec:not([hidden])")
    assert page.locator("[data-ncopy]").count() == 0, "gone after issue"
    texts, _ = _pdf(page)
    whole = " ".join(texts)
    assert "Deliver after 2pm please" in whole and "ZEBRAQUARTZ" not in whole
    assert "ZEBRAQUARTZ" not in page.evaluate("TCPDesk.waText(TCPDesk.doc())") and "ZEBRAQUARTZ" not in page.url
    assert not errors


# N03: internal notes after issue: categories default to General; a double
# tap and a lost reply give one note; who and when are shown.
def test_n03_add_note_once_with_category(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/2")
    page.wait_for_selector("#notesSec:not([hidden])")
    assert page.is_checked('input[name="ncat"][value="general"]')
    page.fill("#nBody", "Customer says the balance comes on Friday by MoMo.")
    page.check('input[name="ncat"][value="follow_up"]')
    page.evaluate("__db.dropReply = 1")
    page.click("#nSave")
    page.wait_for_function("document.querySelector('#nMsg').textContent.includes('no connection')")
    assert page.evaluate("__db.notes.length") == 1, "the database did add it"
    page.dblclick("#nSave")
    page.wait_for_function("document.querySelector('#nMsg').textContent === 'Note saved.'")
    assert page.evaluate("__db.notes.length") == 1, "the retry and the double tap returned the same note"
    log = page.text_content("#nList")
    assert "Follow-up" in log and "Test Owner" in log and "balance comes on Friday" in log
    assert page.is_checked('input[name="ncat"][value="general"]'), "back to General for the next note"
    # Saved but the answer lost, then the words changed: a different note,
    # so a new request id (the database would refuse the old one for it).
    page.fill("#nBody", "Typo in this one")
    page.evaluate("__db.dropReply = 1")
    page.click("#nSave")
    page.wait_for_function("document.querySelector('#nMsg').textContent.includes('no connection')")
    page.fill("#nBody", "Typo fixed in this one")
    page.click("#nSave")
    page.wait_for_function("document.querySelector('#nMsg').textContent === 'Note saved.'")
    assert page.evaluate("__db.notes.map(n => n.body)")[1:] == ["Typo in this one", "Typo fixed in this one"]
    assert not errors


# N04: a payment with both notes: the receipt view shows both, the PDF only
# the note to the customer, WhatsApp neither; the payment history and the
# Payments tab (a note marker) show it too.
def test_n04_payment_notes(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/2", perms=["clipboard-read", "clipboard-write"])
    _open_pay(page)
    page.fill("#pCustNote", "Thank you. Balance due by Friday.")
    page.fill("#pIntNote", "Paid by his brother Kwame. " + SECRET)
    _pay(page, "300", "cash")
    _receipt_shown(page, "TCP-RCT-0003")
    view = page.text_content("#rNotes")
    assert "Thank you. Balance due by Friday." in view and "Paid by his brother Kwame" in view
    t = " ".join(_receipt_pdf(page)[0])
    assert "Thank you. Balance due by Friday." in t and "ZEBRAQUARTZ" not in t and "Kwame" not in t
    msg = page.evaluate("TCPDesk.waReceiptText(TCPDesk.receipt())")
    assert "Friday" not in msg and "ZEBRAQUARTZ" not in msg
    page.click("#rInv")
    page.wait_for_selector("#issuedSec:not([hidden])")
    assert "Paid by his brother Kwame" in page.text_content("#payList")
    page.evaluate("location.hash = '#/payments?period=all'")
    page.wait_for_selector("#ledRows .dk-led")
    assert page.locator("#ledRows .dk-led", has_text="TCP-RCT-0003").locator(".dk-note-led").count() == 1
    assert page.locator("#ledRows .dk-led", has_text="TCP-RCT-0001").locator(".dk-note-led").count() == 0
    assert "ZEBRAQUARTZ" not in page.url
    assert not errors


# N05: correcting an invoice note, then the correction: the original struck
# through with its latest correction and "Corrected 2 times"; Correct this
# note only on the latest; the same in the notes log and in search.
def test_n05_correction_chain_on_invoice_notes(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/2", staff=NOTE_TEAM, users=[OWNER, FIN, SALES])
    _add_note(page, "Paid by his brother Kwame.")
    _correct(page, page.locator('#nList [data-note="1"] [data-ncorr]'), "It was his brother Kofi, not Kwame.")
    first = page.locator('#nList [data-note="1"]')
    assert "Corrected" in first.text_content() and "Corrected 1 time" in _latest(first)
    assert first.locator(".dk-note-body").evaluate("e => getComputedStyle(e).textDecorationLine") == "line-through"
    assert "Corrects Test Owner's note of" in page.text_content('#nList [data-note="2"]')
    assert first.locator("[data-ncorr]").text_content() == "Correct the latest"
    _correct(page, page.locator('#nList [data-note="2"] [data-ncorr]'), "Actually his cousin Kofi.")
    first = page.locator('#nList [data-note="1"]')
    log_latest = _latest(first)
    assert "Corrected 2 times" in log_latest and "Actually his cousin Kofi." in log_latest
    # Correct this note only on the latest (note 3); the others say "the latest".
    assert page.locator('#nList [data-note="3"] [data-ncorr]').text_content() == "Correct this note"
    assert page.locator('#nList [data-note="2"] [data-ncorr]').text_content() == "Correct the latest"
    assert page.locator('#nList [data-note="2"] [data-ncorr]').get_attribute("data-nid") == "3"
    mid_latest = _latest(page.locator('#nList [data-note="2"]'))
    assert "Corrected 1 time" in mid_latest, "a correction that was corrected shows its own latest"
    # Search shows each with the same latest correction as the log.
    page.evaluate("location.hash = '#/notes?q=Kwame'")
    page.wait_for_function("document.querySelector('#nsInfo').textContent.startsWith('2 notes')")
    orig = page.locator("#nsRows .dk-nres", has_text="Paid by his brother Kwame.")
    corr = page.locator("#nsRows .dk-nres", has_text="It was his brother Kofi, not Kwame.")
    assert "Corrected" in orig.text_content() and _latest(orig) == log_latest
    assert _latest(corr) == mid_latest and "Corrects Test Owner's note of" in corr.text_content()
    assert not errors


# N06: correcting a payment, refund and correction note: shown corrected in
# the receipt view, the payment history and search, all alike; the receipt
# and its amount unchanged.
def test_n06_correcting_payment_refund_and_correction_notes(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/3", staff=NOTE_TEAM, users=[OWNER, FIN, SALES])
    # The Correct form offers no note to the customer (a correction is
    # internal); the Refund form does.
    page.click('[data-fix="correction"][data-pid="1"]'); page.wait_for_selector("#fixForm:not([hidden])")
    assert not page.locator("#fCustNote").is_visible() and page.locator("#fIntNote").is_visible()
    page.click("#fCancel"); page.wait_for_selector("#issuedSec:not([hidden])")
    page.click('[data-fix="refund"][data-pid="1"]'); page.wait_for_selector("#fixForm:not([hidden])")
    assert page.locator("#fCustNote").is_visible()
    page.click("#fCancel"); page.wait_for_selector("#issuedSec:not([hidden])")
    _open_pay(page)
    page.fill("#pIntNote", "Paid by his brother Kwame.")
    _pay(page, "100", "cash")
    _receipt_shown(page, "TCP-RCT-0003")
    pdf_before = _receipt_pdf(page)[0]
    _correct(page, page.locator("#rNotes [data-ncorr]"), "It was his brother Kofi.")
    page.wait_for_selector("#rNotes .dk-note-latest")
    receipt_latest = _latest(page.locator("#rNotes"))
    assert "It was his brother Kofi." in receipt_latest and "Corrected 1 time" in receipt_latest
    assert _receipt_pdf(page)[0] == pdf_before, "the receipt PDF never changes"
    assert page.evaluate("__db.payments[2].internal_note") == "Paid by his brother Kwame."
    page.click("#rInv")
    page.wait_for_selector("#issuedSec:not([hidden])")
    pay3 = page.locator("#payList .dk-pay", has_text="TCP-RCT-0003")
    assert _latest(pay3) == receipt_latest
    assert "Correction to the internal note on payment TCP-RCT-0003" in page.text_content("#nList")
    # A refund and a correction record, each with an internal note.
    page.evaluate("TCPDeskApi.refundPayment({p_payment_id: 3, p_amount: 20, p_method: 'cash', p_reason: 'Short', p_internal_note: 'Cash handed over at the depot.', p_request_id: crypto.randomUUID()})")
    page.evaluate("TCPDeskApi.correctPayment({p_payment_id: 1, p_reason: 'Wrong invoice', p_internal_note: 'MoMo reversed by the network.', p_request_id: crypto.randomUUID()})")
    for rid, no, word in [(4, "TCP-RCT-0004", "refund"), (5, "TCP-RCT-0005", "correction")]:
        page.goto(BO + f"#/receipt/{rid}")
        _receipt_shown(page, no)
        assert ("Refund note" if word == "refund" else "Correction note") in page.text_content("#rNotes")
        _correct(page, page.locator("#rNotes [data-ncorr]"), f"Fixed {word} note.")
        page.wait_for_selector("#rNotes .dk-note-latest")
        rl = _latest(page.locator("#rNotes"))
        page.goto(BO + "#/invoice/3")
        page.wait_for_selector("#issuedSec:not([hidden])")
        assert _latest(page.locator("#payList .dk-pay", has_text=no)) == rl
        assert f"Correction to the internal note on {word} {no}" in page.text_content("#nList")
        page.evaluate(f"location.hash = '#/notes?cat=payment'")
        page.wait_for_selector("#nsRows .dk-nres")
        tag = "Refund note" if word == "refund" else "Correction note"
        hit = page.locator("#nsRows .dk-nres").filter(has=page.locator("i.dk-note-tag", has_text=re.compile("^" + tag + "$"))).first
        assert _latest(hit) == rl
    assert not errors


# N07: two people correcting the same note: the second is told, sees the
# first's correction, and keeps their typed words in a box against the
# latest. Only one correction of the original exists.
def test_n07_competing_correction(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/2", staff=NOTE_TEAM, users=[OWNER, FIN, SALES])
    _seed_note(page, 2, "Deliver on Monday.")
    page.evaluate("TCPDeskApi.home()")   # any call keeps the seeded note
    page.reload(); page.wait_for_selector('#nList [data-note="1"]')
    page.click('#nList [data-note="1"] [data-ncorr]')
    page.fill("#ncText", "Deliver on Tuesday, not Monday.")
    # Meanwhile Test Sales corrects it on another phone.
    _seed_note(page, 2, "Deliver on Wednesday.", corrects_note=1, at="2026-11-22T10:00:00.000Z")
    page.click("#ncSave")
    page.wait_for_function("document.querySelector('#ncMsg') && document.querySelector('#ncMsg').textContent.includes('was just corrected by')")
    assert page.input_value("#ncText") == "Deliver on Tuesday, not Monday.", "nothing typed is lost"
    assert "Deliver on Wednesday." in _latest(page.locator('#nList [data-note="1"]'))
    # The box is now against the latest (note 2).
    box_note = page.evaluate("document.querySelector('#ncBox').previousElementSibling.dataset.note")
    assert box_note == "2"
    assert page.evaluate("__db.notes.filter(n => n.corrects_note_id === 1).length") == 1
    page.click("#ncSave")
    page.wait_for_function("!document.querySelector('#ncBox')")
    assert page.evaluate("__db.notes.map(n => n.corrects_note_id)") == [None, 1, 2]
    assert not errors


# N08: the Notes screen: 3 letters per word, filters, marked words, Leave
# out corrected notes, links to the right record, and an address that holds
# the typed words and filters only, never a note's text.
def test_n08_notes_search(browser):
    page, errors = _bo(browser, seed=MIX, route="#/", staff=NOTE_TEAM, users=[OWNER, FIN, SALES])
    assert page.locator('#homeV a[href="#/notes"]').is_visible()
    page.evaluate("location.hash = '#/invoices'")
    page.wait_for_selector("#listV:not([hidden])")
    assert page.locator('#listV a[href="#/notes"]').is_visible()
    _seed_note(page, 2, "Balance comes Friday " + SECRET, by="u-s", cat="payment", at="2026-11-20T09:00:00.000Z")
    _seed_note(page, 3, "Complaint about broken bags on Friday", by="u-owner", cat="complaint", at="2026-11-21T09:00:00.000Z")
    _seed_note(page, 3, "Bags replaced on Friday", by="u-owner", corrects_note=2, at="2026-11-21T10:00:00.000Z", cat="complaint")
    page.evaluate("TCPDeskApi.home()")
    page.click('#listV a[href="#/notes"]')
    page.wait_for_selector("#notesV:not([hidden])")
    page.fill("#nsq", "fr")
    page.wait_for_function("document.querySelector('#nsInfo').textContent.includes('at least 3')")
    page.fill("#nsq", "friday")
    page.wait_for_function("document.querySelector('#nsInfo').textContent.startsWith('3 notes')")
    assert page.locator("#nsRows mark").first.text_content() == "Friday"
    assert "ZEBRAQUARTZ" not in page.url and "q=friday" in page.url
    page.click('#nsCats [data-ncat="complaint"]')
    page.wait_for_function("document.querySelector('#nsInfo').textContent.startsWith('2 notes')")
    assert "cat=complaint" in page.url
    page.check("#nsHide")
    page.wait_for_function("document.querySelector('#nsInfo').textContent.startsWith('1 note')")
    assert "Bags replaced" in page.text_content("#nsRows")
    page.uncheck("#nsHide")
    page.click('#nsCats [data-ncat="all"]')
    page.select_option("#nsBy", "u-s")
    page.wait_for_function("document.querySelector('#nsInfo').textContent.startsWith('1 note')")
    assert "Sal ·" in page.text_content("#nsRows")
    page.select_option("#nsBy", "")
    page.fill("#nsFrom", "2026-11-21"); page.dispatch_event("#nsFrom", "change")
    page.fill("#nsTo", "2026-11-21"); page.dispatch_event("#nsTo", "change")
    page.wait_for_function("document.querySelector('#nsInfo').textContent.startsWith('2 notes')")
    assert "from=2026-11-21" in page.url and "to=2026-11-21" in page.url
    # A reload keeps the filters (from the address).
    page.reload(); page.wait_for_selector("#nsRows .dk-nres")
    assert page.input_value("#nsq") == "friday" and page.input_value("#nsFrom") == "2026-11-21"
    # Tapping a result opens its invoice.
    page.locator("#nsRows .dk-nres-rec").first.click()
    page.wait_for_selector("#issuedSec:not([hidden])")
    assert page.url.endswith("#/invoice/3")
    assert not errors


# N09: a payment whose answer was lost, then the page reloaded: the phone
# kept the operation but no note text; the retried form says notes were not
# kept, and nothing is recorded twice.
def test_n09_recovery_keeps_no_note_text(browser):
    page, errors = _bo(browser, seed=MIX, route="#/invoice/2")
    _open_pay(page)
    page.fill("#pCustNote", "Thanks")
    page.fill("#pIntNote", SECRET)
    page.evaluate("__db.offlineOnce = 1")
    _pay(page, "100", "cash")
    page.wait_for_function("document.querySelector('#pMsg').textContent.includes('No connection')")
    kept = page.evaluate("JSON.stringify(Object.assign({}, localStorage))")
    assert "ZEBRAQUARTZ" not in kept and "Thanks" not in kept
    page.reload()
    page.wait_for_selector("#payForm:not([hidden])")
    assert "Notes are not kept on this phone" in page.text_content("#pMsg")
    assert page.input_value("#pIntNote") == ""
    assert page.evaluate("__db.payments.length") == 2
    assert not errors


@pytest.mark.parametrize("width", [360, 390])
def test_n10_notes_fit_a_phone(browser, width):
    page, errors = _bo(browser, width=width, seed=MIX, route="#/invoice/3")
    fits = lambda: page.evaluate("document.documentElement.scrollWidth") <= width
    _add_note(page, "A long note " + "with many words " * 30)
    _correct(page, page.locator('#nList [data-note="1"] [data-ncorr]'), "Shorter.")
    assert fits()
    _open_pay(page); assert fits()
    page.evaluate("location.hash = '#/notes?q=many'"); page.wait_for_selector("#nsRows .dk-nres"); assert fits()
    assert not errors


# N11: the notes column's own lines (ChatGPT's review of PR #42): only the
# exact lines the Back Office writes are read as delivery and the estimate
# reference; a note to the customer starting "Estimate" stays a note, in
# the form and on the PDF.
def test_n11_customer_note_starting_estimate(browser):
    notes = "Customer pickup\nEstimate TCP-261120-MEBLV2\nEstimate valid for 7 days"
    page, errors = _bo(browser, seed=[{"name": "Ama Owusu", "phone": "+233241234567", "state": "draft", "notes": notes},
                                      {"name": "Yaw Mensah", "phone": "+233552331234", "state": "issued", "due": FUTURE, "notes": notes}],
                       route="#/invoice/1")
    page.wait_for_selector("#form:not([hidden])")
    assert page.input_value("#iNote") == "Estimate valid for 7 days"
    assert page.evaluate("TCPDesk.state().ref") == "TCP-261120-MEBLV2"
    assert page.get_attribute("#iNote", "maxlength") == "500"
    page.evaluate("location.hash = '#/invoice/2'")
    page.wait_for_selector("#issuedSec:not([hidden])")
    whole = " ".join(_pdf(page)[0])
    assert "Estimate valid for 7 days" in whole and "TCP-261120-MEBLV2" in whole
    assert not errors
