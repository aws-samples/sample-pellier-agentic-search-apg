# Lab 1: Retrieve

**Anna.** Keep the matching Workshop Studio guide open for the requests, the marked edit regions and the checks.

## Open the file

| File in this folder | Task | Region to edit | Application file |
|---|---|---|---|
| [1A-rrf.sql](1A-rrf.sql) | Recompute the RRF score | `PostgreSQL RRF - fusion expression` | `workshop/lab-1-rrf.sql` |
| [1B-search-plan.py](1B-search-plan.py) | Keep the budget, stock and exclusions on the fallback | `Search plan - preserve requirements` | `pellier/backend/services/search_plan.py` |

Both are links to the application's own files, so there is no second copy to synchronize. Saving `1B-search-plan.py` changes the code the backend runs. `1A-rrf.sql` is a worksheet you run with `psql`: it recomputes the scores Anna's search recorded and changes nothing the app runs. Edit only the marked region named in the guide.

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
