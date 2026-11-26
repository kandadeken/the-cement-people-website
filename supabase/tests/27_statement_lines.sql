-- Phase 2.3: the statement line rules for credit notes (Design v1.3 and the
-- Architecture Note v1.1), worked out as a calculation now so Phase 3's
-- statement function can use them as they are:
--   - a credit note is a line DOWN on its effective date;
--   - a backdated one is marked "entered on" its issue date, because a
--     statement already sent for that earlier period did not show it;
--   - a cancelled credit note keeps its line down on its effective date
--     and gets a line UP on the day it was cancelled (never backdated);
--   - over any period, the lines add up to the change in what is credited.
\set QUIET on

-- The rules, as one query (the shape Phase 3's statement function will
-- take for its credit note lines).
create function pg_temp.credit_lines(p_customer bigint, p_from date, p_to date)
returns table (on_date date, direction text, ref text, amount numeric, entered_on date)
language sql stable as $$
  select cn.effective_on, 'down', cn.credit_note_no, -cn.amount,
         case when cn.issued_on <> cn.effective_on then cn.issued_on end
    from public.credit_notes cn join public.invoices i on i.id = cn.invoice_id
   where i.customer_id = p_customer and cn.effective_on between p_from and p_to
  union all
  select x.cancelled_on, 'up', 'Cancelled ' || cn.credit_note_no, cn.amount, null
    from public.credit_note_cancellations x
    join public.credit_notes cn on cn.id = x.credit_note_id
    join public.invoices i on i.id = cn.invoice_id
   where i.customer_id = p_customer and x.cancelled_on between p_from and p_to
  order by 1, 3
$$;

-- An invoice issued 20 days ago (test only: the issue date is moved back
-- with the guard lifted for that one change).
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
set role authenticated;
select (public.create_customer('0241234567', 'Ama Owusu')).id as cust \gset
select public.save_draft_invoice(null, :cust, null, null, null, null, null,
  '[{"kind":"product","product_id":1,"quantity":10,"unit_price":100}]'::jsonb) as inv \gset
select public.issue_invoice(:inv) \gset
select public.set_credit_notes_switch(true, 'Statement test', gen_random_uuid()) \gset
reset role;
alter table public.invoices disable trigger invoices_guard;
update public.invoices set issued_at = now() - interval '20 days' where id = :inv;
alter table public.invoices enable trigger invoices_guard;
select id as line from public.invoice_lines where invoice_id = :inv \gset

set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
set role authenticated;
-- 1. Today, not backdated.
select (public.issue_credit_note(p_invoice_id => :inv,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', :line)::jsonb,
  p_reason => 'One bag', p_request_id => gen_random_uuid())).id as cn1 \gset
-- 2. Backdated 15 days (falls in the earlier period).
select (public.issue_credit_note(p_invoice_id => :inv,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"not_supplied","quantity":2}]', :line)::jsonb,
  p_reason => 'Two bags short', p_effective_on => current_date - 15, p_backdate_reason => 'Found at stock count',
  p_request_id => gen_random_uuid())).id as cn2 \gset
-- 3. Backdated 12 days, then cancelled today.
select (public.issue_credit_note(p_invoice_id => :inv,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":3}]', :line)::jsonb,
  p_reason => 'Three bags', p_effective_on => current_date - 12, p_backdate_reason => 'Late paperwork',
  p_request_id => gen_random_uuid())).id as cn3 \gset
select public.cancel_credit_note(:cn3, 'Bags were used on site after all', gen_random_uuid()) \gset
reset role;

-- The earlier period (20 to 10 days ago): the two backdated credit notes,
-- each marked "entered on" today; no cancellation line (that is today).
select tcp_test.ok((select string_agg(format('%s %s %s %s', on_date - current_date, direction, amount, entered_on - current_date), ' | ')
                      from pg_temp.credit_lines(:cust, current_date - 20, current_date - 10))
                   = '-15 down -200.00 0 | -12 down -300.00 0',
                   'earlier period: backdated credit notes on their effective dates, marked "entered on" today');
-- This period (9 days ago to today): the credit note made today (not
-- marked) and the cancellation, up, today.
select tcp_test.ok((select string_agg(format('%s %s %s %s', on_date - current_date, direction, amount, coalesce((entered_on - current_date)::text, '-')), ' | ')
                      from pg_temp.credit_lines(:cust, current_date - 9, current_date))
                   = '0 up 300.00 - | 0 down -100.00 -',
                   'this period: today''s credit note, and the cancellation on the day it was cancelled');
-- Over all time, the lines add up to what is credited now.
select tcp_test.ok((select -sum(amount) from pg_temp.credit_lines(:cust, current_date - 365, current_date))
                   = (select credited from public.invoice_summary where id = :inv),
                   'all lines together equal the active credit');
-- A cancellation can never be backdated: it is always dated the day it was recorded.
select tcp_test.ok((select cancelled_on = (recorded_at at time zone 'Africa/Accra')::date from public.credit_note_cancellations
                    where credit_note_id = :cn3), 'the cancellation is dated the day it was recorded');
