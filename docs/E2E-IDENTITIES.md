# Identities for hosted E2E and manual Cognito checks

The `fresh-deployment-e2e` workflow uses dedicated identities that already exist
in the deployment under test. It does not create users, reset passwords, delete
users, assume an AWS role, or request an OIDC ID token. The Cognito bootstrap and
teardown scripts are optional manual tools for a separately approved disposable
identity exercise.

## Configure the hosted workflow

Configure the protected GitHub environment named `workshop-e2e` before dispatching
[the workflow](../.github/workflows/e2e.yml). Its variable and secrets must belong
to the same approved deployment:

| Environment setting | Purpose |
| --- | --- |
| Variable `E2E_ALLOWED_BASE_URL` | Approved HTTPS origin, including a nondefault port if needed. |
| Secrets `E2E_TEST_USER_EMAIL`, `E2E_TEST_USER_PASSWORD` | Existing dedicated, nonstaff Cognito identity for password sign-in, cookie, refresh, and authorization checks. |
| Secrets `E2E_GOVERN_USERNAME`, `E2E_GOVERN_PASSWORD` | Existing Marco workshop identity for the governed shopper and workbench paths. |
| Secrets `E2E_OPERATOR_USERNAME`, `E2E_OPERATOR_PASSWORD` | Existing staff identity with the deployment's Operator authorization. |

Supply both required dispatch inputs:

- `base_url`: the approved HTTPS origin, without a trailing slash, path, query,
  fragment, or embedded credentials.
- `boundary_run`: an already completed five-outcome boundary proof from that
  deployment, in the form `boundaries-` followed by 32 lowercase hexadecimal
  characters.

[The input validator](../tests/e2e/validate_deployment_inputs.py) runs before
dependency setup and browser tests. It rejects missing live inputs, a non-HTTPS
or malformed origin, a mismatch with `E2E_ALLOWED_BASE_URL`, and an invalid
boundary-run identifier. Format validation does not establish that a boundary
run exists or is complete; the live test checks the supplied run's evidence.

The job runs workshop smoke, persona modal, govern reference, resolution trace,
live workbench, Cognito, and Operator client-preview tests. The Operator preview
signs in through the application's password API with its existing Operator
identity, establishing the browser context's HTTP-only cookies. It does not set
a global `Authorization` header that could be attached to third-party image
requests. No fixed bearer-token secret or AWS identity-management permission is
needed by this workflow.

Keep passwords in the protected environment's secrets and the test process
environment. Configure the three identity pairs explicitly; the manual helper
does not create customer bindings, Marco's persona association, staff groups,
or Operator permissions.

## Optional manual identity creation

Use these tools only with an independently verified, dedicated development pool
and credentials authorized for that pool. The `prod`/`production`/`prd` substring
denylist catches some configuration mistakes. **Passing that check does not prove
that a Cognito pool is nonproduction.** Pool IDs are opaque; verify the actual
account, pool purpose, and IAM scope outside the helper.

The live helper needs a Python environment with `boto3` already installed and
the appropriate pool-scoped administrative permissions:
`cognito-idp:AdminCreateUser`, `cognito-idp:AdminSetUserPassword`,
`cognito-idp:AdminGetUser`, and `cognito-idp:AdminDeleteUser`. This is a separate
manual authorization scope from the hosted workflow.

Provide these environment variables through the approved local configuration and
secret source. Do not put a password on a command line, in a credential JSON
file, or in a checked-in configuration:

| Variable | Used by |
| --- | --- |
| `E2E_COGNITO_POOL_ID` | Creation and cleanup; must match the receipt. |
| `E2E_AWS_REGION` | Creation and cleanup; must match the receipt. |
| `E2E_TEST_USER_EMAIL` | New, disposable user's requested username/email; cleanup must match the original request. |
| `E2E_TEST_USER_PASSWORD` | Creation only; supplied directly to Cognito after the receipt is saved. |
| `E2E_COGNITO_CLIENT_ID` | Required bootstrap configuration for the email/password test client. Admin user operations do not validate the app client's membership or permissions. |

From the repository root, preview the conditional calls:

```bash
python3 tests/e2e/bootstrap_cognito_dev_pool.py --dry-run
python3 tests/e2e/teardown_cognito_dev_pool.py --dry-run
```

Both dry runs require their configuration variables. They create no AWS clients,
read no receipts, write no files, and do not establish live ownership. They do
not need AWS credentials or the AWS SDK. Passwords are redacted in the plan and
never emitted as a final credentials payload. The former `--out` credential-file
option has been removed.

For live creation, use a private directory on a local POSIX filesystem that
supports file permissions, exclusive creation, hard links, and `fsync`. The
receipt path itself must not exist. For example, using the repository's existing
backend Python environment:

