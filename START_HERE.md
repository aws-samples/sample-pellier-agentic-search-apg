# Start here: Pellier

This is the code behind **Ask Pellier**, the store assistant you are about to fix. The
Workshop Studio guide has the steps; this editor is where you make the edits and run the
checks. Keep the two side by side.

## Nothing to start

Your workshop was checked before you sat down: the database, the models, AgentCore and the
app. Every terminal starts at the repository root, so open the guide's Lab 1 and begin.

## The four labs

Each numbered group holds one lab's files: the files you edit, a short `README.md`, and a
collapsed `solution` folder.

| Group | Customer | Outcome | You build | You apply |
|---|---|---|---|---|
| [01 - Retrieve](labs/01-retrieve/README.md) | Anna | A search that ranks by meaning, and a retry that keeps her limits | `1B-search-plan.py` | `1A-vector-branch.py` |
| [02 - Ground](labs/02-ground/README.md) | Marco | A stock tool that answers from a warehouse row, held by one agent | `2B-check-stock.sql` | `2A-stock-agent.py` |
| [03 - Deploy](labs/03-deploy/README.md) | Theo | A published ticket tool bound to the caller on AgentCore, and a row-ownership policy in Aurora | `3B-row-ownership.sql` | `3A-1-publish-tool.py`, `3A-2-bind-caller.py` |
| [04 - Govern](labs/04-govern/README.md) | Jessica, with Nadia | A Cedar credit limit, and a money role that writes only through the credit function | `4B-credit-writer.sql` | `4A-credit-policy.cedar` |

You build 1B, 2B, 3B and 4B in the marked region. You apply 1A, 2A, 3A and 4A, the supplied
changes, with `uv run scripts/lab_run.py solution --lab N --task NX`, which shows the change
before it installs it and keeps your file as `.bak`.

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

Each task has three steps. **See it fail** runs in the terminal: a SQL file, a check, or
`uv run scripts/lab_run.py send`, which sends the customer's exact sentence. **Fix** is the
marked region you build, or the supplied repair you apply by command. **Prove** is one command
that ends with one pass token, such as `Lab 1A check passed`; a fluent answer in the chat is not
the proof. Then you look at the same thing in the app.

## Where to look in the app

Open **PellierURL** from the event outputs once a check has passed. The Storefront's
**Ask Pellier** panel, with **Builder view** on, shows each turn's Router step, the tools
the agent called and **How it ranked**. The **Operator** is where Nadia approves Jessica's
credit in Lab 4; that decision and its three buttons are the one step that happens in the
app, and its proof comes back to the terminal. The AgentCore console shows Lab 3's Runtime,
Gateway and Memory.

## If you get stuck

Each task you build has a **Stuck?** box on the guide with three tabs: hints, a prompt for the
coding coach, and the solution. The `solution` folder in each group holds the same answers as
files. To skip one task, run its apply command:

```bash
uv run scripts/lab_run.py solution --lab N --task NX
```

To finish a whole lab, run the one command below. It backs up your files, applies the lab's
answers, restarts or deploys, sends the requests, runs every check and stops at the first
failure:

```bash
uv run scripts/lab_run.py finish --lab N
```

## Start a lab over

Choose **Terminal > Run Task** and pick **Reset Lab 1** to **Reset Lab 4**: the lab's files,
its database piece and its AgentCore state go back to the start, the other labs stay as they
are, and that lab's checks ignore turns from before the reset. **Reset the whole workshop**
starts everything over, and **Repair workshop files** restores any file you changed or deleted
outside the marked regions. Each task asks you to confirm and defaults to Cancel.

## The coding coach

Claude Code is installed in this terminal and pointed at Amazon Bedrock through the
workshop's instance role; nothing to sign in to. Start it with `claude` and paste the prompt
from your task's **Stuck?** box. It asks before every edit and command, and it is set up to ask
for your prediction, give one hint at a time, and propose a patch inside your region only when
you ask. You run the checks yourself. The guide's coaching page has the two-minute setup.

## At the end

The guide's **Wrap-up** page rebuilds Jessica's credit from her request to the row with one
read-only SQL file, `psql -f workshop/wrap-up-reconstruct.sql`
(`Wrap-up reconstruction passed`), hands you the four contracts as `governed-postgres-agent`, a
skill for reviewing your own team's agents the way a DBA would, and exports your evidence:

```bash
uv run scripts/workshop_evidence.py --save workshop-evidence.txt
```

If this opened as a plain folder rather than a workspace, choose **File → Open Workspace
from File… → Pellier.code-workspace**; the same groups are under `labs/`. For how the
repository is put together, see [README.md](README.md) and the
[task and check map](workshop/README.md).
