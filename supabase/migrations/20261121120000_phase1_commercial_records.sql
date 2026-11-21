-- =============================================================================
-- The Cement People: Phase 1 commercial records (customers, products,
-- invoices, payments, audit log)
--
-- What this file is
--   The first database "migration": the exact set of instructions that builds
--   TCP's sales records inside Supabase (a hosted Postgres database). It follows
--   "TCP Admin System - Data Model Spec (v3)" plus ChatGPT's final v3 review.
--
-- How it is meant to be used
--   Supabase runs files in supabase/migrations/ in name order, once each.
--   Nothing here has been run against a real Supabase project yet. The tests in
--   supabase/tests/ run it against a throwaway Postgres database instead.
--
-- The rules this file enforces (all inside the database, so no web page,
-- app bug or mistake can get round them)
--   1. Prices are frozen on each invoice line at the moment it is added.
--   2. Totals, balances and statuses are calculated here, never typed.
--   3. Nothing financial is deleted or silently edited. Issued invoices are
--      locked; mistakes are fixed with cancellations, corrections or refunds.
--   4. Every customer has a code plus a phone number or a name.
--   5. Every change is written to an audit log nobody can edit or delete.
--   6. Who may do what is decided here (row-level security), not by hiding
--      buttons on a screen.
--
-- How changes are made
--   Staff never write to the tables directly. They call the functions below
--   (create_customer, issue_invoice, record_payment, ...). Each one checks the
--   caller's role and the business rules, then makes the change. The tables
--   are read-only to everyone except those functions.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 0. A private area for internal helpers
--    Supabase publishes the "public" schema through its web API. Helpers that
--    should never be called from outside live in "tcp_private" instead.
-- -----------------------------------------------------------------------------
create schema if not exists tcp_private;
revoke all on schema tcp_private from public;


-- -----------------------------------------------------------------------------
-- 1. Staff and roles
--    Each staff member is a Supabase login (auth.users) with one role.
--    owner   = Daniel: can do everything.
--    sales   = (future) customers, invoices, recording payments.
--    finance = (future) recording payments, corrections and refunds.
--    Staff are added by invitation only; there is no public sign-up for staff.
-- -----------------------------------------------------------------------------
create table public.staff (
  user_id     uuid primary key references auth.users (id),
  full_name   text not null check (length(trim(full_name)) > 0),
  role        text not null check (role in ('owner', 'sales', 'finance')),
  active      boolean not null default true,
  created_at  timestamptz not null default now()
);
comment on table public.staff is 'TCP staff logins and their role. Added by invitation only.';

-- The role of whoever is calling, or null if they are not active staff.
-- auth.uid() is Supabase's "who is logged in" function.
create function tcp_private.staff_role()
returns text
language sql stable security definer
set search_path = ''
as $$
  select s.role from public.staff s
  where s.user_id = auth.uid() and s.active
$$;

-- True when the caller is active staff (any role).
create function tcp_private.is_staff()
returns boolean
language sql stable security definer
set search_path = ''
as $$ select tcp_private.staff_role() is not null $$;

-- Stops the calling function unless the caller has one of the allowed roles.
-- Used at the top of every function that changes data.
create function tcp_private.require_role(variadic allowed text[])
returns void
language plpgsql stable security definer
set search_path = ''
as $$
declare
  r text := tcp_private.staff_role();
begin
  if r is null then
    raise exception 'Not allowed: only TCP staff can do this'
      using errcode = '42501';
  end if;
  if not (r = any (allowed)) then
    raise exception 'Not allowed: the % role cannot do this', r
      using errcode = '42501';
  end if;
end;
$$;


-- -----------------------------------------------------------------------------
-- 2. Ghana phone numbers
--    Stored one way only (+233 and nine digits) so that 024 123 4567,
--    0241234567 and +233 24 123 4567 are recognised as the same number.
-- -----------------------------------------------------------------------------
create function public.normalise_gh_phone(raw text)
returns text
language plpgsql immutable
set search_path = ''
as $$
declare
  digits text := regexp_replace(coalesce(raw, ''), '[^0-9]', '', 'g');
begin
  if digits = '' then
    return null;                                  -- no number given
  elsif length(digits) = 12 and left(digits, 3) = '233' then
    return '+' || digits;                         -- 233241234567
  elsif length(digits) = 10 and left(digits, 1) = '0' then
    return '+233' || substr(digits, 2);           -- 0241234567
  elsif length(digits) = 9 then
    return '+233' || digits;                      -- 241234567
  end if;
  raise exception 'Not a Ghana phone number: %', raw using errcode = '22023';
end;
$$;


-- -----------------------------------------------------------------------------
-- 3. Numbering (TCP-C-0001, TCP-INV-0001, TCP-RCT-0001)
--    One counter row per kind. Taking a number locks that row until the
--    surrounding change is saved; if the change fails, the number is handed
--    back. That is what keeps numbers gapless in normal use. Postgres
--    "sequences" were not used because they can skip numbers.
-- -----------------------------------------------------------------------------
create table tcp_private.number_counters (
  kind        text primary key check (kind in ('customer', 'invoice', 'receipt')),
  prefix      text not null,
  last_value  bigint not null default 0 check (last_value >= 0)
);
insert into tcp_private.number_counters (kind, prefix) values
  ('customer', 'TCP-C-'),
  ('invoice',  'TCP-INV-'),
  ('receipt',  'TCP-RCT-');

create function tcp_private.next_number(counter_kind text)
returns text
language plpgsql
set search_path = ''
as $$
declare
  result text;
begin
  update tcp_private.number_counters
     set last_value = last_value + 1
   where kind = counter_kind
  returning prefix || lpad(last_value::text, 4, '0') into result;
  if result is null then
    raise exception 'Unknown number kind: %', counter_kind;
  end if;
  return result;   -- 0001 to 9999, then 10000 and up (still unique)
end;
$$;


