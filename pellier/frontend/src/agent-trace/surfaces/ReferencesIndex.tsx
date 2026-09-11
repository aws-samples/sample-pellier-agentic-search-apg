import type { LucideIcon } from 'lucide-react';
import {
  ArrowRight,
  BookOpen,
  ClipboardCheck,
  ConciergeBell,
  DatabaseZap,
  Footprints,
  Gauge,
  History,
  IdCard,
  Layers,
  Network,
  Search,
  Signpost,
  Wrench,
} from 'lucide-react';
import { Link } from 'react-router-dom';

interface ReferenceLink {
  label: string;
  description: string;
  path: string;
  icon: LucideIcon;
}

interface ReferenceGroup {
  title: string;
  description: string;
  links: ReferenceLink[];
}

const REFERENCE_GROUPS: ReferenceGroup[] = [
  {
    title: 'Replay and compare',
    description:
      'Return to canonical shopper requests or inspect an earlier session.',
    links: [
      {
        label: 'Persona journeys',
        description: 'Compare Marco, Anna, and Theo across request and tool paths.',
        path: '/pellier-labs/persona-journeys',
        icon: Footprints,
      },
      {
        label: 'Sessions',
        description: 'Replay captured conversations and their emitted evidence.',
        path: '/pellier-labs/sessions',
        icon: History,
      },
    ],
  },
  {
    title: 'Inspect the request path',
    description:
      'Open a focused technical lens only when the workshop or your own investigation calls for it.',
    links: [
      {
        label: 'Architecture',
        description: 'Request topology, runtime boundaries, and component ownership.',
        path: '/pellier-labs/architecture',
        icon: Network,
      },
      {
        label: 'Agents',
        description: 'Specialist instructions, tool grants, and handoffs.',
        path: '/pellier-labs/agents',
        icon: ConciergeBell,
      },
      {
        label: 'Tools',
        description: 'Callable contracts and Aurora-backed operations.',
        path: '/pellier-labs/tools',
        icon: Wrench,
      },
      {
        label: 'Skills',
        description: 'Prompt overlays selected for each request.',
        path: '/pellier-labs/skills',
        icon: BookOpen,
      },
      {
        label: 'Search',
        description: 'Hybrid retrieval, rank fusion, filtering, and reranking.',
        path: '/pellier-labs/search',
        icon: Search,
      },
      {
        label: 'Routing',
        description: 'Intent classification and deterministic specialist dispatch.',
        path: '/pellier-labs/routing',
        icon: Signpost,
      },
      {
        label: 'Memory',
        description:
          'AgentCore session turns and preferences, separated from Aurora state and evidence.',
        path: '/pellier-labs/memory',
        icon: IdCard,
      },
      {
        label: 'Write path',
        description: 'Audited mutations and the controls around them.',
        path: '/pellier-labs/write-path',
        icon: DatabaseZap,
      },
    ],
  },
  {
    title: 'Evaluate and productionize',
    description:
      'Use these deeper lenses after the required build and observation path.',
    links: [
      {
        label: 'Performance',
        description: 'Four-strategy retrieval comparison, timing, and index behavior.',
        path: '/pellier-labs/performance',
        icon: Gauge,
      },
      {
        label: 'Evaluations',
        description: 'Golden journeys and response-quality checks.',
        path: '/pellier-labs/evaluations',
        icon: ClipboardCheck,
      },
      {
        label: 'Production patterns',
        description: 'Identity, tenancy, reliability, and guardrail decisions.',
        path: '/pellier-labs/production-patterns',
        icon: Layers,
      },
    ],
  },
];

export default function ReferencesIndex() {
  return (
    <div className="pellier-labs-references">
      <header className="pellier-labs-references-header">
        <h1>Optional Deep Dives</h1>
        <p>
          Follow the lab guide for the required steps. Open a deep dive when
          a lab links here or you want to explore the implementation.
        </p>
      </header>

      <div className="pellier-labs-reference-groups">
        {REFERENCE_GROUPS.map((group) => {
          const sectionId = `reference-${group.title.toLowerCase().replace(/ /g, '-')}`;
          return (
            <section
              key={group.title}
              className="pellier-labs-reference-group"
              aria-labelledby={sectionId}
            >
              <div className="pellier-labs-reference-group-heading">
                <h2 id={sectionId}>{group.title}</h2>
                <p>{group.description}</p>
              </div>
              <div className="pellier-labs-reference-links">
                {group.links.map((item) => {
                  const ItemIcon = item.icon;
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      className="pellier-labs-reference-link"
                    >
                      <span className="pellier-labs-reference-link-icon">
                        <ItemIcon size={19} strokeWidth={1.85} aria-hidden="true" />
                      </span>
                      <span className="pellier-labs-reference-link-copy">
                        <strong>{item.label}</strong>
                        <span>{item.description}</span>
                      </span>
                      <ArrowRight
                        className="pellier-labs-reference-link-arrow"
                        size={17}
                        strokeWidth={1.7}
                        aria-hidden="true"
                      />
                    </Link>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
