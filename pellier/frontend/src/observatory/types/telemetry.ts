/**
 * Pellier Observatory — Telemetry types
 *
 * Represents a single step in the telemetry timeline for a session.
 *
 * Requirements: 16.5
 */

import type {
  EvidenceLedgerEventKind,
  EvidenceLedgerPhase,
  EvidenceLedgerProvenance,
  EvidenceLedgerStatus,
  EvidenceReference,
} from '../../shared/evidenceLedger';

export interface TelemetryPanel {
  index: number;
  category: 'both' | 'managed' | 'owned' | 'teaching';
  title: string;
  description: string;
  status:
    | 'complete'
    | 'running'
    | 'queued'
    /** The tool ran and returned data without stating an outcome. */
    | 'recorded'
    | EvidenceLedgerStatus;
  durationMs: number;
  agent?: string;
  sql?: string;
  rows?: Record<string, unknown>[];
  meta?: string;
  eventKind?: EvidenceLedgerEventKind;
  phase?: EvidenceLedgerPhase;
  provenance?: EvidenceLedgerProvenance;
  evidenceRef?: EvidenceReference;
  occurredAt?: string | null;
  turnId?: string;
  traceId?: string | null;
}
