-- Editing customer details, and refusing zero-value invoices
-- (both added after ChatGPT's review of PR #33).
\set QUIET on

set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';  -- sales
set role authenticated;

select public.create_customer('0241234567', 'Kwame Mensa', 'Kasoa');

-- Correct a misspelt name and a new phone number.
select public.update_customer(1, '020 111 2222', 'Kwame Mensah', 'Kasoa', 'Mason, buys monthly');
select tcp_test.ok((select name from public.customers where id = 1) = 'Kwame Mensah', 'name corrected');
select tcp_test.ok((select phone from public.customers where id = 1) = '+233201112222', 'phone corrected and tidied');
select tcp_test.ok((select code from public.customers where id = 1) = 'TCP-C-0001', 'code unchanged');

-- The rule "phone or name" still holds.
select tcp_test.fails($$select public.update_customer(1, null, ' ', null, null)$$, 'customer_needs_phone_or_name');
select tcp_test.fails($$select public.update_customer(999, '0241234567', 'x', null, null)$$, 'No such customer');

-- The audit log keeps the before and after.
reset role;
select tcp_test.ok(exists (
  select 1 from public.audit_log
  where table_name = 'customers' and action = 'update'
    and before ->> 'name' = 'Kwame Mensa' and after ->> 'name' = 'Kwame Mensah'
    and actor = '22222222-2222-2222-2222-222222222222'), 'edit logged with before/after and who');

-- A code never changes, even with full database rights.
select tcp_test.fails($$update public.customers set code = 'TCP-C-9999' where id = 1$$, 'never changes');

-- Merged records can't be edited.
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';  -- owner
set role authenticated;
select public.create_customer('0241234567', 'K. Mensah');
select public.merge_customers(1, 2);
select tcp_test.fails($$select public.update_customer(2, '0241234567', 'x', null, null)$$, 'merged');
reset role;
select tcp_test.fails($$update public.customers set notes = 'x' where id = 2$$, 'merged customer record cannot be changed');

-- Finance and strangers can't edit customers.
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
set role authenticated;
select tcp_test.fails($$select public.update_customer(1, '0241234567', 'x', null, null)$$, 'finance role cannot');
reset role;
set request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
set role authenticated;
select tcp_test.fails($$select public.update_customer(1, '0241234567', 'x', null, null)$$, 'only TCP staff');
reset role;

-- ------------------------------------------------- zero-value invoices
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
set role authenticated;
select public.create_draft_invoice(1);
select public.add_invoice_line(1, 'product', 1, (select id from public.products where site_id = 'c1'));  -- 75
select public.add_invoice_line(1, 'discount', 1, null, -75, 'Free bag', 'bag');                         -- -75
select tcp_test.fails($$select public.issue_invoice(1)$$, 'more than zero');
-- A discount bigger than the order is refused too.
select public.add_invoice_line(1, 'discount', 1, null, -10, 'Extra', 'bag');
select tcp_test.fails($$select public.issue_invoice(1)$$, 'more than zero');
-- The refusals used up no invoice number.
select public.create_draft_invoice(1);
select public.add_invoice_line(2, 'product', 1, (select id from public.products where site_id = 'c1'));
select tcp_test.ok(public.issue_invoice(2) = 'TCP-INV-0001', 'no number used by refused issues');
reset role;
