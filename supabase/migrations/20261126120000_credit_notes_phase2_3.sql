-- =============================================================================
-- The Cement People: TCP Back Office, Phase 2.3 (credit notes)
--
-- What this file is
--   It follows "TCP Back Office Phase 2.3: Credit Notes Implementation
--   Specification (v1.4)" and "Credit Notes Design (v1.3)", approved by
--   ChatGPT and Daniel on 26 November 2026. It only adds: nothing existing
--   is removed, and no existing figure changes, because no existing invoice
--   has a credit note.
--
--   A credit note is TCP's own numbered document that lowers what an issued
--   invoice is worth. It moves no money (refunds stay refunds) and is never
--   edited or deleted: a wrong one is cancelled by the owner, with a reason,
--   and the cancellation is its own record.
--
-- What it adds
--   1. The counter TCP-CN-0001, and a unique (invoice_id, id) on invoice
--      lines so a credit note line can only point at a line of its own
--      invoice.
--   2. Three append-only tables: credit_notes, credit_note_lines and
--      credit_note_cancellations.
--   3. An activation switch (tcp_private.feature_switches, with its history
--      in tcp_private.feature_switch_changes). It is created OFF: no credit
--      note can be issued, by any route, until the owner switches it on.
--      The switch never stops the owner cancelling a wrong credit note.
--   4. tcp_private.creditable_lines(): each line's value after discounts and
--      what is still left to credit.
--   5. invoice_summary gains "credited"; balance = total - credited - paid;
--      two new statuses, in_credit and credited.
--   6. cancel_invoice is refused while the invoice has an active credit
--      note; invoice_document lists the invoice's credit notes.
--   7. Six new functions: credit_note_options, issue_credit_note,
--      cancel_credit_note, credit_note_document (staff), credit_note_print
--      (the only data the PDF gets) and set_credit_notes_switch.
--   Plus, so nothing else changes by accident:
--   8. receipt_document leaves the two new invoice keys out, so a receipt
--      reads exactly as it did when it was recorded.
--   9. back_office_home gains two columns at the end: the money TCP owes on
--      invoices in credit, and how many there are (decision 1: shown apart
--      from "owed", so a credit never hides a debt).
--
-- Merging this into main deploys it to the tcp-test project only, with the
-- switch off.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. Numbering, and the key credit note lines point at
-- -----------------------------------------------------------------------------
alter table tcp_private.number_counters
  drop constraint number_counters_kind_check,
  add constraint number_counters_kind_check
    check (kind in ('customer', 'invoice', 'receipt', 'credit_note'));
insert into tcp_private.number_counters (kind, prefix) values ('credit_note', 'TCP-CN-');

-- "This line, on this invoice": lets credit_note_lines refer to
-- (invoice_id, invoice_line_id), so a line of another invoice can never be
-- credited, even by a direct insert.
alter table public.invoice_lines
  add constraint invoice_lines_invoice_id_id_key unique (invoice_id, id);


-- -----------------------------------------------------------------------------
-- 2. The credit note tables
-- -----------------------------------------------------------------------------
create table public.credit_notes (
  id                  bigint generated always as identity primary key,
  credit_note_no      text not null unique,
  invoice_id          bigint not null references public.invoices (id),
  -- The Ghana day it was recorded: the date printed on it.
  issued_on           date not null,
  -- The Ghana day from which it counts; earlier only when the owner backdates.
  effective_on        date not null,
  backdate_reason     text,
  -- The overall reason, written for the customer and printed on the PDF.
  reason              text not null,
  customer_note       text,
  internal_note       text,
  amount              numeric(14, 2) not null check (amount > 0),
  -- Snapshots: the invoice's value and amount owed right after this credit
  -- note was recorded, so a reprint always matches the original.
  value_after         numeric(14, 2) not null,
  owed_after          numeric(14, 2) not null,
  recorded_at         timestamptz not null default now(),
  recorded_by         uuid not null,
  request_id          uuid not null unique,
  request_fingerprint text not null,
  constraint credit_notes_id_invoice_key unique (id, invoice_id),
  constraint credit_notes_issued_on_is_ghana_day
    check (issued_on = (recorded_at at time zone 'Africa/Accra')::date),
  constraint credit_notes_effective_not_after_issue check (effective_on <= issued_on),
  constraint credit_notes_backdate_needs_reason
    check ((effective_on <> issued_on) = (backdate_reason is not null and length(trim(backdate_reason)) > 0)),
  constraint credit_notes_reason_length
    check (length(trim(reason)) between 1 and 300),
  constraint credit_notes_customer_note_length
    check (customer_note is null or char_length(customer_note) <= 300),
  constraint credit_notes_internal_note_length
    check (internal_note is null or char_length(internal_note) <= 500)
);
create index credit_notes_invoice_idx on public.credit_notes (invoice_id);
create index credit_notes_effective_idx on public.credit_notes (effective_on);
create index credit_notes_recorded_idx on public.credit_notes (recorded_at);
comment on table public.credit_notes is
  'Credit notes: lower what an issued invoice is worth. Never edited or deleted; cancelled by a separate record.';

