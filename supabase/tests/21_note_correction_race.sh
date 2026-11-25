#!/usr/bin/env bash
# =============================================================================
# Two staff correct the same note at the same moment (Phase 2.2 design v1.5,
# "One straight line of corrections"). The timing is made certain: the first
# correction is held open for 2 seconds before it is saved; the second is
# sent meanwhile. The database must keep only the first and refuse the
# second with a message naming who corrected it, for an invoice note and for
# a payment's internal note.
# =============================================================================
set -euo pipefail
DB="${TCP_TEST_DB:?run this through run-tests.sh}"
OWNER="11111111-1111-1111-1111-111111111111"
FIN="33333333-3333-3333-3333-333333333333"
as() { echo "set request.jwt.claim.sub = '$1'; set role authenticated;"; }
q() { psql -X -q -t -A -v ON_ERROR_STOP=1 -d "$DB" -c "$1"; }
run() { psql -X -q -t -A -v ON_ERROR_STOP=1 -d "$DB" -c "$(as "$1")" -c "$2"; }
fail() { echo "TEST FAILED: $1"; exit 1; }

run "$OWNER" "select public.create_customer('0241234567', 'Kwame Mensah');" >/dev/null
run "$OWNER" "select public.save_draft_invoice(null, 1, null, null, null, null, null, '[{\"kind\":\"product\",\"product_id\":3,\"quantity\":10}]'::jsonb);" >/dev/null
run "$OWNER" "select public.issue_invoice(1);" >/dev/null
run "$OWNER" "select public.add_invoice_note(1, 'Paid by his brother Kwame.');" >/dev/null
run "$OWNER" "select public.record_payment(1, 100, 'cash', null, current_date, null, null, 'Cash from the site manager');" >/dev/null

race() {  # $1 = what is corrected ("null, 1" for note 1, "null, null, 1" style args), $2 = label
  psql -X -q -t -A -v ON_ERROR_STOP=1 -d "$DB" -c "$(as "$OWNER")" \
    -c "begin; select public.add_invoice_note(1, 'Owner: it was Kofi', null, $1); select pg_sleep(2); commit;" >/dev/null &
  first=$!
  sleep 0.7
  if second="$(run "$FIN" "select public.add_invoice_note(1, 'Finance: it was Kojo', null, $1);" 2>&1)"; then
    fail "$2: the competing correction was saved too"
  fi
  echo "$second" | grep -q "just corrected by Test Owner" || fail "$2: unexpected refusal: $second"
  wait $first || fail "$2: the first correction failed"
}

# ---------------------------------------------- A. an invoice note
race "1" "invoice note"
[ "$(q "select count(*) from public.invoice_notes where corrects_note_id = 1")" = "1" ] || fail "two corrections of note 1"
[ "$(q "select body from public.invoice_notes where corrects_note_id = 1")" = "Owner: it was Kofi" ] || fail "the wrong correction was kept"

# ---------------------------------------------- B. a payment's internal note
race "null, 1" "payment note"
[ "$(q "select count(*) from public.invoice_notes where corrects_payment_id = 1")" = "1" ] || fail "two corrections of the payment note"

# The line goes on from the latest: correcting the correction works.
run "$FIN" "select public.add_invoice_note(1, 'Finance: Kojo, on second thoughts', null, (select id from public.invoice_notes where corrects_note_id = 1));" >/dev/null \
  || fail "correcting the latest correction was refused"
[ "$(q "select count(*) from public.invoice_notes")" = "4" ] || fail "expected 4 notes in all"
echo "ok"
