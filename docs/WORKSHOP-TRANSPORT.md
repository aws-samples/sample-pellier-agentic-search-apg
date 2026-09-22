# Governed workshop browser connection

The governed Workshop Studio templates use an authenticated SageMaker notebook
workspace as the browser entry point. Code Editor, participant files and the
Pellier application remain on the private EC2 workshop host.

Browser HTTPS enters the managed workspace. Its local proxy connects to EC2 on
TLS port 443, checking a per-deployment certificate and its DNS identity. EC2
nginx forwards to Code Editor on `127.0.0.1:8080` and Pellier on
`127.0.0.1:8000`. These last connections are same-host loopback HTTP. The host has
no public IP; its security group permits 443 only from the browser workspace.

## Source and template contract

- `scripts/configure-origin-tls.sh` creates the host key and certificate, checks
  their correspondence and validity, and publishes only the public certificate
  to the template-provided Secrets Manager ARN. Reboots reuse the certificate.
  Rotate it by replacing the host and workspace together; it expires after 90 days.
- `scripts/bootstrap-environment.sh` requires `/editor` for the private editor,
  starts nginx with TLS 1.2/1.3 and validates its authenticated editor route using
  the public trust anchor. It does not bypass certificate verification.
- `scripts/bootstrap-labs.sh` keeps the application on loopback, persists the
  explicit `OAUTH_REDIRECT_URI`, and builds the frontend for `/ports/8000/`.
- `apiUrl` and `apiFetch` in `pellier/frontend/src/services/apiBase.ts` keep API
  calls under that deployed prefix. They preserve requests, cookies, cancellation
  and streaming responses without replacing the browser's global fetch function.
- Shopper and Operator streams request `Accept: text/event-stream` to select
  progressive forwarding through Jupyter server proxy. Omitting it buffers the
  response until completion in the pinned proxy version.

Local development remains at `/`; an explicit `VITE_API_URL` can select a
separate API origin. All new application requests should use the shared API
helpers or the existing Axios client. Avoid root `/api` browser navigation.

## Participant workflow

Workshop Studio exposes two participant links: `CodeEditorURL` targets
`/editor/open/` and `PellierURL` targets `/ports/8000/` on the managed workspace.
The workspace root also defaults to the editor entry. Run lab commands in Code
Editor's terminal; open Operator and Observatory from Pellier's navigation.
The separate shopper and Operator sign-in details live in
`/workshop/test-credentials.txt` inside Code Editor.

AWS session authentication remains managed by SageMaker. The direct links contain
neither an editor token nor an expiring presigned URL; the editor token is obtained
only behind the authenticated proxy. Participants do not select a JupyterLab
launcher. New-session and expired-session sign-in redirects must be verified in
the fresh event account for both links.

The paired Workshop Studio package owns notebook roles, launch permission,
network rules, the proxy lifecycle, Cognito callback registration and the
per-deployment trust resource. Publish source and update its source pin together.
A new template paired with older source is not a usable deployment.

## Proof boundary

The Studio integration test uses real Jupyter server proxy and nginx with
synthetic app responses. It checks authentication on both direct entries, the
workspace root redirect, editor redirects, app routing, authorization headers,
cookies, live SSE chunks, WebSockets, certificate and hostname rejection, and
rejection of TLS 1.1.
The source tests cover callback persistence, bootstrap gates and API prefixes.

Those checks do not establish that a new event account has notebook capacity,
the expected Jupyter lifecycle environment or correct event-role permissions.
Before event release, provision and scan the exact pinned package, confirm the
AWS-managed transport boundary, and exercise the real editor, Cognito, both chat
surfaces, application restart, host replacement, rollback and teardown. The
separate Studio transport review contains that rehearsal checklist.
