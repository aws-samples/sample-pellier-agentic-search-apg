# Lab 3: Deploy

**Theo.** He wants his taste remembered and help with his own chipped bowl, and must never
see another customer's account. On AgentCore the starter's Gateway withholds `get_tickets`,
and the starter's row-ownership predicate is `false`. Keep the Workshop Studio guide open
beside this file.

## Run it in the terminal

Every terminal starts at the repository root. First move Pellier onto AgentCore, once:

```bash
bash scripts/lab3-start.sh theo
```

| Task | See it fail | Edit | Prove it |
|---|---|---|---|
| 3A, publish `get_tickets` and bind it to the caller | `python3 scripts/lab3_check.py --task 3A` | [3A-1-publish-tool.py](3A-1-publish-tool.py), region `Gateway catalogue - published tools`; [3A-2-bind-caller.py](3A-2-bind-caller.py), region `Support agent - Gateway tools` | `python3 scripts/lab3_check.py --task 3A` ends `Lab 3A check passed` |
| 3B, deploy, write the ownership rule, then challenge it | `psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-3-row-ownership.sql` | deploy with `python3 scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant`; while it runs, [3B-row-ownership.sql](3B-row-ownership.sql), region `Row ownership - predicate`, and the same `psql` run until it ends `Lab 3B predicate check passed`; then `python3 scripts/lab_run.py send --lab 3` | `python3 scripts/lab3_check.py --task 3B` ends `Lab 3B check passed` |

Editing the 3A files alone does not update Runtime or Gateway; the deployment does.
`3B-row-ownership.sql` deploys itself: when every probe matches, it commits your predicate
as the live row-level security policy on orders and support tickets; when any probe
differs, it rolls back.

After the 3B token, open **PellierURL** and read Theo's turns in **Ask Pellier** with
**Builder view** on: the remembered record the check printed, his ticket read bound to
`CUST-THEO`, and the household request staying on his account. The AgentCore console shows
the Runtime, the Gateway and the Memory record.

## If you need a solution

Open [solution/README.md](solution/README.md) when you choose the recovery path. Installing
an answer does not complete the task; its check still has to pass.

[All labs](../../START_HERE.md)
