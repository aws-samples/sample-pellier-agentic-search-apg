# Lab 4: Govern

**Jessica, with Nadia.** Jessica sent two items back and has no credit yet. Nadia must
approve the credit, Cedar must cap it at $100, and the role that writes it must be able to
write it only through the credit function. Keep the Workshop Studio guide open beside this
file.

## Run it in the terminal

Every terminal starts at the repository root. You apply 4A and build 4B. Pellier is already on AgentCore from Lab 3.

| Task | See it fail | Fix | Prove |
|---|---|---|---|
| 4A, cap the credit at $100 in Cedar | `uv run scripts/lab_run.py send --lab 4 --shopper-only`, Nadia's **Execute** in the Operator, then `uv run scripts/lab4_check.py --task 4A` | Apply: `uv run scripts/lab_run.py solution --lab 4 --task 4A`. It shows the change to [4A-credit-policy.cedar](4A-credit-policy.cedar), the final `unless` block, installs it and keeps your file as `.bak`. Then deploy with `uv run scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant` | After 4B: **Execute again** and **Replay with the same key**, then `uv run scripts/lab4_check.py --task 4A` ends `Lab 4A check passed` |
| 4B, let the money role write only through the function | `psql -f labs/04-govern/4B-credit-writer.sql` | Build: [4B-credit-writer.sql](4B-credit-writer.sql), region `Credit writer - privileges`, while 4A deploys, then the same `psql` run until it ends `Lab 4B privileges check passed` | `uv run scripts/lab4_check.py --task 4B` ends `Lab 4B check passed` |

The deploy ends `Pellier is already using AgentCore.`

Jessica's request goes from the terminal:

```bash
uv run scripts/lab_run.py send --lab 4 --shopper-only
```

Its last line prints Nadia's sign-in for the Operator. Nadia's decision is the one step that
happens in the app. In **PellierURL**, select **Operator**, sign in as `nadia`, investigate
Jessica's case, approve the proposed credit and select **Execute**: with the rule as shipped,
Policy reads DENY. After the deploy, select **Execute again** and then **Replay with the same
key**. Their proof comes back here: the two checks above, then the supplied absence check, which
ends `Lab 4 absence check passed`:

```bash
psql -f workshop/lab-4-absence.sql
```

`4B-credit-writer.sql` checks itself: when every probe matches, it commits your privileges
for `pellier_credit_writer`; when any probe differs, it rolls back.

## Start this lab over

In Code Editor choose **Terminal > Run Task > Reset Lab 4** (or run `uv run scripts/lab_run.py reset --lab 4`). It puts this lab back as shipped and leaves the other labs alone. Once a credit has been written it stops and points you to **Reset the whole workshop**.

## If you need a solution

To finish the whole lab, run `uv run scripts/lab_run.py finish --lab 4`. It backs up your
files, applies both answers, deploys, performs Nadia's approval and execution once (a rerun only
replays), runs every check and stops at the first failure. The answers are also in
[solution/README.md](solution/README.md).

[All labs](../../START_HERE.md)
