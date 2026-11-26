-- Phase 2.1 (payments ledger and cancelling invoices), the database side:
--   A. One set of records, three sums: the signed ledger sum, every
--      invoice's "paid", and payment_totals('all') agree.
--   B. Period totals: today, yesterday, month and week; corrected payments
--      leave their own day; refunds are money out; corrections move none;
--      method splits add up; the record count includes every kind.
--   C. The day boundary: records dated the day before and the day itself
--      fall on different days; "today" is the Ghana date whatever the
--      session's time zone.
--   D. Who sees what: owner, sales and finance see the ledger and totals;
--      non-staff and retired staff see nothing; the public is refused.
--   E. Search text: a phone typed in the 0..., +233... or last-digits form,
--      and part of a reference, find their records.
--   F. Cancelling: owner only, reason needed, refused while money is held,
--      allowed after a full refund or a correction (with different
--      histories), leaves Owed, and a second cancel is refused.
--   G. (Phase 2.3) A credit note, and its cancellation, change nothing in
--      the ledger or the Payments tab totals: a credit note is not money.
\set QUIET on

-- ------------------------------------------------ the records (as sales)
-- Five invoices of GH₵1,100 each (10 bags of product 3 at GH₵110).
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';  -- sales
set role authenticated;
select (public.create_customer('0241234567', 'Ama Owusu')).id   as ama \gset
select (public.create_customer('0551112222', 'Kofi Mensah')).id as kofi \gset
select public.save_draft_invoice(null, :ama,  null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as inv1 \gset
select public.save_draft_invoice(null, :kofi, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as inv2 \gset
select public.save_draft_invoice(null, :ama,  null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as inv3 \gset
select public.save_draft_invoice(null, :kofi, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as inv4 \gset
select public.save_draft_invoice(null, :kofi, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as inv5 \gset
select public.issue_invoice(:inv1), public.issue_invoice(:inv2), public.issue_invoice(:inv3),
       public.issue_invoice(:inv4), public.issue_invoice(:inv5) \gset
-- D = today. p1 is dated yesterday; p7 the last day of last month.
select (public.record_payment(:inv1,  400, 'mobile_money',  'MP111222333', current_date - 1)).id as p1 \gset
select (public.record_payment(:inv1,  300, 'cash',          null,          current_date)).id     as p2 \gset
select (public.record_payment(:inv2,  500, 'bank_transfer', 'BNK-9',       current_date)).id     as p3 \gset
select (public.record_payment(:inv2,  200, 'mobile_money',  'MP999',       current_date)).id     as p4 \gset
select (public.record_payment(:inv3, 1100, 'cash',          null,          current_date)).id     as p5 \gset
select (public.record_payment(:inv4,  600, 'mobile_money',  'MP600',       current_date)).id     as p6 \gset
select (public.record_payment(:inv2,  100, 'cash',          null,
        (date_trunc('month', current_date) - interval '1 day')::date)).id as p7 \gset
reset role;
-- Finance: p4 corrected, 100 refunded from p1, p5 refunded in full, p6 corrected.
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
set role authenticated;
select (public.correct_payment(:p4, 'Never arrived')).id                     as c4 \gset
select (public.refund_payment(:p1, 100, 'cash', 'Two bags returned')).id     as r1 \gset
select (public.refund_payment(:p5, 1100, 'cash', 'Order called off')).id     as r5 \gset
select (public.correct_payment(:p6, 'Recorded on the wrong invoice')).id     as c6 \gset

-- ------------------------------------------------ A. three sums agree
select public.payment_totals('all') as t_all \gset
select tcp_test.ok((select sum(amount) from public.payment_ledger) = 1200,
                   'the signed ledger sum is 3,200 paid - 800 corrected - 1,200 refunded = 1,200');
select tcp_test.ok((select sum(paid) from public.invoice_summary) = 1200,
                   'the invoices'' paid add up to the same 1,200');
select tcp_test.ok((:'t_all'::jsonb ->> 'net')::numeric = 1200,
                   'payment_totals(all) net is the same 1,200');
select tcp_test.ok((:'t_all'::jsonb -> 'received' ->> 'total')::numeric = 2400
                   and (:'t_all'::jsonb -> 'refunded' ->> 'total')::numeric = 1200,
                   'all time: received 2,400 (corrected payments left out), refunded 1,200');
select tcp_test.ok((select bool_and(s.paid = coalesce((select sum(l.amount) from public.payment_ledger l where l.invoice_id = s.id), 0))
                      from public.invoice_summary s where s.id in (:inv1, :inv2, :inv3, :inv4, :inv5)),
                   'per invoice: paid = the sum of its ledger rows');
select tcp_test.ok((:'t_all'::jsonb ->> 'records')::int = 11 and (:'t_all'::jsonb ->> 'from') is null,
                   'all time: 11 records, no start date');

-- ------------------------------------------------ B. periods
select public.payment_totals('today', current_date) as t_today \gset
select tcp_test.ok((:'t_today'::jsonb -> 'received' ->> 'cash')::numeric = 1400
                   and (:'t_today'::jsonb -> 'received' ->> 'bank_transfer')::numeric = 500
                   and (:'t_today'::jsonb -> 'received' ->> 'mobile_money')::numeric = 0,
                   'today received: cash 300 + 1,100, bank 500; the corrected MoMo payments count nothing');
select tcp_test.ok((:'t_today'::jsonb -> 'refunded' ->> 'cash')::numeric = 1200
                   and (:'t_today'::jsonb -> 'refunded' ->> 'total')::numeric = 1200,
                   'today refunded: 100 + 1,100 cash; corrections are not refunds');
select tcp_test.ok((:'t_today'::jsonb ->> 'net')::numeric = 700, 'today net: 1,900 - 1,200 = 700');
select tcp_test.ok((:'t_today'::jsonb ->> 'records')::int = 9,
                   'today: 9 records (5 payments, 2 corrections, 2 refunds)');
select tcp_test.ok((:'t_today'::jsonb -> 'received' ->> 'total')::numeric
                   = (:'t_today'::jsonb -> 'received' ->> 'mobile_money')::numeric
                   + (:'t_today'::jsonb -> 'received' ->> 'cash')::numeric
                   + (:'t_today'::jsonb -> 'received' ->> 'bank_transfer')::numeric,
                   'received total = MoMo + cash + bank');
select public.payment_totals('today', current_date - 1) as t_yday \gset
select tcp_test.ok((:'t_yday'::jsonb -> 'received' ->> 'mobile_money')::numeric = 400
                   and (:'t_yday'::jsonb ->> 'net')::numeric = 400 and (:'t_yday'::jsonb ->> 'records')::int = 1,
                   'yesterday: only p1 (400 MoMo); its refund today counts today');
select public.payment_totals('month', current_date) as t_month \gset
select tcp_test.ok((:'t_month'::jsonb ->> 'from')::date = date_trunc('month', current_date)::date
                   and (:'t_month'::jsonb ->> 'net')::numeric
                       = 1200 - 100 - case when current_date - 1 < date_trunc('month', current_date) then 400 else 0 end,
                   'this month: all but last month''s 100 (and yesterday''s 400 if yesterday was last month)');
select tcp_test.ok((public.payment_totals('week', current_date) ->> 'from')::date
                   = current_date - (extract(isodow from current_date)::int - 1),
                   'a week starts on Monday');
-- A corrected payment stays in the ledger, marked; so does its correction.
select tcp_test.ok((select corrected from public.payment_ledger where id = :p4)
                   and (select corrected from public.payment_ledger where id = :p6)
                   and not (select corrected from public.payment_ledger where id = :p1),
                   'p4 and p6 are marked corrected; p1 (refunded in part) is not');
select tcp_test.ok((select reverses_receipt_no from public.payment_ledger where id = :c4)
                   = (select receipt_no from public.payments where id = :p4),
                   'a correction names the receipt it reverses');
select tcp_test.fails($$select public.payment_totals('year')$$, 'Unknown period');

-- ------------------------------------------------ C. the day boundary
-- "Today" follows the Ghana date, whatever the session's time zone.
set timezone = 'Pacific/Kiritimati';
select tcp_test.ok((public.payment_totals('today') ->> 'from')::date = (now() at time zone 'Africa/Accra')::date,
                   'today is the Ghana date even in a UTC+14 session');
-- (UTC+14 and UTC-12 together: at any hour one of them is on a different
-- date from Ghana, so a check that used the session's date would fail.)
set timezone = 'Etc/GMT+12';
select tcp_test.ok((public.payment_totals('today') ->> 'from')::date = (now() at time zone 'Africa/Accra')::date,
                   'and in a UTC-12 session');
reset timezone;
reset role;

-- ------------------------------------------------ D. who sees what
create temp table seen (who text, ledger int, totals_ok boolean);
grant all on seen to authenticated, anon;
do $$
declare
  w record;
  ok boolean;
begin
  for w in select * from (values ('owner', '11111111-1111-1111-1111-111111111111'),
                                 ('sales', '22222222-2222-2222-2222-222222222222'),
                                 ('finance', '33333333-3333-3333-3333-333333333333'),
                                 ('stranger', '44444444-4444-4444-4444-444444444444'),
                                 ('retired', '55555555-5555-5555-5555-555555555555')) v(name, sub) loop
    perform set_config('request.jwt.claim.sub', w.sub, true);
    execute 'set local role authenticated';
    begin
      ok := (public.payment_totals('all') ->> 'net')::numeric = 1200;
    exception when others then
      ok := false;
    end;
    insert into seen select w.name, (select count(*) from public.payment_ledger), ok;
    execute 'reset role';
  end loop;
end $$;
select tcp_test.ok((select bool_and(ledger = 11 and totals_ok) from seen where who in ('owner', 'sales', 'finance')),
                   'owner, sales and finance see all 11 ledger rows and the totals');
select tcp_test.ok((select bool_and(ledger = 0 and not totals_ok) from seen where who in ('stranger', 'retired')),
                   'non-staff and retired staff see no rows and are refused the totals');
set request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
set role authenticated;
select tcp_test.fails($$select public.payment_totals('today')$$, 'only TCP staff');
reset role;
set role anon;
select tcp_test.fails($$select id from public.payment_ledger$$, 'permission denied');
select tcp_test.fails($$select public.payment_totals('today')$$, 'permission denied');
reset role;

-- ------------------------------------------------ E. search text
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
set role authenticated;
select tcp_test.ok((select count(*) from public.payment_ledger where search_text like '%0241234567%')
                   = (select count(*) from public.payment_ledger where invoice_id in (:inv1, :inv3)),
                   'the 0... form of Ama''s number finds all her records');
select tcp_test.ok((select count(*) from public.payment_ledger where search_text like '%233241234567%')
                 = (select count(*) from public.payment_ledger where search_text like '%4567%'),
                   'the +233 form and the last 4 digits find the same records');
select tcp_test.ok((select array_agg(id) from public.payment_ledger where search_text like '%mp111%') = array[:p1]::bigint[],
                   'part of a MoMo reference finds its payment');
select tcp_test.ok((select count(*) from public.payment_ledger where search_text like '%kofi%') = 6,
                   'a customer''s name finds their records (p3, p4, p7, c4 on inv2; p6, c6 on inv4)');
reset role;

-- ------------------------------------------------ F. cancelling
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';  -- sales
set role authenticated;
select tcp_test.fails(format($$select public.cancel_invoice(%s, 'test')$$, :inv5), 'sales role cannot');
reset role;
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';  -- finance
set role authenticated;
select tcp_test.fails(format($$select public.cancel_invoice(%s, 'test')$$, :inv5), 'finance role cannot');
reset role;
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';  -- owner
set role authenticated;
select tcp_test.fails(format($$select public.cancel_invoice(%s, '  ')$$, :inv5), 'A reason is needed');
select tcp_test.fails(format($$select public.cancel_invoice(%s, 'test')$$, :inv1), 'still holds');
select public.cancel_invoice(:inv3, 'Order called off, refunded') \gset
select public.cancel_invoice(:inv4, 'Duplicate invoice') \gset
select public.cancel_invoice(:inv5, 'Customer changed their mind') \gset
select tcp_test.fails(format($$select public.cancel_invoice(%s, 'again')$$, :inv5), 'Only a draft or issued');
select tcp_test.ok((select bool_and(state = 'cancelled') from public.invoices where id in (:inv3, :inv4, :inv5)),
                   'the three invoices are cancelled');
select tcp_test.ok((select owed from public.back_office_home) = 1000,
                   'Owed is now only inv1 (500 left) and inv2 (500 left)');
select tcp_test.ok((select array_agg(kind || case when corrected then '*' else '' end order by id)
                      from public.payment_ledger where invoice_id = :inv3) = array['payment', 'refund'],
                   'refunded then cancelled: the history is a payment and a refund');
select tcp_test.ok((select array_agg(kind || case when corrected then '*' else '' end order by id)
                      from public.payment_ledger where invoice_id = :inv4) = array['payment*', 'correction'],
                   'corrected then cancelled: a corrected payment and a correction');
select tcp_test.ok((public.payment_totals('all') ->> 'net')::numeric = 1200,
                   'cancelling changes no money figure');
select tcp_test.ok(coalesce(public.invoice_document(:inv5) ->> 'cancelled_by', '') <> ''
                   -- issued by sales, cancelled by the owner: two different names
                   and public.invoice_document(:inv5) ->> 'cancelled_by' <> public.invoice_document(:inv5) ->> 'issued_by'
                   and (public.invoice_document(:inv5) ->> 'cancelled_at') is not null
                   and public.invoice_document(:inv5) ->> 'cancel_reason' = 'Customer changed their mind',
                   'the invoice document says who cancelled it, when, and why');
select tcp_test.ok((public.invoice_document(:inv1) -> 'cancelled_at') = 'null'::jsonb,
                   'an invoice that is not cancelled has no cancelled date');
reset role;

-- ------------------------------------------------ G. credit notes (Phase 2.3)
-- A credit note is not money: the Payments tab's ledger and every total are
-- exactly the same after one is issued (and after it is cancelled).
create temp table ledger_before as
select (select jsonb_agg(to_jsonb(l) order by l.id) from public.payment_ledger l) as ledger,
       public.payment_totals('all') as t_all, public.payment_totals('today') as t_today,
       public.payment_totals('month') as t_month;
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';  -- owner
set role authenticated;
select public.set_credit_notes_switch(true, 'Ledger test', gen_random_uuid()) \gset
select (public.issue_credit_note(p_invoice_id => :inv1,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":2}]',
                    (select id from public.invoice_lines where invoice_id = :inv1))::jsonb,
  p_reason => 'Two bags returned', p_request_id => gen_random_uuid())).id as cn \gset
reset role;
select tcp_test.ok((select ledger from ledger_before) = (select jsonb_agg(to_jsonb(l) order by l.id) from public.payment_ledger l),
                   'the ledger is unchanged by a credit note');
select tcp_test.ok((select t_all = public.payment_totals('all') and t_today = public.payment_totals('today')
                           and t_month = public.payment_totals('month') from ledger_before),
                   'the Payments tab totals are unchanged by a credit note');
select tcp_test.ok((select balance from public.invoice_summary where id = :inv1) = 280,
                   'but the invoice owes 220 less (500 - 220)');
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
set role authenticated;
select public.cancel_credit_note(:cn, 'Bags were not returned', gen_random_uuid()) \gset
reset role;
select tcp_test.ok((select ledger from ledger_before) = (select jsonb_agg(to_jsonb(l) order by l.id) from public.payment_ledger l)
                   and (select t_all from ledger_before) = public.payment_totals('all'),
                   'and unchanged after the credit note is cancelled');
