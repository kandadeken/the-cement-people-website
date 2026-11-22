-- After ChatGPT's review of PR #35:
--   A. create_customer with a request id: a retry returns the same customer
--      (also one with no phone number); the same id for a different customer
--      is refused.
--   B. my_staff(): name and role for active staff; refused for anyone else.
--   C. Why the desk needs my_staff(): once someone's access is removed,
--      plain reads come back EMPTY (no error), while every action and
--      document refuses.
\set QUIET on

set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';  -- sales
set role authenticated;

-- ------------------------------------------------ A. customer request ids
select (public.create_customer(null, 'Site foreman Yaw', null, null, 'c0000000-0000-4000-8000-000000000001')).id as yaw \gset
-- The retry (the answer was lost on the way back) gets the same customer.
select tcp_test.ok((public.create_customer(null, 'Site foreman Yaw', null, null, 'c0000000-0000-4000-8000-000000000001')).id = :yaw,
                   'retry returns the same customer (no phone to match on)');
select tcp_test.ok((select count(*) from public.customers) = 1, 'no twin customer');
select tcp_test.ok((select code from public.customers where id = :yaw) = 'TCP-C-0001', 'one code used');
-- Phone written differently on the retry: still the same request.
select (public.create_customer('024 123 4567', 'Ama', null, null, 'c0000000-0000-4000-8000-000000000002')).id as ama \gset
select tcp_test.ok((public.create_customer('+233241234567', ' Ama ', null, null, 'c0000000-0000-4000-8000-000000000002')).id = :ama,
                   'same phone in another format is the same request');
-- The same id for a different customer is refused.
select tcp_test.fails($$select public.create_customer(null, 'Someone else', null, null, 'c0000000-0000-4000-8000-000000000001')$$,
                      'already used for a different customer');
select tcp_test.ok((select count(*) from public.customers) = 2, 'refused attempt added nobody');
-- Without a request id it works as before (each call adds a customer).
select public.create_customer('0201112222', 'Kofi');
select tcp_test.ok((select count(*) from public.customers) = 3, 'no request id: added as before');
-- Codes stayed gapless through the retries and the refusal.
select tcp_test.ok((select string_agg(code, ',' order by id) from public.customers) = 'TCP-C-0001,TCP-C-0002,TCP-C-0003',
                   'customer codes gapless');

-- A draft for the access checks below.
select public.save_draft_invoice(null, :ama, null, null, null, null, null,
  '[{"kind":"product","product_id":3,"quantity":2}]'::jsonb) as draft \gset

-- ------------------------------------------------ B. my_staff
select tcp_test.ok(public.my_staff() ->> 'role' = 'sales', 'sales: my_staff gives the role');
reset role;
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111'; set role authenticated;
select tcp_test.ok(public.my_staff() ->> 'role' = 'owner', 'owner: my_staff gives the role');
reset role;
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333'; set role authenticated;
select tcp_test.ok(public.my_staff() ->> 'role' = 'finance', 'finance: my_staff gives the role');
reset role;
set request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444'; set role authenticated;
select tcp_test.fails($$select public.my_staff()$$, 'only TCP staff');
reset role;

-- ------------------------------------------------ C. a removed staff member
set request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555'; set role authenticated;  -- retired
select tcp_test.fails($$select public.my_staff()$$, 'only TCP staff');
-- Reads come back empty, without an error: this is what the desk must not
-- mistake for "no products" or "new customer".
select tcp_test.ok((select count(*) from public.products) = 0, 'removed staff: products read is empty, not an error');
select tcp_test.ok((select count(*) from public.customers_with_phone('0241234567')) = 0, 'removed staff: phone lookup is empty');
select tcp_test.ok((select count(*) from public.invoice_list) = 0, 'removed staff: invoice list is empty');
select tcp_test.ok((select count(*) from public.staff) = 0 or (select bool_and(not active) from public.staff),
                   'removed staff: sees at most their own inactive row');
-- Every action and document refuses.
select tcp_test.fails(format($$select public.invoice_document(%s)$$, :draft), 'only TCP staff');
select tcp_test.fails($$select public.create_customer('0207778888', 'X', null, null, 'c0000000-0000-4000-8000-000000000009')$$, 'only TCP staff');
select tcp_test.fails(format($$select public.save_draft_invoice(%s, 1, null, null, null, null, null, '[]'::jsonb)$$, :draft), 'only TCP staff');
select tcp_test.fails(format($$select public.issue_invoice(%s)$$, :draft), 'only TCP staff');
reset role;
