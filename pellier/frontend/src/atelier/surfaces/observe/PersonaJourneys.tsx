/**
 * PersonaJourneys — the workshop's narrative spine in one screen.
 *
 * Four personas (Marco / Anna / Theo / fresh) each surface five Boutique
 * hero pills from `PERSONA_HERO_PILLS` — the same strings as the
 * storefront "Try asking" row. For each turn we list agent / tool /
 * model / outcome and link into captured session fixtures when they
 * exist (Marco Turn 4 links twice: opening demo = floor_check stub,
 * midpoint = wired warehouse answer).
 *
 * Lives under OBSERVE — adjacent to Sessions (replay) and Observatory.
 */

import React from 'react';
import { Link } from 'react-router-dom';
import { EditorialTitle, ExpCard, Eyebrow } from '../../components';
import { PERSONA_HERO_PILLS } from '../../../data/personaCurations';

interface JourneyTurn {
  n: number;
  pill: string;
  agent: string;
  model: string;
  tool?: string;
  outcome: string;
  /** Primary Atelier fixture for this turn (stub path, or only path). */
  sessionId?: string;
  /** When set, second fixture shows the post-build / wired path (e.g. floor_check). */
  wiredSessionId?: string;
}

interface PersonaJourney {
  id: 'marco' | 'anna' | 'theo' | 'fresh';
  displayName: string;
  capability: string;
  capabilityRole: string;
  blurb: string;
  turns: JourneyTurn[];
  capstoneNote?: string;
}

const MARCO_TURNS_META: Omit<JourneyTurn, 'pill' | 'n'>[] = [
  {
    agent: 'Style Advisor',
    model: 'Claude Opus 4.6 · 0.4',
    tool: 'find_pieces',
    outcome: '3 linen pieces with editorial voice',
    sessionId: 'marco-opening-demo',
  },
  {
    agent: 'Curator (the-packing-list)',
    model: 'Claude Opus 4.6 · 0.4',
    tool: 'style_match',
    outcome: 'Complementary pieces; voice mentions packability',
    sessionId: 'marco-opening-demo',
  },
  {
    agent: 'Value Analyst',
    model: 'Claude Haiku 4.5 · 0.1',
    tool: 'price_intelligence',
    outcome: '"$88 to $285, median $148" — sub-200ms',
    sessionId: 'marco-opening-demo',
  },
  {
    agent: 'Stock Keeper',
    model: 'Claude Haiku 4.5 · 0.0',
    tool: 'floor_check',
    outcome:
      'Opening demo: Dispatcher matches stock intent; floor_check still stubbed → fall-through telemetry (no tool). Midpoint: same Boutique pill — real warehouse breakdown after the build.',
    sessionId: 'marco-opening-demo',
    wiredSessionId: 'marco-midpoint-checkpoint',
  },
  {
    agent: 'Curator (the-packing-list)',
    model: 'Claude Opus 4.6 · 0.4',
    tool: 'style_match',
    outcome: 'Capstone — Ecru overshirt anchor; pairing + price discipline',
    sessionId: 'marco-capstone',
  },
];

const ANNA_TURNS_META: Omit<JourneyTurn, 'pill' | 'n'>[] = [
  {
    agent: 'Curator (the-gift-table)',
    model: 'Claude Opus 4.6 · 0.4',
    tool: 'find_pieces_hybrid',
    outcome:
      'Vector → BM25 → RRF → Rerank v3.5. Four SSE telemetry spans visible.',
  },
  {
    agent: 'Curator',
    model: 'Claude Opus 4.6 · 0.4',
    tool: 'find_pieces_hybrid',
    outcome: 'Soft "beautiful" + literal "$100" — hybrid handles both.',
  },
  {
    agent: 'Curator',
    model: 'Claude Opus 4.6 · 0.4',
    tool: 'find_pieces_hybrid',
    outcome: 'Candle as anchor + "with something else" reranks the band.',
  },
  {
    agent: 'Curator',
    model: 'Claude Opus 4.6 · 0.4',
    tool: 'find_pieces_hybrid',
    outcome: 'Gift Wrapping Kit at rank 1 — Cohere reads "wrap-ready" intent.',
    sessionId: 'anna-birthday-gift',
  },
  {
    agent: 'Curator',
    model: 'Claude Opus 4.6 · 0.4',
    tool: 'find_pieces_hybrid',
    outcome: 'Milestone-coded vibe + homeowner literal converge cleanly.',
    sessionId: 'anna-housewarming',
  },
];

