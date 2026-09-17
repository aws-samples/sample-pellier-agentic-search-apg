/**
 * MemoryDetail - Architecture detail page for Memory.
 *
 * Conversation context, business records and instructions, with their owners.
 */

import React from 'react';
import DetailPageShell from './DetailPageShell';
import { ExpCard, CategoryBadge } from '../../../components';
import { useObservatoryData } from '../../../hooks/useObservatoryData';
import { usePersona } from '../../../../contexts/PersonaContext';
import type {
  MemoryState,
  MemorySubstratePanel,
  MemoryItem,
} from '../../../types';
import { ARCHITECTURE_CODE_BLOCK } from './codeStyles';
import { SectionEyebrow, StateBadge } from '../../../../shared';
import type { StateBadgeTone } from '../../../../shared';

/* Anonymous / unknown personas fall through to Marco, the required path
 * persona, so the brief starts from the workshop's primary memory path. */
const MEMORY_PERSONA_IDS: ReadonlySet<string> = new Set(['marco', 'anna', 'theo']);

/* -----------------------------------------------------------------------
 * Source pill - tiny chip beside each panel header so attendees can
 * see whether each substrate read live or is waiting on async extraction.
 * ----------------------------------------------------------------------- */

/* Provenance, through the shared state badge. This was a mono 0.18em pill
   with a bullet glyph prefixed to the label; `live` now carries the database
   mark and `settling` the in-flight mark, so the two states differ by shape
   as well as by colour. `Live` reads the substrate; `Settling` means the
   asynchronous extraction has not landed yet, which is a state of the run
   rather than a claim about where the data came from. */
const SOURCE_TONE: Record<MemorySubstratePanel['source'], StateBadgeTone> = {
  live: 'live',
  settling: 'attention',
};

const SOURCE_LABEL: Record<MemorySubstratePanel['source'], string> = {
  live: 'Live',
  settling: 'Settling',
};

const SOURCE_DESCRIPTION: Record<MemorySubstratePanel['source'], string> = {
  live: 'Read from the substrate on this request.',
  settling: 'Asynchronous extraction has not produced records yet.',
};

const SourcePill: React.FC<{ source: MemorySubstratePanel['source'] }> = ({ source }) => (
  <StateBadge tone={SOURCE_TONE[source]} description={SOURCE_DESCRIPTION[source]}>
    {SOURCE_LABEL[source]}
  </StateBadge>
);

/* -----------------------------------------------------------------------
 * Provenance legend - one-liner that explains the Live source pill.
 * ----------------------------------------------------------------------- */

const ProvenanceLegend: React.FC = () => (
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      flexWrap: 'wrap',
      gap: '10px',
      fontFamily: 'var(--obs-sans)',
      fontSize: '12px',
      lineHeight: 1.5,
      color: 'var(--obs-ink-2)',
    }}
  >
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
      <SourcePill source="live" />
      <span>read from the real source on this request</span>
    </span>
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
      <SourcePill source="settling" />
      <span>read succeeded, but async extraction has not produced records yet</span>
    </span>
  </span>
);

/* -----------------------------------------------------------------------
 * Substrate panel - one of the four cards in the 2x2 grid below the
 * tier cards. Shows the items the route returned, with provenance.
 * ----------------------------------------------------------------------- */

interface SubstratePanelProps {
  panel: MemorySubstratePanel;
}

const SubstratePanel: React.FC<SubstratePanelProps> = ({ panel }) => (
  <ExpCard>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {/* Card title, at the shared card-title step. See MemoryDashboard:
            the same panel used to be labelled in mono uppercase here too. */}
        <span
          style={{
            fontFamily: 'var(--obs-heading)',
            fontSize: '16px',
            fontWeight: 600,
            letterSpacing: '-0.01em',
            lineHeight: 1.25,
            color: 'var(--obs-ink-1)',
          }}
        >
          {panel.label}
        </span>
        <SourcePill source={panel.source} />
      </div>
      <span
        style={{
          fontFamily: 'var(--obs-mono)',
          fontSize: '11px',
          color: 'var(--obs-ink-2)',
          letterSpacing: '0.02em',
        }}
      >
        {panel.store}
      </span>

      {panel.caveat && (
        <p
          style={{
            fontFamily: 'var(--obs-sans)',
            fontSize: '12px',
            lineHeight: 1.5,
            color: 'var(--obs-ink-2)',
            margin: 0,
            paddingLeft: '10px',
            borderLeft: '2px solid var(--obs-ink-4)',
          }}
        >
          {panel.caveat}
        </p>
      )}

      {panel.items.length === 0 ? (
        <p
          style={{
            fontFamily: 'var(--obs-sans)',
            fontSize: '13px',
            color: 'var(--obs-ink-4)',
            margin: 0,
          }}
        >
          No items for this persona yet.
        </p>
      ) : (
        <ul
          style={{
            listStyle: 'none',
            padding: 0,
            margin: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
          }}
        >
          {panel.items.map((item) => (
            <SubstrateItem key={item.id} item={item} />
          ))}
        </ul>
      )}
    </div>
  </ExpCard>
);

