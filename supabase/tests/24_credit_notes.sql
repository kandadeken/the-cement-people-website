-- Phase 2.3 (credit notes), the database side, per the implementation
-- specification v1.4:
--   A. The activation switch: created off; issuing refused while off; owner
--      only; every change logged; retries; the switch tables closed to
--      every client role.
--   B. Roles: who may issue, adjust, backdate, cancel, view and print.
--   C. Caps: the 10 + 20 + 70 bags example (with a discount), the 3-bag
--      GH₵290 rounding example, net values with the remainder on the
--      largest line, delivery credits, adjustments.
--   D. Dates: issue, effective and backdating rules.
--   E. Statuses: every row of the Design v1.3 status table.
--   F. Refunds stay separate; cancelling after a refund.
--   G. Cancelling credit notes: caps given back; retries; already cancelled.
--   H. cancel_invoice refused while a credit note is active.
--   I. Request fingerprints: retries, any difference refused, line order
--      and the day of the retry do not matter.
--   J. Snapshots, documents and the print data (no private field).
--   K. Record rules: never edited or deleted; direct writes refused; a line
--      must match its invoice line's kind and invoice; amount = its lines.
\set QUIET on
\set owner   '''11111111-1111-1111-1111-111111111111'''
\set sales   '''22222222-2222-2222-2222-222222222222'''
\set finance '''33333333-3333-3333-3333-333333333333'''

-- ------------------------------------------------ the invoices
-- A: 100 bags at GH₵100 less a GH₵1,000 discount = GH₵9,000 (the design's
--    10 + 20 + 70 example).
-- B: 3 bags at GH₵100 less GH₵10 = GH₵290 (the rounding example).
-- C: 10 bags at 75 + 3 bags at 110 + delivery 200, less 100 = GH₵1,180
--    (net values: the remainder goes on the largest line).
-- D, E, F, G, H: GH₵1,000 each (10 bags at 100) for statuses, refunds,
--    adjustments and cancelling.
set request.jwt.claim.sub = :sales;
set role authenticated;
select (public.create_customer('0241234567', 'Ama Owusu')).id as cust \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":1,"quantity":100,"unit_price":100},
    {"kind":"discount","quantity":1,"unit_price":-1000,"description":"Builder discount","unit":"each"}]'::jsonb) as a \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":1,"quantity":3,"unit_price":100},
    {"kind":"discount","quantity":1,"unit_price":-10,"description":"Discount","unit":"each"}]'::jsonb) as b \gset
select public.save_draft_invoice(null, :cust, 'Kasoa', null, null, current_date + 30, null,
  '[{"kind":"product","product_id":1,"quantity":10},
    {"kind":"product","product_id":3,"quantity":3},
    {"kind":"delivery","quantity":1,"unit_price":200,"description":"Delivery to Kasoa","unit":"trip"},
    {"kind":"discount","quantity":1,"unit_price":-100,"description":"Discount","unit":"each"}]'::jsonb) as c \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":1,"quantity":10,"unit_price":100}]'::jsonb) as d \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":1,"quantity":10,"unit_price":100}]'::jsonb) as e \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":1,"quantity":10,"unit_price":100}]'::jsonb) as f \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":1,"quantity":10,"unit_price":100}]'::jsonb) as g \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":1,"quantity":10,"unit_price":100}]'::jsonb) as h \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":1,"quantity":10,"unit_price":100}]'::jsonb) as dr \gset
select public.save_draft_invoice(null, :cust, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":1,"quantity":5},{"kind":"product","product_id":2,"quantity":5}]'::jsonb) as k \gset
select public.issue_invoice(:a), public.issue_invoice(:b), public.issue_invoice(:c), public.issue_invoice(:d),
       public.issue_invoice(:e), public.issue_invoice(:f), public.issue_invoice(:g), public.issue_invoice(:h), public.issue_invoice(:k) \gset
reset role;
select id as a1 from public.invoice_lines where invoice_id = :a and position = 1 \gset
select id as a2 from public.invoice_lines where invoice_id = :a and position = 2 \gset
select id as b1 from public.invoice_lines where invoice_id = :b and position = 1 \gset
select id as c1 from public.invoice_lines where invoice_id = :c and position = 1 \gset
select id as c2 from public.invoice_lines where invoice_id = :c and position = 2 \gset
select id as c3 from public.invoice_lines where invoice_id = :c and position = 3 \gset
select id as d1 from public.invoice_lines where invoice_id = :d and position = 1 \gset
select id as e1 from public.invoice_lines where invoice_id = :e and position = 1 \gset
select id as f1 from public.invoice_lines where invoice_id = :f and position = 1 \gset
select id as g1 from public.invoice_lines where invoice_id = :g and position = 1 \gset
select id as h1 from public.invoice_lines where invoice_id = :h and position = 1 \gset
select id as dr1 from public.invoice_lines where invoice_id = :dr and position = 1 \gset
select id as k1 from public.invoice_lines where invoice_id = :k and position = 1 \gset
select id as k2 from public.invoice_lines where invoice_id = :k and position = 2 \gset

-- Invoice D was issued 10 days ago (for backdating; test only: the guard
-- that locks issued invoices is lifted for this one change).
alter table public.invoices disable trigger invoices_guard;
update public.invoices set issued_at = now() - interval '10 days' where id = :d;
alter table public.invoices enable trigger invoices_guard;

-- ================================================ A. the activation switch
select tcp_test.ok((select is_on from tcp_private.feature_switches where name = 'credit_notes') = false,
                   'the switch is created off');
select tcp_test.ok((select count(*) from tcp_private.feature_switch_changes) = 0, 'no switch history yet');

set request.jwt.claim.sub = :finance;
set role authenticated;
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', p_reason => 'Returned',
  p_request_id => gen_random_uuid())$$, :a, :a1), 'Credit notes are not switched on');
