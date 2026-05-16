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

import React, { useState, useCallback, useMemo, useRef } from 'react';
import { Link } from 'react-router-dom';
import { EditorialTitle, ExpCard, Eyebrow, SurfaceFilterBar } from '../../components';
import { useAtelierData } from '../../hooks/useAtelierData';
import type { Skill } from '../../types';
import { routeSkillsOffline, routerQueryForSkill } from './skillsRouterUtils';

type PersonaFilter = 'all' | 'marco' | 'anna' | 'theo';

const PERSONA_FILTER_OPTIONS = [
  { id: 'all' as const, label: 'All personas' },
  { id: 'marco' as const, label: 'Marco' },
  { id: 'anna' as const, label: 'Anna' },
  { id: 'theo' as const, label: 'Theo' },
];

function filterSkillsByPersona(skills: Skill[], filter: PersonaFilter): Skill[] {
  if (filter === 'all') return skills;
  return skills.filter((s) => s.persona === filter);
}

/* -----------------------------------------------------------------------
 * Skill Router Demo Card
 *
 * Live demonstration of the SkillRouter (Haiku 4.5 at temperature 0.0).
 * Mirrors the Tools page's DiscoveryDemoCard pattern: type a query,
 * see what the router would decide for that turn (which skills to
 * load + which it considered and why it rejected them).
 *
 * The same call shape is used by the chat pipeline — when a user
 * submits a query in the Boutique, this exact decision is emitted as
 * an SSE skill_routing event before any text streams.
 * ----------------------------------------------------------------------- */

interface RouterConsidered {
  name: string;
  reason: string;
}

interface RouterResult {
  loaded_skills: string[];
  considered: RouterConsidered[];
  elapsed_ms: number;
  user_message: string;
  error?: string;
}

const EXAMPLES: { label: string; query: string }[] = [
  { label: "Marco's Turn 2", query: 'What would go with the Hadley shirt?' },
  { label: "Anna's gift query", query: 'wrap-ready gifts with no extra effort' },
  { label: "Theo's pairing query", query: 'what goes well with the pour-over set?' },
];

interface SkillRouterDemoCardProps {
  skills: Skill[];
  highlightedSkillName: string | null;
  onSelectSkill: (name: string) => void;
  runRequest?: { query: string; nonce: number } | null;
  onLoadedSkills?: (names: string[]) => void;
}

