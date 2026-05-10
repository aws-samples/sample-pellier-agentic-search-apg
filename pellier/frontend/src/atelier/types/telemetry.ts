/**
 * Atelier Observatory — Telemetry types
 *
 * Represents a single step in the telemetry timeline for a session.
 *
 * Requirements: 16.5
 */

export interface TelemetryPanel {
  index: number;
  category: 'both' | 'managed' | 'owned' | 'teaching';
  title: string;
  description: string;
  status: 'complete' | 'running' | 'queued';
  durationMs: number;
  agent?: string;
  sql?: string;
  rows?: Record<string, unknown>[];
  meta?: string;
}
