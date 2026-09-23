import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowDown, ArrowRight, Check, Copy, RefreshCw, ShieldCheck } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { useObservatoryData } from '../../hooks/useObservatoryData';
import IdentityBoundaryCard from '../understand/IdentityBoundaryCard';
import BoundaryOutcomes from './BoundaryOutcomes';
import type { IdentityObservation, PolicySnapshot } from './governanceTypes';
import TraceScenarioLoop from '../../../shared/trace/TraceScenarioLoop';
import './Govern.css';
import ReferenceBrief from '../../components/ReferenceBrief';
import { imageSrc } from '../../../utils/assetPath';

const BASE = '/observatory/govern';
const CHAPTERS = [
  { id: 'authentication', label: 'Authentication & JWTs', group: 'Identity & access', description: 'Validate the caller. Understand which token travels with the request.' },
  { id: 'permissions', label: 'Roles & permissions', group: 'Identity & access', description: 'Separate shopper scope, Operator authority, and database ownership.' },
  { id: 'agent-access', label: 'Agent Access', group: 'Identity & access', description: 'Follow delegated identity through the agent and its tools.' },
  { id: 'policies', label: 'Cedar policies', group: 'Enforcement & evidence', description: 'Read deployed policy definitions and observed enforcement modes.' },
  { id: 'actions', label: 'Governed actions', group: 'Enforcement & evidence', description: 'Connect human approval, transaction integrity, and safe recovery.' },
  { id: 'verification', label: 'Evidence & verification', group: 'Enforcement & evidence', description: 'Separate authentication, authorization, execution, commit, and output delivery.' },
] as const;
type Chapter = typeof CHAPTERS[number]['id'];

function Notice({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'warning' }) {
  return <div className={`govern-notice govern-notice--${tone}`}>{children}</div>;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section className="govern-section"><h2 className="font-display">{title}</h2>{children}</section>;
}

function Table({ label, headings, rows }: { label: string; headings: string[]; rows: ReactNode[][] }) {
  return <div className="govern-table-scroll" role="region" aria-label={label} tabIndex={0}>
    <table><thead><tr>{headings.map(h => <th scope="col" key={h}>{h}</th>)}</tr></thead>
      <tbody>{rows.map((row, i) => <tr key={i}>{row.map((cell, j) => j === 0
        ? <th scope="row" key={j}>{cell}</th> : <td key={j}>{cell}</td>)}</tr>)}</tbody>
    </table>
  </div>;
}

