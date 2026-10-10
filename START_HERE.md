# Start here: Pellier

This is the code behind **Ask Pellier**, the store assistant you are about to fix. The
Workshop Studio guide has the steps; this editor is where you make the edits and run the
checks. Keep the two side by side.

If you have not opened the guide's **Getting started** page yet, do that first. It opens this
editor and Pellier from the event outputs, starts the session with one command, and signs you
in as Anna.

## The four labs

Each numbered group holds one lab's files: the two files you edit, a short `README.md`, and a
collapsed `solution` folder.

| Group | Customer | What you build | You edit |
|---|---|---|---|
| [01 - Retrieve](labs/01-retrieve/README.md) | Anna | A ranking you can recompute, and a retry that keeps her limits | `1A-rrf.sql`, `1B-search-plan.py` |
| [02 - Ground](labs/02-ground/README.md) | Marco | A stock tool that answers from a warehouse row, held by one agent | `2A-check-stock.py`, `2B-stock-agent.py` |
| [03 - Deploy](labs/03-deploy/README.md) | Theo | A published ticket tool bound to the caller, on AgentCore | `3A-1-publish-tool.py`, `3A-2-bind-caller.py` |
| [04 - Govern](labs/04-govern/README.md) | Jessica, with Nadia | A Cedar credit limit and a row-ownership policy in Aurora | `4A-credit-policy.cedar`, `4B-row-ownership.sql` |

The files in these groups are the application's own files, linked into place. Saving one
changes what the app runs; there is no second copy to keep in sync. Edit only between the
`START` and `END` markers the guide names for your task.

**05 - Explore Pellier source** is the whole repository, for when you want to see how a
tool, an agent or a check is built. Every terminal starts at the repository root, so the
guide's commands work whichever file is open.

## How a lab goes

Every lab page follows the same shape. You watch the starter get it wrong, live in Pellier.
You fix it in two marked regions, one task at a time. You prove each fix with a check that
reads Aurora, and the page tells you the one line to look for. A passing check is the
evidence; a fluent answer in the chat is not.

If you get stuck, each task on the guide has a **Stuck?** box with three tabs: hints, a
prompt for the coding coach, and the solution. The `solution` folder in each group holds the
same answers as files. And every lab ends with a one-paste catch-up that installs the answers
and runs the checks, so you can rejoin at the next lab; the guide's cheat sheet has all four.

## The coding coach

Claude Code is installed in this terminal and pointed at Amazon Bedrock through the
workshop's instance role; nothing to sign in to. Start it with
`claude --permission-mode plan` and paste the prompt from your task's **Stuck?** box. It is
set up to ask for your prediction, give one hint at a time, and propose a patch inside your
region only when you ask. You run the checks yourself. The guide's coaching page has the
two-minute setup.

## At the end

The guide's **Wrap-up** page hands you the four contracts you built as a skill for your own
code, `governed-postgres-agent`, and exports your evidence:

```bash
python3 scripts/workshop_evidence.py --save workshop-evidence.txt
```

If this opened as a plain folder rather than a workspace, choose **File → Open Workspace
from File… → Pellier.code-workspace**; the same groups are under `labs/`. For how the
repository is put together, see [README.md](README.md) and the
[worksheet and check map](workshop/README.md).
