import { useState } from 'react';
import MarkdownMessage from '../../../components/MarkdownMessage';
import { RefreshCw } from 'lucide-react';
import { StateBadge } from '../../../shared';
import { TabNav } from '../../components/TabNav';
import { useObservatoryData } from '../../hooks/useObservatoryData';
import './MemoryShowcase.css';

type Kind = 'facts' | 'preferences' | 'summary' | 'episodic';
interface RecordEvidence {
  id: string; content: string; raw: string; strategyId: string; namespaces?: string[];
  kind?: Kind;
  episode: { situation: string; intent: string; assessment: string; justification: string } | null;
}
interface ShowcaseState {
  resourceStatus: string;
  strategies: Record<Kind, { strategyStatus: string; state: string; namespace: string | null; records: RecordEvidence[] }>;
  proof: null | {
    sourceSessionId: string; sourceEventId: string;
    conversation: { role: string; content: string }[];
    recall: null | {
      sessionId: string; historyEventsLoaded: number; question: string; answer: string; closingMessage?: string;
      records: RecordEvidence[]; products: { productId?: string; id?: string; product_id?: string; name?: string; price?: number }[];
    };
  };
}
const TABS: { id: Kind; label: string }[] = [
  { id: 'preferences', label: 'Preferences' },
  { id: 'facts', label: 'Facts' },
  { id: 'summary', label: 'Summary' },
  { id: 'episodic', label: 'Episodic (optional)' },
];
const REQUIRED_TYPES: Kind[] = ['facts', 'preferences', 'summary'];

