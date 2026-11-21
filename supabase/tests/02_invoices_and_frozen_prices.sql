-- Drafts, issuing, frozen prices and locked invoices.
\set QUIET on

set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';  -- sales
set role authenticated;

select public.create_customer('0241234567', 'Kwame Mensah');
-- Billed to Kwame (abroad), delivered to a site in Kasoa with its own contact.
select public.create_draft_invoice(1, 'Plot 12, Kasoa', 'Yaw (site foreman)', '0559998888', null, 'First order');

-- A draft has no number yet.
select tcp_test.ok((select invoice_no from public.invoices where id = 1) is null, 'draft has no number');
select tcp_test.ok((select deliver_to_phone from public.invoices where id = 1) = '+233559998888',
                   'delivery contact phone stored separately and tidied');

-- Product line: name, unit and today's price are copied from the product.
select public.add_invoice_line(1, 'product', 200, (select id from public.products where site_id = 'c3'));
-- Decimal quantity: 2.5 tons of 16 mm rods.
select public.add_invoice_line(1, 'product', 2.5, (select id from public.products where site_id = 'j1'));
-- Negotiated delivery charge.
select public.add_invoice_line(1, 'delivery', 1, null, 450, 'Delivery to Kasoa', 'trip');
-- Discount (negative).
select public.add_invoice_line(1, 'discount', 1, null, -100, 'Loyal customer discount', 'discount');

select tcp_test.ok((select line_total from public.invoice_lines where invoice_id = 1 and position = 1) = 22000.00,
                   '200 bags x GH₵110 = 22,000');
select tcp_test.ok((select line_total from public.invoice_lines where invoice_id = 1 and position = 2) = 17000.00,
                   '2.5 tons x GH₵6,800 = 17,000');
select tcp_test.ok((select total from public.invoice_summary where id = 1) = 39350.00,
                   'total 22,000 + 17,000 + 450 - 100 = 39,350');

-- A discount must be negative; a product line must point at a product.
select tcp_test.fails($$select public.add_invoice_line(1, 'discount', 1, null, 50, 'Bad', 'x')$$, 'discount_is_negative');
select tcp_test.fails($$select public.add_invoice_line(1, 'product', 1, 999999)$$, 'Unknown product');
select tcp_test.fails($$select public.add_invoice_line(1, 'product', 0, 1)$$, 'quantity');

-- A draft can be edited and lines removed.
select public.add_invoice_line(1, 'product', 10, (select id from public.products where site_id = 'i8'));
select public.remove_invoice_line((select id from public.invoice_lines where invoice_id = 1 and position = 5));
select tcp_test.ok((select count(*) from public.invoice_lines where invoice_id = 1) = 4, 'draft line removed');

-- An empty draft cannot be issued, and the failed attempt uses no number.
select public.create_draft_invoice(1);
select tcp_test.fails($$select public.issue_invoice(2)$$, 'at least one line');

-- Issuing gives the permanent number.
select tcp_test.ok(public.issue_invoice(1) = 'TCP-INV-0001', 'first invoice number, no gap');
select tcp_test.ok((select state from public.invoices where id = 1) = 'issued', 'issued');
select tcp_test.fails($$select public.issue_invoice(1)$$, 'Only a draft');

-- Prices are frozen: the owner changes the cement price afterwards...
reset role;
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';  -- owner
set role authenticated;
select public.save_product('c3', 'Dzata 42.5R Premium', 'Cement', '50 kg bag', 125);
-- ...and the issued invoice still says GH₵110 and the old name.
select tcp_test.ok((select unit_price from public.invoice_lines where invoice_id = 1 and position = 1) = 110.00,
                   'issued line keeps its old price');
select tcp_test.ok((select description from public.invoice_lines where invoice_id = 1 and position = 1) = 'Dzata 42.5R',
                   'issued line keeps its old name');
select tcp_test.ok((select total from public.invoice_summary where id = 1) = 39350.00, 'issued total unchanged');

-- Issued invoices are locked: no new lines, no edits, no deletes...
select tcp_test.fails($$select public.add_invoice_line(1, 'product', 1, 1)$$, 'draft');
select tcp_test.fails($$select public.update_draft_invoice(1, 'x', null, null, null, null)$$, 'Only a draft');
-- ...even for someone writing to the tables directly with full rights.
reset role;
select tcp_test.fails($$update public.invoice_lines set quantity = 1 where invoice_id = 1$$, 'only change while the invoice is a draft');
select tcp_test.fails($$delete from public.invoice_lines where invoice_id = 1$$, 'only change while the invoice is a draft');
select tcp_test.fails($$update public.invoices set due_date = '2030-01-01' where id = 1$$, 'locked');
select tcp_test.fails($$delete from public.invoices where id = 1$$, 'never deleted');

-- The next invoice continues the sequence.
set role authenticated;
select public.add_invoice_line(2, 'product', 1, 1);
select tcp_test.ok(public.issue_invoice(2) = 'TCP-INV-0002', 'second invoice number');
