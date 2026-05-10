/**
 * PersonaJourneys — the workshop's narrative spine in one screen.
 *
 * Three personas (Marco / Anna / Theo) each anchor a distinct Aurora
 * capability:
 *   * Marco — pgvector semantic search (foundation)
 *   * Anna — hybrid (vector + BM25) + Cohere Rerank v3.5
 *   * Theo — Aurora as agent system-of-record (Cedar + tool_audit)
 *
 * For each persona, this surface lists their canonical 5-turn journey
 * with the agent / tool / model / outcome per turn. Click any turn and
 * the corresponding session fixture opens in a new tab.
 *
 * Data is static — these journeys ARE the workshop's narrative spine
 * and don't change between runs. lab-content/shared/{marco,anna,theo}-
 * arc-overview.en.md is the source-of-truth; this surface mirrors that
 * structure visually so workshop participants can scan all 15 turns at
 * a glance instead of reading three markdown files.
 *
 * Lives under OBSERVE because it answers "what canonical conversations
 * does the system handle?" — adjacent to Sessions (which is the
 * captured replay store) and Observatory (the wide-angle dashboard).
 */

import React from 'react';
import { Link } from 'react-router-dom';
import { EditorialTitle, ExpCard, Eyebrow } from '../../components';

interface JourneyTurn {
  n: number;
  pill: string;
  agent: string;
  model: string;
  tool?: string;
  outcome: string;
  /** Atelier session id (without the 'session-' prefix) for the
   *  fixture that captures this turn, when one exists. */
  sessionId?: string;
}

interface PersonaJourney {
  id: 'marco' | 'anna' | 'theo';
  displayName: string;
  capability: string;
  capabilityRole: string;
  blurb: string;
  turns: JourneyTurn[];
  capstoneNote?: string;
}