select tcp_test.fails($$select public.set_credit_notes_switch(true, 'Go live', gen_random_uuid())$$, 'Not allowed: the finance role');
-- Staff see the switch, read-only.
select tcp_test.ok((public.credit_note_options()->'switch'->>'on')::boolean = false, 'staff see the switch is off');
-- The switch tables are closed to every client role.
select tcp_test.fails($$select * from tcp_private.feature_switches$$, 'permission denied');
select tcp_test.fails($$select * from tcp_private.feature_switch_changes$$, 'permission denied');
select tcp_test.fails($$update tcp_private.feature_switches set is_on = true$$, 'permission denied');
select tcp_test.fails($$insert into tcp_private.feature_switch_changes (name, is_on, reason, changed_by, request_id, request_fingerprint)
                        values ('credit_notes', true, 'x', gen_random_uuid(), gen_random_uuid(), 'x')$$, 'permission denied');
reset role;
set role anon;
select tcp_test.fails($$select * from tcp_private.feature_switches$$, 'permission denied');
select tcp_test.fails($$select public.credit_note_options()$$, 'permission denied');
reset role;

set request.jwt.claim.sub = :owner;
set role authenticated;
select tcp_test.fails($$select public.set_credit_notes_switch(true, '  ', gen_random_uuid())$$, 'A reason is needed');
select tcp_test.fails($$select public.set_credit_notes_switch(true, 'Go live', null)$$, 'A request id is needed');
-- Asking for the state it already has changes and logs nothing.
select tcp_test.ok((public.set_credit_notes_switch(false, 'Just checking', gen_random_uuid()))->>'message'
                   = 'Credit notes are already off', 'already off: says so');
reset role;
select tcp_test.ok((select count(*) from tcp_private.feature_switch_changes) = 0, 'already off: nothing logged');
set request.jwt.claim.sub = :owner;
set role authenticated;
select tcp_test.ok((public.set_credit_notes_switch(true, 'New screens verified',
                    'a0000000-0000-4000-8000-000000000001'))->>'message' = 'Credit notes are switched on', 'the owner switches on');
-- A retry (lost reply) changes nothing twice.
select tcp_test.ok((public.set_credit_notes_switch(true, 'New screens verified',
                    'a0000000-0000-4000-8000-000000000001'))->>'on' = 'true', 'a retry returns the same result');
select tcp_test.fails($$select public.set_credit_notes_switch(false, 'New screens verified', 'a0000000-0000-4000-8000-000000000001')$$,
                      'already used for a different switch change');
select tcp_test.fails($$select public.set_credit_notes_switch(true, 'Another reason', 'a0000000-0000-4000-8000-000000000001')$$,
                      'already used for a different switch change');
select tcp_test.ok((public.set_credit_notes_switch(true, 'Again', gen_random_uuid()))->>'message'
                   = 'Credit notes are already on', 'already on: says so');
select tcp_test.ok((public.credit_note_options()->'switch'->>'reason') = 'New screens verified'
                   and (public.credit_note_options()->'switch'->>'changed_by') = 'Test Owner',
                   'staff see when, by whom and why it last changed');
reset role;
select tcp_test.ok((select count(*) from tcp_private.feature_switch_changes) = 1, 'one real change, one history row');
select tcp_test.ok((select is_on from tcp_private.feature_switches where name = 'credit_notes'), 'the switch is on');
-- The history and the switch can never be edited, deleted or emptied.
select tcp_test.fails($$update tcp_private.feature_switch_changes set reason = 'x'$$, 'cannot be edited or deleted');
select tcp_test.fails($$delete from tcp_private.feature_switch_changes$$, 'cannot be edited or deleted');
select tcp_test.fails($$truncate tcp_private.feature_switch_changes$$, 'cannot be edited or deleted');
select tcp_test.fails($$delete from tcp_private.feature_switches$$, 'never removed');

-- ================================================ B and C. roles and caps
-- Sales, strangers and retired staff cannot issue.
set request.jwt.claim.sub = :sales;
set role authenticated;
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":10}]', p_reason => 'Returned',
  p_request_id => gen_random_uuid())$$, :a, :a1), 'Not allowed: the sales role');
reset role;
set request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
set role authenticated;
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":10}]', p_reason => 'Returned',
  p_request_id => gen_random_uuid())$$, :a, :a1), 'only TCP staff');
select tcp_test.fails(format($$select public.credit_note_options(%s)$$, :a), 'only TCP staff');
reset role;
set request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
set role authenticated;
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":10}]', p_reason => 'Returned',
  p_request_id => gen_random_uuid())$$, :a, :a1), 'only TCP staff');
reset role;

-- Finance: the 10 + 20 + 70 bags example on invoice A (after discount).
set request.jwt.claim.sub = :finance;
set role authenticated;
select tcp_test.ok((select (x->>'net_value')::numeric = 9000 and (x->>'quantity_left')::numeric = 100
                      and (x->>'value_left')::numeric = 9000
                    from jsonb_array_elements(public.credit_note_options(:a)->'lines') x
                    where (x->>'invoice_line_id')::bigint = :a1), 'A: 100 bags worth GH₵9,000 after the discount');
select tcp_test.ok(jsonb_array_length(public.credit_note_options(:a)->'lines') = 1, 'discount lines are not creditable');
select (public.issue_credit_note(p_invoice_id => :a,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":10}]', :a1)::jsonb,
  p_reason => 'Ten bags returned', p_customer_note => 'Thank you', p_internal_note => 'Driver brought them back',
  p_request_id => 'b0000000-0000-4000-8000-000000000001')).id as cn1 \gset
