# Builder's Session — CloudFormation source

Workshop Studio uploads this folder to
`s3://${AssetsBucketName}/${AssetsBucketPrefix}/` (prefix usually ends with `static/`).

**Bundle files (all in this directory):**

| File | Role |
|------|------|
| `pellier-builders.yml` | Parent stack (`contentspec` entrypoint) |
| `pellier-vpc.yml` | Nested stack |
| `pellier-database.yml` | Nested stack |
| `pellier-code-editor.yml` | Nested stack (`WORKSHOP_FORMAT=builders`) |
| `iam_policy.json` | Participant inline policy (AgentCore + Bedrock models) |

These files are the source of truth for the Builder's Session. Update
CloudFormation here.
