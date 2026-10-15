# Lab 4 solution

Try the marked task first. These files are the supplied answers, not the files the
application executes.

- [4A-credit-policy.cedar](4A-credit-policy.cedar)
- [4B-credit-writer.sql](4B-credit-writer.sql)

To catch up on the whole lab, save any edits you want to keep, then run this from the
repository root. It installs both answers, commits the credit writer's privileges, deploys
the Cedar rule, sends Jessica's request and does Nadia's approval and execution, then runs
the checks:

```bash
python3 scripts/lab_run.py solution --lab 4 && \
  psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-4-credit-writer.sql && \
  python3 scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant && \
  python3 scripts/lab_run.py send --lab 4 && \
  python3 scripts/lab4_check.py --task 4A && \
  python3 scripts/lab4_check.py --task 4B && \
  psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-4-absence.sql
```

The exercise runs before `send`, so Nadia's credit is written under the privileges you
committed.

Return to the [lab README](../README.md) and continue in Workshop Studio.
