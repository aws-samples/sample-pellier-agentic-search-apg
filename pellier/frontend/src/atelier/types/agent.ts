/**
 * Atelier Observatory — Agent type
 *
 * Represents one of the 5 peer specialist agents in the system.
 *
 * Requirements: 16.5
 */

export interface Agent {
  numeral: string;
  name: string;
  role: string;
  status: 'shipped' | 'exercise';
  tools: string[];
  model: string;
  temperature: number;
  exerciseFiles?: string[];
}
