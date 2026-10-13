# Lab 1 solution

Try the marked task first. These files are the supplied answers, not the files the
application executes.

- [1A-vector-branch.py](1A-vector-branch.py)
- [1B-search-plan.py](1B-search-plan.py)
- [go-deeper-rrf.sql](go-deeper-rrf.sql), the optional worksheet's answer

To catch up on the whole lab, save any edits you want to keep, then run this from the
repository root. It installs both tasks' answers, leaves the optional worksheet alone,
restarts the backend, sends Anna's request and runs both checks:

```bash
python3 scripts/lab_run.py solution --lab 1 && \
  sudo systemctl restart pellier && \
  python3 scripts/lab_run.py send --lab 1 && \
  python3 scripts/lab1_vector_check.py && \
  python3 scripts/lab1_compare.py
```

Return to the [lab README](../README.md) and continue in Workshop Studio.