-- -----------------------------------------------------------------------------
-- 4. Customers
--    Everyone TCP sells to. A customer must have a phone number or a name.
--    Phone numbers are NOT unique: families and companies share numbers.
--    When two records turn out to be the same person, the owner merges them;
--    the merged record's code is kept in customer_code_aliases.
-- -----------------------------------------------------------------------------
create table public.customers (
  id           bigint generated always as identity primary key,
  code         text not null unique,
  phone        text check (phone is null or phone ~ '^\+233[0-9]{9}$'),
  name         text check (name is null or length(trim(name)) > 0),
  area         text,
  notes        text,
  merged_into  bigint references public.customers (id),
  created_at   timestamptz not null default now(),
  created_by   uuid default auth.uid(),
  constraint customer_needs_phone_or_name check (phone is not null or name is not null),
  constraint customer_not_merged_into_self check (merged_into is null or merged_into <> id)
);
create index customers_phone_idx on public.customers (phone);
comment on table public.customers is 'Everyone TCP sells to. Phone or name required; phone not unique.';

create table public.customer_code_aliases (
  code         text primary key,
  customer_id  bigint not null references public.customers (id),
  created_at   timestamptz not null default now()
);
comment on table public.customer_code_aliases is 'Old customer codes kept after a merge, so an old code still finds the customer.';


-- -----------------------------------------------------------------------------
-- 5. Products
--    The price list. site_id links a product to the website's own id (c1, i1,
--    j1 ...). Published = shown on the website; price_visible = its price is
--    shown. A price change here never alters an invoice already written.
-- -----------------------------------------------------------------------------
create table public.products (
  id                bigint generated always as identity primary key,
  site_id           text unique,
  name              text not null check (length(trim(name)) > 0),
  category          text not null check (length(trim(category)) > 0),
  unit              text not null check (length(trim(unit)) > 0),
  current_price     numeric(12, 2) not null check (current_price >= 0),
  published         boolean not null default false,
  price_visible     boolean not null default true,
  price_updated_at  timestamptz not null default now(),
  created_at        timestamptz not null default now(),
  constraint product_name_unique_in_category unique (category, name)
);
comment on table public.products is 'The price list. Source of truth for the website once connected.';

-- Keep price_updated_at honest: it changes only when the price itself changes.
create function tcp_private.stamp_price_change()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' or new.current_price is distinct from old.current_price then
    new.price_updated_at := now();
  end if;
  return new;
end;
$$;
create trigger products_stamp_price
  before insert or update on public.products
  for each row execute function tcp_private.stamp_price_change();


-- -----------------------------------------------------------------------------
-- 6. Invoices
--    An invoice starts as a draft (no number yet) so it can be prepared and
--    checked. Issuing gives it its permanent number and locks it for good.
--    "Billed to" (who pays) and "deliver to" (the site) are kept separate:
--    the payer may be abroad while the cement goes to Kasoa.
--    Status like Paid / Part paid / Overdue is never stored; see section 9.
-- -----------------------------------------------------------------------------
create table public.invoices (
  id                     bigint generated always as identity primary key,
  invoice_no             text unique,                       -- given on issue
  customer_id            bigint not null references public.customers (id),
  state                  text not null default 'draft'
                           check (state in ('draft', 'issued', 'cancelled')),
  deliver_to_location    text,                              -- null = pickup
  deliver_to_contact     text,
  deliver_to_phone       text check (deliver_to_phone is null
                                     or deliver_to_phone ~ '^\+233[0-9]{9}$'),
  due_date               date,
  notes                  text,
  issued_at              timestamptz,
  cancelled_at           timestamptz,
  cancelled_by           uuid,
  cancel_reason          text,
  created_at             timestamptz not null default now(),
  created_by             uuid default auth.uid(),
  -- A number and an issue date come together, at the moment of issuing.
  -- Drafts have neither; issued invoices have both; a cancelled invoice has
  -- both if it was issued first, or neither if it was cancelled as a draft.
  constraint number_and_issue_date_together
    check ((invoice_no is null) = (issued_at is null)),
  constraint draft_has_no_number
    check (state <> 'draft' or invoice_no is null),
  constraint issued_invoice_has_number
    check (state <> 'issued' or invoice_no is not null),
  constraint cancellation_is_complete
    check ((state = 'cancelled') = (cancelled_at is not null and cancel_reason is not null))
);
create index invoices_customer_idx on public.invoices (customer_id);
comment on table public.invoices is 'Invoices. Drafts have no number; issued invoices are locked.';


-- -----------------------------------------------------------------------------
-- 7. Invoice lines
--    One line per product, delivery charge or discount. The description,
--    unit and price are COPIED onto the line, so renaming or repricing a
--    product later never changes an invoice. Quantities can have decimals
--    (2.5 tons). The line total is calculated by the database.
-- -----------------------------------------------------------------------------
create table public.invoice_lines (
  id           bigint generated always as identity primary key,
  invoice_id   bigint not null references public.invoices (id),
  position     integer not null,
  kind         text not null check (kind in ('product', 'delivery', 'discount')),
  product_id   bigint references public.products (id),
  description  text not null check (length(trim(description)) > 0),
  unit         text not null check (length(trim(unit)) > 0),
  quantity     numeric(14, 3) not null check (quantity > 0),
  unit_price   numeric(12, 2) not null,
  line_total   numeric(14, 2) generated always as (round(quantity * unit_price, 2)) stored,
  created_at   timestamptz not null default now(),
  constraint product_line_has_product
    check ((kind = 'product') = (product_id is not null)),
  constraint discount_is_negative_others_not
    check ((kind = 'discount' and unit_price < 0) or (kind <> 'discount' and unit_price >= 0)),
  constraint line_position_unique unique (invoice_id, position)
);
create index invoice_lines_invoice_idx on public.invoice_lines (invoice_id);


