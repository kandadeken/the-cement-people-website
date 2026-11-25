-- Phase 2.2 (notes from estimate to receipt), the database side, per the
-- design v1.6:
--   A. Payment, refund and correction notes stored; the request id matches
--      every detail (notes and reference included).
--   B. Lengths and the no-customer-note-on-corrections rule.
--   C. add_invoice_note: any invoice state, categories, request ids.
--   D. Corrections form one line: notes and payment, refund and correction
--      records' notes; a second, competing correction is refused.
--   E. Same-invoice enforcement by the database itself (direct inserts that
--      bypass the function are refused); notes never edited or deleted.
--   F. Who sees what: staff only.
--   G. search_notes: words, categories, authors, Ghana days, corrected
--      notes, the invoice note box, plain-text matching, paging.
--   H. Snapshots: issued documents unchanged by later internal notes.
\set QUIET on

-- ------------------------------------------------ the records
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';  -- sales
set role authenticated;
select (public.create_customer('0241234567', 'Ama Owusu')).id as ama \gset
select public.save_draft_invoice(null, :ama, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as inv1 \gset
select public.save_draft_invoice(null, :ama, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as inv2 \gset
select public.save_draft_invoice(null, :ama, null, null, null, null, E'Customer pickup\nPrices held until Friday',
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as inv3 \gset
select public.save_draft_invoice(null, :ama, null, null, null, current_date + 30, null,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb) as inv4 \gset
select public.issue_invoice(:inv1), public.issue_invoice(:inv2), public.issue_invoice(:inv4) \gset
select (public.record_payment(:inv1, 400, 'cash', null, current_date, 'c0000000-0000-4000-8000-000000000001',
        'Thank you. Balance due Friday.', 'Paid by his brother Kwame.')).id as p1 \gset
select (public.record_payment(:inv1, 300, 'mobile_money', 'MP1', current_date, 'c0000000-0000-4000-8000-000000000002',
        null, 'Sent from Kofi''s phone')).id as p2 \gset
select (public.record_payment(:inv1, 50, 'cash')).id as p3 \gset
select (public.record_payment(:inv4, 20, 'cash', null, current_date, null, null, 'Other invoice')).id as p4 \gset
reset role;

set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';  -- finance
set role authenticated;
select (public.refund_payment(:p1, 100, 'cash', 'Two bags back', null, 'c0000000-0000-4000-8000-000000000003',
        'Refund for two bags', 'Cash handed over at the depot')).id as r1 \gset
select (public.correct_payment(:p2, 'Never arrived', 'c0000000-0000-4000-8000-000000000004',
        'MoMo reversed by the network')).id as c1 \gset
reset role;
-- ------------------------------------------------ H (part 1): snapshots before notes
create temp table snap as
select public.invoice_document(:inv1) - 'internal_notes' as inv_doc,
       public.receipt_document(:p1) - 'internal_note_chain' as rct_doc;
-- (Taken after every payment, refund and correction, before any note.
--  The payments' chain field is the only internal-note field inside the
--  invoice's payments; it is dropped for the comparison.)
create function pg_temp.customer_view(d jsonb) returns jsonb language sql as $$
  select (d - 'internal_notes') || jsonb_build_object('payments',
    coalesce((select jsonb_agg(p - 'internal_note_chain' order by (p->>'id')::bigint) from jsonb_array_elements(d->'payments') p), '[]'::jsonb));
$$;
update snap set inv_doc = pg_temp.customer_view(public.invoice_document(:inv1));

set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
set role authenticated;

-- ------------------------------------------------ A. request ids match every detail
select tcp_test.ok((public.refund_payment(:p1, 100, 'cash', 'Two bags back', null, 'c0000000-0000-4000-8000-000000000003',
        'Refund for two bags', 'Cash handed over at the depot')).id = :r1, 'the same refund again gives the first refund');
select tcp_test.fails(format($$select public.refund_payment(%s, 100, 'cash', 'Two bags back', null, 'c0000000-0000-4000-8000-000000000003',
        'Refund for two bags', 'Cash handed over somewhere else')$$, :p1), 'already used for a different payment');
select tcp_test.fails(format($$select public.correct_payment(%s, 'Never arrived', 'c0000000-0000-4000-8000-000000000004', 'Different note')$$, :p2),
                      'already used for a different payment');
reset role;
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
set role authenticated;
select tcp_test.ok((public.record_payment(:inv1, 400, 'cash', null, current_date, 'c0000000-0000-4000-8000-000000000001',
        'Thank you. Balance due Friday.', 'Paid by his brother Kwame.')).id = :p1, 'the same payment again gives the first receipt');
select tcp_test.fails(format($$select public.record_payment(%s, 400, 'cash', null, current_date, 'c0000000-0000-4000-8000-000000000001',
        'Thank you. Balance due Friday.', 'Paid by his brother Kofi.')$$, :inv1), 'already used for a different payment');
select tcp_test.fails(format($$select public.record_payment(%s, 300, 'mobile_money', 'MP2', current_date, 'c0000000-0000-4000-8000-000000000002',
        null, 'Sent from Kofi''s phone')$$, :inv1), 'already used for a different payment');
select tcp_test.ok((select customer_note = 'Thank you. Balance due Friday.' and internal_note = 'Paid by his brother Kwame.'
                      from public.payments where id = :p1), 'a payment keeps both notes');
select tcp_test.ok((public.receipt_document(:r1) ->> 'customer_note') = 'Refund for two bags'
                   and (public.receipt_document(:c1) ->> 'internal_note') = 'MoMo reversed by the network'
                   and (public.receipt_document(:c1) -> 'customer_note') = 'null'::jsonb,
                   'receipts return their notes; a correction has no note to the customer');
select tcp_test.ok(not (public.receipt_document(:p1) -> 'invoice') ? 'internal_notes',
                   'the invoice inside a receipt carries no internal notes');
select tcp_test.ok((select search_text like '%kwame%' from public.payment_ledger where id = :p1),
                   'the Payments tab search covers payment notes');

-- ------------------------------------------------ B. lengths and rules
select tcp_test.fails(format($$select public.record_payment(%s, 10, 'cash', null, current_date, null, %L)$$, :inv1, repeat('x', 301)),
                      'payments_customer_note_length');
select tcp_test.fails(format($$select public.record_payment(%s, 10, 'cash', null, current_date, null, null, %L)$$, :inv1, repeat('x', 501)),
                      'payments_internal_note_length');
select tcp_test.fails(format($$select public.save_draft_invoice(%s, %s, null, null, null, null, %L,
  '[{"kind":"product","product_id":3,"quantity":10}]'::jsonb)$$, :inv3, :ama, repeat('x', 601)), 'invoices_notes_length');
reset role;
select tcp_test.fails(format($$insert into public.payments (receipt_no, invoice_id, kind, amount, method, reverses_payment_id, reason, customer_note)
                              values ('X-1', %s, 'correction', -50, 'cash', %s, 'x', 'hello')$$, :inv1, :p3),
                      'payments_no_customer_note_on_corrections');

-- ------------------------------------------------ C. add_invoice_note
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
set role authenticated;
select (public.add_invoice_note(:inv1, '  Customer says the balance comes on Friday by MoMo.  ', 'payment', null, null,
        'd0000000-0000-4000-8000-000000000001')).id as n1 \gset
select tcp_test.ok((public.add_invoice_note(:inv1, 'Customer says the balance comes on Friday by MoMo.', 'payment', null, null,
        'd0000000-0000-4000-8000-000000000001')).id = :n1, 'the same note again gives the first note');
select tcp_test.fails(format($$select public.add_invoice_note(%s, 'Customer says Saturday.', 'payment', null, null,
        'd0000000-0000-4000-8000-000000000001')$$, :inv1), 'already used for a different note');
select tcp_test.fails(format($$select public.add_invoice_note(%s, 'Customer says the balance comes on Friday by MoMo.', 'delivery', null, null,
        'd0000000-0000-4000-8000-000000000001')$$, :inv1), 'already used for a different note');
select tcp_test.ok((select body = 'Customer says the balance comes on Friday by MoMo.' from public.invoice_notes where id = :n1),
                   'a note is saved trimmed');
select (public.add_invoice_note(:inv3, 'Deliver after 2 pm. Call my site manager Kofi.', null, null, null, null, 'TCP-241126-K7Q2PA')).id as nest \gset
select tcp_test.ok((select category = 'general' and estimate_ref = 'TCP-241126-K7Q2PA' and created_by = '22222222-2222-2222-2222-222222222222'
                      from public.invoice_notes where id = :nest),
                   'a note from an estimate, on a draft: General, with its reference and author');
select tcp_test.fails(format($$select public.add_invoice_note(%s, 'x', 'gossip')$$, :inv1), 'Unknown note category');
select tcp_test.fails(format($$select public.add_invoice_note(%s, '   ')$$, :inv1), 'cannot be empty');
select tcp_test.fails(format($$select public.add_invoice_note(%s, %L)$$, :inv1, repeat('x', 1001)), 'at most 1,000');
reset role;
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';  -- owner
set role authenticated;
select public.cancel_invoice(:inv2, 'Customer changed their mind') \gset
select (public.add_invoice_note(:inv2, 'Cancelled after a call with Ama.', 'follow_up')).id as ncan \gset
select tcp_test.ok(:ncan > 0, 'notes can be added to a cancelled invoice');
reset role;

-- ------------------------------------------------ D. corrections, one line
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
set role authenticated;
select (public.add_invoice_note(:inv1, 'Correction: it was Saturday, not Friday.', null, :n1)).id as n2 \gset
reset role;
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
set role authenticated;
select (public.add_invoice_note(:inv1, 'Correction: Sunday, he called again.', null, :n2)).id as n3 \gset
select tcp_test.ok((select category from public.invoice_notes where id = :n3) = 'payment',
                   'a correction keeps the category of what it corrects');
select tcp_test.fails(format($$select public.add_invoice_note(%s, 'Another correction of the original', null, %s)$$, :inv1, :n1),
                      'just corrected by');
select tcp_test.fails(format($$select public.add_invoice_note(%s, 'Another correction of n2', null, %s)$$, :inv1, :n2),
                      'just corrected by');
reset role;  -- (note_chain is internal: checked as the test's administrator)
select tcp_test.ok((select array_agg((e->>'id')::bigint order by ord) from jsonb_array_elements(tcp_private.note_chain(:n1, null)) with ordinality x(e, ord))
                   = array[:n2, :n3]::bigint[], 'the chain of n1 is n2, then n3 (latest last)');
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
set role authenticated;
-- Payment, refund and correction records' notes.
select (public.add_invoice_note(:inv1, 'Correction to the internal note on payment: it was Kofi, not Kwame.', null, null, :p1)).id as pn1 \gset
select tcp_test.ok((select category from public.invoice_notes where id = :pn1) = 'payment', 'a payment note correction is Payment');
select tcp_test.fails(format($$select public.add_invoice_note(%s, 'Again', null, null, %s)$$, :inv1, :p1), 'just corrected by');
select (public.add_invoice_note(:inv1, 'Correction: Kofi Mensah, his cousin.', null, :pn1)).id as pn2 \gset
select (public.add_invoice_note(:inv1, 'Correction to the refund note: handed over at the site.', null, null, :r1)).id as rn1 \gset
select (public.add_invoice_note(:inv1, 'Correction to the correction note: the bank reversed it.', null, null, :c1)).id as cn1 \gset
select tcp_test.fails(format($$select public.add_invoice_note(%s, 'x', null, null, %s)$$, :inv1, :p3), 'no internal note to correct');
select tcp_test.ok(jsonb_array_length(public.receipt_document(:p1) -> 'internal_note_chain') = 2
                   and (public.receipt_document(:p1) -> 'internal_note_chain' -> -1 ->> 'id')::bigint = :pn2,
                   'the payment''s receipt shows its two corrections, the latest last');
select tcp_test.ok((select bool_and(jsonb_array_length(p -> 'internal_note_chain') = case (p->>'id')::bigint when :p1 then 2 when :r1 then 1 when :c1 then 1 else 0 end)
                      from jsonb_array_elements(public.invoice_document(:inv1) -> 'payments') p),
                   'the payment history agrees: p1 two corrections, the refund and the correction one each');
select tcp_test.ok((select (n ->> 'corrected_by_note_id')::bigint from jsonb_array_elements(public.invoice_document(:inv1) -> 'internal_notes') n
                     where (n->>'id')::bigint = :n1) = :n2
                   and (select n ->> 'corrects_receipt_no' from jsonb_array_elements(public.invoice_document(:inv1) -> 'internal_notes') n
                     where (n->>'id')::bigint = :pn1) = (select receipt_no from public.payments where id = :p1),
                   'the invoice''s notes log links each correction both ways');
reset role;

-- ------------------------------------------------ E. the database's own rules
select (select id from public.invoice_notes where invoice_id = :inv3 limit 1) as n_other \gset
select tcp_test.fails(format($$select public.add_invoice_note(%s, 'x', null, %s)$$, :inv1, :n_other), 'not on this invoice');
select tcp_test.fails(format($$insert into public.invoice_notes (invoice_id, body, corrects_payment_id, created_by)
                              values (%s, 'bypass', %s, '11111111-1111-1111-1111-111111111111')$$, :inv1, :p4),
                      'invoice_notes_corrects_payment_same_invoice');
select tcp_test.fails(format($$insert into public.invoice_notes (invoice_id, body, corrects_note_id, created_by)
                              values (%s, 'bypass', %s, '11111111-1111-1111-1111-111111111111')$$, :inv1, :n_other),
                      'invoice_notes_corrects_note_same_invoice');
select tcp_test.fails(format($$insert into public.invoice_notes (invoice_id, body, corrects_note_id, corrects_payment_id, created_by)
                              values (%s, 'bypass', %s, %s, '11111111-1111-1111-1111-111111111111')$$, :inv1, :n3, :p3),
                      'invoice_notes_one_target');
select tcp_test.fails(format($$insert into public.invoice_notes (invoice_id, body, corrects_note_id, created_by)
                              values (%s, 'bypass', %s, '11111111-1111-1111-1111-111111111111')$$, :inv1, :n1),
                      'invoice_notes_one_correction_per_note');
select tcp_test.fails(format($$update public.invoice_notes set body = 'rewritten' where id = %s$$, :n1), 'never edited or deleted');
select tcp_test.fails(format($$delete from public.invoice_notes where id = %s$$, :n1), 'never edited or deleted');

-- ------------------------------------------------ F. who sees what
create temp table seen (who text, rows int, search_ok boolean, add_ok boolean);
grant all on seen to authenticated, anon;
do $$
declare
  w record; s boolean; a boolean;
begin
  for w in select * from (values ('owner', '11111111-1111-1111-1111-111111111111'),
                                 ('sales', '22222222-2222-2222-2222-222222222222'),
                                 ('finance', '33333333-3333-3333-3333-333333333333'),
                                 ('stranger', '44444444-4444-4444-4444-444444444444'),
                                 ('retired', '55555555-5555-5555-5555-555555555555')) v(name, sub) loop
    perform set_config('request.jwt.claim.sub', w.sub, true);
    execute 'set local role authenticated';
    begin perform public.search_notes('balance'); s := true; exception when others then s := false; end;
    begin perform public.add_invoice_note((select min(id) from public.invoices), 'probe'); a := true;
      exception when others then a := false; end;
    insert into seen select w.name, (select count(*) from public.invoice_notes where body <> 'probe'), s, a;
    execute 'reset role';
  end loop;
end $$;
select tcp_test.ok((select bool_and(rows > 0 and search_ok and add_ok) from seen where who in ('owner', 'sales', 'finance')),
                   'owner, sales and finance read, search and write notes');
select tcp_test.ok((select bool_and(rows = 0 and not search_ok and not add_ok) from seen where who in ('stranger', 'retired')),
                   'non-staff and retired staff read nothing, cannot search, cannot write');
set role anon;
select tcp_test.fails($$select id from public.invoice_notes$$, 'permission denied');
select tcp_test.fails($$select public.search_notes('balance')$$, 'permission denied');
select tcp_test.fails($$select public.note_authors()$$, 'permission denied');
reset role;

-- ------------------------------------------------ G. search_notes
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
set role authenticated;
create temp table r as select public.search_notes('balance friday') as j;
select tcp_test.ok((select (j->>'count')::int from r) = 2
                   and (select array_agg(e->>'kind' order by e->>'kind') from r, jsonb_array_elements(j->'rows') e)
                       = array['invoice_note', 'receipt_customer_note'],
                   'two words, any order: the invoice note and the receipt''s note to the customer');
select tcp_test.ok((select e->>'by' from r, jsonb_array_elements(j->'rows') e where e->>'kind' = 'receipt_customer_note')
                   = public.receipt_document(:p1) ->> 'recorded_by',
                   'a receipt''s note to the customer is by whoever recorded the receipt');
select tcp_test.ok((select (e->>'corrected')::boolean and jsonb_array_length(e->'chain') = 2
                           and (e->'chain'->-1->>'id')::bigint = :n3
                      from r, jsonb_array_elements(j->'rows') e where e->>'kind' = 'invoice_note'),
                   'a corrected note arrives with its chain; the latest correction last');
select tcp_test.ok((select bool_and(e->>'category' = 'payment') from jsonb_array_elements(public.search_notes(null, 'payment')->'rows') e)
                   and (select count(*) from jsonb_array_elements(public.search_notes(null, 'payment')->'rows') e
                         where e->>'kind' in ('receipt_customer_note', 'invoice_customer_note')) = 0,
                   'a category shows only categorised notes; notes to the customer drop out');
select tcp_test.ok((select count(*) from jsonb_array_elements(public.search_notes('cousin')->'rows') e where e->>'kind' = 'invoice_note') = 1,
                   'corrections are searchable too');
select tcp_test.fails($$select public.search_notes('to')$$, 'at least 3 letters');
select tcp_test.fails($$select public.search_notes('balance ok')$$, 'at least 3 letters');
select tcp_test.ok((public.search_notes('___') ->> 'count')::int = 0 and (public.search_notes('%%%') ->> 'count')::int = 0,
                   '_ and % are plain text, not wildcards');
select tcp_test.ok((select array_agg(e->>'body') from jsonb_array_elements(public.search_notes('held')->'rows') e) = array['Prices held until Friday'],
                   'the invoice note box is searched without the delivery and estimate lines');
select tcp_test.ok((public.search_notes('pickup') ->> 'count')::int = 0, 'the delivery line is not a note');
select tcp_test.ok((select bool_and(e->>'by' = 'Test Finance')
                      from jsonb_array_elements(public.search_notes(null, null, '33333333-3333-3333-3333-333333333333')->'rows') e)
                   and (public.search_notes(null, null, '33333333-3333-3333-3333-333333333333') ->> 'count')::int >= 5,
                   'author: only finance''s notes (refund, correction, and the corrections finance wrote)');
-- Hide corrected: n1 and n2 (corrected) drop out, n3 stays.
select tcp_test.ok((select array_agg((e->>'note_id')::bigint) from jsonb_array_elements(public.search_notes('correction sunday', null, null, null, null, true)->'rows') e) = array[:n3]::bigint[]
                   and (select count(*) from jsonb_array_elements(public.search_notes('friday', null, null, null, null, true)->'rows') e where (e->>'note_id')::bigint = :n1) = 0,
                   'Leave out corrected notes hides originals that have a correction, not the latest');
-- Paging.
select tcp_test.ok((select array_agg(x order by x) from (
                      select (coalesce(e->>'note_id', e->>'payment_id') || (e->>'kind')) as x from jsonb_array_elements(public.search_notes(null, null, null, null, null, false, 0, 4)->'rows') e
                      union all
                      select (coalesce(e->>'note_id', e->>'payment_id') || (e->>'kind')) from jsonb_array_elements(public.search_notes(null, null, null, null, null, false, 4, 100)->'rows') e) t)
                   = (select array_agg(x order by x) from (
                      select (coalesce(e->>'note_id', e->>'payment_id') || (e->>'kind')) as x from jsonb_array_elements(public.search_notes(null, null, null, null, null, false, 0, 100)->'rows') e) t),
                   'pages add up to the whole list, nothing skipped or repeated');
reset role;
-- Ghana days, both ends included, whatever the session's time zone: a note
-- at 23:59:59 yesterday (Ghana) and one at 00:00:00 today.
select (now() at time zone 'Africa/Accra')::date as gtoday \gset
insert into public.invoice_notes (invoice_id, body, created_by, created_at)
values (:inv1, 'boundary late', '11111111-1111-1111-1111-111111111111', ((:'gtoday'::date - 1)::timestamp + interval '23:59:59') at time zone 'Africa/Accra'),
       (:inv1, 'boundary early', '11111111-1111-1111-1111-111111111111', (:'gtoday'::date::timestamp) at time zone 'Africa/Accra');
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
set role authenticated;
set timezone = 'Pacific/Kiritimati';
select tcp_test.ok((select array_agg(e->>'body') from jsonb_array_elements(public.search_notes('boundary', null, null, :'gtoday'::date - 1, :'gtoday'::date - 1)->'rows') e) = array['boundary late']
                   and (select array_agg(e->>'body') from jsonb_array_elements(public.search_notes('boundary', null, null, :'gtoday'::date, :'gtoday'::date)->'rows') e) = array['boundary early'],
                   'Ghana days: 23:59:59 is the day before, 00:00 the day itself (UTC+14 session)');
set timezone = 'Etc/GMT+12';
select tcp_test.ok((select count(*) from jsonb_array_elements(public.search_notes('boundary', null, null, :'gtoday'::date - 1, :'gtoday'::date - 1)->'rows') e) = 1,
                   'the same in a UTC-12 session');
reset timezone;
select tcp_test.ok(jsonb_array_length(public.note_authors()) >= 3, 'note_authors lists the staff for the author filter');

-- ------------------------------------------------ H (part 2): snapshots unchanged
reset role;
select tcp_test.ok((select inv_doc from snap) = pg_temp.customer_view(public.invoice_document(:inv1)),
                   'the invoice document is unchanged by internal notes and their corrections');
select tcp_test.ok((select rct_doc from snap) = public.receipt_document(:p1) - 'internal_note_chain',
                   'the receipt document is unchanged by internal notes and their corrections');
reset role;
