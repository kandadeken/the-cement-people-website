-- Invoice Desk phase 1 additions (Design v2.1): frozen "billed to" and
-- issuer, whole-draft saving, request ids, stored balance_after, document
-- functions and the invoice list.
\set QUIET on

set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';  -- sales
set role authenticated;

select public.create_customer('0241234567', 'Kwame Mensah');   -- id 1

-- ------------------------------------------------ save_draft_invoice
-- A whole draft in one step, with a request id.
select public.save_draft_invoice(null, 1, 'Plot 12, Kasoa', 'Yaw', '0559998888', null, null,
  '[{"kind":"product","product_id":3,"quantity":10},
    {"kind":"product","product_id":11,"quantity":2.5,"unit_price":6700},
    {"kind":"delivery","quantity":1,"unit_price":450,"description":"Delivery to Kasoa","unit":"trip"}]'::jsonb,
  'a0000000-0000-4000-8000-000000000001') as draft \gset
select tcp_test.ok((select count(*) from public.invoice_lines where invoice_id = :draft) = 3, 'draft saved with 3 lines');
select tcp_test.ok((select unit_price from public.invoice_lines where invoice_id = :draft and position = 1) = 110.00,
                   'product price copied from the price list');
select tcp_test.ok((select unit_price from public.invoice_lines where invoice_id = :draft and position = 2) = 6700.00,
                   'agreed price kept');
-- A retry of the same new draft (connection dropped) returns the SAME draft.
select tcp_test.ok(public.save_draft_invoice(null, 1, 'Plot 12, Kasoa', 'Yaw', '0559998888', null, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb,
  'a0000000-0000-4000-8000-000000000001') = :draft, 'retry returns the same draft');
select tcp_test.ok((select count(*) from public.invoices) = 1, 'no second draft');
-- Saving again replaces the lines (the retry above saved 1 line).
select tcp_test.ok((select count(*) from public.invoice_lines where invoice_id = :draft) = 1, 'lines replaced');
select public.save_draft_invoice(:draft, 1, 'Plot 12, Kasoa', 'Yaw', '0559998888', null, null,
  '[{"kind":"product","product_id":3,"quantity":10},
    {"kind":"delivery","quantity":1,"unit_price":450,"description":"Delivery to Kasoa","unit":"trip"}]'::jsonb);
select tcp_test.ok((select total from public.invoice_summary where id = :draft) = 1550.00, 'total 1,100 + 450');
-- A bad line refuses the whole save (nothing half-saved).
select tcp_test.fails(format($$select public.save_draft_invoice(%s, 1, null, null, null, null, null,
  '[{"kind":"product","product_id":3,"quantity":5},{"kind":"discount","quantity":1,"unit_price":50,"description":"x","unit":"x"}]'::jsonb)$$, :draft),
  'discount_is_negative');
select tcp_test.ok((select count(*) from public.invoice_lines where invoice_id = :draft) = 2, 'refused save left the draft as it was');

-- ------------------------------------------------ issuing freezes "billed to"
select tcp_test.ok(public.issue_invoice(:draft) = 'TCP-INV-0001', 'issued');
select tcp_test.ok((select billed_to_name from public.invoices where id = :draft) = 'Kwame Mensah', 'name frozen');
select tcp_test.ok((select billed_to_phone from public.invoices where id = :draft) = '+233241234567', 'phone frozen');
select tcp_test.ok((select issued_by from public.invoices where id = :draft) = '22222222-2222-2222-2222-222222222222', 'issuer recorded');
select tcp_test.fails(format($$select public.save_draft_invoice(%s, 1, null, null, null, null, null, '[]'::jsonb)$$, :draft), 'Only a draft');

