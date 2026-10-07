# Lab 2: Ground

**Marco.** Keep the matching Workshop Studio guide open for the requests, predictions, marked edit regions and checks.

## Open the file

| File in this folder | Task | Application file |
|---|---|---|
| [2A-check-stock.py](2A-check-stock.py) | Keep not carried apart from sold out | `pellier/backend/services/agent_tools.py` |
| [2B-stock-agent.py](2B-stock-agent.py) | Narrow the Stock agent grant | `pellier/backend/agents/stock_agent.py` |

These are links to the actual application files. Saving here changes the file the app or deployment uses; there is no second copy to synchronize. Edit only the marked region named in the guide.

## Check your work

Every prepared terminal starts at the repository root. Run the checks at the point specified in the guide:

```bash
python3 scripts/lab2_contract_check.py
python3 scripts/lab2_contract_check.py --task 2B
```

Restart the backend as the guide directs, then repeat Marco’s requests. The checks inspect the agent that actually answered.

## If you need a solution

Open [solution/README.md](solution/README.md) when you choose the recovery path. Applying an answer does not complete the lab; repeat the same requests and checks.

[All labs](../../START_HERE.md)
