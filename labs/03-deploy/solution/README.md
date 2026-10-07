# Lab 3 solution

Try the marked task first. These files are the supplied answers, not the files the application executes.

- [3A-published-tools.py](3A-published-tools.py)
- [3A-caller-binding.py](3A-caller-binding.py)

To use the guide’s full recovery path, first save any edits you want to keep. Then run these commands **from the repository root**; they replace the corresponding exercise files:

```bash
cp solutions/the-ledger/gateway/gateway_tool_schemas_solution.py scripts/deploy/gateway_tool_schemas.py
cp solutions/the-ledger/services/agentcore_gateway.py pellier/backend/services/agentcore_gateway.py
```

Task 3B deploys the two Task 3A edits. Run the guide’s participant deployment, start a new Theo conversation, and then run `scripts/lab3_check.py`. Editing these files alone does not update Runtime or Gateway.

Return to the [lab README](../README.md), repeat its checks and continue in Workshop Studio.
