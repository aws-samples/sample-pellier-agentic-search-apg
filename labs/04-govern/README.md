# Lab 4: Govern

**Jessica and Nadia.** Keep the matching Workshop Studio guide open for the requests, the marked edit regions and the checks.

## Open the file

| File in this folder | Task | Region to edit | Application file |
|---|---|---|---|
| [4A-credit-policy.cedar](4A-credit-policy.cedar) | Authorize credits within the amount limit | the final `unless` block | `policies/workshop_credit_limit.cedar` |
| [4B-row-ownership.sql](4B-row-ownership.sql) | Enforce row ownership | `Row ownership - predicate` | `workshop/lab-4-rls.sql` |

Both are links to the application's own files, so there is no second copy to synchronize. Saving `4A-credit-policy.cedar` changes the policy the guide's participant deployment publishes. `4B-row-ownership.sql` deploys itself: run it with `psql` and, when every probe matches, it commits your predicate as the live row-level security policy on both tables; when any probe differs, it rolls back and the live policies stay as they were. Edit only the marked region named in the guide.

## Check your work

Every prepared terminal starts at the repository root. Run the checks at the point specified in the guide:

```bash
python3 scripts/lab4_policy_check.py
psql -X -P pager=off -f workshop/lab-4-rls.sql
python3 scripts/lab4_rls_check.py
```

Deploy the Cedar edit with the guide’s participant deployment. `scripts/lab4_rls_check.py` then confirms the live policies carry the predicate in your file and probes them as Theo, in process and through the Gateway Lambda's Data API binding, rolling its own probes back. Run `workshop/lab-4-absence.sql` for the final absence proof. Afterwards, `python3 scripts/observability_check.py` reads the steps outside AgentCore's trace: the app's spans, Database Insights and the refused write in the PostgreSQL log.

## If you need a solution

Open [solution/README.md](solution/README.md) when you choose the recovery path. Applying an answer does not complete the lab; repeat the same requests and checks.

[All labs](../../START_HERE.md)
