import { Link } from 'react-router-dom';
import DetailPageShell from './DetailPageShell';
import { ExpCard } from '../../../components';

export default function McpDetail() {
  return <DetailPageShell numeral="VIII" conceptName="MCP Gateway" category="workshop"
    title="Gateway, governed."
    prose="Labs 1 and 2 establish an in-process baseline. Lab 3 moves the specialist tool path behind AgentCore Runtime and Gateway. The managed path carries the verified caller token and fails closed when its required Gateway boundary is unavailable."
    cheatSheet={[
      { numeral: 'i.', text: 'Discover tool names and schemas through Gateway with the same caller identity used for invocation.' },
      { numeral: 'ii.', text: 'Gateway publication, Cedar permission, runtime binding, and Aurora ownership checks are separate contracts.' },
      { numeral: 'iii.', text: 'Retain the managed trace and database evidence. A deployment identifier alone does not prove the request used the managed path.' },
    ]}>
    <div style={{ display: 'grid', gap: '20px', lineHeight: 1.65 }}>
      <ExpCard><h2>Follow the caller to the database</h2>
        <ol>
          <li>The application verifies the caller and invokes the managed Runtime.</li>
          <li>The specialist discovers and invokes its bound tools through Gateway with the caller token.</li>
          <li>Gateway applies the configured Cedar policy before the target executes.</li>
          <li>The target validates the request and calls Aurora under the appropriate ownership and business constraints.</li>
          <li>The participant compares the tool result, trace, receipt, and database state.</li>
        </ol>
        <p>Verify the effective policy enforcement mode. A logged decision alone does not establish that a prohibited request was blocked.</p>
      </ExpCard>
      <ExpCard><h2>Check names before counting tools</h2>
        <p>The source catalogue, published target schemas, caller-visible discovery result, and specialist binding can contain different sets. Staff-only actions must not become shopper capabilities merely because their schemas exist.</p>
        <Link to="/observatory/labs/managed-agent-path">Run the Lab 3 discovery and ownership checks</Link>
      </ExpCard>
      <ExpCard><h2>Separate shopper execution from operator review</h2>
        <p>A managed shopper return invokes its authorized tool after the relevant checks. The Operator Concierge uses a separate durable human review flow. Both need evidence of the resulting database effect.</p>
        <Link to="/observatory/govern">Inspect governance contracts and receipts</Link>
      </ExpCard>
    </div>
  </DetailPageShell>;
}
