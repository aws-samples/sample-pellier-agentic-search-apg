import { Link } from 'react-router-dom';
import { EditorialTitle, ExpCard } from '../../components';

/** Source-backed design reference. No synthetic metrics or unavailable API. */
export default function ProductionPatterns() {
  return <div style={{ padding: '40px clamp(20px, 4vw, 48px)', maxWidth: '1100px' }}>
    <EditorialTitle referenceId="production" backToReferences eyebrow="Design reference · Governed L400"
      title="Production patterns"
      summary="Follow identity, memory, tool permission, and committed effects across the governed path. These are implementation contracts; use your run evidence to establish what actually happened." />
    <div style={{ display: 'grid', gap: '20px', lineHeight: 1.65 }}>
      <ExpCard><h2>Bind identity at every boundary</h2>
        <p>A verified Cognito principal and session identify the caller. The managed Runtime forwards the caller token to Gateway. Cedar evaluates permission; the target and Aurora must still validate ownership and business conditions.</p>
        <p>Lab 3 tests both an owned ticket-history read and a foreign customer read before the Storefront request. A successful discovery response does not establish permission for every argument.</p>
        <Link to="/observatory/workbench?lab=managed-agent-path">Open Lab 3: managed identity and tools</Link>
      </ExpCard>
      <ExpCard><h2>Keep memory scope explicit</h2>
        <p>Ordinary Storefront history uses a session-scoped namespace: <code>user-{'{cognito_sub}'}-session-{'{session_id}'}</code> for a signed-in user, or <code>anon-{'{session_id}'}</code> for an anonymous session. Starting a new session changes that namespace.</p>
        <p>The Lab 3 memory experiment deliberately keeps the verified actor stable within an isolated run and starts a new conversation with zero prior chat events. Inspect the extracted records supplied to the agent before claiming continuity. Extraction is asynchronous.</p>
        <Link to="/observatory/architecture/memory">Inspect memory sources and scope</Link>
      </ExpCard>
      <ExpCard><h2>Separate discovery, publication, and permission</h2>
        <p>Aurora can rank tool descriptions using pgvector. Gateway publishes canonical MCP schemas, and caller policy filters discovery and invocation. These are distinct mechanisms.</p>
        <p>Labs 1 and 2 establish the in-process baseline. Lab 3 publishes the missing read and binds it to the managed agent. Staff-only writes stay outside shopper permissions. Compare the discovered names with the expected caller-visible set.</p>
        <Link to="/observatory/architecture/mcp">Trace the managed Gateway boundary</Link>
      </ExpCard>
      <ExpCard><h2>Prove the effect independently of the response</h2>
        <p>Lab 4 separates policy denial, database refusal, a committed action, and replay. Retain the caller, run identifier, request identifier, action hash, receipt, and before/after database state.</p>
        <p>The required sequential replay check proves the observed replay case. Concurrent duplicates, lost responses, transaction rollback, and renewed requests after a policy change require additional fault tests before a production claim.</p>
        <p>Operator Concierge stores a human review checkpoint in PostgreSQL between requests. A managed shopper return follows its own authorization and business checks; it does not inherit that human approval step.</p>
        <Link to="/observatory/workbench?lab=fail-closed-policy">Open Lab 4: decisions and committed effects</Link>
      </ExpCard>
    </div>
  </div>;
}
