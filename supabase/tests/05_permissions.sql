-- Who can see and do what. These are the checks that protect TCP's records
-- from the public, from logged-in strangers and from the wrong staff role.
\set QUIET on

-- Some records to protect, made by the owner.
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
set role authenticated;
select public.create_customer('0241234567', 'Kwame Mensah');
select public.create_draft_invoice(1);
select public.add_invoice_line(1, 'product', 10, 1);
select public.issue_invoice(1);
select public.record_payment(1, 100, 'cash');
select public.save_product('x1', 'Hidden-price item', 'Aggregates', 'trip', 900, true, false);
select public.save_product('x2', 'Unpublished item', 'Aggregates', 'trip', 500, false, true);
reset role;

-- ---------------------------------------------------------------- the public
set request.jwt.claim.sub = '';
set role anon;
-- Can read the catalogue: published products only, no price where hidden.
select tcp_test.ok((select count(*) from public.public_catalogue) = 18, '17 published products plus x1');
select tcp_test.ok((select price from public.public_catalogue where site_id = 'x1') is null, 'hidden price not shown');
select tcp_test.ok(not exists (select 1 from public.public_catalogue where site_id = 'x2'), 'unpublished not shown');
-- Can read nothing else, and do nothing.
select tcp_test.fails($$select * from public.customers$$, 'permission denied');
select tcp_test.fails($$select * from public.products$$, 'permission denied');
select tcp_test.fails($$select * from public.invoices$$, 'permission denied');
select tcp_test.fails($$select * from public.payments$$, 'permission denied');
select tcp_test.fails($$select * from public.audit_log$$, 'permission denied');
select tcp_test.fails($$select * from public.invoice_summary$$, 'permission denied');
select tcp_test.fails($$select public.create_customer('0201234567', 'x')$$, 'permission denied');
select tcp_test.fails($$select public.record_payment(1, 1, 'cash')$$, 'permission denied');
select tcp_test.fails($$insert into public.customers (code, name) values ('X', 'x')$$, 'permission denied');
reset role;

-- --------------------------------------------- logged in, but not TCP staff
set request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
set role authenticated;
select tcp_test.ok((select count(*) from public.customers) = 0, 'stranger sees no customers');
select tcp_test.ok((select count(*) from public.invoices) = 0, 'stranger sees no invoices');
select tcp_test.ok((select count(*) from public.payments) = 0, 'stranger sees no payments');
select tcp_test.ok((select count(*) from public.invoice_summary) = 0, 'stranger sees no totals');
select tcp_test.ok((select count(*) from public.audit_log) = 0, 'stranger sees no audit log');
select tcp_test.ok((select count(*) from public.customers_with_phone('0241234567')) = 0, 'stranger cannot look up phones');
select tcp_test.fails($$select public.create_customer('0201234567', 'x')$$, 'only TCP staff');
select tcp_test.fails($$select public.record_payment(1, 1, 'cash')$$, 'only TCP staff');
select tcp_test.fails($$select public.save_product('c1', 'x', 'x', 'x', 1)$$, 'only TCP staff');
-- Direct writes are refused even to logged-in users.
select tcp_test.fails($$insert into public.customers (code, name) values ('X', 'x')$$, 'permission denied');
select tcp_test.fails($$update public.products set current_price = 1$$, 'permission denied');
select tcp_test.fails($$insert into public.staff (user_id, full_name, role) values (auth.uid(), 'Me', 'owner')$$,
                      'permission denied');
-- Internal helpers can't be called from outside.
select tcp_test.fails($$select tcp_private.next_number('invoice')$$, 'permission denied');
select tcp_test.fails($$select public.claim_site_publish()$$, 'permission denied');
reset role;

-- ------------------------------------------------- switched-off staff member
set request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
set role authenticated;
select tcp_test.ok((select count(*) from public.customers) = 0, 'inactive staff sees nothing');
select tcp_test.fails($$select public.create_customer('0201234567', 'x')$$, 'only TCP staff');
reset role;

-- ------------------------------------------------------------- sales role
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
set role authenticated;
select tcp_test.ok((select count(*) from public.customers) = 1, 'sales sees customers');
select tcp_test.ok((select count(*) from public.audit_log) = 0, 'sales cannot read the audit log');
select tcp_test.fails($$select public.cancel_invoice(1, 'x')$$, 'sales role cannot');
select tcp_test.fails($$select public.correct_payment(1, 'x')$$, 'sales role cannot');
select tcp_test.fails($$select public.refund_payment(1, 1, 'cash', 'x')$$, 'sales role cannot');
select tcp_test.fails($$select public.merge_customers(1, 1)$$, 'sales role cannot');
select tcp_test.fails($$select public.save_product('c1', 'x', 'x', 'x', 1)$$, 'sales role cannot');
select public.record_payment(1, 50, 'cash');   -- sales may take payments
reset role;

-- ----------------------------------------------------------- finance role
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
set role authenticated;
select tcp_test.fails($$select public.create_customer('0201234567', 'x')$$, 'finance role cannot');
select tcp_test.fails($$select public.create_draft_invoice(1)$$, 'finance role cannot');
select tcp_test.fails($$select public.cancel_invoice(1, 'x')$$, 'finance role cannot');
select public.refund_payment(1, 10, 'cash', 'finance may refund');
reset role;

-- ------------------------------------------------------------------ owner
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
set role authenticated;
select tcp_test.ok((select count(*) from public.audit_log) > 0, 'owner reads the audit log');
select tcp_test.ok((select count(*) from public.staff) = 4, 'owner sees the staff list');
reset role;