select tcp_test.ok((select amount from public.credit_notes where id = :cn1) = 900, 'first credit note: 10 bags, GH₵900');
select tcp_test.ok((select credit_note_no from public.credit_notes where id = :cn1) = 'TCP-CN-0001', 'numbered TCP-CN-0001');
select (public.issue_credit_note(p_invoice_id => :a,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"not_supplied","quantity":20}]', :a1)::jsonb,
  p_reason => 'Twenty bags not supplied', p_request_id => gen_random_uuid())).id as cn2 \gset
select tcp_test.ok((select amount from public.credit_notes where id = :cn2) = 1800, 'second: 20 bags, GH₵1,800');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":71}]', p_reason => 'Too many',
  p_request_id => gen_random_uuid())$$, :a, :a1), 'Only 70 bags are left to credit');
select (public.issue_credit_note(p_invoice_id => :a,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":70}]', :a1)::jsonb,
  p_reason => 'The rest returned', p_request_id => gen_random_uuid())).id as cn3 \gset
select tcp_test.ok((select amount from public.credit_notes where id = :cn3) = 6300, 'third: the 70 left, GH₵6,300 (what is left)');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', p_reason => 'One more',
  p_request_id => gen_random_uuid())$$, :a, :a1), 'Only 0 bags are left to credit');
select tcp_test.ok((select status from public.invoice_summary where id = :a) = 'credited'
                   and (select credited from public.invoice_summary where id = :a) = 9000
                   and (select balance from public.invoice_summary where id = :a) = 0, 'A: credited in full, nothing owed');

-- The 3-bag rounding example on invoice B: 96.67, 96.67, then exactly 96.66.
select tcp_test.ok((select (x->>'net_value')::numeric from jsonb_array_elements(public.credit_note_options(:b)->'lines') x) = 290,
                   'B: 3 bags worth GH₵290');
select (public.issue_credit_note(p_invoice_id => :b,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', :b1)::jsonb,
  p_reason => 'One bag back', p_request_id => gen_random_uuid())).amount as r1 \gset
select (public.issue_credit_note(p_invoice_id => :b,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', :b1)::jsonb,
  p_reason => 'One bag back', p_request_id => gen_random_uuid())).amount as r2 \gset
select (public.issue_credit_note(p_invoice_id => :b,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', :b1)::jsonb,
  p_reason => 'One bag back', p_request_id => gen_random_uuid())).amount as r3 \gset
select tcp_test.ok(:r1 = 96.67 and :r2 = 96.67 and :r3 = 96.66, format('rounding: %s, %s, %s', :r1, :r2, :r3));
select tcp_test.ok((select credited from public.invoice_summary where id = :b) = 290, 'B: credited exactly GH₵290');

-- Invoice C: net values add up exactly to the total, the remainder (-0.01)
-- on the largest line.
select tcp_test.ok((select sum((x->>'net_value')::numeric) from jsonb_array_elements(public.credit_note_options(:c)->'lines') x) = 1180,
                   'C: net values add up to the invoice total');
select tcp_test.ok((select string_agg(x->>'net_value', ',' order by (x->>'position')::int)
                      from jsonb_array_elements(public.credit_note_options(:c)->'lines') x) = '691.40,304.22,184.38',
                   'C: 691.41 - 0.01 on the largest line, 304.22, 184.38');
-- A delivery credit takes the delivery line's whole value left; it has no quantity.
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"delivery","why":"delivery_not_made","quantity":1}]', p_reason => 'No delivery',
  p_request_id => gen_random_uuid())$$, :c, :c3), 'A delivery credit has no quantity');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', p_reason => 'x',
  p_request_id => gen_random_uuid())$$, :c, :c3), 'Only a product line can be credited by quantity');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"delivery","why":"delivery_not_made"}]', p_reason => 'x',
  p_request_id => gen_random_uuid())$$, :c, :c1), 'Only a delivery line can be credited as a delivery');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"lost","quantity":1}]', p_reason => 'x',
  p_request_id => gen_random_uuid())$$, :c, :c1), 'not supplied or returned');
select (public.issue_credit_note(p_invoice_id => :c,
  p_lines => format('[{"invoice_line_id":%s,"kind":"delivery","why":"delivery_not_made"},
                      {"invoice_line_id":%s,"kind":"quantity","why":"not_supplied","quantity":3}]', :c3, :c2)::jsonb,
  p_reason => 'Customer collected; the iron rods were not supplied', p_request_id => gen_random_uuid())).id as cnc \gset
select tcp_test.ok((select amount from public.credit_notes where id = :cnc) = 184.38 + 304.22,
                   'C: delivery (its whole value) and the 3 bags (the whole line) in one credit note');
select tcp_test.ok((select count(*) from public.credit_note_lines where credit_note_id = :cnc) = 2, 'two lines');
select tcp_test.ok((select quantity is null from public.credit_note_lines where credit_note_id = :cnc and kind = 'delivery'),
                   'a delivery credit line has no quantity');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"delivery","why":"delivery_not_made"}]', p_reason => 'Again',
  p_request_id => gen_random_uuid())$$, :c, :c3), 'Only GH₵0.00 of this line is left to credit');
-- Lines: once each, of this invoice, at least one.
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1},
               {"invoice_line_id":%s,"kind":"quantity","why":"not_supplied","quantity":1}]', p_reason => 'x',
  p_request_id => gen_random_uuid())$$, :c, :c1, :c1), 'only once in a credit note');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', p_reason => 'x',
  p_request_id => gen_random_uuid())$$, :c, :d1), 'not on this invoice');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s, p_lines => '[]', p_reason => 'x',
  p_request_id => gen_random_uuid())$$, :c), 'at least one line');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":"%s","kind":"quantity","why":"returned","quantity":"1"}]', p_reason => 'x',
  p_request_id => gen_random_uuid())$$, :c, :c1), 'not in the right form');
