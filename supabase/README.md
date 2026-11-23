# TCP sales records database (Supabase)

This folder holds The Cement People's sales-records database: customers,
products, invoices, payments and receipts, with an audit log. It follows
**TCP Admin System - Data Model Spec (v3)**, together with ChatGPT's final
review of v3.

> **Status: built and tested, not live.** No Supabase project has been
> created and no real records exist. Everything here has been run against a
> throwaway Postgres database (`run-tests.sh`). Going live is a separate step
> that needs its own approval (see `DEPLOYMENT.md`).

## What's in here

```
supabase/
├─ migrations/
│  ├─ 20261121120000_phase1_commercial_records.sql   the whole database, commented
│  ├─ 20261121180000_desk_phase1.sql                 additions for the Invoice Desk
│  └─ 20261122210000_back_office_home.sql            the Back Office Home figures (one view)
├─ seed.sql            the 17 products on the website today (starting price list)
├─ run-tests.sh        runs every test on a throwaway database
├─ tests/
│  ├─ 01 … 09 *.sql    tests, one subject each (see the table below)
│  ├─ 10_concurrency.sh  things happening at the same moment
│  └─ support/         a Supabase stand-in and test helpers (tests only)
├─ README.md           this file
└─ DEPLOYMENT.md       how it goes live, backups and recovery
```

## The tables

| Table | What it holds |
| --- | --- |
| `customers` | Everyone TCP sells to. Code (TCP-C-0001), phone in +233 form, name. Phone or name required; phone numbers may be shared |
| `customer_code_aliases` | Old codes kept after two records of the same person are merged |
| `products` | The price list. `published` = on the website, `price_visible` = price shown |
| `invoices` | Drafts (no number) and issued invoices (TCP-INV-0001). Billed-to customer and deliver-to site kept separate |
| `invoice_lines` | Product, delivery and discount lines. Name, unit and price copied at the time; quantities may have decimals |
| `payments` | Receipts (TCP-RCT-0001): payments, corrections and refunds. Never edited or deleted |
| `audit_log` | Every change, who made it, and the values before and after. Cannot be edited or deleted |
| `staff` | Staff logins and their role (owner, sales, finance) |
| `site_publish_requests` | Catalogue changes waiting to be sent to the website |
| `site_catalogue_state` | When the public catalogue last changed, and what changed |

Totals, balances and statuses are never stored. They are calculated by the
`invoice_summary` view every time, so they can't go out of step with the
payments. Statuses are draft, unpaid, part paid, paid, overdue and cancelled.

## How a sale works

1. `create_customer` (or find an existing one with `customers_with_phone` /
   `find_customer_by_code`). Details are corrected with `update_customer`;
   the code never changes.
2. `create_draft_invoice`, then `add_invoice_line` for each product, the agreed
   delivery charge and any discount. Drafts can be changed freely.
3. `issue_invoice`: the invoice gets its permanent number and is locked.
   Invoices of GH₵0 or less are refused.
4. `record_payment` for each payment (part payments allowed, overpayments
   refused).
5. Mistakes are fixed without rewriting history:
   - wrong payment recorded: `correct_payment` (undoes it in full), then record
     the right one
   - money given back: `refund_payment` (partial allowed, never more than paid)
   - wrong invoice: `cancel_invoice` with a reason (only once no money is held
     against it), then issue a replacement

## Who can do what

| Action | Owner | Sales | Finance | Logged in, not staff | Public |
| --- | :-: | :-: | :-: | :-: | :-: |
| Read customers, invoices, payments | ✓ | ✓ | ✓ | – | – |
| Add and edit customers, prepare and issue invoices | ✓ | ✓ | – | – | – |
| Record payments | ✓ | ✓ | ✓ | – | – |
| Corrections and refunds | ✓ | – | ✓ | – | – |
| Cancel invoices, merge customers, change prices | ✓ | – | – | – | – |
| Read the audit log and staff list | ✓ | – | – | – | – |
| Read the public price list (`public_catalogue`) | ✓ | ✓ | ✓ | ✓ | ✓ |

These rules sit inside the database (row-level security and checks at the top
of each function), so they hold whatever app or screen is used. For now Daniel
is the only staff member, as owner.

## The tests

Run them from the top folder of the repository:

```bash
bash supabase/run-tests.sh
```

They also run automatically on GitHub for every pull request that changes this
folder (`.github/workflows/database-tests.yml`).

