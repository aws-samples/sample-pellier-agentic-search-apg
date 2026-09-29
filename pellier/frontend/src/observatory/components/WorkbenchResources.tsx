import { useEffect, useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { EXTENSION_REFERENCES, GOVERNED_SOURCE, LAB_REFERENCE_GROUPS, REFERENCES, type ReferenceId } from './referenceCatalog';
import './WorkbenchResources.css';

function ReferenceLinks({ ids }: { ids: ReferenceId[] }) {
  return <ul className="workbench-resource-links">{ids.map(id => {
    const reference = REFERENCES[id];
    return <li key={id}>
      <div className="workbench-resource-view"><Link to={reference.path}>{reference.label}</Link></div>
      <p className="workbench-resource-shows">{reference.question}</p>
      <span className="workbench-resource-role">{reference.role}</span>
    </li>;
  })}</ul>;
}

interface WorkbenchResourcesProps {
  compact?: boolean;
  collapsible?: boolean;
  defaultExpanded?: boolean;
  /**
   * `all` is the full index on the Lab Collection. `extensions` is what the
   * Workbench keeps: its lab's own views are in the lab strip above the page.
   */
  scope?: 'all' | 'extensions';
}

const EXTENSION_NOTE = 'Extend an established lab result into a production question. These views are outside the four required lab builds.';

export default function WorkbenchResources({ compact = false, collapsible = false, defaultExpanded = true, scope = 'all' }: WorkbenchResourcesProps) {
  const contentId = useId();
  const { hash } = useLocation();
  const [expanded, setExpanded] = useState(!collapsible || defaultExpanded || hash === '#resources');
  // React Router hash navigation does not always dispatch a native hashchange.
  useEffect(() => { if (hash === '#resources') setExpanded(true); }, [hash]);
  if (scope === 'extensions') {
    return <section id="resources" className="workbench-resources" data-compact="true" aria-label="After the labs">
      <details className="workbench-resource-extension"><summary>After the labs: evaluation and recovery</summary>
        <p>{EXTENSION_NOTE}</p>
        <ReferenceLinks ids={EXTENSION_REFERENCES} />
      </details>
    </section>;
  }
  const groups = (items: typeof LAB_REFERENCE_GROUPS) => <div className="workbench-resources-index">{items.map(group => (
    <section key={group.lab} className="workbench-resource-question" aria-label={group.title}>
      <div className="workbench-resource-question-head"><h3>{group.title}</h3><p>{group.question}</p></div>
      <ReferenceLinks ids={group.refs} />
    </section>
  ))}</div>;
  return <section id="resources" className="workbench-resources"
    data-compact={compact ? 'true' : undefined} data-collapsible={collapsible ? 'true' : undefined}
    aria-label="Reference views">
    {collapsible && <div className="workbench-resources-disclosure">
      <button type="button" className="workbench-resources-disclosure-button" aria-expanded={expanded} aria-controls={contentId} onClick={() => setExpanded(value => !value)}>
        <span className="workbench-resources-disclosure-copy"><strong>{expanded ? 'Hide reference views' : 'Explore reference views'}</strong>
          <ChevronDown size={14} aria-hidden="true" data-expanded={expanded ? 'true' : undefined} />
        </span>
      </button>
    </div>}
    <div id={contentId} className="workbench-resources-content" hidden={collapsible && !expanded}>
      <header className="workbench-resources-heading">
        <div className="workbench-resources-title"><h2>Telemetry &amp; system references</h2>
          <p>Follow the four lab questions into their evidence and implementation. Workshop Studio holds the instructions and acceptance checks.</p>
        </div>
        <div className="workbench-resources-canonical"><span>Four labs · evidence and explanation</span><a href={GOVERNED_SOURCE} target="_blank" rel="noopener noreferrer">Governed workshop source</a></div>
      </header>
      {groups(LAB_REFERENCE_GROUPS)}
      <details className="workbench-resource-extension"><summary>After the labs: evaluation and recovery</summary>
        <p>{EXTENSION_NOTE}</p>
        <ReferenceLinks ids={EXTENSION_REFERENCES} />
      </details>
      <p className="workbench-resources-legend">Use these views to interpret evidence. Retain the matching <code>psql</code> output and AgentCore CLI results from Workshop Studio; opening a reference does not complete a lab.</p>
    </div>
  </section>;
}