-- Only issued invoices.
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', p_reason => 'x',
  p_request_id => gen_random_uuid())$$, :dr, :dr1), 'Only an issued invoice can be credited');
-- The reason is required, at most 300 characters; notes 300 / 500.
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', p_reason => '  ',
  p_request_id => gen_random_uuid())$$, :c, :c1), 'A reason is needed');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', p_reason => repeat('x', 301),
  p_request_id => gen_random_uuid())$$, :c, :c1), 'at most 300 characters');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', p_reason => 'x',
  p_customer_note => repeat('x', 301), p_request_id => gen_random_uuid())$$, :c, :c1), 'at most 300 characters');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', p_reason => 'x',
  p_internal_note => repeat('x', 501), p_request_id => gen_random_uuid())$$, :c, :c1), 'at most 500 characters');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', p_reason => 'x')$$, :c, :c1),
  'A request id is needed');
-- Finance cannot adjust or backdate.
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"kind":"adjustment","why":"price_adjustment","amount":50}]', p_reason => 'Price agreed',
  p_request_id => gen_random_uuid())$$, :d), 'Only the owner can make an adjustment credit');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', p_reason => 'x',
  p_effective_on => current_date - 2, p_backdate_reason => 'Returned last week', p_request_id => gen_random_uuid())$$, :d, :d1),
  'Only the owner can backdate a credit note, and a reason is needed');
-- Finance cannot cancel.
select tcp_test.fails(format($$select public.cancel_credit_note(%s, 'Wrong', gen_random_uuid())$$, :cn1), 'Not allowed: the finance role');
reset role;

-- Adjustments (owner): at most one per credit note; they never use or free
-- a line's value, but count against the invoice total.
set request.jwt.claim.sub = :owner;
set role authenticated;
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"kind":"adjustment","why":"price_adjustment","amount":50},{"kind":"adjustment","why":"price_adjustment","amount":20}]',
  p_reason => 'x', p_request_id => gen_random_uuid())$$, :g), 'only one adjustment line');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"kind":"adjustment","why":"price_adjustment","amount":1000.01}]',
  p_reason => 'x', p_request_id => gen_random_uuid())$$, :g), 'more than the invoice is worth');
select (public.issue_credit_note(p_invoice_id => :g,
  p_lines => '[{"kind":"adjustment","why":"price_adjustment","amount":600}]'::jsonb,
  p_reason => 'Price agreed after delivery', p_request_id => gen_random_uuid())).id as adj1 \gset
select tcp_test.ok((select (x->>'value_left')::numeric = 1000 and (x->>'quantity_left')::numeric = 10
                    from jsonb_array_elements(public.credit_note_options(:g)->'lines') x),
                   'an adjustment uses none of the line''s value or quantity');
select tcp_test.ok((public.credit_note_options(:g)->>'invoice_left')::numeric = 400, 'but GH₵400 is left at invoice level');
-- The line still shows GH₵1,000 left, but 5 bags (GH₵500) would take the
-- invoice past its total: refused.
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":5}]', p_reason => 'x',
  p_request_id => gen_random_uuid())$$, :g, :g1), 'This would credit more than the invoice is worth');
select (public.issue_credit_note(p_invoice_id => :g,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":4}]', :g1)::jsonb,
  p_reason => 'Four bags back', p_request_id => gen_random_uuid())).id as g4 \gset
select tcp_test.ok((select credited from public.invoice_summary where id = :g) = 1000, 'G: adjustment 600 + 4 bags 400');
-- Cancelling the adjustment frees invoice-level value, not line value.
select public.cancel_credit_note(:adj1, 'Price was not changed after all', gen_random_uuid()) \gset
select tcp_test.ok((select (x->>'value_left')::numeric = 600 from jsonb_array_elements(public.credit_note_options(:g)->'lines') x)
                   and (public.credit_note_options(:g)->>'invoice_left')::numeric = 600,
                   'after cancelling the adjustment: line and invoice both have GH₵600 left');
reset role;

-- ================================================ D. dates
set request.jwt.claim.sub = :owner;
set role authenticated;
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', p_reason => 'x',
  p_effective_on => current_date - 2, p_request_id => gen_random_uuid())$$, :d, :d1),
  'Only the owner can backdate a credit note, and a reason is needed');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', p_reason => 'x',
  p_effective_on => current_date - 11, p_backdate_reason => 'Too early', p_request_id => gen_random_uuid())$$, :d, :d1),
  'cannot take effect before the invoice was issued, or in the future');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', p_reason => 'x',
  p_effective_on => current_date + 1, p_backdate_reason => 'Tomorrow', p_request_id => gen_random_uuid())$$, :d, :d1),
  'cannot take effect before the invoice was issued, or in the future');
reset role;

-- A payment today, then a credit note backdated to 5 days ago: its
-- snapshots are the figures when it was RECORDED (after the payment), not
-- as at its effective date.
set request.jwt.claim.sub = :sales;
set role authenticated;
select public.record_payment(:d, 300, 'cash') \gset
reset role;
set request.jwt.claim.sub = :owner;
set role authenticated;
select (public.issue_credit_note(p_invoice_id => :d,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":2}]', :d1)::jsonb,
  p_reason => 'Two bags returned on site', p_effective_on => current_date - 5,
  p_backdate_reason => 'Returned last week; recorded late', p_request_id => gen_random_uuid())).id as dcn \gset
reset role;
select tcp_test.ok(issued_on = (now() at time zone 'Africa/Accra')::date and effective_on = current_date - 5
                   and backdate_reason = 'Returned last week; recorded late', 'backdated: issued today, effective 5 days ago, reason kept')
  from public.credit_notes where id = :dcn;