const SubstrateItem: React.FC<{ item: MemoryItem }> = ({ item }) => {
  const meta: string[] = [];
  if (item.tsOffsetDays != null) meta.push(`${item.tsOffsetDays}d`);
  if (item.similarity != null) meta.push(item.similarity.toFixed(2));

  return (
    <li
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        gap: '10px',
        padding: '8px 10px',
        background: 'var(--obs-cream-2)',
        border: '1px solid var(--obs-card-border)',
        borderRadius: '6px',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--obs-sans)',
          fontSize: '13px',
          lineHeight: 1.5,
          color: 'var(--obs-ink-1)',
          flex: 1,
        }}
      >
        {item.content}
      </span>
      {meta.length > 0 && (
        <span
          style={{
            fontFamily: 'var(--obs-mono)',
            fontSize: '11px',
            color: 'var(--obs-ink-4)',
            letterSpacing: '0.04em',
            flexShrink: 0,
            paddingTop: '2px',
          }}
        >
          {meta.join(', ')}
        </span>
      )}
    </li>
  );
};

/* -----------------------------------------------------------------------
 * Tier card - explainer card sitting above the live panels, one per
 * substrate. Same purpose as before: code snippet + role + prose.
 * ----------------------------------------------------------------------- */

interface TierCardProps {
  tierName: string;
  category: 'live' | 'optional';
  title: string;
  role: string;
  prose: string;
  codeSnippet: string;
}

