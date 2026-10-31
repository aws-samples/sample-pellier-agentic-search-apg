# Lab 1: Retrieve

**Anna.** She asks for a housewarming gift in one sentence, with a budget, a stock rule and
no candles. As shipped, the search matches her words and ranks nothing by meaning, and its
retry drops her limits. Keep the Workshop Studio guide open beside this file.

## Run it in the terminal

Every terminal starts at the repository root. You apply 1A and build 1B.

| Task | See it fail | Fix | Prove |
|---|---|---|---|
| 1A, search by what she means | `uv run scripts/lab_run.py send --lab 1 --task 1A`: her ranking has no vector rank | Apply: `uv run scripts/lab_run.py solution --lab 1 --task 1A`. It shows the change to [1A-vector-search.py](1A-vector-search.py), installs it, keeps your file as `.bak` and restarts the backend | `uv run scripts/lab1_check.py --task 1A` ends `Lab 1A check passed` |
| 1B, keep her limits on the retry | `uv run scripts/lab_run.py send --lab 1 --task 1B`, her sentence with her limits, then `psql -f workshop/lab-1-receipt.sql` | Build: [1B-search-plan.py](1B-search-plan.py), region `Search plan - preserve requirements`, then `uv run scripts/lab_run.py restart` and `uv run scripts/lab_run.py send --lab 1 --task 1B` | `uv run scripts/lab1_check.py --task 1B` ends `Lab 1B check passed` |

Sends in this lab print `ran in process`: the agents run inside the app.

After `Lab 1B check passed`, open **PellierURL** and choose **Anna** in **Ask Pellier** with
**Builder view** on. Your request is there, marked **Sent from the terminal**; **How it ranked**
shows **Vector** ranks, what her three limits left out, and no candles.

## The files

`1A-vector-search.py` and `1B-search-plan.py` are links to `pellier/backend/services/`, so
saving here changes the code the backend runs. Edit only the marked region. `go-deeper-fusion.sql` is the guide's optional Go deeper Build: it recomputes
the fused scores Anna's search recorded and changes nothing the app runs.

## Start this lab over

In Code Editor choose **Terminal > Run Task > Reset Lab 1** (or run `uv run scripts/lab_run.py reset --lab 1`). It puts this lab back as shipped and leaves the other labs alone.

## If you need a solution

To skip one task, run its apply command above. To finish the whole lab, run
`uv run scripts/lab_run.py finish --lab 1`. Either way the check still has to pass. The answers
are also in [solution/README.md](solution/README.md).