select tcp_test.ok(value_after = 800 and owed_after = 500, 'snapshots: value 800, owed 500 (the payment counted)')
  from public.credit_notes where id = :dcn;
-- A backdate reason with no earlier date is not stored.
set request.jwt.claim.sub = :owner;
set role authenticated;
select (public.issue_credit_note(p_invoice_id => :d,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', :d1)::jsonb,
  p_reason => 'One bag', p_effective_on => current_date, p_backdate_reason => 'Not needed',
  p_request_id => gen_random_uuid())).id as dcn2 \gset
reset role;
select tcp_test.ok(backdate_reason is null and effective_on = issued_on, 'same-day: no backdate reason stored')
  from public.credit_notes where id = :dcn2;

-- ================================================ E. every status row
-- (value = total - credited; owed = value - money)
-- A: value 0, money 0 -> credited (checked above). D: value 700, money 300
-- -> part_paid.
select tcp_test.ok((select status from public.invoice_summary where id = :d) = 'part_paid'
                   and (select balance from public.invoice_summary where id = :d) = 400, 'D: part paid, 400 owed');
-- E: paid 1,000, then 300 credited -> in credit by 300 (TCP owes).
set request.jwt.claim.sub = :sales;
set role authenticated;
select (public.record_payment(:e, 1000, 'cash')).id as pe \gset
select tcp_test.fails(format($$select public.record_payment(%s, 1, 'cash')$$, :e), 'more than the GH₵ 0.00 still owed');
reset role;
set request.jwt.claim.sub = :finance;
set role authenticated;
select (public.issue_credit_note(p_invoice_id => :e,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":3}]', :e1)::jsonb,
  p_reason => 'Three bags returned', p_request_id => gen_random_uuid())).id as ecn \gset
reset role;
select tcp_test.ok(status = 'in_credit' and balance = -300 and credited = 300 and paid = 1000, 'E: in credit, TCP owes 300')
  from public.invoice_summary where id = :e;
select tcp_test.ok(owed_after = -300 and value_after = 700, 'E: the snapshot says TCP owes 300')
  from public.credit_notes where id = :ecn;
-- No new payment on an invoice in credit.
set request.jwt.claim.sub = :sales;
set role authenticated;
select tcp_test.fails(format($$select public.record_payment(%s, 1, 'cash')$$, :e), 'still owed');
reset role;
-- F: paid 1,000 then fully credited -> in credit by 1,000 (value 0, money 1,000).
set request.jwt.claim.sub = :sales;
set role authenticated;
select (public.record_payment(:f, 400, 'cash')).id as pf \gset
reset role;
set request.jwt.claim.sub = :finance;
set role authenticated;
select (public.issue_credit_note(p_invoice_id => :f,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"not_supplied","quantity":10}]', :f1)::jsonb,
  p_reason => 'Nothing supplied', p_request_id => gen_random_uuid())).id as fcn \gset
reset role;
select tcp_test.ok(status = 'in_credit' and balance = -400, 'F: fully credited after part payment: in credit 400')
  from public.invoice_summary where id = :f;
-- H: part credited, unpaid -> unpaid with the lower amount owed; then
-- overdue once past due.
set request.jwt.claim.sub = :finance;
set role authenticated;
select (public.issue_credit_note(p_invoice_id => :h,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"not_supplied","quantity":3}]', :h1)::jsonb,
  p_reason => 'Three bags short', p_request_id => gen_random_uuid())).id as hcn \gset
reset role;
select tcp_test.ok(status = 'unpaid' and balance = 700, 'H: part credited, unpaid: 700 owed') from public.invoice_summary where id = :h;
alter table public.invoices disable trigger invoices_guard;
update public.invoices set due_date = current_date - 1 where id = :h;
alter table public.invoices enable trigger invoices_guard;
select tcp_test.ok(status = 'overdue', 'H: overdue once past the due date') from public.invoice_summary where id = :h;
-- G: value 600 (after the adjustment was cancelled), paid 600 -> paid.
set request.jwt.claim.sub = :sales;
set role authenticated;
select public.record_payment(:g, 600, 'cash') \gset
reset role;
select tcp_test.ok(status = 'paid' and balance = 0, 'G: part credited and paid in full: paid') from public.invoice_summary where id = :g;
-- An invoice with no credit note: credited is zero, everything as before.
select tcp_test.ok((select count(*) from public.invoice_summary where id = :dr and credited = 0 and status = 'draft') = 1,
                   'a draft: credited 0');
-- Home: owed counts only what is owed; in credit is apart (decision 1).
select tcp_test.ok(in_credit = 300 + 400 and in_credit_count = 2
                   and owed = (select sum(balance) from public.invoice_summary where status in ('unpaid','part_paid','overdue')),
                   'Home: in credit (E 300 + F 400) shown apart from owed')
  from public.back_office_home;

-- ================================================ F. refunds stay separate
-- The credit notes made no payment rows.
select tcp_test.ok((select count(*) from public.payments where invoice_id in (:a, :b, :c)) = 0, 'credit notes move no money');
set request.jwt.claim.sub = :finance;
set role authenticated;
-- The refund rule is unchanged: never more than the payment's amount.
select tcp_test.fails(format($$select public.refund_payment(%s, 1000.01, 'cash', 'Too much')$$, :pe), 'more than the GH₵ 1000.00 paid');
select (public.refund_payment(:pe, 300, 'cash', 'Credit for returned bags refunded')).balance_after as rb \gset
reset role;
select tcp_test.ok(:rb = 0, 'the refund''s balance_after includes the credit: 0');
select tcp_test.ok(status = 'paid' and balance = 0, 'E: after the refund, paid') from public.invoice_summary where id = :e;
select tcp_test.ok((select count(*) from public.credit_notes where invoice_id = :e) = 1
                   and (select amount from public.credit_notes where id = :ecn) = 300, 'the refund changed no credit note');

