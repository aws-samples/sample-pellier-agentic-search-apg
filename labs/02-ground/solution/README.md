# Lab 2 solution

Try the marked task first. These files are the supplied answers, not the files the
application executes.

- [2A-stock-agent.py](2A-stock-agent.py)
- [2B-check-stock.sql](2B-check-stock.sql)

Skip one task: the task's own apply command shows the change, installs that task's answer,
keeps your file as `.bak`, restarts the backend when needed and prints the next command.

```bash
uv run scripts/lab_run.py solution --lab 2 --task 2A   # or 2B
```

Finish the whole lab: back up your files, apply the answers, restart, send the requests and
run every check, stopping at the first failure. It runs the 2B file, which
commits the function.

```bash
uv run scripts/lab_run.py finish --lab 2
```

Return to the [lab README](../README.md) and continue in Workshop Studio.
