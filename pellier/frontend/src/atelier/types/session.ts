/**
 * Atelier Observatory — Session types
 *
 * Session represents a single conversation between a persona and the agentic system.
 * SessionDetail extends Session with full chat, telemetry, and brief data.
 *
 * Requirements: 16.5
 */

import type { ChatTurn } from './chat';
import type { TelemetryPanel } from './telemetry';
import type { BriefContent } from './brief';

export interface Session {
  id: string;
  personaId: string;
  openingQuery: string;
  elapsedMs: number;
  agentCount: number;
  routingPattern: string;
  timestamp: string;
  status: 'complete' | 'active';
}

export interface SessionDetail extends Session {
  chat: ChatTurn[];
  telemetry: TelemetryPanel[];
  brief: BriefContent;
}
