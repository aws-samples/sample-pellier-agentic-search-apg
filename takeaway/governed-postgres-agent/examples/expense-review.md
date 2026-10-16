# Worked review: an approved expense can still be changed

**Question:** Can an agent turn an approved $25 reimbursement into $500?

**Takeaway:** Requiring approval inside a function is insufficient when the
calling role can update the written row directly.

## The tool being reviewed

A finance assistant calls `apply_credit` for an approved expense. The function
checks the exact terms and supports retries. A legacy table grant, however,
allows `UPDATE` through `PUBLIC`:

```sql
GRANT UPDATE ON review_example.credits TO PUBLIC;
```

That grant reaches the application's write role even though no grant names
the role directly. The schema permits amounts up to $500, so its amount
constraint does not preserve this particular approval's $25 limit.

## Reproduce it, then test the correction

Use an empty disposable PostgreSQL database and an administrator connection
that can create roles. From the extracted package directory, replace
`takeaway_review` with that database's name. Supply connection details through
your normal local PostgreSQL configuration; no AWS account is needed.

```bash
psql -X -v ON_ERROR_STOP=1 -d takeaway_review -f examples/setup.sql
psql -X -v ON_ERROR_STOP=1 -d takeaway_review -f examples/expense-review.sql
```

Setup creates `review_writer` and `review_support`, which are cluster-wide
role names. Use a fresh local cluster if those names already exist. The
example never drops existing objects and is intended to run once per setup.

The first transaction grants the unsafe privilege, writes the approved $25,
then updates it to $500 as `review_writer`. It prints `50000` and confirms
effective UPDATE privilege. It rolls back both the grant and that write.

The second transaction uses the restricted role configuration. The approved
write succeeds, the direct UPDATE is refused with SQLSTATE `42501`, and a
retry returns `replayed: true`. After commit, the database contains one credit
for `2500` cents and one first-write audit row.

Run the independent read-only checks:

```bash
psql -X -v ON_ERROR_STOP=1 -d takeaway_review \
  -v request_id=search-1 -v case_id=stock-1 -v write_key=approval:1 \
  -f references/proof-queries.sql
```

The file names each claim. Retrieval examines one known eligible product;
stock compares a complete expected result; ownership pairs an own-row read
with a foreign-row denial. Approval, effective privileges and committed-write
checks inspect the corrected reimbursement. These fixture results do not
establish anything about a different database or deployed service.

## The review to hand back

**Claim:** Execution must preserve the approved customer, amount and reason.

**Code evidence:** [The unsafe grant](expense-review.sql) bypasses
`apply_credit`'s approval checks. [The function and schema](setup.sql) bound
the overall amount but cannot prevent a role with direct UPDATE privilege
from changing an approved row within that bound.

**Test evidence:** As `review_writer`, an approved 2500-cent credit was
changed directly to 50000 cents. With the grant removed, the same UPDATE was
refused; execution through the function and replay still worked.

**Result:** Failed before correction. Passed for the direct-update denial,
approved write and same-key replay after correction, in the local fixture.

**Limit:** This test does not exercise staff authentication, AgentCore Policy,
payment settlement, concurrency, or a deployed application. A first-write
audit row is not a log of every invocation. The supplied database function
also trusts a separate approval service, represented here by administrator
setup.

**Next action:** Inspect effective privileges and alternative callable
functions in the target application. Run these probes as its actual write
role, then race two connections using the application's transaction isolation
level. Test both the same key and different approvals for the same expense.

In the source repository, `scripts/test_takeaway_package.py` executes these
distributed files and also tests the two races at READ COMMITTED, malformed
approvals, inherited privileges and missing evidence. Those tests support the
example's claims; they are not evidence about the application you review.
