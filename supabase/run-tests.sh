#!/usr/bin/env bash
# =============================================================================
# Runs every database test against a brand-new, throwaway Postgres database.
#
# What it does
#   1. Starts a temporary Postgres server in a temporary folder (nothing is
#      installed or left behind, and no Supabase project is touched).
#   2. Builds a "template" database: Supabase stand-in, the migration(s), the
#      starting price list and the test helpers.
#   3. For each test file in supabase/tests/, makes a fresh copy of the
#      template and runs the file against it, so tests can't affect each other.
#   4. Prints PASS or FAIL per file, then stops the server and deletes it all.
#
# How to run it (from the top folder of the repository)
#   bash supabase/run-tests.sh
#   Needs Postgres 15 or newer installed (the same family Supabase uses).
#
# Exit code 0 = everything passed. Anything else = something failed.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Postgres refuses to run as the "root" user. On a computer or server where
# this script is run as root, run it again as the "postgres" user instead.
if [ "$(id -u)" = "0" ]; then
  COPY="$(mktemp -d)"
  cp -r "$HERE" "$COPY/supabase"
  chown -R postgres "$COPY"
  exec runuser -u postgres -- bash "$COPY/supabase/run-tests.sh"
fi

# Find the Postgres programs (initdb, pg_ctl), newest version first.
PG_BIN="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1 || true)"
if [ -z "$PG_BIN" ]; then
  PG_BIN="$(dirname "$(command -v initdb || command -v pg_ctl)")"
fi
export PATH="$PG_BIN:$PATH"

WORK="$(mktemp -d)"
PORT="${TCP_TEST_PORT:-54329}"
export PGHOST="$WORK" PGPORT="$PORT" PGUSER="postgres"

cleanup() {
  pg_ctl -D "$WORK/data" -m immediate stop >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

echo "Starting a throwaway Postgres ($(postgres --version))"
initdb -D "$WORK/data" -U postgres --auth=trust >/dev/null
pg_ctl -D "$WORK/data" -l "$WORK/server.log" \
  -o "-k $WORK -p $PORT -c listen_addresses=''" -w start >/dev/null

PSQL=(psql -X -q -v ON_ERROR_STOP=1 --no-psqlrc)

echo "Building the template database"
createdb tcp_template
"${PSQL[@]}" -d tcp_template -f "$HERE/tests/support/supabase_stub.sql" >/dev/null
for migration in "$HERE"/migrations/*.sql; do
  echo "  migration: $(basename "$migration")"
  "${PSQL[@]}" -d tcp_template -f "$migration" >/dev/null
done
"${PSQL[@]}" -d tcp_template -f "$HERE/seed.sql" >/dev/null
"${PSQL[@]}" -d tcp_template -f "$HERE/tests/support/test_helpers.sql" >/dev/null

passed=0
failed=0
n=0
for test in "$HERE"/tests/*.sql "$HERE"/tests/*.sh; do
  [ -e "$test" ] || continue
  n=$((n + 1))
  db="tcp_test_$n"
  createdb -T tcp_template "$db"
  name="$(basename "$test")"
  if [[ "$test" == *.sql ]]; then
    run=("${PSQL[@]}" -d "$db" -f "$test")
  else
    run=(env TCP_TEST_DB="$db" bash "$test")
  fi
  if output="$("${run[@]}" 2>&1)"; then
    echo "PASS  $name"
    # Measured timings (e.g. the notes search speed test) are shown even
    # when the test passes.
    echo "$output" | grep -E "TIMING" | sed 's/^.*TIMING/      TIMING/' || true
    passed=$((passed + 1))
  else
    echo "FAIL  $name"
    echo "$output" | grep -E "ERROR|TEST FAILED|DETAIL|psql:" | head -20 | sed "s/^/      /"
    failed=$((failed + 1))
  fi
done

echo
echo "$passed passed, $failed failed"
[ "$failed" -eq 0 ]