-- -----------------------------------------------------------------------------
-- 8. Payments, corrections and refunds (receipts)
--    payment    = money received. Positive amount.
--    correction = a recording mistake undone in FULL (negative amount equal
--                 to the original). The right amount is then recorded as a
--                 new payment.
--    refund     = money actually given back. Negative, may be partial, may
--                 happen more than once, but never more than the original.
--    Every row gets its own receipt number. Rows are never edited or deleted.
-- -----------------------------------------------------------------------------
create table public.payments (
  id                  bigint generated always as identity primary key,
  receipt_no          text not null unique,
  invoice_id          bigint not null references public.invoices (id),
  kind                text not null check (kind in ('payment', 'correction', 'refund')),
  amount              numeric(14, 2) not null,
  method              text not null check (method in ('mobile_money', 'cash', 'bank_transfer')),
  reference           text,
  paid_on             date not null default current_date,
  reverses_payment_id bigint references public.payments (id),
  reason              text,
  recorded_at         timestamptz not null default now(),
  recorded_by         uuid default auth.uid(),
  constraint payment_sign_and_link check (
    (kind = 'payment' and amount > 0 and reverses_payment_id is null)
    or (kind in ('correction', 'refund') and amount < 0
        and reverses_payment_id is not null
        and reason is not null and length(trim(reason)) > 0)
  )
);
create index payments_invoice_idx on public.payments (invoice_id);
create index payments_reverses_idx on public.payments (reverses_payment_id);
-- A payment can be corrected only once (enforced here, not just in code).
create unique index payments_one_correction_per_payment
  on public.payments (reverses_payment_id) where kind = 'correction';
comment on table public.payments is 'Receipts: payments, corrections and refunds. Never edited or deleted.';


-- -----------------------------------------------------------------------------
-- 9. Calculated totals and status
--    total    = sum of line totals
--    paid     = sum of all payments, corrections and refunds
--    balance  = total - paid
--    status   = draft | cancelled | paid | part_paid | overdue | unpaid
--    security_invoker makes the view obey the same permissions as the tables.
-- -----------------------------------------------------------------------------
create view public.invoice_summary
with (security_invoker = true)
as
select
  i.id,
  i.invoice_no,
  i.customer_id,
  i.state,
  i.issued_at,
  i.due_date,
  coalesce(l.total, 0)::numeric(14, 2)                        as total,
  coalesce(p.paid, 0)::numeric(14, 2)                         as paid,
  (coalesce(l.total, 0) - coalesce(p.paid, 0))::numeric(14, 2) as balance,
  case
    when i.state = 'draft'      then 'draft'
    when i.state = 'cancelled'  then 'cancelled'
    when coalesce(p.paid, 0) >= coalesce(l.total, 0) then 'paid'
    when i.due_date is not null and i.due_date < current_date then 'overdue'
    when coalesce(p.paid, 0) > 0 then 'part_paid'
    else 'unpaid'
  end as status
from public.invoices i
left join (select invoice_id, sum(line_total) as total
             from public.invoice_lines group by invoice_id) l on l.invoice_id = i.id
left join (select invoice_id, sum(amount) as paid
             from public.payments group by invoice_id) p on p.invoice_id = i.id;
comment on view public.invoice_summary is 'Totals, balance and status, always calculated, never stored.';

-- Issued invoices past their due date with money still owed. A scheduled job
-- (see supabase/DEPLOYMENT.md) emails Daniel from this list.
create view public.overdue_invoices
with (security_invoker = true)
as
select s.*, c.code as customer_code, c.name as customer_name, c.phone as customer_phone
from public.invoice_summary s
join public.customers c on c.id = s.customer_id
where s.status = 'overdue';


-- -----------------------------------------------------------------------------
-- 10. Locks that protect the history
--     These triggers stop changes even if someone bypasses the functions.
-- -----------------------------------------------------------------------------

-- Invoices: never deleted. Once issued, only a cancellation may change them.
create function tcp_private.guard_invoices()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'Invoices are never deleted; cancel it instead' using errcode = '42501';
  end if;
  -- A customer merge (merge_customers sets this flag) may move any invoice,
  -- draft, issued or cancelled, to the surviving customer record, changing
  -- nothing else about it.
  if coalesce(current_setting('tcp.merging_customers', true), '') = 'on'
     and (to_jsonb(new) - 'customer_id') = (to_jsonb(old) - 'customer_id') then
    return new;
  end if;
  if old.state = 'cancelled' then
    raise exception 'A cancelled invoice cannot be changed' using errcode = '42501';
  end if;
  if old.state = 'issued' then
    -- The only allowed change to an issued invoice is cancelling it.
    if new.state <> 'cancelled'
       or new.invoice_no  is distinct from old.invoice_no
       or new.customer_id is distinct from old.customer_id
       or new.issued_at   is distinct from old.issued_at
       or new.due_date    is distinct from old.due_date
       or new.deliver_to_location is distinct from old.deliver_to_location
       or new.deliver_to_contact  is distinct from old.deliver_to_contact
       or new.deliver_to_phone    is distinct from old.deliver_to_phone
       or new.notes       is distinct from old.notes then
      raise exception 'An issued invoice is locked; cancel it and issue a replacement'
        using errcode = '42501';
    end if;
  end if;
  return new;
end;
$$;
create trigger invoices_guard
  before update or delete on public.invoices
  for each row execute function tcp_private.guard_invoices();

-- Invoice lines: may only be added, changed or removed while the invoice is a draft.
create function tcp_private.guard_invoice_lines()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  inv_state text;
begin
  -- Lock the invoice (shared) while checking it. If the invoice is being
  -- issued at this moment, this waits until issuing is saved and then sees
  -- "issued", so a line can never slip in or out of an invoice mid-issue.
  select state into inv_state from public.invoices
   where id = case when tg_op = 'DELETE' then old.invoice_id else new.invoice_id end
   for share;
  if inv_state is distinct from 'draft' then
    raise exception 'Lines can only change while the invoice is a draft'
      using errcode = '42501';
  end if;
  if tg_op = 'UPDATE' and new.invoice_id <> old.invoice_id then
    raise exception 'A line cannot move to another invoice' using errcode = '42501';
  end if;
  return case when tg_op = 'DELETE' then old else new end;
end;
$$;
create trigger invoice_lines_guard
  before insert or update or delete on public.invoice_lines
  for each row execute function tcp_private.guard_invoice_lines();

-- Payments: never edited, never deleted.
create function tcp_private.guard_payments()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'Receipts are never edited or deleted; record a correction or refund instead'
    using errcode = '42501';
end;
$$;
create trigger payments_guard
  before update or delete on public.payments
  for each row execute function tcp_private.guard_payments();

