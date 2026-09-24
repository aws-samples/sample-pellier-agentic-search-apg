import { apiFetch } from '../../../services/apiBase'
/**
 * Skills — the 5 prompt overlays loaded by the SkillRouter.
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
 * /skills/<slug>/SKILL.md file directly, not a database row.
 */

import React, { useState, useCallback, useMemo, useRef } from 'react';
import { Link } from 'react-router-dom';
import { EditorialTitle, ExpCard, Eyebrow, SurfaceFilterBar } from '../../components';
import { useObservatoryData } from '../../hooks/useObservatoryData';
import type { Skill, SkillApiRow } from '../../types';
import { toSkill } from '../../types/skill';
import { routerQueryForSkill } from './skillsRouterUtils';

type PersonaFilter = 'all' | 'marco' | 'anna' | 'theo' | 'shared';

const PERSONA_FILTER_OPTIONS = [
  { id: 'all' as const, label: 'All personas' },
  { id: 'marco' as const, label: 'Marco' },
  { id: 'anna' as const, label: 'Anna' },
  { id: 'theo' as const, label: 'Theo' },
  { id: 'shared' as const, label: 'Shared' },
];

function filterSkillsByPersona(skills: Skill[], filter: PersonaFilter): Skill[] {
  if (filter === 'all') return skills;
  return skills.filter((s) => s.persona === filter);
}

