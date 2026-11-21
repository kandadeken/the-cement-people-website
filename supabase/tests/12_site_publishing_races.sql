-- Website publishing: changes during a build, non-price changes, stuck
-- requests (all added after ChatGPT's review of PR #33).
\set QUIET on

-- Start from "website up to date": publish the seed.
set role service_role;
select (public.claim_site_publish()).id as r0 \gset
select public.finish_site_publish(:r0, true);
reset role;
select tcp_test.ok(not (select website_out_of_date from public.site_price_status), 'up to date at start');

-- A NAME-only change (no price change) still makes the website out of date.
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
set role authenticated;
select public.save_product('c1', 'Supacem Supa Fast 32.5R', 'Cement', '50 kg bag', 75);
reset role;
select tcp_test.ok((select website_out_of_date from public.site_price_status), 'name change flags out of date');
select tcp_test.ok((select last_change from public.site_price_status) like 'Product c1%', 'what changed is shown');

-- Unpublishing or hiding a price counts too.
set role service_role;
select (public.claim_site_publish()).id as r1 \gset
select public.finish_site_publish(:r1, true);
reset role;
set role authenticated;
select public.save_product('c2', 'Supacem 42.5R', 'Cement', '50 kg bag', 98, true, false);   -- hide price
reset role;
select tcp_test.ok((select website_out_of_date from public.site_price_status), 'hiding a price flags out of date');

-- THE RACE: a build starts, then a product changes while it runs.
set role service_role;
select (public.claim_site_publish()).id as r2 \gset
reset role;
set role authenticated;
select public.save_product('c3', 'Dzata 42.5R', 'Cement', '50 kg bag', 115);   -- during the build
reset role;
-- The change during the build queued a fresh request (not lost).
select tcp_test.ok((select count(*) from public.site_publish_requests where status = 'pending') = 1,
                   'change during a build queues a new request');
-- Only one build at a time: nothing else can be claimed while one is sending.
set role service_role;
select tcp_test.ok((public.claim_site_publish()).id is null, 'no second build while one runs');
select public.finish_site_publish(:r2, true);
reset role;
-- The first build finished, but it started before the c3 change: still out of date.
select tcp_test.ok((select website_out_of_date from public.site_price_status),
                   'still out of date: last build started before the change');
-- The waiting request is sent next, and then the website is up to date.
set role service_role;
select (public.claim_site_publish()).id as r3 \gset
select tcp_test.ok(:r3 > :r2, 'the newer request is sent');
select public.finish_site_publish(:r3, true);
reset role;
select tcp_test.ok(not (select website_out_of_date from public.site_price_status), 'up to date after the second build');

-- A FAILED build while a newer request waits: superseded, not retried twice.
set role authenticated;
select public.save_product('c1', 'Supacem Supa Fast 32.5R', 'Cement', '50 kg bag', 76);
reset role;
set role service_role;
select (public.claim_site_publish()).id as r4 \gset
reset role;
set role authenticated;
select public.save_product('c1', 'Supacem Supa Fast 32.5R', 'Cement', '50 kg bag', 77);
reset role;
set role service_role;
select public.finish_site_publish(:r4, false, 'Cloudflare 500');
reset role;
select tcp_test.ok((select status from public.site_publish_requests where id = :r4) = 'superseded',
                   'failed build superseded by the newer waiting request');
select tcp_test.ok((select count(*) from public.site_publish_requests where status = 'pending') = 1,
                   'exactly one request waiting');

-- A STUCK build (the worker never reported back) is taken back after 15 minutes.
set role service_role;
select (public.claim_site_publish()).id as r5 \gset
reset role;
update public.site_publish_requests set claimed_at = clock_timestamp() - interval '16 minutes' where id = :r5;
set role service_role;
select (public.claim_site_publish()).id as r6 \gset
reset role;
select tcp_test.ok(:r6 = :r5, 'stuck request taken back and retried');
select tcp_test.ok((select attempts from public.site_publish_requests where id = :r5) = 2, 'retry counted');
select tcp_test.ok((select last_error from public.site_publish_requests where id = :r5) like 'No report%', 'reason recorded');

-- A stuck build when a newer request is already waiting: superseded.
set role authenticated;
select public.save_product('c1', 'Supacem Supa Fast 32.5R', 'Cement', '50 kg bag', 78);   -- queues pending
reset role;
update public.site_publish_requests set claimed_at = clock_timestamp() - interval '16 minutes' where id = :r5;
set role service_role;
select (public.claim_site_publish()).id as r7 \gset
select public.finish_site_publish(:r7, true);
reset role;
select tcp_test.ok((select status from public.site_publish_requests where id = :r5) = 'superseded', 'stuck one superseded');
select tcp_test.ok(not (select website_out_of_date from public.site_price_status), 'up to date in the end');
select tcp_test.ok((select count(*) from public.site_publish_requests where status in ('pending', 'sending')) = 0,
                   'nothing left waiting');

-- Changing something the public can't see (nothing) queues nothing.
set role authenticated;
select public.save_product('c1', 'Supacem Supa Fast 32.5R', 'Cement', '50 kg bag', 78);   -- identical
reset role;
select tcp_test.ok((select count(*) from public.site_publish_requests where status = 'pending') = 0,
                   'an identical save queues nothing');

-- A build that gets stuck EVERY time is not retried forever: after 5 attempts
-- (the same limit as reported failures) it is marked failed and stays visible.
set role authenticated;
select public.save_product('c1', 'Supacem Supa Fast 32.5R', 'Cement', '50 kg bag', 79);
reset role;
set role service_role;
select (public.claim_site_publish()).id as stuck \gset
reset role;
select tcp_test.ok((select attempts from public.site_publish_requests where id = :stuck) = 1, 'attempt 1');
-- Attempts 2 to 5: each time the worker never reports and 16 minutes pass.
update public.site_publish_requests set claimed_at = clock_timestamp() - interval '16 minutes' where id = :stuck;
set role service_role; select public.claim_site_publish(); reset role;
update public.site_publish_requests set claimed_at = clock_timestamp() - interval '16 minutes' where id = :stuck;
set role service_role; select public.claim_site_publish(); reset role;
update public.site_publish_requests set claimed_at = clock_timestamp() - interval '16 minutes' where id = :stuck;
set role service_role; select public.claim_site_publish(); reset role;
update public.site_publish_requests set claimed_at = clock_timestamp() - interval '16 minutes' where id = :stuck;
set role service_role; select public.claim_site_publish(); reset role;
select tcp_test.ok((select attempts from public.site_publish_requests where id = :stuck) = 5, '5 attempts used');
select tcp_test.ok((select status from public.site_publish_requests where id = :stuck) = 'sending', 'fifth attempt running');
-- The fifth attempt gets stuck too: the next check marks it failed, no 6th try.
update public.site_publish_requests set claimed_at = clock_timestamp() - interval '16 minutes' where id = :stuck;
set role service_role;
select tcp_test.ok((public.claim_site_publish()).id is null, 'no sixth attempt');
reset role;
select tcp_test.ok((select status from public.site_publish_requests where id = :stuck) = 'failed', 'marked failed after 5');
select tcp_test.ok((select attempts from public.site_publish_requests where id = :stuck) = 5, 'still 5 attempts');
select tcp_test.ok((select last_error from public.site_publish_requests where id = :stuck) like 'No report%', 'error kept');
select tcp_test.ok((select failed_requests from public.site_price_status) >= 1, 'failure visible');
select tcp_test.ok((select website_out_of_date from public.site_price_status), 'website shown as out of date');
