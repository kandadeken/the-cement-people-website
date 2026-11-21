-- Status calculation (unpaid, part paid, paid, overdue) and exact money.
\set QUIET on

set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';  -- owner
set role authenticated;
select public.create_customer('0241234567', 'Kwame Mensah');

-- Unpaid, due in the future.
select public.create_draft_invoice(1, null, null, null, current_date + 7);
select public.add_invoice_line(1, 'product', 3, (select id from public.products where site_id = 'c1'));  -- 225
select public.issue_invoice(1);
select tcp_test.ok((select status from public.invoice_summary where id = 1) = 'unpaid', 'unpaid');

-- Part paid, due date already passed: overdue, and on the overdue list.
select public.create_draft_invoice(1, null, null, null, current_date - 1);
select public.add_invoice_line(2, 'product', 3, (select id from public.products where site_id = 'c1'));
select public.issue_invoice(2);
select public.record_payment(2, 100, 'cash');
select tcp_test.ok((select status from public.invoice_summary where id = 2) = 'overdue', 'overdue');
select tcp_test.ok((select count(*) from public.overdue_invoices) = 1, 'one overdue invoice');
select tcp_test.ok((select customer_name from public.overdue_invoices) = 'Kwame Mensah', 'overdue list names customer');

-- Paid in full, even past the due date: paid, not overdue.
select public.record_payment(2, 125, 'cash');
select tcp_test.ok((select status from public.invoice_summary where id = 2) = 'paid', 'paid beats overdue');
select tcp_test.ok((select count(*) from public.overdue_invoices) = 0, 'no longer overdue');

-- Exact money: no floating-point drift on awkward amounts.
select public.create_draft_invoice(1);
select public.add_invoice_line(3, 'delivery', 3, null, 33.33, 'Delivery', 'trip');      -- 99.99
select public.add_invoice_line(3, 'delivery', 0.1, null, 0.1, 'Odd', 'unit');           -- 0.01
select public.add_invoice_line(3, 'product', 1234.567, (select id from public.products where site_id = 'j1'));
select tcp_test.ok((select line_total from public.invoice_lines where invoice_id = 3 and position = 3) = 8395055.60,
                   '1,234.567 tons x 6,800 = 8,395,055.60 exactly');
select tcp_test.ok((select total from public.invoice_summary where id = 3) = 8395155.60, 'total exact to the pesewa');

-- Prices and payments are rounded to the pesewa.
select public.add_invoice_line(3, 'delivery', 1, null, 10.005, 'Rounded', 'trip');
select tcp_test.ok((select unit_price from public.invoice_lines where invoice_id = 3 and position = 4) = 10.01,
                   'price rounded to 2 decimals');
select public.issue_invoice(3);
-- A payment that rounds to GH₵0.00 is refused.
select tcp_test.fails($$select public.record_payment(3, 0.004, 'cash')$$, 'more than zero');
select tcp_test.ok((public.record_payment(3, 100.005, 'cash')).amount = 100.01, 'payment rounded to the pesewa');
reset role;
