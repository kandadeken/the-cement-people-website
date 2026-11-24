-- =============================================================================
-- The Cement People: TCP Back Office, Phase 2.1 (the payments ledger)
--
-- What this file is
--   It follows "TCP Back Office: Phase 2.1 Design, Payments Ledger and
--   Cancelling Invoices (v1.1)", approved by ChatGPT and Daniel on
--   24 November 2026. It adds one read-only view, one read-only function and
--   one index, and invoice_document gains two fields (cancelled_at and
--   cancelled_by) for the cancelled invoice's view and PDF; every other field
--   stays. No table, column, policy, money function or cancel_invoice
--   changes: cancelling an issued invoice needs no other database change.
--
-- The money rules (design, "Money rules", exact sums)
--   Amounts are stored signed: a payment is +A, its correction -A, a refund -R.
--   For a period of dates:
--     received = sum of A over payments dated in the period with NO correction
--     refunded = sum of R over refunds dated in the period
--     net      = received - refunded
--   A correction moves no money: the corrected payment and its correction are
--   both left out of the money figures (together they sum to zero), but both
--   stay in the ledger. The database already refuses a refund after a
--   correction and a correction after a refund, so nothing counts twice.
--   Over all time: net = the sum of every stored amount = the sum of every
--   invoice's "paid" (invoice_summary). Database test 19 checks all three
--   on the same records.
--
-- "Today" is the date in Ghana (Africa/Accra, UTC), taken by the database,
-- never the phone's clock. Records carry a date, not a time, so the day
-- boundary is the date itself.
--
-- Merging this into main deploys it to the tcp-test project only.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- payment_ledger: one row per payment, correction and refund, with its
-- invoice and customer (as billed), what it reverses, and whether a payment
-- was corrected. Runs with the caller's rights (security_invoker), so the
-- row rules on payments and invoices still apply: staff see every row,
-- anyone else sees none.
-- -----------------------------------------------------------------------------
create view public.payment_ledger
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
    case when i.billed_to_phone like '+233%' then '0' || substr(i.billed_to_phone, 5) end
  ))                                 as search_text
from public.payments p
join public.invoices i      on i.id = p.invoice_id
left join public.payments o on o.id = p.reverses_payment_id;

comment on view public.payment_ledger is
  'Every payment, correction and refund, with its invoice and customer. Read-only; runs with the caller''s rights.';

revoke all on public.payment_ledger from public, anon, authenticated;
grant select on public.payment_ledger to authenticated;

-- The Payments tab lists and sums by date.
create index payments_paid_on_idx on public.payments (paid_on);


-- -----------------------------------------------------------------------------
-- payment_totals(period): the figures at the top of the Payments tab and
-- Home's "Received today". Staff only (owner, sales, finance).
--   p_period: 'today', 'week' (Monday to today), 'month' or 'all'.
--   p_on:     the day taken as "today"; leave it out to use today in Ghana.
--             (Tests fix it; nothing is changed by it.)
-- Returns the period's first and last date (null for 'all') so the list
-- shows exactly the same days, then received, refunded and net, each split
-- by method, and the number of records. Paging the list never changes these.
-- -----------------------------------------------------------------------------
create function public.payment_totals(p_period text, p_on date default null)
returns jsonb
language plpgsql stable security definer
set search_path = ''
as $$
declare
  today  date := coalesce(p_on, (now() at time zone 'Africa/Accra')::date);
  d_from date;
  d_to   date;
  out    jsonb;
begin
  perform tcp_private.require_role('owner', 'sales', 'finance');

  case p_period
    when 'today' then d_from := today; d_to := today;
    when 'week'  then d_from := today - (extract(isodow from today)::int - 1); d_to := today;
    when 'month' then d_from := date_trunc('month', today)::date;               d_to := today;
    when 'all'   then d_from := null;  d_to := null;
    else raise exception 'Unknown period: %', p_period;
  end case;

  with r as (
    select p.kind, p.method, p.amount,
           (p.kind = 'payment' and exists (
              select 1 from public.payments c
               where c.reverses_payment_id = p.id and c.kind = 'correction')) as corrected
      from public.payments p
     where (d_from is null or p.paid_on >= d_from)
       and (d_to   is null or p.paid_on <= d_to)
  ), s as (
    select
      coalesce(sum(amount)  filter (where kind = 'payment' and not corrected and method = 'mobile_money'), 0) as rec_momo,
      coalesce(sum(amount)  filter (where kind = 'payment' and not corrected and method = 'cash'), 0)         as rec_cash,
      coalesce(sum(amount)  filter (where kind = 'payment' and not corrected and method = 'bank_transfer'), 0) as rec_bank,
      coalesce(-sum(amount) filter (where kind = 'refund' and method = 'mobile_money'), 0)  as ref_momo,
      coalesce(-sum(amount) filter (where kind = 'refund' and method = 'cash'), 0)          as ref_cash,
      coalesce(-sum(amount) filter (where kind = 'refund' and method = 'bank_transfer'), 0) as ref_bank,
      count(*) as records
    from r
  )
  select jsonb_build_object(
    'period',   p_period,
    'from',     d_from,
    'to',       d_to,
    'received', jsonb_build_object('mobile_money', rec_momo, 'cash', rec_cash, 'bank_transfer', rec_bank,
                                   'total', rec_momo + rec_cash + rec_bank),
    'refunded', jsonb_build_object('mobile_money', ref_momo, 'cash', ref_cash, 'bank_transfer', ref_bank,
                                   'total', ref_momo + ref_cash + ref_bank),
    'net',      (rec_momo + rec_cash + rec_bank) - (ref_momo + ref_cash + ref_bank),
    'records',  records)
    into out
    from s;
  return out;
end;
$$;

comment on function public.payment_totals(text, date) is
  'Money received, refunded and net for today / week / month / all, split by method. Staff only. Read-only.';

revoke all on function public.payment_totals(text, date) from public, anon, authenticated;
grant execute on function public.payment_totals(text, date) to authenticated;


-- -----------------------------------------------------------------------------
-- invoice_document: as in the Phase 2 migration, plus when the invoice was
-- cancelled and by whom. Same name, input, rights and every earlier field.
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
                           end)
             order by pay.id)
      from public.payments pay where pay.invoice_id = inv.id), '[]'::jsonb)
  );
end;
$$;
