# Templates

The four CloudFormation templates Workshop Studio deploys for a DAT416 event, owned here.

| File | Stack | What it creates |
|---|---|---|
| `pellier-governed.yml` | root | the three nested stacks below, the shared `WorkshopId`, and the Outputs the guide reads |
| `pellier-vpc.yml` | `VpcStack` | the VPC, two public and two private subnets, two NAT gateways, three interface endpoints |
| `pellier-database.yml` | `DatabaseStack` | the Aurora PostgreSQL Serverless v2 cluster, its secret and its log group |
| `pellier-code-editor.yml` | `CodeEditorStack` | the Code Editor host, Cognito, CloudFront, the KMS key for AgentCore logs, and the bootstrap that builds Pellier |

The Workshop Studio repo copies these files at each repin and rewrites the `RepoRevision` and
`InfrastructureRevision` defaults in its copies; everything else stays byte-identical, which its
validator checks. `deploy/own-account/deploy.py` uploads them to a private bucket and deploys them
in your own account; the `InfrastructureRevision` it passes is the digest of these four files,
computed the way the Studio tool computes it. Lint them with `cfn-lint deploy/own-account/templates/*.yml`.
