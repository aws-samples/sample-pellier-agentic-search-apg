# Lab 1 solution

Try the marked task first. These files are the supplied answers, not the files the
application executes.

- [1A-vector-branch.py](1A-vector-branch.py)
- [1B-search-plan.py](1B-search-plan.py)
- [go-deeper-fusion.sql](go-deeper-fusion.sql), the optional exercise's answer

Skip one task: the task's own apply command shows the change, installs that task's answer,
keeps your file as `.bak`, restarts the backend when needed and prints the next command.

```bash
uv run scripts/lab_run.py solution --lab 1 --task 1A   # or 1B
```

Finish the whole lab: back up your files, apply the answers, restart or deploy, send the
requests and run every check, stopping at the first failure. It leaves the optional Go deeper
exercise alone.

```bash
uv run scripts/lab_run.py finish --lab 1
```

Return to the [lab README](../README.md) and continue in Workshop Studio.
