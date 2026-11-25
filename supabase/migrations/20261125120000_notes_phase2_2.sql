-- =============================================================================
-- The Cement People: TCP Back Office, Phase 2.2 (notes from estimate to receipt)
--
-- What this file is
--   It follows "TCP Back Office: Phase 2.2 Design, Notes from Estimate to
--   Receipt (v1.6)", approved by ChatGPT and Daniel on 25 November 2026.
--   Additive: nothing is removed; every earlier field of every document stays.
--
--   Notes to the customer: on invoices, the existing notes column (the Back
--   Office's "Note to the customer" box, printed on the invoice; it also
--   holds the delivery choice and the estimate reference, one per line); on
--   payments and refunds, a new customer_note column, printed on the receipt.
--   All are fixed once issued or recorded (invoices are locked at issue;
--   payments are never edited).
--
--   Internal notes: on payments, refunds and corrections, a new
--   internal_note column, fixed once recorded; on invoices, a new log table,
--   invoice_notes, that staff add to at any stage. A note is never edited or
--   deleted: a mistake is fixed by a correction, a new note linked to what it
--   corrects (an invoice note, or a payment record's internal note). Each
--   note or payment note can be corrected ONCE, so corrections form a single
--   line; the database enforces that, and that a correction points at
--   something on the same invoice.
--
--   Request ids: the same request id with exactly the same details gives
--   back the first record; with any different detail (notes included) it is
--   refused. This now also compares the reference (repeat_payment).
--
--   search_notes(): one staff-only function that searches every kind of note
--   inside the database (trigram indexes on the note text).
--
-- Merging this into main deploys it to the tcp-test project only.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. pg_trgm (Postgres's trigram extension; Supabase offers it). If it is
--    already installed somewhere, that copy is used; the indexes below find
--    its schema rather than assume one.
-- -----------------------------------------------------------------------------
create schema if not exists extensions;
create extension if not exists pg_trgm with schema extensions;

-- -----------------------------------------------------------------------------
-- 2. Notes to the customer and internal notes on payments; lengths.
-- -----------------------------------------------------------------------------
-- The invoice's notes column: the note box allows 500 characters, plus the
-- delivery and estimate lines, so at most 600 in all. Checked by a trigger
-- only when the notes themselves are written or changed. (A CHECK
-- constraint, even NOT VALID, is checked again whenever ANY column of a row
-- changes, so issuing or cancelling an older invoice with a longer note
-- would have been refused. Existing invoices are never blocked this way.)
create function tcp_private.invoices_notes_length()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.notes is not null and char_length(new.notes) > 600
     and (tg_op = 'INSERT' or new.notes is distinct from old.notes) then
    raise exception 'The note to the customer is too long: at most 600 characters, including the delivery and estimate lines'
      using errcode = '23514';
  end if;
  return new;
end;
$$;
create trigger invoices_notes_length
  before insert or update of notes on public.invoices
  for each row execute function tcp_private.invoices_notes_length();

alter table public.payments
  add column customer_note text,
  add column internal_note text,
  add constraint payments_customer_note_length check (customer_note is null or char_length(customer_note) <= 300),
  add constraint payments_internal_note_length check (internal_note is null or char_length(internal_note) <= 500),
  -- A correction is never sent to the customer.
  add constraint payments_no_customer_note_on_corrections check (kind <> 'correction' or customer_note is null),
  -- So a note's correction can point at "this payment, on this invoice".
  add constraint payments_invoice_id_id_key unique (invoice_id, id);

-- -----------------------------------------------------------------------------
-- 3. invoice_notes: the invoice's internal notes log, and every correction.
-- -----------------------------------------------------------------------------
create table public.invoice_notes (
  id                  bigint generated always as identity primary key,
  invoice_id          bigint not null references public.invoices (id),
  body                text not null check (char_length(trim(body)) between 1 and 1000),
  category            text not null default 'general' check (category in (
                        'general', 'payment', 'delivery', 'customer_request',
                        'complaint', 'stock', 'follow_up')),
  -- What this note corrects: another note, or a payment record's internal
  -- note, on the SAME invoice (the composite keys below), never both.
  corrects_note_id    bigint,
  corrects_payment_id bigint,
  -- A note brought in from the customer's website estimate.
  estimate_ref        text,
  created_by          uuid not null default auth.uid(),
  created_at          timestamptz not null default now(),
  request_id          uuid unique,
  constraint invoice_notes_invoice_id_id_key unique (invoice_id, id),
  constraint invoice_notes_corrects_note_same_invoice
    foreign key (invoice_id, corrects_note_id) references public.invoice_notes (invoice_id, id),
  constraint invoice_notes_corrects_payment_same_invoice
    foreign key (invoice_id, corrects_payment_id) references public.payments (invoice_id, id),
  constraint invoice_notes_one_target check (corrects_note_id is null or corrects_payment_id is null),
  constraint invoice_notes_not_itself check (corrects_note_id is null or corrects_note_id <> id)
);
comment on table public.invoice_notes is
  'Internal notes on invoices, and corrections of notes. Staff only. Never edited or deleted.';
-- Each note, and each payment note, is corrected at most once: corrections
-- form one line, and a second, competing correction is refused.
create unique index invoice_notes_one_correction_per_note
  on public.invoice_notes (corrects_note_id) where corrects_note_id is not null;
create unique index invoice_notes_one_correction_per_payment
  on public.invoice_notes (corrects_payment_id) where corrects_payment_id is not null;
create index invoice_notes_created_at_idx on public.invoice_notes (created_at);
create index invoice_notes_created_by_idx on public.invoice_notes (created_by);
create index payments_recorded_at_idx on public.payments (recorded_at);
create index payments_recorded_by_idx on public.payments (recorded_by);

-- Trigram indexes on every note text, built with whichever schema holds
-- pg_trgm (see 1).
do $$
declare
  ops text := (select quote_ident(n.nspname) || '.gin_trgm_ops'
                 from pg_extension e join pg_namespace n on n.oid = e.extnamespace
                where e.extname = 'pg_trgm');
begin
  execute format('create index invoice_notes_body_trgm on public.invoice_notes using gin (body %s)', ops);
  execute format('create index payments_internal_note_trgm on public.payments using gin (internal_note %s)', ops);
  execute format('create index payments_customer_note_trgm on public.payments using gin (customer_note %s)', ops);
  execute format('create index invoices_notes_trgm on public.invoices using gin (notes %s)', ops);
end $$;

-- Row rules: staff read; nobody inserts directly (add_invoice_note does);
-- nobody updates or deletes, not even the owner (the trigger below).
alter table public.invoice_notes enable row level security;
create policy staff_read on public.invoice_notes for select to authenticated using (tcp_private.is_staff());
revoke all on public.invoice_notes from public, anon, authenticated;
grant select on public.invoice_notes to authenticated;

create function tcp_private.guard_invoice_notes()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'Notes are never edited or deleted; add a correction instead'
    using errcode = '42501';
end;
$$;
create trigger invoice_notes_guard
  before update or delete on public.invoice_notes
  for each row execute function tcp_private.guard_invoice_notes();

-- -----------------------------------------------------------------------------
-- 4. The corrections of a note or of a payment's internal note, oldest
--    first: one line, so the last is the current wording.
-- -----------------------------------------------------------------------------
create function tcp_private.note_chain(p_note_id bigint, p_payment_id bigint)
returns jsonb
language sql stable
set search_path = ''
as $$
  with recursive chain as (
    select n.*, 1 as depth from public.invoice_notes n
     where (p_note_id is not null and n.corrects_note_id = p_note_id)
        or (p_payment_id is not null and n.corrects_payment_id = p_payment_id)
    union all
    select n.*, c.depth + 1 from public.invoice_notes n join chain c on n.corrects_note_id = c.id
  )
  select coalesce(jsonb_agg(jsonb_build_object(
           'id', id, 'body', body, 'category', category,
           'by', tcp_private.staff_name(created_by), 'at', created_at) order by depth), '[]'::jsonb)
    from chain;
$$;
revoke all on function tcp_private.note_chain(bigint, bigint) from public, anon, authenticated;

-- -----------------------------------------------------------------------------
-- 5. Request ids for payments, refunds and corrections, now matching every
--    detail: the same id with any different detail is refused.
-- -----------------------------------------------------------------------------
create function tcp_private.repeat_payment(
  p_request_id uuid, p_kind text, p_invoice_id bigint, p_reverses bigint,
  p_amount numeric, p_method text, p_reference text, p_reason text,
  p_customer_note text, p_internal_note text,
  -- The date the money was paid: given by record_payment only. Refunds and
  -- corrections are dated by the server when recorded, so they pass null
  -- and their date is not compared (a retry just after midnight is still
  -- the same refund).
  p_paid_on date default null
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
     or existing.reference is distinct from nullif(trim(p_reference), '')
     or coalesce(trim(existing.reason), '') is distinct from coalesce(trim(p_reason), '')
     or existing.customer_note is distinct from nullif(trim(p_customer_note), '')
     or existing.internal_note is distinct from nullif(trim(p_internal_note), '')
     or (p_paid_on is not null and existing.paid_on is distinct from p_paid_on) then
    raise exception 'This request id was already used for a different payment';
  end if;
  return existing;
end;
$$;
revoke all on function tcp_private.repeat_payment(uuid, text, bigint, bigint, numeric, text, text, text, text, text, date)
  from public, anon, authenticated;

-- -----------------------------------------------------------------------------
-- 6. The money functions, with their optional notes. Same names; the new
--    inputs come last with defaults, so every existing call works unchanged.
-- -----------------------------------------------------------------------------
drop function public.record_payment(bigint, numeric, text, text, date, uuid);
drop function public.refund_payment(bigint, numeric, text, text, text, uuid);
drop function public.correct_payment(bigint, text, uuid);

create function public.record_payment(
  p_invoice_id bigint,
  p_amount     numeric,
  p_method     text,
  p_reference  text default null,
  p_paid_on    date default current_date,
  p_request_id uuid default null,
  -- Phase 2.2: optional notes, fixed once recorded.
  p_customer_note text default null,
  p_internal_note text default null
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
    receipt := tcp_private.repeat_payment(p_request_id, 'payment', p_invoice_id, null,
                                     round(p_amount, 2), p_method, p_reference, null,
                                     p_customer_note, p_internal_note, p_paid_on);
    if receipt.id is not null then
      return receipt;
    end if;
    raise exception 'Payments can only be recorded against an issued invoice';
  end if;
  receipt := tcp_private.repeat_payment(p_request_id, 'payment', p_invoice_id, null,
                                   round(p_amount, 2), p_method, p_reference, null,
                                   p_customer_note, p_internal_note, p_paid_on);
  if receipt.id is not null then
    return receipt;
  end if;
  if p_amount is null or round(p_amount, 2) <= 0 then
    raise exception 'A payment must be more than zero';
  end if;
  -- Phase 2, decision 3: money is recorded when it has been received.
  if p_paid_on is null or p_paid_on > current_date then
    raise exception 'A payment date cannot be in the future';
  end if;
  select balance into owed from public.invoice_summary where id = p_invoice_id;
  if round(p_amount, 2) > owed then
    raise exception 'GH₵ % is more than the GH₵ % still owed', round(p_amount, 2), owed;
  end if;
  insert into public.payments (receipt_no, invoice_id, kind, amount, method, reference,
                               paid_on, request_id, balance_after,
                               customer_note, internal_note)
  values (tcp_private.next_number('receipt'), p_invoice_id, 'payment',
          round(p_amount, 2), p_method, nullif(trim(p_reference), ''), p_paid_on,
          p_request_id, owed - round(p_amount, 2),
          nullif(trim(p_customer_note), ''), nullif(trim(p_internal_note), ''))
  returning * into receipt;
  return receipt;
end;
$$;

create function public.refund_payment(
  p_payment_id bigint,
  p_amount     numeric,
  p_method     text,
  p_reason     text,
  p_reference  text default null,
  p_request_id uuid default null,
  -- Phase 2.2: optional notes, fixed once recorded.
  p_customer_note text default null,
  p_internal_note text default null
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
  receipt := tcp_private.repeat_payment(p_request_id, 'refund', orig.invoice_id, orig.id,
                                   -round(p_amount, 2), p_method, p_reference, p_reason,
                                   p_customer_note, p_internal_note);
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
                               paid_on, reverses_payment_id, reason, request_id, balance_after,
                               customer_note, internal_note)
  values (tcp_private.next_number('receipt'), orig.invoice_id, 'refund', -round(p_amount, 2),
          p_method, nullif(trim(p_reference), ''), current_date, orig.id, trim(p_reason),
          p_request_id, owed + round(p_amount, 2),
          nullif(trim(p_customer_note), ''), nullif(trim(p_internal_note), ''))
  returning * into receipt;
  return receipt;
end;
$$;

create function public.correct_payment(
  p_payment_id bigint,
  p_reason     text,
  p_request_id uuid default null,
  -- Phase 2.2: an optional internal note (a correction is never sent to the
  -- customer, so it has no note to the customer).
  p_internal_note text default null
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
  receipt := tcp_private.repeat_payment(p_request_id, 'correction', orig.invoice_id, orig.id,
                                   -orig.amount, orig.method, orig.reference, p_reason,
                                   null, p_internal_note);
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
                               paid_on, reverses_payment_id, reason, request_id, balance_after,
                               internal_note)
  values (tcp_private.next_number('receipt'), orig.invoice_id, 'correction', -orig.amount,
          orig.method, orig.reference, current_date, orig.id, trim(p_reason),
          p_request_id, owed + orig.amount,
          nullif(trim(p_internal_note), ''))
  returning * into receipt;
  return receipt;
end;
$$;

revoke all on function public.record_payment(bigint, numeric, text, text, date, uuid, text, text) from public, anon, authenticated;
revoke all on function public.refund_payment(bigint, numeric, text, text, text, uuid, text, text) from public, anon, authenticated;
revoke all on function public.correct_payment(bigint, text, uuid, text) from public, anon, authenticated;
grant execute on function
  public.record_payment(bigint, numeric, text, text, date, uuid, text, text),
  public.refund_payment(bigint, numeric, text, text, text, uuid, text, text),
  public.correct_payment(bigint, text, uuid, text)
  to authenticated;

-- -----------------------------------------------------------------------------
-- 7. add_invoice_note: an internal note on an invoice (any state), or a
--    correction of a note or of a payment record's internal note.
--    Owner, sales and finance. The same request id with the same details
--    gives back the first note; with any different detail it is refused.
-- -----------------------------------------------------------------------------
create function public.add_invoice_note(
  p_invoice_id          bigint,
  p_body                text,
  p_category            text default null,
  p_corrects_note_id    bigint default null,
  p_corrects_payment_id bigint default null,
  p_request_id          uuid default null,
  p_estimate_ref        text default null
)
returns public.invoice_notes
language plpgsql security definer
set search_path = ''
as $$
declare
  existing public.invoice_notes;
  target   public.invoice_notes;
  pay      public.payments;
  cat      text := p_category;
  who      text;
  note     public.invoice_notes;
begin
  perform tcp_private.require_role('owner', 'sales', 'finance');
  perform tcp_private.request_lock(p_request_id);
  if p_corrects_note_id is not null and p_corrects_payment_id is not null then
    raise exception 'A correction corrects one note';
  end if;
  -- A correction keeps the category of what it corrects, unless one is given;
  -- a payment note's correction is filed as Payment.
  if p_corrects_note_id is not null then
    select * into target from public.invoice_notes where id = p_corrects_note_id;
    if not found or target.invoice_id <> p_invoice_id then
      raise exception 'That note is not on this invoice';
    end if;
    cat := coalesce(cat, target.category);
  elsif p_corrects_payment_id is not null then
    select * into pay from public.payments where id = p_corrects_payment_id;
    if not found or pay.invoice_id <> p_invoice_id then
      raise exception 'That receipt is not on this invoice';
    end if;
    if pay.internal_note is null then
      raise exception 'That receipt has no internal note to correct';
    end if;
    cat := coalesce(cat, 'payment');
  end if;
  cat := coalesce(cat, 'general');
  -- The same request again: the first note, if every detail matches.
  if p_request_id is not null then
    select * into existing from public.invoice_notes where request_id = p_request_id;
    if found then
      if existing.invoice_id is distinct from p_invoice_id
         or existing.body is distinct from trim(p_body)
         or existing.category is distinct from cat
         or existing.corrects_note_id is distinct from p_corrects_note_id
         or existing.corrects_payment_id is distinct from p_corrects_payment_id
         or existing.estimate_ref is distinct from nullif(trim(p_estimate_ref), '') then
        raise exception 'This request id was already used for a different note';
      end if;
      return existing;
    end if;
  end if;
  if not exists (select 1 from public.invoices where id = p_invoice_id) then
    raise exception 'No such invoice';
  end if;
  if p_body is null or length(trim(p_body)) = 0 then
    raise exception 'A note cannot be empty';
  end if;
  if char_length(trim(p_body)) > 1000 then
    raise exception 'A note can be at most 1,000 characters';
  end if;
  if cat not in ('general', 'payment', 'delivery', 'customer_request', 'complaint', 'stock', 'follow_up') then
    raise exception 'Unknown note category: %', cat;
  end if;
  -- Corrections form one line: correct the latest, never an older one.
  if p_corrects_note_id is not null then
    select tcp_private.staff_name(created_by) into who from public.invoice_notes where corrects_note_id = p_corrects_note_id;
  elsif p_corrects_payment_id is not null then
    select tcp_private.staff_name(created_by) into who from public.invoice_notes where corrects_payment_id = p_corrects_payment_id;
  end if;
  if who is not null then
    raise exception 'This note was just corrected by %. Here is the latest; correct that instead.', who;
  end if;
  begin
    insert into public.invoice_notes (invoice_id, body, category, corrects_note_id, corrects_payment_id,
                                      estimate_ref, request_id)
    values (p_invoice_id, trim(p_body), cat, p_corrects_note_id, p_corrects_payment_id,
            nullif(trim(p_estimate_ref), ''), p_request_id)
    returning * into note;
  exception when unique_violation then
    -- Someone else's correction of the same note was saved a moment earlier.
    select tcp_private.staff_name(created_by) into who from public.invoice_notes
     where (p_corrects_note_id is not null and corrects_note_id = p_corrects_note_id)
        or (p_corrects_payment_id is not null and corrects_payment_id = p_corrects_payment_id);
    raise exception 'This note was just corrected by %. Here is the latest; correct that instead.',
      coalesce(who, 'someone else');
  end;
  return note;
end;
$$;
revoke all on function public.add_invoice_note(bigint, text, text, bigint, bigint, uuid, text) from public, anon, authenticated;
grant execute on function public.add_invoice_note(bigint, text, text, bigint, bigint, uuid, text) to authenticated;

-- -----------------------------------------------------------------------------
-- 8. The documents: invoice_document and receipt_document also return the
--    notes (internal ones for the staff screens only; the PDFs print only the
--    notes to the customer). Every earlier field stays.
-- -----------------------------------------------------------------------------
create or replace function public.invoice_document(p_invoice_id bigint)
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
    -- Phase 2.1: when the invoice was cancelled, and by whom (shown on the
    -- cancelled invoice's view and PDF).
    'cancelled_at', inv.cancelled_at,
    'cancelled_by', tcp_private.staff_name(inv.cancelled_by),
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
               'recorded_by', tcp_private.staff_name(pay.recorded_by),
               -- Phase 2: what the payment history needs (all worked out here,
               -- not on the phone).
               'reason', pay.reason,
               'reverses_payment_id', pay.reverses_payment_id,
               'reverses_receipt_no', (select o.receipt_no from public.payments o
                                       where o.id = pay.reverses_payment_id),
               'corrected', (pay.kind = 'payment' and exists (
                               select 1 from public.payments c
                               where c.reverses_payment_id = pay.id and c.kind = 'correction')),
               'refunded', case when pay.kind = 'payment' then coalesce((
                               select -sum(r.amount) from public.payments r
                               where r.reverses_payment_id = pay.id and r.kind = 'refund'), 0)
                           end,
               -- Phase 2.2: the payment's two notes, and the corrections of
               -- its internal note (oldest first; the last is the current one).
               'customer_note', pay.customer_note,
               'internal_note', pay.internal_note,
               'recorded_at', pay.recorded_at,
               'internal_note_chain', tcp_private.note_chain(null, pay.id))
             order by pay.id)
      from public.payments pay where pay.invoice_id = inv.id), '[]'::jsonb),
    -- Phase 2.2: the invoice's internal notes, oldest first, each with what
    -- it corrects and which note corrects it. Staff only; never printed.
    'internal_notes', coalesce((
      select jsonb_agg(jsonb_build_object(
               'id', n.id, 'body', n.body, 'category', n.category,
               'by', tcp_private.staff_name(n.created_by), 'at', n.created_at,
               'estimate_ref', n.estimate_ref,
               'corrects_note_id', n.corrects_note_id,
               'corrects_payment_id', n.corrects_payment_id,
               'corrects_receipt_no', (select p.receipt_no from public.payments p where p.id = n.corrects_payment_id),
               'corrects_kind', (select p.kind from public.payments p where p.id = n.corrects_payment_id),
               'corrected_by_note_id', (select c.id from public.invoice_notes c where c.corrects_note_id = n.id))
             order by n.id)
      from public.invoice_notes n where n.invoice_id = inv.id), '[]'::jsonb)
  );