/* -----------------------------------------------------------------------
 * Skill Router Demo Card
 *
 * Live demonstration of the SkillRouter (Sonnet 5).
 * Mirrors the Tools page's DiscoveryDemoCard pattern: type a query,
 * see what the router would decide for that turn (which skills to
 * load + which it considered and why it rejected them).
 *
 * The same call shape is used by the chat pipeline — when a user
 * submits a query in Pellier, this exact decision is emitted as
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
  { label: "Marco's Turn 2", query: 'What would go with the Hadley Linen Shirt?' },
  { label: "Anna's gift query", query: 'wrap-ready gifts with no extra effort' },
  { label: "Theo's pairing query", query: 'what goes well with the pour-over set?' },
  { label: 'Care path', query: 'The bowl arrived damaged. What now?' },
  { label: 'Proof path', query: 'How do you know this fits my taste?' },
];

interface SkillRouterDemoCardProps {
  highlightedSkillName: string | null;
  onSelectSkill: (name: string) => void;
  runRequest?: { query: string; nonce: number } | null;
  onLoadedSkills?: (names: string[]) => void;
}

const SkillRouterDemoCard: React.FC<SkillRouterDemoCardProps> = ({
  highlightedSkillName,
  onSelectSkill,
  runRequest,
  onLoadedSkills,
}) => {
  const [query, setQuery] = useState('');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RouterResult | null>(null);

  const run = useCallback(
    async (q: string) => {
      if (!q.trim()) return;
      setRunning(true);
      setResult(null);
      try {
        const r = await apiFetch('/api/observatory/skills/route', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: q }),
        });
        if (r.ok) {
          const data = (await r.json()) as RouterResult;
          setResult(data);
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
        setResult({
          loaded_skills: [],
          considered: [],
          elapsed_ms: 0,
          user_message: q,
          error: 'Router unreachable',
        });
      } finally {
        setRunning(false);
      }
    },
    [],
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
      <Eyebrow label="Live skill router · Sonnet 5" />
      <h3
        style={{
          fontFamily: 'var(--obs-heading)',
          fontSize: '24px',
          fontWeight: 400,
          margin: '6px 0 14px',
          color: 'var(--obs-ink-1)',
        }}
      >
        Type a query – see which skill the router would load.
      </h3>
      <p
        style={{
          fontFamily: 'var(--obs-sans)',
          fontSize: '14px',
          lineHeight: 1.6,
          color: 'var(--obs-ink-2)',
          marginBottom: '16px',
        }}
      >
        The same call shape that fires before every chat turn. The router
        uses a tight JSON-only prompt so repeated queries should land on the
        same skill decision.
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
              fontFamily: 'var(--obs-mono)',
              fontSize: '12px',
              padding: '4px 10px',
              borderRadius: '999px',
              border: '1px solid var(--obs-card-border)',
              background: 'var(--obs-cream-2)',
              color: 'var(--obs-ink-2)',
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
            fontFamily: 'var(--obs-sans)',
            fontSize: '14px',
            padding: '10px 14px',
            border: '1px solid var(--obs-card-border)',
            borderRadius: '6px',
            background: 'var(--obs-cream-1)',
            color: 'var(--obs-ink-1)',
          }}
        />
        <button
          onClick={() => run(query)}
          disabled={running || !query.trim()}
          style={{
            fontFamily: 'var(--obs-mono)',
            fontSize: '13px',
            padding: '10px 18px',
            borderRadius: '6px',
            border: 'none',
            background: 'var(--obs-burgundy)',
            color: 'var(--obs-cream-1)',
            cursor: running || !query.trim() ? 'not-allowed' : 'pointer',
            opacity: running || !query.trim() ? 0.5 : 1,
          }}
        >
          {running ? 'Routing…' : 'Run router'}
        </button>
      </div>

      {/* Result */}
      {result && result.error && (
        <div style={{ fontFamily: 'var(--obs-mono)', fontSize: '13px', color: 'var(--obs-red-1)' }}>
          {result.error}
        </div>
      )}
      {result && !result.error && (
        <div
          style={{
            border: '1px solid var(--obs-card-border)',
            borderRadius: '6px',
            padding: '14px',
            background: 'var(--obs-cream-1)',
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
                fontFamily: 'var(--obs-mono)',
                fontSize: '12px',
                color: 'var(--obs-ink-3)',
              }}
            >
              {result.elapsed_ms} ms
            </span>
          </div>

          {result.considered.length > 0 && (
            <div>
              <div
                style={{
                  fontFamily: 'var(--obs-mono)',
                  fontSize: '11px',
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase' as const,
                  color: 'var(--obs-ink-3)',
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
                          ? '1px solid var(--obs-red-1)'
                          : '1px solid transparent',
                        borderRadius: '6px',
                        padding: '6px 8px',
                        background: isLoaded ? 'var(--obs-green-soft)' : 'transparent',
                        cursor: 'pointer',
                        display: 'grid',
                        gridTemplateColumns: '160px 1fr',
                        gap: '14px',
                        fontFamily: 'var(--obs-sans)',
                        fontSize: '13px',
                        color: 'var(--obs-ink-2)',
                      }}
                    >
                      <code
                        style={{
                          fontFamily: 'var(--obs-mono)',
                          fontSize: '12px',
                          color: isLoaded
                            ? 'var(--obs-status-shipped-text)'
                            : 'var(--obs-ink-3)',
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
      backgroundColor: 'var(--obs-cream-2)',
      border: '1px solid var(--obs-rule-1)',
      color: 'var(--obs-ink-1)',
      fontFamily: 'var(--obs-mono)',
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
      color: 'var(--obs-red-1)',
      fontFamily: 'var(--obs-mono)',
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
        background: 'var(--obs-red-1)',
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
      color: 'var(--obs-ink-1)',
      fontFamily: 'var(--obs-sans)',
      fontSize: '12px',
      fontWeight: 500,
      lineHeight: 1.4,
    }}
  >
    {name}
  </span>
);

function renderSkillBody(body: string): React.ReactNode {
  const lines = body.split('\n');
  return lines.map((line, index) => {
    const isBullet = line.trim().startsWith('- ');
    const isIntro = index === 0;

    return (
      <React.Fragment key={`${index}-${line}`}>
        <span
          style={{
            color: isIntro
              ? '#f7c873'
              : isBullet
                ? '#e8927c'
                : 'var(--dl-accent-soft)',
          }}
        >
          {isBullet ? (
            <>
              <span style={{ color: '#f7c873' }}>- </span>
              <span>{line.trim().slice(2)}</span>
            </>
          ) : (
            line
          )}
        </span>
        {index < lines.length - 1 && '\n'}
      </React.Fragment>
    );
  });
}

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
    aria-label={skill.displayName}
    aria-pressed={isSelected}
    onClick={onSelect}
    onKeyDown={(e) => {
      if (e.target !== e.currentTarget) return;
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onSelect();
      }
    }}
    style={{
      borderRadius: 'var(--obs-card-radius)',
      outline: isSelected
        ? '2px solid var(--obs-red-1)'
        : isRouterMatch
          ? '2px solid var(--obs-green-1)'
          : undefined,
      boxShadow: isRouterMatch ? '0 0 0 3px var(--obs-green-soft)' : undefined,
      cursor: 'pointer',
    }}
  >
  <ExpCard>
    {/* Head: numeral + title + persona chip */}
    <div style={{ display: 'grid', gridTemplateColumns: '38px 1fr auto', gap: '14px', alignItems: 'baseline', marginBottom: '14px' }}>
      <span
        style={{
          fontFamily: 'var(--obs-heading)',
          fontSize: '30px',
          color: 'var(--obs-red-1)',
          letterSpacing: '-0.02em',
          lineHeight: 1,
        }}
      >
        {numeral}
      </span>
      <h3
        style={{
          fontFamily: 'var(--obs-heading)',
          fontWeight: 400,
          fontSize: '24px',
          letterSpacing: '-0.012em',
          lineHeight: 1.1,
          color: 'var(--obs-ink-1)',
          margin: 0,
        }}
      >
        {skill.displayName}
      </h3>
      <div style={{ alignSelf: 'start' }}>
        <PersonaChip name={skill.personaDisplayName} />
      </div>
    </div>

    {/* Description — sans Instrument Sans, mirroring the ObservatoryWelcome
        summary treatment so explanatory copy reads as documentation
        not editorial. */}
    <p
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: '15px',
        color: 'var(--obs-ink-2)',
        lineHeight: 1.6,
        margin: '0 0 18px',
        maxWidth: '680px',
      }}
    >
      {skill.description}
    </p>

    {/* Signals and "loaded by" are curated fields that the live registry does
        not own: GET /api/observatory/skills reads SKILL.md frontmatter, which
        carries name, display_name, description, version and persona only. When
        the surface reads live data these are absent, so the panel is omitted
        rather than filled — an inspection surface must not invent the evidence
        it is supposed to show. `skill.signals.map` on an absent array is what
        crashed this route into the error boundary. */}
    {skill.signals && skill.signals.length > 0 ? (
      <div style={{ marginBottom: '18px' }}>
        <Eyebrow label="Signals the SkillRouter watches for" />
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
          {skill.signals.map((s) => (
            <SignalPill key={s} label={s} />
          ))}
        </div>
      </div>
    ) : null}

    {skill.loadedBy && skill.loadedBy.length > 0 ? (
      <div style={{ marginBottom: '18px' }}>
        <Eyebrow label="Loaded by" />
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
          {skill.loadedBy.map((a) => (
            <AgentChip key={a} name={a} />
          ))}
        </div>
      </div>
    ) : null}

    {/* Body (the guidance passed to the model) */}
    <div>
      <Eyebrow label="Skill body (injected into system prompt)" />
      <pre
        tabIndex={0}
        role="region"
        aria-label={`${skill.name} skill guidance`}
        style={{
          marginTop: '8px',
          padding: '18px 20px',
          backgroundColor: 'var(--dl-ink)',
          border: '1px solid color-mix(in srgb, var(--dl-accent-soft) 18%, transparent)',
          borderRadius: 'var(--dl-r-lg)',
          fontFamily: 'var(--obs-mono)',
          fontSize: '13px',
          lineHeight: 1.6,
          color: 'var(--dl-accent-soft)',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          overflow: 'auto',
          maxHeight: '320px',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04)',
        }}
      >
        {renderSkillBody(skill.body)}
      </pre>
    </div>

    {/* File path hint */}
    <p
      style={{
        marginTop: '10px',
        fontFamily: 'var(--obs-mono)',
        fontSize: '11px',
        color: 'var(--obs-ink-2)',
        lineHeight: 1.4,
      }}
    >
      Source: <code>/skills/{skill.name}/SKILL.md</code>
    </p>

    {isSelected && (
      <div
        style={{
          marginTop: '14px',
          padding: '12px 14px',
          borderRadius: '8px',
          background: 'var(--obs-cream-2)',
          border: '1px dashed var(--obs-rule-2)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <span
          style={{
            fontFamily: 'var(--obs-sans)',
            fontSize: '14px',
            color: 'var(--obs-ink-2)',
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
            fontFamily: 'var(--obs-mono)',
            fontSize: '11px',
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            fontWeight: 600,
            color: 'var(--obs-cream-1)',
            background: 'var(--obs-ink-1)',
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
  <div style={{ padding: '32px', textAlign: 'center', color: 'var(--obs-ink-2)' }}>Loading skills…</div>
);

const ErrorState: React.FC<{ message: string; onRetry: () => void }> = ({ message, onRetry }) => (
  <div style={{ padding: '32px', textAlign: 'center' }}>
    <p style={{ color: 'var(--obs-red-1)', marginBottom: '12px' }}>Failed to load skills: {message}</p>
    <button onClick={onRetry} style={{ padding: '6px 14px', borderRadius: '6px', border: '1px solid var(--obs-rule-2)', background: 'var(--obs-cream-1)', cursor: 'pointer' }}>
      Retry
    </button>
  </div>
);

const EmptyState: React.FC = () => (
  <div style={{ padding: '32px', textAlign: 'center', color: 'var(--obs-ink-2)' }}>
    <p>No skills loaded. Check <code>/skills/</code>.</p>
  </div>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */
const ROMAN = ['I.', 'II.', 'III.', 'IV.', 'V.'];

const Skills: React.FC = () => {
  const { data, loading, error, refetch } = useObservatoryData<SkillApiRow[]>({
    key: 'skills',
  });
  // The registry answers in snake_case and omits the curated fields; normalize
  // once here so no card reads `undefined` for its own title.
  const skills: Skill[] = useMemo(() => (data ?? []).map(toSkill), [data]);
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
      shared: skills.filter((s) => s.persona === 'shared').length,
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
        backToReferences
        eyebrow="Understand · Skills · five prompt overlays"
        title="Runtime skills"
        summary="Five Markdown files. Three are persona-tied; two are shared proof and care overlays. Loaded per turn by the SkillRouter – Sonnet 5 with a JSON-only routing prompt – and injected into the specialist's system prompt. Skills change voice and handling, not product selection."
      />
      <ExpCard>
        <Eyebrow label="Two routers · different jobs" />
        <p
          style={{
            fontFamily: 'var(--obs-sans)',
            fontSize: '14px',
            lineHeight: 1.6,
            color: 'var(--obs-ink-2)',
            margin: '8px 0 0',
          }}
        >
          Intent router in <code style={{ fontFamily: 'var(--obs-mono)' }}>services/chat.py</code>{' '}
          picks the specialist. SkillRouter then decides whether to inject persona overlays from{' '}
          <code style={{ fontFamily: 'var(--obs-mono)' }}>/skills/&lt;slug&gt;/SKILL.md</code>{' '}
          into that specialist&apos;s prompt for this turn.
        </p>
      </ExpCard>

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={refetch} />}
      {!loading && !error && skills.length === 0 && <EmptyState />}

      {!loading && !error && skills.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          <div ref={routerSectionRef}>
            <SkillRouterDemoCard
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
          borderTop: '1px solid var(--obs-card-border)',
          fontFamily: 'var(--obs-mono)',
          fontSize: '13px',
          color: 'var(--obs-ink-2)',
        }}
      >
        <Link
          to="/observatory/architecture/skills"
          style={{ color: 'var(--obs-burgundy)', textDecoration: 'none' }}
        >
          → Read the architecture brief on Skills
        </Link>
      </div>
    </div>
  );
};

export default Skills;
