-- =============================================================================
-- The Cement People: TCP Back Office, version 1 (Home figures)
--
-- What this file is
--   The third migration. It follows "TCP Back Office: Design Specification
--   v1.1", approved by ChatGPT and Daniel on 22 November 2026. It adds ONE
--   read-only view and changes nothing else: no table, column, function,
--   rule or permission from the earlier migrations.
--
-- back_office_home
--   One row with the figures on the Back Office's Home screen. It is built
--   on invoice_summary, the same calculation the Invoices list (invoice_list)
--   and the invoice documents use, so Home can never disagree with them.
--   It runs with the caller's rights (security_invoker): staff see the real
--   figures; anyone else sees zeros (row-level security hides every invoice
--   from them), and the Back Office then signs them out via my_staff().
--
-- Merging this into main deploys it to the tcp-test project only.
-- =============================================================================

create view public.back_office_home
with (security_invoker = true)
as
select
  -- What customers still owe TCP on issued invoices. Drafts and cancelled
  -- invoices are never owed; a paid invoice has no balance.
  coalesce(sum(balance) filter (where status in ('unpaid', 'part_paid', 'overdue')), 0)::numeric(14, 2) as owed,
  count(*) filter (where status = 'unpaid')    as unpaid,
  count(*) filter (where status = 'part_paid') as part_paid,
  count(*) filter (where status = 'overdue')   as overdue,
  count(*) filter (where status = 'draft')     as drafts
from public.invoice_summary;

comment on view public.back_office_home is
  'The Back Office Home figures, from invoice_summary. Read-only; runs with the caller''s rights.';

-- Signed-in users only (row-level security then decides what they see);
-- never the public.
revoke all on public.back_office_home from public, anon, authenticated;
grant select on public.back_office_home to authenticated;
