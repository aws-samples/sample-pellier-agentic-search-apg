import { useEffect, useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { Link } from 'react-router-dom';

import './WorkbenchResources.css';

interface ResourceLink {
  label: string;
  description: string;
  path: string;
  /** The table, service or artefact the view reads. Never a paraphrase. */
  source: string;
}

interface ResourceQuestion {
  question: string;
  answer: string;
  links: ResourceLink[];
}

const RESOURCE_QUESTIONS: readonly ResourceQuestion[] = [
  {
    question: 'What ran?',
    answer:
      'Open the recorded turn, then inspect the control and receipt claims tied to it.',
    links: [
      {
        label: 'Sessions & traces',
        description: 'Turn-scoped chat, telemetry, and durable replay.',
        path: '/observatory/sessions',

        source: 'governed_turn_receipts, evidence_ledger_event_refs',
      },
      {
        label: 'Proof Board',
        description: 'Managed rail, policy, audit, and SQL-backed checkpoints.',
        path: '/observatory/proof-board',

        source: 'policy, tool_audit and write receipts per lab',
      },
      {
        label: 'Replacement recovery',
        description: 'An exact approval, reservation, outbox, and fulfillment history.',
        path: '/observatory/replacement',
        source: 'approvals, replacements, replacement_outbox, replacement_events',
      },
    ],
  },
  {
    question: 'Why was it allowed?',
    answer:
      'Separate verified identity and policy authorization from tool execution.',
    links: [
      {
        label: 'Govern: identity, access & policy',
        description: 'Authentication, delegated agent access, Cedar policies, and durable outcomes.',
        path: '/observatory/govern',

        source: 'governed_receipts (Cedar), tool_audit',
      },
      {
        label: 'Tool Registry',
        description: 'Callable schemas and the exact governed Aurora surface.',
        path: '/observatory/tools',

        source: 'tool registry, MCP schemas',
      },
    ],
  },
  {
    question: 'What reached PostgreSQL?',
    answer:
      'Inspect eligibility, rank fusion, SQL receipts, and the owning tables.',
    links: [
      {
        label: 'Search pipeline',
        description: 'pgvector, full-text search, RRF, filters, and reranking.',
        path: '/observatory/search',

        source: 'retrieval_receipts, live EXPLAIN',
      },
      {
        label: 'Retrieval comparison',
        description: 'Observed latency, index behavior, quality, and cost.',
        path: '/observatory/performance',

        source: 'measured on Aurora at run time',
      },
    ],
  },
  {
    question: 'How does this operate?',
    answer:
      'Pressure-test ownership, release gates, and production failure modes.',
    links: [
      {
        label: 'Architecture',
        description: 'Runtime boundaries, control planes, and state ownership.',
        path: '/observatory/architecture',

        source: 'source tree, deploy templates',
      },
      {
        label: 'Evaluations & production',
        description: 'Golden journeys, tenancy, reliability, and release gates.',
        path: '/observatory/evaluations',

        source: 'evaluation scorecards, golden journeys',
      },
    ],
  },
];

const GITHUB_REPOSITORY_URL =
  'https://github.com/aws-samples/sample-pellier-agentic-search-apg';

/* A source token is set in mono only when it is something a participant can
   paste: a snake_case relation or a relation with a qualifier, such as
   `governed_receipts (Cedar)`. "measured on Aurora at run time" and "golden
   journeys" describe a source in words and take the prose register, because
   mono on these surfaces means code or measurement and never a technical
   costume. */
const IDENTIFIER_TOKEN = /^[a-z][a-z0-9_]*(?: \([A-Za-z][A-Za-z ]*\))?$/;

function sourceTokens(source: string): string[] {
  return source
    .split(',')
    .map((token) => token.trim())
    .filter(Boolean);
}

const VIEW_COUNT = RESOURCE_QUESTIONS.reduce((total, group) => total + group.links.length, 0);

function ResourceSources({ source }: { source: string }) {
  return (
    <span className="workbench-resource-sources">
      {sourceTokens(source).map((token) => (
        <span key={token} className="workbench-resource-source" data-register={IDENTIFIER_TOKEN.test(token) ? 'identifier' : 'prose'}>
          {IDENTIFIER_TOKEN.test(token) ? <code>{token}</code> : token}
        </span>
      ))}
    </span>
  );
}

interface WorkbenchResourcesProps {
  compact?: boolean;
  /**
   * The Lab Collection is an orientation surface, while the live workbench is
   * an execution surface. The latter can keep this index available without
   * taking space from the Evidence ledger until a participant asks for it.
   */
  collapsible?: boolean;
  defaultExpanded?: boolean;
}

export default function WorkbenchResources({
  compact = false,
  collapsible = false,
  defaultExpanded = true,
}: WorkbenchResourcesProps) {
  const contentId = useId();
  const [expanded, setExpanded] = useState(
    () =>
      !collapsible ||
      defaultExpanded ||
      (typeof window !== 'undefined' && window.location.hash === '#resources'),
  );

  // Several reference links intentionally target /observatory/workbench#resources.
  // Opening the index before the browser scrolls there keeps that destination
  // useful without making the workbench default to a long reference section.
  useEffect(() => {
    if (!collapsible) return undefined;

    const revealForResourceHash = () => {
      if (window.location.hash === '#resources') {
        setExpanded(true);
      }
    };

    revealForResourceHash();
    window.addEventListener('hashchange', revealForResourceHash);
    return () => window.removeEventListener('hashchange', revealForResourceHash);
  }, [collapsible]);

  const content = (
    <div
      id={contentId}
      className="workbench-resources-content"
      hidden={collapsible && !expanded}
    >
      <header className="workbench-resources-heading">
        <div className="workbench-resources-title">
          <h2 id="workbench-resources-title">Telemetry &amp; system references</h2>
          <p>Follow a question into the evidence. Each view names its sources.</p>
        </div>
        <div className="workbench-resources-canonical">
          <span>{VIEW_COUNT} reference views</span>
          <a href={GITHUB_REPOSITORY_URL} target="_blank" rel="noopener noreferrer">
            Workshop source
          </a>
        </div>
      </header>

      <div className="workbench-resources-index">
        {RESOURCE_QUESTIONS.map((group) => (
          <section
            key={group.question}
            className="workbench-resource-question"
            aria-label={group.question}
          >
            <div className="workbench-resource-question-head">
              <h3>{group.question}</h3>
              <p>{group.answer}</p>
            </div>
            <ul className="workbench-resource-links">
              {group.links.map((resource) => (
                <li key={resource.path}>
                  <div className="workbench-resource-view">
                    <Link to={resource.path}>{resource.label}</Link>
                  </div>
                  <p className="workbench-resource-shows">{resource.description}</p>
                  <details className="workbench-source-disclosure">
                    <summary>View sources</summary>
                    <ResourceSources source={resource.source} />
                  </details>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <p className="workbench-resources-legend">These views are optional. Use <code>psql</code> and the AgentCore CLI for the lab proof.</p>
    </div>
  );

  return (
    <section
      id="resources"
      className="workbench-resources"
      data-compact={compact ? 'true' : undefined}
      data-collapsible={collapsible ? 'true' : undefined}
      aria-label={collapsible ? 'Reference views' : undefined}
      aria-labelledby={collapsible ? undefined : 'workbench-resources-title'}
    >
      {collapsible ? (
        <div className="workbench-resources-disclosure">
          <button
            type="button"
            className="workbench-resources-disclosure-button"
            aria-expanded={expanded}
            aria-controls={contentId}
            onClick={() => setExpanded((current) => !current)}
          >
            <span className="workbench-resources-disclosure-copy">
              <strong>
                {expanded ? 'Hide reference views' : 'Explore reference views'}
              </strong>
              <ChevronDown
                size={14}
                strokeWidth={1.8}
                aria-hidden="true"
                data-expanded={expanded ? 'true' : undefined}
              />
            </span>
          </button>
        </div>
      ) : null}
      {content}
    </section>
  );
}
