# Lab 3: Deploy

**Theo.** He wants his taste remembered and help with his own chipped bowl, and must never
see another customer's account. As shipped, the Gateway on AgentCore withholds
`get_tickets`, the Support agent asks only for `get_return_policy` and `ask_a_person`, and
the row-ownership predicate is `false`. Keep the Workshop Studio guide open beside this
file.

## Run it in the terminal

Every terminal starts at the repository root. You apply 3A and build 3B. Before this lab, the
room finishes Labs 1 and 2 together; the deploy below then moves Pellier from local agents onto
AgentCore.

| Task | See it fail | Fix | Prove |
|---|---|---|---|
| 3A, publish `get_tickets` and bind it to the caller | `uv run scripts/lab3_check.py --task 3A` | Apply: `uv run scripts/lab_run.py solution --lab 3 --task 3A`. It shows the change to [3A-1-publish-tool.py](3A-1-publish-tool.py) and [3A-2-bind-caller.py](3A-2-bind-caller.py), installs it and keeps your files as `.bak` | `uv run scripts/lab3_check.py --task 3A` ends `Lab 3A check passed` |
| 3B, deploy, write the ownership rule, then challenge it | `uv run scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant`, then in a second terminal `psql -f labs/03-deploy/3B-row-ownership.sql` | Write: [3B-row-ownership.sql](3B-row-ownership.sql), region `Row ownership - predicate`, then the same `psql` run until it ends `Lab 3B predicate check passed` | `uv run scripts/lab_run.py send --lab 3`, then `uv run scripts/lab3_check.py --task 3B` ends `Lab 3B check passed` |

The order is: the 3A check fails, you apply 3A, the 3A check passes, then the deploy. No send
comes before the deploy, because only the deploy moves Pellier onto the AgentCore path that
`send --lab 3` needs. After it come the 3B exercise, `uv run scripts/lab_run.py send --lab 3`
and the 3B check.

The deploy carries your 3A files to Runtime and Gateway. When it reports ready it moves Pellier
onto AgentCore itself and ends `Pellier is now using AgentCore. Continue with Theo's requests.`
From then on every send prints `ran on AgentCore Runtime and Gateway`. If a deploy instead ends
`Pellier did not move onto AgentCore`, run `bash scripts/lab3-start.sh theo` once and send again.
Editing the 3A files alone does not update Runtime or Gateway; the deployment does.
`3B-row-ownership.sql` deploys itself: when every probe matches, it commits your predicate
as the live row-level security policy on orders and support tickets; when any probe
differs, it rolls back.

After the 3B token, open **PellierURL**, choose **Theo** in **Ask Pellier** with **Builder
view** on. His three requests are there, marked **Sent from the terminal**, each with its trace:
the remembered record the check printed, his ticket read bound to `CUST-THEO`, and the household
request staying on his account. The AgentCore console shows the Runtime, the Gateway and the
Memory record.

Then look from the database's side. This supplied query reads `pg_stat_statements` and
lists what each role ran: the agent's reads as `pellier_agent`, the app's own login, and one
plan with the row policy inside it. It only reads.

```bash
psql -f workshop/lab-3-agent-workload.sql
```

It ends `Lab 3 workload check passed` once Theo's requests have run.

## Start this lab over

In Code Editor choose **Terminal > Run Task > Reset Lab 3** (or run `uv run scripts/lab_run.py reset --lab 3`). It puts this lab back as shipped and leaves the other labs alone.

## If you need a solution

To skip one task, run its apply command above. To finish the whole lab, run
`uv run scripts/lab_run.py finish --lab 3`, which also deploys and takes about three minutes.
Either way the check still has to pass. The answers are also in
[solution/README.md](solution/README.md).

[All labs](../../START_HERE.md)
