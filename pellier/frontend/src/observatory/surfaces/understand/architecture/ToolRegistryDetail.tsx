import { Link } from 'react-router-dom';
import DetailPageShell from './DetailPageShell';
import { ExpCard } from '../../../components';

export default function ToolRegistryDetail() {
  return <DetailPageShell numeral="VII" conceptName="Tool Registry" category="workshop"
    title="Tools, discovered."
    prose="Aurora semantic discovery and AgentCore Gateway publication answer different questions. A relevant tool description does not establish that the tool is published, bound to an agent, or authorized for this caller."
    cheatSheet={[
      { numeral: 'i.', text: 'Discovery ranks embedded tool descriptions with pgvector. Inspect actual registry rows and the query result.' },
      { numeral: 'ii.', text: 'The canonical Gateway schemas define the managed interface. Publication selects the schemas exposed by a target.' },
      { numeral: 'iii.', text: 'Caller policy determines visibility and permission. Compare tool names for the same verified principal before and after the lab change.' },
    ]}>
    <div style={{ display: 'grid', gap: '20px', lineHeight: 1.65 }}>
      <ExpCard><h2>Read the actual registry</h2>
        <p>The Aurora registry is a teaching surface for semantic discovery. Its row count is separate from the Gateway schema count and the tools bound to one specialist.</p>
        <Link to="/observatory/tools">Inspect registered tools and discovery</Link>
      </ExpCard>
      <ExpCard><h2>Prove the managed tool contract</h2>
        <p>Lab 3 compares canonical schemas, published targets, caller-visible discovery, and the agent binding. It then probes an owned and a foreign ticket-history request. Keep those receipts with the final Storefront trace.</p>
        <p>A listed tool can still be denied for particular arguments. A missing result can reflect publication, caller policy, or runtime binding; identify the boundary before changing code.</p>
        <Link to="/observatory/labs/managed-agent-path">Open Lab 3: publish, bind, and verify</Link>
      </ExpCard>
    </div>
  </DetailPageShell>;
}
