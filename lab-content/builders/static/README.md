# Builder's Session — static assets for Workshop Studio

Workshop Studio uploads this folder to
`s3://${AssetsBucketName}/${AssetsBucketPrefix}/` (prefix usually ends with `static/`).

**Required files (all in this directory):**

| File | Role |
|------|------|
| `pellier-builders.yml` | Parent stack (`contentspec` entrypoint) |
| `pellier-vpc.yml` | Nested stack |
| `pellier-database.yml` | Nested stack |
| `pellier-code-editor.yml` | Nested stack (`WORKSHOP_FORMAT=builders`) |
| `iam_policy.json` | Participant inline policy (AgentCore + Bedrock models) |

Source-of-truth copies also live under `lab-content/builders/assets/` and `infrastructure/`.
