-- =============================================================================
-- Phase 2.3 (credit notes): FULL REMOVAL, prepared in advance (specification
-- v1.4, "Rollback").
--
-- What this file is
--   NOT a migration (it is not in supabase/migrations, so nothing runs it
--   automatically). It undoes 20261126120000_credit_notes_phase2_3.sql and
--   puts back exactly the earlier invoice_summary, back_office_home,
--   cancel_invoice, invoice_document and receipt_document.
--
-- When it may be used
--   ONLY while no credit note exists. Once any credit note exists it is a
--   financial record and is never removed: problems are fixed forward, and
--   the everyday way back is the owner's switch (credit notes off). The
--   first step below refuses to go on if any credit note exists.
--
-- How it is checked
--   Database test 26 applies Phase 2.3, runs this file, and compares every
--   document, balance, status, row and definition with the database before
--   Phase 2.3.
-- =============================================================================
set client_min_messages = warning;
begin;

do $$
begin
  if exists (select 1 from public.credit_notes) then
    raise exception 'Credit notes exist: they are financial records and are never removed. Switch credit notes off instead.';
  end if;
end $$;

-- The new functions and helpers.
drop function public.set_credit_notes_switch(boolean, text, uuid);
drop function public.credit_note_print(bigint);
drop function public.credit_note_document(bigint);
drop function public.cancel_credit_note(bigint, text, uuid);
drop function public.issue_credit_note(bigint, jsonb, text, text, text, date, text, uuid);
drop function public.credit_note_options(bigint);
drop function tcp_private.credit_notes_switch_state();
drop function tcp_private.unit_word(text, numeric);
drop function tcp_private.credit_note_fingerprint(bigint, jsonb, text, text, text, date, text);
drop function tcp_private.ghana_today();

-- invoice_summary loses "credited": a view's column can only be removed by
-- dropping it, which also drops the three views built on it. All four are
-- put back exactly as they were, with their permissions.
drop view public.invoice_summary cascade;   -- also overdue_invoices, invoice_list, back_office_home

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

comment on view public.invoice_summary is 'Totals, balance and status, always calculated, never stored.';

create view public.overdue_invoices
with (security_invoker = true)
as
select s.*, c.code as customer_code, c.name as customer_name, c.phone as customer_phone
from public.invoice_summary s
join public.customers c on c.id = s.customer_id
where s.status = 'overdue';

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

create view public.back_office_home
with (security_invoker = true)
as
select
  -- What customers still owe TCP on issued invoices. Drafts and cancelled
  -- invoices are never owed; a paid invoice has no balance.
  coalesce(sum(balance) filter (where status in ('unpaid', 'part_paid', 'overdue')), 0)::numeric(14, 2) as owed,
  count(*) filter (where status = 'unpaid')    as unpaid,
  count(*) filter (where status = 'part_paid') as part_paid,
  count(*) filter (where status = 'overdue')   as overdue,
  count(*) filter (where status = 'draft')     as drafts
from public.invoice_summary;

comment on view public.back_office_home is
  'The Back Office Home figures, from invoice_summary. Read-only; runs with the caller''s rights.';

revoke all on public.invoice_summary, public.overdue_invoices, public.invoice_list, public.back_office_home
  from public, anon, authenticated;
grant select on public.invoice_summary, public.overdue_invoices, public.invoice_list, public.back_office_home
  to authenticated;

drop function tcp_private.creditable_lines(bigint);

-- cancel_invoice, invoice_document and receipt_document as before Phase 2.3.
create or replace function public.cancel_invoice(p_invoice_id bigint, p_reason text)
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


-- The tables, their triggers and the switch.
drop table public.credit_note_cancellations;
drop table public.credit_note_lines;
drop table public.credit_notes;
drop table tcp_private.feature_switch_changes;
drop table tcp_private.feature_switches;
drop function tcp_private.credit_note_line_kind();
drop function tcp_private.credit_note_total();
drop function tcp_private.guard_credit_notes();
drop function tcp_private.guard_feature_switch_changes();
drop function tcp_private.guard_feature_switches();

alter table public.invoice_lines drop constraint invoice_lines_invoice_id_id_key;
delete from tcp_private.number_counters where kind = 'credit_note';
alter table tcp_private.number_counters
  drop constraint number_counters_kind_check,
  add constraint number_counters_kind_check check (kind in ('customer', 'invoice', 'receipt'));

-- Supabase records applied migrations here; forget Phase 2.3 so it could be
-- applied again later. (Skipped where the table does not exist, as in tests.)
do $$
begin
  if to_regclass('supabase_migrations.schema_migrations') is not null then
    delete from supabase_migrations.schema_migrations where version = '20261126120000';
  end if;
end $$;

commit;
