# Lab 3: Deploy

**Theo.** Keep the matching Workshop Studio guide open for the requests, the marked edit regions and the checks.

## Open the file

| File in this folder | Task | Application file |
|---|---|---|
| [3A-1-publish-tool.py](3A-1-publish-tool.py) | Publish the support-ticket tool | `scripts/deploy/gateway_tool_schemas.py` |
| [3A-2-bind-caller.py](3A-2-bind-caller.py) | Bind the support read to the signed-in customer | `pellier/backend/services/agentcore_gateway.py` |

These are links to the actual application files. Saving here changes the file the app or deployment uses; there is no second copy to synchronize. Edit only the marked region named in the guide.

## Check your work

Every prepared terminal starts at the repository root. Run the checks at the point specified in the guide:

```bash
python3 scripts/workshop_doctor.py --lab 3 --phase prerequisites
python3 scripts/lab3_check.py
```

Task 3B deploys the two Task 3A edits. Run the guide’s participant deployment, start a new Theo conversation, and then run `scripts/lab3_check.py`. Editing these files alone does not update Runtime or Gateway.

## If you need a solution

Open [solution/README.md](solution/README.md) when you choose the recovery path. Applying an answer does not complete the lab; repeat the same requests and checks.

[All labs](../../START_HERE.md)
