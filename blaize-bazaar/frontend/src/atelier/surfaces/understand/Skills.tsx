/**
 * Skills — the 3 persona-tied skills loaded by the SkillRouter.
 *
 * One card per skill. Each card shows:
 *   · display name (Fraunces) + persona chip
 *   · description (one-line from YAML frontmatter)
 *   · signals the SkillRouter watches for (burgundy dots)
 *   · "Loaded by" agent list as chips
 *   · full Markdown body in a monospace panel (the guidance the model receives)
 *
 * Skills are file-based, not DB-backed — this surface is intentionally
 * read-only; the lab's Customize-the-Gift-Table challenge edits the
 * SKILL.md file directly, not a database row.
 */

import React from 'react';
import { EditorialTitle, ExpCard, Eyebrow } from '../../components';
import { useAtelierData } from '../../hooks/useAtelierData';
import type { Skill } from '../../types';

/* -----------------------------------------------------------------------
 * Persona chip — small pill with persona's first name
 * ----------------------------------------------------------------------- */
const PersonaChip: React.FC<{ name: string }> = ({ name }) => (
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      padding: '3px 10px',
      borderRadius: '999px',
      backgroundColor: 'var(--at-cream-2)',
      border: '1px solid var(--at-rule-1)',
      color: 'var(--at-ink-1)',
      fontFamily: 'var(--at-mono)',
      fontSize: '11px',
      fontWeight: 500,
      letterSpacing: '0.08em',
      textTransform: 'uppercase',
      lineHeight: 1.4,
    }}
  >
    {name}
  </span>
);

/* -----------------------------------------------------------------------
 * Signal dot — small burgundy circle + label
 * ----------------------------------------------------------------------- */
const SignalPill: React.FC<{ label: string }> = ({ label }) => (
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
      padding: '3px 10px 3px 8px',
      borderRadius: '999px',
      backgroundColor: 'rgba(168, 66, 58, 0.08)',
      color: 'var(--at-red-1)',
      fontFamily: 'var(--at-mono)',
      fontSize: '11px',
      fontWeight: 500,
      lineHeight: 1.4,
    }}
  >
    <span
      aria-hidden
      style={{
        width: 5,
        height: 5,
        borderRadius: '50%',
        background: 'var(--at-red-1)',
        display: 'inline-block',
      }}
    />
    {label}
  </span>
);

/* -----------------------------------------------------------------------
 * Loaded-by agent chip
 * ----------------------------------------------------------------------- */
const AgentChip: React.FC<{ name: string }> = ({ name }) => (
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      padding: '3px 10px',
      borderRadius: '6px',
      backgroundColor: 'rgba(31, 20, 16, 0.04)',
      color: 'var(--at-ink-1)',
      fontFamily: 'var(--at-sans)',
      fontSize: '12px',
      fontWeight: 500,
      lineHeight: 1.4,
    }}
  >
    {name}
  </span>
);

/* -----------------------------------------------------------------------
 * Skill card
 * ----------------------------------------------------------------------- */
interface SkillCardProps {
  skill: Skill;
  numeral: string;
}

