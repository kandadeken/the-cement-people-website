#!/usr/bin/env bash
# =============================================================================
# Existing records are unchanged by the Phase 2.3 migration, and the
# prepared full removal puts everything back (specification v1.4, test 26;
# test 23's method).
#
# What it does
#   1. Builds a database as it was BEFORE Phase 2.3: every earlier migration,
#      the price list and the test staff.
#   2. Makes every kind of record there: a draft; unpaid, part paid, paid,
#      overdue, corrected, refunded and cancelled invoices; delivery and
#      discount lines; a zero-value draft; notes of every kind.
#   3. Saves a fingerprint of everything: every invoice and receipt
#      document, every invoice_summary row (balance and status), the Home
#      figures, and a checksum of every invoices, invoice_lines and payments
#      row; plus the definitions and permissions of the views and functions
#      Phase 2.3 replaces.
#   4. Applies Phase 2.3 and checks:
#      - every receipt document is byte-for-byte the same;
#      - every invoice document is the same once the two new keys are taken
#        out, and those are "credited 0" and "no credit notes";
#      - every summary row is the same, with credited 0; Home the same;
#      - every row of invoices, invoice_lines and payments is the same.
#   5. Runs the prepared removal script and checks everything, definitions
#      and permissions included, is exactly as before Phase 2.3.
#   6. Applies Phase 2.3 again, makes one credit note, and checks the
#      removal script then refuses to run.
# =============================================================================
set -euo pipefail
DB="${TCP_TEST_DB:?run this through run-tests.sh}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OWNER="11111111-1111-1111-1111-111111111111"
P23="20261126120000"
OLD="${DB}_before_2_3"
REMOVE="$HERE/rollback/${P23}_credit_notes_phase2_3_remove.sql"
PSQL=(psql -X -q -t -A -v ON_ERROR_STOP=1 --no-psqlrc)
fail() { echo "TEST FAILED: $1"; exit 1; }
as() { echo "set request.jwt.claim.sub = '$OWNER'; set role authenticated;"; }
q() { "${PSQL[@]}" -d "$OLD" -c "$1"; }
run() { "${PSQL[@]}" -d "$OLD" -c "$(as)" -c "$1"; }
apply23() { "${PSQL[@]}" -d "$OLD" -f "$HERE/migrations/${P23}_credit_notes_phase2_3.sql" >/dev/null; }

