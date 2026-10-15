# Lab 1: Retrieve

**Anna.** She asks for a housewarming gift in one sentence, with a budget, a stock rule and
no candles. As shipped, the search matches her words and ranks nothing by meaning, and its
retry drops her limits. Keep the Workshop Studio guide open beside this file.

## Run it in the terminal

Every terminal starts at the repository root.

| Task | See it fail | Edit | Prove it |
|---|---|---|---|
| 1A, search by what she means | `python3 scripts/lab_run.py send --lab 1 --task 1A`: her ranking has no vector rank | Read why first: `psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-1-words.sql`, then `psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-1-meaning.sql`. Then [1A-vector-branch.py](1A-vector-branch.py), region `Vector branch - order by meaning` | `python3 scripts/lab1_check.py --task 1A` ends `Lab 1A check passed` |
| 1B, keep her limits on the retry | `python3 scripts/lab_run.py send --lab 1 --task 1B`, her sentence with her limits, then `python3 scripts/lab1_check.py --task 1B` | [1B-search-plan.py](1B-search-plan.py), region `Search plan - preserve requirements`, then restart and send her request again | `python3 scripts/lab1_check.py --task 1B` ends `Lab 1B check passed` |

After the 1B token, open **PellierURL**, choose **Anna** in **Ask Pellier** with **Builder
view** on. The request you sent is there, marked **Sent from the terminal**, and **How it
ranked** shows a **Vector** rank on every row, her three limits, and no candles.

## The files

`1A-vector-branch.py` and `1B-search-plan.py` are links to `pellier/backend/services/`, so
saving here changes the code the backend runs: it reloads on save. Edit only the marked
region. `go-deeper-fusion.sql` is the guide's optional Go deeper: a worksheet that recomputes
the fused scores Anna's search recorded and changes nothing the app runs.

## Start this lab over

In Code Editor choose **Terminal > Run Task > Reset Lab 1** (or run `python3 scripts/lab_run.py reset --lab 1`). It puts this lab back as shipped and leaves the other labs alone.

## If you need a solution

Open [solution/README.md](solution/README.md) when you choose the recovery path. Installing
an answer does not complete the task; its check still has to pass.

[All labs](../../START_HERE.md)