-- Customers and products: not deleted (invoices point at them).
create function tcp_private.forbid_delete()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception '% records are never deleted', tg_table_name using errcode = '42501';
end;
$$;
create trigger customers_no_delete before delete on public.customers
  for each row execute function tcp_private.forbid_delete();
create trigger products_no_delete before delete on public.products
  for each row execute function tcp_private.forbid_delete();
create trigger staff_no_delete before delete on public.staff
  for each row execute function tcp_private.forbid_delete();


-- -----------------------------------------------------------------------------
-- 11. Audit log
--     Every insert, change and delete on the main tables is recorded here by
--     the database itself, in the same step as the change (so if the change
--     is saved, its log entry is saved too, and vice versa). Nobody can edit
--     or delete an entry, not even the owner.
--
--     Note on refused attempts: when an action is refused, Postgres undoes
--     everything in that step, including any log entry written during it. So
--     refused attempts are not logged here; Supabase's own API logs keep a
--     record of failed requests. See supabase/README.md.
-- -----------------------------------------------------------------------------
create table public.audit_log (
  id          bigint generated always as identity primary key,
  at          timestamptz not null default now(),
  actor       uuid,                 -- the staff login, or null for the system
  action      text not null check (action in ('insert', 'update', 'delete')),
  table_name  text not null,
  record_id   text not null,
  before      jsonb,
  after       jsonb
);
create index audit_log_record_idx on public.audit_log (table_name, record_id);
comment on table public.audit_log is 'Who changed what, and when. Written automatically; cannot be edited or deleted.';

create function tcp_private.write_audit()
returns trigger
language plpgsql security definer
set search_path = ''
as $$
declare
  rec jsonb := case when tg_op = 'DELETE' then to_jsonb(old) else to_jsonb(new) end;
  key text  := coalesce(rec ->> 'id', rec ->> 'code', rec ->> 'user_id');
begin
  insert into public.audit_log (actor, action, table_name, record_id, before, after)
  values (
    auth.uid(),
    lower(tg_op),
    tg_table_name,
    key,
    case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) end,
    case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) end
  );
  return null;
end;
$$;

create trigger audit_staff after insert or update or delete on public.staff
  for each row execute function tcp_private.write_audit();
create trigger audit_customers after insert or update or delete on public.customers
  for each row execute function tcp_private.write_audit();
create trigger audit_customer_code_aliases after insert or update or delete on public.customer_code_aliases
  for each row execute function tcp_private.write_audit();
create trigger audit_products after insert or update or delete on public.products
  for each row execute function tcp_private.write_audit();
create trigger audit_invoices after insert or update or delete on public.invoices
  for each row execute function tcp_private.write_audit();
create trigger audit_invoice_lines after insert or update or delete on public.invoice_lines
  for each row execute function tcp_private.write_audit();
create trigger audit_payments after insert or update or delete on public.payments
  for each row execute function tcp_private.write_audit();

-- The log itself can never be changed or emptied.
create function tcp_private.guard_audit_log()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'The audit log cannot be edited or deleted' using errcode = '42501';
end;
$$;
create trigger audit_log_guard
  before update or delete on public.audit_log
  for each row execute function tcp_private.guard_audit_log();
create trigger audit_log_no_truncate
  before truncate on public.audit_log
  for each statement execute function tcp_private.guard_audit_log();


-- -----------------------------------------------------------------------------
-- 12. Website publishing (the price list on thecementpeople.com)
--     When anything the public sees about a product changes (name, category,
--     unit, price, published, price visible), the change time is recorded and
--     a "publish request" is queued. A small Supabase Edge Function (see
--     DEPLOYMENT.md) takes the request, calls Cloudflare's build hook, and
--     reports back. Safeguards:
--       - only one request WAITS at a time, so repeat changes don't pile up
--       - only one request is SENT at a time; a change made while a build is
--         running queues a fresh request, so it is never lost
--       - a request stuck in "sending" for 15 minutes is taken back and retried
--       - failures are retried up to 5 times, with the error kept
--       - site_price_status compares the last catalogue change with the moment
--         the last successful build started, and says plainly when the
--         website is out of date
-- -----------------------------------------------------------------------------

-- One row: when the public catalogue last changed, and what changed.
create table public.site_catalogue_state (
  id              boolean primary key default true check (id),
  last_change_at  timestamptz not null default clock_timestamp(),
  last_change     text not null default 'Initial'
);
insert into public.site_catalogue_state default values;

create table public.site_publish_requests (
  id            bigint generated always as identity primary key,
  requested_at  timestamptz not null default clock_timestamp(),
  reason        text not null,
  status        text not null default 'pending'
                  check (status in ('pending', 'sending', 'succeeded', 'failed', 'superseded')),
  attempts      integer not null default 0 check (attempts >= 0),
  claimed_at    timestamptz,       -- when the current/last attempt started
  last_error    text,
  finished_at   timestamptz
);
-- At most one request waiting, and at most one being sent, at any moment.
create unique index site_publish_one_pending
  on public.site_publish_requests ((true)) where status = 'pending';
create unique index site_publish_one_sending
  on public.site_publish_requests ((true)) where status = 'sending';

create function tcp_private.queue_site_publish()
returns trigger
language plpgsql security definer
set search_path = ''
as $$
begin
  -- Only changes the public can see count (not, say, created_at).
  if tg_op = 'UPDATE'
     and new.site_id       is not distinct from old.site_id
     and new.name          is not distinct from old.name
     and new.category      is not distinct from old.category
     and new.unit          is not distinct from old.unit
     and new.current_price is not distinct from old.current_price
     and new.published     is not distinct from old.published
     and new.price_visible is not distinct from old.price_visible then
    return null;
  end if;
  update public.site_catalogue_state
     set last_change_at = clock_timestamp(),
         last_change = 'Product ' || coalesce(new.site_id, new.id::text) || ' ' || lower(tg_op) || 'd';
  insert into public.site_publish_requests (reason)
  values ('Product ' || coalesce(new.site_id, new.id::text) || ' changed')
  on conflict do nothing;      -- one already waiting: it will carry this change too
  return null;
end;
$$;
create trigger products_queue_publish
  after insert or update on public.products
  for each row execute function tcp_private.queue_site_publish();