# ---------------------------------------------- 1. the database before 2.3
createdb "$OLD"
trap 'dropdb --if-exists "$OLD" >/dev/null 2>&1 || true; rm -f /tmp/$OLD.*' EXIT
"${PSQL[@]}" -d "$OLD" -f "$HERE/tests/support/supabase_stub.sql" >/dev/null
for m in "$HERE"/migrations/*.sql; do
  [[ "$(basename "$m")" < "$P23" ]] && "${PSQL[@]}" -d "$OLD" -f "$m" >/dev/null
done
"${PSQL[@]}" -d "$OLD" -f "$HERE/seed.sql" >/dev/null
"${PSQL[@]}" -d "$OLD" -f "$HERE/tests/support/test_helpers.sql" >/dev/null
[ "$(q "select count(*) from pg_tables where tablename = 'credit_notes'")" = "0" ] || fail "the old database already has Phase 2.3"

# ---------------------------------------------- 2. records of every kind
run "select public.create_customer('0241234567', 'Ama Mensah');" >/dev/null
L='[{"kind":"product","product_id":3,"quantity":10},{"kind":"delivery","quantity":1,"unit_price":150,"description":"Delivery","unit":"trip"},{"kind":"discount","quantity":1,"unit_price":-50,"description":"Discount","unit":"each"}]'
draft() { run "select public.save_draft_invoice(null, 1, 'Kasoa', null, null, $1, 'Customer note', '${2:-$L}'::jsonb);"; }
issue() { run "select public.issue_invoice($1);" >/dev/null; }
pay() { run "select (public.record_payment(p_invoice_id => $1, p_amount => $2, p_method => 'cash', p_paid_on => current_date,
                     p_customer_note => 'Thank you', p_internal_note => 'Paid at the depot')).id;"; }

I1=$(draft "current_date + 30")                                           # draft
I2=$(draft "current_date + 30"); issue "$I2"                               # unpaid (1,200)
I3=$(draft "current_date + 30"); issue "$I3"; pay "$I3" 100 >/dev/null     # part paid
I4=$(draft "current_date + 30"); issue "$I4"; pay "$I4" 1200 >/dev/null    # paid
I5=$(draft "current_date - 3"); issue "$I5"; pay "$I5" 50 >/dev/null      # overdue
I6=$(draft "current_date + 30"); issue "$I6"; P6=$(pay "$I6" 300)
run "select public.correct_payment(p_payment_id => $P6, p_reason => 'Wrong amount', p_internal_note => 'Typo');" >/dev/null   # corrected
I7=$(draft "current_date + 30"); issue "$I7"; P7=$(pay "$I7" 1200)
run "select public.refund_payment(p_payment_id => $P7, p_amount => 200, p_method => 'cash', p_reason => 'Short delivery',
                                  p_customer_note => 'Sorry', p_internal_note => 'Cash back');" >/dev/null                # refunded
I8=$(draft "current_date + 30"); issue "$I8"
run "select public.cancel_invoice($I8, 'Customer changed their mind');" >/dev/null                                         # cancelled
I9=$(draft "null" '[{"kind":"product","product_id":3,"quantity":1,"unit_price":0}]')       # a zero-value draft
run "select public.add_invoice_note($I2, 'Customer will pay Friday');" >/dev/null
INVOICES="$I1 $I2 $I3 $I4 $I5 $I6 $I7 $I8 $I9"
RECEIPTS="$(q "select string_agg(id::text, ' ' order by id) from public.payments")"

# ---------------------------------------------- 3. the fingerprint
docs() {  # $1 = jq-like strip for invoice documents ('' before, the two keys after)
  for i in $INVOICES; do run "select 'inv $i ' || (public.invoice_document($i) $1)::text;"; done
  for p in $RECEIPTS; do run "select 'rct $p ' || public.receipt_document($p)::text;"; done
  run "select 'sum ' || string_agg(format('%s %s %s %s %s %s', id, invoice_no, total, paid, balance, status), ' | ' order by id)
         from public.invoice_summary;"
  run "select 'home ' || (select format('%s %s %s %s %s', owed, unpaid, part_paid, overdue, drafts) from public.back_office_home);"
  q "select 'rows ' || (select md5(string_agg(t::text, '|' order by t.id)) from public.invoices t)
               || ' ' || (select md5(string_agg(t::text, '|' order by t.id)) from public.invoice_lines t)
               || ' ' || (select md5(string_agg(t::text, '|' order by t.id)) from public.payments t);"
}
defs() {  # the definitions and permissions Phase 2.3 replaces
  q "select 'view ' || c.relname || ' ' || md5(pg_get_viewdef(c.oid)) || ' ' || coalesce(c.relacl::text, '')
       from pg_class c where c.relnamespace = 'public'::regnamespace
        and c.relname in ('invoice_summary', 'overdue_invoices', 'invoice_list', 'back_office_home') order by 1;"
  q "select 'func ' || p.oid::regprocedure::text || ' ' || md5(p.prosrc) || ' ' || coalesce(p.proacl::text, '')
       from pg_proc p where p.proname in ('cancel_invoice', 'invoice_document', 'receipt_document')
        and p.pronamespace = 'public'::regnamespace order by 1;"
  q "select 'objects ' || (select count(*) from pg_class where relname like 'credit_note%' or relname like 'feature_switch%')
             || ' ' || (select count(*) from pg_proc where proname like '%credit_note%')
             || ' ' || (select string_agg(kind, ',' order by kind) from tcp_private.number_counters)
             || ' ' || (select count(*) from pg_constraint where conname = 'invoice_lines_invoice_id_id_key');"
}
docs "" > "/tmp/$OLD.before"
defs > "/tmp/$OLD.defs"

# ---------------------------------------------- 4. apply Phase 2.3
apply23
docs "- 'credited' - 'credit_notes'" > "/tmp/$OLD.after"
if ! diff -q "/tmp/$OLD.before" "/tmp/$OLD.after" >/dev/null; then
  diff "/tmp/$OLD.before" "/tmp/$OLD.after" | head -6 | tr '\n' ' ' | cut -c1-1500
  fail "something changed after the migration (diff above)"
fi
[ "$(grep -c '^inv ' "/tmp/$OLD.after")" = "9" ] && [ "$(grep -c '^rct ' "/tmp/$OLD.after")" = "7" ] \
  || fail "expected 9 invoices and 7 receipts compared"
for i in $INVOICES; do
  [ "$(run "select (d->>'credited')::numeric = 0 and d->'credit_notes' = '[]'::jsonb from (select public.invoice_document($i) d) x;")" = "t" ] \
    || fail "invoice $i has credits it never had"
done
[ "$(q "select count(*) from public.invoice_summary where credited <> 0")" = "0" ] || fail "credited is not zero everywhere"
[ "$(run "select in_credit = 0 and in_credit_count = 0 from public.back_office_home;")" = "t" ] || fail "Home shows money in credit"
[ "$(q "select is_on from tcp_private.feature_switches where name = 'credit_notes'")" = "f" ] || fail "the switch is not created off"

# ---------------------------------------------- 5. the full removal
"${PSQL[@]}" -d "$OLD" -f "$REMOVE" >/dev/null || fail "the removal script failed"
docs "" > "/tmp/$OLD.removed"
diff -q "/tmp/$OLD.before" "/tmp/$OLD.removed" >/dev/null || fail "a figure or document differs after the removal"
defs > "/tmp/$OLD.defs2"
if ! diff -q "/tmp/$OLD.defs" "/tmp/$OLD.defs2" >/dev/null; then
  diff "/tmp/$OLD.defs" "/tmp/$OLD.defs2" | head -6 | tr '\n' ' ' | cut -c1-1500
  fail "a definition or permission differs after the removal (diff above)"
fi
# The database still works as before: a payment, and an overdue list read.
pay "$I2" 100 >/dev/null || fail "a payment failed after the removal"
run "select count(*) from public.overdue_invoices;" >/dev/null || fail "overdue_invoices cannot be read after the removal"
run "select count(*) from public.invoice_list;" >/dev/null || fail "invoice_list cannot be read after the removal"

# ---------------------------------------------- 6. never once a credit note exists
apply23 || fail "Phase 2.3 could not be applied again after the removal"
run "select public.set_credit_notes_switch(true, 'Test', gen_random_uuid());" >/dev/null
LINE=$(q "select id from public.invoice_lines where invoice_id = $I2 and kind = 'product'")
run "select public.issue_credit_note(p_invoice_id => $I2,
       p_lines => '[{\"invoice_line_id\":$LINE,\"kind\":\"quantity\",\"why\":\"returned\",\"quantity\":1}]'::jsonb,
       p_reason => 'One bag back', p_request_id => gen_random_uuid());" >/dev/null
if out="$("${PSQL[@]}" -d "$OLD" -f "$REMOVE" 2>&1)"; then fail "the removal ran although a credit note exists"; fi
echo "$out" | grep -q "never removed" || fail "unexpected refusal: $out"
[ "$(q "select count(*) from public.credit_notes")" = "1" ] || fail "the credit note is gone"
echo "ok: 9 invoices, $(echo $RECEIPTS | wc -w) receipts, every summary row and table row unchanged; removal checked"