const JOURNEYS: PersonaJourney[] = [
  {
    id: 'marco',
    displayName: 'Marco',
    capability: 'pgvector semantic search',
    capabilityRole: 'Foundation · Capability 1',
    blurb:
      "Returning customer. Natural fabrics, linen, travel-ready, warm tones. Marco's arc anchors the workshop's first Aurora capability — pure pgvector cosine over Cohere Embed v4. The Stock Keeper gap on Turn 4 is the build.",
    turns: [
      {
        n: 1,
        pill: 'What linen do you have for 10 days in Goa?',
        agent: 'Style Advisor',
        model: 'Sonnet 4.6 · 0.4',
        tool: 'find_pieces',
        outcome: '3 linen pieces with editorial voice',
        sessionId: 'marco-opening-demo',
      },
      {
        n: 2,
        pill: 'What would go with the Hadley shirt?',
        agent: 'Curator (the-packing-list)',
        model: 'Sonnet 4.6 · 0.4',
        tool: 'style_match',
        outcome: 'Complementary pieces; voice mentions packability',
        sessionId: 'marco-opening-demo',
      },
      {
        n: 3,
        pill: "What's the price range for linen shirts?",
        agent: 'Value Analyst',
        model: 'Haiku 4.5 · 0.1',
        tool: 'price_intelligence',
        outcome: '"$88 to $285, median $148" — sub-200ms',
        sessionId: 'marco-opening-demo',
      },
      {
        n: 4,
        pill: 'Is the Hadley shirt at the Brooklyn warehouse?',
        agent: 'Stock Keeper',
        model: 'Haiku 4.5 · 0.0',
        tool: 'floor_check',
        outcome:
          'Brooklyn 20 / Austin 15 / Portland 15 with ship windows · the workshop build payoff',
        sessionId: 'marco-midpoint-checkpoint',
      },
      {
        n: 5,
        pill: 'Show me one more linen piece under $100.',
        agent: 'Style Advisor',
        model: 'Sonnet 4.6 · 0.4',
        tool: 'find_pieces',
        outcome: 'Capstone — the system holds the price constraint',
        sessionId: 'marco-capstone',
      },
    ],
    capstoneNote:
      'Sonnet turns at ~1200ms. Haiku turns at ~150ms. An order of magnitude apart. That\'s the architectural lesson, made visible.',
  },
  {
    id: 'anna',
    displayName: 'Anna',
    capability: 'hybrid + Cohere Rerank v3.5',
    capabilityRole: 'Capability 2 · when pure vector wears thin',
    blurb:
      "Gift-giver. Buys for others — partner, sister, friend. Her queries blend editorial intent with literal constraints (\"thoughtful gift for someone who loves morning rituals\"). Pure cosine drifts on these. Hybrid + rerank lifts ranking by 20 points at 6× the cost — and the cost earns its keep here.",
    turns: [
      {
        n: 1,
        pill: 'a thoughtful gift for someone who loves morning rituals',
        agent: 'Curator (the-gift-table)',
        model: 'Sonnet 4.6 · 0.4',
        tool: 'find_pieces_hybrid',
        outcome:
          'Vector → BM25 → RRF → Rerank v3.5. 4 SSE telemetry spans visible.',
      },
      {
        n: 2,
        pill: 'something beautiful under $100',
        agent: 'Curator',
        model: 'Sonnet 4.6 · 0.4',
        tool: 'find_pieces_hybrid',
        outcome: 'Soft "beautiful" + literal "$100" — hybrid handles both.',
      },
      {
        n: 3,
        pill: 'help me pair a candle with something else',
        agent: 'Curator',
        model: 'Sonnet 4.6 · 0.4',
        tool: 'find_pieces_hybrid',
        outcome: 'Candle as anchor + "with something else" reranks the band.',
      },
      {
        n: 4,
        pill: 'wrap-ready gifts with no extra effort',
        agent: 'Curator',
        model: 'Sonnet 4.6 · 0.4',
        tool: 'find_pieces_hybrid',
        outcome: 'Gift Wrapping Kit at rank 1 — Cohere reads "wrap-ready" intent.',
        sessionId: 'anna-birthday-gift',
      },
      {
        n: 5,
        pill: 'a milestone gift for a new homeowner',
        agent: 'Curator',
        model: 'Sonnet 4.6 · 0.4',
        tool: 'find_pieces_hybrid',
        outcome: 'Milestone-coded vibe + homeowner literal converge cleanly.',
        sessionId: 'anna-housewarming',
      },
    ],
    capstoneNote:
      'Recall@5 jumps 20 points; p50 doubles; cost goes 6×. The Performance card lets you decide. There\'s no universally right answer — pick per query class.',
  },
  {
    id: 'theo',
    displayName: 'Theo',
    capability: 'Aurora as agent system-of-record',
    capabilityRole: 'Capability 3 · writes leave a paper trail',
    blurb:
      "Slow-craft buyer. Ceramics, linen throws, stoneware. Theo's hero pills cover read-path queries, but his canonical Module 2 turn is the chipped Wabi-Sabi Bowl return. That one message triggers three Aurora writes in one transaction, gated by Cedar (BeforeToolCallEvent) and SQL (ownership).",
    turns: [
      {
        n: 1,
        pill: 'hand-thrown ceramics for a slower morning routine',
        agent: 'Curator (the-makers-shelf)',
        model: 'Sonnet 4.6 · 0.4',
        tool: 'find_pieces',
        outcome: 'Stoneware Pour-Over Set at rank 1 — patina vibe matches.',
        sessionId: 'theo-pour-over',
      },
      {
        n: 2,
        pill: 'what goes well with the pour-over set?',
        agent: 'Curator',
        model: 'Sonnet 4.6 · 0.4',
        tool: 'style_match',
        outcome: 'Ceramic Tumblers + Bud Vase — same kiln register.',
      },
      {
        n: 3,
        pill: 'linen pieces that soften over seasons',
        agent: 'Style Advisor',
        model: 'Sonnet 4.6 · 0.4',
        tool: 'find_pieces',
        outcome: 'Washed-linen pieces with patina-leaning prose.',
      },
      {
        n: 4,
        pill: "My Wabi-Sabi Bowl arrived chipped. Please file a damaged return — my customer id is 'theo'.",
        agent: 'Experience Guide',
        model: 'Sonnet 4.6 · 0.2',
        tool: 'find_pieces → process_return',
        outcome:
          '3 writes in 1 transaction · returns row + product_catalog quantity decrement + tool_audit row · Cedar + SQL gated',
        sessionId: 'theo-ceramics-return',
      },
      {
        n: 5,
        pill: 'something for the home, not the wardrobe',
        agent: 'Curator',
        model: 'Sonnet 4.6 · 0.4',
        tool: 'find_pieces',
        outcome: 'Home-decor pieces with slow-craft handling.',
      },
    ],
    capstoneNote:
      'Every mutation is reconstructible from a single SELECT against tool_audit. See the Write-path surface for the live audit trail.',
  },
];

/* -----------------------------------------------------------------------
 * Turn row
 * ----------------------------------------------------------------------- */

const TurnRow: React.FC<{ turn: JourneyTurn }> = ({ turn }) => {
  const inner = (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '32px 1fr 200px',
        gap: '14px',
        alignItems: 'flex-start',
        padding: '14px 16px',
        borderTop: '1px solid var(--at-card-border)',
        cursor: turn.sessionId ? 'pointer' : 'default',
      }}
    >
      {/* Numeral */}
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

      {/* Pill + outcome */}
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
      </div>

      {/* Agent / model / tool */}
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
  );

  if (turn.sessionId) {
    return (
      <Link
        to={`/atelier/sessions/${turn.sessionId}`}
        style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}
      >
        {inner}
      </Link>
    );
  }
  return inner;
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
      style={{
        fontFamily: 'var(--at-serif)',
        fontSize: '32px',
        fontWeight: 400,
        margin: '4px 0 12px',
        color: 'var(--at-ink-1)',
        letterSpacing: '-0.012em',
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
        <div
          key={t.n}
          style={{
            background: i === 0 ? 'transparent' : undefined,
          }}
        >
          {/* First row's borderTop is hidden via the wrapper's overflow */}
          <TurnRow turn={t} />
        </div>
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
      eyebrow="Observe · Persona Journeys · 15 canonical turns"
      title="Three personas, three Aurora capabilities."
      summary="Marco read. Anna read harder. Theo writes. Each persona's 5-turn journey anchors one Aurora capability — pgvector semantic, hybrid+rerank, system-of-record. Every turn shows the agent, model/temperature, tool, and outcome. Click any turn with a captured session to replay it."
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