const THEO_TURNS_META: Omit<JourneyTurn, 'pill' | 'n'>[] = [
  {
    agent: 'Curator (the-makers-shelf)',
    model: 'Claude Opus 4.6 · 0.4',
    tool: 'find_pieces',
    outcome: 'Stoneware Pour-Over Set at rank 1 — patina vibe matches.',
    sessionId: 'theo-pour-over',
  },
  {
    agent: 'Curator',
    model: 'Claude Opus 4.6 · 0.4',
    tool: 'style_match',
    outcome: 'Ceramic Tumblers + Bud Vase — same kiln register.',
  },
  {
    agent: 'Style Advisor',
    model: 'Claude Opus 4.6 · 0.4',
    tool: 'find_pieces',
    outcome: 'Washed-linen pieces with patina-leaning prose.',
  },
  {
    agent: 'Experience Guide',
    model: 'Claude Opus 4.6 · 0.2',
    tool: 'find_pieces → process_return',
    outcome:
      'Three writes in one transaction · returns row + product_catalog decrement + tool_audit · Cedar + SQL gated',
    sessionId: 'theo-ceramics-return',
  },
  {
    agent: 'Curator',
    model: 'Claude Opus 4.6 · 0.4',
    tool: 'find_pieces',
    outcome: 'Home-decor read — same fifth pill as the Boutique hero row.',
  },
];

const FRESH_TURNS_META: Omit<JourneyTurn, 'pill' | 'n'>[] = PERSONA_HERO_PILLS.fresh.map(() => ({
  agent: 'Live storefront',
  model: 'Runtime routing',
  outcome:
    'Anonymous hero pills only — identical to the Boutique "Try asking" row. Capture a run under Sessions when you need telemetry.',
}));

function attachPills(meta: Omit<JourneyTurn, 'pill' | 'n'>[], pills: string[]): JourneyTurn[] {
  return meta.map((m, idx) => ({
    n: idx + 1,
    pill: pills[idx],
    ...m,
  }));
}

const JOURNEYS: PersonaJourney[] = [
  {
    id: 'marco',
    displayName: 'Marco',
    capability: 'pgvector semantic search',
    capabilityRole: 'Foundation · Capability 1',
    blurb:
      "Returning customer. Natural fabrics, linen, travel-ready, warm tones. Marco's arc anchors pgvector cosine over Cohere Embed v4. Turn 4 is the Builder's Session: same hero pill ships stub telemetry in opening demo, then a real floor_check replay in midpoint.",
    turns: attachPills(MARCO_TURNS_META, PERSONA_HERO_PILLS.marco),
    capstoneNote:
      "Claude Opus 4.6 turns at ~1200ms. Claude Haiku 4.5 turns at ~150ms. That's the architectural lesson, made visible — and Turn 4 is where the wiring exercise lands.",
  },
  {
    id: 'anna',
    displayName: 'Anna',
    capability: 'hybrid + Cohere Rerank v3.5',
    capabilityRole: 'Capability 2 · when pure vector wears thin',
    blurb:
      "Gift-giver — observe & learn only. Her five Boutique hero strings are a live demo of Capability 2 (hybrid + rerank); there is no Builder's Session wiring exercise on this arc. Use Sessions and Observatory to study spans and cost.",
    turns: attachPills(ANNA_TURNS_META, PERSONA_HERO_PILLS.anna),
    capstoneNote:
      "Recall@5 jumps ~20 points; p50 doubles; cost goes 6×. The Performance card lets you decide — there's no universally right answer per query class.",
  },
  {
    id: 'theo',
    displayName: 'Theo',
    capability: 'Aurora as agent system-of-record',
    capabilityRole: 'Capability 3 · writes leave a paper trail',
    blurb:
      "Slow-craft buyer — observe & learn only. This arc demonstrates Capability 3 (writes + tool_audit / Cedar). No participant coding checkpoint on Theo in the Builder's Session; replay session fixtures to see the paper trail.",
    turns: attachPills(THEO_TURNS_META, PERSONA_HERO_PILLS.theo),
    capstoneNote:
      'Every mutation is reconstructible from tool_audit — see Write-path.',
  },
  {
    id: 'fresh',
    displayName: 'Fresh visitor',
    capability: 'Canonical baseline',
    capabilityRole: 'Anonymous · no persona lean',
    blurb:
      'First-time storefront. Tags and curated grid fall through to unbiased ordering; hero pills mirror the Boutique row so instructors can cite the same twenty strings everywhere.',
    turns: attachPills(FRESH_TURNS_META, PERSONA_HERO_PILLS.fresh),
  },
];

/* -----------------------------------------------------------------------
 * Turn row
 * ----------------------------------------------------------------------- */

function sessionLinkLabel(id: string, suffix?: string): string {
  const base = id.replace(/-/g, ' ');
  return suffix ? `${base} · ${suffix}` : base;
}

