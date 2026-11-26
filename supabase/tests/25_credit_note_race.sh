#!/usr/bin/env bash
# =============================================================================
# Credit notes at the same moment (Phase 2.3 specification v1.4, test 25).
# The timing is made certain: the first call is held open for 2 seconds
# before it is saved; the second is sent meanwhile.
#   A. Two credit notes for the last value on one line: one wins, the other
#      is refused with what is left.
#   B. Two adjustments that together pass the invoice total: one wins.
#   C. Two cancellations of one credit note: one wins.
#   D. A credit note being issued holds the switch: a switch-off waits until
#      the credit note is saved, then takes effect.
#   E. A switch-off being saved holds the switch: a credit note sent
#      meanwhile waits, then is refused ("not switched on").
#   F. A cancellation is never held up by the switch, even while the switch
#      row is locked.
# =============================================================================
set -euo pipefail
DB="${TCP_TEST_DB:?run this through run-tests.sh}"
OWNER="11111111-1111-1111-1111-111111111111"
FIN="33333333-3333-3333-3333-333333333333"
as() { echo "set request.jwt.claim.sub = '$1'; set role authenticated;"; }
q() { psql -X -q -t -A -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
run() { psql -X -q -t -A -v ON_ERROR_STOP=1 -d "$DB" -c "$(as "$1")" -c "$2"; }
fail() { echo "TEST FAILED: $1"; exit 1; }
now() { date +%s.%N; }
secs() { awk -v a="$1" -v b="$2" 'BEGIN { printf "%.2f", b - a }'; }   # seconds between two now() readings
more() { awk -v a="$1" -v b="$2" 'BEGIN { exit !(a > b) }'; }    # true if $1 > $2

# Held: run $2 as $1 inside a transaction kept open for 2 seconds.
held() { psql -X -q -t -A -v ON_ERROR_STOP=1 -d "$DB" -c "$(as "$1")" -c "begin; $2; select pg_sleep(2); commit;" >/dev/null; }
issue() {  # $1 = who, $2 = invoice, $3 = lines json
  echo "select (public.issue_credit_note(p_invoice_id => $2, p_lines => '$3'::jsonb, p_reason => 'Race', p_request_id => gen_random_uuid())).id"
}

LINES='[{"kind":"product","product_id":3,"quantity":10}]'
run "$OWNER" "select public.create_customer('0241234567', 'Kwame Mensah');" >/dev/null
for i in 1 2 3 4 5; do
  run "$OWNER" "select public.save_draft_invoice(null, 1, null, null, null, null, null, '$LINES'::jsonb);" >/dev/null
  run "$OWNER" "select public.issue_invoice($i);" >/dev/null
done
run "$OWNER" "select public.set_credit_notes_switch(true, 'Race test', gen_random_uuid());" >/dev/null
L1=$(q "select id from public.invoice_lines where invoice_id = 1")
L4=$(q "select id from public.invoice_lines where invoice_id = 4")
L5=$(q "select id from public.invoice_lines where invoice_id = 5")

# ---------------------------------------------- A. the last value on one line
SIX="[{\"invoice_line_id\":$L1,\"kind\":\"quantity\",\"why\":\"returned\",\"quantity\":6}]"
held "$FIN" "$(issue "$FIN" 1 "$SIX")" & first=$!
sleep 0.7
if second="$(run "$OWNER" "$(issue "$OWNER" 1 "$SIX")" 2>&1)"; then fail "A: both credit notes for 6 of 10 bags were saved"; fi
echo "$second" | grep -q "Only 4 bags are left to credit" || fail "A: unexpected refusal: $second"
wait $first || fail "A: the first credit note failed"
[ "$(q "select count(*) from public.credit_notes where invoice_id = 1")" = "1" ] || fail "A: expected one credit note"

# ---------------------------------------------- B. the invoice total
ADJ='[{"kind":"adjustment","why":"price_adjustment","amount":700}]'
held "$OWNER" "$(issue "$OWNER" 2 "$ADJ")" & first=$!
sleep 0.7
if second="$(run "$OWNER" "$(issue "$OWNER" 2 "$ADJ")" 2>&1)"; then fail "B: two adjustments of 700 on a 1,100 invoice were saved"; fi
echo "$second" | grep -q "more than the invoice is worth" || fail "B: unexpected refusal: $second"
wait $first || fail "B: the first adjustment failed"
[ "$(q "select credited from public.invoice_summary where id = 2")" = "700.00" ] || fail "B: expected 700 credited"

# ---------------------------------------------- C. two cancellations
CN=$(q "select id from public.credit_notes where invoice_id = 2")
held "$OWNER" "select public.cancel_credit_note($CN, 'First', gen_random_uuid())" & first=$!
sleep 0.7
if second="$(run "$OWNER" "select public.cancel_credit_note($CN, 'Second', gen_random_uuid());" 2>&1)"; then
  fail "C: the credit note was cancelled twice"
fi
echo "$second" | grep -q "already cancelled" || fail "C: unexpected refusal: $second"
wait $first || fail "C: the first cancellation failed"
[ "$(q "select reason from public.credit_note_cancellations where credit_note_id = $CN")" = "First" ] || fail "C: the wrong cancellation was kept"

# ---------------------------------------------- D. issuing holds the switch
TWO4="[{\"invoice_line_id\":$L4,\"kind\":\"quantity\",\"why\":\"returned\",\"quantity\":2}]"
held "$FIN" "$(issue "$FIN" 4 "$TWO4")" & first=$!
sleep 0.7
t0=$(now)
run "$OWNER" "select public.set_credit_notes_switch(false, 'Switch off during an issue', gen_random_uuid());" >/dev/null \
  || fail "D: the switch-off failed"
t1=$(now)
wait $first || fail "D: the credit note being issued failed"
more "$(secs "$t0" "$t1")" 0.8 || fail "D: the switch-off did not wait for the credit note being issued ($(secs "$t0" "$t1") s)"
[ "$(q "select count(*) from public.credit_notes where invoice_id = 4")" = "1" ] || fail "D: the credit note was not saved"
[ "$(q "select is_on from tcp_private.feature_switches")" = "f" ] || fail "D: the switch is not off"

# ---------------------------------------------- E. switching off holds the switch
run "$OWNER" "select public.set_credit_notes_switch(true, 'Back on', gen_random_uuid());" >/dev/null
held "$OWNER" "select public.set_credit_notes_switch(false, 'Switch off first', gen_random_uuid())" & first=$!
sleep 0.7
t0=$(now)
TWO5="[{\"invoice_line_id\":$L5,\"kind\":\"quantity\",\"why\":\"returned\",\"quantity\":2}]"
if second="$(run "$FIN" "$(issue "$FIN" 5 "$TWO5")" 2>&1)"; then fail "E: a credit note was issued while the switch was being turned off"; fi
t1=$(now)
echo "$second" | grep -q "Credit notes are not switched on" || fail "E: unexpected refusal: $second"
more "$(secs "$t0" "$t1")" 0.8 || fail "E: the credit note did not wait for the switch-off ($(secs "$t0" "$t1") s)"
wait $first || fail "E: the switch-off failed"
[ "$(q "select count(*) from public.credit_notes where invoice_id = 5")" = "0" ] || fail "E: a credit note was saved"

# ---------------------------------------------- F. cancelling ignores the switch
CN4=$(q "select id from public.credit_notes where invoice_id = 4")
psql -X -q -t -A -v ON_ERROR_STOP=1 -d "$DB" \
  -c "begin; select 1 from tcp_private.feature_switches for update; select pg_sleep(3); commit;" >/dev/null & first=$!
sleep 0.7
t0=$(now)
run "$OWNER" "select public.cancel_credit_note($CN4, 'Cancelled while the switch is locked', gen_random_uuid());" >/dev/null \
  || fail "F: the cancellation failed"
t1=$(now)
more 1.0 "$(secs "$t0" "$t1")" || fail "F: the cancellation waited for the switch ($(secs "$t0" "$t1") s)"
wait $first
[ "$(q "select count(*) from public.credit_note_cancellations where credit_note_id = $CN4")" = "1" ] || fail "F: not cancelled"
echo "ok"
