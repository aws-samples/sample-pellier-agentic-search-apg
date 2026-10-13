# Lab 3 solution

Try the marked task first. These files are the supplied answers, not the files the
application executes.

- [3A-1-publish-tool.py](3A-1-publish-tool.py)
- [3A-2-bind-caller.py](3A-2-bind-caller.py)
- [3B-row-ownership.sql](3B-row-ownership.sql)

To catch up on the whole lab, save any edits you want to keep, then run this from the
repository root. It moves Pellier onto AgentCore, installs the answers, deploys them, runs
the row-ownership worksheet, sends Theo's requests and runs both checks:

```bash
bash scripts/lab3-start.sh theo && \
  python3 scripts/lab_run.py solution --lab 3 && \
  python3 scripts/lab3_check.py --task 3A && \
  python3 scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant && \
  psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-3-rls.sql && \
  python3 scripts/lab_run.py send --lab 3 && \
  python3 scripts/lab3_check.py
```

Return to the [lab README](../README.md) and continue in Workshop Studio.
