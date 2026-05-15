# Builder's Session — copy-paste escape hatches

DC Summit hands-on: **one exercise** (`floor_check`). Everything else is pre-applied
or demonstrated (AgentCore STM + Runtime).

## floor_check (section 02)

```bash
cp solutions/closing-marcos-gap/services/agent_tools.py \
   pellier/backend/services/agent_tools.py
```

Or paste only the tool body from `solutions/builders/floor_check_tool_body.py` into
`pellier/backend/services/agent_tools.py` between the `floor_check` challenge markers.

## AgentCore Runtime entrypoint (reference — pre-deployed at bootstrap)

The live entrypoint is `pellier/backend/agentcore_runtime.py`. Bootstrap runs
`agentcore configure` + `agentcore launch` before you sit down. In-room you read
that file and invoke with `USE_AGENTCORE_RUNTIME=true` — you do not launch again.