-- ================================================ G. cancelling credit notes
set request.jwt.claim.sub = :owner;
set role authenticated;
-- Cancelling after a refund: allowed; the customer owes the refunded amount again.
select public.cancel_credit_note(:ecn, 'Bags were not actually returned', 'c0000000-0000-4000-8000-000000000001') as ecx \gset
select tcp_test.ok((:'ecx'::jsonb->>'balance')::numeric = 300, 'cancelling after a refund: 300 owed again');
select tcp_test.ok(status = 'part_paid' and credited = 0, 'E: part paid again') from public.invoice_summary where id = :e;
-- The same request again returns the first cancellation; anything else refused.
select tcp_test.ok((public.cancel_credit_note(:ecn, 'Bags were not actually returned', 'c0000000-0000-4000-8000-000000000001'))->>'id'
                   = :'ecx'::jsonb->>'id', 'a retry returns the first cancellation');
select tcp_test.fails(format($$select public.cancel_credit_note(%s, 'Another reason', 'c0000000-0000-4000-8000-000000000001')$$, :ecn),
                      'already used for a different cancellation');
select tcp_test.fails(format($$select public.cancel_credit_note(%s, 'Bags were not actually returned', 'c0000000-0000-4000-8000-000000000001')$$, :cn1),
                      'already used for a different cancellation');
select tcp_test.fails(format($$select public.cancel_credit_note(%s, 'Again', gen_random_uuid())$$, :ecn), 'already cancelled');
select tcp_test.fails(format($$select public.cancel_credit_note(%s, '  ', gen_random_uuid())$$, :cn2), 'A reason is needed');
-- Cancelling gives the caps back: A's 20 bags can be credited again.
select public.cancel_credit_note(:cn2, 'Entered twice', gen_random_uuid()) \gset
select tcp_test.ok((select (x->>'quantity_left')::numeric = 20 and (x->>'value_left')::numeric = 1800
                    from jsonb_array_elements(public.credit_note_options(:a)->'lines') x), 'A: 20 bags, GH₵1,800 back');
select tcp_test.ok(status = 'unpaid' and balance = 1800, 'A: 1,800 owed again') from public.invoice_summary where id = :a;
select tcp_test.ok((select cancelled_on = (now() at time zone 'Africa/Accra')::date from public.credit_note_cancellations
                    where credit_note_id = :cn2), 'a cancellation is dated today in Ghana');
reset role;

-- ================================================ H. cancel_invoice
set request.jwt.claim.sub = :owner;
set role authenticated;
select tcp_test.fails(format($$select public.cancel_invoice(%s, 'Order cancelled')$$, :b),
                      'This invoice has active credit notes. Cancel them before cancelling the invoice.');
select count(public.cancel_credit_note(id, 'Cancelling the invoice instead', gen_random_uuid())) as bx
  from public.credit_notes where invoice_id = :b \gset
select public.cancel_invoice(:b, 'Order cancelled') \gset
reset role;
select tcp_test.ok((select state from public.invoices where id = :b) = 'cancelled', 'B cancelled once its credit notes were');
select tcp_test.ok((select count(*) from public.credit_notes where invoice_id = :b) = 3
                   and (select count(*) from public.credit_note_cancellations x join public.credit_notes n on n.id = x.credit_note_id
                        where n.invoice_id = :b) = 3, 'every credit note and cancellation is still on record');

-- ================================================ I. request fingerprints
set request.jwt.claim.sub = :finance;
set role authenticated;
-- The same request again (lines in a different order) returns the first.
select tcp_test.ok((public.issue_credit_note(p_invoice_id => :a,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":10.0}]', :a1)::jsonb,
  p_reason => ' Ten bags returned ', p_customer_note => 'Thank you', p_internal_note => 'Driver brought them back',
  p_request_id => 'b0000000-0000-4000-8000-000000000001')).id = :cn1, 'a retry returns the first credit note');
select tcp_test.ok((select count(*) from public.credit_notes where request_id = 'b0000000-0000-4000-8000-000000000001') = 1, 'still one');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":11}]',
  p_reason => 'Ten bags returned', p_customer_note => 'Thank you', p_internal_note => 'Driver brought them back',
  p_request_id => 'b0000000-0000-4000-8000-000000000001')$$, :a, :a1), 'already used for a different credit note');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":10}]',
  p_reason => 'Ten bags returned', p_customer_note => 'Thank you', p_internal_note => 'Someone else brought them',
  p_request_id => 'b0000000-0000-4000-8000-000000000001')$$, :a, :a1), 'already used for a different credit note');
-- Line order, number formats and spaces around words do not matter.
select (public.issue_credit_note(p_invoice_id => :k,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1},
                      {"invoice_line_id":%s,"kind":"quantity","why":"not_supplied","quantity":2}]', :k1, :k2)::jsonb,
  p_reason => 'Mixed', p_request_id => 'b0000000-0000-4000-8000-000000000009')).id as kcn \gset
select tcp_test.ok((public.issue_credit_note(p_invoice_id => :k,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"not_supplied","quantity":2.000},
                      {"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', :k2, :k1)::jsonb,
  p_reason => 'Mixed ', p_request_id => 'b0000000-0000-4000-8000-000000000009')).id = :kcn, 'lines in another order: the same request');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":2},
               {"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]',
  p_reason => 'Mixed', p_request_id => 'b0000000-0000-4000-8000-000000000009')$$, :k, :k2, :k1), 'already used for a different credit note');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1},
               {"invoice_line_id":%s,"kind":"quantity","why":"not_supplied","quantity":2}]',
  p_reason => 'Mixed', p_effective_on => current_date, p_request_id => 'b0000000-0000-4000-8000-000000000009')$$, :k, :k1, :k2),
  'already used for a different credit note');
