# Remembering preferences in a new conversation

This experiment answers a specific question: can a new conversation
recommend products using records that AgentCore extracted from an earlier
conversation? The workshop uses Theo's first conversation in Introduction and
recalls his preferences in Lab 3. The optional **Observatory > Memory** view
(`/observatory/memory`) displays the same evidence when signed in as that shopper.

The source conversation is scripted and visible in the page. Its long-term
records are not seeded. Facts, preferences, a session summary, and completed
episodes must come back from the real AgentCore Memory APIs.
The required exercise uses facts, preferences, the summary and a completed
episode to produce a new recommendation. Closing the second conversation and
inspecting actor-level reflections are optional extensions.

## Before you start

- Complete the managed deployment. Its Memory configuration now declares
  `SEMANTIC`, `USER_PREFERENCE`, `SUMMARIZATION`, and `EPISODIC` strategies.
- Use the backend Python environment and the configured workshop AWS identity.
  The CLI obtains the named shopper's token through the existing workshop
  Cognito credential helper. It never prints the token.
- Run from the application repository root. The commands below use `marco`;
  `anna`, `theo`, and `jessica` have their own briefs.

## Run the demonstration

```bash
# Record a brief and a separate message that closes the first conversation.
python scripts/showcase_agentcore_memory.py learn --persona marco

# Inspect actual resource, strategy, and extraction state.
python scripts/showcase_agentcore_memory.py status --persona marco

# After all four record types, including a completed episode, appear:
python scripts/showcase_agentcore_memory.py recall --persona marco

# Optional: review the answer, then send this scripted acknowledgement.
python scripts/showcase_agentcore_memory.py finish --persona marco

# Optional: inspect the second episode and actor-level reflections.
python scripts/showcase_agentcore_memory.py status --persona marco
```

On a local checkout, use `pellier/backend/.venv/bin/python` if that environment
is not active. Click **Refresh** on the Memory page after each step.

`learn` creates a new isolated run. `recall` reuses an existing cited answer
only if it used all four record types; an incomplete answer can be retried.
`finish` writes an
explicit closing message and refuses an answer without product citations.
It does **not** set the episode to completed. Only AgentCore's consolidated
episode record can do that.

Extraction is asynchronous. Preferences and summaries may appear before an
episode. Prepare the first conversation before a timed demonstration; do not
promise a fixed extraction deadline or use a local timer as completion proof.
Memory extraction and Runtime model invocations can incur AWS charges.

## What the evidence proves

| Evidence | What it establishes |
|---|---|
| First conversation and its event IDs | A scripted conversation was stored in AgentCore short-term memory. |
| Fact, preference, summary and completed-episode record IDs | AgentCore returned all four required long-term record types. |
| New conversation with a different session ID and zero prior chat events | The new invocation did not receive the first conversation's raw chat history. |
| Retrieved record IDs passed to the model | Context came from Memory retrieval, not a repeated shopper brief. |
| Live agent answer, tool results and product IDs | Product grounding came from the managed agent's catalog tools. Memory is not current price or stock truth. |
| An active episodic strategy **and** a consolidated episode record | An episode was returned. An active strategy alone proves only configuration readiness. |

Episode completion and outcome success are different facts. A completed
episode can assess the outcome as unsuccessful. Reflections and in-progress
turn extractions are not rendered as completed episodes.

The service can return the consolidated episode as JSON or XML. The reader
recognizes both schemas and preserves the raw record. Actor-level facts and
preferences can consolidate after later conversations; the source summary and
episode remain session-scoped. The answer's evidence keeps the exact record
IDs and text retrieved for that invocation, even if the live records evolve.
The status response exposes `configurationErrors` and reads reflections separately
under `.reflections.records`; an empty list is not completed extraction.

Fresh-account provisioning also requires an isolated all-four extraction and
retrieval probe. See the [AgentCore readiness contract](AGENTCORE-READINESS.md)
for its record-ID checks, receipt and failure behavior. Participant recall still
uses its own conversation and actual managed product results.

## Identity and source boundaries

The showcase derives an actor from the verified Cognito subject and a fresh
run ID. That actor stays the same across both conversations. A different shopper or a
different run gets a different actor. The read endpoint checks the selected
customer against the verified identity before making any AWS request;
Operator membership does not grant access to shopper memory.

This explicit demonstration does not migrate existing Storefront memory.
Regular Storefront conversations still use
`user-{sub}-session-{sid}` as their actor and session namespace. Aurora
customer history, onboarding preference seeds, runtime skills and
`tool_audit` remain separate sources.

The showcase saves its evidence envelope as a non-conversational JSON blob
event in AgentCore. It is a read model of the demonstration, not an Aurora
transaction receipt or proof that any order, refund or stock change occurred.
The Observatory endpoint only reads; it never provisions a strategy or runs
a shopper turn merely because someone opened the page.

The governed reset helper surveys all four managed namespace prefixes,
including episode reflections. Its existing dry-run and explicit-apply behavior
also covers showcase records; this demonstration does not run a cleanup.

## When something is missing

- **Strategy not configured:** deploy the updated managed project using the
  normal workshop deployment. Runtime and Memory retain their resource names.
- **Waiting for extraction:** refresh later. Do not seed long-term records to
  make the tab green.
- **Answer without product citations:** inspect the deployed Runtime revision.
  The current entrypoint returns `products` and structured `tool_calls`.
- **A profile access error:** sign in as the selected shopper. A persona picker
  changes the requested view; it grants no access.
- **Service unavailable:** check AWS credentials and the configured Memory ID.
  The view never substitutes local fixtures for failed reads.

[Built-in memory strategies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-configuring-built-in-strategies.html)
and [episodic memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/episodic-memory-strategy.html)
describe the service contracts behind the demonstration.
