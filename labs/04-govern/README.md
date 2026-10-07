# Lab 4: Govern

**Jessica and Nadia.** Keep the matching Workshop Studio guide open for the requests, predictions, marked edit regions and checks.

## Open the file

| File in this folder | Task | Application file |
|---|---|---|
| [4A-credit-policy.cedar](4A-credit-policy.cedar) | Authorize credits within the amount limit | `policies/workshop_credit_limit.cedar` |
| [4B-row-ownership.sql](4B-row-ownership.sql) | Enforce row ownership | `workshop/lab-4-rls.sql` |

These are links to the actual application files. Saving here changes the file the app or deployment uses; there is no second copy to synchronize. Edit only the marked region named in the guide.

## Check your work

Every prepared terminal starts at the repository root. Run the checks at the point specified in the guide:

```bash
python3 scripts/lab4_policy_check.py
psql -X -P pager=off -f workshop/lab-4-rls.sql
```

Deploy the Cedar edit with the guide’s participant deployment. The RLS worksheet runs in a transaction that rolls back; it does not replace the deployed policy. Run `workshop/lab-4-absence.sql` for the final absence proof.

## If you need a solution

Open [solution/README.md](solution/README.md) when you choose the recovery path. Applying an answer does not complete the lab; repeat the same requests and checks.

[All labs](../../START_HERE.md)
