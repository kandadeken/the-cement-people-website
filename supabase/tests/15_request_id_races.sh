#!/usr/bin/env bash
# =============================================================================
# The same request arriving twice at the same moment (Design v2.1, point A):
# a phone retries while the first try is still being processed. The timing
# is made certain: the first call is held open for 2 seconds before it saves.
#
#   A. two payments with the same request id  -> one receipt
#   B. two refunds with the same request id   -> one refund
#   C. two new drafts with the same request id -> one draft
# =============================================================================
set -euo pipefail
DB="${TCP_TEST_DB:?run this through run-tests.sh}"
OWNER="11111111-1111-1111-1111-111111111111"
LOGIN="set request.jwt.claim.sub = '$OWNER'; set role authenticated;"
q() { psql -X -q -t -A -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
run() { psql -X -q -t -A -v ON_ERROR_STOP=1 -d "$DB" -c "$LOGIN" -c "$1"; }
fail() { echo "TEST FAILED: $1"; exit 1; }

run "select public.create_customer('0241234567', 'Kwame Mensah');" >/dev/null
run "select public.save_draft_invoice(null, 1, null, null, null, null, null, '[{\"kind\":\"product\",\"product_id\":3,\"quantity\":10}]'::jsonb);" >/dev/null
run "select public.issue_invoice(1);" >/dev/null

# ---------------------------------------------- A. same payment, twice at once
PAY="select (public.record_payment(1, 500, 'cash', null, current_date, 'e0000000-0000-4000-8000-000000000001')).receipt_no"
psql -X -q -t -A -v ON_ERROR_STOP=1 -d "$DB" -c "$LOGIN" \
  -c "begin; $PAY; select pg_sleep(2); commit;" > /tmp/tcp_ra1_$$ &
first=$!
sleep 0.7
second_out="$(run "$PAY;")" || fail "the repeated payment was refused instead of answered"
wait $first || fail "the first payment failed"
[ "$(q "select count(*) from public.payments")" = "1" ] || fail "two payments recorded for one request id"
grep -q "TCP-RCT-0001" /tmp/tcp_ra1_$$ || fail "first call did not get TCP-RCT-0001"
[ "$second_out" = "TCP-RCT-0001" ] || fail "repeat got '$second_out' instead of the same receipt"
rm -f /tmp/tcp_ra1_$$

# ---------------------------------------------- B. same refund, twice at once
REF="select (public.refund_payment(1, 100, 'cash', 'returned', null, 'e0000000-0000-4000-8000-000000000002')).receipt_no"
psql -X -q -t -A -v ON_ERROR_STOP=1 -d "$DB" -c "$LOGIN" \
  -c "begin; $REF; select pg_sleep(2); commit;" >/dev/null &
first=$!
sleep 0.7
second_out="$(run "$REF;")" || fail "the repeated refund was refused instead of answered"
wait $first || fail "the first refund failed"
[ "$(q "select count(*) from public.payments where kind = 'refund'")" = "1" ] || fail "two refunds recorded for one request id"
[ "$second_out" = "TCP-RCT-0002" ] || fail "repeat refund got '$second_out'"

# ---------------------------------------------- C. same new draft, twice at once
DRAFT="select public.save_draft_invoice(null, 1, null, null, null, null, null, '[{\"kind\":\"product\",\"product_id\":1,\"quantity\":1}]'::jsonb, 'e0000000-0000-4000-8000-000000000003')"
psql -X -q -t -A -v ON_ERROR_STOP=1 -d "$DB" -c "$LOGIN" \
  -c "begin; $DRAFT; select pg_sleep(2); commit;" >/dev/null &
first=$!
sleep 0.7
# The second call waits for the first; it then either returns the same draft
# or is refused by the unique request id. Either way: never a second draft.
run "$DRAFT;" >/dev/null 2>&1 || true
wait $first || fail "the first draft save failed"
[ "$(q "select count(*) from public.invoices where request_id = 'e0000000-0000-4000-8000-000000000003'")" = "1" ] \
  || fail "two drafts for one request id"
[ "$(q "select count(*) from public.invoices")" = "2" ] || fail "unexpected number of invoices"

echo "request-id race checks passed"
