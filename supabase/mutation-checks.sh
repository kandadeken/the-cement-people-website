#!/usr/bin/env bash
# =============================================================================
# Mutation checks for Phase 2.3 (credit notes), specification v1.4, section 6.
#
# What it does
#   For each rule below, makes a copy of supabase/ with that ONE rule taken
#   out of the credit notes migration, runs the credit note tests (24 and
#   25) against the copy, and expects them to FAIL. If the tests still pass
#   with a rule removed, the tests do not really check that rule, and this
#   script says so and exits with an error.
#
#   The rules: the per-line quantity cap, the per-line value cap, the
#   invoice cap, the invoice lock, the switch row lock and the backdate rule.
#
# How to run it (from the top folder of the repository)
#   bash supabase/mutation-checks.sh
#   Takes a few minutes (the two tests are run six times). Needs Postgres and
#   python3. Nothing in the repository is changed.
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIG="migrations/20261126120000_credit_notes_phase2_3.sql"

# Each mutation: a name, the exact text to find in the issue function, and
# what to put instead.
mutations=(
  "quantity cap|if q > cl.quantity_left then|if false then"
  "value cap|least(round(q * cl.net_value / cl.quantity, 2), cl.value_left)|round(q * cl.net_value / cl.quantity, 2)"
  "invoice cap|if s.credited + new_total > s.total then|if false then"
  "invoice lock|select * into inv from public.invoices where id = p_invoice_id for update;|select * into inv from public.invoices where id = p_invoice_id;"
  "switch row lock|where name = 'credit_notes' for share;|where name = 'credit_notes';"
  "backdate rule|if eff <> today and (role_now <> 'owner'|if false and (role_now <> 'owner'"
)

bad=0
for m in "${mutations[@]}"; do
  IFS='|' read -r name find put <<<"$m"
  COPY="$(mktemp -d)"
  cp -r "$HERE" "$COPY/supabase"
  # Change the text inside issue_credit_note only (cancel_invoice has a
  # line that looks the same). For the value cap, the "nothing left" checks
  # go too, so only the cap itself guards the value.
  python3 - "$COPY/supabase/$MIG" "$name" "$find" "$put" <<'PY'
import sys
path, name, find, put = sys.argv[1:]
s = open(path).read()
start = s.index("create function public.issue_credit_note")
end = s.index("create function public.cancel_credit_note")
body = s[start:end]
if find not in body:
    sys.exit(f"mutation '{name}': text not found")
body = body.replace(find, put)
if name == "value cap":
    body = body.replace("if cl.value_left <= 0 then", "if false then").replace("if amt <= 0 then", "if false then")
open(path, "w").write(s[:start] + body + s[end:])
PY
  if bash "$COPY/supabase/run-tests.sh" 24_credit_notes.sql 25_credit_note_race.sh >"$COPY/out" 2>&1; then
    echo "NOT CAUGHT  $name: the tests still pass with this rule removed"
    bad=$((bad + 1))
  else
    echo "caught      $name: $(grep -m1 -o 'TEST FAILED.\{0,110\}' "$COPY/out" || echo 'a test failed')"
  fi
  rm -rf "$COPY"
done
echo
[ "$bad" -eq 0 ] && echo "Every mutation was caught." || { echo "$bad mutation(s) not caught."; exit 1; }
