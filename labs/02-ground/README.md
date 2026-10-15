# Lab 2: Ground

**Marco.** He needs stock and dispatch facts he can rely on. As shipped, the Stock agent
holds only catalog tools, so its call to `check_stock` is refused and no answer reads a
warehouse row; and once it holds `check_stock`, the database function behind it calls a
piece Pellier does not carry 0 in stock. Keep the Workshop Studio guide open beside this
file.

## Run it in the terminal

Every terminal starts at the repository root.

| Task | See it fail | Edit | Prove it |
|---|---|---|---|
| 2A, connect `check_stock` to the Stock agent, alone | `python3 scripts/lab_run.py send --lab 2 --task 2A`, his Brooklyn count, then `python3 scripts/lab2_check.py --task 2A` | [2A-stock-agent.py](2A-stock-agent.py), region `Stock agent - definition`, then `sudo systemctl restart pellier` and send his Brooklyn count again | `python3 scripts/lab2_check.py --task 2A` ends `Lab 2A check passed` |
| 2B, keep "not carried" distinct from sold out | `python3 scripts/lab_run.py send --lab 2 --task 2B`, the cape Pellier never carried, then `psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-2-check-stock.sql` | [2B-check-stock.sql](2B-check-stock.sql), region `Stock check - not carried`, then run the exercise again | the exercise ends `Lab 2B function check passed`, then `python3 scripts/lab2_check.py --task 2B` ends `Lab 2B check passed` |

The 2A check reads the grant the answering Stock agent actually held from its audit row, so
it needs Marco's requests sent again; the restart makes them run on your saved file. The 2B
exercise changes the live `pellier.check_stock` only when its four probes match, and the
2B check runs that live function, so it needs no restart.

After the 2B token, open **PellierURL**, choose **Marco** in **Ask Pellier** with **Builder
view** on, and send his requests again. Both are there, marked **Sent from the terminal**:
the cape now reads **Not a piece Pellier carries**, and the Hadley one shows the Stock agent,
one `check_stock` call and the Brooklyn warehouse row.

## The files

Both files are links to the application's own files, so there is no second copy to
synchronize. Edit only the marked region.

## Start this lab over

In Code Editor choose **Terminal > Run Task > Reset Lab 2** (or run `python3 scripts/lab_run.py reset --lab 2`). It puts this lab back as shipped and leaves the other labs alone.

## If you need a solution

Open [solution/README.md](solution/README.md) when you choose the recovery path. Installing
an answer does not complete the task; its check still has to pass.

[All labs](../../START_HERE.md)
