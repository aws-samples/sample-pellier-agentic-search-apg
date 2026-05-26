# Builder's Session — CloudFormation source

Workshop Studio requires the two-folder layout: `static/` for assets
referenced from `contentspec.yaml` (the parent CFN, IAM policy, and
participant-facing images), and `assets/` for nested CFN children.
**Do not collapse them.** Both upload to
`s3://${AssetsBucketName}/${AssetsBucketPrefix}/` and the parent
stack's nested `TemplateURL` references resolve because all five
files end up siblings at deploy time.

**Bundle files (do not move between folders):**

| File | Role | Lives in |
|------|------|------|
| `pellier-builders.yml` | Parent stack (`contentspec` entrypoint) | `static/` |
| `pellier-vpc.yml` | Nested stack | `assets/` |
| `pellier-database.yml` | Nested stack | `assets/` |
| `pellier-code-editor.yml` | Nested stack (`WORKSHOP_FORMAT=builders`) | `assets/` |
| `iam_policy.json` | Participant inline policy (AgentCore + Bedrock models) | `static/` |

These files are the source of truth for the Builder's Session. Update
CloudFormation in whichever folder the file lives in (per the table
above), then sync to `lab-content/builders/static/` in the
`sample-pellier-agentic-search-apg` repo so the working copy stays
in sync.

**Image assets** (`introduction/`, `prereq/`, `aws-logo.png`) are
participant-facing screenshots referenced from `content/`. They live
in `static/` (per Workshop Studio convention) and must be kept in
sync with `lab-content/builders/static/` in the source repo.
