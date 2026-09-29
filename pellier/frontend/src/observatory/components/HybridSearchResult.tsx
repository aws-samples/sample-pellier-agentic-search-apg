/**
 * A recorded hybrid search, read as a ranking rather than as JSON.
 *
 * The plan the call ran with, then each returned product with its fused score
 * and, when the reranker ordered the list, its rerank score and how far rerank
 * moved it. The caption and columns follow the recorded search method, and a
 * declared merchandising rule is disclosed and credited with its own move. The
 * raw arguments and result stay one click away, because the JSON is still the
 * record a participant reconciles against `tool_audit`.
 */

import React from 'react';
import type { HybridResultRow, HybridSearchView, MerchandisingRule } from '../labs/hybridSearchResult';
import '../styles/evidence-depth.css';

const DASH = '—';

function fixed(value: number | null, digits: number): string {
  return value === null ? DASH : value.toFixed(digits);
}

function price(value: number | null): string {
  return value === null ? DASH : `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function Moved({ row }: { row: HybridResultRow }) {
  if (row.movedByRerank === null) return <span>{DASH}</span>;
  if (row.movedByRerank === 0) {
    return <span className="observatory-evidence-move" data-direction="same">same</span>;
  }
  const up = row.movedByRerank > 0;
  const places = Math.abs(row.movedByRerank);
  return (
    <span
      className="observatory-evidence-move"
      data-direction={up ? 'up' : 'down'}
      aria-label={`${up ? 'Up' : 'Down'} ${places} ${places === 1 ? 'place' : 'places'} from RRF order to rerank order`}
    >
      <span aria-hidden="true">{up ? '▲' : '▼'} {places}</span>
    </span>
  );
}

function methodSentence(view: HybridSearchView): string {
  const method = view.searchMethod;
  switch (view.ordering) {
    case 'rerank':
      return `Recorded method ${method}: the reranker ordered the list, so Final is the returned order after rerank.`;
    case 'rrf':
      return `Recorded method ${method}: no reranker ran, so Final is fused RRF order.`;
    case 'rrf-fallback':
      return `Recorded method ${method}: the reranker returned no ranking, so Final falls back to fused RRF order.`;
    default:
      return method
        ? `Recorded method ${method} is not one this view maps, so Final is only the returned order.`
        : 'This record does not name its search method, so Final is only the returned order.';
  }
}

function ruleSentence(rule: MerchandisingRule, ordering: HybridSearchView['ordering']): string {
  const from = rule.fromRank ?? DASH;
  const to = rule.toRank ?? DASH;
  const step = ordering === 'rerank' ? 'the reranker’s' : 'the ranking’s';
  return `Then declared rule ${rule.ruleId ?? DASH} promoted ${rule.product ?? DASH} from ${from} to ${to}; that move is the rule’s, not ${step}.`;
}

function poolSentence(view: HybridSearchView): string {
  const shown = `RRF rank orders the ${view.rows.length} shown products by fused score`;
  return view.poolSize === null
    ? `${shown}; this record does not give the size of the fused pool.`
    : `${shown}; the fused pool held ${view.poolSize} candidates, and this record does not give each product’s rank in that pool.`;
}

export function HybridSearchResult({
  view,
  raw,
}: {
  view: HybridSearchView;
  /** The recorded args and result, rendered inside the raw disclosure. */
  raw: React.ReactNode;
}) {
  const reranked = view.ordering === 'rerank';
  const showRerankScore = reranked || (view.ordering === 'unrecorded' && view.rows.some((row) => row.rerankScore !== null));
  const showAfterRerank = reranked && view.merchandisingReordered;
  const shown = view.rows.length;
  return (
    <div className="observatory-evidence-depth" data-testid="hybrid-search-result" data-ordering={view.ordering}>
      <ul className="observatory-evidence-plan" aria-label="Search plan as recorded">
        {view.plan.map((item) => (
          <li key={item.field} title={item.full ?? undefined}>
            <span>{item.field}</span> <b>{item.value ?? DASH}</b>
          </li>
        ))}
      </ul>
      {view.merchandising.length > 0 ? (
        <div className="observatory-evidence-merch" role="note" aria-label="Merchandising disclosed in this result">
          <strong>Merchandising</strong>
          {view.merchandising.map((rule, index) => (
            <p key={`${rule.ruleId ?? 'rule'}-${index}`}>
              <code>{rule.ruleId ?? DASH}</code>
              {rule.signal ? <span> ({rule.signal})</span> : null} promoted {rule.product ?? DASH} from{' '}
              {rule.fromRank ?? DASH} to {rule.toRank ?? DASH}.{rule.reason ? ` ${rule.reason}` : ''}
            </p>
          ))}
        </div>
      ) : null}
      <div className="observatory-evidence-table-wrap">
        <table className="observatory-evidence-rank">
          <caption>
            {methodSentence(view)}{' '}
            {view.merchandising.map((rule) => `${ruleSentence(rule, view.ordering)} `)}
            {poolSentence(view)}
          </caption>
          <thead>
            <tr>
              <th scope="col">Final</th>
              <th scope="col">Product</th>
              <th scope="col">RRF score</th>
              <th scope="col">RRF rank of {shown} shown</th>
              {showRerankScore ? <th scope="col">Rerank score</th> : null}
              {showAfterRerank ? <th scope="col">After rerank</th> : null}
              {reranked ? <th scope="col">Moved by rerank</th> : null}
              <th scope="col">Price</th>
            </tr>
          </thead>
          <tbody>
            {view.rows.map((row) => (
              <tr key={`${row.final}-${row.productId ?? row.name}`}>
                <td className="num">{row.final}</td>
                <th scope="row">
                  {row.name}
                  {row.merchandising ? (
                    <span className="observatory-evidence-promoted">
                      Promoted by rule, {row.merchandising.fromRank ?? DASH} to {row.merchandising.toRank ?? DASH}
                    </span>
                  ) : null}
                </th>
                <td className="num">{fixed(row.rrfScore, 5)}</td>
                <td className="num">{row.rrfRank ?? DASH}</td>
                {showRerankScore ? <td className="num">{fixed(row.rerankScore, 3)}</td> : null}
                {showAfterRerank ? <td className="num">{row.rerankRank ?? DASH}</td> : null}
                {reranked ? <td><Moved row={row} /></td> : null}
                <td className="num">{price(row.price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="observatory-evidence-raw">
        <summary>
          Raw arguments and result ({view.rawCharacters.toLocaleString()} characters)
        </summary>
        {raw}
      </details>
    </div>
  );
}
