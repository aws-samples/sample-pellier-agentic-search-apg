# Lab 1: Retrieve

**Anna.** Keep the matching Workshop Studio guide open for the requests, the marked edit regions and the checks.

## Open the file

| File in this folder | Task | Application file |
|---|---|---|
| [1A-rrf.sql](1A-rrf.sql) | Recompute the RRF score | `workshop/lab-1-rrf.sql` |
| [1B-search-plan.py](1B-search-plan.py) | Keep the budget, stock and exclusions on the fallback | `pellier/backend/services/search_plan.py` |

These are links to the actual application files. Saving here changes the file the app or deployment uses; there is no second copy to synchronize. Edit only the marked region named in the guide.

## Check your work

Every prepared terminal starts at the repository root. Run the checks at the point specified in the guide:

```bash
psql -X -P pager=off -f workshop/lab-1-rrf.sql
python3 scripts/lab1_compare.py
```

After editing Python, use the backend restart in the guide and repeat Anna’s request.

## If you need a solution

Open [solution/README.md](solution/README.md) when you choose the recovery path. Applying an answer does not complete the lab; repeat the same requests and checks.

[All labs](../../START_HERE.md)
