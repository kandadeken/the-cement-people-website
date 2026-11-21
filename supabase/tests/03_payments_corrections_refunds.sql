-- Payments, part payments, overpayment, corrections and refunds.
\set QUIET on

set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';  -- owner
set role authenticated;

select public.create_customer('0241234567', 'Kwame Mensah');
select public.create_draft_invoice(1);
select public.add_invoice_line(1, 'product', 100, (select id from public.products where site_id = 'c3'));  -- 11,000
select public.issue_invoice(1);

-- No payments on a draft.
select public.create_draft_invoice(1);
select public.add_invoice_line(2, 'product', 1, 1);
select tcp_test.fails($$select public.record_payment(2, 10, 'cash')$$, 'issued invoice');

-- Part payment. GH₵6,000 typed by mistake instead of 5,000.
select tcp_test.ok((public.record_payment(1, 6000, 'mobile_money', 'MOMO-123')).receipt_no = 'TCP-RCT-0001', 'first receipt');
select tcp_test.ok((select status from public.invoice_summary where id = 1) = 'part_paid', 'part paid');
select tcp_test.ok((select balance from public.invoice_summary where id = 1) = 5000.00, 'balance 5,000');

-- Overpayment refused, and the refused attempt uses no receipt number.
select tcp_test.fails($$select public.record_payment(1, 5000.01, 'cash')$$, 'more than');
select tcp_test.fails($$select public.record_payment(1, 0, 'cash')$$, 'more than zero');
select tcp_test.fails($$select public.record_payment(1, -5, 'cash')$$, 'more than zero');

-- Correction: undoes the WHOLE wrong payment, with a reason, own receipt number.
select tcp_test.ok((public.correct_payment(1, 'Typed 6,000; customer paid 5,000')).receipt_no = 'TCP-RCT-0002',
                   'correction gets its own receipt number');
select tcp_test.ok((select amount from public.payments where receipt_no = 'TCP-RCT-0002') = -6000.00,
                   'correction is the full negative amount');
select tcp_test.ok((select reverses_payment_id from public.payments where receipt_no = 'TCP-RCT-0002') = 1,
                   'correction points at the original');
select tcp_test.ok((select balance from public.invoice_summary where id = 1) = 11000.00, 'balance back to 11,000');

-- A payment can be corrected only once; corrections can't be corrected.
select tcp_test.fails($$select public.correct_payment(1, 'again')$$, 'already been corrected');
select tcp_test.fails($$select public.correct_payment(2, 'x')$$, 'Only a payment');
-- And a corrected payment can't then be refunded.
select tcp_test.fails($$select public.refund_payment(1, 10, 'cash', 'x')$$, 'was corrected');
-- A reason is required.
reset role;
select tcp_test.fails($$insert into public.payments (receipt_no, invoice_id, kind, amount, method, reverses_payment_id)
                        values ('X', 1, 'refund', -1, 'cash', 1)$$, 'payment_sign_and_link');
set role authenticated;

-- The right amount recorded as a new payment.
select public.record_payment(1, 5000, 'mobile_money', 'MOMO-123');   -- TCP-RCT-0003
select tcp_test.ok((select balance from public.invoice_summary where id = 1) = 6000.00, 'balance 6,000');
select public.record_payment(1, 6000, 'cash');                       -- TCP-RCT-0004
select tcp_test.ok((select status from public.invoice_summary where id = 1) = 'paid', 'paid in full');
select tcp_test.fails($$select public.record_payment(1, 1, 'cash')$$, 'more than');

-- Partial refunds, more than one allowed, never more than the original.
select public.refund_payment((select id from public.payments where receipt_no = 'TCP-RCT-0004'), 1000, 'cash', '10 bags returned');
select public.refund_payment((select id from public.payments where receipt_no = 'TCP-RCT-0004'), 500, 'cash', '5 more bags returned');
select tcp_test.ok((select count(*) from public.payments where reverses_payment_id = (select id from public.payments where receipt_no = 'TCP-RCT-0004') and kind = 'refund') = 2,
                   'two partial refunds');
select tcp_test.fails($$select public.refund_payment((select id from public.payments where receipt_no = 'TCP-RCT-0004'), 4500.01, 'cash', 'too much')$$, 'more than the');
select public.refund_payment((select id from public.payments where receipt_no = 'TCP-RCT-0004'), 4500, 'cash', 'rest returned');      -- exactly the remainder is fine
select tcp_test.ok((select balance from public.invoice_summary where id = 1) = 6000.00, 'balance after refunds');
-- Once refunded, a payment can no longer be corrected.
select tcp_test.fails($$select public.correct_payment((select id from public.payments where receipt_no = 'TCP-RCT-0004'), 'x')$$, 'refunds against it');

-- Receipts are never edited or deleted, even with full database rights.
reset role;
select tcp_test.fails($$update public.payments set amount = 1 where receipt_no = 'TCP-RCT-0003'$$, 'never edited');
select tcp_test.fails($$delete from public.payments where receipt_no = 'TCP-RCT-0003'$$, 'never edited');

-- Receipt numbers ran 0001..0007 with no gaps despite all the refusals.
select tcp_test.ok((select string_agg(receipt_no, ',' order by receipt_no) from public.payments)
  = 'TCP-RCT-0001,TCP-RCT-0002,TCP-RCT-0003,TCP-RCT-0004,TCP-RCT-0005,TCP-RCT-0006,TCP-RCT-0007',
  'receipt numbers gapless');
