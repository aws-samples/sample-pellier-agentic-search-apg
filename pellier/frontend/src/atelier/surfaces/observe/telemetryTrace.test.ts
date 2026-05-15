import { describe, expect, it } from 'vitest';
import sessionMarco from '../../fixtures/session-marco-opening-demo.json';
import type { SessionDetail } from '../../types';
import {
  getTopPickProduct,
  parseTelemetryPanelIndex,
  resolveTracePanelIndex,
} from './telemetryTrace';

describe('telemetryTrace', () => {
  it('parses panel-N and #telemetry-N refs', () => {
    expect(parseTelemetryPanelIndex('panel-3')).toBe(3);
    expect(parseTelemetryPanelIndex('#telemetry-4')).toBe(4);
    expect(parseTelemetryPanelIndex('trace 2')).toBe(2);
  });

  it('resolves marco camp shirt to panel-3', () => {
    const session = sessionMarco as SessionDetail;
    const pick = getTopPickProduct(session);
    expect(pick?.name).toContain('Camp Shirt');
    expect(resolveTracePanelIndex(pick, session.telemetry)).toBe(3);
  });
});
