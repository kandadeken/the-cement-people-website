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
│  └─ 20261121120000_phase1_commercial_records.sql   the whole database, commented
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
| `site_publish_requests` | Price changes waiting to be sent to the website |

Totals, balances and statuses are never stored. They are calculated by the
`invoice_summary` view every time, so they can't go out of step with the
payments. Statuses are draft, unpaid, part paid, paid, overdue and cancelled.

## How a sale works

1. `create_customer` (or find an existing one with `customers_with_phone` /
   `find_customer_by_code`).
2. `create_draft_invoice`, then `add_invoice_line` for each product, the agreed
   delivery charge and any discount. Drafts can be changed freely.
3. `issue_invoice`: the invoice gets its permanent number and is locked.
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
| Add customers, prepare and issue invoices | ✓ | ✓ | – | – | – |
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
| `10_concurrency` | 20 invoices issued at the same moment get 0001 to 0020 with no gaps or repeats; two payments, two refunds or two corrections racing each other can never overpay or double up |

The concurrency test was itself checked: with the payment lock removed, it
fails (both racing payments go through), so a pass means the lock works.

## Limits worth knowing

- **Refused attempts are not in the audit log.** When Postgres refuses an
  action it undoes that whole step, including any log entry. Supabase's own
  API logs record failed requests; the audit log records everything that
  actually changed.
- **The website doesn't read from here yet.** The `public_catalogue` view and
  the publish queue are ready; connecting the website (and the small Supabase
  Edge Function that calls Cloudflare) is the next piece of work.
- **No screens yet.** This is the database only. The Invoice Desk will be
  rebuilt on top of these functions once the database is approved.