const TierCard: React.FC<TierCardProps> = ({
  tierName,
  category,
  title,
  role,
  prose,
  codeSnippet,
}) => (
  <ExpCard>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <span
          style={{
            fontFamily: 'var(--obs-heading)',
            fontSize: '16px',
            fontWeight: 600,
            letterSpacing: '-0.01em',
            lineHeight: 1.25,
            color: 'var(--obs-ink-1)',
          }}
        >
          {tierName}
        </span>
        <CategoryBadge category={category} />
      </div>
      <h3
        style={{
          fontFamily: 'var(--obs-heading)',
          fontSize: '22px',
          fontWeight: 400,
          lineHeight: 1.15,
          letterSpacing: '-0.012em',
          color: 'var(--obs-ink-1)',
          margin: 0,
        }}
      >
        {title}
      </h3>
      <p
        style={{
          fontFamily: 'var(--obs-sans)',
          fontSize: '14px',
          lineHeight: 1.45,
          color: 'var(--obs-red-1)',
          margin: 0,
        }}
      >
        {role}
      </p>
      <p
        style={{
          fontFamily: 'var(--obs-sans)',
          fontSize: 'var(--obs-body-size)',
          lineHeight: 'var(--obs-body-leading)',
          color: 'var(--obs-ink-1)',
          margin: 0,
        }}
      >
        {prose}
      </p>
      <pre
        style={{
          ...ARCHITECTURE_CODE_BLOCK,
          whiteSpace: 'pre',
        }}
      >
        {codeSnippet}
      </pre>
    </div>
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const MemoryDetail: React.FC = () => {
  // Track the global persona from the top-right switcher so the panels
  // reflect the active customer. Anonymous / unknown ids fall back to
  // Marco, the required-path persona.
  const { persona } = usePersona();
  const activePersonaId =
    persona && MEMORY_PERSONA_IDS.has(persona.id) ? persona.id : 'marco';

  // Memory is live-only. Disable the static fallback so API failures do not
  // silently render non-live memory data.
  const { data, loading, error, refetch } = useObservatoryData<MemoryState>({
    key: `memory-${activePersonaId}`,
  });

  const liveCount = data
    ? [
        data.working,
        data.semantic,
        data.episodic,
        data.procedural,
        data.operational,
      ].filter(
        (p) => p.source === 'live',
      ).length
    : 0;
  const totalItems = data
    ? data.working.items.length +
      data.semantic.items.length +
      data.episodic.items.length +
      data.procedural.items.length +
      data.operational.items.length
    : 0;

  return (
    <DetailPageShell
      numeral="II"
      conceptName="Memory"
      category="live"
      title="Conversation context and business records."
      prose="AgentCore Memory stores conversation events and extracts learned context. Aurora PostgreSQL owns current product, inventory, order and return records. Reviewed runtime skills and MCP schemas define how tools work. The tool_audit table records execution evidence."
      seeInPellier={{
        href: '/?ask=Pick+up+where+I+left+off',
        label: 'Open the Storefront',
      }}
      cheatSheet={[
        {
          numeral: 'i.',
          text: 'Conversation events: AgentCore Memory stores turns under an actor and session. Reusing a session can carry chat history forward. The Lab 3 exercise uses a new session with zero prior chat events to isolate learned context.',
        },
        {
          numeral: 'ii.',
          text: 'Learned preferences: the USER_PREFERENCE strategy extracts records asynchronously from conversation into /pellier/preferences/{actorId}/. The exercise keeps the verified actor unchanged across conversations and inspects the exact records supplied to the agent.',
        },
        {
          numeral: 'iii.',
          text: 'Customer history: Aurora orders and returns record business activity. The customer_episodic_seed table supplies curated scenario context. These rows are separate from records extracted by the optional AgentCore EPISODIC strategy.',
        },
        {
          numeral: 'iv.',
          text: 'Runtime instructions: checked-in skills guide the agent, and MCP schemas define accepted tool arguments. These are reviewed source files, not context learned from conversation.',
        },
      ]}
      liveState={
        data
          ? {
              label: 'Current records for the selected customer. Each panel names its source and shows whether the read returned records or is waiting for extraction.',
              measured: true,
              values: [
                { label: 'Live sources', value: `${liveCount} / 5` },
                { label: 'Items', value: String(totalItems) },
                { label: 'Persona', value: data.persona },
              ],
            }
          : undefined
      }
    >
      {loading && <MemoryLoadingState />}
      {error && <MemoryErrorState message={error} onRetry={refetch} />}

      {!loading && !error && data && (
        <>
          {/* Tier explainer cards - 2x2 */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: '20px',
              marginBottom: '36px',
            }}
          >
            <TierCard
              tierName="Conversation events: AgentCore Memory"
              category="live"
              title="Session turns"
              role="Conversation history scoped to the caller and session"
              prose="The Storefront builds its history namespace from the verified principal and session ID. get_session_history reads the recorded turns in that namespace. Lab 3 uses a separate experiment: the same verified actor, a new session ID, and extracted records supplied without earlier chat."
              codeSnippet={`# Storefront conversation history
ns = AgentCoreIdentityService.build_namespace(principal_sub, session_id)
# "user-{principal_sub}-session-{session_id}"
await memory.append_session_turn(ns, turn)

# Read this conversation's recorded turns
history = await memory.get_session_history(ns)`}
            />
            <TierCard
              tierName="User preferences: AgentCore Memory"
              category="live"
              title="Extracted preferences"
              role="Extracted from conversation and retrieved by actor"
              prose="The USER_PREFERENCE strategy extracts preferences such as material, color and occasion into durable records. Extraction is asynchronous, so a configured strategy does not mean records are ready. A learned preference can guide a recommendation; current product details still come from Aurora."
              codeSnippet={`# AgentCore Memory USER_PREFERENCE records
prefs = await memory.get_semantic_memories(
    actor_id  # resolved from the verified caller
)
# Read /pellier/preferences/{actor_id}/
# An empty result means no extracted preferences are available.`}
            />
            <TierCard
              tierName="Customer history: Aurora PostgreSQL"
              category="live"
              title="Per-customer events"
              role="What this customer has done over time"
              prose="Orders and returns are authoritative business records. The customer_episodic_seed table holds curated context for the workshop scenario. Its name does not mean these rows were extracted by AgentCore Memory; the optional EPISODIC strategy has its own records and namespaces."
              codeSnippet={`# Curated scenario context in Aurora
seed = await fetch_episodic_seed(customer_id)
# -> [{summary_text, ts_offset_days}, ...]

# Order records for the authorized customer
SELECT product_id, placed_at FROM pellier.orders
WHERE customer_id = $1
ORDER BY placed_at DESC;`}
            />
            <TierCard
              tierName="Runtime instructions: repository"
              category="live"
              title="Instructions and contracts"
              role="How the agent should perform work"
              prose="Runtime skills provide conditional operating guidance. Canonical MCP schemas define each tool's arguments. Both are checked-in, reviewable source and survive process restarts because the runtime reloads them from the deployed artifact."
              codeSnippet={`# Reviewed instructions and tool contracts
skills/*/SKILL.md
scripts/deploy/gateway_tool_schemas.py

# Operational history remains separate
SELECT tool, count(*), avg(latency_ms)
FROM pellier.tool_audit
GROUP BY tool;`}
            />
          </div>

          {/* Live substrate panels - 2x2 with provenance pills */}
          <div
            style={{
              marginBottom: '12px',
              display: 'flex',
              alignItems: 'baseline',
              flexWrap: 'wrap',
              gap: '14px',
            }}
          >
            <SectionEyebrow dot={false}>
              Live state for {data.persona}
            </SectionEyebrow>
            <ProvenanceLegend />
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: '16px',
            }}
          >
            <SubstratePanel panel={data.working} />
            <SubstratePanel panel={data.semantic} />
            <SubstratePanel panel={data.episodic} />
            <SubstratePanel panel={data.procedural} />
            <div style={{ gridColumn: '1 / -1' }}>
              <SubstratePanel panel={data.operational} />
            </div>
          </div>
        </>
      )}

      {!loading && !error && !data && <MemoryEmptyState />}
    </DetailPageShell>
  );
};

