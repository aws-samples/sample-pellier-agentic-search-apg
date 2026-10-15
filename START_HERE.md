# Start here: Pellier

This is the code behind **Ask Pellier**, the store assistant you are about to fix. The
Workshop Studio guide has the steps; this editor is where you make the edits and run the
checks. Keep the two side by side.

## Start the session

Every terminal starts at the repository root. Run:

```bash
bash scripts/workshop-start.sh
```

It prints the psql client beside the Aurora server version, both 18, and ends with
`+ OK    Ready for Lab 1`. If it ends on anything else, keep the output and raise your
hand.

## The four labs

Each numbered group holds one lab's files: the files you edit, a short `README.md`, and a
collapsed `solution` folder.

| Group | Customer | What you build | You edit |
|---|---|---|---|
| [01 - Retrieve](labs/01-retrieve/README.md) | Anna | A search that ranks by meaning, and a retry that keeps her limits | `1A-vector-branch.py`, `1B-search-plan.py` |
| [02 - Ground](labs/02-ground/README.md) | Marco | A stock tool that answers from a warehouse row, held by one agent | `2A-stock-agent.py`, `2B-check-stock.sql` |
| [03 - Deploy](labs/03-deploy/README.md) | Theo | A published ticket tool bound to the caller on AgentCore, and a row-ownership policy in Aurora | `3A-1-publish-tool.py`, `3A-2-bind-caller.py`, `3B-row-ownership.sql` |
| [04 - Govern](labs/04-govern/README.md) | Jessica, with Nadia | A Cedar credit limit, and a money role that writes only through the credit function | `4A-credit-policy.cedar`, `4B-credit-writer.sql` |

The files in these groups are links to the application's own files, so there is no second
copy to keep in sync. Python edits reach the running backend when you save, because it reloads; the Lab 3
edits and the Lab 4 Cedar rule reach AgentCore when you run the guide's deployment. Three
files deploy themselves: `2B-check-stock.sql`, `3B-row-ownership.sql` and
`4B-credit-writer.sql`, run with `psql`, commit your statements to Aurora only when every
probe they run matches.
`go-deeper-fusion.sql`, last in 01 - Retrieve, is optional. Edit only between the `START`
and `END` markers the guide names for your task.

**05 - Explore Pellier source** is the whole repository, for when you want to see how a
tool, an agent or a check is built.

## How every task runs

Each task fails in the terminal first: a worksheet, a check, or
`python3 scripts/lab_run.py send`, which sends the customer's exact sentence. You fix the
marked region. One command proves the fix and ends with one pass token, such as
`Lab 1A check passed`; a fluent answer in the chat is not the proof. Then you look at the
same thing in the app.

## Where to look in the app

Open **PellierURL** from the event outputs once a check has passed. The Storefront's
**Ask Pellier** panel, with **Builder view** on, shows each turn's Router step, the tools
the agent called and **How it ranked**. The **Operator** is where Nadia approves Jessica's
credit in Lab 4; that decision and its three buttons are the one step that happens in the
app, and its proof comes back to the terminal. The AgentCore console shows Lab 3's Runtime,
Gateway and Memory.

## If you get stuck

Each task on the guide has a **Stuck?** box with three tabs: hints, a prompt for the coding
coach, and the solution. The `solution` folder in each group holds the same answers as
files. Every lab ends with a one-paste catch-up that installs the answers, runs the
worksheets and the checks, so you can rejoin at the next lab; the guide's cheat sheet has
all four.

## The coding coach

Claude Code is installed in this terminal and pointed at Amazon Bedrock through the
workshop's instance role; nothing to sign in to. Start it with `claude` and paste the prompt
from your task's **Stuck?** box. It asks before every edit and command, and it is set up to ask
for your prediction, give one hint at a time, and propose a patch inside your region only when
you ask. You run the checks yourself. The guide's coaching page has the two-minute setup.

## At the end

The guide's **Wrap-up** page rebuilds Jessica's credit from her request to the row with one
read-only worksheet, `psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/wrap-up-reconstruct.sql`
(`Wrap-up reconstruction passed`), hands you the four contracts as `governed-postgres-agent`, a
skill for reviewing your own team's agents the way a DBA would, and exports your evidence:

```bash
python3 scripts/workshop_evidence.py --save workshop-evidence.txt
```

If this opened as a plain folder rather than a workspace, choose **File → Open Workspace
from File… → Pellier.code-workspace**; the same groups are under `labs/`. For how the
repository is put together, see [README.md](README.md) and the
[worksheet and check map](workshop/README.md).