```bash
e2e_python="$PWD/pellier/backend/.venv/bin/python"
e2e_receipt_dir="$(mktemp -d "${TMPDIR:-/tmp}/pellier-e2e-identity.XXXXXXXX")"
chmod 700 "$e2e_receipt_dir"
e2e_identity_receipt="$e2e_receipt_dir/identity.json"

"$e2e_python" tests/e2e/bootstrap_cognito_dev_pool.py \
  --receipt "$e2e_identity_receipt"
```

Creation is create-only. The helper reserves an exclusive `identity.json.pending`
file before contacting Cognito. It requests `MessageAction=SUPPRESS` and
`ForceAliasCreation=False`; an existing username or alias causes a nonzero exit
without resetting a password or migrating an alias.

After `AdminCreateUser` succeeds, the helper extracts Cognito's **returned**
username and unique `sub`. It saves and syncs a mode-`0600` file, then atomically
links the complete receipt to the requested path without replacing any existing
file or symlink. Only after that publication succeeds does it set the new user's
permanent password, using the returned username.

The versioned receipt contains only its type, the pool, region, original
requested username, actual returned username, and `sub`. It contains no password,
token, credential output, or unrelated response attributes. Receipt and recovery
files are private identity evidence; keep them outside the repository and
ordinary uploaded test reports.

## Receipt-verified cleanup and retries

After the manual exercise, or after a password-setup failure that left a complete
receipt, retain the same pool, region, and requested email configuration and run:

```bash
"$e2e_python" tests/e2e/teardown_cognito_dev_pool.py \
  --receipt "$e2e_identity_receipt"
unset E2E_TEST_USER_PASSWORD
```

Cleanup does not require the password or app-client ID. It first verifies that
the receipt is a mode-`0600` regular file owned by the current OS user, with one
filesystem link, a complete supported schema, and the configured creation scope.
It rejects receipt symlinks and incomplete `.pending` records. Then it calls
`AdminGetUser` for the actual receipted username. Both the returned username and
unique `sub` must match before `AdminDeleteUser` is called.

| Outcome | Result and retained evidence |
| --- | --- |
| Existing receipt or `.pending` path | Creation fails before an AWS create. Existing content is preserved. Choose a genuinely new exercise identity and receipt after reconciling the earlier attempt. |
| Existing Cognito user or alias | Creation fails without changing that identity's password. The private `.pending` record is retained; it is not proof of ownership. |
| Create fails, times out, or returns an incomplete identity | Nonzero exit, no password setup. Retain `.pending` and any recovery files. A create may have reached Cognito; reconcile the outcome without adopting a user based only on its email. |
| Receipt publication fails after creation | Nonzero exit, no password setup. A completed private `.identity.json.<generated-id>.created` file, when present, records the actual created identity. Preserve the competing destination and all evidence. |
| Password setup fails or its result is uncertain | Nonzero exit with a complete receipt retained. Use receipt-verified cleanup; rerunning creation does not reset the password. |
| Live username or `sub` differs from the receipt | Cleanup fails without deletion. A reused username is not ownership of the new user. |
| Cognito explicitly returns `UserNotFoundException` | Cleanup succeeds and reports absence, without claiming it deleted a user. The receipt is retained. |
| Lookup/delete returns any other error, including access denial or a missing pool | Nonzero exit; the receipt is retained for investigation or a verified retry. |
| Verified deletion succeeds | Success; the receipt is retained. A later cleanup can honestly report that the user is already absent. |

If a destination race left a complete `.created` recovery file with a single
filesystem link, pass its exact path to teardown's `--receipt` option instead of
the competing destination. It undergoes the same scope and live identity checks.
An interrupted publish can leave multiple links, a partial file, or only a
`.pending` record. Preserve the directory and reconcile it before cleanup; do not
fabricate a receipt or blindly remove the destination to retry.

Receipts are local creation evidence, not a signed authorization grant. Protect
the directory and use credentials restricted to the approved pool. Cognito
lookup and deletion are separate operations, with no conditional `sub` argument
on deletion; serialize identity lifecycle operations so another actor cannot
replace a username between verification and deletion. A process or disk failure
between remote creation and saving its response also requires reconciliation.
The helper stops without password setup when it cannot save usable evidence.

Exit codes are `0` for completion or confirmed absence, `1` for missing
configuration/receipt arguments, `2` for the supplemental label guard or CLI
usage errors, `3` for AWS/client-operation failures, and `4` for receipt or
ownership failures. Service exception details are not echoed because they can
contain request data.

The relevant AWS API contracts are [AdminCreateUser](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_AdminCreateUser.html),
[AdminGetUser](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_AdminGetUser.html),
and [AdminDeleteUser](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_AdminDeleteUser.html).

## Local verification

Run the isolated CLI and ownership tests from `pellier/backend`:

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/test_e2e_bootstrap_dry_run.py \
  tests/test_e2e_identity_ownership.py
```

These checks exercise temporary files and injected Cognito responses. They do
not create AWS clients, change live identities, run the hosted workflow, or prove
that a configured pool is a development pool.
