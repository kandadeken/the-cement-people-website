-- Phase 2.2: search_notes over 50,000 notes on 5,000 invoices (design v1.6,
-- "What fails the test, and what only reports").
--   Hard checks (fail the test): the results are right in every case; the
--   rare-word search uses the trigram index (from the query plan).
--   Measured (reported): every case's real execution time, printed as a
--   TIMING line. Over 300 ms is a warning to look into; only over 3 seconds
--   fails, as that means something is badly wrong, not a slow machine.
--   A common word may use a full scan (Postgres rightly prefers it when a
--   word is in a third of the notes), so its plan is not checked.
\set QUIET on

set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
set role authenticated;
select (public.create_customer('0241234567', 'Speed Test')).id as cust \gset
reset role;

-- 5,000 draft invoices and 50,000 notes, made directly (fast, test only).
insert into public.invoices (customer_id, created_by)
select :cust, '11111111-1111-1111-1111-111111111111' from generate_series(1, 5000);
insert into public.invoice_notes (invoice_id, body, category, created_by, created_at)
select (select min(id) from public.invoices) + (g % 5000),
       concat_ws(' ',
         (array['Customer','Site manager','Driver','Ama','Kofi'])[1 + g % 5],
         (array['called about','asked for','confirmed','queried','wants'])[1 + (g / 5) % 5],
         case when g % 10 < 3 then 'cement' end,
         (array['delivery','payment','rods','blocks','sand','balance'])[1 + (g / 25) % 6],
         case when g % 1000 = 7 then 'zebrafinch' end,
         'on ' || to_char(date '2026-01-01' + (g % 330), 'DD Mon'),
         'ref ' || md5(g::text)),
       (array['general','payment','delivery','customer_request','complaint','stock','follow_up'])[1 + g % 7],
       (array['11111111-1111-1111-1111-111111111111','22222222-2222-2222-2222-222222222222','33333333-3333-3333-3333-333333333333'])[1 + g % 3]::uuid,
       timestamptz '2026-01-01 08:00+00' + (g % 330) * interval '1 day' + (g % 600) * interval '1 minute'
  from generate_series(1, 50000) g;
analyze public.invoice_notes;
analyze public.invoices;
analyze public.payments;

-- Hard: the rare-word search reads the trigram index, not every note.
do $$
declare
  p text := '';
  l record;
begin
  for l in execute $q$explain select id from public.invoice_notes where body ilike '%zebrafinch%'$q$ loop
    p := p || l."QUERY PLAN" || E'\n';
  end loop;
  if p !~ 'invoice_notes_body_trgm' then
    raise exception 'TEST FAILED: the rare-word search does not use the trigram index:%', E'\n' || p;
  end if;
end $$;

create temp table timings (name text, ms numeric, rows int, count int);
grant all on timings to authenticated;

set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
set role authenticated;
do $$
declare
  c record;
  t0 timestamptz;
  r jsonb;
begin
  for c in select * from (values
      ('common word',                        'cement',          null,       null::uuid,                              null::date,    null::date,    0),
      ('rare word',                          'zebrafinch',      null,       null,                                    null,          null,          0),
      ('two words',                          'cement balance',  null,       null,                                    null,          null,          0),
      ('author + dates + category',          null,              'payment',  '33333333-3333-3333-3333-333333333333', date '2026-03-01', date '2026-05-31', 0),
      ('author + dates + category + word',   'cement',          'payment',  '33333333-3333-3333-3333-333333333333', date '2026-03-01', date '2026-05-31', 0),
      ('common word, page 50',               'cement',          null,       null,                                    null,          null,          1470)
    ) v(name, words, category, author, d_from, d_to, off) loop
    t0 := clock_timestamp();
    r := public.search_notes(c.words, c.category, c.author, c.d_from, c.d_to, false, c.off, 30);
    insert into timings values (c.name, round(extract(epoch from clock_timestamp() - t0) * 1000, 1),
                                jsonb_array_length(r -> 'rows'), (r ->> 'count')::int);
  end loop;
end $$;
reset role;

-- Hard: the results are right.
select tcp_test.ok((select count from timings where name = 'rare word') = 50
                   and (select rows from timings where name = 'rare word') = 30, 'rare word: 50 notes, a page of 30');
select tcp_test.ok((select count from timings where name = 'common word') = 15000, 'common word: 15,000 notes (30%)');
select tcp_test.ok((select count from timings where name = 'two words')
                   = (select count(*) from public.invoice_notes where body ilike '%cement%' and body ilike '%balance%'),
                   'two words: both must appear');
select tcp_test.ok((select count from timings where name = 'author + dates + category')
                   = (select count(*) from public.invoice_notes where category = 'payment'
                        and created_by = '33333333-3333-3333-3333-333333333333'
                        and created_at >= date '2026-03-01'::timestamp at time zone 'Africa/Accra'
                        and created_at <  date '2026-06-01'::timestamp at time zone 'Africa/Accra'),
                   'author, dates and category together');
select tcp_test.ok((select rows from timings where name = 'common word, page 50') = 30, 'page 50 has 30 rows');

-- Measured: printed with the test results; a warning over 300 ms; a
-- failure only over 3 seconds.
do $$
declare
  t record;
begin
  for t in select * from timings loop
    raise notice 'TIMING  % : % ms (% of % matches)%', rpad(t.name, 34), t.ms, t.rows, t.count,
      case when t.ms > 300 then '  WARNING: over the 300 ms target, look into it' else '' end;
    if t.ms > 3000 then
      raise exception 'TEST FAILED: % took % ms, over 3 seconds', t.name, t.ms;
    end if;
  end loop;
end $$;
