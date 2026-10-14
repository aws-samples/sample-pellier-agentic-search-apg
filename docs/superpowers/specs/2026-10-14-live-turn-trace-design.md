# Live turn traces for terminal-sent turns

Status: approved by the owner on 2026-10-14. Ships before re:Invent only if it passes a new
Workshop Studio test event; until then it lives on `feat/live-turn-trace` and `governed` stays
at `46b45b3d`.

## Problem

Each lab sends the customer's request from the terminal (`python3 scripts/lab_run.py send`),
and the check judges that turn. The Storefront panel cannot show it. `lab_run.py` and the
browser each get their own session from `/api/persona/switch` (`app.py:1715`), choosing a
shopper clears the panel's stored chat (`PersonaContext.tsx:202-224`), the panel's history
hydration reads only its own session and restores text without steps
(`useAgentChat.ts:285-312`), and **How it ranked** is built from the browser's own streamed
steps (`StoreResultsContext.tsx`). The guide's step "read the turn the terminal sent" therefore
lands on an empty chat. `46b45b3d` ships a fallback (send the request again in the browser).

## Goal

The turn the terminal sends, the one the check judges, is visible live in two places:

1. **The terminal.** `lab_run.py send` prints each turn's trace as it streams.
2. **The UI.** The same shopper's Ask Pellier panel shows the turn, labelled "Sent from the
   terminal", with its Builder view trace: the Router step, each tool step, and How it ranked.
   It streams live when the panel is open during the send, and the recent turns appear when
   the panel opens after it.

## Design

### 1. The relay (`pellier/backend/services/turn_relay.py`, new)

An in-memory fan-out keyed by the verified Cognito `sub`. The backend runs as one uvicorn
worker (`bootstrap-labs.sh:1103`), so one process holds every turn and every watcher.

- `publish(sub, turn_id, kind, payload)` records an event for that shopper's channel and
  pushes it to every live subscriber of that `sub`. It never blocks and never raises into the
  turn: a full subscriber queue drops that subscriber, which reconnects and gets the replay.
- Retention: the last 3 terminal turns per `sub`, each kept 30 minutes after it ends, each
  capped at 2 MB of serialized events. Replay omits `content_delta` events when the turn's
  final `content` event is present.
- Limits: at most 5 live subscribers per `sub`; each subscriber queue holds 1,000 events.
- A process restart empties it. Each lab sends after its restart, so the labs' turns survive.

### 2. Publishing from the chat route (`app.py`, `/api/chat/stream`)

- `ChatRequest` gains `source: Optional[Literal["terminal"]] = None`. `lab_run.py` sets it;
  the browser never does.
- The route's `event_generator` is wrapped, not edited: when `source == "terminal"` and
  `get_current_user` returned a verified user with a `sub`, every chunk the route yields is also
  parsed and published to the relay under that `sub`, framed as:
  - `relay_turn` first: `{turn_id, session_id, message, source:"terminal", started_at}`, sent once
    `turn_start` supplies the `turn_id`;
  - `relay_event` for each original event: `{turn_id, event:{...}}`, the event unchanged;
  - `relay_end` after `complete` or `error`: `{turn_id, outcome}`.
- Anonymous turns and browser turns are never published. What the route streams to its own
  caller is byte for byte unchanged.

### 3. The watch stream (`GET /api/chat/watch`, new)

- Requires a verified shopper (`get_current_user`; the browser's httpOnly cookie or a Bearer
  token). Anonymous: `401`.
- Subscribes to the caller's own `sub` and nothing else; there is no parameter that names
  another channel.
- On connect, replays the retained turns (`relay_turn`, its events, `relay_end`, each
  `relay_turn` marked `replay: true`), then streams live ones.
- `data: {json}\n\n` framing as `/api/chat/stream` does, the same headers
  (`Cache-Control: no-cache`, `X-Accel-Buffering: no`), and an SSE comment heartbeat
  (`: keep-alive`) every 15 seconds so CloudFront (`OriginReadTimeout: 60`) and nginx
  (`proxy_buffering off`, `proxy_read_timeout 300`) keep it open.

### 4. The panel (`pellier/frontend`)

- The event handling in `useAgentChat.ts:449-532` moves into one exported function that applies
  a stream event to an assistant message. Local turns and relayed turns both use it, so a
  relayed turn renders exactly like a local one.
