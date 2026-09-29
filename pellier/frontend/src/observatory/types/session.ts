/**
 * Pellier Observatory — Session types
 *
 * Session represents a single conversation between a persona and the agentic system.
 * SessionDetail extends Session with full chat, telemetry, and brief data.
 *
 * Requirements: 16.5
 */

import type { ChatTurn } from './chat';
import type { TelemetryPanel } from './telemetry';
import type { BriefContent } from './brief';
import type { EvidenceLedger } from '../../shared/evidenceLedger';

export interface Session {
  id: string;
  personaId: string;
  openingQuery: string;
  elapsedMs: number;
  agentCount: number;
  routingPattern: string;
  timestamp: string;
  status: 'complete' | 'active' | 'failed' | 'denied-before-execution' | 'unknown';
  /** Recorded by the chat pipeline, or a direct run: a probe, proof, or Gateway or Operator call. */
  provenance?: 'conversation' | 'direct';
}

export interface SessionDetail extends Session {
  chat: ChatTurn[];
  telemetry: TelemetryPanel[];
  evidenceLedger?: EvidenceLedger | null;
  brief: BriefContent;
}