-- The customer's details are corrected AND a product is renamed and repriced...
select public.update_customer(1, '0201112222', 'Kwame A. Mensah', null, null);
reset role;
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';  -- owner
set role authenticated;
select public.save_product('c3', 'Dzata Premium', 'Cement', '50 kg bag', 140);
-- ...and the invoice document still reads exactly as issued.
select public.invoice_document(:draft) as doc \gset
select tcp_test.ok((:'doc'::jsonb ->> 'billed_to_name') = 'Kwame Mensah', 'document shows the name as issued');
select tcp_test.ok((:'doc'::jsonb ->> 'billed_to_phone') = '+233241234567', 'document shows the phone as issued');
select tcp_test.ok((:'doc'::jsonb -> 'lines' -> 0 ->> 'description') = 'Dzata 42.5R', 'line name as issued');
select tcp_test.ok((:'doc'::jsonb -> 'lines' -> 0 ->> 'unit_price')::numeric = 110, 'line price as issued');
select tcp_test.ok((:'doc'::jsonb ->> 'issued_by') = 'Test Sales', 'issuer name on the document');
select tcp_test.ok((:'doc'::jsonb ->> 'total')::numeric = 1550, 'document total');
-- The frozen fields can't be changed, even with full database rights.
reset role;
select tcp_test.fails(format($$update public.invoices set billed_to_name = 'x' where id = %s$$, :draft), 'locked');
select tcp_test.fails(format($$update public.invoices set issued_by = null where id = %s$$, :draft), 'locked');
set role authenticated;

-- ------------------------------------------------ request ids on payments
select (public.record_payment(:draft, 500, 'mobile_money', 'MOMO-1', current_date,
        'b0000000-0000-4000-8000-000000000001')).id as p1 \gset
-- Exact repeat: the same receipt, no second payment.
select tcp_test.ok((public.record_payment(:draft, 500, 'mobile_money', 'MOMO-1', current_date,
        'b0000000-0000-4000-8000-000000000001')).id = :p1, 'repeat returns the same receipt');
select tcp_test.ok((select count(*) from public.payments) = 1, 'no second payment');
-- Same id, different amount or method: refused.
select tcp_test.fails(format($$select public.record_payment(%s, 600, 'mobile_money', null, current_date, 'b0000000-0000-4000-8000-000000000001')$$, :draft),
                      'already used for a different payment');
select tcp_test.fails(format($$select public.record_payment(%s, 500, 'cash', null, current_date, 'b0000000-0000-4000-8000-000000000001')$$, :draft),
                      'already used for a different payment');
-- Same id used for a refund: refused.
select tcp_test.fails(format($$select public.refund_payment(%s, 10, 'cash', 'x', null, 'b0000000-0000-4000-8000-000000000001')$$, :p1),
                      'already used for a different payment');

-- Refund with a request id: a repeat returns the first refund, never a second.
select (public.refund_payment(:p1, 100, 'cash', '2 bags returned', null,
        'c0000000-0000-4000-8000-000000000001')).id as r1 \gset
select tcp_test.ok((public.refund_payment(:p1, 100, 'cash', '2 bags returned', null,
        'c0000000-0000-4000-8000-000000000001')).id = :r1, 'repeated refund returns the first');
select tcp_test.ok((select count(*) from public.payments where kind = 'refund') = 1, 'only one refund');
select tcp_test.fails(format($$select public.refund_payment(%s, 100, 'cash', 'different reason', null, 'c0000000-0000-4000-8000-000000000001')$$, :p1),
                      'already used for a different payment');
select tcp_test.fails(format($$select public.refund_payment(%s, 50, 'cash', '2 bags returned', null, 'c0000000-0000-4000-8000-000000000001')$$, :p1),
                      'already used for a different payment');

-- Correction with a request id (on a second payment).
select (public.record_payment(:draft, 300, 'cash', null, current_date,
        'b0000000-0000-4000-8000-000000000002')).id as p2 \gset
select (public.correct_payment(:p2, 'Wrong amount', 'd0000000-0000-4000-8000-000000000001')).id as c1 \gset
select tcp_test.ok((public.correct_payment(:p2, 'Wrong amount', 'd0000000-0000-4000-8000-000000000001')).id = :c1,
                   'repeated correction returns the first');
