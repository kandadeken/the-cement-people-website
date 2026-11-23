-- Phase 2 (payments and receipts), the database side:
--   A. invoice_document's payment history carries reason, the receipt a
--      correction or refund reverses, "corrected" and "refunded".
--   B. receipt_document names the receipt it reverses.
--   C. record_payment refuses a date in the future (decision 3); today and
--      earlier days are fine.
--   D. The functions are still refused to the public and to non-staff, and
--      the phase 1 fields of invoice_document are all still there.
\set QUIET on

-- An issued invoice of GH₵1,100 (10 bags of product 3 at GH₵110), and a
-- second one for the correction.
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';  -- sales
set role authenticated;
select (public.create_customer('0241234567', 'Ama Owusu')).id as cust \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as inv \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as inv2 \gset
select public.issue_invoice(:inv), public.issue_invoice(:inv2) \gset

-- ------------------------------------------------ C. dates (as sales)
select tcp_test.fails(format($$select public.record_payment(%s, 100, 'cash', null, current_date + 1)$$, :inv),
                      'cannot be in the future');
select tcp_test.ok((select count(*) from public.payments) = 0, 'the future-dated payment recorded nothing');
select (public.record_payment(:inv, 400, 'mobile_money', 'MM7712345', current_date - 3)).id as p1 \gset
select tcp_test.ok((select paid_on from public.payments where id = :p1) = current_date - 3, 'an earlier date is fine');
select (public.record_payment(:inv, 300, 'cash', null, current_date)).id as p2 \gset
select (public.record_payment(:inv2, 500, 'bank_transfer', 'BNK-1', current_date)).id as p3 \gset
reset role;

-- Two partial refunds on p1, a correction of p3 (finance).
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
set role authenticated;
select (public.refund_payment(:p1, 100, 'mobile_money', 'Goods returned', 'MM-R1')).id as r1 \gset
select (public.refund_payment(:p1, 50, 'cash', 'Price agreed lower')).id as r2 \gset
select (public.correct_payment(:p3, 'Recorded against the wrong invoice')).id as c1 \gset

-- ------------------------------------------------ A. the history
select public.invoice_document(:inv) as doc \gset
select tcp_test.ok(jsonb_array_length(:'doc'::jsonb -> 'payments') = 4, 'two payments and two refunds listed');
select tcp_test.ok((select (p ->> 'refunded')::numeric from jsonb_array_elements(:'doc'::jsonb -> 'payments') p
                    where (p ->> 'id')::bigint = :p1) = 150, 'p1 shows GH₵150 refunded');
select tcp_test.ok((select (p ->> 'refunded')::numeric from jsonb_array_elements(:'doc'::jsonb -> 'payments') p
                    where (p ->> 'id')::bigint = :p2) = 0, 'p2 shows nothing refunded');
select tcp_test.ok((select bool_and(not (p ->> 'corrected')::boolean) from jsonb_array_elements(:'doc'::jsonb -> 'payments') p
                    where p ->> 'kind' = 'payment'), 'no payment on this invoice is corrected');
select tcp_test.ok((select p ->> 'reverses_receipt_no' from jsonb_array_elements(:'doc'::jsonb -> 'payments') p
                    where (p ->> 'id')::bigint = :r1) = (select receipt_no from public.payments where id = :p1),
                   'a refund names the receipt it reverses');
select tcp_test.ok((select p ->> 'reason' from jsonb_array_elements(:'doc'::jsonb -> 'payments') p
                    where (p ->> 'id')::bigint = :r2) = 'Price agreed lower', 'a refund carries its reason');
select tcp_test.ok((select p -> 'refunded' from jsonb_array_elements(:'doc'::jsonb -> 'payments') p
                    where (p ->> 'id')::bigint = :r1) = 'null'::jsonb, '"refunded" is only given for payments');
select tcp_test.ok((:'doc'::jsonb ->> 'balance')::numeric = 1100 - 700 + 150, 'balance: 1,100 - 700 paid + 150 refunded');

select public.invoice_document(:inv2) as doc2 \gset
select tcp_test.ok((select (p ->> 'corrected')::boolean from jsonb_array_elements(:'doc2'::jsonb -> 'payments') p
                    where (p ->> 'id')::bigint = :p3), 'the corrected payment says so');
select tcp_test.ok((select p ->> 'reverses_receipt_no' from jsonb_array_elements(:'doc2'::jsonb -> 'payments') p
                    where (p ->> 'id')::bigint = :c1) = (select receipt_no from public.payments where id = :p3),
                   'the correction names the receipt it reverses');
select tcp_test.ok((:'doc2'::jsonb ->> 'balance')::numeric = 1100, 'after the correction the whole invoice is owed again');

-- ------------------------------------------------ B. the receipt documents
select tcp_test.ok(public.receipt_document(:r1) ->> 'reverses_receipt_no' = (select receipt_no from public.payments where id = :p1),
                   'refund receipt names the payment receipt');
select tcp_test.ok(public.receipt_document(:p1) -> 'reverses_receipt_no' = 'null'::jsonb, 'a payment receipt reverses nothing');
select tcp_test.ok((public.receipt_document(:p2) ->> 'balance_after')::numeric = 400, 'p2: balance after 1,100 - 400 - 300');
select tcp_test.ok((public.receipt_document(:p2) ->> 'paid_before')::numeric = 400, 'p2: paid before it = 400 (frozen)');
reset role;

-- ------------------------------------------------ D. unchanged rules
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
set role authenticated;
select tcp_test.ok(
  (select bool_and(public.invoice_document(:inv) ? k) from unnest(array[
    'id','invoice_no','state','status','issued_at','issued_by','due_date','notes','cancel_reason','customer_id',
    'customer_code','billed_to_name','billed_to_phone','deliver_to_location','deliver_to_contact',
    'deliver_to_phone','lines','total','paid','balance','payments']) k),
  'every phase 1 field of invoice_document is still there');
reset role;
set request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';  -- not staff
set role authenticated;
select tcp_test.fails(format($$select public.invoice_document(%s)$$, :inv), 'only TCP staff');
select tcp_test.fails(format($$select public.receipt_document(%s)$$, :p1), 'only TCP staff');
select tcp_test.fails(format($$select public.record_payment(%s, 10, 'cash')$$, :inv), 'only TCP staff');
reset role;
set role anon;
select tcp_test.fails(format($$select public.record_payment(%s, 10, 'cash')$$, :inv), 'permission denied');
select tcp_test.fails(format($$select public.invoice_document(%s)$$, :inv), 'permission denied');
reset role;
