# Lab 2 solution

Try the marked task first. These files are the supplied answers, not the files the
application executes.

- [2A-check-stock.py](2A-check-stock.py)
- [2B-stock-agent.py](2B-stock-agent.py)

To catch up on the whole lab, save any edits you want to keep, then run this from the
repository root. It installs both answers, restarts the backend, sends Marco's requests and
runs both checks:

```bash
python3 scripts/lab_run.py solution --lab 2 && \
  sudo systemctl restart pellier && \
  python3 scripts/lab_run.py send --lab 2 && \
  python3 scripts/lab2_check.py --task 2A && \
  python3 scripts/lab2_check.py --task 2B
```

Return to the [lab README](../README.md) and continue in Workshop Studio.