-- Called by the Edge Function: take the waiting request (if any) to send.
-- Returns nothing (all fields empty) when there is nothing to do, or when a
-- build is already running.
create function public.claim_site_publish()
returns public.site_publish_requests
language plpgsql security definer
set search_path = ''
as $$
declare
  req public.site_publish_requests;
begin
  -- Serialise claims so two workers can't both start a build.
  lock table public.site_publish_requests in share row exclusive mode;

  -- Recover a request stuck in "sending" (the worker crashed or timed out).
  -- If a newer request is already waiting, the stuck one is superseded by it;
  -- otherwise it goes back to waiting and is retried.
  update public.site_publish_requests
     set status = case when exists (select 1 from public.site_publish_requests
                                     where status = 'pending')
                       then 'superseded' else 'pending' end,
         last_error = 'No report after 15 minutes',
         finished_at = case when exists (select 1 from public.site_publish_requests
                                          where status = 'pending')
                            then clock_timestamp() end
   where status = 'sending' and claimed_at < clock_timestamp() - interval '15 minutes';

  -- One build at a time.
  if exists (select 1 from public.site_publish_requests where status = 'sending') then
    return req;
  end if;

  update public.site_publish_requests
     set status = 'sending', attempts = attempts + 1, claimed_at = clock_timestamp()
   where id = (select id from public.site_publish_requests
                where status = 'pending' order by id limit 1)
  returning * into req;
  return req;
end;
$$;

-- Called by the Edge Function after calling Cloudflare.
--   success: the request is closed. If the catalogue changed after this
--            build started, a fresh request is waiting (or is queued now).
--   failure: back to waiting for a retry, until 5 attempts, then failed.
--            If a newer request is already waiting, this one is superseded.
create function public.finish_site_publish(request_id bigint, ok boolean, error_text text default null)
returns void
language plpgsql security definer
set search_path = ''
as $$
declare
  req public.site_publish_requests;
  newer_waiting boolean;
begin
  lock table public.site_publish_requests in share row exclusive mode;
  select * into req from public.site_publish_requests
   where id = request_id and status = 'sending';
  if not found then
    raise exception 'No publish request % is being sent', request_id;
  end if;
  newer_waiting := exists (select 1 from public.site_publish_requests where status = 'pending');

  update public.site_publish_requests
     set status = case when ok then 'succeeded'
                       when newer_waiting then 'superseded'
                       when attempts >= 5 then 'failed'
                       else 'pending' end,
         last_error = case when ok then null else error_text end,
         finished_at = case when ok or newer_waiting or attempts >= 5
                            then clock_timestamp() end
   where id = request_id;

  -- Belt and braces: anything changed after this build started must be sent.
  if ok and (select last_change_at from public.site_catalogue_state) > req.claimed_at then
    insert into public.site_publish_requests (reason)
    values ('Catalogue changed while the last build was running')
    on conflict do nothing;
  end if;
end;
$$;

