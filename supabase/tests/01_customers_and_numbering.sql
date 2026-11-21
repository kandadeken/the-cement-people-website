-- Customers, phone numbers and gapless numbering.
\set QUIET on

-- Phone numbers in every common Ghana format end up the same.
select tcp_test.ok(public.normalise_gh_phone('024 123 4567')     = '+233241234567', '0-prefix number');
select tcp_test.ok(public.normalise_gh_phone('+233 24 123 4567') = '+233241234567', '+233 number with spaces');
select tcp_test.ok(public.normalise_gh_phone('233241234567')     = '+233241234567', '233 without plus');
select tcp_test.ok(public.normalise_gh_phone('241234567')        = '+233241234567', 'nine digits');
select tcp_test.ok(public.normalise_gh_phone('')  is null, 'empty phone means no phone');
select tcp_test.fails($$select public.normalise_gh_phone('12345')$$, 'Not a Ghana phone number');

set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';  -- sales
set role authenticated;

-- Codes run in order from 0001.
select tcp_test.ok((public.create_customer('0241234567', 'Kwame Mensah')).code = 'TCP-C-0001', 'first customer code');
select tcp_test.ok((public.create_customer(null, 'Walk-in, paid cash')).code = 'TCP-C-0002', 'name only is fine');
select tcp_test.ok((public.create_customer('0201112222')).code = 'TCP-C-0003', 'phone only is fine');

-- Neither phone nor name: refused, and the refused attempt uses up no number.
select tcp_test.fails($$select public.create_customer(null, '  ')$$, 'customer_needs_phone_or_name');
select tcp_test.ok((public.create_customer(null, 'Ama')).code = 'TCP-C-0004', 'no gap after a refused customer');

-- Shared phone numbers are allowed (families, companies) and can be looked up.
select public.create_customer('+233 24 123 4567', 'Kwame''s brother');
select tcp_test.ok((select count(*) from public.customers_with_phone('0241234567')) = 2,
                   'two customers share one phone number');
select tcp_test.ok((select phone from public.customers where code = 'TCP-C-0001') = '+233241234567',
                   'phone stored in +233 form');

-- Customers are never deleted, even by someone with direct database rights.
reset role;
select tcp_test.fails($$delete from public.customers where code = 'TCP-C-0001'$$, 'never deleted');
