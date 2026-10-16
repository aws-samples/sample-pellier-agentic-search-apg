# Review one agent tool like a database engineer

**Can this agent read or change something it should not?**

Take the four contracts from DAT416 into your next application review. This
Agent Skill helps a coding assistant trace one tool and return findings,
supporting evidence and the tests still needed. It is a review aid, not a
production certification or a replacement for application tests.

## First use: allow about 15 minutes

1. Choose one tool and open its repository. Start with a read, such as stock
   lookup, or a write, such as a reimbursement. You need source access;
   database access is optional.
2. Install the skill or open [SKILL.md](SKILL.md) and give its instructions to
   your coding assistant.
3. Paste the prompt below with the tool's path. Check the assistant's source
   citations and choose one proposed test your team should run next.

```text
/governed-postgres-agent review <tool and source path> against the applicable DAT416 contracts.
Trace its arguments, caller identity, database role and SQL.
Cite the source for each finding.
Separate what the code indicates from behavior actually tested.
Do not change files or execute database writes.
Finish with the smallest useful verification plan.
```

Your output should distinguish a code finding from a passed or failed test,
and say what remains untested. Compare it with the
[worked expense review](examples/expense-review.md).

## Install

For Claude Code, from the directory containing the extracted folder:

```bash
mkdir -p ~/.claude/skills
cp -r governed-postgres-agent ~/.claude/skills/
```

Use `.claude/skills/` in a repository for a project-only installation.
Other compatible agents use their own skills directories. The instructions
are plain Markdown and can also be read without installing anything.

To try the review on Pellier, replace the prompt's tool and path with
`give_store_credit in pellier/backend/services/store_tools.py` and select
contract 4. Trace the database function too; a wrapper alone cannot establish
the write's guarantees. This source review does not require a running event.

## What to read next

| Your question | Reference |
|---|---|
| Do search limits survive fallback? | [Retrieval](references/01-filter-before-ranking.md) |
| Does missing data become an invented fact? | [Bounded results](references/02-bounded-facts.md) |
| Who decides whose records are accessible? | [Identity and RLS](references/03-bind-identity-enforce-ownership.md) |
| What prevents an unauthorized or duplicate write? | [Controlled writes](references/04-approve-and-deduplicate-writes.md) |
| How do I construct evidence? | [SQL examples](references/proof-queries.sql) |
| What changes across AgentCore Gateway? | [Optional MCP reference](references/mcp-publishing.md) |

## Runnable examples

[examples/setup.sql](examples/setup.sql) supplies a small independent schema,
roles, fixture data and a controlled credit function. The worked review gives
the setup and probe commands. Use an empty disposable PostgreSQL database
where you can create roles. It does not connect to AWS or use workshop data.

The core example and its regression checks were exercised on PostgreSQL
18.6. They demonstrate selected invariants, not compatibility with every
Aurora or RDS version. The optional vector guidance requires pgvector and
your own representative data. Adapt the examples to your schema and expected
results before using them in an application review.
