/**
 * MemoryDashboard - Observe surface for the 4-substrate memory model.
 *
 * Shows the live state of working / semantic / episodic / procedural
 * memory for the active persona. Each substrate panel carries a
 * provenance pill ('live' | 'fixture' | 'sketch') so attendees see
 * which reads hit the real source on this request and which fell
 * back to a teaching fixture.
 */

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  EditorialTitle,
  ExpCard,
  Eyebrow,
  SurfaceFilterBar,
} from '../../components';
import { useAtelierData } from '../../hooks/useAtelierData';
import { usePersona } from '../../../contexts/PersonaContext';
import type {
  MemoryState,
  MemorySubstratePanel,
  MemoryItem,
} from '../../types';

/* -----------------------------------------------------------------------
 * Source pill
 * ----------------------------------------------------------------------- */

const SOURCE_COPY: Record<MemorySubstratePanel['source'], { label: string; bg: string; fg: string }> = {
  live: { label: 'Live', bg: 'var(--at-status-shipped-bg)', fg: 'var(--at-status-shipped-text)' },
  fixture: { label: 'Fixture', bg: 'var(--at-cream-2)', fg: 'var(--at-ink-2)' },
  sketch: { label: 'Sketch', bg: 'var(--at-cream-2)', fg: 'var(--at-ink-4)' },
};

const SourcePill: React.FC<{ source: MemorySubstratePanel['source'] }> = ({ source }) => {
  const { label, bg, fg } = SOURCE_COPY[source];
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: '2px 8px',
        borderRadius: '999px',
        background: bg,
        color: fg,
        fontFamily: 'var(--at-mono)',
        fontSize: '9px',
        letterSpacing: '0.18em',
        textTransform: 'uppercase',
        fontWeight: 600,
      }}
    >
      {source === 'live' ? '● ' : ''}
      {label}
    </span>
  );
};

/* -----------------------------------------------------------------------
 * Substrate panel
 * ----------------------------------------------------------------------- */

const SubstratePanel: React.FC<{ panel: MemorySubstratePanel }> = ({ panel }) => (
  <ExpCard>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '11px',
            letterSpacing: '0.22em',
            textTransform: 'uppercase',
            color: 'var(--at-ink-1)',
            fontWeight: 500,
          }}
        >
          {panel.label}
        </span>
        <SourcePill source={panel.source} />
      </div>
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '12px',
          color: 'var(--at-ink-2)',
          letterSpacing: '0.02em',
        }}
      >
        {panel.store}
      </span>

      {panel.caveat && (
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '13px',
            lineHeight: 1.5,
            color: 'var(--at-ink-2)',
            margin: 0,
            paddingLeft: '10px',
            borderLeft: '2px solid var(--at-ink-4)',
          }}
        >
          {panel.caveat}
        </p>
      )}

      {panel.items.length === 0 ? (
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '13px',
            color: 'var(--at-ink-4)',
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
        background: 'var(--at-cream-2)',
        border: '1px solid var(--at-card-border)',
        borderRadius: '6px',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '13px',
          lineHeight: 1.5,
          color: 'var(--at-ink-1)',
          flex: 1,
        }}
      >
        {item.content}
      </span>
      {meta.length > 0 && (
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '11px',
            color: 'var(--at-ink-4)',
            letterSpacing: '0.04em',
            flexShrink: 0,
            paddingTop: '2px',
          }}
        >
          {meta.join(' · ')}
        </span>
      )}
    </li>
  );
};

/* -----------------------------------------------------------------------
 * Loading / error / empty states
 * ----------------------------------------------------------------------- */

const LoadingState: React.FC = () => (
  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '18px', padding: '24px 0' }}>
    {[0, 1, 2, 3].map((i) => (
      <div
        key={i}
        style={{
          background: 'var(--at-cream-2)',
          borderRadius: 'var(--at-card-radius)',
          height: '240px',
          opacity: 0.5,
          animation: 'pulse 1.5s ease-in-out infinite',
        }}
      />
    ))}
  </div>
);

