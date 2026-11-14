# How Pellier remembers a shopper across conversations

Ask Pellier uses the signed-in shopper's customer ID as the AgentCore Memory actor. Each
conversation keeps its own session ID. A message from Theo in one chat can therefore
produce a preference the agent reads in a later chat. His earlier messages stay in the
first chat.

| Caller | Memory actor | Conversation history |
|---|---|---|
| Shopper with a verified customer mapping | Customer ID, such as `CUST-THEO` | `user-<subject>-session-<session id>` |
| Signed-in user without a customer mapping | The conversation namespace | That same namespace |
| Anonymous visitor, including a simulated persona | `anon-<session id>` | That same namespace |

The managed Storefront and the in-process chat use the same mapping. The server resolves
the customer from the verified identity. Choosing a persona or sending a customer ID in a
message cannot put that message in another shopper's Memory. Older conversations remain
readable under their original subject and session. Preferences previously extracted under
a session-only actor stay there.

A full workshop reset keeps a clean setup conversation. If a seeded shopper also has live
turns, the reset removes that actor's events and extracted records together, then restores
the setup messages. This avoids keeping a live preference that was merged with an older record.

AgentCore extracts preferences in the background. Runtime reads the signed-in shopper's
records from `/pellier/preferences/<customer id>/`. Preferences can shape a recommendation.
Gateway policy and Aurora still decide which customer records a tool may read.

## What Lab 3 shows

Setup supplies Theo's starting conversation. The required Task 3B check names the preference
record IDs a deployed turn used and checks them against Theo's Memory. Participants already
have everything they need for this check.

The optional **Memory and preferences** tab in **Go deeper into Lab 3** lets a participant
say something new as Theo. `uv run scripts/lab3_where_memory_lands.py` reads the live message
and looks for a matching preference in Theo's namespace. A later turn's Builder view names
the records passed to the agent. A recommendation alone cannot establish which record was
used, and a stored message can appear before a preference record exists.