create table public.credit_note_lines (
  id              bigint generated always as identity primary key,
  credit_note_id  bigint not null,
  invoice_id      bigint not null,
  -- Null only for the one adjustment line, which belongs to no invoice line.
  invoice_line_id bigint,
  kind            text not null check (kind in ('quantity', 'delivery', 'adjustment')),
  why             text not null,
  -- Units credited; only quantity lines have one (delivery and adjustment
  -- lines are money only).
  quantity        numeric(14, 3),
  -- Worked out by issue_credit_note, never sent by the screen (except the
  -- owner's adjustment amount).
  amount          numeric(14, 2) not null check (amount > 0),
  constraint credit_note_lines_note_fk foreign key (credit_note_id, invoice_id)
    references public.credit_notes (id, invoice_id),
  constraint credit_note_lines_invoice_line_fk foreign key (invoice_id, invoice_line_id)
    references public.invoice_lines (invoice_id, id),
  constraint credit_note_lines_adjustment_has_no_line
    check ((kind = 'adjustment') = (invoice_line_id is null)),
  constraint credit_note_lines_why_matches_kind check (
    (kind = 'quantity'   and why in ('not_supplied', 'returned'))
    or (kind = 'delivery'   and why = 'delivery_not_made')
    or (kind = 'adjustment' and why = 'price_adjustment')),
  constraint credit_note_lines_quantity_only_on_quantity_lines
    check ((kind = 'quantity') = (quantity is not null) and (quantity is null or quantity > 0)),
  constraint credit_note_lines_line_once unique (credit_note_id, invoice_line_id)
);
-- An ordinary unique constraint lets several nulls through, so this index
-- is what allows at most ONE adjustment line per credit note.
create unique index credit_note_lines_one_adjustment
  on public.credit_note_lines (credit_note_id) where invoice_line_id is null;
create index credit_note_lines_invoice_line_idx on public.credit_note_lines (invoice_line_id);
create index credit_note_lines_invoice_idx on public.credit_note_lines (invoice_id);

create table public.credit_note_cancellations (
  id                  bigint generated always as identity primary key,
  credit_note_id      bigint not null unique references public.credit_notes (id),
  -- The Ghana day it was recorded. A cancellation is never backdated.
  cancelled_on        date not null,
  reason              text not null check (length(trim(reason)) between 1 and 300),
  recorded_at         timestamptz not null default now(),
  recorded_by         uuid not null,
  request_id          uuid not null unique,
  request_fingerprint text not null,
  constraint credit_note_cancellations_ghana_day
    check (cancelled_on = (recorded_at at time zone 'Africa/Accra')::date)
);
comment on table public.credit_note_cancellations is
  'One row per cancelled credit note. Never edited or deleted.';

-- A credit note line must match the kind of invoice line it credits: units
-- of a product line, or a delivery line's charge.
create function tcp_private.credit_note_line_kind()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  line_kind text;
begin
  if new.invoice_line_id is not null then
    select kind into line_kind from public.invoice_lines where id = new.invoice_line_id;
    if not ((new.kind = 'quantity' and line_kind = 'product')
            or (new.kind = 'delivery' and line_kind = 'delivery')) then
      raise exception 'A % credit cannot be made on a % line', new.kind, line_kind;
    end if;
  end if;
  return new;
end;
$$;
create trigger credit_note_lines_kind
  before insert on public.credit_note_lines
  for each row execute function tcp_private.credit_note_line_kind();

-- A credit note's amount is exactly the sum of its lines. Checked when the
-- transaction is saved (the note is inserted before its lines), and again
-- if anything ever tried to add a line to a saved credit note.
create function tcp_private.credit_note_total()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  -- (Read through jsonb: the two tables name the credit note differently.)
  cn_id  bigint := case when tg_table_name = 'credit_notes' then (to_jsonb(new) ->> 'id')::bigint
                        else (to_jsonb(new) ->> 'credit_note_id')::bigint end;
  total  numeric;
  lines  numeric;
begin
  select amount into total from public.credit_notes where id = cn_id;
  select coalesce(sum(amount), 0) into lines from public.credit_note_lines where credit_note_id = cn_id;
  if total is distinct from lines then
    raise exception 'A credit note''s amount must equal the sum of its lines' using errcode = '23514';
  end if;
  return null;
end;
$$;
create constraint trigger credit_notes_total
  after insert on public.credit_notes deferrable initially deferred
  for each row execute function tcp_private.credit_note_total();
create constraint trigger credit_note_lines_total
  after insert on public.credit_note_lines deferrable initially deferred
  for each row execute function tcp_private.credit_note_total();

-- Never edited, never deleted, never emptied: a wrong credit note is
-- cancelled instead.
create function tcp_private.guard_credit_notes()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'Credit notes are never edited or deleted; cancel the credit note instead'
    using errcode = '42501';
end;
$$;
create trigger credit_notes_guard before update or delete on public.credit_notes
  for each row execute function tcp_private.guard_credit_notes();
create trigger credit_note_lines_guard before update or delete on public.credit_note_lines
  for each row execute function tcp_private.guard_credit_notes();
create trigger credit_note_cancellations_guard before update or delete on public.credit_note_cancellations
  for each row execute function tcp_private.guard_credit_notes();
create trigger credit_notes_no_truncate before truncate on public.credit_notes
  for each statement execute function tcp_private.guard_credit_notes();
create trigger credit_note_lines_no_truncate before truncate on public.credit_note_lines
  for each statement execute function tcp_private.guard_credit_notes();
create trigger credit_note_cancellations_no_truncate before truncate on public.credit_note_cancellations
  for each statement execute function tcp_private.guard_credit_notes();

-- The same audit log as invoices and payments.
create trigger audit_credit_notes after insert or update or delete on public.credit_notes
  for each row execute function tcp_private.write_audit();
create trigger audit_credit_note_lines after insert or update or delete on public.credit_note_lines
  for each row execute function tcp_private.write_audit();
create trigger audit_credit_note_cancellations after insert or update or delete on public.credit_note_cancellations
  for each row execute function tcp_private.write_audit();

-- Staff read; nobody writes directly (every write goes through the functions).
alter table public.credit_notes              enable row level security;
alter table public.credit_note_lines         enable row level security;
alter table public.credit_note_cancellations enable row level security;
revoke all on public.credit_notes, public.credit_note_lines, public.credit_note_cancellations
  from public, anon, authenticated;
revoke all on sequence public.credit_notes_id_seq, public.credit_note_lines_id_seq,
                       public.credit_note_cancellations_id_seq from public, anon, authenticated;
grant select on public.credit_notes, public.credit_note_lines, public.credit_note_cancellations
  to authenticated;
create policy staff_read on public.credit_notes              for select to authenticated using (tcp_private.is_staff());
create policy staff_read on public.credit_note_lines         for select to authenticated using (tcp_private.is_staff());
create policy staff_read on public.credit_note_cancellations for select to authenticated using (tcp_private.is_staff());


-- -----------------------------------------------------------------------------
-- 3. The activation switch
--    One row, credit_notes, created OFF. Only set_credit_notes_switch (owner)
--    changes it, writing a history row in the same step. No client role can
--    read or write either table directly; staff see the switch through
--    credit_note_options.
-- -----------------------------------------------------------------------------
create table tcp_private.feature_switches (
  name  text primary key,
  is_on boolean not null
);
insert into tcp_private.feature_switches (name, is_on) values ('credit_notes', false);

create table tcp_private.feature_switch_changes (
  id                  bigint generated always as identity primary key,
  name                text not null references tcp_private.feature_switches (name),
  is_on               boolean not null,
  reason              text not null check (length(trim(reason)) between 1 and 300),
  changed_at          timestamptz not null default now(),
  changed_by          uuid not null,
  request_id          uuid not null unique,
  request_fingerprint text not null
);

create function tcp_private.guard_feature_switch_changes()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'The switch history cannot be edited or deleted' using errcode = '42501';
end;
$$;
create trigger feature_switch_changes_guard before update or delete on tcp_private.feature_switch_changes
  for each row execute function tcp_private.guard_feature_switch_changes();
create trigger feature_switch_changes_no_truncate before truncate on tcp_private.feature_switch_changes
  for each statement execute function tcp_private.guard_feature_switch_changes();

create function tcp_private.guard_feature_switches()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'A switch is never removed; turn it off instead' using errcode = '42501';
end;
$$;
create trigger feature_switches_no_delete before delete on tcp_private.feature_switches
  for each row execute function tcp_private.guard_feature_switches();
create trigger feature_switches_no_truncate before truncate on tcp_private.feature_switches
  for each statement execute function tcp_private.guard_feature_switches();

alter table tcp_private.feature_switches       enable row level security;
alter table tcp_private.feature_switch_changes enable row level security;
revoke all on tcp_private.feature_switches, tcp_private.feature_switch_changes
  from public, anon, authenticated;


-- -----------------------------------------------------------------------------
-- 4. What can still be credited, line by line
--    Net value per line: its share of the invoice total after discounts,
--    rounded to the pesewa, with the rounding remainder on the line with the
--    largest gross total (ties: the lowest position), so the net values add
--    up exactly to the invoice total. "Left" is net value and quantity minus
--    what ACTIVE (not cancelled) credit note lines have taken. Adjustment
--    lines belong to no invoice line, so they never use or free a line's
--    value; they count only against the invoice total.
-- -----------------------------------------------------------------------------
create function tcp_private.creditable_lines(p_invoice_id bigint)
returns table (
  invoice_line_id   bigint,
  line_position     integer,
  kind              text,
  description       text,
  unit              text,
  quantity          numeric,
  gross             numeric,
  net_value         numeric,
  credited_quantity numeric,
  credited_value    numeric,
  quantity_left     numeric,
  value_left        numeric
)
language sql stable
set search_path = ''
as $$
  with l as (
    select il.id, il.position, il.kind, il.description, il.unit, il.quantity, il.line_total
      from public.invoice_lines il where il.invoice_id = p_invoice_id
  ), t as (
    select coalesce(sum(line_total) filter (where kind <> 'discount'), 0) as gross_total,
           coalesce(sum(line_total), 0) as invoice_total
      from l
  ), shares as (
    select l.*, t.invoice_total,
           case when t.gross_total = 0 then 0
                else round(l.line_total * t.invoice_total / t.gross_total, 2) end as share,
           row_number() over (order by l.line_total desc, l.position) as size_rank
      from l cross join t
     where l.kind <> 'discount'
  ), net as (
    select s.*,
           s.share + case when s.size_rank = 1 then s.invoice_total - sum(s.share) over () else 0 end as net
      from shares s
  ), used as (
    select cl.invoice_line_id, sum(cl.quantity) as q, sum(cl.amount) as a
      from public.credit_note_lines cl
     where cl.invoice_id = p_invoice_id
       and cl.invoice_line_id is not null
       and not exists (select 1 from public.credit_note_cancellations x
                        where x.credit_note_id = cl.credit_note_id)
     group by cl.invoice_line_id
  )
  select n.id, n.position, n.kind, n.description, n.unit, n.quantity, n.line_total, n.net,
         coalesce(u.q, 0), coalesce(u.a, 0),
         case when n.kind = 'product' then n.quantity - coalesce(u.q, 0) end,
         n.net - coalesce(u.a, 0)
    from net n left join used u on u.invoice_line_id = n.id
   order by n.position
$$;
revoke all on function tcp_private.creditable_lines(bigint) from public, anon, authenticated;


-- -----------------------------------------------------------------------------
-- 5. invoice_summary: "credited" appended; balance and status learn about it
--    credited = the sum of active (not cancelled) credit notes; zero for
--    every existing invoice, so every existing balance and status is the
--    same as before. Statuses, checked in this order (Design v1.3):
--      in_credit  owed below zero: TCP owes the customer
--      credited   credited in full: value zero and no money kept
--      paid       owed zero
--      overdue    owed, past the due date
--      part_paid  owed, some money kept
--      unpaid     owed, no money
--    Every column keeps its name, type and position.
-- -----------------------------------------------------------------------------
create or replace view public.invoice_summary
with (security_invoker = true)
as
select
  i.id,
  i.invoice_no,
  i.customer_id,
  i.state,
  i.issued_at,
  i.due_date,
  coalesce(l.total, 0)::numeric(14, 2)                                                as total,
  coalesce(p.paid, 0)::numeric(14, 2)                                                 as paid,
  (coalesce(l.total, 0) - coalesce(c.credited, 0) - coalesce(p.paid, 0))::numeric(14, 2) as balance,
  case
    when i.state = 'draft'      then 'draft'
    when i.state = 'cancelled'  then 'cancelled'
    when coalesce(l.total, 0) - coalesce(c.credited, 0) - coalesce(p.paid, 0) < 0 then 'in_credit'
    when coalesce(c.credited, 0) > 0
         and coalesce(l.total, 0) - coalesce(c.credited, 0) = 0
         and coalesce(p.paid, 0) = 0 then 'credited'
    when coalesce(p.paid, 0) >= coalesce(l.total, 0) - coalesce(c.credited, 0) then 'paid'
    when i.due_date is not null and i.due_date < current_date then 'overdue'
    when coalesce(p.paid, 0) > 0 then 'part_paid'
    else 'unpaid'
  end as status,
  coalesce(c.credited, 0)::numeric(14, 2)                                             as credited
from public.invoices i
left join (select invoice_id, sum(line_total) as total
             from public.invoice_lines group by invoice_id) l on l.invoice_id = i.id
left join (select invoice_id, sum(amount) as paid
             from public.payments group by invoice_id) p on p.invoice_id = i.id
left join (select cn.invoice_id, sum(cn.amount) as credited
             from public.credit_notes cn
            where not exists (select 1 from public.credit_note_cancellations x
                               where x.credit_note_id = cn.id)
            group by cn.invoice_id) c on c.invoice_id = i.id;
comment on view public.invoice_summary is
  'Totals, credits, balance and status, always calculated, never stored.';

-- Home: "owed" is unchanged (only invoices still owing). What TCP owes on
-- invoices in credit is shown beside it, never netted into it.
create or replace view public.back_office_home
with (security_invoker = true)
as
select
  coalesce(sum(balance) filter (where status in ('unpaid', 'part_paid', 'overdue')), 0)::numeric(14, 2) as owed,
  count(*) filter (where status = 'unpaid')    as unpaid,
  count(*) filter (where status = 'part_paid') as part_paid,
  count(*) filter (where status = 'overdue')   as overdue,
  count(*) filter (where status = 'draft')     as drafts,
  coalesce(-sum(balance) filter (where status = 'in_credit'), 0)::numeric(14, 2) as in_credit,
  count(*) filter (where status = 'in_credit') as in_credit_count
from public.invoice_summary;


-- -----------------------------------------------------------------------------
-- 6. cancel_invoice and the documents
-- -----------------------------------------------------------------------------

-- As before, plus: refused while the invoice has an active credit note.
-- Once every credit note on it is cancelled, the earlier rules apply
-- unchanged; the credit notes and their cancellations stay on record.
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
  if exists (select 1 from public.credit_notes cn
              where cn.invoice_id = p_invoice_id
                and not exists (select 1 from public.credit_note_cancellations x
                                 where x.credit_note_id = cn.id)) then
    raise exception 'This invoice has active credit notes. Cancel them before cancelling the invoice.';
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

-- invoice_document: every earlier key unchanged, plus "credited" and the
-- invoice's credit notes (number, dates, amount, cancelled or not).
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
               'customer_note', pay.customer_note,
               'internal_note', pay.internal_note,
               'recorded_at', pay.recorded_at,
               'internal_note_chain', tcp_private.note_chain(null, pay.id))
             order by pay.id)
      from public.payments pay where pay.invoice_id = inv.id), '[]'::jsonb),
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
      from public.invoice_notes n where n.invoice_id = inv.id), '[]'::jsonb),
    -- Phase 2.3: the sum of active credit notes, and every credit note on
    -- the invoice (cancelled ones included, marked).
    'credited', s.credited,
    'credit_notes', coalesce((
      select jsonb_agg(jsonb_build_object(
               'id', cn.id, 'credit_note_no', cn.credit_note_no,
               'issued_on', cn.issued_on, 'effective_on', cn.effective_on,
               'amount', cn.amount,
               'cancelled', x.id is not null, 'cancelled_on', x.cancelled_on)
             order by cn.id)
      from public.credit_notes cn
      left join public.credit_note_cancellations x on x.credit_note_id = cn.id
      where cn.invoice_id = inv.id), '[]'::jsonb)
  );