| File | What it proves |
| --- | --- |
| `01_customers_and_numbering` | Phone numbers in any Ghana format match; phone or name required; shared phones allowed; codes have no gaps, even after a refused attempt; customers can't be deleted |
| `02_invoices_and_frozen_prices` | Drafts have no number; product name, unit and price copied onto the line; 2.5 tons works; totals right; empty drafts can't be issued; repricing a product leaves issued invoices untouched; issued invoices and their lines can't be edited or deleted, even with full database rights |
| `03_payments_corrections_refunds` | Part payments; overpayments and zero or negative payments refused; corrections undo the whole payment, once only, with a reason and their own receipt number; several partial refunds allowed but never more than paid; no correcting after a refund; receipts can't be edited or deleted; receipt numbers gapless |
| `04_cancellation` | Can't cancel while money is held; a reason is needed; cancelling never creates a refund; cancelled invoices keep their number and are final; replacement gets the next number |
| `05_permissions` | The public sees only the published catalogue (hidden prices blank); a logged-in stranger and a switched-off staff member see and do nothing; no direct writes to tables; sales and finance limited to their actions |
| `06_audit_log` | Price changes, issuing, payments and corrections logged with who and before/after values; the log can't be edited, deleted or emptied, even with full database rights; a refused action leaves no trace |
| `07_merge_customers` | Invoices move to the kept record unchanged; old codes kept as aliases and still work, through chains of merges; merged records can't be reused; owner only |
| `08_site_publishing` | Price changes queue one request, never a pile; success recorded; failures retried with the error kept, given up after 5 and shown; "out of date" flag correct; the catalogue shows the new price |
| `09_status_and_precision` | Unpaid, part paid, overdue and paid worked out correctly; overdue list; exact money on large and awkward amounts (1,234.567 tons); prices and payments rounded to the pesewa |
| `11_customer_updates_and_zero_invoices` | Customer details corrected with before/after in the audit log; codes never change; merged records locked; finance and strangers can't edit; zero or negative invoices refused without using up a number |
| `12_site_publishing_races` | A change made while a build is running queues a new request and is never lost; one build at a time; name, unpublish and hidden-price changes count, not just prices; a failed build is superseded by a newer waiting one; a build stuck for 15 minutes is taken back; a build stuck every time stops after 5 attempts and shows as failed; an identical save queues nothing |
| `13_issue_versus_line_race` | Issuing an invoice while a line is being removed or added at the same moment (timing made certain, both orders): no line slips in or out mid-issue |
| `14_desk_phase1_additions` | Issued invoices keep the "billed to" name and phone as they were at issue, even after the customer is renamed; who issued is recorded; a draft saves in one step and a repeated save with the same request id makes no second draft; a repeated payment, refund or correction with the same request id is recorded once, and a different request reusing an id is refused; each receipt keeps the balance after it; the invoice and receipt documents and the invoice list; only staff can read them |
| `15_request_id_races` | Two identical payment, refund, new-draft or new-customer requests arriving at the same moment are recorded once, and both get the answer (the second waits for the first instead of failing) |
| `16_customer_requests_and_access` | A retried new customer (even one with no phone) is added once, and a reused id for a different customer is refused, with codes still gapless; `my_staff()` answers for active staff and refuses anyone else; once access is removed, plain reads come back empty while every action and document refuses (why the desk checks `my_staff()` when a read is empty) |
| `17_back_office_home` | The Home figures (owed, unpaid, part paid, overdue, open drafts) for invoices in every status, read as signed-in sales, owner and finance; every count equals what the Invoices list shows under that filter and "owed" equals the list's balances; zeros for someone who is not staff or was removed; the public cannot read it |
| `10_concurrency` | 20 invoices issued at the same moment get 0001 to 0020 with no gaps or repeats; two payments, two refunds or two corrections racing each other can never overpay or double up |

The race tests were themselves checked: with the payment lock removed,
`10_concurrency` fails (both racing payments go through); with the invoice
lock in the line guard removed, `13_issue_versus_line_race` fails (a line is
removed from an invoice mid-issue). So a pass means the locks work.

## Limits worth knowing

- **Refused attempts are not in the audit log.** When Postgres refuses an
  action it undoes that whole step, including any log entry. Supabase's own
  API logs record failed requests; the audit log records everything that
  actually changed.
- **The website doesn't read from here yet.** The `public_catalogue` view and
  the publish queue are ready; connecting the website (and the small Supabase
  Edge Function that calls Cloudflare) is the next piece of work.
- **The TCP Back Office** (`/back-office/`, 22 Nov 2026) is built on these
  functions: Home figures, every draft and invoice with search and filters,
  the invoice form (the phase 1 Invoice Desk) and the read-only invoice view
  with its PDF. Payments and receipts on screen are phase 2. Setup steps are
  in `DEPLOYMENT.md`.
- **The Back Office's screen tests use a stand-in for Supabase's API**
  (`tests/test_back_office.py`); the database rules themselves are tested
  here on real Postgres, and end to end on `tcp-test` from a phone.
