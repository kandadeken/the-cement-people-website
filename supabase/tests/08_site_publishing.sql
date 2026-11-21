-- Sending price changes to the website, with its safeguards.
\set QUIET on

-- Loading the starting price list queued exactly one request.
select tcp_test.ok((select count(*) from public.site_publish_requests) = 1, 'one request after the seed');
select tcp_test.ok((select website_out_of_date from public.site_price_status), 'out of date until published');

-- The server (service_role) picks it up and reports success.
set role service_role;
select (public.claim_site_publish()).id as req \gset
select public.finish_site_publish(:req, true);
reset role;
select tcp_test.ok(not (select website_out_of_date from public.site_price_status), 'up to date after success');
select tcp_test.ok((select last_successful_publish from public.site_price_status) is not null, 'last success recorded');

-- Nothing waiting: claiming returns nothing.
set role service_role;
select tcp_test.ok((public.claim_site_publish()).id is null, 'nothing to send');
reset role;

-- Several price changes in a row: still only one waiting request.
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
set role authenticated;
select public.save_product('c1', 'Supacem 32.5R', 'Cement', '50 kg bag', 76);
select public.save_product('c2', 'Supacem 42.5R', 'Cement', '50 kg bag', 99);
select public.save_product('c3', 'Dzata 42.5R', 'Cement', '50 kg bag', 111);
reset role;
select tcp_test.ok((select count(*) from public.site_publish_requests where status = 'pending') = 1,
                   'repeat changes do not pile up');
select tcp_test.ok((select website_out_of_date from public.site_price_status), 'out of date again');

-- Cloudflare fails: the request goes back to wait for a retry, error kept.
set role service_role;
select (public.claim_site_publish()).id as req \gset
select public.finish_site_publish(:req, false, 'Cloudflare 503');
reset role;
select tcp_test.ok((select status from public.site_publish_requests where id = :req) = 'pending', 'retry pending');
select tcp_test.ok((select last_error from public.site_publish_requests where id = :req) = 'Cloudflare 503', 'error kept');
select tcp_test.ok((select attempts from public.site_publish_requests where id = :req) = 1, 'attempt counted');

-- After 5 failed attempts it is marked failed and the status says so.
set role service_role;
select public.claim_site_publish(); select public.finish_site_publish(:req, false, 'Cloudflare 503');
select public.claim_site_publish(); select public.finish_site_publish(:req, false, 'Cloudflare 503');
select public.claim_site_publish(); select public.finish_site_publish(:req, false, 'Cloudflare 503');
select public.claim_site_publish(); select public.finish_site_publish(:req, false, 'Cloudflare 503');
reset role;
select tcp_test.ok((select status from public.site_publish_requests where id = :req) = 'failed', 'gave up after 5');
select tcp_test.ok((select failed_requests from public.site_price_status) = 1, 'failure visible');
select tcp_test.ok((select website_out_of_date from public.site_price_status), 'still flagged out of date');

-- Reporting on a request that isn't being sent is refused (no double reports).
set role service_role;
select tcp_test.fails(format('select public.finish_site_publish(%s, true)', :req), 'is being sent');
reset role;

-- The next price change starts a fresh request, which can succeed.
set role authenticated;
select public.save_product('c1', 'Supacem 32.5R', 'Cement', '50 kg bag', 77);
reset role;
set role service_role;
select (public.claim_site_publish()).id as req2 \gset
select public.finish_site_publish(:req2, true);
reset role;
select tcp_test.ok(not (select website_out_of_date from public.site_price_status), 'up to date again');

-- The catalogue shows the new price.
set role anon;
select tcp_test.ok((select price from public.public_catalogue where site_id = 'c1') = 77.00, 'catalogue shows new price');
reset role;
