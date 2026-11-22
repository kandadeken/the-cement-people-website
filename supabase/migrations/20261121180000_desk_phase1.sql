-- =============================================================================
-- The Cement People: Invoice Desk, phase 1 database additions
--
-- What this file is
--   The second migration. It adds what the Supabase-connected Invoice Desk
--   needs, following "TCP Invoice Desk on Supabase: Design (v2.1)", approved
--   by ChatGPT and Daniel on 21 November 2026. It changes no money rule,
--   numbering rule or permission from the first migration.
--
-- What it adds
--   1. Request ids on payments, corrections and refunds: a retry after a
--      dropped connection returns the receipt already made, never a second
--      one; the same id with different details is refused.
--   2. balance_after on every receipt, stored at the moment it is recorded,
--      so an old receipt always shows the balance as it was.
--   3. A frozen "billed to" (name and phone) and issued_by on every issued
--      invoice, so an old invoice reproduces exactly even after the
--      customer's details are corrected.
--   4. invoice_document() and receipt_document(): one consistent read of an
--      invoice or a receipt, from which the PDFs are drawn.
--   5. invoice_list: the list and search screens.
--   Plus save_draft_invoice(): saves a whole draft (customer, delivery and
--   every line) in one step, so a weak connection can never leave a draft
--   half-saved. Its request id stops a retry from creating a second draft.
--   Plus (after ChatGPT's review of PR #35):
--   6. A request id on create_customer, so a retry never adds a twin
--      customer, even one with no phone number to match on.
--   7. Two calls with the same request id at the same moment are taken one
--      after the other (request_lock), so the second gets the first one's
--      draft or customer instead of an error.
--   8. my_staff(): "am I still active staff?" that refuses clearly, because
--      plain reads (products, customer lookups, the invoice list) return
--      an empty answer, not an error, once someone's access is removed.
--
-- Nothing here has been applied to any database yet. The tests in
-- supabase/tests/ run it on a throwaway Postgres; merging it into main
-- deploys it to the tcp-test project only (see DEPLOYMENT.md).
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1 and 2. Payments: request id and balance after
-- -----------------------------------------------------------------------------
alter table public.payments
  add column request_id    uuid,
  add column balance_after numeric(14, 2);

-- One request id, one receipt.
create unique index payments_request_id_unique
  on public.payments (request_id) where request_id is not null;

comment on column public.payments.request_id is
  'Made once on the phone when Record is first tapped; the same id on a retry returns this receipt.';
comment on column public.payments.balance_after is
  'What was still owed on the invoice right after this receipt, stored when it was recorded.';


-- -----------------------------------------------------------------------------
-- 3. Invoices: frozen "billed to" and who issued
-- -----------------------------------------------------------------------------
alter table public.invoices
  add column billed_to_name  text,
  add column billed_to_phone text,
  add column issued_by       uuid,
  add column request_id      uuid,
  add constraint issued_invoice_has_snapshot
    check (invoice_no is null or (issued_by is not null
           and (billed_to_name is not null or billed_to_phone is not null)));

create unique index invoices_request_id_unique
  on public.invoices (request_id) where request_id is not null;

comment on column public.invoices.billed_to_name is
  'The customer''s name as it was when the invoice was issued. Never changes afterwards.';
comment on column public.invoices.request_id is
  'Made once on the phone for a new draft; a retry returns the same draft instead of a second one.';

-- The lock on issued invoices now also covers the new frozen fields.
create or replace function tcp_private.guard_invoices()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'Invoices are never deleted; cancel it instead' using errcode = '42501';
  end if;
  -- A customer merge (merge_customers sets this flag) may move any invoice
  -- to the surviving customer record, changing nothing else about it.
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
       or (to_jsonb(new) - array['state', 'cancelled_at', 'cancelled_by', 'cancel_reason'])
          <> (to_jsonb(old) - array['state', 'cancelled_at', 'cancelled_by', 'cancel_reason']) then
      raise exception 'An issued invoice is locked; cancel it and issue a replacement'
        using errcode = '42501';
    end if;
  end if;
  return new;
end;
$$;

-- Issuing now also freezes who is billed and records who issued.
create or replace function public.issue_invoice(p_invoice_id bigint)
returns text
language plpgsql security definer
set search_path = ''
as $$
declare
  inv  public.invoices;
  cust public.customers;
  num  text;
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
  select * into cust from public.customers where id = inv.customer_id;
  if cust.merged_into is not null then
    raise exception 'That customer record was merged; use the surviving record';
  end if;
  num := tcp_private.next_number('invoice');
  update public.invoices
     set state = 'issued', invoice_no = num, issued_at = now(),
         issued_by = auth.uid(),
         billed_to_name = cust.name, billed_to_phone = cust.phone
   where id = p_invoice_id;
  return num;
end;
$$;


-- -----------------------------------------------------------------------------
-- 7. One request id at a time
--   Holds a lock on the request id until the end of the transaction. A
--   second call with the same id waits here, then finds what the first one
--   made (each statement after the wait sees the first call's committed
--   work). Different ids never wait for each other.
-- -----------------------------------------------------------------------------
create function tcp_private.request_lock(p_request_id uuid)
returns void
language sql
set search_path = ''
as $$
  select pg_advisory_xact_lock(('x' || substr(md5(p_request_id::text), 1, 16))::bit(64)::bigint);
$$;


-- -----------------------------------------------------------------------------
-- 6. Customers: request id
-- -----------------------------------------------------------------------------
alter table public.customers add column request_id uuid;
create unique index customers_request_id_unique
  on public.customers (request_id) where request_id is not null;
comment on column public.customers.request_id is
  'Made once on the phone when a new customer is first saved; a retry returns this customer.';

-- create_customer gains p_request_id (optional). Everything else is as in
-- the first migration. A repeat must ask for exactly the same customer.
drop function public.create_customer(text, text, text, text);
create function public.create_customer(
  p_phone      text default null,
  p_name       text default null,
  p_area       text default null,
  p_notes      text default null,
  p_request_id uuid default null
)
returns public.customers
language plpgsql security definer
set search_path = ''
as $$
declare
  c public.customers;
begin
  perform tcp_private.require_role('owner', 'sales');
  if p_request_id is not null then
    perform tcp_private.request_lock(p_request_id);
    select * into c from public.customers where request_id = p_request_id;
    if found then
      if c.phone is distinct from public.normalise_gh_phone(p_phone)
         or c.name  is distinct from nullif(trim(p_name), '')
         or c.area  is distinct from nullif(trim(p_area), '')
         or c.notes is distinct from nullif(trim(p_notes), '') then
        raise exception 'This request id was already used for a different customer';
      end if;
      return c;
    end if;
  end if;
  insert into public.customers (code, phone, name, area, notes, request_id)
  values (tcp_private.next_number('customer'),
          public.normalise_gh_phone(p_phone),
          nullif(trim(p_name), ''),
          nullif(trim(p_area), ''),
          nullif(trim(p_notes), ''),
          p_request_id)
  returning * into c;
  return c;
end;
$$;


-- -----------------------------------------------------------------------------
-- 8. my_staff: who am I, and am I still allowed in?
--   Returns the caller's name and role, or refuses with the same message as
--   every action ("only TCP staff"). The desk asks this whenever a read comes
--   back empty, so a removed staff member is signed out instead of being
--   shown an empty price list or "new customer".
-- -----------------------------------------------------------------------------
create function public.my_staff()
returns jsonb
language plpgsql stable security definer
set search_path = ''
as $$
declare
  st public.staff;
begin
  perform tcp_private.require_role('owner', 'sales', 'finance');
  select * into st from public.staff where user_id = auth.uid();
  return jsonb_build_object('full_name', st.full_name, 'role', st.role);
end;
$$;


-- -----------------------------------------------------------------------------
-- save_draft_invoice: the whole draft in one step
--   p_invoice_id null = a new draft (with p_request_id, a retry returns the
--   same draft). Otherwise the draft is updated and its lines replaced.
--   p_lines: a JSON list of {kind, product_id, quantity, unit_price,
--   description, unit}. Each line goes through add_invoice_line, so the
--   same rules apply (price copied from the product unless agreed, etc.).
-- -----------------------------------------------------------------------------
create function public.save_draft_invoice(
  p_invoice_id          bigint,
  p_customer_id         bigint,
  p_deliver_to_location text,
  p_deliver_to_contact  text,
  p_deliver_to_phone    text,
  p_due_date            date,
  p_notes               text,
  p_lines               jsonb,
  p_request_id          uuid default null
)
returns bigint
language plpgsql security definer
set search_path = ''
as $$
declare
  inv_id bigint := p_invoice_id;
  line   jsonb;
begin
  perform tcp_private.require_role('owner', 'sales');
  if p_lines is null or jsonb_typeof(p_lines) <> 'array' then
    raise exception 'The lines must be a list';
  end if;

  if inv_id is null then
    -- A retry of a draft that was already created: carry on with it. The
    -- lock makes a simultaneous retry wait for the first call, then find
    -- its draft (instead of failing on the unique request id).
    if p_request_id is not null then
      perform tcp_private.request_lock(p_request_id);
      select id into inv_id from public.invoices where request_id = p_request_id;
    end if;
    if inv_id is null then
      inv_id := public.create_draft_invoice(p_customer_id, p_deliver_to_location,
                  p_deliver_to_contact, p_deliver_to_phone, p_due_date, p_notes);
      update public.invoices set request_id = p_request_id where id = inv_id;
    end if;
  end if;

  -- Lock the draft so nothing else changes it while it is saved.
  perform 1 from public.invoices where id = inv_id and state = 'draft' for update;
  if not found then
    raise exception 'Only a draft invoice can be changed';
  end if;
  if exists (select 1 from public.customers where id = p_customer_id and merged_into is not null) then
    raise exception 'That customer record was merged; use the surviving record';
  end if;
  update public.invoices
     set customer_id         = p_customer_id,
         deliver_to_location = nullif(trim(p_deliver_to_location), ''),
         deliver_to_contact  = nullif(trim(p_deliver_to_contact), ''),
         deliver_to_phone    = public.normalise_gh_phone(p_deliver_to_phone),
         due_date            = p_due_date,
         notes               = nullif(trim(p_notes), '')
   where id = inv_id;

  delete from public.invoice_lines where invoice_id = inv_id;
  for line in select * from jsonb_array_elements(p_lines) loop
    perform public.add_invoice_line(
      inv_id,
      line ->> 'kind',
      (line ->> 'quantity')::numeric,
      (line ->> 'product_id')::bigint,
      (line ->> 'unit_price')::numeric,
      line ->> 'description',
      line ->> 'unit');
  end loop;
  return inv_id;
end;
$$;


-- -----------------------------------------------------------------------------
-- Payments, corrections and refunds with request ids and balance_after.
-- The old versions are replaced; their behaviour is unchanged except for:
--   - p_request_id (optional): checked AFTER the lock is taken, so two
--     simultaneous calls with the same id are handled one after the other
--   - balance_after is written on every new receipt
-- -----------------------------------------------------------------------------

-- A repeat of a request is only accepted if it asks for exactly the same
-- thing. Returns the existing receipt, or nothing if the id is new.
create function tcp_private.repeat_of(
  p_request_id uuid, p_kind text, p_invoice_id bigint, p_reverses bigint,
  p_amount numeric, p_method text, p_reason text
)
returns public.payments
language plpgsql
set search_path = ''
as $$
declare
  existing public.payments;
begin
  if p_request_id is null then
    return null;
  end if;
  select * into existing from public.payments where request_id = p_request_id;
  if not found then
    return null;
  end if;
  if existing.kind is distinct from p_kind
     or existing.invoice_id is distinct from p_invoice_id
     or existing.reverses_payment_id is distinct from p_reverses
     or existing.amount is distinct from p_amount
     or existing.method is distinct from p_method
     or coalesce(trim(existing.reason), '') is distinct from coalesce(trim(p_reason), '') then
    raise exception 'This request id was already used for a different payment';
  end if;
  return existing;
end;
$$;

drop function public.record_payment(bigint, numeric, text, text, date);
create function public.record_payment(
  p_invoice_id bigint,
  p_amount     numeric,
  p_method     text,
  p_reference  text default null,
  p_paid_on    date default current_date,
  p_request_id uuid default null
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
  -- Lock the invoice: payments arriving at the same moment are handled one
  -- after the other, so together they can never exceed what is owed.
  select * into inv from public.invoices where id = p_invoice_id for update;
  if not found or inv.state <> 'issued' then
    -- A repeat of a payment already recorded is still answered, even if the
    -- invoice has since been fully paid.
    receipt := tcp_private.repeat_of(p_request_id, 'payment', p_invoice_id, null,
                                     round(p_amount, 2), p_method, null);
    if receipt.id is not null then
      return receipt;
    end if;
    raise exception 'Payments can only be recorded against an issued invoice';
  end if;
  receipt := tcp_private.repeat_of(p_request_id, 'payment', p_invoice_id, null,
                                   round(p_amount, 2), p_method, null);
  if receipt.id is not null then
    return receipt;
  end if;
  if p_amount is null or round(p_amount, 2) <= 0 then
    raise exception 'A payment must be more than zero';
  end if;
  select balance into owed from public.invoice_summary where id = p_invoice_id;
  if round(p_amount, 2) > owed then
    raise exception 'GH₵ % is more than the GH₵ % still owed', round(p_amount, 2), owed;
  end if;
  insert into public.payments (receipt_no, invoice_id, kind, amount, method, reference,
                               paid_on, request_id, balance_after)
  values (tcp_private.next_number('receipt'), p_invoice_id, 'payment',
          round(p_amount, 2), p_method, nullif(trim(p_reference), ''), p_paid_on,
          p_request_id, owed - round(p_amount, 2))
  returning * into receipt;
  return receipt;
end;
$$;

drop function public.correct_payment(bigint, text);
create function public.correct_payment(
  p_payment_id bigint,
  p_reason     text,
  p_request_id uuid default null
)
returns public.payments
language plpgsql security definer
set search_path = ''
as $$
declare
  orig    public.payments;
  owed    numeric;
  receipt public.payments;
begin
  perform tcp_private.require_role('owner', 'finance');
  select * into orig from public.payments where id = p_payment_id for update;
  if not found or orig.kind <> 'payment' then
    raise exception 'Only a payment can be corrected';
  end if;
  -- Lock the invoice too, so balance_after is exact.
  perform 1 from public.invoices where id = orig.invoice_id for update;
  receipt := tcp_private.repeat_of(p_request_id, 'correction', orig.invoice_id, orig.id,
                                   -orig.amount, orig.method, p_reason);
  if receipt.id is not null then
    return receipt;
  end if;
  if exists (select 1 from public.payments where reverses_payment_id = p_payment_id and kind = 'correction') then
    raise exception 'This payment has already been corrected';
  end if;
  if exists (select 1 from public.payments where reverses_payment_id = p_payment_id and kind = 'refund') then
    raise exception 'This payment has refunds against it and can no longer be corrected';
  end if;
  select balance into owed from public.invoice_summary where id = orig.invoice_id;
  insert into public.payments (receipt_no, invoice_id, kind, amount, method, reference,
                               paid_on, reverses_payment_id, reason, request_id, balance_after)
  values (tcp_private.next_number('receipt'), orig.invoice_id, 'correction', -orig.amount,
          orig.method, orig.reference, current_date, orig.id, trim(p_reason),
          p_request_id, owed + orig.amount)
  returning * into receipt;
  return receipt;
end;
$$;

drop function public.refund_payment(bigint, numeric, text, text, text);
create function public.refund_payment(
  p_payment_id bigint,
  p_amount     numeric,
  p_method     text,
  p_reason     text,
  p_reference  text default null,
  p_request_id uuid default null
)
returns public.payments
language plpgsql security definer
set search_path = ''
as $$
declare
  orig     public.payments;
  refunded numeric;
  owed     numeric;
  receipt  public.payments;
begin
  perform tcp_private.require_role('owner', 'finance');
  select * into orig from public.payments where id = p_payment_id for update;
  if not found or orig.kind <> 'payment' then
    raise exception 'Only a payment can be refunded';
  end if;
  perform 1 from public.invoices where id = orig.invoice_id for update;
  receipt := tcp_private.repeat_of(p_request_id, 'refund', orig.invoice_id, orig.id,
                                   -round(p_amount, 2), p_method, p_reason);
  if receipt.id is not null then
    return receipt;
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
  select balance into owed from public.invoice_summary where id = orig.invoice_id;
  insert into public.payments (receipt_no, invoice_id, kind, amount, method, reference,
                               paid_on, reverses_payment_id, reason, request_id, balance_after)
  values (tcp_private.next_number('receipt'), orig.invoice_id, 'refund', -round(p_amount, 2),
          p_method, nullif(trim(p_reference), ''), current_date, orig.id, trim(p_reason),
          p_request_id, owed + round(p_amount, 2))
  returning * into receipt;
  return receipt;
end;
$$;


-- -----------------------------------------------------------------------------
-- 4. Documents: one consistent read for each PDF
-- -----------------------------------------------------------------------------

-- A staff member's name, for "issued by" / "recorded by" on documents.
create function tcp_private.staff_name(p_user uuid)
returns text
language sql stable security definer
set search_path = ''
as $$ select full_name from public.staff where user_id = p_user $$;

-- Everything an invoice PDF shows, as one JSON record. For an issued (or
-- cancelled after issue) invoice, "billed to" comes from the frozen copy,
-- never from the customer's current details.
create function public.invoice_document(p_invoice_id bigint)
returns jsonb
language plpgsql stable security definer
set search_path = ''
as $$
declare
  inv  public.invoices;
  cust public.customers;
  s    public.invoice_summary;
begin
  perform tcp_private.require_role('owner', 'sales', 'finance');
  select * into inv from public.invoices where id = p_invoice_id;
  if not found then
    raise exception 'No such invoice';
  end if;
  select * into cust from public.customers where id = inv.customer_id;
  select * into s from public.invoice_summary where id = p_invoice_id;
  return jsonb_build_object(
    'id', inv.id,
    'invoice_no', inv.invoice_no,
    'state', inv.state,
    'status', s.status,
    'issued_at', inv.issued_at,
    'issued_by', tcp_private.staff_name(inv.issued_by),
    'due_date', inv.due_date,
    'notes', inv.notes,
    'cancel_reason', inv.cancel_reason,
    'customer_id', inv.customer_id,
    'customer_code', cust.code,
    'billed_to_name', case when inv.invoice_no is not null then inv.billed_to_name else cust.name end,
    'billed_to_phone', case when inv.invoice_no is not null then inv.billed_to_phone else cust.phone end,
    'deliver_to_location', inv.deliver_to_location,
    'deliver_to_contact', inv.deliver_to_contact,
    'deliver_to_phone', inv.deliver_to_phone,
    'lines', coalesce((
      select jsonb_agg(jsonb_build_object(
               'position', l.position, 'kind', l.kind, 'product_id', l.product_id,
               'site_id', p.site_id, 'category', p.category,
               'description', l.description, 'unit', l.unit,
               'quantity', l.quantity, 'unit_price', l.unit_price, 'line_total', l.line_total)
             order by l.position)
      from public.invoice_lines l left join public.products p on p.id = l.product_id
      where l.invoice_id = inv.id), '[]'::jsonb),
    'total', s.total,
    'paid', s.paid,
    'balance', s.balance,
    'payments', coalesce((
      select jsonb_agg(jsonb_build_object(
               'id', pay.id, 'receipt_no', pay.receipt_no, 'kind', pay.kind,
               'amount', pay.amount, 'method', pay.method, 'reference', pay.reference,
               'paid_on', pay.paid_on, 'balance_after', pay.balance_after,
               'recorded_by', tcp_private.staff_name(pay.recorded_by))
             order by pay.id)
      from public.payments pay where pay.invoice_id = inv.id), '[]'::jsonb)
  );
end;
$$;

-- Everything a receipt PDF shows. The balance is the stored balance_after,
-- and "paid before" counts only receipts made before this one, so a receipt
-- reads the same however many later payments or refunds follow.
create function public.receipt_document(p_payment_id bigint)
returns jsonb
language plpgsql stable security definer
set search_path = ''
as $$
declare
  pay public.payments;
  doc jsonb;
begin
  perform tcp_private.require_role('owner', 'sales', 'finance');
  select * into pay from public.payments where id = p_payment_id;
  if not found then
    raise exception 'No such receipt';
  end if;
  doc := public.invoice_document(pay.invoice_id);
  return jsonb_build_object(
    'receipt_no', pay.receipt_no,
    'kind', pay.kind,
    'amount', pay.amount,
    'method', pay.method,
    'reference', pay.reference,
    'paid_on', pay.paid_on,
    'reason', pay.reason,
    'balance_after', pay.balance_after,
    'recorded_by', tcp_private.staff_name(pay.recorded_by),
    'payments_before', (select count(*) from public.payments
                         where invoice_id = pay.invoice_id and id < pay.id),
    'paid_before', (select coalesce(sum(amount), 0) from public.payments
                     where invoice_id = pay.invoice_id and id < pay.id),
    'invoice', doc - 'payments' - 'paid' - 'balance' - 'status'
  );
end;
$$;


-- -----------------------------------------------------------------------------
-- 5. invoice_list: the list and search screens (newest first)
-- -----------------------------------------------------------------------------
create view public.invoice_list
with (security_invoker = true)
as
select
  s.id,
  s.invoice_no,
  s.state,
  s.status,
  s.issued_at,
  i.created_at,
  s.due_date,
  s.total,
  s.paid,
  s.balance,
  i.customer_id,
  c.code as customer_code,
  coalesce(i.billed_to_name, c.name)   as billed_to_name,
  coalesce(i.billed_to_phone, c.phone) as billed_to_phone
from public.invoice_summary s
join public.invoices i on i.id = s.id
join public.customers c on c.id = i.customer_id
order by coalesce(s.issued_at, i.created_at) desc, s.id desc;


-- -----------------------------------------------------------------------------
-- Permissions for the new pieces (same model as the first migration)
-- -----------------------------------------------------------------------------
revoke all on function public.save_draft_invoice(bigint, bigint, text, text, text, date, text, jsonb, uuid) from public, anon, authenticated;
revoke all on function public.record_payment(bigint, numeric, text, text, date, uuid) from public, anon, authenticated;
revoke all on function public.correct_payment(bigint, text, uuid) from public, anon, authenticated;
revoke all on function public.refund_payment(bigint, numeric, text, text, text, uuid) from public, anon, authenticated;
revoke all on function public.invoice_document(bigint) from public, anon, authenticated;
revoke all on function public.receipt_document(bigint) from public, anon, authenticated;
revoke all on function tcp_private.repeat_of(uuid, text, bigint, bigint, numeric, text, text) from public, anon, authenticated;
revoke all on function tcp_private.staff_name(uuid) from public, anon, authenticated;
revoke all on function tcp_private.request_lock(uuid) from public, anon, authenticated;
revoke all on function public.create_customer(text, text, text, text, uuid) from public, anon, authenticated;
revoke all on function public.my_staff() from public, anon, authenticated;
revoke all on public.invoice_list from anon, authenticated;

grant execute on function
  public.save_draft_invoice(bigint, bigint, text, text, text, date, text, jsonb, uuid),
  public.create_customer(text, text, text, text, uuid),
  public.my_staff(),
  public.record_payment(bigint, numeric, text, text, date, uuid),
  public.correct_payment(bigint, text, uuid),
  public.refund_payment(bigint, numeric, text, text, text, uuid),
  public.invoice_document(bigint),
  public.receipt_document(bigint)
  to authenticated;
grant select on public.invoice_list to authenticated;
