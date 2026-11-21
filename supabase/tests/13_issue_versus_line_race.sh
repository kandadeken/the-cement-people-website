#!/usr/bin/env bash
# =============================================================================
# Issuing an invoice while someone changes its lines at the same moment
# (added after ChatGPT's review of PR #33).
#
# The timing is made certain, not left to luck: one connection starts its
# action and holds it open for 2 seconds before saving; the other acts during
# that window. Both orders are tested.
#
#   A. Issue first (held open), then remove a line: the removal must wait and
#      then be refused. The issued invoice keeps both lines.
#   B. Line change first (held open), then issue: issuing must wait, then
#      issue the invoice WITH the new line included in its total.
# =============================================================================
set -euo pipefail
DB="${TCP_TEST_DB:?run this through run-tests.sh}"
OWNER="11111111-1111-1111-1111-111111111111"
LOGIN="set request.jwt.claim.sub = '$OWNER'; set role authenticated;"
q() { psql -X -q -t -A -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
fail() { echo "TEST FAILED: $1"; exit 1; }

psql -X -q -v ON_ERROR_STOP=1 -d "$DB" -c "$LOGIN" \
  -c "select public.create_customer('0241234567', 'Kwame Mensah');" \
  -c "select public.create_draft_invoice(1); select public.add_invoice_line(1, 'product', 1, 1); select public.add_invoice_line(1, 'product', 2, 1);" \
  -c "select public.create_draft_invoice(1); select public.add_invoice_line(2, 'product', 1, 1);" >/dev/null

# ------------------------------------------------ A. issue first, then remove
line2="$(q "select id from public.invoice_lines where invoice_id = 1 and position = 2")"
psql -X -q -v ON_ERROR_STOP=1 -d "$DB" -c "$LOGIN" \
  -c "begin; select public.issue_invoice(1); select pg_sleep(2); commit;" >/dev/null &
issuer=$!
sleep 0.7
# The removal must be REFUSED, with the database's own reason. ON_ERROR_STOP
# makes psql exit with a non-zero status on any SQL error, and the message is
# checked too, so an unrelated error can't pass for the expected refusal.
if removal_output="$(psql -X -q -v ON_ERROR_STOP=1 -d "$DB" -c "$LOGIN" \
      -c "select public.remove_invoice_line($line2);" 2>&1)"; then
  wait $issuer
  fail "a line was removed from an invoice while it was being issued"
fi
echo "$removal_output" | grep -q "Lines can only change while the invoice is a draft" \
  || fail "removal refused for the wrong reason: $removal_output"
wait $issuer || fail "issuing invoice 1 failed"
[ "$(q "select state from public.invoices where id = 1")" = "issued" ] || fail "invoice 1 not issued"
[ "$(q "select count(*) from public.invoice_lines where invoice_id = 1")" = "2" ] || fail "invoice 1 lost a line"
[ "$(q "select total from public.invoice_summary where id = 1")" = "225.00" ] || fail "invoice 1 total wrong"

# ------------------------------------------------ B. add a line first, then issue
psql -X -q -v ON_ERROR_STOP=1 -d "$DB" -c "$LOGIN" \
  -c "begin; select public.add_invoice_line(2, 'product', 3, 1); select pg_sleep(2); commit;" >/dev/null &
adder=$!
sleep 0.7
psql -X -q -v ON_ERROR_STOP=1 -d "$DB" -c "$LOGIN" -c "select public.issue_invoice(2);" >/dev/null || fail "issuing invoice 2 failed"
wait $adder || fail "adding the line before issue failed"
[ "$(q "select count(*) from public.invoice_lines where invoice_id = 2")" = "2" ] || fail "invoice 2 should have 2 lines"
[ "$(q "select total from public.invoice_summary where id = 2")" = "300.00" ] || fail "invoice 2 total should include the new line"

echo "issue-versus-line race checks passed"