end;
$$;

-- receipt_document: exactly as in Phase 2.2, with the two new invoice keys
-- also left out, so a receipt never changes after it is recorded.
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
    'customer_note', pay.customer_note,
    'internal_note', pay.internal_note,
    'recorded_at', pay.recorded_at,
    'internal_note_chain', tcp_private.note_chain(null, pay.id),
    'payments_before', (select count(*) from public.payments
                         where invoice_id = pay.invoice_id and id < pay.id),
    'paid_before', (select coalesce(sum(amount), 0) from public.payments
                     where invoice_id = pay.invoice_id and id < pay.id),
    'invoice', doc - 'payments' - 'paid' - 'balance' - 'status' - 'internal_notes'
                   - 'credited' - 'credit_notes'
  );
end;
$$;


-- -----------------------------------------------------------------------------
-- 7. The functions
-- -----------------------------------------------------------------------------

-- The Ghana day now (Africa/Accra is UTC all year).
create function tcp_private.ghana_today()
returns date
language sql stable
set search_path = ''
as $$ select (now() at time zone 'Africa/Accra')::date $$;
revoke all on function tcp_private.ghana_today() from public, anon, authenticated;

-- The request's fingerprint: a SHA-256 hash of its canonical form, so a
-- retry is recognised whatever order the lines came in, and any real
-- difference is caught. The effective date is kept AS SENT (empty meaning
-- "same as the issue date"), so a genuine retry after midnight still matches.
create function tcp_private.credit_note_fingerprint(
  p_invoice_id bigint, p_lines jsonb, p_reason text, p_customer_note text,
  p_internal_note text, p_effective_on date, p_backdate_reason text)
