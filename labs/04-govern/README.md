# Lab 4: Govern

**Jessica, with Nadia.** Jessica sent two items back and has no credit yet. Nadia must
approve the credit, Cedar must cap it at $100, and the role that writes it must be able to
write it only through the credit function. Keep the Workshop Studio guide open beside this
file.

## Run it in the terminal

Every terminal starts at the repository root.

| Task | See it fail | Edit | Prove it |
|---|---|---|---|
| 4A, cap the credit at $100 in Cedar | `python3 scripts/lab4_check.py --task 4A` | [4A-credit-policy.cedar](4A-credit-policy.cedar), the final `unless` block, then deploy with `python3 scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant` | `python3 scripts/lab4_check.py --task 4A` ends `Lab 4A check passed` |
| 4B, let the money role write only through the function | `psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-4-credit-writer.sql` | [4B-credit-writer.sql](4B-credit-writer.sql), region `Credit writer - privileges`, while 4A deploys, and the same `psql` run until it ends `Lab 4B privileges check passed` | `python3 scripts/lab4_check.py --task 4B` ends `Lab 4B check passed` |

Jessica's request goes from the terminal:

```bash
python3 scripts/lab_run.py send --lab 4 --shopper-only
```

Nadia's decision is the one step that happens in the app. In **PellierURL**, select
**Operator**, sign in as `nadia`, investigate Jessica's case, approve the proposed credit
and select **Execute**: with the starter rule, Policy reads DENY. After the deploy, select
**Execute again** and then **Retry execution**. Their proof comes back here: the two checks
above, then the supplied absence check, which ends `Lab 4 absence check passed`:

```bash
psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-4-absence.sql
```

`4B-credit-writer.sql` deploys itself: when every probe matches, it commits your privileges
for `pellier_credit_writer`; when any probe differs, it rolls back.

## If you need a solution

Open [solution/README.md](solution/README.md) when you choose the recovery path. Installing
an answer does not complete the task; its check still has to pass.

[All labs](../../START_HERE.md)
