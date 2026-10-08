# Lab 4 solution

Try the marked task first. These files are the supplied answers, not the files the application executes.

- [4A-credit-policy.cedar](4A-credit-policy.cedar)
- [4B-row-ownership.sql](4B-row-ownership.sql)

To use the guide’s full recovery path, first save any edits you want to keep. Then run this **from the repository root**; it copies the lab’s answers over the corresponding exercise files:

```bash
python3 scripts/lab_run.py solution --lab 4
```

Deploy the Cedar edit with the guide’s participant deployment. Then `python3 scripts/lab_run.py send --lab 4` makes Jessica’s request and does Nadia’s approval and execution for you. The RLS worksheet runs in a transaction that rolls back; it does not replace the deployed policy. Run `workshop/lab-4-absence.sql` for the final absence proof.

Return to the [lab README](../README.md), repeat its checks and continue in Workshop Studio.
