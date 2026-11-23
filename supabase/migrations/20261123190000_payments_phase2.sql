-- =============================================================================
-- The Cement People: TCP Back Office, phase 2 (payments and receipts)
--
-- What this file is
--   The fourth migration. It follows "TCP Back Office: Phase 2 Design,
--   Payments and Receipts (v1)" (23 Nov 2026), approved by ChatGPT and
--   Daniel; GitHub issue #39. Only the changes in that design's section 8:
--
--   1. invoice_document: each payment in its history also returns reason,
--      reverses_payment_id, reverses_receipt_no, corrected (true/false) and
--      refunded (GH₵ refunded from it so far). Every existing field stays.
--   2. receipt_document: also returns reverses_receipt_no.
--   3. record_payment: refuses a payment date in the future (decision 3).
--      (refund_payment and correct_payment always use today's date, so
--      they need no change.)
--
--   The three functions keep their names, inputs, permissions and rules;
--   "create or replace" keeps their grants. No table, column, view, policy
--   or permission changes. Nothing existing is altered or deleted.
--
-- Merging this into main deploys it to the tcp-test project only.
-- =============================================================================

-- 1. ---------------------------------------------------------------------------
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


-- 2. ---------------------------------------------------------------------------
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
    'payments_before', (select count(*) from public.payments
                         where invoice_id = pay.invoice_id and id < pay.id),
    'paid_before', (select coalesce(sum(amount), 0) from public.payments
                     where invoice_id = pay.invoice_id and id < pay.id),
    'invoice', doc - 'payments' - 'paid' - 'balance' - 'status'
  );
end;
$$;


-- 3. ---------------------------------------------------------------------------
create or replace function public.record_payment(
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
  -- Phase 2, decision 3: money is recorded when it has been received.
  if p_paid_on is null or p_paid_on > current_date then
    raise exception 'A payment date cannot be in the future';
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