const ErrorState: React.FC<{ message: string; onRetry: () => void }> = ({ message, onRetry }) => (
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
        fontFamily: 'var(--at-sans)',
        fontSize: '16px',
        lineHeight: 1.45,
        color: 'var(--at-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      We couldn't load the memory dashboard.
    </p>
    <p
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: '14px',
        color: 'var(--at-ink-2)',
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
        fontFamily: 'var(--at-sans)',
        fontSize: '14px',
        fontWeight: 500,
        color: 'var(--at-cream-1)',
        backgroundColor: 'var(--at-ink-1)',
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
        fontFamily: 'var(--at-sans)',
        fontSize: '16px',
        lineHeight: 1.45,
        color: 'var(--at-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      No memory has been recorded for this persona.
    </p>
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '14px',
        color: 'var(--at-ink-4)',
        maxWidth: '380px',
        marginTop: '8px',
      }}
    >
      Start a conversation in the boutique to build memory, or check that the
      memory fixture data is available.
    </p>
  </div>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

type MemoryPersona = 'marco' | 'anna' | 'theo';

const PERSONA_OPTIONS = [
  { id: 'marco' as const, label: 'Marco' },
  { id: 'anna' as const, label: 'Anna' },
  { id: 'theo' as const, label: 'Theo' },
];

const MEMORY_PERSONA_IDS: ReadonlySet<MemoryPersona> = new Set([
  'marco',
  'anna',
  'theo',
]);

function isMemoryPersona(id: string | undefined): id is MemoryPersona {
  return id !== undefined && MEMORY_PERSONA_IDS.has(id as MemoryPersona);
}

const MemoryDashboard: React.FC = () => {
  // Default the local picker to whichever persona is signed in via the
  // top-right switcher. Attendees who haven't signed in (or are on a
  // persona without seeded memory fixtures) land on Marco — the only
  // fully-shipped arc — instead of an empty dashboard.
  const { persona: activePersona } = usePersona();
  const initialPersona: MemoryPersona = isMemoryPersona(activePersona?.id)
    ? (activePersona!.id as MemoryPersona)
    : 'marco';
  const [persona, setPersona] = useState<MemoryPersona>(initialPersona);

  // source: 'api' so the dashboard hits /api/atelier/memory/{persona}
  // and gets the live overlays from the backend (episodic + procedural
  // from Aurora, working + semantic from AgentCore Memory). Defaults
  // to 'fixture', which would render every panel as fixture/sketch even
  // when the database is connected.
  const { data, loading, error, refetch } = useAtelierData<MemoryState>({
    key: `memory-${persona}`,
    source: 'api',
  });

  const personaCounts = { marco: 1, anna: 1, theo: 1 } as Record<MemoryPersona, number>;

  const hasData =
    data != null &&
    (data.working.items.length > 0 ||
      data.semantic.items.length > 0 ||
      data.episodic.items.length > 0 ||
      data.procedural.items.length > 0);

  const liveCount = data
    ? [data.working, data.semantic, data.episodic, data.procedural].filter(
        (p) => p.source === 'live',
      ).length
    : 0;

  return (
    <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
      <EditorialTitle
        eyebrow="Understand · Memory · four substrates · persona-scoped"
        title="What the system remembers."
        summary="Memory has four substrates, each with its own storage and lifetime. AgentCore Memory owns working (session turns) and semantic (durable preferences). Aurora owns episodic (per-customer events) and procedural (tool patterns). Each panel below names the real backing store and tells you whether it read live on this request."
      />

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={refetch} />}
      {!loading && !error && !hasData && <EmptyState />}

      {!loading && !error && hasData && data != null && (
        <>
          <SurfaceFilterBar
            label="Persona"
            filter={persona}
            counts={personaCounts}
            options={PERSONA_OPTIONS}
            onChange={(p) => setPersona(p)}
          />

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '14px',
              margin: '20px 0 14px',
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: 'var(--at-ink-2)',
            }}
          >
            <span>Live substrates: {liveCount} / 4</span>
            <span style={{ color: 'var(--at-ink-4)' }}>·</span>
            <span>Persona: {data.persona}</span>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '18px',
            }}
          >
            <SubstratePanel panel={data.working} />
            <SubstratePanel panel={data.semantic} />
            <SubstratePanel panel={data.episodic} />
            <SubstratePanel panel={data.procedural} />
          </div>
        </>
      )}

      {/* Cross-link to the Architecture concept brief on Memory. */}
      <div
        style={{
          marginTop: '32px',
          paddingTop: '20px',
          borderTop: '1px solid var(--at-card-border)',
          fontFamily: 'var(--at-mono)',
          fontSize: '13px',
          color: 'var(--at-ink-2)',
        }}
      >
        <Link
          to="/atelier/architecture/memory"
          style={{ color: 'var(--at-burgundy)', textDecoration: 'none' }}
        >
          → Read the architecture brief on Memory
        </Link>
      </div>
    </div>
  );
};

export default MemoryDashboard;