export default function MemoryShowcase({ persona }: { persona: string }) {
  const [tab, setTab] = useState<Kind>('preferences');
  const { data, error, loading, refetch } = useObservatoryData<ShowcaseState>({ key: `memory-showcase-${persona}` });
  const panel = data?.strategies[tab];
  const proof = data?.proof;
  const recall = proof?.recall;
  const complete = panel?.state === 'completed';
  const returnedTypes = REQUIRED_TYPES.filter(kind => data?.strategies[kind].records.length).length;
  const independentConversation = recall?.historyEventsLoaded === 0
    && recall.sessionId !== proof?.sourceSessionId;
  return (
    <section className="memory-showcase" aria-labelledby="memory-showcase-title">
      <div className="memory-showcase-heading">
        <div><img src="/services/amazon-bedrock-agentcore.png" alt="" width="32" height="32" />
          <h2 id="memory-showcase-title">Use learned preferences in a new conversation</h2></div>
        <button type="button" onClick={refetch} disabled={loading} aria-label="Refresh memory showcase evidence"><RefreshCw size={15} />Refresh</button>
      </div>
      <p className="memory-showcase-intro">Follow a preference from the first conversation into a new recommendation. Check the records returned by each service.</p>
      <dl className="memory-showcase-owners" aria-label="Service roles">
        <div><dt>AgentCore Memory</dt><dd>Conversation events and extracted preferences.</dd></div>
        <div><dt>Aurora PostgreSQL</dt><dd>Current products, prices, stock, and order records.</dd></div>
      </dl>
      <p className="memory-showcase-scope">This exercise shares one verified actor across two conversations with different session IDs. Regular Storefront conversations keep their existing session scope.</p>
      {error && <div className="memory-showcase-notice" role="alert"><strong>Memory evidence unavailable</strong><p>{error}</p></div>}
      {loading && <p role="status">Reading AgentCore evidence…</p>}
      {data && <>
        <ol className="memory-showcase-steps">
          <li><strong>Share preferences</strong><span>{proof ? 'Conversation recorded' : 'Ready to begin'}</span></li>
          <li><strong>Extract memory</strong><span>{returnedTypes} of 3 required record types returned. Episodic is optional.</span></li>
          <li><strong>Recall and recommend</strong><span>{recall ? (recall.products.length ? 'Answer and products returned' : 'Answer returned without product citations') : 'Waiting for a new conversation'}</span></li>
        </ol>
        {proof && <details className="memory-showcase-details"><summary>First conversation: share preferences</summary>
          <code>{proof.sourceSessionId}</code>
          {proof.conversation.map((turn, index) => <p key={index}><strong>{turn.role === 'USER' ? 'Shopper' : 'Pellier'}:</strong> {turn.content}</p>)}
          <code>Event {proof.sourceEventId}</code>
        </details>}
        <TabNav className="memory-showcase-tabs" tabs={TABS} activeTab={tab} onTabChange={id => setTab(id as Kind)} />
        <div role="tabpanel" aria-label={TABS.find(t => t.id === tab)?.label} className="memory-showcase-records">
          <div className="memory-showcase-status"><StateBadge tone={panel?.strategyStatus === 'ACTIVE' ? 'live' : 'attention'}>Strategy {panel?.strategyStatus.toLowerCase().replace(/_/g, ' ')}</StateBadge>
            <span>{complete ? 'Completed episode returned by AgentCore' : panel?.records.length ? `${panel.records.length} extracted record${panel.records.length === 1 ? '' : 's'}` : !proof ? 'No conversation recorded' : panel?.strategyStatus === 'ACTIVE' ? 'Waiting for extraction' : 'Strategy is not ready'}</span>
          </div>
          {!panel?.records.length && <p>{tab === 'episodic' ? 'An active strategy is not a completed episode. This optional tab waits for a consolidated AgentCore record; Aurora orders and seeded history do not count.' : !proof ? 'Record the first conversation in the Code Editor, then refresh this view.' : 'Extraction runs asynchronously. Continue the workshop and refresh later; the app does not supply substitute records.'}</p>}
          {panel?.records.map(record => <article key={record.id} className="memory-showcase-record">
            <p>{record.content}</p>
            {record.episode && <p><strong>Outcome assessment:</strong> {record.episode.assessment}</p>}
            <details><summary>Inspect record evidence</summary>
              <dl className="memory-showcase-identifiers">
                <div><dt>Record ID</dt><dd><code>{record.id}</code></dd></div>
                <div><dt>Strategy ID</dt><dd><code>{record.strategyId}</code></dd></div>
                <div><dt>Namespace</dt><dd><code>{record.namespaces?.join('\n') || panel.namespace}</code></dd></div>
              </dl>
              <pre tabIndex={0} role="region" aria-label="Raw memory record">{record.raw}</pre>
            </details>
          </article>)}
        </div>
        {proof && recall && <div className="memory-showcase-answer">
          <h3>{independentConversation ? 'New conversation' : 'Recall result'}</h3>
          <dl className="memory-showcase-inputs" aria-label="Context supplied to this answer">
            <div><dt>Prior chat events</dt><dd>{recall.historyEventsLoaded}</dd></div>
            <div><dt>Memory records supplied</dt><dd>{recall.records.length}</dd></div>
            <div><dt>Product records returned</dt><dd>{recall.products.length}</dd></div>
          </dl>
          {!independentConversation && <p className="memory-showcase-notice" role="note">This run includes prior chat or reuses the first session. It cannot establish Memory use in a new conversation.</p>}
          <p className="memory-showcase-question"><strong>Shopper request:</strong> {recall.question}</p>
          <div className="memory-showcase-answer-text"><MarkdownMessage content={recall.answer} /></div>
          <p className="memory-showcase-check"><strong>Check:</strong> identify a retrieved preference used in this answer, then verify the product in Aurora.</p>
          <details><summary>Product evidence: {recall.products.length} returned records</summary>
          <p>These are the tool's retrieved candidates. The answer may recommend a subset or explain why a result is unsuitable.</p>
          <ul className="memory-showcase-products">{recall.products.map((product, i) => <li key={product.productId ?? product.id ?? product.product_id ?? i}>
            <strong>{product.name || 'Returned product'}</strong><code>{product.productId ?? product.id ?? product.product_id}</code>
            {product.price != null && <span>{new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(product.price))}</span>}
          </li>)}</ul></details>
          <details><summary>Inspect the exact context supplied</summary>
            <dl className="memory-showcase-identifiers">
              <div><dt>First session ID</dt><dd><code>{proof.sourceSessionId}</code></dd></div>
              <div><dt>Recall session ID</dt><dd><code>{recall.sessionId}</code></dd></div>
            </dl>
            <p>These are the record IDs and text supplied to this answer. Live Memory records may change after later conversations.</p>
            <ul className="memory-showcase-context">{recall.records.map(r => <li key={r.id}><code>{r.id}</code><p>{r.content}</p></li>)}</ul>
            {recall.closingMessage && <p><strong>Scripted closing message:</strong> {recall.closingMessage}</p>}
          </details>
        </div>}
      </>}
      <details className="memory-showcase-details"><summary>Run this exercise in the Code Editor</summary>
        <p>From the source repository root, with the backend Python environment active. Use the matching shopper sign-in to view the result here.</p>
        <pre tabIndex={0} role="region" aria-label="Memory exercise commands">{`python scripts/showcase_agentcore_memory.py learn --persona ${persona}\npython scripts/showcase_agentcore_memory.py status --persona ${persona}\n# Wait for facts, preferences and summary records, then:\npython scripts/showcase_agentcore_memory.py recall --persona ${persona}\n# Optional episode: review the answer, then send the scripted acknowledgement:\npython scripts/showcase_agentcore_memory.py finish --persona ${persona}`}</pre>
        <p>The workshop deployment configures four managed strategies. Learn writes a scripted first conversation. Recall invokes the live agent and can incur model charges. Refresh only reads evidence. Episode consolidation is optional and can take longer.</p>
      </details>
    </section>
  );
}
