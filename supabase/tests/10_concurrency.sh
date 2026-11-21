#!/usr/bin/env bash
# =============================================================================
# Things happening at the same moment (needs several connections, so it is a
# shell script rather than a .sql file). Run by run-tests.sh, which provides
# TCP_TEST_DB and the connection settings.
#
#   1. 20 invoices issued at once from 20 connections: every number unique,
#      and 0001 to 0020 with no gaps.
#   2. Two payments that each fit the balance, but not together, arriving at
#      the same moment: exactly one succeeds, so no overpayment.
#   3. Two refunds of the same payment at once that together exceed it:
#      exactly one succeeds.
#   4. Two corrections of the same payment at once: exactly one succeeds.
# =============================================================================
set -euo pipefail
DB="${TCP_TEST_DB:?run this through run-tests.sh}"
OWNER="11111111-1111-1111-1111-111111111111"

# Run SQL as the owner, logged in through the web role.
as_owner() {
  psql -X -q -t -A -v ON_ERROR_STOP=1 -d "$DB" \
    -c "set request.jwt.claim.sub = '$OWNER'; set role authenticated;" -c "$1"
}
fail() { echo "TEST FAILED: $1"; exit 1; }

# ---------------------------------------------------------------- setup
as_owner "select public.create_customer('0241234567', 'Kwame Mensah');" >/dev/null
for i in $(seq 1 20); do
  as_owner "select public.create_draft_invoice(1);" >/dev/null
  as_owner "select public.add_invoice_line($i, 'product', 1, 1);" >/dev/null
done

# ------------------------------------- 1. 20 invoices issued at the same time
for i in $(seq 1 20); do
  as_owner "select pg_sleep(0.2); select public.issue_invoice($i);" >/dev/null &
done
wait
numbers="$(psql -X -t -A -d "$DB" -c "select string_agg(invoice_no, ',' order by invoice_no) from public.invoices")"
expected="$(for i in $(seq 1 20); do printf 'TCP-INV-%04d,' "$i"; done)"
[ "$numbers," = "$expected" ] || fail "invoice numbers not unique and gapless: $numbers"

# -------------------------- 2. two payments racing for the same balance
# Invoice 1 total is 75. Two payments of 50 at once: only one may succeed.
ok=0
for _ in 1 2; do
  ( as_owner "select pg_sleep(0.2); select public.record_payment(1, 50, 'cash');" >/dev/null 2>&1 && echo ok ) &
done > /tmp/tcp_race_payments_$$ ; wait
ok="$(grep -c ok /tmp/tcp_race_payments_$$ || true)"; rm -f /tmp/tcp_race_payments_$$
[ "$ok" = "1" ] || fail "expected exactly 1 of 2 racing payments to succeed, got $ok"
paid="$(psql -X -t -A -d "$DB" -c "select paid from public.invoice_summary where id = 1")"
[ "$paid" = "50.00" ] || fail "invoice 1 paid should be 50.00, is $paid"

# --------------------------- 3. two refunds racing past the original amount
pid="$(psql -X -t -A -d "$DB" -c "select id from public.payments where invoice_id = 1 and kind = 'payment'")"
for _ in 1 2; do
  ( as_owner "select pg_sleep(0.2); select public.refund_payment($pid, 30, 'cash', 'race');" >/dev/null 2>&1 && echo ok ) &
done > /tmp/tcp_race_refunds_$$ ; wait
ok="$(grep -c ok /tmp/tcp_race_refunds_$$ || true)"; rm -f /tmp/tcp_race_refunds_$$
[ "$ok" = "1" ] || fail "expected exactly 1 of 2 racing refunds (30+30 > 50) to succeed, got $ok"

# ------------------------------- 4. two corrections of the same payment
as_owner "select public.record_payment(2, 40, 'cash');" >/dev/null
pid2="$(psql -X -t -A -d "$DB" -c "select id from public.payments where invoice_id = 2 and kind = 'payment'")"
for _ in 1 2; do
  ( as_owner "select pg_sleep(0.2); select public.correct_payment($pid2, 'race');" >/dev/null 2>&1 && echo ok ) &
done > /tmp/tcp_race_corrections_$$ ; wait
ok="$(grep -c ok /tmp/tcp_race_corrections_$$ || true)"; rm -f /tmp/tcp_race_corrections_$$
[ "$ok" = "1" ] || fail "expected exactly 1 of 2 racing corrections to succeed, got $ok"

# Receipt numbers still unique and gapless after all the racing.
receipts="$(psql -X -t -A -d "$DB" -c "select string_agg(receipt_no, ',' order by receipt_no) from public.payments")"
count="$(psql -X -t -A -d "$DB" -c "select count(*) from public.payments")"
expected_r="$(for i in $(seq 1 "$count"); do printf 'TCP-RCT-%04d,' "$i"; done)"
[ "$receipts," = "$expected_r" ] || fail "receipt numbers not gapless: $receipts"

echo "concurrency checks passed"
