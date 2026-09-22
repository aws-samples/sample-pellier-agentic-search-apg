import { apiFetch } from '../../../services/apiBase'
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { EditorialTitle } from '../../components';
import { useObservatoryData } from '../../hooks/useObservatoryData';
import { CANONICAL_ANNA_QUERY } from '../../constants/canonicalQuery';
import type { PerformanceData } from '../../types';
import MicroEvalCard from './MicroEvalCard';
import './Performance.css';

/** Match the live comparison response. No fixture metrics are merged into it. */
type Strategy = Pick<PerformanceData['searchStrategies'][number],
  'strategy' | 'observedMs' | 'modeledCostPerThousandUsd' | 'products' | 'rerank' | 'extractedFilters'> & {
    shares_storefront_executor?: boolean;
    hardConstraintsEnforced?: unknown;
    searchPlan?: unknown;
    relaxations?: unknown[];
  };
interface Comparison {
  query: string;
  strategies: Strategy[];
  sharedQueryEmbeddingObservedMs?: number;
  receipt?: { comparisonId: string; persisted: boolean };
  measurementAssumptions?: { latency?: string; cost?: string; quality?: string };
}
const measured = (value: number | undefined, unit: string) =>
  typeof value === 'number' && Number.isFinite(value) ? `${value}${unit}` : 'Not reported';

