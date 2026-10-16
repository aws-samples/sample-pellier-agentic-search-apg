# Contract 2: ground bounded answers

**Question:** Does the tool preserve the source's facts, including an absence?

**Takeaway:** A missing product is not a product with zero stock. A tool's
available authority and result contract matter more than its prompt.

## Follow the fact to its source

Find the authoritative table or service for the question. Pellier's stock
agent uses warehouse inventory; catalog availability is not a substitute for
warehouse counts. Trace the result through wrappers and the final answer.
The model can explain the result, but cannot invent a count or erase an error.

A useful result contract distinguishes:

| Case | Expected meaning |
|---|---|
| No product matches | Not found; no stock claim |
| Several products match | Ambiguous; resolve the product first |
| One product, recorded quantity zero | Found and sold out |
| One product, stock rows present | Found with the recorded counts |
| Product exists but expected inventory records are missing | Incomplete data, unless the business contract explicitly defines this as zero |
| Query fails | Unavailable or error; no factual answer |

An aggregate such as `coalesce(sum(quantity), 0)` can collapse the first and
third cases. Establish that the product exists before aggregating. A name
lookup may use ids, aliases or lexical matching. Semantic matching is useful
for discovery but must not silently replace the exact product in a stock
claim. Bound candidate matches, warehouse rows and caller-supplied limits.

## Review the tools the agent can actually call

Pellier's Stock agent holds `check_stock` alone. Its prompt cannot grant a
tool, and removing alternative catalog tools closes an unreliable factual
path. For another application, inspect the complete tool set and the SQL
permissions behind it. A tool list is analogous to a function grant, but is
not itself a PostgreSQL privilege and does not stop direct callers from
reaching an exposed backend.

Source inspection establishes configured tools. A correlated execution
record establishes which tool ran. Neither establishes that the final prose
accurately reflected its result; test that separately when reviewing answers.

## Verification

Use explicit case ids for found, zero, missing, ambiguous and failed reads.
Compare the complete returned set against an independently known expected
set. An inner join can hide an omitted warehouse. Check both directions,
duplicates, status and field types; missing evidence must stay visible.

Query `stock` in [proof-queries.sql](proof-queries.sql) compares one recorded
result with a fixture expectation. It includes status and exact JSON values,
so a missing warehouse or an unexpected field fails. Arrays are ordered in
this fixture. If the application's contract treats them as sets, normalize
both sides and still check duplicates. This query verifies a tool result,
not what an agent eventually said to a shopper.

Keep business expectations independent of the function under review. A test
that computes its expected answer by calling the same defective tool proves
nothing about grounding.
