# Governed workshop browser connection

The governed workshop uses Mosaic's browser access model. CloudFront provides
HTTPS on its generated `cloudfront.net` hostname and connects directly to the
private EC2 host through a VPC origin over HTTP port 80. Code Editor, participant
files, terminals and Pellier all remain on EC2. No SageMaker notebook, custom
domain, participant certificate setup or local proxy client is required.

This is browser HTTPS with a private HTTP origin, not TLS on every network hop.
The owner selected this tradeoff on 23 September 2026 to remove the notebook's
capacity, quota, lifecycle and extra-instance dependencies.

## Source and template contract

- EC2 has no public IP. Its security group permits port 80 only from the
  us-east-1 CloudFront origin-facing prefix list. nginx additionally requires a
  separate per-deployment origin credential supplied by the distribution.
- `scripts/bootstrap-environment.sh` preserves `/editor/` for Code Editor and
  strips `/ports/8000/` before forwarding to Pellier. Both services listen on
  loopback. The origin token differs from the editor connection token.
- CloudFront disables caching and forwards headers, cookies and query strings.
  It sets the trusted HTTPS scheme; nginx overwrites forwarded Host to prevent
  a caller-supplied header from changing OAuth callback construction.
- `scripts/bootstrap-labs.sh` builds the frontend for `/ports/8000/` and persists
  `APP_BASE_PATH`. An explicit `OAUTH_REDIRECT_URI` remains supported. When unset,
  the backend derives the callback from the browser origin plus that prefix.
  A stack custom resource registers the generated distribution callback with
  Cognito after CloudFront exists, avoiding a bootstrap dependency cycle.
- `apiUrl` and `apiFetch` keep requests under the deployed application prefix.
  nginx also rewrites authentication cookie paths beneath `/ports/8000/`,
  including cookie deletion, so CSRF and OAuth state reach their browser requests.
  SSE buffering and compression are disabled in nginx. CloudFront compression is
  also disabled. WebSocket upgrade headers reach Code Editor.
- nginx access logging and WAF sampled requests are disabled for these launch
  paths so the editor token is not recorded there. The response uses
  `Referrer-Policy: no-referrer`.

Local development remains at `/`; an explicit `VITE_API_URL` can select a
separate API origin. New application requests should use the shared API helpers
or the existing Axios client. Avoid root `/api` browser navigation.

## Participant workflow

Workshop Studio exposes exactly two participant links:

- `CodeEditorURL`: `https://<distribution>/editor/?tkn=<generated-token>`.
  Open it directly to edit files and use the terminal. Treat the link as a
  credential; no AWS workspace sign-in or launcher is involved.
- `PellierURL`: `https://<distribution>/ports/8000/`.
  Open it independently of the editor. Use Pellier's navigation for Operator and
  Observatory. Application identity is still handled separately by Cognito.

The throwaway shopper and Operator account details remain in
`/workshop/test-credentials.txt` inside Code Editor.

## Verification boundary

Source tests cover callback construction and the actual nginx config emitter.
The Studio integration test starts real nginx with synthetic backend responses
and checks origin credential rejection, editor authentication, independent app
entry, prefix forwarding, cookies, authorization, forwarded-host normalization,
SSE first-chunk delivery and WebSocket traffic. It makes no AWS API calls.

Live acceptance still requires the exact published package: CloudFormation and
bootstrap completion; real editor file and terminal operations; app refresh;
Cognito login/logout; shopper and Operator streams; and teardown. Local proxy
tests do not prove CloudFront deployment or end-to-end participant acceptance.
