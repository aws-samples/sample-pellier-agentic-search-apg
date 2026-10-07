# Lab 4 solution

Try the marked task first. These files are the supplied answers, not the files the application executes.

- [4A-credit-policy.cedar](4A-credit-policy.cedar)
- [4B-row-ownership.sql](4B-row-ownership.sql)

To use the guide’s full recovery path, first save any edits you want to keep. Then run these commands **from the repository root**; they replace the corresponding exercise files:

```bash
cp solutions/the-concierge/policies/workshop_credit_limit.cedar policies/workshop_credit_limit.cedar
cp solutions/the-concierge/sql/lab-4-rls-solution.sql workshop/lab-4-rls.sql
```

Deploy the Cedar edit with the guide’s participant deployment. The RLS worksheet runs in a transaction that rolls back; it does not replace the deployed policy. Run `workshop/lab-4-absence.sql` for the final absence proof.

Return to the [lab README](../README.md), repeat its checks and continue in Workshop Studio.