- A new `useTerminalTurns` hook, used by the docked panel when a shopper is signed in, reads
  `/api/chat/watch` with `apiFetch` and `credentials: 'include'`, the same reader
  `services/chat.ts` uses. Per `relay_turn` it appends a user bubble and an assistant message
  marked `source: 'terminal'`; `relay_event`s update that message through the shared function;
  `relay_end` completes it. It dedupes by `turn_id`, reports turn events to `onTurn` (so How it
  ranked over the grid follows a relayed turn too), reconnects with backoff (1 s doubling to
  10 s) after a drop, and re-subscribes when the shopper changes.
- A relayed turn carries a small "Sent from the terminal" label, in the panel's existing token
  styles. Its steps, tools and How it ranked show in Builder view like any turn.
- Relayed messages are not written to the panel's localStorage persistence; the relay replays
  them.

### 5. The terminal tail (`scripts/lab_run.py`)

- `send_turn` prints the trace as events arrive, under the turn's existing line, in the words
  Builder view uses (the step's `label` and `finding`; no new wording):
  - the route step: the agent and the Router's finding;
  - each tool step when it finishes: `done` or `failed`, its label, `builder.duration_ms`, and
    its finding;
  - for a step whose `builder.ranking.available`, the top 5 ranking rows: name, full-text rank,
    vector rank, fused rank;
  - then the existing `Pellier:` answer line.
- Lines wrap at 120 columns like the checks. `--quiet` restores today's output.
- Each request carries `"source": "terminal"`.

## Errors and edge cases

- Relay failure of any kind is logged once per turn and never changes the turn or its stream.
- A watcher disconnecting mid-turn loses nothing: on reconnect, the replay brings the turn
  back, ended or still running (a running turn replays what it has, then continues live).
- The browser's own turns never appear twice: the browser never sets `source`.
- A different shopper never sees another's turns: the channel is the verified `sub`, never a
  persona id or session id from the request.
- Lab 4's `send --lab 4 --shopper-only` relays Jessica's turn like any other; Nadia's Operator
  actions are not chat turns and are not relayed.

## Testing

- Backend unit (`tests/test_turn_relay.py`): publish and subscribe by `sub`; another `sub` sees
  nothing; replay order and `replay: true`; the 3-turn and 30-minute retention; the 2 MB cap; a
  full subscriber queue drops only that subscriber; `content_delta` omitted from replay.
- Route (`tests/test_live_turn_trace_route.py`, the `test_turn_id_contract.py` pattern): a
  terminal turn by a verified user publishes `relay_turn`, every event and `relay_end`; the
  caller's own stream is unchanged; a browser turn and an anonymous terminal turn publish
  nothing.
- Watch endpoint: `401` when anonymous; replay then live for the caller's `sub`; heartbeat
  comment; no way to name another channel.
- `lab_run.py` (`tests/test_lab_run.py` pattern, a fake backend): the trace lines for a route
  step, a tool step, a ranking and a failed step; `--quiet`; `source: "terminal"` in the body.
- Frontend unit: the shared event function gives a relayed and a local turn the same message;
  `useTerminalTurns` appends a labelled turn, dedupes by `turn_id`, reconnects after a drop and
  re-subscribes on a shopper change.
- Playwright (`e2e/`, the `page.route` SSE fixture pattern): a relayed turn appears with the
  label and its Builder view steps; the existing specs stay green.
- Full gates: backend suite, frontend `npm test -- --run`, `type-check`, `lint`, `build`,
  `npm audit --omit=dev --audit-level=high`, `git diff --check`, governed-quality CI.

## Ship gate: a new test event

On an event provisioned from this branch, through the CloudFront path prefix:

1. Pellier open as Anna with Builder view on; `send --lab 1` from the terminal: the turn
   appears live, labelled, with its Router step, search step and How it ranked; the terminal
   prints the same trace.
2. Pellier opened after `send --lab 2`: Marco's turns are there.
3. After `lab3-start.sh`, `send --lab 3`: Theo's managed-rail turns relay with their steps.
4. Marco's panel never shows Anna's turns, in two browsers side by side.
5. The watch stream stays open through 10 idle minutes behind CloudFront.
6. `sudo systemctl restart pellier` with the panel open: it reconnects; a new send appears.

Pass: fast-forward `governed`, re-pin Workshop Studio, change Labs 1-3's after-token step to
"the turn you sent is there, marked Sent from the terminal" (with a tip to open Pellier before
sending to watch it stream), and update the lab READMEs. Fail: nothing ships; the `46b45b3d`
fallback stays.

## Out of scope

The Operator; persistence across restarts; any shopper's view of another's turns; relaying
browser turns between tabs.
