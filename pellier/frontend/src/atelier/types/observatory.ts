/**
 * Atelier Observatory — Observatory types
 *
 * Wide-angle dashboard summary data.
 *
 * Requirements: 16.5
 */

export interface ObservatorySummary {
  activeSessions: number;
  totalSessions: number;
  agentStatus: { name: string; status: 'live' | 'idle' }[];
  toolInvocations: number;
  memoryItems: { stm: number; ltm: number };
  performanceHeadlines: { label: string; value: string; unit?: string }[];
  lastUpdated: string;
}
