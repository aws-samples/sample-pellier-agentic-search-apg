/**
 * Atelier Observatory — Architecture types
 *
 * Represents one of the 8 architectural concepts in the system.
 *
 * Requirements: 16.5
 */

export interface ArchitectureConcept {
  numeral: string;
  category: 'both' | 'managed' | 'owned' | 'teaching';
  title: string;
  role: string;
  description: string;
  codeSnippet: string;
  slug: string;
}
