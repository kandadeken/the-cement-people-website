-- =============================================================================
-- Supabase stand-in for local tests ONLY (never run on the real project)
--
-- A real Supabase project already has these pieces. A plain Postgres database
-- does not, so the tests create small stand-ins first:
--   - the three web roles: anon (not logged in), authenticated (logged in),
--     service_role (the server, which skips row-level security)
--   - the auth schema with a users table
--   - auth.uid(), which in Supabase returns the logged-in user's id from their
--     login token. Here the tests set that id with:
--       set request.jwt.claim.sub = '<uuid>';
-- =============================================================================

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end;
$$;

create schema if not exists auth;
grant usage on schema auth to anon, authenticated, service_role;
grant usage on schema public to anon, authenticated, service_role;

create table if not exists auth.users (
  id     uuid primary key,
  email  text
);

create or replace function auth.uid()
returns uuid
language sql stable
as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
grant execute on function auth.uid() to anon, authenticated, service_role;

-- Supabase's default: the web roles get rights on new tables in public.
-- Reproduced here so the tests prove the migration takes them away again.
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
