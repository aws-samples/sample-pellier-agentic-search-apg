import React, { useMemo } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { lookupVocab } from '../../shared';

const PROOF_ANCHOR_LABELS: Record<string, string> = {
  'runtime-gateway-policy': 'Runtime, Gateway, and policy proof',
  'marco-floor-check': "Marco's check_inventory proof",
  'retrieval-comparison': 'retrieval comparison proof',
  'audit-ledger': 'audit ledger proof',
};

function anchorLabel(hash: string): string {
  const anchor = hash.replace(/^#/, '');
  return PROOF_ANCHOR_LABELS[anchor] ?? 'the matching proof section';
}

const ObservatoryContextBanner: React.FC = () => {
  const location = useLocation();

  const context = useMemo(() => {
    const params = new URLSearchParams(location.search);
    if (params.get('from') !== 'pellier') return null;
    const trace = params.get('trace') ?? 'tool.transparency';
    const vocab = lookupVocab(trace);
    return {
      label: vocab.label,
      trace,
      section: location.pathname.endsWith('/audit-proof')
        ? 'audit ledger proof'
        : anchorLabel(location.hash),
    };
  }, [location.pathname, location.search, location.hash]);

  if (!context) return null;

  const cleanPath = `${location.pathname}${location.hash}`;

  return (
    <aside
      className="observatory-context-banner"
      data-testid="observatory-context-banner"
      aria-label="Pellier trace context"
    >
      <div className="observatory-context-copy">
        <span className="observatory-context-kicker">Pellier trace</span>
        <strong>{context.label}</strong>
        <span>
          Landed here from a shopper-facing trace chip. This Pellier Observatory view shows {context.section}.
        </span>
      </div>
      <div className="observatory-context-actions">
        <Link to="/" className="pellier-action-quiet">
          Return to Storefront
        </Link>
        <Link to={cleanPath} className="pellier-action-quiet">
          Keep proof
        </Link>
      </div>
    </aside>
  );
};

export default ObservatoryContextBanner;
