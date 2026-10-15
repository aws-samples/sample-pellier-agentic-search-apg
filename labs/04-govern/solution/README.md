# Lab 4 solution

Try the marked task first. These files are the supplied answers, not the files the
application executes.

- [4A-credit-policy.cedar](4A-credit-policy.cedar)
- [4B-credit-writer.sql](4B-credit-writer.sql)

Skip one task: the task's own apply command shows the change, installs that task's answer,
keeps your file as `.bak`, restarts the backend when needed and prints the next command.

```bash
python3 scripts/lab_run.py solution --lab 4 --task 4A   # or 4B
```

Finish the whole lab: back up your files, apply the answers, restart or deploy, send the
requests and run every check, stopping at the first failure. It deploys the Cedar rule and also performs Nadia's approval and execution once; a rerun only replays.

```bash
python3 scripts/lab_run.py finish --lab 4
```

The credit writer's privileges are committed before Nadia's credit is written, so the credit is written under them.

Return to the [lab README](../README.md) and continue in Workshop Studio.
