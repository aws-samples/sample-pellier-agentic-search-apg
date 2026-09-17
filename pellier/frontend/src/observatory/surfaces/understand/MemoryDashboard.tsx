/**
 * MemoryDashboard - conversation context, business records and instructions.
 *
 * Names each record's owner for the active persona and separates tool
 * execution history. Each panel shows whether it read live or is waiting
 * for asynchronous extraction. Empty means no records yet, not static data.
 */

import React, { useEffect, useState } from 'react';
import MemoryShowcase from './MemoryShowcase';
import { redirectToSignIn } from '../../../utils/auth';
import { Link } from 'react-router-dom';
import {
  EditorialTitle,
  ExpCard,
  Eyebrow,
  SurfaceFilterBar,
} from '../../components';
import { useObservatoryData } from '../../hooks/useObservatoryData';
import { usePersona } from '../../../contexts/PersonaContext';
import type {
  MemoryState,
  MemorySubstratePanel,
  MemoryItem,
} from '../../types';
import { StateBadge } from '../../../shared';
import type { StateBadgeTone } from '../../../shared';

/* -----------------------------------------------------------------------
 * Source pill
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
 * Substrate panel
 * ----------------------------------------------------------------------- */

const SubstratePanel: React.FC<{ panel: MemorySubstratePanel }> = ({ panel }) => (
  <ExpCard>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        {/* The substrate name is this card's title, so it is set as one:
            sans, sentence case, at the card-title step. Mono uppercase at
            0.22em said "identifier" about a phrase that is not one, and left
            the store path below it with no way to look different. */}
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
          fontSize: '12px',
          color: 'var(--obs-ink-2)',
          letterSpacing: '0.02em',
          /* A store path has no spaces to break on. Without this it runs off
             a 375px screen instead of wrapping. */
          overflowWrap: 'anywhere',
        }}
      >
        {panel.store}
      </span>

      {panel.caveat && (
        <p
          style={{
            fontFamily: 'var(--obs-sans)',
            fontSize: '13px',
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

/* The four substrates, two up. `1fr 1fr` was two things wrong at once: it
   never collapsed, so a 375px screen got two 117px panels, and a `1fr` track's
   automatic minimum is its content's min-content width, which is why a store
   path ran off the page.

   340px is chosen, not rounded: `auto-fit` fits
   `floor((container + gap) / (min + gap))` tracks, so at the 1000px this grid
   gets on a 1440px screen it resolves to two columns and keeps the intended
   2x2, while a 300px floor would have made it three and left the fourth
   substrate alone on its own row. Below about 700px it drops to one. */
const SUBSTRATE_GRID: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 340px), 1fr))',
  gap: '18px',
};

/* -----------------------------------------------------------------------
 * Loading / error / empty states
 * ----------------------------------------------------------------------- */

const LoadingState: React.FC = () => (
  <div style={{ ...SUBSTRATE_GRID, padding: '24px 0' }}>
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
);

const ErrorState: React.FC<{ message: string; onRetry: () => void; signIn?: boolean }> = ({ message, onRetry, signIn }) => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '80px 24px',
      textAlign: 'center',
    }}
  >
    <Eyebrow label="Something went wrong" variant="muted" />
    <p
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: '16px',
        lineHeight: 1.45,
        color: 'var(--obs-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      We couldn't load the memory dashboard.
    </p>
    <p
      style={{
        fontFamily: 'var(--obs-mono)',
        fontSize: '14px',
        color: 'var(--obs-ink-2)',
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
      {signIn ? 'Sign in to view memory' : 'Try again'}
    </button>
  </div>
);

const EmptyState: React.FC = () => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '80px 24px',
      textAlign: 'center',
    }}
  >
    <Eyebrow label="No memory" variant="muted" />
    <p
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: '16px',
        lineHeight: 1.45,
        color: 'var(--obs-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      No memory has been recorded for this persona.
    </p>
    <p
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: '14px',
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

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