const SkillRouterDemoCard: React.FC<SkillRouterDemoCardProps> = ({
  skills,
  highlightedSkillName,
  onSelectSkill,
  runRequest,
  onLoadedSkills,
}) => {
  const [query, setQuery] = useState('');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RouterResult | null>(null);
  const [usedOffline, setUsedOffline] = useState(false);

  const run = useCallback(
    async (q: string) => {
      if (!q.trim()) return;
      setRunning(true);
      setResult(null);
      setUsedOffline(false);
      const start = performance.now();
      try {
        const r = await fetch('/api/atelier/skills/route', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: q }),
        });
        if (r.ok) {
          const data = (await r.json()) as RouterResult;
          setResult(data);
        } else if (skills.length > 0) {
          const offline = routeSkillsOffline(q, skills);
          setResult({ ...offline, elapsed_ms: Math.round(performance.now() - start) });
          setUsedOffline(true);
        } else {
          setResult({
            loaded_skills: [],
            considered: [],
            elapsed_ms: 0,
            user_message: q,
            error: `HTTP ${r.status}`,
          });
        }
      } catch {
        if (skills.length > 0) {
          const offline = routeSkillsOffline(q, skills);
          setResult({ ...offline, elapsed_ms: Math.round(performance.now() - start) });
          setUsedOffline(true);
        } else {
          setResult({
            loaded_skills: [],
            considered: [],
            elapsed_ms: 0,
            user_message: q,
            error: 'Router unreachable',
          });
        }
      } finally {
        setRunning(false);
      }
    },
    [skills],
  );

  React.useEffect(() => {
    if (!runRequest?.query) return;
    setQuery(runRequest.query);
    run(runRequest.query);
  }, [runRequest?.nonce, runRequest?.query, run]);

  React.useEffect(() => {
    if (result && !result.error) {
      onLoadedSkills?.(result.loaded_skills);
    }
  }, [result, onLoadedSkills]);

  return (
    <ExpCard>
      <Eyebrow label="Live skill router · Haiku 4.5 @ 0.0" />
      <h3
        style={{
          fontFamily: 'var(--at-serif)',
          fontSize: '24px',
          fontWeight: 400,
          margin: '6px 0 14px',
          color: 'var(--at-ink-1)',
        }}
      >
        Type a query — see which skill the router would load.
      </h3>
      <p
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '14px',
          lineHeight: 1.6,
          color: 'var(--at-ink-2)',
          marginBottom: '16px',
        }}
      >
        The same call shape that fires before every chat turn. Haiku at
        temperature 0.0 is deterministic — try the same query twice and
        get the same routing.
      </p>

      {/* Example pills */}
      <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: '8px', marginBottom: '14px' }}>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.label}
            onClick={() => {
              setQuery(ex.query);
              run(ex.query);
            }}
            disabled={running}
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '12px',
              padding: '4px 10px',
              borderRadius: '999px',
              border: '1px solid var(--at-card-border)',
              background: 'var(--at-cream-2)',
              color: 'var(--at-ink-2)',
              cursor: running ? 'not-allowed' : 'pointer',
            }}
          >
            {ex.label}
          </button>
        ))}
      </div>

      {/* Input + run */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !running) run(query);
          }}
          placeholder="Try: hand-thrown ceramics for a slower morning"
          style={{
            flex: 1,
            fontFamily: 'var(--at-sans)',
            fontSize: '14px',
            padding: '10px 14px',
            border: '1px solid var(--at-card-border)',
            borderRadius: '6px',
            background: 'var(--at-cream-1)',
            color: 'var(--at-ink-1)',
          }}
        />
        <button
          onClick={() => run(query)}
          disabled={running || !query.trim()}
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '13px',
            padding: '10px 18px',
            borderRadius: '6px',
            border: 'none',
            background: 'var(--at-burgundy)',
            color: 'var(--at-cream-1)',
            cursor: running || !query.trim() ? 'not-allowed' : 'pointer',
            opacity: running || !query.trim() ? 0.5 : 1,
          }}
        >
          {running ? 'Routing…' : 'Run router'}
        </button>
      </div>

      {/* Result */}
      {result && result.error && (
        <div style={{ fontFamily: 'var(--at-mono)', fontSize: '13px', color: 'var(--at-red-1)' }}>
          {result.error}
        </div>
      )}
      {result && !result.error && (
        <div
          style={{
            border: '1px solid var(--at-card-border)',
            borderRadius: '6px',
            padding: '14px',
            background: 'var(--at-cream-1)',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              marginBottom: '12px',
            }}
          >
            <Eyebrow
              label={
                result.loaded_skills.length > 0
                  ? `Loaded · ${result.loaded_skills.join(', ')}`
                  : 'Loaded · none (base prompt only)'
              }
            />
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '12px',
                color: 'var(--at-ink-3)',
              }}
            >
              {result.elapsed_ms} ms
            </span>
          </div>

          {result.considered.length > 0 && (
            <div>
              <div
                style={{
                  fontFamily: 'var(--at-mono)',
                  fontSize: '11px',
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase' as const,
                  color: 'var(--at-ink-3)',
                  marginBottom: '8px',
                }}
              >
                Considered
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {result.considered.map((c) => {
                  const isLoaded = result.loaded_skills.includes(c.name);
                  const isHighlighted = highlightedSkillName === c.name;
                  return (
                    <button
                      key={c.name}
                      type="button"
                      onClick={() => onSelectSkill(c.name)}
                      style={{
                        width: '100%',
                        textAlign: 'left',
                        border: isHighlighted
                          ? '1px solid var(--at-red-1)'
                          : '1px solid transparent',
                        borderRadius: '6px',
                        padding: '6px 8px',
                        background: isLoaded ? 'var(--at-green-soft)' : 'transparent',
                        cursor: 'pointer',
                        display: 'grid',
                        gridTemplateColumns: '160px 1fr',
                        gap: '14px',
                        fontFamily: 'var(--at-sans)',
                        fontSize: '13px',
                        color: 'var(--at-ink-2)',
                      }}
                    >
                      <code
                        style={{
                          fontFamily: 'var(--at-mono)',
                          fontSize: '12px',
                          color: isLoaded
                            ? 'var(--at-status-shipped-text)'
                            : 'var(--at-ink-3)',
                          fontWeight: isLoaded ? 600 : 400,
                        }}
                      >
                        {isLoaded ? '✓ ' : '○ '}
                        {c.name}
                      </code>
                      <span style={{ lineHeight: 1.5 }}>{c.reason}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {usedOffline && result && !result.error && (
        <p
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            color: 'var(--at-ink-4)',
            marginTop: '10px',
          }}
        >
          Offline workshop routing — live endpoint unavailable; decisions are illustrative.
        </p>
      )}
    </ExpCard>
  );
};

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
  isSelected: boolean;
  isRouterMatch: boolean;
  rowRef: (el: HTMLDivElement | null) => void;
  onSelect: () => void;
  onTryRouter: () => void;
}

const SkillCard: React.FC<SkillCardProps> = ({
  skill,
  numeral,
  isSelected,
  isRouterMatch,
  rowRef,
  onSelect,
  onTryRouter,
}) => (
  <div
    ref={rowRef}
    data-testid={`skill-card-${skill.name}`}
    role="button"
    tabIndex={0}
    onClick={onSelect}
    onKeyDown={(e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onSelect();
      }
    }}
    style={{
      borderRadius: 'var(--at-card-radius)',
      outline: isSelected
        ? '2px solid var(--at-red-1)'
        : isRouterMatch
          ? '2px solid var(--at-green-1)'
          : undefined,
      boxShadow: isRouterMatch ? '0 0 0 3px var(--at-green-soft)' : undefined,
      cursor: 'pointer',
    }}
  >
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

    {/* Description — sans Instrument Sans, mirroring the AtelierWelcome
        summary treatment so explanatory copy reads as documentation
        not editorial. */}
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '15px',
        color: 'var(--at-ink-2)',
        lineHeight: 1.6,
        margin: '0 0 18px',
        maxWidth: '680px',
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
          backgroundColor: 'var(--dl-paper)',
          border: '1px solid var(--dl-line)',
          borderRadius: 'var(--dl-r-lg)',
          fontFamily: 'var(--dl-font-mono)',
          fontSize: '12.5px',
          lineHeight: 1.55,
          color: 'var(--dl-ink)',
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
      Source: <code>pellier/backend/skills/{skill.name}/SKILL.md</code>
    </p>

    {isSelected && (
      <div
        style={{
          marginTop: '14px',
          padding: '12px 14px',
          borderRadius: '8px',
          background: 'var(--at-cream-2)',
          border: '1px dashed var(--at-rule-2)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <span
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '14px',
            color: 'var(--at-ink-2)',
            marginRight: '12px',
          }}
        >
          Run the skill router with a query tuned for this persona.
        </span>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onTryRouter();
          }}
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '11px',
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            fontWeight: 600,
            color: 'var(--at-cream-1)',
            background: 'var(--at-ink-1)',
            border: 'none',
            borderRadius: '6px',
            padding: '7px 12px',
            cursor: 'pointer',
          }}
        >
          Try in router
        </button>
      </div>
    )}
  </ExpCard>
  </div>
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
    <p>No skills loaded. Check <code>pellier/backend/skills/</code>.</p>
  </div>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */
const ROMAN = ['I.', 'II.', 'III.', 'IV.', 'V.'];

const Skills: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<Skill[]>({ key: 'skills' });
  const skills = data ?? [];
  const [personaFilter, setPersonaFilter] = useState<PersonaFilter>('all');
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null);
  const [routerMatchSkill, setRouterMatchSkill] = useState<string | null>(null);
  const [routerRun, setRouterRun] = useState<{ query: string; nonce: number } | null>(null);
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const routerSectionRef = useRef<HTMLDivElement>(null);

  const filterCounts = useMemo(
    (): Record<PersonaFilter, number> => ({
      all: skills.length,
      marco: skills.filter((s) => s.persona === 'marco').length,
      anna: skills.filter((s) => s.persona === 'anna').length,
      theo: skills.filter((s) => s.persona === 'theo').length,
    }),
    [skills],
  );

  const filteredSkills = useMemo(
    () => filterSkillsByPersona(skills, personaFilter),
    [skills, personaFilter],
  );

  const focusSkill = useCallback((name: string) => {
    setSelectedSkill(name);
    setPersonaFilter('all');
    requestAnimationFrame(() => {
      rowRefs.current[name]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }, []);

  const handleTryRouter = useCallback(
    (skill: Skill) => {
      setRouterRun({ query: routerQueryForSkill(skill), nonce: Date.now() });
      routerSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },
    [],
  );

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
          <div ref={routerSectionRef}>
            <SkillRouterDemoCard
              skills={skills}
              highlightedSkillName={selectedSkill ?? routerMatchSkill}
              onSelectSkill={focusSkill}
              runRequest={routerRun}
              onLoadedSkills={(names) => setRouterMatchSkill(names[0] ?? null)}
            />
          </div>

          <SurfaceFilterBar
            label="Persona"
            filter={personaFilter}
            counts={filterCounts}
            options={PERSONA_FILTER_OPTIONS}
            onChange={setPersonaFilter}
          />

          {filteredSkills.map((skill, idx) => (
            <SkillCard
              key={skill.name}
              skill={skill}
              numeral={ROMAN[idx] ?? `${idx + 1}.`}
              isSelected={selectedSkill === skill.name}
              isRouterMatch={routerMatchSkill === skill.name}
              rowRef={(el) => {
                rowRefs.current[skill.name] = el;
              }}
              onSelect={() =>
                setSelectedSkill((prev) => (prev === skill.name ? null : skill.name))
              }
              onTryRouter={() => handleTryRouter(skill)}
            />
          ))}
        </div>
      )}

      {/* Cross-link to the Architecture concept brief for Skills.
          Helps participants jump from "what is this in production?" to
          "how does it fit in the broader architecture?" without going
          back to the sidebar. */}
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
          to="/atelier/architecture/skills"
          style={{ color: 'var(--at-burgundy)', textDecoration: 'none' }}
        >
          → Read the architecture brief on Skills
        </Link>
      </div>
    </div>
  );
};

export default Skills;
