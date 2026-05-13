# `static/` — Workshop Studio packaging mirror (Builder's Session)

Mirror of the seven Pellier CloudFormation templates plus the participant
IAM policy, packaged for Workshop Studio's 60-minute Builder's Session
deployment.

The parent template here is `pellier-builders.yml` (sets
`LabFormat=builders`, which makes the Code Editor pre-apply the Experience
Guide + restock_shelf + running_low so participants only build Stock
Keeper's system prompt + the floor_check tool).

These files are **symlinks back into `infrastructure/`** — edit originals
there, not here. See `lab-content/workshop/static/README.md` for the full
packaging rationale; the only difference between the two bundles is the
parent template (`pellier-builders.yml` here, `pellier-workshop.yml` in
the workshop bundle) and the contentspec defaults.