reset role;
-- The fingerprint holds the effective date AS SENT (none here), never the
-- issue date, so a genuine retry after midnight still matches.
select tcp_test.ok((select request_fingerprint from public.credit_notes where id = :cn1)
                   = tcp_private.credit_note_fingerprint(:a, format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":10}]', :a1)::jsonb,
                       'Ten bags returned', 'Thank you', 'Driver brought them back', null, null),
                   'the fingerprint holds no date: a retry after midnight still matches');
-- A retry is answered even after the switch is turned off (the first call
-- succeeded; only its reply was lost).
set request.jwt.claim.sub = :owner;
set role authenticated;
select public.set_credit_notes_switch(false, 'Pause for a check', gen_random_uuid()) \gset
reset role;
set request.jwt.claim.sub = :finance;
set role authenticated;
select tcp_test.ok((public.issue_credit_note(p_invoice_id => :k,
  p_lines => format('[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1},
                      {"invoice_line_id":%s,"kind":"quantity","why":"not_supplied","quantity":2}]', :k1, :k2)::jsonb,
  p_reason => 'Mixed', p_request_id => 'b0000000-0000-4000-8000-000000000009')).id = :kcn,
  'switched off: a retry of a credit note already made still returns it');
select tcp_test.fails(format($$select public.issue_credit_note(p_invoice_id => %s,
  p_lines => '[{"invoice_line_id":%s,"kind":"quantity","why":"returned","quantity":1}]', p_reason => 'New',
  p_request_id => gen_random_uuid())$$, :k, :k1), 'Credit notes are not switched on');
-- Viewing and printing still work while off.
select tcp_test.ok((public.credit_note_document(:kcn)->>'credit_note_no') is not null
                   and (public.credit_note_print(:kcn)->>'credit_note_no') is not null, 'switched off: view and print still work');
reset role;
-- The owner can still cancel a wrong credit note while off.
set request.jwt.claim.sub = :owner;
set role authenticated;
select tcp_test.ok((public.cancel_credit_note(:kcn, 'Wrong lines', gen_random_uuid()))->>'credit_note_id' = :'kcn',
                   'switched off: the owner can still cancel');
select public.set_credit_notes_switch(true, 'Check done', gen_random_uuid()) \gset
reset role;
select tcp_test.ok((select count(*) from tcp_private.feature_switch_changes) = 3
                   and (select string_agg(is_on::text || ':' || reason, ' / ' order by id) from tcp_private.feature_switch_changes)
                       = 'true:New screens verified / false:Pause for a check / true:Check done', 'every change logged, in order');

-- ================================================ J. documents and print data
set request.jwt.claim.sub = :sales;
set role authenticated;
-- Staff view: everything, including the private fields.
select tcp_test.ok(d->>'internal_note' = 'Driver brought them back' and d->>'recorded_by' = 'Test Finance'
                   and d->>'reason' = 'Ten bags returned' and d->>'customer_note' = 'Thank you'
                   and d->>'invoice_no' is not null and jsonb_array_length(d->'lines') = 1
                   and (d->'lines'->0->>'quantity')::numeric = 10 and d->'lines'->0->>'why' = 'returned',
                   'credit_note_document: the staff view')
  from (select public.credit_note_document(:cn1) d) x;
select tcp_test.ok(d->>'backdate_reason' = 'Returned last week; recorded late', 'the staff view has the backdate reason')
  from (select public.credit_note_document(:dcn) d) x;
-- Print data: the overall reason and the note to the customer; never the
-- internal note, the backdate reason, a staff name or a cancel reason.
select tcp_test.ok(p->>'reason' = 'Ten bags returned' and p->>'customer_note' = 'Thank you'
                   and (p->>'amount')::numeric = 900 and (p->>'value_before')::numeric = 9000
                   and (p->>'value_after')::numeric = 8100 and (p->>'owed_after')::numeric = 8100
                   and p->'lines'->0->>'why' = 'Returned' and p->>'effective_on' is null
                   and p->>'billed_to_name' = 'Ama Owusu', 'credit_note_print: what the PDF prints')
  from (select public.credit_note_print(:cn1) p) x;
select tcp_test.ok(p->>'effective_on' = (current_date - 5)::text, 'print: the effective date only when it differs')
  from (select public.credit_note_print(:dcn) p) x;
select tcp_test.ok(not exists (
         select 1 from public.credit_notes n,
                lateral jsonb_each_text(public.credit_note_print(n.id)) kv
          where kv.key in ('internal_note', 'backdate_reason', 'recorded_by', 'cancel_reason', 'cancelled_by', 'request_id')
             or kv.value like '%Driver brought%' or kv.value like '%recorded late%'
             or kv.value like '%Test Finance%' or kv.value like '%Test Owner%'
             or kv.value like '%Entered twice%'),
       'no print data anywhere holds a private field or a staff name');
select tcp_test.ok((public.credit_note_print(:cn2)->>'cancelled_on') = ((now() at time zone 'Africa/Accra')::date)::text,
                   'a cancelled credit note prints its cancellation date (and not the reason)');
