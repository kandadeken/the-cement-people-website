-- The audit log: written automatically, with who and what, and untouchable.
\set QUIET on

set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';  -- owner
set role authenticated;

select public.save_product('c1', 'Supacem 32.5R', 'Cement', '50 kg bag', 80);  -- price 75 -> 80
select public.create_customer('0241234567', 'Kwame Mensah');
select public.create_draft_invoice(1);
select public.add_invoice_line(1, 'product', 10, 1);
select public.issue_invoice(1);
select public.record_payment(1, 100, 'cash');
select public.correct_payment(1, 'wrong amount');

-- A price change is logged with who did it and the before and after price.
select tcp_test.ok(exists (
  select 1 from public.audit_log
  where table_name = 'products' and action = 'update'
    and actor = '11111111-1111-1111-1111-111111111111'
    and (before ->> 'current_price')::numeric = 75
    and (after  ->> 'current_price')::numeric = 80), 'price change logged with before/after and actor');

-- Issuing, payment and correction are logged.
select tcp_test.ok(exists (select 1 from public.audit_log where table_name = 'invoices' and action = 'update'
                           and before ->> 'state' = 'draft' and after ->> 'state' = 'issued'), 'issue logged');
select tcp_test.ok((select count(*) from public.audit_log where table_name = 'payments' and action = 'insert') = 2,
                   'payment and correction logged');
select tcp_test.ok(exists (select 1 from public.audit_log where table_name = 'customers' and action = 'insert'),
                   'new customer logged');

-- Nobody can change or delete the log: not the owner through the app...
select tcp_test.fails($$update public.audit_log set actor = null$$, 'permission denied');
select tcp_test.fails($$delete from public.audit_log$$, 'permission denied');
reset role;
-- ...and not even someone with full database rights.
select tcp_test.fails($$update public.audit_log set actor = null$$, 'cannot be edited');
select tcp_test.fails($$delete from public.audit_log$$, 'cannot be edited');
select tcp_test.fails($$truncate public.audit_log$$, 'cannot be edited');

-- A refused action leaves no half-written trace: a refused overpayment adds
-- no payment and no log entry (the whole step is undone together).
set role authenticated;
select count(*) as before_count from public.audit_log \gset
select tcp_test.fails($$select public.record_payment(1, 999999, 'cash')$$, 'more than');
select tcp_test.ok((select count(*) from public.audit_log) = :before_count, 'refused action wrote nothing');
reset role;
