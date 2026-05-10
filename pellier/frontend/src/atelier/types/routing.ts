/**
 * Atelier Observatory — Routing types
 *
 * Represents one of the 3 orchestration routing patterns.
 *
 * Requirements: 16.5
 */

export interface RoutingPattern {
  name: string;
  slug: string;
  description: string;
  isActive: boolean;
  agents: string[];
  codeSnippet: string;
  diagram?: string;
}
