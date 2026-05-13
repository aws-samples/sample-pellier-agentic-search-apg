# `static/` — Workshop Studio packaging mirror

This directory exists for Workshop Studio's content packaging step. When the
event team builds the workshop bundle, everything in `static/` is uploaded to
`s3://${AssetsBucketName}/${AssetsBucketPrefix}/static/` and
`pellier-workshop.yml` resolves the nested-stack URLs from there.

The files here are **symlinks back into `infrastructure/`** — that directory
is the single source of truth for every Pellier CloudFormation template and
the participant IAM policy. Do not edit the symlinks; edit the originals
under `infrastructure/` and Workshop Studio will pick up the change on the
next package build.

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

## Why not just point Workshop Studio at `infrastructure/`?

Workshop Studio's `templateLocation` is resolved relative to the lab content
root, not the repo root. Symlinks let us keep one source of truth without
duplicating ~80 KB of YAML across two contentspecs.
