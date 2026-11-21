-- =============================================================================
-- Test helpers and test people (local tests ONLY)
--
-- Loaded after the migration and the seed. Creates:
--   - tcp_test.ok(condition, message): stops the test with the message if the
--     condition is false
--   - tcp_test.fails(sql, expected words): runs a statement that SHOULD be
--     refused and checks the refusal message contains the expected words
--   - five test logins with fixed ids, used by every test file:
--       owner    11111111-...  (role owner, like Daniel)
--       sales    22222222-...  (role sales)
--       finance  33333333-...  (role finance)
--       stranger 44444444-...  (logged in, but not staff)
--       retired  55555555-...  (staff, but switched off)
--
-- How a test acts as someone:
--   set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
--   set role authenticated;
--   ... do things ...
--   reset role;
-- =============================================================================

create schema tcp_test;
grant usage on schema tcp_test to anon, authenticated, service_role;

create function tcp_test.ok(condition boolean, message text)
returns void
language plpgsql
as $$
begin
  if condition is distinct from true then
    raise exception 'TEST FAILED: %', message;
  end if;
end;
$$;

create function tcp_test.fails(statement text, expected text)
returns void
language plpgsql
as $$
begin
  begin
    execute statement;
  exception when others then
    if position(lower(expected) in lower(sqlerrm)) = 0 then
      raise exception 'TEST FAILED: "%" was refused, but with "%" instead of "%"',
        statement, sqlerrm, expected;
    end if;
    return;
  end;
  raise exception 'TEST FAILED: "%" should have been refused (expected "%")', statement, expected;
end;
$$;

-- Value of one column from a query, as text (keeps the tests short).
create function tcp_test.val(query text)
returns text
language plpgsql
as $$
declare
  result text;
begin
  execute query into result;
  return result;
end;
$$;

grant execute on all functions in schema tcp_test to anon, authenticated, service_role;

insert into auth.users (id, email) values
  ('11111111-1111-1111-1111-111111111111', 'owner@test.local'),
  ('22222222-2222-2222-2222-222222222222', 'sales@test.local'),
  ('33333333-3333-3333-3333-333333333333', 'finance@test.local'),
  ('44444444-4444-4444-4444-444444444444', 'stranger@test.local'),
  ('55555555-5555-5555-5555-555555555555', 'retired@test.local');

insert into public.staff (user_id, full_name, role, active) values
  ('11111111-1111-1111-1111-111111111111', 'Test Owner',   'owner',   true),
  ('22222222-2222-2222-2222-222222222222', 'Test Sales',   'sales',   true),
  ('33333333-3333-3333-3333-333333333333', 'Test Finance', 'finance', true),
  ('55555555-5555-5555-5555-555555555555', 'Test Retired', 'owner',   false);