end;
$$;

create or replace function public.receipt_document(p_payment_id bigint)
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
    'reverses_receipt_no', (select o.receipt_no from public.payments o
                            where o.id = pay.reverses_payment_id),
    'balance_after', pay.balance_after,
    'recorded_by', tcp_private.staff_name(pay.recorded_by),
    -- Phase 2.2: the note printed on the receipt, and the staff-only note
    -- with its corrections (the receipt PDF prints only customer_note).
    'customer_note', pay.customer_note,
    'internal_note', pay.internal_note,
    'recorded_at', pay.recorded_at,
    'internal_note_chain', tcp_private.note_chain(null, pay.id),
    'payments_before', (select count(*) from public.payments
                         where invoice_id = pay.invoice_id and id < pay.id),
    'paid_before', (select coalesce(sum(amount), 0) from public.payments
                     where invoice_id = pay.invoice_id and id < pay.id),
    'invoice', doc - 'payments' - 'paid' - 'balance' - 'status' - 'internal_notes'
  );
end;
$$;

-- -----------------------------------------------------------------------------
-- 9. payment_ledger: as in Phase 2.1, plus the records' notes (searchable
--    from the Payments tab).
-- -----------------------------------------------------------------------------
create or replace view public.payment_ledger
with (security_invoker = true)
as
select
  p.id,
  p.receipt_no,
  p.kind,
  p.amount,
  p.method,
  p.reference,
  p.paid_on,
  p.recorded_at,
  p.reason,
  p.balance_after,
  p.reverses_payment_id,
  o.receipt_no                       as reverses_receipt_no,
  p.invoice_id,
  i.invoice_no,
  i.billed_to_name,
  i.billed_to_phone,
  -- A payment that a correction has reversed: it stays in the list, marked,
  -- but no longer counts as money received.
  (p.kind = 'payment' and exists (
     select 1 from public.payments c
      where c.reverses_payment_id = p.id and c.kind = 'correction')) as corrected,
  -- What the Back Office's search box matches, in lower case. Phones are
  -- stored as +233XXXXXXXXX; the 0XXXXXXXXX form staff type is added so a
  -- number typed either way (or just its last digits) is found.
  lower(concat_ws(' ',
    p.receipt_no, i.invoice_no, i.billed_to_name, p.reference, o.receipt_no,
    i.billed_to_phone,
    case when i.billed_to_phone like '+233%' then '0' || substr(i.billed_to_phone, 5) end,
    -- Phase 2.2: the record's notes are searchable from the Payments tab.
    p.customer_note, p.internal_note
  ))                                 as search_text,
  -- Phase 2.2 (added at the end, as a view's columns must be):
  p.customer_note,
  p.internal_note
from public.payments p
join public.invoices i      on i.id = p.invoice_id
left join public.payments o on o.id = p.reverses_payment_id;

-- -----------------------------------------------------------------------------
-- 10. note_authors(): the staff names for the Notes screen's author filter.
-- -----------------------------------------------------------------------------
create function public.note_authors()
returns jsonb
language plpgsql stable security definer
set search_path = ''
as $$
begin
  perform tcp_private.require_role('owner', 'sales', 'finance');
  return coalesce((select jsonb_agg(jsonb_build_object('id', user_id, 'name', full_name, 'active', active)
                                    order by full_name) from public.staff), '[]'::jsonb);
end;
$$;
revoke all on function public.note_authors() from public, anon, authenticated;
grant execute on function public.note_authors() to authenticated;


-- Helpers for search_notes: the word conditions on one text column
-- (patterns already escaped, put in as quoted literals so the planner sees
-- them), and a time range (whole Ghana days, as instants).
create function tcp_private.notes_words_sql(p_col text, p_pats text[], p_and boolean default false)
returns text
language sql immutable
set search_path = ''
as $$
  select case
    when coalesce(array_length(p_pats, 1), 0) = 0 then case when p_and then '' else 'true' end
    else (case when p_and then 'and ' else '' end)
         || array_to_string(array(select format('%s ilike %L', p_col, pat) from unnest(p_pats) pat), ' and ')
  end;
$$;
create function tcp_private.notes_range_sql(p_col text, p_from timestamptz, p_to timestamptz)
returns text
language sql immutable
set search_path = ''
as $$
  select concat(case when p_from is not null then format(' and %s >= %L::timestamptz', p_col, p_from) end,
                case when p_to   is not null then format(' and %s < %L::timestamptz',  p_col, p_to)   end);
$$;
revoke all on function tcp_private.notes_words_sql(text, text[], boolean) from public, anon, authenticated;
revoke all on function tcp_private.notes_range_sql(text, timestamptz, timestamptz) from public, anon, authenticated;

-- -----------------------------------------------------------------------------
-- 11. search_notes(): every kind of note, searched inside the database.
--   p_words     each word 3 characters or more; every word must appear, in
--               any order, case ignored, matched as plain text.
--   p_category  only categorised notes: invoice notes (their category) and
--               payment, refund and correction notes (always 'payment').
--               Notes to the customer have no category and drop out.
--   p_author    the staff member who wrote it (for a note to the customer:
--               who issued the invoice or recorded the receipt).
--   p_from/to   Ghana days, both included.
--   p_hide_corrected  leave out notes that have a correction.
-- Returns {count, rows}, newest first, a page at a time. Staff only.
-- Each source is filtered on its own columns, so the trigram, time and
-- author indexes can be used; the words are put in as quoted literals.
-- -----------------------------------------------------------------------------
create function public.search_notes(
  p_words          text default null,
  p_category       text default null,
  p_author         uuid default null,
  p_from           date default null,
  p_to             date default null,
  p_hide_corrected boolean default false,
  p_offset         integer default 0,
  p_limit          integer default 30
)
returns jsonb
language plpgsql stable security definer
set search_path = ''
as $$
declare
  words  text[];
  w      text;
  pats   text[] := '{}';
  t_from timestamptz;
  t_to   timestamptz;
  lim    integer := least(greatest(coalesce(p_limit, 30), 1), 100);
  off    integer := greatest(coalesce(p_offset, 0), 0);
  q      text;
  out    jsonb;
  -- The conditions for one source: its text column, time, author.
  conds  text;
begin
  perform tcp_private.require_role('owner', 'sales', 'finance');
  words := array(select x from regexp_split_to_table(coalesce(trim(p_words), ''), '\s+') x where x <> '');
  foreach w in array words loop
    if char_length(w) < 3 then
      raise exception 'Type at least 3 letters or digits for each word';
    end if;
    -- Plain text: \, % and _ lose their special meaning.
    pats := pats || ('%' || replace(replace(replace(w, '\', '\\'), '%', '\%'), '_', '\_') || '%');
  end loop;
  if p_category is not null and p_category not in
     ('general', 'payment', 'delivery', 'customer_request', 'complaint', 'stock', 'follow_up') then
    raise exception 'Unknown note category: %', p_category;
  end if;
  if p_from is not null then t_from := p_from::timestamp at time zone 'Africa/Accra'; end if;
  if p_to   is not null then t_to   := (p_to + 1)::timestamp at time zone 'Africa/Accra'; end if;

  q := format($q$
    with hits as (
      -- a. invoice internal notes (and corrections)
      select 'invoice_note'::text as kind, n.category, n.id as note_id, null::bigint as payment_id,
             n.invoice_id, n.body, n.created_by as author, n.created_at as at,
             n.corrects_note_id, n.corrects_payment_id,
             exists (select 1 from public.invoice_notes c where c.corrects_note_id = n.id) as corrected
        from public.invoice_notes n
       where %1$s %2$s %3$s %4$s %5$s
      union all
      -- b. payment, refund and correction internal notes ('payment')
      select 'payment_note', 'payment', null, p.id, p.invoice_id, p.internal_note, p.recorded_by, p.recorded_at,
             null, null,
             exists (select 1 from public.invoice_notes c where c.corrects_payment_id = p.id)
        from public.payments p
       where p.internal_note is not null %6$s %7$s %8$s %9$s %10$s
      union all
      -- c. notes to the customer on receipts (no category)
      select 'receipt_customer_note', null, null, p.id, p.invoice_id, p.customer_note, p.recorded_by, p.recorded_at,
             null, null, false
        from public.payments p
       where p.customer_note is not null %11$s %7$s %8$s %12$s
      union all
      -- d. notes to the customer on invoices: the note box only, not the
      --    delivery and estimate lines kept in the same column
      select 'invoice_customer_note', null, null, null, i.id, x.body, coalesce(i.issued_by, i.created_by),
             coalesce(i.issued_at, i.created_at), null, null, false
        from public.invoices i
        cross join lateral (select array_to_string(array(
                 select l from unnest(string_to_array(i.notes, E'\n')) l
                  where l not in ('Customer pickup', 'Free delivery')
                    -- only the exact estimate line the Back Office writes
                    -- ("Estimate TCP-261120-MEBLV2"), so a customer's line
                    -- such as "Estimate valid for 7 days" is still found
                    and l !~ '^Estimate TCP-[0-9]{6}-[A-Z0-9]{6}$'), E'\n') as body) x
       where i.notes is not null and x.body <> '' %13$s %14$s %15$s %16$s
    ),
    -- The page first (the count over every match comes with it), then the
    -- details for those 30 rows only.
    page as (
      select h.*, count(*) over () as total
        from hits h
       order by h.at desc, coalesce(h.note_id, h.payment_id) desc
       offset %17$s limit %18$s
    )
    select jsonb_build_object(
             'count', coalesce((select max(total) from page), 0),
             'rows', coalesce(jsonb_agg(jsonb_build_object(
                 'kind', h.kind, 'category', h.category, 'note_id', h.note_id, 'payment_id', h.payment_id,
                 'record_kind', p.kind, 'receipt_no', p.receipt_no,
                 'invoice_id', h.invoice_id, 'invoice_no', i.invoice_no, 'invoice_state', i.state,
                 'customer', coalesce(i.billed_to_name, cu.name), 'status', s.status, 'balance', s.balance,
                 'body', h.body, 'by', tcp_private.staff_name(h.author), 'at', h.at,
                 'corrected', h.corrected,
                 'chain', case when h.corrected then tcp_private.note_chain(h.note_id, case when h.kind = 'payment_note' then h.payment_id end) end,
                 'corrects_note_id', h.corrects_note_id, 'corrects_payment_id', h.corrects_payment_id,
                 'corrects_by', (select tcp_private.staff_name(t.created_by) from public.invoice_notes t where t.id = h.corrects_note_id),
                 'corrects_at', (select t.created_at from public.invoice_notes t where t.id = h.corrects_note_id),
                 'corrects_receipt_no', (select cp.receipt_no from public.payments cp where cp.id = h.corrects_payment_id),
                 'corrects_record_kind', (select cp.kind from public.payments cp where cp.id = h.corrects_payment_id)
               ) order by h.at desc, coalesce(h.note_id, h.payment_id) desc), '[]'::jsonb))
      from page h
      join public.invoices i on i.id = h.invoice_id
      left join public.customers cu on cu.id = i.customer_id
      left join public.invoice_summary s on s.id = h.invoice_id
      left join public.payments p on p.id = h.payment_id
  $q$,
    -- a
    tcp_private.notes_words_sql('n.body', pats),
    case when p_category is not null then format('and n.category = %L', p_category) else '' end,
    tcp_private.notes_range_sql('n.created_at', t_from, t_to),
    case when p_author is not null then format('and n.created_by = %L', p_author) else '' end,
    case when p_hide_corrected then 'and not exists (select 1 from public.invoice_notes c where c.corrects_note_id = n.id)' else '' end,
    -- b
    tcp_private.notes_words_sql('p.internal_note', pats, true),
    tcp_private.notes_range_sql('p.recorded_at', t_from, t_to),
    case when p_author is not null then format('and p.recorded_by = %L', p_author) else '' end,
    case when p_category is not null and p_category <> 'payment' then 'and false' else '' end,
    case when p_hide_corrected then 'and not exists (select 1 from public.invoice_notes c where c.corrects_payment_id = p.id)' else '' end,
    -- c
    tcp_private.notes_words_sql('p.customer_note', pats, true),
    case when p_category is not null then 'and false' else '' end,
    -- d
    tcp_private.notes_words_sql('i.notes', pats, true) || ' ' || tcp_private.notes_words_sql('x.body', pats, true),
    tcp_private.notes_range_sql('coalesce(i.issued_at, i.created_at)', t_from, t_to),
    case when p_author is not null then format('and coalesce(i.issued_by, i.created_by) = %L', p_author) else '' end,
    case when p_category is not null then 'and false' else '' end,
    off, lim);
  execute q into out;
  return out;
end;
$$;
revoke all on function public.search_notes(text, text, uuid, date, date, boolean, integer, integer) from public, anon, authenticated;
grant execute on function public.search_notes(text, text, uuid, date, date, boolean, integer, integer) to authenticated;