returns text
language sql immutable
set search_path = ''
as $$
  select encode(sha256(convert_to(jsonb_build_object(
    'invoice_id', p_invoice_id,
    'lines', coalesce((
      select jsonb_agg(jsonb_build_object(
               'invoice_line_id', (e ->> 'invoice_line_id')::bigint,
               'kind', e ->> 'kind',
               'why', e ->> 'why',
               'quantity', trim_scale(round((e ->> 'quantity')::numeric, 3)),
               'amount', case when e ->> 'kind' = 'adjustment'
                              then trim_scale(round((e ->> 'amount')::numeric, 2)) end)
             order by (e ->> 'invoice_line_id')::bigint nulls last, e ->> 'kind', e ->> 'why')
        from jsonb_array_elements(p_lines) e), '[]'::jsonb),
    'reason', coalesce(trim(p_reason), ''),
    'customer_note', coalesce(trim(p_customer_note), ''),
    'internal_note', coalesce(trim(p_internal_note), ''),
    'effective_on', coalesce(p_effective_on::text, ''),
    'backdate_reason', coalesce(trim(p_backdate_reason), ''))::text, 'UTF8')), 'hex')
$$;
revoke all on function tcp_private.credit_note_fingerprint(bigint, jsonb, text, text, text, date, text)
  from public, anon, authenticated;

-- A word for the unit, for messages: "50 kg bag" -> bags, "ton" -> tons.
create function tcp_private.unit_word(p_unit text, p_quantity numeric)
returns text
language sql immutable
set search_path = ''
as $$
  select case when p_quantity = 1 or w like '%s' then w else w || 's' end
    from (select regexp_replace(trim(coalesce(p_unit, 'unit')), '^.*\s', '') as w) x
