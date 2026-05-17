# `static/` — Workshop CloudFormation source

This directory is the source of truth for the 120-minute Workshop Studio
CloudFormation bundle. When the event team builds the workshop bundle,
everything in `static/` is uploaded to
`s3://${AssetsBucketName}/${AssetsBucketPrefix}/static/`, and
`pellier-workshop.yml` resolves the nested-stack URLs from there.

## What ships in this bundle

`pellier-workshop.yml` — the parent stack for the 120-minute re:Invent
workshop. Sets `LabFormat=workshop` and delegates to `pellier-labs.yml`,
which composes VPC + Aurora + Cognito + Code Editor.

The four nested children (`pellier-vpc.yml`, `pellier-database.yml`,
`pellier-cognito.yml`, `pellier-code-editor.yml`) and the labs orchestrator
(`pellier-labs.yml`) need to be in this directory because the parent stack
resolves them via `${TemplatesBaseUrl}/<name>.yml`, and Workshop Studio
populates `TemplatesBaseUrl` from `{{.AssetsBucketName}}` /
`{{.AssetsBucketPrefix}}` (see `../contentspec.yaml`).

`iam_policy.json` — attached to the participant role by Workshop Studio.

## Why the templates live here

Workshop Studio's `templateLocation` is resolved relative to the lab content
root, not the repo root. Keeping the CloudFormation templates in this
`static/` folder makes the packaged artifact match the files reviewers edit.
