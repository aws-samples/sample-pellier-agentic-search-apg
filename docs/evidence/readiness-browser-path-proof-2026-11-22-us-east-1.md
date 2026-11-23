# Event readiness from a laptop: proof, 2026-11-22, us-east-1

What was run: `browser_path` and `_get` from `scripts/event_readiness.py` (working tree after
governed `791aa764`), from a laptop, with no credentials, token or sign-in, against one
Workshop Studio event account provisioned from the Studio build that pins governed `791aa764`
(infrastructure revision `cc7420831fa400f6`). Run at 2026-11-22T23:25Z. The account's CloudFront host is
written here as `<distribution>`.

| Request | Answer |
|---|---|
| `https://<distribution>/ports/8000/` (the `PellierURL` output) | HTTP 200, `text/html; charset=utf-8` |
| `https://<distribution>/ports/8000/api/health` | HTTP 200, `application/json`, `"status":"healthy"`, `"database":"connected"`, `"bedrock":"accessible"` |
| `https://<distribution>/editor/healthz` (`CodeEditorURL` without its query, plus `healthz`) | HTTP 200, `application/json`, `{"hasActiveConnections":false}` |
| `https://<distribution>/healthz` | HTTP 404 |
| `https://<distribution>/editor/` without the editor token | HTTP 403 |

`browser_path(PellierURL, CodeEditorURL without its query)` returned no reason: the browser path
answered. Nothing was left afterwards; the requests change no file, row or setting on the box.

## Every account, with the Ops role (23:33 UTC)

The same account's Ops-role credentials, copied from the event console's Teams > Access AWS
account > Ops role, saved as one file of mode 0600 with `AWS_DEFAULT_REGION=us-east-1`, then
`scripts/event_readiness.py --accounts DIR --save FILE` with the hash-pinned laptop packages:

```
File          Account     Region      Instance   Recorded (UTC)     Status
team-01.env   <account>   us-east-1   <i-...>    2026-11-22 18:43   ✅ READY FOR LAB 1
1 of 1 ready
```

Exit status 0. At the time of the check the root stack read `CREATE_COMPLETE`, created
18:03:35 UTC, with a `LastUpdatedTime` 30 s later (18:04:05 UTC); the newest record was written
by the box at 18:43:50 UTC and taken in by CloudWatch at 18:44:13 UTC, and it named the
instance in the nested Code Editor stack's `InstanceId` output. STS GetCallerIdentity,
CloudFormation DescribeStacks, CloudWatch Logs FilterLogEvents and EC2 DescribeInstances all
answered for the Ops role. `--recheck FILE`, with no credentials, then read the same row ✅,
exit 0; the saved file was mode 0600 and its Code Editor URL carried no `tkn=` query.

The event's Teams table before and after: Participant count 1 and Last joined about 5 hours
ago both unchanged (the team had been joined earlier for a walk); Last account access moved
to "Just now", from the console's Ops-role credentials. The credential file was deleted
afterwards.
