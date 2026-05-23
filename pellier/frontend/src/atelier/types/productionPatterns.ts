/**
 * Atelier Observatory — Production Patterns types
 *
 * Four production patterns sit underneath every shipped agent: identity,
 * guardrails, multi-tenancy & STM hygiene, and tool publishing. The
 * default builder path runs without any of them by design — they're the
 * seams you reach for once the prototype is real.
 */

interface CrossLink {
  label: string;
  to: string;
}

export interface IdentityPattern {
  numeral: string;
  slug: 'identity';
  title: string;
  role: string;
  summary: string;
  shipped: boolean;
  shippedNote?: string;
  category: 'auth';
  namespacePattern: {
    anon: string;
    signedIn: string;
    note: string;
  };
  codeSnippet: string;
  whatToReachFor: string;
  crossLinks: CrossLink[];
}

export interface GuardrailsPattern {
  numeral: string;
  slug: 'guardrails';
  title: string;
  role: string;
  summary: string;
  shipped: boolean;
  shippedNote?: string;
  category: 'policy';
  layers: { name: string; where: string; what: string }[];
  codeSnippet: string;
  crossLinks: CrossLink[];
}

export interface MultitenancyPattern {
  numeral: string;
  slug: 'multitenancy';
  title: string;
  role: string;
  summary: string;
  shipped: boolean;
  shippedNote?: string;
  category: 'ops';
  concerns: { concern: string; answer: string }[];
  codeSnippet: string;
  crossLinks: CrossLink[];
}

export interface ToolPublishingPattern {
  numeral: string;
  slug: 'tool-publishing';
  title: string;
  role: string;
  summary: string;
  shipped: boolean;
  shippedNote?: string;
  category: 'scaling';
  surfaces: { name: string; where: string; purpose: string; tradeoff: string }[];
  codeSnippet: string;
  crossLinks: CrossLink[];
}

export type ProductionPattern =
  | IdentityPattern
  | GuardrailsPattern
  | MultitenancyPattern
  | ToolPublishingPattern;

export interface ProductionPatternsData {
  summary: string;
  patterns: ProductionPattern[];
}