function Code({ children, label }: { children: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => () => clearTimeout(timer.current), []);
  async function copy() {
    try {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      setFailed(false);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      setFailed(true);
    }
  }
  return <div className="govern-code">
    <div className="govern-code-heading"><span>{label}</span>
      <button type="button" onClick={copy} aria-label={`Copy ${label}`}>
        {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
    <pre tabIndex={0}><code>{children}</code></pre>
    {failed && <p role="status">Copy is unavailable. Select the text to copy it manually.</p>}
  </div>;
}

function EvidenceLink({ to, children }: { to: string; children: ReactNode }) {
  return <Link className="govern-evidence-link" to={to}>{children}<ArrowRight size={16} aria-hidden="true" /></Link>;
}

function IdentityCard() {
  const { data, loading, error, errorStatus, refetch } = useObservatoryData<IdentityObservation>({ key: 'governance/identity' });
  const caller = data?.caller;
  return <section className="govern-observation" aria-label="Current caller observation">
    <div className="govern-observation-heading"><span className="govern-eyebrow">Current caller</span>
      <button className="govern-refresh" type="button" onClick={refetch} disabled={loading}><RefreshCw size={14} />Refresh identity</button>
    </div>
    {loading && <p role="status">Validating the current caller…</p>}
    {error && <Notice tone="warning">{errorStatus === 401
      ? 'The supplied credentials could not be validated. Sign in again. No Cedar decision was made by this identity check.'
      : 'Identity validation is unavailable. This is not a policy denial.'}</Notice>}
    {!loading && !error && data?.state === 'anonymous' && <>
      <h2 className="govern-observation-title">No authenticated caller</h2>
      <p>These reference pages are readable without signing in. Customer evidence and Operator actions have separate access checks.</p>
    </>}
    {(errorStatus === 401 || data?.state === 'anonymous') &&
      <EvidenceLink to={`/signin?returnTo=${encodeURIComponent(`${BASE}/authentication`)}`}>Sign in to inspect your identity</EvidenceLink>}
    {caller && <><h2 className="govern-observation-title">{caller.username} <span className="govern-badge">Validated access token</span></h2>
      <dl className="govern-facts">
        <div><dt>Customer claim</dt><dd>{caller.customerClaim || 'No customer claim'}</dd></div>
        <div><dt>Staff scope</dt><dd>{caller.staffScope || 'No staff scope'}</dd></div>
        <div><dt>Operator group</dt><dd>{caller.operatorGroup ? 'Member of pellier-operators' : 'Not a member'}</dd></div>
        <div><dt>Token type</dt><dd><code>{caller.tokenUse}</code></dd></div>
        <div><dt>Expires</dt><dd>{new Date(caller.expiresAt * 1000).toLocaleString()}</dd></div>
        <div><dt>Subject fingerprint</dt><dd><code>{caller.subjectFingerprint}</code></dd></div>
      </dl>
      <details className="govern-details"><summary>Token contract and safe correlation</summary>
        <dl className="govern-facts govern-facts--single">
          <div><dt>Issuer</dt><dd><code>{caller.issuer}</code></dd></div>
          <div><dt>Client ID</dt><dd><code>{caller.clientId}</code></dd></div>
          <div><dt>Token fingerprint</dt><dd><code>{caller.tokenFingerprint}</code></dd></div>
        </dl>
        <p>Fingerprints are truncated hashes. Raw tokens, passwords, and the full subject are not returned by this view.</p>
      </details>
      <p className="govern-meta">Validated at {new Date(data.observedAt).toLocaleString()}. These claims identify the caller; they do not authorize a particular tool call.</p>
    </>}
  </section>;
}

function Overview() {
  return <>
    <div className="govern-overview-demo">
    <div className="govern-overview-copy">
    <p className="govern-lead">A useful agent needs a clear boundary: who is asking, what it may do, and what actually changed.</p>
    <ol className="govern-chain" aria-label="Governed request boundaries">
      {[
        ['Authenticate', 'Cognito establishes the caller.'],
        ['Authorize', 'Gateway evaluates the tool request with Cedar.'],
        ['Validate & commit', 'Aurora checks live state and records the transaction.'],
        ['Inspect output & verify', 'Output checks may withhold a response. Reconcile receipts and the durable effect.'],
      ].map(([title, text], i) => <li key={title}><span className="govern-step">{i + 1}</span><strong>{title}</strong><p>{text}</p></li>)}
    </ol>
    </div>
    <TraceScenarioLoop />
    </div>
    <Notice><strong>Keep the boundaries separate.</strong> A valid identity does not guarantee permission. A permitted request does not guarantee a commit. Withholding the response does not undo a write. Inspect all five outcomes in Lab 4’s verification view.</Notice>
    <EvidenceLink to={`${BASE}/verification`}>Inspect the five Lab 4 outcomes</EvidenceLink>
    <Section title="Explore the boundaries">
      <div className="govern-chapters">{CHAPTERS.map((chapter, i) => <Link key={chapter.id} to={`${BASE}/${chapter.id}`}>
        <span className="govern-chapter-number">0{i + 1}</span><div><h3>{chapter.label}</h3><p>{chapter.description}</p></div><ArrowRight size={20} aria-hidden="true" />
      </Link>)}</div>
    </Section>
    <Section title="Use this alongside the workshop">
      <p>Labs 1–3 establish the facts an agent can use, how it finds them, and which managed build runs. Lab 4 asks the next question: who may act on those facts, and what proves the outcome?</p>
      <p>Build in the Code Editor, run the required lab checks, then inspect the evidence here. Follow Jessica’s investigation in Operator through a human-confirmed action, then reconcile its recorded effect. The reference explains intended controls; live observations report this environment.</p>
      <EvidenceLink to="/observatory/workbench?lab=fail-closed-policy">Open the governed-action workbench</EvidenceLink>
    </Section>
  </>;
}

function Authentication() {
  return <>
    <p className="govern-lead">Pellier validates a Cognito access token before it treats a request as an authenticated caller.</p>
    <IdentityCard />
    <Section title="From sign-in to a verified principal">
      <p>The hosted sign-in path uses an authorization code with PKCE and a browser-bound state check. The workshop also supplies a password sign-in path. Both establish the same access-token contract for the backend.</p>
      <Table label="Access-token validation" headings={['Check', 'What Pellier requires']} rows={[
        [<code>signature / kid</code>, 'RS256 signature verified against the pool’s JWKS. An unknown signing key triggers a guarded key refresh.'],
        [<code>iss</code>, 'The configured Cognito user-pool issuer.'],
        [<code>client_id</code>, 'The configured app client. An ID token’s aud claim is not a substitute.'],
        [<code>token_use</code>, <><code>access</code>. ID tokens are rejected by this validator.</>],
        [<code>sub / exp</code>, 'A non-empty subject and an expiry in the future.'],
      ]} />
    </Section>
    <Section title="Session handling">
      <p>The backend reads the Bearer header first, then the access-token cookie. Sign-in stores tokens in secure, HttpOnly cookies. The refresh endpoint uses the refresh-token cookie; sign-out clears session cookies and attempts token revocation.</p>
      <Notice><strong>A scenario is not a credential.</strong> Choosing Marco, Anna, or Theo changes the workshop scenario. It does not sign in as that person or change the principal carried to Gateway.</Notice>
    </Section>
    <Section title="Verify the identity boundary">
      <p>Sign in, refresh the caller observation, and compare the customer claim with the scenario you chose. An expired or malformed token is an authentication failure. It is not a Cedar denial.</p>
      <EvidenceLink to={`${BASE}/permissions`}>See what each identity may request</EvidenceLink>
    </Section>
  </>;
}

function Permissions() {
  return <>
    <p className="govern-lead">Authentication establishes who is calling. Application checks, Cedar policies, and PostgreSQL each enforce a different boundary.</p>
    <p>This table describes the source permission model. Inspect the deployed policy set and the exact request’s evidence to establish the protection active in this environment.</p>
    <Table label="Pellier identity and permission model" headings={['Caller', 'Application boundary', 'Managed tool boundary']} rows={[
      ['Anonymous visitor', 'Browse public storefront and reference content. No authenticated customer or Operator evidence.', 'No delegated token for the governed Runtime path.'],
      ['Authenticated shopper', 'Customer reads are scoped to the verified account. Operator routes return 403.', 'Catalogue tools use an explicit allow-list. Customer reads require the matching customer claim.'],
      ['Operator', <><code>pellier-operators</code> group required on every Operator route, including reads.</>, <><code>custom:staff_scope=returns</code> authorizes the staff actions named by the deployed permits.</>],
      ['Authenticated caller without customer or staff claims', 'Signing in alone grants no customer or Operator scope.', 'The source baseline permits the reviewed catalogue tools; protected actions need their own matching permit.'],
    ]} />
    <Notice tone="warning"><strong>Workshop starter exception.</strong> The initial shopper return permit deliberately omits the requested-customer ownership condition. Lab 4 adds the ownership forbid and proves its effect. Read the deployed policy and the measured result before treating this protection as active.</Notice>
    <Section title="Where authority comes from">
      <p>Cognito’s pre-token trigger derives customer and staff claims from server-controlled mappings. A tool argument such as <code>customer_id</code> is a request, not proof of ownership. A membership tier is also not an authorization role.</p>
      <p>The Operator uses their own validated token for a confirmed managed action. Human approval remains a separate requirement; an agent cannot grant itself that approval by requesting a staff tool.</p>
    </Section>
    <Section title="PostgreSQL checks live state">
      <p>SQL checks that the order belongs to the requested customer and meets the business rules. Binding that customer to the verified caller is a separate control. The independent RLS exercise uses a non-owner role without BYPASSRLS and binds the principal within the transaction. Do not assume that a call using the table-owner role receives the same RLS protection.</p>
      <EvidenceLink to={`${BASE}/policies`}>Inspect the observed policy set</EvidenceLink>
      <EvidenceLink to={`${BASE}/verification`}>Compare the expected refusal cases</EvidenceLink>
    </Section>
  </>;
}

function AgentAccess() {
  return <>
    <p className="govern-lead">A managed agent request carries the caller’s identity through to Gateway. Its tool list does not replace authorization.</p>
    <div className="govern-request-path" aria-label="Managed caller identity path">
      {[
        ['Signed-in caller', 'Cognito access token'],
        ['Pellier backend', 'Validate the token and select the execution path'],
        ['AgentCore Runtime', 'Receive the caller’s Bearer token on the managed path'],
        ['AgentCore Gateway', 'Validate delegated identity and evaluate Cedar'],
        ['Tool target → Aurora', 'Execute under service permissions and validate business state'],
      ].map(([title, text], i) => <div key={title}><div className="govern-path-node"><strong>{title}</strong><span>{text}</span></div>{i < 4 && <ArrowDown size={17} aria-hidden="true" />}</div>)}
    </div>
    <Section title="Three different execution paths">
      <Table label="Agent execution paths" headings={['Path', 'Where it runs', 'What to verify']} rows={[
        ['In-process shopper agent', 'Strands in the Pellier backend.', 'Do not attribute a Gateway decision to a call that stayed in process.'],
        ['Managed shopper agent', 'AgentCore Runtime, using Gateway MCP tools.', 'The exact turn’s Runtime fingerprint, JWT passthrough, tool target, and policy evidence.'],
        ['Operator investigation and action', 'In managed mode, the backend invokes a separate IAM-authenticated AgentCore Runtime for the investigation. A confirmed governed action carries the Operator’s token through Gateway.', 'Staff access, the investigation’s Runtime fingerprint and ordered graph nodes, then the separate human decision and action receipt. A managed failure does not fall back to local execution.'],
      ]} />
    </Section>
    <Section title="Discovery, permission, and service credentials">
      <p>A specialist’s tool list limits what it can ask to call. Gateway policies decide whether the caller may make that request with those arguments. AWS execution roles let the service reach its downstream resources; they are distinct from the shopper or Operator principal.</p>
      <p>The governed client requires a caller token and Gateway configuration. It does not silently replace a missing identity with a shared service key. The exact published tool set is visible in the registry.</p>
      <EvidenceLink to="/observatory/tools">Open the tool registry</EvidenceLink>
      <EvidenceLink to="/observatory/proof-board">Inspect an actual managed turn</EvidenceLink>
    </Section>
    <Notice>These pages document Pellier’s connected paths. External IDE onboarding and general machine-to-machine access are not configured by this guide.</Notice>
  </>;
}

function PolicyExplorer() {
  const { data, loading, error, refetch } = useObservatoryData<PolicySnapshot>({ key: 'governance/policies' });
  const [query, setQuery] = useState('');
  const policies = (data?.policies || []).filter(p => `${p.name} ${p.description} ${p.cedar || ''}`.toLowerCase().includes(query.toLowerCase()));
  return <section className="govern-observation" aria-label="Observed Gateway and policy configuration">
    <div className="govern-observation-heading"><span className="govern-eyebrow">Read from the managed control plane</span>
      <button type="button" className="govern-refresh" disabled={loading} onClick={refetch}><RefreshCw size={14} />Refresh policies</button>
    </div>
    {loading && <p role="status">Reading Gateway attachment and policy definitions…</p>}
    {error && <Notice tone="warning">The policy snapshot is unavailable. No enforcement mode or request decision can be established from this read.</Notice>}
    {data && <>
      <dl className="govern-facts">
        <div><dt>Gateway attachment</dt><dd>{data.gatewayMode || (data.gatewayState === 'not-configured' ? 'Not configured' : 'Unknown')}</dd></div>
        <div><dt>Attached to this engine</dt><dd>{data.attachmentMatches === true ? 'Match observed' : data.attachmentMatches === false ? 'Different engine' : 'Not established'}</dd></div>
        <div><dt>Policy definitions</dt><dd>{data.source === 'managed-engine' ? `${data.policies.length} observed${data.complete ? '' : ' · partial read'}` : data.source === 'not-configured' ? 'Engine not configured' : 'Unavailable'}</dd></div>
        <div><dt>Checked</dt><dd>{new Date(data.observedAt).toLocaleString()}</dd></div>
      </dl>
      {data.gatewayMode === 'LOG_ONLY' && <Notice tone="warning"><strong>Gateway is observing, not enforcing.</strong> A would-deny observation does not mean the tool was blocked.</Notice>}
      {data.attachmentMatches === false && <Notice tone="warning">The configured policy engine differs from the Gateway attachment. This policy list cannot establish the Gateway’s effective protection.</Notice>}
      {data.source !== 'managed-engine' && <Notice tone="warning">{data.source === 'not-configured'
        ? 'No policy engine is configured for this backend. This does not prove that the workshop controls are deployed.'
        : 'The managed policy list could not be read completely. A failed read is not an empty engine.'}</Notice>}
      {data.source === 'managed-engine' && !data.complete && <Notice tone="warning">Some definitions or modes could not be read. Missing details remain unknown.</Notice>}
      <div className="govern-lab-state">
        <span className="govern-eyebrow">Lab 4 · ownership rule</span>
        <h2 className="govern-observation-title">{data.labPolicyState === 'present' ? 'Policy name observed' : data.labPolicyState === 'not-observed' ? 'Workshop policy name not observed' : 'Deployment state unknown'}</h2>
        <p>{data.labPolicyState === 'present'
          ? 'The engine lists workshop_identity_match_forbid. Inspect its definition and mode, then run the ownership proof. A matching name does not establish the rule’s correctness.'
          : 'The starter deliberately leaves the shopper return ownership condition for Lab 4. A differently named policy may also implement it; only inspection and a measured request establish protection.'}</p>
      </div>
      <label className="govern-search">Find a policy or action
        <input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search names, descriptions, or Cedar…" />
      </label>
      <p className="govern-meta" role="status">{policies.length} matching {policies.length === 1 ? 'policy' : 'policies'}</p>
      <div className="govern-policies">{policies.map(p => <details className="govern-policy" key={p.id}>
        <summary><span>{p.name}<small>{p.description}</small></span><span className="govern-badge">{p.mode || 'Mode unknown'}</span></summary>
        <div className="govern-policy-body">
          <p className="govern-meta">Policy ID: <code>{p.id}</code></p>
          {p.mode === 'LOG_ONLY' && <Notice tone="warning">This policy is in LOG_ONLY. Do not describe its would-deny result as an enforced denial.</Notice>}
          {p.cedar ? <Code label={`Cedar for ${p.name}`}>{p.cedar}</Code> : <Notice tone="warning">The policy definition could not be read.</Notice>}
          {p.definitionHash && <p className="govern-meta">Definition SHA-256: <code>{p.definitionHash}</code></p>}
        </div>
      </details>)}</div>
      {data.source === 'managed-engine' && data.complete && data.policies.length === 0 && <p>The managed engine returned an empty policy list.</p>}
      <details className="govern-details"><summary>Source and observation boundaries</summary>
        <dl className="govern-facts govern-facts--single">
          <div><dt>Configured engine ID</dt><dd><code>{data.engineId || 'Not configured'}</code></dd></div>
          <div><dt>{data.checkout.source === 'checkout' ? 'Source checkout' : 'Declared source revision'}</dt><dd><code>{data.checkout.revision || 'Not recorded'}</code>{data.checkout.modified === true && ' · local changes present'}</dd></div>
        </dl>
        <p>The checkout revision describes this source tree. The policy hashes describe the definitions just read. Neither proves which Runtime package executed a turn; use the turn’s recorded fingerprint and receipts.</p>
      </details>
    </>}
  </section>;
}

function Policies() {
  return <>
    <p className="govern-lead">Cedar authorizes a caller’s tool request. Read the deployed configuration, then verify its effect on an exact request.</p>
    <PolicyExplorer />
    <Section title="Read a Pellier policy">
      <Table label="Pellier Cedar vocabulary" headings={['Element', 'Meaning in Pellier']} rows={[
        ['Principal', <><code>AgentCore::OAuthUser</code>, with signed customer or staff claims exposed as principal tags.</>],
        ['Action', 'The target-qualified Gateway tool name, such as the experience target’s initiate_return action.'],
        ['Resource', 'The specific Gateway ARN named by the policy.'],
        ['Context', <><code>context.input</code> carries the tool arguments. Compare caller-controlled input with verified claims where ownership matters.</>],
        ['Decision', 'No applicable permit means deny. An applicable forbid overrides a permit. Enforcement also depends on the observed modes.'],
      ]} />
    </Section>
    <Section title="Keep configuration and decisions separate">
      <p>A Gateway attachment uses <code>ENFORCE</code> or <code>LOG_ONLY</code>. Individual policies use <code>ACTIVE</code> or <code>LOG_ONLY</code>. A policy definition naming an action is not evidence that the policy applied to a particular call.</p>
      <Notice><strong>Reading this page changes nothing.</strong> Author and deploy the Lab 4 policy using the workshop’s Code Editor instructions. Refresh here to inspect the result, then run the required proof.</Notice>
      <EvidenceLink to={`${BASE}/verification`}>Verify policy decisions and database effects</EvidenceLink>
    </Section>
  </>;
}

function Actions() {
  return <>
    <p className="govern-lead">Authorization permits an attempt. The approved terms, live business state, and database transaction determine its outcome.</p>
    <Section title="From a proposal to a durable result">
      <ol className="govern-prose-list">
        <li><strong>Prepare.</strong> The agent gathers evidence and proposes an action against an exact customer and record.</li>
        <li><strong>Review.</strong> A human confirms the proposed terms. A suggestion or chat message is not an approval.</li>
        <li><strong>Authorize.</strong> The managed action carries the Operator’s token. The governed execution path requires a verified enforcing Gateway attachment.</li>
        <li><strong>Validate and commit.</strong> SQL checks current ownership, eligibility, and operation keys, and commits the related business state together.</li>
        <li><strong>Reconcile.</strong> A receipt links the decision, execution attempt, and durable result. A retry preserves the original operation identity.</li>
      </ol>
    </Section>
    <Section title="Read the outcome precisely">
      <Table label="Governed action outcomes" headings={['Outcome', 'What it establishes']} rows={[
        ['Policy denied', 'An enforced decision blocked the tool request. Correlate it with the exact invocation and measured absence of execution.'],
        ['Business refused', 'The tool was entered, but a live business rule rejected the operation. Permission did not guarantee a committed return.'],
        ['Committed', 'The durable business result exists and is correlated with the operation.'],
        ['Replayed', 'The same authorized operation key returned its recorded result without another business effect.'],
        ['Outcome unknown', 'The response was interrupted. Establish the durable result before claiming either rollback or success.'],
      ]} />
    </Section>
    <Notice><strong>An idempotency key grants no access.</strong> Recovery still requires the authorized caller and the correct customer scope. Changed arguments must not silently reuse an earlier approved result.</Notice>
    <Section title="Inspect the existing workflows">
      <p>The Operator desk and its receipts preserve the human checkpoint. Replacement recovery also records reservation, outbox, and fulfillment history when that path is deployed. Its fulfillment provider is explicitly a workshop simulator.</p>
      <EvidenceLink to="/operator/reviews">Open Operator reviews</EvidenceLink>
      <EvidenceLink to="/observatory/operator-lineage">Follow the Operator evidence</EvidenceLink>
      <EvidenceLink to="/observatory/replacement">Inspect replacement recovery</EvidenceLink>
    </Section>
  </>;
}

function Verification() {
  return <>
    <p className="govern-lead">Use the exact caller, request key, and recorded outcome. A missing row by itself does not prove a denial.</p>
    <BoundaryOutcomes />
    <Section title="Run the Lab 4 boundary proof">
      <p>Follow Workshop Studio to run the five-outcome proof after deploying the identity rule and managed output policy. It includes the return and RLS matrix, an unsigned Gateway call, two one-cent workshop credits, and a credit replay. Use synthetic workshop data. Output checks never roll back a committed credit.</p>
      <Code label="Lab 4 five-outcome proof">{'python3 scripts/prove_governance_outcomes.py --json /tmp/pellier-evidence/lab-4-boundaries.json'}</Code>
    </Section>
    <details>
      <summary>Inspect the return and RLS subset</summary>
      <p>The combined proof already runs this subset once. Use the isolated command only to diagnose that boundary; another run consumes returnable quantity. It performs real test return attempts, including one eligible return and a replay.</p>
      <Code label="Lab 4 identity and Aurora proof">{'python3 scripts/prove_identity_boundary.py'}</Code>
      <p>The command checks Cedar denial, business refusal, commit, replay, and independent Aurora RLS behavior. Keep its request keys and recorded IDs. This reference page does not run the command or mark the lab complete.</p>
      <p>The cross-principal reconstruction below requires Operator access. Each record retains its provenance; fixture evidence and live provider evidence remain distinct.</p>
      <IdentityBoundaryCard />
    </details>
    <details><summary>Other access and observation boundaries</summary>
      <Table label="Additional governance boundaries" headings={['Case', 'Boundary', 'Evidence to inspect']} rows={[
        ['Shopper opens an Operator route', 'Application authorization refusal', '403 operator_group_required after identity validation. This is separate from Cedar.'],
        ['LOG_ONLY observation', 'Observed evaluation', 'Report would-deny separately from whether execution occurred.'],
        ['No evidence or an unavailable read', 'Unknown', 'No pass, inferred denial, or fabricated zero-row result.'],
      ]} />
    </details>
    <Section title="Follow one request across the boundaries">
      <p>Use the Proof Board and the selected turn’s receipts to connect the validated principal, Runtime revision, Gateway policy observation, execution, and Aurora outcome. “Not correlated” is different from a measured absence.</p>
      <EvidenceLink to="/observatory/proof-board">Open the Proof Board</EvidenceLink>
      <EvidenceLink to="/observatory/workbench?lab=fail-closed-policy">Return to the Lab 4 workbench</EvidenceLink>
    </Section>
  </>;
}

const PAGES: Record<Chapter, () => ReactNode> = {
  authentication: Authentication, permissions: Permissions, 'agent-access': AgentAccess,
  policies: Policies, actions: Actions, verification: Verification,
};

export default function Govern() {
  const { section } = useParams<{ section?: string }>();
  const chapter = CHAPTERS.find(c => c.id === section);
  const [topicsOpen, setTopicsOpen] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    setTopicsOpen(false);
    // The overview and topic routes can mount separate instances. Orient the
    // reader on arrival as well as when a mounted instance changes topics.
    // RouteExperience owns scroll restoration, including browser Back.
    heading.current?.focus({ preventScroll: true });
  }, [section]);
  const Page = chapter ? PAGES[chapter.id] : Overview;
  const index = chapter ? CHAPTERS.findIndex(c => c.id === chapter.id) : -1;
  const next = CHAPTERS[index + 1];
  return <div className="govern-layout">
    <aside className="govern-sidebar">
      <Link className="govern-home" to={BASE} aria-current={!section ? 'page' : undefined}><ShieldCheck size={18} />Govern</Link>
      <p>Identity to durable outcome</p>
      <button className="govern-topics-toggle" type="button" aria-expanded={topicsOpen}
        aria-controls="govern-topics" onClick={() => setTopicsOpen(value => !value)}>
        {topicsOpen ? 'Close topics' : 'Browse Govern topics'}
      </button>
      <nav id="govern-topics" aria-label="Govern topics" data-open={topicsOpen}>
        {['Identity & access', 'Enforcement & evidence'].map(group => <div className="govern-nav-group" key={group}>
          <span className="govern-eyebrow">{group}</span>
          {CHAPTERS.filter(c => c.group === group).map(c => <Link key={c.id} to={`${BASE}/${c.id}`} aria-current={section === c.id ? 'page' : undefined}>{c.label}</Link>)}
        </div>)}
      </nav>
      <Link className="govern-back" to="/observatory/workbench?lab=fail-closed-policy">← Back to Lab 4</Link>
    </aside>
    <article className="govern-content">
      <header className="govern-page-heading"><span className="govern-eyebrow">Pellier Observatory / Govern</span>
        <div className="govern-title-row">
          <h1 className="font-display" ref={heading} tabIndex={-1}>{section && !chapter ? 'Topic not found' : chapter?.label || 'Governed agent access'}</h1>
          {chapter?.id === 'policies' && <a className="govern-cedar-link" href="https://cedarpolicy.com/en" target="_blank" rel="noopener noreferrer" aria-label="Cedar policy language (opens in a new tab)">
            <img src={imageSrc('/assets/icons/cedar/cedar-wordmark.svg')} alt="Cedar" width={84} height={20} />
            <span>Policy language <ArrowRight size={12} aria-hidden="true" /></span>
          </a>}
        </div>
      </header>
      {!chapter && <ReferenceBrief id="govern" />}
      {section && !chapter ? <EvidenceLink to={BASE}>Return to Govern</EvidenceLink> : <Page />}
      {next && (!section || chapter) && <footer className="govern-next"><span className="govern-eyebrow">Continue reading</span><EvidenceLink to={`${BASE}/${next.id}`}>{next.label}</EvidenceLink></footer>}
    </article>
  </div>;
}
