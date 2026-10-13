# Lab 2: Ground

**Marco.** He needs stock and dispatch facts he can rely on. The starter's `check_stock`
calls a piece Pellier does not carry sold out, and the Stock agent holds only catalog
tools, so no answer reads a warehouse row. Keep the Workshop Studio guide open beside this
file.

## Run it in the terminal

Every terminal starts at the repository root.

| Task | See it fail | Edit | Prove it |
|---|---|---|---|
| 2A, keep "not carried" distinct from sold out | `python3 scripts/lab2_contract_check.py` | [2A-check-stock.py](2A-check-stock.py), region `Stock agent - check_stock` | `python3 scripts/lab2_contract_check.py` ends `Lab 2A check passed` |
| 2B, connect `check_stock` to the Stock agent, alone | `python3 scripts/lab_run.py send --lab 2`, then `python3 scripts/lab2_contract_check.py --task 2B` | [2B-stock-agent.py](2B-stock-agent.py), region `Stock agent - definition`, then `sudo systemctl restart pellier` and send his requests again | `python3 scripts/lab2_contract_check.py --task 2B` ends `Lab 2B check passed` |

The 2A check runs your `check_stock` directly, so it needs no restart. The 2B check reads
the grant the answering Stock agent actually held from its audit row, so it needs the
restart and Marco's requests sent again.

After the 2B token, open **PellierURL**, choose **Marco** in **Ask Pellier** with **Builder
view** on, and read his Hadley turn: the Stock agent, one `check_stock` call, the Brooklyn
warehouse row.

## The files

Both files are links to the application's own files, so there is no second copy to
synchronize. Edit only the marked region.

## If you need a solution

Open [solution/README.md](solution/README.md) when you choose the recovery path. Installing
an answer does not complete the task; its check still has to pass.

[All labs](../../START_HERE.md)
