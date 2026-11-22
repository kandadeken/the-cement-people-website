-- TCP Back Office v1.1: the Home figures (back_office_home).
--   A. Each figure is right for a set of invoices in every status, read as
--      a signed-in sales user (the way the Back Office reads it, through
--      row-level security, not as the database owner).
--   B. Home agrees with the Invoices list: each count equals the rows
--      invoice_list shows for that status, and "owed" equals their balances.
--   C. The same figures for the owner and finance; zeros for someone who is
--      not staff and for a removed staff member; no access at all for the
--      public (anon).
\set QUIET on

-- Every invoice: 10 bags of product 3 (GH₵110 each) = GH₵1,100.
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';  -- sales
set role authenticated;
select (public.create_customer('0241234567', 'Ama Owusu')).id as cust \gset
select public.save_draft_invoice(null, :cust, null, null, null, null, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as draft \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as unpaid \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as partpaid \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as paid \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date - 5, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as overdue \gset
select public.save_draft_invoice(null, :cust, null, null, null, null, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as cancelled_draft \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as cancelled_issued \gset
select public.issue_invoice(:unpaid), public.issue_invoice(:partpaid), public.issue_invoice(:paid),
       public.issue_invoice(:overdue), public.issue_invoice(:cancelled_issued) \gset
reset role;

set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';  -- finance
set role authenticated;
select public.record_payment(:partpaid, 300, 'cash');
select public.record_payment(:paid, 1100, 'mobile_money');
reset role;

set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';  -- owner
set role authenticated;
select public.cancel_invoice(:cancelled_draft, 'Customer bought elsewhere');
select public.cancel_invoice(:cancelled_issued, 'Raised in error');
reset role;

-- ------------------------------------------------ A. the figures (as sales)
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
set role authenticated;
select tcp_test.ok((select owed from public.back_office_home) = 3000.00,
                   'owed = 1,100 unpaid + 800 left on the part paid + 1,100 overdue');
select tcp_test.ok((select unpaid from public.back_office_home) = 1, 'one unpaid');
select tcp_test.ok((select part_paid from public.back_office_home) = 1, 'one part paid');
select tcp_test.ok((select overdue from public.back_office_home) = 1, 'one overdue');
select tcp_test.ok((select drafts from public.back_office_home) = 1, 'one open draft (the cancelled draft is not counted)');
select tcp_test.ok((select count(*) from public.back_office_home) = 1, 'always exactly one row');

-- ------------------------------------------------ B. Home agrees with the list
select tcp_test.ok(
  (select unpaid    from public.back_office_home) = (select count(*) from public.invoice_list where status = 'unpaid') and
  (select part_paid from public.back_office_home) = (select count(*) from public.invoice_list where status = 'part_paid') and
  (select overdue   from public.back_office_home) = (select count(*) from public.invoice_list where status = 'overdue') and
  (select drafts    from public.back_office_home) = (select count(*) from public.invoice_list where status = 'draft'),
  'every count equals the rows the Invoices list shows under that filter');
select tcp_test.ok((select owed from public.back_office_home) =
                   (select sum(balance) from public.invoice_list where status in ('unpaid', 'part_paid', 'overdue')),
                   'owed equals the balances the list shows');
select tcp_test.ok((select count(*) from public.invoice_list where status = 'cancelled') = 2,
                   'both cancelled invoices are in the list (under Cancelled), not owed');
reset role;

-- ------------------------------------------------ C. other roles
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';  -- owner
set role authenticated;
select tcp_test.ok((select owed from public.back_office_home) = 3000.00, 'owner sees the same figures');
reset role;
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';  -- finance
set role authenticated;
select tcp_test.ok((select owed from public.back_office_home) = 3000.00
                   and (select drafts from public.back_office_home) = 1, 'finance sees the same figures');
reset role;
set request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';  -- not staff
set role authenticated;
select tcp_test.ok((select owed = 0 and unpaid = 0 and part_paid = 0 and overdue = 0 and drafts = 0
                    from public.back_office_home), 'someone who is not staff sees only zeros');
reset role;
set request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';  -- removed staff
set role authenticated;
select tcp_test.ok((select owed = 0 and drafts = 0 from public.back_office_home), 'a removed staff member sees only zeros');
reset role;
set role anon;
select tcp_test.fails($$select * from public.back_office_home$$, 'permission denied');
reset role;