select tcp_test.fails(format($$select public.correct_payment(%s, 'Other reason', 'd0000000-0000-4000-8000-000000000001')$$, :p2),
                      'already used for a different payment');

-- ------------------------------------------------ balance_after is stored
-- Sequence: total 1550. Pay 500 -> 1050. Refund 100 -> 1150. Pay 300 -> 850.
-- Correct the 300 -> 1150.
select tcp_test.ok((select string_agg(receipt_no || '=' || balance_after, ', ' order by id) from public.payments)
  = 'TCP-RCT-0001=1050.00, TCP-RCT-0002=1150.00, TCP-RCT-0003=850.00, TCP-RCT-0004=1150.00',
  'every receipt stored its own balance');
-- A later payment leaves earlier receipts exactly as they were.
select public.record_payment(:draft, 1150, 'bank_transfer', 'GCB-1');
select tcp_test.ok((select balance_after from public.payments where receipt_no = 'TCP-RCT-0001') = 1050.00,
                   'first receipt still shows 1,050 after later receipts');
select tcp_test.ok((select balance_after from public.payments where receipt_no = 'TCP-RCT-0005') = 0.00, 'paid in full');
reset role;
select tcp_test.fails($$update public.payments set balance_after = 0$$, 'never edited');
set role authenticated;

-- ------------------------------------------------ receipt_document
select public.receipt_document(:p1) as rdoc \gset
select tcp_test.ok((:'rdoc'::jsonb ->> 'receipt_no') = 'TCP-RCT-0001', 'receipt number');
select tcp_test.ok((:'rdoc'::jsonb ->> 'balance_after')::numeric = 1050, 'receipt shows its stored balance');
select tcp_test.ok((:'rdoc'::jsonb ->> 'payments_before')::int = 0, 'first receipt: nothing before it');
select tcp_test.ok((:'rdoc'::jsonb ->> 'recorded_by') = 'Test Owner', 'recorder name');
select tcp_test.ok((:'rdoc'::jsonb -> 'invoice' ->> 'billed_to_name') = 'Kwame Mensah', 'receipt uses the frozen name');
select tcp_test.ok((:'rdoc'::jsonb -> 'invoice' ->> 'invoice_no') = 'TCP-INV-0001', 'receipt links to the invoice');

-- ------------------------------------------------ invoice_list
select tcp_test.ok((select status from public.invoice_list where id = :draft) = 'paid', 'list shows status');
select tcp_test.ok((select billed_to_name from public.invoice_list where id = :draft) = 'Kwame Mensah', 'list shows frozen name');
reset role;

-- ------------------------------------------------ who may use them
set request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';  -- not staff
set role authenticated;
select tcp_test.ok((select count(*) from public.invoice_list) = 0, 'stranger sees no invoices in the list');
select tcp_test.fails(format('select public.invoice_document(%s)', :draft), 'only TCP staff');
select tcp_test.fails(format('select public.receipt_document(%s)', :p1), 'only TCP staff');
select tcp_test.fails($$select public.save_draft_invoice(null, 1, null, null, null, null, null, '[]'::jsonb)$$, 'only TCP staff');
reset role;
set request.jwt.claim.sub = '';
set role anon;
select tcp_test.fails('select * from public.invoice_list', 'permission denied');
select tcp_test.fails(format('select public.invoice_document(%s)', :draft), 'permission denied');
select tcp_test.fails('select tcp_private.staff_name(null)', 'permission denied');
reset role;
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';  -- finance
set role authenticated;
select tcp_test.fails($$select public.save_draft_invoice(null, 1, null, null, null, null, null, '[]'::jsonb)$$, 'finance role cannot');
select tcp_test.ok((public.invoice_document(:draft) ->> 'invoice_no') = 'TCP-INV-0001', 'finance can read documents');
reset role;
