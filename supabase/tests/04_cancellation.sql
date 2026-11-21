-- Cancelling invoices: never while money is held, never a hidden refund.
\set QUIET on

set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';  -- owner
set role authenticated;

select public.create_customer('0241234567', 'Kwame Mensah');
select public.create_draft_invoice(1);
select public.add_invoice_line(1, 'product', 10, 1);   -- 10 x 75 = 750
select public.issue_invoice(1);
select public.record_payment(1, 300, 'cash');           -- payment id 1

-- Money is held: cancelling is refused.
select tcp_test.fails($$select public.cancel_invoice(1, 'Customer changed mind')$$, 'still holds');
-- A reason is always needed.
select tcp_test.fails($$select public.cancel_invoice(1, '  ')$$, 'reason');

-- A partial refund still leaves money held.
select public.refund_payment(1, 100, 'cash', 'partial');
select tcp_test.fails($$select public.cancel_invoice(1, 'x')$$, 'still holds');

-- Refund the rest, recorded as its own step. Then cancelling is allowed.
select public.refund_payment(1, 200, 'cash', 'rest');
select public.cancel_invoice(1, 'Customer changed mind');
select tcp_test.ok((select state from public.invoices where id = 1) = 'cancelled', 'cancelled');
select tcp_test.ok((select status from public.invoice_summary where id = 1) = 'cancelled', 'status cancelled');
select tcp_test.ok((select invoice_no from public.invoices where id = 1) = 'TCP-INV-0001', 'keeps its number');
select tcp_test.ok((select cancel_reason from public.invoices where id = 1) = 'Customer changed mind', 'reason kept');
select tcp_test.ok((select cancelled_by from public.invoices where id = 1) = '11111111-1111-1111-1111-111111111111',
                   'who cancelled is kept');

-- Cancelling created no payment rows of its own (no hidden refund).
select tcp_test.ok((select count(*) from public.payments where invoice_id = 1) = 3, 'no extra payment rows');

-- A cancelled invoice is final.
select tcp_test.fails($$select public.cancel_invoice(1, 'again')$$, 'Only a draft or issued');
select tcp_test.fails($$select public.record_payment(1, 10, 'cash')$$, 'issued invoice');
reset role;
select tcp_test.fails($$update public.invoices set state = 'issued' where id = 1$$, 'cannot be changed');

-- The replacement invoice gets the next number.
set role authenticated;
select public.create_draft_invoice(1);
select public.add_invoice_line(2, 'product', 8, 1);
select tcp_test.ok(public.issue_invoice(2) = 'TCP-INV-0002', 'replacement invoice number');

-- A draft can be cancelled too (it never got a number).
select public.create_draft_invoice(1);
select public.cancel_invoice(3, 'Prepared by mistake');
select tcp_test.ok((select state from public.invoices where id = 3) = 'cancelled', 'draft cancelled');

-- After a full correction (a recording mistake), cancelling is allowed too.
select public.record_payment(2, 600, 'cash');            -- payment id 4
select public.correct_payment(4, 'Wrong invoice');
select public.cancel_invoice(2, 'Duplicate invoice');
select tcp_test.ok((select status from public.invoice_summary where id = 2) = 'cancelled', 'cancelled after correction');