-- invoice_document: credited and the credit notes; every earlier key kept.
select tcp_test.ok((d->>'credited')::numeric = 7200 and jsonb_array_length(d->'credit_notes') = 3
                   and (select bool_or((c->>'cancelled')::boolean) from jsonb_array_elements(d->'credit_notes') c)
                   and d ?& array['id','invoice_no','state','status','issued_at','issued_by','due_date','notes','cancel_reason',
                                  'customer_id','customer_code','billed_to_name','billed_to_phone','lines','total','paid','balance',
                                  'payments','internal_notes','cancelled_at','cancelled_by'],
                   'invoice_document: credited, the credit notes, and every earlier key')
  from (select public.invoice_document(:a) d) x;
-- The invoice's own lines are untouched by credit notes.
select tcp_test.ok((select sum((l->>'line_total')::numeric) from jsonb_array_elements(public.invoice_document(:a)->'lines') l) = 9000,
                   'the invoice lines are unchanged');
-- A receipt never shows later credit notes.
select tcp_test.ok(not (public.receipt_document(:pe)->'invoice' ?| array['credited', 'credit_notes']), 'receipts leave the credit keys out');
reset role;

-- ================================================ K. record rules
-- Staff read the tables; nobody writes to them directly.
set request.jwt.claim.sub = :sales;
set role authenticated;
select tcp_test.ok((select count(*) from public.credit_notes) > 0 and (select count(*) from public.credit_note_lines) > 0,
                   'staff read credit notes');
select tcp_test.fails(format($$insert into public.credit_note_cancellations (credit_note_id, cancelled_on, reason, recorded_by, request_id, request_fingerprint)
                               values (%s, current_date, 'x', gen_random_uuid(), gen_random_uuid(), 'x')$$, :cn1), 'permission denied');
select tcp_test.fails($$update public.credit_notes set amount = 1$$, 'permission denied');
select tcp_test.fails($$delete from public.credit_note_lines$$, 'permission denied');
reset role;
set request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
set role authenticated;
select tcp_test.ok((select count(*) from public.credit_notes) = 0, 'non-staff see no credit notes');
select tcp_test.fails(format($$select public.credit_note_print(%s)$$, :cn1), 'only TCP staff');
reset role;
set role anon;
select tcp_test.fails($$select * from public.credit_notes$$, 'permission denied');
reset role;
-- Even with full rights, nothing is edited, deleted or emptied.
select tcp_test.fails(format($$update public.credit_notes set reason = 'x' where id = %s$$, :cn1), 'never edited or deleted');
select tcp_test.fails(format($$delete from public.credit_notes where id = %s$$, :cn1), 'never edited or deleted');
select tcp_test.fails($$update public.credit_note_lines set amount = 1$$, 'never edited or deleted');
select tcp_test.fails($$delete from public.credit_note_cancellations$$, 'never edited or deleted');
select tcp_test.fails($$truncate public.credit_note_lines cascade$$, 'never edited or deleted');
-- A line must match its invoice line's kind, and belong to its credit
-- note's invoice; the amount must equal its lines.
create function pg_temp.raw_credit(p_invoice bigint, p_line bigint, p_kind text, p_why text, p_qty numeric, p_amount numeric, p_total numeric)
returns void language plpgsql as $$
declare
  nid bigint;
begin
  insert into public.credit_notes (credit_note_no, invoice_id, issued_on, effective_on, reason, amount, value_after,
                                   owed_after, recorded_by, request_id, request_fingerprint)
  values ('RAW-' || gen_random_uuid(), p_invoice, (now() at time zone 'Africa/Accra')::date,
          (now() at time zone 'Africa/Accra')::date, 'raw', p_total, 0, 0, gen_random_uuid(), gen_random_uuid(), 'x')
  returning id into nid;
  insert into public.credit_note_lines (credit_note_id, invoice_id, invoice_line_id, kind, why, quantity, amount)
  values (nid, p_invoice, p_line, p_kind, p_why, p_qty, p_amount);
  set constraints all immediate;
end $$;
select tcp_test.fails(format($$select pg_temp.raw_credit(%s, %s, 'delivery', 'delivery_not_made', null, 10, 10)$$, :h, :h1),
                      'A delivery credit cannot be made on a product line');
select tcp_test.fails(format($$select pg_temp.raw_credit(%s, %s, 'quantity', 'returned', 1, 10, 10)$$, :h, :g1),
                      'credit_note_lines_invoice_line_fk');
select tcp_test.fails(format($$select pg_temp.raw_credit(%s, %s, 'quantity', 'returned', 1, 10, 11)$$, :h, :h1),
                      'amount must equal the sum of its lines');
select tcp_test.fails(format($$select pg_temp.raw_credit(%s, %s, 'quantity', 'returned', null, 10, 10)$$, :h, :h1),
                      'credit_note_lines_quantity_only_on_quantity_lines');
select tcp_test.fails(format($$select pg_temp.raw_credit(%s, null, 'adjustment', 'returned', null, 10, 10)$$, :h),
                      'credit_note_lines_why_matches_kind');
select pg_temp.raw_credit(:h, :h1, 'quantity', 'returned', 1, 10, 10) \gset
select tcp_test.ok((select count(*) from public.credit_notes where credit_note_no like 'RAW-%') = 1,
                   'a well-formed one passes the rules (so the refusals above are the rules, not the helper)');
-- Every change is in the audit log.
select tcp_test.ok((select count(*) from public.audit_log where table_name = 'credit_notes')
                   = (select count(*) from public.credit_notes)
                   and (select count(*) from public.audit_log where table_name = 'credit_note_cancellations')
                   = (select count(*) from public.credit_note_cancellations), 'every credit note and cancellation is audited');
-- The counter: TCP-CN-0001 upwards, no gaps among those made by the function.
select tcp_test.ok((select count(*) from public.credit_notes where credit_note_no like 'TCP-CN-%')
                   = (select last_value from tcp_private.number_counters where kind = 'credit_note'), 'credit note numbers have no gaps');
