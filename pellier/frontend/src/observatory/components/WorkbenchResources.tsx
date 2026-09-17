import { useEffect, useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import type { LabExerciseId } from '../labs/labCatalog';
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
  labId?: LabExerciseId;
}

export default function WorkbenchResources({ compact = false, collapsible = false, defaultExpanded = true, labId }: WorkbenchResourcesProps) {
  const contentId = useId();
  const { hash } = useLocation();
  const [expanded, setExpanded] = useState(!collapsible || defaultExpanded || hash === '#resources');
  // React Router hash navigation does not always dispatch a native hashchange.
  useEffect(() => { if (hash === '#resources') setExpanded(true); }, [hash]);
  const activeGroups = LAB_REFERENCE_GROUPS.filter(group => !labId || group.lab === labId);
  const otherGroups = LAB_REFERENCE_GROUPS.filter(group => labId && group.lab !== labId);
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
          <p>{labId ? 'References for your current lab. Open one when you need to explain a result, then return to your Workbench.' : 'Follow the four lab questions into their evidence and implementation. Workshop Studio holds the instructions and acceptance checks.'}</p>
        </div>
        <div className="workbench-resources-canonical"><span>Four labs · evidence and explanation</span><a href={GOVERNED_SOURCE} target="_blank" rel="noopener noreferrer">Governed workshop source</a></div>
      </header>
      {groups(activeGroups)}
      {otherGroups.length > 0 && <details className="workbench-resource-extension"><summary>References for the other labs</summary>{groups(otherGroups)}</details>}
      <details className="workbench-resource-extension"><summary>After the labs: evaluation and recovery</summary>
        <p>Extend an established lab result into a production question. These views are outside the four required lab builds.</p>
        <ReferenceLinks ids={EXTENSION_REFERENCES} />
      </details>
      <p className="workbench-resources-legend">Use these views to interpret evidence. Retain the matching <code>psql</code> output and AgentCore CLI results from Workshop Studio; opening a reference does not complete a lab.</p>
    </div>
  </section>;
}