const TurnRow: React.FC<{ turn: JourneyTurn; isFirst?: boolean }> = ({ turn, isFirst }) => {
  const links =
    turn.sessionId || turn.wiredSessionId ? (
      <div
        style={{
          marginTop: '10px',
          display: 'flex',
          flexWrap: 'wrap' as const,
          gap: '12px',
        }}
      >
        {turn.sessionId && (
          <Link
            to={`/atelier/sessions/${turn.sessionId}`}
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              color: 'var(--at-burgundy)',
              textDecoration: 'none',
            }}
          >
            {sessionLinkLabel(turn.sessionId, turn.wiredSessionId ? 'stub / arc' : 'replay')}
            →
          </Link>
        )}
        {turn.wiredSessionId && (
          <Link
            to={`/atelier/sessions/${turn.wiredSessionId}`}
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              color: 'var(--at-burgundy)',
              textDecoration: 'none',
            }}
          >
            {sessionLinkLabel(turn.wiredSessionId, 'wired')}→
          </Link>
        )}
      </div>
    ) : null;

  return (
    <div
      style={{
        padding: '14px 16px',
        borderTop: isFirst ? 'none' : '1px solid var(--at-card-border)',
      }}
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '32px 1fr 200px',
          gap: '14px',
          alignItems: 'flex-start',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '13px',
            color: 'var(--at-ink-3)',
            paddingTop: '2px',
          }}
        >
          T{turn.n}
        </span>

        <div>
          <div
            style={{
              fontFamily: 'var(--at-serif)',
              fontSize: '15px',
              color: 'var(--at-ink-1)',
              marginBottom: '4px',
              fontStyle: 'italic' as const,
            }}
          >
            “{turn.pill}”
          </div>
          <div
            style={{
              fontFamily: 'var(--at-sans)',
              fontSize: '13px',
              color: 'var(--at-ink-2)',
              lineHeight: 1.55,
            }}
          >
            {turn.outcome}
          </div>
          {links}
        </div>

        <div
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            color: 'var(--at-ink-3)',
            textAlign: 'right' as const,
            lineHeight: 1.6,
          }}
        >
          <div style={{ color: 'var(--at-ink-1)' }}>{turn.agent}</div>
          <div>{turn.model}</div>
          {turn.tool && <div>{turn.tool}</div>}
        </div>
      </div>
    </div>
  );
};

/* -----------------------------------------------------------------------
 * Persona section
 * ----------------------------------------------------------------------- */

const PersonaSection: React.FC<{ journey: PersonaJourney }> = ({ journey }) => (
  <ExpCard>
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        marginBottom: '8px',
      }}
    >
      <Eyebrow label={journey.capabilityRole} />
      <code
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '12px',
          color: 'var(--at-burgundy)',
        }}
      >
        {journey.capability}
      </code>
    </div>
    <h2
      className="font-display italic text-espresso"
      style={{
        fontSize: 'clamp(28px, 3.5vw, 44px)',
        fontWeight: 400,
        margin: '4px 0 12px',
        letterSpacing: '-0.015em',
        lineHeight: 1.1,
      }}
    >
      {journey.displayName}
    </h2>
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '14px',
        lineHeight: 1.6,
        color: 'var(--at-ink-2)',
        marginBottom: '20px',
      }}
    >
      {journey.blurb}
    </p>

    <div
      style={{
        border: '1px solid var(--at-card-border)',
        borderRadius: '6px',
        background: 'var(--at-cream-1)',
        overflow: 'hidden' as const,
      }}
    >
      {journey.turns.map((t, i) => (
        <TurnRow key={t.n} turn={t} isFirst={i === 0} />
      ))}
    </div>

    {journey.capstoneNote && (
      <div
        style={{
          marginTop: '16px',
          paddingTop: '14px',
          borderTop: '1px solid var(--at-card-border)',
          fontFamily: 'var(--at-sans)',
          fontSize: '13px',
          fontStyle: 'italic' as const,
          color: 'var(--at-ink-2)',
          lineHeight: 1.6,
        }}
      >
        {journey.capstoneNote}
      </div>
    )}
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Page
 * ----------------------------------------------------------------------- */

const PersonaJourneys: React.FC = () => (
  <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
    <EditorialTitle
      eyebrow="Observe · Persona Journeys · 20 Boutique hero turns"
      title="Four personas, twenty hero queries."
      summary="Every quoted line is the same string as the Boutique “Try asking” pill for that slot (see personaCurations · PERSONA_HERO_PILLS). Marco Turn 4 links twice: opening demo shows floor_check still stubbed; midpoint shows the wired warehouse answer. Click a session link to replay telemetry."
    />

    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {JOURNEYS.map((j) => (
        <PersonaSection key={j.id} journey={j} />
      ))}
    </div>

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
        to="/atelier/architecture/grounding"
        style={{ color: 'var(--at-burgundy)', textDecoration: 'none' }}
      >
        → Read the architecture brief on Grounding (the capability ladder
        in detail)
      </Link>
    </div>
  </div>
);

export default PersonaJourneys;