type MemoryPersona = 'marco' | 'anna' | 'theo' | 'jessica';

const PERSONA_OPTIONS = [
  { id: 'marco' as const, label: 'Marco' },
  { id: 'anna' as const, label: 'Anna' },
  { id: 'theo' as const, label: 'Theo' },
  { id: 'jessica' as const, label: 'Jessica' },
];

const MEMORY_PERSONA_IDS: ReadonlySet<MemoryPersona> = new Set([
  'marco',
  'anna',
  'theo',
  'jessica',
]);

function isMemoryPersona(id: string | undefined): id is MemoryPersona {
  return id !== undefined && MEMORY_PERSONA_IDS.has(id as MemoryPersona);
}

const MemoryDashboard: React.FC = () => {
  // Default the local picker to whichever persona is signed in via the
  // top-right switcher. Attendees who haven't signed in (or are on a
  // persona without live records yet) land on Marco, the required path persona.
  const { persona: activePersona } = usePersona();
  const initialPersona: MemoryPersona = isMemoryPersona(activePersona?.id)
    ? (activePersona!.id as MemoryPersona)
    : 'marco';
  const [persona, setPersona] = useState<MemoryPersona>(initialPersona);
  useEffect(() => {
    if (isMemoryPersona(activePersona?.id)) setPersona(activePersona.id);
  }, [activePersona?.id]);

  // Memory is live-only. Disable the static fallback so an API failure is visible.
  const { data, loading, error, errorStatus, refetch } = useObservatoryData<MemoryState>({
    key: `memory-${persona}`,
  });

  const personaCounts = { marco: 1, anna: 1, theo: 1, jessica: 1 } as Record<MemoryPersona, number>;

  const hasData = data != null;

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

  return (
    <div style={{ padding: 'clamp(24px, 4vw, 40px) clamp(16px, 4vw, 48px)', maxWidth: '1100px' }}>
      <EditorialTitle referenceId="memory"
        backToReferences
        eyebrow="Understand: Memory"
        title="Memory"
        summary="See how AgentCore carries learned preferences into a new conversation. Inspect Aurora business records and reviewed source instructions separately."
      />

      <SurfaceFilterBar label="Persona" filter={persona} counts={personaCounts} options={PERSONA_OPTIONS} onChange={setPersona} />
      <MemoryShowcase key={persona} persona={persona} />
      <h2 style={{ fontFamily: 'var(--obs-heading)', fontSize: '22px', margin: '28px 0 8px' }}>Conversation memory and business context</h2>
      {loading && <LoadingState />}
      {error && <ErrorState message={error} signIn={errorStatus === 401} onRetry={errorStatus === 401 ? () => redirectToSignIn('email') : refetch} />}
      {!loading && !error && !hasData && <EmptyState />}

      {!loading && !error && hasData && data != null && (
        <>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '14px',
              margin: '20px 0 14px',
              /* Mono stays: this line is a count and a principal name, which
                 is what mono marks. Only the tracking converges -- 0.18em was
                 a fourth value on a surface that documents one. */
              fontFamily: 'var(--obs-mono)',
              fontSize: '11px',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'var(--obs-ink-2)',
            }}
          >
            <span>Live sources: {liveCount} / 5</span>
            <span>Persona: {data.persona}</span>
          </div>

          <div style={SUBSTRATE_GRID}>
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

      {/* Cross-link to the Architecture concept brief on Memory. */}
      <div
        style={{
          marginTop: '32px',
          paddingTop: '20px',
          borderTop: '1px solid var(--obs-card-border)',
          fontFamily: 'var(--obs-mono)',
          fontSize: '13px',
          color: 'var(--obs-ink-2)',
        }}
      >
        <Link
          to="/observatory/architecture/memory"
          style={{ color: 'var(--obs-burgundy)', textDecoration: 'none' }}
        >
          → Architecture brief: Memory
        </Link>
      </div>
    </div>
  );
};

export default MemoryDashboard;
