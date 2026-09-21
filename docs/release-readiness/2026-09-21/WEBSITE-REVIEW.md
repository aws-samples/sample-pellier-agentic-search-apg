# Pellier governed website review — 21 September 2026

Status: **PASS for the bounded local website review.** The final combined
browser run passed all 67 checks after the repairs below.

Scope: the governed website's Storefront → Operator → Observatory journey,
including the premium retail design, responsive layouts, authentication,
keyboard access, reference panels, and real service reads. Source baseline:
`894b04a8` in `.worktrees/governed-product-pass` on `governed`.

This is local website proof against the existing workshop services. It does
not change the hosted release decision, Workshop Studio publication, or the
fresh-account rehearsal gate. The source publication checks are recorded below.

## Design assessment

The existing design has a coherent premium retail identity: warm paper,
espresso navigation, restrained burgundy actions, Fraunces editorial titles,
Instrument Sans for service information, and generous product photography.
Storefront presents the collection and concierge; Operator presents the
client and the case; Observatory presents the evidence. Preserve those roles.

The material improvements were reliability, truthful editorial destinations,
legibility, and continuity between views. No new visual system, extra dashboard
navigation, or larger image dataset was needed. Open service request pills keep
their quiet treatment; their filter and search behavior were exercised.

## Findings repaired

| Finding | Result |
| --- | --- |
| Product zoom allowed Tab to reach the page behind its modal. | The shared focus trap now moves focus into zoom, contains Tab and Shift+Tab, supports Escape, restores the opener, and restores body scrolling. Its backdrop uses the storefront's warm espresso hue. |
| Three Stories cards described unavailable films/essays and all linked to one generic heading. | Each card now introduces Marco, Anna, or Theo and opens that person's actual essay. Router-aware links, focusable targets, and sticky-header clearance make the jump usable on mobile and by keyboard. |
| Hash navigation moved the viewport without moving keyboard focus to the destination. | Keyboard navigation now focuses the target. Pointer navigation keeps its existing behavior. |
| Memory command blocks inherited pale text on a pale background (1.07:1 in the initial scan). | The light code surface explicitly uses the dark ink token. Long command and raw-record regions are keyboard focusable and named. |
| Scrollable skill guidance could not be reached by keyboard. | Each guidance region now receives focus and supports native keyboard scrolling. |
| Architecture category labels were too faint on warm backgrounds. | Quality uses deep amber; Workshop lens uses the stronger existing ink token. Both index and detail views were checked. |
| Tool and skill cards intercepted Enter/Space intended for controls inside the card. | Card selection handles only keys targeted at the card itself. Keyboard activation of discovery and routing now reaches the real endpoints. Tool rows also expose their expanded state. |
| A real Cognito sign-in returned 502 after rejecting a newly issued token with `ImmatureSignatureError`. | JWT validation now allows a fixed five-second clock difference. Tests accept small differences and reject out-of-window issued-at, not-before, and expiry claims; signature, issuer, client, subject, and access-token checks remain active. The maintained fallback twin received the same fix. |
| Session history was oldest-first, putting earlier workshop runs ahead of the turn a participant just completed. | Sessions now show the latest recorded activity first, retaining search, persona filtering, and pagination. |
| Changing a session tab remounted both application error boundaries and fetched the same session again. | Navigation resets a boundary only after an error. Healthy parent routes retain state; Replay, Evidence, and Brief share the loaded session. Failure recovery is still tested. |
| The session Brief introduced a second H1 beneath the session title. | The brief title is now a section heading. |
| Local app health failed because the running backend held an old database credential. | The app was restarted with the current Secrets Manager credential through the existing certificate-verified SSM tunnel. The normal `localhost:5173` app is healthy. No credential was printed or committed. |
| The backend environment lacked the already-declared `defusedxml` dependency, breaking Memory showcase reads and test collection. | Installed the exact `0.7.1` version already in the lockfile; no dependency declaration changed. |
| Operator browser checks waited for network silence and used a separate HTTP client's cookie handling. | Checks now wait for actual UI readiness and use the browser's Secure-cookie behavior for authenticated loopback reads. |

