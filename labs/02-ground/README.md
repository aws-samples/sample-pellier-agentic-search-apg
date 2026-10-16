# Lab 2: Ground

**Marco.** He needs stock and dispatch facts he can rely on. As shipped, the Stock agent
holds only catalog tools, so its call to `check_stock` is refused and no answer reads a
warehouse row; and once it holds `check_stock`, the database function behind it calls a
piece Pellier does not carry 0 in stock. Keep the Workshop Studio guide open beside this
file.

## Run it in the terminal

Every terminal starts at the repository root. You apply 2A and build 2B.

| Task | See it fail | Fix | Prove |
|---|---|---|---|
| 2A, connect `check_stock` to the Stock agent, alone | `uv run scripts/lab_run.py send --lab 2 --task 2A`, his Brooklyn count | Apply: `uv run scripts/lab_run.py solution --lab 2 --task 2A`. It shows the change to [2A-stock-agent.py](2A-stock-agent.py), installs it, keeps your file as `.bak` and restarts the backend. Then `uv run scripts/lab_run.py send --lab 2 --task 2A` | `uv run scripts/lab2_check.py --task 2A` ends `Lab 2A check passed` |
| 2B, keep "not carried" distinct from sold out | `uv run scripts/lab_run.py send --lab 2 --task 2B`, the cape Pellier never carried, then the exercise: `psql -f labs/02-ground/2B-check-stock.sql` | Write: [2B-check-stock.sql](2B-check-stock.sql), region `Stock check - not carried`, then run the exercise again | the exercise ends `Lab 2B function check passed`, then `uv run scripts/lab2_check.py --task 2B` ends `Lab 2B check passed` |

Sends in this lab print `ran in process`. The 2A check reads the grant the answering Stock
agent actually held from its audit row, so it needs Marco's requests sent again after the
change. The 2B exercise changes the live `pellier.check_stock` only when its four probes
match, and the 2B check runs that live function, so it needs no restart.

After the 2B token, open **PellierURL**, choose **Marco** in **Ask Pellier** with **Builder
view** on, and send his requests again. Both are there, marked **Sent from the terminal**:
the cape now reads **Not a piece Pellier carries**, and the Hadley one shows the Stock agent,
one `check_stock` call and the Brooklyn warehouse row.

## The files

Both files are links to the application's own files, so there is no second copy to
synchronize. Edit only the marked region.

## Start this lab over

In Code Editor choose **Terminal > Run Task > Reset Lab 2** (or run `uv run scripts/lab_run.py reset --lab 2`). It puts this lab back as shipped and leaves the other labs alone.

## If you need a solution

To skip one task, run its apply command above. To finish the whole lab, run
`uv run scripts/lab_run.py finish --lab 2`. Either way the check still has to pass. The answers
are also in [solution/README.md](solution/README.md).

[All labs](../../START_HERE.md)
