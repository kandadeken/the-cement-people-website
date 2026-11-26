#!/usr/bin/env bash
# =============================================================================
# Existing invoices and receipts are unchanged by the Phase 2.2 migration
# (ChatGPT's review of PR #42, check 2).
#
# What it does
#   1. Builds a database as it was BEFORE Phase 2.2: every migration up to
#      Phase 2.1, the price list and the test staff.
#   2. Makes every kind of record there, the old way: a draft, unpaid, part
#      paid, paid, corrected, refunded and cancelled invoices, with the
#      delivery and estimate lines in the notes column, a note to the
#      customer, and one older invoice whose notes are longer than the new
#      600-character limit.
#   3. Saves what invoice_document and receipt_document return for each.
#      These are everything the invoice and receipt PDFs are drawn from.
#   4. Applies the Phase 2.2 migration (and any later ones).
#   5. Checks each document is exactly as before once the new keys are
#      taken out, and the new keys are empty (no notes yet). So every PDF
#      is drawn from the same data as before.
#   6. Checks the older records still work: the long-note invoice can still
#      be issued and cancelled (the 600 limit is only checked when the
#      notes themselves change), and payments still record on the others.
# =============================================================================
set -euo pipefail
DB="${TCP_TEST_DB:?run this through run-tests.sh}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OWNER="11111111-1111-1111-1111-111111111111"
P22="20261125120000"
OLD="${DB}_before_2_2"
PSQL=(psql -X -q -t -A -v ON_ERROR_STOP=1 --no-psqlrc)
fail() { echo "TEST FAILED: $1"; exit 1; }
as() { echo "set request.jwt.claim.sub = '$OWNER'; set role authenticated;"; }
q() { "${PSQL[@]}" -d "$OLD" -c "$1"; }
run() { "${PSQL[@]}" -d "$OLD" -c "$(as)" -c "$1"; }