/* -----------------------------------------------------------------------
 * Loading / error / empty states
 * ----------------------------------------------------------------------- */

const MemoryLoadingState: React.FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px' }}>
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          style={{
            background: 'var(--obs-cream-2)',
            borderRadius: 'var(--obs-card-radius)',
            height: '240px',
            opacity: 0.5,
            animation: 'pulse 1.5s ease-in-out infinite',
          }}
        />
      ))}
    </div>
  </div>
);

const MemoryErrorState: React.FC<{ message: string; onRetry: () => void }> = ({
  message,
  onRetry,
}) => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '60px 24px',
      textAlign: 'center',
    }}
  >
    <p
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: '16px',
        lineHeight: 1.45,
        color: 'var(--obs-ink-1)',
        maxWidth: '420px',
      }}
    >
      We couldn't load the memory data.
    </p>
    <p
      style={{
        fontFamily: 'var(--obs-mono)',
        fontSize: '14px',
        color: 'var(--obs-ink-4)',
        maxWidth: '480px',
        marginTop: '8px',
      }}
    >
      {message}
    </p>
    <button
      onClick={onRetry}
      style={{
        marginTop: '24px',
        fontFamily: 'var(--obs-sans)',
        fontSize: '14px',
        fontWeight: 500,
        color: 'var(--obs-cream-1)',
        backgroundColor: 'var(--obs-ink-1)',
        border: 'none',
        borderRadius: '8px',
        padding: '10px 24px',
        cursor: 'pointer',
      }}
    >
      Try again
    </button>
  </div>
);

const MemoryEmptyState: React.FC = () => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '60px 24px',
      textAlign: 'center',
    }}
  >
    <p
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: '16px',
        lineHeight: 1.45,
        color: 'var(--obs-ink-1)',
        maxWidth: '420px',
      }}
    >
      No memory data available for this persona.
    </p>
    <p
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: 'var(--obs-body-size)',
        color: 'var(--obs-ink-4)',
        maxWidth: '380px',
        marginTop: '8px',
      }}
    >
      Start a conversation in Pellier, or check that AgentCore Memory and
      Aurora are reachable.
    </p>
  </div>
);

export default MemoryDetail;
