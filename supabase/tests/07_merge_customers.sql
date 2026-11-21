-- Merging two records of the same buyer.
\set QUIET on

set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';  -- owner
set role authenticated;

select public.create_customer('0241234567', 'Kwame Mensah');   -- TCP-C-0001
select public.create_customer('0241234567', 'K. Mensah');      -- TCP-C-0002 (same man)
select public.create_customer(null, 'Kwame M (site)');         -- TCP-C-0003 (same man again)

-- Invoices on the duplicate records: one issued, one cancelled draft.
select public.create_draft_invoice(2);
select public.add_invoice_line(1, 'product', 1, 1);
select public.issue_invoice(1);
select public.create_draft_invoice(3);
select public.cancel_invoice(2, 'not needed');

-- Merge 0002 into 0001, then 0003 into 0001.
select public.merge_customers(1, 2);
select public.merge_customers(1, 3);

select tcp_test.ok((select count(*) from public.invoices where customer_id = 1) = 2, 'invoices moved to the kept record');
select tcp_test.ok((select invoice_no from public.invoices where id = 1) = 'TCP-INV-0001', 'issued invoice otherwise unchanged');
select tcp_test.ok((select state from public.invoices where id = 2) = 'cancelled', 'cancelled invoice otherwise unchanged');
select tcp_test.ok((select count(*) from public.customer_code_aliases where customer_id = 1) = 2, 'two old codes kept as aliases');

-- Old codes still find the right customer.
select tcp_test.ok((public.find_customer_by_code('TCP-C-0002')).code = 'TCP-C-0001', 'old code finds kept customer');
select tcp_test.ok((public.find_customer_by_code('tcp-c-0003')).code = 'TCP-C-0001', 'case does not matter');

-- Merged records can't be used or merged again.
select tcp_test.fails($$select public.create_draft_invoice(2)$$, 'merged');
select tcp_test.fails($$select public.merge_customers(1, 2)$$, 'already been merged');
select tcp_test.fails($$select public.merge_customers(1, 1)$$, 'two different');

-- Chains: merging the kept record into another carries its aliases along.
select public.create_customer('0201112222', 'Mensah Enterprises');   -- TCP-C-0004
select public.merge_customers(4, 1);
select tcp_test.ok((select count(*) from public.customer_code_aliases where customer_id = 4) = 3, 'aliases follow the merge');
select tcp_test.ok((public.find_customer_by_code('TCP-C-0002')).code = 'TCP-C-0004', 'oldest code still resolves');

-- Logged.
select tcp_test.ok((select count(*) from public.audit_log where table_name = 'customer_code_aliases') >= 3, 'merges logged');

-- Only the owner can merge.
reset role;
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
set role authenticated;
select tcp_test.fails($$select public.merge_customers(4, 1)$$, 'sales role cannot');
reset role;

-- Outside a merge, issued invoices still can't change customer.
select tcp_test.fails($$update public.invoices set customer_id = 2 where id = 1$$, 'locked');
