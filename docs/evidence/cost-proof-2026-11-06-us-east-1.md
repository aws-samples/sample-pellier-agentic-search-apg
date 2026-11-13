# Cost proof, 2026-11-06, us-east-1

One scripted pass through the four labs on a Workshop Studio test event, measured for the cost
section of [Run Pellier in your own account](../run-in-your-own-account.md#1-what-you-get-and-what-it-costs).
Usage is from the event account's CloudWatch metrics. Prices are from the AWS Price List API
(GetProducts, regionCode us-east-1) or the AgentCore, Aurora and Cognito pricing pages, read on
6 November 2026. The values were written down during the measurement that evening; nothing is
rounded or recalled.

| Item | Value |
|---|---|
| Account | a Workshop Studio test event account, ID withheld; Region us-east-1 |
| Source the host ran | `5f099fe27023ce3bf66b607f1f91d5cc8fdaa4dd` on `governed`, plus the then-uncommitted credit-owner change, a SQL delta taken from the patched `001_schema.sql` and applied to the database at 15:27:43Z, released later that day as `9f5e07f2` |
| Infrastructure revision | not recorded |
| What ran | the workshop reset at 15:22:03Z, then `uv run scripts/lab_run.py finish --lab N` for Labs 1 to 4, then `uv run scripts/follow_credit.py` |
| Aurora cluster | created 13:39:05Z; Aurora Standard (`StorageType` unset); 0 to 16 ACU, auto-pause after 300 s |

## Timeline of the pass (UTC)

Reset 15:22:03, credit-owner delta applied 15:27:43, `finish --lab 1` 15:27:44, Lab 2 15:28:10, Lab 3
15:28:26, Lab 4 with Nadia's investigation and credit 15:32:12, log-export wait 15:34:12, `follow_credit` 15:36:42, done 15:36:48.
Requests (`scripts/lab_run.py` conversations): Anna 2, Marco 2, Theo 3, Jessica 1, then Nadia's
investigation.

An earlier pass the same day, Labs 1 to 3 ending 14:41Z and Lab 4 ending 14:47Z, was not
measured separately. Aurora's totals below include it.

## Amazon Bedrock

`AWS/Bedrock` per minute, by model ID, 15:20 to 15:40Z. No model read or wrote cache tokens.

| Minute | Claude Opus 5.5 | Claude Sonnet 5.5 | Cohere Embed v4 |
|---|---|---|---|
| 15:27 | 4 calls, 19,546 input, 733 output | 1 call, 1,511 input, 139 output | 4 calls, 18 tokens |
| 15:28 | 2 calls, 11,904 input, 542 output | 5 calls, 13,804 input, 550 output | 2 calls, 19 tokens |
| 15:31 | 7 calls, 27,735 input, 1,211 output | | 4 calls, 23 tokens |
| 15:32 | 3 calls, 8,974 input, 506 output | | |
| 15:33 | 5 calls, 16,963 input, 751 output | 1 call, 1,187 input, 104 output | 1 call, 2 tokens |
| 15:34 | | 3 calls, 5,587 input, 600 output | |
| **Total** | 21 calls, 85,122 input, 3,743 output | 10 calls, 22,089 input, 1,393 output | 11 calls, 62 tokens |

Cohere Rerank 3.5: 7 invocations of at most 30 documents each (`RERANK_MAX_DOCUMENTS`). Catalog
searches also call Sonnet for structured extraction, so Labs 1 and 2, and Labs 3 and 4, are
reported as pairs rather than per customer.

## AgentCore, logs, network and Lambda

For the pass only, 15:27 to 15:37Z:

- Runtime: 8 `InvokeAgentRuntime` invocations. Runtime bills until its sessions close; the
  five-minute buckets from 15:25 to 15:50Z total 0.03106 vCPU-hours and 1.86669 GB-hours.
- Gateway: 58 operations. Policy: 13 allow and 2 deny decisions, and 1 request with no
  determining policy.
- Memory: 34 events written (`CreationCount`), 11 `ListMemoryRecords` calls, 6 `ListEvents`
  calls, 13 `CreateEvent` calls, no `RetrieveMemoryRecords`. The reset before the pass made 224
  `ListMemoryRecords` and 56 `ListEvents` calls, which the pass's figures leave out.
- CloudWatch Logs: 2,324,612 bytes ingested.
- NAT gateways: 1,396,176 bytes each way. Interface endpoints: 1,039,324 bytes processed.
- Lambda: 26 invocations, 5,821.73 ms in all (five functions at 128 MB, one at 512 MB).

## Aurora

- `ServerlessDatabaseCapacity` in 30-minute buckets: 0.00 at 13:30Z (creation), then a minimum
  of 0.50 ACU or more in every bucket from 14:00Z to 23:00Z, and exactly 0.50 in every bucket from
16:00Z to 23:00Z, after both passes. It never paused.
- ACU-hours: 7.919 from 13:39 to 23:00Z; 0.762 during the pass.
- I/O over the cluster's life to 23:00Z: 15,172 reads and 713,668 writes.
- `VolumeBytesUsed`: 834,519,040.

## Other usage and the template

- CloudFront: 135 requests and 69,324,964 bytes downloaded, 10:00 to 23:00Z.
- Template: one `c6g.2xlarge` with a 100 GiB gp3 volume, two NAT gateways, three interface
  endpoints in two subnets, a WAF web ACL with two rules, one KMS key and six Secrets Manager
  secrets.

## The Claude Code coach

Run on the host with `claude -p` (Claude Code 2.1.316, Claude Sonnet 5.5):

- Task 1A's coach prompt from the guide: 4 turns, 30,893 tokens written to the cache, 54,102
  read from it, 6 input and 1,320 output; Claude Code reported $0.0958547 at list prices.
- Task 1B's coach prompt: 3 turns, 14,854 written to the cache, 63,187 read, 6 input and 824
  output; $0.0517057. This run disallowed Edit, Write and NotebookEdit.

## Prices (us-east-1, 6 November 2026)

- Claude Opus 5.5 (global): $4 input, $20 output, $0.20 cache read and $5 cache write per million
  tokens. Claude Sonnet 5.5 (global): $2, $10, $0.10 and $2.50.
- Cohere Embed v4 $0.12 per million tokens; Cohere Rerank 3.5 $0.002 per search unit.
- AgentCore Runtime V1 $0.0895 per vCPU-hour and $0.00945 per GB-hour (V2 $0.1276 and $0.0169);
  Gateway $0.005 per 1,000 operations; Policy $0.000025 per authorization request; Memory $1 per
  GB of events written and $0.20 per GB read (12 KB to 64 KB billed per event), $0.10 per
  GB-month of events, $0.75 per 1,000 long-term records a month and $0.50 per 1,000 retrievals.
- EC2 `c6g.2xlarge` $0.272 an hour; EBS gp3 $0.08 per GB-month; NAT gateway $0.045 an hour and
  $0.045 per GB; public IPv4 $0.005 an hour; interface endpoint $0.01 an hour per Availability
  Zone and $0.01 per GB.
- Aurora PostgreSQL Serverless v2 $0.12 per ACU-hour (I/O-Optimized $0.16); storage $0.10 per
  GB-month (I/O-Optimized $0.225); I/O $0.20 per million; Database Insights Advanced $0.003125
  per ACU-hour.
- WAF $5 per web ACL and $1 per rule a month; Secrets Manager $0.40 per secret a month; KMS $1
  per key a month; CloudWatch Logs ingestion $0.50 per GB; Lambda $0.20 per million requests and
  $0.0000166667 per GB-second; CloudFront $0.085 per GB out (first 10 TB) and $0.01 per 10,000
  HTTPS requests; Cognito's free tier covers 10,000 monthly active users.

## How the page derives its figures

This section is arithmetic on the values above, at the prices above. It is not a measurement.

- **Labs 1 and 2** are the 15:27 and 15:28Z minutes: Opus 6 calls, 31,450 input and 1,275
  output tokens; Sonnet 6 calls, 15,315 and 689. $0.189.
- **Labs 3 and 4**, Nadia's investigation included, are 15:31 to 15:34Z: Opus 15 calls, 53,672
  and 2,468; Sonnet 4 calls, 6,774 and 704. $0.285.
- **Search ranking**: 7 reranks at $0.002, $0.014; the 62 embedding tokens cost less than a
  hundredth of a cent.
- **AgentCore**: Runtime $0.0204, and Gateway and Policy $0.0007 for 58 operations and 15
  decisions (16 if the request with no determining policy bills, which rounds the same). The
  metrics do not show event sizes, how many events each read returned or whether a record list
  bills as a retrieval. With every event at 12 KB and no list billed, Memory adds $0.0004, so the
  floor is $0.021. With every event at 64 KB, each of the six event reads returning all 34 events,
  and each of the 11 record lists billed as a retrieval, Memory adds about $0.0103, so the ceiling
  is $0.031.
- **Logs, Lambda and network**: about $0.001. The pass totals $0.51 to $0.52.
- **The hourly table** prices the template's resources and Aurora's 0.5 ACU floor: $0.5193 an
  hour, about $379 a month. It counts the seven secrets the templates hold today; the staff
  Runtime added the seventh on 8 November 2026. Six or seven secrets with the key both round to
  $0.005 an hour.
- **A whole run**: the [own-account proof](own-account-proof-2026-10-30-us-west-2.md) deployed in
  39 min 43 s and tore down in 31 min 7 s. With a two-hour session that is 3 h 10 min 50 s, at
  $0.5193 an hour $1.65.
- **Aurora above its floor**: 7.919 ACU-hours less 0.5 ACU over the 9.35 hours from creation to
  23:00Z leaves 3.244 ACU-hours, $0.39, for the setup, both passes and the idle time. Standard
  cost $0.95 for capacity and $0.146 for I/O, $1.10 in all, so I/O was 13%; I/O-Optimized would
  have cost $1.27.
