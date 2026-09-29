/**
 * A recorded hybrid search, read as a ranking rather than as JSON.
 *
 * The plan the call ran with, then each returned product with its fused score,
 * its order by that score, its rerank score, and how far rerank moved it. The
 * raw arguments and result stay one click away, because the JSON is still the
 * record a participant reconciles against `tool_audit`.
 */

import React from 'react';
import type { HybridResultRow, HybridSearchView } from '../labs/hybridSearchResult';
import '../styles/evidence-depth.css';

const DASH = '—';

function fixed(value: number | null, digits: number): string {
  return value === null ? DASH : value.toFixed(digits);
}

function price(value: number | null): string {
  return value === null ? DASH : `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function Moved({ row }: { row: HybridResultRow }) {
  if (row.moved === null) return <span>{DASH}</span>;
  if (row.moved === 0) {
    return <span className="observatory-evidence-move" data-direction="same">same</span>;
  }
  const up = row.moved > 0;
  const places = Math.abs(row.moved);
  return (
    <span
      className="observatory-evidence-move"
      data-direction={up ? 'up' : 'down'}
      aria-label={`${up ? 'Up' : 'Down'} ${places} ${places === 1 ? 'place' : 'places'} from RRF order`}
    >
      <span aria-hidden="true">{up ? '▲' : '▼'} {places}</span>
    </span>
  );
}

export function HybridSearchResult({
  view,
  raw,
}: {
  view: HybridSearchView;
  /** The recorded args and result, rendered inside the raw disclosure. */
  raw: React.ReactNode;
}) {
  return (
    <div className="observatory-evidence-depth" data-testid="hybrid-search-result">
      <ul className="observatory-evidence-plan" aria-label="Search plan as recorded">
        {view.plan.map((item) => (
          <li key={item.field} title={item.full ?? undefined}>
            <span>{item.field}</span> <b>{item.value ?? DASH}</b>
          </li>
        ))}
      </ul>
      <div className="observatory-evidence-table-wrap">
        <table className="observatory-evidence-rank">
          <caption>
            Final is the returned order after rerank. RRF rank orders these{' '}
            {view.rows.length} products by fused score
            {view.poolSize !== null ? `; the fused pool held ${view.poolSize} candidates` : ''}.
          </caption>
          <thead>
            <tr>
              <th scope="col">Final</th>
              <th scope="col">Product</th>
              <th scope="col">RRF score</th>
              <th scope="col">RRF rank</th>
              <th scope="col">Rerank score</th>
              <th scope="col">Moved</th>
              <th scope="col">Price</th>
            </tr>
          </thead>
          <tbody>
            {view.rows.map((row) => (
              <tr key={`${row.final}-${row.productId ?? row.name}`}>
                <td className="num">{row.final}</td>
                <th scope="row">{row.name}</th>
                <td className="num">{fixed(row.rrfScore, 5)}</td>
                <td className="num">{row.rrfRank ?? DASH}</td>
                <td className="num">{fixed(row.rerankScore, 3)}</td>
                <td><Moved row={row} /></td>
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