# ---------------------------------------------- 1. the database before 2.2
createdb "$OLD"
trap 'dropdb --if-exists "$OLD" >/dev/null 2>&1 || true' EXIT
"${PSQL[@]}" -d "$OLD" -f "$HERE/tests/support/supabase_stub.sql" >/dev/null
for m in "$HERE"/migrations/*.sql; do
  [[ "$(basename "$m")" < "$P22" ]] && "${PSQL[@]}" -d "$OLD" -f "$m" >/dev/null
done
"${PSQL[@]}" -d "$OLD" -f "$HERE/seed.sql" >/dev/null
"${PSQL[@]}" -d "$OLD" -f "$HERE/tests/support/test_helpers.sql" >/dev/null
[ "$(q "select count(*) from pg_tables where tablename = 'invoice_notes'")" = "0" ] || fail "the old database already has Phase 2.2"

# ---------------------------------------------- 2. records made the old way
run "select public.create_customer('0241234567', 'Ama Mensah');" >/dev/null
LINES='[{"kind":"product","product_id":3,"quantity":10}]'
draft() {  # $1 = the notes column, as the Back Office writes it
  run "select public.save_draft_invoice(null, 1, 'Kasoa', null, null, null, \$n\$$1\$n\$, '$LINES'::jsonb);"
}
issue() { run "select public.issue_invoice($1);" >/dev/null; }
pay() { run "select (public.record_payment(p_invoice_id => $1, p_amount => $2, p_method => 'cash', p_paid_on => current_date)).id;"; }

I1=$(draft $'Customer pickup\nEstimate TCP-261120-MEBLV2')                      # stays a draft
I2=$(draft $'Free delivery\nEstimate TCP-261121-AB12CD\nPay to MoMo 024 000 0000'); issue "$I2"   # unpaid
I3=$(draft $'Customer pickup\nEstimate valid for 7 days'); issue "$I3"; pay "$I3" 100 >/dev/null  # part paid
I4=$(draft 'Thank you for your order'); issue "$I4"; pay "$I4" 400 >/dev/null; pay "$I4" 350 >/dev/null  # paid
I5=$(draft ''); issue "$I5"; P5=$(pay "$I5" 300)
run "select public.correct_payment(p_payment_id => $P5, p_reason => 'Wrong amount');" >/dev/null       # corrected
pay "$I5" 200 >/dev/null
I6=$(draft 'Refund test'); issue "$I6"; P6=$(pay "$I6" 750)
run "select public.refund_payment(p_payment_id => $P6, p_amount => 50, p_method => 'cash', p_reason => 'Short delivery');" >/dev/null
I7=$(draft 'To be cancelled'); issue "$I7"
run "select public.cancel_invoice($I7, 'Customer changed their mind');" >/dev/null                    # cancelled
LONG="$(printf 'x%.0s' $(seq 1 800))"
I8=$(draft "Free delivery"$'\n'"$LONG")                                              # longer than 600
INVOICES="$I1 $I2 $I3 $I4 $I5 $I6 $I7 $I8"
RECEIPTS="$(q "select string_agg(id::text, ' ' order by id) from public.payments")"

# ---------------------------------------------- 3. the documents before
snap() {  # the documents as JSON text, one per line (key order is fixed by jsonb)
  for i in $INVOICES; do run "select 'inv $i ' || public.invoice_document($i)::text;"; done
  for p in $RECEIPTS; do run "select 'rct $p ' || public.receipt_document($p)::text;"; done
}
snap > "/tmp/$OLD.before"

# ---------------------------------------------- 4. apply Phase 2.2 (and later)
for m in "$HERE"/migrations/*.sql; do
  [[ "$(basename "$m")" < "$P22" ]] || "${PSQL[@]}" -d "$OLD" -f "$m" >/dev/null
done

# ---------------------------------------------- 5. the same documents after
# The new keys are taken out of the new documents (and checked empty); what
# is left must be exactly the old document. (Phase 2.3 adds two more keys to
# the invoice document, credited and credit_notes; test 26 checks those.)
strip() {
  run "select 'inv $1 ' || (public.invoice_document($1)
         #- '{internal_notes}' #- '{credited}' #- '{credit_notes}'
         || jsonb_build_object('payments', coalesce((select jsonb_agg(p - 'customer_note' - 'internal_note' - 'recorded_at' - 'internal_note_chain')
                                                      from jsonb_array_elements(public.invoice_document($1)->'payments') p), '[]'::jsonb)))::text;"
}
{
  for i in $INVOICES; do strip "$i"; done
  for p in $RECEIPTS; do
    run "select 'rct $p ' || (public.receipt_document($p) - 'customer_note' - 'internal_note' - 'recorded_at' - 'internal_note_chain')::text;"
  done
} > "/tmp/$OLD.after"
if ! diff -q "/tmp/$OLD.before" "/tmp/$OLD.after" >/dev/null; then
  diff "/tmp/$OLD.before" "/tmp/$OLD.after" | head -6 | tr '\n' ' ' | cut -c1-1500
  fail "a document changed after the migration (diff above)"
fi
[ "$(grep -c . "/tmp/$OLD.after")" = "16" ] && [ "$(echo $RECEIPTS | wc -w)" = "8" ] || fail "expected 8 invoices and 8 receipts compared"
for i in $INVOICES; do
  [ "$(run "select public.invoice_document($i)->'internal_notes' = '[]'::jsonb
              and not exists (select 1 from jsonb_array_elements(public.invoice_document($i)->'payments') p
                              where p->>'customer_note' is not null or p->>'internal_note' is not null
                                 or p->'internal_note_chain' <> '[]'::jsonb);")" = "t" ] || fail "invoice $i has notes it never had"
done
rm -f "/tmp/$OLD.before" "/tmp/$OLD.after"

# ---------------------------------------------- 6. older records still work
# The long-note invoice: issued and cancelled after the migration, without
# changing its notes. A changed long note is refused.
issue "$I8" || fail "the older long-note invoice could not be issued"
run "select public.cancel_invoice($I8, 'Test of an older invoice');" >/dev/null || fail "the older long-note invoice could not be cancelled"
[ "$(q "select char_length(notes) from public.invoices where id = $I8")" -gt 600 ] || fail "the long note was changed"
I9=$(draft "Free delivery"$'\n'"$LONG" 2>&1) && fail "a new 800-character note was accepted"
echo "$I9" | grep -q "too long: at most 600 characters" || fail "unexpected refusal: $I9"
# Old invoices take payments, old-style calls (no notes) included.
pay "$I2" 100 >/dev/null || fail "a payment on an older invoice failed"
pay "$I3" 50 >/dev/null || fail "a second payment on an older part-paid invoice failed"
[ "$(run "select (d->>'total')::numeric - (d->>'balance')::numeric = 150 from (select public.invoice_document($I3) d) x;")" = "t" ] || fail "the part-paid balance is wrong"
echo "ok: $(echo $INVOICES | wc -w) invoices and $(echo $RECEIPTS | wc -w) receipts unchanged"
