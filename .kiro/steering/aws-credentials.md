---
inclusion: auto
---

# AWS Credential Refresh

## Permanent fix (recommended)

Once set up, you never see `ExpiredTokenException` again — every AWS SDK call pulls fresh creds transparently via `credential_process`.

**One-time setup:**

1. Create `~/bin/ada-credentials-json` (executable) that wraps `ada` and emits the credential_process JSON shape. See `docs/ada-credentials-json.sh` in this repo for the current script (it calls `mwinit --aea` silently first so ada never fails on stale Midway).

2. Add a profile to `~/.aws/config`:

   ```ini
   [profile dat4]
   region = us-east-1
   credential_process = /Users/<you>/bin/ada-credentials-json
   ```

3. Set `AWS_PROFILE=dat4` in `pellier/backend/.env`.

4. Restart the backend. That's it — no more manual refresh.

Caveat: `mwinit -f` may still open a browser occasionally when Midway expires (every ~12h). That's one click, not a full re-auth ritual.

## Manual fallback (when the permanent fix isn't set up)

When you encounter `ExpiredTokenException`, `ExpiredToken`, or `The security token included in the request is expired` in any AWS CLI call, Bedrock API response, or backend log, suggest these steps in order:

1. Refresh Midway auth first (ada depends on it):
   ```bash
   mwinit -f
   ```
2. Then refresh AWS credentials:
   ```bash
   ada credentials update --account 619763002613 --role Admin
   ```
3. Restart the affected service (e.g., the backend uvicorn process).

If `ada credentials update` fails with an auth/cookie error, that means Midway expired — run `mwinit -f` first and retry.
