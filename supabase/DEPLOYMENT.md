# Going live, backups and recovery

This is the plan for moving the tested database onto a real Supabase project.
**None of it happens until Daniel (with ChatGPT) approves it.** Each numbered
step is a separate go-ahead.

## 1. Create the Supabase project

- Plan: **Pro** (about $25 a month) before any real record goes in. Pro
  includes daily backups and is never paused. Development and testing can stay
  on the throwaway database in `run-tests.sh` until then.
- Region: the closest one Supabase offers to Ghana, chosen when creating the
  project.
- Owner account: the TCP Google Workspace account
  (DanielOkraku@thecementpeople.com), so the business, not a personal account,
  owns it.
- Turn on multi-factor sign-in for that Supabase account.

## 2. Keys: what goes where

Supabase gives two kinds of key:

| Key | Safe in website code? | Used for |
| --- | --- | --- |
| `anon` (public) key | Yes | The website reading `public_catalogue`; staff signing in |
| `service_role` key | **Never** | The Edge Function that sends price changes to Cloudflare |

The `service_role` key skips every permission rule. It lives only in Supabase's
own secret settings for the Edge Function, never in GitHub, never in the
website, never in a chat.

## 3. Apply the database

There are two ways. **Route A is the preferred one**, because it is repeatable
and records in Supabase which migrations have been applied. Route B is the
fallback if the command-line tool can't be used.

Whichever route is used, first run `bash supabase/run-tests.sh` on the exact
commit being deployed and confirm all tests pass.

### Route A: Supabase command-line tool (CLI)

Run from the top folder of the repository, on a computer with the Supabase CLI
installed (`npm install -g supabase`, or `npx supabase ...` each time):

1. `supabase init`, once. This creates `supabase/config.toml`, the CLI's
   project settings file. It deliberately isn't in the repository yet: it is
   created at go-live and committed in the go-live pull request. Keep the
   existing `migrations/` and `seed.sql`, which are already where the CLI
   expects them.
2. `supabase login` (opens the browser), then
   `supabase link --project-ref <project ref>`. The project ref is in the
   project's dashboard address. It asks for the database password set when the
   project was created; that password is never written into any file.
3. `supabase db push --dry-run` lists what would be applied: exactly the one
   migration file. Check it, then run `supabase db push` for real.
4. Load the starting price list once:
   `supabase db push --include-seed` (or paste `seed.sql` into the SQL editor).
5. `supabase migration list` should show the migration as applied both locally
   and remotely.

Later changes follow the same path: a new file in `migrations/`, tested here,
reviewed in a pull request, then `supabase db push`.

### Route B: SQL editor (fallback)

1. In the Supabase dashboard, SQL editor, paste the whole migration file and
   run it once. It runs as one unit: if anything fails, nothing is applied.
2. Paste `seed.sql` and run it once.
3. Because Supabase didn't record this migration, run Route A's
   `supabase migration repair --status applied 20261121120000` before any later
   CLI use, so the CLI doesn't try to apply it a second time.

### Check (both routes)

- `select count(*) from public.public_catalogue` returns 17.
- `select * from public.site_price_status` shows the website as out of date
  (nothing published from the database yet). That is expected.

## 4. Make Daniel the owner

1. In Supabase: Authentication > Users > **Invite user** with Daniel's email.
   Turn **off** public sign-ups (Authentication > Providers > Email > "Allow new
   users to sign up"), so staff only join by invitation.
2. After Daniel accepts, in the SQL editor:
   ```sql
   insert into public.staff (user_id, full_name, role)
   select id, 'Daniel Okraku', 'owner' from auth.users where email = '<Daniel''s email>';
   ```
   This is the only time the staff table is written by hand. Later staff are
   added the same way with role `sales` or `finance`.

## 5. Test with realistic transactions (before any real customer)

As agreed with ChatGPT, the system is exercised with realistic but made-up
sales first: part payments, a correction, a refund, a cancellation, a merge, a
price change. Then those test records are cleared by recreating the project
from step 3 (records can't be deleted, by design), and real use begins.

## 6. Prices to the website (Cloudflare)

When TCP moves to Cloudflare:

1. In Cloudflare Pages, create a **deploy hook** (a private web address that
   starts a rebuild). Store it as a Supabase secret, never in GitHub.
2. Deploy a small Supabase Edge Function that runs every minute (Supabase
   scheduled function):
   - `claim_site_publish()` takes the waiting request, if any
   - calls the Cloudflare deploy hook
   - `finish_site_publish(id, ok, error)` reports back
3. The website build reads `public_catalogue` with the anon key.
4. `site_price_status` shows whether the website has the latest prices; the
   admin screen will show a warning when `website_out_of_date` is true.

Safeguards already built in: one waiting request and one build at a time
(repeated changes don't pile up); a change made during a build queues another
build, so it is never lost; any public change counts (name, unit, price,
published, price visible); a build that never reports back is retried after
15 minutes; up to 5 retries with the error kept; and the "out of date" flag
compares the last change with the moment the last successful build started.

## 7. Overdue reminders

A second scheduled Edge Function, once a day, reads `overdue_invoices` and
emails Daniel the list (free; uses the TCP Workspace email). Customer reminders
by WhatsApp are a later decision, as they cost money.

## Backups and recovery

| What | How |
| --- | --- |
| Daily backups | Included in Supabase Pro, kept for 7 days |
| Point-in-time recovery | Optional Supabase add-on (restore to any minute). Worth turning on once money volumes justify the cost |
| Our own copy | Once a week, a downloaded backup (`supabase db dump`) kept in the TCP Google Drive, so TCP never depends on a single company |
| The design itself | Always rebuildable from this repository: the migration file recreates every table, rule and permission |

**Recovery drill:** before real use, restore a backup into a fresh project once
and check the records and totals match. A backup that has never been restored
is not yet a backup.

## Rollback

Until real records exist, rollback is simply deleting the Supabase project.
After that, changes to the database are made only by new migration files,
tested here first, never by editing live tables by hand.