$$;
revoke all on function tcp_private.unit_word(text, numeric) from public, anon, authenticated;

-- The switch as staff see it (read-only): on or off, and its last change.
create function tcp_private.credit_notes_switch_state()
returns jsonb
language sql stable
set search_path = ''
as $$
  select jsonb_build_object(
    'on', s.is_on,
    'changed_at', c.changed_at,
    'changed_by', tcp_private.staff_name(c.changed_by),
    'reason', c.reason)
    from tcp_private.feature_switches s
    left join lateral (select * from tcp_private.feature_switch_changes ch
                        where ch.name = s.name order by ch.id desc limit 1) c on true
   where s.name = 'credit_notes'
$$;
revoke all on function tcp_private.credit_notes_switch_state() from public, anon, authenticated;


-- credit_note_options: what can still be credited on an invoice (the form
-- previews amounts with it; issue_credit_note always recalculates), and the
-- switch. With no invoice, just the switch (for the owner's switch button).
create function public.credit_note_options(p_invoice_id bigint default null)
returns jsonb
language plpgsql stable security definer
set search_path = ''
as $$
declare
  inv public.invoices;
  s   public.invoice_summary;
begin
  perform tcp_private.require_role('owner', 'sales', 'finance');
  if p_invoice_id is null then
    return jsonb_build_object('switch', tcp_private.credit_notes_switch_state());
  end if;
  select * into inv from public.invoices where id = p_invoice_id;
  if not found then
    raise exception 'No such invoice';
  end if;
  select * into s from public.invoice_summary where id = p_invoice_id;
  return jsonb_build_object(
    'switch', tcp_private.credit_notes_switch_state(),
    'invoice_id', inv.id,
    'invoice_no', inv.invoice_no,
    'state', inv.state,
    'status', s.status,
    'issued_on', (inv.issued_at at time zone 'Africa/Accra')::date,
    'today', tcp_private.ghana_today(),
    'total', s.total,
    'credited', s.credited,
    'value', s.total - s.credited,
    'paid', s.paid,
    'balance', s.balance,
    -- What is left at invoice level (adjustments count here only).
    'invoice_left', s.total - s.credited,
    'lines', coalesce((
      select jsonb_agg(jsonb_build_object(
               'invoice_line_id', c.invoice_line_id, 'position', c.line_position,
               'kind', c.kind, 'description', c.description, 'unit', c.unit,
               'quantity', c.quantity, 'gross', c.gross, 'net_value', c.net_value,
               'credited_quantity', c.credited_quantity, 'credited_value', c.credited_value,
               'quantity_left', c.quantity_left, 'value_left', c.value_left)
             order by c.line_position)
      from tcp_private.creditable_lines(inv.id) c), '[]'::jsonb)
  );
end;
$$;


-- issue_credit_note: owner and finance; an adjustment line or an earlier
-- effective date, owner only. Steps, in this order:
--   1. role  2. request lock and fingerprint (a retry returns the credit
--   note already made, even if the switch has since been turned off)
--   3. the switch, under a SHARED lock held to the end (so a switch-off
--   waits for this credit note, and one switched off first refuses it)
--   4. lock the invoice (credits, payments and cancellations on one invoice
--   are taken one after the other)  5. issued invoices only  6. each line
--   and its amount  7. every cap  8. dates  9. the number  10. save.
--
-- p_lines is a list, each one of:
--   {"invoice_line_id": 12, "kind": "quantity", "why": "returned", "quantity": 10}
--   {"invoice_line_id": 13, "kind": "delivery", "why": "delivery_not_made"}
--   {"kind": "adjustment", "why": "price_adjustment", "amount": 50}   (owner)
create function public.issue_credit_note(
  p_invoice_id      bigint,
  p_lines           jsonb,
  p_reason          text,
  p_customer_note   text default null,
  p_internal_note   text default null,
  p_effective_on    date default null,
  p_backdate_reason text default null,
  p_request_id      uuid default null
)
returns public.credit_notes
language plpgsql security definer
set search_path = ''
as $$
declare
  role_now   text;
  fp         text;
  existing   public.credit_notes;
  switch_on  boolean;
  inv        public.invoices;
  s          public.invoice_summary;
  e          jsonb;
  cl         record;
  q          numeric;
  amt        numeric;
  adj_seen   boolean := false;
  seen       bigint[] := '{}';
  planned    jsonb := '[]'::jsonb;
  new_total  numeric := 0;
  today      date := tcp_private.ghana_today();
  eff        date;
  result     public.credit_notes;
begin
  -- 1. Who
  perform tcp_private.require_role('owner', 'finance');
  role_now := tcp_private.staff_role();
  if p_request_id is null then
    raise exception 'A request id is needed';
  end if;
  if p_lines is null or jsonb_typeof(p_lines) <> 'array' or jsonb_array_length(p_lines) = 0 then
    raise exception 'A credit note needs at least one line';
  end if;
  for e in select * from jsonb_array_elements(p_lines) loop
    if jsonb_typeof(e) <> 'object'
       or coalesce(jsonb_typeof(e -> 'invoice_line_id'), 'null') not in ('number', 'null')
       or coalesce(jsonb_typeof(e -> 'quantity'), 'null') not in ('number', 'null')
       or coalesce(jsonb_typeof(e -> 'amount'), 'null') not in ('number', 'null') then
      raise exception 'A credit note line is not in the right form';
    end if;
  end loop;

  -- 2. A retry of a request already made returns its credit note; the same
  --    request id with any difference is refused.
  perform tcp_private.request_lock(p_request_id);
  fp := tcp_private.credit_note_fingerprint(p_invoice_id, p_lines, p_reason, p_customer_note,
                                            p_internal_note, p_effective_on, p_backdate_reason);
  select * into existing from public.credit_notes where request_id = p_request_id;
  if found then
    if existing.request_fingerprint = fp then
      return existing;
    end if;
    raise exception 'This request id was already used for a different credit note';
  end if;

  -- 3. The switch: a shared lock, held until this credit note is saved.
  select is_on into switch_on from tcp_private.feature_switches
   where name = 'credit_notes' for share;
  if switch_on is not true then
    raise exception 'Credit notes are not switched on';
  end if;

  -- 4 and 5. The invoice, locked; issued invoices only.
  select * into inv from public.invoices where id = p_invoice_id for update;
  if not found then
    raise exception 'No such invoice';
  end if;
  if inv.state <> 'issued' then
    raise exception 'Only an issued invoice can be credited';
  end if;

  -- The overall reason and the notes.
  if p_reason is null or length(trim(p_reason)) = 0 then
    raise exception 'A reason is needed; it is printed on the credit note';
  end if;
  if char_length(trim(p_reason)) > 300 then
    raise exception 'The reason can be at most 300 characters';
  end if;
  if char_length(coalesce(trim(p_customer_note), '')) > 300 then
    raise exception 'The note to the customer can be at most 300 characters';
  end if;
  if char_length(coalesce(trim(p_internal_note), '')) > 500 then
    raise exception 'The internal note can be at most 500 characters';
  end if;

  -- 6. Each line, and its amount (worked out here, never taken from the
  --    screen, except the owner's adjustment amount).
  for e in select * from jsonb_array_elements(p_lines) loop
    if e ->> 'kind' = 'adjustment' then
      if role_now <> 'owner' then
        raise exception 'Only the owner can make an adjustment credit';
      end if;
      if adj_seen then
        raise exception 'A credit note can have only one adjustment line';
      end if;
      adj_seen := true;
      if e ? 'invoice_line_id' and e -> 'invoice_line_id' <> 'null'::jsonb then
        raise exception 'An adjustment credit belongs to no invoice line';
      end if;
      if coalesce(e ->> 'why', '') <> 'price_adjustment' then
        raise exception 'An adjustment credit''s reason must be price_adjustment';
      end if;
      amt := round((e ->> 'amount')::numeric, 2);
      if amt is null or amt <= 0 then
        raise exception 'An adjustment credit must be more than zero';
      end if;
      planned := planned || jsonb_build_array(jsonb_build_object(
                   'invoice_line_id', null, 'kind', 'adjustment', 'why', 'price_adjustment',
                   'quantity', null, 'amount', amt));
      new_total := new_total + amt;
      continue;
    end if;

    if e ->> 'kind' not in ('quantity', 'delivery') or e ->> 'kind' is null then
      raise exception 'A credit note line must be a quantity, delivery or adjustment credit';
    end if;
    select * into cl from tcp_private.creditable_lines(p_invoice_id) c
     where c.invoice_line_id = (e ->> 'invoice_line_id')::bigint;
    if not found then
      raise exception 'That line is not on this invoice';
    end if;
    if cl.invoice_line_id = any (seen) then
      raise exception 'Each invoice line can appear only once in a credit note';
    end if;
    seen := seen || cl.invoice_line_id;

    if e ->> 'kind' = 'quantity' then
      if cl.kind <> 'product' then
        raise exception 'Only a product line can be credited by quantity';
      end if;
      if coalesce(e ->> 'why', '') not in ('not_supplied', 'returned') then
        raise exception 'Say whether the goods were not supplied or returned';
      end if;
      q := round((e ->> 'quantity')::numeric, 3);
      if q is null or q <= 0 then
        raise exception 'The quantity to credit must be more than zero';
      end if;
      if q > cl.quantity_left then
        raise exception 'Only % % are left to credit',
          trim_scale(cl.quantity_left), tcp_private.unit_word(cl.unit, cl.quantity_left);
      end if;
      if cl.value_left <= 0 then
        raise exception 'Only GH₵% of this line is left to credit', greatest(cl.value_left, 0)::numeric(14, 2);
      end if;
      -- The whole quantity left takes exactly the value left (so rounding
      -- never leaves or over-takes a pesewa); otherwise a share, capped.
      if q = cl.quantity_left then
        amt := cl.value_left;
      else
        amt := least(round(q * cl.net_value / cl.quantity, 2), cl.value_left);
      end if;
      if amt <= 0 then
        raise exception 'Only GH₵% of this line is left to credit', greatest(cl.value_left, 0)::numeric(14, 2);
      end if;
      planned := planned || jsonb_build_array(jsonb_build_object(
                   'invoice_line_id', cl.invoice_line_id, 'kind', 'quantity', 'why', e ->> 'why',
                   'quantity', q, 'amount', amt));
    else
      if cl.kind <> 'delivery' then
        raise exception 'Only a delivery line can be credited as a delivery';
      end if;
      if coalesce(e ->> 'why', '') <> 'delivery_not_made' then
        raise exception 'A delivery credit''s reason must be delivery_not_made';
      end if;
      if e ? 'quantity' and e -> 'quantity' <> 'null'::jsonb then
        raise exception 'A delivery credit has no quantity: it credits the whole delivery charge left';
      end if;
      -- Decision 4: a delivery credit takes the whole value left; a part
      -- reduction is an owner adjustment.
      amt := cl.value_left;
      if amt <= 0 then
        raise exception 'Only GH₵% of this line is left to credit', greatest(cl.value_left, 0)::numeric(14, 2);
      end if;
      planned := planned || jsonb_build_array(jsonb_build_object(
                   'invoice_line_id', cl.invoice_line_id, 'kind', 'delivery', 'why', 'delivery_not_made',
                   'quantity', null, 'amount', amt));
    end if;
    new_total := new_total + amt;
  end loop;

  -- 7. The invoice cap: all active credit notes together never more than
  --    the invoice total.
  select * into s from public.invoice_summary where id = p_invoice_id;
  if s.credited + new_total > s.total then
    raise exception 'This would credit more than the invoice is worth';
  end if;

  -- 8. Dates. The issue date is today in Ghana; an earlier effective date
  --    is for the owner only, with a reason; never before the invoice was
  --    issued, never in the future.
  eff := coalesce(p_effective_on, today);
  if eff > today or eff < (inv.issued_at at time zone 'Africa/Accra')::date then
    raise exception 'A credit note cannot take effect before the invoice was issued, or in the future';
  end if;
  if eff <> today and (role_now <> 'owner' or p_backdate_reason is null
                       or length(trim(p_backdate_reason)) = 0) then
    raise exception 'Only the owner can backdate a credit note, and a reason is needed';
  end if;

  -- 9 and 10. The number, then the credit note with its snapshots, then
  -- its lines.
  insert into public.credit_notes (credit_note_no, invoice_id, issued_on, effective_on,
                                   backdate_reason, reason, customer_note, internal_note,
                                   amount, value_after, owed_after, recorded_at, recorded_by,
                                   request_id, request_fingerprint)
  values (tcp_private.next_number('credit_note'), p_invoice_id, today, eff,
          case when eff <> today then trim(p_backdate_reason) end,
          trim(p_reason), nullif(trim(p_customer_note), ''), nullif(trim(p_internal_note), ''),
          new_total, s.total - s.credited - new_total, s.balance - new_total,
          now(), auth.uid(), p_request_id, fp)
  returning * into result;

  insert into public.credit_note_lines (credit_note_id, invoice_id, invoice_line_id, kind, why, quantity, amount)
  select result.id, p_invoice_id, (x ->> 'invoice_line_id')::bigint, x ->> 'kind', x ->> 'why',
         (x ->> 'quantity')::numeric, (x ->> 'amount')::numeric
    from jsonb_array_elements(planned) x;

  return result;
end;
$$;


-- cancel_credit_note: owner only, with a reason. Works whether the switch
-- is on or off (it never reads or locks the switch). Returns the
-- cancellation and the invoice's amount owed afterwards.
create function public.cancel_credit_note(
  p_credit_note_id bigint,
  p_reason         text,
  p_request_id     uuid default null
)
returns jsonb
language plpgsql security definer
set search_path = ''
as $$
declare
  cn       public.credit_notes;
  fp       text;
  existing public.credit_note_cancellations;
  done     public.credit_note_cancellations;
begin
  perform tcp_private.require_role('owner');
  if p_request_id is null then
    raise exception 'A request id is needed';
  end if;
  perform tcp_private.request_lock(p_request_id);
  select * into cn from public.credit_notes where id = p_credit_note_id;
  if not found then
    raise exception 'No such credit note';
  end if;
  perform 1 from public.invoices where id = cn.invoice_id for update;
  fp := encode(sha256(convert_to(jsonb_build_object(
          'credit_note_id', p_credit_note_id, 'reason', coalesce(trim(p_reason), ''))::text, 'UTF8')), 'hex');
  select * into existing from public.credit_note_cancellations where request_id = p_request_id;
  if found then
    if existing.request_fingerprint <> fp then
      raise exception 'This request id was already used for a different cancellation';
    end if;
    done := existing;
  else
    if exists (select 1 from public.credit_note_cancellations where credit_note_id = p_credit_note_id) then
      raise exception 'This credit note is already cancelled';
    end if;
    if p_reason is null or length(trim(p_reason)) = 0 then
      raise exception 'A reason is needed to cancel a credit note';
    end if;
    if char_length(trim(p_reason)) > 300 then
      raise exception 'The reason can be at most 300 characters';
    end if;
    insert into public.credit_note_cancellations (credit_note_id, cancelled_on, reason,
                                                  recorded_at, recorded_by, request_id, request_fingerprint)
    values (p_credit_note_id, tcp_private.ghana_today(), trim(p_reason), now(), auth.uid(),
            p_request_id, fp)
    returning * into done;
  end if;
  return jsonb_build_object(
    'id', done.id,
    'credit_note_id', cn.id,
    'credit_note_no', cn.credit_note_no,
    'invoice_id', cn.invoice_id,
    'cancelled_on', done.cancelled_on,
    'balance', (select balance from public.invoice_summary where id = cn.invoice_id),
    'status', (select status from public.invoice_summary where id = cn.invoice_id));
end;
$$;


-- credit_note_document: the staff view. Everything about the credit note,
-- including the internal note, backdate reason, recorded time and who
-- issued and cancelled it. Never given to the PDF.
create function public.credit_note_document(p_credit_note_id bigint)
returns jsonb
language plpgsql stable security definer
set search_path = ''
as $$
declare
  cn  public.credit_notes;
  inv public.invoices;
  x   public.credit_note_cancellations;
begin
  perform tcp_private.require_role('owner', 'sales', 'finance');
  select * into cn from public.credit_notes where id = p_credit_note_id;
  if not found then
    raise exception 'No such credit note';
  end if;
  select * into inv from public.invoices where id = cn.invoice_id;
  select * into x from public.credit_note_cancellations where credit_note_id = cn.id;
  return jsonb_build_object(
    'id', cn.id,
    'credit_note_no', cn.credit_note_no,
    'invoice_id', inv.id,
    'invoice_no', inv.invoice_no,
    'invoice_issued_on', (inv.issued_at at time zone 'Africa/Accra')::date,
    'billed_to_name', inv.billed_to_name,
    'billed_to_phone', inv.billed_to_phone,
    'issued_on', cn.issued_on,
    'effective_on', cn.effective_on,
    'backdate_reason', cn.backdate_reason,
    'reason', cn.reason,
    'customer_note', cn.customer_note,
    'internal_note', cn.internal_note,
    'amount', cn.amount,
    'value_after', cn.value_after,
    'owed_after', cn.owed_after,
    'recorded_at', cn.recorded_at,
    'recorded_by', tcp_private.staff_name(cn.recorded_by),
    'lines', coalesce((
      select jsonb_agg(jsonb_build_object(
               'kind', l.kind, 'why', l.why, 'quantity', l.quantity, 'amount', l.amount,
               'invoice_line_id', l.invoice_line_id,
               'description', coalesce(il.description, 'Price adjustment'), 'unit', il.unit)
             order by il.position nulls last, l.id)
      from public.credit_note_lines l
      left join public.invoice_lines il on il.id = l.invoice_line_id
      where l.credit_note_id = cn.id), '[]'::jsonb),
    'cancelled', x.id is not null,
    'cancelled_on', x.cancelled_on,
    'cancel_reason', x.reason,
    'cancelled_at', x.recorded_at,
    'cancelled_by', tcp_private.staff_name(x.recorded_by),
    -- The invoice now, for the cancel button's "owed after" preview.
    'invoice_balance', (select balance from public.invoice_summary where id = inv.id),
    'invoice_status', (select status from public.invoice_summary where id = inv.id)
  );
end;
$$;


-- credit_note_print: the ONLY data the credit note PDF and the WhatsApp
-- message are made from. It holds no private field (no internal note, no
-- backdate reason, no staff name, no cancellation reason), so the PDF can
-- never print one by mistake.
create function public.credit_note_print(p_credit_note_id bigint)
returns jsonb
language plpgsql stable security definer
set search_path = ''
as $$
declare
  cn  public.credit_notes;
  inv public.invoices;
  x   public.credit_note_cancellations;
begin
  perform tcp_private.require_role('owner', 'sales', 'finance');
  select * into cn from public.credit_notes where id = p_credit_note_id;
  if not found then
    raise exception 'No such credit note';
  end if;
  select * into inv from public.invoices where id = cn.invoice_id;
  select * into x from public.credit_note_cancellations where credit_note_id = cn.id;
  return jsonb_build_object(
    'credit_note_no', cn.credit_note_no,
    'issued_on', cn.issued_on,
    'effective_on', case when cn.effective_on <> cn.issued_on then cn.effective_on end,
    'invoice_no', inv.invoice_no,
    'invoice_issued_on', (inv.issued_at at time zone 'Africa/Accra')::date,
    'billed_to_name', inv.billed_to_name,
    'billed_to_phone', inv.billed_to_phone,
    'lines', coalesce((
      select jsonb_agg(jsonb_build_object(
               'description', coalesce(il.description, 'Price adjustment'),
               'quantity', l.quantity,
               'unit', il.unit,
               'why', case l.why when 'not_supplied' then 'Not supplied'
                                 when 'returned' then 'Returned'
                                 when 'delivery_not_made' then 'Delivery not made'
                                 else 'Price adjustment' end,
               'amount', l.amount)
             order by il.position nulls last, l.id)
      from public.credit_note_lines l
      left join public.invoice_lines il on il.id = l.invoice_line_id
      where l.credit_note_id = cn.id), '[]'::jsonb),
    'amount', cn.amount,
    'value_before', cn.value_after + cn.amount,
    'value_after', cn.value_after,
    'owed_after', cn.owed_after,
    'reason', cn.reason,
    'customer_note', cn.customer_note,
    'cancelled_on', x.cancelled_on
  );
end;
$$;


-- set_credit_notes_switch: the owner turns credit notes on or off, with a
-- reason. Safe to retry: the same request id with the same state and
-- reason returns the earlier result and changes nothing; with a different
-- state or reason it is refused. Asking for the state the switch already
-- has changes and logs nothing. The switch row is locked EXCLUSIVELY, so a
-- switch-off waits for any credit note being issued (which holds a shared
-- lock on it) and every issue after it is refused.
create function public.set_credit_notes_switch(
  p_on         boolean,
  p_reason     text,
  p_request_id uuid default null
)
returns jsonb
language plpgsql security definer
set search_path = ''
as $$
declare
  fp       text;
  existing tcp_private.feature_switch_changes;
  now_on   boolean;
begin
  perform tcp_private.require_role('owner');
  if p_on is null then
    raise exception 'Say whether credit notes should be on or off';
  end if;
  if p_request_id is null then
    raise exception 'A request id is needed';
  end if;
  if p_reason is null or length(trim(p_reason)) = 0 then
    raise exception 'A reason is needed to switch credit notes on or off';
  end if;
  if char_length(trim(p_reason)) > 300 then
    raise exception 'The reason can be at most 300 characters';
  end if;
  perform tcp_private.request_lock(p_request_id);
  fp := encode(sha256(convert_to(jsonb_build_object(
          'name', 'credit_notes', 'on', p_on, 'reason', trim(p_reason))::text, 'UTF8')), 'hex');
  select * into existing from tcp_private.feature_switch_changes where request_id = p_request_id;
  if found then
    if existing.request_fingerprint <> fp then
      raise exception 'This request id was already used for a different switch change';
    end if;
    return jsonb_build_object('on', existing.is_on, 'changed', true,
                              'message', case when existing.is_on then 'Credit notes are switched on'
                                              else 'Credit notes are switched off' end,
                              'switch', tcp_private.credit_notes_switch_state());
  end if;
  select is_on into now_on from tcp_private.feature_switches where name = 'credit_notes' for update;
  if now_on = p_on then
    return jsonb_build_object('on', now_on, 'changed', false,
                              'message', case when now_on then 'Credit notes are already on'
                                              else 'Credit notes are already off' end,
                              'switch', tcp_private.credit_notes_switch_state());
  end if;
  insert into tcp_private.feature_switch_changes (name, is_on, reason, changed_at, changed_by,
                                                  request_id, request_fingerprint)
  values ('credit_notes', p_on, trim(p_reason), now(), auth.uid(), p_request_id, fp);
  update tcp_private.feature_switches set is_on = p_on where name = 'credit_notes';
  return jsonb_build_object('on', p_on, 'changed', true,
                            'message', case when p_on then 'Credit notes are switched on'
                                            else 'Credit notes are switched off' end,
                            'switch', tcp_private.credit_notes_switch_state());
end;
$$;


-- -----------------------------------------------------------------------------
-- 8. Permissions (the same model as every earlier migration)
--    Staff call the six functions; require_role inside each decides who may
--    do what. The private helpers are granted to no one.
-- -----------------------------------------------------------------------------
revoke all on function tcp_private.credit_note_line_kind() from public, anon, authenticated;
revoke all on function tcp_private.credit_note_total() from public, anon, authenticated;
revoke all on function tcp_private.guard_credit_notes() from public, anon, authenticated;
revoke all on function tcp_private.guard_feature_switch_changes() from public, anon, authenticated;
revoke all on function tcp_private.guard_feature_switches() from public, anon, authenticated;
revoke all on function public.credit_note_options(bigint) from public, anon, authenticated;
revoke all on function public.issue_credit_note(bigint, jsonb, text, text, text, date, text, uuid) from public, anon, authenticated;
revoke all on function public.cancel_credit_note(bigint, text, uuid) from public, anon, authenticated;
revoke all on function public.credit_note_document(bigint) from public, anon, authenticated;
revoke all on function public.credit_note_print(bigint) from public, anon, authenticated;
revoke all on function public.set_credit_notes_switch(boolean, text, uuid) from public, anon, authenticated;

grant execute on function
  public.credit_note_options(bigint),
  public.issue_credit_note(bigint, jsonb, text, text, text, date, text, uuid),
  public.cancel_credit_note(bigint, text, uuid),
  public.credit_note_document(bigint),
  public.credit_note_print(bigint),
  public.set_credit_notes_switch(boolean, text, uuid)
  to authenticated;