const SkillCard: React.FC<SkillCardProps> = ({ skill, numeral }) => (
  <ExpCard>
    {/* Head: numeral + title + persona chip */}
    <div style={{ display: 'grid', gridTemplateColumns: '38px 1fr auto', gap: '14px', alignItems: 'baseline', marginBottom: '14px' }}>
      <span
        style={{
          fontFamily: 'var(--at-serif)',
          fontStyle: 'italic',
          fontSize: '30px',
          color: 'var(--at-red-1)',
          letterSpacing: '-0.02em',
          lineHeight: 1,
        }}
      >
        {numeral}
      </span>
      <h3
        style={{
          fontFamily: 'var(--at-serif)',
          fontWeight: 400,
          fontSize: '24px',
          letterSpacing: '-0.012em',
          lineHeight: 1.1,
          color: 'var(--at-ink-1)',
          margin: 0,
        }}
      >
        {skill.displayName}
      </h3>
      <div style={{ alignSelf: 'start' }}>
        <PersonaChip name={skill.personaDisplayName} />
      </div>
    </div>

    {/* Description */}
    <p
      style={{
        fontFamily: 'var(--at-serif)',
        fontStyle: 'italic',
        fontSize: '16px',
        color: 'var(--at-ink-1)',
        lineHeight: 1.5,
        margin: '0 0 18px',
        maxWidth: '640px',
      }}
    >
      {skill.description}
    </p>

    {/* Signals */}
    <div style={{ marginBottom: '18px' }}>
      <Eyebrow label="Signals the SkillRouter watches for" />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
        {skill.signals.map((s) => (
          <SignalPill key={s} label={s} />
        ))}
      </div>
    </div>

    {/* Loaded by */}
    <div style={{ marginBottom: '18px' }}>
      <Eyebrow label="Loaded by" />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
        {skill.loadedBy.map((a) => (
          <AgentChip key={a} name={a} />
        ))}
      </div>
    </div>

    {/* Body (the guidance passed to the model) */}
    <div>
      <Eyebrow label="Skill body (injected into system prompt)" />
      <pre
        style={{
          marginTop: '8px',
          padding: '16px 20px',
          backgroundColor: 'var(--at-cream-2)',
          border: '1px solid var(--at-rule-1)',
          borderRadius: '8px',
          fontFamily: 'var(--at-mono)',
          fontSize: '12.5px',
          lineHeight: 1.55,
          color: 'var(--at-ink-1)',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          overflow: 'auto',
          maxHeight: '320px',
        }}
      >
        {skill.body}
      </pre>
    </div>

    {/* File path hint */}
    <p
      style={{
        marginTop: '10px',
        fontFamily: 'var(--at-mono)',
        fontSize: '11px',
        color: 'var(--at-ink-2)',
        lineHeight: 1.4,
      }}
    >
      Source: <code>blaize-bazaar/backend/skills/{skill.name}/SKILL.md</code>
    </p>
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Empty + loading + error states
 * ----------------------------------------------------------------------- */
const LoadingState: React.FC = () => (
  <div style={{ padding: '32px', textAlign: 'center', color: 'var(--at-ink-2)' }}>Loading skills…</div>
);

const ErrorState: React.FC<{ message: string; onRetry: () => void }> = ({ message, onRetry }) => (
  <div style={{ padding: '32px', textAlign: 'center' }}>
    <p style={{ color: 'var(--at-red-1)', marginBottom: '12px' }}>Failed to load skills: {message}</p>
    <button onClick={onRetry} style={{ padding: '6px 14px', borderRadius: '6px', border: '1px solid var(--at-rule-2)', background: 'var(--at-cream-1)', cursor: 'pointer' }}>
      Retry
    </button>
  </div>
);

const EmptyState: React.FC = () => (
  <div style={{ padding: '32px', textAlign: 'center', color: 'var(--at-ink-2)' }}>
    <p>No skills loaded. Check <code>blaize-bazaar/backend/skills/</code>.</p>
  </div>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */
const ROMAN = ['I.', 'II.', 'III.', 'IV.', 'V.'];

const Skills: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<Skill[]>({ key: 'skills' });
  const skills = data ?? [];

  return (
    <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
      <EditorialTitle
        eyebrow="Understand · Skills · three persona-tied files"
        title="Persona-specific knowledge the agents load."
        summary="Three Markdown files. One per persona. Loaded per turn by the SkillRouter — Haiku 4.5 at 0.0, deterministic classification — and injected into the specialist's system prompt. Skills change voice and handling, not product selection."
      />

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={refetch} />}
      {!loading && !error && skills.length === 0 && <EmptyState />}

      {!loading && !error && skills.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          {skills.map((skill, idx) => (
            <SkillCard key={skill.name} skill={skill} numeral={ROMAN[idx] ?? `${idx + 1}.`} />
          ))}
        </div>
      )}
    </div>
  );
};

export default Skills;
