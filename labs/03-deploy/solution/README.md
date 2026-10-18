# Lab 3 solution

Try the marked task first. These files are the supplied answers, not the files the
application executes.

- [3A-1-publish-tool.py](3A-1-publish-tool.py)
- [3A-2-bind-caller.py](3A-2-bind-caller.py)
- [3B-row-ownership.sql](3B-row-ownership.sql)

Skip one task: the task's own apply command shows the change, installs that task's answer,
keeps your file as `.bak`, restarts the backend when needed and prints the next command.

```bash
uv run scripts/lab_run.py solution --lab 3 --task 3A   # or 3B
```

Finish the whole lab: back up your files, apply the answers, restart or deploy, send the
requests and run every check, stopping at the first failure. It deploys to AgentCore, which
takes about three minutes, and runs the row-ownership file.

```bash
uv run scripts/lab_run.py finish --lab 3
```

Return to the [lab README](../README.md) and continue in Workshop Studio.