-- One-row answer to "is the website showing the latest catalogue?"
-- The website is up to date when the last successful build STARTED after the
-- last catalogue change (a build started earlier can't contain that change).
create view public.site_price_status
with (security_invoker = true)
as
with last_ok as (
  select claimed_at, finished_at from public.site_publish_requests
   where status = 'succeeded' order by claimed_at desc limit 1
)
select
  (select last_change_at from public.site_catalogue_state)                     as last_catalogue_change,
  (select last_change from public.site_catalogue_state)                        as last_change,
  (select max(price_updated_at) from public.products)                          as last_price_change,
  (select finished_at from last_ok)                                            as last_successful_publish,
  (select claimed_at from last_ok)                                             as website_catalogue_as_of,
  (select count(*) from public.site_publish_requests
    where status in ('pending', 'sending'))                                     as waiting_requests,
  (select count(*) from public.site_publish_requests where status = 'failed')  as failed_requests,
  coalesce((select last_change_at from public.site_catalogue_state)
           > (select claimed_at from last_ok), true)                           as website_out_of_date;

-- What the public website may read: published products only, and no price
-- where price_visible is off. This view deliberately runs with the owner's
-- rights so the public never needs (or gets) access to the products table.
create view public.public_catalogue
as
select
  p.site_id,
  p.name,
  p.category,
  p.unit,
  case when p.price_visible then p.current_price end as price,
  case when p.price_visible then p.price_updated_at end as price_updated_at
from public.products p
where p.published;
comment on view public.public_catalogue is 'The only thing the public can read: published products, prices only where visible.';


-- -----------------------------------------------------------------------------
-- 13. The actions staff can take (the only way data changes)
--     "security definer" means the function itself has the rights to write;
--     the caller only needs to pass the role check at the top of each one.
-- -----------------------------------------------------------------------------

-- Add a customer. Phone is tidied into +233 form. Returns the new customer.
create function public.create_customer(
  p_phone text default null,
  p_name  text default null,
  p_area  text default null,
  p_notes text default null
)
returns public.customers
language plpgsql security definer
set search_path = ''
as $$
declare
  c public.customers;
begin
  perform tcp_private.require_role('owner', 'sales');
  insert into public.customers (code, phone, name, area, notes)
  values (tcp_private.next_number('customer'),
          public.normalise_gh_phone(p_phone),
          nullif(trim(p_name), ''),
          nullif(trim(p_area), ''),
          nullif(trim(p_notes), ''))
  returning * into c;
  return c;
end;
$$;

-- Correct a customer's details (name, phone, area, notes). The code never
-- changes. The audit log keeps the before and after automatically.
create function public.update_customer(
  p_customer_id bigint,
  p_phone       text,
  p_name        text,
  p_area        text,
  p_notes       text
)
returns public.customers
language plpgsql security definer
set search_path = ''
as $$
declare
  c public.customers;
begin
  perform tcp_private.require_role('owner', 'sales');
  update public.customers
     set phone = public.normalise_gh_phone(p_phone),
         name  = nullif(trim(p_name), ''),
         area  = nullif(trim(p_area), ''),
         notes = nullif(trim(p_notes), '')
   where id = p_customer_id and merged_into is null
  returning * into c;
  if c.id is null then
    raise exception 'No such customer, or it was merged into another record';
  end if;
  return c;
end;
$$;

-- Customers' codes and merge links are never changed by hand.
create function tcp_private.guard_customers()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.code is distinct from old.code then
    raise exception 'A customer code never changes' using errcode = '42501';
  end if;
  if old.merged_into is not null then
    raise exception 'A merged customer record cannot be changed' using errcode = '42501';
  end if;
  return new;
end;
$$;
create trigger customers_guard
  before update on public.customers
  for each row execute function tcp_private.guard_customers();

-- Other customers already using this phone number (for a "possible duplicate"
-- warning before adding someone).
create function public.customers_with_phone(p_phone text)
returns setof public.customers
language sql stable security definer
set search_path = ''
as $$
  select c.* from public.customers c
  where tcp_private.is_staff()
    and c.merged_into is null
    and c.phone = public.normalise_gh_phone(p_phone)
$$;

-- Start a draft invoice for a customer. Returns the invoice id.
create function public.create_draft_invoice(
  p_customer_id         bigint,
  p_deliver_to_location text default null,
  p_deliver_to_contact  text default null,
  p_deliver_to_phone    text default null,
  p_due_date            date default null,
  p_notes               text default null
)
returns bigint
language plpgsql security definer
set search_path = ''
as $$
declare
  new_id bigint;
begin
  perform tcp_private.require_role('owner', 'sales');
  if exists (select 1 from public.customers where id = p_customer_id and merged_into is not null) then
    raise exception 'That customer record was merged; use the surviving record';
  end if;
  insert into public.invoices (customer_id, deliver_to_location, deliver_to_contact,
                               deliver_to_phone, due_date, notes)
  values (p_customer_id, nullif(trim(p_deliver_to_location), ''),
          nullif(trim(p_deliver_to_contact), ''),
          public.normalise_gh_phone(p_deliver_to_phone), p_due_date,
          nullif(trim(p_notes), ''))
  returning id into new_id;
  return new_id;
end;
$$;

-- Change the details of a draft (issued invoices are locked by the trigger).
create function public.update_draft_invoice(
  p_invoice_id          bigint,
  p_deliver_to_location text,
  p_deliver_to_contact  text,
  p_deliver_to_phone    text,
  p_due_date            date,
  p_notes               text
)
returns void
language plpgsql security definer
set search_path = ''
as $$
begin
  perform tcp_private.require_role('owner', 'sales');
  update public.invoices
     set deliver_to_location = nullif(trim(p_deliver_to_location), ''),
         deliver_to_contact  = nullif(trim(p_deliver_to_contact), ''),
         deliver_to_phone    = public.normalise_gh_phone(p_deliver_to_phone),
         due_date            = p_due_date,
         notes               = nullif(trim(p_notes), '')
   where id = p_invoice_id and state = 'draft';
  if not found then
    raise exception 'Only a draft invoice can be changed';
  end if;
end;
$$;

-- Add a line to a draft invoice.
--   product line:  give p_product_id; name, unit and today's price are copied
--                  from the product unless a negotiated price is given.
--   delivery line: give a description, unit, quantity and the agreed price.
--   discount line: give a description and a NEGATIVE unit price.
create function public.add_invoice_line(
  p_invoice_id  bigint,
  p_kind        text,
  p_quantity    numeric,
  p_product_id  bigint  default null,
  p_unit_price  numeric default null,
  p_description text    default null,
  p_unit        text    default null
)
returns bigint
language plpgsql security definer
set search_path = ''
as $$
declare
  prod     public.products;
  new_id   bigint;
  next_pos integer;
begin
  perform tcp_private.require_role('owner', 'sales');

  -- Lock the invoice so two people adding lines at once can't clash.
  perform 1 from public.invoices where id = p_invoice_id and state = 'draft' for update;
  if not found then
    raise exception 'Lines can only be added to a draft invoice';
  end if;

  if p_kind = 'product' then
    select * into prod from public.products where id = p_product_id;
    if not found then
      raise exception 'Unknown product %', p_product_id;
    end if;
  elsif p_unit_price is null or p_description is null or p_unit is null then
    raise exception 'Delivery and discount lines need a description, unit and price';
  end if;

  select coalesce(max(position), 0) + 1 into next_pos
    from public.invoice_lines where invoice_id = p_invoice_id;

  insert into public.invoice_lines (invoice_id, position, kind, product_id,
                                    description, unit, quantity, unit_price)
  values (p_invoice_id, next_pos, p_kind, prod.id,
          coalesce(nullif(trim(p_description), ''), prod.name),
          coalesce(nullif(trim(p_unit), ''), prod.unit),
          p_quantity,
          round(coalesce(p_unit_price, prod.current_price), 2))
  returning id into new_id;
  return new_id;
end;
$$;

-- Remove a line from a draft invoice (the audit log keeps a record of it).
create function public.remove_invoice_line(p_line_id bigint)
returns void
language plpgsql security definer
set search_path = ''
as $$
begin
  perform tcp_private.require_role('owner', 'sales');
  delete from public.invoice_lines where id = p_line_id;
  if not found then
    raise exception 'No such line';
  end if;
end;
$$;

-- Issue a draft: give it its permanent number and lock it.
create function public.issue_invoice(p_invoice_id bigint)
returns text
language plpgsql security definer
set search_path = ''
as $$
declare
  inv public.invoices;
  num text;
begin
  perform tcp_private.require_role('owner', 'sales');
  select * into inv from public.invoices where id = p_invoice_id for update;
  if not found or inv.state <> 'draft' then
    raise exception 'Only a draft invoice can be issued';
  end if;
  if not exists (select 1 from public.invoice_lines where invoice_id = p_invoice_id) then
    raise exception 'An invoice needs at least one line before it is issued';
  end if;
  -- No zero or negative invoices (TCP has no complimentary sales for now).
  if (select sum(line_total) from public.invoice_lines where invoice_id = p_invoice_id) <= 0 then
    raise exception 'An invoice total must be more than zero';
  end if;
  num := tcp_private.next_number('invoice');
  update public.invoices
     set state = 'issued', invoice_no = num, issued_at = now()
   where id = p_invoice_id;
  return num;
end;
$$;

-- Cancel an invoice (draft or issued). Refused while any money is held
-- against it: correct or refund the payments first. Cancelling never
-- refunds anything by itself.
create function public.cancel_invoice(p_invoice_id bigint, p_reason text)
returns void
language plpgsql security definer
set search_path = ''
as $$
declare
  inv public.invoices;
  held numeric;
begin
  perform tcp_private.require_role('owner');
  if p_reason is null or length(trim(p_reason)) = 0 then
    raise exception 'A reason is needed to cancel an invoice';
  end if;
  select * into inv from public.invoices where id = p_invoice_id for update;
  if not found or inv.state = 'cancelled' then
    raise exception 'Only a draft or issued invoice can be cancelled';
  end if;
  select coalesce(sum(amount), 0) into held from public.payments where invoice_id = p_invoice_id;
  if held <> 0 then
    raise exception 'This invoice still holds GH₵ % in payments; correct or refund them first', held;
  end if;
  update public.invoices
     set state = 'cancelled', cancelled_at = now(), cancelled_by = auth.uid(),
         cancel_reason = trim(p_reason)
   where id = p_invoice_id;
end;
$$;

-- Record money received against an issued invoice. Refused if it is more
-- than what is still owed (no overpayments until a process exists for them).
create function public.record_payment(
  p_invoice_id bigint,
  p_amount     numeric,
  p_method     text,
  p_reference  text default null,
  p_paid_on    date default current_date
)
returns public.payments
language plpgsql security definer
set search_path = ''
as $$
declare
  inv     public.invoices;
  owed    numeric;
  receipt public.payments;
begin
  perform tcp_private.require_role('owner', 'sales', 'finance');
  -- Lock the invoice: two payments arriving at the same moment are handled
  -- one after the other, so together they can never exceed what is owed.
  select * into inv from public.invoices where id = p_invoice_id for update;
  if not found or inv.state <> 'issued' then
    raise exception 'Payments can only be recorded against an issued invoice';
  end if;
  if p_amount is null or round(p_amount, 2) <= 0 then
    raise exception 'A payment must be more than zero';
  end if;
  select balance into owed from public.invoice_summary where id = p_invoice_id;
  if round(p_amount, 2) > owed then
    raise exception 'GH₵ % is more than the GH₵ % still owed', round(p_amount, 2), owed;
  end if;
  insert into public.payments (receipt_no, invoice_id, kind, amount, method, reference, paid_on)
  values (tcp_private.next_number('receipt'), p_invoice_id, 'payment',
          round(p_amount, 2), p_method, nullif(trim(p_reference), ''), p_paid_on)
  returning * into receipt;
  return receipt;
end;
$$;

-- Undo a payment that was recorded wrongly (wrong amount, wrong invoice).
-- Always undoes the WHOLE payment; record the right amount as a new payment.
-- Not allowed once any of it has been refunded.
create function public.correct_payment(p_payment_id bigint, p_reason text)
returns public.payments
language plpgsql security definer
set search_path = ''
as $$
declare
  orig    public.payments;
  receipt public.payments;
begin
  perform tcp_private.require_role('owner', 'finance');
  select * into orig from public.payments where id = p_payment_id for update;
  if not found or orig.kind <> 'payment' then
    raise exception 'Only a payment can be corrected';
  end if;
  if exists (select 1 from public.payments where reverses_payment_id = p_payment_id and kind = 'correction') then
    raise exception 'This payment has already been corrected';
  end if;
  if exists (select 1 from public.payments where reverses_payment_id = p_payment_id and kind = 'refund') then
    raise exception 'This payment has refunds against it and can no longer be corrected';
  end if;
  insert into public.payments (receipt_no, invoice_id, kind, amount, method, reference,
                               paid_on, reverses_payment_id, reason)
  values (tcp_private.next_number('receipt'), orig.invoice_id, 'correction', -orig.amount,
          orig.method, orig.reference, current_date, orig.id, trim(p_reason))
  returning * into receipt;
  return receipt;
end;
$$;

-- Give money back. May be partial and may happen more than once, but the
-- refunds together never exceed the original payment.
create function public.refund_payment(
  p_payment_id bigint,
  p_amount     numeric,
  p_method     text,
  p_reason     text,
  p_reference  text default null
)
returns public.payments
language plpgsql security definer
set search_path = ''
as $$
declare
  orig     public.payments;
  refunded numeric;
  receipt  public.payments;
begin
  perform tcp_private.require_role('owner', 'finance');
  select * into orig from public.payments where id = p_payment_id for update;
  if not found or orig.kind <> 'payment' then
    raise exception 'Only a payment can be refunded';
  end if;
  if exists (select 1 from public.payments where reverses_payment_id = p_payment_id and kind = 'correction') then
    raise exception 'This payment was corrected; there is nothing left to refund';
  end if;
  if p_amount is null or round(p_amount, 2) <= 0 then
    raise exception 'A refund must be more than zero';
  end if;
  select coalesce(-sum(amount), 0) into refunded
    from public.payments where reverses_payment_id = p_payment_id and kind = 'refund';
  if refunded + round(p_amount, 2) > orig.amount then
    raise exception 'Refunds would total GH₵ %, more than the GH₵ % paid',
      refunded + round(p_amount, 2), orig.amount;
  end if;
  insert into public.payments (receipt_no, invoice_id, kind, amount, method, reference,
                               paid_on, reverses_payment_id, reason)
  values (tcp_private.next_number('receipt'), orig.invoice_id, 'refund', -round(p_amount, 2),
          p_method, nullif(trim(p_reference), ''), current_date, orig.id, trim(p_reason))
  returning * into receipt;
  return receipt;
end;
$$;

-- Merge two records of the same person. Everything moves to p_keep_id; the
-- other record is marked as merged and its code(s) become aliases.
create function public.merge_customers(p_keep_id bigint, p_merge_id bigint)
returns void
language plpgsql security definer
set search_path = ''
as $$
declare
  keep  public.customers;
  gone  public.customers;
begin
  perform tcp_private.require_role('owner');
  if p_keep_id = p_merge_id then
    raise exception 'Choose two different customers';
  end if;
  -- Lock both, in id order, so two merges at once can't deadlock.
  perform 1 from public.customers where id in (p_keep_id, p_merge_id) order by id for update;
  select * into keep from public.customers where id = p_keep_id;
  select * into gone from public.customers where id = p_merge_id;
  if keep.id is null or gone.id is null then
    raise exception 'Unknown customer';
  end if;
  if keep.merged_into is not null or gone.merged_into is not null then
    raise exception 'One of these customers has already been merged';
  end if;

  perform set_config('tcp.merging_customers', 'on', true);
  update public.invoices set customer_id = keep.id where customer_id = gone.id;
  perform set_config('tcp.merging_customers', 'off', true);

  update public.customer_code_aliases set customer_id = keep.id where customer_id = gone.id;
  insert into public.customer_code_aliases (code, customer_id) values (gone.code, keep.id);
  update public.customers set merged_into = keep.id where id = gone.id;
end;
$$;

-- Find a customer by current or old code.
create function public.find_customer_by_code(p_code text)
returns public.customers
language sql stable security definer
set search_path = ''
as $$
  select c.* from public.customers c
  where tcp_private.is_staff()
    and c.id = coalesce(
      (select id from public.customers where code = upper(trim(p_code)) and merged_into is null),
      (select customer_id from public.customer_code_aliases where code = upper(trim(p_code))),
      (select merged_into from public.customers where code = upper(trim(p_code)))
    )
$$;

-- Add or change a product (owner only). Prices are rounded to the pesewa.
create function public.save_product(
  p_site_id       text,
  p_name          text,
  p_category      text,
  p_unit          text,
  p_price         numeric,
  p_published     boolean default true,
  p_price_visible boolean default true
)
returns public.products
language plpgsql security definer
set search_path = ''
as $$
declare
  prod public.products;
begin
  perform tcp_private.require_role('owner');
  insert into public.products (site_id, name, category, unit, current_price, published, price_visible)
  values (p_site_id, trim(p_name), trim(p_category), trim(p_unit), round(p_price, 2),
          p_published, p_price_visible)
  on conflict (site_id) do update
     set name = excluded.name, category = excluded.category, unit = excluded.unit,
         current_price = excluded.current_price, published = excluded.published,
         price_visible = excluded.price_visible
  returning * into prod;
  return prod;
end;
$$;


-- -----------------------------------------------------------------------------
-- 14. Who can see and touch what (permissions)
--     Supabase normally lets its two web roles ("anon" = not logged in,
--     "authenticated" = logged in) reach tables in "public". Here that is
--     taken away and given back precisely:
--       - nobody writes to tables directly (only through the functions above)
--       - logged-in active staff can read the business tables
--       - the public can read public_catalogue and nothing else
--       - the publish helpers are for the server only ("service_role")
-- -----------------------------------------------------------------------------
revoke all on all tables    in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from public, anon, authenticated;
revoke all on all functions in schema tcp_private from public, anon, authenticated;
revoke all on all tables    in schema tcp_private from public, anon, authenticated;

-- Row-level security on every table: with no matching rule, nothing is visible.
alter table public.staff                 enable row level security;
alter table public.customers             enable row level security;
alter table public.customer_code_aliases enable row level security;
alter table public.products              enable row level security;
alter table public.invoices              enable row level security;
alter table public.invoice_lines         enable row level security;
alter table public.payments              enable row level security;
alter table public.audit_log             enable row level security;
alter table public.site_publish_requests enable row level security;
alter table public.site_catalogue_state  enable row level security;

-- Staff may read the business records.
grant usage on schema tcp_private to authenticated;
grant execute on function tcp_private.staff_role() to authenticated;
grant execute on function tcp_private.is_staff() to authenticated;

grant select on public.customers, public.customer_code_aliases, public.products,
                public.invoices, public.invoice_lines, public.payments,
                public.site_publish_requests, public.site_catalogue_state
  to authenticated;
grant select on public.invoice_summary, public.overdue_invoices, public.site_price_status
  to authenticated;

create policy staff_read on public.customers             for select to authenticated using (tcp_private.is_staff());
create policy staff_read on public.customer_code_aliases for select to authenticated using (tcp_private.is_staff());
create policy staff_read on public.products              for select to authenticated using (tcp_private.is_staff());
create policy staff_read on public.invoices              for select to authenticated using (tcp_private.is_staff());
create policy staff_read on public.invoice_lines         for select to authenticated using (tcp_private.is_staff());
create policy staff_read on public.payments              for select to authenticated using (tcp_private.is_staff());
create policy staff_read on public.site_publish_requests for select to authenticated using (tcp_private.is_staff());
create policy staff_read on public.site_catalogue_state  for select to authenticated using (tcp_private.is_staff());

-- Only the owner reads the staff list and the audit log.
grant select on public.staff, public.audit_log to authenticated;
create policy owner_read on public.staff     for select to authenticated
  using (tcp_private.staff_role() = 'owner' or user_id = auth.uid());
create policy owner_read on public.audit_log for select to authenticated
  using (tcp_private.staff_role() = 'owner');

-- The actions staff can take. Each checks the role itself.
grant execute on function
  public.normalise_gh_phone(text),
  public.create_customer(text, text, text, text),
  public.update_customer(bigint, text, text, text, text),
  public.customers_with_phone(text),
  public.find_customer_by_code(text),
  public.create_draft_invoice(bigint, text, text, text, date, text),
  public.update_draft_invoice(bigint, text, text, text, date, text),
  public.add_invoice_line(bigint, text, numeric, bigint, numeric, text, text),
  public.remove_invoice_line(bigint),
  public.issue_invoice(bigint),
  public.cancel_invoice(bigint, text),
  public.record_payment(bigint, numeric, text, text, date),
  public.correct_payment(bigint, text),
  public.refund_payment(bigint, numeric, text, text, text),
  public.merge_customers(bigint, bigint),
  public.save_product(text, text, text, text, numeric, boolean, boolean)
  to authenticated;

-- The public website's only window into the database.
grant select on public.public_catalogue to anon, authenticated;

-- Publishing helpers: server only.
grant execute on function public.claim_site_publish() to service_role;
grant execute on function public.finish_site_publish(bigint, boolean, text) to service_role;
