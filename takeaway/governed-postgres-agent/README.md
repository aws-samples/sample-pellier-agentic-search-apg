# Review one agent tool like a database engineer

**Can this agent read or change something it should not?**

Take the four contracts from DAT416 into your next application review. This
Agent Skill helps a coding assistant trace one tool. It returns findings,
supporting evidence and the tests still needed. It is a review aid. It is not
a production certification and it does not replace application tests.

## First use, about 15 minutes

1. Choose one tool and open its repository. Start with a read, such as stock
   lookup, or a write, such as a reimbursement. You need source access.
   Database access is optional.
2. Install the skill, or open [SKILL.md](SKILL.md) and give its instructions to
   your coding assistant.
3. Paste the prompt below with the tool's path. Check the assistant's source
   citations. Then choose one proposed test your team should run next.

```text
/governed-postgres-agent review <tool and source path> against the applicable DAT416 contracts.
Trace its arguments, caller identity, database role and SQL.
Cite the source for each finding.
Separate what the code indicates from behavior actually tested.
Do not change files or execute database writes.
Finish with the smallest useful verification plan.
```

Your output should tell a code finding apart from a passed or failed test.
It should also say what remains untested. Compare it with the
[worked expense review](examples/expense-review.md).

## Install

For Claude Code, from the directory containing the extracted folder:

```bash
mkdir -p ~/.claude/skills
cp -r governed-postgres-agent ~/.claude/skills/
```

Use `.claude/skills/` in a repository for a project-only installation.
Other compatible agents use their own skills directories. The instructions
are plain Markdown. You can also read them without installing anything.

To try the review on Pellier, replace the prompt's tool and path with
`give_store_credit in pellier/backend/services/store_tools.py` and select
contract 4. Trace the database function too. A wrapper alone cannot establish
the write's guarantees. This source review does not require a running event.

## What to read next

| Your question | Reference |
|---|---|
| Do search requirements survive fallback? | [Retrieval](references/01-filter-before-ranking.md) |
| Does missing data become an invented fact? | [Bounded results](references/02-bounded-facts.md) |
| Who decides whose records are accessible? | [Identity and RLS](references/03-bind-identity-enforce-ownership.md) |
| What prevents an unauthorized or duplicate write? | [Controlled writes](references/04-approve-and-deduplicate-writes.md) |
| How do I construct evidence? | [SQL examples](references/proof-queries.sql) |
| What changes across AgentCore Gateway? | [Optional MCP reference](references/mcp-publishing.md) |

## Runnable examples

[examples/setup.sql](examples/setup.sql) provides a small independent schema,
roles, fixture data and a controlled credit function. The worked review gives
the setup and probe commands. Use an empty disposable PostgreSQL database
where you can create roles. The example does not connect to AWS or use
workshop data.

The core example and its regression checks were run on PostgreSQL 18.6. They
demonstrate selected invariants. They do not show compatibility with every
Aurora or RDS version. The optional vector guidance requires pgvector and
your own representative data. Adapt the examples to your schema and expected
results before using them in an application review.