export default function Performance() {
  const { data, loading, error: metricsError } = useObservatoryData<PerformanceData>({ key: 'performance' });
  const [query, setQuery] = useState(CANONICAL_ANNA_QUERY);
  const [result, setResult] = useState<Comparison | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => () => abortRef.current?.abort(), []);

  async function run(event: FormEvent) {
    event.preventDefault();
    if (running || !query.trim()) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setResult(null);
    setError(null);
    try {
      const response = await apiFetch(`/api/observatory/search-strategies/compare?query=${encodeURIComponent(query.trim())}`, { signal: controller.signal });
      if (!response.ok) throw new Error(`Comparison unavailable (HTTP ${response.status}).`);
      const payload: Comparison = await response.json();
      if (!Array.isArray(payload.strategies) || !payload.strategies.length) throw new Error('No strategy observations were returned.');
      if (!controller.signal.aborted) setResult(payload);
    } catch (reason) {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Comparison unavailable.');
    } finally {
      if (!controller.signal.aborted) setRunning(false);
    }
  }

  return <div className="observatory-reading-page retrieval-comparison">
    <EditorialTitle backToReferences referenceId="performance" eyebrow="Lab 2 · Measured retrieval" title="Retrieval comparison"
      summary="Compare four strategies on one query, then investigate the candidate budget. Every result below comes from an explicit run against this deployment." />
    <section className="retrieval-comparison-section" aria-labelledby="strategy-heading">
      <h2 id="strategy-heading">Compare the retrieval choices</h2>
      <p>Vector finds semantic neighbours. Full-text search adds lexical matches; RRF combines their ranks. Reranking reorders that pool. The model proposes retrieval controls. PostgreSQL enforces the hard constraints. The agentic strategy applies typed predicates before fusion and rechecks them after reranking.</p>
      <p>The first three strategies in this experiment use unconstrained inputs. A price phrase in the query does not itself become a SQL predicate. Compare their returned rows with the agentic plan before choosing a strategy.</p>
      <form onSubmit={run} className="retrieval-comparison-form">
        <label htmlFor="strategy-query">Query to compare</label>
        <div><input id="strategy-query" value={query} onChange={event => setQuery(event.target.value)} disabled={running} />
          <button disabled={running || !query.trim()} type="submit">{running ? 'Running comparison…' : 'Run on Aurora'}</button></div>
      </form>
      <p className="retrieval-comparison-note">Runs Aurora retrieval and Bedrock calls. No comparison runs on page load.</p>
      {running && <p role="status">Running the strategies sequentially after a shared query embedding…</p>}
      {error && <p role="alert">{error} No result is asserted for this attempt. Check the service and retry the same query.</p>}
      {result && <div aria-live="polite">
        <h3>Observed query: {result.query}</h3>
        <p>Shared embedding: <code>{measured(result.sharedQueryEmbeddingObservedMs, ' ms')}</code>. Recall: <strong>not measured</strong> by this comparison.</p>
        <div className="retrieval-comparison-results">{result.strategies.map(strategy => <article className="retrieval-strategy" key={strategy.strategy}>
          <h3>{strategy.strategy}</h3>
          <dl><div><dt>Observed duration</dt><dd>{measured(strategy.observedMs, ' ms')}</dd></div>
            <div><dt>Modeled cost / 1,000 queries</dt><dd>{typeof strategy.modeledCostPerThousandUsd === 'number' && Number.isFinite(strategy.modeledCostPerThousandUsd) ? `$${strategy.modeledCostPerThousandUsd.toFixed(2)}` : 'Not reported'}</dd></div></dl>
          {strategy.products?.length ? <ol aria-label={`${strategy.strategy} product order`}>{strategy.products.map(product => <li key={product.productId}>{product.name} <code>#{product.productId}</code></li>)}</ol> : <p>No products returned.</p>}
          {strategy.rerank && <p className="retrieval-comparison-note">{strategy.rerank.status === 'applied' ? `Rerank applied to ${strategy.rerank.candidates} candidates; ${strategy.rerank.returned} returned.` : `Rerank unavailable. Fallback order: ${strategy.rerank.fallbackOrder ?? 'not reported'}.`} Model: <code>{strategy.rerank.model}</code>.</p>}
          {strategy.extractedFilters && <div className="retrieval-strategy-constraints">
            <h4>Proposed constraints and executed plan</h4>
            <p>Price ceiling: {strategy.extractedFilters.priceMaxUsd == null ? 'not proposed' : `$${strategy.extractedFilters.priceMaxUsd}`}. In-stock only: {strategy.extractedFilters.inStockOnly ? 'yes' : 'no'}. Relaxation: <code>{strategy.extractedFilters.filterUsed}</code>.</p>
            <p>Categories: {strategy.extractedFilters.categories.join(', ') || 'none'}. Soft tags: {strategy.extractedFilters.tags.join(', ') || 'none'}. Taste phrase: {strategy.extractedFilters.softSignal || 'none'}.</p>
            <p>Only soft tag preferences may widen. Price, availability, explicit categories, and exclusions remain hard constraints.</p>
            {strategy.searchPlan != null && <details><summary>Inspect the typed plan and enforced constraints</summary><pre>{JSON.stringify({ plan: strategy.searchPlan, hardConstraintsEnforced: strategy.hardConstraintsEnforced, relaxations: strategy.relaxations }, null, 2)}</pre></details>}
          </div>}
        </article>)}</div>
        <div className="retrieval-comparison-receipt">
          <h3>Retain the comparison receipt</h3>
          {result.receipt ? <p>Comparison <code>{result.receipt.comparisonId}</code>: {result.receipt.persisted ? 'persisted to Aurora.' : 'not persisted. Do not treat this response as durable evidence.'}</p> : <p>No receipt was reported. Durable evidence is unconfirmed.</p>}
          <p>Use this identifier with the Lab 2 SQL checks in Workshop Studio. Recompute RRF, check eligibility, and compare candidate counts with the returned rows.</p>
          <Link to="/observatory/proof-board#retrieval-comparison">Inspect the Lab 2 proof checkpoint</Link>
        </div>
        {result.measurementAssumptions && <details><summary>Measurement assumptions returned by the service</summary>{Object.entries(result.measurementAssumptions).map(([key, value]) => <p key={key}><strong>{key}: </strong>{value}</p>)}</details>}
      </div>}
    </section>
    <section className="retrieval-comparison-section" aria-labelledby="pool-heading">
      <h2 id="pool-heading">Explain the candidate-budget tradeoff</h2>
      <p>Hold the query and eligibility rules fixed. Compare which labelled relevant rows reach the reranker as the pool changes. Keep cold and warm observations separate; do not generalize a small labelled set into a production quality rate.</p>
      <MicroEvalCard />
    </section>
    <details className="retrieval-comparison-telemetry"><summary>Supporting context: recorded tool latency</summary>
      {loading ? <p>Reading tool audit samples…</p> : metricsError ? <p>Tool audit samples are unavailable. The explicit retrieval experiments above remain available.</p> : data && data.sampleCount > 0 ? <p>Median recorded tool duration: <code>{measured(data.warmReuseP50, ' ms')}</code> across <code>{data.sampleCount}</code> samples. The API reads the latest 1,000 non-null latency rows from <code>pellier.tool_audit</code>, across tools. This is not Runtime warm-start latency or end-to-end shopper latency.</p> : <p>No tool audit latency samples are recorded. Run a lab turn before interpreting this aggregate.</p>}
      <p>Cold starts, index benchmarks, storage footprint, and latency percentiles are not measured by this endpoint.</p>
    </details>
  </div>;
}
