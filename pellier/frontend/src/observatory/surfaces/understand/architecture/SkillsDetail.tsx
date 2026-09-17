/**
 * SkillsDetail — Architecture detail page for Skills.
 *
 * Five skills: three persona-resident overlays plus two shared proof/care
 * overlays. Source-of-truth slugs live in skills.json and each
 * /skills/<slug>/SKILL.md file at repo root.
 *
 * Requirements: 7.1, 7.6, 7.7
 */

import React from 'react';
import DetailPageShell from './DetailPageShell';
import { ExpCard } from '../../../components';
import { useObservatoryData } from '../../../hooks/useObservatoryData';
import type { ArchitectureConcept } from '../../../types';
import { DetailLoadingState, DetailErrorState, DetailEmptyState } from './DetailStates';
import { ARCHITECTURE_CODE_BLOCK } from './codeStyles';
import { SectionEyebrow } from '../../../../shared';

const SkillsDetail: React.FC = () => {
  const { data, loading, error, refetch } = useObservatoryData<ArchitectureConcept[]>({
    key: 'architecture',
  });

  const concept = data?.find((c) => c.slug === 'skills');

  return (
    <DetailPageShell
      numeral="III"
      conceptName="Skills"
      category="live"
      title="Skills, persona-routed."
      prose="Five skills – three persona overlays plus the shared Care Card and Proof Counter – can load when the configured SkillRouter selects guidance for a specialist turn. Markdown briefs live under /skills/<slug>/SKILL.md; they are not separate agents."
      cheatSheet={[
        {
          numeral: 'i.',
          text: 'Skills are not agents. They\'re markdown briefs injected into the specialist\'s system prompt at runtime based on persona context.',
        },
        {
          numeral: 'ii.',
          text: 'The SkillRouter uses BEDROCK_ROUTER_MODEL with a JSON-only prompt. Intent routing already chose the specialist; this second router only decides which skill overlays to inject for that turn.',
        },
        {
          numeral: 'iii.',
          text: 'Skills are turn-routed: persona context can activate Marco/Anna/Theo overlays, while care and proof language can activate shared overlays.',
        },
      ]}
      liveState={{
        label: 'Source-defined skill routing. Inspect a recorded turn for the actual model, selection, and elapsed time.',
        values: [
          { label: 'Skills available', value: '5' },
          { label: 'Router model', value: 'Configured at deployment' },
          { label: 'Activation', value: 'Inspect the turn' },
        ],
      }}
    >
      {loading && <DetailLoadingState />}
      {error && <DetailErrorState message={error} onRetry={refetch} />}
      {!loading && !error && !concept && <DetailEmptyState conceptName="Skills" />}
      {!loading && !error && concept && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Five skills — matches skills.json + /skills/<slug>/SKILL.md bundles */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
            <SkillCard
              name="the-packing-list"
              trigger="Travel wardrobes, pack-flat pieces, natural fibers, weekender bags"
              description="Marco's capsule logic – tight palette, linen-forward, pieces that earn suitcase space."
              example='"I need a Goa trip wardrobe that still feels like me."'
            />
            <SkillCard
              name="the-gift-table"
              trigger="Gifts, milestones, wrap-ready pieces, housewarmings, birthdays"
              description="Anna's giving register – price bands, pairing, tissue-and-ribbon presentation."
              example='"A housewarming gift for someone who loves slow morning rituals."'
            />
            <SkillCard
              name="the-makers-shelf"
              trigger="Hand-thrown ceramics, kiln language, slow craft, patina, studio provenance"
              description="Theo's slow-craft framing – imperfect glazes as feature, care that honors the object."
              example='"Hand-thrown ceramics for a slower morning routine."'
            />
            <SkillCard
              name="the-care-card"
              trigger="Returns, damaged items, repair, care, warranty, what-now moments"
              description="Post-purchase language – clear boundaries, concrete next step, no invented policy."
              example='"The bowl arrived damaged. What now?"'
            />
            <SkillCard
              name="the-proof-counter"
              trigger="Why this, how do you know, audit receipts, memory proof, Gateway traces"
              description="Governed explanations – name the memory source, tool receipt, row, or policy boundary."
              example='"How do you know this fits my taste?"'
            />
          </div>

          {/* SkillRouter flow */}
          <ExpCard>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <SectionLabel label="The routing flow" />
              <h3 style={titleStyle}>Turn arrives, router decides.</h3>
              <p style={proseStyle}>
                Specialist turns can pass through the SkillRouter after intent classification.
                Greetings and other triage fast paths can return before this call. The router
                selects prompt guidance; the recorded skill_routing event identifies the
                selected skills and elapsed time. Skill selection does not grant tool permission.
              </p>
              <pre style={codeStyle}>{concept.codeSnippet}</pre>
            </div>
          </ExpCard>
        </div>
      )}
    </DetailPageShell>
  );
};

/* ---- Sub-components ---- */

const SkillCard: React.FC<{
  name: string;
  trigger: string;
  description: string;
  example: string;
}> = ({ name, trigger, description, example }) => (
  <ExpCard>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      <span
        style={{
          fontFamily: 'var(--obs-mono)',
          fontSize: '14px',
          fontWeight: 600,
          color: 'var(--obs-ink-1)',
        }}
      >
        {name}
      </span>
      <div>
        <SectionEyebrow tone="muted" dot={false}>
          Triggers on
        </SectionEyebrow>
        <p style={{ fontFamily: 'var(--obs-sans)', fontSize: '14px', lineHeight: 1.5, color: 'var(--obs-ink-1)', margin: '4px 0 0 0' }}>
          {trigger}
        </p>
      </div>
      <p style={{ fontFamily: 'var(--obs-sans)', fontSize: '14px', lineHeight: 1.5, color: 'var(--obs-ink-1)', margin: 0 }}>
        {description}
      </p>
      <div
        style={{
          fontFamily: 'var(--obs-heading)',
          fontSize: '14px',
          color: 'var(--obs-ink-1)',
          padding: '10px 14px',
          backgroundColor: 'var(--obs-cream-2)',
          borderRadius: '8px',
          borderLeft: '2px solid var(--obs-red-1)',
        }}
      >
        {example}
      </div>
    </div>
  </ExpCard>
);

/* ---- Shared styles ---- */

/* One label register on the surface. This was six identical copies of a mono
   0.22em recipe, one per detail page; mono here marked prose, not an
   identifier, which is the distinction the shared primitive restores. */
const SectionLabel: React.FC<{ label: string }> = ({ label }) => (
  <SectionEyebrow tone="muted" dot={false}>
    {label}
  </SectionEyebrow>
);

const titleStyle: React.CSSProperties = {
  fontFamily: 'var(--obs-heading)', fontSize: '22px', fontWeight: 400,
  lineHeight: 1.15, color: 'var(--obs-ink-1)', margin: 0,
};

const proseStyle: React.CSSProperties = {
  fontFamily: 'var(--obs-sans)', fontSize: 'var(--obs-body-size)', lineHeight: 'var(--obs-body-leading)',
  color: 'var(--obs-ink-1)', margin: 0, maxWidth: '560px',
};

const codeStyle: React.CSSProperties = {
  ...ARCHITECTURE_CODE_BLOCK,
  whiteSpace: 'pre',
};

export default SkillsDetail;