The JWT implementation uses PyJWT's bounded verification allowance; see the
[PyJWT API reference](https://pyjwt.readthedocs.io/en/stable/api.html).

## Coverage

The initial inspection covered **33 routes at 1440, 768, and 390 pixels**:
99 route/viewport combinations, including visible disclosures, rendered
controls, images, overflow checks, page exceptions, and WCAG A/AA checks.
There were no page exceptions, broken loaded images, or horizontal document
overflows in that inspection. Its accessibility failures are preserved in
`website-initial-inspection.json`; that file is deliberately the pre-fix record.

| Surface | Inspected interactions |
| --- | --- |
| Storefront | Welcome tour, scenario selection, collection navigation, product detail, availability, image zoom, bag quantity controls, signed-out order review, mobile menu, About, How Pellier Works, all three Stories destinations, and navigation into the other surfaces. |
| Operator | Real sign-in, membership filters, open-request filter, client search and reset, all 15 client records at desktop and phone widths, record disclosures, all four existing review records, their evidence links, Jessica's read-only storefront preview, and Marco's canonical scenario handoff. |
| Operator investigation | A new read-only Jessica investigation streamed real numbered steps and persisted the investigation trace. No existing review was approved, declined, or executed during the navigation audit. |
| Observatory core | Lab Collection, all four Workbench lab paths, setup and result panels, failure recovery, Govern topics, policy search/disclosure, and links back to the relevant lab. |
| Observatory detail | All seven architecture briefs; all 17 tool contracts and filters; keyboard discovery and skill routing; expanded Memory and Skills evidence; Memory's four tabs and refresh; saved session Replay/Evidence/Brief; search examples, four-strategy retrieval comparison, and the two-pool micro-evaluation. |
| Additional references | Proof Board, Operator lineage, Operator turn, replacement recovery, routing, evaluations, production patterns, and settings were included in the initial route/viewport inspection. |

The real shopper conversation and real Workbench turn were reconciled with
stored, principal-scoped evidence. Govern's five-outcome display was checked
against an existing completed evidence run, including response suppression.
That display check did **not** create a new five-outcome mutation rehearsal.

## Verification record

- Backend: **3,571 passed, 90 skipped**. Skipped integration gates are not counted
  as proof of live execution. Two existing deprecation warnings remain.
- Frontend: **1,132 passed across 158 files**.
- Browser: **67 passed, zero skipped** in the final combined Chromium run
  (6.6 minutes). This includes authenticated live-service checks and controlled
  failure/recovery checks; it is not 67 separate live mutations.
- Final WCAG A/AA automated checks passed on the public journey at 1920,
  1280, and 390 pixels, and on expanded Memory/Skills/architecture references
  at 1440, 768, and 390 pixels. All seven architecture detail pages passed their
  checks. Automated checks supplement the rendered and keyboard review.
- Frontend build, type check, lint, dependency audit, copy compliance, and diff
  whitespace checks **passed**. Dependency audit reported zero vulnerabilities.
- Impeccable's design hook scanned the edited frontend files without reporting
  deterministic design violations. Rendered visual review was also performed.

New regression coverage lives in `pellier/frontend/e2e/retail-journey.spec.ts`.
Existing Operator preview coverage was repaired in
`pellier/frontend/e2e/operator-client-preview.spec.ts`. Focused unit checks cover
modal focus, navigation recovery, session ordering, and bounded JWT clock skew.

The initial pass collected detailed evidence in `/tmp/pellier-design-e2e-20260921/`:
`inspection/report.json`, `baseline.log`, `live.log`, `release-browser.log`,
`frontend-final.log`, `backend-tests.log`, `typecheck-final.log`,
`lint-final.log`, `build-final.log`, `audit.log`, and `final-visuals/`.
That temporary directory is no longer available after the local runtime
transition. `website-initial-inspection.json` retains the initial inspection
summary. Historical failures included the actual token failure, missing
dependency, anchor failure, and repeated session loads; the passing results
reported above followed their fixes.

## Proof boundary and handoff

- PASS is limited to the checked website, current source, and existing workshop
  services. A viewport check is not a physical-device or cross-browser certification.
- Fresh-account provisioning, public-origin/TLS readiness, hosted asset parity,
  room rehearsal, and Workshop Studio publication remain separate gates.
- External password-recovery messages, new account registration, and consequential
  review decisions were not triggered merely to exercise a button. Their UI/error
  paths and deterministic tests are separate from real external side effects.
- Temporary browser checks used workshop identities. Disposable test Operator
  identities were removed; existing customer identities and passwords were not changed.
- The current local preview is `http://localhost:18168`, with the API on 8003
  and the certificate-verified Aurora tunnel. It replaced the earlier 5173
  preview after the local runtime transition. Temporary browser viewport
  overrides were reset.
- Source commit/push, Studio pinning, S3 sync, and publication were not performed
  in this website review.

## Palette follow-up: Mosaic reference

The requested button refinement uses Mosaic's actual dark-wine tokens and
button styling as a reference. Pellier now uses deep Bordeaux `#481626`, with
`#30101b` for hover/pressed states, `#713348` for secondary brand accents, and
`#f2e9eb` for quiet selection backgrounds. A fine inset highlight and low shadow
give primary controls slight depth. Shared aliases carry the palette across
Storefront, Operator, and Observatory; semantic success, warning, and denial
colors retain their existing meanings.

The revised frontend build and the existing accessibility check passed (six
public routes at three viewport widths). Computed base, hover, and keyboard
focus states were also checked on Storefront, Lab Collection, Workbench, and
Operator sign-in at 1440 and 390 pixels: eight combinations passed. The ivory
button-label contrast is at least 13.39:1. This follow-up did not repeat the
earlier authenticated journey checks. Current screenshots
and computed styles are in `/tmp/pellier-color-review/`.

## Operator follow-up: client, conversation, review

The live pass found useful chat functionality outside the ordinary client-list
path, a prepared-review link buried in long conversation history, and a return
from the review that could open the newest thread instead of the discussion the
operator had left. Narrow layouts also placed the composer below a long replay
and the whole review queue before the selected case.

Changes:

- Every client row now visibly offers **Open chat** and navigates to the client
  conversation. The record remains beside it on desktop and has a direct link
  from the chat header on narrow screens.
- A review handoff stays outside the transcript scroller, beside the composer.
  It uses saved proposal IDs, or a pending review for the same client from the
  authenticated queue. A historical proposal is not labeled pending without a
  current queue read. Preparing an action refreshes the shared queue.
- Review links carry client, session, and turn navigation context. **Return to
  conversation** restores that session and turn, including after a review-page
  reload or when a newer client conversation exists. A mismatched client or
  session fails closed; retry does not silently substitute the latest thread.
- The chat pane keeps the composer and handoff reachable at narrow widths.
  **Browse action queue** is collapsed on narrower review pages so the selected
  case leads. It remains available without leaving the case.
- Order and exact-terms tables now support keyboard scrolling with named focus
  regions. The new accessibility tests exposed this pre-existing gap.
- Opening chat or a review performs reads. Preparing a review, confirming its
  exact terms, and executing it remain separate requests and deliberate actions.

Validation of this follow-up:

- **243 Operator unit tests passed** across 16 files. Coverage includes exact
  session restoration, wrong-client/session rejection, retrying the requested
  history, and the unchanged confirmation/execution boundary.
- **4 controlled browser-flow tests passed** at 1440, 768, and 390 pixels:
  client list → chat → prepared review → original conversation, plus a pending
  review surfaced from a newer discussion. All Operator mutations are blocked
  in these fixtures. Accessibility scans passed on chat and review at all three
  widths, with no horizontal document overflow or page exceptions.
- **7 live authenticated browser tests passed**, including client chat/review
  navigation at all three widths and the existing Storefront preview handoffs.
  Navigation emitted no Operator write requests. No existing review was
  confirmed, declined, or executed. The temporary test identity was removed.
- **9 live visual captures** covered client book, chat, and review at the three
  widths. Frontend build, type check, lint, and diff whitespace checks passed.

Durable evidence: [unit tests](operator-flow/unit.txt),
[controlled browser checks](operator-flow/browser.txt), and
[authenticated browser checks](operator-flow/live.txt).
Representative live captures: [desktop chat](operator-flow/chat-1440.png),
[phone chat](operator-flow/chat-390.png), and
[phone review](operator-flow/review-390.png).

This validates navigation, rendering, and existing live reads. It does not
rehearse a new managed investigation, approval, policy decision, or transaction.
Workshop Studio was not changed as part of this work.

## Source publication validation

The complete maintainer gates were rerun after the palette and Operator
follow-ups, before committing the reviewed changes to `governed`:

- Backend: **3,571 passed, 90 skipped**, with the same two dependency
  deprecation warnings. Skipped integration tests remain outside this proof.
- Frontend: **1,138 passed across 158 files**.
- Type check, lint, production build, and production dependency audit: **PASS**.
  The dependency audit reported zero vulnerabilities.
- Shell syntax, diff whitespace, and byte parity of the maintained Cognito
  authentication implementation: **PASS**.

The four controlled Operator browser checks and seven live authenticated
checks above cover the final application changes. They were not repeated for
this documentation-only publication update. Publication does not change the
fresh-account, hosted deployment, or Workshop Studio proof boundaries.
